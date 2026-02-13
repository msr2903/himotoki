# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-02-08

### Added
- **30+ new suffix compounds**: Compound verbs (出す, 切る, 合う, 込む,
  始める, 終わる, 付ける), te-form auxiliaries (てやる, てまいる,
  てくださる, てさしあげる), adjective suffixes (っぽい, 難い, み, 方,
  らしい+noun), and more (放題, やすい, まくる, 直す, 損なう, 忘れる,
  終える, 辛い, ぎみ, っぱなし, たち, なで).
- **Na-adjective + suffix chaining**: Na-adj stems (静か, 元気, 便利)
  now connect to すぎる, っぽい, み, そう handlers.
- **Auxiliary verb labels**: Conjugated auxiliary verbs (しまう, いる,
  たい, etc.) now show their identity and description in the conjugation
  tree instead of being invisible.
- **Suffix descriptions in display**: Base-form suffix components include
  grammatical descriptions (e.g., `└─ いる (indicates continuing action)`).
- **Te-form suffixes**: てみる (try doing), てあげる (do for someone),
  てほしい (want someone to) recognized as compound words.
- `SEQ_MIRU`, `SEQ_AGERU`, `SEQ_HOSHII`, `SEQ_AU`, `SEQ_KOMU`,
  `SEQ_HOUDAI`, `SEQ_OWARU`, `SEQ_HAJIMERU`, `SEQ_TSUKERU`, `SEQ_YARU`,
  `SEQ_MAIRU`, `SEQ_KUDASARU`, `SEQ_SASHIAGERU` and more constants.
- 22 new tests (433 total, up from 411).

### Fixed
- **だろう/でしょう segmentation over-absorption**: Sentence-level copula forms
  are no longer forced into preceding-word suffix compounds. Examples like
  神だろう, 近いだろう, 迷惑でしょうか now segment compositionally.
- **Copula polite label in tree**: Copula-path polite steps now render as
  `Polite (です)` instead of `Polite (ます)`.
- **Standalone copula trees**: Standalone forms now show conjugation trees for
  ではない, だろう, and でしょう (with source `← だ`).
- **na-adjective + copula ambiguity**: Fixed bad splits such as
  大丈夫で + すか and 静かで + した by preferring copula analyses.
- **na-adjective copula tree clarity**: Forms like 静かでした now show
  `← 静かだ` → `Polite (です)` → `Past (~ta) (でした)`.
- **i-adjective + すぎる source form**: 高すぎる now shows source and stem in
  the tree (`← 高い` → `Adjective Stem` → `すぎる`).
- **Negative split in conjugation tree**: Negative conjugations now display
  as separate tree levels (Negative + Past) instead of combined (not Past).
  食べられなかった shows `└─ Negative (ない): not` → `└─ Past (~ta) (かった)`.
  Also applies to formal (ません), potential (行けない), and adjective forms.
- **ないで reading bug**: Compound kana now uses the correct kanji reading
  ordinal instead of always using ord=0.  食べないでほしい correctly shows
  【たべないで ほしい】 (was 【たべなくて ほしい】).
- **ちゃ/じゃ contraction reading**: Surface pronunciation preserved for
  contracted forms.  食べちゃいけない shows 【たべちゃ】 (was 【たべは】).
- **Conjugation chain aux verb labels**: Conjugated auxiliary verbs
  (e.g., しまう in 飲んでしまった) now visible in conjugation tree.
- **Suffix descriptions in display**: Base-form and conjugated suffix
  components now show descriptions. Uses kana reading for auxiliary verbs
  (しまう not 仕舞う).
- 13 grammar pattern issues (abbreviations, suffix chains, handler
  improvements, label fixes).

## [0.3.0] - 2025-07-17

### Added
- **Conjugation breakdown tree**: Visual display tracing every inflection
  step from surface form back to dictionary root.  Renders as an indented
  tree with grammatical labels, suffix text, and English glosses.
- `ConjStep` dataclass and `CONJ_STEP_GLOSSES` dictionary in constants.py
  for conjugation step representation.
