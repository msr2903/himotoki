"""
Tests for output.py - WordInfo and JSON output formatting.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from himotoki.db.models import Base, Entry, KanjiText, KanaText, Sense, Gloss, SenseProp
from himotoki.output import (
    WordInfo, WordType,
    reading_str, get_entry_reading, word_info_reading_str,
    get_senses_raw, get_senses, get_senses_str, get_senses_json,
    get_conj_description, conj_prop_json,
    word_info_from_segment, word_info_from_segment_list, word_info_from_text,
    word_info_gloss_json,
    fill_segment_path,
)
from himotoki.lookup import Segment, SegmentList, WordMatch


@pytest.fixture
def session():
    """Create an in-memory database with test data."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Create test entries
    # Entry 1: 学校 (school)
    entry1 = Entry(seq=1206730, content="<entry/>", root_p=True, n_kanji=1, n_kana=1)
    session.add(entry1)
    
    kanji1 = KanjiText(seq=1206730, text="学校", ord=0, common=1)
    kana1 = KanaText(seq=1206730, text="がっこう", ord=0, common=1)
    session.add_all([kanji1, kana1])
    
    sense1 = Sense(seq=1206730, ord=0)
    session.add(sense1)
    session.flush()
    
    gloss1 = Gloss(sense_id=sense1.id, text="school", ord=0)
    pos1 = SenseProp(sense_id=sense1.id, tag="pos", text="n", ord=0, seq=1206730)
    session.add_all([gloss1, pos1])
    
    # Entry 2: 勉強 (study)
    entry2 = Entry(seq=1512670, content="<entry/>", root_p=True, n_kanji=1, n_kana=1)
    session.add(entry2)
    
    kanji2 = KanjiText(seq=1512670, text="勉強", ord=0, common=1)
    kana2 = KanaText(seq=1512670, text="べんきょう", ord=0, common=1)
    session.add_all([kanji2, kana2])
    
    sense2 = Sense(seq=1512670, ord=0)
    session.add(sense2)
    session.flush()
    
    gloss2a = Gloss(sense_id=sense2.id, text="study", ord=0)
    gloss2b = Gloss(sense_id=sense2.id, text="diligence", ord=1)
    pos2 = SenseProp(sense_id=sense2.id, tag="pos", text="n", ord=0, seq=1512670)
    pos2b = SenseProp(sense_id=sense2.id, tag="pos", text="vs", ord=1, seq=1512670)
    session.add_all([gloss2a, gloss2b, pos2, pos2b])
    
    # Entry 3: で (particle)
    entry3 = Entry(seq=2028980, content="<entry/>", root_p=True, n_kanji=0, n_kana=1)
    session.add(entry3)
    
    kana3 = KanaText(seq=2028980, text="で", ord=0, common=1)
    session.add(kana3)
    
    sense3 = Sense(seq=2028980, ord=0)
    session.add(sense3)
    session.flush()
    
    gloss3 = Gloss(sense_id=sense3.id, text="at; in", ord=0)
    pos3 = SenseProp(sense_id=sense3.id, tag="pos", text="prt", ord=0, seq=2028980)
    info3 = SenseProp(sense_id=sense3.id, tag="s_inf", text="indicates location", ord=0, seq=2028980)
    session.add_all([gloss3, pos3, info3])
    
    session.commit()
    yield session
    session.close()


# ============================================================================
# WordInfo Tests
# ============================================================================

class TestWordInfo:
    """Tests for WordInfo dataclass."""
    
    def test_basic_creation(self):
        """Test basic WordInfo creation."""
        wi = WordInfo(
            type=WordType.KANJI,
            text="学校",
            kana="がっこう",
            seq=1206730,
            score=100,
        )
        assert wi.type == WordType.KANJI
        assert wi.text == "学校"
        assert wi.kana == "がっこう"
        assert wi.seq == 1206730
        assert wi.score == 100
    
    def test_gap_type(self):
        """Test gap WordInfo."""
        wi = WordInfo(
            type=WordType.GAP,
            text="...",
            kana="...",
        )
        assert wi.type == WordType.GAP
    
    def test_to_dict(self):
        """Test conversion to dict."""
        wi = WordInfo(
            type=WordType.KANA,
            text="する",
            kana="する",
            seq=1157170,
            score=50,
        )
        d = wi.to_dict()
        assert d['type'] == 'KANA'
        assert d['text'] == "する"
        assert d['kana'] == "する"
        assert d['score'] == 50
    
    def test_alternative(self):
        """Test alternative WordInfo with components."""
        wi1 = WordInfo(type=WordType.KANA, text="する", kana="する", seq=1)
        wi2 = WordInfo(type=WordType.KANA, text="する", kana="する", seq=2)
        
        wi = WordInfo(
            type=WordType.KANA,
            text="する",
            kana=["する"],
            seq=[1, 2],
            alternative=True,
            components=[wi1, wi2],
        )
        assert wi.alternative
        assert len(wi.components) == 2


