#!/usr/bin/env python3
"""
Generate HTML comparison report from results.json.

Usage:
    python -m scripts.report
"""
import json
import os
from pathlib import Path

# Resolve paths relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

def generate_html(data):
    json_data = json.dumps(data)
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Himotoki vs Ichiran Comparison Results</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f5f5f5; }}
        h1 {{ text-align: center; color: #2c3e50; }}
        .summary {{ display: flex; justify-content: space-around; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .stat-box {{ text-align: center; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #3498db; }}
        .stat-label {{ font-size: 14px; color: #7f8c8d; }}
        .controls {{ margin-bottom: 20px; display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }}
        button {{ padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; background: #e0e0e0; transition: background 0.3s; }}
        button.active {{ background: #3498db; color: white; }}
        button:hover:not(.active) {{ background: #d0d0d0; }}
        input[type="text"] {{ padding: 10px; border: 1px solid #ddd; border-radius: 4px; width: 300px; }}
        .card {{ background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; overflow: hidden; }}
        .card-header {{ padding: 15px 20px; background: #f8f9fa; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; cursor: pointer; }}
        .card-header:hover {{ background: #f0f0f0; }}
        .sentence {{ font-size: 1.2em; font-weight: bold; }}
        .status {{ padding: 4px 8px; border-radius: 4px; font-size: 0.8em; text-transform: uppercase; font-weight: bold; }}
        .status.match {{ background: #d4edda; color: #155724; }}
        .status.partial {{ background: #fff3cd; color: #856404; }}
        .status.mismatch {{ background: #f8d7da; color: #721c24; }}
        .status.uncomparable {{ background: #e2e3e5; color: #383d41; }}
        .status.ichiran_error {{ background: #cce5ff; color: #004085; }}
        .status.himotoki_error {{ background: #d4edda; color: #155724; }}
        .card-body {{ padding: 20px; display: none; }}
        .card.open .card-body {{ display: block; }}
        .comparison {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .column h3 {{ border-bottom: 2px solid #eee; padding-bottom: 10px; margin-top: 0; }}
        .segment-list {{ list-style: none; padding: 0; }}
        .segment-item {{ background: #f9f9f9; border: 1px solid #eee; margin-bottom: 10px; padding: 10px; border-radius: 4px; }}
        .segment-text {{ font-size: 1.1em; font-weight: bold; color: #2c3e50; }}
        .segment-detail {{ font-size: 0.9em; color: #666; margin-top: 5px; }}
        .tag {{ display: inline-block; background: #e1e1e1; padding: 2px 6px; border-radius: 3px; font-size: 0.8em; margin-right: 5px; }}
        .timing {{ margin-top: 20px; font-size: 0.9em; color: #7f8c8d; text-align: right; border-top: 1px solid #eee; padding-top: 10px; }}
        .diff-section {{ margin-top: 20px; background: #fff3cd; padding: 10px; border-radius: 4px; color: #856404; }}
        .diff-list {{ padding-left: 20px; margin: 0; }}
        .diff-list li {{ margin-bottom: 5px; }}
        .diff-val {{ font-weight: bold; color: #d9534f; }}
        .header-right {{ display: flex; gap: 10px; align-items: center; }}
        .warn-tag {{ background: #ffc107; color: #856404; padding: 2px 6px; border-radius: 3px; font-size: 0.8em; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>Himotoki vs Ichiran Comparison</h1>
    
    <div id="app">
        <div class="summary">
            <div class="stat-box">
                <div class="stat-value" id="total-count">0</div>
                <div class="stat-label">Total Sentences</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" id="match-count">0</div>
                <div class="stat-label">Matches</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" id="partial-count">0</div>
                <div class="stat-label">Partial</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" id="mismatch-count">0</div>
                <div class="stat-label">Mismatches</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" id="uncomparable-count">0</div>
                <div class="stat-label">Uncomparable</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" id="match-rate">0%</div>
                <div class="stat-label">Match Rate</div>
            </div>
        </div>

        <div class="controls">
            <input type="text" id="search-input" placeholder="Search sentence...">
            <button class="filter-btn active" data-filter="all">All</button>
            <button class="filter-btn" data-filter="match">Matches</button>
            <button class="filter-btn" data-filter="partial">Partial</button>
            <button class="filter-btn" data-filter="mismatch">Mismatches</button>
            <button class="filter-btn" data-filter="uncomparable">Uncomparable</button>
            <button class="filter-btn" data-filter="errors">Errors</button>
        </div>

        <div id="results-container"></div>
    </div>

    <script>
        const data = {json_data};
        
        // DOM Elements
        const container = document.getElementById('results-container');
        const totalCountEl = document.getElementById('total-count');
        const matchCountEl = document.getElementById('match-count');
        const partialCountEl = document.getElementById('partial-count');
        const mismatchCountEl = document.getElementById('mismatch-count');
        const uncomparableCountEl = document.getElementById('uncomparable-count');
        const matchRateEl = document.getElementById('match-rate');
        const filterBtns = document.querySelectorAll('.filter-btn');
        const searchInput = document.getElementById('search-input');

        // State
        let currentFilter = 'all';
        let searchQuery = '';

        function init() {{
            updateStats();
            renderList();
            
            filterBtns.forEach(btn => {{
                btn.addEventListener('click', (e) => {{
                    filterBtns.forEach(b => b.classList.remove('active'));
                    e.target.classList.add('active');
                    currentFilter = e.target.dataset.filter;
                    renderList();
                }});
            }});

            searchInput.addEventListener('input', (e) => {{
                searchQuery = e.target.value.toLowerCase();
                renderList();
            }});
        }}

        function updateStats() {{
            const total = data.length;
            const matches = data.filter(d => d.status === 'match').length;
            const partial = data.filter(d => d.status === 'partial').length;
            const mismatches = data.filter(d => d.status === 'mismatch').length;
            const uncomparable = data.filter(d => d.status === 'uncomparable').length;
            const errors = data.filter(d => d.status === 'ichiran_error' || d.status === 'himotoki_error').length;
            
            // Comparable = total minus uncomparable and errors
            const comparable = total - uncomparable - errors;
            
            totalCountEl.textContent = total;
            matchCountEl.textContent = matches;
            partialCountEl.textContent = partial;
            mismatchCountEl.textContent = mismatches;
            uncomparableCountEl.textContent = uncomparable;
            matchRateEl.textContent = comparable > 0 ? Math.round((matches / comparable) * 100) + '%' : '0%';
        }}

        function renderSegment(seg, otherSeg) {{
            const posTags = seg.pos ? seg.pos.map(p => `<span class="tag">${{p}}</span>`).join('') : '';
            
            // Check for differences if otherSeg is provided
            let scoreStyle = 'background:#d1ecf1';
            let seqStyle = 'background:#e2e3e5';
            
            if (otherSeg) {{
                if (seg.score !== otherSeg.score) scoreStyle = 'background:#ffc107; font-weight:bold';
                if (seg.seq !== otherSeg.seq) seqStyle = 'background:#ffc107; font-weight:bold';
            }}

            return `
                <div class="segment-item">
                    <div class="segment-text">${{seg.text}} <span style="font-weight:normal; font-size:0.9em; color:#888">(${{seg.kana || ''}})</span></div>
                    <div class="segment-detail">
                        ${{posTags}}
                        ${{seg.score ? `<span class="tag" style="${{scoreStyle}}">Score: ${{seg.score}}</span>` : ''}}
                        ${{seg.seq ? `<span class="tag" style="${{seqStyle}}">Seq: ${{seg.seq}}</span>` : ''}}
                    </div>
                </div>
            `;
        }}

        function renderDiffs(diffs) {{
            if (!diffs || diffs.length === 0) return '';
            const listItems = diffs.map(d => `<li>${{d}}</li>`).join('');
            return `<div class="diff-section"><strong>Differences:</strong><ul class="diff-list">${{listItems}}</ul></div>`;
        }}

        function renderList() {{
            container.innerHTML = '';
            
            const filteredData = data.filter(item => {{
                let matchesFilter = false;
                if (currentFilter === 'all') {{
                    matchesFilter = true;
                }} else if (currentFilter === 'errors') {{
                    matchesFilter = item.status === 'ichiran_error' || item.status === 'himotoki_error';
                }} else {{
                    matchesFilter = item.status === currentFilter;
                }}
                const matchesSearch = item.sentence.toLowerCase().includes(searchQuery);
                return matchesFilter && matchesSearch;
            }});

            // Limit rendering to first 200 items initially to avoid freezing if list is huge
            const itemsToRender = filteredData.slice(0, 200);
            
            itemsToRender.forEach((item, index) => {{
                const card = document.createElement('div');
                card.className = 'card';
                
                const isMatch = item.status === 'match';
                const isPartial = item.status === 'partial';
                const statusClass = item.status.replace('_', '-');
                
                const diffHtml = (!isMatch) ? renderDiffs(item.differences) : '';

                // Check for score/seq differences even in matches
                let hasScoreDiff = false;
                let hasSeqDiff = false;
                if (item.ichiran_segments && item.himotoki_segments && 
                    item.ichiran_segments.length === item.himotoki_segments.length) {{
                    for (let i = 0; i < item.ichiran_segments.length; i++) {{
                        if (item.ichiran_segments[i].score !== item.himotoki_segments[i].score) hasScoreDiff = true;
                        if (item.ichiran_segments[i].seq !== item.himotoki_segments[i].seq) hasSeqDiff = true;
                    }}
                }}

                const ichiranHtml = (item.ichiran_segments || []).map((seg, i) => {{
                    const other = item.himotoki_segments ? item.himotoki_segments[i] : null;
                    const shouldCompare = (isMatch || isPartial) || (other && other.text === seg.text);
                    return renderSegment(seg, shouldCompare ? other : null);
                }}).join('');

                const himotokiHtml = (item.himotoki_segments || []).map((seg, i) => {{
                    const other = item.ichiran_segments ? item.ichiran_segments[i] : null;
                    const shouldCompare = (isMatch || isPartial) || (other && other.text === seg.text);
                    return renderSegment(seg, shouldCompare ? other : null);
                }}).join('');

                card.innerHTML = `
                    <div class="card-header" onclick="this.parentElement.classList.toggle('open')">
                        <div class="sentence">${{item.sentence}}</div>
                        <div class="header-right">
                            ${{hasScoreDiff ? '<span class="warn-tag">Score Diff</span>' : ''}}
                            ${{hasSeqDiff ? '<span class="warn-tag">Seq Diff</span>' : ''}}
                            <div class="status ${{statusClass}}">${{item.status}}</div>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="comparison">
                            <div class="column">
                                <h3>Ichiran (${{item.time_ichiran ? item.time_ichiran.toFixed(4) : '?'}}s)</h3>
                                <div class="segment-list">
                                    ${{ichiranHtml}}
                                </div>
                            </div>
                            <div class="column">
                                <h3>Himotoki (${{item.time_himotoki ? item.time_himotoki.toFixed(4) : '?'}}s)</h3>
                                <div class="segment-list">
                                    ${{himotokiHtml}}
                                </div>
                            </div>
                        </div>
                        ${{diffHtml}}
                    </div>
                `;
                container.appendChild(card);
            }});
            
            if (filteredData.length > 200) {{
                const moreDiv = document.createElement('div');
                moreDiv.style.textAlign = 'center';
                moreDiv.style.padding = '20px';
                moreDiv.innerHTML = `<em>Showing first 200 of ${{filteredData.length}} items. Filter to see specific items.</em>`;
                container.appendChild(moreDiv);
            }}
        }}

        init();
    </script>
</body>
</html>
    """
    return html

def main():
    input_file = OUTPUT_DIR / 'results.json'
    output_file = OUTPUT_DIR / 'report.html'
    
    if not input_file.exists():
        print(f"Error: {input_file} not found.")
        return

    print(f"Reading {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Generating {output_file}...")
    html_content = generate_html(data)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Done! Open {output_file} in your browser.")

if __name__ == "__main__":
    main()
