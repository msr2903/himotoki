"""
Romanization module for Himotoki.

Provides various romanization methods for Japanese text including
Hepburn (basic, traditional, modified, passport), Kunrei-shiki,
and custom methods.

Mirrors romanize.lisp from the original Ichiran.
"""

import re
import unicodedata
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union

from himotoki.characters import (
    get_char_class, normalize, basic_split, as_hiragana,
    KANA_CHARACTERS, ALL_CHARACTERS, MODIFIER_CHARACTERS,
    CHAR_CLASS_HASH, voice_char
)


# ============================================================================
# Character Class Processing
# ============================================================================

def get_character_classes(word: str) -> List[Union[str, str]]:
    """
    Transform a word into a list of character classes.
    
    Args:
        word: Japanese word (kana).
        
    Returns:
        List of character class identifiers.
    """
    return [get_char_class(char) for char in word]


def process_iteration_characters(cc_list: List[str]) -> List[str]:
    """
    Replace iteration characters in a character class list.
    
    ゝ (iter) repeats the previous character.
    ゞ (iter_v) repeats the previous character with voicing.
    
    Args:
        cc_list: List of character classes.
        
    Returns:
        Processed list with iteration characters resolved.
    """
    result = []
    prev = None
    
    for cc in cc_list:
        if cc == 'iter':
            if prev:
                result.append(prev)
        elif cc == 'iter_v':
            if prev:
                result.append(voice_char(prev))
        else:
            result.append(cc)
            prev = cc
    
    return result


def process_modifiers(cc_list: List[str]) -> List:
    """
    Process modifier characters into a tree structure.
    
    Small kana (ゃ, ゅ, ょ, etc.) and sokuon (っ) are nested
    under their base characters.
    
    Args:
        cc_list: List of character classes.
        
    Returns:
        Nested structure representing modifier relationships.
    """
    result = []
    i = 0
    
    while i < len(cc_list):
        cc = cc_list[i]
        
        if cc == 'sokuon':
            # Sokuon applies to everything after it
            rest = process_modifiers(cc_list[i+1:])
            result.append(('sokuon', rest))
            break
        elif cc in MODIFIER_CHARACTERS or cc.startswith('+'):
            # Modifier modifies the previous element
            if result:
                prev = result.pop()
                result.append((cc, [prev]))
            else:
                result.append(cc)
        else:
            result.append(cc)
        
        i += 1
    
    return result


def leftmost_atom(cc_tree) -> Optional[str]:
    """
    Get the leftmost atomic element from a character class tree.
    
    Args:
        cc_tree: Character class tree structure.
        
    Returns:
        Leftmost character class.
    """
    if not cc_tree:
        return None
    
    first = cc_tree[0] if isinstance(cc_tree, list) else cc_tree
    
    if isinstance(first, str):
        return first
    elif isinstance(first, tuple):
        return leftmost_atom(first[1])
    
    return None


# ============================================================================
# Base Romanization Classes
# ============================================================================

class RomanizationMethod(ABC):
    """Base class for romanization methods."""
    
    @abstractmethod
    def get_base(self, char_class: str) -> str:
        """Get the romanization for a base character class."""
        pass
    
    def apply_modifier(self, modifier: str, cc_tree: List) -> str:
        """Apply a modifier to romanized content."""
        inner = self.romanize_tree(cc_tree)
        
        if modifier == 'sokuon':
            # Double the first consonant
            if inner and inner[0].isalpha():
                return inner[0] + inner
            return inner
        elif modifier == 'long_vowel':
            return inner
        elif modifier.startswith('+'):
            # Small kana modifier
            mod_roma = self.get_base(modifier)
            return inner + mod_roma
        else:
            return inner + modifier.lower()
    
    def romanize_tree(self, cc_tree: List) -> str:
        """Romanize a character class tree."""
        result = []
        
        for item in cc_tree:
            if item is None:
                continue
            elif isinstance(item, str):
                if len(item) == 1 and ord(item) < 128:
                    # ASCII character - keep as-is
                    result.append(item)
                else:
                    # Character class
                    result.append(self.get_base(item))
            elif isinstance(item, tuple):
                modifier, subtree = item
                result.append(self.apply_modifier(modifier, subtree))
        
        return ''.join(result)
    
    def simplify(self, text: str) -> str:
        """Apply simplifications to the romanized text."""
        return text
    
    def romanize(self, word: str) -> str:
        """
        Romanize a Japanese word.
        
        Args:
            word: Japanese word in kana.
            
        Returns:
            Romanized string.
        """
        cc_list = get_character_classes(word)
        cc_list = process_iteration_characters(cc_list)
        cc_tree = process_modifiers(cc_list)
        result = self.romanize_tree(cc_tree)
        return self.simplify(result)


