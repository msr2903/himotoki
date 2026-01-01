"""
Himotoki - Japanese Morphological Analyzer and Romanization Tool

A Python port of Ichiran, using SQLite3 instead of PostgreSQL.
"""

__version__ = "0.1.0"

# Core romanization
from himotoki.romanize import romanize, romanize_word

# Character conversion
from himotoki.characters import (
    normalize, as_hiragana, as_katakana,
    is_kana, is_kanji, test_word, mora_length,
    split_sentences, split_paragraphs
)

# Segmentation
from himotoki.dict import simple_segment, dict_segment, find_word, lookup_conjugation, WordInfo

# De-romanization
from himotoki.deromanize import romaji_to_hiragana, romaji_to_katakana

# Number conversion
from himotoki.numbers import number_to_kanji, number_to_kana, parse_number

__all__ = [
    # Version
    "__version__",
    # Romanization
    "romanize",
    "romanize_word",
    # Character conversion
    "normalize",
    "as_hiragana",
    "as_katakana",
    "is_kana",
    "is_kanji",
    "test_word",
    "mora_length",
    "split_sentences",
    "split_paragraphs",
    # Segmentation
    "simple_segment",
    "dict_segment",
    "find_word",
    "WordInfo",
    # De-romanization
    "romaji_to_hiragana",
    "romaji_to_katakana",
    # Numbers
    "number_to_kanji",
    "number_to_kana",
    "parse_number",
    # Conjugation lookup
    "lookup_conjugation",
]
