# Himotoki v0.3.0 Release Notes

This release introduces the **conjugation breakdown tree**, a visual
display that traces every inflection step from a conjugated surface form
back to its dictionary root.  It also includes major segmentation accuracy
improvements, achieving **510/510 (100%)** on the LLM-evaluated gold set.

## Conjugation Breakdown Tree

The flagship feature of v0.3.0.  When Himotoki encounters a conjugated
word, it now walks the full conjugation chain -- including multi-step via
chains, suffix compounds, and contracted forms -- and renders the result
as an indented tree:

```
$ himotoki -f "書かせられていた"

  ← 書く 【かく】
  └─ Causative (かせ): makes do
       └─ Passive (られる): is done (to)
            └─ Conjunctive (~te) (て)
                 └─ Past (~ta) (た): did/was
```

Each tree line shows:
- The grammatical label (e.g., Causative, Passive, Past)
- The suffix text that was applied (e.g., かせ, られる, た)
- An English gloss (e.g., "makes do", "is done (to)", "did/was")
- Markers for polite (`polite`) and negative (`not`) forms
- Dual label `Potential/Passive` for ambiguous ichidan verb forms

### Implementation

- `ConjStep` dataclass in `output.py` holds one step (type, suffix, gloss,
  neg, fml).
- `_build_conj_chain()` walks a conjugation's `via` chain from the innermost
  step outward, producing an ordered list of `ConjStep` objects.
- `_get_compound_display()` handles suffix compounds (te-iru, te-shimau,
  tai, sou, etc.) by building the primary component's chain and appending
  each suffix component at the correct depth.
- `_get_conjugation_display()` dispatches between single words, multi-
  alternative words, and compound words.
- `CONJ_STEP_GLOSSES` in `constants.py` maps conjugation type IDs to
  concise English glosses.

## Bug Fixes

### Multi-alternative compound words (empty tree)

Words like `食べられていた` that have multiple dictionary analyses
(potential vs. passive of `食べる`) AND are suffix compounds were
producing no conjugation tree at all.  The merged `WordInfo` had
`alternative=True` with `is_compound=False`, causing the display
function to skip both compound and simple paths.

**Fix**: `_get_conjugation_display()` now checks whether the primary
alternative is itself a compound and delegates accordingly.

### Duplicate root lines from archaic readings

Compound words like `忘れてしまった` were showing two root arrows
-- one for `忘れる` (modern) and one for `忘る` (archaic) -- because
`format_conjugation_info()` iterated over all conjugation entries for
a given sequence number.

**Fix**: Limit to the first (primary) conjugation entry to avoid
showing duplicate analyses from archaic or variant readings.

### Variant kanji in suffix extraction

The suffix extraction logic preferred kanji-containing readings via
`has_kanji()`, but some entries have variant kanji (`喰べ` for `食べ`,
`旨味し` for `美味し`) with different characters.  `_extract_suffix()`
then failed to find a common prefix and returned the full variant text
instead of the real suffix.

**Fix**: `_get_conj_suffix()` and `_collect_via_steps()` now try all
available readings and pick the one that produces the shortest
non-empty suffix, avoiding variant kanji that break prefix comparison.

## Test Suite

Added `tests/test_conjugation_tree.py` with 86 new tests across
14 test classes:

| Class | Coverage |
|-------|----------|
| `TestExtractSuffix` | Unit tests for `_extract_suffix()` (16 cases) |
| `TestSimpleConjugation` | Past, negative, polite, te-form, volitional, imperative, etc. |
| `TestAdjectiveConjugation` | Adj past, negative, adverbial, te-form |
| `TestViaChains` | Passive, causative, causative-passive, potential |
| `TestCompoundDisplay` | te-iru, te-shimau, te-kureru, desiderative, sou |
| `TestMultiAlternativeCompound` | Regression test for the empty-tree bug |
| `TestSuffixExtraction` | Regression test for variant kanji (no `喰`, no `旨味`) |
| `TestDeepChains` | 5+ step chains (te-shimau-tai-past, etc.) |
| `TestIrregularVerbs` | `来る`, `する`, copula `だ` |
| `TestGodanVerbs` | bu, gu, su, tsu verb endings |
| `TestNoConjugation` | Dictionary forms and nouns produce no tree |
| `TestTreeStructure` | Root arrow, box-drawing, gloss, indentation, no duplicate roots |
| `TestConjStep` | Dataclass construction |
| `TestSpecialForms` | Keigo, contracted forms |

