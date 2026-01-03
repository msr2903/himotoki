"""
Tests for the himotoki lookup module.
Tests word lookup, scoring, and segment operations.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from himotoki.db.models import (
    Base, Entry, KanjiText, KanaText, Sense, Gloss, SenseProp,
    Conjugation, ConjProp, ConjSourceReading, create_all_tables,
)
from himotoki.lookup import (
    # Constants
    MAX_WORD_LENGTH,
    SCORE_CUTOFF,
    LENGTH_COEFF_SEQUENCES,
    # Functions
    length_multiplier,
    length_multiplier_coeff,
    find_word,
    find_word_full,
    get_conj_data,
    compare_common,
    kanji_break_penalty,
    calc_score,
    cull_segments,
    gen_score,
    gap_penalty,
    # Data structures
    WordMatch,
    Segment,
    SegmentList,
    ConjData,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def engine():
    """Create an in-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    create_all_tables(engine)
    return engine


@pytest.fixture
def session(engine):
    """Create a database session."""
    with Session(engine) as session:
        yield session


@pytest.fixture
def populated_session(session):
    """Create a session with sample dictionary data."""
    # Add entry for 食べる (to eat) - verb, common
    taberu = Entry(seq=1358280, content="", root_p=True, n_kanji=1, n_kana=1)
    session.add(taberu)
    
    taberu_kanji = KanjiText(seq=1358280, text="食べる", ord=0, common=1)
    taberu_kana = KanaText(seq=1358280, text="たべる", ord=0, common=1)
    session.add_all([taberu_kanji, taberu_kana])
    
    # Add sense
    taberu_sense = Sense(seq=1358280, ord=0)
    session.add(taberu_sense)
    session.flush()
    
    taberu_gloss = Gloss(sense_id=taberu_sense.id, text="to eat", ord=0)
    taberu_pos = SenseProp(sense_id=taberu_sense.id, seq=1358280, tag="pos", text="v1", ord=0)
    session.add_all([taberu_gloss, taberu_pos])
    
    # Add entry for は (particle)
    ha = Entry(seq=2028920, content="", root_p=True, n_kanji=0, n_kana=1)
    session.add(ha)
    
    ha_kana = KanaText(seq=2028920, text="は", ord=0, common=1)
    session.add(ha_kana)
    
    ha_sense = Sense(seq=2028920, ord=0)
    session.add(ha_sense)
    session.flush()
    
    ha_gloss = Gloss(sense_id=ha_sense.id, text="topic marker particle", ord=0)
    ha_pos = SenseProp(sense_id=ha_sense.id, seq=2028920, tag="pos", text="prt", ord=0)
    session.add_all([ha_gloss, ha_pos])
    
    # Add entry for 学校 (school) - noun, common
    gakkou = Entry(seq=1280820, content="", root_p=True, n_kanji=1, n_kana=1)
    session.add(gakkou)
    
    gakkou_kanji = KanjiText(seq=1280820, text="学校", ord=0, common=1)
    gakkou_kana = KanaText(seq=1280820, text="がっこう", ord=0, common=1)
    session.add_all([gakkou_kanji, gakkou_kana])
    
    gakkou_sense = Sense(seq=1280820, ord=0)
    session.add(gakkou_sense)
    session.flush()
    
    gakkou_gloss = Gloss(sense_id=gakkou_sense.id, text="school", ord=0)
    gakkou_pos = SenseProp(sense_id=gakkou_sense.id, seq=1280820, tag="pos", text="n", ord=0)
    session.add_all([gakkou_gloss, gakkou_pos])
    
    # Add entry for 勉強 (study) - noun/verb
    benkyou = Entry(seq=1595340, content="", root_p=True, n_kanji=1, n_kana=1)
    session.add(benkyou)
    
    benkyou_kanji = KanjiText(seq=1595340, text="勉強", ord=0, common=1)
    benkyou_kana = KanaText(seq=1595340, text="べんきょう", ord=0, common=1)
    session.add_all([benkyou_kanji, benkyou_kana])
    
    # Add entry for する (to do) - suru verb
    suru = Entry(seq=1157170, content="", root_p=True, n_kanji=0, n_kana=1)
    session.add(suru)
    
    suru_kana = KanaText(seq=1157170, text="する", ord=0, common=1)
    session.add(suru_kana)
    
    suru_sense = Sense(seq=1157170, ord=0)
    session.add(suru_sense)
    session.flush()
    
    suru_gloss = Gloss(sense_id=suru_sense.id, text="to do", ord=0)
    suru_pos = SenseProp(sense_id=suru_sense.id, seq=1157170, tag="pos", text="vs-i", ord=0)
    session.add_all([suru_gloss, suru_pos])
    
    # Add entry for 猫 (cat)
    neko = Entry(seq=1467640, content="", root_p=True, n_kanji=1, n_kana=1)
    session.add(neko)
    
    neko_kanji = KanjiText(seq=1467640, text="猫", ord=0, common=1)
    neko_kana = KanaText(seq=1467640, text="ねこ", ord=0, common=1)
    session.add_all([neko_kanji, neko_kana])
    
    # Add entry for アメリカ (America) - katakana word
    america = Entry(seq=1001670, content="", root_p=True, n_kanji=0, n_kana=1)
    session.add(america)
    
    america_kana = KanaText(seq=1001670, text="アメリカ", ord=0, common=1)
    session.add(america_kana)
    
    # Add uncommon word for testing
    rare = Entry(seq=9999999, content="", root_p=True, n_kanji=1, n_kana=1)
    session.add(rare)
    
    rare_kanji = KanjiText(seq=9999999, text="稀有", ord=0, common=None)
    rare_kana = KanaText(seq=9999999, text="けう", ord=0, common=None)
    session.add_all([rare_kanji, rare_kana])
    
    session.commit()
    return session


