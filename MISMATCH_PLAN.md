# Mismatch Priority Plan

**Current Status**: 23 mismatches, 88 partial matches (54.5% exact match rate)

## Summary of Mismatches by Category

### 🔴 HIGH PRIORITY - Himotoki bugs (clear errors)

| # | Sentence | Issue | Root Cause |
|---|----------|-------|------------|
| 5 | 彼が来るかどうかはまだわからない | `はま` + `だ` instead of `は` + `まだ` | Boundary detection broken |
| 10 | 困っている人がいたら | `人がい` + `たら` instead of `人` + `が` + `いたら` | Boundary detection broken |
| 13 | 言いたそう | `言` + `いたそう` instead of `言いたそう` | Suffix attachment broken |
| 17 | おすすめ | `お` + `すすめ` instead of `おすすめ` | Word boundary issue |
| 19 | やっとかないと | `やっと` + `かない` instead of proper parse | Contracted form issue |

### 🟡 MEDIUM PRIORITY - Segmentation style differences

| # | Sentence | Issue | Notes |
|---|----------|-------|-------|
| 2 | してる vs している | Himotoki keeps contracted, Ichiran expands | Both valid |
| 18 | 怒ってる vs 怒っている | Same pattern | Both valid |
| 3 | とは vs と + は | Particle splitting | Both valid |
| 6, 7 | 無理をしなければ, 運が良ければ | Compound vs split | Himotoki arguably better |
| 8 | 勉強し + 続けている vs 勉強 + し続けている | Verb split point | Style difference |
| 9 | 言わないで vs 言わない + で | ~ないで handling | Style difference |
| 11 | でないと vs でない + と | Grammar pattern | Style difference |
| 14, 16 | ~そうにない | Split vs merged | Style difference |
| 15 | 気がしてきた | Compound vs split | Style difference |
| 21 | もの + であった vs も + ので + あった | Copula handling | Both valid |
| 22 | につれ vs に + つれ | Suffix handling | Style difference |

### 🟢 LOW PRIORITY - Edge cases / Ichiran issues

| # | Sentence | Issue | Notes |
|---|----------|-------|-------|
| 1 | 帰ん | User prefers Himotoki - SKIP |
| 4 | なぜそう | Himotoki merging なぜそう | Minor |
| 12 | おいしそう | Ichiran broken (お + いし + そうですね) | Himotoki is correct! |
| 20 | あれってさ | Ichiran incomplete (stops early) | Ichiran issue |
| 23 | 百円ショップ | Compound word not in dict | Would need data |

---

## Recommended Fix Order

### Phase 1: Critical boundary detection bugs

1. **#5 はまだ → はま + だ** - Clear boundary detection failure
2. **#10 人がいたら → 人がい + たら** - Clear boundary detection failure  
3. **#13 言いたそう → 言 + いたそう** - Suffix attachment failure
4. **#17 おすすめ → お + すすめ** - Word not recognized

### Phase 2: Contracted forms (if time permits)

5. **#19 やっとかないと** - Contracted form handling

### Phase 3: Style alignment (low priority)

These are style differences where both are linguistically valid - may skip.

---

## Current Fix Progress

- ✅ Fixed compound text parsing (`言わず` was showing as `言わないず` due to wrong text extraction)
- ✅ Added synergy for `かどうか` + `は` to fix はまだ boundary issue (23→22 mismatches)
- 🔄 Investigated `人がい` issue - dictionary contains malformed entry without senses
- 🔄 Investigated `おすすめ` issue - scoring favors お+すすめ over おすすめ

## Remaining Mismatches Analysis

### Fixable with synergies/data:
1. **#5 はまだ** - ✅ FIXED with かどうか+は synergy
2. **#10 人がいたら** - Needs dictionary cleanup (人がい entry has no senses)
3. **#17 おすすめ** - Scoring issue: お+すすめ(100) > おすすめ(64)
4. **#13 言いたそう** - Suffix attachment issue

### Style differences (both valid):
5. **#2, #18 してる/怒ってる** - Himotoki keeps contracted forms, Ichiran expands
6. **#3 とは vs と+は** - Particle splitting style
7. **#6, #7 運が良ければ等** - Himotoki properly splits, Ichiran treats as compound
8. **#8, #9 勉強し/言わないで** - Verb split points differ
9. **#11, #14, #16 でないと/そうにない** - Grammar pattern handling

### Low priority / Ichiran issues:
10. **#1 帰ん** - User prefers Himotoki's split
11. **#12 おいしそう** - Ichiran broken (お+いし+そうですね), Himotoki correct
12. **#20 あれってさ** - Ichiran incomplete (stops early)
13. **#21, #22 ものであった, につれ** - Style differences
14. **#23 百円ショップ** - Compound word not in dictionary
