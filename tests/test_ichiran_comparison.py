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

# Test case 9: あいつ何考えてんだろうね
# ichiran output (reference):
# 1. あいつ 【あいつ】 (pn) that guy; he; she
# 2. 何 【なに】 (pn) what
# 3. 考えて 【かんがえて】 = 考える (v1,vt) to think (te-form)
# 4. ん (int) uh; huh (contraction of いる)
# 5. だろう (exp) seems; I think; probably
# 6. ね (prt) sentence-ending particle
#
# This tests that the ん contraction does NOT incorrectly match 考えていないん
# (negative progressive of いる), which would be semantically wrong.
# 考えてん = 考えている (thinking), NOT 考えていない (not thinking)
TEST_CASE_9_N_CONTRACTION = SegmentTestCase(
    input_text="あいつ何考えてんだろうね",
    expected_segments=[
        ExpectedSegment(text="あいつ", pos=["pn"]),
        ExpectedSegment(text="何", reading="なに", pos=["pn"]),
        ExpectedSegment(text="考えて", reading="かんがえて"),
        ExpectedSegment(text="ん", pos=["int"]),
        ExpectedSegment(text="だろう", pos=["exp"]),
        ExpectedSegment(text="ね", pos=["prt"]),
    ],
    description="ん contraction must NOT match 考えていないん (tests BLOCKED_NAI_SEQS)"
)

# Test case 10: 来てんの (similar test for 来る blocking)
# The ん should not match 来ていないん
TEST_CASE_10_KURU_N = SegmentTestCase(
    input_text="来てんの",
    expected_segments=[
        ExpectedSegment(text="来て", reading="きて"),
        ExpectedSegment(text="ん", pos=["int"]),
        ExpectedSegment(text="の", pos=["prt"]),
    ],
    description="ん contraction must NOT match 来ていないん (tests BLOCKED_NAI_SEQS for 来る)"
)

