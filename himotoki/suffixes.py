"""
Suffix handling module for himotoki.
Ports ichiran's dict-grammar.lisp suffix functionality.

Suffixes are grammatical endings that attach to word stems to form compound words.
Examples include:
- たい (tai): want to...
- ている (teiru): indicates continuing action
- そう (sou): looks like...
- たくない (takunai): don't want to...

The suffix cache maps suffix strings to (keyword, kana_form) pairs.
This enables efficient lookup during segmentation.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Union, Any, Callable, Set
from functools import lru_cache
import threading

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from himotoki.db.models import (
    Entry, KanjiText, KanaText, Sense, SenseProp,
    Conjugation, ConjProp, ConjSourceReading,
)
from himotoki.characters import is_kana, as_hiragana
from himotoki.constants import (
    CONJ_ADVERBIAL, CONJ_ADJECTIVE_STEM,
    # Particles
    SEQ_O_PREFIX, SEQ_DE, SEQ_KA, SEQ_NI, SEQ_WO, SEQ_NO, SEQ_TTE, SEQ_KARA,
    SEQ_WA, SEQ_MO,
    # Common verbs
    SEQ_IRU, SEQ_KURU, SEQ_SURU, SEQ_TOMU, SEQ_ORU, SEQ_ARU, SEQ_OKU, SEQ_IKU,
    SEQ_SHIMAU, SEQ_MORAU, SEQ_ITADAKU, SEQ_KURERU,
    # Honorific/humble verb forms
    SEQ_ITASU, SEQ_SARERU, SEQ_SASERU, SEQ_TOKU,
    # Suffix-related
    SEQ_CHAU, SEQ_CHIMAU, SEQ_TAI, SEQ_NIKUI, SEQ_II, SEQ_KUDASAI,
    SEQ_SOU, SEQ_SOU_NI_NAI, SEQ_MOII,
    # Blocked seqs
    BLOCKED_NAI_SEQS, BLOCKED_NAI_X_SEQS,
    # Suffix descriptions (to merge with local ones)
    SUFFIX_DESCRIPTION as SUFFIX_DESCRIPTION_SEQS,
)


# ============================================================================
# Suffix Descriptions
# ============================================================================

SUFFIX_DESCRIPTION: Dict[Union[str, int], str] = {
    # Verbal suffixes
    'chau': 'indicates completion (to finish ...)',
    'ha': 'topic marker particle',
    'tai': 'want to... / would like to...',
    'iru': 'indicates continuing action (to be ...ing)',
    'oru': 'indicates continuing action (to be ...ing) (humble)',
    'aru': 'indicates completion / finished action',
    'kuru': 'indicates action that had been continuing up till now / came to be',
    'oku': 'to do in advance / to leave in the current state expecting a later change',
    'kureru': '(asking) to do something for one',
    'morau': '(asking) to get somebody to do something',
    'itadaku': '(asking) to get somebody to do something (polite)',
    'iku': 'is becoming / action starting now and continuing',
    'suru': 'makes a verb from a noun',
    'itasu': 'makes a verb from a noun (humble)',
    'sareru': 'makes a verb from a noun (honorific or passive)',
    'saseru': 'let/make someone/something do ...',
    'rou': 'probably / it seems that... / I guess ...',
    'ii': "it's ok if ... / is it ok if ...?",
    'mo': 'even if ...',
    'sugiru': 'to be too (much) ...',
    'nikui': 'difficult to...',
    'sa': '-ness (degree or condition of adjective)',
    'tsutsu': 'while ... / in the process of ...',
    'tsutsuaru': 'to be doing ... / to be in the process of doing ...',
    'tsuzukeru': 'to continue ...',
    'uru': 'can ... / to be able to ...',
    'sou': 'looking like ... / seeming ...',
    'nai': 'negative suffix',
    'naide': 'without doing ... / don\'t',
    'ra': 'pluralizing suffix (not polite)',
    'kudasai': 'please do ...',
    'yagaru': 'indicates disdain or contempt',
    'naru': 'to become ...',
    'desu': 'formal copula',
    'desho': "it seems/perhaps/don't you think?",
    'tosuru': 'to try to .../to be about to...',
    'garu': 'to feel .../have a ... impression of someone',
    'me': 'somewhat/-ish',
    'gai': 'worth it to ...',
    'tasou': 'seem to want to... (tai+sou)',
    # Particle seqs - imported from constants and merged
    **SUFFIX_DESCRIPTION_SEQS,
}


# ============================================================================
# Maximum Suffix Nesting Depth
# ============================================================================
# Limits recursion when finding nested compound words like:
# 勉強し続けている (勉強し + 続けて + いる)
# Without a limit, pathological inputs could cause infinite recursion.
MAX_SUFFIX_DEPTH = 5

# Thread-local storage for tracking current recursion depth
import contextvars
_current_suffix_depth: contextvars.ContextVar[int] = contextvars.ContextVar('suffix_depth', default=0)

# ============================================================================
# Global Suffix Cache
# ============================================================================

# Cache mapping suffix text to (keyword, kana_form) pairs
_suffix_cache: Dict[str, List[Tuple[str, Optional[Any]]]] = {}

# Set of all unique 1-char suffix endings for quick filtering
# If a word doesn't end with any of these, no suffix can match
_suffix_ending_chars: Set[str] = set()

# Mapping from seq to suffix class
_suffix_class: Dict[int, str] = {}

# Lock for thread-safe cache initialization
_suffix_lock = threading.Lock()

# Flag indicating cache is initialized
_suffix_initialized = False


# ============================================================================
# Suffix Cache Initialization
# ============================================================================

def get_suffix_description(seq: int) -> Optional[str]:
    """Get description for a suffix by its seq number."""
    suffix_class = _suffix_class.get(seq, seq)
    return SUFFIX_DESCRIPTION.get(suffix_class)


def _update_cache(text: str, value: Tuple[str, Optional[Any]], join: bool = False):
    """Update suffix cache with a new entry."""
    global _suffix_cache, _suffix_ending_chars
    old = _suffix_cache.get(text)
    if old is None:
        _suffix_cache[text] = [value]
        # Track the last character of this suffix for quick filtering
        if text:
            _suffix_ending_chars.add(text[-1])
    elif join:
        _suffix_cache[text].append(value)
    else:
        _suffix_cache[text] = [value]


def get_kana_forms(session: Session, seq: int) -> List[KanaText]:
    """
    Get all kana forms for an entry and its conjugations.
    
    Returns kana text objects for both root and conjugated forms.
    """
    # Get kana texts for this seq directly
    direct = session.execute(
        select(KanaText).where(KanaText.seq == seq)
    ).scalars().all()
    
    # Also get kana texts for conjugations of this seq
    conj_seqs = session.execute(
        select(Conjugation.seq).where(Conjugation.from_seq == seq)
    ).scalars().all()
    
    if conj_seqs:
        indirect = session.execute(
            select(KanaText).where(KanaText.seq.in_(conj_seqs))
        ).scalars().all()
    else:
        indirect = []
    
    result = []
    for kt in direct:
        kt._conj_type = 'root'
        result.append(kt)
    
    for kt in indirect:
        kt._conj_type = 'conj'
        result.append(kt)
    
    return result


def get_kana_form(session: Session, seq: int, text: str, conj: Optional[str] = None) -> Optional[KanaText]:
    """Get a specific kana form by seq and text."""
    result = session.execute(
        select(KanaText).where(and_(KanaText.seq == seq, KanaText.text == text))
    ).scalars().first()
    
    if result and conj:
        result._conj_type = conj
    
    return result


def _load_conjs(session: Session, key: str, seq: int, suffix_class: Optional[str] = None, join: bool = False, include_kanji: bool = False):
    """Load all conjugation forms into suffix cache.
    
    Args:
        session: Database session
        key: Handler key for suffix matching
        seq: Entry sequence number
        suffix_class: Optional suffix class (defaults to key)
        join: If True, join with existing cache entries
        include_kanji: If True, also load kanji text forms
    """
    from himotoki.db.models import KanjiText
    actual_class = suffix_class or key
    for kf in get_kana_forms(session, seq):
        _update_cache(kf.text, (key, kf), join=join)
        _suffix_class[kf.seq] = actual_class
        
        # Also load kanji forms if requested
        if include_kanji:
            kanji_texts = session.execute(
                select(KanjiText.text).where(KanjiText.seq == kf.seq)
            ).scalars().all()
            for kanji_text in kanji_texts:
                if kanji_text != kf.text:  # Don't duplicate if already kana
                    _update_cache(kanji_text, (key, kf), join=join)


def _load_kf(key: str, kf: KanaText, suffix_class: Optional[str] = None, text: Optional[str] = None, join: bool = False):
    """Load a single kana form into suffix cache."""
    actual_text = text or kf.text
    actual_class = suffix_class or key
    _update_cache(actual_text, (key, kf), join=join)
    _suffix_class[kf.seq] = actual_class


def _load_abbr(key: str, text: str, join: bool = False):
    """Load an abbreviation into suffix cache."""
    _update_cache(text, (key, None), join=join)


def init_suffixes(session: Session, blocking: bool = True, reset: bool = False):
    """
    Initialize the suffix cache.
    
    This loads all suffix patterns into the cache for efficient lookup.
    
    Args:
        session: Database session
        blocking: If True, wait for initialization to complete
        reset: If True, force re-initialization
    """
    global _suffix_cache, _suffix_class, _suffix_ending_chars, _suffix_initialized
    
    if _suffix_initialized and not reset:
        return
    
    with _suffix_lock:
        if _suffix_initialized and not reset:
            return
        
        _suffix_cache = {}
        _suffix_class = {}
        _suffix_ending_chars = set()
        
        # ちゃう (chau) - completion
        _load_conjs(session, 'chau', SEQ_CHAU)
        _load_conjs(session, 'chau', SEQ_CHIMAU)
        
        # は particle with ちゃ/じゃ reading
        ha_kf = get_kana_form(session, SEQ_WA, 'は')
        if ha_kf:
            _load_kf('chau', ha_kf, suffix_class='ha', text='ちゃ')
            _load_kf('chau', ha_kf, suffix_class='ha', text='じゃ')
        
        # たい (tai) - want to
        _load_conjs(session, 'tai', SEQ_TAI)
        
        # たそう (tasou) - seem to want to (tai + sou)
        tasou_kf = get_kana_form(session, 900000, 'たそう')  # Synthetic entry
        if tasou_kf:
            _load_kf('tai', tasou_kf, suffix_class='tasou')
        
        # 難い (nikui) - difficult to
        _load_conjs(session, 'ren-', SEQ_NIKUI, suffix_class='nikui')
        
        # おる (oru) - humble progressive
        _load_conjs(session, 'te', SEQ_ORU, suffix_class='oru')
        
        # ある (aru) - result state
        _load_conjs(session, 'te', SEQ_ARU, suffix_class='aru')
        
        # いる (iru) - progressive
        for kf in get_kana_forms(session, SEQ_IRU):
            tkf = kf.text
            if len(tkf) > 1:
                _update_cache(tkf, ('teiru+', kf))
                _update_cache(tkf[1:], ('teiru', kf))
            else:
                _update_cache(tkf, ('teiru', kf))
            _suffix_class[kf.seq] = 'iru'
        
        # くる (kuru) - coming to be
        _load_conjs(session, 'te', SEQ_KURU, suffix_class='kuru')
        
        # おく (oku) - in advance
        _load_conjs(session, 'te', SEQ_OKU, suffix_class='oku')
        _load_conjs(session, 'to', SEQ_TOKU, suffix_class='oku')
        
        # しまう (shimau) - completion (via chau)
        _load_conjs(session, 'te', SEQ_SHIMAU, suffix_class='chau')
        
        # くれる/もらう/いただく - request forms
        _load_conjs(session, 'te+space', SEQ_KURERU, suffix_class='kureru')
        _load_conjs(session, 'te+space', SEQ_MORAU, suffix_class='morau')
        _load_conjs(session, 'te+space', SEQ_ITADAKU, suffix_class='itadaku')
        
        # いく (iku) - going/becoming
        for kf in get_kana_forms(session, SEQ_IKU):
            tkf = kf.text
            if tkf.startswith('い'):
                _update_cache(tkf, ('te', kf))
                if len(tkf) > 1:
                    _update_cache(tkf[1:], ('te', kf))
            _suffix_class[kf.seq] = 'iku'
        
        # いい (ii) - ok if
        ii_kf = get_kana_form(session, SEQ_II, 'いい')
        if ii_kf:
            _load_kf('teii', ii_kf, suffix_class='ii')
        
        # もいい - "it's ok if" (て form + もいい)
        # This creates the compound ～てもいい pattern
        # Try to load from database first, otherwise register directly
        moii_kf = get_kana_form(session, SEQ_MOII, 'もいい')
        if moii_kf:
            _load_kf('teii', moii_kf, suffix_class='ii', text='もいい')
        else:
            # If the custom entry doesn't exist, register abbreviation for もいい
            # This allows ～てもいい to be recognized
            _load_abbr('teii', 'もいい')
        
        # も (mo) - even if
        mo_kf = get_kana_form(session, SEQ_MO, 'も')
        if mo_kf:
            _load_kf('te', mo_kf, suffix_class='mo')
        
        # ください (kudasai) - please do
        kudasai_kf = get_kana_form(session, SEQ_KUDASAI, 'ください', conj='root')
        if kudasai_kf:
            _load_kf('kudasai', kudasai_kf)
        
        # する (suru) - make verb from noun
        _load_conjs(session, 'suru', SEQ_SURU)
        _load_conjs(session, 'suru', SEQ_ITASU, suffix_class='itasu')
        _load_conjs(session, 'suru', SEQ_SARERU, suffix_class='sareru')
        _load_conjs(session, 'suru', SEQ_SASERU, suffix_class='saseru')
        
        # そう (sou) - looks like
        # Only load そう conjugations, NOT そうにない (SEQ_SOU_NI_NAI = 2141080)
        # because そうにない conjugations include そうにな which incorrectly matches
        # patterns like 張り裂けそうになる (should be 張り裂けそう + に + なる)
        _load_conjs(session, 'sou', SEQ_SOU)
        
        # ろう (rou) - probably
        darou_kf = get_kana_form(session, 1928670, 'だろう')  # だろう seq not frequently used
        if darou_kf:
            _load_kf('rou', darou_kf, text='ろう')
        
        # すぎる (sugiru) - too much
        _load_conjs(session, 'sugiru', 1195970)
        
        # さ (sa) - -ness
        sa_kf = get_kana_form(session, 2029120, 'さ')
        if sa_kf:
            _load_kf('sa', sa_kf)
        
        # つつ (tsutsu) - while
        tsutsu_kf = get_kana_form(session, 1008120, 'つつ')
        if tsutsu_kf:
            _load_kf('ren', tsutsu_kf, suffix_class='tsutsu')
        _load_conjs(session, 'ren', 2027910, suffix_class='tsutsuaru')
        
        # 続ける (tsuzukeru) - to continue (V-続ける pattern)
        # Include kanji forms so 続けて matches alongside つづけて
        _load_conjs(session, 'ren', 1405800, suffix_class='tsuzukeru', include_kanji=True)
        
        # うる (uru) - can
        uru_kf = get_kana_form(session, 1454500, 'うる')
        if uru_kf:
            _load_kf('ren', uru_kf, suffix_class='uru')
        
        # なく (naku) - negative
        naku_kf = session.execute(
            select(KanaText)
            .join(Conjugation, KanaText.seq == Conjugation.seq)
            .where(and_(KanaText.text == 'なく', Conjugation.from_seq == 1529520))
        ).scalars().first()
        if naku_kf:
            _load_kf('neg', naku_kf, suffix_class='nai')
        
        # ないで (naide) - negative te-form "without doing" / "don't"
        naide_kf = get_kana_form(session, 2258690, 'ないで')
        if naide_kf:
            _load_kf('neg', naide_kf, suffix_class='naide')
        
        # なる (naru) - become
        _load_conjs(session, 'adv', 1375610, suffix_class='naru')
        
        # やがる (yagaru) - disdain
        _load_conjs(session, 'teren', 1012740, suffix_class='yagaru')
        
        # ら (ra) - plural
        ra_kf = get_kana_form(session, 2067770, 'ら')
        if ra_kf:
            _load_kf('ra', ra_kf)
        
        # らしい (rashii) - seems like
        _load_conjs(session, 'rashii', 1013240)
        
        # です (desu) - formal copula
        desu_kf = get_kana_form(session, 1628500, 'です')
        if desu_kf:
            _load_kf('desu', desu_kf)
        
        # でしょう (desho)
        desho_kf = get_kana_form(session, 1008420, 'でしょう')
        if desho_kf:
            _load_kf('desho', desho_kf)
        desho2_kf = get_kana_form(session, 1008420, 'でしょ')
        if desho2_kf:
            _load_kf('desho', desho2_kf)
        
        # とする (tosuru) - try to
        _load_conjs(session, 'tosuru', 2136890)
        
        # くらい (kurai) - about/approximately
        kurai_kf = get_kana_form(session, 1154340, 'くらい')
        if kurai_kf:
            _load_kf('kurai', kurai_kf)
        gurai_kf = get_kana_form(session, 1154340, 'ぐらい')
        if gurai_kf:
            _load_kf('kurai', gurai_kf)
        
        # がる (garu) - feel
        _load_conjs(session, 'garu', 1631750)
        
        # がち (gachi) - tend to
        gachi_kf = get_kana_form(session, 2016470, 'がち')
        if gachi_kf:
            _load_kf('ren', gachi_kf, suffix_class='gachi')
        
        # げ (ge) - -ish
        ge_kf = get_kana_form(session, 2006580, 'げ')
        if ge_kf:
            _load_kf('iadj', ge_kf)
        
        # め (me) - somewhat
        me_kf = get_kana_form(session, 1604890, 'め')
        if me_kf:
            _load_kf('iadj', me_kf, suffix_class='me')
        
        # がい (gai) - worth
        gai_kf = get_kana_form(session, 2606690, 'がい')
        if gai_kf:
            _load_kf('ren-', gai_kf, suffix_class='gai')
        
        # Abbreviations
        _load_abbr('nai', 'ねえ')
        _load_abbr('nai', 'ねぇ')
        _load_abbr('nai', 'ねー')
        _load_abbr('nai-x', 'ず')
        _load_abbr('nai-x', 'ざる')
        _load_abbr('nai-x', 'ぬ')
        _load_abbr('nai-n', 'ん')
        
        _load_abbr('nakereba', 'なきゃ')
        _load_abbr('nakereba', 'なくちゃ')
        
        _load_abbr('teba', 'ちゃ', join=True)  # つ
        _load_abbr('reba', 'りゃ')  # る
        _load_abbr('keba', 'きゃ')  # く
        _load_abbr('geba', 'ぎゃ')  # ぐ
        _load_abbr('neba', 'にゃ')  # ぬ
        _load_abbr('beba', 'びゃ')  # ぶ
        _load_abbr('meba', 'みゃ')  # む
        _load_abbr('seba', 'しゃ')  # す
        
        _load_abbr('shimashou', 'しましょ')
        _load_abbr('dewanai', 'じゃない')
        
        _load_abbr('ii', 'ええ')
        
        _suffix_initialized = True


def is_suffix_cache_ready() -> bool:
    """Check if suffix cache is initialized."""
    return _suffix_initialized


def could_have_suffix(word: str) -> bool:
    """
    Quick check if a word could possibly have a suffix.
    
    Returns False if the word doesn't end with any character that 
    appears at the end of known suffixes. This is a cheap O(1) filter.
    
    Args:
        word: Word to check
        
    Returns:
        True if a suffix could potentially match, False if definitely not
    """
    if not _suffix_initialized or len(word) < 2:
        return False
    # Check if word ends with any character that suffixes end with
    return word[-1] in _suffix_ending_chars


# ============================================================================
# Suffix Lookup Functions
# ============================================================================

def get_suffix_map(session: Session, text: str) -> Dict[int, List[Tuple[str, str, Optional[KanaText]]]]:
    """
    Create a suffix map for the given text.
    
    Maps end positions to list of (suffix, keyword, kana_form) tuples.
    
    Args:
        session: Database session
        text: Text to create suffix map for
    
    Returns:
        Dictionary mapping end position to suffix entries
    """
    init_suffixes(session)
    
    result: Dict[int, List[Tuple[str, str, Optional[KanaText]]]] = {}
    
    for start in range(len(text)):
        for end in range(start + 1, len(text) + 1):
            substr = text[start:end]
            vals = _suffix_cache.get(substr)
            if vals:
                for keyword, kf in vals:
                    if end not in result:
                        result[end] = []
                    result[end].append((substr, keyword, kf))
    
    return result


def get_suffixes(session: Session, word: str) -> List[Tuple[str, str, Optional[KanaText]]]:
    """
    Get all suffix matches for a word.
    
    Searches from the end of the word backwards.
    
    Args:
        session: Database session
        word: Word to find suffixes for
    
    Returns:
        List of (suffix, keyword, kana_form) tuples
    """
    init_suffixes(session)
    
    results = []
    for start in range(len(word) - 1, 0, -1):
        substr = word[start:]
        vals = _suffix_cache.get(substr)
        if vals:
            for keyword, kf in vals:
                results.append((substr, keyword, kf))
    
    return results


# ============================================================================
# Suffix Matching
# ============================================================================

# List of suffix types where only unique matches are allowed
SUFFIX_UNIQUE_ONLY: Set[str] = {
    'ra', 'mo', 'nikui', 'gai', 'nai-n', 'dewanai',
    'eba', 'teba', 'reba', 'keba', 'geba', 'neba', 'beba', 'meba', 'seba', 'ii',
}

# Abbreviation suffix types - these create compounds that should be scored 
# without using the abbreviated compound's mora length.
# Matches Ichiran's def-abbr-suffix handlers which create proxy-text objects.
ABBREVIATION_SUFFIXES: Set[str] = {
    'nai', 'nai-x', 'nai-n', 'nakereba', 'shimashou', 'dewanai',
    'teba', 'reba', 'keba', 'geba', 'neba', 'beba', 'meba', 'seba', 'ii',
}


def match_unique(suffix_class: str, matches: List[Any]) -> bool:
    """
    Check if only unique matches are allowed for this suffix class.
    
    Some suffix patterns should only match when no other word exists.
    """
    return suffix_class in SUFFIX_UNIQUE_ONLY


def find_word_suffix(
    session: Session,
    word: str,
    matches: Optional[List[Any]] = None,
    suffix_map: Optional[Dict] = None,
    next_end: Optional[int] = None,
    depth: int = 0,
) -> List[Any]:
    """
    Find suffix matches for a word.
    
    This tries to match grammatical suffixes at the end of the word
    and return compound word objects.
    
    Ports ichiran's find-word-suffix from dict-grammar.lisp lines 692-706.
    
    Args:
        session: Database session
        word: Word to find suffix for
        matches: Existing matches (for uniqueness checking)
        suffix_map: Pre-computed suffix map (optional)
        next_end: End position in source text (optional)
        depth: Current recursion depth for nested compounds
    
    Returns:
        List of compound word matches
    """
    # Guard against excessive recursion using both explicit depth and context var
    current_depth = _current_suffix_depth.get()
    effective_depth = max(depth, current_depth)
    if effective_depth >= MAX_SUFFIX_DEPTH:
        return []
    
    # Set context var for handlers that may call find_word_suffix recursively
    token = _current_suffix_depth.set(effective_depth + 1)
    
    try:
        from himotoki.lookup import adjoin_word, WordMatch
        
        init_suffixes(session)
        
        # Get suffixes from map or by direct lookup
        if suffix_map and next_end:
            suffixes = suffix_map.get(next_end, [])
        else:
            suffixes = get_suffixes(session, word)
        
        results = []
        
        for suffix, keyword, kf in suffixes:
            # Check uniqueness constraint
            suffix_class = _suffix_class.get(kf.seq if kf else None, keyword)
            if matches and match_unique(suffix_class, matches):
                continue
            
            offset = len(word) - len(suffix)
            if offset <= 0:
                continue
            
            root = word[:offset]
            
            # Get suffix function based on keyword
            suffix_fn = SUFFIX_HANDLERS.get(keyword)
            if not suffix_fn:
                continue
            
            # Call suffix handler to get primary words
            primary_words = suffix_fn(session, root, suffix, kf)
            
            for pw in primary_words:
                if pw is None:
                    continue
                
                # Create suffix word for adjoin
                # Get conjugation IDs for the suffix word if it's a conjugated form
                suffix_conj_ids = None
                if kf and hasattr(kf, '_conj_type') and kf._conj_type == 'conj':
                    # This is a conjugated form - get the conjugation IDs
                    from himotoki.db.models import Conjugation
                    conj_query = select(Conjugation.id).where(Conjugation.seq == kf.seq)
                    suffix_conj_ids = list(session.execute(conj_query).scalars().all())
                
                if kf:
                    suffix_word = WordMatch(reading=kf, conjugations=suffix_conj_ids)
                else:
                    # Create a placeholder for the suffix (abbreviation case)
                    # For abbreviations like もいい, we create a minimal placeholder
                    # that looks like a KanaText but without a database entry
                    class PlaceholderReading:
                        def __init__(self, text):
                            self.text = text
                            self.seq = None
                            self.ord = 0
                            self.common = None
                    placeholder = PlaceholderReading(suffix)
                    suffix_word = WordMatch(reading=placeholder)
                
                # Use adjoin_word to create compound (following ichiran's pattern)
                # Score is determined by the suffix handler configuration
                # For 'sou' suffix, use conditional scoring based on root
                if keyword in ('sou', 'sou+'):
                    score_mod = get_sou_score(root)
                else:
                    score_mod = SUFFIX_SCORES.get(keyword, 0)
                connector = SUFFIX_CONNECTORS.get(keyword, '')
                
                # Check if this is an abbreviation suffix
                is_abbrev = keyword in ABBREVIATION_SUFFIXES
                
                # Get kana for the compound
                # For primary word: get kana from reading, look up if kanji
                def get_word_kana(w):
                    from himotoki.lookup import CompoundWord
                    # For CompoundWord, return the compound's kana directly
                    if isinstance(w, CompoundWord):
                        return w.kana
                    if hasattr(w, 'reading'):
                        reading = w.reading
                        # Check if it's a kanji reading - look up kana
                        if hasattr(reading, 'seq') and hasattr(reading, 'text'):
                            # Try to get kana for this seq
                            from himotoki.db.models import KanaText
                            kana_result = session.execute(
                                select(KanaText.text)
                                .where(KanaText.seq == reading.seq)
                            ).scalars().first()
                            if kana_result:
                                return kana_result
                            # If no kana found, assume text is already kana
                            return reading.text
                    return w.text if hasattr(w, 'text') else ''
                
                primary_kana = get_word_kana(pw)
                suffix_kana = kf.text if kf else suffix
                # Include connector in kana (e.g., space for suru, kudasai, te+space)
                compound_kana = primary_kana + connector + suffix_kana
                
                compound = adjoin_word(
                    pw,
                    suffix_word,
                    text=word,
                    kana=compound_kana,
                    score_mod=score_mod,
                    is_abbrev=is_abbrev,
                )
                results.append(compound)
        
        return results
    finally:
        # Reset context var to previous value
        _current_suffix_depth.reset(token)


# Suffix scores - from def-simple-suffix definitions in ichiran's dict-grammar.lisp
SUFFIX_SCORES: Dict[str, float] = {
    'tai': 5,
    'ren': 5,
    'ren-': 0,
    'neg': 5,
    'te': 0,
    'teiru': 3,
    'teiru+': 6,
    'te+space': 3,
    'teren': 4,
    'teii': 1,
    'chau': 5,
    'to': 0,
    'suru': 5,
    'sou': 60,  # Default, but overridden by get_sou_score for specific roots
    'sou+': 1,
    'rou': 1,
    'adv': 1,
    'sugiru': 5,
    'sa': 2,
    'iadj': 1,
    'garu': 0,
    'ra': 1,
    'rashii': 3,
    'desu': 200,
    'desho': 300,
    'tosuru': 3,
    'kurai': 3,
    'nai': 5,
    'kudasai': 360,
}

# Suffix connectors - space between root and suffix in kana
SUFFIX_CONNECTORS: Dict[str, str] = {
    'suru': ' ',
    'kudasai': ' ',
    'te+space': ' ',
    'teii': ' ',
}


def get_sou_score(root: str) -> float:
    """
    Get the score_mod for そう suffix based on the root.
    
    Ports ichiran's conditional scoring for suffix-sou:
    - root "から" → 40
    - root "い" → 0
    - root "出来" → 100
    - otherwise → 60
    
    Additional adjustment: reduce score for short hiragana-only roots
    that could be confused with verb continuative forms (e.g., いた, よさ).
    This prevents incorrect splits like 言+いたそう when 言いたそう exists.
    """
    from himotoki.characters import count_char_class
    
    if root == 'から':
        return 40
    elif root == 'い':
        return 0
    elif root == '出来':
        return 100
    else:
        # For short hiragana-only roots, reduce the score to prevent
        # incorrect splits with verb continuatives
        if len(root) <= 2 and count_char_class(root, 'kanji') == 0:
            return 10  # Reduced from 60 to lower priority
        return 60


# ============================================================================
# Suffix Handler Functions
# ============================================================================

def find_word_with_conj_type(session: Session, word: str, *conj_types: int) -> List[Any]:
    """Import and call find_word_with_conj_type from lookup."""
    from himotoki.lookup import find_word_with_conj_type as _find_word_with_conj_type
    return _find_word_with_conj_type(session, word, *conj_types)


def find_word_with_pos(session: Session, word: str, *posi: str) -> List[Any]:
    """Find words with specific part-of-speech tags."""
    from himotoki.lookup import find_word
    from himotoki.db.models import SenseProp
    from sqlalchemy import select, and_
    
    words = find_word(session, word)
    results = []
    
    for w in words:
        # Check if any sense has the required POS
        has_pos = session.execute(
            select(SenseProp)
            .where(and_(
                SenseProp.seq == w.seq,
                SenseProp.tag == 'pos',
                SenseProp.text.in_(posi)
            ))
        ).scalars().first()
        
        if has_pos:
            results.append(w)
    
    return results


def find_word_with_neg_prop(session: Session, word: str) -> List[Any]:
    """Find words with negative conjugation property."""
    from himotoki.lookup import find_word_with_conj_prop
    
    def filter_fn(cdata):
        if cdata.prop and hasattr(cdata.prop, 'neg'):
            return cdata.prop.neg
        return False
    
    return find_word_with_conj_prop(session, word, filter_fn)


def _handler_tai(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle たい suffix - want to..."""
    if root == 'い':
        return []
    return find_word_with_conj_type(session, root, 13)  # Continuative


