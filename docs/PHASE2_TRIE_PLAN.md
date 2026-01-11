# Phase 2: Word Trie Implementation Plan

**STATUS: ✅ IMPLEMENTED**

## Overview

Build a prefix trie of all dictionary surface forms loaded at startup. Use it to filter the ~2500 substring candidates per sentence before hitting the database—most substrings won't match anything.

## Results

| Metric | Before | After | Notes |
|--------|--------|-------|-------|
| DB queries (substrings) | 105 | 22 | **79% reduction** |
| Suffix candidates | 105 | 55 | Filtered by ending char |
| Trie entries | - | 8,302,734 | All surface forms |
| Trie build time | - | ~8.6s | One-time at startup |
| Memory overhead | - | ~50-80MB | marisa-trie |

**Note**: Overall `find_substring_words()` speedup is modest (~1.5x) because suffix compound checking (not covered by trie) now dominates. The trie significantly reduces DB I/O but suffix lookup is the new bottleneck. Consider Phase 3: suffix lookup optimization.

## Current State (Post Phase 1)

```
find_substring_words() flow:
1. Generate all substrings (O(n²) where n = text length)
2. Split into kana_keys / kanji_keys lists
3. Batch SQL query: SELECT ... WHERE text IN (?)
4. Return matches
```

**Problem**: For a 50-char sentence, we generate ~1250 substrings × 2 tables = 2500 IN-clause elements. Most don't exist.

## Database Statistics

| Table | Rows | Avg Length | Max Length |
|-------|------|------------|------------|
| kana_text | 3,455,241 | 9.5 chars | 37 chars |
| kanji_text | 5,718,106 | 8.6 chars | 29 chars |
| **Total** | **9,173,347** | | |

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    warm_up() additions                       │
│  Build WordTrie from all kanji_text + kana_text surface     │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    WordTrie (new module)                     │
│  - Prefix trie storing all dictionary surface forms          │
│  - O(k) lookup where k = string length                       │
│  - ~9M entries, estimated ~150-300MB RAM                     │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│              find_substring_words() (modified)               │
│  1. Generate substrings (same as before)                     │
│  2. NEW: Filter through trie.contains(substring)             │
│  3. Only query DB for matches (typically <5% of substrings)  │
│  4. Return matches                                           │
└──────────────────────────────────────────────────────────────┘
```

## Implementation Tasks

### Task 1: Create `himotoki/trie.py`

```python
"""
Prefix trie optimized for Japanese dictionary lookup.

Design decisions:
- Use dict-based nodes (Python 3.10+ dicts are memory-efficient)
- Store only existence, not values (we query DB for full data)
- Support both exact match and prefix check
"""
from typing import Optional, Set

class WordTrie:
    """Prefix trie for fast substring existence checks."""
    
    __slots__ = ('_root', '_size')
    
    def __init__(self):
        self._root: dict = {}
        self._size: int = 0
    
    def add(self, word: str) -> None:
        """Add a word to the trie. O(k) where k = len(word)."""
        node = self._root
        for char in word:
            if char not in node:
                node[char] = {}
            node = node[char]
        if None not in node:  # None marks end-of-word
            node[None] = True
            self._size += 1
    
    def contains(self, word: str) -> bool:
        """Check if exact word exists. O(k)."""
        node = self._root
        for char in word:
            if char not in node:
                return False
            node = node[char]
        return None in node
    
    def has_prefix(self, prefix: str) -> bool:
        """Check if any word starts with prefix. O(k)."""
        node = self._root
        for char in prefix:
            if char not in node:
                return False
            node = node[char]
        return True
    
    def __len__(self) -> int:
        return self._size
    
    def __contains__(self, word: str) -> bool:
        return self.contains(word)


# Module-level singleton
_WORD_TRIE: Optional[WordTrie] = None

def get_word_trie() -> Optional[WordTrie]:
    """Get the initialized trie, or None if not ready."""
    return _WORD_TRIE

def is_trie_ready() -> bool:
    """Check if trie has been initialized."""
    return _WORD_TRIE is not None

def init_word_trie(session) -> WordTrie:
    """
    Initialize the word trie from database.
    Called during warm_up().
    """
    global _WORD_TRIE
    if _WORD_TRIE is not None:
        return _WORD_TRIE
    
    trie = WordTrie()
    conn = session.connection().connection
    cursor = conn.cursor()
    
    # Load all kana surface forms
    cursor.execute("SELECT DISTINCT text FROM kana_text")
    for (text,) in cursor:
        trie.add(text)
    
    # Load all kanji surface forms
    cursor.execute("SELECT DISTINCT text FROM kanji_text")
    for (text,) in cursor:
        trie.add(text)
    
    _WORD_TRIE = trie
    return trie
