"""
Character utilities for himotoki.
Ports ichiran's characters.lisp functionality.

Provides character class determination, kana conversion,
text normalization, and basic Japanese text splitting.
"""

import re
from typing import Optional, List, Tuple, Dict, Set
from functools import lru_cache


# ============================================================================
# Kana Character Mappings
# ============================================================================

# Sokuon (small tsu for gemination)
SOKUON_CHARS = "っッ"

# Iteration marks
ITERATION_CHARS = "ゝヽ"
ITERATION_VOICED_CHARS = "ゞヾ"

# Modifier characters (small kana, long vowel mark)
MODIFIER_CHARS = {
    '+a': "ぁァ", '+i': "ぃィ", '+u': "ぅゥ", '+e': "ぇェ", '+o': "ぉォ",
    '+ya': "ゃャ", '+yu': "ゅュ", '+yo': "ょョ", '+wa': "ゎヮ",
    'long_vowel': "ー"
}

# Main kana character mappings (hiragana, katakana pairs)
KANA_CHARS = {
    'a': "あア", 'i': "いイ", 'u': "うウ", 'e': "えエ", 'o': "おオ",
    'ka': "かカ", 'ki': "きキ", 'ku': "くク", 'ke': "けケ", 'ko': "こコ",
    'sa': "さサ", 'shi': "しシ", 'su': "すス", 'se': "せセ", 'so': "そソ",
    'ta': "たタ", 'chi': "ちチ", 'tsu': "つツ", 'te': "てテ", 'to': "とト",
    'na': "なナ", 'ni': "にニ", 'nu': "ぬヌ", 'ne': "ねネ", 'no': "のノ",
    'ha': "はハ", 'hi': "ひヒ", 'fu': "ふフ", 'he': "へヘ", 'ho': "ほホ",
    'ma': "まマ", 'mi': "みミ", 'mu': "むム", 'me': "めメ", 'mo': "もモ",
    'ya': "やヤ", 'yu': "ゆユ", 'yo': "よヨ",
    'ra': "らラ", 'ri': "りリ", 'ru': "るル", 're': "れレ", 'ro': "ろロ",
    'wa': "わワ", 'wi': "ゐヰ", 'we': "ゑヱ", 'wo': "をヲ",
    'n': "んン",
    # Voiced (dakuten)
    'ga': "がガ", 'gi': "ぎギ", 'gu': "ぐグ", 'ge': "げゲ", 'go': "ごゴ",
    'za': "ざザ", 'ji': "じジ", 'zu': "ずズ", 'ze': "ぜゼ", 'zo': "ぞゾ",
    'da': "だダ", 'dji': "ぢヂ", 'dzu': "づヅ", 'de': "でデ", 'do': "どド",
    'ba': "ばバ", 'bi': "びビ", 'bu': "ぶブ", 'be': "べベ", 'bo': "ぼボ",
    # Semi-voiced (handakuten)
    'pa': "ぱパ", 'pi': "ぴピ", 'pu': "ぷプ", 'pe': "ぺペ", 'po': "ぽポ",
    # Special
    'vu': "ゔヴ",
}

# Build reverse lookup: char -> class name
_CHAR_CLASS_MAP: Dict[str, str] = {}
for name, chars in KANA_CHARS.items():
    for char in chars:
        _CHAR_CLASS_MAP[char] = name
for name, chars in MODIFIER_CHARS.items():
    for char in chars:
        _CHAR_CLASS_MAP[char] = name
for char in SOKUON_CHARS:
    _CHAR_CLASS_MAP[char] = 'sokuon'
for char in ITERATION_CHARS:
    _CHAR_CLASS_MAP[char] = 'iter'
for char in ITERATION_VOICED_CHARS:
    _CHAR_CLASS_MAP[char] = 'iter_v'


# Voicing mappings (dakuten)
DAKUTEN_MAP = {
    'ka': 'ga', 'ki': 'gi', 'ku': 'gu', 'ke': 'ge', 'ko': 'go',
    'sa': 'za', 'shi': 'ji', 'su': 'zu', 'se': 'ze', 'so': 'zo',
    'ta': 'da', 'chi': 'dji', 'tsu': 'dzu', 'te': 'de', 'to': 'do',
    'ha': 'ba', 'hi': 'bi', 'fu': 'bu', 'he': 'be', 'ho': 'bo',
    'u': 'vu'
}

# Unvoicing (reverse dakuten)
UNDAKUTEN_MAP = {v: k for k, v in DAKUTEN_MAP.items()}

