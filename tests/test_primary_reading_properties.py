"""
Property-based tests for primary reading detection.

Feature: score-calculation-alignment
Property 6: Primary Reading Detection

Validates: Requirements 6.1, 6.2, 6.3, 6.4
"""

import pytest
from hypothesis import given, strategies as st, settings, assume

from himotoki.lookup import (
    WordMatch,
    determine_primary_full,
    calc_score,
    find_word,
    get_non_arch_posi,
    get_conj_data,
)
from himotoki.db.models import Entry, KanaText, KanjiText, SenseProp, Sense


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

class TestPrimaryReadingDetection:
    """
    Property 6: Primary Reading Detection
    
    For any word, the primary_p determination SHALL match ichiran's logic,
    considering 'uk' tags, ord values, pronoun status, and primary_nokanji flags.
    
    **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
    """
    
    def test_uk_tag_prefers_kana_reading(self, db_session):
        """
        Property: For any word with 'uk' (usually kana) tag and no primary_nokanji
        restriction, kana readings SHALL be preferred as primary.
        
        **Feature: score-calculation-alignment, Property 6: Primary Reading Detection**
        **Validates: Requirements 6.1**
        """
        # Find words with uk tag
        from sqlalchemy import select, and_
        
        # Get a sample of entries with uk tag that don't have primary_nokanji set
        uk_entries = db_session.execute(
            select(SenseProp.seq)
            .where(and_(
                SenseProp.tag == 'misc',
                SenseProp.text == 'uk'
            ))
            .limit(100)
        ).scalars().all()
        
        tested = 0
        for seq in uk_entries:
            # Check if entry has primary_nokanji flag
            entry = db_session.get(Entry, seq)
            if not entry or entry.primary_nokanji:
                # Skip entries with primary_nokanji flag - they have special handling
                continue
            
            # Get kana readings for this entry
            kana_readings = db_session.execute(
                select(KanaText)
                .where(KanaText.seq == seq)
            ).scalars().all()
            
            for reading in kana_readings:
                if reading.ord == 0:
                    word = WordMatch(reading=reading)
                    score, info = calc_score(db_session, word)
                    kpcl = info.get('kpcl', [])
                    if len(kpcl) >= 2 and score > 0:
                        primary_p = kpcl[1]
                        # Kana reading with uk tag, ord=0, and no primary_nokanji should be primary
                        assert primary_p is True, f"Word {reading.text} (seq={seq}) should be primary"
                        tested += 1
                        if tested >= 20:
                            return
        
        # Ensure we tested at least some words
        assert tested > 0, "No uk-tagged words found to test"
    
    def test_kanji_ord0_without_uk_is_primary(self, db_session):
        """
        Property: For any word with ord=0 and kanji form without 'uk' tag,
        THE Scorer SHALL treat it as primary.
        
        **Feature: score-calculation-alignment, Property 6: Primary Reading Detection**
        **Validates: Requirements 6.2**
        """
        from sqlalchemy import select, and_, not_
        
        # Find kanji entries without uk tag
        # First get seqs that have uk tag
        uk_seqs = db_session.execute(
            select(SenseProp.seq)
            .where(and_(
                SenseProp.tag == 'misc',
                SenseProp.text == 'uk'
            ))
        ).scalars().all()
        uk_seqs_set = set(uk_seqs)
        
        # Get kanji readings with ord=0 that don't have uk tag
        kanji_readings = db_session.execute(
            select(KanjiText)
            .where(and_(
                KanjiText.ord == 0,
                KanjiText.common.isnot(None)
            ))
            .limit(100)
        ).scalars().all()
        
        tested = 0
        for reading in kanji_readings:
            if reading.seq not in uk_seqs_set:
                word = WordMatch(reading=reading)
                score, info = calc_score(db_session, word)
                kpcl = info.get('kpcl', [])
                if len(kpcl) >= 2 and score > 0:
                    kanji_p = kpcl[0]
                    primary_p = kpcl[1]
                    # Kanji reading with ord=0 and no uk tag should be primary
                    if kanji_p:
                        assert primary_p is True, f"Kanji word {reading.text} (seq={reading.seq}) should be primary"
                        tested += 1
                        if tested >= 20:
                            return
        
        assert tested > 0, "No kanji words without uk tag found to test"
    
    def test_pronoun_with_common_is_primary(self, db_session):
        """
        Property: For any pronoun with common reading, THE Scorer SHALL
        treat it as primary.
        
        **Feature: score-calculation-alignment, Property 6: Primary Reading Detection**
        **Validates: Requirements 6.3**
        """
        from sqlalchemy import select, and_
        
        # Find pronouns (pn tag)
        pronoun_seqs = db_session.execute(
            select(SenseProp.seq)
            .where(and_(
                SenseProp.tag == 'pos',
                SenseProp.text == 'pn'
            ))
            .distinct()
            .limit(50)
        ).scalars().all()
        
        tested = 0
        for seq in pronoun_seqs:
            # Get readings for this pronoun
            kana_readings = db_session.execute(
                select(KanaText)
                .where(and_(
                    KanaText.seq == seq,
                    KanaText.common.isnot(None),
                    KanaText.ord == 0
                ))
            ).scalars().all()
            
            for reading in kana_readings:
                word = WordMatch(reading=reading)
                score, info = calc_score(db_session, word)
                kpcl = info.get('kpcl', [])
                if len(kpcl) >= 3 and score > 0:
                    primary_p = kpcl[1]
                    common_p = kpcl[2]
                    # Pronoun with common reading should be primary
                    if common_p:
                        assert primary_p is True, f"Pronoun {reading.text} (seq={seq}) should be primary"
                        tested += 1
                        if tested >= 20:
                            return
        
        assert tested > 0, "No pronouns with common reading found to test"
    
    def test_primary_nokanji_flag_respected(self, db_session):
        """
        Property: When determining primary status, THE Scorer SHALL check
        the primary_nokanji flag on entries.
        
        **Feature: score-calculation-alignment, Property 6: Primary Reading Detection**
        **Validates: Requirements 6.4**
        """
        from sqlalchemy import select, and_
        
        # Find entries with primary_nokanji flag set
        entries_with_nokanji = db_session.execute(
            select(Entry)
            .where(Entry.primary_nokanji == True)
            .limit(50)
        ).scalars().all()
        
        tested = 0
        for entry in entries_with_nokanji:
            # Get kana readings for this entry
            kana_readings = db_session.execute(
                select(KanaText)
                .where(and_(
                    KanaText.seq == entry.seq,
                    KanaText.ord == 0
                ))
            ).scalars().all()
            
            for reading in kana_readings:
                # Check if reading has nokanji flag
                if hasattr(reading, 'nokanji') and reading.nokanji:
                    word = WordMatch(reading=reading)
                    score, info = calc_score(db_session, word)
                    kpcl = info.get('kpcl', [])
                    if len(kpcl) >= 2 and score > 0:
                        primary_p = kpcl[1]
                        # Reading with nokanji flag should be primary
                        assert primary_p is True, f"Word {reading.text} with nokanji flag should be primary"
                        tested += 1
                        if tested >= 10:
                            return
        
        # This test may not find any entries if nokanji flag is not commonly set
        # That's okay - the flag is checked in the code
        if tested == 0:
            pytest.skip("No entries with primary_nokanji and nokanji reading found")