# ============================================================================
# Length Coefficient Tests
# ============================================================================

class TestLengthMultiplier:
    """Tests for length_multiplier function."""
    
    def test_below_limit(self):
        """Test length multiplier below limit."""
        assert length_multiplier(2, 2, 5) == 4  # 2^2
        assert length_multiplier(3, 2, 5) == 9  # 3^2
        
    def test_at_limit(self):
        """Test length multiplier at limit."""
        assert length_multiplier(5, 2, 5) == 25  # 5^2
        
    def test_above_limit(self):
        """Test length multiplier above limit (linear)."""
        # Above limit: length * len_lim^(power-1)
        # 6 * 5^1 = 30
        assert length_multiplier(6, 2, 5) == 30
        assert length_multiplier(7, 2, 5) == 35


class TestLengthMultiplierCoeff:
    """Tests for length_multiplier_coeff function."""
    
    def test_strong_coefficients(self):
        """Test strong coefficient sequence."""
        assert length_multiplier_coeff(1, 'strong') == 1
        assert length_multiplier_coeff(2, 'strong') == 8
        assert length_multiplier_coeff(3, 'strong') == 24
        assert length_multiplier_coeff(4, 'strong') == 40
        assert length_multiplier_coeff(5, 'strong') == 60
    
    def test_weak_coefficients(self):
        """Test weak coefficient sequence."""
        assert length_multiplier_coeff(1, 'weak') == 1
        assert length_multiplier_coeff(2, 'weak') == 4
        assert length_multiplier_coeff(3, 'weak') == 9
        assert length_multiplier_coeff(4, 'weak') == 16
        assert length_multiplier_coeff(5, 'weak') == 25
        assert length_multiplier_coeff(6, 'weak') == 36
    
    def test_tail_coefficients(self):
        """Test tail coefficient sequence."""
        assert length_multiplier_coeff(1, 'tail') == 4
        assert length_multiplier_coeff(2, 'tail') == 9
        assert length_multiplier_coeff(3, 'tail') == 16
        assert length_multiplier_coeff(4, 'tail') == 24
    
    def test_extrapolation(self):
        """Test linear extrapolation beyond table."""
        # strong has 6 entries [0,1,8,24,40,60], last_idx=5, last_coeff=60
        # For length 6: 6 * (60 // 5) = 6 * 12 = 72
        assert length_multiplier_coeff(6, 'strong') == 72
        
    def test_unknown_class(self):
        """Test fallback for unknown coefficient class."""
        # Unknown class returns just the length
        assert length_multiplier_coeff(5, 'nonexistent') == 5


# ============================================================================
# Word Lookup Tests
# ============================================================================

