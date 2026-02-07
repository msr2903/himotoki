#!/usr/bin/env python3
"""Analyze expressions that should be split into morphemes."""

import json
from collections import Counter

with open('output/llm_results.json') as f:
    data = json.load(f)

# Find failing entries with [exp] tokens that have particles
particle_chars = 'をがにのでとへもは'
splitable_exps = []

for idx, entry in enumerate(data):
    score = entry.get('llm_score', {})
    if score.get('verdict') != 'pass':
        for seg in entry['segments']:
            pos = seg.get('pos', [])
            text = seg.get('text', '')
            if any('[exp' in p.lower() for p in pos):
                # Check if there's a particle in the middle of the expression
                has_particle = any(c in text[1:-1] for c in particle_chars)
                if has_particle and len(text) >= 3:
                    seq = seg.get('seq')
                    splitable_exps.append((idx, seq, text, pos[0]))

print(f'Found {len(splitable_exps)} splitable expressions in failing entries')
print()
print('Examples (first 30):')
for idx, seq, text, pos in splitable_exps[:30]:
    print(f'  #{idx}: {text} ({pos}) seq={seq}')

# Group by pattern
print()
print('By particle:')
for p in particle_chars:
    count = sum(1 for _, _, text, _ in splitable_exps if p in text[1:-1])
    if count > 0:
        print(f'  {p}: {count}')
