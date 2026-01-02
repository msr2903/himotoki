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
# Suffix Context (matches Ichiran's *suffix-map-temp* and *suffix-next-end*)
# ============================================================================

# These module-level variables are used to pass context to recursive suffix matching
# Like Ichiran's dynamic variables *suffix-map-temp* and *suffix-next-end*
_suffix_map_temp: Optional[Dict] = None
_suffix_next_end: Optional[int] = None


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

# Weak conjugation types that should be filtered out when loading suffix forms
# From Ichiran's dict-errata.lisp lines 1168-1172, 1248-1253
# These are forms that don't make sense as standalone suffixes
WEAK_CONJ_TYPES = {
    51,  # +conj-adjective-stem+ (e.g., た from たい)
    52,  # +conj-negative-stem+
    53,  # +conj-causative-su+
    54,  # +conj-adjective-literary+
}

# Skip forms: (conj_type, neg) pairs that should be completely skipped
# From Ichiran's *skip-conj-forms*
SKIP_CONJ_FORMS = {
    (10, True),   # Type 10 with neg=True
    (3, True),    # Te-form with neg=True and fml=True (handled separately)
}


def _is_weak_conj_form(conj_type: int, neg: bool, fml: bool) -> bool:
    """
    Check if a conjugation form should be filtered out.
    
    Matches Ichiran's test-conj-prop with *weak-conj-forms*.
    """
    # Filter out weak conjugation types (any neg/fml)
    if conj_type in WEAK_CONJ_TYPES:
        return True
    
    # Filter type 9 with neg=True (from Ichiran: (9 t :any))
    if conj_type == 9 and neg:
        return True
    
    return False


