"""
Character handling and kana conversion for Himotoki.

Provides character classification, hiragana/katakana conversion, 
normalization, rendaku (sequential voicing), and text splitting.

Mirrors characters.lisp from the original Ichiran.
"""

import re
import unicodedata
from typing import Dict, List, Optional, Tuple, Set, Union

# ============================================================================
# Kana Character Tables
# ============================================================================

# Sokuon (gemination marker)
SOKUON_CHARACTERS = {"sokuon": "っッ"}

# Iteration marks
ITERATION_CHARACTERS = {
    "iter": "ゝヽ",
    "iter_v": "ゞヾ"
}

# Small kana modifiers and long vowel marker
MODIFIER_CHARACTERS = {
    "+a": "ぁァ", "+i": "ぃィ", "+u": "ぅゥ", "+e": "ぇェ", "+o": "ぉォ",
    "+ya": "ゃャ", "+yu": "ゅュ", "+yo": "ょョ", "+wa": "ゎヮ",
    "long_vowel": "ー"
}

# Main kana table
KANA_CHARACTERS = {
    "a": "あア",     "i": "いイ",     "u": "うウ",     "e": "えエ",     "o": "おオ",
    "ka": "かカ",    "ki": "きキ",    "ku": "くク",    "ke": "けケ",    "ko": "こコ",
    "sa": "さサ",    "shi": "しシ",   "su": "すス",    "se": "せセ",    "so": "そソ",
    "ta": "たタ",    "chi": "ちチ",   "tsu": "つツ",   "te": "てテ",    "to": "とト",
    "na": "なナ",    "ni": "にニ",    "nu": "ぬヌ",    "ne": "ねネ",    "no": "のノ",
    "ha": "はハ",    "hi": "ひヒ",    "fu": "ふフ",    "he": "へヘ",    "ho": "ほホ",
    "ma": "まマ",    "mi": "みミ",    "mu": "むム",    "me": "めメ",    "mo": "もモ",
    "ya": "やヤ",                     "yu": "ゆユ",                     "yo": "よヨ",
    "ra": "らラ",    "ri": "りリ",    "ru": "るル",    "re": "れレ",    "ro": "ろロ",
    "wa": "わワ",    "wi": "ゐヰ",                     "we": "ゑヱ",    "wo": "をヲ",
    "n": "んン",
    # Voiced consonants (dakuten)
    "ga": "がガ",    "gi": "ぎギ",    "gu": "ぐグ",    "ge": "げゲ",    "go": "ごゴ",
    "za": "ざザ",    "ji": "じジ",    "zu": "ずズ",    "ze": "ぜゼ",    "zo": "ぞゾ",
    "da": "だダ",    "dji": "ぢヂ",   "dzu": "づヅ",   "de": "でデ",    "do": "どド",
    "ba": "ばバ",    "bi": "びビ",    "bu": "ぶブ",    "be": "べベ",    "bo": "ぼボ",
    "pa": "ぱパ",    "pi": "ぴピ",    "pu": "ぷプ",    "pe": "ぺペ",    "po": "ぽポ",
    "vu": "ゔヴ",
}

# Combined character table
ALL_CHARACTERS = {
    **SOKUON_CHARACTERS,
    **ITERATION_CHARACTERS, 
    **MODIFIER_CHARACTERS,
    **KANA_CHARACTERS
}

# ============================================================================
# Character Class Mapping
# ============================================================================

# Build character -> class mapping
CHAR_CLASS_HASH: Dict[str, str] = {}
for char_class, chars in ALL_CHARACTERS.items():
    for char in chars:
        CHAR_CLASS_HASH[char] = char_class


def get_char_class(char: str) -> str:
    """
    Get the character class for a kana character.
    
    Args:
        char: A single character.
        
    Returns:
        Character class name (e.g., 'ka', 'shi', 'sokuon') or the character itself.
    """
    return CHAR_CLASS_HASH.get(char, char)


# ============================================================================
# Dakuten (Voicing) Tables
# ============================================================================

# Unvoiced -> voiced mappings
DAKUTEN_HASH = {
    "ka": "ga", "ki": "gi", "ku": "gu", "ke": "ge", "ko": "go",
    "sa": "za", "shi": "ji", "su": "zu", "se": "ze", "so": "zo",
    "ta": "da", "chi": "dji", "tsu": "dzu", "te": "de", "to": "do",
    "ha": "ba", "hi": "bi", "fu": "bu", "he": "be", "ho": "bo",
    "u": "vu",
}

