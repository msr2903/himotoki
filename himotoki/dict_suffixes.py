"""
Suffix handling for compound words in Himotoki.

This is a 1:1 port of Ichiran's suffix system from dict-grammar.lisp.
Handles verb compounds like te-form + いる/ある/しまう, たい forms, etc.

Key Ichiran components ported:
- *suffix-cache*: Maps suffix text -> (keyword, kana_form)
- *suffix-class*: Maps seq -> suffix class (e.g., :iru, :aru)
- get-suffix-map: Creates position -> suffix map for a string
- find-word-suffix: Finds compound words by matching suffixes
- Various suffix handlers (suffix-teiru, suffix-te, etc.)

Reference: ichiran-source-code/dict-grammar.lisp lines 1-700
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any, Set, Callable
from functools import lru_cache

from himotoki.conn import query, query_one
from himotoki.characters import as_hiragana, is_kana


# ============================================================================
# Suffix Cache (matches Ichiran's *suffix-cache* and *suffix-class*)
# ============================================================================

# suffix_cache: Maps suffix text -> list of (keyword, kana_form_row)
# kana_form_row is a dict with keys: seq, text, common, conjugations
_suffix_cache: Dict[str, List[Tuple[str, Optional[dict]]]] = {}

# suffix_class: Maps seq -> class keyword (e.g., 'iru', 'aru')
_suffix_class: Dict[int, str] = {}

# Initialized flag
_suffixes_initialized = False


# ============================================================================
# Suffix Descriptions (from Ichiran's *suffix-description*)
# ============================================================================

SUFFIX_DESCRIPTIONS = {
    'chau': "indicates completion (to finish ...)",
    'ha': "topic marker particle",
    'tai': "want to... / would like to...",
    'iru': "indicates continuing action (to be ...ing)",
    'oru': "indicates continuing action (to be ...ing) (humble)",
    'aru': "indicates completion / finished action",
    'kuru': "indicates action that had been continuing up till now / came to be",
    'oku': "to do in advance / to leave in the current state expecting a later change",
    'kureru': "(asking) to do something for one",
    'morau': "(asking) to get somebody to do something",
    'itadaku': "(asking) to get somebody to do something (polite)",
    'iku': "is becoming / action starting now and continuing",
    'suru': "makes a verb from a noun",
    'itasu': "makes a verb from a noun (humble)",
    'sareru': "makes a verb from a noun (honorific or passive)",
    'saseru': "let/make someone/something do ...",
    'rou': "probably / it seems that... / I guess ...",
    'ii': "it's ok if ... / is it ok if ...?",
    'mo': "even if ...",
    'sugiru': "to be too (much) ...",
    'nikui': "difficult to...",
    'sa': "-ness (degree or condition of adjective)",
    'tsutsu': "while ... / in the process of ...",
    'tsutsuaru': "to be doing ... / to be in the process of doing ...",
    'uru': "can ... / to be able to ...",
    'sou': "looking like ... / seeming ...",
    'nai': "negative suffix",
    'ra': "pluralizing suffix (not polite)",
    'kudasai': "please do ...",
    'yagaru': "indicates disdain or contempt",
    'naru': "to become ...",
    'desu': "formal copula",
    'desho': "it seems/perhaps/don't you think?",
    'tosuru': "to try to .../to be about to...",
    'garu': "to feel .../have a ... impression of someone",
    'me': "somewhat/-ish",
    'gai': "worth it to ...",
    'tasou': "seem to want to... (tai+sou)",
}


def get_suffix_description(seq_or_class) -> Optional[str]:
    """Get description for a suffix by seq or class."""
    if isinstance(seq_or_class, int):
        suffix_class = _suffix_class.get(seq_or_class)
        if suffix_class:
            return SUFFIX_DESCRIPTIONS.get(suffix_class)
    return SUFFIX_DESCRIPTIONS.get(seq_or_class)


# ============================================================================
# Kana Form Lookup (matches Ichiran's get-kana-forms)
# ============================================================================

def get_kana_forms(seq: int) -> List[dict]:
    """
    Get all kana forms for an entry, including conjugated forms.
    
    Matches Ichiran's get-kana-forms function.
    
    Args:
        seq: Entry sequence number.
        
    Returns:
        List of dicts with keys: seq, text, common, conjugations
    """
    # Get root forms
    rows = query(
        """
        SELECT kt.seq, kt.text, kt.common
        FROM kana_text kt
        WHERE kt.seq = ?
        """,
        (seq,)
    )
    
    result = []
    for row in rows:
        result.append({
            'seq': row['seq'],
            'text': row['text'],
            'common': row['common'],
            'conjugations': 'root',
        })
    
    # Get conjugated forms (forms where from_seq = seq)
    conj_rows = query(
        """
        SELECT kt.seq, kt.text, kt.common, c.id as conj_id
        FROM kana_text kt
        INNER JOIN conjugation c ON c.seq = kt.seq
        WHERE c.from_seq = ?
        """,
        (seq,)
    )
    
    for row in conj_rows:
        result.append({
            'seq': row['seq'],
            'text': row['text'],
            'common': row['common'],
            'conjugations': [row['conj_id']],
        })
    
    return result


def get_kana_form(seq: int, text: str, conj: Any = None) -> Optional[dict]:
    """
    Get a specific kana form by seq and text.
    
    Matches Ichiran's get-kana-form function.
    """
    row = query_one(
        "SELECT seq, text, common FROM kana_text WHERE seq = ? AND text = ?",
        (seq, text)
    )
    if row:
        return {
            'seq': row['seq'],
            'text': row['text'],
            'common': row['common'],
            'conjugations': conj,
        }
    return None


# ============================================================================
# Initialize Suffix Cache (matches Ichiran's init-suffixes-thread)
# ============================================================================

def _update_suffix_cache(text: str, value: Tuple[str, Optional[dict]], join: bool = False):
    """Update suffix cache with a new entry."""
    old = _suffix_cache.get(text)
    if old is None:
        _suffix_cache[text] = [value]
    elif join:
        _suffix_cache[text].append(value)
    else:
        _suffix_cache[text] = [value]


def _load_kf(key: str, kf: Optional[dict], text: str = None, 
             suffix_class: str = None, join: bool = False):
    """Load a kana form as a suffix."""
    if kf is None:
        return
    actual_text = text or kf['text']
    _update_suffix_cache(actual_text, (key, kf), join=join)
    _suffix_class[kf['seq']] = suffix_class or key


def _load_conjs(key: str, seq: int, suffix_class: str = None, join: bool = False):
    """Load all conjugated forms of an entry as suffixes."""
    for kf in get_kana_forms(seq):
        _load_kf(key, kf, suffix_class=suffix_class, join=join)


def _load_abbr(key: str, text: str, join: bool = False):
    """Load an abbreviation as a suffix (no kana form)."""
    _update_suffix_cache(text, (key, None), join=join)


def init_suffixes():
    """
    Initialize the suffix cache with all known suffixes.
    
    This is a 1:1 port of Ichiran's init-suffixes-thread function
    from dict-grammar.lisp lines 167-318.
    """
    global _suffixes_initialized
    
    if _suffixes_initialized:
        return
    
    # Clear caches
    _suffix_cache.clear()
    _suffix_class.clear()
    
    # ちゃう / ちまう (completion)
    _load_conjs('chau', 2013800)  # ちゃう
    _load_conjs('chau', 2210750)  # ちまう
    
    # は particle for ちゃ/じゃ
    kf_ha = get_kana_form(2028920, 'は')
    if kf_ha:
        _load_kf('chau', kf_ha, text='ちゃ', suffix_class='ha', join=True)
        _load_kf('chau', kf_ha, text='じゃ', suffix_class='ha')
    
    # たい (want to)
    _load_conjs('tai', 2017560)
    
    # たそう (tai+sou - seems to want to)
    kf_tasou = get_kana_form(900000, 'たそう')
    if kf_tasou:
        _load_kf('tai', kf_tasou, suffix_class='tasou')
    
    # にくい (difficult to)
    _load_conjs('ren-', 2772730, suffix_class='nikui')
    
    # おる (to be, humble)
    _load_conjs('te', 1577985, suffix_class='oru')
    
    # ある (to exist, resultative)
    _load_conjs('te', 1296400, suffix_class='aru')
    
    # いる (to be, progressive) - special handling
    for kf in get_kana_forms(1577980):
        tkf = kf['text']
        # Longer forms get :teiru+, single char gets :teiru
        keyword = 'teiru+' if len(tkf) > 1 else 'teiru'
        _suffix_cache[tkf] = [(keyword, kf)]
        _suffix_class[kf['seq']] = 'iru'
        # Also register shortened form (without first char) as :teiru
        if len(tkf) > 1:
            short = tkf[1:]
            if short not in _suffix_cache:
                _suffix_cache[short] = [('teiru', kf)]
    
    # くる (to come)
    _load_conjs('te', 1547720, suffix_class='kuru')
    
    # おく (to put, preparatory)
    _load_conjs('te', 1421850, suffix_class='oku')
    _load_conjs('to', 2108590, suffix_class='oku')  # とく
    
    # しまう (completion, regrettable)
    _load_conjs('te', 1305380, suffix_class='chau')
    
    # くれる (do for me)
    _load_conjs('te+space', 1269130, suffix_class='kureru')
    
    # もらう (get someone to do)
    _load_conjs('te+space', 1535910, suffix_class='morau')
    
    # いただく (get someone to do, polite)
    _load_conjs('te+space', 1587290, suffix_class='itadaku')
    
    # いく (to go, becoming)
    for kf in get_kana_forms(1578850):
        tkf = kf['text']
        if tkf and tkf[0] == 'い':  # Only forms starting with い
            val = ('te', kf)
            _suffix_cache[tkf] = [val]
            _suffix_class[kf['seq']] = 'iku'
            # Short form
            tkf_short = tkf[1:]
            if tkf_short and tkf_short not in _suffix_cache:
                _suffix_cache[tkf_short] = [val]
    
    # いい (it's ok if)
    kf_ii = get_kana_form(2820690, 'いい')
    if kf_ii:
        _load_kf('teii', kf_ii, suffix_class='ii')
    kf_moii = get_kana_form(900001, 'もいい')
    if kf_moii:
        _load_kf('teii', kf_moii, text='もいい', suffix_class='ii')
    
    # も (even if)
    kf_mo = get_kana_form(2028940, 'も')
    if kf_mo:
        _load_kf('te', kf_mo, suffix_class='mo')
    
    # ください (please)
    kf_kudasai = get_kana_form(1184270, 'ください')
    if kf_kudasai:
        kf_kudasai['conjugations'] = 'root'
        _load_kf('kudasai', kf_kudasai)
    
    # する (to do, makes verb from noun)
    _load_conjs('suru', 1157170)
    _load_conjs('suru', 1421900, suffix_class='itasu')  # いたす
    _load_conjs('suru', 2269820, suffix_class='sareru')  # される
    _load_conjs('suru', 1005160, suffix_class='saseru')  # させる
    
    # そう (seeming)
    _load_conjs('sou', 1006610)
    _load_conjs('sou+', 2141080)  # そうにない
    
    # だろう -> ろう
    kf_darou = get_kana_form(1928670, 'だろう')
    if kf_darou:
        _load_kf('rou', kf_darou, text='ろう')
    
    # すぎる (too much)
    _load_conjs('sugiru', 1195970)
    
    # さ (nominalizer for adjectives)
    kf_sa = get_kana_form(2029120, 'さ')
    if kf_sa:
        _load_kf('sa', kf_sa)
    
    # つつ (while)
    kf_tsutsu = get_kana_form(1008120, 'つつ')
    if kf_tsutsu:
        _load_kf('ren', kf_tsutsu, suffix_class='tsutsu')
    
    # つつある (in the process of)
    _load_conjs('ren', 2027910, suffix_class='tsutsuaru')
    
    # うる (can)
    kf_uru = get_kana_form(1454500, 'うる')
    if kf_uru:
        _load_kf('ren', kf_uru, suffix_class='uru')
    
    # なく (negative stem form of ない)
    # TODO: find-word-conj-of for なく
    
    # なる (to become)
    _load_conjs('adv', 1375610, suffix_class='naru')
    
    # やがる (disdain)
    _load_conjs('teren', 1012740, suffix_class='yagaru')
    
    # ら (pluralizer)
    kf_ra = get_kana_form(2067770, 'ら')
    if kf_ra:
        _load_kf('ra', kf_ra)
    
    # らしい (seems like)
    _load_conjs('rashii', 1013240)
    
    # です (copula)
    kf_desu = get_kana_form(1628500, 'です')
    if kf_desu:
        _load_kf('desu', kf_desu)
    
    # でしょう / でしょ
    kf_deshou = get_kana_form(1008420, 'でしょう')
    if kf_deshou:
        _load_kf('desho', kf_deshou)
    kf_desho = get_kana_form(1008420, 'でしょ')
    if kf_desho:
        _load_kf('desho', kf_desho)
    
    # とする (try to)
    _load_conjs('tosuru', 2136890)
    
    # くらい / ぐらい
    kf_kurai = get_kana_form(1154340, 'くらい')
    if kf_kurai:
        _load_kf('kurai', kf_kurai)
    kf_gurai = get_kana_form(1154340, 'ぐらい')
    if kf_gurai:
        _load_kf('kurai', kf_gurai)
    
    # がる (to feel)
    _load_conjs('garu', 1631750)
    
    # がち (prone to)
    kf_gachi = get_kana_form(2016470, 'がち')
    if kf_gachi:
        _load_kf('ren', kf_gachi, suffix_class='gachi')
    
    # げ (adjective suffix)
    kf_ge = get_kana_form(2006580, 'げ')
    if kf_ge:
        _load_kf('iadj', kf_ge)
    
    # め (somewhat)
    kf_me = get_kana_form(1604890, 'め')
    if kf_me:
        _load_kf('iadj', kf_me, suffix_class='me')
    
    # がい (worth)
    kf_gai = get_kana_form(2606690, 'がい')
    if kf_gai:
        _load_kf('ren-', kf_gai, suffix_class='gai')
    
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
    
    _suffixes_initialized = True


# ============================================================================
# Suffix Map (matches Ichiran's get-suffix-map)
# ============================================================================

def get_suffix_map(text: str) -> Dict[int, List[Tuple[str, str, Optional[dict]]]]:
    """
    Create a map of positions to suffixes for a string.
    
    Matches Ichiran's get-suffix-map function.
    
    Args:
        text: Text to analyze.
        
    Returns:
        Dict mapping end_position -> list of (suffix_text, keyword, kana_form)
    """
    init_suffixes()
    
    result: Dict[int, List[Tuple[str, str, Optional[dict]]]] = {}
    
    for start in range(len(text)):
        for end in range(start + 1, len(text) + 1):
            substr = text[start:end]
            if substr in _suffix_cache:
                for keyword, kf in _suffix_cache[substr]:
                    if end not in result:
                        result[end] = []
                    result[end].append((substr, keyword, kf))
    
    return result


def get_suffixes(word: str) -> List[Tuple[str, str, Optional[dict]]]:
    """
    Get suffixes that match the end of a word.
    
    Matches Ichiran's get-suffixes function.
    
    Args:
        word: Word to find suffixes for.
        
    Returns:
        List of (suffix_text, keyword, kana_form) from longest to shortest.
    """
    init_suffixes()
    
    result = []
    for start in range(len(word) - 1, 0, -1):
        substr = word[start:]
        if substr in _suffix_cache:
            for keyword, kf in _suffix_cache[substr]:
                result.append((substr, keyword, kf))
    
    return result


# ============================================================================
# Suffix Handlers (matches Ichiran's defsuffix definitions)
# ============================================================================

# Suffix handler registry: keyword -> function(root, suffix_text, kana_form) -> list of compound words
_suffix_handlers: Dict[str, Callable] = {}


def _kf_to_kana_text(kf: Optional[dict]):
    """Convert a kana_form dict to a KanaText object."""
    if kf is None:
        return None
    from himotoki.dict import KanaText
    return KanaText(
        id=0,  # No actual id for suffix forms
        seq=kf['seq'],
        text=kf['text'],
        ord=0,
        common=kf.get('common'),
        common_tags="",
        conjugate_p=True,
        nokanji=False,
        conjugations=kf.get('conjugations'),
        best_kanji=None,
    )


def _te_check(root: str) -> bool:
    """Check if root is a valid te-form stem."""
    if not root or root == 'で':
        return False
    last_char = root[-1]
    return last_char in 'てで'


def _teiru_check(root: str) -> bool:
    """Check if root is valid for teiru suffix."""
    return root != 'いて' and _te_check(root)


def _find_word_with_conj_type(word: str, *conj_types: int):
    """
    Find words that are conjugations of the given types.
    
    Matches Ichiran's find-word-with-conj-type which uses find-word-full.
    This means we need to check conjugated forms, not just dictionary entries.
    """
    from himotoki.dict import find_word, ConjugatedText
    
    results = []
    
    # First check dictionary entries that might be conjugated forms
    for w in find_word(word):
        seq = w.seq
        # Check if this word has the given conjugation types in conjugation table
        rows = query(
            """
            SELECT DISTINCT cp.conj_type, c.from_seq
            FROM conjugation c
            INNER JOIN conj_prop cp ON cp.conj_id = c.id
            WHERE c.seq = ?
            """,
            (seq,)
        )
        for row in rows:
            if row['conj_type'] in conj_types:
                results.append({
                    'word': w,
                    'conj_type': row['conj_type'],
                    'from_seq': row['from_seq'],
                })
    
    # Also look for ConjugatedText entries in conj_lookup
    # This matches what find_substring_words does
    placeholders = ','.join('?' * len(conj_types))
    rows = query(
        f"""
        SELECT c.*, 
               COALESCE(entry_kana.common, k.common, n.common) as common
        FROM conj_lookup c
        LEFT JOIN kanji_text k ON c.seq = k.seq AND c.source_text = k.text
        LEFT JOIN kana_text n ON c.seq = n.seq AND c.source_text = n.text
        LEFT JOIN kana_text entry_kana ON c.seq = entry_kana.seq AND entry_kana.ord = 0
        WHERE c.text = ? AND c.conj_type IN ({placeholders})
        """,
        (word,) + conj_types
    )
    
    for row in rows:
        # Create ConjugatedText for this entry
        # sqlite3.Row doesn't have .get(), so use try/except or check keys
        try:
            reading = row['reading']
        except (KeyError, IndexError):
            reading = row['text']
        
        try:
            pos = row['pos']
        except (KeyError, IndexError):
            pos = ''
            
        try:
            neg = bool(row['neg'])
        except (KeyError, IndexError):
            neg = False
            
        try:
            fml = bool(row['fml'])
        except (KeyError, IndexError):
            fml = False
            
        try:
            from_seq = row['from_seq']
        except (KeyError, IndexError):
            from_seq = row['seq']
            
        try:
            source_reading = row['source_reading']
        except (KeyError, IndexError):
            source_reading = row['source_text']
        
        conj = ConjugatedText(
            id=row['id'],
            seq=row['seq'],
            text=row['text'],
            reading=reading,
            conj_type=row['conj_type'],
            pos=pos,
            neg=neg,
            fml=fml,
            common=row['common'],
            source_text=row['source_text'],
            source_reading=source_reading,
        )
        results.append({
            'word': conj,
            'conj_type': row['conj_type'],
            'from_seq': from_seq,
        })
    
    return results


# ============================================================================
# Compound Text - Use the one from dict.py to avoid type mismatches
# ============================================================================

def _get_compound_text_class():
    """Get CompoundText class from dict.py (late import to avoid circular import)."""
    from himotoki.dict import CompoundText
    return CompoundText


def adjoin_word(word1, word2, text: str = None, kana: str = None, 
                score_mod: int = 0, suffix_class: str = None):
    """
    Create a compound word from two words.
    
    Matches Ichiran's adjoin-word method.
    """
    CompoundText = _get_compound_text_class()
    
    if text is None:
        text = getattr(word1, 'get_text', lambda: str(word1))() + \
               getattr(word2, 'get_text', lambda: str(word2))()
    if kana is None:
        kana = getattr(word1, 'get_kana', lambda: '')() + \
               getattr(word2, 'get_kana', lambda: '')()
    
    if isinstance(word1, CompoundText):
        # Extend existing compound
        word1.text = text
        word1.kana = kana
        word1.words.append(word2)
        if isinstance(word1.score_mod, list):
            word1.score_mod = [score_mod] + word1.score_mod
        else:
            word1.score_mod = [score_mod, word1.score_mod]
        return word1
    else:
        return CompoundText(
            text=text,
            kana=kana,
            primary=word1,
            words=[word1, word2],
            score_mod=score_mod,
            suffix_class=suffix_class,
        )


# ============================================================================
# Suffix Handlers Implementation
# ============================================================================

def suffix_te(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """Handle te-form suffix (て + auxiliary verb)."""
    if not _te_check(root):
        return []
    
    matches = _find_word_with_conj_type(root, 3)  # Conjunctive (te-form)
    results = []
    
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    for m in matches:
        word = m['word']
        suffix_class = _suffix_class.get(kf['seq']) if kf else None
        compound = adjoin_word(
            word, 
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=0,
            suffix_class=suffix_class,
        )
        results.append(compound)
    
    return results


def suffix_teiru(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """Handle teiru suffix (て + いる progressive)."""
    if not _teiru_check(root):
        return []
    
    matches = _find_word_with_conj_type(root, 3)  # Conjunctive (te-form)
    results = []
    
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    for m in matches:
        word = m['word']
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=3,
            suffix_class='iru',
        )
        results.append(compound)
    
    return results


def suffix_teiru_plus(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """Handle teiru+ suffix (て + longer いる forms like います)."""
    if not _teiru_check(root):
        return []
    
    matches = _find_word_with_conj_type(root, 3)  # Conjunctive (te-form)
    results = []
    
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    for m in matches:
        word = m['word']
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=6,  # Higher score for longer forms
            suffix_class='iru',
        )
        results.append(compound)
    
    return results


# Register handlers
_suffix_handlers['te'] = suffix_te
_suffix_handlers['teiru'] = suffix_teiru
_suffix_handlers['teiru+'] = suffix_teiru_plus


# ============================================================================
# Find Word Suffix (matches Ichiran's find-word-suffix)
# ============================================================================

def find_word_suffix(word: str, suffix_map: Dict = None, 
                     suffix_next_end: int = None,
                     matches: List = None) -> List[CompoundText]:
    """
    Find compound words by matching suffixes.
    
    Matches Ichiran's find-word-suffix function.
    
    Args:
        word: Word to analyze.
        suffix_map: Pre-computed suffix map (from get_suffix_map).
        suffix_next_end: Position for suffix lookup in suffix_map.
        matches: Existing matches to check uniqueness against.
        
    Returns:
        List of CompoundText objects.
    """
    if suffix_map is not None and suffix_next_end is not None:
        suffixes = suffix_map.get(suffix_next_end, [])
    else:
        suffixes = get_suffixes(word)
    
    results = []
    
    for suffix_text, keyword, kf in suffixes:
        handler = _suffix_handlers.get(keyword)
        if handler is None:
            continue
        
        offset = len(word) - len(suffix_text)
        if offset <= 0:
            continue
        
        root = word[:offset]
        compounds = handler(root, suffix_text, kf)
        results.extend(compounds)
    
    return results
