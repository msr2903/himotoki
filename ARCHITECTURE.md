# Himotoki Architecture

This document describes the technical architecture of Himotoki, a Python port of ichiran.

## Overview

Himotoki is a Japanese morphological analyzer that segments Japanese text into words and provides dictionary definitions. It is a faithful port of ichiran (written in Common Lisp) to Python.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          CLI Interface                          │
│                        (himotoki/cli.py)                        │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Output Formatting                          │
│                      (himotoki/output.py)                        │
│  - WordInfo dataclass                                           │
│  - JSON/text formatting                                         │
│  - dict_segment() entry point                                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Segmentation Engine                           │
│                    (himotoki/segment.py)                         │
│  - find_sticky_positions() - word boundary detection            │
│  - join_substring_words() - candidate word finding              │
│  - find_best_path() - dynamic programming                       │
│  - TopArray - priority queue for path tracking                  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Lookup & Scoring                             │
│                    (himotoki/lookup.py)                          │
│  - find_word() - database lookup                                │
│  - calc_score() - scoring algorithm                             │
│  - Segment/SegmentList - word match containers                  │
│  - ConjData - conjugation tracking                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Character Utilities                            │
│                  (himotoki/characters.py)                        │
│  - Character classification (kana/kanji detection)              │
│  - Kana conversion (hiragana ↔ katakana)                        │
│  - Voicing transformations (rendaku)                            │
│  - Romanization                                                 │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Database Layer                               │
│                   (himotoki/db/*.py)                             │
│  - SQLAlchemy ORM models                                        │
│  - Connection management                                        │
│  - Caching                                                      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SQLite Database                            │
│                     (himotoki.db file)                           │
│  - Entry, KanjiText, KanaText                                   │
│  - Sense, Gloss, SenseProp                                      │
│  - Conjugation, ConjProp, ConjSourceReading                     │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema

### Core Tables

```sql
-- Dictionary entries
CREATE TABLE entry (
    seq INTEGER PRIMARY KEY,  -- JMdict sequence number
    content TEXT,             -- Original XML
    root_p BOOLEAN,           -- Is this a root entry?
    n_kanji INTEGER,          -- Number of kanji readings
    n_kana INTEGER            -- Number of kana readings
);

-- Kanji readings
CREATE TABLE kanji_text (
    id INTEGER PRIMARY KEY,
    seq INTEGER REFERENCES entry(seq),
    text TEXT,                -- Kanji text
    ord INTEGER,              -- Reading order (0 = primary)
    common INTEGER,           -- Commonness rank
    best_kana TEXT            -- Best matching kana reading
);

-- Kana readings
CREATE TABLE kana_text (
    id INTEGER PRIMARY KEY,
    seq INTEGER REFERENCES entry(seq),
    text TEXT,                -- Kana text
    ord INTEGER,              -- Reading order
    common INTEGER,           -- Commonness rank
    best_kanji TEXT           -- Best matching kanji
);

-- Word senses (definitions)
CREATE TABLE sense (
    id INTEGER PRIMARY KEY,
    seq INTEGER REFERENCES entry(seq),
    ord INTEGER               -- Sense order
);

-- English glosses
CREATE TABLE gloss (
    id INTEGER PRIMARY KEY,
    sense_id INTEGER REFERENCES sense(id),
    text TEXT,                -- English meaning
    ord INTEGER               -- Gloss order
);

-- Sense properties (POS, usage, etc.)
CREATE TABLE sense_prop (
    id INTEGER PRIMARY KEY,
    sense_id INTEGER REFERENCES sense(id),
    seq INTEGER,
    tag TEXT,                 -- Property tag (pos, misc, etc.)
    text TEXT,                -- Property value
    ord INTEGER
);

-- Conjugation links
CREATE TABLE conjugation (
    id INTEGER PRIMARY KEY,
    seq INTEGER REFERENCES entry(seq),   -- Conjugated form
    from_seq INTEGER REFERENCES entry(seq),  -- Root form
    via INTEGER               -- Intermediate form (for secondary conj)
);

-- Conjugation properties
CREATE TABLE conj_prop (
    id INTEGER PRIMARY KEY,
    conj_id INTEGER REFERENCES conjugation(id),
    conj_type INTEGER,        -- Conjugation type ID
    pos TEXT,                 -- Part of speech
    neg BOOLEAN,              -- Is negative?
    fml BOOLEAN               -- Is formal?
);

-- Source reading mappings
CREATE TABLE conj_source_reading (
    id INTEGER PRIMARY KEY,
    conj_id INTEGER REFERENCES conjugation(id),
    text TEXT,                -- Conjugated text
    source_text TEXT          -- Source (root) text
);
```

## Segmentation Algorithm

### Step 1: Find Sticky Positions

Identify positions where words cannot start or end:
- After sokuon (っ) - next consonant must be part of same word
- Before modifier kana (ゃ, ゅ, ょ, ー) - must attach to previous

```python
def find_sticky_positions(text: str) -> List[int]:
    """Return positions where word boundaries are forbidden."""
```

### Step 2: Find Candidate Words

For each position, find all dictionary words that could start there:

```python
def find_substring_words(text: str, sticky: List[int]) -> Dict[str, List]:
    """Build hash of all possible word matches by substring."""
```

### Step 3: Score Candidates

Each word candidate receives a score based on:
- **Commonness** (common words score higher)
- **Length** (longer words generally preferred)
- **Kanji presence** (kanji words score higher)
- **Part of speech** (particles get special handling)
- **Conjugation status** (conjugated forms need source verification)
- **Context** (final position, preceding/following words)

```python
def calc_score(session, word: WordMatch, final: bool = False, ...) -> Tuple[float, Dict]:
    """Calculate score for a word match."""
```

### Step 4: Dynamic Programming Path Finding

Use dynamic programming to find the optimal segmentation:

```python
def find_best_path(segment_lists: List[SegmentList], text_length: int, limit: int = 5):
    """Find best N segmentation paths using TopArray priority queues."""
```

The algorithm:
1. Initialize with gap penalty for entire text
2. For each segment position, track top N paths ending there
3. Connect non-overlapping segments, accumulating scores
4. Apply gap penalties for uncovered regions
5. Return top N complete paths

### Step 5: Format Output

Convert segments to WordInfo objects and fill gaps:

```python
def fill_segment_path(session, text: str, path: List[SegmentList]) -> List[WordInfo]:
    """Convert segment path to WordInfo list, filling gaps."""
```

## Scoring System

### Length Coefficients

Different character types use different length bonus sequences:

```python
LENGTH_COEFF_SEQUENCES = {
    'strong': [0, 1, 8, 24, 40, 60],   # Kanji, katakana
    'weak': [0, 1, 4, 9, 16, 25, 36],  # Hiragana
    'tail': [0, 4, 9, 16, 24],         # Suffix context
    'ltail': [0, 4, 12, 18, 24],       # Long suffix
}
```

### Gap Penalty

Uncovered text receives a penalty:
```python
GAP_PENALTY = -500  # Per character
```

### Kanji Break Penalty

Splitting kanji sequences is penalized:
```python
def kanji_break_penalty(kanji_break, score, info, text, ...):
    """Reduce score for words that split kanji sequences."""
```

## Porting Notes

### Lisp to Python Translation

| Lisp Construct | Python Equivalent |
|----------------|-------------------|
| `defclass` | `dataclass` or class |
| `defstruct` | `dataclass` |
| `defun` | `def` function |
| `defparameter` | Module constant |
| `defcache` | `ensure_cache()` pattern |
| `with-connection` | Session context manager |
| `select-dao` | SQLAlchemy query |

### Key Differences

1. **Database**: PostgreSQL → SQLite
   - Requires schema adaptation
   - No stored procedures
   - Simpler deployment

2. **Performance**: Lisp optimizations → Python idioms
   - Type declarations → type hints
   - `(declare (optimize ...))` → not applicable
   - CLOS dispatch → Python method resolution

3. **Memory**: Lisp GC → Python reference counting
   - Different caching strategies
   - Session management

## File Mapping

| ichiran File | himotoki File | Purpose |
|--------------|---------------|---------|
| dict.lisp | lookup.py, output.py | Main dictionary functions |
| dict-split.lisp | segment.py | Segmentation algorithm |
| characters.lisp | characters.py | Character utilities |
| cli.lisp | cli.py | Command line interface |
| conn.lisp | db/connection.py | Database connection |
| dict-load.lisp | loading/jmdict.py | Dictionary loading |
| dict-grammar.lisp | loading/conjugations.py | Grammar/conjugation |

## Testing Strategy

### Unit Tests
- Character utilities
- Database models
- Individual functions

### Integration Tests
- Full segmentation pipeline
- CLI output comparison
- Database loading

### Validation
- Compare output against ichiran
- Use same test sentences
- Verify identical segmentation

Himotoki vs Ichiran: Comprehensive Debugging Guide
1. Architecture Overview
Component	Ichiran (Common Lisp)	Himotoki (Python)
Entry Point	dict-segment in dict.lisp	dict_segment in output.py
Scoring	calc-score in dict.lisp	calc_score in lookup.py
Path Finding	find-best-path in dict.lisp	find_best_path in segment.py
Splits	dict-split.lisp	splits.py
Synergies	dict-grammar.lisp	synergies.py
Counters	dict-counters.lisp	counters.py
Characters	characters.lisp	characters.py
2. Segmentation Pipeline
3. Critical Scoring Constants
Constant	Ichiran	Himotoki	Description
*score-cutoff* / SCORE_CUTOFF	5	5	Minimum score to keep
Gap penalty	-500	-500	Per-char penalty for gaps
Max word length	50	50	Max chars to search
Cull ratio	0.5	0.5	Cutoff for culling
4. Length Coefficient Sequences
Type	Values	Usage
strong	[1, 8, 24, 40, 60]	Kanji/katakana words
weak	[1, 4, 9, 16, 25, 36]	Hiragana-only words
tail	[4, 9, 16, 24]	Suffix context bonus
ltail	[4, 12, 18, 24]	Longer suffix bonus
⚠️ Potential Issue: Himotoki adds 0 at index 0 for 1-based indexing—verify get_length_coeff uses consistent indexing.

5. Key Score Flags
Flag	What It Checks	Impact
kanji_p	Contains kanji	+3-5 bonus
primary_p	Is primary reading	+2-10 bonus
common_p	Has commonness tag	+2-20 bonus
particle_p	Is particle (助詞)	+2 bonus
long_p	Length ≥ threshold	+length bonus
root_p	Is root (not conjugated)	Affects scoring
6. Conjugation Types to Watch
ID	Name	Notes
50	Adverbial	Weak form
51	Adjective Stem	Weak form
52	Negative Stem	Weak form
53	Causative (～す)	Weak form
9 (neg)	Volitional Negative	Weak form
7. Synergy Bonuses
Pattern	Left Word	Right Word	Score
Noun+Particle	is_noun	In NOUN_PARTICLES	10 + 4×len
Noun+だ	is_noun	seq=2089020	10
Na-adjective	adj-na	な/に	15
No-adjective	adj-no	の	15
To-adverb	adv-to	と	10 + 10×len
8. Database Differences
Aspect	Ichiran	Himotoki
DB Type	PostgreSQL	SQLite
Aggregation	string_agg()	group_concat()
NULL	:null keyword	Python None
Caching	defcache macro	dict/lru_cache
9. Debugging Checklist
When mismatches occur:

Compare sticky positions - Are sokuon/modifiers detected the same?
Compare candidate words - Do both find the same dictionary entries?
Compare scores - Print calc_score intermediate values
Check synergies - Are bonuses/penalties applied identically?
Verify path selection - Compare TopArray alternatives
10. Key Seq Numbers to Know
Seq	Word	Usage
2089020	だ (copula)	Noun+だ synergy
2029110	な	Na-adjective synergy
1469800	の	No-adjective synergy
2013800	ちゃう	Skip word
2017560	たい	Suffix :tai
1577980	いる	Suffix :teiru
Further Considerations
What type of mismatch are you seeing? Segmentation boundary differences / Score ranking differences / Missing words
Do you have specific test sentences? I can trace through both systems for the failing case
Is your SQLite DB in sync with Ichiran's PostgreSQL? Dictionary version mismatches can cause differences
Please share the specific mismatch problem you'd like me to debug, and I'll trace through both codebases to identify the root cause.