# Unvoiced -> semi-voiced (handakuten) mappings
HANDAKUTEN_HASH = {
    "ha": "pa", "hi": "pi", "fu": "pu", "he": "pe", "ho": "po",
}

# Voiced/semi-voiced -> unvoiced mappings
UNDAKUTEN_HASH = {
    "ga": "ka", "gi": "ki", "gu": "ku", "ge": "ke", "go": "ko",
    "za": "sa", "ji": "shi", "zu": "su", "ze": "se", "zo": "so",
    "da": "ta", "dji": "chi", "dzu": "tsu", "de": "te", "do": "to",
    "ba": "ha", "bi": "hi", "bu": "fu", "be": "he", "bo": "ho",
    "pa": "ha", "pi": "hi", "pu": "fu", "pe": "he", "po": "ho",
    "vu": "u",
}


def voice_char(cc: str) -> str:
    """Returns the voiced form of a character class, or the same class."""
    return DAKUTEN_HASH.get(cc, cc)


# ============================================================================
# Character Width Normalization
# ============================================================================

# Half-width to full-width kana mapping
HALF_WIDTH_KANA = "･ｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝﾞﾟ"
FULL_WIDTH_KANA = "・ヲァィゥェォャュョッーアイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン゛゜"

# Full-width alphanumeric to half-width
ABNORMAL_CHARS = (
    "０１２３４５６７８９ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "＃＄％＆（）＊＋／〈＝〉？＠［］＾＿'｛｜｝～"
    + HALF_WIDTH_KANA
)

NORMAL_CHARS = (
    "0123456789abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "#$%&()*+/<=>?@[]^_`{|}~"
    + FULL_WIDTH_KANA
)

# Build normalization mapping
_CHAR_NORM_MAP = {}
for i, c in enumerate(ABNORMAL_CHARS):
    if i < len(NORMAL_CHARS):
        _CHAR_NORM_MAP[c] = NORMAL_CHARS[i]

# Dakuten combining character mappings
DAKUTEN_JOIN = {}
for (cc, ccd) in DAKUTEN_HASH.items():
    kc = KANA_CHARACTERS.get(cc, "")
    kcd = KANA_CHARACTERS.get(ccd, "")
    if kc and kcd:
        for i, char in enumerate(kc):
            if i < len(kcd):
                DAKUTEN_JOIN[char + "゛"] = kcd[i]

for (cc, ccd) in HANDAKUTEN_HASH.items():
    kc = KANA_CHARACTERS.get(cc, "")
    kcd = KANA_CHARACTERS.get(ccd, "")
    if kc and kcd:
        for i, char in enumerate(kc):
            if i < len(kcd):
                DAKUTEN_JOIN[char + "゜"] = kcd[i]

# Punctuation normalization
PUNCTUATION_MARKS = {
    "【": " [", "】": "] ",
    "、": ", ", "，": ", ",
    "。": ". ", "・・・": "... ", "・": " ", "　": " ",
    "「": ' "', "」": '" ', "゛": '"',
    "『": " «", "』": "» ",
    "〜": " - ", "：": ": ", "！": "! ", "？": "? ", "；": "; "
}

# ============================================================================
# Regular Expressions
# ============================================================================

KATAKANA_REGEX = r"[ァ-ヺヽヾー]"
KATAKANA_UNIQ_REGEX = r"[ァ-ヺヽヾ]"
HIRAGANA_REGEX = r"[ぁ-ゔゝゞー]"
KANJI_REGEX = r"[々ヶ〆一-龯]"
KANJI_CHAR_REGEX = r"[一-龯]"
NONWORD_REGEX = r"[^々ヶ〆一-龯ァ-ヺヽヾぁ-ゔゝゞー〇]"
NUMERIC_REGEX = r"[0-9０-９〇一二三四五六七八九零壱弐参拾十百千万億兆京]"
NUM_WORD_REGEX = r"[0-9０-９〇々ヶ〆一-龯ァ-ヺヽヾぁ-ゔゝゞー]"
WORD_REGEX = r"[々ヶ〆一-龯ァ-ヺヽヾぁ-ゔゝゞー〇]"
DIGIT_REGEX = r"[0-9０-９〇]"
DECIMAL_POINT_REGEX = r"[.,]"
KANA_REGEX = f"({KATAKANA_REGEX}|{HIRAGANA_REGEX})"

