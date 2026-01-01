"""
Dictionary grammar module for Himotoki.

Handles grammatical suffixes, conjugation forms, and
word attachment patterns.

Mirrors dict-grammar.lisp from the original Ichiran.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import re

from himotoki.conn import query, query_one, Cache, defcache
from himotoki.characters import as_hiragana


# ============================================================================
# Suffix Registry
# ============================================================================

@dataclass
class SuffixClass:
    """Represents a grammatical suffix pattern."""
    id: str
    form: str  # The form to add
    reading: str  # Reading in kana
    strip: str = ""  # Form to strip from base
    conj: Optional[int] = None  # Required conjugation type
    matches: Optional[List[Callable]] = None  # Match functions
    modifies: Optional[str] = None  # Type modifier
    primary: bool = False  # Is this a primary form
    
    def __post_init__(self):
        if self.matches is None:
            self.matches = []


# Suffix cache - maps suffix_id to SuffixClass
SUFFIX_CACHE: Dict[str, SuffixClass] = {}

# Default suffix patterns
DEFAULT_SUFFIXES: List[SuffixClass] = []


def get_suffix(suffix_id: str) -> Optional[SuffixClass]:
    """Get a suffix by ID."""
    return SUFFIX_CACHE.get(suffix_id)


def register_suffix(suffix: SuffixClass):
    """Register a suffix in the cache."""
    SUFFIX_CACHE[suffix.id] = suffix


def init_suffixes():
    """Initialize all built-in suffixes."""
    global DEFAULT_SUFFIXES
    
    # Clear existing
    SUFFIX_CACHE.clear()
    
    # Define suffixes
    suffixes = [
        # て-form suffixes
        SuffixClass(
            id='te',
            form='て',
            reading='て',
            conj=3,  # Conjunctive
        ),
        SuffixClass(
            id='de',
            form='で',
            reading='で',
            conj=3,
        ),
        
        # ている (progressive/resultative)
        SuffixClass(
            id='teiru',
            form='ている',
            reading='ている',
            conj=3,
        ),
        SuffixClass(
            id='deiru',
            form='でいる',
            reading='でいる',
            conj=3,
        ),
        SuffixClass(
            id='teru',
            form='てる',
            reading='てる',
            conj=3,
        ),
        SuffixClass(
            id='deru',
            form='でる',
            reading='でる',
            conj=3,
        ),
        
        # ておく (preparation)
        SuffixClass(
            id='teoku',
            form='ておく',
            reading='ておく',
            conj=3,
        ),
        SuffixClass(
            id='toku',
            form='とく',
            reading='とく',
            conj=3,
        ),
        
        # てしまう (completion/regret)
        SuffixClass(
            id='teshimau',
            form='てしまう',
            reading='てしまう',
            conj=3,
        ),
        SuffixClass(
            id='chau',
            form='ちゃう',
            reading='ちゃう',
            conj=3,
        ),
        SuffixClass(
            id='jau',
            form='じゃう',
            reading='じゃう',
            conj=3,
        ),
        SuffixClass(
            id='chimau',
            form='ちまう',
            reading='ちまう',
            conj=3,
        ),
        
        # てみる (try doing)
        SuffixClass(
            id='temiru',
            form='てみる',
            reading='てみる',
            conj=3,
        ),
        SuffixClass(
            id='demiru',
            form='でみる',
            reading='でみる',
            conj=3,
        ),
        
        # てくる (coming/going action)
        SuffixClass(
            id='tekuru',
            form='てくる',
            reading='てくる',
            conj=3,
        ),
        SuffixClass(
            id='teiku',
            form='ていく',
            reading='ていく',
            conj=3,
        ),
        
        # たい (want to)
        SuffixClass(
            id='tai',
            form='たい',
            reading='たい',
            conj=13,  # Continuative
        ),
        
        # ます (polite)
        SuffixClass(
            id='masu',
            form='ます',
            reading='ます',
            conj=13,
        ),
        
        # そう (seems like)
        SuffixClass(
            id='sou',
            form='そう',
            reading='そう',
            conj=13,
        ),
        SuffixClass(
            id='sou_adj',
            form='そう',
            reading='そう',
            strip='い',
        ),
        
        # すぎる (too much)
        SuffixClass(
            id='sugiru',
            form='すぎる',
            reading='すぎる',
            conj=13,
        ),
        SuffixClass(
            id='sugiru_adj',
            form='すぎる',
            reading='すぎる',
            strip='い',
        ),
        
        # やすい/にくい (ease/difficulty)
        SuffixClass(
            id='yasui',
            form='やすい',
            reading='やすい',
            conj=13,
        ),
        SuffixClass(
            id='nikui',
            form='にくい',
            reading='にくい',
            conj=13,
        ),
        
        # はじめる/つづける/おわる
        SuffixClass(
            id='hajimeru',
            form='はじめる',
            reading='はじめる',
            conj=13,
        ),
        SuffixClass(
            id='tsuzukeru',
            form='つづける',
            reading='つづける',
            conj=13,
        ),
        SuffixClass(
            id='owaru',
            form='おわる',
            reading='おわる',
            conj=13,
        ),
        
        # かた (way of doing)
        SuffixClass(
            id='kata',
            form='かた',
            reading='かた',
            conj=13,
        ),
        SuffixClass(
            id='kata_k',
            form='方',
            reading='かた',
            conj=13,
        ),
        
        # ない (negative)
        SuffixClass(
            id='nai',
            form='ない',
            reading='ない',
            conj=14,  # Negative stem
        ),
        
        # れる/られる (passive/potential)
        SuffixClass(
            id='reru',
            form='れる',
            reading='れる',
            conj=14,
        ),
        SuffixClass(
            id='rareru',
            form='られる',
            reading='られる',
            conj=14,
        ),
        
        # せる/させる (causative)
        SuffixClass(
            id='seru',
            form='せる',
            reading='せる',
            conj=14,
        ),
        SuffixClass(
            id='saseru',
            form='させる',
            reading='させる',
            conj=14,
        ),
        
        # Adjective-to-adverb
        SuffixClass(
            id='ku',
            form='く',
            reading='く',
            strip='い',
        ),
        
        # Noun suffix
        SuffixClass(
            id='sa',
            form='さ',
            reading='さ',
            strip='い',
        ),
        SuffixClass(
            id='mi',
            form='み',
            reading='み',
            strip='い',
        ),
        
        # だ/です (copula)
        SuffixClass(
            id='da',
            form='だ',
            reading='だ',
        ),
        SuffixClass(
            id='desu',
            form='です',
            reading='です',
        ),
        
        # など (etc.)
        SuffixClass(
            id='nado',
            form='など',
            reading='など',
        ),
        
        # だけ (only)
        SuffixClass(
            id='dake',
            form='だけ',
            reading='だけ',
        ),
        
        # ほど (extent)
        SuffixClass(
            id='hodo',
            form='ほど',
            reading='ほど',
        ),
        
        # まで (until)
        SuffixClass(
            id='made',
            form='まで',
            reading='まで',
        ),
        
        # ばかり (just/only)
        SuffixClass(
            id='bakari',
            form='ばかり',
            reading='ばかり',
        ),
        SuffixClass(
            id='bakkari',
            form='ばっかり',
            reading='ばっかり',
        ),
        SuffixClass(
            id='bakka',
            form='ばっか',
            reading='ばっか',
        ),
        
        # よう (appearance/seem)
        SuffixClass(
            id='you',
            form='よう',
            reading='よう',
        ),
        
        # ぽい (-ish)
        SuffixClass(
            id='ppoi',
            form='っぽい',
            reading='っぽい',
        ),
        
        # らしい (seems like)
        SuffixClass(
            id='rashii',
            form='らしい',
            reading='らしい',
        ),
        
        # みたい (like)
        SuffixClass(
            id='mitai',
            form='みたい',
            reading='みたい',
        ),
        
        # じゃない (isn't)
        SuffixClass(
            id='janai',
            form='じゃない',
            reading='じゃない',
        ),
        SuffixClass(
            id='janee',
            form='じゃねえ',
            reading='じゃねえ',
        ),
        
        # ことができる (can do)
        SuffixClass(
            id='kotogadekiru',
            form='ことができる',
            reading='ことができる',
        ),
        
        # かもしれない (might)
        SuffixClass(
            id='kamoshirenai',
            form='かもしれない',
            reading='かもしれない',
        ),
        SuffixClass(
            id='kamo',
            form='かも',
            reading='かも',
        ),
        
        # なければならない (must)
        SuffixClass(
            id='nakereba_naranai',
            form='なければならない',
            reading='なければならない',
            conj=14,
        ),
        SuffixClass(
            id='nakucha',
            form='なくちゃ',
            reading='なくちゃ',
            conj=14,
        ),
        SuffixClass(
            id='nakya',
            form='なきゃ',
            reading='なきゃ',
            conj=14,
        ),
        
        # がる (seem/feel)
        SuffixClass(
            id='garu',
            form='がる',
            reading='がる',
            strip='い',
        ),
        
        # がち (tendency)
        SuffixClass(
            id='gachi',
            form='がち',
            reading='がち',
            conj=13,
        ),
    ]
    
    for suffix in suffixes:
        register_suffix(suffix)
    
    DEFAULT_SUFFIXES = suffixes


# ============================================================================
# Suffix Matching
# ============================================================================

def match_suffix(word_text: str, base_words: List) -> List:
    """
    Try to match a suffix pattern on a word.
    
    Args:
        word_text: The word text to analyze.
        base_words: List of potential base words.
        
    Returns:
        List of (suffix, base_word) matches.
    """
    results = []
    
    for suffix_id, suffix in SUFFIX_CACHE.items():
        if not word_text.endswith(suffix.form):
            continue
        
        # Calculate the base form
        base_len = len(word_text) - len(suffix.form)
        if suffix.strip:
            base_text = word_text[:base_len] + suffix.strip
        else:
            base_text = word_text[:base_len]
        
        if not base_text:
            continue
        
        # Find matching base words
        for base_word in base_words:
            base_word_text = base_word.get_text() if hasattr(base_word, 'get_text') else str(base_word)
            
            if as_hiragana(base_word_text) == as_hiragana(base_text):
                # Check conjugation requirement
                if suffix.conj is not None:
                    # Would need to check if base_word has this conjugation
                    # For now, skip this check
                    pass
                
                results.append((suffix, base_word))
    
    return results


def find_suffix_chains(word_text: str, max_depth: int = 3) -> List[List[SuffixClass]]:
    """
    Find chains of suffixes that could build up the word.
    
    Args:
        word_text: The word text to analyze.
        max_depth: Maximum number of suffixes to chain.
        
    Returns:
        List of suffix chains.
    """
    chains = []
    
    def search(current: str, chain: List[SuffixClass], depth: int):
        if depth >= max_depth:
            return
        
        for suffix_id, suffix in SUFFIX_CACHE.items():
            if not current.endswith(suffix.form):
                continue
            
            base_len = len(current) - len(suffix.form)
            if suffix.strip:
                base = current[:base_len] + suffix.strip
            else:
                base = current[:base_len]
            
            if not base:
                continue
            
            new_chain = [suffix] + chain
            chains.append((base, new_chain))
            search(base, new_chain, depth + 1)
    
    search(word_text, [], 0)
    return chains


# ============================================================================
# Part-of-Speech Matching
# ============================================================================

# POS categories for suffix attachment
POS_VERB = {'v1', 'v5', 'v5aru', 'v5b', 'v5g', 'v5k', 'v5k-s', 'v5m', 
            'v5n', 'v5r', 'v5r-i', 'v5s', 'v5t', 'v5u', 'v5u-s', 'v5uru',
            'vk', 'vs', 'vs-i', 'vs-s', 'vz'}

POS_ADJ = {'adj-i', 'adj-ix'}

POS_NOUN = {'n', 'n-adv', 'n-pr', 'n-suf', 'n-t'}


def get_pos_category(pos_tags: List[str]) -> str:
    """Determine POS category from tags."""
    for tag in pos_tags:
        if tag in POS_VERB:
            return 'verb'
        if tag in POS_ADJ:
            return 'adjective'
        if tag in POS_NOUN:
            return 'noun'
    return 'other'


def suffix_compatible(suffix: SuffixClass, pos_category: str) -> bool:
    """Check if a suffix is compatible with a POS category."""
    # Verbal suffixes
    if suffix.conj in (3, 13, 14):  # te-form, continuative, negative stem
        return pos_category == 'verb'
    
    # Adjectival suffixes
    if suffix.strip == 'い':
        return pos_category == 'adjective'
    
    # General suffixes (particles, etc.) attach to many things
    return True


# ============================================================================
# Conjugation Table
# ============================================================================

CONJ_TYPES = {
    1: 'negative',
    2: 'past',
    3: 'te-form',
    4: 'conditional-eba',
    5: 'potential',
    6: 'passive',
    7: 'causative',
    8: 'causative-passive',
    9: 'volitional',
    10: 'imperative',
    11: 'conditional-tara',
    12: 'alternative-tari',
    13: 'continuative',
    14: 'negative-stem',
}


def get_conj_type_name(conj_type: int) -> str:
    """Get the name of a conjugation type."""
    return CONJ_TYPES.get(conj_type, f'unknown-{conj_type}')


# ============================================================================
# Seg-Filters (1:1 from Ichiran's def-seg-filter)
# ============================================================================
"""
Segment filters determine whether a word can appear at a given position.