class GenericRomanization(RomanizationMethod):
    """Generic romanization with customizable kana table."""
    
    def __init__(self, kana_table: Optional[Dict[str, str]] = None):
        self.kana_table = kana_table or {}
    
    def get_base(self, char_class: str) -> str:
        return self.kana_table.get(char_class, char_class.lower())


# ============================================================================
# Hepburn Romanization
# ============================================================================

HEPBURN_KANA_TABLE = {
    'a': 'a',      'i': 'i',      'u': 'u',      'e': 'e',      'o': 'o',
    'ka': 'ka',    'ki': 'ki',    'ku': 'ku',    'ke': 'ke',    'ko': 'ko',
    'sa': 'sa',    'shi': 'shi',  'su': 'su',    'se': 'se',    'so': 'so',
    'ta': 'ta',    'chi': 'chi',  'tsu': 'tsu',  'te': 'te',    'to': 'to',
    'na': 'na',    'ni': 'ni',    'nu': 'nu',    'ne': 'ne',    'no': 'no',
    'ha': 'ha',    'hi': 'hi',    'fu': 'fu',    'he': 'he',    'ho': 'ho',
    'ma': 'ma',    'mi': 'mi',    'mu': 'mu',    'me': 'me',    'mo': 'mo',
    'ya': 'ya',                   'yu': 'yu',                   'yo': 'yo',
    'ra': 'ra',    'ri': 'ri',    'ru': 'ru',    're': 're',    'ro': 'ro',
    'wa': 'wa',    'wi': 'wi',                   'we': 'we',    'wo': 'wo',
    'n': "n'",
    'ga': 'ga',    'gi': 'gi',    'gu': 'gu',    'ge': 'ge',    'go': 'go',
    'za': 'za',    'ji': 'ji',    'zu': 'zu',    'ze': 'ze',    'zo': 'zo',
    'da': 'da',    'dji': 'ji',   'dzu': 'zu',   'de': 'de',    'do': 'do',
    'ba': 'ba',    'bi': 'bi',    'bu': 'bu',    'be': 'be',    'bo': 'bo',
    'pa': 'pa',    'pi': 'pi',    'pu': 'pu',    'pe': 'pe',    'po': 'po',
    '+a': 'a',     '+i': 'i',     '+u': 'u',     '+e': 'e',     '+o': 'o',
    '+ya': 'ya',                  '+yu': 'yu',                  '+yo': 'yo',
    'vu': 'vu',    '+wa': 'wa',
    'sokuon': '',
    'long_vowel': '',
}


