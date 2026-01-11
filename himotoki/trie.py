"""
Word trie for fast dictionary surface form lookup.

Uses marisa-trie for memory-efficient storage (~50-80MB for 9M entries
vs ~300-500MB for a dict-based trie).

This module provides a prefix trie of all dictionary surface forms
(kanji_text and kana_text). It's used to filter substring candidates
before hitting the database - most substrings don't exist in the dictionary.
"""

from typing import Optional

import marisa_trie

# Module-level singleton
_WORD_TRIE: Optional[marisa_trie.Trie] = None


def get_word_trie() -> Optional[marisa_trie.Trie]:
    """Get the initialized trie, or None if not ready."""
    return _WORD_TRIE


def is_trie_ready() -> bool:
    """Check if trie has been initialized."""
    return _WORD_TRIE is not None


def init_word_trie(session) -> marisa_trie.Trie:
    """
    Initialize the word trie from database.
    
    Loads all unique surface forms from kanji_text and kana_text tables.
    Called during warm_up().
    
    Args:
        session: Database session
        
    Returns:
        The initialized marisa_trie.Trie
    """
    global _WORD_TRIE
    if _WORD_TRIE is not None:
        return _WORD_TRIE
    
    # Get raw connection for fast cursor iteration
    conn = session.connection().connection
    cursor = conn.cursor()
    
    # Use UNION ALL (faster than UNION - no dedup overhead)
    # marisa-trie handles duplicates automatically
    cursor.execute(
        "SELECT text FROM kana_text "
        "UNION ALL "
        "SELECT text FROM kanji_text"
    )
    rows = cursor.fetchall()
    
    # Build marisa-trie (handles duplicates, ~50-80MB for 9M entries)
    _WORD_TRIE = marisa_trie.Trie(row[0] for row in rows)
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
    # marisa_trie.keys(prefix) returns all keys starting with prefix
    # We just need to check if there's at least one
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
