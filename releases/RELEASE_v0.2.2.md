# Himotoki v0.2.2 - Linguistic Refinement & Expanded Testing 🌸

This release focuses on improving the linguistic accuracy of the segmentation engine, particularly for colloquial Japanese and common compound expressions, while significantly expanding our testing infrastructure.

## Key Highlights

### 🗣️ Colloquial Grammar Support
- **Contracted Suffix Handlers**: Added dedicated logic for handling contracted forms like `ちゃう` (`-chau` from `てしまう`) and `とく` (`-toku` from `ておく`). These now correctly reconstruct the underlying `te-form` for precise dictionary lookups.
- **Dialect & Slang Optimization**: Introduced specific synergy penalties to ensure common expressions like `わかんない` (wakan-nai) and `知らんけど` (shiran-kedo) are prioritized as single tokens rather than fragmented pieces.

### 🛡️ Segmentation Robustness
- **Prefix Synergy Refinement**: Updated the `o-prefix` (honorific) synergy to be smarter. It now avoids splitting valid compounds like `ごみ` (garbage) into `ご` + `みの`, resolving a long-standing segmentation ambiguity.
- **Improved Penalty System**: Better handling of short kana sequences to prefer longer, more meaningful dictionary matches.

### 🧪 Massive Test Suite Expansion
- **500+ Test Sentences**: Centralized a new repository of over 500 Japanese sentences in `scripts/test_sentences.py`, sourced from anime, news, TV dramas, business contexts, and proverbs.
- **Batch Testing Infrastructure**: Updated `scripts/compare.py` to support full batch evaluations against Ichiran, allowing for data-driven accuracy tracking.

## Changes

### 📁 Core
- **`himotoki/suffixes.py`**: Added `_handler_chau` and `_handler_to_contracted`.
- **`himotoki/synergies.py`**: Refined prefix synergies and added specific expression penalties.
- **`himotoki/__init__.py`**: Version bump to `0.2.2`.

### 🛠️ Scripts & Tools
- **`scripts/test_sentences.py`**: [NEW] Centralized test data.
- **`scripts/compare.py`**: Refactored to use modular test data and support quick/full modes.
- **`fork_project.sh`**: [NEW] Utility for repository management.

---
*This release brings Himotoki closer to "human-like" segmentation of natural Japanese conversation.*
