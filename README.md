# 🧶 Himotoki (紐解き)

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Himotoki** (紐解き, "unraveling" or "untying strings") is a high-performance Python port of [ichiran](https://github.com/tshatrov/ichiran), the comprehensive Japanese morphological analyzer. It provides sophisticated text segmentation, dictionary lookup, and conjugation analysis, all powered by a portable SQLite backend.

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
# Clone the repository
git clone https://github.com/himotoki/himotoki.git
cd himotoki

# Install in development mode with all dependencies
pip install -e ".[dev]"
```

### Quick CLI Usage

Analyze Japanese text directly from your terminal:

```bash
# Basic segmentation and romanization
himotoki "学校で勉強しています"

# Detailed analysis with dictionary info
himotoki -i "学校で勉強しています"

# Full JSON output for integration
himotoki -f "学校で勉強しています"
```

### Python API Example

Integrate Himotoki into your own projects with ease:

```python
from himotoki.db.connection import get_session
from himotoki.output import dict_segment

# Initialize session
session = get_session()

# Analyze a sentence
results = dict_segment(session, "日本語を勉強しています", limit=1)

for word_infos, score in results:
    print(f"Path Score: {score}")
    for wi in word_infos:
        print(f"Result: {wi.text} 【{wi.kana}】 - {wi.gloss[:50]}...")
```

---

## 🏗️ Project Architecture

Himotoki is designed with modularity in mind, keeping the database, logic, and output layers distinct.

```text
himotoki/
├── 🧠 segment.py    # Pathfinding and segmentation logic
├── 📖 lookup.py     # Dictionary retrieval and scoring
├── 🔄 deconjugate/  # Conjugation rules and engine
├── 🗄️ db/           # SQLAlchemy models and connection management
├── 🔤 characters.py # Kana/Kanji classification and conversion
└── 🖥️ cli.py        # Command line interface
```

---

## 📊 Evaluation & Correctness

Himotoki aims for 1:1 parity with the original `ichiran` implementation. We use a comprehensive evaluation suite to track accuracy:

```bash
# Run the comparison script against ichiran results
python compare_ichiran.py
```

Check out `ARCHITECTURE.md` for a deep dive into the internal mechanics and scoring algorithms.

---

## 🛠️ Development

We welcome contributions! To get started:

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
