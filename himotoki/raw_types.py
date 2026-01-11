"""
Lightweight data structures for raw SQL queries.

These namedtuples replace the heavy ORM objects (KanaText, KanjiText) in
performance-critical paths. They have identical attribute names but ~10x
less memory overhead.

Usage:
    # In hot path (segment.py)
    from himotoki.raw_types import RawKanaReading, RawKanjiReading
    
    cursor.execute("SELECT id, seq, text, ord, common, best_kanji FROM kana_text ...")
    results = [RawKanaReading(*row) for row in cursor.fetchall()]
"""

from typing import NamedTuple, Optional


class RawKanaReading(NamedTuple):
    """
    Lightweight replacement for KanaText ORM object.
    
    Column order MUST match: id, seq, text, ord, common, best_kanji
    """
    id: int
    seq: int
    text: str
    ord: int
    common: Optional[int]
    best_kanji: Optional[str]


class RawKanjiReading(NamedTuple):
    """
    Lightweight replacement for KanjiText ORM object.
    
    Column order MUST match: id, seq, text, ord, common, best_kana
    """
    id: int
    seq: int
    text: str
    ord: int
    common: Optional[int]
    best_kana: Optional[str]