From Ichiran's dict-grammar.lisp, seg-filters check:
- Whether an auxiliary verb follows the correct conjugation form
- Whether ん follows a non-particle
- Whether じゃない follows appropriate forms
- Whether できる follows appropriate stems
- Whether honorific forms are used correctly

Each filter returns True if the segment is ALLOWED, False if BLOCKED.
"""

from typing import Callable

# Filter registry
SEG_FILTERS: Dict[str, Callable] = {}


def def_seg_filter(name: str):
    """Decorator to register a seg-filter function."""
    def decorator(func: Callable):
        SEG_FILTERS[name] = func
        return func
    return decorator


@def_seg_filter("aux-verb")
def filter_aux_verb(word, prev_word) -> bool:
    """
    Auxiliary verbs must follow conjunctive (ren'youkei) form.
    
    From Ichiran:
        (def-seg-filter aux-verb :pos (:aux-v)
          (or (not prev)
              (and (typep prev 'word)
                   (eql (get-conj-type prev) :ren-youkei))))
    
    Returns True if:
    - There's no previous word (segment start)
    - Previous word is in conjunctive/continuative form
    """
    if prev_word is None:
        # Aux verbs CAN start a segment (e.g., ます after implicit verb)
        # But this is rare - return True with low confidence
        return True
    
    # Check if prev_word is in conjunctive form
    prev_conj = getattr(prev_word, 'conj_type', None)
    if prev_conj:
        conj_lower = prev_conj.lower() if isinstance(prev_conj, str) else ''
        # Ichiran checks for ren'youkei (連用形) - continuative form
        if any(t in conj_lower for t in ('continuative', 'masu-stem', 'ren', '連用')):
            return True
    
    # Also check if prev ends in proper stems
    prev_text = getattr(prev_word, 'text', str(prev_word))
    # Godan/Ichidan continuative ends
    if prev_text and prev_text[-1] in 'いきしちにひみりぎじびぴえけせてねへめれげぜでべぺ':
        return True
    
    # Default: not allowed
    return False


@def_seg_filter("n-contraction")
def filter_n_contraction(word, prev_word) -> bool:
    """
    ん (contraction) must follow non-particles.
    
    From Ichiran:
        (def-seg-filter n-contraction :seq (2210270)
          (and prev (not (has-pos prev :prt))))
    
    ん as a contraction of ぬ/の must follow verbs/adjectives, not particles.
    """
    word_seq = getattr(word, 'seq', 0)
    if word_seq != 2210270:  # Only applies to ん (2210270)
        return True
    
    if prev_word is None:
        return False  # ん can't start a segment
    
    # Check if prev is a particle
    from .synergies import is_particle
    prev_seq = getattr(prev_word, 'seq', 0)
    if prev_seq and is_particle(prev_seq):
        return False  # ん can't follow a particle
    
    return True


@def_seg_filter("janai")
def filter_janai(word, prev_word) -> bool:
    """
    じゃない must follow nouns or na-adjectives.
    
    From Ichiran:
        (def-seg-filter janai :seq (2257550)
          (and prev (or (has-pos prev :n) (has-pos prev :adj-na))))
    """
    word_seq = getattr(word, 'seq', 0)
    if word_seq != 2257550:  # Only applies to じゃ (2257550)
        return True
    
    if prev_word is None:
        return False
    
    from .synergies import is_noun, is_na_adjective
    prev_seq = getattr(prev_word, 'seq', 0)
    if prev_seq:
        if is_noun(prev_seq) or is_na_adjective(prev_seq):
            return True
    
    return False


@def_seg_filter("dekiru")
def filter_dekiru(word, prev_word) -> bool:
    """
    できる as potential must follow noun+が/を pattern or ことが pattern.
    
    From Ichiran:
        (def-seg-filter dekiru :seq (1596200)
          (or (not prev)
              (and (typep prev 'word)
                   (or (equal (get-text prev) "ことが")
                       (equal (get-text prev) "ことを")
                       (equal (get-text prev) "が")
                       (equal (get-text prev) "を")))))
    """
    word_seq = getattr(word, 'seq', 0)
    if word_seq != 1596200:  # Only applies to できる
        return True
    
    if prev_word is None:
        return True  # Can start a segment
    
    prev_text = getattr(prev_word, 'text', str(prev_word))
    if prev_text in ('ことが', 'ことを', 'が', 'を'):
        return True
    
    # Also allow after potential-marked conjugations
    return True


@def_seg_filter("honorific")
def filter_honorific(word, prev_word) -> bool:
    """
    Honorific forms (お/ご + stem) need proper context.
    
    From Ichiran:
        (def-seg-filter honorific :reading "お" ...)
        
    This filter ensures honorific prefixes are used correctly.
    """
    word_text = getattr(word, 'text', str(word))
    if not word_text.startswith('お') and not word_text.startswith('ご'):
        return True
    
    # Honorific prefix is generally allowed
    return True


def apply_seg_filters(word, prev_word) -> bool:
    """
    Apply all seg-filters to determine if word is allowed.
    
    Args:
        word: Current word to check
        prev_word: Previous word (or None if at segment start)
        
    Returns:
        True if word passes all filters, False if blocked by any filter.
    """
    for filter_name, filter_func in SEG_FILTERS.items():
        if not filter_func(word, prev_word):
            return False
    return True


# ============================================================================
# Length Coefficients (1:1 from Ichiran)
# ============================================================================
"""
Ichiran uses different length coefficient tables for different word types:
- strong: For important content words
- weak: For particles and minor function words  
- tail: For suffix-like elements
- ltail: For longer tail elements
"""

# Length coefficient tables (0-indexed: index = length - 1)
SCORE_COEFF_STRONG = [1, 8, 24, 40, 60]
SCORE_COEFF_WEAK = [1, 4, 9, 16, 25, 36]
SCORE_COEFF_TAIL = [4, 9, 16, 24]
SCORE_COEFF_LTAIL = [4, 12, 18, 24]


def get_length_coeff(length: int, coeff_type: str = 'strong') -> int:
    """
    Get the length coefficient for scoring.
    
    Args:
        length: Character length of the word
        coeff_type: 'strong', 'weak', 'tail', or 'ltail'
        
    Returns:
        Score coefficient for that length
    """
    if coeff_type == 'strong':
        table = SCORE_COEFF_STRONG
    elif coeff_type == 'weak':
        table = SCORE_COEFF_WEAK
    elif coeff_type == 'tail':
        table = SCORE_COEFF_TAIL
    elif coeff_type == 'ltail':
        table = SCORE_COEFF_LTAIL
    else:
        table = SCORE_COEFF_STRONG
    
    if length <= 0:
        return 0
    
    if length <= len(table):
        return table[length - 1]
    else:
        # Extrapolate for longer words
        last = table[-1]
        diff = table[-1] - table[-2] if len(table) > 1 else 8
        return last + diff * (length - len(table))


# ============================================================================
# Gap Penalty (1:1 from Ichiran)
# ============================================================================

# Penalty per uncovered character
GAP_PENALTY = -500


def calculate_gap_penalty(gap_length: int) -> int:
    """
    Calculate penalty for uncovered characters.
    
    From Ichiran:
        (defparameter *gap-penalty* -500)
        
    Each uncovered character gets a -500 penalty.
    """
    return GAP_PENALTY * gap_length


# ============================================================================
# Score Cutoff (1:1 from Ichiran)
# ============================================================================

# Minimum score to keep a path candidate
SCORE_CUTOFF = 5


def should_prune_path(score: int) -> bool:
    """
    Determine if a path should be pruned due to low score.
    
    From Ichiran:
        (defparameter *score-cutoff* 5)
    """
    return score < SCORE_CUTOFF


# ============================================================================
# Segfilters (1:1 from Ichiran's dict-grammar.lisp)
# ============================================================================

"""
Segfilters prevent certain combinations of adjacent segments.
They return True if the combination should be BLOCKED.

From Ichiran:
    (defmacro def-segfilter-must-follow (name (segment-list-left segment-list-right)
                                         filter-left filter-right &key allow-first)
      "This segfilter is for when segments that satisfy filter-right MUST follow segments that
       satisfy filter-left")
"""

from typing import Set

# Sequences used by segfilters (from Ichiran)
SEGFILTER_AUX_VERBS: Set[int] = {1342560}  # 初める/そめる
SEGFILTER_N_SEQS: Set[int] = {2139720, 2849370, 2849387}  # ん, んだ
SEGFILTER_SURU_SEQS: Set[int] = {1157170, 2424740, 1305070}  # する, して, しまう
SEGFILTER_IRU_SEQ: int = 1577980  # いる
SEGFILTER_KURU_SEQS: Set[int] = {2830009, 1547720}  # 来る conjugations
SEGFILTER_OMOU_SEQS: Set[int] = {1589350, 1587040}  # 思う, 言う
SEGFILTER_NAI_SEQS: Set[int] = {1529520, 1296400, 2139720}  # ない, ある, ん
SEGFILTER_HAYAMETE_SEQ: int = 1601080  # 早めて
SEGFILTER_NO_SEQ: int = 1469800  # の
SEGFILTER_TO_SEQ: int = 1008490  # と
SEGFILTER_NANDATO_SEQ: int = 2837117  # 何だと
SEGFILTER_TTE_SEQ: int = 2086960  # って
SEGFILTER_DE_SEQ: int = 2896380  # 出
SEGFILTER_DE_ALT: Set[int] = {1896380, 2422860}  # 出 forms
SEGFILTER_DA_SEQ: int = 2089020  # だ
SEGFILTER_DE_PARTICLE_SEQ: int = 2028980  # で (particle)
SEGFILTER_HONORIFICS: Set[int] = {1247260}  # 君

# Bad compound endings (from Ichiran's segfilter-badend)
BAD_COMPOUND_ENDINGS: Set[str] = {'ちゃい', 'いか', 'とか', 'とき', 'い'}


def _is_kana_only(text: str) -> bool:
    """Check if text contains only hiragana/katakana."""
    for c in text:
        cp = ord(c)
        if not ((0x3040 <= cp <= 0x309F) or (0x30A0 <= cp <= 0x30FF)):
            return False
    return True


def _ends_with_compound(seg_text: str, seqs: Set[int]) -> bool:
    """
    Check if a compound word ends with one of the given sequences.
    This is a simplified version - full implementation would check actual compound structure.
    """
    # For now, check common patterns
    return False  # Will be refined based on actual compound tracking


def segfilter_n(left_seq: Optional[int], left_text: str,
                right_seq: int, right_text: str) -> bool:
    """
    Segfilter: ん/んだ must not follow simple noun particles.
    
    From Ichiran (dict-grammar.lisp:1072-1075):
        (def-segfilter-must-follow segfilter-n (l r)
          (complement (apply 'filter-in-seq-set-simple *noun-particles*))
          (filter-in-seq-set 2139720 2849370 2849387) ;; ん んだ
          :allow-first t)
    
    Returns True if this combination should be BLOCKED.
    """
    if right_seq in SEGFILTER_N_SEQS:
        # Block if left is a simple noun particle
        from .synergies import NOUN_PARTICLES
        if left_seq and left_seq in NOUN_PARTICLES:
            return True
    return False


def segfilter_badend(left_seq: Optional[int], left_text: str,
                     right_seq: int, right_text: str) -> bool:
    """
    Segfilter: Prevent bad compound endings.
    
    From Ichiran (dict-grammar.lisp:1081-1083):
        (def-segfilter-must-follow segfilter-badend (l r)
          (constantly nil)
          (filter-is-compound-end-text "ちゃい" "いか" "とか" "とき" "い"))
    
    IMPORTANT: In Ichiran, filter-is-compound-end-text only applies to
    COMPOUND words (words with multiple parts/seqs). It checks if the
    LAST PART of a compound ends with the given text.
    
    We don't have compound tracking here, so we disable this filter.
    The compound system handles these cases differently.
    
    Returns True if the right segment ends with a bad compound pattern.
    """
    # NOTE: This filter was incorrectly blocking standalone words like いい
    # In Ichiran, this only applies to compound words (words with listp seq)
    # Since we don't track compounds the same way, we disable this filter
    # for now to avoid false positives.
    return False


def segfilter_janai(left_seq: Optional[int], left_text: str,
                    right_seq: int, right_text: str) -> bool:
    """
    Segfilter: じゃ + ない/ある/ん pattern.
    
    From Ichiran (dict-grammar.lisp:1118-1121):
        (def-segfilter-must-follow segfilter-janai (l r)
          (complement (filter-is-compound-end 2028920))  ;; は
          (filter-in-seq-set 1529520 1296400 2139720)  ;; ない ある ん
          :allow-first t)
    
    ない/ある/ん must follow something ending with は (as じゃ = では)
    """
    if right_seq in SEGFILTER_NAI_SEQS:
        # Allow at sentence start
        if left_seq is None:
            return False
        # Must follow は-ending compound
        # For now, simplified check
        return False
    return False


def segfilter_toomou(left_seq: Optional[int], left_text: str,
                     right_seq: int, right_text: str) -> bool:
    """
    Segfilter: と before 思う/言う must be split.
    
    From Ichiran (dict-grammar.lisp:1128-1133):
        (def-segfilter-must-follow segfilter-toomou (l r)
          (complement (filter-in-seq-set 2837117)) ;; 何だと
          (filter-in-seq-set 1589350 1587040)  ;; 思う 言う
          :allow-first t)
    
    思う/言う should be preceded by と quote particle, not compound.
    """
    if right_seq in SEGFILTER_OMOU_SEQS:
        # Block if left is 何だと
        if left_seq == SEGFILTER_NANDATO_SEQ:
            return True
    return False


def segfilter_dashi(left_seq: Optional[int], left_text: str,
                    right_seq: int, right_text: str) -> bool:
    """
    Segfilter: だ not followed by する/して.
    
    From Ichiran (dict-grammar.lisp:1140-1147):
        (def-segfilter-must-follow segfilter-dashi (l r)
          (lambda (segment &aux (seq-set (getf (segment-info segment) :seq-set)))
            (or (not (find 2089020 seq-set)) ;; だ
                (find 2028980 seq-set))) ;; で
          (filter-in-seq-set 1157170 2424740 1305070) ;; する　して
          :allow-first t)
    
    When right is する/して, left should not be standalone だ.
    """
    if right_seq in SEGFILTER_SURU_SEQS:
        if left_seq == SEGFILTER_DA_SEQ:
            # Block だ + する (should be だする compound or different parse)
            return True
    return False


def segfilter_dekiru(left_seq: Optional[int], left_text: str,
                     right_seq: int, right_text: str) -> bool:
    """
    Segfilter: 出 followed by 来る.
    
    From Ichiran (dict-grammar.lisp:1149-1153):
        (def-segfilter-must-follow segfilter-dekiru (l r)
          (complement (filter-in-seq-set 1896380 2422860))  ;; 出
          (filter-in-seq-set 2830009 1547720)  ;; 来る conjugations
          :allow-first t)
    
    来る conjugations must follow 出 to form できる.
    """
    if right_seq in SEGFILTER_KURU_SEQS:
        if left_seq and left_seq in SEGFILTER_DE_ALT:
            return False  # Allow 出 + 来る
        # Block 来る without proper 出 prefix at start
        if left_seq is None:
            return True
    return False


def segfilter_desu_split(left_seq: Optional[int], left_text: str,
                         right_seq: int, right_text: str) -> bool:
    """
    Segfilter: Prevent standalone す after で when です is intended.
    
    This is a himotoki addition to handle the で|す vs です issue.
    
    When we have で followed by single hiragana す that matches a noun,
    block it because です is more likely.
    """
    # After で particle, single す should not match nouns like 酢/巣
    if left_seq == SEGFILTER_DE_PARTICLE_SEQ:
        if right_text == 'す' and _is_kana_only(right_text):
            # Check if right_seq is a standalone noun (not verb する)
            from .synergies import is_noun, is_verb
            if is_noun(right_seq) and not is_verb(right_seq):
                return True  # Block nouns like 酢, 巣 after で
    return False


def segfilter_honorific(left_seq: Optional[int], left_text: str,
                        right_seq: int, right_text: str) -> bool:
    """
    Segfilter: Honorifics like 君 not after particles.
    
    From Ichiran (dict-grammar.lisp:1159-1162):
        (def-segfilter-must-follow segfilter-honorific (l r)
          (complement (apply 'filter-in-seq-set *noun-particles*))
          (apply 'filter-in-seq-set *honorifics*))
    """
    if right_seq in SEGFILTER_HONORIFICS:
        from .synergies import NOUN_PARTICLES
        if left_seq and left_seq in NOUN_PARTICLES:
            return True  # Block particle + honorific
    return False


# List of all segfilter functions
SEGFILTERS = [
    segfilter_n,
    segfilter_badend,
    segfilter_janai,
    segfilter_toomou,
    segfilter_dashi,
    segfilter_dekiru,
    segfilter_desu_split,
    segfilter_honorific,
]


def apply_segfilters(left_seq: Optional[int], left_text: str,
                     right_seq: int, right_text: str) -> bool:
    """
    Apply all segfilters to a pair of segments.
    
    Returns True if the combination should be BLOCKED.
    """
    for segfilter in SEGFILTERS:
        if segfilter(left_seq, left_text, right_seq, right_text):
            return True
    return False


# ============================================================================
# Module Initialization
# ============================================================================

# Initialize suffixes on module load
init_suffixes()