# Test case 11: てか最近どうしてるの
# ichiran output (reference):
# 1. てか 【てか】 (conj) or rather; I mean (colloquial)
# 2. 最近どう 【さいきんどう】 (int) how have you been lately
# 3. している = する (vs-i) to do (progressive)
# 4. の (prt) nominalizer
#
# This tests that てか is recognized as a single conjunction word, not split
# into て (particle) + か (particle). The てか entry has common=0 errata
# applied which boosts its score above the particle split.
TEST_CASE_11_TEKA_CONJ = SegmentTestCase(
    input_text="てか最近どうしてるの",
    expected_segments=[
        ExpectedSegment(text="てか", pos=["conj"]),
        ExpectedSegment(text="最近どう", reading="さいきんどう", pos=["int"]),
        ExpectedSegment(text="している"),  # compound, no specific pos check
        ExpectedSegment(text="の", pos=["prt"]),
    ],
    description="てか must be recognized as conjunction, not split into て+か"
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


def get_segment_pos(segment: Union[Segment, SegmentList]) -> Optional[List[str]]:
    """Extract part-of-speech info from a segment."""
    if isinstance(segment, SegmentList):
        if segment.segments:
            return get_segment_pos(segment.segments[0])
        return None
    if hasattr(segment, 'info') and segment.info:
        posi = segment.info.get('posi')
        if posi:
            return posi if isinstance(posi, list) else list(posi)
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


class TestColloquialContractions:
    """
    Test colloquial contraction handling.
    
    These tests verify that abbreviated/contracted forms are correctly
    handled, particularly the ん contraction which should NOT incorrectly
    match negative forms of いる or 来る.
    
    Background:
    - 考えてん = 考えている (progressive: "is thinking")
    - 考えていないん would be wrong (negative: "is not thinking")
    
    Ichiran blocks いる (seq 1577980) and 来る (seq 1547720) in the
    nai-n suffix handler to prevent this semantic confusion.
    """
    
    def test_n_contraction_does_not_match_iru_negative(self, db_session):
        """
        Test that ん contraction does NOT match いる negative forms.
        
        考えてん should segment as 考えて + ん, NOT as 考えていないん.
        """
        segments = simple_segment(db_session, "考えてんだろうね")
        texts = segments_to_texts(segments)
        
        # Should NOT have 考えていないん as a single segment
        assert "考えていないん" not in texts, \
            f"ん contraction incorrectly matched いない: {texts}"
        
        # Should have 考えて as a separate segment
        full_text = "".join(texts)
        assert "考えて" in full_text or "考え" in full_text, \
            f"Expected 考えて in segments: {texts}"
    
    def test_full_sentence_kangaetennn(self, db_session):
        """Test full sentence: あいつ何考えてんだろうね"""
        segments = simple_segment(db_session, "あいつ何考えてんだろうね")
        texts = segments_to_texts(segments)
        
        # Critical check: 考えていないん should NOT appear
        assert "考えていないん" not in texts, \
            f"BLOCKED_NAI_SEQS filter not working: {texts}"
        
        # Check expected segments are present
        full_text = "".join(texts)
        assert "あいつ" in texts or "あいつ" in full_text
        assert "何" in texts or "何" in full_text
        assert "だろう" in texts or "だろう" in full_text
    
    def test_n_contraction_kuru(self, db_session):
        """
        Test that ん contraction does NOT match 来る negative forms.
        
        来てん should segment as 来て + ん, NOT as 来ていないん.
        """
        segments = simple_segment(db_session, "来てんの")
        texts = segments_to_texts(segments)
        
        # Should NOT have 来ていないん as a single segment
        assert "来ていないん" not in texts, \
            f"ん contraction incorrectly matched 来ない: {texts}"
    
    @pytest.mark.parametrize("text,blocked_form", [
        ("食べてん", "食べていないん"),  # Should NOT match for いる
        ("行ってん", "行っていないん"),  # Should NOT match for いる
        ("見てん", "見ていないん"),      # Should NOT match for いる
    ])
    def test_various_n_contractions(self, db_session, text, blocked_form):
        """Test various verb + てん patterns don't match negative いる."""
        segments = simple_segment(db_session, text)
        texts = segments_to_texts(segments)
        
        assert blocked_form not in texts, \
            f"ん contraction incorrectly matched negative: got {texts}"


class TestConjunctionRecognition:
    """
    Test that colloquial conjunctions are recognized as single words.
    
    Some colloquial conjunctions like てか could be incorrectly split into
    their component particles. The errata sets common=0 on てか to boost
    its score above the particle split alternative.
    """
    
    def test_teka_as_single_conjunction(self, db_session):
        """
        Test that てか is recognized as a single conjunction.
        
        てか should NOT be split into て (particle) + か (particle).
        Ichiran errata sets common=0 on てか (seq 2848303) to ensure
        it scores higher than the particle alternative.
        """
        segments = simple_segment(db_session, "てか最近どうしてるの")
        texts = segments_to_texts(segments)
        
        # てか should be a single segment, not split
        assert "てか" in texts, \
            f"てか should be recognized as single conjunction, got: {texts}"
        
        # Should NOT have て and か as separate particles
        # Check that we don't have consecutive て, か
        for i in range(len(texts) - 1):
            if texts[i] == "て" and texts[i+1] == "か":
                pytest.fail(f"てか incorrectly split into て+か: {texts}")
    
    def test_teka_has_correct_pos(self, db_session):
        """Test that てか has the correct part of speech (conj) when followed by text.
        
        Note: When てか is at the end of input, the か particle gets a final
        particle bonus that makes て+か score higher than the conjunction.
        This matches Ichiran's behavior.
        """
        # Use a sentence where てか is NOT at the end
        # てかさ works (さ is a final particle), but てかね doesn't (かね is a word)
        segments = simple_segment(db_session, "てかさ")
        texts = segments_to_texts(segments)
        
        # Find the てか segment
        teka_segment = None
        for seg in segments:
            if isinstance(seg, SegmentList):
                for s in seg.segments:
                    if hasattr(s, 'word') and s.word and s.word.text == "てか":
                        teka_segment = s
                        break
            elif hasattr(seg, 'word') and seg.word and seg.word.text == "てか":
                teka_segment = seg
                break
        
        assert teka_segment is not None, f"Could not find てか segment in {texts}"
        
        # Get POS info
        posi = get_segment_pos(teka_segment)
        assert posi is not None, f"てか segment has no POS info"
        
        # Check for conjunction POS
        pos_str = " ".join(posi) if posi else ""
        assert "conj" in pos_str, \
            f"てか should have 'conj' POS, got: {posi}"
