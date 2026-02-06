#!/usr/bin/env python3
"""
LLM-based accuracy evaluation for Himotoki.

Usage:
    python -m scripts.llm_eval --quick
    python -m scripts.llm_eval --sentence "猫が食べる"
    python -m scripts.llm_eval --export output/llm_results.json
"""
# Force IPv4 BEFORE any network library imports to avoid IPv6 timeout issues
import socket as _socket
_orig_getaddrinfo = _socket.getaddrinfo
def _ipv4_only_getaddrinfo(*args, **kwargs):
    responses = _orig_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == _socket.AF_INET] or responses
_socket.getaddrinfo = _ipv4_only_getaddrinfo

# Also patch httpcore's cached socket reference
import httpcore._backends.sync as _httpcore_sync
_httpcore_sync.socket.getaddrinfo = _ipv4_only_getaddrinfo

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
DEFAULT_SKIP_FILE = str(DATA_DIR / "llm_skip.json")
DEFAULT_HISTORY_FILE = str(OUTPUT_DIR / "llm_history.jsonl")
DEFAULT_BASELINE_FILE = str(OUTPUT_DIR / "llm_baseline.json")
DEFAULT_TRIAGE_LOCK_FILE = str(DATA_DIR / "llm_triage_lock.json")


def _load_skip_list(skip_file: str) -> Dict[str, str]:
    """Load skip list from JSON file. Returns dict of index -> reason."""
    skip_path = Path(skip_file)
    if not skip_path.exists():
        return {}
    try:
        with open(skip_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("skipped", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def _save_skip_list(skip_file: str, skipped: Dict[str, str]) -> None:
    """Save skip list to JSON file."""
    skip_path = Path(skip_file)
    skip_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "_comment": "Entries to skip in LLM evaluation. Add entry numbers with optional reason.",
        "skipped": skipped,
    }
    with open(skip_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def skip_entry(results_file: str, skip_file: str, entry_index: int, reason: str = "") -> int:
    """Add an entry to the skip list."""
    results_path = Path(results_file)
    if not results_path.exists():
        print(f"Results file not found: {results_file}", file=sys.stderr)
        return 1

    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    if entry_index < 1 or entry_index > len(results):
        print(f"Invalid entry index: #{entry_index}. Valid range: #1 to #{len(results)}", file=sys.stderr)
        return 1

    entry = results[entry_index - 1]
    skipped = _load_skip_list(skip_file)
    
    key = str(entry_index)
    if key in skipped:
        print(f"Entry #{entry_index} is already skipped.")
        print(f"  Reason: {skipped[key]}")
        return 0

    skipped[key] = reason or "No reason provided"
    _save_skip_list(skip_file, skipped)
    
    print(f"Skipped entry #{entry_index}:")
    print(f"  Sentence: {entry['sentence'][:60]}...")
    print(f"  Reason: {skipped[key]}")
    return 0


def unskip_entry(skip_file: str, entry_index: int) -> int:
    """Remove an entry from the skip list."""
    skipped = _load_skip_list(skip_file)
    key = str(entry_index)
    
    if key not in skipped:
        print(f"Entry #{entry_index} is not in the skip list.")
        return 0
    
    del skipped[key]
    _save_skip_list(skip_file, skipped)
    print(f"Unskipped entry #{entry_index}")
    return 0


def list_skipped(skip_file: str, results_file: str) -> int:
    """List all skipped entries."""
    skipped = _load_skip_list(skip_file)
    
    if not skipped:
        print("No entries are skipped.")
        return 0
    
    results_path = Path(results_file)
    results = []
    if results_path.exists():
        with open(results_path, "r", encoding="utf-8") as f:
            results = json.load(f)
    
    print(f"Skipped entries ({len(skipped)}):")
    for key, reason in sorted(skipped.items(), key=lambda x: int(x[0])):
        idx = int(key) - 1
        sentence = results[idx]["sentence"][:50] + "..." if idx < len(results) else "?"
        print(f"  #{key}: {sentence}")
        print(f"       Reason: {reason}")
    
    return 0


# ============================================================================
# Triage Management (Multi-Agent Support)
# ============================================================================

def _load_triage_lock(lock_file: str) -> Dict[str, Any]:
    """Load triage lock file. Returns dict with 'reserved' and 'issued' entries."""
    lock_path = Path(lock_file)
    if not lock_path.exists():
        return {"reserved": {}, "issued": {}}
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "reserved": data.get("reserved", {}),
            "issued": data.get("issued", {}),
        }
    except (json.JSONDecodeError, KeyError):
        return {"reserved": {}, "issued": {}}


def _save_triage_lock(lock_file: str, lock_data: Dict[str, Any]) -> None:
    """Save triage lock file."""
    lock_path = Path(lock_file)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as f:
        json.dump(lock_data, f, ensure_ascii=False, indent=2)


def reserve_entry(lock_file: str, entry_index: int, agent_id: str = "") -> bool:
    """Reserve an entry for triage. Returns True if successful, False if already reserved."""
    from datetime import datetime
    
    lock_data = _load_triage_lock(lock_file)
    key = str(entry_index)
    
    if key in lock_data["reserved"]:
        # Already reserved by someone else
        return False
    
    if key in lock_data["issued"]:
        # Already has an issue created
        return False
    
    lock_data["reserved"][key] = {
        "agent": agent_id or "unknown",
        "timestamp": datetime.now().isoformat(),
    }
    _save_triage_lock(lock_file, lock_data)
    return True


def release_entry(lock_file: str, entry_index: int) -> None:
    """Release a reserved entry."""
    lock_data = _load_triage_lock(lock_file)
    key = str(entry_index)
    if key in lock_data["reserved"]:
        del lock_data["reserved"][key]
        _save_triage_lock(lock_file, lock_data)


def mark_issued(lock_file: str, entry_index: int, issue_id: str) -> None:
    """Mark an entry as having an issue created."""
    from datetime import datetime
    
    lock_data = _load_triage_lock(lock_file)
    key = str(entry_index)
    
    # Remove from reserved if present
    if key in lock_data["reserved"]:
        del lock_data["reserved"][key]
    
    lock_data["issued"][key] = {
        "issue_id": issue_id,
        "timestamp": datetime.now().isoformat(),
    }
    _save_triage_lock(lock_file, lock_data)


def triage_status(results_file: str, skip_file: str, lock_file: str) -> int:
    """Show triage pipeline status."""
    results_path = Path(results_file)
    if not results_path.exists():
        print(f"Results file not found: {results_path}")
        return 1
    
    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)
    
    skipped = _load_skip_list(skip_file)
    lock_data = _load_triage_lock(lock_file)
    
    total = len(results)
    passed = 0
    failed = 0
    skipped_count = len(skipped)
    reserved_count = len(lock_data["reserved"])
    issued_count = len(lock_data["issued"])
    
    untriaged = []
    
    for idx, r in enumerate(results):
        entry_idx = idx + 1
        key = str(entry_idx)
        llm = r.get("llm_score", {})
        verdict = llm.get("verdict", "unknown")
        
        if verdict == "pass":
            passed += 1
        elif verdict == "fail":
            failed += 1
            # Check if this failed entry needs triage
            if key not in skipped and key not in lock_data["issued"] and key not in lock_data["reserved"]:
                untriaged.append(entry_idx)
    
    print("=" * 60)
    print("Triage Pipeline Status")
    print("=" * 60)
    print()
    print(f"Total entries:     {total}")
    print(f"  Passed:          {passed}")
    print(f"  Failed:          {failed}")
    print()
    print(f"Triage status:")
    print(f"  Skipped:         {skipped_count}")
    print(f"  Issues created:  {issued_count}")
    print(f"  Reserved:        {reserved_count}")
    print(f"  Untriaged:       {len(untriaged)}")
    print()
    
    if untriaged:
        print(f"Next entries to triage: {untriaged[:10]}")
        if len(untriaged) > 10:
            print(f"  ... and {len(untriaged) - 10} more")
    else:
        print("All failed entries have been triaged!")
    
    if lock_data["reserved"]:
        print()
        print("Currently reserved:")
        for key, info in lock_data["reserved"].items():
            agent = info.get("agent", "?")
            ts = info.get("timestamp", "?")[:16]
            print(f"  #{key}: by {agent} at {ts}")
    
    return 0


