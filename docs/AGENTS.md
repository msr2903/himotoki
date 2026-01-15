# Himotoki AI Agent Context Guide

This document provides comprehensive context for AI agents working with the Himotoki codebase. It serves as a detailed technical reference for understanding the architecture, conventions, and implementation details.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture Overview](#architecture-overview)
3. [Core Concepts](#core-concepts)
4. [Module Deep Dive](#module-deep-dive)
5. [Data Flow](#data-flow)
6. [Database Schema](#database-schema)
7. [Scoring System](#scoring-system)
8. [Conjugation System](#conjugation-system)
9. [Suffix and Compound Word Handling](#suffix-and-compound-word-handling)
10. [Synergies and Segfilters](#synergies-and-segfilters)
11. [Counter Word Recognition](#counter-word-recognition)
12. [Testing Strategy](#testing-strategy)
13. [Development Commands](#development-commands)
14. [Code Conventions](#code-conventions)
15. [Key Constants and SEQ Numbers](#key-constants-and-seq-numbers)
16. [Common Patterns](#common-patterns)
17. [Troubleshooting Guide](#troubleshooting-guide)

---

## Issue Tracking

This project uses **bd (beads)** for issue tracking.
Run `bd prime` for workflow context, or install hooks (`bd hooks install`) for auto-injection.

**Quick reference:**
- `bd ready` - Find unblocked work
- `bd create "Title" --type task --priority 2` - Create issue
- `bd close <id>` - Complete work
- `bd sync` - Sync with git (run at session end)

For full workflow details: `bd prime`

For GitHub Copilot users:
Add the same content to .github/copilot-instructions.md

How it works:
   • bd prime provides dynamic workflow context (~80 lines)
   • bd hooks install auto-injects bd prime at session start
   • AGENTS.md only needs this minimal pointer, not full instructions

---

## Project Overview

**Himotoki** (紐解き, "unraveling") is a Python remake of [ichiran](https://github.com/tshatrov/ichiran), a comprehensive Japanese morphological analyzer written in Common Lisp. It segments Japanese text into words, provides dictionary definitions, romanization, and conjugation analysis.

### Key Characteristics

| Aspect | Details |
|--------|---------|
| **Language** | Python 3.10+ |
| **Database** | SQLite (portable, ~3GB) |
| **Dictionary** | JMdict (EDRDG) |
| **Algorithm** | Viterbi-style dynamic programming |
| **Package Manager** | pip/uv with pyproject.toml |
| **Code Style** | Black (100 char line length), isort |
| **Type Checking** | mypy (optional) |
| **Testing** | pytest with hypothesis for property-based testing |

### Project Structure

```
himotoki/
├── himotoki/                 # Main package
│   ├── __init__.py           # Public API: analyze(), analyze_async(), warm_up()
│   ├── __main__.py           # Entry point for `python -m himotoki`
│   ├── cli.py                # Command-line interface
│   ├── segment.py            # Core segmentation algorithm (Viterbi DP)
│   ├── lookup.py             # Dictionary lookup and scoring engine
│   ├── output.py             # WordInfo dataclass and output formatting
│   ├── models.py             # Pydantic models for API responses
│   ├── characters.py         # Character utilities (kana/kanji detection, romanization)
│   ├── constants.py          # Consolidated constants (conjugation types, SEQ numbers)
│   ├── synergies.py          # Synergy bonuses and segfilter constraints
│   ├── suffixes.py           # Suffix compound word handling (〜たい, 〜ている, etc.)
│   ├── counters.py           # Counter word recognition (三匹, 五冊)
│   ├── splits.py             # Word split definitions for compound scoring
│   ├── setup.py              # First-time database setup and JMdict download
│   ├── db/                   # Database layer
│   │   ├── __init__.py
│   │   ├── connection.py     # SQLAlchemy engine, session management, caching
│   │   └── models.py         # ORM models (Entry, KanjiText, KanaText, etc.)
│   └── loading/              # Data loading utilities
│       ├── __init__.py
│       ├── jmdict.py         # JMdict XML parser and loader
│       ├── conjugations.py   # Conjugation rule generation
│       └── errata.py         # Manual dictionary corrections
├── tests/                    # Test suite
│   ├── conftest.py           # pytest fixtures (db_session)
│   ├── test_*.py             # Unit and property-based tests
│   └── data/                 # Test data files
├── scripts/                  # Developer utilities
│   ├── compare.py            # Compare output with ichiran
│   ├── init_db.py            # Database initialization helper
│   └── report.py             # HTML report generator
├── data/                     # Dictionary data (CSV files for conjugations)
├── docs/                     # Documentation
└── pyproject.toml            # Project configuration
```

---

## Architecture Overview

Himotoki follows a layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                     PUBLIC API (__init__.py)                     │
│  analyze(), analyze_async(), warm_up(), shutdown()              │
│  Models: WordResult, AnalysisResult, VocabularyResult           │
└────────────────────────────────────────────────────────────────┬┘
                                                                  │
┌────────────────────────────────────────────────────────────────▼┐
│                    CLI LAYER (cli.py)                           │
│  Command-line interface with multiple output formats            │
│  Subcommands: analyze (default), setup, init-db                 │
└────────────────────────────────────────────────────────────────┬┘
                                                                  │
┌────────────────────────────────────────────────────────────────▼┐
│                  OUTPUT LAYER (output.py)                       │
│  - WordInfo dataclass: canonical word representation            │
│  - dict_segment(): main entry point for segmentation            │
│  - fill_segment_path(): converts segments to WordInfo           │
│  - JSON/text formatting functions                               │
└────────────────────────────────────────────────────────────────┬┘
                                                                  │
┌────────────────────────────────────────────────────────────────▼┐
│               SEGMENTATION ENGINE (segment.py)                  │
│  - find_sticky_positions(): detect forbidden word boundaries    │
│  - join_substring_words(): find all candidate words             │
│  - find_best_path(): Viterbi-style dynamic programming          │
│  - TopArray: priority queue for tracking top N paths            │
└────────────────────────────────────────────────────────────────┬┘
                                                                  │
┌────────────────────────────────────────────────────────────────▼┐
│                LOOKUP & SCORING (lookup.py)                     │
│  - find_word_full(): database lookup with conjugation support   │
│  - calc_score(): complex scoring algorithm                      │
│  - Segment, SegmentList: word match containers                  │
│  - WordMatch, CompoundWord, ConjData: data structures           │
└────────────────────────────────────────────────────────────────┬┘
                                                                  │
┌─────────────────────────────────────────────────────────────────┤
│              GRAMMAR SUBSYSTEMS                                 │
├─────────────────┬─────────────────┬─────────────────────────────┤
│ synergies.py    │ suffixes.py     │ counters.py                 │
│ - Synergy bonus │ - Suffix cache  │ - Number parsing            │
│ - Segfilters    │ - ~たい, ~ている │ - Counter cache             │
│ - Penalties     │ - Abbreviations │ - Phonetic rules            │
└─────────────────┴─────────────────┴─────────────────────────────┤
                                                                  │
┌────────────────────────────────────────────────────────────────▼┐
│            CHARACTER UTILITIES (characters.py)                  │
│  - is_kana(), is_kanji(), has_kanji()                           │
│  - as_hiragana(), as_katakana()                                 │
│  - mora_length(), romanize_word()                               │
│  - get_char_class(): character classification                   │
└────────────────────────────────────────────────────────────────┬┘
                                                                  │
┌────────────────────────────────────────────────────────────────▼┐
│                  DATABASE LAYER (db/)                           │
│  - connection.py: SQLAlchemy engine, StaticPool, caching        │
│  - models.py: ORM models matching ichiran schema                │
│  - SQLite with WAL mode, memory-mapped I/O                      │
└────────────────────────────────────────────────────────────────┬┘
                                                                  │
┌────────────────────────────────────────────────────────────────▼┐
│                   SQLITE DATABASE                               │
│  himotoki.db (~3GB) stored in ~/.himotoki/                      │
│  Tables: entry, kanji_text, kana_text, sense, gloss,            │
│          sense_prop, conjugation, conj_prop, conj_source_reading│
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Concepts

### 1. Segmentation Problem

Given Japanese text (e.g., "学校で勉強しています"), find the optimal way to split it into words:

- 学校 (がっこう) - school
- で - at/in (particle)
- 勉強 (べんきょう) - study
- して - doing (conjugated する)
- います - is (ている form of いる)

### 2. The Algorithm: Viterbi-Style Dynamic Programming

The segmentation uses a classic pathfinding approach:

1. **Generate Candidates**: For each position, find all dictionary words that could start there
2. **Score Candidates**: Assign scores based on commonness, length, character type, context
3. **Find Best Path**: Use DP to find the highest-scoring non-overlapping word sequence
4. **Apply Grammar Rules**: Synergies boost valid patterns; segfilters block invalid ones

### 3. Key Data Structures

```python
# WordMatch: Raw database hit
@dataclass
class WordMatch:
    reading: Union[KanjiText, KanaText]  # Database record
    conjugations: Optional[List[int]]     # Conjugation chain
    
# Segment: Scored word candidate
@dataclass
class Segment:
    word: Union[WordMatch, CompoundWord, CounterText]
    score: float
    info: Dict[str, Any]  # Scoring metadata
    
# SegmentList: All segments at a position
@dataclass  
class SegmentList:
    segments: List[Segment]
    start: int
    end: int
    
# WordInfo: Final output representation
@dataclass
class WordInfo:
    type: WordType  # kanji, kana, gap
    text: str
    kana: Union[str, List[str]]
    seq: Optional[Union[int, List[int]]]
    conjugations: Optional[Union[List[int], str]]
    score: int
    meanings: List[str]
    pos: Optional[str]
    # ... conjugation info, compound info, etc.
```

---

## Module Deep Dive

### `himotoki/__init__.py` - Public API

The main entry points for using Himotoki:

```python
# Primary analysis function
def analyze(
    text: str,
    limit: int = 1,
    session: Optional[Session] = None,
    max_length: Optional[int] = None,
) -> List[Tuple[List[WordInfo], int]]:
    """Analyze Japanese text and return segmentation results."""

# Async version for FastAPI/asyncio
async def analyze_async(
    text: str,
    limit: int = 1,
    timeout: Optional[float] = None,
) -> List[Tuple[List[WordInfo], int]]:
    """Async version using thread pool (SQLite isn't truly async)."""

# Cache initialization
def warm_up(verbose: bool = False) -> Tuple[float, dict]:
    """Pre-initialize caches: archaic words, suffixes, counters."""

# Cleanup
def shutdown():
    """Cleanup thread pool and database connections."""
```

### `himotoki/segment.py` - Core Algorithm

**Key Functions:**

```python
def segment_text(session, text, limit=5) -> List[Tuple[List[Segment], float]]:
    """Main entry: segment text into words."""

def find_sticky_positions(text) -> List[int]:
    """Find positions where words can't start/end (after sokuon, before modifiers)."""

def join_substring_words(session, text) -> List[SegmentList]:
    """Find all possible word matches, score them, return as SegmentLists."""

def find_best_path(segment_lists, text_length, limit=5) -> List[Tuple[List, float]]:
    """Viterbi DP to find optimal paths through segment lists."""
```

**TopArray Class**: Priority queue keeping top N paths by score:

```python
class TopArray:
    def __init__(self, limit: int = 5): ...
    def register(self, score: float, payload: Any): ...
    def get_items(self) -> List[TopArrayItem]: ...
```

### `himotoki/lookup.py` - Dictionary & Scoring

**Key Functions:**

```python
def find_word(session, word: str) -> List[WordMatch]:
    """Basic dictionary lookup by text."""

def find_word_full(session, word: str) -> List[WordMatch]:
    """Full lookup including conjugation tracing."""

def calc_score(session, word: WordMatch, final=False, kanji_break=None) -> Tuple[float, dict]:
    """The scoring algorithm - see Scoring System section."""

def get_conj_data(session, seq, from_seq=None) -> List[ConjData]:
    """Get conjugation chain data for a word."""
```

**Important Constants:**

```python
MAX_WORD_LENGTH = 50      # Maximum substring length to search
SCORE_CUTOFF = 5          # Minimum score to keep a candidate
GAP_PENALTY = -500        # Penalty per character of uncovered text
IDENTICAL_WORD_SCORE_CUTOFF = 0.5  # Cull threshold

# Length coefficient sequences
LENGTH_COEFF_SEQUENCES = {
    'strong': [0, 1, 8, 24, 40, 60],   # Kanji, katakana
    'weak': [0, 1, 4, 9, 16, 25, 36],  # Hiragana
    'tail': [0, 4, 9, 16, 24],         # Suffix context
    'ltail': [0, 4, 12, 18, 24],       # Long suffix
}
```

### `himotoki/output.py` - Output Formatting

**Key Functions:**

```python
def dict_segment(session, text, limit=5) -> List[Tuple[List[WordInfo], int]]:
    """Segment and convert to WordInfo list."""

def fill_segment_path(session, text, path) -> List[WordInfo]:
    """Convert segment path to WordInfo, filling gaps."""

def word_info_gloss_json(session, wi) -> Dict:
    """Convert WordInfo to JSON-compatible dict."""

def segment_to_json(session, text, limit=5) -> List:
    """ichiran-compatible JSON output."""
```

### `himotoki/constants.py` - Centralized Constants

All shared constants are defined here to avoid duplication:

- **Conjugation type IDs**: `CONJ_NON_PAST`, `CONJ_PAST`, `CONJ_TE`, etc.
- **SEQ numbers**: `SEQ_WA`, `SEQ_SURU`, `SEQ_IRU`, etc.
- **Interned POS tags**: Memory-efficient string interning
- **Weak/skip conjugation forms**: Forms that reduce or skip scoring

### `himotoki/characters.py` - Character Utilities

**Character Classification:**

```python
def get_char_class(char: str) -> Optional[str]:
    """Get kana class name: 'ka', 'shi', 'n', 'sokuon', etc."""

def is_kana(word: str) -> bool: ...
def is_hiragana(word: str) -> bool: ...
def is_katakana(word: str) -> bool: ...
def has_kanji(word: str) -> bool: ...
```

**Conversion:**

```python
def as_hiragana(text: str) -> str: ...
def as_katakana(text: str) -> str: ...
def mora_length(text: str) -> int:
    """Count mora (doesn't count small kana/long vowels)."""
```

**Romanization:**

```python
def romanize_word(text: str) -> str:
    """Convert kana to romaji."""
```

### `himotoki/synergies.py` - Grammar Patterns

**Synergies** give bonuses to valid grammatical patterns:

| Pattern | Example | Bonus |
|---------|---------|-------|
| Noun + Particle | 学校 + で | 10 + 4×len |
| Na-adjective + な/に | 静か + な | 15 |
| No-adjective + の | ... | 15 |
| To-adverb + と | ゆっくり + と | 10-50 |

**Segfilters** block invalid combinations:

- Auxiliary verbs must follow continuative form
- ん/んだ can't follow simple particles
- いる can't follow 終わる (つ + いる conflict)

### `himotoki/suffixes.py` - Suffix Compounds

Handles suffix patterns like:

- **〜たい**: want to (verb continuative + たい)
- **〜ている**: ongoing action (verb て-form + いる)
- **〜そう**: looks like (stem + そう)
- **〜ない**: negative (stem + ない)

The suffix cache maps suffix strings to handler functions:

```python
SUFFIX_HANDLERS = {
    'tai': _handler_tai,
    'teiru': _handler_teiru,
    'sou': _handler_sou,
    'nai': _handler_abbr_nai,
    # ...
}
```

### `himotoki/counters.py` - Counter Words

Recognizes patterns like 三匹 (sanbiki), 五冊 (gosatsu):

```python
@dataclass
class CounterText:
    text: str           # "三匹"
    kana: str           # "さんびき"
    number_value: int   # 3
    counter_text: str   # "匹"
    # ...

def find_counter_in_text(session, text) -> List[Tuple[int, int, CounterText]]:
    """Find all counter expressions in text."""
```

Handles phonetic rules (rendaku, gemination):

- 三 + 匹 → さんびき (b-voiced)
- 六 + 匹 → ろっぴき (geminated + p-voiced)

---

## Data Flow

### Analysis Pipeline

```
Input Text: "学校で勉強しています"
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│ 1. find_sticky_positions()                                    │
│    Result: [positions where boundaries are forbidden]         │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. find_substring_words()                                     │
│    For each valid start position:                             │
│    - Extract substrings up to MAX_WORD_LENGTH                 │
│    - Query database for matches (kanji_text, kana_text)       │
│    - Check suffix cache for compound patterns                 │
│    - Check counter cache for number expressions               │
│    Result: Dict[substring -> List[WordMatch]]                 │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. join_substring_words()                                     │
│    For each position with matches:                            │
│    - Convert WordMatch to Segment with calc_score()           │
│    - Apply SCORE_CUTOFF filter                                │
│    - Group into SegmentList by (start, end)                   │
│    Result: List[SegmentList] sorted by position               │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. find_best_path()                                           │
│    Dynamic programming over SegmentLists:                     │
│    - Initialize TopArray for each position                    │
│    - For each segment: register with accumulated score        │
│    - Apply gap_penalty() for uncovered regions                │
│    - Apply synergies/penalties between adjacent segments      │
│    - Track top N paths                                        │
│    Result: List[(path, score)] sorted by score                │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│ 5. fill_segment_path()                                        │
│    For each path:                                             │
│    - Convert Segments to WordInfo objects                     │
│    - Fill gaps with GAP WordInfo                              │
│    - Populate meanings, POS from database                     │
│    Result: List[WordInfo]                                     │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
Output: [(words=[WordInfo, ...], score=1234), ...]
```

---

## Database Schema

### Core Tables

```sql
-- Main entry table (one per JMdict entry)
entry (
    seq INTEGER PRIMARY KEY,      -- JMdict sequence number
    content TEXT,                 -- Original XML
    root_p BOOLEAN,               -- True if root entry (not synthetic)
    n_kanji INTEGER,              -- Count of kanji readings
    n_kana INTEGER,               -- Count of kana readings
    primary_nokanji BOOLEAN       -- True if primary is kana-only
)

-- Kanji readings
kanji_text (
    id INTEGER PRIMARY KEY,
    seq INTEGER REFERENCES entry(seq),
    text TEXT,                    -- Kanji text (e.g., "学校")
    ord INTEGER,                  -- Order (0 = primary)
    common INTEGER,               -- Commonness (lower = more common)
    common_tags TEXT,             -- Priority tags "[news1][ichi1]"
    conjugate_p BOOLEAN,          -- Generate conjugations?
    nokanji BOOLEAN,
    best_kana TEXT
)

-- Kana readings  
kana_text (
    id INTEGER PRIMARY KEY,
    seq INTEGER REFERENCES entry(seq),
    text TEXT,                    -- Kana text (e.g., "がっこう")
    ord INTEGER,
    common INTEGER,
    common_tags TEXT,
    conjugate_p BOOLEAN,
    nokanji BOOLEAN,
    best_kanji TEXT
)

-- Senses (meaning groups)
sense (
    id INTEGER PRIMARY KEY,
    seq INTEGER REFERENCES entry(seq),
    ord INTEGER
)

-- English glosses
gloss (
    id INTEGER PRIMARY KEY,
    sense_id INTEGER REFERENCES sense(id),
    text TEXT,                    -- English meaning
    ord INTEGER
)

-- Sense properties (POS, usage notes)
sense_prop (
    id INTEGER PRIMARY KEY,
    sense_id INTEGER REFERENCES sense(id),
    seq INTEGER,
    tag TEXT,                     -- "pos", "misc", "dial", "field"
    text TEXT,                    -- Property value
    ord INTEGER
)

-- Conjugation links
conjugation (
    id INTEGER PRIMARY KEY,
    seq INTEGER REFERENCES entry(seq),      -- Conjugated form
    from_seq INTEGER REFERENCES entry(seq), -- Root form
    via INTEGER                             -- Intermediate (secondary conj)
)

-- Conjugation properties
conj_prop (
    id INTEGER PRIMARY KEY,
    conj_id INTEGER REFERENCES conjugation(id),
    conj_type INTEGER,            -- Type ID (see constants.py)
    pos TEXT,                     -- Part of speech
    neg BOOLEAN,                  -- Negative form?
    fml BOOLEAN                   -- Formal/polite?
)

-- Source text mappings
conj_source_reading (
    id INTEGER PRIMARY KEY,
    conj_id INTEGER REFERENCES conjugation(id),
    text TEXT,                    -- Conjugated text
    source_text TEXT              -- Original/root text
)
```

### Key Indices

```sql
-- Fast lookups by text
ix_kanji_text_text, ix_kana_text_text

-- Composite for find_word
ix_kanji_text_text_seq, ix_kana_text_text_seq

-- Conjugation chain traversal
ix_conjugation_seq, ix_conjugation_from
```

---

## Scoring System

The `calc_score()` function in `lookup.py` implements a complex scoring algorithm. Here's how it works:

### Score Components

1. **Base Score** (5-30 points)
   - kanji_p (has kanji): +5
   - common_p (has commonness): +2 to +20 based on rank
   - primary_p (is primary reading): +2 to +10
   - particle_p (is particle): +2
   - pronoun_p: special handling

2. **Length Multiplier**
   - Uses coefficient sequences based on character type
   - `strong` for kanji/katakana: [0, 1, 8, 24, 40, 60]
   - `weak` for hiragana: [0, 1, 4, 9, 16, 25, 36]
   - Final score = base × coefficient[mora_length]

3. **Score Modifiers**
   - Archaic words: negative modifier
   - Weak conjugations: reduced score
   - Skip conjugations: excluded entirely
   - Kanji break penalty: splitting kanji hurts score

4. **Context Modifiers**
   - `final`: bonus for sentence-final particles
   - `kanji_break`: penalty for splitting kanji sequences

### Scoring Flags (KPCL)

The info dict contains a `kpcl` tuple: `[kanji_p, primary_p, common_p, long_p]`

- **kanji_p**: Contains kanji characters
- **primary_p**: Is the primary reading for entry
- **common_p**: Has commonness priority tags
- **long_p**: Length exceeds threshold

---

## Conjugation System

### Conjugation Types

| ID | Constant | Name |
|----|----------|------|
| 1 | CONJ_NON_PAST | Non-past |
| 2 | CONJ_PAST | Past (~ta) |
| 3 | CONJ_TE | Conjunctive (~te) |
| 4 | CONJ_PROVISIONAL | Provisional (~eba) |
| 5 | CONJ_POTENTIAL | Potential |
| 6 | CONJ_PASSIVE | Passive |
| 7 | CONJ_CAUSATIVE | Causative |
| 8 | CONJ_CAUSATIVE_PASSIVE | Causative-Passive |
| 9 | CONJ_VOLITIONAL | Volitional |
| 10 | CONJ_IMPERATIVE | Imperative |
| 11 | CONJ_CONDITIONAL | Conditional (~tara) |
| 12 | CONJ_ALTERNATIVE | Alternative (~tari) |
| 13 | CONJ_CONTINUATIVE | Continuative (~i) |
| 50 | CONJ_ADVERBIAL | Adverbial (custom) |
| 51 | CONJ_ADJECTIVE_STEM | Adjective Stem |
| 52 | CONJ_NEGATIVE_STEM | Negative Stem |
| 53 | CONJ_CAUSATIVE_SU | Causative (~su) |
| 54 | CONJ_ADJECTIVE_LITERARY | Old/Literary |

### Conjugation Data Structure

```python
@dataclass
class ConjData:
    seq: int          # Conjugated entry seq
    from_seq: int     # Root entry seq
    via: Optional[int]  # Intermediate for secondary conjugations
    prop: ConjProp    # Type, neg, fml info
    src_map: List[Tuple[str, str]]  # (conjugated_text, source_text)
```

### Secondary Conjugations

Some conjugations are "secondary" - they go through an intermediate form:

```
食べさせられる (causative-passive)
  └─ via: 食べさせる (causative)
       └─ from: 食べる (root)
```

---

## Suffix and Compound Word Handling

### Suffix Cache Structure

The suffix cache (`suffixes.py`) maps suffix text to handlers:

```python
_suffix_cache = {
    'たい': [('tai', KanaText)],      # want to
    'ている': [('teiru', KanaText)],  # ongoing
    'ていた': [('teiru', KanaText)],  # was doing
    'ねえ': [('nai', None)],          # abbreviation of ない
    # ...
}
```

### Handler System

Each suffix key has a handler function:

```python
def _handler_tai(session, root, suffix, kf):
    """Handle たい suffix - want to."""
    return find_word_with_conj_type(session, root, CONJ_CONTINUATIVE)
```

### Compound Words

```python
@dataclass
class CompoundWord:
    primary: WordMatch     # Main word
    words: List[WordMatch] # All parts
    text: str              # Full text
    kana: str              # Combined reading
    score_mod: int         # Score adjustment
```

---

## Synergies and Segfilters

### Synergy System

Synergies give score bonuses to valid grammatical patterns:

```python
def def_generic_synergy(
    name: str,
    filter_left: Callable,   # Filter for left word
    filter_right: Callable,  # Filter for right word
    description: str,
    score: Union[int, Callable],
    connector: str = " ",
):
    """Define a synergy between adjacent segments."""
```

**Key Synergies:**

| Name | Left Filter | Right Filter | Score |
|------|-------------|--------------|-------|
| noun-particle | is_noun | in NOUN_PARTICLES | 10 + 4×len |
| noun-da | is_noun | seq=2089020 (だ) | 10 |
| na-adj | adj-na POS | な/に | 15 |
| no-adj | adj-no POS | の | 15 |
| to-adv | adv-to POS | と | 10-50 |

### Segfilter System

Segfilters enforce hard constraints:

```python
def def_segfilter_must_follow(
    name: str,
    filter_left: Callable,   # What must precede
    filter_right: Callable,  # What requires the precedence
    allow_first: bool = False,  # Allow at sentence start?
):
    """Define constraint: filter_right must follow filter_left."""
```

**Key Segfilters:**

- Auxiliary verbs must follow continuative form
- ん/んだ can't follow simple particles
- だ + する blocked (だし false match prevention)

---

## Counter Word Recognition

### Counter Cache

```python
_counter_cache = {
    '匹': [{'counter_text': '匹', 'counter_kana': 'ひき', ...}],
    '冊': [{'counter_text': '冊', 'counter_kana': 'さつ', ...}],
    # ...
}
```

### Phonetic Rules

Counter words undergo sound changes:

```python
def counter_join(digit, number_kana, counter_kana, digit_opts=None):
    """Apply phonetic rules when joining number + counter."""
```

- **Rendaku** (sequential voicing): ひき → びき after certain numbers
- **Gemination**: さん → さっ before certain sounds
- **Handakuten**: ひき → ぴき after 1, 6, 8, 10

### Special Counters

| Seq | Counter | Special Handling |
|-----|---------|------------------|
| 2083110 | 日 (ka) | Days 1-10, 14, 20, 24, 30 use kun readings |
| 2083100 | 日 (nichi) | Other day numbers |
| 2149890 | 人 (nin) | 1人=ひとり, 2人=ふたり |
| 1255430 | 月 (gatsu) | Months use がつ not つき |

---

## Testing Strategy

### Test Files

| File | Purpose |
|------|---------|
| `test_characters.py` | Character utilities |
| `test_lookup.py` | Dictionary lookup |
| `test_segment.py` | Segmentation algorithm |
| `test_output.py` | Output formatting |
| `test_cli.py` | CLI interface |
| `test_ichiran_comparison.py` | Comparison with ichiran |
| `test_*_properties.py` | Property-based tests (hypothesis) |

### Fixtures

```python
@pytest.fixture(scope="module")
def db_session():
    """Module-scoped database session."""

@pytest.fixture(scope="function")
def fresh_session():
    """Function-scoped session for tests that modify state."""
```

### Running Tests

```bash
# Run all tests
pytest

# With coverage
pytest --cov=himotoki --cov-report=term-missing

# Run specific test file
pytest tests/test_segment.py

# Run with verbose output
pytest -v

# Run property-based tests with more examples
pytest --hypothesis-show-statistics
```

---

## Development Commands

### Installation

```bash
# Install from source with dev dependencies
pip install -e ".[dev]"

# Or using uv
uv pip install -e ".[dev]"
```

### Database Setup

```bash
# Interactive setup (downloads JMdict, builds DB)
himotoki setup

# Non-interactive
himotoki setup --yes

# Force rebuild
himotoki setup --force
```

### CLI Usage

```bash
# Default output (dictionary info)
himotoki "学校で勉強しています"

# Romanization only
himotoki -r "学校で勉強しています"

# Full output (romanization + dictionary)
himotoki -f "学校で勉強しています"

# Kana with spaces
himotoki -k "学校で勉強しています"

# JSON output
himotoki -j "学校で勉強しています"
```

### Development Tasks

```bash
# Run tests
pytest

# Type checking
mypy himotoki

# Linting
ruff check .

# Formatting
black .
isort .

# Compare with ichiran
python scripts/compare.py "test sentence"

# Generate HTML report
python scripts/report.py
```

---

## Code Conventions

### Style

- **Black** formatter with 100 character line length
- **isort** for import sorting (black profile)
- Type hints throughout (mypy compatible)

### Naming

- snake_case for functions and variables
- PascalCase for classes
- UPPER_CASE for constants
- Prefix private functions with underscore

### Documentation

- Docstrings for all public functions (Google style)
- Module-level docstrings explaining purpose
- Comments for complex logic (especially ported from ichiran)

### Import Order

```python
# Standard library
from typing import Optional, List, Dict

# Third-party
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

# Local
from himotoki.db.models import Entry, KanjiText
from himotoki.constants import SEQ_SURU, CONJ_TE
```

### Common Patterns

**Session Management:**
```python
# For single operations
def my_function(session: Optional[Session] = None):
    created_session = session is None
    if created_session:
        session = get_session()
    try:
        # ... work
    finally:
        if created_session:
            session.close()

# Using context manager
with session_scope() as session:
    # ... work (auto-commit/rollback)
```

**Caching:**
```python
# Module-level cache with lazy init
_MY_CACHE: Optional[Dict] = None

def ensure_cache(session):
    global _MY_CACHE
    if _MY_CACHE is None:
        _MY_CACHE = build_cache(session)
    return _MY_CACHE
```

---

## Key Constants and SEQ Numbers

### Particles

| Constant | SEQ | Text |
|----------|-----|------|
| SEQ_WA | 2028920 | は |
| SEQ_GA | 2028930 | が |
| SEQ_NI | 2028990 | に |
| SEQ_DE | 2028980 | で |
| SEQ_WO | 2029010 | を |
| SEQ_NO | 1469800 | の |
| SEQ_TO | 1008490 | と |
| SEQ_MO | 2028940 | も |
| SEQ_KA | 2028970 | か |

### Common Verbs

| Constant | SEQ | Text |
|----------|-----|------|
| SEQ_SURU | 1157170 | する |
| SEQ_IRU | 1577980 | いる |
| SEQ_KURU | 1547720 | 来る |
| SEQ_ARU | 1296400 | ある |
| SEQ_NARU | 1375610 | なる |

### Skip/Block Lists

```python
# Words that aren't really standalone words
SKIP_WORDS = {2458040, 2822120, 2013800, ...}

# Final particles (only valid at sentence end)
FINAL_PRT = {2017770, 2425930, 2130430, ...}

# Blocked from specific suffix handlers
BLOCKED_NAI_SEQS = {SEQ_IRU, SEQ_KURU}
BLOCKED_NAI_X_SEQS = {SEQ_SURU, SEQ_TOMU}
```

---

## Common Patterns

### Adding a New Suffix Handler

1. Add to suffix cache initialization in `suffixes.py`:
```python
_load_conjs(session, 'myhandler', MY_SEQ)
```

2. Create handler function:
```python
def _handler_myhandler(session, root, suffix, kf):
    """Handle my suffix."""
    return find_word_with_conj_type(session, root, CONJ_TYPE)
```

3. Register in SUFFIX_HANDLERS:
```python
SUFFIX_HANDLERS['myhandler'] = _handler_myhandler
```

### Adding a New Synergy

```python
# In synergies.py, during module initialization
def_generic_synergy(
    name="my-synergy",
    filter_left=filter_is_pos('adj-i'),
    filter_right=filter_in_seq_set(MY_SEQ),
    description="i-adjective + something",
    score=15,
)
```

### Adding a New Segfilter

```python
def_segfilter_must_follow(
    name="my-segfilter",
    filter_left=my_left_condition,
    filter_right=my_right_condition,
    allow_first=False,
)
```

### Adding Database Entries (Errata)

In `loading/errata.py`:
```python
def add_errata(session):
    # Add synthetic entry
    entry = Entry(seq=900001, root_p=True, n_kanji=0, n_kana=1)
    session.add(entry)
    # Add readings, senses, etc.
```

---

## Troubleshooting Guide

### Common Issues

**1. Database Not Found**
```
Error: Database not found at /path/to/himotoki.db
```
Solution: Run `himotoki setup` to download and build the database.

**2. Slow First Analysis**
The first analysis is slow due to cache building. Call `himotoki.warm_up()` at application startup.

**3. Segmentation Mismatch with Ichiran**
Check these in order:
1. Sticky positions (find_sticky_positions)
2. Candidate words (find_substring_words)
3. Individual scores (calc_score)
4. Synergy/penalty application
5. Path selection (TopArray)

**4. Missing Conjugation**
Check if:
- Entry has `conjugate_p = True`
- Conjugation CSV files are loaded
- ConjData is being retrieved correctly

**5. Counter Not Recognized**
Verify:
- Counter cache is initialized
- Counter SEQ exists in database
- Number format is valid (kanji or arabic)

### Debugging Tips

```python
# Enable SQL echo
from himotoki.db.connection import get_engine
engine = get_engine(echo=True)

# Print scoring details
score, info = calc_score(session, word, final=True)
print(f"Score: {score}, Info: {info}")

# Check suffix cache
from himotoki.suffixes import _suffix_cache
print(_suffix_cache.keys())

# Trace conjugation chain
conj_data = get_conj_data(session, seq)
for cd in conj_data:
    print(f"{cd.seq} <- {cd.from_seq} via {cd.via}: {cd.prop}")
```

---

## Quick Reference

### Essential Imports

```python
# Public API
import himotoki
results = himotoki.analyze("日本語")

# Internal (for development)
from himotoki.db.connection import get_session
from himotoki.segment import segment_text
from himotoki.lookup import calc_score, find_word_full
from himotoki.output import dict_segment, WordInfo
from himotoki.constants import SEQ_SURU, CONJ_TE
```

### Key Entry Points

| Purpose | Function | Module |
|---------|----------|--------|
| Analyze text | `analyze()` | `__init__` |
| Segment only | `segment_text()` | `segment` |
| Get WordInfo | `dict_segment()` | `output` |
| Database lookup | `find_word_full()` | `lookup` |
| Score word | `calc_score()` | `lookup` |
| Warm caches | `warm_up()` | `__init__` |

### Files to Modify By Task

| Task | Primary Files |
|------|---------------|
| Change scoring | lookup.py |
| Add grammar pattern | synergies.py |
| Add suffix | suffixes.py |
| Fix segmentation | segment.py |
| Change output format | output.py, models.py |
| Add database data | loading/errata.py |
| Add CLI option | cli.py |

---

*Last updated: Generated by AI agent analysis*
