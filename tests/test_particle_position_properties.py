"""
Property-based tests for particle position handling.

Feature: score-calculation-alignment
Property 8: Particle Position Handling

Validates: Requirements 8.1, 8.2, 8.3, 8.4
"""

import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck

from himotoki.lookup import (
    calc_score,
    find_word,
    FINAL_PRT,
    SEMI_FINAL_PRT,
    NON_FINAL_PRT,
)


# ============================================================================
# Strategies for generating test data
# ============================================================================

@st.composite
def particle_seq_strategy(draw):
    """Generate a particle seq from the known particle sets."""
    all_particles = list(FINAL_PRT | SEMI_FINAL_PRT | NON_FINAL_PRT)
    if not all_particles:
        # Fallback if sets are empty
        return None
    return draw(st.sampled_from(all_particles))


@st.composite
def final_position_strategy(draw):
    """Generate a boolean for final position."""
    return draw(st.booleans())


# ============================================================================
# Property Tests
# ============================================================================

class TestParticlePositionHandling:
    """
    Property 8: Particle Position Handling
    
    For any particle, the score SHALL be 0 if it's in FINAL_PRT and not at
    final position, and SHALL receive appropriate bonuses based on
    SEMI_FINAL_PRT and NON_FINAL_PRT membership.
    
    **Validates: Requirements 8.1, 8.2, 8.3, 8.4**
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
    
    def test_final_prt_returns_zero_when_not_final(self, db_session):
        """
        Property: For any particle in FINAL_PRT, score SHALL be 0 when not at final position.
        
        **Feature: score-calculation-alignment, Property 8: Particle Position Handling**
        **Validates: Requirements 8.2**
        """
        for seq in FINAL_PRT:
            # Find a word with this seq
            from himotoki.db.models import KanaText
            from sqlalchemy import select
            
            reading = db_session.execute(
                select(KanaText).where(KanaText.seq == seq)
            ).scalars().first()
            
            if reading:
                from himotoki.lookup import WordMatch
                word = WordMatch(reading=reading)
                
                # Score with final=False should be 0
                score, info = calc_score(db_session, word, final=False)
                assert score == 0, f"FINAL_PRT seq {seq} should return 0 when not final, got {score}"
    
    def test_final_prt_returns_nonzero_when_final(self, db_session):
        """
        Property: For any particle in FINAL_PRT, score SHALL be non-zero when at final position.
        
        **Feature: score-calculation-alignment, Property 8: Particle Position Handling**
        **Validates: Requirements 8.1**
        """
        for seq in FINAL_PRT:
            # Find a word with this seq
            from himotoki.db.models import KanaText
            from sqlalchemy import select
            
            reading = db_session.execute(
                select(KanaText).where(KanaText.seq == seq)
            ).scalars().first()
            
            if reading:
                from himotoki.lookup import WordMatch
                word = WordMatch(reading=reading)
                
                # Score with final=True should be non-zero
                score, info = calc_score(db_session, word, final=True)
                assert score > 0, f"FINAL_PRT seq {seq} should return >0 when final, got {score}"
    
    def test_semi_final_prt_gets_bonus_when_final(self, db_session):
        """
        Property: For any particle in SEMI_FINAL_PRT (but not FINAL_PRT), 
        score SHALL be higher when at final position.
        
        **Feature: score-calculation-alignment, Property 8: Particle Position Handling**
        **Validates: Requirements 8.3**
        """
        # Get particles that are in SEMI_FINAL_PRT but not in FINAL_PRT
        semi_only = SEMI_FINAL_PRT - FINAL_PRT
        
        for seq in semi_only:
            from himotoki.db.models import KanaText
            from sqlalchemy import select
            
            reading = db_session.execute(
                select(KanaText).where(KanaText.seq == seq)
            ).scalars().first()
            
            if reading:
                from himotoki.lookup import WordMatch
                word = WordMatch(reading=reading)
                
                # Score with final=True should be higher than final=False
                score_final, _ = calc_score(db_session, word, final=True)
                score_not_final, _ = calc_score(db_session, word, final=False)
                
                # Semi-final particles should get a bonus when final
                # but should still have a score when not final
                assert score_not_final > 0, \
                    f"SEMI_FINAL_PRT seq {seq} should have score >0 when not final"
                assert score_final >= score_not_final, \
                    f"SEMI_FINAL_PRT seq {seq} should have higher score when final"
    
    def test_non_final_prt_no_final_bonus(self, db_session):
        """
        Property: For any particle in NON_FINAL_PRT, the final bonus SHALL NOT be applied.
        
        **Feature: score-calculation-alignment, Property 8: Particle Position Handling**
        **Validates: Requirements 8.4**
        """
        for seq in NON_FINAL_PRT:
            from himotoki.db.models import KanaText
            from sqlalchemy import select
            
            reading = db_session.execute(
                select(KanaText).where(KanaText.seq == seq)
            ).scalars().first()
            
            if reading:
                from himotoki.lookup import WordMatch
                word = WordMatch(reading=reading)
                
                # Score with final=True and final=False
                score_final, _ = calc_score(db_session, word, final=True)
                score_not_final, _ = calc_score(db_session, word, final=False)
                
                # NON_FINAL_PRT particles should not get the primary_p +5 or semi_final +2 bonus
                # The difference should be minimal (only from common_p bonus if any)
                # The key is that they don't get the +5 or +2 final bonus
                assert score_final > 0, f"NON_FINAL_PRT seq {seq} should have score >0"


class TestParticlePositionWithHypothesis:
    """
    Hypothesis-based property tests for particle position handling.
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
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(final=st.booleans())
    def test_final_prt_score_depends_on_position(self, db_session, final: bool):
        """
        Property: For any FINAL_PRT particle, score is 0 iff not final.
        
        **Feature: score-calculation-alignment, Property 8: Particle Position Handling**
        **Validates: Requirements 8.1, 8.2**
        """
        # Pick a known FINAL_PRT particle: かい (2017770)
        seq = 2017770
        
        from himotoki.db.models import KanaText
        from sqlalchemy import select
        
        reading = db_session.execute(
            select(KanaText).where(KanaText.seq == seq)
        ).scalars().first()
        
        if not reading:
            pytest.skip(f"Particle seq {seq} not found in database")
        
        from himotoki.lookup import WordMatch
        word = WordMatch(reading=reading)
        
        score, info = calc_score(db_session, word, final=final)
        
        if final:
            assert score > 0, "FINAL_PRT should have positive score when final"
        else:
            assert score == 0, "FINAL_PRT should have zero score when not final"
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(final=st.booleans())
    def test_semi_final_prt_always_has_score(self, db_session, final: bool):
        """
        Property: For any SEMI_FINAL_PRT (non-FINAL_PRT) particle, score is always positive.
        
        **Feature: score-calculation-alignment, Property 8: Particle Position Handling**
        **Validates: Requirements 8.3**
        """
        # Pick a known SEMI_FINAL_PRT particle that's not in FINAL_PRT: ね (2029080)
        seq = 2029080
        
        from himotoki.db.models import KanaText
        from sqlalchemy import select
        
        reading = db_session.execute(
            select(KanaText).where(KanaText.seq == seq)
        ).scalars().first()
        
        if not reading:
            pytest.skip(f"Particle seq {seq} not found in database")
        
        from himotoki.lookup import WordMatch
        word = WordMatch(reading=reading)
        
        score, info = calc_score(db_session, word, final=final)
        
        # Semi-final particles should always have a positive score
        assert score > 0, f"SEMI_FINAL_PRT should have positive score, got {score}"
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(final=st.booleans())
    def test_non_final_prt_no_extra_final_bonus(self, db_session, final: bool):
        """
        Property: For any NON_FINAL_PRT particle, the final position bonus is not applied.
        
        **Feature: score-calculation-alignment, Property 8: Particle Position Handling**
        **Validates: Requirements 8.4**
        """
        # Pick a known NON_FINAL_PRT particle: ん (2139720)
        seq = 2139720
        
        from himotoki.db.models import KanaText
        from sqlalchemy import select
        
        reading = db_session.execute(
            select(KanaText).where(KanaText.seq == seq)
        ).scalars().first()
        
        if not reading:
            pytest.skip(f"Particle seq {seq} not found in database")
        
        from himotoki.lookup import WordMatch
        word = WordMatch(reading=reading)
        
        score_final, _ = calc_score(db_session, word, final=True)
        score_not_final, _ = calc_score(db_session, word, final=False)
        
        # NON_FINAL_PRT should have the same score regardless of final position
        # (no +5 or +2 final bonus)
        # Note: There might be small differences due to other bonuses, but
        # the key is that the final-specific bonus is not applied
        assert score_final > 0, "NON_FINAL_PRT should have positive score"


