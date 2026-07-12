"""
Word trie for fast dictionary surface form lookup.

Uses marisa-trie for memory-efficient storage (~50-80MB for 9M entries
vs ~300-500MB for a dict-based trie).

This module provides a prefix trie of all dictionary surface forms
(kanji_text and kana_text). It's used to filter substring candidates
before hitting the database - most substrings don't exist in the dictionary.
"""

import os
from pathlib import Path
from typing import Optional

import marisa_trie

# Module-level singleton
_WORD_TRIE: Optional[marisa_trie.Trie] = None


def get_trie_path(db_path: Path) -> Path:
    """Return path for persisted trie file next to the database."""
    db_path = Path(db_path)
    if db_path.suffix == ".db":
        return db_path.with_suffix(".trie")
    return db_path.parent / f"{db_path.name}.trie"


def _get_db_path_from_session(session) -> Path:
    """Resolve database path from session or environment."""
    env_path = os.environ.get("HIMOTOKI_DB_PATH")
    if env_path:
        return Path(env_path)

    bind = session.get_bind()
    if bind is not None and bind.url.database:
        return Path(bind.url.database)

    from himotoki.db.connection import _get_default_db_path
    return _get_default_db_path()


def get_word_trie() -> Optional[marisa_trie.Trie]:
    """Get the initialized trie, or None if not ready."""
    return _WORD_TRIE


def is_trie_ready() -> bool:
    """Check if trie has been initialized."""
    return _WORD_TRIE is not None


def _build_trie_from_db(session) -> marisa_trie.Trie:
    """Build trie from database surface forms."""
    conn = session.connection().connection
    cursor = conn.cursor()

    cursor.execute(
        "SELECT text FROM kana_text "
        "UNION ALL "
        "SELECT text FROM kanji_text"
    )
    rows = cursor.fetchall()

    return marisa_trie.Trie(row[0] for row in rows)


def init_word_trie(session) -> marisa_trie.Trie:
    """
    Initialize the word trie from database.
    
    Loads all unique surface forms from kanji_text and kana_text tables.
    Persists trie to disk next to the database for faster subsequent loads.
    Called during warm_up().
    
    Args:
        session: Database session
        
    Returns:
        The initialized marisa_trie.Trie
    """
    global _WORD_TRIE
    if _WORD_TRIE is not None:
        return _WORD_TRIE

    db_path = _get_db_path_from_session(session)
    trie_path = get_trie_path(db_path)

    if db_path.exists() and trie_path.exists():
        trie_mtime = trie_path.stat().st_mtime
        db_mtime = db_path.stat().st_mtime
        if trie_mtime >= db_mtime:
            _WORD_TRIE = marisa_trie.Trie().mmap(str(trie_path))
            return _WORD_TRIE

    _WORD_TRIE = _build_trie_from_db(session)

    if db_path.exists():
        trie_path.parent.mkdir(parents=True, exist_ok=True)
        _WORD_TRIE.save(str(trie_path))

    return _WORD_TRIE


def trie_contains(word: str) -> bool:
    """
    Check if word exists in the trie.
    
    Returns False if trie is not initialized (graceful fallback).
    
    Args:
        word: Surface form to check
        
    Returns:
        True if word exists in dictionary, False otherwise
    """
    if _WORD_TRIE is None:
        return True  # Fallback: assume it might exist, let DB check
    return word in _WORD_TRIE


def trie_has_prefix(prefix: str) -> bool:
    """
    Check if any word in the trie starts with the given prefix.
    
    Useful for early termination: if no word starts with a prefix,
    we can skip all longer substrings from that position.
    
    Args:
        prefix: Prefix to check
        
    Returns:
        True if any word starts with prefix, False otherwise
    """
    if _WORD_TRIE is None:
        return True  # Fallback: assume it might exist
    try:
        next(iter(_WORD_TRIE.iterkeys(prefix)))
        return True
    except StopIteration:
        return False


def get_trie_size() -> int:
    """Get number of entries in the trie, or 0 if not initialized."""
    if _WORD_TRIE is None:
        return 0
    return len(_WORD_TRIE)