- `_build_conj_chain()`, `_get_compound_display()`,
  `_get_conjugation_display()`, `_collect_via_steps()`,
  `_get_conj_suffix()`, `_extract_suffix()` in output.py.
- 86 new tests in `tests/test_conjugation_tree.py` covering simple
  conjugations, adjectives, via chains, compound words, deep chains,
  irregular verbs, godan verbs, and structural properties.
- LLM accuracy evaluation v3 prompt with comprehensive tolerance for
  reading ambiguity, proper nouns, verb contractions, classical forms,
  and scoring ambiguities.  Achieves **510/510 (100%)** on the 510-sentence
  gold set.

### Fixed
- **ため misparse**: Added `BLOCKED_SUFFIX_WORDS` to prevent common words
  like ため from being decomposed into suffix compounds (ta + me).
- **Contraction kana inflation**: Contracted forms (ちゃう, てる) no longer
  produce inflated readings that expand back to the uncontracted form.
  `CONTRACTION_SUFFIXES` set in suffixes.py strips trailing て/で from
  the primary word kana before concatenation.
- **Compound metadata nulls**: LLM eval extraction now handles alternative
  entries that are themselves compounds, fixing null seq/POS/kana fields.
- **行こうぜ misparse**: Added こうぜ (校是, uncommon) to `SKIP_WORDS`.
- **にいこう misparse**: Added にい (新, uncommon kana reading) to
  `SKIP_WORDS`.
- **から傘 merge**: Added から傘 (karakasa) to `SKIP_WORDS`.
- **もまず misparse**: Added もまず to `BLOCKED_SUFFIX_WORDS`.
- **うける misparse**: Added 浮く potential form to `SKIP_WORDS`.
- **Goldset typos**: Fixed two typos in test sentences (#85, #391).
- Multi-alternative compound words (e.g., 食べられていた) no longer
  produce an empty conjugation tree.
- Duplicate root lines from archaic conjugation analyses (e.g., 忘る
  alongside 忘れる) are no longer shown.
- Variant kanji in suffix extraction (e.g., 喰べ for 食べ, 旨味し for
  美味し) no longer break the conjugation chain display.
- Synced `VERSION` in cli.py with pyproject.toml (was stuck at 0.2.0).

### Changed
- Causative-Passive displayed as two separate tree steps (Causative + Passive)
  instead of one combined step.
- Auxiliary verb roots (居る, 仕舞う, 為る) hidden from compound trees;
  only the suffix form appears.
- Polite forms split into own tree step with sub-steps for Past/Negative/Volitional.
- Ichidan potential forms show dual `Potential/Passive` label; godan stays `Potential`.
- Standard causative suffix (させる/かせる) preferred over dialectal (さす/かす).
- README rewritten: removed all emoji, added conjugation breakdown demos
  as the first section, restructured for clarity.
- LLM eval rescore now normalizes verdict based on score threshold (≥70 = pass)
  instead of trusting the LLM's verdict field directly.

## [0.1.1] - 2026-01-10

### Changed
- **CLI flag restructure**: Redesigned CLI output flags for better UX
  - Default (no flags): Dictionary info only
  - `-r` / `--romanize`: Simple romanization output
  - `-f` / `--full`: Full output (romanization + dictionary info)
  - `-k` / `--kana`: Kana reading with spaces
  - `-j` / `--json`: JSON output (was `-f`)
- Output flags are now mutually exclusive (prevents conflicting flags)
- Added `VERSION` and `CONJUGATION_ROOT` constants
- Improved error messages with output mode context
- Enhanced input validation (rejects whitespace-only input)

### Added
- `get_kana()` helper function for robust kana extraction
- Comprehensive CLI test suite (34 tests)

## [0.1.0] - 2026-01-01

### Added
- Initial release of Himotoki.
- Japanese morphological analyzer (Python port of Ichiran).
- CLI for segmenting and romanizing Japanese text.
- Character conversion utilities (Hiragana, Katakana, Normalization).
- Number conversion tools (Kanji to Arabic, Arabic to Kanji/Kana).
- Kanji information lookup and text difficulty estimation.
- SQLite3 database backend for JMdict and KANJIDIC.
- Automatic dictionary download and initialization.
