#!/usr/bin/env python3
"""
Local web UI for approving LLM evaluation results into a goldset.

Usage:
    python -m scripts.llm_labeler --host 127.0.0.1 --port 8008

Requires optional deps: pip install -e ".[eval]"
"""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
except ImportError as e:
    raise SystemExit(
        "FastAPI is required. Install with: pip install -e \".[eval]\""
    ) from e

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_DIR = PROJECT_ROOT / "data"

DEFAULT_RESULTS_FILE = OUTPUT_DIR / "llm_results.json"
DEFAULT_GOLDSET_FILE = DATA_DIR / "llm_goldset.json"

app = FastAPI(title="Himotoki LLM Labeler")


def _load_json(path: Path) -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in {path}: {e}")


def _write_json(path: Path, data: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.get("/api/results")
async def api_results():
    results_path = Path(os.environ.get("LLM_RESULTS_FILE", DEFAULT_RESULTS_FILE))
    return _load_json(results_path)


@app.get("/api/gold")
async def api_gold():
    gold_path = Path(os.environ.get("LLM_GOLDSET_FILE", DEFAULT_GOLDSET_FILE))
    return _load_json(gold_path)


@app.post("/api/label")
async def api_label(payload: Dict[str, Any]):
    sentence = payload.get("sentence")
    label = payload.get("label")
    notes = payload.get("notes", "")
    llm_score = payload.get("llm_score")
    if not sentence or label not in {"pass", "fail"}:
        raise HTTPException(status_code=400, detail="Missing sentence or invalid label")

    gold_path = Path(os.environ.get("LLM_GOLDSET_FILE", DEFAULT_GOLDSET_FILE))
    gold_data = _load_json(gold_path)
    by_sentence = {item["sentence"]: item for item in gold_data if "sentence" in item}

    entry = {
        "sentence": sentence,
        "label": label,
        "notes": notes,
        "approved_by_human": True,
        "approved_at": datetime.utcnow().isoformat() + "Z",
    }
    if llm_score is not None:
        entry["llm_score"] = llm_score

    by_sentence[sentence] = entry

    updated = list(by_sentence.values())
    _write_json(gold_path, updated)

    return {"status": "ok", "count": len(updated)}


@app.get("/", response_class=HTMLResponse)
async def index():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Himotoki LLM Labeler</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; color: #222; }
    h1 { margin-bottom: 8px; }
    .toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; }
    .card { border: 1px solid #e5e5e5; border-radius: 8px; padding: 12px; margin-bottom: 10px; background: #fff; }
    .sentence { font-weight: 600; font-size: 1.05em; }
    .meta { color: #666; font-size: 0.9em; margin-top: 6px; }
    .actions { margin-top: 10px; display: flex; gap: 8px; align-items: center; }
    button { padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; }
    .approve { background: #2ecc71; color: #fff; }
    .reject { background: #e74c3c; color: #fff; }
    textarea { width: 100%; min-height: 48px; margin-top: 8px; }
    .tag { display: inline-block; background: #f0f0f0; padding: 2px 6px; border-radius: 4px; margin-right: 6px; }
  </style>
</head>
<body>
  <h1>Himotoki LLM Labeler</h1>
  <div class="toolbar">
    <button onclick="loadData()">Reload</button>
    <span id="status"></span>
  </div>
  <div id="list"></div>

  <script>
    let results = [];
    let gold = [];

    async function loadData() {
      const [res1, res2] = await Promise.all([
        fetch('/api/results'),
        fetch('/api/gold')
      ]);
      results = await res1.json();
      gold = await res2.json();
      render();
      document.getElementById('status').textContent = `Loaded ${results.length} results, ${gold.length} labeled`;
    }

    function render() {
      const list = document.getElementById('list');
      list.innerHTML = '';
      const goldMap = new Map(gold.map(g => [g.sentence, g]));

      results.forEach(item => {
        const existing = goldMap.get(item.sentence);
        const card = document.createElement('div');
        card.className = 'card';

        const verdict = item.llm_score?.verdict || 'unknown';
        const score = item.llm_score?.overall_score ?? 'n/a';

        card.innerHTML = `
          <div class="sentence">${item.sentence}</div>
          <div class="meta">
            <span class="tag">LLM verdict: ${verdict}</span>
            <span class="tag">Score: ${score}</span>
            ${existing ? `<span class="tag">Human: ${existing.label}</span>` : ''}
          </div>
          <div class="actions">
            <button class="approve">Approve</button>
            <button class="reject">Reject</button>
          </div>
          <textarea placeholder="Notes">${existing?.notes || ''}</textarea>
        `;

        const approveBtn = card.querySelector('.approve');
        const rejectBtn = card.querySelector('.reject');
        const notesEl = card.querySelector('textarea');

        approveBtn.onclick = () => submitLabel(item, 'pass', notesEl.value);
        rejectBtn.onclick = () => submitLabel(item, 'fail', notesEl.value);

        list.appendChild(card);
      });
    }

    async function submitLabel(item, label, notes) {
      await fetch('/api/label', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sentence: item.sentence,
          label,
          notes,
          llm_score: item.llm_score || null
        })
      });
      await loadData();
    }

    loadData();
  </script>
</body>
</html>
    """


def main():
    parser = argparse.ArgumentParser(description="Run local LLM labeler UI")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8008)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
