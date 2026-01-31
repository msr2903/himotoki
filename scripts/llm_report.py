#!/usr/bin/env python3
"""Generate an interactive HTML report from LLM evaluation results."""

import json
import html
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_SKIP_FILE = DATA_DIR / "llm_skip.json"


def _load_skip_list(skip_file: Path) -> Dict[str, str]:
    """Load skip list from JSON file. Returns dict of index -> reason."""
    if not skip_file.exists():
        return {}
    try:
        with open(skip_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("skipped", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def escape(text: str) -> str:
    """HTML escape text."""
    return html.escape(str(text)) if text else ""

def generate_html_report(results: list[dict[str, Any]], skipped: Dict[str, str] = None) -> str:
    """Generate interactive HTML report from LLM results."""
    if skipped is None:
        skipped = {}
    
    # Calculate summary stats
    total = len(results)
    skipped_count = len(skipped)
    active_results = [r for idx, r in enumerate(results) if str(idx + 1) not in skipped]
    passed = sum(1 for r in active_results if r.get("llm_score", {}).get("verdict") == "pass")
    failed = sum(1 for r in active_results if r.get("llm_score", {}).get("verdict") == "fail")
    avg_score = sum(r.get("llm_score", {}).get("overall_score", 0) or 0 for r in active_results) / len(active_results) if active_results else 0
    
    # Build rows data as JSON for JavaScript
    rows_data = []
    for idx, r in enumerate(results):
        llm = r.get("llm_score", {})
        dims = llm.get("dimensions", {})
        issues = llm.get("issues", [])
        notes = llm.get("notes", "")
        
        # Build segments display
        segments_html = ""
        segments_text = ""
        for seg in r.get("segments", []):
            text = seg.get("text", "")
            kana = seg.get("kana", "")
            pos = ", ".join(seg.get("pos", [])) or "-"
            conj = seg.get("conj_type") or "-"
            source = seg.get("source_text") or "-"
            neg = "✓" if seg.get("conj_neg") else ""
            fml = "✓" if seg.get("conj_fml") else ""
            
            segments_html += f"""<tr>
                <td class="seg-text">{escape(text)}</td>
                <td>{escape(kana)}</td>
                <td class="pos-cell">{escape(pos)}</td>
                <td>{escape(conj)}</td>
                <td>{escape(source)}</td>
                <td class="bool-cell">{neg}</td>
                <td class="bool-cell">{fml}</td>
            </tr>"""
            segments_text += f"  {text} ({kana}) - POS: {pos}, Conj: {conj}, Source: {source}\n"
        
        # Build copy-friendly text
        copy_text = f"""## Sentence #{idx + 1}
**Input:** {r.get("sentence", "")}
**Score:** {llm.get("overall_score", "N/A")} ({llm.get("verdict", "N/A")})

### Segmentation Output:
{segments_text}
### Dimension Scores:
- Segmentation: {dims.get("segmentation", "-")}/5
- Reading: {dims.get("reading", "-")}/5
- Conjugation: {dims.get("conjugation", "-")}/5
- POS: {dims.get("pos", "-")}/5
- Dictionary Form: {dims.get("dictionary_form", "-")}/5

### Issues Found:
{chr(10).join("- " + issue for issue in issues) if issues else "None"}

### Notes:
{notes or "None"}
"""
        
        # Determine lowest dimension for categorization
        dim_scores = {
            "segmentation": dims.get("segmentation", 5) or 5,
            "reading": dims.get("reading", 5) or 5,
            "conjugation": dims.get("conjugation", 5) or 5,
            "pos": dims.get("pos", 5) or 5,
            "dictionary_form": dims.get("dictionary_form", 5) or 5,
        }
        worst_dim = min(dim_scores, key=dim_scores.get) if dim_scores else ""
        
        is_skipped = str(idx + 1) in skipped
        skip_reason = skipped.get(str(idx + 1), "")
        
        rows_data.append({
            "idx": idx + 1,
            "sentence": r.get("sentence", ""),
            "score": llm.get("overall_score", 0) or 0,
            "verdict": llm.get("verdict", "unknown"),
            "seg_score": dims.get("segmentation", 0) or 0,
            "read_score": dims.get("reading", 0) or 0,
            "conj_score": dims.get("conjugation", 0) or 0,
            "pos_score": dims.get("pos", 0) or 0,
            "dict_score": dims.get("dictionary_form", 0) or 0,
            "dimension_scores": dim_scores,
            "worst_dim": worst_dim,
            "issues": issues,
            "notes": notes,
            "segments_html": segments_html,
            "copy_text": copy_text,
            "time_himotoki": r.get("time_himotoki", 0),
            "time_llm": r.get("time_llm", 0),
            "skipped": is_skipped,
            "skip_reason": skip_reason,
        })
    
    skipped_json = json.dumps(skipped, ensure_ascii=False)
    rows_json = json.dumps(rows_data, ensure_ascii=False)
    
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Himotoki LLM Evaluation Report</title>
    <style>
        :root {{
            --pass-bg: #d4edda;
            --pass-border: #28a745;
            --fail-bg: #f8d7da;
            --fail-border: #dc3545;
            --hover-bg: #f5f5f5;
            --header-bg: #343a40;
            --header-text: #fff;
        }}
        
        * {{ box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f8f9fa;
            color: #212529;
        }}
        
        .container {{
            max-width: 1600px;
            margin: 0 auto;
        }}
        
        h1 {{
            color: #343a40;
            margin-bottom: 10px;
        }}
        
        .summary {{
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        
        .stat-card {{
            background: white;
            padding: 15px 25px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }}
        
        .stat-card .value {{
            font-size: 2em;
            font-weight: bold;
            color: #343a40;
        }}
        
        .stat-card .label {{
            color: #6c757d;
            font-size: 0.9em;
        }}
        
        .stat-card.pass .value {{ color: #28a745; }}
        .stat-card.fail .value {{ color: #dc3545; }}
        
        .controls {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .controls label {{
            font-weight: 500;
            color: #495057;
        }}
        
        .controls select, .controls input {{
            padding: 8px 12px;
            border: 1px solid #ced4da;
            border-radius: 4px;
            font-size: 14px;
        }}
        
        .controls button {{
            padding: 8px 16px;
            background: #007bff;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }}
        
        .controls button:hover {{
            background: #0056b3;
        }}
        
        .controls button.secondary {{
            background: #6c757d;
        }}
        
        .controls button.secondary:hover {{
            background: #545b62;
        }}
        
        .results-table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .results-table th {{
            background: var(--header-bg);
            color: var(--header-text);
            padding: 12px 8px;
            text-align: left;
            cursor: pointer;
            user-select: none;
            white-space: nowrap;
        }}
        
        .results-table th:hover {{
            background: #495057;
        }}
        
        .results-table th .sort-icon {{
            margin-left: 5px;
            opacity: 0.5;
        }}
        
        .results-table th.sorted .sort-icon {{
            opacity: 1;
        }}
        
        .results-table td {{
            padding: 10px 8px;
            border-bottom: 1px solid #dee2e6;
            vertical-align: top;
        }}
        
        .results-table tr:hover {{
            background: var(--hover-bg);
        }}
        
        .results-table tr.pass {{
            background: var(--pass-bg);
        }}
        
        .results-table tr.fail {{
            background: var(--fail-bg);
        }}
        
        .results-table tr.pass:hover {{
            background: #c3e6cb;
        }}
        
        .results-table tr.fail:hover {{
            background: #f5c6cb;
        }}
        
        .sentence-cell {{
            max-width: 400px;
            word-break: break-all;
            font-size: 1.1em;
        }}
        
        .score-cell {{
            font-weight: bold;
            text-align: center;
        }}
        
        .verdict-badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
            text-transform: uppercase;
        }}
        
        .verdict-badge.pass {{
            background: #28a745;
            color: white;
        }}
        
        .verdict-badge.fail {{
            background: #dc3545;
            color: white;
        }}
        
        .dim-scores {{
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
        }}
        
        .dim-score {{
            background: #e9ecef;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.8em;
            white-space: nowrap;
        }}
        
        .dim-score.low {{
            background: #f8d7da;
            color: #721c24;
        }}
        
        .action-btn {{
            padding: 5px 10px;
            font-size: 0.85em;
            margin-right: 5px;
            cursor: pointer;
            border: 1px solid #ced4da;
            border-radius: 4px;
            background: white;
        }}
        
        .action-btn:hover {{
            background: #e9ecef;
        }}
        
        .action-btn.copy-btn {{
            background: #17a2b8;
            color: white;
            border: none;
        }}
        
        .action-btn.copy-btn:hover {{
            background: #138496;
        }}
        
        .modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 1000;
            overflow-y: auto;
        }}
        
        .modal.active {{
            display: flex;
            justify-content: center;
            align-items: flex-start;
            padding: 40px 20px;
        }}
        
        .modal-content {{
            background: white;
            border-radius: 8px;
            max-width: 900px;
            width: 100%;
            max-height: calc(100vh - 80px);
            overflow-y: auto;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }}
        
        .modal-header {{
            padding: 15px 20px;
            border-bottom: 1px solid #dee2e6;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            background: white;
            z-index: 10;
        }}
        
        .modal-header h2 {{
            margin: 0;
            font-size: 1.2em;
        }}
        
        .modal-close {{
            background: none;
            border: none;
            font-size: 1.5em;
            cursor: pointer;
            color: #6c757d;
        }}
        
        .modal-body {{
            padding: 20px;
        }}
        
        .detail-section {{
            margin-bottom: 20px;
        }}
        
        .detail-section h3 {{
            margin: 0 0 10px 0;
            color: #495057;
            font-size: 1em;
            border-bottom: 1px solid #dee2e6;
            padding-bottom: 5px;
        }}
        
        .segments-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9em;
        }}
        
        .segments-table th {{
            background: #495057;
            color: white;
            padding: 8px;
            text-align: left;
        }}
        
        .segments-table td {{
            padding: 8px;
            border-bottom: 1px solid #dee2e6;
        }}
        
        .seg-text {{
            font-size: 1.2em;
            font-weight: 500;
        }}
        
        .pos-cell {{
            font-size: 0.85em;
            color: #6c757d;
        }}
        
        .bool-cell {{
            text-align: center;
            color: #28a745;
        }}
        
        .issues-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        
        .issues-list li {{
            background: #fff3cd;
            padding: 10px;
            margin-bottom: 5px;
            border-radius: 4px;
            border-left: 3px solid #ffc107;
        }}
        
        .notes-box {{
            background: #e7f3ff;
            padding: 10px;
            border-radius: 4px;
            border-left: 3px solid #007bff;
        }}
        
        .copy-area {{
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 15px;
            font-family: monospace;
            font-size: 0.85em;
            white-space: pre-wrap;
            max-height: 300px;
            overflow-y: auto;
        }}
        
        .toast {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #28a745;
            color: white;
            padding: 12px 20px;
            border-radius: 4px;
            display: none;
            z-index: 2000;
            animation: fadeIn 0.3s;
        }}
        
        .toast.show {{
            display: block;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .hidden {{ display: none !important; }}
        
        .no-results {{
            text-align: center;
            padding: 40px;
            color: #6c757d;
        }}
        
        @media (max-width: 768px) {{
            .summary {{ flex-direction: column; }}
            .controls {{ flex-direction: column; align-items: stretch; }}
            .dim-scores {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Himotoki LLM Evaluation Report</h1>
        
        <div class="summary">
            <div class="stat-card">
                <div class="value">{total}</div>
                <div class="label">Total Sentences</div>
            </div>
            <div class="stat-card pass">
                <div class="value">{passed}</div>
                <div class="label">Passed</div>
            </div>
            <div class="stat-card fail">
                <div class="value">{failed}</div>
                <div class="label">Failed</div>
            </div>
            <div class="stat-card" style="background:#fff3cd;">
                <div class="value">{skipped_count}</div>
                <div class="label">Skipped</div>
            </div>
            <div class="stat-card">
                <div class="value">{avg_score:.1f}</div>
                <div class="label">Avg Score</div>
            </div>
            <div class="stat-card">
                <div class="value">{passed/(passed+failed)*100 if (passed+failed) > 0 else 0:.1f}%</div>
                <div class="label">Pass Rate</div>
            </div>
        </div>
        
        <div class="controls">
            <label>Filter:</label>
            <select id="filterVerdict">
                <option value="all">All Results</option>
                <option value="pass">Pass Only</option>
                <option value="fail">Fail Only</option>
                <option value="skipped">Skipped Only</option>
            </select>
            
            <label>Score Range:</label>
            <input type="number" id="minScore" placeholder="Min" min="0" max="100" style="width:70px">
            <span>-</span>
            <input type="number" id="maxScore" placeholder="Max" min="0" max="100" style="width:70px">
            
            <label>Search:</label>
            <input type="text" id="searchText" placeholder="Search sentences..." style="width:200px">
            
            <label>Dimension:</label>
            <select id="filterDimension">
                <option value="all">All Dimensions</option>
                <option value="segmentation">Segmentation Issues</option>
                <option value="reading">Reading Issues</option>
                <option value="conjugation">Conjugation Issues</option>
                <option value="pos">POS Issues</option>
                <option value="dictionary_form">Dictionary Form Issues</option>
            </select>
            
            <label style="display:flex;align-items:center;gap:4px;">
                <input type="checkbox" id="hideSkipped" checked>
                Hide Skipped
            </label>
            
            <button onclick="applyFilters()">Apply</button>
            <button class="secondary" onclick="resetFilters()">Reset</button>
            <button class="secondary" onclick="copyAllFailed()">📋 Copy All Failed</button>
            <button class="secondary" onclick="exportCSV()">📊 Export CSV</button>
        </div>
        
        <table class="results-table">
            <thead>
                <tr>
                    <th onclick="sortBy('idx')"># <span class="sort-icon">↕</span></th>
                    <th onclick="sortBy('sentence')">Sentence <span class="sort-icon">↕</span></th>
                    <th onclick="sortBy('score')">Score <span class="sort-icon">↕</span></th>
                    <th onclick="sortBy('verdict')">Verdict <span class="sort-icon">↕</span></th>
                    <th>Dimension Scores</th>
                    <th>Issues</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="resultsBody">
            </tbody>
        </table>
        <div id="noResults" class="no-results hidden">No results match your filters.</div>
    </div>
    
    <div id="modal" class="modal" onclick="closeModalOutside(event)">
        <div class="modal-content" onclick="event.stopPropagation()">
            <div class="modal-header">
                <h2 id="modalTitle">Details</h2>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="modalBody">
            </div>
        </div>
    </div>
    
    <div id="toast" class="toast">Copied to clipboard!</div>
    
    <script>
        const rowsData = {rows_json};
        let filteredData = rowsData.filter(r => !r.skipped);
        let currentSort = {{ col: 'idx', asc: true }};
        
        function renderTable() {{
            const tbody = document.getElementById('resultsBody');
            const noResults = document.getElementById('noResults');
            
            if (filteredData.length === 0) {{
                tbody.innerHTML = '';
                noResults.classList.remove('hidden');
                return;
            }}
            
            noResults.classList.add('hidden');
            
            tbody.innerHTML = filteredData.map(r => `
                <tr class="${{r.skipped ? 'skipped' : r.verdict}}">
                    <td>${{r.idx}}</td>
                    <td class="sentence-cell">${{escapeHtml(r.sentence)}}</td>
                    <td class="score-cell">${{r.skipped ? '-' : r.score}}</td>
                    <td>
                        ${{r.skipped 
                            ? '<span class="verdict-badge" style="background:#ffc107;color:#000;">skipped</span>' 
                            : `<span class="verdict-badge ${{r.verdict}}">${{r.verdict}}</span>`}}
                    </td>
                    <td>
                        ${{r.skipped 
                            ? `<span style="color:#666;font-style:italic;">${{escapeHtml(r.skip_reason || 'No reason')}}</span>`
                            : `<div class="dim-scores">
                            <span class="dim-score ${{r.seg_score < 4 ? 'low' : ''}}">Seg: ${{r.seg_score}}</span>
                            <span class="dim-score ${{r.read_score < 4 ? 'low' : ''}}">Read: ${{r.read_score}}</span>
                            <span class="dim-score ${{r.conj_score < 4 ? 'low' : ''}}">Conj: ${{r.conj_score}}</span>
                            <span class="dim-score ${{r.pos_score < 4 ? 'low' : ''}}">POS: ${{r.pos_score}}</span>
                            <span class="dim-score ${{r.dict_score < 4 ? 'low' : ''}}">Dict: ${{r.dict_score}}</span>
                        </div>`}}
                    </td>
                    <td>${{r.skipped ? '-' : (r.issues.length > 0 ? r.issues.length + ' issue(s)' : '-')}}</td>
                    <td>
                        <button class="action-btn" onclick="showDetails(${{r.idx - 1}})">View</button>
                        <button class="action-btn copy-btn" onclick="copyRow(${{r.idx - 1}})">Copy</button>
                    </td>
                </tr>
            `).join('');
        }}
        
        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}
        
        function sortBy(col) {{
            if (currentSort.col === col) {{
                currentSort.asc = !currentSort.asc;
            }} else {{
                currentSort.col = col;
                currentSort.asc = true;
            }}
            
            filteredData.sort((a, b) => {{
                let va = a[col];
                let vb = b[col];
                if (typeof va === 'string') {{
                    va = va.toLowerCase();
                    vb = vb.toLowerCase();
                }}
                if (va < vb) return currentSort.asc ? -1 : 1;
                if (va > vb) return currentSort.asc ? 1 : -1;
                return 0;
            }});
            
            renderTable();
        }}
        
        function applyFilters() {{
            const verdict = document.getElementById('filterVerdict').value;
            const dimension = document.getElementById('filterDimension').value;
            const hideSkipped = document.getElementById('hideSkipped').checked;
            const minScore = parseFloat(document.getElementById('minScore').value) || 0;
            const maxScore = parseFloat(document.getElementById('maxScore').value) || 100;
            const search = document.getElementById('searchText').value.toLowerCase();
            
            filteredData = rowsData.filter(r => {{
                // Handle skipped filtering
                if (verdict === 'skipped') {{
                    return r.skipped === true;
                }}
                if (hideSkipped && r.skipped) return false;
                
                if (verdict !== 'all' && r.verdict !== verdict) return false;
                if (r.score < minScore || r.score > maxScore) return false;
                if (search && !r.sentence.toLowerCase().includes(search)) return false;
                
                // Dimension filter: show if worst_dim matches or score < 100 in that dimension
                if (dimension !== 'all') {{
                    const dims = r.dimension_scores || {{}};
                    if (dims[dimension] === undefined || dims[dimension] >= 100) return false;
                }}
                
                return true;
            }});
            
            renderTable();
        }}
        
        function resetFilters() {{
            document.getElementById('filterVerdict').value = 'all';
            document.getElementById('filterDimension').value = 'all';
            document.getElementById('hideSkipped').checked = true;
            document.getElementById('minScore').value = '';
            document.getElementById('maxScore').value = '';
            document.getElementById('searchText').value = '';
            filteredData = rowsData.filter(r => !r.skipped);
            renderTable();
        }}
        
        function showDetails(idx) {{
            const r = rowsData[idx];
            const modal = document.getElementById('modal');
            const title = document.getElementById('modalTitle');
            const body = document.getElementById('modalBody');
            
            title.textContent = `Sentence #${{r.idx}}: ${{r.sentence.substring(0, 50)}}${{r.sentence.length > 50 ? '...' : ''}}`;
            
            body.innerHTML = `
                <div class="detail-section">
                    <h3>📝 Original Sentence</h3>
                    <div style="font-size:1.3em;padding:10px;background:#f8f9fa;border-radius:4px;">${{escapeHtml(r.sentence)}}</div>
                </div>
                
                <div class="detail-section">
                    <h3>📊 Score: ${{r.score}} (<span class="verdict-badge ${{r.verdict}}">${{r.verdict}}</span>)</h3>
                    <div class="dim-scores" style="gap:10px;">
                        <span class="dim-score ${{r.seg_score < 4 ? 'low' : ''}}">Segmentation: ${{r.seg_score}}/5</span>
                        <span class="dim-score ${{r.read_score < 4 ? 'low' : ''}}">Reading: ${{r.read_score}}/5</span>
                        <span class="dim-score ${{r.conj_score < 4 ? 'low' : ''}}">Conjugation: ${{r.conj_score}}/5</span>
                        <span class="dim-score ${{r.pos_score < 4 ? 'low' : ''}}">POS: ${{r.pos_score}}/5</span>
                        <span class="dim-score ${{r.dict_score < 4 ? 'low' : ''}}">Dictionary Form: ${{r.dict_score}}/5</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h3>🔤 Segments</h3>
                    <table class="segments-table">
                        <thead>
                            <tr>
                                <th>Text</th>
                                <th>Kana</th>
                                <th>POS</th>
                                <th>Conjugation</th>
                                <th>Source</th>
                                <th>Neg</th>
                                <th>Fml</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${{r.segments_html}}
                        </tbody>
                    </table>
                </div>
                
                ${{r.issues.length > 0 ? `
                <div class="detail-section">
                    <h3>⚠️ Issues (${{r.issues.length}})</h3>
                    <ul class="issues-list">
                        ${{r.issues.map(i => `<li>${{escapeHtml(i)}}</li>`).join('')}}
                    </ul>
                </div>
                ` : ''}}
                
                ${{r.notes ? `
                <div class="detail-section">
                    <h3>📋 Notes</h3>
                    <div class="notes-box">${{escapeHtml(r.notes)}}</div>
                </div>
                ` : ''}}
                
                <div class="detail-section">
                    <h3>📋 Copy for LLM (Bug Report)</h3>
                    <button class="action-btn copy-btn" onclick="copyRow(${{idx}})" style="margin-bottom:10px;">Copy to Clipboard</button>
                    <div class="copy-area">${{escapeHtml(r.copy_text)}}</div>
                </div>
                
                <div class="detail-section">
                    <h3>⏱️ Timing</h3>
                    <div>Himotoki: ${{r.time_himotoki.toFixed(3)}}s | LLM: ${{r.time_llm.toFixed(2)}}s</div>
                </div>
            `;
            
            modal.classList.add('active');
        }}
        
        function closeModal() {{
            document.getElementById('modal').classList.remove('active');
        }}
        
        function closeModalOutside(e) {{
            if (e.target.id === 'modal') closeModal();
        }}
        
        function copyRow(idx) {{
            const r = rowsData[idx];
            navigator.clipboard.writeText(r.copy_text).then(() => {{
                showToast('Copied to clipboard!');
            }});
        }}
        
        function copyAllFailed() {{
            const failed = rowsData.filter(r => r.verdict === 'fail');
            if (failed.length === 0) {{
                showToast('No failed results to copy!');
                return;
            }}
            
            const text = failed.map(r => r.copy_text).join('\\n---\\n\\n');
            navigator.clipboard.writeText(text).then(() => {{
                showToast(`Copied ${{failed.length}} failed results!`);
            }});
        }}
        
        function exportCSV() {{
            const headers = ['#', 'Sentence', 'Score', 'Verdict', 'Seg', 'Read', 'Conj', 'POS', 'Dict', 'Issues'];
            const rows = filteredData.map(r => [
                r.idx,
                '"' + r.sentence.replace(/"/g, '""') + '"',
                r.score,
                r.verdict,
                r.seg_score,
                r.read_score,
                r.conj_score,
                r.pos_score,
                r.dict_score,
                '"' + r.issues.join('; ').replace(/"/g, '""') + '"'
            ]);
            
            const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\\n');
            const blob = new Blob([csv], {{ type: 'text/csv' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'llm_results.csv';
            a.click();
            URL.revokeObjectURL(url);
        }}
        
        function showToast(msg) {{
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 2000);
        }}
        
        // Keyboard shortcuts
        document.addEventListener('keydown', e => {{
            if (e.key === 'Escape') closeModal();
        }});
        
        // Initial render
        renderTable();
    </script>
</body>
</html>
'''
    return html_content


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate HTML report from LLM evaluation results")
    parser.add_argument("-i", "--input", default="output/llm_results.json", help="Input JSON file")
    parser.add_argument("-o", "--output", default="output/llm_report.html", help="Output HTML file")
    parser.add_argument("--skip-file", default="data/llm_skip.json", help="Skip list file")
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    skip_path = Path(args.skip_file)
    
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return 1
    
    print(f"Loading {input_path}...")
    with open(input_path, "r", encoding="utf-8") as f:
        results = json.load(f)
    
    # Load skip list
    skipped = _load_skip_list(skip_path)
    if skipped:
        print(f"Loaded {len(skipped)} skipped entries")
    
    print(f"Generating report for {len(results)} results...")
    html_content = generate_html_report(results, skipped)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"Report saved to {output_path}")
    return 0


if __name__ == "__main__":
    exit(main())
