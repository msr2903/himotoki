"""
Conjugation data lookup functions.
"""

from typing import Optional, List, Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from himotoki.db.models import Conjugation, ConjProp, ConjSourceReading
from himotoki.types import ConjData, WordMatch, CompoundWord
from himotoki.scoring.caches import _CONJ_DATA_CACHE
from himotoki.lookup.constants import CONJ_TYPE_NAMES

# Blocklist for spurious conjugation relationships in the database
# These are (seq, from_seq) pairs that should NOT be treated as conjugations
# because the seq entry is primarily a different word (e.g., particle) that
# happens to have the same reading as a conjugated form
# Example: Particle よ (seq 2029090) looks like adjective stem of いい (seq 2820690)
#          but standalone よ should be parsed as particle, not adjective stem
BLOCKED_CONJUGATIONS = {
    (2029090, 2820690),  # よ (particle) ← いい (adj-ix adjective stem)
}


def get_conj_data(
    session: Session,
    seq: int,
    from_seq: Optional[int] = None,
    conj_ids: Optional[List[int]] = None,
    texts: Optional[List[str]] = None,
) -> List[ConjData]:
    """
    Get conjugation data for an entry.
    
    Args:
        session: Database session
        seq: Entry sequence number
        from_seq: If provided, only get conjugations from this source
        conj_ids: If provided, only get these specific conjugation IDs
        texts: If provided, only get conjugations for these texts
    
    Returns:
        List of ConjData objects
    """
    global _CONJ_DATA_CACHE
    
    # Create cache key from immutable inputs
    cache_key = (seq, from_seq, tuple(sorted(conj_ids)) if conj_ids else None, 
                 tuple(sorted(texts)) if texts else None)
    
    # Check cache first
    if cache_key in _CONJ_DATA_CACHE:
        return _CONJ_DATA_CACHE[cache_key]
    
    # Build query for conjugations
    query = select(Conjugation).where(Conjugation.seq == seq)
    
    if from_seq is not None:
        query = query.where(Conjugation.from_seq == from_seq)
    if conj_ids:
        query = query.where(Conjugation.id.in_(conj_ids))
    
    conjugations = session.execute(query).scalars().all()
    
    # Filter out blocked conjugation relationships
    conjugations = [c for c in conjugations if (c.seq, c.from_seq) not in BLOCKED_CONJUGATIONS]
    
    if not conjugations:
        _CONJ_DATA_CACHE[cache_key] = []
        return []
    
    conj_ids_list = [c.id for c in conjugations]
    
    # Batch-fetch all source readings in one query
    src_query = select(ConjSourceReading).where(
        ConjSourceReading.conj_id.in_(conj_ids_list)
    )
    if texts:
        src_query = src_query.where(ConjSourceReading.text.in_(texts))
    
    all_src_readings = session.execute(src_query).scalars().all()
    src_by_conj: dict[int, list] = {}
    for sr in all_src_readings:
        src_by_conj.setdefault(sr.conj_id, []).append((sr.text, sr.source_text))
    
    # Batch-fetch all conjugation properties in one query
    all_props = session.execute(
        select(ConjProp).where(ConjProp.conj_id.in_(conj_ids_list))
    ).scalars().all()
    props_by_conj: dict[int, list] = {}
    for prop in all_props:
        props_by_conj.setdefault(prop.conj_id, []).append(prop)
    
    result = []
    for conj in conjugations:
        src_map = src_by_conj.get(conj.id, [])
        
        if texts and not src_map:
            continue
        
        for prop in props_by_conj.get(conj.id, []):
            result.append(ConjData(
                seq=conj.seq,
                from_seq=conj.from_seq,
                via=conj.via,
                prop=prop,
                src_map=src_map,
            ))
    
    # Cache result (LRUCache handles eviction automatically)
    _CONJ_DATA_CACHE[cache_key] = result
    
    return result


def get_word_conj_data(
    session: Session,
    word: Union[WordMatch, CompoundWord],
) -> List[ConjData]:
    """
    Get conjugation data for a word match.
    
    Ports ichiran's word-conj-data method from dict.lisp.
    
    For simple words, gets conjugation data from the word's seq.
    For compound words, gets conjugation data from the last word.
    
    Args:
        session: Database session
        word: WordMatch or CompoundWord
    
    Returns:
        List of ConjData objects
    """
    if isinstance(word, CompoundWord):
        # For compound words, get conj data from last word
        if word.words:
            return get_word_conj_data(session, word.words[-1])
        return []
    
    # For simple WordMatch
    seq = word.seq
    conj_ids = word.conjugations if word.conjugations and word.conjugations != 'root' else None
    
    if isinstance(conj_ids, list):
        return get_conj_data(session, seq, conj_ids=conj_ids, texts=[word.text])
    elif not word.is_root:
        return get_conj_data(session, seq, texts=[word.text])
    else:
        return []


def get_conj_type_name(
    session: Session,
    word: Union[WordMatch, CompoundWord],
) -> Optional[str]:
    """
    Get human-readable conjugation type name for a word.
    
    Looks up the conjugation data for the word and returns the
    human-readable name from CONJ_TYPE_NAMES mapping.
    
    Args:
        session: Database session
        word: WordMatch or CompoundWord
    
    Returns:
        Human-readable conjugation type name (e.g., "Past (~ta)", "Conjunctive (~te)")
        or None if no conjugation data found
    """
    conj_data = get_word_conj_data(session, word)
    if not conj_data:
        return None
    
    # Get the first conjugation data entry
    cd = conj_data[0]
    if cd.prop and cd.prop.conj_type:
        return CONJ_TYPE_NAMES.get(cd.prop.conj_type)
    
    return None


def get_conj_neg(
    session: Session,
    word: Union[WordMatch, CompoundWord],
) -> bool:
    """
    Get whether a word is in negative form.
    
    Args:
        session: Database session
        word: WordMatch or CompoundWord
    
    Returns:
        True if the word is in negative form, False otherwise
    """
    conj_data = get_word_conj_data(session, word)
    if not conj_data:
        return False
    
    cd = conj_data[0]
    if cd.prop:
        return bool(cd.prop.neg)
    
    return False


def get_conj_fml(
    session: Session,
    word: Union[WordMatch, CompoundWord],
) -> bool:
    """
    Get whether a word is in formal/polite form.
    
    Args:
        session: Database session
        word: WordMatch or CompoundWord
    
    Returns:
        True if the word is in formal form, False otherwise
    """
    conj_data = get_word_conj_data(session, word)
    if not conj_data:
        return False
    
    cd = conj_data[0]
    if cd.prop:
        return bool(cd.prop.fml)
    
    return False


def get_source_text(
    session: Session,
    word: Union[WordMatch, CompoundWord],
) -> Optional[str]:
    """
    Get source text (dictionary form) for a conjugated word.
    
    Looks up the conjugation data and finds the matching src_map entry
    to return the source text (e.g., "だ" for "で", "食べる" for "食べた").
    
    Args:
        session: Database session
        word: WordMatch or CompoundWord
    
    Returns:
        Source text (dictionary form) or None if not found
    """
    conj_data = get_word_conj_data(session, word)
    if not conj_data:
        return None
    
    # Get the word's text to match against src_map
    word_text = word.text
    
    # Search through all conjugation data entries
    for cd in conj_data:
        if cd.src_map:
            for text, src_text in cd.src_map:
                if text == word_text:
                    return src_text
    
    return None
