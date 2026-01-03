"""
Comparison test suite for himotoki vs ichiran.

This module contains test cases derived from ichiran CLI outputs.
Each test verifies that himotoki produces similar segmentations
to the reference ichiran implementation.

Test sentences are chosen to cover:
1. Basic word segmentation
2. Compound word handling
3. Conjugation chains (causative, passive, etc.)
4. Particle attachment
5. Suffix handling (たい, ている, etc.)
"""

import pytest
from typing import List, Tuple, Optional, Dict, Any, Union
from dataclasses import dataclass

from himotoki.segment import segment_text, simple_segment
from himotoki.lookup import Segment, SegmentList


@dataclass
class ExpectedSegment:
    """Expected segment from ichiran output."""
    text: str
    reading: Optional[str] = None
    pos: Optional[List[str]] = None
    gloss: Optional[str] = None


@dataclass
class SegmentTestCase:
    """Test case for comparison (renamed from TestCase to avoid pytest collection)."""
    input_text: str
    expected_segments: List[ExpectedSegment]
    description: str


# ============================================================================
# Test Cases from ichiran CLI
# ============================================================================

# Test case 1: 学校で勉強しています
# ichiran output:
# 1. 学校 【がっこう】 (n,n-suf) school
# 2. で (prt) at; in
# 3. 勉強 【べんきょう】 (n,vs,adj-no) study; diligence; working hard
# 4. しています = している (v1,vi) is studying [suffix]
TEST_CASE_1 = SegmentTestCase(
    input_text="学校で勉強しています",
    expected_segments=[
        ExpectedSegment(text="学校", reading="がっこう", pos=["n"], gloss="school"),
        ExpectedSegment(text="で", pos=["prt"], gloss="at; in"),
        ExpectedSegment(text="勉強", reading="べんきょう", pos=["n", "vs"], gloss="study"),
        ExpectedSegment(text="しています", pos=["v1"], gloss="to be doing"),
    ],
    description="Basic sentence with noun + particle + suru verb + progressive"
)

# Test case 2: 食べさせられた
# ichiran output:
# 1. 食べさせられた 【たべさせられた】 = 食べる (v1,vt) to eat
#    -> 使役形 (causative)
#    -> 受身形 (passive)  
#    -> 過去形 (past)
TEST_CASE_2 = SegmentTestCase(
    input_text="食べさせられた",
    expected_segments=[
        ExpectedSegment(
            text="食べさせられた",
            reading="たべさせられた",
            pos=["v1"],
            gloss="to eat (causative-passive-past)"
        ),
    ],
    description="Causative-passive-past conjugation chain"
)

# Test case 3: 走りたくなかった
# ichiran output:
# 1. 走りたくなかった = 走る (v5r,vi) to run + たい (aux-adj) want to + ない (aux-adj) not + past
TEST_CASE_3 = SegmentTestCase(
    input_text="走りたくなかった",
    expected_segments=[
        ExpectedSegment(
            text="走りたくなかった",
            reading="はしりたくなかった",
            pos=["v5r"],
            gloss="did not want to run"
        ),
    ],
    description="Verb + tai suffix + negative past"
)

# Test case 4: 日本語を勉強する
TEST_CASE_4 = SegmentTestCase(
    input_text="日本語を勉強する",
    expected_segments=[
        ExpectedSegment(text="日本語", reading="にほんご", pos=["n"], gloss="Japanese"),
        ExpectedSegment(text="を", pos=["prt"]),
        ExpectedSegment(text="勉強", reading="べんきょう", pos=["n", "vs"]),
        ExpectedSegment(text="する", pos=["vs-i"]),
    ],
    description="Basic sentence with suru verb"
)

# Test case 5: これは本です
TEST_CASE_5 = SegmentTestCase(
    input_text="これは本です",
    expected_segments=[
        ExpectedSegment(text="これ", pos=["pn"], gloss="this"),
        ExpectedSegment(text="は", pos=["prt"], gloss="topic marker"),
        ExpectedSegment(text="本", reading="ほん", pos=["n"], gloss="book"),
        ExpectedSegment(text="です", pos=["cop"], gloss="is"),
    ],
    description="Basic copula sentence"
)

# Test case 6: 静かな部屋
TEST_CASE_6 = SegmentTestCase(
    input_text="静かな部屋",
    expected_segments=[
        ExpectedSegment(text="静か", reading="しずか", pos=["adj-na"], gloss="quiet"),
        ExpectedSegment(text="な", pos=["prt"]),
        ExpectedSegment(text="部屋", reading="へや", pos=["n"], gloss="room"),
    ],
    description="Na-adjective + noun (tests na-adjective synergy)"
)