def check_issue_exists(entry_index: int, label: str = "llm-fail") -> Optional[str]:
    """Check if a beads issue already exists for this entry. Returns issue ID if found."""
    import subprocess
    
    try:
        # Search for issues with matching title pattern
        result = subprocess.run(
            ["bd", "search", f"LLM eval #{entry_index}:"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Parse first line to get issue ID
            lines = result.stdout.strip().split("\n")
            if lines:
                # Assume format: "bd-xxx: title..."
                first = lines[0].strip()
                if first.startswith("bd-"):
                    issue_id = first.split(":")[0].strip()
                    return issue_id
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    return None


def export_to_beads(results_file: str, skip_file: str, dry_run: bool = False, label: str = "llm-fail", lock_file: str = DEFAULT_TRIAGE_LOCK_FILE, check_existing: bool = True) -> int:
    """Export failed entries to beads issues using 'bd create'.
    
    Creates one issue per failed entry (excluding skipped).
    """
    import subprocess
    
    results_path = Path(results_file)
    if not results_path.exists():
        print(f"Results file not found: {results_path}")
        return 1
    
    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)
    
    skipped = _load_skip_list(skip_file)
    
    # Find failed entries (not skipped)
    failed_entries = []
    for idx, r in enumerate(results):
        entry_idx = idx + 1
        if str(entry_idx) in skipped:
            continue
        llm = r.get("llm_score", {})
        if llm.get("verdict") == "fail":
            failed_entries.append((entry_idx, r))
    
    if not failed_entries:
        print("No failed entries to export (all passed or skipped).")
        return 0
    
    print(f"Found {len(failed_entries)} failed entries to export as beads issues.")
    if dry_run:
        print("DRY RUN - would create issues for:")
        for entry_idx, r in failed_entries:
            sentence = r.get("sentence", "")[:40]
            print(f"  #{entry_idx}: {sentence}...")
        return 0
    
    created = 0
    skipped_existing = 0
    for entry_idx, r in failed_entries:
        # Check if already issued (in lock file or bd search)
        lock_data = _load_triage_lock(lock_file)
        if str(entry_idx) in lock_data.get("issued", {}):
            skipped_existing += 1
            continue
        
        if check_existing:
            existing_id = check_issue_exists(entry_idx, label)
            if existing_id:
                print(f"  #{entry_idx}: Already has issue {existing_id}, skipping")
                mark_issued(lock_file, entry_idx, existing_id)
                skipped_existing += 1
                continue
        
        sentence = r.get("sentence", "")
        llm = r.get("llm_score", {})
        dims = llm.get("dimensions", {})
        issues = llm.get("issues", [])
        notes = llm.get("notes", "")
        
        # Build issue title and body
        title = f"LLM eval #{entry_idx}: {sentence[:30]}..."
        
        # Find the worst dimension
        dim_scores = {
            "segmentation": dims.get("segmentation", 5) or 5,
            "reading": dims.get("reading", 5) or 5,
            "conjugation": dims.get("conjugation", 5) or 5,
            "pos": dims.get("pos", 5) or 5,
            "dictionary_form": dims.get("dictionary_form", 5) or 5,
        }
        worst_dim = min(dim_scores, key=dim_scores.get)
        
        # Build segments display for the issue
        segments_text = ""
        for seg in r.get("segments", []):
            text = seg.get("text", "")
            kana = seg.get("kana", "")
            pos = ", ".join(seg.get("pos", [])) if seg.get("pos") else "-"
            source = seg.get("source_text", "") or "-"
            segments_text += f"  - `{text}` ({kana}) - POS: {pos}, Source: {source}\n"
        
        body = f"""## Problem

LLM evaluation failed for sentence #{entry_idx}.

**Worst dimension:** {worst_dim} ({dims.get(worst_dim, '?')}/5)

## Sentence

`{sentence}`

## Current Segmentation

{segments_text}

## Dimension Scores

- Segmentation: {dims.get("segmentation", "-")}/5
- Reading: {dims.get("reading", "-")}/5
- Conjugation: {dims.get("conjugation", "-")}/5
- POS: {dims.get("pos", "-")}/5
- Dictionary Form: {dims.get("dictionary_form", "-")}/5

## Issues Found by LLM

{chr(10).join("- " + issue for issue in issues) if issues else "None"}

## Notes

{notes or "None"}

## Code Locations

*TODO: Use chunkhound semantic search to find relevant code:*
- For segmentation issues: search for splitting logic in `himotoki/segment.py`, `himotoki/splits.py`
- For reading issues: search for reading assignment in `himotoki/lookup.py`
- For conjugation issues: search in `himotoki/suffixes.py`, `himotoki/conjugation_hints.py`
- For POS issues: search in `himotoki/lookup.py`, `himotoki/output.py`

## How to Verify

```bash
python scripts/check_segments.py {entry_idx}
python scripts/llm_eval.py --rescore {entry_idx}
```
"""
        
        # Run bd create
        cmd = ["bd", "create", title, "--description", body, "--labels", label]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            issue_id = result.stdout.strip()
            print(f"  Created {issue_id} for #{entry_idx}")
            mark_issued(lock_file, entry_idx, issue_id)
            created += 1
        except subprocess.CalledProcessError as e:
            print(f"  Failed to create issue for #{entry_idx}: {e.stderr}")
    
    print(f"\nCreated {created}/{len(failed_entries)} issues.")
    if skipped_existing > 0:
        print(f"Skipped {skipped_existing} (already have issues).")
    return 0


def save_baseline(results_file: str, baseline_file: str) -> int:
    """Save current results as baseline for future comparison."""
    import shutil
    
    results_path = Path(results_file)
    baseline_path = Path(baseline_file)
    
    if not results_path.exists():
        print(f"Results file not found: {results_path}")
        return 1
    
    shutil.copy2(results_path, baseline_path)
    
    # Calculate summary stats
    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)
    
    passed = sum(1 for r in results if r.get("llm_score", {}).get("verdict") == "pass")
    failed = sum(1 for r in results if r.get("llm_score", {}).get("verdict") == "fail")
    
    print(f"Baseline saved: {baseline_path}")
    print(f"  Total: {len(results)}, Passed: {passed}, Failed: {failed}")
    return 0


