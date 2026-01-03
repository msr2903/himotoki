"""
Database package for himotoki.
Contains SQLite schema, ORM models, and connection management.
"""

from himotoki.db.models import (
    Entry,
    KanjiText,
    KanaText,
    Sense,
    Gloss,
    SenseProp,
    RestrictedReading,
    Conjugation,
    ConjProp,
    ConjSourceReading,
)
from himotoki.db.connection import get_connection, get_session, init_database

__all__ = [
    "Entry",
    "KanjiText",
    "KanaText",
    "Sense",
    "Gloss",
    "SenseProp",
    "RestrictedReading",
    "Conjugation",
    "ConjProp",
    "ConjSourceReading",
    "get_connection",
    "get_session",
    "init_database",
]