"""
Kanji module for Himotoki.

Handles kanji character information, readings, and statistics.

Mirrors kanji.lisp from the original Ichiran.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from himotoki.conn import query, query_one, query_column, query_single, Cache
from himotoki.characters import is_kanji


# ============================================================================
# Kanji Data Classes
# ============================================================================

@dataclass
class Kanji:
    """Information about a kanji character."""
    char: str
    grade: Optional[int] = None  # School grade (1-6 for jouyou, 8 for jouyou high school)
    strokes: Optional[int] = None
    freq: Optional[int] = None  # Frequency ranking
    jlpt: Optional[int] = None  # JLPT level (1-5, lower is harder)
    readings_on: List[str] = field(default_factory=list)  # On'yomi
    readings_kun: List[str] = field(default_factory=list)  # Kun'yomi
    meanings: List[str] = field(default_factory=list)


@dataclass
class KanjiReading:
    """A reading for a kanji character."""
    id: int
    kanji_id: int
    reading: str
    type: str  # 'on' or 'kun'
    common: bool = True


# ============================================================================
# Kanji Cache
# ============================================================================

KANJI_CACHE: Dict[str, Kanji] = {}


def get_kanji(char: str) -> Optional[Kanji]:
    """
    Get kanji information from the database.
    
    Args:
        char: Single kanji character.
        
    Returns:
        Kanji object or None if not found.
    """
    if char in KANJI_CACHE:
        return KANJI_CACHE[char]
    
    if not is_kanji(char):
        return None
    
    row = query_one(
        """SELECT k.id, k.character, k.grade, k.strokes, k.freq, k.jlpt
           FROM kanji k WHERE k.character = ?""",
        (char,)
    )
    
    if not row:
        return None
    
    kanji_id = row['id']
    
    # Get readings
    readings_on = []
    readings_kun = []
    
    reading_rows = query(
        """SELECT reading, type FROM kanji_reading 
           WHERE kanji_id = ? ORDER BY common DESC, id""",
        (kanji_id,)
    )
    
    for r in reading_rows:
        if r['type'] == 'on':
            readings_on.append(r['reading'])
        else:
            readings_kun.append(r['reading'])
    
    # Get meanings
    meaning_rows = query(
        "SELECT meaning FROM kanji_meaning WHERE kanji_id = ? ORDER BY ord",
        (kanji_id,)
    )
    meanings = [m['meaning'] for m in meaning_rows]
    
    kanji = Kanji(
        char=char,
        grade=row['grade'],
        strokes=row['strokes'],
        freq=row['freq'],
        jlpt=row['jlpt'],
        readings_on=readings_on,
        readings_kun=readings_kun,
        meanings=meanings
    )
    
    KANJI_CACHE[char] = kanji
    return kanji


def clear_kanji_cache():
    """Clear the kanji cache."""
    KANJI_CACHE.clear()


# ============================================================================
# Kanji Analysis
# ============================================================================

def extract_kanji(text: str) -> List[str]:
    """
    Extract all kanji characters from text.
    
    Args:
        text: Text to analyze.
        
    Returns:
        List of unique kanji characters in order of appearance.
    """
    seen = set()
    result = []
    
    for char in text:
        if is_kanji(char) and char not in seen:
            seen.add(char)
            result.append(char)
    
    return result


def kanji_count(text: str) -> int:
    """Count kanji characters in text."""
    return sum(1 for char in text if is_kanji(char))


def all_kanji_info(text: str) -> List[Kanji]:
    """
    Get information for all kanji in text.
    
    Args:
        text: Text to analyze.
        
    Returns:
        List of Kanji objects.
    """
    kanji_chars = extract_kanji(text)
    return [k for char in kanji_chars if (k := get_kanji(char)) is not None]


# ============================================================================
# Reading Matching
# ============================================================================

def kanji_has_reading(char: str, reading: str) -> bool:
    """
    Check if a kanji has a specific reading.
    
    Args:
        char: Kanji character.
        reading: Reading in hiragana.
        
    Returns:
        True if the kanji has this reading.
    """
    from himotoki.characters import as_hiragana
    
    kanji = get_kanji(char)
    if not kanji:
        return False
    
    reading_hira = as_hiragana(reading)
    
    # Check on'yomi
    for on in kanji.readings_on:
        if as_hiragana(on) == reading_hira:
            return True
    
    # Check kun'yomi (may have okurigana markers like 'たべ.る')
    for kun in kanji.readings_kun:
        kun_base = kun.split('.')[0] if '.' in kun else kun
        if as_hiragana(kun_base) == reading_hira:
            return True
    
    return False


def find_reading_candidates(word: str, reading: str) -> List[List[Tuple[str, str]]]:
    """
    Find possible ways to assign readings to kanji in a word.
    
    Args:
        word: Word with kanji.
        reading: Full reading of the word.
        
    Returns:
        List of possible (kanji, reading) assignments.
    """
    from himotoki.characters import as_hiragana, is_kana
    
    if not word or not reading:
        return []
    
    reading_hira = as_hiragana(reading)
    
    def match_recursive(word_idx: int, reading_idx: int, 
                        current_match: List[Tuple[str, str]]) -> List[List[Tuple[str, str]]]:
        # Base case: consumed all of word
        if word_idx >= len(word):
            if reading_idx >= len(reading_hira):
                return [current_match]
            return []
        
        # Base case: ran out of reading
        if reading_idx >= len(reading_hira):
            return []
        
        char = word[word_idx]
        results = []
        
        if is_kana(char):
            # Kana must match exactly
            expected = as_hiragana(char)
            if reading_hira[reading_idx] == expected:
                results.extend(match_recursive(
                    word_idx + 1,
                    reading_idx + 1,
                    current_match + [(char, expected)]
                ))
        elif is_kanji(char):
            # Try different reading lengths for the kanji
            kanji = get_kanji(char)
            if kanji:
                all_readings = kanji.readings_on + kanji.readings_kun
                
                for kr in all_readings:
                    # Handle okurigana markers
                    kr_base = kr.split('.')[0] if '.' in kr else kr
                    kr_hira = as_hiragana(kr_base)
                    
                    if reading_hira[reading_idx:].startswith(kr_hira):
                        results.extend(match_recursive(
                            word_idx + 1,
                            reading_idx + len(kr_hira),
                            current_match + [(char, kr_hira)]
                        ))
            
            # Also try single character readings (for uncommon readings)
            for length in range(1, min(5, len(reading_hira) - reading_idx + 1)):
                substr = reading_hira[reading_idx:reading_idx + length]
                results.extend(match_recursive(
                    word_idx + 1,
                    reading_idx + length,
                    current_match + [(char, substr)]
                ))
        else:
            # Non-Japanese character, skip
            results.extend(match_recursive(
                word_idx + 1,
                reading_idx,
                current_match + [(char, '')]
            ))
        
        return results
    
    return match_recursive(0, 0, [])


# ============================================================================
# JLPT and Grade Statistics
# ============================================================================

def kanji_by_jlpt(text: str) -> Dict[int, List[str]]:
    """
    Group kanji in text by JLPT level.
    
    Args:
        text: Text to analyze.
        
    Returns:
        Dict mapping JLPT level to list of kanji.
    """
    result: Dict[int, List[str]] = {1: [], 2: [], 3: [], 4: [], 5: [], 0: []}
    
    for char in extract_kanji(text):
        kanji = get_kanji(char)
        level = kanji.jlpt if kanji and kanji.jlpt else 0
        result[level].append(char)
    
    return result


def kanji_by_grade(text: str) -> Dict[int, List[str]]:
    """
    Group kanji in text by school grade.
    
    Args:
        text: Text to analyze.
        
    Returns:
        Dict mapping grade to list of kanji.
    """
    result: Dict[int, List[str]] = {i: [] for i in range(0, 10)}
    
    for char in extract_kanji(text):
        kanji = get_kanji(char)
        grade = kanji.grade if kanji and kanji.grade else 0
        result[grade].append(char)
    
    return result


def estimate_text_difficulty(text: str) -> Dict[str, float]:
    """
    Estimate the difficulty of Japanese text based on kanji.
    
    Args:
        text: Text to analyze.
        
    Returns:
        Dict with difficulty metrics.
    """
    total_kanji = kanji_count(text)
    if total_kanji == 0:
        return {'level': 0, 'jlpt_estimate': 5, 'complexity': 0}
    
    by_jlpt = kanji_by_jlpt(text)
    by_grade = kanji_by_grade(text)
    
    # Calculate weighted JLPT level
    jlpt_sum = sum(level * len(chars) for level, chars in by_jlpt.items() if level > 0)
    jlpt_count = sum(len(chars) for level, chars in by_jlpt.items() if level > 0)
    jlpt_avg = jlpt_sum / jlpt_count if jlpt_count > 0 else 5
    
    # Calculate weighted grade level
    grade_sum = sum(grade * len(chars) for grade, chars in by_grade.items() if grade > 0)
    grade_count = sum(len(chars) for grade, chars in by_grade.items() if grade > 0)
    grade_avg = grade_sum / grade_count if grade_count > 0 else 1
    
    # Complexity is based on kanji density and advanced kanji
    advanced_count = len(by_jlpt[1]) + len(by_jlpt[2]) + len(by_grade[8]) + len(by_grade[9])
    complexity = (advanced_count / total_kanji) if total_kanji > 0 else 0
    
    return {
        'level': grade_avg,
        'jlpt_estimate': round(jlpt_avg),
        'complexity': complexity,
        'total_kanji': total_kanji,
        'unique_kanji': len(extract_kanji(text)),
    }
