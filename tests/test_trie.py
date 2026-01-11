"""Tests for the word trie module."""

import pytest
import marisa_trie

from himotoki.trie import (
    get_word_trie,
    is_trie_ready,
    init_word_trie,
    trie_contains,
    trie_has_prefix,
    get_trie_size,
)


class TestWordTrieUnit:
    """Unit tests for marisa_trie behavior (no DB required)."""

    def test_marisa_trie_basic(self):
        """Test basic marisa_trie operations."""
        words = ["学校", "学生", "学", "東京", "東京都"]
        trie = marisa_trie.Trie(words)

        assert "学校" in trie
        assert "学生" in trie
        assert "学" in trie
        assert "東京" in trie
        assert "東京都" in trie
        assert "学習" not in trie
        assert "大阪" not in trie
        assert len(trie) == 5

    def test_marisa_trie_prefix_search(self):
        """Test prefix iteration."""
        words = ["東京都", "東京駅", "東北", "大阪"]
        trie = marisa_trie.Trie(words)

        tokyo_keys = list(trie.iterkeys("東京"))
        assert "東京都" in tokyo_keys
        assert "東京駅" in tokyo_keys
        assert "東北" not in tokyo_keys
        assert len(tokyo_keys) == 2

    def test_marisa_trie_japanese_characters(self):
        """Test with various Japanese character types."""
        words = [
            "ありがとう",  # hiragana
            "アリガトウ",  # katakana
            "有難う",      # kanji
            "Thank you",  # romaji (edge case)
            "食べる",     # mixed
        ]
        trie = marisa_trie.Trie(words)

        for word in words:
            assert word in trie

    def test_marisa_trie_empty(self):
        """Test empty trie."""
        trie = marisa_trie.Trie([])
        assert len(trie) == 0
        assert "anything" not in trie


class TestWordTrieIntegration:
    """Integration tests requiring database."""

    def test_init_word_trie(self, db_session):
        """Test trie initialization from database."""
        import himotoki.trie as trie_module

        # Reset global state
        trie_module._WORD_TRIE = None
        assert not is_trie_ready()

        # Initialize
        trie = init_word_trie(db_session)
        assert is_trie_ready()
        assert get_word_trie() is trie
        assert get_trie_size() > 0

        # Should return same instance on second call
        trie2 = init_word_trie(db_session)
        assert trie is trie2

    def test_trie_contains_common_words(self, db_session):
        """Test that common words are in the trie."""
        import himotoki.trie as trie_module

        # Ensure initialized
        if not is_trie_ready():
            init_word_trie(db_session)

        # Common words should exist
        assert trie_contains("学校")
        assert trie_contains("日本")
        assert trie_contains("食べる")
        assert trie_contains("する")
        assert trie_contains("いる")

        # Random garbage should not
        assert not trie_contains("xyzabc")
        assert not trie_contains("ぁぁぁぁぁ")

    def test_trie_has_prefix(self, db_session):
        """Test prefix checking."""
        import himotoki.trie as trie_module

        if not is_trie_ready():
            init_word_trie(db_session)

        # Common prefixes should exist
        assert trie_has_prefix("学")
        assert trie_has_prefix("東")
        assert trie_has_prefix("食")

        # Random garbage should not
        assert not trie_has_prefix("ぁぁぁぁ")

    def test_trie_size_reasonable(self, db_session):
        """Test that trie has reasonable number of entries."""
        import himotoki.trie as trie_module

        if not is_trie_ready():
            init_word_trie(db_session)

        size = get_trie_size()
        # Should have millions of entries (9M+ unique surface forms)
        assert size > 1_000_000, f"Trie too small: {size}"
        assert size < 20_000_000, f"Trie too large: {size}"


class TestTrieFallback:
    """Test graceful fallback when trie is not initialized."""

    def test_trie_contains_fallback(self):
        """When trie not initialized, trie_contains returns True (assume exists)."""
        import himotoki.trie as trie_module

        # Force uninitialized state
        old_trie = trie_module._WORD_TRIE
        trie_module._WORD_TRIE = None

        try:
            # Should return True as fallback
            assert trie_contains("anything") is True
            assert trie_has_prefix("anything") is True
            assert get_trie_size() == 0
        finally:
            trie_module._WORD_TRIE = old_trie
