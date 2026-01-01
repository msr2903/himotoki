"""
Deromanize module for Himotoki.

Converts romanized Japanese (romaji) to kana.

Mirrors deromanize.lisp from the original Ichiran.
"""

import os
import csv
from typing import Dict, List, Optional, Tuple

from himotoki.settings import DATA_DIR


# ============================================================================
# Romaji Mapping
# ============================================================================

# Romaji to kana mapping
ROMAJI_MAP: Dict[str, str] = {}

# Romaji to kana mapping (katakana)
ROMAJI_MAP_KATAKANA: Dict[str, str] = {}


def load_romaji_map():
    """Load romaji mapping from CSV file."""
    global ROMAJI_MAP, ROMAJI_MAP_KATAKANA
    
    map_file = os.path.join(DATA_DIR, 'romaji-map.csv')
    
    if not os.path.exists(map_file):
        # Use built-in mapping
        _init_builtin_map()
        return
    
    ROMAJI_MAP = {}
    ROMAJI_MAP_KATAKANA = {}
    
    with open(map_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        for row in reader:
            if len(row) >= 2:
                romaji = row[0].strip().lower()
                hiragana = row[1].strip()
                
                if romaji and hiragana:
                    ROMAJI_MAP[romaji] = hiragana
                    
                    # Generate katakana version
                    katakana = ''.join(
                        chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c
                        for c in hiragana
                    )
                    ROMAJI_MAP_KATAKANA[romaji] = katakana


def _init_builtin_map():
    """Initialize built-in romaji mapping."""
    global ROMAJI_MAP, ROMAJI_MAP_KATAKANA
    
    # Basic hiragana
    basic = {
        # Vowels
        'a': 'あ', 'i': 'い', 'u': 'う', 'e': 'え', 'o': 'お',
        
        # K-row
        'ka': 'か', 'ki': 'き', 'ku': 'く', 'ke': 'け', 'ko': 'こ',
        'ga': 'が', 'gi': 'ぎ', 'gu': 'ぐ', 'ge': 'げ', 'go': 'ご',
        
        # S-row
        'sa': 'さ', 'si': 'し', 'su': 'す', 'se': 'せ', 'so': 'そ',
        'sha': 'しゃ', 'shi': 'し', 'shu': 'しゅ', 'she': 'しぇ', 'sho': 'しょ',
        'za': 'ざ', 'zi': 'じ', 'zu': 'ず', 'ze': 'ぜ', 'zo': 'ぞ',
        'ja': 'じゃ', 'ji': 'じ', 'ju': 'じゅ', 'je': 'じぇ', 'jo': 'じょ',
        
        # T-row
        'ta': 'た', 'ti': 'ち', 'tu': 'つ', 'te': 'て', 'to': 'と',
        'chi': 'ち', 'tsu': 'つ',
        'cha': 'ちゃ', 'chu': 'ちゅ', 'che': 'ちぇ', 'cho': 'ちょ',
        'da': 'だ', 'di': 'ぢ', 'du': 'づ', 'de': 'で', 'do': 'ど',
        
        # N-row
        'na': 'な', 'ni': 'に', 'nu': 'ぬ', 'ne': 'ね', 'no': 'の',
        'nya': 'にゃ', 'nyu': 'にゅ', 'nyo': 'にょ',
        
        # H-row
        'ha': 'は', 'hi': 'ひ', 'hu': 'ふ', 'he': 'へ', 'ho': 'ほ',
        'fu': 'ふ',
        'hya': 'ひゃ', 'hyu': 'ひゅ', 'hyo': 'ひょ',
        'ba': 'ば', 'bi': 'び', 'bu': 'ぶ', 'be': 'べ', 'bo': 'ぼ',
        'bya': 'びゃ', 'byu': 'びゅ', 'byo': 'びょ',
        'pa': 'ぱ', 'pi': 'ぴ', 'pu': 'ぷ', 'pe': 'ぺ', 'po': 'ぽ',
        'pya': 'ぴゃ', 'pyu': 'ぴゅ', 'pyo': 'ぴょ',
        
        # M-row
        'ma': 'ま', 'mi': 'み', 'mu': 'む', 'me': 'め', 'mo': 'も',
        'mya': 'みゃ', 'myu': 'みゅ', 'myo': 'みょ',
        
        # Y-row
        'ya': 'や', 'yu': 'ゆ', 'yo': 'よ',
        
        # R-row
        'ra': 'ら', 'ri': 'り', 'ru': 'る', 're': 'れ', 'ro': 'ろ',
        'rya': 'りゃ', 'ryu': 'りゅ', 'ryo': 'りょ',
        
        # W-row
        'wa': 'わ', 'wi': 'ゐ', 'we': 'ゑ', 'wo': 'を',
        
        # N
        'n': 'ん', "n'": 'ん',
        
        # Small vowels
        'xa': 'ぁ', 'xi': 'ぃ', 'xu': 'ぅ', 'xe': 'ぇ', 'xo': 'ぉ',
        'la': 'ぁ', 'li': 'ぃ', 'lu': 'ぅ', 'le': 'ぇ', 'lo': 'ぉ',
        
        # Small tsu
        'xtu': 'っ', 'ltu': 'っ', 'xtsu': 'っ', 'ltsu': 'っ',
        
        # Small ya/yu/yo
        'xya': 'ゃ', 'xyu': 'ゅ', 'xyo': 'ょ',
        'lya': 'ゃ', 'lyu': 'ゅ', 'lyo': 'ょ',
        
        # Long vowel
        '-': 'ー',
        
        # Additional combinations
        'kya': 'きゃ', 'kyu': 'きゅ', 'kyo': 'きょ',
        'gya': 'ぎゃ', 'gyu': 'ぎゅ', 'gyo': 'ぎょ',
        'sya': 'しゃ', 'syu': 'しゅ', 'syo': 'しょ',
        'zya': 'じゃ', 'zyu': 'じゅ', 'zyo': 'じょ',
        'tya': 'ちゃ', 'tyu': 'ちゅ', 'tyo': 'ちょ',
        'dya': 'ぢゃ', 'dyu': 'ぢゅ', 'dyo': 'ぢょ',
        
        # Foreign sounds
        'fa': 'ふぁ', 'fi': 'ふぃ', 'fe': 'ふぇ', 'fo': 'ふぉ',
        'ti': 'てぃ', 'di': 'でぃ',
        'va': 'ゔぁ', 'vi': 'ゔぃ', 'vu': 'ゔ', 've': 'ゔぇ', 'vo': 'ゔぉ',
        'wi': 'うぃ', 'we': 'うぇ',
        'tsa': 'つぁ', 'tsi': 'つぃ', 'tse': 'つぇ', 'tso': 'つぉ',
    }
    
    ROMAJI_MAP = basic
    
    # Generate katakana version
    ROMAJI_MAP_KATAKANA = {}
    for romaji, hiragana in ROMAJI_MAP.items():
        katakana = ''.join(
            chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c
            for c in hiragana
        )
        ROMAJI_MAP_KATAKANA[romaji] = katakana


# ============================================================================
# Romaji to Kana Conversion
# ============================================================================

def romaji_to_hiragana(text: str) -> str:
    """
    Convert romanized text to hiragana.
    
    Args:
        text: Romanized Japanese text.
        
    Returns:
        Text converted to hiragana.
    """
    if not ROMAJI_MAP:
        load_romaji_map()
    
    return _convert_romaji(text, ROMAJI_MAP)


def romaji_to_katakana(text: str) -> str:
    """
    Convert romanized text to katakana.
    
    Args:
        text: Romanized Japanese text.
        
    Returns:
        Text converted to katakana.
    """
    if not ROMAJI_MAP_KATAKANA:
        load_romaji_map()
    
    return _convert_romaji(text, ROMAJI_MAP_KATAKANA)


def _convert_romaji(text: str, mapping: Dict[str, str]) -> str:
    """
    Convert romanized text using the given mapping.
    
    Args:
        text: Romanized text.
        mapping: Romaji to kana mapping.
        
    Returns:
        Converted text.
    """
    result = []
    i = 0
    text_lower = text.lower()
    
    while i < len(text_lower):
        # Handle gemination (double consonant -> っ)
        if i + 1 < len(text_lower) and text_lower[i] == text_lower[i + 1]:
            c = text_lower[i]
            if c not in 'aeioun':  # Consonant doubling
                if 'っ' in mapping.get('xtu', 'っ'):
                    result.append(mapping.get('xtu', 'っ'))
                else:
                    result.append('っ')
                i += 1
                continue
        
        # Try matching longest possible romaji
        matched = False
        for length in range(4, 0, -1):
            if i + length > len(text_lower):
                continue
            
            chunk = text_lower[i:i + length]
            
            if chunk in mapping:
                result.append(mapping[chunk])
                i += length
                matched = True
                break
        
        if not matched:
            # Keep the character as-is
            result.append(text[i])
            i += 1
    
    return ''.join(result)


# ============================================================================
# Suggestions
# ============================================================================

def romaji_suggest(prefix: str, limit: int = 10) -> List[Tuple[str, str]]:
    """
    Get romaji completion suggestions.
    
    Args:
        prefix: Romaji prefix to complete.
        limit: Maximum suggestions.
        
    Returns:
        List of (romaji, kana) pairs.
    """
    if not ROMAJI_MAP:
        load_romaji_map()
    
    prefix_lower = prefix.lower()
    results = []
    
    for romaji, kana in sorted(ROMAJI_MAP.items()):
        if romaji.startswith(prefix_lower):
            results.append((romaji, kana))
            if len(results) >= limit:
                break
    
    return results


# ============================================================================
# Extended Romanization Patterns
# ============================================================================

# Alternative romanization patterns
ALT_PATTERNS: Dict[str, List[str]] = {
    'shi': ['si'],
    'chi': ['ti', 'tyi'],
    'tsu': ['tu'],
    'fu': ['hu'],
    'sha': ['sya'],
    'shu': ['syu'],
    'sho': ['syo'],
    'cha': ['tya', 'cya'],
    'chu': ['tyu', 'cyu'],
    'cho': ['tyo', 'cyo'],
    'ja': ['zya', 'jya', 'dya'],
    'ju': ['zyu', 'jyu', 'dyu'],
    'jo': ['zyo', 'jyo', 'dyo'],
    'ji': ['zi', 'di'],
}


def normalize_romaji(text: str) -> str:
    """
    Normalize alternative romanization patterns.
    
    Args:
        text: Romanized text with potentially non-standard romanization.
        
    Returns:
        Normalized romanization.
    """
    text_lower = text.lower()
    
    # Build reverse mapping
    reverse_map = {}
    for standard, alts in ALT_PATTERNS.items():
        for alt in alts:
            reverse_map[alt] = standard
    
    # Replace alternatives with standard forms
    result = text_lower
    for alt, standard in sorted(reverse_map.items(), key=lambda x: -len(x[0])):
        result = result.replace(alt, standard)
    
    return result


# ============================================================================
# Romaji Detection
# ============================================================================

def is_romaji(text: str) -> bool:
    """
    Check if text appears to be romanized Japanese.
    
    Args:
        text: Text to check.
        
    Returns:
        True if text looks like romaji.
    """
    if not text:
        return False
    
    # Check if it's all ASCII letters
    text_clean = text.replace('-', '').replace("'", '').replace(' ', '')
    if not text_clean.isalpha():
        return False
    
    # Check for common romaji patterns
    text_lower = text.lower()
    
    # Count vowels
    vowel_count = sum(1 for c in text_lower if c in 'aeiou')
    consonant_count = len(text_clean) - vowel_count
    
    # Japanese has high vowel-to-consonant ratio
    if len(text_clean) > 3:
        ratio = vowel_count / len(text_clean)
        if ratio < 0.3 or ratio > 0.8:
            return False
    
    return True


def detect_and_convert(text: str) -> str:
    """
    Detect if text is romaji and convert to hiragana if so.
    
    Args:
        text: Text to process.
        
    Returns:
        Converted text if romaji, original otherwise.
    """
    if is_romaji(text):
        return romaji_to_hiragana(text)
    return text


# Initialize mapping
load_romaji_map()