class GenericHepburn(GenericRomanization):
    """Generic Hepburn romanization."""
    
    def __init__(self):
        super().__init__(HEPBURN_KANA_TABLE.copy())
    
    def apply_modifier(self, modifier: str, cc_tree: List) -> str:
        if modifier == 'sokuon':
            atom = leftmost_atom(cc_tree)
            inner = self.romanize_tree(cc_tree)
            # Special case for chi -> tchi
            if atom == 'chi':
                return 't' + inner
            # Double the first consonant
            if inner and inner[0].isalpha():
                return inner[0] + inner
            return inner
        elif modifier == '+ya':
            first = cc_tree[0] if cc_tree else None
            if first == 'shi':
                return 'sha'
            elif first == 'chi':
                return 'cha'
            elif first in ('ji', 'dji'):
                return 'ja'
            else:
                return super().apply_modifier(modifier, cc_tree)
        elif modifier == '+yu':
            first = cc_tree[0] if cc_tree else None
            if first == 'shi':
                return 'shu'
            elif first == 'chi':
                return 'chu'
            elif first in ('ji', 'dji'):
                return 'ju'
            else:
                return super().apply_modifier(modifier, cc_tree)
        elif modifier == '+yo':
            first = cc_tree[0] if cc_tree else None
            if first == 'shi':
                return 'sho'
            elif first == 'chi':
                return 'cho'
            elif first in ('ji', 'dji'):
                return 'jo'
            else:
                return super().apply_modifier(modifier, cc_tree)
        else:
            return super().apply_modifier(modifier, cc_tree)
    
    def simplify(self, text: str) -> str:
        # Remove apostrophe after n if not followed by a vowel or y
        return re.sub(r"n'([^aiueoy]|$)", r"n\1", text)


class SimplifiedHepburn(GenericHepburn):
    """Hepburn with long vowel simplification."""
    
    def __init__(self, simplifications: Optional[Dict[str, str]] = None):
        super().__init__()
        self.simplifications = simplifications or {}
    
    def simplify(self, text: str) -> str:
        text = super().simplify(text)
        for pattern, replacement in self.simplifications.items():
            text = text.replace(pattern, replacement)
        return text


class TraditionalHepburn(SimplifiedHepburn):
    """Traditional Hepburn with macrons for long vowels."""
    
    def __init__(self):
        super().__init__({
            'oo': 'ō', 'ou': 'ō', 
            'uu': 'ū',
        })
    
    def simplify(self, text: str) -> str:
        text = super().simplify(text)
        # Replace n' before vowels with n-
        text = re.sub(r"n'([aiueoy])", r"n-\1", text)
        # Replace n before m, b, p with m
        text = re.sub(r"n([mbp])", r"m\1", text)
        return text


class ModifiedHepburn(SimplifiedHepburn):
    """Modified Hepburn with all long vowels marked."""
    
    def __init__(self):
        super().__init__({
            'oo': 'ō', 'ou': 'ō',
            'uu': 'ū',
            'aa': 'ā',
            'ee': 'ē',
        })
        # wo -> o in modified Hepburn
        self.kana_table['wo'] = 'o'


class PassportHepburn(SimplifiedHepburn):
    """Passport-style Hepburn romanization."""
    
    def __init__(self):
        super().__init__({
            'oo': 'oh', 'ou': 'oh',
            'uu': 'u',
        })


# ============================================================================
# Kunrei-shiki Romanization
# ============================================================================

