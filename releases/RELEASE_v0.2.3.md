# Himotoki v0.2.3 Release Notes

This release focuses on enhancing the linguistic precision of the segmentation engine through advanced synergy heuristics and refined suffix matching rules. These improvements address specific edge cases in particle-adverb combinations and compound noun pluralization.

## Core Enhancements

### Advanced Language Heuristics
* **Refined Suffix Matching**: Optimized the loading of the `sou` (looks like) pattern to prevent incorrect segmentation in complex verb-suffix chains. This change ensures that auxiliary patterns do not over-eagerly consume stems that should remain independent.
* **Length-Aware Plural Scoring**: Introduced a dynamic scoring mechanism for plural suffixes such as `たち` (tachi). By factoring in the length of the preceding noun, the system now more accurately prioritizes compound nouns (e.g., `村人` + `たち`) over fragmented splits (e.g., `村` + `人たち`).
* **Particle-Adverb Synergies**: Implemented new synergy rules for frequent particle-adverb pairs. This significantly improves the segmentation accuracy of patterns like `はまだ`, which were previously prone to being misidentified as rare noun-copula combinations.

### Accuracy Regularization
* **Targeted Penalty Heuristics**: Added specific penalties to resolve high-frequency ambiguities:
    - Resolved the "hama-da" (beach vs. particle+adverb) conflict.
    - Added dynamic penalties for single-kanji prefixes followed by the plural `人たち` (hitotachi) to encourage compound recognition.

## Infrastructure and Tooling
* **Test Suite Consolidation**: Further refinement of the centralized test suite and batch comparison logic to support robust regression testing.
* **Version Control**: Formalized project management utilities for repository maintenance.

---
*For more information on these architectural changes, please refer to the updated documentation in the `docs` directory.*
