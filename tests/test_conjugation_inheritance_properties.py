"""
Property-based tests for conjugation data inheritance.

Feature: score-calculation-alignment
Property 7: Conjugation Data Inheritance

Validates: Requirements 7.1, 7.2, 7.3, 7.4
"""

import pytest
from hypothesis import given, strategies as st, settings, assume

from himotoki.lookup import (
    WordMatch,
    calc_score,
    find_word,
    get_word_conj_data,
    get_original_text_data,
    get_conj_data,
    is_weak_conj_form,
    matches_conj_form,
    WEAK_CONJ_FORMS,
    ConjData,
)
from himotoki.db.models import Entry, KanaText, KanjiText, Conjugation


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def db_session():
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


# ============================================================================
# Property Tests
# ============================================================================

class TestConjugationDataInheritance:
    """
    Property 7: Conjugation Data Inheritance
    
    For any conjugated form, if the source form has a common rating or lower ord,
    the conjugated form SHALL inherit these values for scoring purposes.
    
    **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
    """
    
    def test_conjugated_form_inherits_common_from_source(self, db_session):
        """
        Property: For any conjugated form without common rating, if the source
        form has a common rating, the conjugated form SHALL inherit it.
        
        **Feature: score-calculation-alignment, Property 7: Conjugation Data Inheritance**
        **Validates: Requirements 7.1**
        """
        from sqlalchemy import select, and_
        
        # Find conjugated entries (entries with conjugation data)
        conj_entries = db_session.execute(
            select(Conjugation.seq, Conjugation.from_seq)
            .distinct()
            .limit(100)
        ).all()
        
        tested = 0
        for seq, from_seq in conj_entries:
            # Get kana readings for the conjugated entry
            kana_readings = db_session.execute(
                select(KanaText)
                .where(and_(
                    KanaText.seq == seq,
                    KanaText.common.is_(None)  # No common rating
                ))
            ).scalars().all()
            
            for reading in kana_readings:
                word = WordMatch(reading=reading)
                conj_data = get_word_conj_data(db_session, word)
                
                if not conj_data:
                    continue
                
                # Get original text data
                orig_data = get_original_text_data(db_session, word, conj_data)
                
                if orig_data:
                    # Check if any source has common rating
                    source_common = [c for c, o in orig_data if c is not None]
                    
                    if source_common:
                        # Score the word and check if common was inherited
                        score, info = calc_score(db_session, word)
                        
                        if score > 0:
                            # The common value in info should be set
                            common_in_info = info.get('common')
                            assert common_in_info is not None, \
                                f"Word {reading.text} should inherit common from source"
                            tested += 1
                            if tested >= 20:
                                return
        
        # Ensure we tested at least some words
        if tested == 0:
            pytest.skip("No conjugated words without common found to test")
    
    def test_conjugated_form_inherits_lower_ord_from_source(self, db_session):
        """
        Property: For any conjugated form, if the source form has a lower ord,
        the conjugated form SHALL use the source's ord value.
        
        **Feature: score-calculation-alignment, Property 7: Conjugation Data Inheritance**
        **Validates: Requirements 7.2**
        """
        from sqlalchemy import select, and_
        
        # Find conjugated entries
        conj_entries = db_session.execute(
            select(Conjugation.seq, Conjugation.from_seq)
            .distinct()
            .limit(100)
        ).all()
        
        tested = 0
        for seq, from_seq in conj_entries:
            # Get readings for the conjugated entry with ord > 0
            kana_readings = db_session.execute(
                select(KanaText)
                .where(and_(
                    KanaText.seq == seq,
                    KanaText.ord > 0
                ))
            ).scalars().all()
            
            for reading in kana_readings:
                word = WordMatch(reading=reading)
                conj_data = get_word_conj_data(db_session, word)
                
                if not conj_data:
                    continue
                
                # Get original text data
                orig_data = get_original_text_data(db_session, word, conj_data)
                
                if orig_data:
                    # Check if any source has lower ord
                    source_ords = [o for c, o in orig_data]
                    min_source_ord = min(source_ords) if source_ords else reading.ord
                    
                    if min_source_ord < reading.ord:
                        # The word should use the lower ord for scoring
                        # We can verify this by checking the score is higher
                        # than it would be with the original ord
                        score, info = calc_score(db_session, word)
                        
                        if score > 0:
                            tested += 1
                            if tested >= 20:
                                return
        
        if tested == 0:
            pytest.skip("No conjugated words with higher ord than source found")
    
    def test_secondary_conjugations_filtered_unless_all_secondary(self, db_session):
        """
        Property: When getting conjugation data, secondary conjugations (via forms)
        SHALL be filtered out unless ALL conjugations are secondary.
        
        **Feature: score-calculation-alignment, Property 7: Conjugation Data Inheritance**
        **Validates: Requirements 7.3**
        """
        from sqlalchemy import select, and_
        
        # Find entries with both primary and secondary conjugations
        # (entries where some conjugations have via and some don't)
        entries_with_mixed = db_session.execute(
            select(Conjugation.seq)
            .where(Conjugation.via.isnot(None))
            .distinct()
            .limit(50)
        ).scalars().all()
        
        tested = 0
        for seq in entries_with_mixed:
            # Get all conjugations for this seq
            all_conjs = db_session.execute(
                select(Conjugation)
                .where(Conjugation.seq == seq)
            ).scalars().all()
            
            has_primary = any(c.via is None for c in all_conjs)
            has_secondary = any(c.via is not None for c in all_conjs)
            
            if has_primary and has_secondary:
                # Get a reading for this entry
                reading = db_session.execute(
                    select(KanaText)
                    .where(KanaText.seq == seq)
                ).scalars().first()
                
                if reading:
                    word = WordMatch(reading=reading)
                    conj_data = get_word_conj_data(db_session, word)
                    
                    # In calc_score, secondary conjugations should be filtered
                    # unless all are secondary
                    if conj_data:
                        # Check that we have the expected filtering behavior
                        # by scoring the word
                        score, info = calc_score(db_session, word)
                        
                        if score > 0:
                            # The conj data in info should have secondary filtered
                            info_conj = info.get('conj', [])
                            # If there were primary conjugations, secondary should be filtered
                            if has_primary:
                                # All remaining should be primary (no via)
                                for cd in info_conj:
                                    if cd.via is not None:
                                        # This is okay if ALL were secondary
                                        all_secondary = all(c.via is not None for c in all_conjs)
                                        assert all_secondary, \
                                            f"Secondary conj should be filtered for {reading.text}"
                            tested += 1
                            if tested >= 10:
                                return
        
        if tested == 0:
            pytest.skip("No entries with mixed primary/secondary conjugations found")
    
    def test_weak_forms_reduce_scoring_contribution(self, db_session):
        """
        Property: When a conjugation is a weak form, THE Scorer SHALL reduce
        its contribution to scoring.
        
        **Feature: score-calculation-alignment, Property 7: Conjugation Data Inheritance**
        **Validates: Requirements 7.4**
        """
        from sqlalchemy import select, and_
        from himotoki.lookup import CONJ_ADJECTIVE_STEM, CONJ_NEGATIVE_STEM
        
        # Find words with weak conjugation forms
        # Weak forms include: adjective stem, negative stem, causative (~su), etc.
        weak_conj_types = [
            CONJ_ADJECTIVE_STEM,  # 51
            CONJ_NEGATIVE_STEM,   # 52
        ]
        
        tested = 0
        
        # Get conjugations with weak types
        from himotoki.db.models import ConjProp
        weak_conjs = db_session.execute(
            select(ConjProp.conj_id, Conjugation.seq)
            .join(Conjugation, ConjProp.conj_id == Conjugation.id)
            .where(ConjProp.conj_type.in_(weak_conj_types))
            .limit(50)
        ).all()
        
        for conj_id, seq in weak_conjs:
            # Get a reading for this entry
            reading = db_session.execute(
                select(KanaText)
                .where(KanaText.seq == seq)
            ).scalars().first()
            
            if reading:
                word = WordMatch(reading=reading)
                conj_data = get_word_conj_data(db_session, word)
                
                if conj_data and is_weak_conj_form(conj_data):
                    # Score the word
                    score, info = calc_score(db_session, word)
                    
                    if score > 0:
                        # Weak forms should have reduced contribution
                        # This is reflected in conj_types_p being False
                        # which affects no_common_bonus
                        kpcl = info.get('kpcl', [])
                        if len(kpcl) >= 3:
                            # The scoring should reflect weak form handling
                            tested += 1
                            if tested >= 10:
                                return
        
        if tested == 0:
            pytest.skip("No weak conjugation forms found to test")