KUNREI_KANA_TABLE = {
    'a': 'a',      'i': 'i',      'u': 'u',      'e': 'e',      'o': 'o',
    'ka': 'ka',    'ki': 'ki',    'ku': 'ku',    'ke': 'ke',    'ko': 'ko',
    'sa': 'sa',    'shi': 'si',   'su': 'su',    'se': 'se',    'so': 'so',
    'ta': 'ta',    'chi': 'ti',   'tsu': 'tu',   'te': 'te',    'to': 'to',
    'na': 'na',    'ni': 'ni',    'nu': 'nu',    'ne': 'ne',    'no': 'no',
    'ha': 'ha',    'hi': 'hi',    'fu': 'hu',    'he': 'he',    'ho': 'ho',
    'ma': 'ma',    'mi': 'mi',    'mu': 'mu',    'me': 'me',    'mo': 'mo',
    'ya': 'ya',                   'yu': 'yu',                   'yo': 'yo',
    'ra': 'ra',    'ri': 'ri',    'ru': 'ru',    're': 're',    'ro': 'ro',
    'wa': 'wa',    'wi': 'i',                    'we': 'e',     'wo': 'o',
    'n': "n'",
    'ga': 'ga',    'gi': 'gi',    'gu': 'gu',    'ge': 'ge',    'go': 'go',
    'za': 'za',    'ji': 'zi',    'zu': 'zu',    'ze': 'ze',    'zo': 'zo',
    'da': 'da',    'dji': 'zi',   'dzu': 'zu',   'de': 'de',    'do': 'do',
    'ba': 'ba',    'bi': 'bi',    'bu': 'bu',    'be': 'be',    'bo': 'bo',
    'pa': 'pa',    'pi': 'pi',    'pu': 'pu',    'pe': 'pe',    'po': 'po',
    '+a': 'a',     '+i': 'i',     '+u': 'u',     '+e': 'e',     '+o': 'o',
    '+ya': 'ya',                  '+yu': 'yu',                  '+yo': 'yo',
    'vu': 'vu',    '+wa': 'wa',
    'sokuon': '',
    'long_vowel': '',
}


class KunreiShiki(GenericRomanization):
    """Kunrei-shiki romanization."""
    
    def __init__(self):
        super().__init__(KUNREI_KANA_TABLE.copy())
    
    def simplify(self, text: str) -> str:
        text = re.sub(r"n'([^aiueoy]|$)", r"n\1", text)
        # Long vowel marks
        text = text.replace('oo', 'ô')
        text = text.replace('ou', 'ô')
        text = text.replace('uu', 'û')
        return text


# ============================================================================
# Default Methods
# ============================================================================

HEPBURN_BASIC = GenericHepburn()
HEPBURN_SIMPLE = SimplifiedHepburn({'oo': 'o', 'ou': 'o', 'uu': 'u'})
HEPBURN_PASSPORT = PassportHepburn()
HEPBURN_TRADITIONAL = TraditionalHepburn()
HEPBURN_MODIFIED = ModifiedHepburn()
KUNREI_SIKI = KunreiShiki()

DEFAULT_METHOD = HEPBURN_TRADITIONAL

# Method name to object mapping
ROMANIZATION_METHODS = {
    'hepburn': HEPBURN_TRADITIONAL,
    'traditional': HEPBURN_TRADITIONAL,
    'basic': HEPBURN_BASIC,
    'simplified': HEPBURN_SIMPLE,
    'simple': HEPBURN_SIMPLE,
    'passport': HEPBURN_PASSPORT,
    'modified': HEPBURN_MODIFIED,
    'kunrei': KUNREI_SIKI,
    'kunrei-shiki': KUNREI_SIKI,
    'nihon-shiki': KUNREI_SIKI,
}


def get_romanization_method(name: Union[str, RomanizationMethod]) -> RomanizationMethod:
    """
    Get a romanization method by name.
    
    Args:
        name: Method name or method object.
        
    Returns:
        RomanizationMethod object.
    """
    if isinstance(name, RomanizationMethod):
        return name
    
    name_lower = name.lower() if isinstance(name, str) else 'hepburn'
    return ROMANIZATION_METHODS.get(name_lower, DEFAULT_METHOD)


# ============================================================================
# Special Word Handling
# ============================================================================

SPECIAL_ROMANIZATIONS = {
    'っ': '!',
    'ー': '~',
}


def romanize_special(word: str, method: RomanizationMethod) -> Optional[str]:
    """Handle special word romanizations."""
    return SPECIAL_ROMANIZATIONS.get(word)


# ============================================================================
# Hint Processing
# ============================================================================

# Hints are used to indicate reading annotations in kanji words
HINT_PATTERN = re.compile(r'\[([^\]]+)\]')