def get_kana_forms(seq: int) -> List[dict]:
    """
    Get all kana forms for an entry, including conjugated forms.
    
    Matches Ichiran's get-kana-forms function with filtering.
    Filters out weak conjugation forms like adjective stems.
    
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
    
    # Get conjugated forms (forms where from_seq = seq) with conj_prop info
    # Filter out weak conjugation forms (like adjective stems)
    conj_rows = query(
        """
        SELECT kt.seq, kt.text, kt.common, c.id as conj_id,
               cp.conj_type, cp.neg, cp.fml
        FROM kana_text kt
        INNER JOIN conjugation c ON c.seq = kt.seq
        LEFT JOIN conj_prop cp ON cp.conj_id = c.id
        WHERE c.from_seq = ?
        """,
        (seq,)
    )
    
    for row in conj_rows:
        conj_type = row['conj_type']
        neg = bool(row['neg']) if row['neg'] is not None else False
        fml = bool(row['fml']) if row['fml'] is not None else False
        
        # Skip weak conjugation forms (matches Ichiran's get-kana-forms-conj-data-filter)
        if conj_type is not None and _is_weak_conj_form(conj_type, neg, fml):
            continue
        
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
    # もいい - synthetic entry (seq 900001 is in extra.xml in Ichiran)
    # Create a synthetic kana form since we don't have this in our database
    kf_moii = get_kana_form(900001, 'もいい')
    if not kf_moii:
        # Create synthetic entry for もいい
        kf_moii = {
            'seq': 900001,
            'text': 'もいい',
            'common': 0,  # Treat as common
            'conjugations': None,
        }
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
    
    # ことができる - "can do" grammar pattern
    # Load all conjugations of 出来る (seq 1340450) prefixed with ことが
    for kf in get_kana_forms(1340450):  # 出来る/できる
        dekiru_text = kf['text']
        kotoga_dekiru_text = 'ことが' + dekiru_text
        # Create a modified kana form dict for the kotogadekiru pattern
        kotoga_kf = {
            'seq': kf['seq'],
            'text': kotoga_dekiru_text,
            'common': kf['common'],
            'conjugations': kf['conjugations'],
        }
        _load_kf('kotogadekiru', kotoga_kf, suffix_class='kotogadekiru')
    
    # ことにする - "decide to do" grammar pattern (seq 2215340)
    # This is defined in dict-split.lisp as split-kotonisuru
    for kf in get_kana_forms(1157170):  # する
        suru_text = kf['text']
        koto_ni_suru_text = 'ことに' + suru_text
        koto_ni_kf = {
            'seq': kf['seq'],
            'text': koto_ni_suru_text,
            'common': kf['common'],
            'conjugations': kf['conjugations'],
        }
        _load_kf('kotonisuru', koto_ni_kf, suffix_class='kotonisuru')
    
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


# ============================================================================
# POS Abbreviation Mapping (from Ichiran)
# ============================================================================

# Maps POS abbreviations to their full text equivalents in JMdict
POS_ABBREV_MAP = {
    'vs': 'noun or participle which takes the aux. verb suru',
    'vs-s': 'suru verb - special class',
    'vs-i': 'suru verb - included',
    'adj-i': 'adjective (keiyoushi)',
    'adj-ix': 'adjective (keiyoushi) - yoi/ii class',
    'adj-na': 'adjectival nouns or quasi-adjectives (keiyodoshi)',
    'adj-no': "nouns which may take the genitive case particle 'no'",
    'adj-pn': 'pre-noun adjectival (rentaishi)',
    'adj-t': "'taru' adjective",
    'adj-f': 'noun or verb acting prenominally',
    'adj-nari': 'archaic/formal form of na-adjective',
    'adj-kari': "'kari' adjective (archaic)",
    'adj-ku': "'ku' adjective (archaic)",
    'adj-shiku': "'shiku' adjective (archaic)",
    'adv': 'adverb (fukushi)',
    'aux': 'auxiliary',
    'aux-adj': 'auxiliary adjective',
    'aux-v': 'auxiliary verb',
    'conj': 'conjunction',
    'cop': 'copula',
    'ctr': 'counter',
    'exp': 'expressions (phrases, clauses, etc.)',
    'int': 'interjection (kandoushi)',
    'n': 'noun (common) (futsuumeishi)',
    'n-adv': 'adverbial noun (fukushitekimeishi)',
    'n-pr': 'proper noun',
    'n-pref': 'noun, used as a prefix',
    'n-suf': 'noun, used as a suffix',
    'n-t': 'noun (temporal) (jisoumeishi)',
    'num': 'numeric',
    'pn': 'pronoun',
    'pref': 'prefix',
    'prt': 'particle',
    'suf': 'suffix',
    'unc': 'unclassified',
    'v-unspec': 'verb unspecified',
    'v1': 'Ichidan verb',
    'v1-s': 'Ichidan verb - kureru special class',
    'v2a-s': "Nidan verb with 'u' ending (archaic)",
    'v2b-k': "Nidan verb (upper class) with 'bu' ending (archaic)",
    'v2b-s': "Nidan verb (lower class) with 'bu' ending (archaic)",
    'v2d-k': "Nidan verb (upper class) with 'dzu' ending (archaic)",
    'v2d-s': "Nidan verb (lower class) with 'dzu' ending (archaic)",
    'v2g-k': "Nidan verb (upper class) with 'gu' ending (archaic)",
    'v2g-s': "Nidan verb (lower class) with 'gu' ending (archaic)",
    'v2h-k': "Nidan verb (upper class) with 'hu/fu' ending (archaic)",
    'v2h-s': "Nidan verb (lower class) with 'hu/fu' ending (archaic)",
    'v2k-k': "Nidan verb (upper class) with 'ku' ending (archaic)",
    'v2k-s': "Nidan verb (lower class) with 'ku' ending (archaic)",
    'v2m-k': "Nidan verb (upper class) with 'mu' ending (archaic)",
    'v2m-s': "Nidan verb (lower class) with 'mu' ending (archaic)",
    'v2n-s': "Nidan verb (lower class) with 'nu' ending (archaic)",
    'v2r-k': "Nidan verb (upper class) with 'ru' ending (archaic)",
    'v2r-s': "Nidan verb (lower class) with 'ru' ending (archaic)",
    'v2s-s': "Nidan verb (lower class) with 'su' ending (archaic)",
    'v2t-k': "Nidan verb (upper class) with 'tsu' ending (archaic)",
    'v2t-s': "Nidan verb (lower class) with 'tsu' ending (archaic)",
    'v2w-s': "Nidan verb (lower class) with 'u' ending and 'we' conjugation (archaic)",
    'v2y-k': "Nidan verb (upper class) with 'yu' ending (archaic)",
    'v2y-s': "Nidan verb (lower class) with 'yu' ending (archaic)",
    'v2z-s': "Nidan verb (lower class) with 'zu' ending (archaic)",
    'v4b': "Yodan verb with 'bu' ending (archaic)",
    'v4g': "Yodan verb with 'gu' ending (archaic)",
    'v4h': "Yodan verb with 'hu/fu' ending (archaic)",
    'v4k': "Yodan verb with 'ku' ending (archaic)",
    'v4m': "Yodan verb with 'mu' ending (archaic)",
    'v4n': "Yodan verb with 'nu' ending (archaic)",
    'v4r': "Yodan verb with 'ru' ending (archaic)",
    'v4s': "Yodan verb with 'su' ending (archaic)",
    'v4t': "Yodan verb with 'tsu' ending (archaic)",
    'v5aru': 'Godan verb - -aru special class',
    'v5b': "Godan verb with 'bu' ending",
    'v5g': "Godan verb with 'gu' ending",
    'v5k': "Godan verb with 'ku' ending",
    'v5k-s': 'Godan verb - Iku/Yuku special class',
    'v5m': "Godan verb with 'mu' ending",
    'v5n': "Godan verb with 'nu' ending",
    'v5r': "Godan verb with 'ru' ending",
    'v5r-i': "Godan verb with 'ru' ending (irregular verb)",
    'v5s': "Godan verb with 'su' ending",
    'v5t': "Godan verb with 'tsu' ending",
    'v5u': "Godan verb with 'u' ending",
    'v5u-s': "Godan verb with 'u' ending (special class)",
    'v5uru': 'Godan verb - Uru old class verb (old form of Eru)',
    'vi': 'intransitive verb',
    'vk': 'Kuru verb - special class',
    'vn': 'irregular nu verb',
    'vr': 'irregular ru verb, plain form ends with -ri',
    'vs-c': 'su verb - precursor to the modern suru',
    'vt': 'transitive verb',
    'vz': 'Ichidan verb - zuru verb (alternative form of -jiru verbs)',
}


def _expand_pos(posi: tuple) -> tuple:
    """Expand POS abbreviations to their full text equivalents."""
    expanded = []
    for pos in posi:
        if pos in POS_ABBREV_MAP:
            expanded.append(POS_ABBREV_MAP[pos])
        else:
            expanded.append(pos)
    return tuple(expanded)


def _find_word_with_pos(word: str, *posi: str):
    """
    Find words with specific part-of-speech tags.
    
    Matches Ichiran's find-word-with-pos from dict-grammar.lisp line 89.
    Finds entries where the text matches and has one of the given POS tags.
    
    Args:
        word: Word text to match.
        posi: POS tags to filter by (e.g., "vs", "adj-i", "adj-na", "pn").
        
    Returns:
        List of matching word entries.
    """
    from himotoki.dict import KanaText, KanjiText
    
    if not posi:
        return []
    
    # Expand POS abbreviations
    expanded_posi = _expand_pos(posi)
    
    # Check if word is kana
    table = "kana_text" if is_kana(word) else "kanji_text"
    
    placeholders = ','.join('?' * len(expanded_posi))
    rows = query(
        f"""
        SELECT DISTINCT kt.*
        FROM {table} kt
        INNER JOIN sense_prop sp ON sp.seq = kt.seq AND sp.tag = 'pos'
        WHERE kt.text = ? AND sp.text IN ({placeholders})
        """,
        (word,) + expanded_posi
    )
    
    result = []
    TextClass = KanaText if table == "kana_text" else KanjiText
    for row in rows:
        if table == "kana_text":
            obj = KanaText(
                id=row['id'],
                seq=row['seq'],
                text=row['text'],
                ord=row.get('ord', 0) if hasattr(row, 'get') else row['ord'],
                common=row['common'],
                common_tags='',
                conjugate_p=True,
                nokanji=row.get('nokanji', False) if hasattr(row, 'get') else False,
                conjugations=None,
                best_kanji=None,
            )
        else:
            obj = KanjiText(
                id=row['id'],
                seq=row['seq'],
                text=row['text'],
                ord=row.get('ord', 0) if hasattr(row, 'get') else row['ord'],
                common=row['common'],
                common_tags='',
                conjugate_p=True,
                nokanji=False,
                conjugations=None,
                best_kana=None,
            )
        result.append(obj)
    
    return result


def _find_word_with_conj_type(word: str, *conj_types: int):
    """
    Find words that are conjugations of the given types.
    
    Matches Ichiran's find-word-with-conj-type which uses find-word-full.
    This enables recursive suffix matching - e.g., 勉強して can be found
    as a compound (勉強 + して) with te-form conjugation.
    
    Uses module-level _suffix_map_temp and _suffix_next_end for recursive matching.
    """
    from himotoki.dict import find_word_full, ConjugatedText, CompoundText
    
    global _suffix_map_temp, _suffix_next_end
    
    results = []
    seen_seqs = set()
    
    # Call find_word_full with suffix context to enable recursive suffix matching
    # This is the key to matching compound forms like 勉強して
    words = find_word_full(word, as_hiragana_flag=False, counter=None,
                          suffix_map=_suffix_map_temp,
                          suffix_next_end=_suffix_next_end)
    
    for w in words:
        # Handle CompoundText - check if the suffix part has the conjugation type
        if isinstance(w, CompoundText):
            # For compounds, check the suffix word's conjugation
            # The suffix (e.g., して) should have the conjugation type
            if w.words and len(w.words) > 1:
                suffix_word = w.words[-1]  # Last word is the suffix
                suffix_conj = getattr(suffix_word, 'conjugations', None)
                
                # Check if suffix conjugations indicate the right conj_type
                if suffix_conj:
                    # Get conj_type for the suffix
                    if isinstance(suffix_conj, list):
                        for conj_id in suffix_conj:
                            conj_rows = query(
                                """
                                SELECT cp.conj_type
                                FROM conj_prop cp
                                WHERE cp.conj_id = ?
                                """,
                                (conj_id,)
                            )
                            for row in conj_rows:
                                if row['conj_type'] in conj_types:
                                    seq_key = tuple(w.seq) if isinstance(w.seq, list) else w.seq
                                    if seq_key not in seen_seqs:
                                        seen_seqs.add(seq_key)
                                        results.append({
                                            'word': w,
                                            'conj_type': row['conj_type'],
                                            'from_seq': w.primary.seq if w.primary else None,
                                        })
                                    break
            continue
        
        # Handle regular words
        seq = w.seq
        if seq in seen_seqs:
            continue
            
        # Check if this word has the given conjugation types
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
                seen_seqs.add(seq)
                results.append({
                    'word': w,
                    'conj_type': row['conj_type'],
                    'from_seq': row['from_seq'],
                })
                break
    
    # Also look for ConjugatedText entries in conj_lookup
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
        seq = row['seq']
        if seq in seen_seqs:
            continue
        seen_seqs.add(seq)
        
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
        
        # FILTER: Reject partial suru-verb matches
        # Suru-verb conjugations should have text starting with source_reading
        # E.g., なくて should NOT match なま返事する (source_reading = なまへんじ)
        # because なまへんじしなくて != なくて
        # BUT: Exempt standalone する (seq 1157170) and other base verbs
        if pos in ('vs-i', 'vs-s') and source_reading:
            # Exempt standalone する, いたす, される, させる (base suru-verbs)
            base_suru_seqs = {1157170, 1421900, 2269820, 1005160}
            if seq not in base_suru_seqs:
                text_hira = as_hiragana(row['text'])
                source_hira = as_hiragana(source_reading)
                if source_hira and not text_hira.startswith(source_hira):
                    continue  # Skip this partial match
        
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


def suffix_suru(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle suru suffix (noun + する makes verb).
    
    Matches Ichiran's suffix-suru: finds words with "vs" POS (suru verbs).
    Example: 勉強 + しています = 勉強しています
    """
    matches = _find_word_with_pos(root, "vs")
    results = []
    
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    suffix_class = _suffix_class.get(kf['seq']) if kf else 'suru'
    
    for word in matches:
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=5,  # :score 5 in Ichiran
            suffix_class=suffix_class,
        )
        results.append(compound)
    
    return results


