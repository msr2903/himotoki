#!/usr/bin/env python
"""
Benchmark script for Himotoki CLI and Python API.

Tests:
1. Cold boot (fresh Python process)
2. Warm performance (caches loaded)
3. Single vs batch input
"""

import subprocess
import sys
import time
from pathlib import Path

# Ensure we use local package
sys.path.insert(0, str(Path(__file__).parent.parent))

# Test sentences
SINGLE_SENTENCE = "学校で勉強しています"
BATCH_SENTENCES = [
    "今日は天気がいいですね",
    "日本語を勉強しています",
    "東京は世界で最も人口の多い都市の一つです",
    "彼女は毎朝六時に起きて、ジョギングをする",
    "この映画はとても面白かったです",
    "私の趣味は読書と音楽を聴くことです",
    "明日の会議は午後三時から始まります",
    "昨日スーパーで買い物をしました",
    "日本の四季はとても美しいと思います",
    "コンピューターの使い方を教えてください",
]


def run_cli_cold_boot():
    """Measure CLI cold boot time (fresh subprocess)."""
    times = []
    for _ in range(3):
        start = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-m", "himotoki", "-r", SINGLE_SENTENCE],
            capture_output=True,
            text=True,
        )
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        if result.returncode != 0:
            print(f"CLI error: {result.stderr}")
            return None
    return times


def run_cli_batch():
    """Measure CLI batch processing (multiple calls)."""
    times = []
    for sentence in BATCH_SENTENCES:
        start = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-m", "himotoki", "-r", sentence],
            capture_output=True,
            text=True,
        )
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        if result.returncode != 0:
            print(f"CLI error: {result.stderr}")
    return times


def run_python_api_cold():
    """Measure Python API cold boot (no warm_up) - run FIRST before caches exist."""
    import himotoki
    
    # First call - this is the true cold boot
    start = time.perf_counter()
    results = himotoki.analyze(SINGLE_SENTENCE)
    elapsed = time.perf_counter() - start
    
    return [elapsed]


def run_python_api_warm():
    """Measure Python API with warm caches."""
    import himotoki
    
    # Warm up first
    himotoki.warm_up()
    
    # Single request
    single_times = []
    for _ in range(10):
        start = time.perf_counter()
        results = himotoki.analyze(SINGLE_SENTENCE)
        elapsed = time.perf_counter() - start
        single_times.append(elapsed)
    
    return single_times


def run_python_api_batch():
    """Measure Python API batch processing with shared session."""
    import himotoki
    from himotoki.db.connection import get_session
    from himotoki.suffixes import init_suffixes, is_suffix_cache_ready
    from himotoki.counters import init_counter_cache
    
    # Get session and ensure caches are initialized
    session = get_session()
    if not is_suffix_cache_ready():
        init_suffixes(session)
    init_counter_cache(session)
    himotoki.warm_up()
    
    # Batch with shared session
    batch_times = []
    try:
        for sentence in BATCH_SENTENCES:
            start = time.perf_counter()
            results = himotoki.analyze(sentence, session=session)
            elapsed = time.perf_counter() - start
            batch_times.append(elapsed)
    finally:
        session.close()
    
    return batch_times


def run_python_api_batch_no_session():
    """Measure Python API batch processing WITHOUT shared session."""
    import himotoki
    from himotoki.db.connection import get_session
    from himotoki.suffixes import init_suffixes, is_suffix_cache_ready
    from himotoki.counters import init_counter_cache
    
    # Ensure caches are initialized first
    session = get_session()
    if not is_suffix_cache_ready():
        init_suffixes(session)
    init_counter_cache(session)
    session.close()
    himotoki.warm_up()
    
    # Batch without shared session (creates new session each time)
    batch_times = []
    for sentence in BATCH_SENTENCES:
        start = time.perf_counter()
        results = himotoki.analyze(sentence)
        elapsed = time.perf_counter() - start
        batch_times.append(elapsed)
    
    return batch_times


def format_times(times, label):
    """Format timing results."""
    if not times:
        return f"{label}: N/A"
    
    avg = sum(times) / len(times)
    min_t = min(times)
    max_t = max(times)
    
    return f"{label}:\n  avg: {avg*1000:.1f}ms, min: {min_t*1000:.1f}ms, max: {max_t*1000:.1f}ms (n={len(times)})"


def main():
    print("=" * 60)
    print("Himotoki Performance Benchmark")
    print("=" * 60)
    print()
    
    # 1. Python API Cold - run FIRST before any caches exist
    print("1. Python API Cold Boot (first call, no caches)...")
    api_cold = run_python_api_cold()
    print(format_times(api_cold, "   API cold boot"))
    print()
    
    # 2. Python API Warm (single) - caches now exist
    print("2. Python API Warm (single requests)...")
    api_warm = run_python_api_warm()
    print(format_times(api_warm, "   API warm (single)"))
    print()
    
    # 3. Python API Batch with shared session
    print("3. Python API Batch (10 sentences, shared session)...")
    api_batch = run_python_api_batch()
    print(format_times(api_batch, "   API batch (shared session)"))
    print()
    
    # 4. Python API Batch without shared session
    print("4. Python API Batch (10 sentences, NO shared session)...")
    api_batch_no = run_python_api_batch_no_session()
    print(format_times(api_batch_no, "   API batch (no shared session)"))
    print()
    
    # 5. CLI Cold Boot
    print("5. CLI Cold Boot (fresh subprocess)...")
    cli_cold = run_cli_cold_boot()
    print(format_times(cli_cold, "   CLI cold boot"))
    print()
    
    # 6. CLI Batch
    print("6. CLI Batch (10 sentences, separate processes)...")
    cli_batch = run_cli_batch()
    print(format_times(cli_batch, "   CLI batch"))
    print()
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if cli_cold:
        print(f"CLI cold boot:              {sum(cli_cold)/len(cli_cold)*1000:.0f}ms avg")
    if cli_batch:
        print(f"CLI batch per-request:      {sum(cli_batch)/len(cli_batch)*1000:.0f}ms avg")
    if api_cold:
        print(f"Python API cold boot:       {sum(api_cold)/len(api_cold)*1000:.0f}ms avg")
    if api_warm:
        print(f"Python API warm (single):   {sum(api_warm)/len(api_warm)*1000:.0f}ms avg")
    if api_batch:
        print(f"Python API batch (session): {sum(api_batch)/len(api_batch)*1000:.0f}ms avg")
    if api_batch_no:
        print(f"Python API batch (no sess): {sum(api_batch_no)/len(api_batch_no)*1000:.0f}ms avg")


if __name__ == "__main__":
    main()