# Compiled regex patterns
_KATAKANA_PATTERN = re.compile(KATAKANA_REGEX)
_KATAKANA_UNIQ_PATTERN = re.compile(KATAKANA_UNIQ_REGEX)
_HIRAGANA_PATTERN = re.compile(HIRAGANA_REGEX)
_KANJI_PATTERN = re.compile(KANJI_REGEX)
_KANJI_CHAR_PATTERN = re.compile(KANJI_CHAR_REGEX)
_KANA_PATTERN = re.compile(KANA_REGEX)
_NONWORD_PATTERN = re.compile(NONWORD_REGEX)
_NUMERIC_PATTERN = re.compile(NUMERIC_REGEX)
_WORD_PATTERN = re.compile(WORD_REGEX)

# Basic split regex for separating Japanese from non-Japanese text
BASIC_SPLIT_REGEX = (
    rf"((?:(?<!{DECIMAL_POINT_REGEX}|{DIGIT_REGEX}){DIGIT_REGEX}+|{WORD_REGEX})"
    rf"{NUM_WORD_REGEX}*{WORD_REGEX}|{WORD_REGEX})"
)
_BASIC_SPLIT_PATTERN = re.compile(BASIC_SPLIT_REGEX)

# Sequential kanji pattern for finding kanji boundaries
_SEQUENTIAL_KANJI_PATTERN = re.compile(r"(?=[々一-龯][々一-龯])")


# ============================================================================
# Character Testing Functions
# ============================================================================

def test_word(word: str, char_class: str) -> bool:
    """
    Test if a word consists entirely of a specific character class.
    
    Args:
        word: The word to test.
        char_class: One of 'katakana', 'hiragana', 'kanji', 'kana', 'nonword', 'number'.
        
    Returns:
        True if the word matches the character class entirely.
    """
    if not word:
        return False
        
    patterns = {
        'katakana': rf"^{KATAKANA_REGEX}+$",
        'katakana_uniq': rf"^{KATAKANA_UNIQ_REGEX}+$",
        'hiragana': rf"^{HIRAGANA_REGEX}+$",
        'kanji': rf"^{KANJI_REGEX}+$",
        'kanji_char': rf"^{KANJI_CHAR_REGEX}+$",
        'kana': rf"^{KANA_REGEX}+$",
        'traditional': rf"^({HIRAGANA_REGEX}|{KANJI_REGEX})+$",
        'nonword': rf"^{NONWORD_REGEX}+$",
        'number': rf"^{NUMERIC_REGEX}+$",
    }
    
    pattern = patterns.get(char_class)
    if pattern:
        return bool(re.match(pattern, word))
    return False


def is_kana(word: str) -> bool:
    """Check if word consists entirely of kana (hiragana or katakana)."""
    return test_word(word, 'kana')


def is_kanji(char: str) -> bool:
    """Check if a character is kanji."""
    return bool(_KANJI_CHAR_PATTERN.match(char))


def is_hiragana(word: str) -> bool:
    """Check if word consists entirely of hiragana."""
    return test_word(word, 'hiragana')


def is_katakana(word: str) -> bool:
    """Check if word consists entirely of katakana."""
    return test_word(word, 'katakana')


def count_char_class(word: str, char_class: str) -> int:
    """
    Count characters matching a specific class in a word.
    
    Args:
        word: The word to analyze.
        char_class: Character class to count.
        
    Returns:
        Number of matching characters.
    """
    patterns = {
        'katakana': _KATAKANA_PATTERN,
        'katakana_uniq': _KATAKANA_UNIQ_PATTERN,
        'hiragana': _HIRAGANA_PATTERN,
        'kanji': _KANJI_PATTERN,
        'kanji_char': _KANJI_CHAR_PATTERN,
        'kana': _KANA_PATTERN,
        'nonword': _NONWORD_PATTERN,
        'number': _NUMERIC_PATTERN,
    }
    
    pattern = patterns.get(char_class)
    if pattern:
        return len(pattern.findall(word))
    return 0


