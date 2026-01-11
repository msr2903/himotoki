# Himotoki v0.2.1 - Performance Turbo Charge 🚀

This release introduces significant performance optimizations to the segmentation engine, reducing database I/O and eliminating ORM overhead in critical paths.

## Key Highlights

### 🚄 Optimized Segmentation Engine
- **Raw SQL Integration**: Replaced SQLAlchemy ORM with raw SQL queries in the hot path (`find_substring_words`). This reduces Python object creation overhead and memory usage by ~10x per word match.
- **Marisa-Trie Substring Filtering**: Integrated a `marisa-trie` containing 8.3 million dictionary surface forms. This acts as a fast pre-filter for database queries, resulting in a **79% reduction in DB queries** during segmentation.
- **Fast Suffix Filtering**: Added $O(1)$ character-level filtering for suffix candidates, further pruning the search space.

### 📈 Performance Benchmarks
| Metric | v0.2.0 | v0.2.1 | Improvement |
|--------|--------|--------|-------------|
| DB Substring Queries | 105 | 22 | **-79%** |
| Average Batch Latency | 149ms | 120ms | **+20% speed** |
| Memory Per Match | High (ORM) | Low (Raw) | **~10x reduction** |

## Changes

### 📁 Core
- Added `himotoki/trie.py`: A memory-efficient trie wrapper using `marisa-trie`.
- Added `himotoki/raw_types.py`: Lightweight namedtuples for database results.
- Refactored `himotoki/segment.py` to use the new trie and raw SQL.
- Updated `himotoki/lookup.py` and `himotoki/output.py` for raw type compatibility.

### 🛠 Dependencies
- Added `marisa-trie>=1.0.0` for high-performance string lookups.

## Verification
- **Test Suite**: All 326 tests passed.
- **Accuracy**: Maintained 76.2% exact match with Ichiran while gaining significant speed.

---
*Special thanks to the contributors who worked on the `ditch_orm` transition!*
