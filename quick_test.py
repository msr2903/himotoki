#!/usr/bin/env python3
"""Quick test script to verify Himotoki segmentation matches Ichiran."""

import subprocess
import json
import time
from himotoki import simple_segment

# Test sentences - covering various patterns
TEST_SENTENCES = [
    # Basic particles
    "猫が", "犬を", "山に", "川で", "友達と",
    # Copula
    "学生です", "先生です", "静かです", "元気です",
    # Te-form verbs
    "食べて", "見て", "読んで", "書いて", "走って",
    # Polite forms
    "食べます", "見ます", "読みます", "書きます",
    # Past tense
    "食べた", "見た", "読んだ", "書いた",
    # Counters
    "三匹", "五冊", "百円",
    # Complex sentences
    "日本語を勉強しています",
    "昨日映画を見ました",
    "明日東京に行きます",
    # Te-form compounds
    "食べている", "見ている",
    # Negative
    "食べない", "見ない",
    # Potential
    "食べられる", "見られる",
    # Causative
    "食べさせる", "見させる",
    # Passive
    "食べられる", "見られる",
]

def get_ichiran_result(text: str) -> list:
    """Get Ichiran segmentation result."""
    try:
        result = subprocess.run(
            ["docker", "exec", "ichiran-main-1", "ichiran-cli", "-f", text],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            # Format is: [[[[seg1, seg2, ...], score]]]
            # Each seg is [romanization, {info_dict}, alternatives]
            if data and len(data) > 0 and len(data[0]) > 0:
                interpretations = data[0]  # First interpretation list
                if len(interpretations) > 0:
                    best = interpretations[0]  # Best interpretation [segments, score]
                    if len(best) >= 1:
                        segments = best[0]  # List of segments
                        texts = []
                        for seg in segments:
                            if isinstance(seg, list) and len(seg) >= 2:
                                info = seg[1]
                                if isinstance(info, dict):
                                    texts.append(info.get('text', ''))
                        return texts
    except Exception as e:
        return [f"ERROR: {e}"]
    return []

def get_himotoki_result(text: str) -> list:
    """Get Himotoki segmentation result."""
    try:
        words = simple_segment(text)
        return [w.text for w in words]
    except Exception as e:
        return [f"ERROR: {e}"]

def run_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("Quick Himotoki vs Ichiran Comparison")
    print("=" * 60)
    
    matches = 0
    mismatches = 0
    errors = 0
    
    results = []
    
    for sentence in TEST_SENTENCES:
        h_result = get_himotoki_result(sentence)
        i_result = get_ichiran_result(sentence)
        
        if h_result == i_result:
            status = "✓"
            matches += 1
        elif "ERROR" in str(h_result) or "ERROR" in str(i_result):
            status = "!"
            errors += 1
        else:
            status = "✗"
            mismatches += 1
        
        results.append({
            'sentence': sentence,
            'status': status,
            'himotoki': h_result,
            'ichiran': i_result
        })
        
        print(f"{status} {sentence}")
        if status == "✗":
            print(f"   Himotoki: {h_result}")
            print(f"   Ichiran:  {i_result}")
    
    print()
    print("=" * 60)
    print(f"Results: {matches}/{len(TEST_SENTENCES)} matches "
          f"({100*matches/len(TEST_SENTENCES):.1f}%)")
    print(f"  Matches: {matches}")
    print(f"  Mismatches: {mismatches}")
    print(f"  Errors: {errors}")
    print("=" * 60)
    
    return matches, mismatches, errors

if __name__ == "__main__":
    run_tests()
