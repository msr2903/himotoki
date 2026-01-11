"""
Segmentation module for himotoki.
Ports ichiran's dict.lisp text segmentation functionality.

This module provides:
- join_substring_words: Find all possible word matches in a string
- find_sticky_positions: Identify positions where words cannot start/end
- find_best_path: Dynamic programming algorithm for optimal segmentation
- TopArray: Priority queue for tracking best paths
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any, Set
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from himotoki.db.models import KanjiText, KanaText
from himotoki.characters import (
    is_kana, get_char_class, sequential_kanji_positions,
    count_char_class, KANA_CHARS, MODIFIER_CHARS,
)
from himotoki.lookup import (
    MAX_WORD_LENGTH, SCORE_CUTOFF, GAP_PENALTY,
    WordMatch, Segment, SegmentList,
    find_word_full, gen_score, cull_segments, gap_penalty,
    preload_scoring_caches,
)
from himotoki.synergies import (
    get_synergies, get_penalties, apply_segfilters,
    get_segment_score_synergy, Synergy,
)
from himotoki.counters import (
    find_counter_in_text, CounterText,
)


# ============================================================================
# Constants
# ============================================================================

# Character classes that are modifiers (can't start words)
MODIFIER_CLASSES = frozenset(['+a', '+i', '+u', '+e', '+o', '+ya', '+yu', '+yo', '+wa', 'long_vowel'])

# Iteration characters
ITERATION_CLASSES = frozenset(['iter', 'iter_v'])

# Kana character classes (where sokuon can precede)
KANA_CLASSES = frozenset(KANA_CHARS.keys())


# ============================================================================
# TopArray - Priority Queue for Best Paths
# ============================================================================

@dataclass(slots=True)
class TopArrayItem:
    """Item in the top array."""
    score: float
    payload: Any


class TopArray:
    """
    A limited-size priority array that keeps the top N highest-scoring items.
    Used in the dynamic programming path finding algorithm.
    """
    
    def __init__(self, limit: int = 5):
        self.array: List[Optional[TopArrayItem]] = [None] * limit
        self.count: int = 0
        self.limit: int = limit
    
    def register(self, score: float, payload: Any) -> None:
        """
        Register a new item with the given score.
        Items are kept in descending score order.
        """
        item = TopArrayItem(score=score, payload=payload)
        
        # Insert in sorted position
        insert_pos = min(self.count, self.limit)
        
        for idx in range(insert_pos, -1, -1):
            prev_item = self.array[idx - 1] if idx > 0 else None
            done = prev_item is None or prev_item.score >= score
            
            if idx < self.limit:
                self.array[idx] = item if done else prev_item
            
            if done:
                break
        
        self.count += 1
    
    def get_items(self) -> List[TopArrayItem]:
        """Get all items in the array (highest scores first)."""
        count = min(self.count, self.limit)
        return [item for item in self.array[:count] if item is not None]


# ============================================================================
# Sticky Positions Detection
# ============================================================================

def find_sticky_positions(text: str) -> List[int]:
    """
    Find positions where words cannot start or end.
    
    Words cannot start after sokuon (っ) or end before modifier characters (ゃゅょー etc.)
    This prevents invalid word boundaries.
    
    Args:
        text: The text to analyze
    
    Returns:
        List of sticky positions (indices where words can't start/end)
    """
    sticky = []
    text_len = len(text)
    
    for pos in range(text_len):
        char = text[pos]
        char_class = get_char_class(char)
        
        # After sokuon (っ), words can't start (unless at end of string or not followed by kana)
        if char_class == 'sokuon':
            if pos < text_len - 1:
                next_char = text[pos + 1]
                next_class = get_char_class(next_char)
                if next_class and next_class in KANA_CLASSES:
                    sticky.append(pos + 1)
        
        # Before modifier characters, words can't end
        elif char_class in MODIFIER_CLASSES or char_class in ITERATION_CLASSES:
            # Exception: at end of string with long vowel
            at_end = pos == text_len - 1
            if not at_end or char_class != 'long_vowel':
                # Also check for long vowel modifier pattern
                if pos > 0 and char_class == 'long_vowel':
                    prev_char = text[pos - 1]
                    if is_long_vowel_modifier(char_class, prev_char):
                        continue
                sticky.append(pos)
    
    return sticky


def is_long_vowel_modifier(char_class: str, prev_char: str) -> bool:
    """Check if a long vowel mark is actually modifying the previous character."""
    # Long vowel ー can modify any vowel sound
    prev_class = get_char_class(prev_char)
    if prev_class:
        # Check if previous character ends in a vowel sound
        vowel_endings = ['a', 'i', 'u', 'e', 'o']
        for v in vowel_endings:
            if prev_class.endswith(v):
                return True
    return False


# ============================================================================
# Consecutive Character Groups
# ============================================================================

def consecutive_char_groups(char_type: str, text: str) -> List[Tuple[int, int]]:
    """
    Find consecutive groups of a specific character type.
    
    Args:
        char_type: 'katakana', 'number', etc.
        text: Text to analyze
    
    Returns:
        List of (start, end) tuples for each consecutive group
    """
    groups = []
    current_start = None
    
    for i, char in enumerate(text):
        is_type = False
        
        if char_type == 'katakana':
            char_class = get_char_class(char)
            is_type = (char_class is not None and 
                      (char in 'ァ-ヺヽヾー' or 
                       (char_class in KANA_CHARS and char == KANA_CHARS[char_class][-1])))
        elif char_type == 'number':
            is_type = char in '0123456789０１２３４５６７８９〇一二三四五六七八九零壱弐参'
        
        if is_type:
            if current_start is None:
                current_start = i
        else:
            if current_start is not None:
                groups.append((current_start, i))
                current_start = None
    
    # Handle group at end of string
    if current_start is not None:
        groups.append((current_start, len(text)))
    
    return groups


# ============================================================================
# Substring Word Matching
# ============================================================================

def find_substring_words(
    session: Session,
    text: str,
    sticky: Optional[List[int]] = None,
) -> Dict[str, List[WordMatch]]:
    """
    Find all words that match substrings of the given text.
    
    This pre-loads words for efficiency, avoiding repeated database queries.
    Uses RAW SQL instead of ORM for performance (avoids ORM object overhead).
    Uses a trie filter to skip substrings that don't exist in the dictionary.
    
    Args:
        session: Database session
        text: Text to search for substrings
        sticky: Positions where words can't start/end
    
    Returns:
        Dictionary mapping substring to list of matching words
    """
    from himotoki.raw_types import RawKanaReading, RawKanjiReading
    from himotoki.trie import get_word_trie
    
    if sticky is None:
        sticky = []
    
    sticky_set = set(sticky)
    substring_map: Dict[str, List[WordMatch]] = {}
    kana_keys: List[str] = []
    kanji_keys: List[str] = []
    all_substrings: List[str] = []  # For suffix checking (not filtered by trie)
    
    # Get trie for fast filtering (None if not initialized - graceful fallback)
    trie = get_word_trie()
    
    # Collect all substrings
    text_len = len(text)
    for start in range(text_len):
        if start in sticky_set:
            continue
        
        max_end = min(text_len, start + MAX_WORD_LENGTH)
        for end in range(start + 1, max_end + 1):
            if end in sticky_set:
                continue
            
            part = text[start:end]
            if part in substring_map:
                continue
            
            # Track all substrings for suffix checking
            all_substrings.append(part)
            
            # TRIE FILTER: Only add to DB query lists if in trie
            if trie is None or part in trie:
                substring_map[part] = []
                if is_kana(part):
                    kana_keys.append(part)
                else:
                    kanji_keys.append(part)
    
    # =========================================================================
    # RAW SQL QUERIES (replaces ORM for performance)
    # =========================================================================
    # Get raw connection from SQLAlchemy session
    conn = session.connection().connection
    cursor = conn.cursor()
    
    # Query kana_text table
    if kana_keys:
        unique_kana = list(set(kana_keys))
        placeholders = ','.join('?' * len(unique_kana))
        cursor.execute(
            f"SELECT id, seq, text, ord, common, best_kanji "
            f"FROM kana_text WHERE text IN ({placeholders})",
            unique_kana
        )
        for row in cursor.fetchall():
            reading = RawKanaReading(*row)
            substring_map[reading.text].append(WordMatch(reading=reading))
    
    # Query kanji_text table
    if kanji_keys:
        unique_kanji = list(set(kanji_keys))
        placeholders = ','.join('?' * len(unique_kanji))
        cursor.execute(
            f"SELECT id, seq, text, ord, common, best_kana "
            f"FROM kanji_text WHERE text IN ({placeholders})",
            unique_kanji
        )
        for row in cursor.fetchall():
            reading = RawKanjiReading(*row)
            substring_map[reading.text].append(WordMatch(reading=reading))
    
    # Check for suffix-based compound words for ALL substrings
    # (suffix compounds aren't in the DB, so trie doesn't know about them)
    from himotoki.suffixes import find_word_suffix, is_suffix_cache_ready, could_have_suffix
    if is_suffix_cache_ready():
        for substring in all_substrings:
            # Quick filter: skip if word can't have a suffix (wrong ending char)
            if not could_have_suffix(substring):
                continue
            suffix_results = find_word_suffix(session, substring)
            if suffix_results:
                if substring not in substring_map:
                    substring_map[substring] = []
                substring_map[substring].extend(suffix_results)
    
    return substring_map


def join_substring_words_impl(
    session: Session,
    text: str,
) -> Tuple[List[Tuple[int, int, List[Segment]]], List[int]]:
    """
    Internal implementation for finding all word matches with positions.
    
    Args:
        session: Database session
        text: Text to segment
    
    Returns:
        Tuple of (list of (start, end, segments), kanji_break_positions)
    """
    sticky = find_sticky_positions(text)
    substring_map = find_substring_words(session, text, sticky)
    katakana_groups = consecutive_char_groups('katakana', text)
    number_groups = consecutive_char_groups('number', text)
    
    # Find counter expressions in the text
    counter_matches = find_counter_in_text(session, text)
    counter_map: Dict[Tuple[int, int], List[CounterText]] = {}
    for start, end, counter in counter_matches:
        key = (start, end)
        if key not in counter_map:
            counter_map[key] = []
        counter_map[key].append(counter)
    
    kanji_break: List[int] = []
    ends: Set[int] = set()
    results: List[Tuple[int, int, List[Segment]]] = []
    
    sticky_set = set(sticky)
    text_len = len(text)
    
    for start in range(text_len):
        if start in sticky_set:
            continue
        
        # Check for katakana group ending
        katakana_end = None
        for kg_start, kg_end in katakana_groups:
            if kg_start == start:
                katakana_end = kg_end
                break
        
        # Check for number group
        number_end = None
        for ng_start, ng_end in number_groups:
            if ng_start == start:
                number_end = ng_end
                break
        
        max_end = min(text_len, start + MAX_WORD_LENGTH)
        for end in range(start + 1, max_end + 1):
            if end in sticky_set:
                continue
            
            part = text[start:end]
            
            # Get pre-loaded words
            simple_words = substring_map.get(part, [])
            
            # For words with matches, try extended lookups
            all_words = list(simple_words)
            
            # Try hiragana conversion for katakana words
            as_hiragana = katakana_end is not None and end == katakana_end
            if as_hiragana and not simple_words:
                # This would need hiragana lookup - simplified for now
                pass
            
            # Check for counter expressions at this position
            counter_key = (start, end)
            counters = counter_map.get(counter_key, [])
            
            # Create segments
            segments = []
            
            # Add word-based segments
            for word in all_words:
                segments.append(Segment(start=start, end=end, word=word))
            
            # Add counter-based segments
            for counter in counters:
                # Create a segment with counter as word
                # CounterText is now compatible with calc_score, so we don't pre-score
                seg = Segment(
                    start=start,
                    end=end,
                    word=counter,  # CounterText acts as word
                    score=0,  # Will be scored by gen_score
                    info={'posi': ['ctr'], 'counter': True, 'seq_set': {counter.seq} if counter.seq else set()},
                )
                segments.append(seg)
            
            if segments:
                # Track kanji break positions
                if start == 0 or start in ends:
                    kanji_positions = sequential_kanji_positions(part, start)
                    kanji_break.extend(kanji_positions)
                
                ends.add(end)
                results.append((start, end, segments))
    
    # Remove duplicate kanji break positions
    return results, list(set(kanji_break))


def join_substring_words(session: Session, text: str) -> List[SegmentList]:
    """
    Find all word matches in text and create scored segment lists.
    
    This is the main entry point for finding word candidates.
    
    Args:
        session: Database session
        text: Text to segment
    
    Returns:
        List of SegmentList objects, sorted by position
    """
    results, kanji_break = join_substring_words_impl(session, text)
    segment_lists: List[SegmentList] = []
    
    ends_with_long_vowel = text.endswith('ー')
    text_len = len(text)
    
    # Batch preload all seqs for scoring performance
    # This reduces N individual queries to 1 batch query
    all_seqs: Set[int] = set()
    for start, end, segments in results:
        for seg in segments:
            if hasattr(seg.word, 'seq') and seg.word.seq:
                all_seqs.add(seg.word.seq)
    
    if all_seqs:
        preload_scoring_caches(session, all_seqs)
    
    for start, end, segments in results:
        # Calculate kanji break positions relative to segment
        kb = [
            n - start 
            for n in [start, end] 
            if n in kanji_break
        ]
        
        # Score all segments
        scored_segments = []
        for segment in segments:
            is_final = (end == text_len or 
                       (ends_with_long_vowel and end == text_len - 1))
            gen_score(session, segment, final=is_final, kanji_break=kb if kb else None)
            
            if segment.score >= SCORE_CUTOFF:
                scored_segments.append(segment)
        
        # Only include if we have valid segments
        if scored_segments:
            culled = cull_segments(scored_segments)
            segment_lists.append(SegmentList(
                segments=culled,
                start=start,
                end=end,
                matches=len(segments)
            ))
    
    return segment_lists


# ============================================================================
# Best Path Finding (Dynamic Programming)
# ============================================================================

def get_segment_score(seg: Any) -> float:
    """Get score from a segment, segment list, or synergy."""
    if isinstance(seg, Segment):
        return seg.score
    elif isinstance(seg, SegmentList):
        segments = seg.segments
        return segments[0].score if segments else 0
    elif isinstance(seg, Synergy):
        return get_segment_score_synergy(seg)
    return 0


def find_best_path(
    segment_lists: List[SegmentList],
    text_length: int,
    limit: int = 5,
) -> List[Tuple[List[Any], float]]:
    """
    Find the best segmentation path(s) using dynamic programming.
    
    This algorithm finds paths through the segment lists that maximize
    total score while covering the entire text.
    
    Args:
        segment_lists: List of SegmentList objects from join_substring_words
        text_length: Length of the original text
        limit: Maximum number of paths to return
    
    Returns:
        List of (path, score) tuples, sorted by score descending.
        Each path is a list of Segment/SegmentList objects.
    """
    top = TopArray(limit=limit)
    
    # Register initial path with just gap penalty
    top.register(gap_penalty(0, text_length), [])
    
    # Initialize top arrays for each segment list
    for seg_list in segment_lists:
        seg_list.top = TopArray(limit=limit)
    
    # Process segments in order (assumes sorted by start, end)
    for i, seg1 in enumerate(segment_lists):
        gap_left = gap_penalty(0, seg1.start)
        gap_right = gap_penalty(seg1.end, text_length)
        
        # Get initial segments for this position
        initial_segs = get_initial_segments(seg1)
        
        for seg in initial_segs:
            score1 = get_segment_score(seg)
            
            # Register in segment's top array
            seg1.top.register(gap_left + score1, [seg])
            
            # Register as complete path
            top.register(gap_left + score1 + gap_right, [seg])
        
        # Connect to later segments
        for seg2 in segment_lists[i + 1:]:
            score2 = get_segment_score(seg2)
            
            # Only connect non-overlapping segments
            if seg2.start < seg1.end:
                continue
            
            gap_mid = gap_penalty(seg1.end, seg2.start)
            gap_end = gap_penalty(seg2.end, text_length)
            
            # Try extending paths from seg1's top array
            for tai in seg1.top.get_items():
                path = tai.payload
                if not path:
                    continue
                
                seg_left = path[0]
                tail = path[1:] if len(path) > 1 else []
                score3 = get_segment_score(seg_left)
                score_tail = tai.score - score3
                
                # Get connecting segments
                splits = get_segment_splits(seg_left, seg2)
                
                for split in splits:
                    split_score = sum(get_segment_score(s) for s in split)
                    accum = gap_mid + max(split_score, score3 + 1, score2 + 1) + score_tail
                    new_path = list(split) + list(tail)
                    
                    seg2.top.register(accum, new_path)
                    top.register(accum + gap_end, new_path)
    
    # Clean up top arrays
    for seg_list in segment_lists:
        seg_list.top = None
    
    # Build results
    results = []
    for tai in top.get_items():
        path = list(reversed(tai.payload))
        results.append((path, tai.score))
    
    return results


def get_initial_segments(seg_list: SegmentList) -> List[SegmentList]:
    """Get the initial segment list(s) for a segment list."""
    # Apply segfilters with no left segment
    filtered = apply_segfilters(None, seg_list)
    return [new_right for _, new_right in filtered if new_right and new_right.segments]


def get_segment_splits(seg_left: Any, seg_right: SegmentList) -> List[List[Any]]:
    """
    Get possible segment combinations between two positions.
    
    This applies synergies, penalties, and segfilters between adjacent words.
    
    Synergies give bonuses for common patterns (noun+particle, na-adj+な, etc.)
    Penalties subtract for problematic patterns (short kana + short kana)
    Segfilters block invalid combinations (aux verb not after continuative)
    
    Returns:
        List of paths, where each path is [right_seg, synergy?, left_seg, ...]
    """
    results = []
    
    # First, apply segfilters to get valid segment pairs
    filtered_pairs = apply_segfilters(seg_left, seg_right)
    
    for new_left, new_right in filtered_pairs:
        if not new_right or not new_right.segments:
            continue
        
        # Try synergies for bonus combinations
        synergies = get_synergies(new_left, new_right) if new_left else []
        
        if synergies:
            # Synergies return (new_right, synergy, new_left) tuples
            for syn_right, synergy, syn_left in synergies:
                # Path format: [right, synergy, left]
                results.append([syn_right, synergy, syn_left])
        
        # Also try penalties for regular combinations
        if new_left:
            penalty_result = get_penalties(new_left, new_right)
            if penalty_result not in results:
                results.append(penalty_result)
        else:
            results.append([new_right])
    
    # If no results, return simple combination
    if not results:
        if seg_right.segments:
            return [[seg_right, seg_left]] if seg_left else [[seg_right]]
    
    return results


# ============================================================================
# Main Segmentation Function
# ============================================================================

def segment_text(
    session: Session,
    text: str,
    limit: int = 5,
) -> List[Tuple[List[Segment], float]]:
    """
    Segment text into words.
    
    This is the main entry point for text segmentation.
    
    Args:
        session: Database session
        text: Text to segment
        limit: Maximum number of segmentation options to return
    
    Returns:
        List of (segments, score) tuples, sorted by score descending
    """
    if not text:
        return []
    
    # Find all word matches
    segment_lists = join_substring_words(session, text)
    
    if not segment_lists:
        # No matches found - return the text as-is
        return []
    
    # Find best paths
    paths = find_best_path(segment_lists, len(text), limit=limit)
    
    return paths


def simple_segment(session: Session, text: str) -> List[Segment]:
    """
    Get the best segmentation for text.
    
    Args:
        session: Database session
        text: Text to segment
    
    Returns:
        List of Segment objects for the best segmentation
    """
    results = segment_text(session, text, limit=1)
    if results:
        return results[0][0]
    return []