def compare_baseline(results_file: str, baseline_file: str, skip_file: str) -> int:
    """Compare current results against saved baseline."""
    results_path = Path(results_file)
    baseline_path = Path(baseline_file)
    
    if not results_path.exists():
        print(f"Results file not found: {results_path}")
        return 1
    
    if not baseline_path.exists():
        print(f"Baseline file not found: {baseline_path}")
        print("Run with --save-baseline first to create a baseline.")
        return 1
    
    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)
    
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)
    
    skipped = _load_skip_list(skip_file)
    
    # Compare entry by entry
    improved = []
    regressed = []
    unchanged = []
    
    for idx, (curr, base) in enumerate(zip(results, baseline)):
        entry_idx = idx + 1
        if str(entry_idx) in skipped:
            continue
        
        curr_score = curr.get("llm_score", {}).get("overall_score") or 0
        base_score = base.get("llm_score", {}).get("overall_score") or 0
        curr_verdict = curr.get("llm_score", {}).get("verdict", "unknown")
        base_verdict = base.get("llm_score", {}).get("verdict", "unknown")
        
        if curr_score > base_score:
            improved.append((entry_idx, curr.get("sentence", "")[:30], base_score, curr_score, base_verdict, curr_verdict))
        elif curr_score < base_score:
            regressed.append((entry_idx, curr.get("sentence", "")[:30], base_score, curr_score, base_verdict, curr_verdict))
        else:
            unchanged.append(entry_idx)
    
    print("=" * 60)
    print("Baseline Comparison")
    print("=" * 60)
    
    # Summary
    curr_passed = sum(1 for r in results if r.get("llm_score", {}).get("verdict") == "pass")
    curr_failed = sum(1 for r in results if r.get("llm_score", {}).get("verdict") == "fail")
    base_passed = sum(1 for r in baseline if r.get("llm_score", {}).get("verdict") == "pass")
    base_failed = sum(1 for r in baseline if r.get("llm_score", {}).get("verdict") == "fail")
    
    print(f"\nSummary:")
    print(f"  Baseline: {base_passed} passed, {base_failed} failed")
    print(f"  Current:  {curr_passed} passed, {curr_failed} failed")
    print(f"  ΔPass: {curr_passed - base_passed:+d}")
    
    if improved:
        print(f"\n✅ Improved ({len(improved)}):")
        for entry_idx, sentence, old, new, old_v, new_v in improved[:10]:
            verdict_change = f" ({old_v}→{new_v})" if old_v != new_v else ""
            print(f"  #{entry_idx}: {sentence}... ({old}→{new}){verdict_change}")
        if len(improved) > 10:
            print(f"  ... and {len(improved) - 10} more")
    
    if regressed:
        print(f"\n❌ Regressed ({len(regressed)}):")
        for entry_idx, sentence, old, new, old_v, new_v in regressed:
            verdict_change = f" ({old_v}→{new_v})" if old_v != new_v else ""
            print(f"  #{entry_idx}: {sentence}... ({old}→{new}){verdict_change}")
    
    print(f"\n📊 Unchanged: {len(unchanged)}")
    
    return 1 if regressed else 0