# ============================================================================
# Reading Formatting Tests
# ============================================================================

class TestReadingStr:
    """Tests for reading string formatting."""
    
    def test_kanji_kana_reading(self):
        """Test reading with kanji and kana."""
        result = reading_str("学校", "がっこう")
        assert result == "学校 【がっこう】"
    
    def test_kana_only_reading(self):
        """Test reading without kanji."""
        result = reading_str(None, "する")
        assert result == "する"
    
    def test_empty_kana(self):
        """Test with empty kana."""
        result = reading_str("学校", "")
        assert result == "学校 【】"


class TestGetEntryReading:
    """Tests for get_entry_reading."""
    
    def test_kanji_entry(self, session):
        """Test getting reading for kanji entry."""
        result = get_entry_reading(session, 1206730)
        assert "学校" in result
        assert "がっこう" in result
    
    def test_kana_only_entry(self, session):
        """Test getting reading for kana-only entry."""
        result = get_entry_reading(session, 2028980)
        assert result == "で"


class TestWordInfoReadingStr:
    """Tests for word_info_reading_str."""
    
    def test_kanji_word_info(self):
        """Test reading for kanji WordInfo."""
        wi = WordInfo(type=WordType.KANJI, text="学校", kana="がっこう")
        result = word_info_reading_str(wi)
        assert "学校" in result
        assert "がっこう" in result
    
    def test_kana_word_info(self):
        """Test reading for kana WordInfo."""
        wi = WordInfo(type=WordType.KANA, text="する", kana="する")
        result = word_info_reading_str(wi)
        assert result == "する"


# ============================================================================
# Sense/Gloss Tests
# ============================================================================

class TestGetSensesRaw:
    """Tests for get_senses_raw."""
    
    def test_basic_entry(self, session):
        """Test getting raw senses for basic entry."""
        result = get_senses_raw(session, 1206730)
        assert len(result) == 1
        assert result[0]['gloss'] == "school"
        assert 'pos' in result[0]['props']
    
    def test_multiple_glosses(self, session):
        """Test entry with multiple glosses."""
        result = get_senses_raw(session, 1512670)
        assert len(result) == 1
        # Glosses should be joined with '; '
        assert "study" in result[0]['gloss']
        assert "diligence" in result[0]['gloss']


class TestGetSenses:
    """Tests for get_senses."""
    
    def test_basic_senses(self, session):
        """Test getting formatted senses."""
        result = get_senses(session, 1206730)
        assert len(result) == 1
        assert result[0]['pos'] == '[n]'
        assert result[0]['gloss'] == 'school'


class TestGetSensesStr:
    """Tests for get_senses_str."""
    
    def test_formatted_output(self, session):
        """Test formatted sense string."""
        result = get_senses_str(session, 1206730)
        assert "1. [n]" in result
        assert "school" in result


class TestGetSensesJson:
    """Tests for get_senses_json."""
    
    def test_json_output(self, session):
        """Test JSON sense output."""
        result = get_senses_json(session, 1206730)
        assert len(result) == 1
        assert result[0]['pos'] == '[n]'
        assert result[0]['gloss'] == 'school'
    
    def test_with_info(self, session):
        """Test JSON with sense info."""
        result = get_senses_json(session, 2028980)
        assert len(result) == 1
        assert 'info' in result[0]
        assert 'location' in result[0]['info']


# ============================================================================
# Conjugation Info Tests
# ============================================================================

