"""
Word lookup and scoring module for himotoki.
Ports ichiran's dict.lisp word lookup and scoring functionality.

This module provides:
- find_word: Database lookup for words
- calc_score: Complex scoring algorithm for word segments
- Segment/SegmentList: Data structures for word matches
- Length multipliers and scoring coefficients
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Union, Any, Set
from functools import lru_cache
from collections import OrderedDict

from himotoki.raw_types import RawKanaReading, RawKanjiReading

from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import Session

from himotoki.db.models import (
    Entry, KanjiText, KanaText, Sense, Gloss, SenseProp,
    Conjugation, ConjProp, ConjSourceReading,
)
from himotoki.characters import (
    is_kana, is_katakana, is_hiragana, has_kanji, as_hiragana,
    mora_length, count_char_class, get_char_class,
)

# Import CounterText for type checking in calc_score
# This is imported here to avoid circular imports
def _is_counter_text(obj) -> bool:
    """Check if object is a CounterText without importing the class."""
    return type(obj).__name__ == 'CounterText'


# ============================================================================
# Constants (ported from ichiran's dict-errata.lisp)
# ============================================================================

# Maximum word length to search for
MAX_WORD_LENGTH = 50

# Score cutoff - words below this score are filtered out
# This must filter out ONLY bad kana spellings, and NOT filter out any kanji spellings
SCORE_CUTOFF = 5

# Length coefficient sequences (from ichiran's *length-coeff-sequences*)
# Format: coefficient for mora length 1, 2, 3, 4, 5...
LENGTH_COEFF_SEQUENCES = {
    'strong': [0, 1, 8, 24, 40, 60],  # Index 0 unused, 1-based
    'weak': [0, 1, 4, 9, 16, 25, 36],
    'tail': [0, 4, 9, 16, 24],
    'ltail': [0, 4, 12, 18, 24],
}

# Cutoff ratio for identical word scores
IDENTICAL_WORD_SCORE_CUTOFF = 0.5

# Gap penalty per character for ungapped text
GAP_PENALTY = -500

# Parts of speech that can be conjugated
POS_WITH_CONJ_RULES = frozenset([
    'v1', 'v1s', 'v5aru', 'v5b', 'v5g', 'v5k', 'v5k-s', 'v5m', 'v5n',
    'v5r', 'v5r-i', 'v5s', 'v5t', 'v5u', 'v5u-s', 'v5uru', 'vk', 'vs',
    'vs-i', 'vs-s', 'vz', 'adj-i', 'adj-ix', 'adj-na', 'adj-no',
])

# Copulae seqs (だ, です, etc.) - from ichiran's *copulae*
COPULAE: Set[int] = {2089020, 1628500}  # だ, です

# Skip words - seq of words that aren't really words, like suffixes etc.
# From ichiran's *skip-words*
SKIP_WORDS: Set[int] = {
    2458040,   # てもいい
    2822120,   # ても良い
    2013800,   # ちゃう
    2108590,   # とく
    2029040,   # ば
    2428180,   # い
    2654250,   # た
    2561100,   # うまいな
    2210270,   # ませんか
    2210710,   # ましょうか
    2257550,   # ない
    2210320,   # ません
    2017560,   # たい
    2394890,   # とる
    2194000,   # であ
    2568000,   # れる/られる
    2537250,   # しようとする
    2760890,   # 三箱
    2831062,   # てる
    2831063,   # てく
    2029030,   # ものの
    2568020,   # せる
    900000,    # たそう (custom)
}

# Final particles - words that only have meaning when they're final
# From ichiran's *final-prt*
FINAL_PRT: Set[int] = {
    2017770,   # かい
    2425930,   # なの
    2130430,   # け っけ
    2029130,   # ぞ
    2834812,   # ぜ
    2718360,   # がな
    2201380,   # わい
    2722170,   # のう
    2751630,   # かいな
}

# Semi-final particles - final, but also have other uses
# From ichiran's *semi-final-prt* (which includes *final-prt*)
SEMI_FINAL_PRT: Set[int] = FINAL_PRT | {
    2029120,   # さ
    2086640,   # し
    2029110,   # な
    2029080,   # ね
    2029100,   # わ
}

# Non-final particles - don't get final bonus
# From ichiran's *non-final-prt*
NON_FINAL_PRT: Set[int] = {
    2139720,   # ん
}

# Words that get no kanji break penalty
# From ichiran's *no-kanji-break-penalty*
NO_KANJI_BREAK_PENALTY: Set[int] = {
    1169870,   # 飲む
    1198360,   # 会議
    1277450,   # 好き
    2028980,   # で
    1423000,   # 着る
    1164690,   # 一段
    1587040,   # 言う
    2827864,   # なので
}

# Import conjugation constants from central location
from himotoki.constants import (
    CONJ_ADVERBIAL, CONJ_ADJECTIVE_STEM, CONJ_NEGATIVE_STEM,
    CONJ_CAUSATIVE_SU, CONJ_ADJECTIVE_LITERARY,
    CONJ_TYPE_NAMES, WEAK_CONJ_FORMS, SKIP_CONJ_FORMS,
    CONJ_VOLITIONAL, CONJ_TE, CONJ_POTENTIAL, CONJ_IMPERATIVE,
)

# Archaic words cache - populated on first use
_ARCHAIC_CACHE: Optional[Set[int]] = None


# ============================================================================
# LRU Cache Implementation
# ============================================================================
# A simple LRU cache using OrderedDict to prevent memory leaks in long-running
# processes. This replaces the previous unbounded Dict + "clear half" approach.

class LRUCache:
    """
    A simple LRU (Least Recently Used) cache with a maximum size.
    
    Uses OrderedDict to maintain insertion/access order. When the cache
    reaches capacity, the least recently used item is evicted.
    
    Thread-safety: This implementation is NOT thread-safe. For multi-threaded
    use, wrap access with a lock.
    """
    
    def __init__(self, maxsize: int):
        self.maxsize = maxsize
        self._cache: OrderedDict = OrderedDict()
    
    def get(self, key, default=None):
        """Get item, moving it to the end (most recently used)."""
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return default
    
    def __contains__(self, key):
        return key in self._cache
    
    def __getitem__(self, key):
        self._cache.move_to_end(key)
        return self._cache[key]
    
    def __setitem__(self, key, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.maxsize:
                # Evict oldest (first) item
                self._cache.popitem(last=False)
        self._cache[key] = value
    
    def __len__(self):
        return len(self._cache)
    
    def keys(self):
        return self._cache.keys()
    
    def clear(self):
        self._cache.clear()


# Conjugation data cache - (seq, from_seq, tuple(conj_ids), tuple(texts)) -> List[ConjData]
_CONJ_DATA_CACHE: LRUCache = LRUCache(maxsize=2048)

# POS cache - seq -> frozenset(posi) for per-seq caching
_POS_SEQ_CACHE: LRUCache = LRUCache(maxsize=4096)

# UK (prefer kana) cache - frozenset(seqs) -> bool
_UK_CACHE: LRUCache = LRUCache(maxsize=1024)

# Word lookup cache - (word, is_kana) -> List[WordMatch readings data]
_WORD_CACHE: LRUCache = LRUCache(maxsize=4096)

# Entry cache - seq -> Entry (reduces individual lookups)
_ENTRY_CACHE: LRUCache = LRUCache(maxsize=4096)


# ============================================================================
# Data Structures
# ============================================================================

@dataclass(slots=True)
class ConjData:
    """
    Conjugation data for a word match.
    Tracks the conjugation chain from conjugated form to root.
    """
    seq: int  # Conjugated entry seq
    from_seq: int  # Root entry seq
    via: Optional[int]  # Intermediate seq for secondary conjugations
    prop: Optional[ConjProp]  # Conjugation property
    src_map: List[Tuple[str, str]] = field(default_factory=list)  # (conjugated_text, source_text) pairs


@dataclass
class WordMatch:
    """
    Represents a word found in the database.
    Wraps either a KanjiText/KanaText ORM object OR a lightweight RawKana/KanjiReading.
    """
    reading: Union[KanjiText, KanaText, RawKanaReading, RawKanjiReading]
    conjugations: Optional[List[int]] = None  # List of conjugation IDs, or :root marker
    hinted: bool = False
    # Cached properties for performance (avoid repeated isinstance checks)
    _word_type: Optional[str] = field(default=None, repr=False)
    _seq: Optional[int] = field(default=None, repr=False)
    _text: Optional[str] = field(default=None, repr=False)
    
    def __post_init__(self):
        # Pre-compute cached properties on creation
        # Detect type: ORM objects have __table__, raw namedtuples don't
        # For raw types: RawKanaReading has 'best_kanji', RawKanjiReading has 'best_kana'
        if isinstance(self.reading, (KanjiText, KanaText)):
            # ORM object
            self._word_type = 'kanji' if isinstance(self.reading, KanjiText) else 'kana'
        elif isinstance(self.reading, RawKanaReading):
            self._word_type = 'kana'
        elif isinstance(self.reading, RawKanjiReading):
            self._word_type = 'kanji'
        else:
            # Fallback: check for best_kanji attribute (kana has it, kanji doesn't)
            self._word_type = 'kana' if hasattr(self.reading, 'best_kanji') else 'kanji'
        self._seq = self.reading.seq
        self._text = self.reading.text
    
    @property
    def seq(self) -> int:
        return self._seq
    
    @property
    def text(self) -> str:
        return self._text
    
    @property
    def common(self) -> Optional[int]:
        return self.reading.common
    
    @property
    def ord(self) -> int:
        return self.reading.ord
    
    @property
    def word_type(self) -> str:
        """Returns 'kanji' or 'kana' based on reading type."""
        return self._word_type
    
    @property
    def is_root(self) -> bool:
        """True if this is marked as a root form (not conjugated)."""
        return self.conjugations == 'root'
    
    @property
    def is_compound(self) -> bool:
        """Always False for simple WordMatch."""
        return False
    
    @property
    def components(self) -> List[str]:
        """Return empty list for simple words (no components)."""
        return []
    
    def __repr__(self):
        return f"<WordMatch(seq={self._seq}, text='{self._text}', type={self._word_type})>"


@dataclass
class CompoundWord:
    """
    Compound word made of 2 or more words joined together.
    
    Ports ichiran's compound-text class from dict.lisp lines 608-670.
    Compound words are created when a primary word is joined with a suffix
    (e.g., 食べている = 食べ + て + いる).
    
    Abbreviation compounds (is_abbrev=True) are scored differently - they use
    the original word's mora length instead of the abbreviated compound length.
    This matches Ichiran's proxy-text behavior for abbreviation suffixes.
    """
    text: str  # Full compound text
    kana: str  # Full kana reading
    primary: WordMatch  # Primary word (the main content word)
    words: List[WordMatch]  # All words in the compound
    score_mod: Union[float, List[float]] = 0.0  # Score modifier(s)
    score_base: Optional[WordMatch] = None  # Base for scoring (usually primary)
    is_abbrev: bool = False  # True for abbreviation compounds (e.g., nai-x: ず/ざる/ぬ)
    
    @property
    def seq(self) -> int:
        """Returns primary seq for compound (not a list)."""
        return self.primary.seq
    
    @property
    def is_compound(self) -> bool:
        """Always True for CompoundWord."""
        return True
    
    @property
    def components(self) -> List[str]:
        """Return component texts."""
        return [w.text for w in self.words]
    
    @property
    def reading(self):
        """Reading from primary word (for compatibility with calc_score)."""
        return self.primary.reading
    
    @property
    def is_root(self) -> bool:
        """Compound words are never roots."""
        return False
    
    @property
    def common(self) -> Optional[int]:
        """Common rating from primary word."""
        return self.primary.common
    
    @property
    def ord(self) -> int:
        """Ord from primary word."""
        return self.primary.ord
    
    @property
    def word_type(self) -> str:
        """Word type from primary word."""
        return self.primary.word_type
    
    @property
    def conjugations(self) -> Optional[List[int]]:
        """Conjugations from last word in compound."""
        if self.words:
            return self.words[-1].conjugations
        return None
    
    @conjugations.setter
    def conjugations(self, value):
        """Set conjugations on last word."""
        if self.words:
            self.words[-1].conjugations = value
    
    def get_score_base(self) -> WordMatch:
        """Get the base word for scoring."""
        return self.score_base or self.primary
    
    def get_conjugation_info(self, session: 'Session') -> Dict[str, Any]:
        """
        Get conjugation info from final word.
        
        Extracts conj_type, neg, fml, and source_text from the final word
        in the compound.
        
        Args:
            session: Database session for looking up conjugation data
            
        Returns:
            Dict with keys: conj_type, neg, fml, source_text
        """
        if not self.words:
            return {
                'conj_type': None,
                'neg': False,
                'fml': False,
                'source_text': None,
            }
        
        last_word = self.words[-1]
        conj_data = get_word_conj_data(session, last_word)
        
        if not conj_data:
            return {
                'conj_type': None,
                'neg': False,
                'fml': False,
                'source_text': None,
            }
        
        # Get the first conjugation data entry
        cd = conj_data[0]
        prop = cd.prop
        
        # Get conj_type name
        conj_type = None
        neg = False
        fml = False
        if prop:
            conj_type = prop.conj_type
            neg = prop.neg if prop.neg else False
            fml = prop.fml if prop.fml else False
        
        # Get source_text from src_map
        source_text = None
        if cd.src_map:
            for text, src_text in cd.src_map:
                if text == last_word.text:
                    source_text = src_text
                    break
        
        return {
            'conj_type': conj_type,
            'neg': neg,
            'fml': fml,
            'source_text': source_text,
        }
    
    def __repr__(self):
        return f"<CompoundWord(text='{self.text}', seq={self.seq})>"


def adjoin_word(
    word1: Union[WordMatch, 'CompoundWord'],
    word2: WordMatch,
    text: Optional[str] = None,
    kana: Optional[str] = None,
    score_mod: float = 0.0,
    score_base: Optional[WordMatch] = None,
    is_abbrev: bool = False,
) -> CompoundWord:
    """
    Create compound word from 2 words.
    
    Ports ichiran's adjoin-word from dict.lisp lines 632-654.
    
    Args:
        word1: Primary word or existing compound
        word2: Word to append
        text: Override text (default: concatenate both texts)
        kana: Override kana (default: concatenate both kanas)
        score_mod: Score modifier for this join
        score_base: Base for scoring
        is_abbrev: True if this is an abbreviation suffix (affects scoring)
    
    Returns:
        CompoundWord combining both words
    """
    # Default text and kana by concatenation
    if text is None:
        text = word1.text + word2.text
    if kana is None:
        # Derive kana from each word's kana/reading
        def get_word_kana(w):
            if isinstance(w, CompoundWord):
                return w.kana
            # For WordMatch, get kana from reading
            if hasattr(w, 'reading'):
                # KanjiText/RawKanjiReading has text=kanji, best_kana=kana reading
                # KanaText/RawKanaReading has text=kana directly
                if isinstance(w.reading, (KanjiText, RawKanjiReading)):
                    return w.reading.best_kana or w.reading.text
                elif hasattr(w.reading, 'text'):
                    return w.reading.text
            return w.text
        kana = get_word_kana(word1) + get_word_kana(word2)
    
    if isinstance(word1, CompoundWord):
        # Append to existing compound
        word1.text = text
        word1.kana = kana
        word1.words = word1.words + [word2]
        # Accumulate score_mod
        if isinstance(word1.score_mod, list):
            word1.score_mod = [score_mod] + word1.score_mod
        else:
            word1.score_mod = [score_mod, word1.score_mod]
        # Mark as abbreviation if this join is an abbreviation
        if is_abbrev:
            word1.is_abbrev = True
        return word1
    else:
        # Create new compound from two simple words
        return CompoundWord(
            text=text,
            kana=kana,
            primary=word1,
            words=[word1, word2],
            score_mod=score_mod,
            score_base=score_base,
            is_abbrev=is_abbrev,
        )


@dataclass(slots=True)
class Segment:
    """
    A segment representing a word match within a string.
    Contains position information and scoring.
    """
    start: int  # Start position in source string
    end: int  # End position in source string
    word: WordMatch
    score: float = 0.0
    info: Dict[str, Any] = field(default_factory=dict)
    text: Optional[str] = None  # Cached text
    top: bool = False  # Whether this is the top segment in its list
    # Filter result cache: filter_id -> bool result
    # This avoids re-running expensive filters on the same segment
    _filter_cache: Optional[Dict[int, bool]] = None
    
    def get_text(self) -> str:
        if self.text is None:
            self.text = self.word.text
        return self.text
    
    def get_filter_result(self, filter_id: int) -> Optional[bool]:
        """Get cached filter result if available."""
        if self._filter_cache is None:
            return None
        return self._filter_cache.get(filter_id)
    
    def set_filter_result(self, filter_id: int, result: bool) -> None:
        """Cache a filter result."""
        if self._filter_cache is None:
            self._filter_cache = {}
        self._filter_cache[filter_id] = result
    
    def __repr__(self):
        return f"<Segment({self.start}:{self.end}, '{self.get_text()}', score={self.score})>"


@dataclass(slots=True)
class SegmentList:
    """
    A list of segments at the same position.
    Contains multiple possible interpretations for a substring.
    """
    segments: List[Segment]
    start: int
    end: int
    top: Any = None  # TopArray for path finding
    matches: int = 0  # Total number of matches found
    
    def __repr__(self):
        return f"<SegmentList({self.start}:{self.end}, {len(self.segments)} segments)>"


# ============================================================================
# Length Coefficient Functions
# ============================================================================

def length_multiplier(length: int, power: float, len_lim: int) -> float:
    """
    Calculate length multiplier: len^power until len_lim, linear after.
    
    Args:
        length: Word length in mora
        power: Exponent to use
        len_lim: Limit after which growth becomes linear
    
    Returns:
        The multiplier value
    """
    if length <= len_lim:
        return length ** power
    return length * (len_lim ** (power - 1))


def length_multiplier_coeff(length: int, coeff_class: str) -> int:
    """
    Get length multiplier from coefficient sequence.
    
    Args:
        length: Word length in mora (1-based)
        coeff_class: One of 'strong', 'weak', 'tail', 'ltail'
    
    Returns:
        The coefficient value for this length
    """
    coeffs = LENGTH_COEFF_SEQUENCES.get(coeff_class)
    if not coeffs:
        return length
    
    if 0 < length < len(coeffs):
        return coeffs[length]
    
    # Linear extrapolation for lengths beyond the table
    last_coeff = coeffs[-1]
    last_idx = len(coeffs) - 1
    return length * (last_coeff // last_idx) if last_idx > 0 else length


# ============================================================================
# Database Lookup Functions
# ============================================================================

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
    return [WordMatch(reading=r) for r in results]


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
    
    result = []
    for conj in conjugations:
        # Get source readings
        src_query = select(ConjSourceReading).where(
            ConjSourceReading.conj_id == conj.id
        )
        if texts:
            src_query = src_query.where(ConjSourceReading.text.in_(texts))
        
        src_readings = session.execute(src_query).scalars().all()
        src_map = [(sr.text, sr.source_text) for sr in src_readings]
        
        if texts and not src_map:
            continue
        
        # Get conjugation properties
        props = session.execute(
            select(ConjProp).where(ConjProp.conj_id == conj.id)
        ).scalars().all()
        
        for prop in props:
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


# ============================================================================
# Batch Preloading for Performance
# ============================================================================

def preload_scoring_caches(session: Session, seqs: Set[int]) -> None:
    """
    Batch preload all caches needed for calc_score.
    
    This dramatically reduces cold-start latency by:
    1. Batch loading Entry objects
    2. Batch preloading UK (prefer-kana) status
    3. Batch preloading POS tags
    
    Call this before scoring a batch of segments.
    
    Args:
        session: Database session
        seqs: Set of seq numbers to preload
    """
    global _ENTRY_CACHE, _UK_CACHE, _POS_SEQ_CACHE
    
    if not seqs:
        return
    
    # Filter to seqs not already in entry cache
    missing_seqs = seqs - set(_ENTRY_CACHE.keys())
    
    if missing_seqs:
        # Batch load entries
        entries = session.execute(
            select(Entry).where(Entry.seq.in_(missing_seqs))
        ).scalars().all()
        
        # LRUCache handles eviction automatically
        for entry in entries:
            _ENTRY_CACHE[entry.seq] = entry
    
    # Find seqs not yet in UK cache
    uk_missing = {seq for seq in seqs if frozenset([seq]) not in _UK_CACHE}
    
    if uk_missing:
        # Single batch query for all UK statuses
        uk_seqs = set(session.execute(
            select(SenseProp.seq)
            .where(and_(
                SenseProp.seq.in_(uk_missing),
                SenseProp.tag == 'misc',
                SenseProp.text == 'uk'
            ))
            .distinct()
        ).scalars().all())
        
        # Cache results for all checked seqs
        for seq in uk_missing:
            cache_key = frozenset([seq])
            _UK_CACHE[cache_key] = seq in uk_seqs
    
    # Find seqs not yet in POS cache (now using _POS_SEQ_CACHE)
    pos_missing = {seq for seq in seqs if seq not in _POS_SEQ_CACHE}
    
    if pos_missing:
        # Build archaic senses subquery once
        arch_misc = {'arch', 'obsc', 'rare'}
        arch_senses = (
            select(SenseProp.sense_id)
            .where(and_(
                SenseProp.tag == 'misc',
                SenseProp.text.in_(arch_misc)
            ))
        )
        
        # Batch query for all POS tags (excluding archaic senses)
        pos_results = session.execute(
            select(SenseProp.seq, SenseProp.text)
            .where(and_(
                SenseProp.seq.in_(pos_missing),
                SenseProp.tag == 'pos',
                ~SenseProp.sense_id.in_(arch_senses)
            ))
        ).all()
        
        # Group results by seq
        seq_to_posi: Dict[int, Set[str]] = {seq: set() for seq in pos_missing}
        for seq, pos_text in pos_results:
            seq_to_posi[seq].add(pos_text)
        
        # LRUCache handles eviction automatically
        for seq, posi in seq_to_posi.items():
            _POS_SEQ_CACHE[seq] = frozenset(posi)


def get_cached_entry(session: Session, seq: int) -> Optional[Entry]:
    """
    Get Entry from cache or database.
    Uses _ENTRY_CACHE for faster repeated lookups.
    """
    global _ENTRY_CACHE
    
    if seq in _ENTRY_CACHE:
        return _ENTRY_CACHE[seq]
    
    entry = session.get(Entry, seq)
    
    # LRUCache handles eviction automatically
    if entry:
        _ENTRY_CACHE[seq] = entry
    
    return entry


# ============================================================================
# Archaic Word Detection
# ============================================================================

def build_archaic_cache(session: Session) -> Set[int]:
    """
    Build cache of archaic/obsolete/rare word seqs.
    From ichiran's *is-arch-cache*.
    
    Words where ALL senses are marked arch/obsc/rare are considered archaic.
    A word with even one non-archaic sense is NOT considered archaic.
    """
    arch_misc = {'arch', 'obsc', 'rare'}
    
    # Find seqs where EVERY sense has an arch/obsc/rare tag
    # This is the ichiran logic: 
    # SELECT sense.seq FROM sense
    # LEFT JOIN sense_prop sp ON (... AND sp.text IN ('arch', 'obsc', 'rare'))
    # GROUP BY sense.seq HAVING EVERY(sp.id IS NOT NULL)
    #
    # In SQLAlchemy, we do this by:
    # 1. Get all (seq, sense_id) pairs with their arch tag status
    # 2. Group by seq and check that all senses have the arch tag
    
    from sqlalchemy import func, case, literal_column
    from himotoki.db.models import Sense
    
    # Subquery: for each sense, is it archaic?
    arch_tag_subq = (
        select(SenseProp.sense_id)
        .where(and_(
            SenseProp.tag == 'misc',
            SenseProp.text.in_(arch_misc)
        ))
    )
    
    # Main query: find seqs where ALL senses are in arch_tag_subq
    # We count total senses and archaic senses per seq, keep only where they match
    query = (
        select(Sense.seq)
        .group_by(Sense.seq)
        .having(
            func.count(Sense.id) == func.sum(
                case((Sense.id.in_(arch_tag_subq), 1), else_=0)
            )
        )
    )
    arch_seqs = set(session.execute(query).scalars().all())
    
    # Also add conjugations derived from archaic words
    if arch_seqs:
        conj_query = (
            select(Conjugation.seq)
            .where(Conjugation.from_seq.in_(arch_seqs))
            .distinct()
        )
        conj_seqs = set(session.execute(conj_query).scalars().all())
        arch_seqs |= conj_seqs
    
    return arch_seqs


def is_arch(session: Session, seq_set: Set[int]) -> bool:
    """
    Check if all seqs in seq_set are archaic/obsolete/rare.
    Uses a cached set of archaic word seqs.
    """
    global _ARCHAIC_CACHE
    if _ARCHAIC_CACHE is None:
        _ARCHAIC_CACHE = build_archaic_cache(session)
    
    return all(seq in _ARCHAIC_CACHE for seq in seq_set)


def is_prefer_kana(session: Session, seq_set: List[int]) -> bool:
    """
    Check if entries have 'uk' (usually written in kana) misc tag.
    Cached for performance.
    """
    global _UK_CACHE
    
    cache_key = frozenset(seq_set)
    if cache_key in _UK_CACHE:
        return _UK_CACHE[cache_key]
    
    result = session.execute(
        select(SenseProp)
        .where(and_(
            SenseProp.seq.in_(seq_set),
            SenseProp.tag == 'misc',
            SenseProp.text == 'uk'
        ))
    ).scalars().first() is not None
    
    # LRUCache handles eviction automatically
    _UK_CACHE[cache_key] = result
    
    return result


def get_non_arch_posi(session: Session, seq_set: Set[int]) -> Set[str]:
    """
    Get part-of-speech tags for entries, excluding archaic senses.
    From ichiran's get-non-arch-posi.
    
    Uses per-seq caching for better hit rate when seq_sets overlap.
    """
    global _POS_SEQ_CACHE
    
    # Check if we have all seqs cached
    all_cached = all(seq in _POS_SEQ_CACHE for seq in seq_set)
    
    if all_cached:
        # Combine cached results
        result = set()
        for seq in seq_set:
            result |= _POS_SEQ_CACHE[seq]
        return result
    
    # Find which seqs need to be fetched
    missing_seqs = {seq for seq in seq_set if seq not in _POS_SEQ_CACHE}
    
    if missing_seqs:
        arch_misc = {'arch', 'obsc', 'rare'}
        
        # Subquery to find sense_ids with archaic props
        arch_senses = (
            select(SenseProp.sense_id)
            .where(and_(
                SenseProp.tag == 'misc',
                SenseProp.text.in_(arch_misc)
            ))
        )
        
        # Batch query for all missing seqs
        results = session.execute(
            select(SenseProp.seq, SenseProp.text)
            .where(and_(
                SenseProp.seq.in_(missing_seqs),
                SenseProp.tag == 'pos',
                ~SenseProp.sense_id.in_(arch_senses)
            ))
        ).all()
        
        # Group by seq
        seq_posi: Dict[int, Set[str]] = {seq: set() for seq in missing_seqs}
        for seq, pos_text in results:
            seq_posi[seq].add(pos_text)
        
        # LRUCache handles eviction automatically
        for seq, posi in seq_posi.items():
            _POS_SEQ_CACHE[seq] = frozenset(posi)
    
    # Combine results from cache
    result = set()
    for seq in seq_set:
        if seq in _POS_SEQ_CACHE:
            result |= _POS_SEQ_CACHE[seq]
    
    return result


# ============================================================================
# Conjugation Form Testing
# ============================================================================

def matches_conj_form(prop: ConjProp, forms: List[Tuple]) -> bool:
    """
    Check if a conjugation property matches any of the weak/skip forms.
    From ichiran's test-conj-prop.
    
    Args:
        prop: ConjProp object to test
        forms: List of (conj_type, neg, fml) or (pos, conj_type, neg, fml) tuples
               where None means "any value matches"
    
    Returns:
        True if prop matches any form pattern
    """
    for form in forms:
        if len(form) == 3:
            # (conj_type, neg, fml) format
            pattern = [prop.conj_type, prop.neg, prop.fml]
            if all(
                r is None or l == r
                for l, r in zip(pattern, form)
            ):
                return True
        elif len(form) == 4:
            # (pos, conj_type, neg, fml) format
            if form[0] == prop.pos:
                pattern = [prop.conj_type, prop.neg, prop.fml]
                if all(
                    r is None or l == r
                    for l, r in zip(pattern, form[1:])
                ):
                    return True
    return False


def skip_by_conj_data(conj_data: List[ConjData]) -> bool:
    """
    Check if conjugation data should be skipped entirely.
    From ichiran's skip-by-conj-data.
    
    Returns True if ALL conjugation data matches skip patterns.
    """
    if not conj_data:
        return False
    
    return all(
        cd.prop is not None and matches_conj_form(cd.prop, SKIP_CONJ_FORMS)
        for cd in conj_data
    )


def is_weak_conj_form(conj_data: List[ConjData]) -> bool:
    """
    Check if all conjugations are weak forms (don't contribute as much).
    """
    if not conj_data:
        return False
    
    return all(
        cd.prop is not None and matches_conj_form(cd.prop, WEAK_CONJ_FORMS)
        for cd in conj_data
    )


# ============================================================================
# Scoring Functions
# ============================================================================

def compare_common(c1: Optional[int], c2: Optional[int]) -> bool:
    """
    Compare two commonness values.
    Lower is better, 0 is special (very common), None is worst.
    
    Returns True if c1 should be sorted before c2.
    """
    if c2 is None:
        return c1 is not None
    if c2 == 0:
        return c1 is not None and c1 > 0
    if c1 is not None and c1 > 0:
        return c1 < c2
    return False


def kanji_break_penalty(
    kanji_break: List[int],
    score: float,
    info: Optional[Dict] = None,
    text: str = "",
    use_length: Optional[int] = None,
    score_mod: float = 0,
) -> float:
    """
    Apply penalty for breaks within kanji sequences.
    
    Args:
        kanji_break: List of positions where kanji are broken
        score: Current score
        info: Score info dict
        text: Word text
        use_length: Context length if available
        score_mod: Score modifier
    
    Returns:
        Adjusted score
    """
    if not kanji_break:
        return score
    
    # Determine break position type
    end = 'both' if len(kanji_break) > 1 else (
        'beg' if kanji_break[0] == 0 else 'end'
    )
    
    bonus = 0
    ratio = 2
    posi = info.get('posi', []) if info else []
    
    if info:
        seq_set = info.get('seq_set', set())
        
        # Check for no-penalty words
        if seq_set & NO_KANJI_BREAK_PENALTY:
            return score
        
        # Check for special す break
        if end == 'beg' and text.startswith('す'):
            return score
        
        # Adjust bonus based on POS
        if end == 'beg' and 'num' in posi:
            bonus += 5
        elif end == 'beg' and ('suf' in posi or 'n-suf' in posi):
            bonus += 10
        elif end == 'end' and 'pref' in posi:
            bonus += 12
    
    if score >= SCORE_CUTOFF:
        return max(SCORE_CUTOFF, (score // ratio) + bonus)
    return score


def calc_score(
    session: Session,
    word: Union[WordMatch, CompoundWord],
    final: bool = False,
    use_length: Optional[int] = None,
    score_mod: float = 0,
    kanji_break: Optional[List[int]] = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate score for a word match.
    
    This is the core scoring algorithm ported from ichiran's calc-score (dict.lisp lines 777-983).
    
    The scoring system considers:
    - Word type (kanji vs kana)
    - Commonness ranking
    - Part of speech (particles get special handling)
    - Primary/secondary reading status
    - Conjugation status and type
    - Word length
    - Context length (use_length)
    - Kanji break penalties
    - Archaic word detection
    
    Args:
        session: Database session
        word: WordMatch or CompoundWord object to score
        final: True if this is at the end of the text
        use_length: Context length for scoring
        score_mod: Score modifier (for compound words)
        kanji_break: List of kanji break positions
    
    Returns:
        Tuple of (score, info_dict)
    """
    # Handle compound words by scoring the base word with compound properties
    # From ichiran dict.lisp lines 782-794
    if isinstance(word, CompoundWord):
        base_word = word.get_score_base()
        compound_score_mod = word.score_mod
        
        # Both regular compounds and abbreviation compounds use the compound
        # text's mora length for use_length. This creates a penalty when the
        # compound is shorter than the base word (negative difference in
        # length_multiplier_coeff).
        #
        # For abbreviations like とまず (3 mora) from とまない (4 mora):
        # use_length=3, base word len=4, difference=-1 → penalty applied
        compound_use_length = mora_length(word.text)
        
        score, info = calc_score(
            session, base_word,
            use_length=compound_use_length,
            score_mod=compound_score_mod,
        )
        
        # Add compound word conjugation data
        info['conj'] = get_word_conj_data(session, word)
        
        # Apply kanji break penalty if needed
        if kanji_break:
            score = kanji_break_penalty(
                kanji_break, score, 
                info=info, text=base_word.text,
                use_length=compound_use_length, score_mod=compound_score_mod
            )
        
        return score, info
    
    # Check for counter mode (CounterText objects)
    ctr_mode = _is_counter_text(word)
    
    reading = word.reading
    text = word.text
    seq = word.seq
    ord_val = word.ord
    common = word.common
    
    # Fast path: Early termination for skip words (before any DB lookups)
    # This avoids expensive entry lookups and conjugation data retrieval
    if seq in SKIP_WORDS:
        return 0, {}
    
    # Fast path: Final particles only score at end of text
    if not final and seq in FINAL_PRT:
        return 0, {}
    
    # Get entry info - counters don't have entries
    # Use cached entry lookup for performance
    entry = None if ctr_mode else get_cached_entry(session, seq)
    if not entry and not ctr_mode:
        return 0, {}
    
    # Basic properties
    score = 1
    prop_score = 0
    
    kanji_p = word.word_type == 'kanji'
    katakana_p = not kanji_p and count_char_class(text, 'katakana') > 0
    
    n_kanji = count_char_class(text, 'kanji')
    word_len = max(1, mora_length(text))
    
    # Conjugation info - counters don't have conjugations
    conj_only = False if ctr_mode else (word.conjugations is not None and word.conjugations != 'root')
    root_p = ctr_mode or (not conj_only and entry and entry.root_p)
    
    # Get conjugation data - counters don't have conjugations
    if ctr_mode:
        conj_data = []
    elif conj_only and isinstance(word.conjugations, list):
        conj_data = get_conj_data(session, seq, conj_ids=word.conjugations, texts=[text])
    elif not word.is_root:
        conj_data = get_conj_data(session, seq, texts=[text])
    else:
        conj_data = []
    
    # Handle secondary conjugations (via forms)
    # If this is nil, delete all secondary conjugations from conj data
    secondary_conj_p = False
    if conj_data:
        if all(cd.via for cd in conj_data):
            secondary_conj_p = True
        else:
            # Remove secondary conjugations from data
            conj_data = [cd for cd in conj_data if not cd.via]
    
    conj_of = [cd.from_seq for cd in conj_data]
    conj_props = [cd.prop for cd in conj_data if cd.prop]
    conj_types = [cp.conj_type for cp in conj_props]
    
    # conj_types_p: True if not all conjugations are weak forms
    # From ichiran: "weak" forms don't contribute to scoring as much
    conj_types_p = (
        root_p or
        use_length is not None or
        not all(matches_conj_form(prop, WEAK_CONJ_FORMS) for prop in conj_props if prop)
    )
    
    # Get part-of-speech info
    seq_set = {seq} | set(conj_of) if seq else set()
    sp_seq_set = [seq] if (seq and root_p and not use_length) else list(seq_set)
    
    # For counters, use 'ctr' as the part of speech
    if ctr_mode:
        prefer_kana = False
        is_arch_p = False
        posi = {'ctr'}
    else:
        # Check for prefer kana (uk - usually written in kana) - cached
        prefer_kana = is_prefer_kana(session, sp_seq_set)
        
        # Check if all entries are archaic
        is_arch_p = is_arch(session, set(sp_seq_set))
        
        # Get part-of-speech (excluding archaic senses) - cached
        posi = get_non_arch_posi(session, seq_set)
    
    # Common properties
    common_p = common is not None
    common_of = common
    particle_p = 'prt' in posi
    semi_final_particle_p = seq in SEMI_FINAL_PRT
    non_final_particle_p = seq in NON_FINAL_PRT
    pronoun_p = 'pn' in posi
    cop_da_p = bool(seq_set & COPULAE)
    
    # Length classification (ichiran lines 836-844)
    # More complex logic based on various conditions
    if kanji_p and not prefer_kana:
        if (root_p and not conj_data) or (use_length and 13 in conj_types):
            len_threshold = 2
        elif common_p and common and 0 < common < 10:
            len_threshold = 2
        elif {3, 9} & set(conj_types) and not use_length:
            len_threshold = 4
        else:
            len_threshold = 3
    else:
        if common_p and common and 0 < common < 10:
            len_threshold = 2
        elif {3, 9} & set(conj_types) and not use_length:
            len_threshold = 4
        else:
            len_threshold = 3
    
    long_p = word_len > len_threshold
    
    # no_common_bonus conditions
    no_common_bonus = (
        particle_p or
        not conj_types_p or
        (not long_p and posi == {'int'})
    )
    
    use_length_bonus = 0
    
    # Check for skip words in conjugation chain and final particles
    # Note: We already checked seq in SKIP_WORDS early (line ~1230), but here we check
    # the entire seq_set which includes conjugation sources (conj_of)
    if seq_set & SKIP_WORDS:
        return 0, {}
    if not root_p and skip_by_conj_data(conj_data):
        return 0, {}
    
    # Handle inherited commonness and ord from conjugation source (ichiran lines 859-870)
    # This MUST happen BEFORE primary_p determination so that ord_val is correct
    if conj_data and not (ord_val == 0 and common_p):
        orig_texts = get_original_text_data(session, word, conj_data)
        if orig_texts:
            if not common_p:
                conj_of_common = [c for c, o in orig_texts if c is not None]
                if conj_of_common:
                    common = 0
                    common_p = True
                    # Get the "best" common value
                    common_of = sorted(conj_of_common, key=lambda c: (c or 1000, c == 0))[0]
            
            # Update ord if conjugated form has lower ord
            conj_of_ord = min(o for c, o in orig_texts)
            if conj_of_ord < ord_val:
                ord_val = conj_of_ord
    
    # Primary reading check - now with archaic consideration
    # Pass ord_val to use corrected ord from conjugation source
    primary_p = False
    if not is_arch_p:
        primary_p = determine_primary_full(
            session, entry, word, posi, common_p, kanji_p,
            root_p, conj_data, prefer_kana, conj_types_p, cop_da_p, pronoun_p,
            ord_override=ord_val
        )
    
    # Calculate base score (ichiran lines 890-925)
    if primary_p:
        if long_p:
            score += 10
        elif secondary_conj_p and not kanji_p:
            score += 2
        elif common_p and conj_types_p:
            score += 5
        elif prefer_kana or not entry or entry.n_kanji == 0:
            score += 3
        else:
            score += 2
    
    # Particle bonus (lines 896-902)
    if particle_p and (final or not semi_final_particle_p):
        score += 2
        if common_p:
            score += 2 + word_len
        if final and not non_final_particle_p:
            if primary_p:
                score += 5
            elif semi_final_particle_p:
                score += 2
    
    # Commonness bonus (lines 903-918)
    if common_p and not no_common_bonus:
        if secondary_conj_p and not use_length:
            common_bonus = 4 if (kanji_p and primary_p) else 2
        elif long_p or cop_da_p or (root_p and (kanji_p or (primary_p and word_len > 2))):
            if common == 0:
                common_bonus = 10
            elif not primary_p:
                common_bonus = max(15 - (common or 0), 10)
            else:
                common_bonus = max(20 - (common or 0), 10)
        elif kanji_p:
            common_bonus = 8
        elif primary_p:
            common_bonus = 4
        elif word_len > 2 or (common and 0 < common < 10):
            common_bonus = 3
        else:
            common_bonus = 2
        
        # Reduce bonus for continuative form (conj_type 10)
        if common_bonus >= 10 and 10 in conj_types:
            common_bonus -= 4
        
        score += common_bonus
    
    # Length and kanji bonuses (lines 919-926)
    if long_p:
        score = max(word_len, score)
    
    if kanji_p:
        score = max(3 if is_arch_p else 5, score)
        if long_p and (n_kanji > 1 or word_len > 4):
            score += 2
    
    # Counter mode minimum score (ichiran line 926: (when ctr-mode (setf score (max 5 score))))
    if ctr_mode:
        score = max(5, score)
    
    # Calculate prop_score and apply length multiplier (lines 927-937)
    prop_score = score
    length_class = 'strong' if (kanji_p or katakana_p) else 'weak'
    score = prop_score * (
        length_multiplier_coeff(word_len, length_class) +
        ((n_kanji - 1) * 5 if n_kanji > 1 else 0)
    )
    
    # Split scoring integration (ichiran lines 927-970)
    # Check for split definition and apply split scoring
    # Note: counters don't use split scoring (ichiran: (unless ctr-mode ...))
    split_info = None
    if not ctr_mode:
        from himotoki.splits import get_split
        split_result = get_split(session, word, conj_of if conj_of else None)
        
        if split_result:
            if ':score' in split_result.modifiers:
                # Direct score addition mode
                score += split_result.score_bonus
                split_info = ('score', split_result.score_bonus)
            elif ':pscore' in split_result.modifiers:
                # Proportional score modification mode
                import math
                new_prop_score = max(1, prop_score + split_result.score_bonus)
                score = math.ceil(score * new_prop_score / prop_score) if prop_score > 0 else score
                prop_score = new_prop_score
                split_info = ('pscore', split_result.score_bonus)
            else:
                # Standard split: sum of part scores + bonus
                split_score = split_result.score_bonus
                part_scores = []
                for i, part in enumerate(split_result.parts):
                    is_last = (i == len(split_result.parts) - 1)
                    # Calculate adjusted use_length for final part
                    part_use_length = None
                    if is_last and use_length:
                        # Subtract mora lengths of preceding parts
                        preceding_mora = sum(
                            mora_length(p.text) for p in split_result.parts[:-1]
                        )
                        part_use_length = use_length - preceding_mora
                    
                    part_score, _ = calc_score(
                        session, part.reading,
                        final=final and is_last,
                        use_length=part_use_length,
                        score_mod=score_mod if is_last else 0,
                    )
                    part_scores.append(part_score)
                    split_score += part_score
                
                score = split_score
                split_info = ('split', split_result.score_bonus, part_scores)
    
    # Apply use_length bonus for context
    if use_length:
        tail_len = use_length - word_len
        tail_class = 'ltail' if (word_len > 3 and (kanji_p or katakana_p)) else 'tail'
        use_length_bonus = prop_score * length_multiplier_coeff(tail_len, tail_class)
        
        if score_mod:
            use_length_bonus += apply_score_mod(score_mod, prop_score, tail_len)
        
        score += use_length_bonus
    
    # Build info dict
    info = {
        'posi': list(posi),
        'seq_set': seq_set,
        'conj': conj_data,
        'common': common_of if common_p else None,
        'score_info': [prop_score, kanji_break, use_length_bonus, split_info],
        'kpcl': [kanji_p or katakana_p, primary_p, common_p, long_p],
    }
    
    # Apply kanji break penalty
    if kanji_break:
        score = kanji_break_penalty(
            kanji_break, score,
            info=info, text=text,
            use_length=use_length, score_mod=score_mod
        )
    
    return score, info


def determine_primary_full(
    session: Session,
    entry: Entry,
    word: WordMatch,
    posi: Set[str],
    common_p: bool,
    kanji_p: bool,
    root_p: bool,
    conj_data: List[ConjData],
    prefer_kana: bool,
    conj_types_p: bool,
    cop_da_p: bool,
    pronoun_p: bool,
    ord_override: Optional[int] = None,
) -> bool:
    """
    Full primary reading determination from ichiran lines 872-888.
    More complete than the simple version.
    
    Args:
        ord_override: If provided, use this ord value instead of word.ord.
                     This is used when the ord has been corrected based on
                     conjugation source data.
    """
    if not entry:
        return True
    
    # Use overridden ord if provided, otherwise use word.ord
    ord_val = ord_override if ord_override is not None else word.ord
    
    # Prefer kana and this is kana reading
    if prefer_kana and conj_types_p and not kanji_p:
        if not entry.primary_nokanji:
            return True
        # Check nokanji flag on reading
        if hasattr(word.reading, 'nokanji') and word.reading.nokanji:
            return True
        # Additional case: common hiragana word with ord=0 should be primary
        # This handles words like きれい that are commonly written in kana
        # but don't have the nokanji flag on the hiragana reading
        if ord_val == 0 and common_p and (word.common == 0 or (word.common is not None and word.common < 10)):
            return True
    
    # Primary if ord=0 or copula
    if ord_val == 0 or cop_da_p:
        if (kanji_p or conj_types_p) and (
            (kanji_p and not prefer_kana) or
            (common_p and pronoun_p) or
            entry.n_kanji == 0
        ):
            return True
    
    # Special case: prefer_kana with kanji, ord=0, but uk is not for first sense
    if prefer_kana and kanji_p and ord_val == 0:
        # Check if uk prop is for ord=0 sense
        first_sense_uk = session.execute(
            select(SenseProp)
            .join(Sense, SenseProp.sense_id == Sense.id)
            .where(and_(
                Sense.seq == entry.seq,
                Sense.ord == 0,
                SenseProp.tag == 'misc',
                SenseProp.text == 'uk'
            ))
        ).scalars().first()
        if not first_sense_uk:
            return True
    
    return False


def get_original_text_data(
    session: Session,
    word: WordMatch,
    conj_data: List[ConjData],
) -> List[Tuple[Optional[int], int]]:
    """
    Get (common, ord) pairs from original (unconjugated) text.
    
    Ports ichiran's get-original-text* function from dict.lisp.
    Extended from get_original_text_common to also return ord.
    
    For secondary conjugations (via forms), this function recursively
    follows the conjugation chain to find the original source text.
    
    Args:
        session: Database session
        word: WordMatch object to get original text for
        conj_data: List of ConjData objects for the word
    
    Returns:
        List of (common, ord) tuples from the original source forms
    """
    return _get_original_text_data_recursive(session, conj_data, [word.text])


def _get_original_text_data_recursive(
    session: Session,
    conj_data: List[ConjData],
    texts: List[str],
) -> List[Tuple[Optional[int], int]]:
    """
    Recursive helper for get_original_text_data.
    
    Follows the conjugation chain through via forms to find the
    ultimate source text and its properties.
    
    Args:
        session: Database session
        conj_data: List of ConjData objects
        texts: List of text forms to look up
    
    Returns:
        List of (common, ord) tuples from the original source forms
    """
    result = []
    for cd in conj_data:
        # Find matching source texts from src_map
        src_texts = []
        for text, src_text in cd.src_map:
            if text in texts:
                src_texts.append(src_text)
        
        if not src_texts:
            continue
        
        if cd.via is None:
            # Direct conjugation - look up the source text in from_seq
            for src_text in src_texts:
                table = KanjiText if has_kanji(src_text) else KanaText
                orig = session.execute(
                    select(table)
                    .where(and_(table.seq == cd.from_seq, table.text == src_text))
                ).scalars().first()
                if orig:
                    result.append((orig.common, orig.ord))
        else:
            # Secondary conjugation (via form) - recursively follow the chain
            # Get conjugation data from via -> from_seq
            via_conj_data = get_conj_data(session, cd.via, from_seq=cd.from_seq)
            if via_conj_data:
                result.extend(_get_original_text_data_recursive(
                    session, via_conj_data, src_texts
                ))
    
    return result


def apply_score_mod(
    score_mod: Union[int, float, callable, List],
    score: float,
    length: int,
) -> float:
    """Apply score modifier."""
    if callable(score_mod):
        return score_mod(score)
    if isinstance(score_mod, list):
        return sum(apply_score_mod(sm, score, length) for sm in score_mod)
    return score * score_mod * length


def get_entry_posi(session: Session, seq_set: Set[int]) -> Set[str]:
    """Get part-of-speech tags for entries."""
    query = (
        select(SenseProp.text)
        .where(and_(
            SenseProp.seq.in_(seq_set),
            SenseProp.tag == 'pos'
        ))
        .distinct()
    )
    results = session.execute(query).scalars().all()
    return set(results)


def determine_primary(
    session: Session,
    entry: Entry,
    word: WordMatch,
    posi: Set[str],
    common_p: bool,
    kanji_p: bool,
    root_p: bool,
    conj_data: List[ConjData],
) -> bool:
    """Determine if this is the primary reading for the entry."""
    if not entry:
        return True
    
    # Check for uk (usually kana) preference
    prefer_kana = session.execute(
        select(SenseProp)
        .where(and_(
            SenseProp.seq == entry.seq,
            SenseProp.tag == 'misc',
            SenseProp.text == 'uk'
        ))
    ).scalars().first() is not None
    
    if prefer_kana and not kanji_p and word.ord == 0:
        return True
    
    # Primary if ord=0 and kanji form or no kanji exists
    if word.ord == 0:
        if kanji_p or entry.n_kanji == 0:
            return True
    
    # Check for pronoun with common reading
    if common_p and 'pn' in posi and word.ord == 0:
        return True
    
    return False


def get_original_text_common(
    session: Session,
    word: WordMatch,
    conj_data: List[ConjData],
) -> Optional[int]:
    """Get commonness from original (unconjugated) text."""
    for cd in conj_data:
        for text, src_text in cd.src_map:
            if text == word.text:
                # Look up the source text
                table = KanjiText if has_kanji(src_text) else KanaText
                orig = session.execute(
                    select(table)
                    .where(and_(table.seq == cd.from_seq, table.text == src_text))
                ).scalars().first()
                if orig and orig.common is not None:
                    return orig.common
    return None


# ============================================================================
# Segment Filtering Functions
# ============================================================================

def cull_segments(segments: List[Segment]) -> List[Segment]:
    """
    Filter segments to remove low-scoring duplicates.
    
    Keeps segments scoring at least IDENTICAL_WORD_SCORE_CUTOFF of the max.
    Sorts by score descending, then by commonness ascending.
    """
    if not segments:
        return segments
    
    # Sort by score descending, then by commonness ascending
    # Note: common=0 is the best (most common), so we need to handle it specially
    # since 0 is falsy in Python
    def get_common_key(s):
        common = s.info.get('common') if s.info else None
        if common is None:
            return float('inf')
        return common
    
    segments = sorted(
        segments,
        key=lambda s: (
            -s.score,  # Score descending (higher is better)
            get_common_key(s),  # Commonness ascending (lower is better)
        )
    )
    
    max_score = max(s.score for s in segments)
    cutoff = max_score * IDENTICAL_WORD_SCORE_CUTOFF
    
    return [s for s in segments if s.score >= cutoff]


def gen_score(
    session: Session,
    segment: Segment,
    final: bool = False,
    kanji_break: Optional[List[int]] = None,
) -> Segment:
    """Generate score for a segment."""
    score, info = calc_score(
        session, segment.word,
        final=final, kanji_break=kanji_break
    )
    segment.score = score
    # Preserve counter flag if it was set
    if segment.info and segment.info.get('counter'):
        info['counter'] = True
    segment.info = info
    return segment


# ============================================================================
# Path Finding Utilities
# ============================================================================

def gap_penalty(start: int, end: int) -> int:
    """Calculate penalty for ungapped text."""
    return (end - start) * GAP_PENALTY