def log_history(results: List[dict], history_file: str, skip_file: str, model: str, provider: str) -> None:
    """Append run summary to history JSONL file."""
    from datetime import datetime
    
    skipped = _load_skip_list(skip_file)
    
    # Calculate stats
    total = len(results)
    skipped_count = len(skipped)
    active_results = [r for idx, r in enumerate(results) if str(idx + 1) not in skipped]
    passed = sum(1 for r in active_results if r.get("llm_score", {}).get("verdict") == "pass")
    failed = sum(1 for r in active_results if r.get("llm_score", {}).get("verdict") == "fail")
    
    # Dimension averages
    dim_totals = {"segmentation": 0, "reading": 0, "conjugation": 0, "pos": 0, "dictionary_form": 0}
    for r in active_results:
        dims = r.get("llm_score", {}).get("dimensions", {})
        for dim in dim_totals:
            dim_totals[dim] += dims.get(dim, 0) or 0
    
    n = len(active_results) or 1
    dim_avgs = {dim: round(total / n, 2) for dim, total in dim_totals.items()}
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "provider": provider,
        "total": total,
        "skipped": skipped_count,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / (passed + failed) * 100, 1) if (passed + failed) > 0 else 0,
        "dimension_avgs": dim_avgs,
    }
    
    history_path = Path(history_file)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    print(f"History logged to {history_path}")


