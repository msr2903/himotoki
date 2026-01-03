"""
Tests for himotoki.characters module.
Tests character classification, kana conversion, and text utilities.
"""

import pytest
from himotoki.characters import (
    # Character classification
    get_char_class, word_matches_class, count_char_class,
    is_katakana, is_hiragana, is_kanji, is_kana,
    has_kanji, has_kana,
    # Kana conversion
    as_hiragana, as_katakana,
    # Voicing
    rendaku, unrendaku, geminate,
    # Normalization
    normalize_char, normalize,
    # Text splitting
    basic_split, mora_length,
    # Kanji utilities
    sequential_kanji_positions, kanji_prefix, kanji_mask, kanji_match,
    # Utilities
    safe_subseq, join
)


class TestCharacterClassification:
    """Test character class determination."""
    
    def test_get_char_class_hiragana(self):
        """Test character class for hiragana."""
        assert get_char_class('あ') == 'a'
        assert get_char_class('か') == 'ka'
        assert get_char_class('し') == 'shi'
        assert get_char_class('ん') == 'n'
    
    def test_get_char_class_katakana(self):
        """Test character class for katakana."""
        assert get_char_class('ア') == 'a'
        assert get_char_class('カ') == 'ka'
        assert get_char_class('シ') == 'shi'
        assert get_char_class('ン') == 'n'
    
    def test_get_char_class_voiced(self):
        """Test character class for voiced kana."""
        assert get_char_class('が') == 'ga'
        assert get_char_class('ガ') == 'ga'
        assert get_char_class('ぱ') == 'pa'
        assert get_char_class('パ') == 'pa'
    
    def test_get_char_class_unknown(self):
        """Test character class for non-kana."""
        assert get_char_class('A') is None
        assert get_char_class('0') is None
        assert get_char_class('漢') is None
    
    def test_is_hiragana(self):
        """Test hiragana detection."""
        assert is_hiragana("たべる") == True
        assert is_hiragana("ひらがな") == True
        assert is_hiragana("カタカナ") == False
        assert is_hiragana("食べる") == False
        assert is_hiragana("") == False
    
    def test_is_katakana(self):
        """Test katakana detection."""
        assert is_katakana("カタカナ") == True
        assert is_katakana("アイウエオ") == True
        assert is_katakana("ひらがな") == False
        assert is_katakana("漢字") == False
    
    def test_is_kanji(self):
        """Test kanji detection."""
        assert is_kanji("漢字") == True
        assert is_kanji("日本語") == True
        assert is_kanji("たべる") == False
        assert is_kanji("カタカナ") == False
    
    def test_is_kana(self):
        """Test kana (hiragana or katakana) detection."""
        assert is_kana("ひらがな") == True
        assert is_kana("カタカナ") == True
        assert is_kana("ひらカタ") == True
        assert is_kana("漢字") == False
        assert is_kana("abc") == False
    
    def test_has_kanji(self):
        """Test checking if string contains kanji."""
        assert has_kanji("食べる") == True
        assert has_kanji("日本") == True
        assert has_kanji("たべる") == False
        assert has_kanji("") == False
    
    def test_has_kana(self):
        """Test checking if string contains kana."""
        assert has_kana("食べる") == True
        assert has_kana("ひらがな") == True
        assert has_kana("日本") == False  # No kana, only kanji
        assert has_kana("ABC") == False
    
    def test_word_matches_class(self):
        """Test the word_matches_class function."""
        assert word_matches_class("あいうえお", "hiragana") == True
        assert word_matches_class("アイウエオ", "katakana") == True
        assert word_matches_class("日本語", "kanji") == True
        assert word_matches_class("あア日", "kana") == False
    
    def test_count_char_class(self):
        """Test counting character classes."""
        assert count_char_class("食べる", "kanji") == 1
        assert count_char_class("日本語", "kanji") == 3
        assert count_char_class("たべる", "hiragana") == 3


class TestKanaConversion:
    """Test kana conversion functions."""
    
    def test_as_hiragana_basic(self):
        """Test basic katakana to hiragana conversion."""
        assert as_hiragana("カタカナ") == "かたかな"
        assert as_hiragana("アイウエオ") == "あいうえお"
        assert as_hiragana("ガギグゲゴ") == "がぎぐげご"
    
    def test_as_hiragana_mixed(self):
        """Test conversion with mixed input."""
        assert as_hiragana("ひらがな") == "ひらがな"  # Already hiragana
        assert as_hiragana("日本") == "日本"  # Kanji unchanged
    
    def test_as_hiragana_special(self):
        """Test conversion with special characters."""
        assert as_hiragana("ッ") == "っ"  # Small tsu
        assert as_hiragana("ー") == "ー"  # Long vowel mark
    
    def test_as_katakana_basic(self):
        """Test basic hiragana to katakana conversion."""
        assert as_katakana("ひらがな") == "ヒラガナ"
        assert as_katakana("あいうえお") == "アイウエオ"
        assert as_katakana("がぎぐげご") == "ガギグゲゴ"
    
    def test_as_katakana_mixed(self):
        """Test conversion with mixed input."""
        assert as_katakana("カタカナ") == "カタカナ"  # Already katakana
        assert as_katakana("日本") == "日本"  # Kanji unchanged
    
    def test_as_katakana_special(self):
        """Test conversion with special characters."""
        assert as_katakana("っ") == "ッ"  # Small tsu
        assert as_katakana("ー") == "ー"  # Long vowel mark


