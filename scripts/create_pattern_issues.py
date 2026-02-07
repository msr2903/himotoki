#!/usr/bin/env python3
"""Create beads issues for the 6 failure pattern groups."""
import subprocess
import sys

issues = [
    {
        "title": "Bug: ため misparse as た(adjective stem)+め(suffix) compound",
        "priority": "P1",
        "labels": "segmentation",
        "description": """## Problem
The standalone word ため (because/for the sake of) is being parsed as a suffix compound: た (adjective stem of たい) + め (suffix). This produces wrong POS tags ([aux-adj], [suf,adj-i]) and wrong source_text (たい).

## Affected entries
#19 (score 78), #115 (score 75), #132 (score 85), #145 (score 85), #353 (score 85) — 5 entries

## Reproduction
```
python -m himotoki -f "図るため独自"
```
Shows: ため parsed as compound [た, め] with source_text たい
Expected: ため as standalone noun/conjunction (seq 1520240)

## Root cause
The suffix compound system matches た (adj-i stem of たい, seq 10018814) + め and outscores the correct single-word ため parse. The compound gets score 66 while ため should score higher.

## Suggested fix
Add ため to a blocklist in himotoki/suffixes.py that prevents た+め from forming a compound, OR boost the score of standalone ため to outcompete the compound, OR add a synergy rule.

## Files to investigate
- himotoki/suffixes.py — suffix compound matching
- himotoki/splits.py — split scoring
- himotoki/synergies.py — possible synergy-based fix

## How to verify
```bash
python -m himotoki -f "支援するため国際的な"
python scripts/llm_eval.py --rescore "19,115,132,145,353"
```""",
    },
    {
        "title": "Bug: contraction compounds produce inflated kana readings (extra て)",
        "priority": "P1",
        "labels": "reading",
        "description": """## Problem
When contracted verb forms like ちゃう/ちゃった/てる/てた are parsed as compounds, the kana reading expands back to the uncontracted form, inserting an extra て. For example:
- 行っちゃおう → kana: いってちゃおう (wrong, should be いっちゃおう)
- 見入っちゃった → kana: みいってちゃった (wrong, should be みいっちゃった)
- 遅刻しちゃう → kana: ちこくしてちゃう (wrong, should be ちこくしちゃう)
- 読んどいて → kana: よんでどいて (wrong, should be よんどいて)

## Affected entries
#46, #50, #259, #375, #378, #381, #383, #389, #391, #393, #401, #404, #406 — 11+ entries, scores 45-88

## Root cause
The compound kana builder concatenates the full (uncontracted) kana of each component. For contractions like ちゃう (from てしまう), the te-form component contributes its full って/て kana, and then ちゃう adds its own kana — resulting in って+ちゃう instead of just っちゃう.

## Suggested fix
In the CompoundWord kana generation (lookup.py around L480-510), detect contraction compounds and use the actual surface text's kana rather than concatenating component kana. The surface text IS the contracted form and its reading should match.

## Files to investigate
- himotoki/lookup.py — CompoundWord kana generation, make_compound()
- himotoki/suffixes.py — suffix compound creation
- himotoki/output.py — word_info_from_segment() kana field

## How to verify
```bash
python -m himotoki -f "待ってても来ないならこっちから行っちゃおうか"
python -m himotoki -f "これ食べちゃっていい"
python scripts/llm_eval.py --rescore "50,391,404,406"
```""",
    },
    {
        "title": "Bug: compound words missing seq/POS/conjugation metadata (null fields)",
        "priority": "P1",
        "labels": "metadata",
        "description": """## Problem
Many multi-word compounds end up with null values for seq, POS, and conjugation fields despite being analyzable verb forms. Examples:
- 止めてた — null seq, null conj_type, null pos
- 持ってきてください — null seq, empty POS, no conjugation
- 借りたい — no POS tags
- 開いてしまった — null seq, not marked as is_compound
- 入ってて — no POS, no source_text

## Affected entries
#55 (82), #74 (65), #145 (85), #183 (75), #271 (75), #382 (75), #383 (75), #390 (45), #399 (45), #405 (60), #425 (82) — 11 entries

## Root cause
When word_info_from_segment() handles CompoundWord objects, it correctly sets is_compound=true and populates components. However:
1. If conj_data is empty in segment.info AND CompoundWord.get_conjugation_info() returns nothing, all conj fields stay null
2. The POS of the primary word is not propagated to the compound's POS field
3. Longer compounds (3+ components like 持ってきてください) often have no conj_data at all

## Suggested fix
In himotoki/output.py word_info_from_segment() (CompoundWord branch, ~L832-935):
1. Always populate POS from the primary word's entry
2. For compounds with no conj_data, derive conjugation info from the component chain
3. Ensure seq is set from the primary word even when conj_data is empty

## Files to investigate
- himotoki/output.py L832-935 — word_info_from_segment() CompoundWord branch
- himotoki/lookup.py L300-350 — CompoundWord.get_conjugation_info()

## How to verify
```bash
python -m himotoki -j "止めてたっぽい" | python -m json.tool
python -m himotoki -j "持ってきてください" | python -m json.tool
python scripts/llm_eval.py --rescore "55,183,271,382"
```""",
    },
    {
        "title": "Bug: hiragana いこう (volitional of 行く) misparse as にい+こう",
        "priority": "P2",
        "labels": "segmentation",
        "description": """## Problem
When 行こう appears in hiragana as いこう (common in casual speech), the segmenter splits it incorrectly:
- 飲みにいこう → 飲み + にい + こう (wrong)
- Expected: 飲み + に + いこう

The kanji form 行こう works correctly (verified). The issue is specific to the all-hiragana いこう following the particle に.

## Affected entries
#370 (45), #375 (45), #399 (45) — 3 entries

## Root cause
にい (new/unused, seq for 新しい variant) outscores に+いこう because にい is a valid dictionary word and いこう in hiragana doesn't get matched as volitional of 行く without kanji context. The dictionary has にい as adj-na/prefix meaning "new".

## Suggested fix
Options:
1. Add a synergy penalty for にい when followed by こう (unusual collocation)
2. Boost volitional forms of common verbs like 行く in hiragana
3. Add にいこう as a known split pattern in splits.py

## Files to investigate
- himotoki/splits.py — split scoring
- himotoki/synergies.py — collocation scoring
- himotoki/segment.py — segmentation path selection

## How to verify
```bash
python -m himotoki -f "飲みにいこうって言ってた"
python -m himotoki -f "カラオケ行こうぜ"  # This already works (kanji)
python scripts/llm_eval.py --rescore "370,375,399"
```""",
    },
    {
        "title": "Bug: proper nouns split into individual characters",
        "priority": "P2",
        "labels": "segmentation",
        "description": """## Problem
Several proper nouns are incorrectly split into individual kanji:
- インバウンド → イン + バウンド (#97, score 85)
- 関越道 → 関 + 越 + 道 (#143, score 75)
- 羽田 → 羽 + 田 (#266, score 60)
- 佐藤 → 佐 + 藤 (#333, score 82)

## Affected entries
#97, #143, #266, #333 — 4 entries

## Root cause
These words don't exist in JMdict (the dictionary database). Without a dictionary entry, the segmenter falls back to character-by-character parsing. This is a known limitation of dictionary-based segmentation.

## Suggested fix
Options (in order of preference):
1. Add these as custom dictionary entries via himotoki/db/ loading scripts
2. Add a proper noun list that prevents splitting known names/places
3. For katakana words like インバウンド, add a heuristic that keeps katakana sequences together when no dictionary match exists

Note: 佐藤 and 羽田 are extremely common in Japanese — adding them as dictionary entries is high value.

## How to verify
```bash
python -m himotoki -f "佐藤はただいま席を外しております"
python -m himotoki -f "羽田空港行きのリムジンバス"
python scripts/llm_eval.py --rescore "97,143,266,333"
```""",
    },
    {
        "title": "Bug: unique segmentation errors (から傘, もやし, 腹痛い, もまず, ものだね)",
        "priority": "P2",
        "labels": "segmentation",
        "description": """## Problem
5 entries have unique segmentation bugs not covered by the systemic patterns:

### #401 (score 65): から傘 merge
Sentence: 雨降りそうだから傘持ってった方がいいかもよ
Bug: から (conjunction) + 傘 (umbrella) merged into から傘 (paper umbrella, karakasa)
Fix: Boost conjunction-boundary scoring so から before a noun isn't merged

### #368 (score 85): もやし split
Sentence: 推し活にお金使いすぎて今月ピンチもやし生活確定だわ
Bug: もやし (bean sprouts) split into も (particle) + やし (palm tree)
Fix: もやし needs higher priority as a standalone word

### #384 (score 45): 腹痛い split
Sentence: それマジでうける腹痛いんだけど
Bug: 腹痛い (stomach hurts) parsed as 腹痛 (stomachache noun) + dangling い
Fix: When 痛い follows a body part noun, prefer noun+adj-i over compound-noun parse

### #444 (score 75): もまず misparse
Sentence: どんなに遠い目標でもまずは最初の一歩を踏み出すことから始まる
Bug: もまず parsed as negative of 揉む (to rub) instead of も + まず (adverb)
Fix: Boost common adverb まず when preceded by particle も

### #425 (score 82): ものだね false match
Sentence: 類は友を呼ぶと言う通り似た者同士は自然と集まるものだね
Bug: ものだね matched to 物種 (seed/cause) instead of もの + だ + ね
Fix: 物種 is archaic/rare — penalize its score or require kanji spelling

## How to verify
```bash
python scripts/llm_eval.py --rescore "401,368,384,444,425"
```""",
    },
]

def create_issue(issue):
    cmd = [
        "bd", "create", issue["title"],
        "--priority", issue["priority"],
        "--labels", issue["labels"],
        "--description", issue["description"],
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  OK: {result.stdout.strip()}")
    else:
        print(f"  FAIL: {result.stderr.strip()}")
    return result.returncode == 0

print(f"Creating {len(issues)} issues...")
ok = 0
for i, issue in enumerate(issues, 1):
    print(f"\n[{i}/{len(issues)}] {issue['title'][:60]}...")
    if create_issue(issue):
        ok += 1

print(f"\nDone: {ok}/{len(issues)} created successfully")