class TestFindWord:
    """Tests for find_word function."""
    
    def test_find_kanji_word(self, populated_session):
        """Test finding a word with kanji."""
        results = find_word(populated_session, "食べる")
        assert len(results) == 1
        assert results[0].text == "食べる"
        assert results[0].seq == 1358280
        assert results[0].word_type == "kanji"
    
    def test_find_kana_word(self, populated_session):
        """Test finding a word in kana."""
        results = find_word(populated_session, "たべる")
        assert len(results) == 1
        assert results[0].text == "たべる"
        assert results[0].word_type == "kana"
    
    def test_find_particle(self, populated_session):
        """Test finding a particle."""
        results = find_word(populated_session, "は")
        assert len(results) == 1
        assert results[0].seq == 2028920
    
    def test_find_katakana_word(self, populated_session):
        """Test finding a katakana word."""
        results = find_word(populated_session, "アメリカ")
        assert len(results) == 1
        assert results[0].text == "アメリカ"
    
    def test_find_nonexistent_word(self, populated_session):
        """Test finding a word that doesn't exist."""
        results = find_word(populated_session, "存在しない")
        assert len(results) == 0
    
    def test_max_word_length(self, populated_session):
        """Test that very long words are skipped."""
        # Create a string longer than MAX_WORD_LENGTH
        long_word = "あ" * (MAX_WORD_LENGTH + 10)
        results = find_word(populated_session, long_word)
        assert len(results) == 0
    
    def test_root_only(self, populated_session):
        """Test finding only root entries."""
        results = find_word(populated_session, "学校", root_only=True)
        assert len(results) == 1
        assert results[0].text == "学校"


class TestFindWordFull:
    """Tests for find_word_full function."""
    
    def test_simple_lookup(self, populated_session):
        """Test simple word lookup."""
        results = find_word_full(populated_session, "猫")
        assert len(results) == 1
        assert results[0].text == "猫"


# ============================================================================
# Comparison Functions Tests
# ============================================================================

class TestCompareCommon:
    """Tests for compare_common function."""
    
    def test_none_vs_value(self):
        """None is worse than any value."""
        assert compare_common(1, None) == True
        assert compare_common(0, None) == True
        
    def test_value_vs_none(self):
        """Any value is better than None."""
        assert compare_common(None, 1) == False
    
    def test_zero_special(self):
        """0 is special (very common)."""
        assert compare_common(1, 0) == True  # 1 is not as common as 0
        assert compare_common(0, 1) == False  # 0 is more common than 1
        
    def test_lower_is_better(self):
        """Lower commonness value is better."""
        assert compare_common(1, 5) == True  # 1 is more common
        assert compare_common(5, 1) == False  # 5 is less common


# ============================================================================
# WordMatch Tests
# ============================================================================

class TestWordMatch:
    """Tests for WordMatch data structure."""
    
    def test_word_match_properties(self, populated_session):
        """Test WordMatch properties."""
        results = find_word(populated_session, "学校")
        match = results[0]
        
        assert match.seq == 1280820
        assert match.text == "学校"
        assert match.common == 1
        assert match.ord == 0
        assert match.word_type == "kanji"
        assert match.is_root == False
    
    def test_kana_word_type(self, populated_session):
        """Test word_type for kana words."""
        results = find_word(populated_session, "する")
        assert len(results) == 1
        assert results[0].word_type == "kana"


# ============================================================================
# Segment Tests
# ============================================================================

class TestSegment:
    """Tests for Segment data structure."""
    
    def test_segment_creation(self, populated_session):
        """Test creating a segment."""
        results = find_word(populated_session, "学校")
        match = results[0]
        
        seg = Segment(start=0, end=2, word=match)
        
        assert seg.start == 0
        assert seg.end == 2
        assert seg.get_text() == "学校"
        assert seg.score == 0.0  # Default
    
    def test_segment_text_caching(self, populated_session):
        """Test that segment text is cached."""
        results = find_word(populated_session, "学校")
        seg = Segment(start=0, end=2, word=results[0])
        
        # First call should cache
        text1 = seg.get_text()
        # Second call should use cache
        text2 = seg.get_text()
        
        assert text1 == text2 == "学校"
        assert seg.text == "学校"


class TestSegmentList:
    """Tests for SegmentList data structure."""
    
    def test_segment_list_creation(self, populated_session):
        """Test creating a segment list."""
        results = find_word(populated_session, "学校")
        seg = Segment(start=0, end=2, word=results[0])
        
        seg_list = SegmentList(segments=[seg], start=0, end=2, matches=1)
        
        assert len(seg_list.segments) == 1
        assert seg_list.start == 0
        assert seg_list.end == 2
        assert seg_list.matches == 1