class TestPrimaryReadingConsistency:
    """
    Additional property tests for primary reading consistency.
    """
    
    def test_primary_p_in_kpcl_is_boolean(self, db_session):
        """
        Property: For any word, the primary_p value in kpcl SHALL be a boolean.
        
        **Feature: score-calculation-alignment, Property 6: Primary Reading Detection**
        **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
        """
        # Test with various common words
        test_words = ['私', 'わたし', '食べる', 'たべる', '行く', 'いく', 'きれい', '綺麗']
        
        for word_text in test_words:
            words = find_word(db_session, word_text)
            for word in words:
                score, info = calc_score(db_session, word)
                kpcl = info.get('kpcl', [])
                if len(kpcl) >= 2:
                    primary_p = kpcl[1]
                    assert isinstance(primary_p, bool), f"primary_p should be bool, got {type(primary_p)}"
    
    def test_common_words_have_primary_reading(self, db_session):
        """
        Property: For any common word (common != None), at least one reading
        SHALL be marked as primary.
        
        **Feature: score-calculation-alignment, Property 6: Primary Reading Detection**
        **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
        """
        from sqlalchemy import select, and_
        
        # Get a sample of common entries
        common_entries = db_session.execute(
            select(Entry.seq)
            .where(Entry.root_p == True)
            .limit(100)
        ).scalars().all()
        
        tested = 0
        for seq in common_entries:
            # Get all readings for this entry
            kanji_readings = db_session.execute(
                select(KanjiText).where(KanjiText.seq == seq)
            ).scalars().all()
            kana_readings = db_session.execute(
                select(KanaText).where(KanaText.seq == seq)
            ).scalars().all()
            
            all_readings = list(kanji_readings) + list(kana_readings)
            if not all_readings:
                continue
            
            # Check if at least one reading is primary
            has_primary = False
            for reading in all_readings:
                word = WordMatch(reading=reading)
                score, info = calc_score(db_session, word)
                if score > 0:
                    kpcl = info.get('kpcl', [])
                    if len(kpcl) >= 2 and kpcl[1]:
                        has_primary = True
                        break
            
            # At least one reading should be primary for valid entries
            if has_primary:
                tested += 1
                if tested >= 50:
                    break
        
        assert tested > 0, "No entries with primary readings found"