def show_history(history_file: str, limit: int = 10) -> int:
    """Show recent run history."""
    history_path = Path(history_file)
    
    if not history_path.exists():
        print(f"No history file found: {history_path}")
        print("Run an evaluation first to generate history.")
        return 0
    
    # Read all entries
    entries = []
    with open(history_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    
    if not entries:
        print("History file is empty.")
        return 0
    
    print("=" * 60)
    print("LLM Evaluation History")
    print("=" * 60)
    print()
    
    # Show recent entries
    for entry in entries[-limit:]:
        ts = entry.get("timestamp", "?")[:16].replace("T", " ")
        model = entry.get("model", "?")[:20]
        passed = entry.get("passed", 0)
        failed = entry.get("failed", 0)
        pass_rate = entry.get("pass_rate", 0)
        print(f"  {ts}  {model:<20}  Pass: {passed}  Fail: {failed}  Rate: {pass_rate}%")
    
    print()
    print(f"Total entries: {len(entries)}")
    return 0


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
        # Skip warm_up() for faster startup - not needed for individual rescoring
        # himotoki.warm_up()
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
        import subprocess
        
        # Use v1alpha for gemini-3 models, v1beta for others
        api_version = "v1alpha" if "gemini-3" in self.model else "v1beta"
        endpoint = (
            f"https://generativelanguage.googleapis.com/{api_version}/models/{self.model}:"
            f"generateContent?key={self.api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 1.0,
                "maxOutputTokens": 1024,
                # Minimal thinking for fastest response
                "thinking_config": {"thinking_level": "MINIMAL"},
            },
        })
        
        # Use curl subprocess - most reliable on this system
        result = subprocess.run(
            [
                "curl", "-s", "--max-time", str(int(self.timeout)),
                "-X", "POST", endpoint,
                "-H", "Content-Type: application/json",
                "-d", payload,
            ],
            capture_output=True,
            text=True,
            timeout=self.timeout + 5,
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"curl failed: {result.stderr}")
        
        response = json.loads(result.stdout)

        candidates = response.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {result.stdout[:200]}")
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


def _build_rescore_prompt(sentence: str, old_segments: List[SegmentInfo], old_score: dict, new_segments: List[SegmentInfo]) -> str:
    """Build prompt for rescoring after a fix."""
    old_payload = _serialize_segments(old_segments)
    new_payload = _serialize_segments(new_segments)
    old_issues = old_score.get("issues", [])
    old_notes = old_score.get("notes", "")
    
    return (
        "You are a strict evaluator of Japanese morphological analysis output. "
        "A bug was reported in the previous analysis, and this is the FIXED output. "
        "Your task is to verify if the issues have been resolved.\n\n"
        "## Previous Issues Reported:\n"
        f"{chr(10).join('- ' + issue for issue in old_issues) if old_issues else 'None specified'}\n"
        f"\nPrevious Notes: {old_notes}\n\n"
        "## Previous Segmentation (with issues):\n"
        f"{json.dumps(old_payload, ensure_ascii=False, indent=2)}\n\n"
        "## NEW Segmentation (after fix):\n"
        f"{json.dumps(new_payload, ensure_ascii=False, indent=2)}\n\n"
        "Evaluate the NEW segmentation on these dimensions (0-5 each, 5 is best):\n"
        "- segmentation: token boundaries match correct Japanese parsing\n"
        "- reading: kana readings for tokens are correct\n"
        "- conjugation: conjugation type/neg/polite correctness\n"
        "- pos: part-of-speech tagging plausibility\n"
        "- dictionary_form: source/dictionary form correctness\n\n"
        "In your notes, specifically mention whether the previously reported issues have been fixed.\n\n"
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
        f"{sentence}"
    )