# Handakuten (semi-voicing)
HANDAKUTEN_MAP = {
    'ha': 'pa', 'hi': 'pi', 'fu': 'pu', 'he': 'pe', 'ho': 'po'
}


# ============================================================================
# Character Width Normalization
# ============================================================================

# Half-width katakana to full-width
HALF_WIDTH_KANA = "･ｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝﾞﾟ"
FULL_WIDTH_KANA = "・ヲァィゥェォャュョッーアイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン゛゜"

# Full-width alphanumeric to half-width
ABNORMAL_CHARS = (
    "０１２３４５６７８９"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "＃＄％＆（）＊＋／〈＝〉？＠［］＾＿'｛｜｝～"
    + HALF_WIDTH_KANA
)

NORMAL_CHARS = (
    "0123456789"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "#$%&()*+/<=>?@[]^_`{|}~"
    + FULL_WIDTH_KANA
)

# Punctuation normalization
PUNCTUATION_MAP = {
    "【": " [", "】": "] ",
    "、": ", ", "，": ", ",
    "。": ". ", "・・・": "... ", "・": " ", "　": " ",
    "「": " \"", "」": "\" ", "゛": "\"",
    "『": " «", "』": "» ",
    "〜": " - ", "：": ": ", "！": "! ", "？": "? ", "；": "; "
}


# ============================================================================
# Regex Patterns
# ============================================================================

# Character class patterns
KATAKANA_PATTERN = r'[ァ-ヺヽヾー]'
KATAKANA_UNIQ_PATTERN = r'[ァ-ヺヽヾ]'  # Without long vowel mark
HIRAGANA_PATTERN = r'[ぁ-ゔゝゞー]'
KANJI_PATTERN = r'[々ヶ〆一-龯]'
KANJI_CHAR_PATTERN = r'[一-龯]'  # Only kanji itself, no repeater marks
KANA_PATTERN = f'({KATAKANA_PATTERN}|{HIRAGANA_PATTERN})'
TRADITIONAL_PATTERN = f'({HIRAGANA_PATTERN}|{KANJI_PATTERN})'

# Non-word characters (not Japanese text)
NONWORD_PATTERN = r'[^々ヶ〆一-龯ァ-ヺヽヾぁ-ゔゝゞー〇]'

# Numeric patterns
NUMERIC_PATTERN = r'[0-9０-９〇一二三四五六七八九零壱弐参拾十百千万億兆京]'
DIGIT_PATTERN = r'[0-9０-９〇]'
DECIMAL_POINT_PATTERN = r'[.,]'

# Word pattern (any Japanese word character)
WORD_PATTERN = r'[々ヶ〆一-龯ァ-ヺヽヾぁ-ゔゝゞー〇]'
NUM_WORD_PATTERN = r'[0-9０-９〇々ヶ〆一-龯ァ-ヺヽヾぁ-ゔゝゞー]'

# Compiled regex objects
_KATAKANA_RE = re.compile(f'^{KATAKANA_PATTERN}+$')
_HIRAGANA_RE = re.compile(f'^{HIRAGANA_PATTERN}+$')
_KANJI_RE = re.compile(f'^{KANJI_PATTERN}+$')
_KANA_RE = re.compile(f'^{KANA_PATTERN}+$')
_NONWORD_RE = re.compile(f'^{NONWORD_PATTERN}+$')


# ============================================================================
# Character Classification Functions
# ============================================================================

def get_char_class(char: str) -> Optional[str]:
    """
    Get the character class for a kana character.
    Returns the kana class name (e.g., 'ka', 'shi', 'n') or None.
    """
    return _CHAR_CLASS_MAP.get(char)


def word_matches_class(word: str, char_class: str) -> bool:
    """
    Test if word consists entirely of a particular character class.
    
    Args:
        word: The word to test
        char_class: One of 'katakana', 'hiragana', 'kanji', 'kana', 'nonword'
    
    Returns:
        True if word matches the character class
    """
    if not word:
        return False
    
    patterns = {
        'katakana': _KATAKANA_RE,
        'hiragana': _HIRAGANA_RE,
        'kanji': _KANJI_RE,
        'kana': _KANA_RE,
        'nonword': _NONWORD_RE,
    }
    
    regex = patterns.get(char_class)
    if regex is None:
        return False
    
    return bool(regex.match(word))


def count_char_class(word: str, char_class: str) -> int:
    """Count occurrences of a character class in word."""
    patterns = {
        'katakana': KATAKANA_PATTERN,
        'hiragana': HIRAGANA_PATTERN,
        'kanji': KANJI_PATTERN,
        'kana': KANA_PATTERN,
    }
    
    pattern = patterns.get(char_class)
    if pattern is None:
        return 0
    
    return len(re.findall(pattern, word))


