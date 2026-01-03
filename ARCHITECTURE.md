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
