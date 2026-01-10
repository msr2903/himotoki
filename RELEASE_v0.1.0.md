# 🧶 Himotoki v0.1.0 - Initial Release

**Himotoki (紐解き)** - A pure Python Japanese morphological analyzer, a complete port of [ichiran](https://github.com/tshatrov/ichiran).

> *"Unraveling the complexities of the Japanese language, one string at a time."*

---

## ✨ Highlights

This is the **first public release** of Himotoki, bringing ichiran's powerful Japanese text analysis capabilities to the Python ecosystem with a portable SQLite backend—no PostgreSQL or Docker required!

### 🚀 Key Features

- **Smart Segmentation** — Uses dynamic programming (Viterbi-style algorithm) to find the most linguistically plausible word boundaries
- **Deep Dictionary Integration** — Built on JMDict, providing rich metadata, glosses, readings, and part-of-speech information for 200,000+ entries
- **Advanced Deconjugation** — Recursively traces conjugated verbs, adjectives, and auxiliary forms back to their dictionary entries
- **Scoring Engine** — Implements ichiran's "synergy" and penalty rules for high-quality, context-aware results
- **Counter System** — Full support for Japanese counters with proper number-counter merging
- **Portable SQLite Backend** — No external database servers required

---

## 📦 Installation

```bash
pip install himotoki
```

### First-Time Setup

On first use, Himotoki will prompt you to initialize the dictionary database:

```
🧶 Welcome to Himotoki!

First-time setup required. This will:
  • Download JMdict dictionary data (~15MB compressed)
  • Generate optimized SQLite database (~3GB)
  • Store data in ~/.himotoki/

Proceed with setup? [Y/n]:
```

> ⚠️ **Disk Space**: Requires approximately **3GB** of free disk space. Setup takes 10-20 minutes.

---

## 🔧 Usage

### Command Line

```bash
# Basic romanization
himotoki "学校で勉強しています"
# → gakkou de benkyou shiteimasu

# Detailed analysis with dictionary info
himotoki -i "日本語を勉強しています"

# Full JSON output for integration
himotoki -f "今日は天気がいいですね"
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

## 🏗️ Architecture

Himotoki is designed with modularity in mind:

| Module | Purpose |
|--------|---------|
| `segment.py` | Viterbi-style pathfinding and word lattice construction |
| `lookup.py` | Dictionary retrieval, scoring, and word candidate generation |
| `output.py` | Result formatting, WordInfo construction, and conjugation display |
| `suffixes.py` | Grammar node generation for auxiliary verbs and compound forms |
| `synergies.py` | Edge scoring with synergy bonuses and penalties |
| `counters.py` | Japanese counter system with number-counter merging |
| `characters.py` | Romanization, kana conversion, and character classification |
| `loading/` | JMDict XML parsing and database generation |

---

## 📊 Technical Details

- **Python**: 3.10+
- **Database**: SQLite with WAL mode, memory-mapped I/O, and 64MB cache
- **Dependencies**: SQLAlchemy 2.0+, lxml
- **Dictionary**: JMDict (200,000+ entries)
- **Conjugations**: 47 verb/adjective types × 14 conjugation forms

---

## 🙏 Acknowledgments

- **[tshatrov](https://github.com/tshatrov)** for the original [ichiran](https://github.com/tshatrov/ichiran) implementation in Common Lisp
- **[EDRDG](https://www.edrdg.org/)** for the invaluable JMDict and JMdictDB resources
- **[JMdictDB](https://gitlab.com/yamagoya/jmdictdb)** for conjugation data

---

## 📜 License

MIT License - See [LICENSE](LICENSE) for details.

---

**Full Changelog**: https://github.com/msr2903/himotoki/commits/v0.1.0