def is_katakana(word: str) -> bool:
    """Check if word is entirely katakana."""
    return word_matches_class(word, 'katakana')


def is_hiragana(word: str) -> bool:
    """Check if word is entirely hiragana."""
    return word_matches_class(word, 'hiragana')


def is_kanji(word: str) -> bool:
    """Check if word contains only kanji characters."""
    return word_matches_class(word, 'kanji')


def is_kana(word: str) -> bool:
    """Check if word is entirely kana (hiragana or katakana)."""
    return word_matches_class(word, 'kana')


def has_kanji(word: str) -> bool:
    """Check if word contains any kanji."""
    return bool(re.search(KANJI_PATTERN, word))


def has_kana(word: str) -> bool:
    """Check if word contains any kana."""
    return bool(re.search(KANA_PATTERN, word))


# ============================================================================
# Kana Conversion Functions
# ============================================================================

def as_hiragana(text: str) -> str:
    """
    Convert katakana to hiragana.
    Equivalent to ichiran's as-hiragana function.
    """
    result = []
    for char in text:
        char_class = get_char_class(char)
        if char_class and char_class in KANA_CHARS:
            # Get hiragana (first char of the pair)
            result.append(KANA_CHARS[char_class][0])
        elif char_class and char_class in MODIFIER_CHARS:
            result.append(MODIFIER_CHARS[char_class][0])
        elif char == 'ッ':
            result.append('っ')
        elif char == 'ー':
            result.append('ー')
        elif char in ITERATION_CHARS:
            result.append('ゝ')
        elif char in ITERATION_VOICED_CHARS:
            result.append('ゞ')
        else:
            result.append(char)
    return ''.join(result)


def as_katakana(text: str) -> str:
    """
    Convert hiragana to katakana.
    Equivalent to ichiran's as-katakana function.
    """
    result = []
    for char in text:
        char_class = get_char_class(char)
        if char_class and char_class in KANA_CHARS:
            # Get katakana (second/last char of the pair)
            result.append(KANA_CHARS[char_class][-1])
        elif char_class and char_class in MODIFIER_CHARS:
            result.append(MODIFIER_CHARS[char_class][-1])
        elif char == 'っ':
            result.append('ッ')
        elif char == 'ー':
            result.append('ー')
        elif char in ITERATION_CHARS:
            result.append('ヽ')
        elif char in ITERATION_VOICED_CHARS:
            result.append('ヾ')
        else:
            result.append(char)
    return ''.join(result)


# ============================================================================
# Voicing Functions (Rendaku/Unrendaku)
# ============================================================================

def rendaku(text: str, handakuten: bool = False) -> str:
    """
    Apply rendaku (sequential voicing) to the first character.
    
    Args:
        text: Text to modify
        handakuten: If True, apply handakuten (p-sounds) instead of dakuten
    
    Returns:
        Text with first character voiced, or original if not applicable
    """
    if not text:
        return text
    
    first_char = text[0]
    char_class = get_char_class(first_char)
    
    if not char_class:
        return text
    
    voice_map = HANDAKUTEN_MAP if handakuten else DAKUTEN_MAP
    voiced_class = voice_map.get(char_class)
    
    if not voiced_class:
        return text
    
    # Find position of char in original class
    orig_chars = KANA_CHARS.get(char_class, "")
    if first_char not in orig_chars:
        return text
    pos = orig_chars.index(first_char)
    
    # Get corresponding voiced char
    voiced_chars = KANA_CHARS.get(voiced_class, "")
    if pos < len(voiced_chars):
        return voiced_chars[pos] + text[1:]
    
    return text


def unrendaku(text: str) -> str:
    """
    Remove rendaku (unvoice) the first character.
    
    Returns:
        Text with first character unvoiced, or original if not applicable
    """
    if not text:
        return text
    
    first_char = text[0]
    char_class = get_char_class(first_char)
    
    if not char_class:
        return text
    
    unvoiced_class = UNDAKUTEN_MAP.get(char_class)
    
    if not unvoiced_class:
        return text
    
    # Find position of char in voiced class
    voiced_chars = KANA_CHARS.get(char_class, "")
    if first_char not in voiced_chars:
        return text
    pos = voiced_chars.index(first_char)
    
    # Get corresponding unvoiced char
    unvoiced_chars = KANA_CHARS.get(unvoiced_class, "")
    if pos < len(unvoiced_chars):
        return unvoiced_chars[pos] + text[1:]
    
    return text


def geminate(text: str) -> str:
    """
    Replace the last character with small tsu (gemination marker).
    """
    if not text:
        return text
    
    return text[:-1] + 'っ'


