"""
Japanese number handling for Himotoki.

Provides conversion between Arabic numerals, kanji numerals, and kana readings.

Mirrors numbers.lisp from the original Ichiran.
"""

from typing import List, Optional, Tuple, Union
from himotoki.characters import geminate, rendaku, join_with_separator

# ============================================================================
# Number Kanji Tables
# ============================================================================

# Standard digit kanji (0-9)
DIGIT_KANJI_DEFAULT = "〇一二三四五六七八九"

# Legal/formal digit kanji
DIGIT_KANJI_LEGAL = "〇壱弐参四五六七八九拾"

# Power kanji (10, 100, 1000, 10000, 100000000, etc.)
# Spaces indicate unused positions
POWER_KANJI = "一十百千万   億   兆   京"

# Character to number class mapping
# :jd = Japanese digit, :p = power, :ad = Arabic digit
CHAR_NUMBER_CLASS = {
    # Japanese digits
    '〇': ('jd', 0), '零': ('jd', 0),
    '一': ('jd', 1), '壱': ('jd', 1),
    '二': ('jd', 2), '弐': ('jd', 2),
    '三': ('jd', 3), '参': ('jd', 3),
    '四': ('jd', 4),
    '五': ('jd', 5),
    '六': ('jd', 6),
    '七': ('jd', 7),
    '八': ('jd', 8),
    '九': ('jd', 9),
    # Powers of ten
    '十': ('p', 1), '拾': ('p', 1),
    '百': ('p', 2),
    '千': ('p', 3),
    '万': ('p', 4),
    '億': ('p', 8),
    '兆': ('p', 12),
    '京': ('p', 16),
    # Arabic digits (full-width and half-width)
    '0': ('ad', 0), '０': ('ad', 0),
    '1': ('ad', 1), '１': ('ad', 1),
    '2': ('ad', 2), '２': ('ad', 2),
    '3': ('ad', 3), '３': ('ad', 3),
    '4': ('ad', 4), '４': ('ad', 4),
    '5': ('ad', 5), '５': ('ad', 5),
    '6': ('ad', 6), '６': ('ad', 6),
    '7': ('ad', 7), '７': ('ad', 7),
    '8': ('ad', 8), '８': ('ad', 8),
    '9': ('ad', 9), '９': ('ad', 9),
}

# Digit to kana reading
DIGIT_TO_KANA = {
    0: "れい",
    1: "いち",
    2: "に",
    3: "さん",
    4: "よん",
    5: "ご",
    6: "ろく",
    7: "なな",
    8: "はち",
    9: "きゅう",
}

# Alternative readings for some digits
DIGIT_TO_KANA_ALT = {
    4: "し",
    7: "しち",
    9: "く",
}

# Power to kana reading
POWER_TO_KANA = {
    1: "じゅう",
    2: "ひゃく",
    3: "せん",
    4: "まん",
    8: "おく",
    12: "ちょう",
    16: "けい",
}


# ============================================================================
# Number to Kanji Conversion
# ============================================================================

def number_to_kanji(n: int, digits: str = DIGIT_KANJI_DEFAULT, 
                    powers: str = POWER_KANJI, one_sen: bool = False) -> str:
    """
    Convert a non-negative integer to Japanese kanji numerals.
    
    Args:
        n: Non-negative integer to convert.
        digits: Digit characters to use.
        powers: Power characters to use.
        one_sen: If True, include "一" before 百/千.
        
    Returns:
        Kanji representation of the number.
        
    Example:
        >>> number_to_kanji(123)
        '百二十三'
        >>> number_to_kanji(1000)
        '千'
        >>> number_to_kanji(10500)
        '一万五百'
    """
    assert isinstance(n, int) and n >= 0, "n must be a non-negative integer"
    
    if n == 0:
        return digits[0]
    
    # Find the largest power that divides n
    max_power = 1
    max_power_char = None
    
    power = 1
    for i, char in enumerate(powers):
        if power > n:
            break
        if char != ' ':
            max_power = power
            max_power_char = char
        power *= 10
    
    if max_power == 1:
        return digits[n]
    
    quotient, remainder = divmod(n, max_power)
    
    # Build the result
    result = ""
    
    # Add the quotient (omit 一 for 十, 百, 千 in certain cases)
    if quotient == 1:
        threshold = 100 if one_sen else 1000
        if max_power <= threshold:
            result = ""
        else:
            result = number_to_kanji(quotient, digits, powers, one_sen=True)
    else:
        result = number_to_kanji(quotient, digits, powers, one_sen=True)
    
    result += max_power_char
    
    # Add the remainder
    if remainder > 0:
        result += number_to_kanji(remainder, digits, powers)
    
    return result


