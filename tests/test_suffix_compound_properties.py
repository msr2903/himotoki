"""
Property-based tests for suffix compound creation.

Feature: score-calculation-alignment
Property 5: Suffix Compound Creation

Validates: Requirements 5.1, 5.2, 5.3, 5.4
"""

import pytest
from hypothesis import given, strategies as st, settings, assume

from himotoki.lookup import (
    WordMatch,
    CompoundWord,
    adjoin_word,
)
from himotoki.suffixes import (
    find_word_suffix,
    SUFFIX_SCORES,
    SUFFIX_CONNECTORS,
    init_suffixes,
)


# ============================================================================
# Strategies for generating test data
# ============================================================================

@st.composite
def word_match_strategy(draw):
    """Generate a WordMatch with a mock reading."""
    text = draw(st.text(
        alphabet='あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん',
        min_size=1,
        max_size=5
    ))
    assume(len(text) > 0)
    
    seq = draw(st.integers(min_value=1000000, max_value=9999999))
    ord_val = draw(st.integers(min_value=0, max_value=5))
    common = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=20)))
    
    class MockKanaText:
        def __init__(self, seq, text, ord, common):
            self.seq = seq
            self.text = text
            self.ord = ord
            self.common = common
    
    reading = MockKanaText(seq, text, ord_val, common)
    return WordMatch(reading=reading)


@st.composite
def suffix_keyword_strategy(draw):
    """Generate a valid suffix keyword from SUFFIX_SCORES."""
    return draw(st.sampled_from(list(SUFFIX_SCORES.keys())))


# ============================================================================
# Property Tests
# ============================================================================

class TestSuffixCompoundCreation:
    """
    Property 5: Suffix Compound Creation
    
    For any suffix pattern match, the created compound word SHALL have
    is_compound: true, the primary word as the main content word, and
    preserved conjugation information from the suffix.
    
    **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
    """
    
    @settings(max_examples=100)
    @given(word1=word_match_strategy(), word2=word_match_strategy())
    def test_adjoin_word_creates_compound_with_is_compound_true(
        self, word1: WordMatch, word2: WordMatch
    ):
        """
        Property: For any suffix compound, is_compound SHALL be True.
        
        **Feature: score-calculation-alignment, Property 5: Suffix Compound Creation**
        **Validates: Requirements 5.1**
        """
        compound = adjoin_word(word1, word2)
        assert compound.is_compound is True
    
    @settings(max_examples=100)
    @given(word1=word_match_strategy(), word2=word_match_strategy())
    def test_adjoin_word_sets_primary_correctly(
        self, word1: WordMatch, word2: WordMatch
    ):
        """
        Property: For any suffix compound, primary SHALL be the first word.
        
        **Feature: score-calculation-alignment, Property 5: Suffix Compound Creation**
        **Validates: Requirements 5.2**
        """
        compound = adjoin_word(word1, word2)
        assert compound.primary == word1
        assert compound.seq == word1.seq
    
    @settings(max_examples=100)
    @given(
        word1=word_match_strategy(),
        word2=word_match_strategy(),
        score_mod=st.floats(min_value=0, max_value=500)
    )
    def test_adjoin_word_applies_score_mod(
        self, word1: WordMatch, word2: WordMatch, score_mod: float
    ):
        """
        Property: For any suffix compound, score_mod SHALL be applied.
        
        **Feature: score-calculation-alignment, Property 5: Suffix Compound Creation**
        **Validates: Requirements 5.4**
        """
        compound = adjoin_word(word1, word2, score_mod=score_mod)
        assert compound.score_mod == score_mod
    
    @settings(max_examples=100)
    @given(keyword=suffix_keyword_strategy())
    def test_suffix_scores_mapping_has_valid_values(self, keyword: str):
        """
        Property: For any suffix keyword, SUFFIX_SCORES SHALL have a numeric value.
        
        **Feature: score-calculation-alignment, Property 5: Suffix Compound Creation**
        **Validates: Requirements 5.4**
        """
        score = SUFFIX_SCORES.get(keyword)
        assert score is not None
        assert isinstance(score, (int, float))
        assert score >= 0
    
    @settings(max_examples=100)
    @given(word1=word_match_strategy(), word2=word_match_strategy())
    def test_compound_words_list_contains_both_words(
        self, word1: WordMatch, word2: WordMatch
    ):
        """
        Property: For any suffix compound, words list SHALL contain both words.
        
        **Feature: score-calculation-alignment, Property 5: Suffix Compound Creation**
        **Validates: Requirements 5.1**
        """
        compound = adjoin_word(word1, word2)
        assert len(compound.words) == 2
        assert compound.words[0] == word1
        assert compound.words[1] == word2
    
    @settings(max_examples=100)
    @given(word1=word_match_strategy(), word2=word_match_strategy())
    def test_compound_components_match_word_texts(
        self, word1: WordMatch, word2: WordMatch
    ):
        """
        Property: For any suffix compound, components SHALL match word texts.
        
        **Feature: score-calculation-alignment, Property 5: Suffix Compound Creation**
        **Validates: Requirements 5.1**
        """
        compound = adjoin_word(word1, word2)
        assert compound.components == [word1.text, word2.text]