# ============================================================================
# Text Normalization Functions
# ============================================================================

def normalize_char(char: str, context: str = None) -> str:
    """
    Normalize a single character (e.g., half-width to full-width).
    
    Args:
        char: Single character to normalize
        context: 'kana' for kana-only normalization
    
    Returns:
        Normalized character or original if not found
    """
    if context == 'kana':
        abnormal = HALF_WIDTH_KANA
        normal = FULL_WIDTH_KANA
    else:
        abnormal = ABNORMAL_CHARS
        normal = NORMAL_CHARS
    
    pos = abnormal.find(char)
    if pos >= 0 and pos < len(normal):
        return normal[pos]
    return char


def normalize(text: str, context: str = None) -> str:
    """
    Normalize text by converting abnormal characters to normal form.
    
    This includes:
    - Full-width alphanumeric to half-width
    - Half-width katakana to full-width
    - Combined dakuten characters to single characters
    - Punctuation normalization
    
    Args:
        text: Text to normalize
        context: 'kana' for kana-only context
    
    Returns:
        Normalized text
    """
    # Character-by-character normalization
    chars = [normalize_char(c, context) for c in text]
    text = ''.join(chars)
    
    # Punctuation replacement (if not kana-only context)
    if context != 'kana':
        for old, new in PUNCTUATION_MAP.items():
            text = text.replace(old, new)
    
    return text


# ============================================================================
# Text Splitting Functions
# ============================================================================

# Basic split pattern for Japanese text
_BASIC_SPLIT_PATTERN = rf'({WORD_PATTERN}(?:{NUM_WORD_PATTERN})*{WORD_PATTERN}?|{WORD_PATTERN})'
_BASIC_SPLIT_RE = re.compile(_BASIC_SPLIT_PATTERN)


def basic_split(text: str) -> List[Tuple[str, str]]:
    """
    Split text into segments of Japanese words and misc characters.
    
    Equivalent to ichiran's basic-split function.
    
    Returns:
        List of (type, segment) tuples where type is 'word' or 'misc'
    """
    result = []
    last_end = 0
    
    for match in _BASIC_SPLIT_RE.finditer(text):
        # Add any preceding non-word text
        if match.start() > last_end:
            misc = text[last_end:match.start()]
            if misc:
                result.append(('misc', misc))
        
        # Add the word
        result.append(('word', match.group()))
        last_end = match.end()
    
    # Add any trailing non-word text
    if last_end < len(text):
        misc = text[last_end:]
        if misc:
            result.append(('misc', misc))
    
    return result


def mora_length(text: str) -> int:
    """
    Calculate mora length (doesn't count modifier characters).
    Equivalent to ichiran's mora-length function.
    """
    modifiers = "っッぁァぃィぅゥぇェぉォゃャゅュょョー"
    return sum(1 for c in text if c not in modifiers)


# ============================================================================
# Kanji Utilities
# ============================================================================

def sequential_kanji_positions(word: str, offset: int = 0) -> List[int]:
    """
    Find positions where kanji characters are adjacent.
    Used for identifying potential word boundaries.
    """
    positions = []
    pattern = re.compile(r'(?=[々一-龯][々一-龯])')
    for match in pattern.finditer(word):
        positions.append(match.start() + 1 + offset)
    return positions


def kanji_prefix(word: str) -> str:
    """
    Get the kanji prefix of a word (everything up to and including last kanji).
    """
    match = re.search(rf'^.*{KANJI_PATTERN}', word)
    return match.group() if match else ""


def kanji_mask(word: str) -> str:
    """
    Create SQL LIKE mask for word by replacing kanji sequences with %.
    """
    return re.sub(rf'{KANJI_PATTERN}+', '%', word)


def kanji_match(word: str, reading: str) -> bool:
    """
    Check if a reading matches a word pattern (kanji as wildcards).
    """
    mask = kanji_mask(word)
    # Convert LIKE pattern to regex
    pattern = '^' + mask.replace('%', '.+') + '$'
    return bool(re.match(pattern, reading))


# ============================================================================
# Utility Functions
# ============================================================================

def safe_subseq(sequence: str, start: int, end: int = None) -> Optional[str]:
    """
    Safe substring that returns None if indices are out of bounds.
    """
    length = len(sequence)
    if start < 0 or start > length:
        return None
    if end is not None and (end < start or end > length):
        return None
    return sequence[start:end]


def join(separator: str, items: List, key=None) -> str:
    """
    Join items with separator, optionally applying a key function.
    """
    if key:
        items = [key(item) for item in items]
    return separator.join(str(item) for item in items)