class TestGetConjDescription:
    """Tests for get_conj_description."""
    
    def test_known_types(self):
        """Test known conjugation types."""
        assert get_conj_description(1) == 'Non-past'
        assert get_conj_description(2) == 'Past (~ta)'
        assert get_conj_description(3) == 'Conjunctive (~te)'
    
    def test_unknown_type(self):
        """Test unknown conjugation type."""
        assert get_conj_description(99) == 'Type 99'


# ============================================================================
# WordInfo Creation Tests
# ============================================================================

class TestWordInfoFromSegment:
    """Tests for word_info_from_segment."""
    
    def test_kanji_segment(self, session):
        """Test creating WordInfo from kanji segment."""
        kanji = session.query(KanjiText).filter_by(seq=1206730).first()
        word_match = WordMatch(reading=kanji)
        segment = Segment(start=0, end=2, word=word_match, score=100)
        
        wi = word_info_from_segment(session, segment)
        assert wi.type == WordType.KANJI
        assert wi.text == "学校"
        assert wi.seq == 1206730
        assert wi.score == 100
        assert wi.start == 0
        assert wi.end == 2
    
    def test_kana_segment(self, session):
        """Test creating WordInfo from kana segment."""
        kana = session.query(KanaText).filter_by(seq=2028980).first()
        word_match = WordMatch(reading=kana)
        segment = Segment(start=2, end=3, word=word_match, score=50)
        
        wi = word_info_from_segment(session, segment)
        assert wi.type == WordType.KANA
        assert wi.text == "で"
        assert wi.seq == 2028980


class TestWordInfoFromSegmentList:
    """Tests for word_info_from_segment_list."""
    
    def test_single_segment(self, session):
        """Test creating WordInfo from single-segment list."""
        kanji = session.query(KanjiText).filter_by(seq=1206730).first()
        word_match = WordMatch(reading=kanji)
        segment = Segment(start=0, end=2, word=word_match, score=100)
        segment_list = SegmentList(segments=[segment], start=0, end=2, matches=1)
        
        wi = word_info_from_segment_list(session, segment_list)
        assert wi.type == WordType.KANJI
        assert wi.text == "学校"
        assert not wi.alternative
    
    def test_empty_segment_list(self, session):
        """Test creating WordInfo from empty segment list."""
        segment_list = SegmentList(segments=[], start=0, end=3, matches=0)
        
        wi = word_info_from_segment_list(session, segment_list)
        assert wi.type == WordType.GAP


class TestWordInfoGlossJson:
    """Tests for word_info_gloss_json."""
    
    def test_basic_output(self, session):
        """Test basic JSON output."""
        wi = WordInfo(
            type=WordType.KANJI,
            text="学校",
            kana="がっこう",
            seq=1206730,
            score=100,
        )
        
        result = word_info_gloss_json(session, wi)
        assert 'reading' in result
        assert 'text' in result
        assert 'kana' in result
        assert result['text'] == '学校'
        assert result['score'] == 100
        assert 'gloss' in result
        assert len(result['gloss']) > 0
    
    def test_gap_output(self, session):
        """Test JSON output for gap."""
        wi = WordInfo(
            type=WordType.GAP,
            text="...",
            kana="...",
        )
        
        result = word_info_gloss_json(session, wi)
        assert result['text'] == '...'


# ============================================================================
# Segment Path Tests
# ============================================================================

class TestFillSegmentPath:
    """Tests for fill_segment_path."""
    
    def test_empty_path(self, session):
        """Test filling empty path."""
        result = fill_segment_path(session, "テスト", [])
        assert len(result) == 1
        assert result[0].type == WordType.GAP
        assert result[0].text == "テスト"
    
    def test_partial_coverage(self, session):
        """Test path that doesn't cover entire text."""
        kanji = session.query(KanjiText).filter_by(seq=1206730).first()
        word_match = WordMatch(reading=kanji)
        segment = Segment(start=0, end=2, word=word_match, score=100)
        segment_list = SegmentList(segments=[segment], start=0, end=2, matches=1)
        
        text = "学校で"
        result = fill_segment_path(session, text, [segment_list])
        
        # Should have the word and a trailing gap
        assert len(result) == 2
        assert result[0].type == WordType.KANJI
        assert result[1].type == WordType.GAP
        assert result[1].text == "で"
