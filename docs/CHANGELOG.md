# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