def collect_char_class(word: str, char_class: str) -> List[str]:
    """
    Collect all characters matching a specific class.
    
    Args:
        word: The word to analyze.
        char_class: Character class to collect.
        
    Returns:
        List of matching characters.
    """
    patterns = {
        'katakana': _KATAKANA_PATTERN,
        'hiragana': _HIRAGANA_PATTERN,
        'kanji': _KANJI_PATTERN,
        'kanji_char': _KANJI_CHAR_PATTERN,
        'kana': _KANA_PATTERN,
    }
    
    pattern = patterns.get(char_class)
    if pattern:
        return pattern.findall(word)
    return []


def sequential_kanji_positions(word: str, offset: int = 0) -> List[int]:
    """
    Find positions where two kanji appear consecutively.
    
    Used for detecting kanji compound boundaries.
    
    Args:
        word: The word to analyze.
        offset: Offset to add to positions.
        
    Returns:
        List of positions (1-indexed relative to offset).
    """
    positions = []
    for match in _SEQUENTIAL_KANJI_PATTERN.finditer(word):
        positions.append(match.start() + 1 + offset)
    return positions


def consecutive_char_groups(word: str, char_class: str, start: int = 0, end: Optional[int] = None) -> List[Tuple[int, int]]:
    """
    Find consecutive groups of a character class.
    
    Args:
        word: The word to analyze.
        char_class: Character class to find.
        start: Start position.
        end: End position.
        
    Returns:
        List of (start, end) tuples for each group.
    """
    if end is None:
        end = len(word)
    
    patterns = {
        'katakana': rf"{KATAKANA_REGEX}+",
        'hiragana': rf"{HIRAGANA_REGEX}+",
        'kanji': rf"{KANJI_REGEX}+",
        'number': rf"{NUMERIC_REGEX}+",
        'kana': rf"{KANA_REGEX}+",
    }
    
    pattern = patterns.get(char_class)
    if not pattern:
        return []
    
    regex = re.compile(pattern)
    groups = []
    for match in regex.finditer(word, start, end):
        groups.append((match.start(), match.end()))
    return groups


# ============================================================================
# Text Normalization
# ============================================================================

def to_normal_char(char: str, context: Optional[str] = None) -> Optional[str]:
    """
    Convert an abnormal character to its normal form.
    
    Args:
        char: Character to normalize.
        context: Context for normalization ('kana' uses different mapping).
        
    Returns:
        Normalized character or None if no normalization needed.
    """
    if context == 'kana':
        pos = HALF_WIDTH_KANA.find(char)
        if pos >= 0 and pos < len(FULL_WIDTH_KANA):
            return FULL_WIDTH_KANA[pos]
    else:
        return _CHAR_NORM_MAP.get(char)
    return None


def simplify_ngrams(text: str, mapping: Dict[str, str]) -> str:
    """
    Apply n-gram replacements to text.
    
    Args:
        text: Text to process.
        mapping: Dictionary of patterns to replacements.
        
    Returns:
        Processed text.
    """
    if not mapping:
        return text
    
    # Sort by length (longest first) to handle overlapping patterns
    patterns = sorted(mapping.keys(), key=len, reverse=True)
    result = text
    for pattern in patterns:
        result = result.replace(pattern, mapping[pattern])
    return result


def normalize(text: str, context: Optional[str] = None) -> str:
    """
    Normalize text for processing.
    
    - Converts full-width alphanumeric to half-width
    - Converts half-width kana to full-width
    - Combines dakuten/handakuten with base characters
    - Normalizes punctuation
    
    Args:
        text: Text to normalize.
        context: Optional context ('kana' for kana-specific normalization).
        
    Returns:
        Normalized text.
    """
    # Character normalization
    result = []
    for char in text:
        normal = to_normal_char(char, context)
        result.append(normal if normal else char)
    text = ''.join(result)
    
    # Apply dakuten joining
    text = simplify_ngrams(text, DAKUTEN_JOIN)
    
    # Apply punctuation normalization (unless in kana context)
    if context != 'kana':
        text = simplify_ngrams(text, PUNCTUATION_MARKS)
    
    return text


# ============================================================================
# Kana Conversion
# ============================================================================

