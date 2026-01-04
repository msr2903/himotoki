"""
Property-based tests for compound word detection.

Feature: score-calculation-alignment
Property 1: Compound Word Detection Consistency

Validates: Requirements 1.1, 1.2, 1.3, 1.4
"""

import pytest
from hypothesis import given, strategies as st, settings, assume

from himotoki.lookup import (
    WordMatch,
    CompoundWord,
    adjoin_word,
)
from himotoki.db.models import KanaText, KanjiText


# ============================================================================
# Strategies for generating test data
# ============================================================================

@st.composite
def word_match_strategy(draw):
    """Generate a WordMatch with a mock reading."""
    # Generate a simple kana text for the reading
    text = draw(st.text(
        alphabet='あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん',
        min_size=1,
        max_size=5
    ))
    assume(len(text) > 0)
    
    seq = draw(st.integers(min_value=1000000, max_value=9999999))
    ord_val = draw(st.integers(min_value=0, max_value=5))
    common = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=20)))
    
    # Create a mock KanaText-like object
    class MockKanaText:
        def __init__(self, seq, text, ord, common):
            self.seq = seq
            self.text = text
            self.ord = ord
            self.common = common
    
    reading = MockKanaText(seq, text, ord_val, common)
    return WordMatch(reading=reading)


@st.composite
def compound_word_strategy(draw):
    """Generate a CompoundWord from multiple WordMatches."""
    # Generate 2-4 component words
    num_words = draw(st.integers(min_value=2, max_value=4))
    words = [draw(word_match_strategy()) for _ in range(num_words)]
    
    # Build compound text and kana
    compound_text = ''.join(w.text for w in words)
    compound_kana = ''.join(w.text for w in words)  # For kana words, text == kana
    
    # Primary is the first word
    primary = words[0]
    
    # Score modifier
    score_mod = draw(st.one_of(
        st.floats(min_value=0, max_value=100),
        st.lists(st.floats(min_value=0, max_value=50), min_size=1, max_size=3)
    ))
    
    return CompoundWord(
        text=compound_text,
        kana=compound_kana,
        primary=primary,
        words=words,
        score_mod=score_mod,
    )


# ============================================================================
# Property Tests
# ============================================================================

