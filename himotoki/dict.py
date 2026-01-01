"""
Dictionary module for Himotoki.

Core dictionary operations including word lookup, segmentation,
scoring, and word information extraction.

Mirrors dict.lisp from the original Ichiran.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union, Set
import json
import re

from himotoki.conn import (
    query, query_one, query_column, query_single, 
    execute, insert, get_connection, Cache, defcache
)
from himotoki.characters import (
    test_word, is_kana, is_kanji, mora_length, 
    as_hiragana, count_char_class, kanji_regex, kanji_match,
    sequential_kanji_positions, consecutive_char_groups,
    get_char_class, MODIFIER_CHARACTERS, KANA_CHARACTERS,
    long_vowel_modifier_p, ITERATION_CHARACTERS
)
from himotoki.settings import MAX_WORD_LENGTH, SCORE_CUTOFF, GAP_PENALTY, SEGMENT_SCORE_CUTOFF


# ============================================================================
# Data Classes (DAO equivalents)
# ============================================================================

@dataclass
class Entry:
    """Dictionary entry from JMdict."""
    seq: int
    content: str
    root_p: bool = False
    n_kanji: int = 0
    n_kana: int = 0
    primary_nokanji: bool = False
    
    @classmethod
    def get(cls, seq: int) -> Optional['Entry']:
        """Get an entry by sequence number."""
        row = query_one(
            "SELECT seq, content, root_p, n_kanji, n_kana, primary_nokanji "
            "FROM entry WHERE seq = ?", (seq,)
        )
        if row:
            return cls(
                seq=row['seq'],
                content=row['content'],
                root_p=bool(row['root_p']),
                n_kanji=row['n_kanji'],
                n_kana=row['n_kana'],
                primary_nokanji=bool(row['primary_nokanji'])
            )
        return None


@dataclass
class SimpleText:
    """Base class for text representations."""
    id: int
    seq: int
    text: str
    ord: int
    common: Optional[int]
    common_tags: str = ""
    conjugate_p: bool = True
    nokanji: bool = False
    conjugations: Optional[List[int]] = None
    hintedp: bool = False
    
    def word_type(self) -> str:
        return "gap"
    
    def get_kana(self) -> str:
        return self.text
    
    def get_kanji(self) -> Optional[str]:
        return None
    
    def get_text(self) -> str:
        return self.text


@dataclass
class KanjiText(SimpleText):
    """Kanji text representation."""
    best_kana: Optional[str] = None
    
    def word_type(self) -> str:
        return "kanji"
    
    def get_kana(self) -> str:
        if self.best_kana:
            return self.best_kana
        # Fallback: query kana readings
        kana = query_column(
            "SELECT text FROM kana_text WHERE seq = ? ORDER BY ord",
            (self.seq,)
        )
        return kana[0] if kana else self.text
    
    def get_kanji(self) -> str:
        return self.text
    
    @classmethod
    def from_row(cls, row) -> 'KanjiText':
        return cls(
            id=row['id'],
            seq=row['seq'],
            text=row['text'],
            ord=row['ord'],
            common=row['common'] if row['common'] is not None else None,
            common_tags=row['common_tags'] or "",
            conjugate_p=bool(row['conjugate_p']),
            nokanji=bool(row['nokanji']),
            best_kana=row['best_kana'] if row['best_kana'] else None
        )


@dataclass
class KanaText(SimpleText):
    """Kana text representation."""
    best_kanji: Optional[str] = None
    
    def word_type(self) -> str:
        return "kana"
    
    def get_kana(self) -> str:
        return self.text
    
    def get_kanji(self) -> Optional[str]:
        if self.nokanji:
            return None
        return self.best_kanji
    
    @classmethod
    def from_row(cls, row) -> 'KanaText':
        return cls(
            id=row['id'],
            seq=row['seq'],
            text=row['text'],
            ord=row['ord'],
            common=row['common'] if row['common'] is not None else None,
            common_tags=row['common_tags'] or "",
            conjugate_p=bool(row['conjugate_p']),
            nokanji=bool(row['nokanji']),
            best_kanji=row['best_kanji'] if row['best_kanji'] else None
        )


@dataclass 
class ProxyText:
    """Modified spelling wrapper for a text object."""
    source: SimpleText
    text: str
    kana: str
    
    def word_type(self) -> str:
        return self.source.word_type()
    
    @property
    def seq(self) -> int:
        return self.source.seq
    
    @property
    def common(self) -> Optional[int]:
        return self.source.common
    
    @property
    def ord(self) -> int:
        return self.source.ord
    
    @property
    def nokanji(self) -> bool:
        return self.source.nokanji
    
    @property
    def conjugations(self):
        return self.source.conjugations
    
    @conjugations.setter
    def conjugations(self, value):
        self.source.conjugations = value
    
    def get_text(self) -> str:
        return self.text
    
    def get_kana(self) -> str:
        return self.kana
    
    def get_kanji(self) -> Optional[str]:
        return self.source.get_kanji()
    
    def true_text(self) -> str:
        if isinstance(self.source, ProxyText):
            return self.source.true_text()
        return self.source.text


@dataclass
class CompoundText:
    """Multiple words combined together."""
    text: str
    kana: str
    primary: SimpleText
    words: List[SimpleText]
    score_base: Optional[SimpleText] = None
    score_mod: int = 0
    suffix_class: Optional[str] = None  # Suffix class for description (e.g., 'iru', 'aru')
    
    def word_type(self) -> str:
        return self.primary.word_type()
    
    @property
    def seq(self) -> List[int]:
        return [w.seq for w in self.words]
    
    @property
    def common(self) -> Optional[int]:
        return self.primary.common
    
    @property
    def ord(self) -> int:
        return self.primary.ord
    
    def get_text(self) -> str:
        return self.text
    
    def get_kana(self) -> str:
        return self.kana
    
    @property
    def conjugations(self):
        if self.words:
            return self.words[-1].conjugations
        return None
    
    @conjugations.setter
    def conjugations(self, value):
        if self.words:
            self.words[-1].conjugations = value


@dataclass
class ConjugatedText:
    """
    Conjugated form of a dictionary word.
    
    Represents inflected forms like 書いた (past of 書く) or 食べている (progressive of 食べる).
    """
    id: int
    seq: int
    text: str  # Conjugated form (e.g., 書いた)
    reading: str  # Reading of conjugated form
    conj_type: int  # Conjugation type (1=non-past, 2=past, etc.)
    pos: str  # POS tag (v5k, v1, adj-i, etc.)
    neg: bool  # Is negative form
    fml: bool  # Is formal/polite form
    source_text: str  # Dictionary form (e.g., 書く)
    source_reading: str  # Reading of dictionary form
    common: Optional[int] = None  # Commonness score from source entry
    ord: int = 0
    nokanji: bool = False
    conjugate_p: bool = False  # Already conjugated, don't conjugate again
    conjugations: Optional[List[int]] = None
    
    def word_type(self) -> str:
        """Return word type based on whether text contains kanji."""
        if any('\u4e00' <= c <= '\u9fff' for c in self.text):
            return "kanji"
        return "kana"
    
    def get_text(self) -> str:
        return self.text
    
    def get_kana(self) -> str:
        return self.reading
    
    def get_kanji(self) -> Optional[str]:
        if self.word_type() == "kanji":
            return self.text
        return None
    
    def get_source_text(self) -> str:
        """Get the dictionary form."""
        return self.source_text
    
    def get_conj_description(self) -> str:
        """Human-readable conjugation description."""
        from himotoki.conjugations import get_conj_description
        desc = get_conj_description(self.conj_type)
        if self.neg:
            desc += " Negative"
        if self.fml:
            desc += " Polite"
        return desc
    
    @classmethod
    def from_row(cls, row) -> 'ConjugatedText':
        # Handle sqlite3.Row which doesn't have .get()
        common = None
        try:
            common = row['common']
        except (KeyError, IndexError):
            pass
        
        return cls(
            id=row['id'],
            seq=row['seq'],
            text=row['text'],
            reading=row['reading'],
            conj_type=row['conj_type'],
            pos=row['pos'],
            neg=bool(row['neg']),
            fml=bool(row['fml']),
            source_text=row['source_text'],
            source_reading=row['source_reading'],
            common=common
        )


@dataclass
class Sense:
    """Sense (meaning group) for a dictionary entry."""
    id: int
    seq: int
    ord: int
    
    @classmethod
    def for_entry(cls, seq: int) -> List['Sense']:
        rows = query(
            "SELECT id, seq, ord FROM sense WHERE seq = ? ORDER BY ord",
            (seq,)
        )
        return [cls(id=r['id'], seq=r['seq'], ord=r['ord']) for r in rows]


@dataclass
class Gloss:
    """English definition for a sense."""
    id: int
    sense_id: int
    text: str
    ord: int
    
    @classmethod
    def for_sense(cls, sense_id: int) -> List['Gloss']:
        rows = query(
            "SELECT id, sense_id, text, ord FROM gloss "
            "WHERE sense_id = ? ORDER BY ord",
            (sense_id,)
        )
        return [cls(
            id=r['id'], sense_id=r['sense_id'],
            text=r['text'], ord=r['ord']
        ) for r in rows]


@dataclass
class SenseProp:
    """Sense property (POS, misc, field, etc.)."""
    id: int
    tag: str
    sense_id: int
    text: str
    ord: int
    seq: int


@dataclass
class Conjugation:
    """Conjugation link between entries."""
    id: int
    seq: int
    from_seq: int
    via: Optional[int] = None


@dataclass
class ConjProp:
    """Conjugation properties."""
    id: int
    conj_id: int
    conj_type: int
    pos: str
    neg: Optional[bool] = None
    fml: Optional[bool] = None


@dataclass
class ConjData:
    """Aggregated conjugation data."""
    seq: int
    from_seq: int
    via: Optional[int]
    prop: ConjProp
    src_map: List[Tuple[str, str]]


# ============================================================================
# Conjugation Type Descriptions
# ============================================================================

CONJ_DESCRIPTIONS = {
    1: "Negative",
    2: "Past (~ta)",
    3: "Conjunctive (~te)",
    4: "Provisional (~eba)",
    5: "Potential",
    6: "Passive",
    7: "Causative",
    8: "Causative-Passive",
    9: "Volitional (~ou)",
    10: "Imperative",
    11: "Conditional (~tara)",
    12: "Alternative (~tari)",
    13: "Continuative (ren'youkei)",
    14: "Negative Stem",
}


def get_conj_description(conj_type: int) -> str:
    """Get human-readable description for a conjugation type."""
    return CONJ_DESCRIPTIONS.get(conj_type, f"Type {conj_type}")


# ============================================================================
# Word Lookup Functions
# ============================================================================

def lookup_conjugation(text: str) -> List[Dict]:
    """
    Look up a conjugated form to find its dictionary entry.
    
    Args:
        text: Conjugated form to look up (e.g., 食べた, 行った).
        
    Returns:
        List of dictionaries with conjugation info:
        - seq: Dictionary entry sequence number
        - source_text: Dictionary form
        - source_reading: Dictionary form reading
        - conj_type: Conjugation type ID
        - conj_desc: Conjugation description
        - pos: Part of speech
        - neg: Whether negative form
        - fml: Whether formal form
    """
    from himotoki.conjugations import get_conj_description
    from himotoki.characters import as_hiragana
    
    text_hiragana = as_hiragana(text)
    
    # Try looking up in conj_lookup table
    # Join with text tables to get commonness for ranking
    # Prioritize exact text match, then by commonness of the SOURCE form
    rows = query(
        """
        SELECT c.seq, c.source_text, c.source_reading, c.conj_type, c.pos, c.neg, c.fml,
               kt.common as kt_common,
               CASE WHEN c.text = ? THEN 0 ELSE 1 END as text_match_priority,
               CASE WHEN c.reading = ? THEN 0 ELSE 1 END as reading_match_priority
        FROM conj_lookup c
        LEFT JOIN kanji_text kt ON kt.seq = c.seq AND kt.text = c.source_text
        WHERE c.text = ? OR c.reading = ?
        ORDER BY text_match_priority, 
                 COALESCE(kt.common, 999),
                 reading_match_priority,
                 c.seq
        """,
        (text, text_hiragana, text, text_hiragana)
    )
    
    results = []
    seen = set()
    
    for row in rows:
        key = (row['seq'], row['conj_type'], row['neg'], row['fml'])
        if key in seen:
            continue
        seen.add(key)
        
        results.append({
            'seq': row['seq'],
            'source_text': row['source_text'],
            'source_reading': row['source_reading'],
            'conj_type': row['conj_type'],
            'conj_desc': get_conj_description(row['conj_type']),
            'pos': row['pos'],
            'neg': bool(row['neg']) if row['neg'] is not None else None,
            'fml': bool(row['fml']) if row['fml'] is not None else None,
        })
    
    return results


def find_word(word: str, root_only: bool = False) -> List[SimpleText]:
    """
    Find dictionary entries matching a word.
    
    Args:
        word: Word to search for.
        root_only: If True, only return root forms (not conjugated).
        
    Returns:
        List of matching text objects.
    """
    if len(word) > MAX_WORD_LENGTH:
        return []
    
    # Determine which table to search
    table = 'kana_text' if is_kana(word) else 'kanji_text'
    text_class = KanaText if is_kana(word) else KanjiText
    
    if root_only:
        rows = query(
            f"SELECT wt.* FROM {table} wt "
            f"INNER JOIN entry ON wt.seq = entry.seq "
            f"WHERE wt.text = ? AND entry.root_p = 1",
            (word,)
        )
    else:
        rows = query(f"SELECT * FROM {table} WHERE text = ?", (word,))
    
    return [text_class.from_row(row) for row in rows]


def get_conjugation_info_for_seq(seq: int) -> Optional[Dict]:
    """
    Look up conjugation info for a given seq.
    
    This finds if a dictionary entry is derived from another entry
    (e.g., で particle is te-form of だ copula).
    
    Args:
        seq: Sequence number to look up.
        
    Returns:
        Dictionary with conjugation info, or None if not a conjugated form.
    """
    from himotoki.conjugations import get_conj_description as get_conj_desc
    
    # Check conjugation table for this seq
    rows = query(
        """
        SELECT c.from_seq, cp.conj_type, cp.pos, cp.neg, cp.fml,
               ka.text as source_text, ka.text as source_reading
        FROM conjugation c
        JOIN conj_prop cp ON cp.conj_id = c.id
        JOIN kana_text ka ON ka.seq = c.from_seq
        WHERE c.seq = ?
        ORDER BY cp.conj_type
        LIMIT 1
        """,
        (seq,)
    )
    
    if not rows:
        return None
    
    row = rows[0]
    return {
        'type': get_conj_desc(row['conj_type']),
        'conj_type': row['conj_type'],
        'pos': row['pos'],
        'neg': bool(row['neg']) if row['neg'] is not None else False,
        'fml': bool(row['fml']) if row['fml'] is not None else False,
        'source_text': row['source_text'],
        'source_reading': row['source_reading'],
    }


def find_word_as_hiragana(word: str, exclude: Optional[List[int]] = None,
                          finder=None) -> List[ProxyText]:
    """
    Find words treating katakana as hiragana.
    
    Args:
        word: Word (potentially katakana) to search.
        exclude: Sequence numbers to exclude.
        finder: Custom finder function.
        
    Returns:
        List of ProxyText wrapping matching entries.
    """
    hiragana = as_hiragana(word)
    if hiragana == word:
        return []
    
    if finder:
        words = finder(hiragana)
    else:
        words = find_word(hiragana, root_only=True)
    
    if not words:
        return []
    
    exclude_set = set(exclude or [])
    result = []
    
    for w in words:
        if w.seq not in exclude_set:
            result.append(ProxyText(
                source=w,
                text=word,
                kana=word
            ))
    
    return result


def find_word_full(word: str, as_hiragana_flag: bool = False,
                   counter=None, suffix_map: Optional[Dict] = None,
                   suffix_next_end: Optional[int] = None) -> List[SimpleText]:
    """
    Extended word search including suffixes and hiragana conversion.
    
    Matches Ichiran's find-word-full function.
    
    Args:
        word: Word to search.
        as_hiragana_flag: If True, also search as hiragana.
        counter: Counter mode ('auto' or offset value).
        suffix_map: Pre-computed suffix map for the full text.
        suffix_next_end: End position for suffix lookup.
        
    Returns:
        List of matching text objects.
    """
    simple_words = find_word(word)
    results = list(simple_words)
    
    # Add suffix matches (passing through suffix_map and suffix_next_end)
    suffix_matches = find_word_suffix(word, matches=simple_words,
                                      suffix_map=suffix_map,
                                      suffix_next_end=suffix_next_end)
    results.extend(suffix_matches)
    
    # Add hiragana matches
    if as_hiragana_flag:
        hira_matches = find_word_as_hiragana(
            word, 
            exclude=[w.seq for w in simple_words]
        )
        results.extend(hira_matches)
    
    # Add counter matches
    if counter:
        counter_matches = find_counter_words(word, counter)
        results.extend(counter_matches)
    
    return results


def find_word_suffix(word: str, matches: Optional[List[SimpleText]] = None,
                     suffix_map: Optional[Dict] = None,
                     suffix_next_end: Optional[int] = None) -> List:
    """
    Find words that are root + suffix combinations.
    
    Calls the implementation in dict_suffixes.py.
    
    Args:
        word: Word to analyze.
        matches: Existing matches to check uniqueness against.
        suffix_map: Pre-computed suffix map (from get_suffix_map).
        suffix_next_end: Position for suffix lookup in suffix_map.
        
    Returns:
        List of CompoundText objects.
    """
    from himotoki.dict_suffixes import find_word_suffix as _find_word_suffix
    return _find_word_suffix(word, suffix_map=suffix_map, 
                             suffix_next_end=suffix_next_end,
                             matches=matches)


def find_counter_words(word: str, counter) -> List:
    """
    Find counter word combinations.
    
    Args:
        word: The word to check for counter patterns
        counter: Counter mode ('auto' or offset value)
        
    Returns:
        List of CounterText objects if a counter pattern is detected
    """
    from himotoki.dict_counters import detect_counter, init_counters, CounterText
    
    # Make sure counters are initialized
    init_counters()
    
    result = detect_counter(word)
    if result:
        num_value, counter_text, reading = result
        
        # Try to get the seq for the counter from the dictionary
        counter_seq = None
        counter_entry = find_word(counter_text)
        if counter_entry:
            # Use the first matching entry's seq
            counter_seq = counter_entry[0].seq
        
        # Create a CounterText object
        return [CounterText(
            text=word,
            reading=reading,
            number=num_value,
            counter_text=counter_text,
            seq=counter_seq
        )]
    return []


# ============================================================================
# Segmentation Data Structures
# ============================================================================

@dataclass
class Segment:
    """A single word segment in the text."""
    start: int
    end: int
    word: SimpleText
    score: int = 0
    info: Optional[Dict] = None
    top: bool = False
    _text: Optional[str] = None
    
    @property
    def text(self) -> str:
        if self._text is not None:
            return self._text
        return self.word.get_text()
    
    @text.setter
    def text(self, value: str):
        self._text = value


@dataclass
class SegmentList:
    """List of alternative segments at the same position."""
    segments: List[Segment]
    start: int
    end: int
    top: Optional[Any] = None
    matches: int = 0


# ============================================================================
# Scoring Functions
# ============================================================================

# Length coefficient sequences
LENGTH_COEFF_SEQUENCES = {
    'strong': [1, 8, 24, 40, 60],
    'weak': [1, 4, 9, 16, 25, 36],
    'tail': [4, 9, 16, 24],
    'ltail': [4, 12, 18, 24],
}

# Particles that are commonly absorbed into phrase entries
# but should often be separate grammatical markers
ABSORBED_PARTICLES = {'は', 'が', 'を', 'に', 'で', 'と', 'へ', 'も', 'の'}

# Exceptions: entries that legitimately end with particles
# that should NOT be penalized (e.g., conjunctions, adverbs)
PARTICLE_ENDING_EXCEPTIONS = {
    1008450,   # では (well then) - conjunction
    2089020,   # だ (copula)
    1628500,   # です (copula)
    1324320,   # もしくは (or) - conjunction
    1524990,   # または (or) - conjunction
    1586850,   # あるいは (or / perhaps) - conjunction
}


def get_phrase_length_penalty(word) -> int:
    """
    Get length penalty for phrase entries that absorb particles.
    
    Following Ichiran's def-simple-hint system, expressions and 
    interjections ending with は (and other particles) get their
    effective length reduced by 1.
    
    This ensures 今日は天気がいい segments as 今日 | は | 天気 | が...
    rather than treating 今日は as a greeting.
    
    Args:
        word: Word object to check.
        
    Returns:
        Length penalty (0 or 1).
    """
    text = word.get_text() if hasattr(word, 'get_text') else str(word)
    seq = word.seq if hasattr(word, 'seq') else None
    
    # Skip known exceptions (conjunctions, copulae)
    if seq and seq in PARTICLE_ENDING_EXCEPTIONS:
        return 0
    
    # Check if text ends with a common particle
    if len(text) < 2:
        return 0
    
    last_char = text[-1]
    if last_char not in ABSORBED_PARTICLES:
        return 0
    
    # Get POS - penalize expressions, phrases, AND interjections ending with particles
    if seq:
        pos_rows = list(query("SELECT text FROM sense_prop WHERE seq = ? AND tag = 'pos'", (seq,)))
        for row in pos_rows:
            pos_text = (row['text'] or '').lower()
            # Penalize expressions/phrases that absorb particles
            if 'expression' in pos_text:
                return 1  # Reduce effective length by 1
            # Interjections ending with は also get penalized (per Ichiran)
            # This handles greetings like こんにちは, こんばんは
            if 'interjection' in pos_text and last_char == 'は':
                return 1
    
    return 0


# Embedded particles that expressions shouldn't absorb
EMBEDDED_PARTICLES = {'が', 'を', 'に', 'で', 'と', 'も'}


def get_embedded_particle_penalty(word) -> int:
    """
    Get penalty for expressions with embedded particles.
    
    Expressions like 気がいい (good-natured) contain embedded particles
    that could be better parsed as separate grammatical elements when
    preceded by words like 天気 (weather).
    
    Args:
        word: Word object to check.
        
    Returns:
        Penalty score (0 or positive value).
    """
    text = word.get_text() if hasattr(word, 'get_text') else str(word)
    seq = word.seq if hasattr(word, 'seq') else None
    
    if len(text) < 3:
        return 0
    
    # Check if first character is followed by an embedded particle
    # This catches patterns like 気が..., 物を..., etc.
    first_char = text[0]
    second_char = text[1] if len(text) > 1 else ''
    
    if second_char in EMBEDDED_PARTICLES:
        # Get POS - only penalize expressions
        if seq:
            pos_rows = list(query("SELECT text FROM sense_prop WHERE seq = ? AND tag = 'pos'", (seq,)))
            for row in pos_rows:
                pos_text = (row['text'] or '').lower()
                if 'expression' in pos_text:
                    return 10  # Significant penalty
        # Also penalize conjugated forms from expressions
        if hasattr(word, 'source_text'):
            source = word.source_text
            if len(source) > 1 and source[1] in EMBEDDED_PARTICLES:
                return 10
    
    return 0


def length_multiplier_coeff(length: int, class_type: str) -> int:
    """
    Get the length multiplier coefficient.
    
    Args:
        length: Word length in mora.
        class_type: 'strong' (kanji/katakana) or 'weak' (hiragana).
        
    Returns:
        Coefficient value.
    """
    coeffs = LENGTH_COEFF_SEQUENCES.get(class_type, LENGTH_COEFF_SEQUENCES['weak'])
    
    if 0 < length < len(coeffs):
        return coeffs[length]
    
    # Linear extrapolation beyond the table
    last = coeffs[-1]
    return length * (last // (len(coeffs) - 1))


# Words to skip in segmentation
from himotoki.constants import (
    SKIP_WORDS as _SKIP_WORDS,
    FINAL_PRT as _FINAL_PRT,
    SEMI_FINAL_PRT as _SEMI_FINAL_PRT,
    COPULA_DA,
)
SKIP_WORDS: Set[int] = _SKIP_WORDS

# Final-only particles
FINAL_PRT: Set[int] = _FINAL_PRT
SEMI_FINAL_PRT: Set[int] = _SEMI_FINAL_PRT
NON_FINAL_PRT: Set[int] = set()  # Currently empty in Ichiran too

# Words with no kanji break penalty
NO_KANJI_BREAK_PENALTY: Set[int] = set()

# Copulae
COPULAE: Set[int] = {COPULA_DA}  # だ

# Force kanji break words
FORCE_KANJI_BREAK: Set[str] = set()

# Weak conjugation forms (don't count for primary)
WEAK_CONJ_FORMS = []


def calc_score(reading, final: bool = False, use_length: Optional[int] = None,
               score_mod: int = 0, kanji_break: Optional[List[int]] = None) -> Tuple[int, Dict]:
    """
    Calculate the score for a reading.
    
    This is a simplified version of the scoring algorithm.
    The full version considers many factors including commonness,
    conjugation, part of speech, etc.
    
    Args:
        reading: Text object to score.
        final: Whether this is the final word in the sentence.
        use_length: Override length for scoring.
        score_mod: Score modifier.
        kanji_break: Kanji break positions.
        
    Returns:
        Tuple of (score, info_dict).
    """
    # Import CounterText for type checking
    from himotoki.dict_counters import CounterText
    
    # Handle counter words - they get high score since they're valid semantic units
    if isinstance(reading, CounterText):
        text = reading.get_text()
        length = max(1, mora_length(text))
        n_kanji = count_char_class(text, 'kanji')
        kanji_p = n_kanji > 0
        
        # Counter words get a high base score - higher than the sum of individual kanji
        # For 三匹: individual kanji would score about 216 each = 432 total
        # Counter should score higher to prefer the combined form
        prop_score = 25  # Base score for counters
        
        # Length bonus - longer is better (三匹 > 三 + 匹)
        score = prop_score * length_multiplier_coeff(length, 'strong')
        
        # Add significant bonus for kanji counters (favors combined form)
        if kanji_p:
            score += 20 * n_kanji
        
        # Extra bonus for being a semantic unit (not just multiple chars)
        score += 50  # Bonus for counter being a recognized unit
        
        info = {
            'posi': [],
            'seq_set': [],
            'conj': None,
            'common': reading.common,
            'score_info': [prop_score, [], 0, None],
            'kpcl': [kanji_p, True, True, length > 3],
            'counter': (reading.number, reading.counter_text),
        }
        
        return score, info
    
    # Handle compound words
    if isinstance(reading, CompoundText):
        base = reading.score_base or reading.primary
        score, info = calc_score(
            base,
            use_length=mora_length(reading.text),
            score_mod=reading.score_mod
        )
        info['conj'] = None  # TODO: get_conj_data
        return score, info
    
    # Handle conjugated forms
    if isinstance(reading, ConjugatedText):
        text = reading.text
        kanji_p = reading.word_type() == "kanji"
        katakana_p = not kanji_p and count_char_class(text, 'katakana_uniq') > 0
        
        length = max(1, mora_length(text))
        seq = reading.seq
        ordinal = reading.ord
        common = reading.common
        
        # Base scoring - conjugated forms get bonus for being recognized
        score = 1
        prop_score = 0
        
        # Common word bonus
        if common is not None:
            if common == 0:
                prop_score += 10
            else:
                prop_score += max(1, 20 - common)
        else:
            # Default reasonable score for conjugated forms
            prop_score += 5
        
        # Conjugated form bonus - prefer recognized conjugations over fragments
        conj_type = reading.conj_type
        pos = reading.pos
        source_text = reading.source_text
        STEM_TYPES = {50, 51, 52, 53}  # ADVERBIAL, ADJ_STEM, NEG_STEM, CAUSATIVE_SU
        
        # Check for problematic suru-verb (vs-i/vs-s) conjugations
        # Suru-verb potential/passive/causative should be できる/される/させる
        # NOT kanji forms like 帰る (potential of 帰化)
        is_suru_verb = pos in ('vs-i', 'vs-s')
        is_suru_special_conj = conj_type in (5, 6, 7, 8)  # potential, passive, causative, caus-pass
        is_bad_suru_conj = (is_suru_verb and is_suru_special_conj and 
                           kanji_p and  # The conjugated form has kanji
                           source_text and text != source_text and
                           not text.endswith('できる') and 
                           not text.endswith('される') and
                           not text.endswith('させる'))
        
        if conj_type in STEM_TYPES:
            # Stems don't get the full bonus unless followed by something
            prop_score += 2  # Reduced bonus
        elif is_bad_suru_conj:
            # Likely a database bug - suru-verb conjugation with wrong kanji form
            # e.g., 帰化 -> 帰る (should be 帰化できる)
            prop_score += 1  # Minimal bonus
        else:
            # Normal conjugation bonus
            prop_score += 8
        
        # Kanji/katakana bonus
        if kanji_p or katakana_p:
            prop_score += 3
        
        # Length-based scoring
        n_kanji = count_char_class(text, 'kanji')
        class_type = 'strong' if (kanji_p or katakana_p) else 'weak'
        
        prop_score = max(1, prop_score)
        score = prop_score * (
            length_multiplier_coeff(length, class_type) +
            (5 * (n_kanji - 1) if n_kanji > 1 else 0)
        )
        
        # Apply use_length bonus for compound words
        if use_length and use_length > length:
            tail_class = 'ltail' if length > 3 and (kanji_p or katakana_p) else 'tail'
            score += prop_score * length_multiplier_coeff(use_length - length, tail_class)
            score += score_mod * prop_score * (use_length - length)
        
        # Conjugation info
        conj_info = {
            'type': reading.conj_type,
            'pos': reading.pos,
            'neg': reading.neg,
            'fml': reading.fml,
            'source': reading.source_text,
        }
        
        info = {
            'posi': [],
            'seq_set': [seq] if seq else [],
            'conj': conj_info,
            'common': common,
            'score_info': [prop_score, kanji_break, 0, None],
            'kpcl': [kanji_p or katakana_p, ordinal == 0, common is not None, length > 3],
        }
        
        return score, info
    
    # Basic scoring
    text = reading.get_text()
    kanji_p = reading.word_type() == "kanji"
    katakana_p = not kanji_p and count_char_class(text, 'katakana_uniq') > 0
    
    length = max(1, mora_length(text))
    seq = reading.seq
    ordinal = reading.ord
    common = reading.common
    
    # Get entry info
    entry = Entry.get(seq) if seq else None
    root_p = entry.root_p if entry else False
    
    # Base scoring
    score = 1
    prop_score = 0
    
    # Common word bonus
    common_p = common is not None
    if common_p:
        if common == 0:
            prop_score += 10
        else:
            prop_score += max(1, 20 - common)
    
    # Primary reading bonus
    if ordinal == 0:
        prop_score += 5
    
    # Kanji/katakana bonus
    if kanji_p or katakana_p:
        prop_score += 3
    
    # Length-based scoring
    n_kanji = count_char_class(text, 'kanji')
    class_type = 'strong' if (kanji_p or katakana_p) else 'weak'
    
    # Apply phrase length penalty for expressions that absorb particles
    phrase_penalty = get_phrase_length_penalty(reading)
    effective_length = max(1, length - phrase_penalty)
    
    prop_score = max(1, prop_score)
    score = prop_score * (
        length_multiplier_coeff(effective_length, class_type) +
        (5 * (n_kanji - 1) if n_kanji > 1 else 0)
    )
    
    # Use length bonus
    if use_length and use_length > length:
        tail_class = 'ltail' if length > 3 and (kanji_p or katakana_p) else 'tail'
        score += prop_score * length_multiplier_coeff(use_length - length, tail_class)
        score += score_mod * prop_score * (use_length - length)
    
    # Particle scoring - matches Ichiran's calc-score (dict.lisp:896-902)
    # Particles get a boost to ensure they're selected over homophone nouns/verbs
    posi = []
    if seq:
        from himotoki.synergies import get_pos_tags
        posi = list(get_pos_tags(seq))
    
    # Check for actual particle POS tags - be specific to avoid false positives
    # like "nouns which may take the genitive case particle 'no'"
    PARTICLE_POS_PATTERNS = {
        'particle', 'prt', 'case-marking particle', 'conjunction particle',
        'adverbial particle', 'sentence-ending particle', 'final particle'
    }
    particle_p = any(
        any(pattern == p or p.startswith(pattern + ' ') or p.endswith(' ' + pattern) 
            for pattern in PARTICLE_POS_PATTERNS)
        for p in posi
    )
    semi_final_particle_p = seq in SEMI_FINAL_PRT if seq else False
    non_final_particle_p = seq in NON_FINAL_PRT if seq else False
    
    if particle_p:
        # Ichiran: (when (and particle-p (or final (not semi-final-particle-p)))
        if final or not semi_final_particle_p:
            score += 2 * prop_score  # Scale by prop_score for consistency
            if common_p:
                score += (2 + length) * prop_score
            if final and not non_final_particle_p:
                if ordinal == 0:  # primary-p
                    score += 5 * prop_score
                elif semi_final_particle_p:
                    score += 2 * prop_score
    
    info = {
        'posi': posi,
        'seq_set': [seq] if seq else [],
        'conj': None,
        'common': common,
        'score_info': [prop_score, kanji_break, 0, None],
        'kpcl': [kanji_p or katakana_p, ordinal == 0, common_p, length > 3],
    }
    
    return score, info


def gen_score(segment: Segment, final: bool = False,
              kanji_break: Optional[List[int]] = None) -> Segment:
    """Generate score for a segment."""
    segment.score, segment.info = calc_score(
        segment.word, final=final, kanji_break=kanji_break
    )
    return segment


# ============================================================================
# Sticky Positions (word boundary restrictions)
# ============================================================================

def find_sticky_positions(text: str) -> List[int]:
    """
    Find positions where word boundaries are not allowed.
    
    Words cannot start after sokuon or before yoon characters.
    
    Args:
        text: Text to analyze.
        
    Returns:
        List of sticky positions.
    """
    modifiers = set()
    for chars in MODIFIER_CHARACTERS.values():
        modifiers.update(chars)
    for chars in ITERATION_CHARACTERS.values():
        modifiers.update(chars)
    
    sticky = []
    
    for pos, char in enumerate(text):
        char_class = get_char_class(char)
        
        # Position after sokuon is sticky
        if char_class == 'sokuon':
            if pos < len(text) - 1:
                next_char = text[pos + 1]
                if get_char_class(next_char) in KANA_CHARACTERS:
                    sticky.append(pos + 1)
        
        # Position of modifier is sticky
        elif char in modifiers or char_class in MODIFIER_CHARACTERS:
            if pos < len(text) - 1:
                # Unless it's a long vowel at end or extending previous vowel
                if char_class != 'long_vowel' or (
                    pos > 0 and not long_vowel_modifier_p(char_class, text[pos - 1])
                ):
                    sticky.append(pos)
    
    return sticky


# ============================================================================
# Substring Word Finding
# ============================================================================

def find_substring_words(text: str, sticky: Optional[List[int]] = None) -> Dict[str, List]:
    """
    Find all dictionary matches for substrings.
    
    Args:
        text: Text to search.
        sticky: Positions to skip.
        
    Returns:
        Dictionary mapping substrings to matches.
    """
    if sticky is None:
        sticky = []
    
    sticky_set = set(sticky)
    substring_hash = {}
    kana_keys = []
    kanji_keys = []
    
    # Collect all substrings
    for start in range(len(text)):
        if start in sticky_set:
            continue
        for end in range(start + 1, min(len(text) + 1, start + MAX_WORD_LENGTH + 1)):
            if end in sticky_set:
                continue
            part = text[start:end]
            substring_hash[part] = []
            if is_kana(part):
                kana_keys.append(part)
            else:
                kanji_keys.append(part)
    
    # Query kana matches
    if kana_keys:
        unique_keys = list(set(kana_keys))
        placeholders = ','.join('?' * len(unique_keys))
        rows = query(
            f"SELECT * FROM kana_text WHERE text IN ({placeholders})",
            tuple(unique_keys)
        )
        for row in rows:
            text_key = row['text']
            if text_key in substring_hash:
                substring_hash[text_key].append(KanaText.from_row(row))
    
    # Query kanji matches
    if kanji_keys:
        unique_keys = list(set(kanji_keys))
        placeholders = ','.join('?' * len(unique_keys))
        rows = query(
            f"SELECT * FROM kanji_text WHERE text IN ({placeholders})",
            tuple(unique_keys)
        )
        for row in rows:
            text_key = row['text']
            if text_key in substring_hash:
                substring_hash[text_key].append(KanjiText.from_row(row))
    
    # Query conjugated forms (both kana and kanji)
    all_keys = list(set(kana_keys + kanji_keys))
    if all_keys:
        placeholders = ','.join('?' * len(all_keys))
        # Use window function to pick only the best entry per (text, seq, conj_type, neg, fml)
        # Prefer kanji source_text over kana
        # Get common score from the entry's kana form (most reliable) or the source_text's common
        rows = query(
            f"""SELECT * FROM (
                SELECT c.*, 
                       COALESCE(entry_kana.common, k.common, n.common) as common,
                       CASE WHEN k.text IS NOT NULL THEN 0 ELSE 1 END as kanji_priority,
                       ROW_NUMBER() OVER (
                           PARTITION BY c.text, c.seq, c.conj_type, c.neg, c.fml
                           ORDER BY CASE WHEN k.text IS NOT NULL THEN 0 ELSE 1 END
                       ) as rn
                FROM conj_lookup c
                LEFT JOIN kanji_text k ON c.seq = k.seq AND c.source_text = k.text
                LEFT JOIN kana_text n ON c.seq = n.seq AND c.source_text = n.text
                LEFT JOIN kana_text entry_kana ON c.seq = entry_kana.seq AND entry_kana.ord = 0
                WHERE c.text IN ({placeholders})
            ) WHERE rn = 1""",
            tuple(all_keys)
        )
        for row in rows:
            text_key = row['text']
            if text_key in substring_hash:
                # Skip conjugated forms when there's already a good dictionary entry
                # The dictionary entry will get conjugation info via get_conjugation_info_for_seq()
                existing = substring_hash[text_key]
                has_good_dict_entry = any(
                    not isinstance(e, ConjugatedText) and 
                    getattr(e, 'common', None) is not None and
                    getattr(e, 'common', 999) <= 10
                    for e in existing
                )
                
                if has_good_dict_entry:
                    continue
                    
                conj = ConjugatedText.from_row(row)
                substring_hash[text_key].append(conj)
    
    return substring_hash


# ============================================================================
# Main Segmentation Algorithm
# ============================================================================

def join_substring_words(text: str) -> List[SegmentList]:
    """
    Find all possible word segments in text.
    
    Matches Ichiran's join-substring-words* function.
    
    Args:
        text: Text to segment.
        
    Returns:
        List of SegmentLists at each position.
    """
    from himotoki.dict_suffixes import get_suffix_map
    
    sticky = find_sticky_positions(text)
    substring_hash = find_substring_words(text, sticky)
    sticky_set = set(sticky)
    
    katakana_groups = consecutive_char_groups(text, 'katakana')
    number_groups = consecutive_char_groups(text, 'number')
    
    # Create suffix map for the full text (matches Ichiran's get-suffix-map)
    suffix_map = get_suffix_map(text)
    
    # Find kanji break positions
    kanji_break = []
    ends = set()
    
    result = []
    
    for start in range(len(text)):
        if start in sticky_set:
            continue
        
        # Find katakana and number group ends
        katakana_end = None
        for s, e in katakana_groups:
            if s == start:
                katakana_end = e
                break
        
        number_end = None
        for s, e in number_groups:
            if s == start:
                number_end = e
                break
        
        for end in range(start + 1, min(len(text) + 1, start + MAX_WORD_LENGTH + 1)):
            if end in sticky_set:
                continue
            
            part = text[start:end]
            
            # Find words
            as_hira = katakana_end and end == katakana_end
            counter = None
            if number_end and number_end <= end:
                d = number_end - start
                if d <= 20:
                    counter = d
            
            # Get matches from hash
            words = list(substring_hash.get(part, []))
            
            # Add suffix matches (te+iru compounds, etc.)
            # This matches Ichiran's call to find-word-suffix in find-word-full
            suffix_matches = find_word_suffix(part, matches=words,
                                              suffix_map=suffix_map,
                                              suffix_next_end=end)
            words.extend(suffix_matches)
            
            # Add hiragana matches for katakana
            if as_hira:
                hira_matches = find_word_as_hiragana(
                    part, exclude=[w.seq for w in words]
                )
                words.extend(hira_matches)
            
            # Add counter matches if this spans a number + counter
            # Ichiran adds counter matches alongside dictionary matches, not as fallback
            if counter and end > number_end:
                counter_matches = find_counter_words(part, counter)
                words.extend(counter_matches)
            
            if not words:
                continue
            
            # Create segments
            segments = [
                Segment(start=start, end=end, word=w)
                for w in words
            ]
            
            # Calculate kanji breaks
            if start == 0 or start in ends:
                if part not in FORCE_KANJI_BREAK:
                    kb = sequential_kanji_positions(part, start)
                    kanji_break.extend(kb)
            
            ends.add(end)
            result.append((start, end, segments))
    
    # Remove duplicate kanji breaks
    kanji_break = list(set(kanji_break))
    
    # Generate scores
    segment_lists = []
    for start, end, segments in result:
        kb = [n - start for n in kanji_break if n in (start, end)]
        
        final = end == len(text) or (
            text.endswith('ー') and end == len(text) - 1
        )
        
        scored_segments = []
        for seg in segments:
            gen_score(seg, final=final, kanji_break=kb)
            if seg.score >= SCORE_CUTOFF:
                scored_segments.append(seg)
        
        if scored_segments:
            # Sort by score descending, then by common (lower is better),
            # then by seq (lower seq = more fundamental word, e.g. する vs キスする)
            # For CompoundText, seq is a list, so use the first seq
            def get_seq(word):
                seq = word.seq
                if isinstance(seq, list):
                    return seq[0] if seq else 0
                return seq or 0
            
            scored_segments.sort(
                key=lambda s: (s.score, -(s.word.common or 999), -get_seq(s.word)),
                reverse=True
            )
            
            # Cull to reasonable number
            if len(scored_segments) > 1:
                max_score = scored_segments[0].score
                cutoff = max_score * 0.5
                scored_segments = [s for s in scored_segments if s.score >= cutoff]
            
            segment_lists.append(SegmentList(
                segments=scored_segments,
                start=start,
                end=end,
                matches=len(segments)
            ))
    
    return segment_lists


# ============================================================================
# Path Finding (Dynamic Programming)
# ============================================================================

@dataclass
class TopArrayItem:
    """Item in a top-k array."""
    score: int
    payload: List


class TopArray:
    """Maintains top-k items by score."""
    
    def __init__(self, limit: int = 5):
        self.limit = limit
        self.items: List[TopArrayItem] = []
    
    def register(self, score: int, payload: List):
        """Add an item, maintaining top-k."""
        item = TopArrayItem(score=score, payload=payload)
        
        # Find insertion point
        pos = 0
        for i, existing in enumerate(self.items):
            if existing.score < score:
                break
            pos = i + 1
        
        self.items.insert(pos, item)
        
        # Trim to limit
        if len(self.items) > self.limit:
            self.items = self.items[:self.limit]
    
    def get_items(self) -> List[TopArrayItem]:
        return self.items


def gap_penalty(start: int, end: int) -> int:
    """Calculate penalty for a gap between words."""
    return (end - start) * GAP_PENALTY


def find_best_path(segment_lists: List[SegmentList], str_length: int,
                   limit: int = 5, use_synergies: bool = True) -> List[Tuple[List, int]]:
    """
    Find the best segmentation paths using dynamic programming.
    
    This is a 1:1 port of Ichiran's path-finding algorithm.
    Uses synergy bonuses and penalties to improve segmentation
    quality by rewarding likely word combinations (noun+particle)
    and penalizing unlikely ones (consecutive 1-char kana).
    
    Args:
        segment_lists: Possible segments at each position.
        str_length: Length of the input string.
        limit: Maximum number of paths to return.
        use_synergies: Whether to apply synergy/penalty scoring.
        
    Returns:
        List of (path, score) tuples.
    """
    # Import synergy scoring (lazy import to avoid circular dependencies)
    if use_synergies:
        try:
            from himotoki.synergies import score_segment_pair
        except ImportError:
            use_synergies = False
    
    # Import segfilters
    try:
        from himotoki.dict_grammar import apply_segfilters
        use_segfilters = True
    except ImportError:
        use_segfilters = False
    
    def _get_seg_info(seg):
        """Extract seq and text from segment for segfilter checks.
        
        For CompoundText, returns the primary (first) seq.
        """
        if seg is None:
            return None, ""
        seq = getattr(seg, 'seq', None)
        if not seq:
            word = getattr(seg, 'word', None)
            if word:
                seq = getattr(word, 'seq', None)
        # Handle list seq (from CompoundText)
        if isinstance(seq, list):
            seq = seq[0] if seq else None
        text = getattr(seg, 'text', None) or ""
        if not text:
            word = getattr(seg, 'word', None)
            if word:
                text = getattr(word, 'text', None) or ""
        return seq, text
    
    top = TopArray(limit=limit)
    top.register(gap_penalty(0, str_length), [])
    
    # Initialize segment list tops
    for sl in segment_lists:
        sl.top = TopArray(limit=limit)
    
    # Process segments in order
    for i, seg1 in enumerate(segment_lists):
        gap_left = gap_penalty(0, seg1.start)
        gap_right = gap_penalty(seg1.end, str_length)
        
        # Register initial segments
        for seg in seg1.segments:
            score1 = seg.score
            seg1.top.register(gap_left + score1, [seg])
            top.register(gap_left + score1 + gap_right, [seg])
        
        # Look for connections to later segments
        for seg2 in segment_lists[i+1:]:
            if seg2.start < seg1.end:
                continue
            
            gap_mid = gap_penalty(seg1.end, seg2.start)
            gap_end = gap_penalty(seg2.end, str_length)
            
            for item in seg1.top.get_items():
                seg_left = item.payload[0] if item.payload else None
                if not seg_left:
                    continue
                
                score_left = seg_left.score
                score_tail = item.score - score_left
                
                for seg_right in seg2.segments:
                    score_right = seg_right.score
                    
                    # Apply segfilters to block bad combinations
                    if use_segfilters and seg1.end == seg2.start:
                        left_seq, left_text = _get_seg_info(seg_left)
                        right_seq, right_text = _get_seg_info(seg_right)
                        if apply_segfilters(left_seq, left_text, right_seq, right_text):
                            continue  # Skip this combination
                    
                    # Calculate synergy bonus/penalty between adjacent segments
                    synergy_score = 0
                    if use_synergies and seg1.end == seg2.start:
                        # Only apply synergy for directly adjacent segments
                        # score_segment_pair returns (score, reason)
                        syn_result = score_segment_pair(seg_left, seg_right)
                        if isinstance(syn_result, tuple):
                            synergy_score = syn_result[0]
                        else:
                            synergy_score = syn_result
                    
                    accum = gap_mid + max(score_left + score_right, score_left + 1, score_right + 1) + score_tail + synergy_score
                    path = [seg_right] + item.payload
                    
                    seg2.top.register(accum, path)
                    top.register(accum + gap_end, path)
    
    # Clean up
    for sl in segment_lists:
        sl.top = None
    
    # Return paths
    return [
        (list(reversed(item.payload)), item.score)
        for item in top.get_items()
    ]


# ============================================================================
# Word Info
# ============================================================================

@dataclass
class WordInfo:
    """Information about a segmented word."""
    type: str
    text: str
    kana: Union[str, List[str]]
    seq: Optional[Union[int, List[int]]] = None
    true_text: Optional[str] = None
    conjugations: Optional[Union[str, List]] = None
    score: int = 0
    components: Optional[List['WordInfo']] = None
    alternative: bool = False
    primary: bool = True
    start: Optional[int] = None
    end: Optional[int] = None
    counter: Optional[List] = None
    skipped: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'type': self.type,
            'text': self.text,
            'kana': self.kana,
            'seq': self.seq,
            'true_text': self.true_text,
            'conjugations': 'ROOT' if self.conjugations == 'root' else self.conjugations,
            'score': self.score,
            'components': [c.to_dict() for c in self.components] if self.components else None,
            'alternative': self.alternative,
            'primary': self.primary,
            'start': self.start,
            'end': self.end,
            'counter': self.counter,
            'skipped': self.skipped,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)


def word_info_from_segment(segment: Segment) -> WordInfo:
    """Create WordInfo from a Segment."""
    word = segment.word
    
    # Build conjugation info for ConjugatedText
    conjugations = None
    if isinstance(word, ConjugatedText):
        conjugations = [{
            'type': word.get_conj_description(),
            'conj_type': word.conj_type,
            'pos': word.pos,
            'neg': word.neg,
            'fml': word.fml,
            'source_text': word.source_text,
            'source_reading': word.source_reading,
        }]
    elif hasattr(word, 'conjugations') and word.conjugations:
        conjugations = word.conjugations
    
    # If no conjugation info yet, check if this seq is derived from another entry
    # (e.g., で particle is te-form of だ copula)
    if conjugations is None and word.seq:
        conj_info = get_conjugation_info_for_seq(word.seq)
        if conj_info:
            conjugations = [conj_info]
    
    return WordInfo(
        type=word.word_type(),
        text=segment.text,
        kana=word.get_kana(),
        seq=word.seq,
        true_text=word.get_text() if hasattr(word, 'true_text') else None,
        conjugations=conjugations,
        score=segment.score,
        start=segment.start,
        end=segment.end,
    )


def word_info_from_segment_list(segment_list: SegmentList) -> WordInfo:
    """Create WordInfo from a SegmentList."""
    segments = segment_list.segments
    
    if not segments:
        return WordInfo(
            type='gap',
            text='',
            kana='',
            start=segment_list.start,
            end=segment_list.end,
        )
    
    wi_list = [word_info_from_segment(s) for s in segments]
    wi1 = wi_list[0]
    max_score = wi1.score
    
    # Filter low-scoring alternatives
    wi_list = [
        wi for wi in wi_list 
        if wi.score >= max_score * SEGMENT_SCORE_CUTOFF
    ]
    
    matches = segment_list.matches
    
    if len(wi_list) == 1:
        wi1.skipped = matches - 1
        return wi1
    
    # Multiple alternatives
    kana_list = [wi.kana for wi in wi_list if wi.kana]
    seq_list = [wi.seq for wi in wi_list if wi.seq]
    
    return WordInfo(
        type=wi1.type,
        text=wi1.text,
        kana=list(dict.fromkeys(kana_list)),  # Remove duplicates, preserve order
        seq=seq_list,
        components=wi_list,
        alternative=True,
        score=max_score,
        start=segment_list.start,
        end=segment_list.end,
        skipped=matches - len(wi_list),
    )


def fill_segment_path(text: str, path: List) -> List[WordInfo]:
    """
    Fill gaps in a segment path with gap WordInfo objects.
    
    Args:
        text: Original text.
        path: List of segments.
        
    Returns:
        Complete list of WordInfo objects.
    """
    result = []
    idx = 0
    
    for item in path:
        if isinstance(item, Segment):
            # Add gap if needed
            if item.start > idx:
                gap_text = text[idx:item.start]
                result.append(WordInfo(
                    type='gap',
                    text=gap_text,
                    kana=gap_text,
                    start=idx,
                    end=item.start,
                ))
            
            result.append(word_info_from_segment(item))
            idx = item.end
        elif isinstance(item, SegmentList):
            # Add gap if needed
            if item.start > idx:
                gap_text = text[idx:item.start]
                result.append(WordInfo(
                    type='gap',
                    text=gap_text,
                    kana=gap_text,
                    start=idx,
                    end=item.start,
                ))
            
            result.append(word_info_from_segment_list(item))
            idx = item.end
    
    # Add final gap if needed
    if idx < len(text):
        gap_text = text[idx:]
        result.append(WordInfo(
            type='gap',
            text=gap_text,
            kana=gap_text,
            start=idx,
            end=len(text),
        ))
    
    return result


# ============================================================================
# Main Public Functions
# ============================================================================

def dict_segment(text: str, limit: int = 5) -> List[Tuple[List[WordInfo], int]]:
    """
    Segment Japanese text into words with dictionary lookup.
    
    Args:
        text: Japanese text to segment.
        limit: Maximum number of alternative segmentations.
        
    Returns:
        List of (word_info_list, score) tuples.
    """
    segment_lists = join_substring_words(text)
    paths = find_best_path(segment_lists, len(text), limit=limit)
    
    return [
        (fill_segment_path(text, path), score)
        for path, score in paths
    ]


def simple_segment(text: str, limit: int = 5) -> List[WordInfo]:
    """
    Get the best segmentation of Japanese text.
    
    Args:
        text: Japanese text to segment.
        limit: Passed to dict_segment.
        
    Returns:
        List of WordInfo objects for the best segmentation.
    """
    results = dict_segment(text, limit=limit)
    if results:
        return results[0][0]
    return []


# ============================================================================
# Gloss and Sense Functions
# ============================================================================

def get_senses(seq: int) -> List[Dict]:
    """
    Get senses (meanings) for a dictionary entry.
    
    Args:
        seq: Entry sequence number.
        
    Returns:
        List of sense dictionaries with pos and gloss.
    """
    rows = query(
        """
        SELECT s.ord, GROUP_CONCAT(g.text, '; ') as gloss
        FROM sense s
        LEFT JOIN gloss g ON g.sense_id = s.id
        WHERE s.seq = ?
        GROUP BY s.id
        ORDER BY s.ord
        """,
        (seq,)
    )
    
    senses = []
    for row in rows:
        # Get POS tags
        pos_rows = query(
            """
            SELECT text FROM sense_prop
            WHERE seq = ? AND tag = 'pos'
            ORDER BY ord
            """,
            (seq,)
        )
        pos = [r['text'] for r in pos_rows]
        
        senses.append({
            'ord': row['ord'],
            'gloss': row['gloss'] or '',
            'pos': pos,
        })
    
    return senses


def get_senses_str(seq: int) -> str:
    """
    Get a formatted string of senses for an entry.
    
    Args:
        seq: Entry sequence number.
        
    Returns:
        Formatted string.
    """
    senses = get_senses(seq)
    
    lines = []
    for i, sense in enumerate(senses, 1):
        pos_str = f"[{','.join(sense['pos'])}]" if sense['pos'] else "[]"
        lines.append(f"{i}. {pos_str} {sense['gloss']}")
    
    return '\n'.join(lines)


def reading_str(obj) -> str:
    """
    Get a reading string for a word.
    
    Args:
        obj: SimpleText, WordInfo, or sequence number.
        
    Returns:
        Formatted reading string like "漢字 【かんじ】".
    """
    if isinstance(obj, int):
        # Sequence number
        kanji = query_single(
            "SELECT text FROM kanji_text WHERE seq = ? AND ord = 0",
            (obj,)
        )
        kana = query_single(
            "SELECT text FROM kana_text WHERE seq = ? AND ord = 0",
            (obj,)
        )
        if kanji:
            return f"{kanji} 【{kana}】"
        return kana or str(obj)
    
    elif isinstance(obj, WordInfo):
        kana = obj.kana
        if isinstance(kana, list):
            kana = '/'.join(kana)
        
        if obj.type == 'kanji' or (obj.counter and obj.seq):
            return f"{obj.text} 【{kana}】"
        return obj.text
    
    elif isinstance(obj, SimpleText):
        kanji = obj.get_kanji()
        kana = obj.get_kana()
        if kanji:
            return f"{kanji} 【{kana}】"
        return obj.get_text()
    
    return str(obj)