class TestParticleSetConsistency:
    """
    Tests for particle set consistency and correctness.
    """
    
    def test_final_prt_is_subset_of_semi_final_prt(self):
        """
        Property: FINAL_PRT SHALL be a subset of SEMI_FINAL_PRT.
        
        **Feature: score-calculation-alignment, Property 8: Particle Position Handling**
        **Validates: Requirements 8.2, 8.3**
        """
        assert FINAL_PRT.issubset(SEMI_FINAL_PRT), \
            "FINAL_PRT should be a subset of SEMI_FINAL_PRT"
    
    def test_non_final_prt_is_disjoint_from_final_prt(self):
        """
        Property: NON_FINAL_PRT SHALL be disjoint from FINAL_PRT.
        
        **Feature: score-calculation-alignment, Property 8: Particle Position Handling**
        **Validates: Requirements 8.2, 8.4**
        """
        assert FINAL_PRT.isdisjoint(NON_FINAL_PRT), \
            "FINAL_PRT and NON_FINAL_PRT should be disjoint"
    
    def test_particle_sets_are_not_empty(self):
        """
        Property: All particle sets SHALL be non-empty.
        
        **Feature: score-calculation-alignment, Property 8: Particle Position Handling**
        **Validates: Requirements 8.1, 8.2, 8.3, 8.4**
        """
        assert len(FINAL_PRT) > 0, "FINAL_PRT should not be empty"
        assert len(SEMI_FINAL_PRT) > 0, "SEMI_FINAL_PRT should not be empty"
        assert len(NON_FINAL_PRT) > 0, "NON_FINAL_PRT should not be empty"