# ============================================================================
# Parse Number from Kanji
# ============================================================================

class NotANumber(Exception):
    """Raised when a string cannot be parsed as a Japanese number."""
    
    def __init__(self, text: str, reason: str):
        self.text = text
        self.reason = reason
        super().__init__(f"'{text}' is not a number: {reason}")


def parse_number(text: str) -> int:
    """
    Parse a Japanese number string to an integer.
    
    Args:
        text: String containing Japanese numerals.
        
    Returns:
        Integer value.
        
    Raises:
        NotANumber: If the string cannot be parsed.
        
    Example:
        >>> parse_number("百二十三")
        123
        >>> parse_number("一万五百")
        10500
    """
    # Convert to class/value pairs
    classes = []
    for char in text:
        if char in CHAR_NUMBER_CLASS:
            classes.append(CHAR_NUMBER_CLASS[char])
        else:
            raise NotANumber(text, f"Invalid character: {char}")
    
    if not classes:
        raise NotANumber(text, "Empty string")
    
    return _parse_number_internal(classes, 0, len(classes))


def _parse_number_internal(classes: List[Tuple[str, int]], start: int, end: int) -> int:
    """Internal recursive parser for Japanese numbers."""
    if start >= end:
        return 0
    
    # Find the largest power in the range
    max_power = 0
    max_idx = None
    
    for i in range(start, end):
        cls, val = classes[i]
        if cls == 'p' and val > max_power:
            max_power = val
            max_idx = i
    
    if max_idx is None:
        # No powers, just digits - treat as positional
        result = 0
        for i in range(start, end):
            result = result * 10 + classes[i][1]
        return result
    
    # Calculate value before and after the power
    if max_idx == start:
        # Power at the start means coefficient of 1
        coefficient = 1
    else:
        coefficient = _parse_number_internal(classes, start, max_idx)
    
    power_value = 10 ** max_power
    
    remainder = 0
    if max_idx + 1 < end:
        remainder = _parse_number_internal(classes, max_idx + 1, end)
    
    return coefficient * power_value + remainder


# ============================================================================
# Number Euphonic Changes (Sandhi)
# ============================================================================

