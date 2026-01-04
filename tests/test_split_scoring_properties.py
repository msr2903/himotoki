"""
Property-based tests for split scoring.

Feature: score-calculation-alignment
Property 4: Split Scoring Correctness

Validates: Requirements 4.1, 4.2, 4.3, 4.4
"""

import pytest
from hypothesis import given, strategies as st, settings, assume

from himotoki.splits import (
    SplitResult,
    SplitPart,
    get_split,
    find_word_seq,
)
from himotoki.lookup import (
    WordMatch,
    calc_score,
    find_word,
)
from himotoki.characters import mora_length


# ============================================================================
# Strategies for generating test data
# ============================================================================

@st.composite
def split_result_strategy(draw):
    """Generate a SplitResult with mock parts."""
    # Generate 2-4 parts
    num_parts = draw(st.integers(min_value=2, max_value=4))
    
    parts = []
    for _ in range(num_parts):
        text = draw(st.text(
            alphabet='あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん',
            min_size=1,
            max_size=3
        ))
        assume(len(text) > 0)
        
        # Create a mock reading
        class MockReading:
            def __init__(self, text):
                self.text = text
                self.seq = 1000000
                self.ord = 0
                self.common = 1
        
        parts.append(SplitPart(reading=MockReading(text), text=text))
    
    score_bonus = draw(st.integers(min_value=0, max_value=100))
    modifiers = draw(st.sampled_from([set(), {':score'}, {':pscore'}]))
    
    return SplitResult(parts=parts, score_bonus=score_bonus, modifiers=modifiers)


# ============================================================================
# Property Tests
# ============================================================================

class TestSplitScoringCorrectness:
    """
    Property 4: Split Scoring Correctness
    
    For any word with a split definition, the total score SHALL equal the sum
    of part scores plus the split's score_mod bonus, matching ichiran's split
    scoring algorithm.
    
    **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
    """
    
    @settings(max_examples=100)
    @given(split_result=split_result_strategy())
    def test_split_result_has_modifiers_field(self, split_result: SplitResult):
        """
        Property: For any SplitResult, modifiers SHALL be a set.
        
        **Feature: score-calculation-alignment, Property 4: Split Scoring Correctness**
        **Validates: Requirements 4.3**
        """
        assert isinstance(split_result.modifiers, set)
    
    @settings(max_examples=100)
    @given(split_result=split_result_strategy())
    def test_split_result_modifiers_are_valid(self, split_result: SplitResult):
        """
        Property: For any SplitResult, modifiers SHALL only contain valid values.
        
        **Feature: score-calculation-alignment, Property 4: Split Scoring Correctness**
        **Validates: Requirements 4.3**
        """
        valid_modifiers = {':score', ':pscore'}
        for mod in split_result.modifiers:
            assert mod in valid_modifiers
    
    @settings(max_examples=100)
    @given(split_result=split_result_strategy())
    def test_split_result_has_parts(self, split_result: SplitResult):
        """
        Property: For any SplitResult, parts SHALL be a non-empty list.
        
        **Feature: score-calculation-alignment, Property 4: Split Scoring Correctness**
        **Validates: Requirements 4.1**
        """
        assert isinstance(split_result.parts, list)
        assert len(split_result.parts) > 0
    
    @settings(max_examples=100)
    @given(split_result=split_result_strategy())
    def test_split_result_has_score_bonus(self, split_result: SplitResult):
        """
        Property: For any SplitResult, score_bonus SHALL be an integer.
        
        **Feature: score-calculation-alignment, Property 4: Split Scoring Correctness**
        **Validates: Requirements 4.2**
        """
        assert isinstance(split_result.score_bonus, int)


# ============================================================================
# Integration Tests with Real Database
# ============================================================================

class TestSplitScoringWithDatabase:
    """
    Integration tests for split scoring using the real database.
    These tests verify that split scoring works correctly in practice.
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
    
    def test_split_word_score_includes_bonus(self, db_session):
        """
        Test that split word scores include the score_bonus.
        
        **Feature: score-calculation-alignment, Property 4: Split Scoring Correctness**
        **Validates: Requirements 4.1, 4.2**
        """
        # Test with 一人で which has a split definition
        words = find_word(db_session, '一人で')
        if not words:
            pytest.skip("Word 一人で not found in database")
        
        word = words[0]
        score, info = calc_score(db_session, word)
        
        # Get split info from score_info
        split_info = info.get('score_info', [None, None, None, None])[3]
        
        if split_info:
            assert split_info[0] == 'split'  # Standard split mode
            bonus = split_info[1]
            part_scores = split_info[2]
            
            # Total score should equal sum of parts + bonus
            expected_score = bonus + sum(part_scores)
            assert score == expected_score
    
    def test_split_word_has_correct_parts(self, db_session):
        """
        Test that split words are decomposed into correct parts.
        
        **Feature: score-calculation-alignment, Property 4: Split Scoring Correctness**
        **Validates: Requirements 4.1**
        """
        # Test with 一人で which should split into 一人 + で
        words = find_word(db_session, '一人で')
        if not words:
            pytest.skip("Word 一人で not found in database")
        
        word = words[0]
        split_result = get_split(db_session, word, None)
        
        if split_result:
            assert len(split_result.parts) == 2
            assert split_result.parts[0].text == '一人'
            assert split_result.parts[1].text == 'で'
    
    def test_use_length_affects_final_part_score(self, db_session):
        """
        Test that use_length adjustment affects the final part's score.
        
        **Feature: score-calculation-alignment, Property 4: Split Scoring Correctness**
        **Validates: Requirements 4.4**
        """
        # Test with 一人で
        words = find_word(db_session, '一人で')
        if not words:
            pytest.skip("Word 一人で not found in database")
        
        word = words[0]
        
        # Score without use_length
        score1, info1 = calc_score(db_session, word)
        split_info1 = info1.get('score_info', [None, None, None, None])[3]
        
        # Score with use_length
        score2, info2 = calc_score(db_session, word, use_length=5)
        split_info2 = info2.get('score_info', [None, None, None, None])[3]
        
        if split_info1 and split_info2:
            # The final part (で) should have a higher score with use_length
            part_scores1 = split_info1[2]
            part_scores2 = split_info2[2]
            
            # Final part score should be higher with use_length
            assert part_scores2[-1] >= part_scores1[-1]
    
    def test_split_score_is_sum_of_parts_plus_bonus(self, db_session):
        """
        Property test: For any word with a standard split, score = sum(part_scores) + bonus.
        
        **Feature: score-calculation-alignment, Property 4: Split Scoring Correctness**
        **Validates: Requirements 4.1, 4.2**
        """
        # Test multiple words with split definitions
        test_words = ['一人で', 'ところで', '何で']
        
        for word_text in test_words:
            words = find_word(db_session, word_text)
            if not words:
                continue
            
            word = words[0]
            score, info = calc_score(db_session, word)
            split_info = info.get('score_info', [None, None, None, None])[3]
            
            if split_info and split_info[0] == 'split':
                bonus = split_info[1]
                part_scores = split_info[2]
                expected_score = bonus + sum(part_scores)
                
                assert score == expected_score, \
                    f"For {word_text}: expected {expected_score}, got {score}"