# ============================================================================
# Romanization
# ============================================================================

# Basic kana to romaji mapping
ROMAJI_MAP = {
    'a': 'a', 'i': 'i', 'u': 'u', 'e': 'e', 'o': 'o',
    'ka': 'ka', 'ki': 'ki', 'ku': 'ku', 'ke': 'ke', 'ko': 'ko',
    'sa': 'sa', 'shi': 'shi', 'su': 'su', 'se': 'se', 'so': 'so',
    'ta': 'ta', 'chi': 'chi', 'tsu': 'tsu', 'te': 'te', 'to': 'to',
    'na': 'na', 'ni': 'ni', 'nu': 'nu', 'ne': 'ne', 'no': 'no',
    'ha': 'ha', 'hi': 'hi', 'fu': 'fu', 'he': 'he', 'ho': 'ho',
    'ma': 'ma', 'mi': 'mi', 'mu': 'mu', 'me': 'me', 'mo': 'mo',
    'ya': 'ya', 'yu': 'yu', 'yo': 'yo',
    'ra': 'ra', 'ri': 'ri', 'ru': 'ru', 're': 're', 'ro': 'ro',
    'wa': 'wa', 'wi': 'wi', 'we': 'we', 'wo': 'wo',
    'n': 'n',
    # Voiced
    'ga': 'ga', 'gi': 'gi', 'gu': 'gu', 'ge': 'ge', 'go': 'go',
    'za': 'za', 'ji': 'ji', 'zu': 'zu', 'ze': 'ze', 'zo': 'zo',
    'da': 'da', 'dji': 'di', 'dzu': 'du', 'de': 'de', 'do': 'do',
    'ba': 'ba', 'bi': 'bi', 'bu': 'bu', 'be': 'be', 'bo': 'bo',
    'pa': 'pa', 'pi': 'pi', 'pu': 'pu', 'pe': 'pe', 'po': 'po',
    'vu': 'vu',
    # Small kana (modifiers)
    '+a': 'a', '+i': 'i', '+u': 'u', '+e': 'e', '+o': 'o',
    '+ya': 'ya', '+yu': 'yu', '+yo': 'yo', '+wa': 'wa',
    'sokuon': '',  # Handled specially
    'long_vowel': '',  # Handled specially
    'iter': '',
    'iter_v': '',
}


def romanize_word(text: str) -> str:
    """
    Convert kana text to romaji.
    
    This is a simplified romanization function. For full ichiran
    compatibility, a more complex system would be needed.
    
    Args:
        text: Kana text to romanize
        
    Returns:
        Romanized text
    """
    if not text:
        return text
    
    result = []
    prev_char_class = None
    i = 0
    
    while i < len(text):
        char = text[i]
        char_class = get_char_class(char)
        
        if char_class is None:
            # Non-kana character, pass through
            result.append(char)
            prev_char_class = None
            i += 1
            continue
        
        # Handle sokuon (small tsu) - double next consonant
        if char_class == 'sokuon':
            if i + 1 < len(text):
                next_class = get_char_class(text[i + 1])
                if next_class and next_class in ROMAJI_MAP:
                    romaji = ROMAJI_MAP[next_class]
                    if romaji and romaji[0] not in 'aeioun':
                        result.append(romaji[0])
            prev_char_class = char_class
            i += 1
            continue
        
        # Handle long vowel mark
        if char_class == 'long_vowel':
            if result:
                # Extend the previous vowel
                last = result[-1]
                if last in 'aeiou':
                    result.append(last)
                else:
                    result.append('ō')
            else:
                result.append('ō')
            prev_char_class = char_class
            i += 1
            continue
        
        # Handle small kana (ya, yu, yo)
        if char_class.startswith('+'):
            base_romaji = ROMAJI_MAP.get(char_class, char)
            # Combine with previous consonant
            if result and result[-1].endswith('i'):
                # Replace 'i' with small kana sound
                result[-1] = result[-1][:-1] + base_romaji
            else:
                result.append(base_romaji)
            prev_char_class = char_class
            i += 1
            continue
        
        # Regular kana
        romaji = ROMAJI_MAP.get(char_class, char)
        
        # Handle 'n' before certain sounds
        if char_class == 'n' and i + 1 < len(text):
            next_char = text[i + 1]
            next_class = get_char_class(next_char)
            if next_class and next_class.startswith(('+', 'a', 'i', 'u', 'e', 'o', 'ya', 'yu', 'yo')):
                romaji = "n'"
        
        result.append(romaji)
        prev_char_class = char_class
        i += 1
    
    return ''.join(result)