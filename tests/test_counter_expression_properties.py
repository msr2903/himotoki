"""
Property-based tests for counter expression handling.

Feature: score-calculation-alignment
Property 10: Counter Expression Handling

Validates: Requirements 10.1, 10.2, 10.3
"""

import pytest
from hypothesis import given, strategies as st, settings, assume

from himotoki.counters import (
    CounterText,
    parse_number,
    number_to_kana,
    find_counter,
    counter_join,
    KANJI_NUMBERS,
    DIGIT_TO_KANA,
    DAYS_KUN_READINGS,
    PEOPLE_KUN_READINGS,
)


# ============================================================================
# Strategies for generating test data
# ============================================================================

@st.composite
def number_text_strategy(draw):
    """Generate valid Japanese number text."""
    # Choose between kanji and arabic
    use_kanji = draw(st.booleans())
    
    if use_kanji:
        # Generate kanji number (1-9999)
        value = draw(st.integers(min_value=1, max_value=9999))
        
        # Convert to kanji
        parts = []
        if value >= 1000:
            sen = value // 1000
            if sen > 1:
                parts.append(['一', '二', '三', '四', '五', '六', '七', '八', '九'][sen - 1])
            parts.append('千')
            value %= 1000
        
        if value >= 100:
            hyaku = value // 100
            if hyaku > 1:
                parts.append(['一', '二', '三', '四', '五', '六', '七', '八', '九'][hyaku - 1])
            parts.append('百')
            value %= 100
        
        if value >= 10:
            juu = value // 10
            if juu > 1:
                parts.append(['一', '二', '三', '四', '五', '六', '七', '八', '九'][juu - 1])
            parts.append('十')
            value %= 10
        
        if value > 0:
            parts.append(['一', '二', '三', '四', '五', '六', '七', '八', '九'][value - 1])
        
        return ''.join(parts)
    else:
        # Generate arabic number
        value = draw(st.integers(min_value=1, max_value=9999))
        return str(value)


@st.composite
def counter_text_strategy(draw):
    """Generate a CounterText object with valid properties."""
    number_value = draw(st.integers(min_value=1, max_value=100))
    number_text = str(number_value)
    counter_text = draw(st.sampled_from(['匹', '冊', '本', '人', '円', '時', '日', '月']))
    counter_kana = draw(st.sampled_from(['ひき', 'さつ', 'ほん', 'にん', 'えん', 'じ', 'にち', 'がつ']))
    
    number_kana = number_to_kana(number_value)
    full_kana = number_kana + counter_kana
    full_text = number_text + counter_text
    
    return CounterText(
        text=full_text,
        kana=full_kana,
        number_text=number_text,
        number_value=number_value,
        counter_text=counter_text,
        counter_kana=counter_kana,
        source=None,
        ordinalp=False,
        _common=0,
    )


# ============================================================================
# Property Tests
# ============================================================================

class TestCounterExpressionHandling:
    """
    Property 10: Counter Expression Handling
    
    For any number+counter pattern, a counter segment SHALL be created with
    counter-specific scoring and appropriate readings.
    
    **Validates: Requirements 10.1, 10.2, 10.3**
    """
    
    @settings(max_examples=100)
    @given(counter=counter_text_strategy())
    def test_counter_text_has_required_properties(self, counter: CounterText):
        """
        Property: For any CounterText, required properties SHALL be present.
        
        **Feature: score-calculation-alignment, Property 10: Counter Expression Handling**
        **Validates: Requirements 10.1**
        """
        assert hasattr(counter, 'text')
        assert hasattr(counter, 'kana')
        assert hasattr(counter, 'number_text')
        assert hasattr(counter, 'number_value')
        assert hasattr(counter, 'counter_text')
        assert hasattr(counter, 'counter_kana')
    
    @settings(max_examples=100)
    @given(counter=counter_text_strategy())
    def test_counter_text_is_calc_score_compatible(self, counter: CounterText):
        """
        Property: For any CounterText, it SHALL have properties needed for calc_score.
        
        **Feature: score-calculation-alignment, Property 10: Counter Expression Handling**
        **Validates: Requirements 10.2**
        """
        # CounterText must have these properties for calc_score compatibility
        assert hasattr(counter, 'reading')
        assert hasattr(counter, 'conjugations')
        assert hasattr(counter, 'is_root')
        assert hasattr(counter, 'is_compound')
        assert hasattr(counter, 'components')
        assert hasattr(counter, 'common')
        assert hasattr(counter, 'ord')
        assert hasattr(counter, 'word_type')
        
        # Verify expected values
        assert counter.reading is counter  # reading returns self
        assert counter.conjugations is None  # counters don't conjugate
        assert counter.is_root is True  # counters are root forms
        assert counter.is_compound is False  # counters are not compounds
        assert counter.components == []  # no components
    
    @settings(max_examples=100)
    @given(counter=counter_text_strategy())
    def test_counter_text_full_text_is_number_plus_counter(self, counter: CounterText):
        """
        Property: For any CounterText, text SHALL equal number_text + counter_text.
        
        **Feature: score-calculation-alignment, Property 10: Counter Expression Handling**
        **Validates: Requirements 10.1**
        """
        assert counter.text == counter.number_text + counter.counter_text
    
    @settings(max_examples=100)
    @given(number_text=number_text_strategy())
    def test_parse_number_returns_valid_integer(self, number_text: str):
        """
        Property: For any valid number text, parse_number SHALL return an integer.
        
        **Feature: score-calculation-alignment, Property 10: Counter Expression Handling**
        **Validates: Requirements 10.1**
        """
        result = parse_number(number_text)
        assert result is not None
        assert isinstance(result, int)
        assert result > 0
    
    @settings(max_examples=100)
    @given(value=st.integers(min_value=1, max_value=9999))
    def test_number_to_kana_returns_string(self, value: int):
        """
        Property: For any positive integer, number_to_kana SHALL return a kana string.
        
        **Feature: score-calculation-alignment, Property 10: Counter Expression Handling**
        **Validates: Requirements 10.3**
        """
        result = number_to_kana(value)
        assert isinstance(result, str)
        assert len(result) > 0


