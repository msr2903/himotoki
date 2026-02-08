#!/usr/bin/env python3
"""Create beads issues for grammar audit triage findings."""
import subprocess
import sys

def create_issue(title, description, labels="conjugation"):
    """Create a beads issue."""
    cmd = ["bd", "create", title, "--description", description, "--labels", labels]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        # Extract issue ID from output
        for line in result.stdout.strip().split('\n'):
            if 'Created issue:' in line:
                print(f"  OK: {line.strip()}")
                return True
    print(f"  FAIL: {result.stderr.strip()}")
    return False


issues = [
    # =========================================================================
    # Issue 1: Dict entries hide suffix compound grammar chain
    # =========================================================================
    {
        "title": "Dict entries hide suffix compound grammar chain (nikui, sugiru, sa, etc.)",
        "labels": "conjugation,P1",
        "description": """## Problem

Words like 食べにくい, 食べすぎる, 美しさ exist as standalone JMdict dictionary entries. They ALSO have suffix compound analyses (食べ+にくい, 食べ+すぎる, 美し+さ) that show grammar chains. The dict entry always wins, killing grammar display.

## Root Cause

In cull_segments() (lookup.py ~L2098), segments scoring below 50% of max are removed. The suffix compound (score ~336) scores only 43% of the dict entry (score ~780), so it gets culled.

## Affected Words

All words existing as both a JMdict entry AND a suffix compound:
- 食べにくい, 話しにくい, 読みにくい (nikui: difficult to)
- 食べすぎる, 飲みすぎる (sugiru: too much)
- 美しさ, 大きさ, 高さ (sa: -ness)
- 淋しげ (ge: -ish appearance)
- 大きめ (me: somewhat)

## Fix Approach (dual-entry)

User's request: suffix compound as PRIMARY (has grammar chain), dict entry as SECONDARY.

Step 1 - Protect suffix compounds from culling:
himotoki/lookup.py cull_segments() (~L2098):
  return [s for s in segments if s.score >= cutoff
          or getattr(s.word, 'is_compound', False)]

Step 2 - Reorder compound first:
himotoki/segment.py join_substring_words() (~L287):
  dict_segs = [s for s in culled if not getattr(s.word, 'is_compound', False)]
  compound_segs = [s for s in culled if getattr(s.word, 'is_compound', False)]
  if dict_segs and compound_segs:
      culled = compound_segs + dict_segs

## Code Locations
- himotoki/lookup.py:2085-2113 - cull_segments()
- himotoki/segment.py:268-290 - join_substring_words()
- himotoki/segment.py:230-238 - find_substring_words() both candidates found
- himotoki/output.py:507-570 - word_info_from_segment_list()

## How to Verify
  python -m himotoki -f '食べにくい'
  python -m himotoki -f '食べすぎる'
  python -m himotoki -f '美しさ'
  python -m himotoki -f '高さ'
""",
    },

    # =========================================================================
    # Issue 2: yagaru suffix not shown in chain
    # =========================================================================
    {
        "title": "Suffix やがる not shown in chain display",
        "labels": "conjugation",
        "description": """## Problem

食べやがる shows chain stopping at Continuative (たべ) — the やがる suffix is invisible.

## Current Output
  食べやがる → Continuative (~i) (たべ): and (stem)

## Expected Output
  食べやがる → Continuative (~i) (たべ) → やがる (indicates disdain)

## Root Cause

The suffix やがる is registered with handler 'teren' (suffixes.py ~L287). It should produce a compound word with やがる as a component. Likely the compound is being created but the display in _get_compound_display() doesn't render the やがる component properly - probably falls into the "else" branch at output.py ~L1697 and shows the kana but without the suffix description.

OR the compound word isn't being picked (same dict-vs-compound scoring issue as Issue 1).

## Code Locations
- himotoki/suffixes.py:287 - _load_conjs for yagaru
- himotoki/output.py:1697 - compound component display
- himotoki/suffixes.py:73 - SUFFIX_DESCRIPTION['yagaru']

## How to Verify
  python -m himotoki -f '食べやがる'
  python -m himotoki -f '食べやがった'
""",
    },

    # =========================================================================
    # Issue 3: garu (3rd person want) misparse
    # =========================================================================
    {
        "title": "Suffix がる misparses as Past tense (食べたがる → 食べた+がる)",
        "labels": "conjugation",
        "description": """## Problem

食べたがる (3rd person wants to eat) shows "Past (~ta) (た)" instead of the correct chain: 食べ → たい (want) → がる (3rd person feeling).

## Current Output
  食べたがる → ← 食べる | Past (~ta) (た): did/was

## Expected Output
  食べたがる → ← 食べる | Continuative (~i) (たべ) → たい (want) → がる (3rd person)

## Root Cause

The がる suffix handler uses CONJ_ADJECTIVE_STEM to find root words. For 食べたがる, the root is 食べた which matches 食べる Past tense. But the correct parse is 食べ (continuative) + た (part of たい adj stem) + がる.

This is actually a compound: 食べ + たがる where たがる = たい-stem + がる. The suffix system builds: root=食べた + suffix=がる, but 食べた matches 食べる past instead of recognizing the たい→がる pattern.

Note: 食べたがっている (with further conjugation) works correctly because the full compound chain resolves. The base form 食べたがる is the broken case.

## Code Locations
- himotoki/suffixes.py:499 - _handler_garu()
- himotoki/suffixes.py:64 - SUFFIX_DESCRIPTION['garu']

## How to Verify
  python -m himotoki -f '食べたがる'
  python -m himotoki -f '食べたがっている'  # This one works
""",
    },

    # =========================================================================
    # Issue 4: だろう/でしょう not recognized as suffix
    # =========================================================================
    {
        "title": "だろう/でしょう suffix not recognized on verb/adj forms",
        "labels": "conjugation",
        "description": """## Problem

食べるだろう (probably eats) and 食べるでしょう (probably eats, polite) show no chain at all. The だろう/でしょう suffixes are registered in suffixes.py but use conj_type=2 (Past) for the root — plain non-past forms don't match.

## Current Output
  食べるだろう → (none)
  食べるでしょう → (none)

## Expected Output
  食べるだろう → ← 食べる → だろう (probably)
  食べるでしょう → ← 食べる → でしょう (probably, polite)

## Root Cause

The suffix handler _handler_rou() (suffixes.py ~L491) calls find_word_with_conj_type(root, 2) — conj_type 2 is Past. But だろう attaches to the plain/dictionary form (Non-past), NOT the past form.

Similarly, _handler_desho() only accepts roots ending in ない/なかった (negative forms).

These handlers are too restrictive. だろう/でしょう attach to:
- Plain form: 食べるだろう, 行くだろう
- Past form: 食べただろう
- i-adj: 高いだろう
- na-adj/copula: 静かだろう

## Code Locations
- himotoki/suffixes.py:491 - _handler_rou (conj_type=2, should also accept non-past)
- himotoki/suffixes.py:501 - _handler_desho (only accepts ない)
- himotoki/suffixes.py:243-247 - registration of rou/desho suffixes

## How to Verify
  python -m himotoki -f '食べるだろう'
  python -m himotoki -f '食べるでしょう'
  python -m himotoki -f '高いだろう'
""",
    },

    # =========================================================================
    # Issue 5: 食べましょ contraction misparse
    # =========================================================================
    {
        "title": "食べましょ (shimashou contraction) misparses as continuative",
        "labels": "conjugation",
        "description": """## Problem

食べましょ (let's eat, contraction of 食べましょう) shows only Continuative instead of the polite volitional.

## Current Output
  食べましょ → ← 食べる | Continuative (~i) (たべ): and (stem)

## Expected Output
  食べましょ → ← 食べる | Polite (ます) → Volitional (しょう→しょ)

## Root Cause

The abbreviation handler _handler_abbr_shimasho() (suffixes.py ~L556) reconstructs root + しましょう and calls find_word_full(). But the root matching may fail — it expects the full しましょう form in the DB conjugation table.

The contraction 食べましょ → root is 食べ, full form is 食べしましょう which is not a valid form. It should be: stem=食べ, suffix=ましょう→ましょ.

## Code Locations
- himotoki/suffixes.py:556 - _handler_abbr_shimasho()
- himotoki/suffixes.py:297 - ABBREVIATION_STEMS['shimashou'] = 5

## How to Verify
  python -m himotoki -f '食べましょ'
  python -m himotoki -f '食べましょう'  # Full form for comparison
""",
    },

    # =========================================================================
    # Issue 6: 食べてもいい chain truncated
    # =========================================================================
    {
        "title": "てもいい (it's ok to) chain truncated - もいい not shown",
        "labels": "conjugation",
        "description": """## Problem

食べてもいい (it's ok to eat) shows te-form but もいい is displayed as empty tree node.

## Current Output
  食べてもいい → ← 食べる | Conjunctive (~te) (て) | └─ (empty)

## Expected Output
  食べてもいい → ← 食べる | Conjunctive (~te) (て) → もいい (it's ok if)

## Root Cause

The teii suffix handler correctly finds the compound, but the もいい component has no conjugation data (it's registered via _load_abbr or placeholder). When _get_compound_display() encounters a component with no seq/conjugations, it tries to show comp_kana but the placeholder reading may be empty.

## Code Locations
- himotoki/suffixes.py:248-258 - moii/teii registration
- himotoki/output.py:1676-1700 - _get_compound_display() component rendering

## How to Verify
  python -m himotoki -f '食べてもいい'
  python -m himotoki -f '食べなくてもいい'
""",
    },

    # =========================================================================
    # Issue 7: ながら (while) not registered as suffix
    # =========================================================================
    {
        "title": "ながら (simultaneous action) not registered as suffix",
        "labels": "enhancement,conjugation",
        "description": """## Problem

食べながら (while eating) shows only Continuative stem, ながら is invisible. It is NOT registered in the suffix system at all.

## Current Output
  食べながら → ← 食べる | Continuative (~i) (たべ): and (stem)
  歩きながら → ← 歩く | Continuative (~i) (き): and (stem)

## Expected Output
  食べながら → ← 食べる | Continuative (~i) (たべ) → ながら (while doing)
  歩きながら → ← 歩く | Continuative (~i) (き) → ながら (while doing)

## Root Cause

ながら is not in the suffix cache. It attaches to the continuative (ren'youkei) stem, same as つつ, つづける, etc. Ichiran does not register it either — this is an enhancement.

## Fix Approach

In suffixes.py init_suffixes():
  nagara_kf = get_kana_form(session, <SEQ_NAGARA>, 'ながら')
  if nagara_kf:
      _load_kf('ren', nagara_kf, suffix_class='nagara')

Add to SUFFIX_DESCRIPTION:
  'nagara': 'while doing ... / simultaneously ...'

Need to find the JMdict seq for ながら first.

## Code Locations
- himotoki/suffixes.py:230+ - init_suffixes() (add registration)
- himotoki/suffixes.py:56+ - SUFFIX_DESCRIPTION (add entry)
- himotoki/constants.py - add SEQ_NAGARA

## How to Verify
  python -m himotoki -f '食べながら'
  python -m himotoki -f '歩きながら'
""",
    },

    # =========================================================================
    # Issue 8: 彼ら (plural ra) not recognized
    # =========================================================================
    {
        "title": "ら (plural) suffix not triggering on pronouns like 彼ら",
        "labels": "conjugation",
        "description": """## Problem

彼ら (they) shows no chain. The ら (plural) suffix is registered and the handler checks for POS='pn' (pronoun), but 彼 alone may not have POS='pn'.

## Current Output
  彼ら → (none)

## Expected
  彼ら → 彼 (he) → ら (plural)

## Root Cause

The _handler_ra() filters for POS='pn' on the root. The root is 彼 which has seq=1220550. Its POS tag may be 'pn' but the handler may not find it due to how find_word_with_pos works. OR 彼ら itself is a dict entry (seq=1357980) which wins over the compound.

This is likely another dict-entry-hides-compound case (same as Issue 1).

## Code Locations
- himotoki/suffixes.py:508 - _handler_ra()
- himotoki/suffixes.py:290 - ra registration

## How to Verify
  python -m himotoki -f '彼ら'
  python -m himotoki -j '彼ら'  # Check if dict entry
""",
    },

    # =========================================================================
    # Issue 9: Na-adj 静かで (te-form) not recognized
    # =========================================================================
    {
        "title": "Na-adjective te-form (静かで) not recognized",
        "labels": "conjugation",
        "description": """## Problem

静かで (na-adj te-form: quiet and...) shows no chain. Na-adjective conjugation via copula で (te-form of だ) is not displayed.

## Current Output
  静かで → (none)

## Expected
  静かで → 静か (quiet, na-adj) + で (te-form of copula だ)

## Root Cause

Na-adjective conjugation goes through the copula だ. The forms だった (past), じゃない (negative), なら (conditional) all work because they have distinct entries. But で alone is ambiguous - it's also the particle で (at/in/by).

The parser likely matches で as the particle rather than the copula te-form.

## Code Locations
- himotoki/lookup.py - copula conjugation handling
- himotoki/segment.py - disambiguation of で

## How to Verify
  python -m himotoki -f '静かで'
  python -m himotoki -f '静かだった'  # This works
""",
    },

    # =========================================================================
    # Issue 10: Na-adj + そう (静かそう) not recognized
    # =========================================================================
    {
        "title": "Na-adjective + そう (静かそう) not recognized",
        "labels": "conjugation",
        "description": """## Problem

静かそう (looks quiet) shows no chain. The そう suffix handler looks for Continuative/Adjective Stem forms, but na-adjectives don't have that conjugation type in the DB.

## Current Output
  静かそう → (none)

## Expected
  静かそう → 静か (quiet) → そう (looks like)

## Root Cause

The _handler_sou() calls find_word_with_conj_type(root, 13, CONJ_ADJECTIVE_STEM, CONJ_ADVERBIAL). For na-adjectives, the root is 静か but this doesn't appear as a conjugated form of anything — na-adj stems ARE the root form. The handler needs to also accept na-adjectives directly (POS='adj-na').

高そう works because 高い is an i-adjective and 高 appears as the adj stem (conj_type=51). 静か has no such conjugation.

## Fix Approach

In _handler_sou(), after the conjugation check, also try:
  results.extend(find_word_with_pos(session, root, 'adj-na'))

## Code Locations
- himotoki/suffixes.py:468 - _handler_sou()
- himotoki/suffixes.py:228 - sou registration

## How to Verify
  python -m himotoki -f '静かそう'
  python -m himotoki -f '高そう'  # This works (i-adj)
""",
    },

    # =========================================================================
    # Issue 11: 食べなくちゃ (must) empty chain
    # =========================================================================
    {
        "title": "食べなくちゃ (must eat, contraction) shows empty chain",
        "labels": "conjugation",
        "description": """## Problem

食べなくちゃ (must eat, contraction of 食べなくては) shows an empty chain.

## Current Output
  食べなくちゃ → └─ (empty)

## Expected
  食べなくちゃ → ← 食べる → なくちゃ (must do, contraction)

## Root Cause

The abbreviation handler _handler_abbr_nakereba() reconstructs root + なければ and calls find_word_full(). For なくちゃ, ABBREVIATION_STEMS['nakereba'] = 4, so it removes 4 chars from the root's ない form... but なくちゃ contracts from なくては, not なければ.

Actually なくちゃ is registered separately alongside なきゃ:
  _load_abbr('nakereba', 'なきゃ')
  _load_abbr('nakereba', 'なくちゃ')

The handler appends なければ to the root. Root for 食べなくちゃ with stem=4: 食べなくちゃ has 6 chars, stem removes 4 from ない → root=食べ... then 食べ+なければ = 食べなければ. But find_word_full may not find this.

## Code Locations
- himotoki/suffixes.py:549 - _handler_abbr_nakereba()
- himotoki/suffixes.py:295 - ABBREVIATION_STEMS
- himotoki/suffixes.py:282 - abbreviation registrations

## How to Verify
  python -m himotoki -f '食べなくちゃ'
  python -m himotoki -f '食べなきゃ'  # Compare
""",
    },

    # =========================================================================
    # Issue 12: Keigo お〜になる pattern not recognized
    # =========================================================================
    {
        "title": "Keigo patterns not recognized (お読みになる, お書きする, etc.)",
        "labels": "enhancement,conjugation",
        "description": """## Problem

Honorific/humble keigo patterns using お〜になる and お〜する are not recognized as grammatical constructions.

## Current Output
  お読みになる → (none)
  お書きする → ← 書く | Continuative (~i) (き) (partial, loses お and なる)
  お読みください → misparse as 下さる imperative

## Expected
  お読みになる → お + 読む (continuative) + になる (honorific)
  お書きする → お + 書く (continuative) + する (humble)
  お読みください → お + 読む (continuative) + ください (honorific request)

## Root Cause

The お〜になる/お〜する pattern is a periphrastic honorific/humble construction that is NOT in the suffix system. It requires:
1. Recognizing お as honorific prefix
2. Finding the verb stem (continuative)
3. Matching になる/する/ください as the honorific/humble marker

This is a multi-token grammatical pattern, not a simple suffix. Implementing it requires either:
- A new pattern matcher for お+stem+になる/する/ください
- Or treating it as a special compound type

## Scope: Enhancement beyond ichiran

## Code Locations
- himotoki/suffixes.py - would need new suffix type or pattern
- himotoki/constants.py - SEQ_O_PREFIX already exists

## How to Verify
  python -m himotoki -f 'お読みになる'
  python -m himotoki -f 'お書きする'
""",
    },

    # =========================================================================
    # Issue 13: Sentence-ending modals (のだ, べきだ, はずだ, etc.)
    # =========================================================================
    {
        "title": "Sentence-ending modal expressions not recognized (のだ, べきだ, はずだ, etc.)",
        "labels": "enhancement,conjugation",
        "description": """## Problem

Common sentence-ending modal expressions are not parsed as grammatical constructions. They are multi-token patterns that the suffix system doesn't handle.

## Failing Patterns

1. 食べるのだ (explanatory: it is that...) → no chain
2. 食べるんだ (contracted explanatory) → no chain
3. 食べるべきだ (should eat) → no chain
4. 食べるはずだ (expected to eat) → no chain
5. 食べるつもりだ (intend to eat) → no chain
6. 食べることにする (decide to eat) → no chain
7. 食べることができる (can eat) → no chain
8. 食べるな (prohibitive: don't eat!) → no chain

## Root Cause

These are multi-word grammatical constructions, not single-word suffix patterns:
- のだ/んだ = nominalizer の + copula だ
- べきだ = べき (should) + copula だ
- はずだ = はず (expectation) + copula だ
- つもりだ = つもり (intention) + copula だ
- ことにする = こと (fact) + に + する (decide)
- ことができる = こと + が + できる (ability)
- な (prohibitive) = sentence-final particle

These would require a new grammar pattern recognizer or multi-word expression handler. Currently out of scope for the suffix system (ichiran doesn't handle these either).

## Scope: Enhancement - low priority, multi-word patterns

## How to Verify
  python -m himotoki -f '食べるのだ'
  python -m himotoki -f '食べるべきだ'
""",
    },

    # =========================================================================
    # Issue 14: Additional compound verbs with no chain
    # =========================================================================
    {
        "title": "Compound verbs show no chain (kakeru, naosu, yamu, mawaru, komu, etc.)",
        "labels": "enhancement,conjugation",
        "description": """## Problem

Compound verbs (V-stem + V) that exist as dictionary entries show no conjugation chain at all. Same root cause as Issue 1 (dict entries hide compound analysis), but these may not even have suffix compound matches to begin with.

## Failing Patterns

1. 食べかける (half-done/start to) → no chain, dict entry
2. 書き直す (rewrite/redo) → no chain, dict entry
3. 泣き止む (stop crying) → no chain, dict entry
4. 走り回る (run around) → no chain, dict entry
5. 飲み込む (gulp down) → no chain, dict entry
6. 切り替える (switch over) → no chain, dict entry
7. 取り出す (take out) → no chain, dict entry
8. 引き受ける (undertake) → no chain, dict entry

## Root Cause

Unlike suffixes (にくい, すぎる, etc.), these second verbs (かける, 直す, 止む, 回る, etc.) are NOT registered in the suffix system. They are standalone dictionary entries.

The suffix system currently registers: 始める, 終わる, 続ける, 過ぎる, 合う, 出す. The above verbs are NOT registered because they are full standalone verbs (not grammaticalized suffixes).

## Scope: Enhancement

Could register additional compound verb patterns as suffixes:
- かける (start/half-done) - partially grammaticalized
- 直す (redo) - productive suffix meaning

But most of these (止む, 回る, 込む) are lexicalized compounds, not productive suffixes.

## Code Locations
- himotoki/suffixes.py - would need new registrations
- himotoki/lookup.py - compound verb recognition

## How to Verify
  python -m himotoki -f '書き直す'
  python -m himotoki -f '走り回る'
""",
    },

    # =========================================================================
    # Issue 15: くらい suffix chain cuts off
    # =========================================================================
    {
        "title": "くらい suffix chain cuts off - label not shown",
        "labels": "conjugation",
        "description": """## Problem

食べくらい shows the Continuative chain but くらい itself has no label in the display.

## Current Output
  食べくらい → ← 食べる | Continuative (~i) (たべ): and (stem)

## Expected
  食べくらい → ← 食べる | Continuative (~i) (たべ) → くらい (about/approximately)

## Root Cause

Same as the base-form suffix label issue (himotoki-z5js). The compound component for くらい is rendered as bare kana without the SUFFIX_DESCRIPTION. The description 'about/approximately' exists but get_suffix_description() is not called.

This is a duplicate of himotoki-z5js (suffix descriptions not shown). Will be fixed when that issue is resolved.

## Code Locations
- himotoki/output.py:1697 - bare kana display
- himotoki/suffixes.py:62 - SUFFIX_DESCRIPTION for kurai exists

## How to Verify
  python -m himotoki -f '食べくらい'
""",
    },
]

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    
    if which == "all":
        indices = range(len(issues))
    else:
        indices = [int(x) - 1 for x in which.split(",")]
    
    for i in indices:
        issue = issues[i]
        print(f"\n[{i+1}/{len(issues)}] {issue['title']}")
        create_issue(issue["title"], issue["description"], issue.get("labels", "conjugation"))