```

### Task 2: Modify `warm_up()` in `__init__.py`

Add trie initialization after session creation:

```python
# In warm_up(), after session init:
from himotoki.trie import init_word_trie

t0 = time.perf_counter()
trie = init_word_trie(session)
timings['word_trie'] = (time.perf_counter() - t0) * 1000
if verbose:
    print(f"  Word trie:      {timings['word_trie']:>7.1f}ms ({len(trie):,} entries)")
```

### Task 3: Modify `find_substring_words()` in `segment.py`

```python
def find_substring_words(
    session: Session,
    text: str,
    sticky: Optional[List[int]] = None,
) -> Dict[str, List[WordMatch]]:
    from himotoki.raw_types import RawKanaReading, RawKanjiReading
    from himotoki.trie import get_word_trie, is_trie_ready
    
    if sticky is None:
        sticky = []
    
    sticky_set = set(sticky)
    substring_map: Dict[str, List[WordMatch]] = {}
    kana_keys: List[str] = []
    kanji_keys: List[str] = []
    
    # Get trie if available (cold path falls back to DB-only)
    trie = get_word_trie() if is_trie_ready() else None
    
    # Collect substrings, filtering through trie
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
            
            # TRIE FILTER: Skip if trie says this substring doesn't exist
            if trie is not None and part not in trie:
                continue
            
            substring_map[part] = []
            if is_kana(part):
                kana_keys.append(part)
            else:
                kanji_keys.append(part)
    
    # ... rest of function unchanged (DB queries)
```

### Task 4: Memory Optimization (Optional)

If memory is a concern, consider these alternatives:

**Option A: marisa-trie** (C++ library with Python bindings)
```python
# pip install marisa-trie
import marisa_trie
trie = marisa_trie.Trie(all_words)  # ~50-80MB for 9M entries
```

**Option B: datrie** (double-array trie)
```python
# pip install datrie
import datrie
trie = datrie.BaseTrie(alphabet)
```

**Option C: Bloom filter** (probabilistic, smaller memory)
```python
# Only for existence check, allows false positives
from pybloom_live import BloomFilter
bf = BloomFilter(capacity=10_000_000, error_rate=0.01)  # ~12MB
```

### Task 5: Add Tests

```python
# tests/test_trie.py
import pytest
from himotoki.trie import WordTrie

def test_trie_basic():
    trie = WordTrie()
    trie.add("学校")
    trie.add("学生")
    trie.add("学")
    
    assert "学校" in trie
    assert "学生" in trie
    assert "学" in trie
    assert "学習" not in trie
    assert len(trie) == 3

def test_trie_has_prefix():
    trie = WordTrie()
    trie.add("東京都")
    
    assert trie.has_prefix("東")
    assert trie.has_prefix("東京")
    assert trie.has_prefix("東京都")
    assert not trie.has_prefix("大阪")

def test_trie_japanese_characters():
    trie = WordTrie()
    trie.add("ありがとう")
    trie.add("アリガトウ")
    trie.add("有難う")
    
    assert "ありがとう" in trie
    assert "アリガトウ" in trie
    assert "有難う" in trie
```

## Expected Performance Impact

### Before (Phase 1 only)
```
Substrings generated: ~1250 per 50-char sentence
DB queries: 2 (kana + kanji) with large IN clauses
```

### After (Phase 2)
```
Substrings checked: ~1250 (trie lookup, ~0.1μs each)
Substrings to query: ~50-100 (actual matches)
DB queries: 2 with small IN clauses
```

**Estimated speedup**: 5-20x for `find_substring_words()`

### Memory Overhead
- Dict-based trie: ~300-500MB for 9M unique entries
- marisa-trie: ~50-80MB (recommended if memory constrained)

### Warm-up Time
- Expected: +500-1500ms to load all surface forms
- Acceptable for server deployment (one-time cost)

## Implementation Order

1. **Create `trie.py`** with `WordTrie` class and module functions
2. **Add tests** in `tests/test_trie.py`
3. **Modify `warm_up()`** to initialize trie
4. **Modify `find_substring_words()`** to use trie filter
5. **Benchmark** with `scripts/compare.py` or custom script
6. **Optional**: Switch to marisa-trie if memory is an issue

## Rollback Strategy

The trie is optional—if `is_trie_ready()` returns False, the code falls back to DB-only path. This makes it safe to deploy incrementally.

## Future Enhancements

- **Prefix pruning**: If `trie.has_prefix(part)` is False, skip all longer substrings from that position
- **Trie serialization**: Save to disk, load on startup (faster than rebuilding)
- **Suffix trie integration**: Check suffix cache membership in the same pass
