#!/usr/bin/env python3
"""
Ichiran vs Himotoki Comparison Test Suite

Compares segmentation results between Ichiran (Docker CLI) and Himotoki
to identify discrepancies and areas for improvement.

Usage:
    python compare_ichiran.py                    # Run all tests
    python compare_ichiran.py --quick            # Run quick subset
    python compare_ichiran.py --sentence "猫が食べる"  # Test single sentence
    python compare_ichiran.py --export results.json   # Export results
"""

import subprocess
import json
import sys
import argparse
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
import time


# ============================================================================
# Configuration
# ============================================================================

ICHIRAN_CONTAINER = "ichiran-main-1"
ICHIRAN_TIMEOUT = 30  # seconds


# ============================================================================
# Data Classes
# ============================================================================

class MatchStatus(Enum):
    MATCH = "match"              # Exact match
    PARTIAL = "partial"          # Same segmentation, different details
    MISMATCH = "mismatch"        # Different segmentation
    ICHIRAN_ERROR = "ichiran_error"  # Ichiran failed
    HIMOTOKI_ERROR = "himotoki_error"  # Himotoki failed


@dataclass
class SegmentInfo:
    """Information about a single segment."""
    text: str
    kana: str = ""
    seq: Optional[int] = None
    score: int = 0
    is_compound: bool = False
    components: List[str] = field(default_factory=list)
    conj_type: Optional[str] = None
    conj_neg: bool = False  # Negative form
    conj_fml: bool = False  # Polite form
    source_text: Optional[str] = None  # Dictionary form for conjugated words
    pos: List[str] = field(default_factory=list)


@dataclass
class SegmentationResult:
    """Result from either Ichiran or Himotoki."""
    segments: List[SegmentInfo]
    total_score: int = 0
    raw_output: Any = None
    error: Optional[str] = None


@dataclass
class ComparisonResult:
    """Comparison between Ichiran and Himotoki for a sentence."""
    sentence: str
    status: MatchStatus
    ichiran: Optional[SegmentationResult]
    himotoki: Optional[SegmentationResult]
    ichiran_texts: List[str] = field(default_factory=list)
    himotoki_texts: List[str] = field(default_factory=list)
    differences: List[str] = field(default_factory=list)
    time_ichiran: float = 0.0
    time_himotoki: float = 0.0


# ============================================================================
# Ichiran Interface
# ============================================================================

def run_ichiran(sentence: str) -> SegmentationResult:
    """
    Run Ichiran CLI and parse the JSON output.
    
    Args:
        sentence: Japanese text to segment.
        
    Returns:
        SegmentationResult with parsed segments.
    """
    try:
        cmd = [
            "docker", "exec", "-i", ICHIRAN_CONTAINER,
            "ichiran-cli", "-f", sentence
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=ICHIRAN_TIMEOUT
        )
        
        if result.returncode != 0:
            return SegmentationResult(
                segments=[],
                error=f"Ichiran returned code {result.returncode}: {result.stderr}"
            )
        
        # Parse JSON output
        data = json.loads(result.stdout)
        return parse_ichiran_output(data)
        
    except subprocess.TimeoutExpired:
        return SegmentationResult(segments=[], error="Timeout")
    except json.JSONDecodeError as e:
        return SegmentationResult(segments=[], error=f"JSON parse error: {e}")
    except Exception as e:
        return SegmentationResult(segments=[], error=str(e))


