# Himotoki v0.3.1 Release Notes

**Release date:** 2026-02-08

This patch release greatly expands suffix compound coverage, fixes reading
generation bugs, and adds na-adjective suffix support.

## Highlights

### 30+ New Suffix Compounds

Himotoki now recognizes a much wider range of productive suffix patterns:

**Compound verbs** (ren'youkei stem + verb):

| Suffix | Meaning | Example |
|--------|---------|---------|
| 出す   | burst out / start suddenly | 泣き出す |
| 切る   | do completely | 使い切る |
| 合う   | do mutually / together | 食べ合う |
| 込む   | do into / thoroughly | 食べ込む |
| 始める | start doing | 食べ始める |
| 終わる | finish doing | 食べ終わる |
| 付ける | be accustomed to | 飲みつける |

**Te-form auxiliaries** (verb + て + auxiliary):

| Suffix | Meaning | Example |
|--------|---------|---------|
| てみる  | try doing | 食べてみる |
| てあげる | do for someone | 食べてあげる |
| てほしい | want someone to | 食べてほしい |
| てやる   | do for (casual) | 食べてやる |
| てまいる | go/come (humble) | 食べてまいる |
| てくださる | kindly do (honorific) | 食べてくださる |
| てさしあげる | do for (humble) | 食べてさしあげる |

**I-adjective / na-adjective suffixes**:

| Suffix | Meaning | Example |
|--------|---------|---------|
| っぽい | -ish / tends to | 忘れっぽい, 静かっぽい |
| 難い   | difficult to (literary) | 信じ難い |
| み     | -ness (nominalization) | 深み, 静かみ |
| らしい+noun | -like (as noun) | 男らしさ |
| 方     | way of doing | 食べ方 |

**Other patterns**: 放題 (unlimited), やすい (easy to), まくる (relentlessly),
直す (redo), 損なう (fail to), 忘れる (forget to), 終える (finish), 辛い
(difficult to), ぎみ (tending to), っぱなし (left doing), たち (plural)

### Auxiliary Verb Labels in Conjugation Trees

Conjugated auxiliary verbs now show their identity and description:

```
飲んでしまいたかった:
  ← 飲む 【のむ】
  └─ Conjunctive (~te) (んで)
       └─ しまう (indicates completion / to do something by accident or regret)
            └─ Continuative (~i) (い): and (stem)
                 └─ たい (want to... / would like to...)
                      └─ Past (~ta) (かった): did/was
```

### Na-Adjective + Suffix Chaining

Na-adjective stems now connect to productive suffixes:

- 静かすぎる → shizukasugiru (too quiet)
- 元気すぎる → genkisugiru (too energetic)
- 静かっぽい → shizukappoi (quiet-ish)
- 静かみ → shizukami (quietness)
- 静かそう → shizukasou (looks quiet)

### Reading Generation Fixes

- **ないで reading**: Compound kana now uses the correct kanji reading
  ordinal. 食べないでほしい shows 【たべないで ほしい】 (was incorrectly
  showing 【たべなくて ほしい】).
- **ちゃ/じゃ contraction reading**: Surface pronunciation is preserved.
  食べちゃいけない shows 【たべちゃ】 (was showing 【たべは】).

### Separate Negative Tree Levels

Negative conjugations are now split into distinct tree levels instead of
being combined with the conjugation type. For example, 食べられなかった:

```
Before:  └─ not Past (~ta) (なかった): not did/was
After:   └─ Negative (ない): not
              └─ Past (~ta) (かった): did/was
```

This gives a clearer, more linguistically accurate breakdown. Also
applies to formal negative (ません → Polite + Negative), potential
negative (行けない → Potential + Negative), and adjective negative forms.

## Issues Resolved

### Batch 1 -- New suffix patterns
- `himotoki-5yb6`: Register っぽい (-ish) as compound suffix
- `himotoki-1j3e`: Register 難い (difficult to, literary) as compound suffix
- `himotoki-dvn5`: Register 出す (burst out / start suddenly) as compound verb suffix
- `himotoki-xrzn`: Register 切る (do completely) as compound verb suffix
- `himotoki-2qer`: Register 方 (way of doing) as compound suffix
- `himotoki-3jyf`: Register み (-ness, nominalization) as compound suffix
- `himotoki-07te`: Register らしい + noun (noun-like) pattern
- `himotoki-a7vz`: Register やすい (easy to) as compound suffix

### Batch 2 -- More suffix patterns
- `himotoki-kus5`: Register まくる (relentlessly) suffix
- `himotoki-qfc5`: Register 直す (redo) suffix
- `himotoki-1bnw`: Register 損なう (fail to) suffix
- `himotoki-bqjn`: Register 忘れる (forget to do) suffix
- `himotoki-1etb`: Register 終える (finish doing) suffix
- `himotoki-h3s0`: Register 辛い (difficult to) suffix
- `himotoki-c2wc`: Register ぎみ (-ish / tending to) suffix
- `himotoki-dci3`: Register っぱなし (left doing) suffix
- `himotoki-z9dz`: Register たち (plural) suffix
- `himotoki-oh5y`: Register なで (na-adj conjunctive) suffix

### Batch 3 -- Compound verbs and te-form auxiliaries
- `himotoki-wnza`: Register 合う (do mutually) compound verb
- `himotoki-8vok`: Register 込む (do thoroughly) compound verb
- `himotoki-oqot`: Register 放題 (unlimited) suffix
- `himotoki-i9jl`: Register 終わる/始める compound verbs
- `himotoki-7jut`: Register te-form auxiliaries (やる, まいる, くださる, さしあげる)
- `himotoki-om3h`: Register 付ける (accustomed to) compound verb

### Batch 4 -- Reading bugs and na-adjective support
- `himotoki-99w1`: Fix ないで reading showing なくて instead of ないで
- `himotoki-uesp`: Fix ちゃ contraction showing は reading instead of ちゃ
- `himotoki-l68s`: Add na-adjective support to すぎる, っぽい, み handlers

### Earlier fixes (grammar patterns)
- `himotoki-nvuf`: Conjugation chain drops auxiliary verb labels
- `himotoki-z5js`: Show suffix descriptions in conjugation chain display
- `himotoki-tsdr`: Register てみる, てあげる, てほしい te-form suffixes
- Plus 13 grammar pattern issues (abbreviations, suffix chains, handler improvements)

## Test Coverage

- 433 tests (up from 411 in v0.3.0)
- All tests passing
