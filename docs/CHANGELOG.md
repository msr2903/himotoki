# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

### Fixed
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
