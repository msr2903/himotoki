"""
Synergies and Segfilters runtime API for himotoki.
Ports ichiran's dict-grammar.lisp synergy and segfilter functionality.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple, Union, Any, Callable

from himotoki.constants import NOUN_PARTICLES

from himotoki.grammar.synergy_filters import (
    cached_filter,
    filter_is_noun,
    filter_is_pos,
    filter_in_seq_set,
    filter_in_seq_set_simple,
    filter_is_conjugation,
    filter_is_compound_end,
    filter_is_compound_end_text,
    filter_short_kana,
)

# ============================================================================
# Synergy Data Structure
# ============================================================================

@dataclass(slots=True)
class Synergy:
    """Represents a synergy between two adjacent segments."""
    description: str
    connector: str  # Space or empty string between words
    score: int
    start: int  # Position where synergy starts
    end: int  # Position where synergy ends


def get_segment_score_synergy(syn: Synergy) -> int:
    """Get the score value from a synergy."""
    return syn.score


# ============================================================================
# Synergy List and Registration
# ============================================================================

_synergy_list: List[Callable] = []


def register_synergy(func: Callable):
    """Register a synergy function."""
    _synergy_list.append(func)
    return func


def def_generic_synergy(
    name: str,
    filter_left: Callable,
    filter_right: Callable,
    description: str,
    score: Union[int, Callable],
    connector: str = " ",
):
    """
    Define a generic synergy between two segment lists.
    """
    def synergy_fn(seg_list_left: Any, seg_list_right: Any) -> List[Tuple]:
        start = seg_list_left.end
        end = seg_list_right.start
        
        # Must be adjacent
        if start != end:
            return []
        
        left_segments = [s for s in seg_list_left.segments if filter_left(s)]
        right_segments = [s for s in seg_list_right.segments if filter_right(s)]
        
        if not left_segments or not right_segments:
            return []
        
        # Calculate score
        if callable(score):
            actual_score = score(seg_list_left, seg_list_right)
        else:
            actual_score = score
        
        # Create synergy
        syn = Synergy(
            description=description,
            connector=connector,
            score=actual_score,
            start=start,
            end=end,
        )
        
        # Return modified segment lists with synergy
        from himotoki.lookup import SegmentList
        new_left = SegmentList(
            segments=left_segments,
            start=seg_list_left.start,
            end=seg_list_left.end,
            matches=seg_list_left.matches,
        )
        new_right = SegmentList(
            segments=right_segments,
            start=seg_list_right.start,
            end=seg_list_right.end,
            matches=seg_list_right.matches,
        )
        
        return [(new_right, syn, new_left)]
    
    register_synergy(synergy_fn)
    return synergy_fn

def get_synergies(seg_list_left: Any, seg_list_right: Any) -> List[Tuple]:
    """
    Get all synergies between two segment lists.
    
    Returns list of (new_right, synergy, new_left) tuples.
    """
    results = []
    for fn in _synergy_list:
        results.extend(fn(seg_list_left, seg_list_right))
    return results
# ============================================================================
# Penalty List and Registration
# ============================================================================

_penalty_list: List[Callable] = []


def register_penalty(func: Callable):
    """Register a penalty function."""
    _penalty_list.append(func)
    return func


def def_generic_penalty(
    name: str,
    test_left: Callable,
    test_right: Callable,
    description: str,
    score: int,
    serial: bool = True,
    connector: str = " ",
):
    """
    Define a generic penalty between two segment lists.
    """
    def penalty_fn(seg_list_left: Any, seg_list_right: Any) -> Optional[Synergy]:
        start = seg_list_left.end
        end = seg_list_right.start
        
        # Check serial requirement
        if serial and start != end:
            return None
        
        if not test_left(seg_list_left):
            return None
        if not test_right(seg_list_right):
            return None
        
        return Synergy(
            description=description,
            connector=connector,
            score=score,
            start=start,
            end=end,
        )
    
    register_penalty(penalty_fn)
    return penalty_fn

def get_penalties(seg_list_left: Any, seg_list_right: Any) -> List[Any]:
    """
    Get penalties between two segment lists.
    
    Returns [seg_right, penalty, seg_left] if penalty applies,
    otherwise [seg_right, seg_left].
    """
    for fn in _penalty_list:
        penalty = fn(seg_list_left, seg_list_right)
        if penalty:
            return [seg_list_right, penalty, seg_list_left]
    
    return [seg_list_right, seg_list_left]
# ============================================================================
# Segfilter List and Registration
# ============================================================================

_segfilter_list: List[Callable] = []


def register_segfilter(func: Callable):
    """Register a segfilter function."""
    _segfilter_list.append(func)
    return func


def def_segfilter_must_follow(
    name: str,
    filter_left: Callable,
    filter_right: Callable,
    allow_first: bool = False,
):
    """
    Define a segfilter where filter_right MUST follow filter_left.
    
    If filter_right matches but filter_left doesn't (and we're not at the start),
    the matching segments are removed.
    """
    def classify(filter_fn: Callable, items: List) -> Tuple[List, List]:
        satisfies = []
        contradicts = []
        for item in items:
            if filter_fn(item):
                satisfies.append(item)
            else:
                contradicts.append(item)
        return satisfies, contradicts
    
    def segfilter_fn(seg_list_left: Optional[Any], seg_list_right: Any) -> List[Tuple]:
        from himotoki.lookup import SegmentList
        
        satisfies_right, contradicts_right = classify(filter_right, seg_list_right.segments)
        
        # If nothing satisfies filter_right, pass through
        if not satisfies_right:
            return [(seg_list_left, seg_list_right)]
        
        # If first position and allowed, pass through
        if allow_first and seg_list_left is None:
            return [(seg_list_left, seg_list_right)]
        
        # If not adjacent, only allow contradicts
        if seg_list_left is None or seg_list_left.end != seg_list_right.start:
            if contradicts_right:
                new_right = SegmentList(
                    segments=contradicts_right,
                    start=seg_list_right.start,
                    end=seg_list_right.end,
                    matches=seg_list_right.matches,
                )
                return [(seg_list_left, new_right)]
            return []
        
        # Check left side
        satisfies_left, contradicts_left = classify(filter_left, seg_list_left.segments)
        
        results = []
        
        # If left has contradicts, allow those with right contradicts
        if contradicts_left and contradicts_right:
            results.append((
                seg_list_left,
                SegmentList(
                    segments=contradicts_right,
                    start=seg_list_right.start,
                    end=seg_list_right.end,
                    matches=seg_list_right.matches,
                ),
            ))
        
        # If left satisfies, allow with right satisfies
        if satisfies_left:
            results.append((
                SegmentList(
                    segments=satisfies_left,
                    start=seg_list_left.start,
                    end=seg_list_left.end,
                    matches=seg_list_left.matches,
                ),
                SegmentList(
                    segments=satisfies_right,
                    start=seg_list_right.start,
                    end=seg_list_right.end,
                    matches=seg_list_right.matches,
                ),
            ))
        
        if not results and contradicts_right:
            results.append((
                seg_list_left,
                SegmentList(
                    segments=contradicts_right,
                    start=seg_list_right.start,
                    end=seg_list_right.end,
                    matches=seg_list_right.matches,
                ),
            ))
        
        return results if results else [(seg_list_left, seg_list_right)]
    
    register_segfilter(segfilter_fn)
    return segfilter_fn
def apply_segfilters(seg_left: Optional[Any], seg_right: Any) -> List[Tuple]:
    """
    Apply all segfilters to a pair of segment lists.
    
    Returns list of (seg_left, seg_right) pairs that pass all filters.
    """
    splits = [(seg_left, seg_right)]
    
    for segfilter in _segfilter_list:
        new_splits = []
        for seg_l, seg_r in splits:
            new_splits.extend(segfilter(seg_l, seg_r))
        splits = new_splits
    
    return splits

# Load rule registrations
import himotoki.grammar.synergy_rules  # noqa: F401
