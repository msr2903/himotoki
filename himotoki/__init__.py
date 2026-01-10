"""
Himotoki: Japanese Morphological Analyzer
A Python port of ichiran (https://github.com/tshatrov/ichiran)
"""

import time
from typing import Optional, Tuple

__version__ = "0.1.1"


def warm_up(verbose: bool = False) -> Tuple[float, dict]:
    """
    Pre-initialize all caches for optimal performance.
    
    Call this once at application startup to avoid cold-start latency.
    This eagerly builds all lazy-initialized caches:
    - Archaic word cache (~165ms)
    - Suffix pattern cache (~145ms)
    - Counter cache (~10ms)
    
    Args:
        verbose: If True, print timing information.
        
    Returns:
        Tuple of (total_time_seconds, timing_details_dict)
    
    Example:
        >>> import himotoki
        >>> elapsed, details = himotoki.warm_up(verbose=True)
        Warming up himotoki caches...
          Session:        12.3ms
          Archaic cache:  165.4ms
          Suffix cache:   143.2ms
          Counter cache:   10.1ms
        Total warm-up:    330.9ms
    """
    from himotoki.db.connection import get_session
    from himotoki.lookup import build_archaic_cache, _ARCHAIC_CACHE
    from himotoki.suffixes import init_suffixes, is_suffix_cache_ready
    from himotoki.counters import init_counter_cache
    
    timings = {}
    total_start = time.perf_counter()
    
    if verbose:
        print("Warming up himotoki caches...")
    
    # 1. Initialize session
    t0 = time.perf_counter()
    session = get_session()
    timings['session'] = (time.perf_counter() - t0) * 1000
    if verbose:
        print(f"  Session:        {timings['session']:>7.1f}ms")
    
    # 2. Build archaic cache (largest cache)
    t0 = time.perf_counter()
    import himotoki.lookup as lookup_module
    if lookup_module._ARCHAIC_CACHE is None:
        lookup_module._ARCHAIC_CACHE = build_archaic_cache(session)
    timings['archaic'] = (time.perf_counter() - t0) * 1000
    if verbose:
        print(f"  Archaic cache:  {timings['archaic']:>7.1f}ms")
    
    # 3. Build suffix cache
    t0 = time.perf_counter()
    if not is_suffix_cache_ready():
        init_suffixes(session)
    timings['suffix'] = (time.perf_counter() - t0) * 1000
    if verbose:
        print(f"  Suffix cache:   {timings['suffix']:>7.1f}ms")
    
    # 4. Build counter cache
    t0 = time.perf_counter()
    init_counter_cache(session)
    timings['counter'] = (time.perf_counter() - t0) * 1000
    if verbose:
        print(f"  Counter cache:  {timings['counter']:>7.1f}ms")
    
    total_time = time.perf_counter() - total_start
    timings['total'] = total_time * 1000
    
    if verbose:
        print(f"Total warm-up:    {timings['total']:>7.1f}ms")
    
    return total_time, timings


def analyze(
    text: str,
    limit: int = 1,
    session=None,
) -> list:
    """
    Analyze Japanese text and return segmentation results.
    
    This is the main high-level API for text analysis.
    
    Args:
        text: Japanese text to analyze.
        limit: Maximum number of segmentation results to return.
        session: Optional database session. If None, creates one.
        
    Returns:
        List of (word_info_list, score) tuples.
        
    Example:
        >>> import himotoki
        >>> himotoki.warm_up()  # Optional but recommended
        >>> results = himotoki.analyze("今日は天気がいい")
        >>> for words, score in results:
        ...     for w in words:
        ...         print(f"{w.text} [{w.kana}]: {w.gloss[:30]}...")
    """
    from himotoki.db.connection import get_session as _get_session
    from himotoki.segment import segment_text
    from himotoki.output import fill_segment_path
    
    if session is None:
        session = _get_session()
    
    results = segment_text(session, text, limit=limit)
    
    output = []
    for path, score in results:
        words = fill_segment_path(session, text, path)
        output.append((words, score))
    
    return output