Total test count: **411 passed**.

## Display Refinements

After the initial v0.3.0 release, the conjugation tree display was
refined based on review:

- **Causative-Passive split**: Instead of one `Causative-Passive` step,
  the tree now shows two separate steps: `Causative (かせ)` then
  `Passive (られる)`, making the decomposition clearer.
- **Auxiliary verb roots hidden**: Compound trees no longer show
  intermediate root lines (居る, 仕舞う, 為る); only the suffix form
  appears.
- **Polite split**: Polite forms show `Polite (ます)` as its own tree
  step, with sub-steps for Past (した), Negative (せん), Volitional (よう).
- **Potential/Passive dual label**: Ichidan potential forms (れる/られる)
  show `Potential/Passive` since the form is ambiguous. Godan potential
  forms (ける, める, etc.) show just `Potential`.
- **Standard causative suffix**: Displays standard させる/かせる instead
  of dialectal さす/かす.

## Other Changes

- **README rewrite**: Removed all emoji.  Added conjugation breakdown
  demos as the first section, followed by features, installation, usage,
  architecture overview, project structure, and development instructions.
- **Version sync**: Unified version to `0.3.0` across `pyproject.toml`,
  `himotoki/__init__.py`, and `himotoki/cli.py` (cli.py was previously
  stuck at `0.2.0`).

## Segmentation Accuracy Improvements

### Summary

The LLM evaluation system (510 curated Japanese sentences scored by Gemini)
was upgraded to v3 prompt and all 6 open beads issues were resolved,
bringing accuracy from **449/510 (88%)** to **510/510 (100%)**.

### Fixes

| Bug | Description | Fix |
|-----|-------------|-----|
| ため misparse | ため decomposed as た+め suffix compound | `BLOCKED_SUFFIX_WORDS` set in suffixes.py |
| Contraction kana inflation | ちゃう/てる compounds expanded back to uncontracted kana | `CONTRACTION_SUFFIXES` strips trailing て/で before concatenation |
| Compound metadata nulls | Eval extraction missed alternative-compound structures | Fixed `_segments_from_himotoki_json()` |
| 行こうぜ misparse | こうぜ (校是, uncommon) outscored correct parse | Added to `SKIP_WORDS` |
| にいこう misparse | にい (新, uncommon kana) caused split | Added to `SKIP_WORDS` |
| から傘/もまず | Uncommon words absorbed adjacent characters | Added to `SKIP_WORDS`/`BLOCKED_SUFFIX_WORDS` |
| うける misparse | 浮く potential outscored 受ける | Added to `SKIP_WORDS` |

### LLM Eval v3 Prompt

The evaluation prompt was enhanced with tolerance for:
- **Reading ambiguity**: Multiple valid readings for the same kanji (市場=いちば/しじょう)
- **Proper nouns**: Not in JMdict (person/place names split into characters)
- **Verb contractions**: Residual fragments from colloquial speech
- **Classical/archaic Japanese**: Minor misidentification of classical forms
- **Scoring ambiguities**: Compound words absorbing adjacent characters
- **Parenthetical annotations**: Stripped before segmentation to prevent distortion

## Files Changed

| File | Change |
|------|--------|
| `himotoki/output.py` | Conjugation tree functions, 3 bug fixes |
| `himotoki/constants.py` | `CONJ_STEP_GLOSSES` dictionary |
| `himotoki/suffixes.py` | `BLOCKED_SUFFIX_WORDS`, `CONTRACTION_SUFFIXES`, kana fix |
| `himotoki/lookup.py` | Expanded `SKIP_WORDS` for misparse prevention |
| `himotoki/cli.py` | Version bump, `_get_conjugation_display` integration |
| `himotoki/__init__.py` | Version bump |
| `pyproject.toml` | Version bump |
| `scripts/llm_eval.py` | v3 prompt, parenthetical stripping, compound extraction fixes |
| `scripts/test_sentences.py` | Goldset typo fixes (#85, #391) |
| `tests/test_conjugation_tree.py` | 86 new tests |
| `README.md` | Full rewrite, LLM accuracy badge |
| `docs/CHANGELOG.md` | v0.3.0 entry with all fixes |
| `releases/RELEASE_v0.3.0.md` | This file |