class TestCompoundWordDetectionConsistency:
    """
    Property 1: Compound Word Detection Consistency
    
    For any text containing a verb + auxiliary pattern, if ichiran identifies
    it as a compound word, himotoki SHALL also identify it as a compound word
    with matching is_compound, seq, and components fields.
    
    **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
    """
    
    @settings(max_examples=100)
    @given(compound=compound_word_strategy())
    def test_compound_is_compound_property(self, compound: CompoundWord):
        """
        Property: For any CompoundWord, is_compound SHALL always be True.
        
        **Feature: score-calculation-alignment, Property 1: Compound Word Detection Consistency**
        **Validates: Requirements 1.1, 1.2**
        """
        assert compound.is_compound is True
    
    @settings(max_examples=100)
    @given(word=word_match_strategy())
    def test_simple_word_is_not_compound(self, word: WordMatch):
        """
        Property: For any simple WordMatch, is_compound SHALL always be False.
        
        **Feature: score-calculation-alignment, Property 1: Compound Word Detection Consistency**
        **Validates: Requirements 1.1, 1.2**
        """
        assert word.is_compound is False
    
    @settings(max_examples=100)
    @given(compound=compound_word_strategy())
    def test_compound_seq_is_primary_seq(self, compound: CompoundWord):
        """
        Property: For any CompoundWord, seq SHALL equal the primary word's seq.
        
        **Feature: score-calculation-alignment, Property 1: Compound Word Detection Consistency**
        **Validates: Requirements 1.3**
        """
        assert compound.seq == compound.primary.seq
        assert isinstance(compound.seq, int)
    
    @settings(max_examples=100)
    @given(compound=compound_word_strategy())
    def test_compound_components_match_words(self, compound: CompoundWord):
        """
        Property: For any CompoundWord, components SHALL contain the text of each word.
        
        **Feature: score-calculation-alignment, Property 1: Compound Word Detection Consistency**
        **Validates: Requirements 1.2**
        """
        expected_components = [w.text for w in compound.words]
        assert compound.components == expected_components
    
    @settings(max_examples=100)
    @given(word=word_match_strategy())
    def test_simple_word_has_empty_components(self, word: WordMatch):
        """
        Property: For any simple WordMatch, components SHALL be an empty list.
        
        **Feature: score-calculation-alignment, Property 1: Compound Word Detection Consistency**
        **Validates: Requirements 1.2**
        """
        assert word.components == []
    
    @settings(max_examples=100)
    @given(word1=word_match_strategy(), word2=word_match_strategy())
    def test_adjoin_word_creates_compound(self, word1: WordMatch, word2: WordMatch):
        """
        Property: For any two WordMatches, adjoin_word SHALL create a CompoundWord.
        
        **Feature: score-calculation-alignment, Property 1: Compound Word Detection Consistency**
        **Validates: Requirements 1.1, 1.2**
        """
        compound = adjoin_word(word1, word2)
        
        assert isinstance(compound, CompoundWord)
        assert compound.is_compound is True
        assert compound.primary == word1
        assert len(compound.words) == 2
        assert compound.words[0] == word1
        assert compound.words[1] == word2
    
    @settings(max_examples=100)
    @given(word1=word_match_strategy(), word2=word_match_strategy(), word3=word_match_strategy())
    def test_adjoin_word_extends_compound(self, word1: WordMatch, word2: WordMatch, word3: WordMatch):
        """
        Property: For any CompoundWord and WordMatch, adjoin_word SHALL extend the compound.
        
        **Feature: score-calculation-alignment, Property 1: Compound Word Detection Consistency**
        **Validates: Requirements 1.1, 1.2**
        """
        # First create a compound
        compound = adjoin_word(word1, word2)
        
        # Then extend it
        extended = adjoin_word(compound, word3)
        
        assert isinstance(extended, CompoundWord)
        assert extended.is_compound is True
        assert extended.primary == word1  # Primary should remain the same
        assert len(extended.words) == 3
    
    @settings(max_examples=100)
    @given(compound=compound_word_strategy())
    def test_compound_text_is_concatenation(self, compound: CompoundWord):
        """
        Property: For any CompoundWord, text SHALL be the concatenation of component texts.
        
        **Feature: score-calculation-alignment, Property 1: Compound Word Detection Consistency**
        **Validates: Requirements 1.1**
        """
        expected_text = ''.join(w.text for w in compound.words)
        assert compound.text == expected_text
    
    @settings(max_examples=100)
    @given(compound=compound_word_strategy())
    def test_compound_inherits_primary_properties(self, compound: CompoundWord):
        """
        Property: For any CompoundWord, common and ord SHALL come from primary word.
        
        **Feature: score-calculation-alignment, Property 1: Compound Word Detection Consistency**
        **Validates: Requirements 1.4**
        """
        assert compound.common == compound.primary.common
        assert compound.ord == compound.primary.ord
        assert compound.word_type == compound.primary.word_type


# ============================================================================
# Integration Tests with Real Database
# ============================================================================

class TestCompoundWordWithDatabase:
    """
    Integration tests for compound word detection using the real database.
    These tests verify that compound words are correctly identified in practice.
    """
    
    @pytest.fixture
    def db_session(self):
        """Get database session for tests."""
        from tests.conftest import _create_session
        from pathlib import Path
        
        DB_PATH = Path(__file__).parent.parent / "data" / "himotoki.db"
        if not DB_PATH.exists():
            pytest.skip(f"Database not found at {DB_PATH}")
        
        session = _create_session()
        try:
            yield session
        finally:
            session.close()
    
    def test_compound_word_from_suffix_is_compound(self, db_session):
        """
        Test that compound words created from suffix matching have is_compound=True.
        
        **Feature: score-calculation-alignment, Property 1: Compound Word Detection Consistency**
        **Validates: Requirements 1.1, 1.2**
        """
        from himotoki.suffixes import find_word_suffix
        
        # Try to find suffix compounds for a te-form word
        # 食べている should create a compound
        results = find_word_suffix(db_session, "食べている")
        
        # If we get results, they should all be compounds
        for result in results:
            if isinstance(result, CompoundWord):
                assert result.is_compound is True
                assert isinstance(result.seq, int)
                assert len(result.components) > 0
    
    def test_compound_word_seq_is_int_not_list(self, db_session):
        """
        Test that compound word seq is an int, not a list.
        
        **Feature: score-calculation-alignment, Property 1: Compound Word Detection Consistency**
        **Validates: Requirements 1.3**
        """
        from himotoki.suffixes import find_word_suffix
        
        # Try various te-form patterns
        test_words = ["食べている", "見ている", "行っている"]
        
        for word in test_words:
            results = find_word_suffix(db_session, word)
            for result in results:
                if isinstance(result, CompoundWord):
                    # seq should be an int, not a list
                    assert isinstance(result.seq, int), f"seq should be int, got {type(result.seq)}"
                    # seq should equal primary's seq
                    assert result.seq == result.primary.seq