def parse_ichiran_output(data: Any) -> SegmentationResult:
    """
    Parse Ichiran's JSON output into SegmentationResult.
    
    Ichiran output structure:
    [[[[segment1, segment2, ...], score]]]
    
    Where each segment is:
    ["romanization", {info_dict}, [alternatives]]
    """
    try:
        # Navigate to the first (best) segmentation
        # Structure: [[[segments_with_score]]]
        if not data or not data[0] or not data[0][0]:
            return SegmentationResult(segments=[], error="Empty result")
        
        best_result = data[0][0]  # [[segments], score]
        if not best_result:
            return SegmentationResult(segments=[], error="No segmentation")
        
        segments_data = best_result[0]  # List of segments
        total_score = best_result[1] if len(best_result) > 1 else 0
        
        def extract_conj_info(word_info: dict) -> Tuple[Optional[str], bool, bool, Optional[str]]:
            """Extract conjugation type, neg, fml, and source text from word info."""
            conj_type = None
            neg = False
            fml = False
            source = None
            
            if word_info.get("conj"):
                conj = word_info["conj"][0]
                prop = conj.get("prop", [])
                if prop:
                    conj_type = prop[0].get("type")
                    neg = prop[0].get("neg", False)
                    fml = prop[0].get("fml", False)
                # Extract source (dictionary form) from reading
                reading = conj.get("reading", "")
                if reading:
                    # Format: "書く 【かく】" - extract the first part
                    source = reading.split(" ")[0] if " " in reading else reading
            
            return conj_type, neg, fml, source
        
        segments = []
        for seg in segments_data:
            # seg = ["romanization", {info}, [alternatives]]
            if len(seg) < 2:
                continue
                
            romaji = seg[0]
            info = seg[1]
            
            # Handle compound words (like 食べています)
            if "compound" in info:
                # Compound word - treat as single segment with the full text
                component_texts = info.get("compound", [])
                components_info = info.get("components", [])
                
                # Join component texts to get the full compound text
                full_text = "".join(component_texts)
                
                # Get conjugation info from the last component
                conj_type = None
                neg = False
                fml = False
                source = None
                if components_info:
                    last_comp = components_info[-1] if components_info else {}
                    conj_type, neg, fml, source = extract_conj_info(last_comp)
                
                # Get kana by joining component kanas
                kana_parts = [c.get("kana", "") for c in components_info]
                full_kana = "".join(kana_parts)
                
                seg_info = SegmentInfo(
                    text=full_text,
                    kana=full_kana,
                    seq=components_info[0].get("seq") if components_info else None,
                    score=info.get("score", 0),
                    is_compound=True,
                    components=component_texts,
                    conj_type=conj_type,
                    conj_neg=neg,
                    conj_fml=fml,
                    source_text=source,
                )
                segments.append(seg_info)
            else:
                # Regular word - check for 'alternative' field (multiple readings)
                # Use the first alternative or the main info
                word_info = info
                if "alternative" in info and info["alternative"]:
                    word_info = info["alternative"][0]
                
                conj_type, neg, fml, source = extract_conj_info(word_info)
                
                pos_list = []
                for gloss in word_info.get("gloss", []):
                    if "pos" in gloss:
                        pos_list.append(gloss["pos"])
                
                seg_info = SegmentInfo(
                    text=word_info.get("text", ""),
                    kana=word_info.get("kana", ""),
                    seq=word_info.get("seq"),
                    score=word_info.get("score", 0),
                    conj_type=conj_type,
                    conj_neg=neg,
                    conj_fml=fml,
                    source_text=source,
                    pos=pos_list[:3],  # Limit to first 3
                )
                segments.append(seg_info)
        
        return SegmentationResult(
            segments=segments,
            total_score=total_score,
            raw_output=data
        )
        
    except Exception as e:
        return SegmentationResult(segments=[], error=f"Parse error: {e}")


# ============================================================================
# Himotoki Interface
# ============================================================================

def run_himotoki(sentence: str) -> SegmentationResult:
    """
    Run Himotoki segmentation.
    
    Args:
        sentence: Japanese text to segment.
        
    Returns:
        SegmentationResult with parsed segments.
    """
    try:
        from himotoki.dict import simple_segment
        
        result = simple_segment(sentence)
        
        segments = []
        for word in result:
            # Handle kana as string or list
            kana = word.kana
            if isinstance(kana, list):
                kana = kana[0] if kana else ""
            
            # Get conjugation info if available
            conj_type = None
            conj_neg = False
            conj_fml = False
            source_text = None
            
            if word.conjugations and isinstance(word.conjugations, list) and word.conjugations:
                conj_info = word.conjugations[0]
                if isinstance(conj_info, dict):
                    # New format: {'type': 'Past', 'conj_type': 2, 'neg': False, 'fml': False, ...}
                    conj_type = conj_info.get('type')
                    conj_neg = conj_info.get('neg', False)
                    conj_fml = conj_info.get('fml', False)
                    source_text = conj_info.get('source_text')
                else:
                    conj_type = str(conj_info)
            
            seg_info = SegmentInfo(
                text=word.text,
                kana=kana,
                seq=word.seq if isinstance(word.seq, int) else None,
                score=word.score,
                conj_type=conj_type,
                conj_neg=conj_neg,
                conj_fml=conj_fml,
                source_text=source_text,
            )
            segments.append(seg_info)
        
        total_score = sum(s.score for s in segments)
        
        return SegmentationResult(
            segments=segments,
            total_score=total_score,
        )
        
    except Exception as e:
        import traceback
        return SegmentationResult(
            segments=[],
            error=f"Himotoki error: {e}\n{traceback.format_exc()}"
        )