def as_hiragana(text: str) -> str:
    """
    Convert katakana to hiragana.
    
    Args:
        text: Text to convert.
        
    Returns:
        Text with katakana converted to hiragana.
    """
    result = []
    for char in text:
        # First normalize the character
        normal = to_normal_char(char)
        if normal:
            char = normal
        
        # Get character class and convert
        char_class = CHAR_CLASS_HASH.get(char)
        if char_class and char_class in ALL_CHARACTERS:
            # Get the hiragana (first character in the pair)
            chars = ALL_CHARACTERS[char_class]
            result.append(chars[0])
        else:
            result.append(char)
    
    return ''.join(result)


def as_katakana(text: str) -> str:
    """
    Convert hiragana to katakana.
    
    Args:
        text: Text to convert.
        
    Returns:
        Text with hiragana converted to katakana.
    """
    result = []
    for char in text:
        # First normalize the character
        normal = to_normal_char(char)
        if normal:
            char = normal
        
        # Get character class and convert
        char_class = CHAR_CLASS_HASH.get(char)
        if char_class and char_class in ALL_CHARACTERS:
            # Get the katakana (last character in the pair)
            chars = ALL_CHARACTERS[char_class]
            result.append(chars[-1])
        else:
            result.append(char)
    
    return ''.join(result)


# ============================================================================
# Rendaku (Sequential Voicing)
# ============================================================================

def rendaku(text: str, handakuten: bool = False) -> str:
    """
    Apply rendaku (sequential voicing) to the first character.
    
    Rendaku converts unvoiced consonants to voiced (e.g., か→が).
    
    Args:
        text: Text to modify.
        handakuten: If True, apply handakuten (semi-voicing) instead.
        
    Returns:
        Text with rendaku applied.
    """
    if not text:
        return text
    
    first_char = text[0]
    cc = CHAR_CLASS_HASH.get(first_char)
    
    if not cc:
        return text
    
    use_hash = HANDAKUTEN_HASH if handakuten else DAKUTEN_HASH
    voiced = use_hash.get(cc)
    
    if not voiced:
        return text
    
    # Find the character position in the original class
    orig_chars = KANA_CHARACTERS.get(cc, "")
    pos = orig_chars.find(first_char)
    
    if pos >= 0:
        voiced_chars = KANA_CHARACTERS.get(voiced, "")
        if pos < len(voiced_chars):
            return voiced_chars[pos] + text[1:]
    
    return text


def unrendaku(text: str) -> str:
    """
    Remove rendaku (voicing) from the first character.
    
    Args:
        text: Text to modify.
        
    Returns:
        Text with rendaku removed.
    """
    if not text:
        return text
    
    first_char = text[0]
    cc = CHAR_CLASS_HASH.get(first_char)
    
    if not cc:
        return text
    
    unvoiced = UNDAKUTEN_HASH.get(cc)
    
    if not unvoiced:
        return text
    
    # Find the character position in the original class
    orig_chars = KANA_CHARACTERS.get(cc, "")
    pos = orig_chars.find(first_char)
    
    if pos >= 0:
        unvoiced_chars = KANA_CHARACTERS.get(unvoiced, "")
        if pos < len(unvoiced_chars):
            return unvoiced_chars[pos] + text[1:]
    
    return text


def geminate(text: str) -> str:
    """
    Apply gemination (sokuon) to the last character.
    
    Replaces the last character with っ/ッ.
    
    Args:
        text: Text to modify.
        
    Returns:
        Text with gemination applied.
    """
    if not text:
        return text
    
    # Check if the text ends with katakana
    last_char = text[-1]
    if last_char in FULL_WIDTH_KANA or is_katakana(last_char):
        return text[:-1] + "ッ"
    else:
        return text[:-1] + "っ"


# ============================================================================
# Text Splitting
# ============================================================================

def basic_split(text: str) -> List[Tuple[str, str]]:
    """
    Split text into segments of Japanese and non-Japanese characters.
    
    Args:
        text: Text to split.
        
    Returns:
        List of (type, text) tuples where type is 'word' or 'misc'.
    """
    if not text:
        return []
    
    segments = []
    last_end = 0
    
    for match in _BASIC_SPLIT_PATTERN.finditer(text):
        start, end = match.span()
        
        # Add any non-matching text before this match
        if start > last_end:
            misc_text = text[last_end:start]
            if misc_text:
                segments.append(('misc', misc_text))
        
        # Add the matching Japanese text
        segments.append(('word', match.group()))
        last_end = end
    
    # Add any remaining non-matching text
    if last_end < len(text):
        misc_text = text[last_end:]
        if misc_text:
            segments.append(('misc', misc_text))
    
    return segments