def num_sandhi(c1: Optional[str], v1: Optional[int], 
               c2: str, v2: int, 
               s1: str, s2: str) -> str:
    """
    Apply euphonic changes when joining number components.
    
    Handles special cases like:
    - 一 + 千 → いっせん (gemination)
    - 三 + 百 → さんびゃく (rendaku)
    - 六 + 百 → ろっぴゃく (gemination + handakuten)
    
    Args:
        c1: First component class ('jd' or 'p').
        v1: First component value.
        c2: Second component class.
        v2: Second component value.
        s1: First component kana.
        s2: Second component kana.
        
    Returns:
        Combined kana string with appropriate changes.
    """
    s1_mod = s1
    s2_mod = s2
    
    if c1 == 'jd':
        if v1 == 1:
            # 一 + (千, 兆, 京) = gemination
            if v2 in (3, 12, 16):
                s1_mod = geminate(s1_mod)
        elif v1 == 3:
            # 三 + (百, 千) = rendaku
            if v2 in (2, 3):
                s2_mod = rendaku(s2_mod)
        elif v1 == 6:
            # 六 + 百 = gemination + handakuten
            if v2 == 2:
                s1_mod = geminate(s1_mod)
                s2_mod = rendaku(s2_mod, handakuten=True)
            elif v2 == 16:
                s1_mod = geminate(s1_mod)
        elif v1 == 8:
            # 八 + (百, 千, 兆, 京) = gemination (+ handakuten for 百)
            if v2 == 2:
                s1_mod = geminate(s1_mod)
                s2_mod = rendaku(s2_mod, handakuten=True)
            elif v2 in (3, 12, 16):
                s1_mod = geminate(s1_mod)
    elif c1 == 'p':
        if v1 == 1:
            # 十 + (兆, 京) = gemination
            if v2 in (12, 16):
                s1_mod = geminate(s1_mod)
        elif v1 == 2:
            # 百 + 京 = gemination
            if v2 == 16:
                s1_mod = geminate(s1_mod)
    
    return s1_mod + s2_mod


def group_to_kana(group: List[Tuple[str, int]], 
                  digit_kana: dict = DIGIT_TO_KANA,
                  power_kana: dict = POWER_TO_KANA) -> str:
    """
    Convert a group of number classes to kana.
    
    Args:
        group: List of (class, value) tuples.
        digit_kana: Mapping from digit values to kana.
        power_kana: Mapping from power values to kana.
        
    Returns:
        Kana reading of the group.
    """
    result = ""
    last_class = None
    last_val = None
    
    for cls, val in group:
        if cls == 'jd':
            kana = digit_kana.get(val, "")
        elif cls == 'p':
            kana = power_kana.get(val, "")
        else:
            kana = digit_kana.get(val, "")
        
        if last_class is not None:
            result = num_sandhi(last_class, last_val, cls, val, result, kana)
        else:
            result = kana
        
        last_class = cls
        last_val = val
    
    return result


def number_to_kana(n: int, separator: str = " ", 
                   kanji_method=number_to_kanji) -> Union[str, List[str]]:
    """
    Convert a number to its kana reading.
    
    Args:
        n: Number to convert.
        separator: Separator between groups (None for list output).
        kanji_method: Function to convert number to kanji first.
        
    Returns:
        Kana reading, or list of readings if separator is None.
        
    Example:
        >>> number_to_kana(123)
        'ひゃく にじゅうさん'
        >>> number_to_kana(10)
        'じゅう'
    """
    kanji = kanji_method(n)
    
    # Build groups based on power structure
    groups = []
    current_group = []
    last_class = None
    last_val = None
    
    for char in kanji:
        if char not in CHAR_NUMBER_CLASS:
            continue
        cls, val = CHAR_NUMBER_CLASS[char]
        
        # Start a new group when transitioning to a larger power
        if last_class is not None:
            if cls == 'p' and (last_class == 'jd' or 
                              (last_class == 'p' and val > last_val)):
                current_group.append((cls, val))
            else:
                if current_group:
                    groups.append(current_group)
                current_group = [(cls, val)]
        else:
            current_group = [(cls, val)]
        
        last_class = cls
        last_val = val
    
    if current_group:
        groups.append(current_group)
    
    # Convert groups to kana
    kana_groups = [group_to_kana(group) for group in groups]
    
    if separator is not None:
        return separator.join(kana_groups)
    return kana_groups


# ============================================================================
# Utility Functions
# ============================================================================

def get_digit(n: int) -> int:
    """
    Get the ones digit of a number.
    
    Args:
        n: Number.
        
    Returns:
        Ones digit (0-9).
    """
    return n % 10


def is_numeric_string(text: str) -> bool:
    """
    Check if a string contains only numeric characters (Arabic or Japanese).
    
    Args:
        text: String to check.
        
    Returns:
        True if the string is numeric.
    """
    return all(c in CHAR_NUMBER_CLASS for c in text)
