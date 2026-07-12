"""
Filter helpers and caching for synergy/penalty/segfilter matching.
"""

from typing import Optional, List, Dict, Any, Callable

# ============================================================================
# Filter Caching System
# ============================================================================

# Global filter ID counter for unique identification
_filter_id_counter = 0


def _get_next_filter_id() -> int:
    """Get a unique filter ID."""
    global _filter_id_counter
    _filter_id_counter += 1
    return _filter_id_counter


def cached_filter(filter_fn: Callable) -> Callable:
    """
    Wrap a filter function with segment-level caching.
    
    Each filter gets a unique ID, and results are cached on the segment
    to avoid re-running the same filter on the same segment.
    """
    filter_id = _get_next_filter_id()
    
    def _cached_filter(segment: Any) -> bool:
        # Try to get cached result
        if hasattr(segment, 'get_filter_result'):
            cached = segment.get_filter_result(filter_id)
            if cached is not None:
                return cached
        
        # Compute and cache result
        result = filter_fn(segment)
        
        if hasattr(segment, 'set_filter_result'):
            segment.set_filter_result(filter_id, result)
        
        return result
    
    # Preserve the filter's identity for debugging
    _cached_filter.__name__ = getattr(filter_fn, '__name__', 'cached_filter')
    _cached_filter._filter_id = filter_id
    
    return _cached_filter


# ============================================================================
# Filter Helpers
# ============================================================================

def _filter_is_noun_impl(segment: Any) -> bool:
    """Check if segment is a noun (implementation)."""
    info = getattr(segment, 'info', {})
    kpcl = info.get('kpcl', [False, False, False, False])
    if len(kpcl) < 4:
        kpcl = kpcl + [False] * (4 - len(kpcl))
    k, p, c, l = kpcl
    
    posi = info.get('posi', [])
    noun_pos = {'n', 'n-adv', 'n-t', 'adj-na', 'n-suf', 'pn'}
    
    if (l or k or (p and c)) and noun_pos.intersection(posi):
        return True
    
    # Check for counter
    word = getattr(segment, 'word', None)
    if word and hasattr(word, '__class__') and 'counter' in word.__class__.__name__.lower():
        return bool(info.get('seq_set'))
    
    return False


# Create cached version of filter_is_noun
filter_is_noun = cached_filter(_filter_is_noun_impl)


# Cache for filter_is_pos filters to avoid creating duplicates
_pos_filter_cache: Dict[frozenset, Callable] = {}


def filter_is_pos(*pos_list: str):
    """Create filter for specific parts of speech (cached)."""
    pos_key = frozenset(pos_list)
    if pos_key in _pos_filter_cache:
        return _pos_filter_cache[pos_key]
    
    pos_set = set(pos_list)
    
    def _filter(segment: Any) -> bool:
        info = getattr(segment, 'info', {})
        posi = info.get('posi', [])
        return bool(pos_set.intersection(posi))
    
    result = cached_filter(_filter)
    _pos_filter_cache[pos_key] = result
    return result


# Cache for filter_in_seq_set filters
_seq_filter_cache: Dict[frozenset, Callable] = {}


def filter_in_seq_set(*seqs: int):
    """Create filter for specific sequence numbers (cached)."""
    seq_key = frozenset(seqs)
    if seq_key in _seq_filter_cache:
        return _seq_filter_cache[seq_key]
    
    seq_set = set(seqs)
    
    def _filter(segment: Any) -> bool:
        info = getattr(segment, 'info', {})
        segment_seqs = info.get('seq_set', [])
        return bool(seq_set.intersection(segment_seqs))
    
    result = cached_filter(_filter)
    _seq_filter_cache[seq_key] = result
    return result


# Cache for filter_in_seq_set_simple filters
_seq_simple_filter_cache: Dict[frozenset, Callable] = {}


def filter_in_seq_set_simple(*seqs: int):
    """Filter for seqs, checking that word is not compound (cached)."""
    seq_key = frozenset(seqs)
    if seq_key in _seq_simple_filter_cache:
        return _seq_simple_filter_cache[seq_key]
    
    seq_set = set(seqs)
    
    def _filter(segment: Any) -> bool:
        word = getattr(segment, 'word', None)
        if not word:
            return False
        seq = getattr(word, 'seq', None)
        if isinstance(seq, list):
            return False
        info = getattr(segment, 'info', {})
        segment_seqs = info.get('seq_set', [])
        return bool(seq_set.intersection(segment_seqs))
    
    result = cached_filter(_filter)
    _seq_simple_filter_cache[seq_key] = result
    return result


# Cache for filter_is_conjugation filters
_conj_filter_cache: Dict[int, Callable] = {}


def filter_is_conjugation(conj_type: int):
    """Create filter for specific conjugation type (cached)."""
    if conj_type in _conj_filter_cache:
        return _conj_filter_cache[conj_type]
    
    def _filter(segment: Any) -> bool:
        info = getattr(segment, 'info', {})
        conj = info.get('conj', [])
        for cdata in conj:
            if hasattr(cdata, 'prop') and cdata.prop:
                if getattr(cdata.prop, 'conj_type', None) == conj_type:
                    return True
        return False
    
    result = cached_filter(_filter)
    _conj_filter_cache[conj_type] = result
    return result


# Cache for filter_is_compound_end filters
_compound_end_filter_cache: Dict[frozenset, Callable] = {}


def filter_is_compound_end(*seqs: int):
    """Filter for compound words ending with specific seqs (cached)."""
    seq_key = frozenset(seqs)
    if seq_key in _compound_end_filter_cache:
        return _compound_end_filter_cache[seq_key]
    
    seq_set = set(seqs)
    
    def _filter(segment: Any) -> bool:
        word = getattr(segment, 'word', None)
        if not word:
            return False
        seq = getattr(word, 'seq', None)
        if isinstance(seq, list) and seq:
            return seq[-1] in seq_set
        return False
    
    result = cached_filter(_filter)
    _compound_end_filter_cache[seq_key] = result
    return result


# Cache for filter_is_compound_end_text filters
_compound_end_text_filter_cache: Dict[frozenset, Callable] = {}


def filter_is_compound_end_text(*texts: str):
    """Filter for compound words ending with specific texts (cached)."""
    text_key = frozenset(texts)
    if text_key in _compound_end_text_filter_cache:
        return _compound_end_text_filter_cache[text_key]
    
    text_set = set(texts)
    
    def _filter(segment: Any) -> bool:
        word = getattr(segment, 'word', None)
        if not word:
            return False
        seq = getattr(word, 'seq', None)
        if not isinstance(seq, list):
            return False
        words = getattr(word, 'words', [])
        if words:
            last_word = words[-1]
            text = getattr(last_word, 'text', '')
            return text in text_set
        return False
    
    result = cached_filter(_filter)
    _compound_end_text_filter_cache[text_key] = result
    return result


def filter_short_kana(length: int, except_list: Optional[List[str]] = None):
    """Filter for short kana words."""
    except_set = set(except_list) if except_list else set()
    
    def _filter(segment_list: Any) -> bool:
        segments = getattr(segment_list, 'segments', [])
        if not segments:
            return False
        seg = segments[0]
        
        seg_len = segment_list.end - segment_list.start
        if seg_len > length:
            return False
        
        info = getattr(seg, 'info', {})
        kpcl = info.get('kpcl', [False, False, False, False])
        if kpcl and kpcl[0]:  # Has kanji
            return False
        
        text = getattr(seg, 'text', '') or getattr(seg.word, 'text', '')
        if text in except_set:
            return False
        
        return True
    
    return _filter