def mora_length(text: str) -> int:
    """
    Calculate the mora length of text.
    
    Modifier characters (small kana, long vowel marker) don't count as separate mora.
    
    Args:
        text: Text to measure.
        
    Returns:
        Mora count.
    """
    modifiers = set("っッぁァぃィぅゥぇェぉォゃャゅュょョー")
    return sum(1 for char in text if char not in modifiers)


# ============================================================================
# Kanji Pattern Matching
# ============================================================================

def kanji_mask(word: str) -> str:
    """
    Create a SQL LIKE mask for a word with kanji replaced by %.
    
    Args:
        word: Word containing kanji.
        
    Returns:
        Mask string with % for each kanji sequence.
    """
    return re.sub(KANJI_REGEX + "+", "%", word)


def kanji_regex(word: str) -> re.Pattern:
    """
    Create a regex pattern for matching kanji readings.
    
    Kanji are replaced with .+ patterns.
    
    Args:
        word: Word containing kanji.
        
    Returns:
        Compiled regex pattern.
    """
    mask = kanji_mask(word)
    pattern_parts = []
    for char in mask:
        if char == '%':
            pattern_parts.append('.+')
        else:
            pattern_parts.append(re.escape(char))
    
    return re.compile('^' + ''.join(pattern_parts) + '$')


def kanji_match(word: str, reading: str) -> bool:
    """
    Check if a reading matches a word with kanji.
    
    Args:
        word: Word containing kanji.
        reading: Proposed reading.
        
    Returns:
        True if the reading could match the word.
    """
    pattern = kanji_regex(word)
    return bool(pattern.match(reading))


def kanji_prefix(word: str) -> str:
    """
    Get the prefix of a word up to and including the last kanji.
    
    Args:
        word: Word to analyze.
        
    Returns:
        Kanji prefix or empty string.
    """
    match = re.match(rf"^.*{KANJI_REGEX}", word)
    return match.group() if match else ""


# ============================================================================
# Utility Functions
# ============================================================================

def destem(word: str, stem: int, char_class: str = 'kana') -> str:
    """
    Remove characters from the end of a word.
    
    Args:
        word: Word to destem.
        stem: Number of characters to remove.
        char_class: Character class to count for stemming.
        
    Returns:
        Destemmed word.
    """
    if stem == 0:
        return word
    
    # Find positions of matching characters from the end
    patterns = {
        'kana': KANA_REGEX,
        'hiragana': HIRAGANA_REGEX,
        'katakana': KATAKANA_REGEX,
    }
    
    pattern = patterns.get(char_class, KANA_REGEX)
    positions = [m.start() for m in re.finditer(pattern, word)]
    
    if len(positions) >= stem:
        cut_pos = positions[-(stem)]
        return word[:cut_pos]
    
    return ""


def safe_subseq(sequence: str, start: int, end: Optional[int] = None) -> Optional[str]:
    """
    Safely get a subsequence of a string.
    
    Args:
        sequence: String to slice.
        start: Start index.
        end: End index (optional).
        
    Returns:
        Substring or None if indices are invalid.
    """
    length = len(sequence)
    if start < 0 or start > length:
        return None
    if end is not None and (end < start or end > length):
        return None
    return sequence[start:end]


def join_with_separator(separator: str, items: List, key=None) -> str:
    """
    Join items with a separator.
    
    Args:
        separator: Separator string.
        items: Items to join.
        key: Optional function to extract string from each item.
        
    Returns:
        Joined string.
    """
    if key:
        return separator.join(key(item) for item in items)
    return separator.join(str(item) for item in items)


