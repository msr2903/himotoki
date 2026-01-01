<h1 align="center">Himotoki (紐解き)</h1>

<p align="center">
  <strong>A high-performance Japanese Morphological Analyzer and Romanization Tool.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python Version"></a>
  <a href="https://github.com/himotoki/himotoki/issues"><img src="https://img.shields.io/github/issues/himotoki/himotoki" alt="Issues"></a>
</p>

---

## 📖 Overview

**Himotoki** (meaning "to unravel" or "to untie a knot") is a Python port of the renowned [Ichiran](https://github.com/tshatrov/ichiran) morphological analyzer. It provides sophisticated Japanese text segmentation, romanization, and linguistic analysis without the heavy dependency on PostgreSQL, using a lightweight **SQLite3** backend instead.

Whether you're building a language learning app, a search engine, or just need to romanize Japanese text with high accuracy, Himotoki is designed to be your go-to library.

## ✨ Key Features

- 🧩 **Advanced Segmentation**: Accurate word boundary detection using Viterbi-based pathfinding and Ichiran's synergy scoring.
- 🔡 **Romanization**: Supports multiple systems including Hepburn, Kunrei, and Passport.
- 🔄 **Kana Conversion**: Fluidly convert between Hiragana, Katakana, and Romaji.
- 🔢 **Number Parsing**: Robust handling of Japanese numerals and counters.
- 📚 **Dictionary Integration**: Full support for JMdict and KANJIDIC data.
- 📊 **Text Analysis**: Estimate text difficulty (JLPT levels) and extract detailed kanji information.
- 🚀 **CLI Interface**: Powerful command-line tools for quick text analysis.

## 🚀 Getting Started

### Installation

```bash
pip install himotoki
```

### Database Initialization

Himotoki requires dictionary data to function. You can automatically download and initialize the database with a single command:

```bash
himotoki init --download
```

## 🛠 Usage

### Command Line Interface

Himotoki comes with a comprehensive CLI:

```bash
# Analyze a sentence
himotoki analyze "日本語の勉強は楽しいです。"

# Romanize text
himotoki romanize "こんにちは" --method hepburn

# Segment text into words (JSON output)
himotoki segment "走っています" --json

# Get kanji details
himotoki kanji "学習"
```

### Python API

```python
from himotoki import romanize, simple_segment, WordInfo

# Romanization
print(romanize("学校に行きます")) 
# Output: gakkou ni ikimasu

# Segmentation
words = simple_segment("美味しい料理を食べた")
for word in words:
    print(f"{word.text} ({word.kana})")
```

## 🏗 Architecture

Himotoki is built with performance and portability in mind:

- **Engine**: Ported from Ichiran's Lisp implementation to modern Python.
- **Database**: Uses SQLite3 for efficient, single-file dictionary lookups.
- **Scoring**: Implements Ichiran's complex scoring rules to ensure the most natural segmentation.

## 🤝 Contributing

Contributions are welcome! Please check our [Contributing Guidelines](CONTRIBUTING.md) to get started.

## 📜 License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **tshatrov** for the original [Ichiran](https://github.com/tshatrov/ichiran) project.
- **EDRDG** for the JMdict and KANJIDIC projects.

---

<p align="center">Made with ❤️ for Japanese learners and developers.</p>
