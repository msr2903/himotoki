"""
Counter word recognition module for himotoki.
Ports ichiran's dict-counters.lisp counter functionality.

Counter expressions combine a number with a counter suffix to form compound words.
Examples:
- 三匹 (sanbiki) = 三 (san, three) + 匹 (hiki, counter for small animals)
- 五冊 (gosatsu) = 五 (go, five) + 冊 (satsu, counter for books)
- 千人 (sennin) = 千 (sen, thousand) + 人 (nin, counter for people)

This module dynamically generates counter expressions and provides scoring.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any, Set, Union
from functools import lru_cache

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from himotoki.db.models import (
    Entry, KanjiText, KanaText, SenseProp,
)
from himotoki.characters import (
    get_char_class, mora_length, as_hiragana, count_char_class,
)


# ============================================================================
# Japanese Number Parsing
# ============================================================================

# Number kanji to value mapping
KANJI_NUMBERS = {
    '零': 0, '〇': 0,
    '一': 1, '壱': 1,
    '二': 2, '弐': 2,
    '三': 3, '参': 3,
    '四': 4,
    '五': 5,
    '六': 6,
    '七': 7,
    '八': 8,
    '九': 9,
    '十': 10,
    '百': 100,
    '千': 1000,
    '万': 10000,
    '億': 100000000,
}

# Arabic digit to value
DIGIT_VALUES = {
    '0': 0, '１': 0, '０': 0,
    '1': 1, '１': 1,
    '2': 2, '２': 2,
    '3': 3, '３': 3,
    '4': 4, '４': 4,
    '5': 5, '５': 5,
    '6': 6, '６': 6,
    '7': 7, '７': 7,
    '8': 8, '８': 8,
    '9': 9, '９': 9,
}

# Number kana to digit
DIGIT_TO_KANA = {
    1: 'いち',
    2: 'に',
    3: 'さん',
    4: 'よん',  # or し
    5: 'ご',
    6: 'ろく',
    7: 'なな',  # or しち
    8: 'はち',
    9: 'きゅう',  # or く
    10: 'じゅう',
    100: 'ひゃく',
    1000: 'せん',
    10000: 'まん',
}

# Power values to kana
POWER_TO_KANA = {
    1: 'じゅう',  # 10
    2: 'ひゃく',  # 100
    3: 'せん',    # 1000
    4: 'まん',    # 10000
}


def parse_number(text: str) -> Optional[int]:
    """
    Parse a Japanese number string into an integer.
    
    Supports:
    - Arabic numerals (1, 2, 3 or １, ２, ３)
    - Kanji numerals (一, 二, 三)
    - Mixed (十二, 百三十四)
    
    Returns None if the text is not a valid number.
    """
    if not text:
        return None
    
    # Try Arabic numerals first
    arabic_str = ''
    for char in text:
        if char in DIGIT_VALUES:
            arabic_str += str(DIGIT_VALUES[char])
        elif char.isdigit():
            arabic_str += char
        else:
            break
    
    if arabic_str and len(arabic_str) == len(text):
        return int(arabic_str)
    
    # Try kanji numerals
    return parse_kanji_number(text)


def parse_kanji_number(text: str) -> Optional[int]:
    """Parse a kanji number string into an integer."""
    if not text:
        return None
    
    result = 0
    current = 0
    
    for char in text:
        if char not in KANJI_NUMBERS:
            return None
        
        value = KANJI_NUMBERS[char]
        
        if value >= 10:
            # Multiplier (十, 百, 千, 万, 億)
            if current == 0:
                current = 1
            
            if value >= 10000:
                # 万 or higher - adds to result
                result += current * value
                current = 0
            else:
                # 十, 百, 千 - multiplies current
                current *= value
                result += current
                current = 0
        else:
            # Digit
            if current > 0:
                result += current
            current = value
    
    # Add any remaining current
    result += current
    
    return result if result > 0 or text == '零' or text == '〇' else None


def number_to_kana(n: int, separator: str = '') -> str:
    """Convert a number to its kana reading."""
    if n == 0:
        return 'ゼロ'
    
    parts = []
    
    # Handle 10000s
    if n >= 10000:
        man = n // 10000
        if man > 1:
            parts.append(number_to_kana(man))
        parts.append('まん')
        n %= 10000
    
    # Handle 1000s
    if n >= 1000:
        sen = n // 1000
        if sen == 3:
            parts.append('さん')
        elif sen > 1:
            parts.append(DIGIT_TO_KANA.get(sen, ''))
        parts.append('せん')
        n %= 1000
    
    # Handle 100s
    if n >= 100:
        hyaku = n // 100
        if hyaku == 3:
            parts.append('さん')
            parts.append('びゃく')  # 300 = sanbyaku
        elif hyaku == 6:
            parts.append('ろっ')
            parts.append('ぴゃく')  # 600 = roppyaku
        elif hyaku == 8:
            parts.append('はっ')
            parts.append('ぴゃく')  # 800 = happyaku
        else:
            if hyaku > 1:
                parts.append(DIGIT_TO_KANA.get(hyaku, ''))
            parts.append('ひゃく')
        n %= 100
    
    # Handle 10s
    if n >= 10:
        juu = n // 10
        if juu > 1:
            parts.append(DIGIT_TO_KANA.get(juu, ''))
        parts.append('じゅう')
        n %= 10
    
    # Handle 1s
    if n > 0:
        parts.append(DIGIT_TO_KANA.get(n, ''))
    
    return separator.join(parts)


# ============================================================================
# Counter Text Class
# ============================================================================

@dataclass
class CounterText:
    """
    Represents a counter expression (number + counter).
    
    Ports ichiran's counter-text class from dict-counters.lisp.
    
    CounterText objects are designed to be compatible with WordMatch
    so they can be scored using the main calc_score function.
    """
    text: str  # Full text (e.g., "三匹")
    kana: str  # Kana reading (e.g., "さんびき")
    number_text: str  # Number part (e.g., "三")
    number_value: int  # Numeric value (e.g., 3)
    counter_text: str  # Counter part (e.g., "匹")
    counter_kana: str  # Counter kana (e.g., "ひき")
    source: Optional[Union[KanjiText, KanaText]] = None  # Source counter entry
    ordinalp: bool = False  # Is this ordinal? (〜目)
    suffix: Optional[str] = None  # Kana suffix (e.g., "め" for 目)
    _common: Optional[int] = None  # Commonness rating (internal)
    digit_opts: Optional[Dict] = None  # Digit-specific options for phonetic rules
    
    @property
    def seq(self) -> Optional[int]:
        """Get the seq from the source counter."""
        return self.source.seq if self.source else None
    
    @property
    def ord(self) -> int:
        """Get the ord from the source counter."""
        return self.source.ord if self.source else 0
    
    @property
    def common(self) -> Optional[int]:
        """Get commonness rating from source or override."""
        if self._common is not None:
            return self._common
        if self.source:
            return self.source.common
        return 0
    
    @property
    def word_type(self) -> str:
        """Counter expressions are typically kanji."""
        # Check if text contains kanji
        if count_char_class(self.text, 'kanji') > 0:
            return 'kanji'
        return 'kana'
    
    @property
    def reading(self):
        """Return self as the reading for compatibility with calc_score."""
        return self
    
    @property
    def conjugations(self) -> None:
        """Counters don't have conjugations."""
        return None
    
    @property
    def is_root(self) -> bool:
        """Counters are always root forms."""
        return True
    
    @property
    def is_compound(self) -> bool:
        """Counters are not compound words."""
        return False
    
    @property
    def components(self) -> List[str]:
        """Return empty list for counters (no components)."""
        return []
    
    def __repr__(self):
        return f"<CounterText(text='{self.text}', value={self.number_value}, counter='{self.counter_text}')>"


