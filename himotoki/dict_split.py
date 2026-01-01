"""
Dictionary split module for Himotoki.

Handles compound word splitting, word boundary detection,
and predefined splits/hints.

Mirrors dict-split.lisp from the original Ichiran.

This module contains:
1. Compound word detection (find_split_points, analyze_compound)
2. Phonetic variations (rendaku, gemination)
3. SimpleSplit definitions (def-simple-split from Ichiran)
4. Hint system for readings
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from himotoki.characters import (
    as_hiragana, is_kana, is_kanji, 
    rendaku, unrendaku, geminate,
    count_char_class
)


# ============================================================================
# Simple Split Definitions (1:1 from Ichiran's def-simple-split)
# ============================================================================

@dataclass
class SimpleSplit:
    """A predefined split point in a compound expression."""
    text: str
    parts: List[str]
    readings: Optional[List[str]] = None
    score_bonus: int = 0


# Split registry: text -> SimpleSplit
SPLIT_REGISTRY: Dict[str, SimpleSplit] = {}


def def_simple_split(text: str, parts: List[str], 
                     readings: Optional[List[str]] = None,
                     score_bonus: int = 0):
    """
    Define a simple split for a compound expression.
    
    This mirrors Ichiran's:
        (def-simple-split text ("part1" "part2" ...))
    """
    split = SimpleSplit(
        text=text,
        parts=parts,
        readings=readings,
        score_bonus=score_bonus
    )
    SPLIT_REGISTRY[text] = split


def get_simple_split(text: str) -> Optional[SimpleSplit]:
    """Get predefined split for text if available."""
    return SPLIT_REGISTRY.get(text)


def init_simple_splits():
    """Initialize all predefined splits."""
    global SPLIT_REGISTRY
    SPLIT_REGISTRY.clear()
    
    # ==== GREETING / TIME EXPRESSIONS ====
    def_simple_split("今日は", ["今日", "は"])
    def_simple_split("今晩は", ["今晩", "は"])
    
    # ==== COMMON COMPOUND PARTICLES ====
    def_simple_split("について", ["に", "ついて"])
    def_simple_split("によって", ["に", "よって"])
    def_simple_split("にとって", ["に", "とって"])
    def_simple_split("において", ["に", "おいて"])
    def_simple_split("に対して", ["に", "対して"])
    def_simple_split("に関して", ["に", "関して"])
    def_simple_split("として", ["と", "して"])
    def_simple_split("という", ["と", "いう"])
    def_simple_split("といった", ["と", "いった"])
    def_simple_split("とする", ["と", "する"])
    def_simple_split("からこそ", ["から", "こそ"])
    
    # ==== CONJUNCTIONS ====
    def_simple_split("だから", ["だ", "から"])
    def_simple_split("ですから", ["です", "から"])
    def_simple_split("それから", ["それ", "から"])
    
    # ==== AUX VERB CHAINS ====
    def_simple_split("ている", ["て", "いる"])
    def_simple_split("ていた", ["て", "いた"])
    def_simple_split("ています", ["て", "います"])
    def_simple_split("ていました", ["て", "いました"])
    def_simple_split("ておく", ["て", "おく"])
    def_simple_split("ておいた", ["て", "おいた"])
    def_simple_split("てしまう", ["て", "しまう"])
    def_simple_split("てしまった", ["て", "しまった"])
    def_simple_split("てくる", ["て", "くる"])
    def_simple_split("てきた", ["て", "きた"])
    def_simple_split("ていく", ["て", "いく"])
    def_simple_split("ていった", ["て", "いった"])
    def_simple_split("てみる", ["て", "みる"])
    def_simple_split("てみた", ["て", "みた"])
    def_simple_split("てあげる", ["て", "あげる"])
    def_simple_split("てくれる", ["て", "くれる"])
    def_simple_split("てもらう", ["て", "もらう"])
    def_simple_split("てください", ["て", "ください"])
    
    # ==== COMMON EXPRESSIONS ====
    def_simple_split("かもしれない", ["かも", "しれない"])
    def_simple_split("かもしれません", ["かも", "しれません"])
    def_simple_split("なければならない", ["なければ", "ならない"])
    def_simple_split("なければなりません", ["なければ", "なりません"])
    def_simple_split("ことができる", ["こと", "が", "できる"])
    def_simple_split("ことができます", ["こと", "が", "できます"])
    def_simple_split("ようにする", ["よう", "に", "する"])
    def_simple_split("ようになる", ["よう", "に", "なる"])
    def_simple_split("ことにする", ["こと", "に", "する"])
    def_simple_split("ことになる", ["こと", "に", "なる"])
    
    # ==== IDIOMATIC SPLITS ====
    def_simple_split("気がいい", ["気", "が", "いい"])
    def_simple_split("気が悪い", ["気", "が", "悪い"])
    def_simple_split("気がする", ["気", "が", "する"])
    def_simple_split("気になる", ["気", "に", "なる"])
    def_simple_split("目がいい", ["目", "が", "いい"])
    def_simple_split("目が悪い", ["目", "が", "悪い"])
    
    # ==== SENTENCE ENDINGS ====
    def_simple_split("のです", ["の", "です"])
    def_simple_split("のだ", ["の", "だ"])
    def_simple_split("んです", ["ん", "です"])
    def_simple_split("んだ", ["ん", "だ"])


# ============================================================================
# Hint System (from Ichiran's hint definitions)
# ============================================================================

@dataclass 
class Hint:
    """A reading/romanization hint for a word."""
    text: str
    reading: str
    alternative_readings: List[str] = field(default_factory=list)
    notes: str = ""


HINT_REGISTRY: Dict[str, Hint] = {}


def def_hint(text: str, reading: str, 
             alternatives: Optional[List[str]] = None,
             notes: str = ""):
    """Define a hint for a word's reading."""
    hint = Hint(
        text=text,
        reading=reading,
        alternative_readings=alternatives or [],
        notes=notes
    )
    HINT_REGISTRY[text] = hint


