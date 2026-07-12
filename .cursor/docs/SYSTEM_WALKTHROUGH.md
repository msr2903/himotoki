# Himotoki System Walkthrough

Agent- and developer-facing map of the Japanese morphological analyzer. Prefer this over stale paths in `docs/AGENTS.md` (e.g. missing `himotoki/models.py`, `scripts/check_segments.py`).

Deeper background: `docs/ARCHITECTURE.md`, `docs/OPTIMIZATION_REPORT.md`.

---

## 1. What Himotoki is

Himotoki (紐解き) is a Python port of [ichiran](https://github.com/tshatrov/ichiran). It segments Japanese text into words with readings, glosses, and conjugation trees using:

1. Dictionary candidate generation (JMdict surfaces + conjugations)
2. Heuristic scoring (`calc_score`, ichiran-compatible)
3. Viterbi-style DP for the best path (`find_best_path`)
4. Grammar overlays (suffixes, synergies/segfilters, counters, splits)

Runtime depends on a local SQLite DB (`~/.himotoki/himotoki.db` or `data/himotoki.db`, ~**1.8 GB** after index slim / covering indexes; was ~2.94 GB). Persisted trie: `himotoki.trie` (~25 MB) beside the DB.

---

## 2. Package map (where to change what)

| Concern | Primary location | Notes |
|---------|------------------|-------|
| Public API | `himotoki/__init__.py` | `analyze()`, `warm_up()`, `shutdown()` |
| CLI | `himotoki/cli.py` | `-r/-k/-j/-f`, `setup` |
| Segmentation DP | `himotoki/segment.py` | sticky positions, substring join, Viterbi |
| Types | `himotoki/types.py` | `WordMatch`, `Segment`, `SegmentList`, `CompoundWord`, `ConjData` |
| Scoring | `himotoki/scoring/` | `calc_score`, caches, archaic/UK/POS |
| Dictionary lookup | `himotoki/lookup/` | `find_word*`, `get_conj_data` |
| Grammar | `himotoki/grammar/` | synergies, suffixes, counters, splits |
| Output / WordInfo | `himotoki/output/` | glosses, conjugation display, JSON/text |
| Characters | `himotoki/characters.py` | kana/kanji, mora, romanize |
| Constants | `himotoki/constants.py` | SEQ IDs, conj types (JMdict-version sensitive) |
| Trie filter | `himotoki/trie.py` | marisa-trie of surface forms |
| DB | `himotoki/db/` | models, connection, pragmas |
| Offline load | `himotoki/loading/` | JMdict XML, conjugations, errata |
| Setup | `himotoki/setup.py` | first-run download + DB build |

**Compatibility shims:** `himotoki/lookup.py`, `output.py`, `synergies.py`, `suffixes.py`, `counters.py`, `splits.py` re-export from the new packages so existing imports keep working.

### Task → file cheat sheet

| Task | Touch |
|------|--------|
| Wrong score / ranking | `scoring/calc_score.py`, constants |
| Missing grammar pattern | `grammar/synergy_rules.py` or segfilters |
| Suffix compound (〜ている) | `grammar/suffix_handlers.py` |
| Counter (三匹) | `grammar/counters.py` |
| Segmentation bug | `segment.py` then scoring |
| Gloss / JSON display | `output/` |
| DB schema / indexes | `db/models.py` + rebuild |
| Synthetic entries | `loading/errata.py` |

---

## 3. End-to-end data flow

```
Input text
  → analyze() / dict_segment()
  → segment_text()
      → find_sticky_positions()          # forbidden boundaries
      → find_substring_words()           # trie filter + batched IN queries
      → find_word_suffix() / counters    # compounds not in DB as wholes
      → join_substring_words()
          → preload_scoring_caches()
          → gen_score() → calc_score()
          → cull_segments()
      → find_best_path()                 # DP + synergies / segfilters
  → fill_segment_path()                  # WordInfo + gaps
  → populate_meanings()                  # gloss / POS (display)
```

Key entry points:

- `himotoki.analyze(text)` → `segment_text` + `fill_segment_path`
- `output.dict_segment` / `segment_to_json` for CLI formats
- `warm_up()` builds archaic, suffix, counter, and word-trie caches

---

## 4. Database

### Location

1. `HIMOTOKI_DB_PATH` / `HIMOTOKI_DB`
2. `~/.himotoki/himotoki.db` if present
3. `data/himotoki.db` (dev)

### Tables

| Table | Role | Segmentation-critical? |
|-------|------|------------------------|
| `entry` | seq, root_p, n_kanji/n_kana, primary_nokanji | Yes (metadata; not XML) |
| `kanji_text` / `kana_text` | surface forms + common/ord/best_* | Yes |
| `sense` / `sense_prop` | POS, misc (uk, arch), … | Yes for scoring tags |
| `gloss` | English definitions | Display only |
| `conjugation` / `conj_prop` / `conj_source_reading` | conj chains | Yes |
| `restricted_reading` | kana↔kanji restrictions | Loaded at build; rarely runtime |

### Hot queries

- Batched `SELECT … FROM kana_text/kanji_text WHERE text IN (…)`
- Scoring preload: Entry, UK, POS by seq
- `get_conj_data`: conjugations + source readings + props (batched)
- Output: Sense/Gloss for meanings

Pragmas: WAL, 64MB cache, 256MB mmap (`db/connection.py`).

### Build pipeline

1. Parse `JMdict_e.xml` → entries/readings/senses (`loading/jmdict.py`)
2. Generate conjugations from CSV rules (`loading/conjugations.py`)
3. Apply errata (`loading/errata.py`)
4. `ANALYZE` + `VACUUM`

---

## 5. Scoring & equivalence

“Query quality” means **identical segmentation winners and scores**, not merely valid Japanese.

Preserve:

- Candidate `(text, seq, ord, common)` sets
- `calc_score` bonuses/penalties (length coeffs, archaic, weak/skip conj, splits)
- DP: `GAP_PENALTY`, `SCORE_CUTOFF`, synergies/segfilters
- Suffix and counter decomposition

Safe optimizations: indexes, batched SQL returning the same rows, caches, trie filter (exact membership), dropping unused `entry` XML storage.

Unsafe: dropping `common`/POS/conj props, changing score constants, approximate matching.

---

## 6. Caches & performance

| Cache | Module | Notes |
|-------|--------|-------|
| Archaic seq set | `scoring/caches.py` | ~165ms cold |
| Suffix cache | `grammar/suffixes.py` | ~145ms cold |
| Counter cache | `grammar/counters.py` | ~10ms |
| Word trie (+ disk) | `trie.py` | skip full-table rebuild when file fresh |
| LRU Entry/POS/UK/conj/word | `scoring/caches.py` | |
| Meanings | `output/` | display |

Hot path already uses raw SQL + trie before DB. Remaining cost is often conjugation metadata and DP over candidates.

---

## 7. Tests & commands

```bash
source .venv/bin/activate
pip install -e .
pytest tests/ -x --tb=short
python scripts/benchmark.py
himotoki setup --yes   # rebuild DB after schema changes
```

LLM eval tooling lives under `scripts/llm_eval.py` (see root `AGENTS.md`).

---

## 8. Layers (dependency direction)

```
cli / __init__
  → output
  → segment
      → lookup + scoring + grammar + trie + characters
      → db
loading / setup → db (offline only)
```

Avoid new cycles; prefer lazy imports where historical cycles existed (`lookup` ↔ `splits`).
