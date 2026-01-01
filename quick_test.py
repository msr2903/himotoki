#!/usr/bin/env python3
"""Quick test script to verify Himotoki segmentation matches Ichiran."""

import subprocess
import json
import time
import sys
from himotoki import simple_segment

# Test sentences - covering various patterns
TEST_SENTENCES = [
    # === LEVEL 1: Basic word + particle ===
    "猫が", "犬を", "山に", "川で", "友達と",
    
    # === LEVEL 2: Copula patterns ===
    "学生です", "先生です", "静かです", "元気です",
    
    # === LEVEL 3: Basic verb conjugations ===
    "食べて", "見て", "読んで", "書いて", "走って",
    "食べます", "見ます", "読みます", "書きます",
    "食べた", "見た", "読んだ", "書いた",
    
    # === LEVEL 4: Counters ===
    "三匹", "五冊", "百円",
    
    # === LEVEL 5: Simple sentences ===
    "日本語を勉強しています",
    "昨日映画を見ました",
    "明日東京に行きます",
    
    # === LEVEL 6: Verb compounds ===
    "食べている", "見ている",
    "食べない", "見ない",
    "食べられる", "見られる",
    "食べさせる", "見させる",
    
    # === LEVEL 7: Multi-clause sentences ===
    "私は日本人です",
    "これは本です",
    "あの人は学生です",
    "今日は天気がいいです",
    "彼女は美しい人です",
    
    # === LEVEL 8: Complex verb forms ===
    "食べたくない",
    "行きたいです",
    "読まなければならない",
    "書かなくてもいい",
    "見てください",
    
    # === LEVEL 9: Longer sentences with multiple clauses ===
    "私は毎日学校に行きます",
    "彼は日本語が上手です",
    "この本はとても面白いです",
    "昨日友達と映画を見に行きました",
    "来週東京に出張に行く予定です",
    
    # === LEVEL 10: Conversational patterns ===
    "何を食べますか",
    "どこに行きたいですか",
    "いつ帰りますか",
    "なぜそう思いますか",
    "どうやって行きますか",
    
    # === LEVEL 11: Relative clauses ===
    "私が買った本",
    "彼が作った料理",
    "日本で撮った写真",
    "先生が言ったこと",
    
    # === LEVEL 12: Quotations and embedded clauses ===
    "彼は来ると言った",
    "明日雨が降ると思います",
    "日本語は難しいと聞きました",
    
    # === LEVEL 13: Compound sentences ===
    "朝ご飯を食べて学校に行きます",
    "本を読んで勉強しました",
    "電車に乗って会社に行きます",
    
    # === LEVEL 14: Conditional patterns ===
    "雨が降ったら行きません",
    "時間があれば手伝います",
    "お金があったら買いたい",
    
    # === LEVEL 15: Honorific/Humble forms ===
    "お待ちください",
    "いらっしゃいませ",
    "失礼いたします",
    "ありがとうございます",
    
    # === LEVEL 16: Challenging ambiguous sentences ===
    "彼女は泳ぐことができる",
    "日本語を話せるようになりたい",
    "食べ過ぎてしまった",
    "読み終わりました",
    "走り続けています",
    
    # === LEVEL 17: News/Formal style ===
    "政府は新しい政策を発表した",
    "経済成長が続いている",
    "選挙が行われる予定です",
    
    # === LEVEL 18: Literary/Written style ===
    "彼は静かに本を読んでいた",
    "風が吹いている",
    "夜が更けていく",
    
    # === LEVEL 19: Idiomatic expressions ===
    "よろしくお願いします",
    "お疲れ様でした",
    "気をつけてください",
    "頑張ってください",
    
    # === LEVEL 20: Complex real-world sentences ===
    "日本の文化について勉強しています",
    "来年日本に留学するつもりです",
    "彼女と結婚することにしました",
    "この問題を解決しなければなりません",
    "できるだけ早く返事をください",
]

# Cache file for Ichiran results (to avoid slow Docker calls on re-runs)
CACHE_FILE = "ichiran_cache.json"

def load_cache() -> dict:
    """Load cached Ichiran results."""
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_cache(cache: dict):
    """Save Ichiran results to cache."""
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def get_ichiran_result(text: str, cache: dict = None) -> list:
    """Get Ichiran segmentation result."""
    # Check cache first
    if cache is not None and text in cache:
        return cache[text]
    
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
                                    # Check for 'text' key directly
                                    if 'text' in info:
                                        texts.append(info['text'])
                                    # Handle alternative readings (e.g., 本 with hon/moto)
                                    elif 'alternative' in info:
                                        alts = info['alternative']
                                        if alts and isinstance(alts, list) and len(alts) > 0:
                                            # Get text from first alternative
                                            texts.append(alts[0].get('text', ''))
                                        else:
                                            texts.append('')
                                    else:
                                        texts.append('')
                        if cache is not None:
                            cache[text] = texts
                        return texts
    except subprocess.TimeoutExpired:
        return ["ERROR: timeout"]
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

def run_tests(quick_mode: bool = False):
    """Run all tests and report results."""
    print("=" * 60)
    print("Quick Himotoki vs Ichiran Comparison")
    if quick_mode:
        print("(Quick mode: using cached Ichiran results)")
    print("=" * 60)
    
    # Load cache
    cache = load_cache()
    initial_cache_size = len(cache)
    
    matches = 0
    mismatches = 0
    errors = 0
    
    results = []
    total = len(TEST_SENTENCES)
    
    for i, sentence in enumerate(TEST_SENTENCES):
        # Progress indicator
        cached = sentence in cache
        progress = f"[{i+1}/{total}]"
        
        h_result = get_himotoki_result(sentence)
        
        if quick_mode and sentence not in cache:
            # Skip uncached in quick mode
            print(f"? {progress} {sentence} (not in cache, skipped)")
            continue
            
        i_result = get_ichiran_result(sentence, cache)
        
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
        
        cache_indicator = "©" if cached else "→"
        print(f"{status} {progress} {cache_indicator} {sentence}")
        if status == "✗":
            print(f"      Himotoki: {h_result}")
            print(f"      Ichiran:  {i_result}")
    
    # Save updated cache
    if len(cache) > initial_cache_size:
        save_cache(cache)
        print(f"\n(Saved {len(cache) - initial_cache_size} new results to cache)")
    
    tested = matches + mismatches + errors
    print()
    print("=" * 60)
    print(f"Results: {matches}/{tested} matches "
          f"({100*matches/tested:.1f}%)" if tested > 0 else "No tests run")
    print(f"  Matches: {matches}")
    print(f"  Mismatches: {mismatches}")
    print(f"  Errors: {errors}")
    print("=" * 60)
    
    return matches, mismatches, errors

if __name__ == "__main__":
    quick_mode = "--quick" in sys.argv or "-q" in sys.argv
    run_tests(quick_mode=quick_mode)
