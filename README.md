# Himotoki (紐解き)

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-411%20passed-brightgreen.svg)](tests/)

**Himotoki** (紐解き, "unraveling") is a Python remake of
[ichiran](https://github.com/tshatrov/ichiran), the comprehensive Japanese
morphological analyzer. It segments Japanese text into words, provides
dictionary definitions, and traces conjugation chains back to their root
forms -- all powered by a portable SQLite backend.

---

## Features

- **Portable SQLite Backend** -- No PostgreSQL setup required. Dictionary data
  lives in a single file (~3 GB) that is generated on first use.
- **Dynamic-Programming Segmentation** -- Uses a Viterbi-style algorithm to
  find the most linguistically plausible word boundaries.
- **Deep Dictionary Integration** -- Built on JMDict, providing glosses,
  part-of-speech tags, usage notes, and cross-references.
- **Recursive Deconjugation** -- Walks the conjugation database to trace
  inflected forms (passive, causative, te-form, negation, etc.) back to
  dictionary entries.
- **Conjugation Breakdown Tree** -- Displays each transformation step in a
  visual tree with the suffix, grammatical label, and English gloss.
- **Compound Word Detection** -- Recognizes suffix compounds
  (te-iru progressive, te-shimau completion, tai desiderative, sou
  appearance, etc.) and shows their internal structure.
- **Scoring Engine** -- Implements synergy and penalty heuristics from
  ichiran to resolve segmentation ambiguities.

---

## Installation

```bash
pip install himotoki
```

### First-Time Setup

On first run, Himotoki will offer to download JMDict and build the
SQLite database. The process takes approximately 10-20 minutes and
requires about 3 GB of free disk space.

```bash
himotoki "日本語テキスト"
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Welcome to Himotoki!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

First-time setup required. This will:
  - Download JMdict dictionary data (~15MB compressed)
  - Generate optimized SQLite database (~3GB)
  - Store data in ~/.himotoki/

Proceed with setup? [Y/n]:
```

Non-interactive setup for CI environments:

```bash
himotoki setup --yes
```

---

## Usage

### Command Line

```bash
# Default: dictionary info with conjugation breakdown
himotoki "学校で勉強しています"

# Full output: romanization + dictionary info + conjugation tree
himotoki -f "食べられなかった"

# Simple romanization
himotoki -r "学校で勉強しています"
# Output: gakkou de benkyou shiteimasu

# Kana reading with spaces
himotoki -k "学校で勉強しています"
# Output: がっこう で べんきょう しています

# JSON output for programmatic use
himotoki -j "学校で勉強しています"
```

### Python API

```python
import himotoki

# Optional: pre-warm caches for faster first request
himotoki.warm_up()

# Analyze Japanese text
results = himotoki.analyze("日本語を勉強しています")

for words, score in results:
    for w in words:
        print(f"{w.text} 【{w.kana}】 - {w.gloss[:50]}...")
```

---

## Conjugation Breakdown

Himotoki traces conjugated words through every transformation step,
showing the root form and each inflection applied:

```
$ himotoki -f "書かせられていた"

kakaserareteita

* kakaserareteita  書かせられていた 【かかせられていた】

  ← 書く 【かく】
  └─ Causative (かせ): makes do
       └─ Passive (られる): is done (to)
            └─ Conjunctive (~te) (て): and/then
                 └─ Past (~ta) (た): did/was
```

A deeply nested chain parsed into its constituent parts:

```
$ himotoki -f "飲んでしまいたかった"

nondeshimaitakatta

* nondeshimaitakatta  飲んでしまいたかった 【のんでしまいたかった】

  ← 飲む 【のむ】
  └─ Conjunctive (~te) (んで): and/then
       └─ Continuative (~i) (い): and (stem)
            └─ Past (~ta) (かった): did/was
```

Full sentence analysis with per-word dictionary entries and conjugation trees:

```
$ himotoki "学校で勉強しています"

* 学校 【がっこう】
1. [n] school

* で
1. [prt] at; in
2. [prt] at; when
3. [prt] by; with

* 勉強しています 【べんきょう しています】
1. [n,vs,vt] study
2. [n,vs,vi] diligence; working hard
  └─ Conjunctive (~te) (て): and/then
       └─ Polite (ます)
```

---

## How It Works

Himotoki processes Japanese text through three stages:

1. **Segmentation** -- A dynamic-programming algorithm considers all
   possible word boundaries and selects the highest-scoring path.
   Scoring uses dictionary frequency data, part-of-speech synergies,
   and penalty heuristics ported from ichiran.

2. **Suffix Compound Assembly** -- Adjacent segments are checked against
   known suffix patterns (te-iru, te-shimau, tai, sou, etc.). Matching
   segments are merged into compound WordInfo objects with preserved
   component structure.

3. **Conjugation Chain Resolution** -- For each conjugated word, the
   system queries the conjugation database to walk the `via` chain from
   the surface form back to the dictionary entry. Each step records the
   conjugation type, suffix text, and English gloss, then formats the
   result as an indented tree.

---

## Project Structure

```
himotoki/
    segment.py             # Viterbi-style segmentation engine
    lookup.py              # Dictionary lookup, scoring, conjugation data
    output.py              # WordInfo, conjugation tree, JSON/text formatting
    suffixes.py            # Suffix compound detection (te-iru, tai, etc.)
    synergies.py           # Part-of-speech synergy and penalty rules
    conjugation_hints.py   # Supplementary conjugation patterns
    constants.py           # Conjugation type IDs, POS tags, glosses
    characters.py          # Kana/kanji conversion, romanization
    counters.py            # Japanese counter expression handling
    cli.py                 # Command-line interface
    db/                    # SQLAlchemy models and connection management
    loading/               # JMDict XML parsing and database generation
scripts/
    llm_eval.py            # LLM-based accuracy evaluation (510 sentences)
    check_segments.py      # Quick segmentation change checker
    llm_report.py          # HTML report generator
tests/                     # 411 tests (pytest + hypothesis)
data/                      # Dictionary data, evaluation datasets
```

---

## Development

### Setup

```bash
git clone https://github.com/msr2903/himotoki.git
cd himotoki
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -x --tb=short
```

### Testing

```bash
# Run all tests
pytest tests/ -x --tb=short

# Run conjugation tree tests only
pytest tests/test_conjugation_tree.py -v

# Run with coverage
pytest tests/ --cov=himotoki --cov-report=term-missing
```

### LLM Accuracy Evaluation

The project includes an LLM-based evaluation system that scores
segmentation accuracy against 510 curated Japanese sentences:

```bash
python scripts/llm_eval.py --quick          # 50-sentence subset
python scripts/llm_eval.py                  # Full evaluation
python scripts/llm_eval.py --rescore 5      # Re-evaluate entry #5
python scripts/llm_report.py                # Generate HTML report
```

---

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.

## Acknowledgments

- [tshatrov](https://github.com/tshatrov) for the original
  [ichiran](https://github.com/tshatrov/ichiran) implementation.
- [EDRDG](https://www.edrdg.org/) for the JMDict dictionary resource.