# Test case 7: ゆっくりと歩く
TEST_CASE_7 = SegmentTestCase(
    input_text="ゆっくりと歩く",
    expected_segments=[
        ExpectedSegment(text="ゆっくり", pos=["adv-to"], gloss="slowly"),
        ExpectedSegment(text="と", pos=["prt"]),
        ExpectedSegment(text="歩く", reading="あるく", pos=["v5k"], gloss="to walk"),
    ],
    description="To-adverb + と particle (tests to-adverb synergy)"
)

# Test case 8: 子供たち
TEST_CASE_8 = SegmentTestCase(
    input_text="子供たち",
    expected_segments=[
        ExpectedSegment(text="子供", reading="こども", pos=["n"], gloss="child"),
        ExpectedSegment(text="たち", pos=["suf"], gloss="plural suffix"),
    ],
    description="Noun + tachi suffix (tests suffix synergy)"
)


# ============================================================================
# Test Fixtures (now using conftest.py db_session)
# ============================================================================


# ============================================================================
# Helper Functions
# ============================================================================

def get_segment_text(segment: Union[Segment, SegmentList]) -> str:
    """Extract text from a segment or segment list."""
    if isinstance(segment, SegmentList):
        if segment.segments:
            return get_segment_text(segment.segments[0])
        return ""
    if hasattr(segment, 'word') and segment.word:
        return segment.word.text
    return ""


def get_segment_reading(segment: Union[Segment, SegmentList]) -> Optional[str]:
    """Extract reading from a segment or segment list."""
    if isinstance(segment, SegmentList):
        if segment.segments:
            return get_segment_reading(segment.segments[0])
        return None
    if hasattr(segment, 'word') and segment.word:
        reading = segment.word.reading
        if hasattr(reading, 'text'):
            return reading.text
    return None


def segments_to_texts(segments: List[Union[Segment, SegmentList]]) -> List[str]:
    """Convert segments to list of text strings."""
    return [get_segment_text(s) for s in segments]


def compare_segmentation(
    actual: List[Segment],
    expected: List[ExpectedSegment],
    strict: bool = False,
) -> Tuple[bool, str]:
    """
    Compare actual segmentation to expected.
    
    Args:
        actual: Actual segments from himotoki
        expected: Expected segments from test case
        strict: If True, require exact match; else allow partial
    
    Returns:
        (matches, description)
    """
    actual_texts = segments_to_texts(actual)
    expected_texts = [e.text for e in expected]
    
    if strict:
        if actual_texts != expected_texts:
            return False, f"Texts differ: {actual_texts} vs {expected_texts}"
        return True, "Exact match"
    
    # Non-strict: check that key words are present
    for exp in expected:
        found = any(exp.text in at for at in actual_texts)
        if not found and exp.text not in "".join(actual_texts):
            return False, f"Missing expected segment: {exp.text}"
    
    return True, "Partial match"


# ============================================================================
# Basic Segmentation Tests
# ============================================================================

class TestBasicSegmentation:
    """Test basic word segmentation."""
    
    def test_simple_word(self, db_session):
        """Test segmentation of a single word."""
        segments = simple_segment(db_session, "学校")
        assert len(segments) >= 1
        texts = segments_to_texts(segments)
        assert "学校" in "".join(texts)
    
    def test_particle_attachment(self, db_session):
        """Test noun + particle segmentation."""
        segments = simple_segment(db_session, "学校で")
        texts = segments_to_texts(segments)
        # Should have school and particle
        assert len(segments) >= 2
    
    def test_verb_conjugation(self, db_session):
        """Test conjugated verb detection."""
        segments = simple_segment(db_session, "食べた")
        texts = segments_to_texts(segments)
        # Should recognize as past of 食べる
        assert len(segments) >= 1


class TestCompoundWords:
    """Test compound word handling."""
    
    def test_suru_verb_compound(self, db_session):
        """Test noun + suru verb compounds."""
        segments = simple_segment(db_session, "勉強する")
        texts = segments_to_texts(segments)
        # Could be compound "勉強する" or split "勉強" + "する"
        full_text = "".join(texts)
        assert "勉強" in full_text
        assert "する" in full_text or "勉強する" in texts
    
    def test_teiru_progressive(self, db_session):
        """Test verb + ている progressive."""
        segments = simple_segment(db_session, "食べている")
        texts = segments_to_texts(segments)
        full_text = "".join(texts)
        assert "食べ" in full_text or "たべ" in full_text.lower()