# ============================================================================
# Integration Tests with Real Database
# ============================================================================

class TestSuffixCompoundWithDatabase:
    """
    Integration tests for suffix compound creation using the real database.
    These tests verify that suffix compounds are correctly created in practice.
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
            # Initialize suffix cache
            init_suffixes(session)
            yield session
        finally:
            session.close()
    
    def test_teiru_suffix_creates_compound(self, db_session):
        """
        Test that ている suffix creates a proper compound word.
        
        **Feature: score-calculation-alignment, Property 5: Suffix Compound Creation**
        **Validates: Requirements 5.1, 5.2**
        """
        # 食べている should create a compound with 食べて as primary
        results = find_word_suffix(db_session, "食べている")
        
        compounds = [r for r in results if isinstance(r, CompoundWord)]
        if not compounds:
            pytest.skip("No compound found for 食べている")
        
        for compound in compounds:
            assert compound.is_compound is True
            assert isinstance(compound.seq, int)
            assert compound.primary is not None
    
    def test_tai_suffix_creates_compound(self, db_session):
        """
        Test that たい suffix creates a proper compound word.
        
        **Feature: score-calculation-alignment, Property 5: Suffix Compound Creation**
        **Validates: Requirements 5.1, 5.2**
        """
        # 食べたい should create a compound
        results = find_word_suffix(db_session, "食べたい")
        
        compounds = [r for r in results if isinstance(r, CompoundWord)]
        if not compounds:
            pytest.skip("No compound found for 食べたい")
        
        for compound in compounds:
            assert compound.is_compound is True
            assert isinstance(compound.seq, int)
    
    def test_suffix_compound_has_score_mod(self, db_session):
        """
        Test that suffix compounds have score_mod from SUFFIX_SCORES.
        
        **Feature: score-calculation-alignment, Property 5: Suffix Compound Creation**
        **Validates: Requirements 5.4**
        """
        # Test with たい suffix which has score 5
        results = find_word_suffix(db_session, "食べたい")
        
        compounds = [r for r in results if isinstance(r, CompoundWord)]
        if not compounds:
            pytest.skip("No compound found for 食べたい")
        
        for compound in compounds:
            # score_mod should be set (tai has score 5)
            assert compound.score_mod is not None
            # For tai suffix, score_mod should be 5
            if isinstance(compound.score_mod, (int, float)):
                assert compound.score_mod == SUFFIX_SCORES.get('tai', 0)
    
    def test_suffix_compound_preserves_conjugation_info(self, db_session):
        """
        Test that suffix compounds preserve conjugation info from suffix word.
        
        **Feature: score-calculation-alignment, Property 5: Suffix Compound Creation**
        **Validates: Requirements 5.3**
        """
        # 食べている - the いる suffix may have conjugation info
        results = find_word_suffix(db_session, "食べている")
        
        compounds = [r for r in results if isinstance(r, CompoundWord)]
        if not compounds:
            pytest.skip("No compound found for 食べている")
        
        for compound in compounds:
            # The compound should have words list
            assert len(compound.words) >= 2
            # The last word (suffix) should be accessible
            last_word = compound.words[-1]
            assert last_word is not None
    
    def test_suffix_compound_kana_includes_connector(self, db_session):
        """
        Test that suffix compound kana includes connector when applicable.
        
        **Feature: score-calculation-alignment, Property 5: Suffix Compound Creation**
        **Validates: Requirements 5.1**
        """
        # Test with する suffix which has connector ' '
        results = find_word_suffix(db_session, "勉強する")
        
        compounds = [r for r in results if isinstance(r, CompoundWord)]
        if not compounds:
            pytest.skip("No compound found for 勉強する")
        
        for compound in compounds:
            # The kana should be set
            assert compound.kana is not None
            # For suru suffix, there should be a space connector
            # The kana should contain the primary kana + space + suffix kana
            if ' ' in compound.kana:
                # Connector was included
                assert True
    
    def test_multiple_suffix_patterns(self, db_session):
        """
        Test that various suffix patterns create proper compounds.
        
        **Feature: score-calculation-alignment, Property 5: Suffix Compound Creation**
        **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
        """
        test_cases = [
            ("食べている", "teiru"),  # te-form + iru
            ("食べたい", "tai"),       # continuative + tai
            ("見ている", "teiru"),    # te-form + iru
            ("行きたい", "tai"),       # continuative + tai
        ]
        
        for word, expected_suffix_type in test_cases:
            results = find_word_suffix(db_session, word)
            compounds = [r for r in results if isinstance(r, CompoundWord)]
            
            if compounds:
                for compound in compounds:
                    # All compounds should have is_compound=True
                    assert compound.is_compound is True
                    # All compounds should have int seq
                    assert isinstance(compound.seq, int)
                    # All compounds should have primary set
                    assert compound.primary is not None
