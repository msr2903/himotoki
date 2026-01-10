# 🧶 Himotoki (紐解き)

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Himotoki** (紐解き, "unraveling" or "untying strings") is a Python remake of [ichiran](https://github.com/tshatrov/ichiran), the comprehensive Japanese morphological analyzer. It provides sophisticated text segmentation, dictionary lookup, and conjugation analysis, all powered by a portable SQLite backend.

---

## ✨ Key Features

- 🚀 **Fast & Portable**: Uses SQLite for rapid dictionary lookups without the need for a complex PostgreSQL setup.
- 🧠 **Smart Segmentation**: Employs dynamic programming (Viterbi-style) to find the most linguistically plausible segmentation.
- 📚 **Deep Dictionary Integration**: Built on JMDict, providing rich metadata, glosses, and part-of-speech information.
- 🔄 **Advanced Deconjugation**: Recursively traces conjugated verbs and adjectives back to their dictionary forms.
- 📊 **Scoring Engine**: Implements the "synergy" and penalty rules from ichiran to ensure high-quality results.
- 🛠️ **Developer Friendly**: Clean Python API and a robust CLI for quick analysis.

---

## 🚀 Getting Started

### Installation

```bash
pip install himotoki
```

### First-Time Setup

On first use, Himotoki will prompt you to download and initialize the dictionary database:

```bash
himotoki "日本語テキスト"
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧶 Welcome to Himotoki!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

First-time setup required. This will:
  • Download JMdict dictionary data (~15MB compressed)
  • Generate optimized SQLite database (~3GB)
  • Store data in ~/.himotoki/

Proceed with setup? [Y/n]:
```

> ⚠️ **Disk Space**: The database requires approximately **3GB** of free disk space.  
> The setup process takes approximately **10-20 minutes** to complete.

You can also run setup manually:
```bash
himotoki setup            # Interactive setup
himotoki setup --yes      # Non-interactive (for scripts/CI)
```

### Quick CLI Usage

Analyze Japanese text directly from your terminal:

```bash
# Default: Dictionary info only
himotoki "学校で勉強しています"

# Simple romanization
himotoki -r "学校で勉強しています"

# Full output (romanization + dictionary info)
himotoki -f "学校で勉強しています"

# Kana reading with spaces
himotoki -k "学校で勉強しています"

# JSON output for integration
himotoki -j "学校で勉強しています"
```

### Python API Example

Integrate Himotoki into your own projects with ease:

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

## 🏗️ Project Structure

Himotoki is designed with modularity in mind, keeping the database, logic, and output layers distinct.

```text
himotoki/
├── himotoki/          # Main package
│   ├── 🧠 segment.py    # Pathfinding and segmentation logic
│   ├── 📖 lookup.py     # Dictionary retrieval and scoring
│   ├── 🔄 constants.py  # Shared constants and SEQ definitions
│   ├── 🗄️ db/           # SQLAlchemy models and connection
│   ├── 📚 loading/      # JMdict and conjugation loaders
│   └── 🖥️ cli.py        # Command line interface
├── scripts/           # Developer tools
│   ├── compare.py       # Ichiran comparison suite
│   ├── init_db.py       # Database initialization
│   └── report.py        # HTML report generator
├── tests/             # Test suite
├── data/              # Dictionary data files
├── output/            # Generated results and reports
└── docs/              # Documentation
```

---

## 🛠️ Development

We welcome contributions! To get started:

### Install from Source

```bash
git clone https://github.com/msr2903/himotoki.git
cd himotoki
pip install -e ".[dev]"
```

### Development Commands

1. **Tests**: `pytest`
2. **Coverage**: `pytest --cov=himotoki`
3. **Linting**: `ruff check .`
4. **Formatting**: `black .`

---

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.

## 🙏 Acknowledgments

- **[tshatrov](https://github.com/tshatrov)** for the original [ichiran](https://github.com/tshatrov/ichiran) implementation.
- **[EDRDG](https://www.edrdg.org/)** for the invaluable JMDict resource.

---

<p align="center">
  <i>"Unraveling the complexities of the Japanese language, one string at a time."</i>
</p>