def suffix_tai(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle tai suffix (want to do).
    
    Matches Ichiran's suffix-tai: conj_type 13 (masu stem).
    Excludes い as root.
    """
    if root == 'い':
        return []
    
    matches = _find_word_with_conj_type(root, 13)  # Ren'youkei/masu stem
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
            score_mod=5,
            suffix_class='tai',
        )
        results.append(compound)
    
    return results


def suffix_ren(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle ren suffix (generic ren'youkei/masu stem suffix).
    
    Matches Ichiran's suffix-ren: conj_type 13.
    """
    matches = _find_word_with_conj_type(root, 13)
    results = []
    
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    suffix_class = _suffix_class.get(kf['seq']) if kf else 'ren'
    
    for m in matches:
        word = m['word']
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=5,
            suffix_class=suffix_class,
        )
        results.append(compound)
    
    return results


def suffix_ren_minus(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle ren- suffix (ren'youkei with score 0).
    
    Matches Ichiran's suffix-ren-: conj_type 13 with score 0.
    """
    matches = _find_word_with_conj_type(root, 13)
    results = []
    
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    suffix_class = _suffix_class.get(kf['seq']) if kf else None
    
    for m in matches:
        word = m['word']
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


# Conjugation constants (from Ichiran)
CONJ_NEGATIVE_STEM = 25  # +conj-negative-stem+
CONJ_ADJECTIVE_STEM = 26  # +conj-adjective-stem+
CONJ_ADVERBIAL = 2  # +conj-adverbial+


def suffix_neg(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle neg suffix (negative stem).
    
    Matches Ichiran's suffix-neg: conj_type 13 with CONJ_NEGATIVE_STEM.
    """
    # Find words with conj_type 13 and negative property
    matches = _find_word_with_conj_type(root, 13)
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
            score_mod=5,
            suffix_class='neg',
        )
        results.append(compound)
    
    return results


def suffix_te_space(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle te+space suffix (te-form + auxiliary with space connector).
    
    Matches Ichiran's suffix-te+space.
    """
    if not _te_check(root):
        return []
    
    matches = _find_word_with_conj_type(root, 3)
    results = []
    
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    suffix_class = _suffix_class.get(kf['seq']) if kf else None
    
    for m in matches:
        word = m['word']
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=3,
            suffix_class=suffix_class,
        )
        results.append(compound)
    
    return results


def suffix_kudasai(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle kudasai suffix (please do...).
    
    Matches Ichiran's suffix-kudasai: te-form check with constant score 360.
    """
    if not _te_check(root):
        return []
    
    matches = _find_word_with_conj_type(root, 3)
    results = []
    
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    for m in matches:
        word = m['word']
        # Score is (constantly 360) in Ichiran - high fixed score
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=360,
            suffix_class='kudasai',
        )
        results.append(compound)
    
    return results


def suffix_teren(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle teren suffix (te or ren'youkei).
    
    Matches Ichiran's suffix-te-ren.
    """
    if root == 'で':
        return []
    
    results = []
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    suffix_class = _suffix_class.get(kf['seq']) if kf else None
    
    # Check te-form
    if root and root[-1] in 'てで':
        matches = _find_word_with_conj_type(root, 3)
        for m in matches:
            word = m['word']
            compound = adjoin_word(
                word,
                suffix_word,
                text=root + suffix_text,
                kana=word.get_kana() + suffix_text,
                score_mod=4,
                suffix_class=suffix_class,
            )
            results.append(compound)
    elif root != 'い':
        # Try ren'youkei
        matches = _find_word_with_conj_type(root, 13)
        for m in matches:
            word = m['word']
            compound = adjoin_word(
                word,
                suffix_word,
                text=root + suffix_text,
                kana=word.get_kana() + suffix_text,
                score_mod=4,
                suffix_class=suffix_class,
            )
            results.append(compound)
    
    return results


def suffix_teii(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle teii suffix (te-form + いい - it's ok if...).
    
    Matches Ichiran's suffix-teii.
    """
    if not root or root[-1] not in 'てで':
        return []
    
    matches = _find_word_with_conj_type(root, 3)
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
            score_mod=1,
            suffix_class='ii',
        )
        results.append(compound)
    
    return results


def suffix_chau(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle chau suffix (completion - ちゃう/ちまう).
    
    Matches Ichiran's suffix-chau: stem 1, needs to reconstruct te-form.
    """
    if not suffix_text:
        return []
    
    # Determine te-form ending based on suffix start
    first_char = suffix_text[0]
    if first_char == 'じ':  # ぢ→じ
        te = 'で'
    elif first_char == 'ち':
        te = 'て'
    else:
        return []
    
    te_root = root + te
    matches = _find_word_with_conj_type(te_root, 3)
    results = []
    
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    suffix_class = _suffix_class.get(kf['seq']) if kf else 'chau'
    
    for m in matches:
        word = m['word']
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana()[:-1] + suffix_text if word.get_kana().endswith(te[-1]) else word.get_kana() + suffix_text,
            score_mod=5,
            suffix_class=suffix_class,
        )
        results.append(compound)
    
    return results


def suffix_to(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle to suffix (とく - ておく contraction).
    
    Matches Ichiran's suffix-to: stem 1, needs to reconstruct te-form.
    """
    if not suffix_text:
        return []
    
    first_char = suffix_text[0]
    if first_char == 'と':
        te = 'て'
    elif first_char == 'ど':
        te = 'で'
    else:
        return []
    
    te_root = root + te
    matches = _find_word_with_conj_type(te_root, 3)
    results = []
    
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    suffix_class = _suffix_class.get(kf['seq']) if kf else 'oku'
    
    for m in matches:
        word = m['word']
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


def suffix_sou(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle sou suffix (seeming - そう).
    
    Matches Ichiran's suffix-sou.
    """
    # Special score based on root
    if root == 'から':
        score = 40
    elif root == 'い':
        score = 0
    elif root == '出来':
        score = 100
    else:
        score = 60
    
    # Check for なさ ending (negative stem)
    if root.endswith('なさ'):
        # Negative stem → find negative form
        patched_root = root[:-1] + 'い'  # なさ → ない
        # TODO: implement negative stem matching
        return []
    elif root in ('な', 'よ', 'よさ', 'に', 'き'):
        return []
    else:
        # Look for adjective stem or ren'youkei
        matches = _find_word_with_conj_type(root, 13, CONJ_ADJECTIVE_STEM, CONJ_ADVERBIAL)
    
    results = []
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    for m in matches:
        word = m['word']
        # Check if the base word is uncommon - if so, reduce score
        # This prevents uncommon conjugations from beating common standalone words
        word_common = getattr(word, 'common', None)
        if word_common is None:
            # Uncommon base word - significantly reduce score
            # This prevents なぜそう (from 撫ぜる) from beating なぜ + そう
            actual_score = max(1, score // 10)
        else:
            actual_score = score
            
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=actual_score,
            suffix_class='sou',
        )
        results.append(compound)
    
    return results


def suffix_sou_plus(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle sou+ suffix (そうにない).
    
    Matches Ichiran's suffix-sou+.
    """
    if root.endswith('なさ'):
        return []
    elif root in ('な', 'よ', 'よさ', 'に', 'き'):
        return []
    
    matches = _find_word_with_conj_type(root, 13, CONJ_ADJECTIVE_STEM, CONJ_ADVERBIAL)
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
            score_mod=1,
            suffix_class='sou',
        )
        results.append(compound)
    
    return results


def suffix_rou(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle rou suffix (probably/volitional - ろう).
    
    Matches Ichiran's suffix-rou: conj_type 2 (terminal).
    """
    matches = _find_word_with_conj_type(root, 2)
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
            score_mod=1,
            suffix_class='rou',
        )
        results.append(compound)
    
    return results


def suffix_adv(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle adv suffix (adverbial form + なる etc).
    
    Matches Ichiran's suffix-adv: conj_type +conj-adverbial+ (2).
    """
    matches = _find_word_with_conj_type(root, CONJ_ADVERBIAL)
    results = []
    
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    suffix_class = _suffix_class.get(kf['seq']) if kf else 'naru'
    
    for m in matches:
        word = m['word']
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=1,
            suffix_class=suffix_class,
        )
        results.append(compound)
    
    return results


def suffix_sugiru(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle sugiru suffix (too much - すぎる).
    
    Matches Ichiran's suffix-sugiru.
    """
    if root == 'い':
        return []
    
    # Check for なさ/無さ ending (negative stem)
    if root.endswith('なさ') or root.endswith('無さ'):
        # Negative stem → find negative form
        return []  # TODO: implement negative stem matching
    
    # Add い to root to form adjective
    adj_root = root + 'い'
    matches = _find_word_with_pos(adj_root, "adj-i")
    results = []
    
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    for word in matches:
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana()[:-1] + suffix_text,  # Remove い from kana
            score_mod=5,
            suffix_class='sugiru',
        )
        results.append(compound)
    
    return results


def suffix_sa(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle sa suffix (adjective nominalization - さ).
    
    Matches Ichiran's suffix-sa.
    """
    results = []
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    # Try adjective stem
    matches = _find_word_with_conj_type(root, CONJ_ADJECTIVE_STEM)
    for m in matches:
        word = m['word']
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=2,
            suffix_class='sa',
        )
        results.append(compound)
    
    # Also try na-adjectives
    na_matches = _find_word_with_pos(root, "adj-na")
    for word in na_matches:
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=2,
            suffix_class='sa',
        )
        results.append(compound)
    
    return results


def suffix_iadj(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle iadj suffix (i-adjective stem + suffix like げ, め).
    
    Matches Ichiran's suffix-iadj.
    """
    matches = _find_word_with_conj_type(root, CONJ_ADJECTIVE_STEM)
    results = []
    
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    suffix_class = _suffix_class.get(kf['seq']) if kf else None
    
    for m in matches:
        word = m['word']
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=1,
            suffix_class=suffix_class,
        )
        results.append(compound)
    
    return results


def suffix_garu(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle garu suffix (to feel - がる).
    
    Matches Ichiran's suffix-garu.
    """
    if root in ('な', 'い', 'よ'):
        return []
    
    results = []
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    # Try adjective stem
    matches = _find_word_with_conj_type(root, CONJ_ADJECTIVE_STEM)
    for m in matches:
        word = m['word']
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=0,
            suffix_class='garu',
        )
        results.append(compound)
    
    # Check for そ ending (sou form)
    if root.endswith('そ'):
        # TODO: find-word-with-suffix for :sou
        pass
    
    return results


def suffix_rashii(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle rashii suffix (seems like - らしい).
    
    Matches Ichiran's suffix-rashii.
    """
    results = []
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    # conj_type 2 (terminal)
    matches = _find_word_with_conj_type(root, 2)
    for m in matches:
        word = m['word']
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=3,
            suffix_class='rashii',
        )
        results.append(compound)
    
    # Also check root + ら with conj_type 11
    ra_root = root + 'ら'
    ra_matches = _find_word_with_conj_type(ra_root, 11)
    for m in ra_matches:
        word = m['word']
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=3,
            suffix_class='rashii',
        )
        results.append(compound)
    
    return results


def suffix_desu(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle desu suffix (formal copula after negative forms).
    
    Matches Ichiran's suffix-desu.
    """
    # Only applies to ない/なかった endings
    if not (root.endswith('ない') or root.endswith('なかった')):
        return []
    
    # TODO: find negative conjugation prop matches
    # For now, simple check
    results = []
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    # Score is (constantly 200)
    from himotoki.dict import find_word
    for word in find_word(root):
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=200,
            suffix_class='desu',
        )
        results.append(compound)
    
    return results


def suffix_desho(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle desho suffix (seems/perhaps).
    
    Matches Ichiran's suffix-desho.
    """
    if not root.endswith('ない'):
        return []
    
    results = []
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    # Score is (constantly 300)
    from himotoki.dict import find_word
    for word in find_word(root):
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=300,
            suffix_class='desho',
        )
        results.append(compound)
    
    return results


def suffix_tosuru(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle tosuru suffix (try to/about to - とする).
    
    Matches Ichiran's suffix-tosuru: conj_type 9 (conditional).
    """
    matches = _find_word_with_conj_type(root, 9)
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
            suffix_class='tosuru',
        )
        results.append(compound)
    
    return results


def suffix_kurai(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle kurai suffix (about/approximately - くらい/ぐらい).
    
    Matches Ichiran's suffix-kurai: conj_type 2 (terminal).
    """
    matches = _find_word_with_conj_type(root, 2)
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
            suffix_class='kurai',
        )
        results.append(compound)
    
    return results


def suffix_ra(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle ra suffix (plural marker - ら).
    
    Matches Ichiran's suffix-ra.
    """
    if root.endswith('ら'):
        return []
    
    results = []
    suffix_word = _kf_to_kana_text(kf)
    if suffix_word is None:
        return []
    
    # Try pronouns (pn)
    matches = _find_word_with_pos(root, "pn")
    
    # Also check hiragana version
    hiragana_root = as_hiragana(root)
    if hiragana_root != root:
        matches.extend(_find_word_with_pos(hiragana_root, "pn"))
    
    for word in matches:
        compound = adjoin_word(
            word,
            suffix_word,
            text=root + suffix_text,
            kana=word.get_kana() + suffix_text,
            score_mod=1,
            suffix_class='ra',
        )
        results.append(compound)
    
    return results


def suffix_kotogadekiru(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle ことができる as a standalone grammar pattern.
    
    Unlike other suffixes, this creates a standalone word for ことができる
    rather than attaching to a preceding verb.
    
    Example: ことができる, ことができず, etc.
    """
    # This pattern should only match when the root is empty or trivial
    # The suffix itself (ことができる) IS the word we want
    if root:  
        # If there's a root, we don't want to attach - just return empty
        # This prevents creating compounds like 泳ぐことができる
        return []
    
    # Should not reach here - suffix handlers are called with non-empty roots
    return []


def suffix_kotonisuru(root: str, suffix_text: str, kf: Optional[dict]) -> List:
    """
    Handle ことにする as a standalone grammar pattern.
    
    Unlike other suffixes, this creates a standalone word for ことにする
    rather than attaching to a preceding verb.
    
    Example: ことにする, ことにしました, etc.
    """
    # This pattern should only match when the root is empty or trivial
    if root:  
        return []
    
    return []


# Register handlers
_suffix_handlers['te'] = suffix_te
_suffix_handlers['teiru'] = suffix_teiru
_suffix_handlers['teiru+'] = suffix_teiru_plus
_suffix_handlers['suru'] = suffix_suru
_suffix_handlers['tai'] = suffix_tai
_suffix_handlers['ren'] = suffix_ren
_suffix_handlers['ren-'] = suffix_ren_minus
_suffix_handlers['neg'] = suffix_neg
_suffix_handlers['te+space'] = suffix_te_space
_suffix_handlers['kudasai'] = suffix_kudasai
_suffix_handlers['teren'] = suffix_teren
_suffix_handlers['teii'] = suffix_teii
_suffix_handlers['chau'] = suffix_chau
_suffix_handlers['to'] = suffix_to
_suffix_handlers['sou'] = suffix_sou
_suffix_handlers['sou+'] = suffix_sou_plus
_suffix_handlers['rou'] = suffix_rou
_suffix_handlers['adv'] = suffix_adv
_suffix_handlers['sugiru'] = suffix_sugiru
_suffix_handlers['sa'] = suffix_sa
_suffix_handlers['iadj'] = suffix_iadj
_suffix_handlers['garu'] = suffix_garu
_suffix_handlers['rashii'] = suffix_rashii
_suffix_handlers['desu'] = suffix_desu
_suffix_handlers['desho'] = suffix_desho
_suffix_handlers['tosuru'] = suffix_tosuru
_suffix_handlers['kurai'] = suffix_kurai
_suffix_handlers['ra'] = suffix_ra
_suffix_handlers['kotogadekiru'] = suffix_kotogadekiru
_suffix_handlers['kotonisuru'] = suffix_kotonisuru


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
    global _suffix_map_temp, _suffix_next_end
    
    # Set context for recursive matching
    _suffix_map_temp = suffix_map
    
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
        
        # Update suffix_next_end for recursive matching (like Ichiran's let binding)
        old_suffix_next_end = _suffix_next_end
        if suffix_next_end is not None:
            _suffix_next_end = suffix_next_end - len(suffix_text)
        
        try:
            compounds = handler(root, suffix_text, kf)
            results.extend(compounds)
        finally:
            # Restore previous value
            _suffix_next_end = old_suffix_next_end
    
    return results