# ============================================================================
# Counter Cache
# ============================================================================

# Cache for counter readings
_counter_cache: Dict[str, List[Tuple[type, Dict]]] = {}
_counter_cache_initialized = False

# Special counter handling overrides
# Maps seq to digit_opts dict for phonetic rules
# Format: {digit: [opts]} where opts can be 'g' (geminate), 'r' (rendaku), 'h' (handakuten)
# or a string to replace the number reading
SPECIAL_COUNTER_OPTS: Dict[int, Dict] = {
    # 匹/疋 (hiki) - counter for small animals
    1583370: {3: ['r']},  # 3 -> さんびき (rendaku)
    # 本 (hon) - counter for long thin objects
    1522150: {3: ['r']},  # 3 -> さんぼん (rendaku)
    # 杯/盃 (hai) - counter for cups/glasses
    2019640: {3: ['r']},  # 3 -> さんばい (rendaku)
    # 階 (kai) - counter for floors
    1203020: {3: ['r']},  # 3 -> さんがい (rendaku)
    # 軒 (ken) - counter for houses
    2078590: {3: ['r']},  # 3 -> さんげん (rendaku)
    # 遍 (hen) - counter for times
    2208060: {3: ['r']},  # 3 -> さんべん (rendaku)
    # 編/篇 (hen) - counter for literary works
    1511870: {3: ['r']},  # 3 -> さんべん (rendaku)
    # 足 (soku) - counter for pairs of footwear
    2412230: {3: ['r']},  # 3 -> さんぞく (rendaku)
    # 時 (ji) - counter for hours
    2020680: {4: 'よ', 7: 'しち', 9: 'く'},
    # 時間 (jikan) - counter for hours duration
    1315920: {4: 'よ', 9: 'く'},
    # 年 (nen) - counter for years
    2084840: {4: 'よ', 7: 'しち', 9: 'く'},
    # 円 (en) - counter for yen
    1175570: {4: 'よ'},
    # 分 (fun) - counter for minutes
    1502840: {4: ['h']},  # 4 -> よんぷん (handakuten)
    # 舗 (ho) - counter for shops
    1514050: {4: ['h']},
    # 敗 (hai) - counter for losses
    1901390: {4: ['h']},
    # 泊 (haku) - counter for nights stay
    1919550: {4: ['h']},
    # 筆 (hitsu) - counter for brush strokes
    1487770: {4: ['h']},
    # 冊 (satsu) - counter for books - uses standard rules
    # 人 (nin) - counter for people - special class
    2149890: {4: 'よ', 7: 'しち'},
    # 月 (gatsu) - counter for months
    1255430: {4: 'し', 7: 'しち', 9: 'く'},
}