# ============================================================================
# Integration Tests with Real Database
# ============================================================================

class TestCounterExpressionWithDatabase:
    """
    Integration tests for counter expression handling using the real database.
    These tests verify that counter handling works correctly in practice.
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
    
    def test_find_counter_creates_counter_segment(self, db_session):
        """
        Test that find_counter creates proper counter segments.
        
        **Feature: score-calculation-alignment, Property 10: Counter Expression Handling**
        **Validates: Requirements 10.1**
        """
        # Test basic counter: 三匹 (3 small animals)
        counters = find_counter(db_session, '三', '匹')
        
        assert len(counters) > 0
        counter = counters[0]
        
        assert isinstance(counter, CounterText)
        assert counter.text == '三匹'
        assert counter.number_text == '三'
        assert counter.number_value == 3
        assert counter.counter_text == '匹'
    
    def test_counter_scoring_uses_calc_score(self, db_session):
        """
        Test that counter segments can be scored using calc_score.
        
        **Feature: score-calculation-alignment, Property 10: Counter Expression Handling**
        **Validates: Requirements 10.2**
        """
        from himotoki.lookup import calc_score
        
        counters = find_counter(db_session, '三', '匹')
        assert len(counters) > 0
        counter = counters[0]
        
        # calc_score should work with CounterText
        score, info = calc_score(db_session, counter)
        
        assert isinstance(score, int)
        assert score > 0
        # Counter mode should be detected - posi contains 'ctr'
        assert 'ctr' in info.get('posi', [])
    
    def test_special_counter_readings_days(self, db_session):
        """
        Test that special counter readings are used for days.
        
        **Feature: score-calculation-alignment, Property 10: Counter Expression Handling**
        **Validates: Requirements 10.3**
        """
        # Test 二日 (futsuka) - special kun reading
        counters = find_counter(db_session, '二', '日')
        
        # Should find the counter with kun reading
        kun_counter = None
        for c in counters:
            if c.kana == 'ふつか':
                kun_counter = c
                break
        
        assert kun_counter is not None, "Should find 二日 with ふつか reading"
        assert kun_counter.number_value == 2
    
    def test_special_counter_readings_people(self, db_session):
        """
        Test that special counter readings are used for people.
        
        **Feature: score-calculation-alignment, Property 10: Counter Expression Handling**
        **Validates: Requirements 10.3**
        """
        # Test 二人 (futari) - special kun reading
        counters = find_counter(db_session, '二', '人')
        
        # Should find the counter with kun reading
        kun_counter = None
        for c in counters:
            if c.kana == 'ふたり':
                kun_counter = c
                break
        
        assert kun_counter is not None, "Should find 二人 with ふたり reading"
        assert kun_counter.number_value == 2
    
    def test_counter_phonetic_rules_rendaku(self, db_session):
        """
        Test that rendaku is applied correctly for counters.
        
        **Feature: score-calculation-alignment, Property 10: Counter Expression Handling**
        **Validates: Requirements 10.3**
        """
        # Test 三匹 (sanbiki) - rendaku: ひき -> びき
        counters = find_counter(db_session, '三', '匹')
        
        assert len(counters) > 0
        counter = counters[0]
        
        # Should have rendaku applied
        assert 'びき' in counter.kana, f"Expected rendaku in {counter.kana}"
    
    def test_counter_phonetic_rules_gemination(self, db_session):
        """
        Test that gemination (sokuon) is applied correctly for counters.
        
        **Feature: score-calculation-alignment, Property 10: Counter Expression Handling**
        **Validates: Requirements 10.3**
        """
        # Test 一冊 (issatsu) - gemination: いち -> いっ
        counters = find_counter(db_session, '一', '冊')
        
        assert len(counters) > 0
        counter = counters[0]
        
        # Should have gemination applied
        assert 'いっ' in counter.kana, f"Expected gemination in {counter.kana}"
    
    def test_counter_scores_match_ichiran(self, db_session):
        """
        Test that counter scores are calculated correctly.
        
        **Feature: score-calculation-alignment, Property 10: Counter Expression Handling**
        **Validates: Requirements 10.1, 10.2, 10.3**
        """
        from himotoki.lookup import calc_score
        
        # Test cases with actual counter expressions
        # Note: Some expressions like 一つ, 三時, 百円 are not counters in the database
        # and 二人, 二日 have dictionary entries that score higher than counter-generated versions
        test_cases = [
            ('三', '匹', 286),   # 3 small animals - rendaku applied
            ('五', '冊', 208),   # 5 books
            ('千', '人', 208),   # 1000 people
            ('四', '本', 208),   # 4 long objects
            ('一', '月', 208),   # January
        ]
        
        for number_text, counter_text, expected_score in test_cases:
            counters = find_counter(db_session, number_text, counter_text)
            assert len(counters) > 0, f"No counter found for {number_text}{counter_text}"
            
            counter = counters[0]
            score, _ = calc_score(db_session, counter)
            
            assert score == expected_score, \
                f"For {number_text}{counter_text}: expected {expected_score}, got {score}"