def long_vowel_modifier_p(modifier: str, prev_char: str) -> bool:
    """
    Check if a modifier extends a previous vowel.
    
    Args:
        modifier: Modifier character class.
        prev_char: Previous character.
        
    Returns:
        True if the modifier extends the vowel.
    """
    vowel_map = {
        '+a': 'A', '+i': 'I', '+u': 'U', '+e': 'E', '+o': 'O'
    }
    
    vowel = vowel_map.get(modifier)
    if not vowel:
        return False
    
    char_class = get_char_class(prev_char)
    if not isinstance(char_class, str):
        return False
    
    # Check if the character class ends with this vowel
    return char_class.upper().endswith(vowel)


# ============================================================================
# Sentence Splitting
# ============================================================================

# Sentence-ending punctuation marks (Japanese and Western)
SENTENCE_ENDINGS = "。．.！!？?"
SENTENCE_ENDING_QUOTES = "」』】）)\"'»›"

# Pattern to match sentence boundaries
# Matches sentence-ending punctuation optionally followed by closing quotes
_SENTENCE_SPLIT_PATTERN = re.compile(
    rf"([{re.escape(SENTENCE_ENDINGS)}][{re.escape(SENTENCE_ENDING_QUOTES)}]*)"
)


def split_sentences(text: str, keep_punctuation: bool = True) -> List[str]:
    """
    Split Japanese text into sentences.
    
    Splits on sentence-ending punctuation marks (。！？etc.) while handling
    quotation marks and parentheses properly.
    
    Args:
        text: Text to split into sentences.
        keep_punctuation: Whether to keep the punctuation at the end of each sentence.
                         Default True.
        
    Returns:
        List of sentences.
        
    Examples:
        >>> split_sentences("今日は晴れです。明日は雨かもしれません。")
        ['今日は晴れです。', '明日は雨かもしれません。']
        
        >>> split_sentences("「こんにちは！」と言った。")
        ['「こんにちは！」と言った。']
        
        >>> split_sentences("何ですか？分かりません。")
        ['何ですか？', '分かりません。']
    """
    if not text:
        return []
    
    text = text.strip()
    if not text:
        return []
    
    # Track quote depth to avoid splitting inside quotes
    sentences = []
    current = []
    quote_depth = 0
    
    # Opening/closing quote pairs
    open_quotes = "「『【（(\"'«‹"
    close_quotes = "」』】）)\"'»›"
    
    i = 0
    while i < len(text):
        char = text[i]
        current.append(char)
        
        # Track quote depth
        if char in open_quotes:
            quote_depth += 1
        elif char in close_quotes:
            quote_depth = max(0, quote_depth - 1)
        
        # Check for sentence boundary
        if char in SENTENCE_ENDINGS and quote_depth == 0:
            # Look ahead for closing quotes that belong to this sentence
            j = i + 1
            while j < len(text) and text[j] in SENTENCE_ENDING_QUOTES:
                current.append(text[j])
                if text[j] in close_quotes:
                    quote_depth = max(0, quote_depth - 1)
                j += 1
            
            # Complete the sentence
            sentence = ''.join(current)
            if not keep_punctuation:
                # Remove trailing punctuation
                sentence = sentence.rstrip(SENTENCE_ENDINGS + SENTENCE_ENDING_QUOTES)
            
            if sentence.strip():
                sentences.append(sentence)
            
            current = []
            i = j
            continue
        
        i += 1
    
    # Handle any remaining text (sentence without ending punctuation)
    if current:
        sentence = ''.join(current)
        if sentence.strip():
            sentences.append(sentence)
    
    return sentences


def split_paragraphs(text: str) -> List[str]:
    """
    Split text into paragraphs.
    
    Splits on newlines while preserving non-empty paragraphs.
    
    Args:
        text: Text to split.
        
    Returns:
        List of paragraphs.
    """
    if not text:
        return []
    
    # Split on one or more newlines
    paragraphs = re.split(r'\n+', text)
    
    # Filter out empty paragraphs
    return [p.strip() for p in paragraphs if p.strip()]


def count_sentences(text: str) -> int:
    """
    Count the number of sentences in text.
    
    Args:
        text: Text to count sentences in.
        
    Returns:
        Number of sentences.
    """
    return len(split_sentences(text))


def get_first_sentence(text: str) -> str:
    """
    Get the first sentence from text.
    
    Args:
        text: Text to extract from.
        
    Returns:
        First sentence, or empty string if no sentences found.
    """
    sentences = split_sentences(text)
    return sentences[0] if sentences else ""
