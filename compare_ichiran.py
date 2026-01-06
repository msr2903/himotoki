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
ICHIRAN_CACHE_FILE = "results.json"

# Cache a single Himotoki DB session and suffix initialization so repeated
# comparisons don't pay the startup cost each time.
_himotoki_session = None
_himotoki_suffixes_ready = False

# Cache for ichiran results loaded from file (initialized after dataclass definitions)
_ichiran_cache = {}  # Dict[str, SegmentationResult]
_ichiran_cache_loaded = False


def get_himotoki_session():
    """Return a ready-to-use Himotoki DB session with suffixes initialized."""
    global _himotoki_session, _himotoki_suffixes_ready
    from himotoki.db.connection import get_session, get_db_path
    from himotoki.suffixes import init_suffixes
    
    db_path = get_db_path()
    if not db_path:
        raise RuntimeError(
            "Himotoki database not found. Set HIMOTOKI_DB or run init_db.py to build it."
        )
    
    if _himotoki_session is None:
        _himotoki_session = get_session(db_path)
    
    if not _himotoki_suffixes_ready:
        init_suffixes(_himotoki_session)
        _himotoki_suffixes_ready = True
    
    return _himotoki_session


# ============================================================================
# Data Classes
# ============================================================================

class MatchStatus(Enum):
    MATCH = "match"              # Exact match
    PARTIAL = "partial"          # Same segmentation, different details
    MISMATCH = "mismatch"        # Different segmentation
    ICHIRAN_ERROR = "ichiran_error"  # Ichiran failed
    HIMOTOKI_ERROR = "himotoki_error"  # Himotoki failed
    UNCOMPARABLE = "uncomparable"  # Ichiran result incomplete/unreliable


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
# Ichiran Cache Functions
# ============================================================================

def load_ichiran_cache(cache_file: str = ICHIRAN_CACHE_FILE) -> Dict[str, Any]:
    """
    Load cached ichiran results from a previous run.
    
    Returns:
        Dict mapping sentence -> ichiran SegmentationResult
    """
    global _ichiran_cache, _ichiran_cache_loaded
    
    if _ichiran_cache_loaded:
        return _ichiran_cache
    
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for entry in data:
            sentence = entry.get('sentence', '')
            if not sentence:
                continue
            
            # Reconstruct SegmentationResult from cached data
            ichiran_segments = entry.get('ichiran_segments', [])
            segments = []
            total_score = 0
            
            for seg_data in ichiran_segments:
                seg = SegmentInfo(
                    text=seg_data.get('text', ''),
                    kana=seg_data.get('kana', ''),
                    seq=seg_data.get('seq'),
                    score=seg_data.get('score', 0),
                    is_compound=seg_data.get('is_compound', False),
                    components=seg_data.get('components', []),
                    conj_type=seg_data.get('conj_type'),
                    conj_neg=seg_data.get('conj_neg', False),
                    conj_fml=seg_data.get('conj_fml', False),
                    source_text=seg_data.get('source_text'),
                    pos=seg_data.get('pos', [])
                )
                segments.append(seg)
                total_score += seg.score
            
            _ichiran_cache[sentence] = SegmentationResult(
                segments=segments,
                total_score=total_score
            )
        
        _ichiran_cache_loaded = True
        print(f"Loaded {len(_ichiran_cache)} cached ichiran results from {cache_file}", file=sys.stderr)
        
    except FileNotFoundError:
        print(f"Cache file {cache_file} not found, will call ichiran directly", file=sys.stderr)
    except Exception as e:
        print(f"Error loading cache: {e}", file=sys.stderr)
    
    return _ichiran_cache


def get_ichiran_cached(sentence: str) -> Optional[SegmentationResult]:
    """Get ichiran result from cache if available."""
    if not _ichiran_cache_loaded:
        load_ichiran_cache()
    return _ichiran_cache.get(sentence)


# ============================================================================
# Ichiran Interface
# ============================================================================

# Global flag to control whether to use cache (enabled by default)
_use_ichiran_cache = True


