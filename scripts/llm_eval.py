#!/usr/bin/env python3
"""
LLM-based accuracy evaluation for Himotoki.

Usage:
    python -m scripts.llm_eval --quick
    python -m scripts.llm_eval --sentence "猫が食べる"
    python -m scripts.llm_eval --export output/llm_results.json
"""
import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Resolve paths relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_DIR = PROJECT_ROOT / "data"

DEFAULT_RESULTS_FILE = str(OUTPUT_DIR / "llm_results.json")
DEFAULT_GOLDSET_FILE = str(DATA_DIR / "llm_goldset.json")


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)
# Cache a single Himotoki DB session and suffix initialization
_himotoki_session = None
_himotoki_suffixes_ready = False


def get_himotoki_session():
    """Return a ready-to-use Himotoki DB session with suffixes initialized."""
    global _himotoki_session, _himotoki_suffixes_ready
    from himotoki.db.connection import get_session, get_db_path
    from himotoki.suffixes import init_suffixes
    import himotoki

    db_path = get_db_path()
    if not db_path:
        raise RuntimeError(
            "Himotoki database not found. Set HIMOTOKI_DB or run init_db.py to build it."
        )

    if _himotoki_session is None:
        _himotoki_session = get_session(db_path)

    if not _himotoki_suffixes_ready:
        init_suffixes(_himotoki_session)
        himotoki.warm_up()
        _himotoki_suffixes_ready = True

    return _himotoki_session


@dataclass
class SegmentInfo:
    text: str
    kana: str = ""
    seq: Optional[int] = None
    score: int = 0
    is_compound: bool = False
    components: List[str] = field(default_factory=list)
    conj_type: Optional[str] = None
    conj_neg: bool = False
    conj_fml: bool = False
    source_text: Optional[str] = None
    pos: List[str] = field(default_factory=list)


@dataclass
class LLMScore:
    overall_score: float
    verdict: str
    dimensions: Dict[str, float]
    issues: List[str]
    notes: str = ""


@dataclass
class LLMResult:
    sentence: str
    segments: List[SegmentInfo]
    llm_score: LLMScore
    llm_model: str
    llm_prompt_version: str
    time_himotoki: float
    time_llm: float
LLM_PROMPT_VERSION = "v1"


def _extract_conj_info(word_info: dict) -> Tuple[Optional[str], bool, bool, Optional[str]]:
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
        reading = conj.get("reading", "")
        if reading:
            source = reading.split(" ")[0] if " " in reading else reading
    return conj_type, neg, fml, source


def _segments_from_himotoki_json(data: Any) -> List[SegmentInfo]:
    if not data or not data[0]:
        return []

    segments_data = data[0][0]
    segments = []

    for seg in segments_data:
        if len(seg) < 2:
            continue
        info = seg[1]

        if "compound" in info:
            component_texts = info.get("compound", [])
            components_info = info.get("components", [])
            full_text = info.get("text") or "".join(component_texts)

            conj_type = None
            neg = False
            fml = False
            source = None
            if components_info:
                last_comp = components_info[-1] if components_info else {}
                conj_type, neg, fml, source = _extract_conj_info(last_comp)
            else:
                conj_type, neg, fml, source = _extract_conj_info(info)

            kana_parts = [c.get("kana", "") for c in components_info]
            full_kana = "".join(kana_parts) if kana_parts else info.get("kana", "")

            segments.append(
                SegmentInfo(
                    text=full_text,
                    kana=full_kana,
                    seq=components_info[0].get("seq") if components_info else info.get("seq"),
                    score=info.get("score", 0),
                    is_compound=True,
                    components=component_texts,
                    conj_type=conj_type,
                    conj_neg=neg,
                    conj_fml=fml,
                    source_text=source,
                )
            )
            continue

        word_info = info
        if "alternative" in info and info["alternative"]:
            word_info = info["alternative"][0]

        conj_type, neg, fml, source = _extract_conj_info(word_info)

        pos_list = []
        for gloss in word_info.get("gloss", []):
            if "pos" in gloss:
                pos_list.append(gloss["pos"])

        segments.append(
            SegmentInfo(
                text=word_info.get("text", ""),
                kana=word_info.get("kana", ""),
                seq=word_info.get("seq"),
                score=word_info.get("score", 0),
                conj_type=conj_type,
                conj_neg=neg,
                conj_fml=fml,
                source_text=source,
                pos=pos_list[:3],
            )
        )

    return segments