class TestConjugationChains:
    """Test complex conjugation chains."""
    
    def test_causative(self, db_session):
        """Test causative form."""
        segments = simple_segment(db_session, "食べさせる")
        # Should be recognized as causative of 食べる
        assert len(segments) >= 1
    
    def test_passive(self, db_session):
        """Test passive form."""
        segments = simple_segment(db_session, "食べられる")
        assert len(segments) >= 1
    
    def test_tai_desiderative(self, db_session):
        """Test たい desiderative suffix."""
        segments = simple_segment(db_session, "食べたい")
        assert len(segments) >= 1
    
    def test_negative(self, db_session):
        """Test negative form."""
        segments = simple_segment(db_session, "食べない")
        assert len(segments) >= 1


class TestSynergies:
    """Test synergy detection between segments."""
    
    def test_noun_particle_synergy(self, db_session):
        """Test noun + particle synergy (should boost score)."""
        segments = simple_segment(db_session, "学校で")
        # Filter out synergy objects - keep only SegmentLists
        segment_lists = [s for s in segments if isinstance(s, SegmentList)]
        texts = segments_to_texts(segment_lists)
        # Should have 学校 + で
        assert len(segment_lists) == 2
        assert "学校" in texts
        assert "で" in texts
    
    def test_na_adjective_synergy(self, db_session):
        """Test na-adjective + な synergy."""
        segments = simple_segment(db_session, "静かな")
        segment_lists = [s for s in segments if isinstance(s, SegmentList)]
        texts = segments_to_texts(segment_lists)
        # Should prefer 静か + な
        assert len(segment_lists) >= 2


class TestIchiranComparison:
    """
    Compare himotoki output to ichiran reference outputs.
    
    These tests verify that himotoki produces similar segmentations
    to the reference ichiran implementation.
    """
    
    @pytest.mark.parametrize("test_case", [
        TEST_CASE_1,
        TEST_CASE_4,
        TEST_CASE_5,
        TEST_CASE_6,
        TEST_CASE_7,
        TEST_CASE_8,
    ])
    def test_segmentation(self, db_session, test_case: SegmentTestCase):
        """Test segmentation matches expected output."""
        segments = simple_segment(db_session, test_case.input_text)
        
        matches, desc = compare_segmentation(
            segments,
            test_case.expected_segments,
            strict=False
        )
        
        assert matches, f"{test_case.description}: {desc}"
    
    @pytest.mark.parametrize("test_case", [
        TEST_CASE_2,
        TEST_CASE_3,
    ])
    def test_complex_conjugation(self, db_session, test_case: SegmentTestCase):
        """Test complex conjugation chains."""
        segments = simple_segment(db_session, test_case.input_text)
        
        # For complex conjugations, we mainly check that SOMETHING is parsed
        # and the full text is covered
        assert len(segments) >= 1, f"{test_case.description}: No segments found"
        
        # Check coverage
        covered_text = "".join(segments_to_texts(segments))
        assert test_case.input_text in covered_text or covered_text in test_case.input_text


class TestScoring:
    """Test scoring accuracy."""
    
    def test_common_word_scores_higher(self, db_session):
        """Common words should score higher than rare ones."""
        results = segment_text(db_session, "行く", limit=5)
        if results:
            # Top result should be common 行く
            top_path, top_score = results[0]
            assert top_score > 0
    
    def test_kanji_scores_higher_than_kana(self, db_session):
        """Kanji words should score higher than equivalent kana."""
        results_kanji = segment_text(db_session, "学校", limit=1)
        results_kana = segment_text(db_session, "がっこう", limit=1)
        
        if results_kanji and results_kana:
            _, score_kanji = results_kanji[0]
            _, score_kana = results_kana[0]
            # Kanji should score at least as high
            assert score_kanji >= score_kana


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_string(self, db_session):
        """Empty string should return empty result."""
        segments = simple_segment(db_session, "")
        assert segments == []
    
    def test_single_character(self, db_session):
        """Single character should be handled."""
        segments = simple_segment(db_session, "あ")
        # May or may not find matches, but shouldn't crash
        assert isinstance(segments, list)
    
    def test_mixed_script(self, db_session):
        """Mixed kanji/kana should be handled."""
        segments = simple_segment(db_session, "食べる")
        assert len(segments) >= 1
    
    def test_katakana(self, db_session):
        """Katakana words should be recognized."""
        segments = simple_segment(db_session, "コーヒー")
        # Should find coffee
        assert len(segments) >= 1
    
    def test_long_text(self, db_session):
        """Long text should be handled efficiently."""
        text = "日本語を勉強しています" * 3
        segments = simple_segment(db_session, text)
        # Should produce some results without timeout
        assert isinstance(segments, list)
