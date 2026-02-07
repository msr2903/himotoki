#!/usr/bin/env python3
"""Analyze expression patterns in failing LLM eval entries."""

import json
import re

with open('output/llm_results.json') as f:
    results = json.load(f)

# Find entries with expression over-grouping issues
exp_issues = []
for idx, r in enumerate(results):
    if not r:
        continue
    score = r.get('llm_score', {})
    if score.get('verdict') != 'pass':
        issues = score.get('issues', [])
        for issue in issues:
            if any(term in issue.lower() for term in ['single token', 'over-group', 'unsegmented', 'coarse', 'chunking']):
                # Get the expression
                for seg in r.get('himotoki_result', []):
                    pos = seg.get('gloss', [{}])[0].get('pos', '')
                    text = seg.get('text', '')
                    if 'exp' in pos.lower() and len(text) > 3:
                        exp_issues.append({
                            'idx': idx,
                            'text': text,
                            'seq': seg.get('seq'),
                            'pos': pos
                        })
                break

# Show unique expressions
print("Expressions causing over-grouping issues:")
print("=" * 60)
seen = set()
for e in exp_issues:
    if e['text'] not in seen:
        # Check for particles in the expression
        particles = []
        for p in ['を', 'が', 'に', 'は', 'で', 'と', 'の', 'も', 'へ', 'から', 'まで', 'より']:
            if p in e['text']:
                particles.append(p)
        particles_str = ','.join(particles) if particles else 'none'
        print(f"#{e['idx']}: {e['text']} | particles: {particles_str} | seq={e['seq']}")
        seen.add(e['text'])

print(f"\nTotal unique expressions: {len(seen)}")