def get_hint(text: str) -> Optional[Hint]:
    """Get hint for text if available."""
    return HINT_REGISTRY.get(text)


def init_hints():
    """Initialize reading hints."""
    global HINT_REGISTRY
    HINT_REGISTRY.clear()
    
    # Common irregular readings
    def_hint("今日", "きょう", ["こんにち"])
    def_hint("明日", "あした", ["あす", "みょうにち"])
    def_hint("昨日", "きのう", ["さくじつ"])
    def_hint("一人", "ひとり", ["いちにん"])
    def_hint("二人", "ふたり", ["ににん"])
    def_hint("大人", "おとな", ["たいじん"])
    def_hint("下手", "へた", ["したて"])
    def_hint("上手", "じょうず", ["うわて"])


# ============================================================================
# Compound Word Detection
# ============================================================================

@dataclass
class SplitPoint:
    """A potential split point in a compound word."""
    position: int
    score: int
    left: str
    right: str
    transform: Optional[str] = None  # rendaku, geminate, etc.


def find_split_points(word: str) -> List[SplitPoint]:
    """
    Find potential split points in a compound word.
    
    Args:
        word: Word to analyze.
        
    Returns:
        List of potential split points.
    """
    if len(word) < 2:
        return []
    
    splits = []
    
    # Look for kanji-kanji boundaries
    for i in range(1, len(word)):
        left = word[:i]
        right = word[i:]
        
        if not left or not right:
            continue
        
        # Both parts should have substance
        if len(left) < 1 or len(right) < 1:
            continue
        
        # Check for kanji at boundary
        left_last_kanji = is_kanji(left[-1])
        right_first_kanji = is_kanji(right[0])
        
        score = 0
        
        # Kanji-kanji boundary is strong indicator
        if left_last_kanji and right_first_kanji:
            score += 10
        
        # Both parts have kanji
        if count_char_class(left, 'kanji') > 0:
            score += 5
        if count_char_class(right, 'kanji') > 0:
            score += 5
        
        if score > 0:
            splits.append(SplitPoint(
                position=i,
                score=score,
                left=left,
                right=right
            ))
    
    # Sort by score
    splits.sort(key=lambda x: x.score, reverse=True)
    
    return splits


def try_phonetic_variations(word: str, position: int) -> List[Tuple[str, str, str]]:
    """
    Generate phonetic variations at a split point.
    
    Handles rendaku (voicing), gemination (っ), etc.
    
    Args:
        word: Word to analyze.
        position: Split position.
        
    Returns:
        List of (left, right, transform_name) tuples.
    """
    left = word[:position]
    right = word[position:]
    
    variations = [(left, right, None)]
    
    if not right:
        return variations
    
    # Try un-rendaku (voicing) on the right part
    for unr in unrendaku(right[0]):
        new_right = unr + right[1:]
        if new_right != right:
            variations.append((left, new_right, 'rendaku'))
    
    # Try un-gemination (remove っ)
    if right.startswith('っ') and len(right) > 1:
        new_right = right[1:]
        variations.append((left, new_right, 'gemination'))
    
    return variations