# ============================================================================
# Comparison Logic
# ============================================================================

def compare_segmentations(sentence: str) -> ComparisonResult:
    """
    Compare Ichiran and Himotoki segmentations for a sentence.
    """
    # Run Ichiran
    t0 = time.time()
    ichiran_result = run_ichiran(sentence)
    time_ichiran = time.time() - t0
    
    # Run Himotoki
    t0 = time.time()
    himotoki_result = run_himotoki(sentence)
    time_himotoki = time.time() - t0
    
    # Extract text lists
    ichiran_texts = [s.text for s in ichiran_result.segments]
    himotoki_texts = [s.text for s in himotoki_result.segments]
    
    # Determine status and differences
    differences = []
    
    if ichiran_result.error:
        status = MatchStatus.ICHIRAN_ERROR
        differences.append(f"Ichiran error: {ichiran_result.error}")
    elif himotoki_result.error:
        status = MatchStatus.HIMOTOKI_ERROR
        differences.append(f"Himotoki error: {himotoki_result.error}")
    elif ichiran_texts == himotoki_texts:
        # Same segmentation - check for conjugation/detail differences
        all_match = True
        for i, (iseg, hseg) in enumerate(zip(ichiran_result.segments, himotoki_result.segments)):
            seg_diffs = []
            
            # Check conjugation type (normalize: remove parenthetical hints like "(~ta)")
            i_type = iseg.conj_type
            h_type = hseg.conj_type
            if i_type and " (~" in i_type:
                i_type = i_type.split(" (~")[0]  # "Past (~ta)" -> "Past"
            if h_type and " (~" in h_type:
                h_type = h_type.split(" (~")[0]  # "Past (~ta)" -> "Past"
            if h_type and " Negative" in h_type:
                h_type = h_type.replace(" Negative", "")
            if h_type and " Polite" in h_type:
                h_type = h_type.replace(" Polite", "")
                
            if i_type != h_type:
                seg_diffs.append(f"conj_type: {iseg.conj_type} vs {hseg.conj_type}")
            
            # Check neg/fml flags
            if iseg.conj_neg != hseg.conj_neg:
                seg_diffs.append(f"neg: {iseg.conj_neg} vs {hseg.conj_neg}")
            if iseg.conj_fml != hseg.conj_fml:
                seg_diffs.append(f"fml: {iseg.conj_fml} vs {hseg.conj_fml}")
            
            # Check source text (dictionary form)
            if iseg.source_text and hseg.source_text:
                if iseg.source_text != hseg.source_text:
                    seg_diffs.append(f"source: {iseg.source_text} vs {hseg.source_text}")
            
            # Note seq differences (for info, but don't treat as mismatch for conjugated forms)
            if iseg.seq != hseg.seq and iseg.seq is not None:
                # Ichiran uses generated seqs (10000000+) for conjugated forms
                # Only flag as significant if neither is conjugated
                if not iseg.conj_type and not hseg.conj_type:
                    seg_diffs.append(f"seq: {iseg.seq} vs {hseg.seq}")
            
            if seg_diffs:
                all_match = False
                differences.append(f"Segment '{iseg.text}': {', '.join(seg_diffs)}")
        
        status = MatchStatus.MATCH if all_match else MatchStatus.PARTIAL
    else:
        status = MatchStatus.MISMATCH
        differences.append(f"Ichiran: {ichiran_texts}")
        differences.append(f"Himotoki: {himotoki_texts}")
    
    return ComparisonResult(
        sentence=sentence,
        status=status,
        ichiran=ichiran_result,
        himotoki=himotoki_result,
        ichiran_texts=ichiran_texts,
        himotoki_texts=himotoki_texts,
        differences=differences,
        time_ichiran=time_ichiran,
        time_himotoki=time_himotoki,
    )