def _is_cache_result_complete(sentence: str, cached: SegmentationResult) -> bool:
    """
    Check if a cached ichiran result is complete (covers the full input).
    
    Returns False if:
    - The result has an error
    - The segments don't cover the full input text
    - There are no segments
    """
    if cached.error:
        return False
    if not cached.segments:
        return False
    
    # Join all segment texts and check if they cover the input
    cached_text = "".join(seg.text for seg in cached.segments)
    
    # If cached text is much shorter than input, it's incomplete
    # We allow some tolerance for punctuation differences
    if len(cached_text) < len(sentence) * 0.5:
        return False
    
    return True


def run_ichiran(sentence: str) -> SegmentationResult:
    """
    Run Ichiran CLI and parse the JSON output.
    Uses cache if available and --use-cache flag is set.
    
    Args:
        sentence: Japanese text to segment.
        
    Returns:
        SegmentationResult with parsed segments.
    """
    # Check cache first if enabled
    if _use_ichiran_cache:
        cached = get_ichiran_cached(sentence)
        if cached is not None:
            # Verify the cached result is complete - if not, re-process
            if _is_cache_result_complete(sentence, cached):
                return cached
            else:
                print(f"  (cache incomplete for '{sentence[:20]}...', re-processing)", file=sys.stderr)
    
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
                
                # Use the text field directly if available (Himotoki sets this correctly)
                # Otherwise join component texts (for backwards compatibility)
                full_text = info.get("text") or "".join(component_texts)
                
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
    """Run Himotoki and adapt its JSON to the Ichiran parser."""
    try:
        from himotoki.output import segment_to_json
        session = get_himotoki_session()
    except Exception as e:
        import traceback
        return SegmentationResult(
            segments=[],
            error=f"Himotoki setup error: {e}\n{traceback.format_exc()}",
        )

    try:
        results = segment_to_json(session, sentence, limit=1)
        if not results:
            return SegmentationResult(segments=[], error="No segmentation")

        # segment_to_json returns [[segments, score], ...]; wrap to match
        # Ichiran's [[[segments, score]]] shape expected by parse_ichiran_output.
        parsed = parse_ichiran_output([[results[0]]])
        parsed.raw_output = results
        return parsed

    except Exception as e:
        import traceback
        return SegmentationResult(
            segments=[],
            error=f"Himotoki error: {e}\n{traceback.format_exc()}",
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
    
    # Check if ichiran result is incomplete (covers less than 50% of input)
    ichiran_coverage = len("".join(ichiran_texts))
    if ichiran_coverage < len(sentence) * 0.5 and not ichiran_result.error:
        status = MatchStatus.UNCOMPARABLE
        differences.append(f"Ichiran result incomplete: '{ichiran_texts}' covers only {ichiran_coverage}/{len(sentence)} chars")
    elif ichiran_result.error:
        status = MatchStatus.ICHIRAN_ERROR
        differences.append(f"Ichiran error: {ichiran_result.error}")
    elif himotoki_result.error:
        status = MatchStatus.HIMOTOKI_ERROR
        differences.append(f"Himotoki error: {himotoki_result.error}")
    elif ichiran_texts == himotoki_texts:
        # Same segmentation - check for conjugation/detail differences
        # We track two types of differences:
        # - significant_diffs: conj_type, neg, fml, source (these make it PARTIAL)
        # - info_diffs: seq differences (informational only, still counts as MATCH)
        has_significant_diff = False
        for i, (iseg, hseg) in enumerate(zip(ichiran_result.segments, himotoki_result.segments)):
            seg_significant_diffs = []
            seg_info_diffs = []
            
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
                seg_significant_diffs.append(f"conj_type: {iseg.conj_type} vs {hseg.conj_type}")
            
            # Check neg/fml flags
            if iseg.conj_neg != hseg.conj_neg:
                seg_significant_diffs.append(f"neg: {iseg.conj_neg} vs {hseg.conj_neg}")
            if iseg.conj_fml != hseg.conj_fml:
                seg_significant_diffs.append(f"fml: {iseg.conj_fml} vs {hseg.conj_fml}")
            
            # Check source text (dictionary form)
            if iseg.source_text and hseg.source_text:
                if iseg.source_text != hseg.source_text:
                    seg_significant_diffs.append(f"source: {iseg.source_text} vs {hseg.source_text}")
            
            # Seq differences are informational only - different seq numbers for
            # conjugated forms are expected and don't affect match status
            if iseg.seq != hseg.seq and iseg.seq is not None:
                seg_info_diffs.append(f"seq: {iseg.seq} vs {hseg.seq}")
            
            if seg_significant_diffs:
                has_significant_diff = True
                differences.append(f"Segment '{iseg.text}': {', '.join(seg_significant_diffs)}")
            # Optionally log seq diffs but don't count them as significant
            # (uncomment if you want to see seq diffs in output)
            # elif seg_info_diffs:
            #     differences.append(f"Segment '{iseg.text}' (info): {', '.join(seg_info_diffs)}")
        
        status = MatchStatus.PARTIAL if has_significant_diff else MatchStatus.MATCH
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

# Comprehensive test corpus - full native sentences for release evaluation
TEST_SENTENCES = {
    "daily_conversation": [
        "今日はいい天気ですね",
        "明日の予定はどうなっていますか",
        "ちょっと待ってください",
        "すみません、道を教えていただけませんか",
        "最近忙しくてなかなか会えないね",
        "週末は何をする予定ですか",
        "昨日のパーティーは楽しかったです",
        "電車が遅れているみたいですね",
        "この近くにコンビニはありますか",
        "久しぶりに会えて嬉しいです",
        "ご飯を食べに行きませんか",
        "今何時ですか",
        "ここに座ってもいいですか",
        "お名前を教えていただけますか",
        "日本語がお上手ですね",
    ],

    "casual_speech": [
        "それマジでやばくない",
        "明日暇だったら遊ぼうよ",
        "ちょっとそれ貸してくれない",
        "昨日めっちゃ疲れたわ",
        "なんかお腹すいてきたな",
        "もう帰んなきゃいけないんだけど",
        "あいつ何考えてんだろうね",
        "そんなこと言われてもさ",
        "別にいいんじゃない",
        "てか最近どうしてるの",
        "まあそういうこともあるよね",
        "それってどういう意味",
        "早く来てくれないかな",
        "そろそろ寝ないとまずいな",
        "なんでそんなことするかな",
    ],

    "polite_formal": [
        "お忙しいところ恐れ入りますが",
        "ご検討いただければ幸いです",
        "本日はお越しいただきありがとうございます",
        "何かご不明な点がございましたらお申し付けください",
        "お手数をおかけして申し訳ございません",
        "ご理解いただけますと幸いでございます",
        "本件につきましてご報告申し上げます",
        "ご多忙中恐縮ではございますが",
        "お時間をいただけますでしょうか",
        "改めてご連絡させていただきます",
        "ご確認のほどよろしくお願いいたします",
        "何卒よろしくお願い申し上げます",
        "ご迷惑をおかけして大変申し訳ございません",
        "お返事をお待ちしております",
        "ご参加いただけますようお願いいたします",
    ],

    "news_reporting": [
        "首相は記者会見で新たな政策を発表した",
        "今朝、東京で震度四の地震が観測された",
        "事故の原因については現在調査中である",
        "来月から新しい制度が施行される見込みだ",
        "被害者は病院に搬送されたが命に別状はない",
        "政府は緊急対策本部を設置する方針を固めた",
        "株価は前日比で大幅に下落している",
        "選挙の投票率は過去最低を記録した",
        "専門家は今後の動向に注視する必要があると指摘した",
        "関係者によると計画は来年度から実施されるという",
        "被災地への支援物資の輸送が始まった",
        "警察は容疑者の身柄を確保したと発表した",
        "経済の先行きに対する懸念が広がっている",
        "新型ウイルスの感染者数は減少傾向にある",
        "国際会議で合意に達することはできなかった",
    ],

    "opinions_thoughts": [
        "私はその意見に賛成できないと思います",
        "もう少し時間があればできたのに",
        "彼がそう言うとは思わなかった",
        "正直に言って、あまり期待していません",
        "その問題についてはよく考える必要がある",
        "どうしてそういう結論になるのか理解できない",
        "もしかしたら間違っているかもしれない",
        "そういう考え方もあるのかと驚いた",
        "結局のところ何が正しいのかわからない",
        "たとえ難しくてもやってみる価値はある",
        "彼女の言っていることには一理ある",
        "そこまで深く考えたことはなかった",
        "個人的にはもっと慎重に進めるべきだと思う",
        "この件については様々な意見があるようだ",
        "なぜそうなったのか今でも不思議に思う",
    ],

    "requests_instructions": [
        "この書類に必要事項を記入してください",
        "もう少し大きな声で話していただけますか",
        "電源を切ってからコンセントを抜いてください",
        "ここから先は立ち入り禁止となっております",
        "申込書は窓口にてお受け取りください",
        "作業が終わりましたらお知らせください",
        "荷物は棚の上に置かないでください",
        "出発前に必ず持ち物を確認してください",
        "詳しくは係員にお尋ねください",
        "この薬は食後に一錠ずつ服用してください",
        "緊急の場合はこちらの番号にお電話ください",
        "登録が完了するまでしばらくお待ちください",
        "会議室の利用後は椅子を元の位置に戻してください",
        "パスワードは定期的に変更することをお勧めします",
        "資料は事前にダウンロードしておいてください",
    ],

    "conditional_hypothetical": [
        "もし時間があれば手伝ってくれませんか",
        "雨が降らなければ公園に行くつもりです",
        "あの時もっと勉強していれば合格できたのに",
        "彼が来るかどうかはまだわからない",
        "早く起きていたらこんなことにはならなかった",
        "無理をしなければ体を壊さなかったはずだ",
        "お金さえあれば世界中を旅行したい",
        "もしよろしければご一緒にいかがですか",
        "条件が整えば来月から開始する予定です",
        "許可が下りなかった場合は計画を変更します",
        "彼女に会えるなら何でもする",
        "そうでなければ別の方法を考えなければならない",
        "仮に失敗したとしても後悔はしないだろう",
        "運が良ければ今日中に届くかもしれない",
        "知っていたら教えてあげたのに",
    ],

    "explanations_reasons": [
        "電車が遅れたので遅刻してしまいました",
        "体調が悪いため今日は早退させてください",
        "予算の都合上、その計画は実現できません",
        "彼が怒っているのは誤解があったからだ",
        "締め切りに間に合わなかったのは準備不足のせいだ",
        "参加者が少なかったのでイベントは中止になった",
        "この地域は昔から水が豊富なことで知られている",
        "成功したのは皆さんの協力があったからこそです",
        "物価が上がっているのは円安の影響だと言われている",
        "彼女が辞めた理由は誰も知らない",
        "技術的な問題により本日のサービスは停止しています",
        "そういうわけで今回は見送ることにしました",
        "人手不足のため営業時間を短縮しております",
        "詳しい経緯については後ほど説明いたします",
        "天候の影響でフライトが欠航になりました",
    ],

    "descriptions_narratives": [
        "桜の花が満開で公園は多くの人で賑わっていた",
        "古い町並みが残るこの地域は観光客に人気がある",
        "彼は静かに部屋を出て行った",
        "窓の外には雪が降り始めていた",
        "子供たちは楽しそうに校庭で遊んでいる",
        "夕日が海に沈んでいく様子はとても美しかった",
        "店内は薄暗く、どこか懐かしい雰囲気が漂っていた",
        "彼女は何も言わずに手紙を渡してきた",
        "朝から雨が降り続いていて気分が沈む",
        "山の頂上からは町全体を見渡すことができる",
        "駅前には新しいビルが建設されている",
        "彼の話を聞いて皆が驚きの表情を浮かべた",
        "この道をまっすぐ行くと大きな交差点に出る",
        "祭りの日は街中が活気に満ちている",
        "長い間使われていなかった建物が取り壊されることになった",
    ],

    "te_form_auxiliaries": [
        "この本を読んでみたいと思っています",
        "彼女は毎日日本語を勉強し続けている",
        "旅行の準備はもう終わってしまった",
        "せっかく作ったのに食べてもらえなかった",
        "駅に着いてからすぐに電話してください",
        "彼は何も言わないで帰ってしまった",
        "念のため確認しておいた方がいいですよ",
        "困っている人がいたら助けてあげたい",
        "先生に教えてもらったおかげで理解できた",
        "宿題をやっておかないと明日困るよ",
        "友達に借りていた本を返してきた",
        "疲れていても毎日運動するようにしている",
        "説明書を読んでからでないと使えない",
        "子供のころからずっとピアノを習っている",
        "何度も練習してやっとできるようになった",
    ],

    "complex_grammar": [
        "彼がそう言ったからといって信じるわけにはいかない",
        "日本に来たばかりのころは何もわからなかった",
        "いくら探しても見つからなかったのであきらめた",
        "どんなに忙しくても健康には気をつけるべきだ",
        "この問題は簡単そうに見えて実は難しい",
        "彼女は泣きながら自分の過ちを認めた",
        "せっかくの休みなのに家から出られなかった",
        "彼に限ってそんなことをするはずがない",
        "うっかり約束の時間を忘れてしまうところだった",
        "努力したにもかかわらず結果は出なかった",
        "言われてみれば確かにそうかもしれない",
        "彼が来るか来ないかにかかわらず会議は始める",
        "あの人は見かけによらず優しい性格だ",
        "勉強すればするほど知らないことが増えていく",
        "これだけ準備をしたのだから失敗するわけがない",
    ],

    "sou_patterns": [
        "今にも雨が降りそうな空模様だ",
        "この料理は見た目がとてもおいしそうですね",
        "彼は何か言いたそうにこちらを見ていた",
        "新しい店は繁盛しそうな雰囲気がある",
        "話を聞いていると簡単そうに思える",
        "疲れていそうだから少し休んだ方がいい",
        "その案は実現できそうにないと思う",
        "明日は晴れそうなので洗濯をしよう",
        "彼女は泣き出しそうな顔をしていた",
        "今年の夏は暑くなりそうだと予報が出ている",
        "うまくいきそうな気がしてきた",
        "彼の話は嘘っぽくて信じられそうにない",
        "この仕事は私には難しそうです",
        "もうすぐ届きそうなので待っていてください",
        "頑張れば間に合いそうな気がする",
    ],

    "passive_causative": [
        "電車の中で足を踏まれてしまった",
        "母に野菜を食べさせられた",
        "彼は上司に無理な仕事を押し付けられている",
        "子供にゲームをやめさせるのは難しい",
        "突然の雨に降られて服がびしょ濡れになった",
        "彼女は親に留学を反対されているらしい",
        "部下に仕事を任せてみることにした",
        "この曲を聴くと昔のことを思い出させられる",
        "財布を盗まれたので警察に届け出た",
        "彼は皆から尊敬されている人物だ",
        "子供のころは毎日勉強させられていた",
        "彼の発言は多くの人に批判されている",
        "長時間待たされたので怒りを感じた",
        "この作品は世界中で読まれている",
        "親に心配をかけさせてしまって申し訳ない",
    ],

    "questions_inquiries": [
        "この電車は新宿駅に止まりますか",
        "どうしてそんなに早く起きるんですか",
        "注文した商品はいつ届きますか",
        "このあたりにおすすめのレストランはありますか",
        "どのくらい時間がかかりますか",
        "何か手伝えることはありますか",
        "彼女がなぜ怒っているのか知っていますか",
        "この言葉の意味を教えていただけますか",
        "どちらの方が人気がありますか",
        "予約は必要でしょうか",
        "いつからこの仕事をしているのですか",
        "何人くらい参加する予定ですか",
        "どうやってここまで来たのですか",
        "あの建物は何ですか",
        "会議は何時に終わる予定ですか",
    ],

    "colloquial_contractions": [
        "そんなこと言ったってしょうがないじゃん",
        "やっぱり行かなきゃだめかな",
        "もうちょっと待ってくんない",
        "それって本当なのかな",
        "別に怒ってるわけじゃないんだけど",
        "今日はなんか調子悪いんだよね",
        "ていうか、それ知らなかったの",
        "まあいっか、なんとかなるでしょ",
        "うん、でもそれちょっと違うんじゃない",
        "明日までにやっとかないとまずいかも",
        "そんなの知らないし",
        "ねえねえ、これ見てみて",
        "あれってさ、どう思う",
        "え、マジで言ってんの",
        "だからさ、そういうことじゃないんだって",
    ],

    "literary_written": [
        "彼の行動は理解しがたいものであった",
        "その事実が明らかになるにつれ事態は深刻化した",
        "過去の経験に基づき判断を下すべきである",
        "問題解決に向けた取り組みが求められている",
        "本研究の目的は現象の解明にある",
        "かつてこの地には多くの寺院が存在していた",
        "彼女の功績は後世に語り継がれるであろう",
        "いかなる困難にも屈することなく前進し続けた",
        "状況を鑑みるに慎重な対応が必要である",
        "この問題に対する解答は一つではない",
        "時代の変化とともに価値観も変わっていく",
        "真実を追求する姿勢を忘れてはならない",
        "彼らの努力なくして成功はあり得なかった",
        "未来に向けて何をなすべきか考える必要がある",
        "歴史が証明しているように変化は避けられない",
    ],

    "counters_numbers": [
        "この会社には従業員が三百人以上いる",
        "一週間に二回はジムに通っている",
        "あの映画は三時間もあるから疲れた",
        "本棚には五十冊くらいの本がある",
        "今年で日本に住んで十年になる",
        "駅から歩いて十五分くらいかかります",
        "このビルは三十階建てです",
        "毎朝コーヒーを二杯飲んでいる",
        "今月は五回も出張がある",
        "うちには犬が二匹と猫が一匹いる",
        "このプロジェクトには四つの段階がある",
        "昨日は三件のミーティングがあった",
        "百円ショップで色々買ってきた",
        "試験まであと二週間しかない",
        "このクラスは生徒が二十五人いる",
    ],
}

# Quick subset for fast testing (one per category)
QUICK_SENTENCES = [
    "今日はいい天気ですね",
    "それマジでやばくない",
    "お忙しいところ恐れ入りますが",
    "首相は記者会見で新たな政策を発表した",
    "私はその意見に賛成できないと思います",
    "この書類に必要事項を記入してください",
    "もし時間があれば手伝ってくれませんか",
    "電車が遅れたので遅刻してしまいました",
    "桜の花が満開で公園は多くの人で賑わっていた",
    "この本を読んでみたいと思っています",
    "彼がそう言ったからといって信じるわけにはいかない",
    "今にも雨が降りそうな空模様だ",
    "電車の中で足を踏まれてしまった",
    "この電車は新宿駅に止まりますか",
    "そんなこと言ったってしょうがないじゃん",
    "彼の行動は理解しがたいものであった",
    "この会社には従業員が三百人以上いる",
]


# ============================================================================
# Reporting
# ============================================================================

def _format_segment(seg: SegmentInfo) -> str:
    """Readable one-liner for a segment with dictionary ID and features."""
    pos = ",".join(seg.pos) if seg.pos else "-"
    return (
        f"{seg.text} "
        f"[seq={seg.seq if seg.seq is not None else '-'} "
        f"kana={seg.kana or '-'} "
        f"conj={seg.conj_type or '-'} "
        f"neg={seg.conj_neg} fml={seg.conj_fml} "
        f"src={seg.source_text or '-'} pos={pos}]"
    )


def print_result(result: ComparisonResult, verbose: bool = False, show_details: bool = False):
    """Print a single comparison result."""
    status_symbols = {
        MatchStatus.MATCH: "✓",
        MatchStatus.PARTIAL: "~",
        MatchStatus.MISMATCH: "✗",
        MatchStatus.ICHIRAN_ERROR: "!I",
        MatchStatus.HIMOTOKI_ERROR: "!H",
        MatchStatus.UNCOMPARABLE: "?",
    }
    
    symbol = status_symbols.get(result.status, "?")
    details = verbose or show_details
    
    if result.status == MatchStatus.MATCH:
        if details:
            print(f"  {symbol} {result.sentence}: {result.ichiran_texts}")
            for seg in result.ichiran.segments:
                print(f"      Ichiran  {_format_segment(seg)}")
                print(f"      Himotoki {_format_segment(seg)}")
    elif result.status == MatchStatus.PARTIAL:
        print(f"  {symbol} {result.sentence}: same split, different details")
        if details:
            print(f"      Ichiran:")
            for seg in result.ichiran.segments:
                print(f"        {_format_segment(seg)}")
            print(f"      Himotoki:")
            for seg in result.himotoki.segments:
                print(f"        {_format_segment(seg)}")
        for diff in result.differences:
            print(f"      {diff}")
    elif result.status == MatchStatus.UNCOMPARABLE:
        print(f"  {symbol} {result.sentence}: ichiran incomplete")
        for diff in result.differences:
            print(f"      {diff}")
    else:
        print(f"  {symbol} {result.sentence}")
        print(f"      Ichiran:  {result.ichiran_texts}")
        print(f"      Himotoki: {result.himotoki_texts}")
        if details:
            print(f"      Ichiran segments:")
            for seg in result.ichiran.segments:
                print(f"        {_format_segment(seg)}")
            print(f"      Himotoki segments:")
            for seg in result.himotoki.segments:
                print(f"        {_format_segment(seg)}")
        for diff in result.differences:
            print(f"      {diff}")


def print_summary(results: List[ComparisonResult]):
    """Print summary statistics."""
    total = len(results)
    matches = sum(1 for r in results if r.status == MatchStatus.MATCH)
    partial = sum(1 for r in results if r.status == MatchStatus.PARTIAL)
    mismatches = sum(1 for r in results if r.status == MatchStatus.MISMATCH)
    uncomparable = sum(1 for r in results if r.status == MatchStatus.UNCOMPARABLE)
    ichiran_errors = sum(1 for r in results if r.status == MatchStatus.ICHIRAN_ERROR)
    himotoki_errors = sum(1 for r in results if r.status == MatchStatus.HIMOTOKI_ERROR)
    
    # Calculate comparable total (excluding uncomparable and errors)
    comparable = total - uncomparable - ichiran_errors - himotoki_errors
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total sentences:    {total}")
    print(f"Comparable:         {comparable}")
    print(f"Exact matches:      {matches} ({100*matches/comparable:.1f}% of comparable)" if comparable > 0 else f"Exact matches:      {matches}")
    print(f"Partial matches:    {partial} ({100*partial/comparable:.1f}% of comparable)" if comparable > 0 else f"Partial matches:    {partial}")
    print(f"Mismatches:         {mismatches} ({100*mismatches/comparable:.1f}% of comparable)" if comparable > 0 else f"Mismatches:         {mismatches}")
    print(f"Uncomparable:       {uncomparable} (ichiran incomplete)")
    print(f"Ichiran errors:     {ichiran_errors}")
    print(f"Himotoki errors:    {himotoki_errors}")
    
    # Timing
    avg_ichiran = sum(r.time_ichiran for r in results) / total
    avg_himotoki = sum(r.time_himotoki for r in results) / total
    print(f"\nAvg time Ichiran:   {avg_ichiran*1000:.1f}ms")
    print(f"Avg time Himotoki:  {avg_himotoki*1000:.1f}ms")


def _segmentinfo_to_dict(seg: SegmentInfo) -> Dict[str, Any]:
    """Convert SegmentInfo to a JSON-friendly dict with dictionary IDs."""
    return {
        "text": seg.text,
        "kana": seg.kana,
        "seq": seg.seq,
        "score": seg.score,
        "is_compound": seg.is_compound,
        "components": seg.components,
        "conj_type": seg.conj_type,
        "conj_neg": seg.conj_neg,
        "conj_fml": seg.conj_fml,
        "source_text": seg.source_text,
        "pos": seg.pos,
    }


def export_results(results: List[ComparisonResult], filename: str):
    """Export results to JSON file with detailed segment data."""
    data = []
    for r in results:
        data.append(_comparison_result_to_dict(r))
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\nResults exported to {filename}")


def export_filtered_results(results: List[ComparisonResult]):
    """Export mismatch.json and partial.json for easier debugging."""
    mismatches = [r for r in results if r.status == MatchStatus.MISMATCH]
    partials = [r for r in results if r.status == MatchStatus.PARTIAL]
    
    # Export mismatch.json
    mismatch_data = [_comparison_result_to_dict(r) for r in mismatches]
    with open('mismatch.json', 'w', encoding='utf-8') as f:
        json.dump(mismatch_data, f, ensure_ascii=False, indent=2)
    print(f"Exported {len(mismatches)} mismatches to mismatch.json")
    
    # Export partial.json
    partial_data = [_comparison_result_to_dict(r) for r in partials]
    with open('partial.json', 'w', encoding='utf-8') as f:
        json.dump(partial_data, f, ensure_ascii=False, indent=2)
    print(f"Exported {len(partials)} partial matches to partial.json")


def _comparison_result_to_dict(r: ComparisonResult) -> Dict[str, Any]:
    """Convert a ComparisonResult to a JSON-serializable dict."""
    return {
        "sentence": r.sentence,
        "status": r.status.value,
        "ichiran_texts": r.ichiran_texts,
        "himotoki_texts": r.himotoki_texts,
        "ichiran_segments": [_segmentinfo_to_dict(s) for s in r.ichiran.segments],
        "himotoki_segments": [_segmentinfo_to_dict(s) for s in r.himotoki.segments],
        "differences": r.differences,
        "time_ichiran": r.time_ichiran,
        "time_himotoki": r.time_himotoki,
    }


def update_single_result(result: ComparisonResult, filename: str):
    """
    Update a single sentence result in the JSON file.
    
    Loads existing results, updates or adds the specific sentence,
    and writes back only if there was a change.
    """
    # Load existing data
    existing_data = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing_data = []
    
    # Convert to dict for easy lookup by sentence
    data_by_sentence = {item["sentence"]: item for item in existing_data}
    
    # Get new result as dict
    new_result = _comparison_result_to_dict(result)
    
    # Check if there's a change
    old_result = data_by_sentence.get(result.sentence)
    if old_result:
        # Compare relevant fields (ignore timing differences)
        old_texts = old_result.get("himotoki_texts", [])
        new_texts = new_result.get("himotoki_texts", [])
        old_status = old_result.get("status")
        new_status = new_result.get("status")
        
        if old_texts == new_texts and old_status == new_status:
            print(f"\nNo change for '{result.sentence}' - not updating {filename}")
            return
        else:
            print(f"\nUpdating '{result.sentence}' in {filename}")
            print(f"  Status: {old_status} -> {new_status}")
            if old_texts != new_texts:
                print(f"  Old: {old_texts}")
                print(f"  New: {new_texts}")
    else:
        print(f"\nAdding new sentence '{result.sentence}' to {filename}")
    
    # Update or add the result
    data_by_sentence[result.sentence] = new_result
    
    # Convert back to list, preserving order of existing items
    updated_data = []
    seen = set()
    for item in existing_data:
        sentence = item["sentence"]
        updated_data.append(data_by_sentence[sentence])
        seen.add(sentence)
    
    # Add any new sentences not in original list
    if result.sentence not in seen:
        updated_data.append(new_result)
    
    # Write back
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(updated_data, f, ensure_ascii=False, indent=2)
    
    print(f"Updated {filename}")


# ============================================================================
# Main
# ============================================================================

def run_tests(sentences: List[str], verbose: bool = False, show_details: bool = False) -> List[ComparisonResult]:
    """Run comparison tests on a list of sentences."""
    results = []
    
    for i, sentence in enumerate(sentences):
        if (i + 1) % 10 == 0:
            print(f"  Progress: {i+1}/{len(sentences)}", file=sys.stderr)
        
        result = compare_segmentations(sentence)
        results.append(result)
        print_result(result, verbose, show_details)
    
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
        "--details", "-d",
        action="store_true",
        help="Show per-segment details including dictionary IDs"
    )
    parser.add_argument(
        "--mismatches-only", "-m",
        action="store_true",
        help="Only show mismatches"
    )
    parser.add_argument(
        "--use-cache", "-u",
        action="store_true",
        default=True,
        help="Use cached ichiran results from results.json instead of calling Docker (default: enabled)"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable cache and always call Docker for ichiran results"
    )
    parser.add_argument(
        "--cache-file",
        type=str,
        default=ICHIRAN_CACHE_FILE,
        help=f"Cache file to use (default: {ICHIRAN_CACHE_FILE})"
    )
    
    args = parser.parse_args()
    
    # Cache is enabled by default - load it
    # If a sentence isn't in cache, it will still call ichiran normally
    global _use_ichiran_cache
    if args.no_cache:
        _use_ichiran_cache = False
    else:
        _use_ichiran_cache = True
        load_ichiran_cache(args.cache_file)
    
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
    results = run_tests(sentences, args.verbose, args.details)
    
    # Filter if needed
    if args.mismatches_only:
        results = [r for r in results if r.status == MatchStatus.MISMATCH]
    
    # Print summary
    print_summary(results)
    
    # Export results
    # For single sentence mode, use incremental update
    # For batch mode, export all results
    export_file = args.export if args.export else ICHIRAN_CACHE_FILE
    
    if args.sentence and len(results) == 1:
        # Single sentence mode - update only that sentence in the file
        update_single_result(results[0], export_file)
    else:
        # Batch mode - export all results
        export_results(results, export_file)
        
        # Also export mismatch.json and partial.json for easier debugging
        export_filtered_results(results)
    
    # Return exit code based on results
    mismatches = sum(1 for r in results if r.status == MatchStatus.MISMATCH)
    return 1 if mismatches > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
