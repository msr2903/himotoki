# Analysis Report: Himotoki vs Ichiran

This report analyzes the discrepancies between Himotoki (Python) and Ichiran (Lisp), focusing on why Himotoki lags behind in morphological analysis accuracy, particularly with complex conjugations.

## 1. Conjugation System Discrepancy

The most critical difference lies in how conjugated forms are generated and stored in the database.

### Ichiran (Lisp)
*   **Recursive Generation**: Ichiran employs a two-pass system.
    1.  **Primary**: Generates standard conjugations (e.g., `食べる` -> `食べさせる`) from root entries.
    2.  **Secondary**: Recursively generates conjugations from the output of the first pass (e.g., `食べさせる` -> `食べさせられる`). This handles complex forms like Causative-Passive.
*   **Database Schema**: All conjugated forms are inserted as first-class citizens in the `entry`, `kanji_text`, and `kana_text` tables with high sequence numbers (`10000000+`).
*   **Linkage**: A `conjugation` table links these new entries back to their source (`from_seq`) and, for secondary conjugations, their intermediate root (`via`).

### Himotoki (Current)
*   **Linear Generation**: Himotoki generates only primary conjugations. It lacks the recursive pass for secondary conjugations.
*   **Storage**: Conjugations are stored in a separate, flat `conj_lookup` table. They do not exist in the main `entry` table.
*   **Impact**:
    *   **Missing Forms**: Complex forms like `食べさせられる` (Causative-Passive) are simply missing from the dictionary.
    *   **Suffix Failure**: The suffix handling logic (`dict_suffixes.py`) relies on finding words in the main dictionary. Since conjugations aren't in `entry`, suffixes that attach to conjugated forms (e.g., `te`-form + `iru`) may fail or require complex lookups.

### Remediation Plan
1.  **Rewrite `dict_load.py`**: Port the `generate_conjugations` logic to support recursive generation (Primary -> Secondary).
2.  **Migrate Storage**: Modify the loader to insert conjugated forms into `entry`, `kanji_text`, and `kana_text` with the same `seq > 10000000` convention as Ichiran.
3.  **Update References**: Ensure `dict_suffixes.py` queries the standard tables for these forms.

## 2. Database Schema Alignment

Himotoki uses a simplified schema for conjugations (`conj_lookup`) which diverges from Ichiran's uniform schema.

*   **Ichiran**: Uniformly uses `entry` for roots and conjugations. This allows all grammar functions (suffixes, segfilters) to treat them identically.
*   **Himotoki**: The separate `conj_lookup` table forces code to have two code paths (one for normal words, one for conjugated words), increasing complexity and bugs.

**Fix**: Eliminate `conj_lookup` in favor of the standard schema during the data loading phase.

## 3. Connection and Scoring (Automaton)

The user noted "different calculation method". This refers to the connection matrix construction.

*   **Ichiran**: Uses `conn.lisp` to build a connection matrix based on attributes. It uses a sophisticated `adjoin-word` mechanism in `dict.lisp` that combines scores (`score-mod`) from suffixes.
*   **Himotoki**: Ports this via `dict_suffixes.py`'s `adjoin_word`.
    *   **Findings**: The Python implementation of `adjoin_word` in `dict_suffixes.py` closely mirrors Ichiran's `adjoin-word` in `dict.lisp`. It correctly creates `CompoundText` objects and accumulates scores.
    *   **Gap**: The gap is likely in the *input data* (missing conjugated entries) rather than the calculation logic itself. If the base conjugated word isn't found, `adjoin_word` never gets called for it.

## 4. Synergies and Segfilters

*   **Synergies**: `himotoki/synergies.py` appears to be a faithful port of `dict-grammar.lisp` synergies.
*   **Segfilters**: `himotoki/dict_grammar.py` contains segfilters.
    *   **Issue**: Some segfilters in Ichiran rely on `seq` numbers of conjugated forms. If Himotoki doesn't generate those entries (or assigns different IDs), these filters will fail silently.
    *   **Fix**: Ensuring the conjugation generation (Section 1) assigns stable, Ichiran-compatible IDs (or at least internally consistent IDs in the main table) is prerequisite for segfilters to work.

## Conclusion

The primary reason Himotoki is "behind" is the **lack of recursive conjugation generation** and the **divergent database schema** for conjugations. Fixing `dict_load.py` to recursively generate and store conjugations as proper entries will resolve the majority of parsing discrepancies, enabling the existing suffix and synergy logic to function as intended.