# ============================================================================
# Test Sentences
# ============================================================================

# Comprehensive test corpus
TEST_SENTENCES = {
    "basic_particles": [
        "猫が",
        "犬を",
        "山に",
        "川で",
        "友達と",
        "家から",
        "駅まで",
        "本は",
        "私も",
        "何か",
    ],
    
    "noun_particle_verb": [
        "本を読む",
        "水を飲む",
        "東京に行く",
        "学校で勉強する",
        "友達と話す",
        "家に帰る",
        "電車で行く",
        "日本語を勉強する",
        "ご飯を食べる",
        "音楽を聴く",
    ],
    
    "copula_patterns": [
        "学生です",
        "先生です",
        "静かです",
        "元気です",
        "本だ",
        "猫だ",
        "きれいです",
        "有名です",
        "日本人です",
        "学校です",
    ],
    
    "te_form_compounds": [
        "食べている",
        "食べています",
        "見ている",
        "読んでいる",
        "書いている",
        "走っている",
        "食べてある",
        "書いてある",
        "食べてしまう",
        "忘れてしまった",
    ],
    
    "verb_conjugations": [
        "食べる",
        "食べた",
        "食べない",
        "食べます",
        "食べました",
        "食べません",
        "食べて",
        "食べたい",
        "食べられる",
        "食べさせる",
    ],
    
    "adjective_patterns": [
        "大きい",
        "大きかった",
        "大きくない",
        "大きくなかった",
        "静かな",
        "静かに",
        "きれいな",
        "きれいに",
        "天気がいい",
        "本が面白い",
    ],
    
    "complex_sentences": [
        "一覧は最高だぞ",
        "猫に水をあげる",
        "日本語を勉強しています",
        "東京に行きたいです",
        "明日は雨が降るでしょう",
        "彼女は先生になりました",
        "この本は面白いと思います",
        "時間がないから行けない",
        "食べてから寝る",
        "勉強しなければならない",
    ],
    
    "common_expressions": [
        "おはよう",
        "こんにちは",
        "こんばんは",
        "ありがとう",
        "すみません",
        "ごめんなさい",
        "いただきます",
        "ごちそうさま",
        "お願いします",
        "さようなら",
    ],
    
    "numbers_counters": [
        "一つ",
        "二人",
        "三匹",
        "四本",
        "五冊",
        "一月",
        "二日",
        "三時",
        "百円",
        "千人",
    ],
    
    "katakana_words": [
        "コンピュータ",
        "テレビ",
        "インターネット",
        "レストラン",
        "コーヒー",
        "アメリカ",
        "フランス",
        "ドイツ",
        "スマートフォン",
        "プログラミング",
    ],
    
    "edge_cases": [
        "がんばって",
        "やってみる",
        "してあげる",
        "してもらう",
        "しなくてもいい",
        "食べなくてはいけない",
        "行かなければならない",
        "ということ",
        "というのは",
        "それでは",
    ],
}

# Quick subset for fast testing
QUICK_SENTENCES = [
    "猫が",
    "本を読む",
    "学生です",
    "食べています",
    "食べた",
    "大きい",
    "一覧は最高だぞ",
    "おはよう",
    "三匹",
    "コンピュータ",
]


# ============================================================================
# Reporting
# ============================================================================

def print_result(result: ComparisonResult, verbose: bool = False):
    """Print a single comparison result."""
    status_symbols = {
        MatchStatus.MATCH: "✓",
        MatchStatus.PARTIAL: "~",
        MatchStatus.MISMATCH: "✗",
        MatchStatus.ICHIRAN_ERROR: "!I",
        MatchStatus.HIMOTOKI_ERROR: "!H",
    }
    
    symbol = status_symbols.get(result.status, "?")
    
    if result.status == MatchStatus.MATCH:
        if verbose:
            print(f"  {symbol} {result.sentence}: {result.ichiran_texts}")
    elif result.status == MatchStatus.PARTIAL:
        print(f"  {symbol} {result.sentence}: same split, different details")
        if verbose:
            for diff in result.differences:
                print(f"      {diff}")
    else:
        print(f"  {symbol} {result.sentence}")
        print(f"      Ichiran:  {result.ichiran_texts}")
        print(f"      Himotoki: {result.himotoki_texts}")
        if verbose:
            for diff in result.differences:
                print(f"      {diff}")