def rescore_entry(
    results_file: str,
    entry_index: int,
    model: str,
    timeout: float,
    provider: str,
    openai_base: str,
    openai_key: str,
    gemini_key: Optional[str],
    gemini_model: Optional[str],
) -> int:
    """Re-score a specific entry after a fix, comparing old vs new segmentation."""
    from himotoki.output import segment_to_json
    
    results_path = Path(results_file)
    if not results_path.exists():
        print(f"Results file not found: {results_file}", file=sys.stderr)
        return 1

    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    # Validate index
    if entry_index < 1 or entry_index > len(results):
        print(f"Invalid entry index: #{entry_index}. Valid range: #1 to #{len(results)}", file=sys.stderr)
        return 1

    idx = entry_index - 1  # Convert to 0-based
    entry = results[idx]
    sentence = entry["sentence"]
    old_segments = [SegmentInfo(**seg) for seg in entry.get("segments", [])]
    old_score = entry.get("llm_score", {})

    print(f"Rescoring entry #{entry_index}:")
    print(f"  Sentence: {sentence}")
    print(f"  Previous verdict: {old_score.get('verdict', 'unknown')} ({old_score.get('overall_score', 0)})")

    # Re-run segmentation with current Himotoki
    session = get_himotoki_session()
    t0 = time.time()
    raw = segment_to_json(session, sentence, limit=1)
    time_himotoki = time.time() - t0
    new_segments = _segments_from_himotoki_json([raw[0]] if raw else [])

    print(f"  Re-segmented in {time_himotoki:.3f}s")

    # Check if segmentation actually changed
    old_texts = [s.text for s in old_segments]
    new_texts = [s.text for s in new_segments]
    if old_texts == new_texts:
        print("  Note: Segmentation output is identical to before.")
    else:
        print(f"  Segmentation changed: {old_texts} -> {new_texts}")

    # Build client
    if provider == "openai":
        api_key = openai_key or "not-needed"
        client = OpenAICompatClient(
            base_url=openai_base, api_key=api_key, model=model, timeout=timeout
        )
    elif provider == "gemini":
        gemini_key = gemini_key or os.environ.get("GEMINI_API_KEY", "")
        gemini_model = gemini_model or os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
        if not gemini_key:
            raise RuntimeError("Missing GEMINI_API_KEY for Gemini provider")
        client = GeminiClient(api_key=gemini_key, model=gemini_model, timeout=timeout)
    else:
        raise RuntimeError(f"Unknown provider: {provider}")

    # Build rescore prompt and call LLM
    prompt = _build_rescore_prompt(sentence, old_segments, old_score, new_segments)
    
    print("  Calling LLM for rescore...")
    t0 = time.time()
    try:
        score_obj = client.judge(prompt)
    except Exception as err:
        print(f"  LLM error: {err}", file=sys.stderr)
        return 1
    time_llm = time.time() - t0

    new_verdict = score_obj.get("verdict", "fail")
    new_overall = score_obj.get("overall_score", 0)
    print(f"  New verdict: {new_verdict} ({new_overall})")
    print(f"  LLM time: {time_llm:.2f}s")
    
    if score_obj.get("notes"):
        print(f"  Notes: {score_obj['notes']}")

    # Update entry in results
    results[idx]["segments"] = _serialize_segments(new_segments)
    results[idx]["llm_score"] = {
        "overall_score": float(new_overall),
        "verdict": str(new_verdict),
        "dimensions": score_obj.get("dimensions", {}),
        "issues": score_obj.get("issues", []),
        "notes": str(score_obj.get("notes", "")),
    }
    results[idx]["time_himotoki"] = time_himotoki
    results[idx]["time_llm"] = time_llm
    results[idx]["llm_model"] = model

    # Save updated results
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nUpdated entry #{entry_index} in {results_file}")
    
    # Skip interactive prompt for rescore - user can run llm_report.py manually
    return 0