def process_hints(word: str) -> str:
    """
    Process reading hints in a word.
    
    Hints are in the format [reading] and indicate the reading for the
    preceding kanji.
    
    Args:
        word: Word potentially containing hints.
        
    Returns:
        Word with hints processed.
    """
    # For now, just strip the hints and use them for display
    return HINT_PATTERN.sub('', word)


def strip_hints(word: str) -> str:
    """Remove all hints from a word."""
    return HINT_PATTERN.sub('', word)


# ============================================================================
# Main Romanization Functions
# ============================================================================

def romanize_word(word: str, 
                  method: Union[str, RomanizationMethod] = DEFAULT_METHOD,
                  original_spelling: Optional[str] = None,
                  do_normalize: bool = True) -> str:
    """
    Romanize a single Japanese word.
    
    Args:
        word: Japanese word to romanize.
        method: Romanization method name or object.
        original_spelling: Original spelling (for special handling).
        do_normalize: Whether to normalize the input first.
        
    Returns:
        Romanized string.
    """
    # Resolve method name to object
    method = get_romanization_method(method)
    
    if do_normalize:
        word = normalize(word)
    
    # Check for special romanizations
    special = romanize_special(original_spelling or word, method)
    if special:
        return special
    
    # Process hints
    word = process_hints(word)
    
    return method.romanize(word)


def join_parts(parts: List[str]) -> str:
    """
    Join romanized parts with appropriate spacing.
    
    Args:
        parts: List of romanized segments.
        
    Returns:
        Joined string with proper spacing.
    """
    result = []
    last_space = True
    
    for part in parts:
        if not part:
            continue
        
        # Add space before alphanumeric if previous part didn't end with space
        if (not last_space and 
            part[0].isalnum()):
            result.append(' ')
        
        result.append(part)
        
        if part:
            last_space = unicodedata.category(part[-1]).startswith('Z')
    
    return ''.join(result)


def romanize(text: str, 
             method: Union[str, RomanizationMethod] = DEFAULT_METHOD,
             with_info: bool = False) -> Union[str, Tuple[str, List]]:
    """
    Romanize a Japanese sentence.
    
    Args:
        text: Japanese text to romanize.
        method: Romanization method name or object.
        with_info: If True, also return word information.
        
    Returns:
        Romanized string, or tuple of (string, info) if with_info is True.
    """
    # Resolve method name to object
    method = get_romanization_method(method)
    
    text = normalize(text)
    
    parts = []
    definitions = []
    
    for seg_type, seg_text in basic_split(text):
        if seg_type == 'word':
            # For now, just romanize directly without dictionary lookup
            # (dict.py will provide the proper segmentation)
            rom = romanize_word(seg_text, method=method)
            parts.append(rom)
            
            if with_info:
                definitions.append((rom, seg_text))
        else:
            parts.append(seg_text)
    
    result = join_parts(parts)
    
    if with_info:
        return result, definitions
    return result


def romanize_kana(kana: str, method: RomanizationMethod = DEFAULT_METHOD) -> str:
    """
    Romanize a kana string (convenience function).
    
    Args:
        kana: Kana string to romanize.
        method: Romanization method.
        
    Returns:
        Romanized string.
    """
    return method.romanize(kana)


# ============================================================================
# Method Selection Helpers
# ============================================================================

def get_method(name: str) -> RomanizationMethod:
    """
    Get a romanization method by name.
    
    Args:
        name: Method name ('hepburn', 'traditional', 'modified', 
              'passport', 'simple', 'kunrei').
              
    Returns:
        RomanizationMethod instance.
    """
    methods = {
        'hepburn': HEPBURN_BASIC,
        'basic': HEPBURN_BASIC,
        'simple': HEPBURN_SIMPLE,
        'passport': HEPBURN_PASSPORT,
        'traditional': HEPBURN_TRADITIONAL,
        'modified': HEPBURN_MODIFIED,
        'kunrei': KUNREI_SIKI,
        'kunrei-shiki': KUNREI_SIKI,
    }
    
    return methods.get(name.lower(), DEFAULT_METHOD)