def _handler_ren(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle generic ren'youkei (continuative) suffix."""
    return find_word_with_conj_type(session, root, 13)


def _handler_neg(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle negative stem suffix."""
    from himotoki.lookup import CONJ_NEGATIVE_STEM
    return find_word_with_conj_type(session, root, 13, CONJ_NEGATIVE_STEM)


def _handler_chau(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """
    Handle ちゃう suffix - contracted てしまう (completion).
    
    Ports ichiran's suffix-chau from dict-grammar.lisp.
    The suffix starts with ち or じ (contracted from て or で).
    We reconstruct the te-form by:
    1. Looking at first char of suffix to determine て or で
    2. Concatenating root + て/で to form the te-form
    3. Looking up that te-form in the database
    
    For example: サボっちゃった
    - root = "サボっ"
    - suffix = "ちゃった" (first char is ち → て)
    - lookup "サボっ" + "て" = "サボって" as te-form
    """
    if not suffix:
        return []
    
    # Map first char of suffix to te/de
    first_char = suffix[0]
    if first_char == 'ち':
        te = 'て'
    elif first_char == 'じ':
        te = 'で'
    else:
        return []
    
    # Look up root + te as te-form conjugation
    te_form = root + te
    return find_word_with_conj_type(session, te_form, 3)


def _handler_to_contracted(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """
    Handle とく suffix - contracted ておく (doing in advance).
    
    Ports ichiran's suffix-to from dict-grammar.lisp.
    The suffix starts with と or ど (contracted from て or で).
    We reconstruct the te-form similarly to chau.
    
    For example: 置いとく
    - root = "置い"
    - suffix = "とく" (first char is と → て)  
    - lookup "置い" + "て" = "置いて" as te-form
    """
    if not suffix:
        return []
    
    # Map first char of suffix to te/de
    first_char = suffix[0]
    if first_char == 'と':
        te = 'て'
    elif first_char == 'ど':
        te = 'で'
    else:
        return []
    
    # Look up root + te as te-form conjugation
    te_form = root + te
    return find_word_with_conj_type(session, te_form, 3)


def _handler_te(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle て form suffix."""
    if root == 'で':
        return []
    if not root.endswith('て') and not root.endswith('で'):
        return []
    return find_word_with_conj_type(session, root, 3)  # Te-form


def _handler_teiru(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle ている suffix."""
    if root == 'いて':
        return []
    if not root.endswith('て') and not root.endswith('で'):
        return []
    # First try direct database lookup for te-form
    results = find_word_with_conj_type(session, root, 3)
    if results:
        return results
    # If not found, try to find root as a compound via suffix matching
    # This enables nested compounds like 勉強し続けている (勉強し + 続けて + いる)
    compound_results = find_word_suffix(session, root)
    return compound_results


def _handler_suru(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle する suffix - make verb from noun."""
    return find_word_with_pos(session, root, 'vs')


def _handler_sou(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle そう suffix - looks like."""
    from himotoki.lookup import CONJ_ADJECTIVE_STEM, CONJ_ADVERBIAL
    if root in ('な', 'よ', 'よさ', 'に', 'き'):
        return []
    
    # Check for なさ ending (negative adjective)
    if root.endswith('なさ'):
        root_patched = root[:-1] + 'い'
        return find_word_with_neg_prop(session, root_patched)
    
    results = find_word_with_conj_type(session, root, 13, CONJ_ADJECTIVE_STEM, CONJ_ADVERBIAL)
    # Filter out なぜる (seq 10195060 for conjugated form) which incorrectly matches なぜ + そう
    # The word なぜ is the interrogative "why", not the verb "to stroke"
    results = [r for r in results if getattr(r, 'seq', None) != 10195060]
    return results


def _handler_sugiru(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle すぎる suffix - too much."""
    if root == 'い':
        return []
    
    # Check for なさ ending
    if root.endswith('なさ') or root.endswith('無さ'):
        root_patched = root[:-1] + 'い'
        return find_word_with_neg_prop(session, root_patched)
    
    # Add い to root and look for adjectives
    root_i = root + 'い'
    return find_word_with_pos(session, root_i, 'adj-i')


def _handler_sa(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle さ suffix - -ness."""
    from himotoki.lookup import CONJ_ADJECTIVE_STEM
    result = find_word_with_conj_type(session, root, CONJ_ADJECTIVE_STEM)
    result.extend(find_word_with_pos(session, root, 'adj-na'))
    return result


def _handler_rou(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle ろう suffix - probably."""
    return find_word_with_conj_type(session, root, 2)  # Past


def _handler_adv(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle adverbial suffix."""
    from himotoki.lookup import CONJ_ADVERBIAL
    return find_word_with_conj_type(session, root, CONJ_ADVERBIAL)


def _handler_kudasai(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle ください suffix - please do."""
    if not root.endswith('て') and not root.endswith('で'):
        return []
    return find_word_with_conj_type(session, root, 3)


def _handler_teii(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle ていい suffix - ok if."""
    if not root.endswith('て') and not root.endswith('で'):
        return []
    return find_word_with_conj_type(session, root, 3)


def _handler_garu(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle がる suffix - feel."""
    from himotoki.lookup import CONJ_ADJECTIVE_STEM
    if root in ('な', 'い', 'よ'):
        return []
    
    result = find_word_with_conj_type(session, root, CONJ_ADJECTIVE_STEM)
    
    # Also check for そ ending (そう + がる)
    if root.endswith('そ'):
        root_patched = root[:-1] + 'う'
        result.extend(find_word_with_suffix(session, root_patched, 'sou'))
    
    return result


def _handler_ra(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle ら suffix - plural."""
    if root.endswith('ら'):
        return []
    return find_word_with_pos(session, root, 'pn')


def _handler_rashii(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle らしい suffix - seems like."""
    result1 = find_word_with_conj_type(session, root, 2)
    result2 = find_word_with_conj_type(session, root + 'ら', 11)
    return result1 + result2


def _handler_desu(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle です suffix - formal copula."""
    if root.endswith('ない') or root.endswith('なかった'):
        return find_word_with_neg_prop(session, root)
    return []


def _handler_desho(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle でしょう suffix."""
    if root.endswith('ない'):
        return find_word_with_neg_prop(session, root)
    return []


def _handler_tosuru(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle とする suffix - try to."""
    return find_word_with_conj_type(session, root, 9)  # Volitional


def _handler_kurai(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle くらい suffix - about/approximately."""
    return find_word_with_conj_type(session, root, 2)


def _handler_iadj(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle i-adjective suffix like げ, め."""
    from himotoki.lookup import CONJ_ADJECTIVE_STEM
    return find_word_with_conj_type(session, root, CONJ_ADJECTIVE_STEM)


# Abbreviation handlers

def _find_word_with_neg_prop_filtered(
    session: Session,
    word: str,
    blocked_seqs: set,
    allow_root: bool = False,
) -> List[Any]:
    """
    Find words with negative conjugation property, excluding certain root seqs.
    
    Ports ichiran's filter logic from abbr-nee and abbr-n in dict-grammar.lisp:
    (and (not (find (conj-data-from cdata) '(1577980 1547720)))
         (conj-neg (conj-data-prop cdata)))
    
    Args:
        session: Database session
        word: Word text to search for
        blocked_seqs: Set of from_seq values to exclude
        allow_root: If True, also return root forms
    
    Returns:
        List of word matches with negative conjugation, excluding blocked seqs
    """
    from himotoki.lookup import find_word_with_conj_prop
    
    def filter_fn(cdata):
        # Must be negative form
        if not (cdata.prop and hasattr(cdata.prop, 'neg') and cdata.prop.neg):
            return False
        # Exclude blocked root seqs (居ない, 来ない create problems)
        if cdata.from_seq in blocked_seqs:
            return False
        return True
    
    return find_word_with_conj_prop(session, word, filter_fn, allow_root=allow_root)


def _handler_abbr_nai(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """
    Handle ない abbreviation (ねえ, ねぇ, ねー etc.).
    
    Ports ichiran's abbr-nee from dict-grammar.lisp.
    Blocks いる (SEQ_IRU) and 来る (SEQ_KURU) conjugations to avoid false matches.
    Allows root forms (:allow-root t in ichiran).
    """
    return _find_word_with_neg_prop_filtered(
        session, root + 'ない', BLOCKED_NAI_SEQS, allow_root=True
    )


def _handler_abbr_nai_n(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """
    Handle ん contraction (nai-n suffix).
    
    Ports ichiran's abbr-n from dict-grammar.lisp.
    Blocks いる (SEQ_IRU) and 来る (SEQ_KURU) conjugations to avoid false matches.
    Does NOT allow root forms (differs from abbr-nee).
    
    Example: 考えてん should NOT match 考えていないん (negative of いる).
    Instead, it should match 考えて + ん separately.
    """
    return _find_word_with_neg_prop_filtered(
        session, root + 'ない', BLOCKED_NAI_SEQS, allow_root=False
    )


def _handler_abbr_nx(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """
    Handle ず/ざる/ぬ abbreviation (nai-x suffix).
    
    Ports ichiran's abbr-nx from dict-grammar.lisp.
    Blocks する (SEQ_SURU) and 富む (SEQ_TOMU) conjugations.
    Special case: せ -> しない (for する).
    """
    if root == 'せ':
        return find_word_conj_of(session, 'しない', SEQ_SURU)
    
    from himotoki.lookup import find_word_with_conj_prop
    
    def filter_fn(cdata):
        # Must be negative form
        if not (cdata.prop and hasattr(cdata.prop, 'neg') and cdata.prop.neg):
            return False
        # Exclude blocked words (する, 富む)
        if cdata.from_seq in BLOCKED_NAI_X_SEQS:
            return False
        return True
    
    return find_word_with_conj_prop(session, root + 'ない', filter_fn)


def _handler_abbr_nakereba(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle なきゃ/なくちゃ abbreviation."""
    from himotoki.lookup import find_word_full
    return find_word_full(session, root + 'なければ')


def _handler_abbr_shimasho(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle しましょ abbreviation."""
    from himotoki.lookup import find_word_full
    return find_word_full(session, root + 'しましょう')


def _handler_abbr_dewanai(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle じゃない abbreviation."""
    from himotoki.lookup import find_word_full
    return find_word_full(session, root + 'ではない')


def _handler_abbr_eba(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle conditional abbreviations (りゃ, きゃ, etc.)."""
    from himotoki.lookup import find_word_full
    # Map abbreviation to full conditional form
    suffix_map = {
        'ちゃ': 'てば',
        'りゃ': 'れば',
        'きゃ': 'けば',
        'ぎゃ': 'げば',
        'にゃ': 'ねば',
        'びゃ': 'べば',
        'みゃ': 'めば',
        'しゃ': 'せば',
    }
    full_suffix = suffix_map.get(suffix)
    if full_suffix:
        return find_word_full(session, root + full_suffix)
    return []


def _handler_abbr_ii(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle ええ abbreviation for いい."""
    from himotoki.lookup import find_word_full
    return find_word_full(session, root + 'いい')


# Mapping of suffix keywords to handlers
SUFFIX_HANDLERS: Dict[str, Callable] = {
    'tai': _handler_tai,
    'ren': _handler_ren,
    'ren-': _handler_ren,
    'neg': _handler_neg,
    'te': _handler_te,
    'teiru': _handler_teiru,
    'teiru+': _handler_teiru,
    'te+space': _handler_te,
    'suru': _handler_suru,
    'sou': _handler_sou,
    'sou+': _handler_sou,
    'sugiru': _handler_sugiru,
    'sa': _handler_sa,
    'rou': _handler_rou,
    'adv': _handler_adv,
    'kudasai': _handler_kudasai,
    'teii': _handler_teii,
    'garu': _handler_garu,
    'ra': _handler_ra,
    'rashii': _handler_rashii,
    'desu': _handler_desu,
    'desho': _handler_desho,
    'tosuru': _handler_tosuru,
    'kurai': _handler_kurai,
    'iadj': _handler_iadj,
    'chau': _handler_chau,  # Contracted てしまう with te-reconstruction
    'to': _handler_to_contracted,  # Contracted ておく with te-reconstruction
    # Abbreviations - each has distinct behavior matching ichiran
    'nai': _handler_abbr_nai,      # ねえ, ねぇ, ねー - allows root forms
    'nai-x': _handler_abbr_nx,     # ず, ざる, ぬ - blocks する
    'nai-n': _handler_abbr_nai_n,  # ん contraction - blocks いる/来る, no root
    'nakereba': _handler_abbr_nakereba,
    'shimashou': _handler_abbr_shimasho,
    'dewanai': _handler_abbr_dewanai,
    'teba': _handler_abbr_eba,
    'reba': _handler_abbr_eba,
    'keba': _handler_abbr_eba,
    'geba': _handler_abbr_eba,
    'neba': _handler_abbr_eba,
    'beba': _handler_abbr_eba,
    'meba': _handler_abbr_eba,
    'seba': _handler_abbr_eba,
    'ii': _handler_abbr_ii,
}