def retry_failed_eval(
    results_file: str,
    model: str,
    timeout: float,
    provider: str,
    openai_base: str,
    openai_key: str,
    concurrency: int,
    rpm: Optional[int],
    gemini_key: Optional[str],
    gemini_model: Optional[str],
) -> int:
    """Re-run LLM scoring for failed entries in existing results file."""
    results_path = Path(results_file)
    if not results_path.exists():
        print(f"Results file not found: {results_file}", file=sys.stderr)
        return 1

    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    # Find entries that failed due to LLM errors (not genuine analysis failures)
    failed_indices = []
    for idx, r in enumerate(results):
        llm_score = r.get("llm_score", {})
        issues = llm_score.get("issues", [])
        # Retry if any issue mentions LLM error or if overall_score is 0 with error notes
        has_llm_error = any("LLM error" in issue for issue in issues)
        has_evaluator_error = llm_score.get("notes") == "Evaluator error"
        if has_llm_error or has_evaluator_error:
            failed_indices.append(idx)

    if not failed_indices:
        print("No LLM errors found to retry.")
        return 0

    print(f"Found {len(failed_indices)} entries with LLM errors to retry.")

    # Build client
    if provider == "openai":
        api_key = openai_key or "not-needed"
        client = OpenAICompatClient(
            base_url=openai_base, api_key=api_key, model=model, timeout=timeout
        )
    elif provider == "gemini":
        gemini_key = gemini_key or os.environ.get("GEMINI_API_KEY", "")
        gemini_model = gemini_model or os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
        if not gemini_key:
            raise RuntimeError("Missing GEMINI_API_KEY for Gemini provider")
        client = GeminiClient(api_key=gemini_key, model=gemini_model, timeout=timeout)
    else:
        raise RuntimeError(f"Unknown provider: {provider}")

    # Prepare items for retry
    prepared = []
    for idx in failed_indices:
        r = results[idx]
        segments = [SegmentInfo(**seg) for seg in r.get("segments", [])]
        prompt = _build_prompt(r["sentence"], segments)
        prepared.append({
            "idx": idx,
            "sentence": r["sentence"],
            "segments": segments,
            "prompt": prompt,
        })

    # Rate limiting
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

    def _retry_item(item: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.time()
        try:
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

    # Execute retries
    if concurrency < 1:
        concurrency = 1

    if concurrency == 1:
        retried = []
        for i, item in enumerate(prepared):
            print(f"  Retrying: {i+1}/{len(prepared)}", file=sys.stderr)
            retried.append(_retry_item(item))
    else:
        retried_map: Dict[int, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(_retry_item, item): i for i, item in enumerate(prepared)
            }
            completed = 0
            for future in as_completed(futures):
                i = futures[future]
                retried_map[i] = future.result()
                completed += 1
                if completed % 10 == 0 or completed == len(prepared):
                    print(f"  Retrying: {completed}/{len(prepared)}", file=sys.stderr)
        retried = [retried_map[i] for i in range(len(prepared))]

    # Update results in place
    success_count = 0
    for item in retried:
        idx = item["idx"]
        score_obj = item["score_obj"]
        results[idx]["llm_score"] = {
            "overall_score": float(score_obj.get("overall_score", 0)),
            "verdict": str(score_obj.get("verdict", "fail")),
            "dimensions": score_obj.get("dimensions", {}),
            "issues": score_obj.get("issues", []),
            "notes": str(score_obj.get("notes", "")),
        }
        results[idx]["time_llm"] = item["time_llm"]
        results[idx]["llm_model"] = model
        
        if score_obj.get("notes") != "Evaluator error":
            success_count += 1

    # Save updated results
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Retried {len(failed_indices)} entries, {success_count} succeeded.")
    print(f"Updated {results_file}")
    
    _prompt_generate_report(results_file)
    return 0


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
            gemini_model = gemini_model or os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
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
    
    _prompt_generate_report(export_file)
    return results


def _prompt_generate_report(results_file: str) -> None:
    """Prompt user to generate HTML report."""
    try:
        response = input("\nGenerate HTML report? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    
    if response in ("", "y", "yes"):
        import subprocess
        report_script = PROJECT_ROOT / "scripts" / "llm_report.py"
        result = subprocess.run(
            [sys.executable, str(report_script), "-i", results_file],
            cwd=PROJECT_ROOT,
        )
        if result.returncode == 0:
            report_path = OUTPUT_DIR / "llm_report.html"
            print(f"\nReport generated: {report_path}")
            # Try to open in browser
            try:
                import webbrowser
                webbrowser.open(f"file://{report_path}")
            except Exception:
                pass


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
        default=os.environ.get("LLM_PROVIDER", "gemini"),
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
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry only entries with LLM errors in existing results file",
    )
    parser.add_argument(
        "--rescore",
        type=str,
        metavar="INDEX",
        help="Rescore entry(ies) after fixing a bug (e.g., --rescore 5 or --rescore '5,12,47')",
    )
    parser.add_argument(
        "--skip",
        type=str,
        metavar="INDEX",
        help="Add entry to skip list (e.g., --skip 5 --reason 'known issue')",
    )
    parser.add_argument(
        "--unskip",
        type=str,
        metavar="INDEX",
        help="Remove entry from skip list",
    )
    parser.add_argument(
        "--list-skipped",
        action="store_true",
        help="List all skipped entries",
    )
    parser.add_argument(
        "--reason",
        type=str,
        default="",
        help="Reason for skipping (used with --skip)",
    )
    parser.add_argument(
        "--export-issues",
        action="store_true",
        help="Export failed entries to beads issues",
    )
    parser.add_argument(
        "--issue-label",
        type=str,
        default="llm-fail",
        help="Label to apply to created issues (default: llm-fail)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes (used with --export-issues)",
    )
    parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="Save current results as baseline for future comparison",
    )
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Compare current results against saved baseline",
    )
    parser.add_argument(
        "--baseline-file",
        type=str,
        default=DEFAULT_BASELINE_FILE,
        help="Path to baseline file (default: output/llm_baseline.json)",
    )
    parser.add_argument(
        "--show-history",
        action="store_true",
        help="Show recent evaluation history",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Don't log this run to history",
    )
    parser.add_argument(
        "--triage-status",
        action="store_true",
        help="Show triage pipeline status (for multi-agent workflows)",
    )
    parser.add_argument(
        "--reserve",
        type=str,
        metavar="INDEX",
        help="Reserve an entry for triage (e.g., --reserve 42)",
    )
    parser.add_argument(
        "--release",
        type=str,
        metavar="INDEX",
        help="Release a reserved entry (e.g., --release 42)",
    )
    parser.add_argument(
        "--agent-id",
        type=str,
        default="",
        help="Agent identifier for reservations (e.g., 'triage-agent-1')",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Skip issue deduplication check when exporting",
    )

    args = parser.parse_args()

    # Determine model early for both retry and regular modes
    model_env = os.environ.get("LLM_MODEL")
    if args.model is not None:
        model = args.model
    elif model_env:
        model = model_env
    else:
        model = "gemini-3-flash-preview" if args.provider == "gemini" else "gpt-5-mini"

    rpm_env = os.environ.get("LLM_RPM")
    if args.rpm is not None:
        rpm = args.rpm
    elif rpm_env:
        rpm = int(rpm_env)
    else:
        rpm = 1 if args.provider == "gemini" else 2

    # Handle retry-failed mode
    if args.retry_failed:
        print("=" * 60)
        print("Himotoki LLM Evaluation - Retry Failed")
        print("=" * 60)
        print(f"Results file: {args.export}")
        print(f"Model: {model}")
        print(f"Provider: {args.provider}")
        return retry_failed_eval(
            results_file=args.export,
            model=model,
            timeout=args.timeout,
            provider=args.provider,
            openai_base=args.openai_base,
            openai_key=args.openai_key,
            concurrency=args.concurrency,
            rpm=rpm,
            gemini_key=args.gemini_key,
            gemini_model=args.gemini_model,
        )

    # Handle show history
    if args.show_history:
        return show_history(DEFAULT_HISTORY_FILE)

    # Handle triage status
    if args.triage_status:
        return triage_status(args.export, DEFAULT_SKIP_FILE, DEFAULT_TRIAGE_LOCK_FILE)

    # Handle entry reservation
    if args.reserve:
        idx_str = args.reserve.lstrip("#")
        try:
            entry_index = int(idx_str)
        except ValueError:
            print(f"Invalid index: {args.reserve}", file=sys.stderr)
            return 1
        if reserve_entry(DEFAULT_TRIAGE_LOCK_FILE, entry_index, args.agent_id):
            print(f"Reserved entry #{entry_index}")
            return 0
        else:
            print(f"Entry #{entry_index} is already reserved or issued", file=sys.stderr)
            return 1

    if args.release:
        idx_str = args.release.lstrip("#")
        try:
            entry_index = int(idx_str)
        except ValueError:
            print(f"Invalid index: {args.release}", file=sys.stderr)
            return 1
        release_entry(DEFAULT_TRIAGE_LOCK_FILE, entry_index)
        print(f"Released entry #{entry_index}")
        return 0

    # Handle skip management
    if args.list_skipped:
        return list_skipped(DEFAULT_SKIP_FILE, args.export)

    if args.skip:
        idx_str = args.skip.lstrip("#")
        try:
            entry_index = int(idx_str)
        except ValueError:
            print(f"Invalid index: {args.skip}", file=sys.stderr)
            return 1
        return skip_entry(args.export, DEFAULT_SKIP_FILE, entry_index, args.reason)

    if args.unskip:
        idx_str = args.unskip.lstrip("#")
        try:
            entry_index = int(idx_str)
        except ValueError:
            print(f"Invalid index: {args.unskip}", file=sys.stderr)
            return 1
        return unskip_entry(DEFAULT_SKIP_FILE, entry_index)

    # Handle export to beads
    if args.export_issues:
        return export_to_beads(
            args.export, 
            DEFAULT_SKIP_FILE, 
            dry_run=args.dry_run, 
            label=args.issue_label,
            lock_file=DEFAULT_TRIAGE_LOCK_FILE,
            check_existing=not args.no_dedup,
        )

    # Handle baseline operations
    if args.save_baseline:
        return save_baseline(args.export, args.baseline_file)

    if args.compare_baseline:
        return compare_baseline(args.export, args.baseline_file, DEFAULT_SKIP_FILE)

    # Handle rescore mode (supports comma-separated: 5,12,47)
    if args.rescore:
        # Parse indices - support "5", "#5", "5,12,47", "#5,#12"
        idx_strs = args.rescore.replace("#", "").split(",")
        indices = []
        for s in idx_strs:
            s = s.strip()
            if not s:
                continue
            try:
                indices.append(int(s))
            except ValueError:
                print(f"Invalid index: {s}", file=sys.stderr)
                return 1
        
        if not indices:
            print("No valid indices provided.", file=sys.stderr)
            return 1
        
        print("=" * 60)
        print("Himotoki LLM Evaluation - Rescore After Fix")
        print("=" * 60)
        print(f"Results file: {args.export}")
        print(f"Model: {model}")
        print(f"Provider: {args.provider}")
        print(f"Entries to rescore: {indices}")
        
        failed = 0
        for entry_index in indices:
            result = rescore_entry(
                results_file=args.export,
                entry_index=entry_index,
                model=model,
                timeout=args.timeout,
                provider=args.provider,
                openai_base=args.openai_base,
                openai_key=args.openai_key,
                gemini_key=args.gemini_key,
                gemini_model=args.gemini_model,
            )
            if result != 0:
                failed += 1
        
        return 1 if failed > 0 else 0

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
    print(f"Model: {model}")
    print(f"Provider: {args.provider}")
    if args.mock:
        print("Mode: mock (no API calls)")

    results = run_llm_eval(
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

    # Log to history (unless --no-history)
    if not args.no_history and not args.mock:
        # Load the saved results (export_payload form)
        with open(args.export, "r", encoding="utf-8") as f:
            saved_results = json.load(f)
        log_history(saved_results, DEFAULT_HISTORY_FILE, DEFAULT_SKIP_FILE, model, args.provider)


if __name__ == "__main__":
    sys.exit(main())
