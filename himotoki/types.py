"""
Data types for word lookup and segmentation.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Union, Any

from sqlalchemy.orm import Session

from himotoki.raw_types import RawKanaReading, RawKanjiReading
from himotoki.db.models import KanjiText, KanaText, ConjProp


def _is_counter_text(obj) -> bool:
    """Check if object is a CounterText without importing the class."""
    return type(obj).__name__ == 'CounterText'


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
        from himotoki.lookup.conj_data import get_word_conj_data
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