class TestVoicing:
    """Test voicing (rendaku/unrendaku) functions."""
    
    def test_rendaku_basic(self):
        """Test basic rendaku (voicing)."""
        assert rendaku("かわ") == "がわ"
        assert rendaku("さくら") == "ざくら"
        assert rendaku("たま") == "だま"
    
    def test_rendaku_katakana(self):
        """Test rendaku with katakana."""
        assert rendaku("カワ") == "ガワ"
        assert rendaku("サクラ") == "ザクラ"
    
    def test_rendaku_handakuten(self):
        """Test handakuten (semi-voicing) for ha-row."""
        assert rendaku("はな", handakuten=True) == "ぱな"
        assert rendaku("ひと", handakuten=True) == "ぴと"
        assert rendaku("ハナ", handakuten=True) == "パナ"
    
    def test_rendaku_already_voiced(self):
        """Test rendaku on already voiced chars (no change)."""
        assert rendaku("がわ") == "がわ"  # Already voiced
    
    def test_rendaku_empty(self):
        """Test rendaku with empty string."""
        assert rendaku("") == ""
    
    def test_unrendaku_basic(self):
        """Test basic unrendaku (unvoicing)."""
        assert unrendaku("がわ") == "かわ"
        assert unrendaku("ざくら") == "さくら"
        assert unrendaku("だま") == "たま"
    
    def test_unrendaku_katakana(self):
        """Test unrendaku with katakana."""
        assert unrendaku("ガワ") == "カワ"
        assert unrendaku("ザクラ") == "サクラ"
    
    def test_unrendaku_already_unvoiced(self):
        """Test unrendaku on unvoiced chars (no change)."""
        assert unrendaku("かわ") == "かわ"
    
    def test_geminate(self):
        """Test gemination (adding small tsu)."""
        assert geminate("はしる") == "はしっ"
        assert geminate("かく") == "かっ"
        assert geminate("") == ""


class TestNormalization:
    """Test text normalization functions."""
    
    def test_normalize_char_fullwidth(self):
        """Test normalizing full-width alphanumeric."""
        assert normalize_char('０') == '0'
        assert normalize_char('９') == '9'
        assert normalize_char('ａ') == 'a'
        assert normalize_char('Ｚ') == 'Z'
    
    def test_normalize_char_halfwidth_kana(self):
        """Test normalizing half-width katakana."""
        assert normalize_char('ｱ', context='kana') == 'ア'
        assert normalize_char('ｶ', context='kana') == 'カ'
    
    def test_normalize_basic(self):
        """Test basic text normalization."""
        assert normalize("１２３") == "123"
        assert normalize("ＡＢＣ") == "ABC"
    
    def test_normalize_punctuation(self):
        """Test punctuation normalization."""
        assert normalize("。") == ". "
        assert normalize("、") == ", "


class TestTextSplitting:
    """Test text splitting functions."""
    
    def test_basic_split_simple(self):
        """Test basic splitting of Japanese text."""
        result = basic_split("日本語です")
        assert len(result) >= 1
        # Should identify at least one word segment
        word_segments = [seg for typ, seg in result if typ == 'word']
        assert len(word_segments) > 0
    
    def test_basic_split_mixed(self):
        """Test splitting mixed Japanese and non-Japanese."""
        result = basic_split("Hello日本語World")
        # Should have misc, word, misc segments
        types = [typ for typ, _ in result]
        assert 'misc' in types or 'word' in types
    
    def test_basic_split_empty(self):
        """Test splitting empty string."""
        result = basic_split("")
        assert result == []
    
    def test_mora_length(self):
        """Test mora length calculation."""
        # Regular characters count normally
        assert mora_length("たべる") == 3
        # Small characters and long vowel don't count
        assert mora_length("っ") == 0
        assert mora_length("きょう") == 2  # き + ょ + う, but ょ doesn't count, う does
        assert mora_length("ー") == 0


class TestKanjiUtilities:
    """Test kanji utility functions."""
    
    def test_sequential_kanji_positions(self):
        """Test finding adjacent kanji positions."""
        # 日本語 has kanji at 0,1,2, so adjacent at positions 1 and 2
        positions = sequential_kanji_positions("日本語")
        assert 1 in positions
        assert 2 in positions
    
    def test_sequential_kanji_positions_no_adjacent(self):
        """Test with no adjacent kanji."""
        positions = sequential_kanji_positions("日a本")
        # No adjacent kanji pairs
        assert len(positions) == 0
    
    def test_kanji_prefix(self):
        """Test extracting kanji prefix."""
        assert kanji_prefix("食べる") == "食"
        assert kanji_prefix("日本語") == "日本語"
        assert kanji_prefix("たべる") == ""
    
    def test_kanji_mask(self):
        """Test creating SQL LIKE mask."""
        assert kanji_mask("食べる") == "%べる"
        assert kanji_mask("日本語") == "%"
        assert kanji_mask("たべる") == "たべる"
    
    def test_kanji_match(self):
        """Test kanji pattern matching."""
        assert kanji_match("食べる", "たべる") == True
        assert kanji_match("食べる", "のむ") == False


class TestUtilities:
    """Test utility functions."""
    
    def test_safe_subseq(self):
        """Test safe substring extraction."""
        assert safe_subseq("hello", 0, 3) == "hel"
        assert safe_subseq("hello", 0) == "hello"
        assert safe_subseq("hello", 10) is None
        assert safe_subseq("hello", 0, 10) is None
    
    def test_join(self):
        """Test join function."""
        assert join(", ", ["a", "b", "c"]) == "a, b, c"
        assert join("-", [1, 2, 3]) == "1-2-3"
        assert join(", ", ["a"]) == "a"
        assert join(", ", []) == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])