# Special counter classes that need custom kana generation
# Maps seq to a function that returns the kana for a given number
SPECIAL_COUNTER_KANA: Dict[int, callable] = {}

# Days counter (日 ka) - kun readings for 1-10, 14, 20, 24, 30
DAYS_KUN_READINGS = {
    1: 'ついたち',
    2: 'ふつか',
    3: 'みっか',
    4: 'よっか',
    5: 'いつか',
    6: 'むいか',
    7: 'なのか',
    8: 'ようか',
    9: 'ここのか',
    10: 'とうか',
    14: 'じゅうよっか',
    20: 'はつか',
    24: 'にじゅうよっか',
    30: 'みそか',
}

# People counter (人 nin) - kun readings for 1-2
PEOPLE_KUN_READINGS = {
    1: 'ひとり',
    2: 'ふたり',
}

SPECIAL_COUNTERS: Dict[int, callable] = {}

# Extra counter IDs (not marked as ctr but act as counters)
# Note: 時 (2020680) is intentionally not included because it conflicts with
# regular dictionary entries like 三時 (3 o'clock)
EXTRA_COUNTER_IDS = [
    1255430,  # 月 (months)
    1606800,  # 割 (percentage)
]

# Skip these counter IDs
SKIP_COUNTER_IDS = [
    2426510,  # 一個当り
    2220370,  # 歳 (とせ)
    2248360,  # 入 (しお)
    2423450,  # 差し
    2671670,  # 幅 (の)
    2735690,  # 種 (くさ)
    2838543,  # 杯 (はた)
]

# Counters that accept certain suffixes
COUNTER_ACCEPTS = {
    1194480: ['kan'],  # 年
    1490430: ['kan'],  # 日
    1333450: ['kan', 'kango'],  # 週
}

# Foreign-style counters (different phonetic rules)
COUNTER_FOREIGN = [1120410]

# Counter suffixes (add to base counter)
COUNTER_SUFFIXES = {
    'kan': ('間', 'かん', '[duration]'),
    'kango': ('間後', 'かんご', '[after ...]'),
    'chuu': ('中', 'ちゅう', '[among/out of ...]'),
}


def get_counter_ids(session: Session) -> List[int]:
    """Get all seq IDs that are counters."""
    result = session.execute(
        select(SenseProp.seq)
        .where(and_(SenseProp.tag == 'pos', SenseProp.text == 'ctr'))
        .distinct()
    ).scalars().all()
    
    return sorted(set(result) | set(EXTRA_COUNTER_IDS) - set(SKIP_COUNTER_IDS))