def print_summary(results: List[ComparisonResult]):
    """Print summary statistics."""
    total = len(results)
    matches = sum(1 for r in results if r.status == MatchStatus.MATCH)
    partial = sum(1 for r in results if r.status == MatchStatus.PARTIAL)
    mismatches = sum(1 for r in results if r.status == MatchStatus.MISMATCH)
    ichiran_errors = sum(1 for r in results if r.status == MatchStatus.ICHIRAN_ERROR)
    himotoki_errors = sum(1 for r in results if r.status == MatchStatus.HIMOTOKI_ERROR)
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total sentences:    {total}")
    print(f"Exact matches:      {matches} ({100*matches/total:.1f}%)")
    print(f"Partial matches:    {partial} ({100*partial/total:.1f}%)")
    print(f"Mismatches:         {mismatches} ({100*mismatches/total:.1f}%)")
    print(f"Ichiran errors:     {ichiran_errors}")
    print(f"Himotoki errors:    {himotoki_errors}")
    
    # Timing
    avg_ichiran = sum(r.time_ichiran for r in results) / total
    avg_himotoki = sum(r.time_himotoki for r in results) / total
    print(f"\nAvg time Ichiran:   {avg_ichiran*1000:.1f}ms")
    print(f"Avg time Himotoki:  {avg_himotoki*1000:.1f}ms")


def export_results(results: List[ComparisonResult], filename: str):
    """Export results to JSON file."""
    data = []
    for r in results:
        data.append({
            "sentence": r.sentence,
            "status": r.status.value,
            "ichiran_texts": r.ichiran_texts,
            "himotoki_texts": r.himotoki_texts,
            "differences": r.differences,
            "time_ichiran": r.time_ichiran,
            "time_himotoki": r.time_himotoki,
        })
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\nResults exported to {filename}")


# ============================================================================
# Main
# ============================================================================

def run_tests(sentences: List[str], verbose: bool = False) -> List[ComparisonResult]:
    """Run comparison tests on a list of sentences."""
    results = []
    
    for i, sentence in enumerate(sentences):
        if (i + 1) % 10 == 0:
            print(f"  Progress: {i+1}/{len(sentences)}", file=sys.stderr)
        
        result = compare_segmentations(sentence)
        results.append(result)
        print_result(result, verbose)
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Compare Ichiran and Himotoki segmentation"
    )
    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Run quick subset of tests"
    )
    parser.add_argument(
        "--sentence", "-s",
        type=str,
        help="Test a single sentence"
    )
    parser.add_argument(
        "--category", "-c",
        type=str,
        choices=list(TEST_SENTENCES.keys()),
        help="Test a specific category"
    )
    parser.add_argument(
        "--export", "-e",
        type=str,
        help="Export results to JSON file"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--mismatches-only", "-m",
        action="store_true",
        help="Only show mismatches"
    )
    
    args = parser.parse_args()
    
    # Determine which sentences to test
    if args.sentence:
        sentences = [args.sentence]
    elif args.quick:
        sentences = QUICK_SENTENCES
    elif args.category:
        sentences = TEST_SENTENCES[args.category]
    else:
        # All sentences
        sentences = []
        for category, sents in TEST_SENTENCES.items():
            sentences.extend(sents)
    
    print("=" * 60)
    print("Ichiran vs Himotoki Comparison")
    print("=" * 60)
    print(f"Testing {len(sentences)} sentences...\n")
    
    # Run tests
    results = run_tests(sentences, args.verbose)
    
    # Filter if needed
    if args.mismatches_only:
        results = [r for r in results if r.status == MatchStatus.MISMATCH]
    
    # Print summary
    print_summary(results)
    
    # Export if requested
    if args.export:
        export_results(results, args.export)
    
    # Return exit code based on results
    mismatches = sum(1 for r in results if r.status == MatchStatus.MISMATCH)
    return 1 if mismatches > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
