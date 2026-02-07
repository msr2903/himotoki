# Himotoki v0.3.1 Release Notes

**Release date:** 2025-07-18

This patch release improves conjugation tree display quality and adds three
new te-form suffix compounds.

## Highlights

### Auxiliary Verb Labels Now Visible

Conjugated auxiliary verbs in compound words now show their identity and
description in the conjugation tree.  Previously, the auxiliary name was
silently dropped.

**Before (v0.3.0):**
```
飲んでしまった:
  ← 飲む 【のむ】
  └─ Conjunctive (~te) (んで)
       └─ Past (~ta) (った): did/was
```

**After (v0.3.1):**
```
飲んでしまった:
  ← 飲む 【のむ】
  └─ Conjunctive (~te) (んで)
       └─ しまう (indicates completion (to finish ...))
            └─ Past (~ta) (った): did/was
```

### Suffix Descriptions in Display

Base-form suffix components now include their grammatical description:

```
食べている:
  ← 食べる 【たべる】
  └─ Conjunctive (~te) (て)
       └─ いる (indicates continuing action (to be ...ing))
```

### New Te-Form Suffixes

Three common te-form auxiliaries are now recognized as compound words:

| Pattern | Meaning | Example |
|---------|---------|---------|
| てみる  | try doing | 食べてみる |
| てあげる | do for someone | 食べてあげる |
| てほしい | want someone to | 食べてほしい |

## Issues Resolved

- `himotoki-nvuf`: Conjugation chain drops auxiliary verb labels when suffix is conjugated
- `himotoki-z5js`: Enhancement: show suffix descriptions in conjugation chain display
- `himotoki-tsdr`: Enhancement: register missing te-form suffixes (miru, ageru, hoshii)

## Test Coverage

- 21 new tests added (432 total, up from 411)
- All tests passing
