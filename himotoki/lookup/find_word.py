"""
Database word lookup functions.
"""

from typing import Optional, List, Set, Union

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from himotoki.db.models import Entry, KanjiText, KanaText
from himotoki.characters import is_kana, as_hiragana
from himotoki.types import WordMatch, ConjData, CompoundWord
from himotoki.scoring.calc_score import MAX_WORD_LENGTH
from himotoki.lookup.constants import SUPPRESS_SINGLE_TOKEN_SEQS
from himotoki.lookup.conj_data import get_word_conj_data
from himotoki.scoring.caches import _WORD_CACHE

def find_word(
    session: Session,
    word: str,
    root_only: bool = False,
) -> List[WordMatch]:
    """
    Find words matching the given text in the database.
    
    Args:
        session: Database session
        word: Text to search for
        root_only: If True, only return root entries (not conjugations)
    
    Returns:
        List of WordMatch objects
    """
    # Include DB path so caches from different databases (e.g. test fixtures)
    # do not collide. Session id alone is insufficient across connection pools.
    bind = session.get_bind()
    db_id = getattr(getattr(bind, "url", None), "database", None) or id(bind)
    cache_key = (db_id, word, root_only)
    if cache_key in _WORD_CACHE:
        return _WORD_CACHE[cache_key]
    
    if len(word) > MAX_WORD_LENGTH:
        return []
    
    # Determine which table to search based on word content
    if is_kana(word):
        table = KanaText
    else:
        table = KanjiText
    
    if root_only:
        # Join with entry to filter by root_p
        query = (
            select(table)
            .join(Entry, table.seq == Entry.seq)
            .where(and_(table.text == word, Entry.root_p == True))
        )
    else:
        query = select(table).where(table.text == word)
    
    results = session.execute(query).scalars().all()
    results = [r for r in results if r.seq not in SUPPRESS_SINGLE_TOKEN_SEQS]
    matches = [WordMatch(reading=r) for r in results]
    _WORD_CACHE[cache_key] = matches
    return matches


def find_word_as_hiragana(
    session: Session,
    word: str,
    exclude_seqs: Optional[Set[int]] = None,
) -> List[WordMatch]:
    """
    Find words by converting katakana to hiragana and searching.
    
    Args:
        session: Database session
        word: Text to search for (may contain katakana)
        exclude_seqs: Seqs to exclude from results
    
    Returns:
        List of WordMatch objects with proxy text
    """
    hiragana = as_hiragana(word)
    if hiragana == word:
        return []
    
    words = find_word(session, hiragana, root_only=True)
    
    if exclude_seqs:
        words = [w for w in words if w.seq not in exclude_seqs]
    
    # TODO: Create proxy text objects that preserve original form
    return words


def find_word_full(
    session: Session,
    word: str,
    as_hiragana_lookup: bool = False,
    counter: Union[bool, int] = False,
) -> List[WordMatch]:
    """
    Full word lookup with multiple strategies.
    
    Args:
        session: Database session
        word: Text to search for
        as_hiragana_lookup: If True, also try converting katakana to hiragana
        counter: If True, look for counter patterns
    
    Returns:
        List of WordMatch objects
    """
    simple_words = find_word(session, word)
    results = list(simple_words)
    
    # Add suffix lookup (find_word_suffix)
    from himotoki.suffixes import find_word_suffix
    suffix_words = find_word_suffix(session, word, matches=simple_words)
    results.extend(suffix_words)
    
    if as_hiragana_lookup:
        exclude = {w.seq for w in simple_words}
        results.extend(find_word_as_hiragana(session, word, exclude))
    
    # TODO: Add counter lookup
    
    return results


# ============================================================================
# Conjugation-based Lookup Functions
# ============================================================================

def find_word_with_conj_prop(
    session: Session,
    word: str,
    filter_fn: callable,
    allow_root: bool = False,
) -> List[WordMatch]:
    """
    Find words matching text with conjugation property filter.
    
    Ports ichiran's find-word-with-conj-prop from dict-grammar.lisp.
    
    Args:
        session: Database session
        word: Text to search for
        filter_fn: Function to filter ConjData objects
        allow_root: If True, also return root forms
    
    Returns:
        List of WordMatch objects with conjugation IDs set
    """
    results = []
    for match in find_word_full(session, word):
        conj_data = get_word_conj_data(session, match)
        conj_data_filtered = [cd for cd in conj_data if filter_fn(cd)]
        # Use conj_id (foreign key to Conjugation.id), not prop.id
        # This matches ichiran's (conj-id (conj-data-prop cdata))
        conj_ids = [cd.prop.conj_id if cd.prop else None for cd in conj_data_filtered]
        conj_ids = [cid for cid in conj_ids if cid is not None]
        
        if conj_data_filtered or (not conj_data and allow_root):
            match.conjugations = conj_ids if conj_ids else None
            results.append(match)
    
    return results


def find_word_with_conj_type(
    session: Session,
    word: str,
    *conj_types: int,
) -> List[WordMatch]:
    """
    Find words matching text with specific conjugation types.
    
    Ports ichiran's find-word-with-conj-type from dict-grammar.lisp.
    
    Args:
        session: Database session
        word: Text to search for
        *conj_types: Conjugation type IDs to match
    
    Returns:
        List of WordMatch objects
    """
    def filter_fn(cdata: ConjData) -> bool:
        if cdata.prop and hasattr(cdata.prop, 'conj_type'):
            return cdata.prop.conj_type in conj_types
        return False
    
    return find_word_with_conj_prop(session, word, filter_fn)

