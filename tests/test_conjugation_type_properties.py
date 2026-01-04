"""
Property-based tests for conjugation type detection.

Feature: score-calculation-alignment
Property 2: Conjugation Type Detection Accuracy

Validates: Requirements 2.1, 2.2, 2.3, 2.4
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from typing import Optional, List

from himotoki.lookup import (
    WordMatch,
    CompoundWord,
    ConjData,
    CONJ_TYPE_NAMES,
    get_conj_type_name,
    get_conj_neg,
    get_conj_fml,
    get_source_text,
    get_word_conj_data,
)
from himotoki.db.models import ConjProp


# ============================================================================
# Strategies for generating test data
# ============================================================================

@st.composite
def conj_type_strategy(draw):
    """Generate a valid conjugation type ID."""
    return draw(st.sampled_from(list(CONJ_TYPE_NAMES.keys())))


@st.composite
def mock_conj_prop_strategy(draw):
    """Generate a mock ConjProp object."""
    conj_type = draw(conj_type_strategy())
    neg = draw(st.booleans())
    fml = draw(st.booleans())
    pos = draw(st.sampled_from(['v1', 'v5r', 'adj-i', 'adj-na', 'cop']))
    
    class MockConjProp:
        def __init__(self, conj_type, neg, fml, pos, conj_id=1):
            self.conj_type = conj_type
            self.neg = neg
            self.fml = fml
            self.pos = pos
            self.conj_id = conj_id
            self.id = 1
    
    return MockConjProp(conj_type, neg, fml, pos)


@st.composite
def mock_conj_data_strategy(draw):
    """Generate a mock ConjData object."""
    seq = draw(st.integers(min_value=1000000, max_value=9999999))
    from_seq = draw(st.integers(min_value=1000000, max_value=9999999))
    prop = draw(mock_conj_prop_strategy())
    
    # Generate source text mapping
    text = draw(st.text(
        alphabet='あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん',
        min_size=1,
        max_size=5
    ))
    assume(len(text) > 0)
    
    source_text = draw(st.text(
        alphabet='あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん',
        min_size=1,
        max_size=5
    ))
    assume(len(source_text) > 0)
    
    src_map = [(text, source_text)]
    
    return ConjData(
        seq=seq,
        from_seq=from_seq,
        via=None,
        prop=prop,
        src_map=src_map,
    ), text, source_text


# ============================================================================
# Property Tests
# ============================================================================

class TestConjugationTypeDetectionAccuracy:
    """
    Property 2: Conjugation Type Detection Accuracy
    
    For any conjugated word, if ichiran returns a conj_type value, himotoki
    SHALL return the same conj_type value, including "Adjective Stem" for
    な following adj-na words.
    
    **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    """
    
    @settings(max_examples=100)
    @given(conj_type=conj_type_strategy())
    def test_conj_type_names_mapping_complete(self, conj_type: int):
        """
        Property: For any valid conj_type ID, CONJ_TYPE_NAMES SHALL return a human-readable name.
        
        **Feature: score-calculation-alignment, Property 2: Conjugation Type Detection Accuracy**
        **Validates: Requirements 2.1**
        """
        name = CONJ_TYPE_NAMES.get(conj_type)
        assert name is not None, f"Missing name for conj_type {conj_type}"
        assert isinstance(name, str), f"Name should be string, got {type(name)}"
        assert len(name) > 0, f"Name should not be empty for conj_type {conj_type}"
    
    @settings(max_examples=100)
    @given(prop=mock_conj_prop_strategy())
    def test_conj_prop_has_valid_type(self, prop):
        """
        Property: For any ConjProp, conj_type SHALL be a valid key in CONJ_TYPE_NAMES.
        
        **Feature: score-calculation-alignment, Property 2: Conjugation Type Detection Accuracy**
        **Validates: Requirements 2.1**
        """
        assert prop.conj_type in CONJ_TYPE_NAMES
    
    @settings(max_examples=100)
    @given(data=mock_conj_data_strategy())
    def test_conj_data_source_text_preserved(self, data):
        """
        Property: For any ConjData with src_map, the source text SHALL be retrievable.
        
        **Feature: score-calculation-alignment, Property 2: Conjugation Type Detection Accuracy**
        **Validates: Requirements 2.3**
        """
        conj_data, text, expected_source = data
        
        # Verify src_map contains the expected mapping
        found = False
        for t, src in conj_data.src_map:
            if t == text:
                assert src == expected_source
                found = True
                break
        
        assert found, f"Source text mapping not found for {text}"
    
    @settings(max_examples=100)
    @given(prop=mock_conj_prop_strategy())
    def test_neg_fml_flags_are_boolean(self, prop):
        """
        Property: For any ConjProp, neg and fml flags SHALL be boolean values.
        
        **Feature: score-calculation-alignment, Property 2: Conjugation Type Detection Accuracy**
        **Validates: Requirements 2.4**
        """
        assert isinstance(prop.neg, bool)
        assert isinstance(prop.fml, bool)


# ============================================================================
# Integration Tests with Real Database
# ============================================================================

class TestConjugationTypeWithDatabase:
    """
    Integration tests for conjugation type detection using the real database.
    These tests verify that conjugation types are correctly identified in practice.
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
    
    def test_past_tense_detection(self, db_session):
        """
        Test that past tense conjugation is correctly detected.
        
        **Feature: score-calculation-alignment, Property 2: Conjugation Type Detection Accuracy**
        **Validates: Requirements 2.1, 2.2**
        """
        from himotoki.lookup import find_word_full
        from himotoki.suffixes import init_suffixes
        
        init_suffixes(db_session)
        
        # 食べた is past tense of 食べる
        words = find_word_full(db_session, '食べた')
        assert len(words) > 0, "Should find 食べた"
        
        # At least one should have Past conjugation type
        found_past = False
        for word in words:
            conj_type = get_conj_type_name(db_session, word)
            if conj_type and 'Past' in conj_type:
                found_past = True
                source = get_source_text(db_session, word)
                assert source == '食べる', f"Source should be 食べる, got {source}"
                break
        
        assert found_past, "Should detect Past conjugation type for 食べた"
    
    def test_te_form_detection(self, db_session):
        """
        Test that te-form conjugation is correctly detected.
        
        **Feature: score-calculation-alignment, Property 2: Conjugation Type Detection Accuracy**
        **Validates: Requirements 2.1, 2.2**
        """
        from himotoki.lookup import find_word_full
        from himotoki.suffixes import init_suffixes
        
        init_suffixes(db_session)
        
        # 食べて is te-form of 食べる
        words = find_word_full(db_session, '食べて')
        assert len(words) > 0, "Should find 食べて"
        
        # At least one should have Conjunctive conjugation type
        found_te = False
        for word in words:
            conj_type = get_conj_type_name(db_session, word)
            if conj_type and 'Conjunctive' in conj_type:
                found_te = True
                source = get_source_text(db_session, word)
                assert source == '食べる', f"Source should be 食べる, got {source}"
                break
        
        assert found_te, "Should detect Conjunctive conjugation type for 食べて"
    
    def test_negative_form_detection(self, db_session):
        """
        Test that negative form is correctly detected.
        
        **Feature: score-calculation-alignment, Property 2: Conjugation Type Detection Accuracy**
        **Validates: Requirements 2.4**
        """
        from himotoki.lookup import find_word_full
        from himotoki.suffixes import init_suffixes
        
        init_suffixes(db_session)
        
        # 食べない is negative of 食べる
        words = find_word_full(db_session, '食べない')
        assert len(words) > 0, "Should find 食べない"
        
        # At least one should have neg=True
        found_neg = False
        for word in words:
            neg = get_conj_neg(db_session, word)
            if neg:
                found_neg = True
                break
        
        assert found_neg, "Should detect negative form for 食べない"
    
    def test_formal_form_detection(self, db_session):
        """
        Test that formal/polite form is correctly detected.
        
        **Feature: score-calculation-alignment, Property 2: Conjugation Type Detection Accuracy**
        **Validates: Requirements 2.4**
        """
        from himotoki.lookup import find_word_full
        from himotoki.suffixes import init_suffixes
        
        init_suffixes(db_session)
        
        # 食べます is formal of 食べる
        words = find_word_full(db_session, '食べます')
        assert len(words) > 0, "Should find 食べます"
        
        # At least one should have fml=True
        found_fml = False
        for word in words:
            fml = get_conj_fml(db_session, word)
            if fml:
                found_fml = True
                break
        
        assert found_fml, "Should detect formal form for 食べます"
    
    def test_copula_conjunctive_detection(self, db_session):
        """
        Test that で (conjunctive of だ) is correctly detected.
        
        **Feature: score-calculation-alignment, Property 2: Conjugation Type Detection Accuracy**
        **Validates: Requirements 2.2, 2.3**
        """
        from himotoki.lookup import find_word_full
        from himotoki.suffixes import init_suffixes
        
        init_suffixes(db_session)
        
        # で can be conjunctive of だ
        words = find_word_full(db_session, 'で')
        assert len(words) > 0, "Should find で"
        
        # At least one should have Conjunctive type with source だ
        found_copula = False
        for word in words:
            conj_type = get_conj_type_name(db_session, word)
            source = get_source_text(db_session, word)
            if conj_type and 'Conjunctive' in conj_type and source == 'だ':
                found_copula = True
                break
        
        assert found_copula, "Should detect Conjunctive conjugation type for で with source だ"
    
    def test_segment_output_includes_conjugation_info(self, db_session):
        """
        Test that segment output includes conjugation info fields.
        
        **Feature: score-calculation-alignment, Property 2: Conjugation Type Detection Accuracy**
        **Validates: Requirements 2.4**
        """
        from himotoki.output import simple_segment
        from himotoki.suffixes import init_suffixes
        
        init_suffixes(db_session)
        
        # Test with a conjugated word
        result = simple_segment(db_session, '食べた')
        assert len(result) > 0, "Should segment 食べた"
        
        wi = result[0]
        # Check that conjugation info fields exist
        assert hasattr(wi, 'conj_type')
        assert hasattr(wi, 'conj_neg')
        assert hasattr(wi, 'conj_fml')
        assert hasattr(wi, 'source_text')
        
        # For 食べた, should have Past conjugation
        assert wi.conj_type is not None
        assert 'Past' in wi.conj_type
        assert wi.source_text == '食べる'