def get_counter_readings(session: Session) -> Dict[int, Tuple[List[KanjiText], List[KanaText]]]:
    """
    Get kanji and kana readings for all counters.
    
    Returns dict mapping seq to (kanji_list, kana_list).
    """
    counter_ids = get_counter_ids(session)
    if not counter_ids:
        return {}
    
    result: Dict[int, Tuple[List[KanjiText], List[KanaText]]] = {}
    
    # Get kanji readings
    kanji_readings = session.execute(
        select(KanjiText).where(KanjiText.seq.in_(counter_ids))
    ).scalars().all()
    
    # Get kana readings
    kana_readings = session.execute(
        select(KanaText).where(KanaText.seq.in_(counter_ids))
    ).scalars().all()
    
    # Organize by seq
    for kt in kanji_readings:
        if kt.seq not in result:
            result[kt.seq] = ([], [])
        result[kt.seq][0].append(kt)
    
    for kt in kana_readings:
        if kt.seq not in result:
            result[kt.seq] = ([], [])
        result[kt.seq][1].append(kt)
    
    # Sort by ord
    for seq in result:
        result[seq] = (
            sorted(result[seq][0], key=lambda x: x.ord),
            sorted(result[seq][1], key=lambda x: x.ord)
        )
    
    return result


# ============================================================================
# Phonetic Rules (Gemination/Rendaku)
# ============================================================================

def geminate(kana: str) -> str:
    """
    Apply gemination (sokuon) to the end of a kana string.
    E.g., "いち" -> "いっ"
    """
    if not kana:
        return kana
    return kana[:-1] + 'っ'


def rendaku(kana: str, handakuten: bool = False) -> str:
    """
    Apply rendaku (voicing) or handakuten to the beginning of a kana string.
    E.g., "ひき" -> "びき" (rendaku) or "ぴき" (handakuten)
    """
    if not kana:
        return kana
    
    first_char = kana[0]
    rest = kana[1:]
    
    if handakuten:
        # h -> p
        h_to_p = {
            'は': 'ぱ', 'ひ': 'ぴ', 'ふ': 'ぷ', 'へ': 'ぺ', 'ほ': 'ぽ',
            'ハ': 'パ', 'ヒ': 'ピ', 'フ': 'プ', 'ヘ': 'ペ', 'ホ': 'ポ',
        }
        if first_char in h_to_p:
            return h_to_p[first_char] + rest
    else:
        # Voicing: k->g, s->z, t->d, h->b
        voicing = {
            'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
            'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
            'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
            'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
            'カ': 'ガ', 'キ': 'ギ', 'ク': 'グ', 'ケ': 'ゲ', 'コ': 'ゴ',
            'サ': 'ザ', 'シ': 'ジ', 'ス': 'ズ', 'セ': 'ゼ', 'ソ': 'ゾ',
            'タ': 'ダ', 'チ': 'ヂ', 'ツ': 'ヅ', 'テ': 'デ', 'ト': 'ド',
            'ハ': 'バ', 'ヒ': 'ビ', 'フ': 'ブ', 'ヘ': 'ベ', 'ホ': 'ボ',
        }
        if first_char in voicing:
            return voicing[first_char] + rest
    
    return kana


def get_kana_head_class(kana: str) -> Optional[str]:
    """Get the phonetic class of the first kana character."""
    if not kana:
        return None
    
    first = kana[0]
    
    # Group by consonant
    groups = {
        'ka': 'かきくけこカキクケコ',
        'sa': 'さしすせそサシスセソ',
        'ta': 'たちつてとタチツテト',
        'na': 'なにぬねのナニヌネノ',
        'ha': 'はひふへほハヒフヘホ',
        'ma': 'まみむめもマミムメモ',
        'ya': 'やゆよヤユヨ',
        'ra': 'らりるれろラリルレロ',
        'wa': 'わをんワヲン',
        'pa': 'ぱぴぷぺぽパピプペポ',
    }
    
    for group, chars in groups.items():
        if first in chars:
            return group
    
    return None