def _serialize_segments(segments: List[SegmentInfo]) -> List[Dict[str, Any]]:
    return [asdict(seg) for seg in segments]


def _build_prompt(sentence: str, segments: List[SegmentInfo]) -> str:
    segments_payload = _serialize_segments(segments)
    return (
        "You are a strict evaluator of Japanese morphological analysis output. "
        "Assess the provided segmentation and linguistic features for correctness.\n\n"
        "Evaluate on these dimensions (0-5 each, 5 is best):\n"
        "- segmentation: token boundaries match correct Japanese parsing\n"
        "- reading: kana readings for tokens are correct\n"
        "- conjugation: conjugation type/neg/polite correctness\n"
        "- pos: part-of-speech tagging plausibility\n"
        "- dictionary_form: source/dictionary form correctness\n\n"
        "Return ONLY valid JSON with this schema:\n"
        "{\n"
        "  \"overall_score\": number (0-100),\n"
        "  \"verdict\": \"pass\" or \"fail\",\n"
        "  \"dimensions\": {\n"
        "     \"segmentation\": number,\n"
        "     \"reading\": number,\n"
        "     \"conjugation\": number,\n"
        "     \"pos\": number,\n"
        "     \"dictionary_form\": number\n"
        "  },\n"
        "  \"issues\": [string],\n"
        "  \"notes\": string\n"
        "}\n\n"
        "Sentence:\n"
        f"{sentence}\n\n"
        "Segments (JSON):\n"
        f"{json.dumps(segments_payload, ensure_ascii=False)}"
    )


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
    if text.startswith("json"):
        text = text[4:].strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM response")

    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON response: {e}") from e


class OpenAICompatClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 60.0):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "OpenAI client not installed. Install with: pip install -e \".[eval]\""
            ) from e

        self.model = model
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    def judge(self, prompt: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": "You are an expert Japanese NLP evaluator."},
            {"role": "user", "content": prompt},
        ]

        def _is_concurrency_limit(err: Exception) -> bool:
            name = err.__class__.__name__
            msg = str(err)
            return (
                name == "RateLimitError"
                or "concurrency_limit" in msg
                or "Too many concurrent requests" in msg
            )

        last_err: Optional[Exception] = None
        for attempt in range(5):
            try:
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=0,
                        response_format={"type": "json_object"},
                    )
                except TypeError:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=0,
                    )
                content = response.choices[0].message.content
                return _extract_json(content)
            except Exception as err:
                last_err = err
                if _is_concurrency_limit(err):
                    time.sleep(min(2**attempt, 8))
                    continue
                raise

        raise RuntimeError(f"LLM request failed after retries: {last_err}")


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout: float = 60.0):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def judge(self, prompt: str) -> Dict[str, Any]:
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:"
            f"generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {"temperature": 0},
        }
        data = json.dumps(payload).encode("utf-8")
        req = Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as e:
            raise RuntimeError(f"Gemini HTTP error {e.code}: {e.read().decode('utf-8')}") from e
        except URLError as e:
            raise RuntimeError(f"Gemini connection error: {e}") from e

        response = json.loads(raw)
        candidates = response.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise RuntimeError("Gemini returned empty content")
        content = parts[0].get("text", "")
        return _extract_json(content)


def _mock_judge(segments: List[SegmentInfo]) -> Dict[str, Any]:
    has_segments = bool(segments)
    base = 4.0 if has_segments else 1.0
    dimensions = {
        "segmentation": base,
        "reading": base,
        "conjugation": base,
        "pos": base,
        "dictionary_form": base,
    }
    overall = sum(dimensions.values()) / 25 * 100
    return {
        "overall_score": round(overall, 2),
        "verdict": "pass" if overall >= 70 else "fail",
        "dimensions": dimensions,
        "issues": [] if has_segments else ["No segments produced"],
        "notes": "Mock evaluation",
    }


