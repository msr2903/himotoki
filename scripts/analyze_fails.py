#!/usr/bin/env python3
"""Analyze current LLM eval failures for triage."""
import json
from collections import Counter

with open('output/llm_results.json') as f:
    results = json.load(f)

with open('data/llm_skip.json') as f:
    skips = json.load(f)

skip_ids = set()
for k in skips.keys():
    try:
        skip_ids.add(int(k))
    except ValueError:
        pass

llm_errors = []
real_fails = []

for idx, entry in enumerate(results):
    if idx in skip_ids:
        continue
    sd = entry.get('llm_score', {})
    if sd.get('verdict', '') == 'pass':
        continue
    score = sd.get('overall_score', 0)
    issues = sd.get('issues', [])
    sent = entry.get('sentence', '')
    if score == 0 and any('LLM error' in i or 'error' in i[:15] for i in issues):
        llm_errors.append(idx)
    else:
        real_fails.append((idx, score, sent, issues))

print(f'LLM errors (score 0, retriable): {len(llm_errors)}')
print(f'  IDs: {llm_errors}')
print(f'Real failures: {len(real_fails)}')
print()

# Group by issue pattern
tame_ids = []
ikou_ids = []
contraction_ids = []
segmentation_ids = []
reading_ids = []
null_meta_ids = []
proper_noun_ids = []

for idx, score, sent, issues in real_fails:
    issue_text = ' '.join(issues)
    it_lower = issue_text.lower()
    
    tagged = False
    
    # tame misparse
    if 'ため' in issue_text and ('たい' in issue_text or 'compound' in it_lower):
        tame_ids.append(idx)
        tagged = True
    
    # ikou/行こう split issues
    if '行こう' in issue_text or 'にいこう' in issue_text:
        ikou_ids.append(idx)
        tagged = True
    if '行' in issue_text and 'ぎょう' in issue_text:
        ikou_ids.append(idx)
        tagged = True
    
    # contraction issues (ちゃう、てる、etc)
    if 'contraction' in it_lower or 'contracted' in it_lower:
        contraction_ids.append(idx)
        tagged = True
    
    # Proper noun splitting
    if '佐藤' in issue_text or '羽田' in issue_text or '関越' in issue_text or 'インバウンド' in issue_text:
        proper_noun_ids.append(idx)
        tagged = True
    
    # bad split/segmentation
    if 'split' in it_lower and ('incorrect' in it_lower or 'critical' in it_lower):
        segmentation_ids.append(idx)
        tagged = True
    
    # null seq/pos
    if 'null' in it_lower and ('seq' in it_lower or 'pos' in it_lower):
        null_meta_ids.append(idx)
        tagged = True

# Deduplicate
ikou_ids = list(set(ikou_ids))

print("=== PATTERN GROUPS ===")
print(f"\n1. TAME misparse (ため -> た+め -> たい): {len(tame_ids)} entries")
print(f"   IDs: {tame_ids}")

print(f"\n2. 行こう split (行+こう instead of 行こう): {len(ikou_ids)} entries")  
print(f"   IDs: {ikou_ids}")

print(f"\n3. Contraction handling (ちゃう/てる/etc): {len(contraction_ids)} entries")
print(f"   IDs: {contraction_ids}")

print(f"\n4. Proper noun splitting: {len(proper_noun_ids)} entries")
print(f"   IDs: {proper_noun_ids}")

print(f"\n5. Null metadata (seq/pos): {len(null_meta_ids)} entries")
print(f"   IDs: {null_meta_ids}")

print(f"\n6. Bad segmentation (other): {len(segmentation_ids)} entries")
print(f"   IDs: {segmentation_ids}")

# Show all real fails sorted
print("\n\n=== ALL REAL FAILURES (by score desc) ===")
real_fails.sort(key=lambda x: -x[1])
for idx, score, sent, issues in real_fails:
    print(f"\n#{idx} (score {score}): {sent[:70]}")
    for iss in issues[:3]:
        print(f"  - {iss[:140]}")