def counter_join(number_value: int, number_kana: str, counter_kana: str,
                 digit_opts: Optional[Dict] = None, foreign: bool = False) -> str:
    """
    Join number kana with counter kana, applying phonetic rules.
    
    Ports ichiran's counter-join method from dict-counters.lisp.
    
    Args:
        number_value: The numeric value
        number_kana: The kana reading of the number
        counter_kana: The kana reading of the counter
        digit_opts: Optional dict mapping digits to phonetic options
        foreign: Whether this is a foreign-style counter
    
    Returns:
        The combined kana string with phonetic rules applied
    """
    if digit_opts is None:
        digit_opts = {}
    
    # Get the relevant digit
    digit = number_value % 10
    if digit == 0:
        # For powers of 10
        for power in [10, 100, 1000, 10000]:
            if number_value % power == 0:
                if number_value % (power * 10) != 0:
                    digit = power
                    break
    
    head = get_kana_head_class(counter_kana)
    
    # Check for explicit digit options
    if digit in digit_opts:
        opts = digit_opts[digit]
        if isinstance(opts, str):
            # Replace number reading with the string
            # Get the stem length to replace
            if digit < 10:
                stem_kana = DIGIT_TO_KANA.get(digit, '')
            else:
                power = round(len(str(digit)) - 1)  # log10
                stem_kana = POWER_TO_KANA.get(power, '')
            
            stem_len = len(stem_kana) if stem_kana else 0
            if stem_len > 0 and len(number_kana) >= stem_len:
                return number_kana[:-stem_len] + opts + counter_kana
            return opts + counter_kana
        elif isinstance(opts, list):
            # Apply modifications
            result_number = number_kana
            result_counter = counter_kana
            for opt in opts:
                if opt == 'g':
                    result_number = geminate(result_number)
                elif opt == 'r':
                    result_counter = rendaku(result_counter)
                elif opt == 'h':
                    result_counter = rendaku(result_counter, handakuten=True)
            return result_number + result_counter
    
    # Apply standard rules based on digit and counter head
    result_number = number_kana
    result_counter = counter_kana
    
    if foreign:
        # Simplified foreign counter rules
        if digit in [6, 8, 10, 100] and head in ['ka', 'sa', 'ta', 'pa']:
            result_number = geminate(result_number)
    else:
        # Japanese counter rules
        if digit == 1:
            if head in ['ka', 'sa', 'ta']:
                result_number = geminate(result_number)
            elif head == 'ha':
                result_number = geminate(result_number)
                result_counter = rendaku(result_counter, handakuten=True)
        elif digit == 3:
            if head == 'ha':
                result_counter = rendaku(result_counter, handakuten=True)
        elif digit == 6:
            if head in ['ka', 'pa']:
                result_number = geminate(result_number)
            elif head == 'ha':
                result_number = geminate(result_number)
                result_counter = rendaku(result_counter, handakuten=True)
        elif digit == 8:
            if head in ['ka', 'sa', 'ta', 'pa']:
                result_number = geminate(result_number)
            elif head == 'ha':
                result_number = geminate(result_number)
                result_counter = rendaku(result_counter, handakuten=True)
        elif digit == 10:
            if head in ['ka', 'sa', 'ta', 'pa']:
                result_number = geminate(result_number)
            elif head == 'ha':
                result_number = geminate(result_number)
                result_counter = rendaku(result_counter, handakuten=True)
        elif digit == 100:
            if head == 'ka':
                result_number = geminate(result_number)
            elif head == 'ha':
                result_number = geminate(result_number)
                result_counter = rendaku(result_counter, handakuten=True)
        elif digit in [1000, 10000]:
            if head == 'ha':
                result_counter = rendaku(result_counter, handakuten=True)
    
    return result_number + result_counter


# ============================================================================
# Counter Lookup
# ============================================================================

# Special counter kana overrides
# Maps seq to the kana reading to use for the counter
SPECIAL_COUNTER_KANA_OVERRIDE: Dict[int, str] = {
    1255430: 'がつ',  # 月 (months) - uses がつ not つき
}

def init_counter_cache(session: Session) -> None:
    """Initialize the counter cache with all counter readings."""
    global _counter_cache, _counter_cache_initialized
    
    if _counter_cache_initialized:
        return
    
    _counter_cache = {}
    counter_readings = get_counter_readings(session)
    
    for seq, (kanji_list, kana_list) in counter_readings.items():
        if not kana_list:
            continue
        
        # Primary kana reading - check for override first
        if seq in SPECIAL_COUNTER_KANA_OVERRIDE:
            primary_kana = SPECIAL_COUNTER_KANA_OVERRIDE[seq]
        else:
            primary_kana = kana_list[0].text if kana_list else ''
        
        # Get digit_opts for this counter if it's a special counter
        digit_opts = SPECIAL_COUNTER_OPTS.get(seq)
        
        # Use kanji readings as counter text
        for kt in kanji_list:
            counter_text = kt.text
            is_ordinal = len(counter_text) > 1 and counter_text.endswith('目')
            
            # Add to cache
            if counter_text not in _counter_cache:
                _counter_cache[counter_text] = []
            
            _counter_cache[counter_text].append({
                'class': CounterText,
                'counter_text': counter_text,
                'counter_kana': primary_kana,
                'source': kt,
                'ordinalp': is_ordinal,
                'common': kt.common,
                'digit_opts': digit_opts,
            })
    
    _counter_cache_initialized = True


