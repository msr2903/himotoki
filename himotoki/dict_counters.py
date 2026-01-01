"""
Counter word handling for Himotoki.

Handles Japanese counter words and number+counter combinations.

Mirrors dict-counters.lisp from the original Ichiran.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from himotoki.numbers import (
    parse_number, number_to_kana, number_to_kanji,
    is_digit_kanji
)
from himotoki.characters import as_hiragana


# ============================================================================
# Counter Classes
# ============================================================================

@dataclass
class Counter:
    """Represents a Japanese counter word."""
    id: str
    reading: str  # Base reading in hiragana
    kanji: Optional[str] = None  # Kanji form if any
    ranges: Optional[Dict[int, str]] = None  # Special readings for numbers
    seq: Optional[int] = None  # Dictionary sequence number


# Built-in counter registry
COUNTER_CACHE: Dict[str, Counter] = {}


def register_counter(counter: Counter):
    """Register a counter in the cache."""
    COUNTER_CACHE[counter.id] = counter
    if counter.kanji:
        COUNTER_CACHE[counter.kanji] = counter
    COUNTER_CACHE[counter.reading] = counter


def get_counter(text: str) -> Optional[Counter]:
    """Get a counter by text (reading or kanji)."""
    return COUNTER_CACHE.get(text) or COUNTER_CACHE.get(as_hiragana(text))


# ============================================================================
# Phonetic Changes
# ============================================================================

# Counters that cause phonetic changes
COUNTER_PHONETIC_CHANGES = {
    # k-row counters (っ + counter)
    'かい': {'1': 'いっかい', '6': 'ろっかい', '8': 'はっかい', '10': 'じゅっかい'},
    'こ': {'1': 'いっこ', '6': 'ろっこ', '8': 'はっこ', '10': 'じゅっこ'},
    'けん': {'1': 'いっけん', '6': 'ろっけん', '8': 'はっけん', '10': 'じゅっけん'},
    'かげつ': {'1': 'いっかげつ', '6': 'ろっかげつ', '8': 'はっかげつ', '10': 'じゅっかげつ'},
    
    # s-row counters
    'さい': {'1': 'いっさい', '8': 'はっさい', '10': 'じゅっさい'},
    'せんち': {'1': 'いっせんち', '8': 'はっせんち'},
    
    # t-row counters
    'つう': {'1': 'いっつう', '8': 'はっつう', '10': 'じゅっつう'},
    
    # p-row counters
    'ぽん': {'1': 'いっぽん', '3': 'さんぼん', '6': 'ろっぽん', '8': 'はっぽん', '10': 'じゅっぽん'},
    'ぴき': {'1': 'いっぴき', '3': 'さんびき', '6': 'ろっぴき', '8': 'はっぴき', '10': 'じゅっぴき'},
    'ぷん': {'1': 'いっぷん', '3': 'さんぷん', '4': 'よんぷん', '6': 'ろっぷん', '8': 'はっぷん', '10': 'じゅっぷん'},
    'ぺん': {'1': 'いっぺん', '3': 'さんべん', '6': 'ろっぺん', '8': 'はっぺん', '10': 'じゅっぺん'},
    'ぺーじ': {'1': 'いっぺーじ', '6': 'ろっぺーじ', '8': 'はっぺーじ', '10': 'じゅっぺーじ'},
    
    # h-row counters (b/p alternation)
    'ほん': {'1': 'いっぽん', '3': 'さんぼん', '6': 'ろっぽん', '8': 'はっぽん', '10': 'じゅっぽん'},
    'ひき': {'1': 'いっぴき', '3': 'さんびき', '6': 'ろっぴき', '8': 'はっぴき', '10': 'じゅっぴき'},
    'はい': {'1': 'いっぱい', '3': 'さんばい', '6': 'ろっぱい', '8': 'はっぱい', '10': 'じゅっぱい'},
    
    # Other counters
    'にん': {'1': 'ひとり', '2': 'ふたり', '4': 'よにん', '7': 'しちにん'},
    'つき': {'1': 'ひとつき', '2': 'ふたつき'},
    'ひ': {'1': 'いちにち', '2': 'ふつか', '3': 'みっか', '4': 'よっか', '5': 'いつか',
           '6': 'むいか', '7': 'なのか', '8': 'ようか', '9': 'ここのか', '10': 'とおか',
           '20': 'はつか'},
}

# Native number readings (hitotsu, futatsu, etc.)
NATIVE_COUNTERS = {
    'つ': {
        '1': 'ひとつ',
        '2': 'ふたつ',
        '3': 'みっつ',
        '4': 'よっつ',
        '5': 'いつつ',
        '6': 'むっつ',
        '7': 'ななつ',
        '8': 'やっつ',
        '9': 'ここのつ',
        '10': 'とお',
    }
}


# ============================================================================
# Counter Reading Generation
# ============================================================================

def counter_reading(number: int, counter: str) -> str:
    """
    Generate the reading for a number+counter combination.
    
    Args:
        number: The number.
        counter: Counter reading in hiragana.
        
    Returns:
        Combined reading.
    """
    counter_hira = as_hiragana(counter)
    
    # Check for special readings
    if counter_hira in NATIVE_COUNTERS:
        special = NATIVE_COUNTERS[counter_hira].get(str(number))
        if special:
            return special
    
    if counter_hira in COUNTER_PHONETIC_CHANGES:
        special = COUNTER_PHONETIC_CHANGES[counter_hira].get(str(number))
        if special:
            return special
    
    # Default: number reading + counter
    num_reading = number_to_kana(number)
    return num_reading + counter


def counter_text(number: int, counter_kanji: str, counter_reading: str) -> str:
    """
    Generate the text for a number+counter combination.
    
    Args:
        number: The number.
        counter_kanji: Counter in kanji.
        counter_reading: Counter reading.
        
    Returns:
        Combined text.
    """
    # Special cases for native counters
    if counter_reading in NATIVE_COUNTERS:
        special = NATIVE_COUNTERS[counter_reading].get(str(number))
        if special:
            return special
    
    # Default: numeral + counter
    return number_to_kanji(number) + counter_kanji


# ============================================================================
# Counter Detection
# ============================================================================

def detect_counter(text: str) -> Optional[Tuple[int, str, str]]:
    """
    Detect if text is a number+counter combination.
    
    Args:
        text: Text to analyze.
        
    Returns:
        Tuple of (number, counter_text, counter_reading) if detected.
    """
    if not text:
        return None
    
    # Try to find a number prefix
    num_end = 0
    for i, char in enumerate(text):
        if is_digit_kanji(char) or char.isdigit():
            num_end = i + 1
        else:
            break
    
    if num_end == 0:
        return None
    
    num_text = text[:num_end]
    counter_text = text[num_end:]
    
    if not counter_text:
        return None
    
    # Parse the number
    num_value = parse_number(num_text)
    if num_value is None:
        return None
    
    # Get counter reading
    counter = get_counter(counter_text)
    if counter:
        reading = counter_reading(num_value, counter.reading)
        return (num_value, counter_text, reading)
    
    # Unknown counter - just use hiragana
    counter_hira = as_hiragana(counter_text)
    reading = counter_reading(num_value, counter_hira)
    return (num_value, counter_text, reading)


# ============================================================================
# Common Counters
# ============================================================================

def init_counters():
    """Initialize common Japanese counters."""
    counters = [
        # Generic
        Counter('つ', 'つ'),
        
        # People
        Counter('にん', 'にん', '人'),
        Counter('めい', 'めい', '名'),
        
        # Long thin objects
        Counter('ほん', 'ほん', '本'),
        
        # Small animals
        Counter('ひき', 'ひき', '匹'),
        
        # Large animals, fish
        Counter('とう', 'とう', '頭'),
        
        # Birds, rabbits
        Counter('わ', 'わ', '羽'),
        
        # Flat objects
        Counter('まい', 'まい', '枚'),
        
        # Small objects
        Counter('こ', 'こ', '個'),
        
        # Bound objects (books)
        Counter('さつ', 'さつ', '冊'),
        
        # Machines, vehicles
        Counter('だい', 'だい', '台'),
        
        # Floors, levels
        Counter('かい', 'かい', '階'),
        
        # Times, occurrences
        Counter('かい', 'かい', '回'),
        Counter('ど', 'ど', '度'),
        
        # Pairs
        Counter('そく', 'そく', '足'),  # Pairs of shoes/socks
        Counter('つい', 'つい', '対'),  # Pairs
        
        # Time
        Counter('じ', 'じ', '時'),
        Counter('じかん', 'じかん', '時間'),
        Counter('ふん', 'ふん', '分'),
        Counter('びょう', 'びょう', '秒'),
        Counter('にち', 'にち', '日'),
        Counter('がつ', 'がつ', '月'),
        Counter('かげつ', 'かげつ', 'ヶ月'),
        Counter('ねん', 'ねん', '年'),
        Counter('しゅうかん', 'しゅうかん', '週間'),
        
        # Age
        Counter('さい', 'さい', '歳'),
        
        # Size/amount
        Counter('メートル', 'めーとる', 'メートル'),
        Counter('センチ', 'せんち', 'センチ'),
        Counter('キロ', 'きろ', 'キロ'),
        Counter('グラム', 'ぐらむ', 'グラム'),
        Counter('リットル', 'りっとる', 'リットル'),
        
        # Currency
        Counter('えん', 'えん', '円'),
        Counter('ドル', 'どる', 'ドル'),
        
        # Drinks
        Counter('はい', 'はい', '杯'),
        
        # Slices, portions
        Counter('きれ', 'きれ', '切れ'),
        
        # Lessons, chapters
        Counter('か', 'か', '課'),
        Counter('しょう', 'しょう', '章'),
        
        # Pages
        Counter('ぺーじ', 'ぺーじ', 'ページ'),
        
        # Companies
        Counter('しゃ', 'しゃ', '社'),
        
        # Houses, buildings
        Counter('けん', 'けん', '軒'),
        
        # Letters, passages
        Counter('つう', 'つう', '通'),
    ]
    
    for counter in counters:
        register_counter(counter)


# Initialize on module load
init_counters()
