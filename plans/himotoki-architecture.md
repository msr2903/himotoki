# Himotoki: Ichiran Python Port - Architecture Plan

## Project Overview

Himotoki is a Python port of the ichiran Japanese Morphological Analyzer, focusing on sentence segmentation and dictionary functionality. The goal is to create a functionally identical implementation using SQLite instead of PostgreSQL.

## Ichiran Architecture Analysis

### Core Components

1. **Database Schema** (PostgreSQL → SQLite)
   - `entry`: Core dictionary entries with XML content
   - `kanji_text`: Kanji readings with commonness scores
   - `kana_text`: Kana readings with commonness scores
   - `sense`: Meaning groups within entries
   - `gloss`: English translations
   - `sense_prop`: Part-of-speech and other properties
   - `conjugation`: Links between base and conjugated forms
   - `conj_prop`: Conjugation properties (type, polarity, formality)
   - `conj_source_reading`: Source text for conjugations
   - `restricted_readings`: Kanji-kana reading restrictions

2. **Data Loading Pipeline**
   - **JMDict XML Parsing**: Parses JMdict_e XML file
   - **Conjugation Rules**: Loads CSV files (kwpos.csv, conj.csv, conjo.csv)
   - **Conjugation Generation**: Creates conjugated forms using rules
   - **Secondary Conjugations**: Generates additional forms (causative-passive, etc.)
   - **Best Reading Calculation**: Determines optimal kanji-kana pairings

3. **Character Processing** (characters.lisp)
   - Character classification (hiragana, katakana, kanji)
   - Mora counting and text normalization
   - Rendaku/unrendaku handling
   - Kanji regex generation

4. **Word Lookup & Scoring** (dict.lisp)
   - `find_word`: Basic word lookup by text
   - `calc_score`: Complex scoring algorithm considering:
     - Word length and type (kanji/kana)
     - Commonness scores
     - Conjugation status
     - Part-of-speech
     - Primary vs secondary readings

5. **Segmentation Algorithm** (dict.lisp)
   - **Substring Finding**: `join_substring_words` finds all possible word starts
   - **Dynamic Programming**: `find_best_path` uses Viterbi-like algorithm
   - **Scoring**: Each segment gets score, penalties applied for kanji breaks
   - **Synergies**: Bonus scores for common word combinations (noun+particle)
   - **Penalties**: Score reductions for unlikely combinations
   - **Segfilters**: Hard constraints (must-follow rules)

6. **Split System** (dict-split.lisp)
   - **Split Definitions**: `def-simple-split` macros define compound words
   - **Segment Splits**: Alternative segmentations for expressions
   - **Kana Hints**: Special romanization hints for particles

7. **Grammar & Suffix System** (dict-grammar.lisp)
   - **Suffix Cache**: Precomputed suffix patterns
   - **Compound Words**: Automatic creation of compound forms
   - **Conjugation Detection**: Recognizes conjugated forms

### Key Algorithms

#### Segmentation (find_best_path)
- Uses dynamic programming with segment lists
- Each position gets multiple possible segmentations
- Scores consider word quality, length, combinations
- Kanji break penalties prevent unnatural splits
- Synergies reward common patterns

#### Scoring (calc_score)
- Base score from word properties
- Length multipliers (strong/weak classes)
- Commonness bonuses
- Conjugation penalties/bonuses
- Split bonuses for compound words

#### Conjugation Handling
- Rules-based generation from CSV data
- Multiple conjugation types (negative, formal, etc.)
- Secondary conjugations (causative-passive combinations)
- Source reading tracking for deconjugation

## Himotoki Implementation Plan

### Phase 1: Database Schema & Core Data Structures
- Create SQLite schema matching PostgreSQL
- Implement SQLAlchemy models
- Database connection manager with caching

### Phase 2: JMDict Loading Pipeline
- XML parsing with lxml
- Entry loading with kanji/kana/sense processing
- CSV conjugation rule loading
- Conjugation generation algorithms
- Best reading calculation

### Phase 3: Character Utilities
- Port character classification functions
- Mora counting and normalization
- Rendaku/unrendaku utilities
- Kanji regex generation

### Phase 4: Word Lookup & Scoring
- Implement find_word functions
- Port calc_score with all scoring logic
- Conjugation data retrieval
- Compound word handling

### Phase 5: Segmentation Algorithm
- Substring word finding
- Dynamic programming path finding
- Synergy and penalty systems
- Segfilter constraints

### Phase 6: Split System
- Split definition system
- Segment split handling
- Kana hints system

### Phase 7: Grammar & Suffix System
- Suffix cache initialization
- Suffix matching and compound creation
- All suffix definitions

### Phase 8: Output & CLI
- Word info data structures
- JSON output formatting
- CLI interface matching ichiran-cli

### Phase 9: Testing & Validation
- Test suite porting
- Output comparison with ichiran
- Performance optimization

## Key Technical Decisions

1. **Database**: SQLite with SQLAlchemy ORM
2. **XML Parsing**: lxml for JMdict processing
3. **Character Handling**: Unicode regex patterns
4. **Algorithm Fidelity**: Exact port of ichiran logic
5. **Output Compatibility**: Match ichiran JSON/CLI format
6. **Performance**: Prioritize accuracy over optimization initially

## Data Sources Required

- JMdict_e XML file
- JMdictDB CSV files (kwpos.csv, conj.csv, conjo.csv)
- ichiran pgdump for reference/validation

## Success Criteria

- Identical segmentation results to ichiran
- Same JSON output format
- CLI compatibility
- Full dictionary lookup functionality
- Proper conjugation handling