def find_counter(
    session: Session,
    number_text: str,
    counter_text: str,
    unique: bool = True,
) -> List[CounterText]:
    """
    Find counter expressions matching number + counter.
    
    Args:
        session: Database session
        number_text: Number part (e.g., "三")
        counter_text: Counter part (e.g., "匹")
        unique: If True, only return verified counters
    
    Returns:
        List of CounterText objects
    """
    init_counter_cache(session)
    
    # Parse the number
    number_value = parse_number(number_text)
    if number_value is None:
        return []
    
    # Look up the counter
    counter_args_list = _counter_cache.get(counter_text, [])
    if not counter_args_list:
        return []
    
    results = []
    for args in counter_args_list:
        source = args.get('source')
        seq = source.seq if source else None
        digit_opts = args.get('digit_opts')
        counter_kana = args['counter_kana']
        
        # Check for special kana readings
        special_kana = None
        common_override = args.get('common')
        
        # Days counter (日 ka) - seq 2083110
        # Only valid for 1-10, 14, 20, 24, 30
        if seq == 2083110:
            if number_value in DAYS_KUN_READINGS:
                special_kana = DAYS_KUN_READINGS[number_value]
                # Use source common value, don't override
            else:
                # Skip this counter for numbers without kun readings
                continue
        
        # Days counter (日 nichi) - seq 2083100
        # Valid for numbers > 10 (except 14, 20, 24, 30) and 1
        if seq == 2083100:
            if number_value in DAYS_KUN_READINGS and number_value != 1:
                # Skip nichi reading for numbers that have kun readings (except 1)
                continue
        
        # People counter (人 nin) - seq 2149890
        if seq == 2149890:
            if number_value in PEOPLE_KUN_READINGS:
                special_kana = PEOPLE_KUN_READINGS[number_value]
        
        # Generate the kana reading
        if special_kana:
            full_kana = special_kana
        else:
            number_kana = number_to_kana(number_value)
            # Apply phonetic rules with digit_opts
            full_kana = counter_join(number_value, number_kana, counter_kana, digit_opts=digit_opts)
        
        full_text = number_text + counter_text
        
        counter_obj = CounterText(
            text=full_text,
            kana=full_kana,
            number_text=number_text,
            number_value=number_value,
            counter_text=counter_text,
            counter_kana=counter_kana,
            source=source,
            ordinalp=args.get('ordinalp', False),
            _common=common_override,
            digit_opts=digit_opts,
        )
        
        results.append(counter_obj)
    
    return results


def find_counter_in_text(
    session: Session,
    text: str,
) -> List[Tuple[int, int, CounterText]]:
    """
    Find all counter expressions in a text.
    
    Returns list of (start, end, CounterText) tuples.
    """
    init_counter_cache(session)
    
    results = []
    text_len = len(text)
    
    for start in range(text_len):
        # Find number prefix
        number_end = start
        while number_end < text_len:
            char = text[number_end]
            if char in KANJI_NUMBERS or char in DIGIT_VALUES or char.isdigit():
                number_end += 1
            else:
                break
        
        if number_end == start:
            continue
        
        number_text = text[start:number_end]
        number_value = parse_number(number_text)
        if number_value is None:
            continue
        
        # Try to find matching counters
        for end in range(number_end + 1, min(text_len + 1, number_end + 5)):
            counter_text = text[number_end:end]
            counters = find_counter(session, number_text, counter_text)
            
            for counter in counters:
                results.append((start, end, counter))
    
    return results


# ============================================================================
# Counter Scoring
# ============================================================================

def calc_counter_score(counter: CounterText, use_length: Optional[int] = None) -> int:
    """
    Calculate score for a counter expression.
    
    Counter expressions get a base score of at least 5 (like kanji words).
    """
    # Base score similar to regular words
    score = 5  # Minimum like kanji words
    
    # Common counter bonus
    if counter.common is not None and counter.common == 0:
        score += 10
    elif counter.common is not None:
        score += max(15 - counter.common, 5)
    
    # Length bonus
    word_len = mora_length(counter.text)
    
    # Use strong length coefficients (like kanji)
    # strong: [0, 1, 8, 24, 40, 60]
    length_coeffs = [0, 1, 8, 24, 40, 60]
    if word_len < len(length_coeffs):
        coeff = length_coeffs[word_len]
    else:
        coeff = word_len * (length_coeffs[-1] // (len(length_coeffs) - 1))
    
    final_score = score * coeff
    
    return final_score