# ============================================================================
# Word Combination
# ============================================================================

def join_with_rendaku(left: str, right: str) -> str:
    """
    Join two words applying rendaku if appropriate.
    
    Args:
        left: Left component.
        right: Right component.
        
    Returns:
        Joined word.
    """
    if not left or not right:
        return left + right
    
    # Apply rendaku to first character of right
    right_first_rendaku = rendaku(right[0])
    if right_first_rendaku != right[0]:
        return left + right_first_rendaku + right[1:]
    
    return left + right


def join_with_gemination(left: str, right: str) -> str:
    """
    Join two words applying gemination if appropriate.
    
    Args:
        left: Left component.
        right: Right component.
        
    Returns:
        Joined word.
    """
    if not left or not right:
        return left + right
    
    return left + 'っ' + right


# ============================================================================
# Reading Matching
# ============================================================================

def match_reading_parts(kanji: str, reading: str, 
                        known_readings: Dict[str, List[str]]) -> Optional[List[Tuple[str, str]]]:
    """
    Try to match kanji characters with reading parts.
    
    Args:
        kanji: Kanji string.
        reading: Full reading in kana.
        known_readings: Dict mapping kanji to list of known readings.
        
    Returns:
        List of (kanji, reading) pairs if match found, None otherwise.
    """
    if not kanji or not reading:
        return None
    
    # If it's all kana, trivial match
    if is_kana(kanji):
        if as_hiragana(kanji) == as_hiragana(reading):
            return [(kanji, reading)]
        return None
    
    # Find kanji characters
    result = []
    reading_pos = 0
    
    for i, char in enumerate(kanji):
        if is_kana(char):
            # Match the kana directly
            hira_char = as_hiragana(char)
            if reading_pos < len(reading) and as_hiragana(reading[reading_pos]) == hira_char:
                result.append((char, reading[reading_pos]))
                reading_pos += 1
            else:
                return None
        elif is_kanji(char):
            # Need to find matching reading
            if char not in known_readings or not known_readings[char]:
                return None
            
            found = False
            for possible_reading in sorted(known_readings[char], key=len, reverse=True):
                if reading[reading_pos:].startswith(possible_reading):
                    result.append((char, possible_reading))
                    reading_pos += len(possible_reading)
                    found = True
                    break
            
            if not found:
                return None
    
    # Check we consumed all the reading
    if reading_pos != len(reading):
        return None
    
    return result


# ============================================================================
# Compound Word Analysis
# ============================================================================

@dataclass
class CompoundAnalysis:
    """Analysis of a compound word."""
    components: List[str]
    readings: List[str]
    transforms: List[Optional[str]]
    confidence: float


def analyze_compound(word: str, reading: str) -> Optional[CompoundAnalysis]:
    """
    Analyze a potential compound word.
    
    Args:
        word: Word to analyze.
        reading: Reading of the word.
        
    Returns:
        CompoundAnalysis if compound detected, None otherwise.
    """
    splits = find_split_points(word)
    
    if not splits:
        return None
    
    best_analysis = None
    best_confidence = 0.0
    
    for split in splits[:5]:  # Try top 5 candidates
        variations = try_phonetic_variations(word, split.position)
        
        for left, right, transform in variations:
            # Try to find dictionary entries for both parts
            # This is a simplified check - full version uses database
            
            confidence = split.score / 20.0  # Normalize to 0-1
            
            if transform:
                confidence += 0.1  # Bonus for phonetic transformation
            
            if confidence > best_confidence:
                # Try to split the reading too
                reading_hiragana = as_hiragana(reading)
                left_len = len(as_hiragana(left)) if is_kana(left) else None
                
                if left_len and left_len <= len(reading_hiragana):
                    left_reading = reading_hiragana[:left_len]
                    right_reading = reading_hiragana[left_len:]
                    
                    best_analysis = CompoundAnalysis(
                        components=[left, right],
                        readings=[left_reading, right_reading],
                        transforms=[None, transform],
                        confidence=confidence
                    )
                    best_confidence = confidence
    
    return best_analysis


# ============================================================================
# Module Initialization
# ============================================================================

def init_all():
    """Initialize all split/hint systems."""
    init_simple_splits()
    init_hints()


# Auto-initialize on import
init_all()