# ============================================================================
# Scoring Tests
# ============================================================================

class TestCalcScore:
    """Tests for calc_score function."""
    
    def test_score_common_kanji(self, populated_session):
        """Test scoring a common kanji word."""
        results = find_word(populated_session, "学校")
        match = results[0]
        
        score, info = calc_score(populated_session, match)
        
        assert score > SCORE_CUTOFF
        assert 'posi' in info
        assert 'seq_set' in info
        assert match.seq in info['seq_set']
    
    def test_score_particle(self, populated_session):
        """Test scoring a particle."""
        results = find_word(populated_session, "は")
        match = results[0]
        
        score, info = calc_score(populated_session, match)
        
        assert score > 0
        assert 'prt' in info['posi']
    
    def test_final_particle_bonus(self, populated_session):
        """Test that final=True affects particle scoring."""
        results = find_word(populated_session, "は")
        match = results[0]
        
        score_normal, _ = calc_score(populated_session, match, final=False)
        score_final, _ = calc_score(populated_session, match, final=True)
        
        # Final particles should get a bonus
        assert score_final >= score_normal
    
    def test_score_uncommon_word(self, populated_session):
        """Test scoring an uncommon word."""
        results = find_word(populated_session, "稀有")
        match = results[0]
        
        score, info = calc_score(populated_session, match)
        
        # Uncommon words should still get a valid score
        assert score > 0
        assert info['common'] is None


class TestGenScore:
    """Tests for gen_score function."""
    
    def test_gen_score(self, populated_session):
        """Test generating score for a segment."""
        results = find_word(populated_session, "学校")
        seg = Segment(start=0, end=2, word=results[0])
        
        seg = gen_score(populated_session, seg)
        
        assert seg.score > 0
        assert 'posi' in seg.info


class TestCullSegments:
    """Tests for cull_segments function."""
    
    def test_cull_keeps_high_scorers(self, populated_session):
        """Test that culling keeps high-scoring segments."""
        results = find_word(populated_session, "学校")
        seg1 = Segment(start=0, end=2, word=results[0], score=100, info={'common': 1})
        seg2 = Segment(start=0, end=2, word=results[0], score=60, info={'common': 1})
        
        culled = cull_segments([seg1, seg2])
        
        assert len(culled) == 2  # Both should be kept (60 >= 100 * 0.5)
    
    def test_cull_removes_low_scorers(self, populated_session):
        """Test that culling removes low-scoring segments."""
        results = find_word(populated_session, "学校")
        seg1 = Segment(start=0, end=2, word=results[0], score=100, info={'common': 1})
        seg2 = Segment(start=0, end=2, word=results[0], score=40, info={'common': 1})
        
        culled = cull_segments([seg1, seg2])
        
        # seg2 (40) < 100 * 0.5 (50), so it should be removed
        assert len(culled) == 1
        assert culled[0].score == 100
    
    def test_cull_empty_list(self):
        """Test culling an empty list."""
        assert cull_segments([]) == []


# ============================================================================
# Gap Penalty Tests
# ============================================================================

class TestGapPenalty:
    """Tests for gap_penalty function."""
    
    def test_gap_penalty(self):
        """Test gap penalty calculation."""
        # Gap of 3 characters
        assert gap_penalty(0, 3) == -1500  # 3 * -500
        
    def test_zero_gap(self):
        """Test zero gap penalty."""
        assert gap_penalty(5, 5) == 0


# ============================================================================
# Kanji Break Penalty Tests
# ============================================================================

class TestKanjiBreakPenalty:
    """Tests for kanji_break_penalty function."""
    
    def test_no_break(self):
        """Test no penalty without kanji break."""
        score = kanji_break_penalty([], 100)
        assert score == 100
    
    def test_with_break(self):
        """Test penalty applied with kanji break."""
        score = kanji_break_penalty([1], 100)
        # Score should be reduced
        assert score < 100
    
    def test_below_cutoff(self):
        """Test that scores below cutoff aren't modified."""
        score = kanji_break_penalty([1], 3)  # Below SCORE_CUTOFF
        assert score == 3
