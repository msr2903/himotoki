# 🧶 Himotoki v0.2.0 - Performance & API Overhaul

A major release focusing on performance optimizations, API robustness, and production readiness.

---

## 🚀 Key Highlights

### 1. High-Performance API Overhaul
The Python API has been completely redesigned for use in high-concurrency environments like FastAPI:
- **Async Support**: `analyze_async()` now provides non-blocking analysis using a thread pool.
- **Auto-Session Management**: `analyze()` now automatically creates and closes database sessions, or accepts an external session via `session_context()`.
- **Configurable Timeouts**: Added `HIMOTOKI_DEFAULT_TIMEOUT` and `HIMOTOKI_MAX_TEXT_LENGTH` environment variables for resource protection.
- **Tracing**: Integrated `himotoki.logger` for tracing analysis requests and internal operations.

### 2. Massive Performance Gains
Several layers of caching were added to minimize database overhead:
- **Global Meanings Cache**: Persistent cache for word meanings and POS tags across analysis calls.
- **Filter ID System**: Introduced a unique caching system for morphological filters within the Viterbi scoring loop, dramatically reducing redundant computations.
- **LRU Cache Implementation**: All internal caches now use a strictly bounded `LRUCache` (using `OrderedDict`) to ensure predictable memory usage.

### 3. Unicode & Grammar Robustness
- **NFC Normalization**: All input text is now normalized to Unicode NFC form at the entry point, ensuring base words with decomposed marks match dictionary entries.
- **Nested Compound Fix**: Resolved a long-standing bug where nested verb compounds (like `勉強しています`) would lose segments in romanization and kana output.
- **Conjugation Hints**: Added `conjugation_hints.py` containing 100+ grammar patterns for better auxiliary verb trace-back.

---

## 🔧 Changes

### ✨ New Features
- **Async API**: `await himotoki.analyze_async(text)`
- **Warming Up**: `himotoki.warm_up()` eagerly builds caches for optimal first-request performance.
- **Benchmarking**: New `scripts/benchmark.py` for profiling performance on user hardware.
- **Zero-Dep Core**: Removed Pydantic dependency from the core package to keep it lightweight (FastAPI apps can define their own models).

### 🐛 Bug Fixes
- Fixed `get_word_kana` in `suffixes.py` to correctly preserve data in nested `CompoundWord` objects.
- Fixed `adjoin_word` in `lookup.py` to prioritize `best_kana` over literal kanji text.
- Added missing `LRU` eviction to `_CONJ_DATA_CACHE`, `_POS_SEQ_CACHE`, `_UK_CACHE`, `_WORD_CACHE`, and `_ENTRY_CACHE`.

### 🧹 Cleanup
- Documented `SEQ` stability requirements in `constants.py`.
- Consolidated POS interning and caching logic.
- Removed duplicate cache declarations and manual eviction code.

---

## 📦 Installation & Upgrade

```bash
pip install --upgrade himotoki
```

---

## 🧪 Verification

This release passes the full test suite (**317 tests**) and shows significant performance improvements on the `benchmark.py` suite.

**Full Changelog**: https://github.com/msr2903/himotoki/compare/v0.1.2...v0.2.0