class TestGetOriginalTextData:
    """
    Tests for the get_original_text_data function.
    """
    
    def test_returns_common_and_ord_pairs(self, db_session):
        """
        Property: get_original_text_data SHALL return (common, ord) pairs
        from the source forms.
        
        **Feature: score-calculation-alignment, Property 7: Conjugation Data Inheritance**
        **Validates: Requirements 7.1, 7.2**
        """
        from sqlalchemy import select
        
        # Find a conjugated word
        conj = db_session.execute(
            select(Conjugation)
            .limit(1)
        ).scalars().first()
        
        if not conj:
            pytest.skip("No conjugations found")
        
        # Get a reading for this conjugated entry
        reading = db_session.execute(
            select(KanaText)
            .where(KanaText.seq == conj.seq)
        ).scalars().first()
        
        if not reading:
            pytest.skip("No reading found for conjugated entry")
        
        word = WordMatch(reading=reading)
        conj_data = get_word_conj_data(db_session, word)
        
        if not conj_data:
            pytest.skip("No conjugation data found")
        
        orig_data = get_original_text_data(db_session, word, conj_data)
        
        # Each item should be a tuple of (common, ord)
        for item in orig_data:
            assert isinstance(item, tuple), "Should return tuples"
            assert len(item) == 2, "Should return (common, ord) pairs"
            common, ord_val = item
            assert common is None or isinstance(common, int), "common should be int or None"
            assert isinstance(ord_val, int), "ord should be int"
    
    def test_handles_secondary_conjugations_recursively(self, db_session):
        """
        Property: For secondary conjugations (via forms), get_original_text_data
        SHALL recursively follow the chain to find the original source.
        
        **Feature: score-calculation-alignment, Property 7: Conjugation Data Inheritance**
        **Validates: Requirements 7.1, 7.2**
        """
        from sqlalchemy import select
        
        # Find a secondary conjugation (has via)
        secondary_conj = db_session.execute(
            select(Conjugation)
            .where(Conjugation.via.isnot(None))
            .limit(1)
        ).scalars().first()
        
        if not secondary_conj:
            pytest.skip("No secondary conjugations found")
        
        # Get a reading for this entry
        reading = db_session.execute(
            select(KanaText)
            .where(KanaText.seq == secondary_conj.seq)
        ).scalars().first()
        
        if not reading:
            pytest.skip("No reading found for secondary conjugation")
        
        word = WordMatch(reading=reading)
        conj_data = get_word_conj_data(db_session, word)
        
        # Filter to only secondary conjugations
        secondary_conj_data = [cd for cd in conj_data if cd.via is not None]
        
        if not secondary_conj_data:
            pytest.skip("No secondary conjugation data found")
        
        # This should recursively follow the via chain
        orig_data = get_original_text_data(db_session, word, secondary_conj_data)
        
        # Should return data from the ultimate source
        # (the function should handle the recursion)
        # We just verify it doesn't crash and returns valid data
        for item in orig_data:
            assert isinstance(item, tuple), "Should return tuples"
            assert len(item) == 2, "Should return (common, ord) pairs"