def run_llm_eval(
    sentences: List[str],
    export_file: str,
    model: str,
    timeout: float,
    mock: bool,
    provider: str,
    openai_base: str,
    openai_key: str,
    concurrency: int,
    rpm: Optional[int],
    gemini_key: Optional[str],
    gemini_model: Optional[str],
) -> List[LLMResult]:
    from himotoki.output import segment_to_json

    results: List[LLMResult] = []
    if not mock:
        if provider == "openai":
            api_key = openai_key or "not-needed"
            client = OpenAICompatClient(
                base_url=openai_base, api_key=api_key, model=model, timeout=timeout
            )
        elif provider == "gemini":
            gemini_key = gemini_key or os.environ.get("GEMINI_API_KEY", "")
            gemini_model = gemini_model or os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
            if not gemini_key:
                raise RuntimeError("Missing GEMINI_API_KEY for Gemini provider")
            client = GeminiClient(api_key=gemini_key, model=gemini_model, timeout=timeout)
        else:
            raise RuntimeError(f"Unknown provider: {provider}")
    else:
        client = None

    session = get_himotoki_session()

    prepared: List[Dict[str, Any]] = []
    for idx, sentence in enumerate(sentences):
        if (idx + 1) % 10 == 0:
            print(f"  Segmenting: {idx+1}/{len(sentences)}", file=sys.stderr)

        t0 = time.time()
        raw = segment_to_json(session, sentence, limit=1)
        time_himotoki = time.time() - t0
        segments = _segments_from_himotoki_json([raw[0]] if raw else [])
        prepared.append(
            {
                "sentence": sentence,
                "segments": segments,
                "prompt": _build_prompt(sentence, segments),
                "time_himotoki": time_himotoki,
            }
        )

    rate_lock = Lock()
    last_request_at = {"t": 0.0}
    min_interval = 60.0 / rpm if rpm and rpm > 0 else 0.0

    def _wait_for_rate_limit() -> None:
        if min_interval <= 0:
            return
        with rate_lock:
            now = time.monotonic()
            wait_for = (last_request_at["t"] + min_interval) - now
            if wait_for > 0:
                time.sleep(wait_for)
            last_request_at["t"] = time.monotonic()

    def _judge_item(item: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.time()
        try:
            if mock:
                score_obj = _mock_judge(item["segments"])
            else:
                _wait_for_rate_limit()
                score_obj = client.judge(item["prompt"])
        except Exception as err:
            score_obj = {
                "overall_score": 0,
                "verdict": "fail",
                "dimensions": {},
                "issues": [f"LLM error: {err}"],
                "notes": "Evaluator error",
            }
        item["time_llm"] = time.time() - t0
        item["score_obj"] = score_obj
        return item

    if concurrency < 1:
        concurrency = 1

    if concurrency == 1:
        judged = []
        for idx, item in enumerate(prepared):
            if (idx + 1) % 10 == 0:
                print(f"  Judging: {idx+1}/{len(prepared)}", file=sys.stderr)
            judged.append(_judge_item(item))
    else:
        judged_map: Dict[int, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(_judge_item, item): idx for idx, item in enumerate(prepared)
            }
            completed = 0
            for future in as_completed(futures):
                idx = futures[future]
                judged_map[idx] = future.result()
                completed += 1
                if completed % 10 == 0 or completed == len(prepared):
                    print(f"  Judging: {completed}/{len(prepared)}", file=sys.stderr)
        judged = [judged_map[i] for i in range(len(prepared))]

    for item in judged:
        score_obj = item["score_obj"]
        llm_score = LLMScore(
            overall_score=float(score_obj.get("overall_score", 0)),
            verdict=str(score_obj.get("verdict", "fail")),
            dimensions=score_obj.get("dimensions", {}),
            issues=score_obj.get("issues", []),
            notes=str(score_obj.get("notes", "")),
        )

        results.append(
            LLMResult(
                sentence=item["sentence"],
                segments=item["segments"],
                llm_score=llm_score,
                llm_model=model,
                llm_prompt_version=LLM_PROMPT_VERSION,
                time_himotoki=item["time_himotoki"],
                time_llm=item["time_llm"],
            )
        )

    export_payload = [
        {
            "sentence": r.sentence,
            "segments": _serialize_segments(r.segments),
            "llm_score": asdict(r.llm_score),
            "llm_model": r.llm_model,
            "llm_prompt_version": r.llm_prompt_version,
            "time_himotoki": r.time_himotoki,
            "time_llm": r.time_llm,
        }
        for r in results
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(export_file, "w", encoding="utf-8") as f:
        json.dump(export_payload, f, ensure_ascii=False, indent=2)

    print(f"Exported {len(results)} results to {export_file}")
    return results


# ==========================================================================
# Main
# ==========================================================================

def main():
    _load_env_file(PROJECT_ROOT / ".env")
    try:
        from scripts.test_sentences import TEST_SENTENCES_500, QUICK_SENTENCES_50
    except ModuleNotFoundError:
        from test_sentences import TEST_SENTENCES_500, QUICK_SENTENCES_50

    parser = argparse.ArgumentParser(description="LLM-based evaluation for Himotoki")
    parser.add_argument("--quick", "-q", action="store_true", help="Run quick subset")
    parser.add_argument("--sentence", "-s", type=str, help="Evaluate a single sentence")
    parser.add_argument("--onesentence", type=str, help="Evaluate a single sentence")
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        choices=["common_500"],
        help="Evaluate a category",
    )
    parser.add_argument("--export", "-e", type=str, default=DEFAULT_RESULTS_FILE)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument(
        "--provider",
        type=str,
        default=os.environ.get("LLM_PROVIDER", "openai"),
        choices=["openai", "gemini"],
        help="LLM provider: openai or gemini",
    )
    parser.add_argument(
        "--openai-base",
        type=str,
        default=os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:3030/v1"),
    )
    parser.add_argument(
        "--openai-key",
        type=str,
        default=os.environ.get("OPENAI_API_KEY", ""),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("COPILOT_TIMEOUT", "60")),
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(os.environ.get("LLM_CONCURRENCY", "1")),
        help="Number of concurrent LLM requests (default: 1)",
    )
    parser.add_argument(
        "--rpm",
        type=int,
        default=None,
        help="Max requests per minute (defaults: 2 for openai, 1 for gemini)",
    )
    parser.add_argument("--mock", action="store_true", help="Run without API calls")
    parser.add_argument(
        "--gemini-key",
        type=str,
        default=os.environ.get("GEMINI_API_KEY", ""),
        help="API key for Gemini provider",
    )
    parser.add_argument(
        "--gemini-model",
        type=str,
        default=os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview"),
        help="Model for Gemini provider",
    )

    args = parser.parse_args()

    if args.onesentence:
        sentences = [args.onesentence]
    elif args.sentence:
        sentences = [args.sentence]
    elif args.quick:
        sentences = QUICK_SENTENCES_50
    elif args.category:
        sentences = TEST_SENTENCES_500
    else:
        sentences = TEST_SENTENCES_500

    print("=" * 60)
    print("Himotoki LLM Evaluation")
    print("=" * 60)
    print(f"Sentences: {len(sentences)}")
    model_env = os.environ.get("LLM_MODEL")
    if args.model is not None:
        model = args.model
    elif model_env:
        model = model_env
    else:
        model = "gemini-3-flash-preview" if args.provider == "gemini" else "gpt-5-mini"

    print(f"Model: {model}")
    print(f"Provider: {args.provider}")
    if args.mock:
        print("Mode: mock (no API calls)")

    rpm_env = os.environ.get("LLM_RPM")
    if args.rpm is not None:
        rpm = args.rpm
    elif rpm_env:
        rpm = int(rpm_env)
    else:
        rpm = 1 if args.provider == "gemini" else 2

    run_llm_eval(
        sentences=sentences,
        export_file=args.export,
        model=model,
        timeout=args.timeout,
        mock=args.mock,
        provider=args.provider,
        openai_base=args.openai_base,
        openai_key=args.openai_key,
        concurrency=args.concurrency,
        rpm=rpm,
        gemini_key=args.gemini_key,
        gemini_model=args.gemini_model,
    )


if __name__ == "__main__":
    sys.exit(main())
