"""
Dictionary loading module for Himotoki.

Handles loading JMdict, KANJIDIC, and conjugation data
into the SQLite database.

Mirrors dict-load.lisp from the original Ichiran.
"""

import os
import csv
import gzip
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple, Set
from pathlib import Path
from collections import defaultdict
import time

from himotoki.settings import (
    DB_PATH, DATA_DIR, JMDICT_PATH, KANJIDIC_PATH,
    CONJUGATION_CSV_PATH
)
from himotoki.conn import get_connection, execute, insert, query, query_single


# ============================================================================
# Database Schema
# ============================================================================

SCHEMA_SQL = """
-- Entry table (main JMdict entries)
CREATE TABLE IF NOT EXISTS entry (
    seq INTEGER PRIMARY KEY,
    content TEXT,
    root_p INTEGER DEFAULT 0,
    n_kanji INTEGER DEFAULT 0,
    n_kana INTEGER DEFAULT 0,
    primary_nokanji INTEGER DEFAULT 0
);

-- Kanji text representations
CREATE TABLE IF NOT EXISTS kanji_text (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    ord INTEGER DEFAULT 0,
    common INTEGER,
    common_tags TEXT,
    conjugate_p INTEGER DEFAULT 1,
    nokanji INTEGER DEFAULT 0,
    best_kana TEXT,
    FOREIGN KEY (seq) REFERENCES entry(seq)
);

-- Kana text representations  
CREATE TABLE IF NOT EXISTS kana_text (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    ord INTEGER DEFAULT 0,
    common INTEGER,
    common_tags TEXT,
    conjugate_p INTEGER DEFAULT 1,
    nokanji INTEGER DEFAULT 0,
    best_kanji TEXT,
    FOREIGN KEY (seq) REFERENCES entry(seq)
);

-- Sense (meaning group)
CREATE TABLE IF NOT EXISTS sense (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seq INTEGER NOT NULL,
    ord INTEGER DEFAULT 0,
    FOREIGN KEY (seq) REFERENCES entry(seq)
);

-- Gloss (English definition)
CREATE TABLE IF NOT EXISTS gloss (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sense_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    ord INTEGER DEFAULT 0,
    FOREIGN KEY (sense_id) REFERENCES sense(id)
);

-- Sense properties (POS, misc, field, etc.)
CREATE TABLE IF NOT EXISTS sense_prop (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT NOT NULL,
    sense_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    ord INTEGER DEFAULT 0,
    seq INTEGER NOT NULL,
    FOREIGN KEY (sense_id) REFERENCES sense(id),
    FOREIGN KEY (seq) REFERENCES entry(seq)
);

-- Conjugation links
CREATE TABLE IF NOT EXISTS conjugation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seq INTEGER NOT NULL,
    from_seq INTEGER NOT NULL,
    via INTEGER,
    FOREIGN KEY (seq) REFERENCES entry(seq),
    FOREIGN KEY (from_seq) REFERENCES entry(seq)
);

-- Conjugation properties
CREATE TABLE IF NOT EXISTS conj_prop (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conj_id INTEGER NOT NULL,
    conj_type INTEGER NOT NULL,
    pos TEXT NOT NULL,
    neg INTEGER,
    fml INTEGER,
    FOREIGN KEY (conj_id) REFERENCES conjugation(id)
);

-- Conjugation source map
CREATE TABLE IF NOT EXISTS conj_source_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conj_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    reading TEXT NOT NULL,
    FOREIGN KEY (conj_id) REFERENCES conjugation(id)
);

-- Kanji information (from KANJIDIC)
CREATE TABLE IF NOT EXISTS kanji (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character TEXT UNIQUE NOT NULL,
    grade INTEGER,
    strokes INTEGER,
    freq INTEGER,
    jlpt INTEGER
);

-- Kanji readings
CREATE TABLE IF NOT EXISTS kanji_reading (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kanji_id INTEGER NOT NULL,
    reading TEXT NOT NULL,
    type TEXT NOT NULL,
    common INTEGER DEFAULT 1,
    FOREIGN KEY (kanji_id) REFERENCES kanji(id)
);

-- Kanji meanings
CREATE TABLE IF NOT EXISTS kanji_meaning (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kanji_id INTEGER NOT NULL,
    meaning TEXT NOT NULL,
    ord INTEGER DEFAULT 0,
    FOREIGN KEY (kanji_id) REFERENCES kanji(id)
);

-- Indexes for fast lookup
CREATE INDEX IF NOT EXISTS idx_kanji_text_text ON kanji_text(text);
CREATE INDEX IF NOT EXISTS idx_kanji_text_seq ON kanji_text(seq);
CREATE INDEX IF NOT EXISTS idx_kana_text_text ON kana_text(text);
CREATE INDEX IF NOT EXISTS idx_kana_text_seq ON kana_text(seq);
CREATE INDEX IF NOT EXISTS idx_sense_seq ON sense(seq);
CREATE INDEX IF NOT EXISTS idx_gloss_sense ON gloss(sense_id);
CREATE INDEX IF NOT EXISTS idx_sense_prop_seq ON sense_prop(seq);
CREATE INDEX IF NOT EXISTS idx_sense_prop_sense ON sense_prop(sense_id);
CREATE INDEX IF NOT EXISTS idx_conjugation_seq ON conjugation(seq);
CREATE INDEX IF NOT EXISTS idx_conjugation_from ON conjugation(from_seq);
CREATE INDEX IF NOT EXISTS idx_conj_prop_conj ON conj_prop(conj_id);
CREATE INDEX IF NOT EXISTS idx_kanji_char ON kanji(character);
CREATE INDEX IF NOT EXISTS idx_kanji_reading_kanji ON kanji_reading(kanji_id);
"""

# Starting seq for conjugated forms (Ichiran uses 10000000+)
CONJ_SEQ_START = 10000000

# Secondary conjugation types (from Ichiran)
# 5: Potential, 6: Passive, 7: Causative, 8: Causative-Passive, 53: Causative-su
SECONDARY_CONJ_TYPES_FROM = {5, 6, 7, 8, 53}

def create_schema():
    """Create the database schema."""
    conn = get_connection()
    conn.executescript(SCHEMA_SQL)
    conn.commit()


# ============================================================================
# JMdict Loading
# ============================================================================

def load_jmdict(path: Optional[str] = None, progress_callback=None):
    """
    Load JMdict XML into the database.
    
    Args:
        path: Path to JMdict XML file (gzipped or plain).
        progress_callback: Optional callback(current, total) for progress.
    """
    path = str(path or JMDICT_PATH)
    
    # Also check for .gz version
    if not os.path.exists(path) and os.path.exists(path + '.gz'):
        path = path + '.gz'
    
    if not os.path.exists(path):
        raise FileNotFoundError(f"JMdict not found at: {path}")
    
    # Create schema if needed
    create_schema()
    
    # Open file (handle gzip by extension or magic bytes)
    if path.endswith('.gz') or is_gzip_file(path):
        import gzip
        f = gzip.open(path, 'rb')
    else:
        f = open(path, 'rb')
    
    try:
        conn = get_connection()
        
        # Parse XML
        entries_loaded = 0
        
        # Use iterparse for memory efficiency
        context = ET.iterparse(f, events=('end',))
        
        for event, elem in context:
            if elem.tag == 'entry':
                _load_jmdict_entry(conn, elem)
                entries_loaded += 1
                
                if progress_callback and entries_loaded % 1000 == 0:
                    progress_callback(entries_loaded, None)
                
                # Clear element to save memory
                elem.clear()
        
        conn.commit()
        
        if progress_callback:
            progress_callback(entries_loaded, entries_loaded)
        
        return entries_loaded
    finally:
        f.close()


def _load_jmdict_entry(conn, entry_elem):
    """Load a single JMdict entry."""
    seq = int(entry_elem.findtext('ent_seq', '0'))
    
    if not seq:
        return
    
    # Count kanji and kana elements
    k_eles = entry_elem.findall('k_ele')
    r_eles = entry_elem.findall('r_ele')
    
    n_kanji = len(k_eles)
    n_kana = len(r_eles)
    
    # Check for primary nokanji
    primary_nokanji = 0
    if not k_eles:
        primary_nokanji = 1
    
    # Check if it's a root form (has verb/adj POS but no re_nokanji)
    root_p = 0
    for sense in entry_elem.findall('sense'):
        for pos in sense.findall('pos'):
            pos_text = pos.text or ''
            if 'verb' in pos_text.lower() or 'adj' in pos_text.lower():
                root_p = 1
                break
    
    # Insert entry
    conn.execute(
        """INSERT OR REPLACE INTO entry 
           (seq, content, root_p, n_kanji, n_kana, primary_nokanji)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (seq, ET.tostring(entry_elem, encoding='unicode'), root_p, n_kanji, n_kana, primary_nokanji)
    )
    
    # Insert kanji elements
    for ord_idx, k_ele in enumerate(k_eles):
        keb = k_ele.findtext('keb', '')
        
        # Get common tags
        common = None
        common_tags = []
        for ke_pri in k_ele.findall('ke_pri'):
            pri_text = ke_pri.text or ''
            common_tags.append(pri_text)
            if 'ichi' in pri_text or 'news' in pri_text or 'spec' in pri_text:
                if common is None or 'ichi1' in pri_text:
                    common = 1 if 'ichi1' in pri_text else (2 if 'ichi2' in pri_text else 5)
        
        if keb:
            conn.execute(
                """INSERT INTO kanji_text 
                   (seq, text, ord, common, common_tags, conjugate_p, nokanji)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (seq, keb, ord_idx, common, ','.join(common_tags), 1, 0)
            )
    
    # Insert kana elements
    for ord_idx, r_ele in enumerate(r_eles):
        reb = r_ele.findtext('reb', '')
        
        # Check for nokanji
        nokanji = 1 if r_ele.find('re_nokanji') is not None else 0
        
        # Get common tags
        common = None
        common_tags = []
        for re_pri in r_ele.findall('re_pri'):
            pri_text = re_pri.text or ''
            common_tags.append(pri_text)
            if 'ichi' in pri_text or 'news' in pri_text or 'spec' in pri_text:
                if common is None or 'ichi1' in pri_text:
                    common = 1 if 'ichi1' in pri_text else (2 if 'ichi2' in pri_text else 5)
        
        if reb:
            conn.execute(
                """INSERT INTO kana_text 
                   (seq, text, ord, common, common_tags, conjugate_p, nokanji)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (seq, reb, ord_idx, common, ','.join(common_tags), 1, nokanji)
            )
    
    # Insert senses
    for ord_idx, sense_elem in enumerate(entry_elem.findall('sense')):
        cursor = conn.execute(
            "INSERT INTO sense (seq, ord) VALUES (?, ?)",
            (seq, ord_idx)
        )
        sense_id = cursor.lastrowid
        
        # Insert glosses
        for gloss_idx, gloss_elem in enumerate(sense_elem.findall('gloss')):
            lang = gloss_elem.get('{http://www.w3.org/XML/1998/namespace}lang', 'eng')
            if lang == 'eng':  # Only English for now
                conn.execute(
                    "INSERT INTO gloss (sense_id, text, ord) VALUES (?, ?, ?)",
                    (sense_id, gloss_elem.text or '', gloss_idx)
                )
        
        # Insert POS
        for pos_idx, pos_elem in enumerate(sense_elem.findall('pos')):
            conn.execute(
                """INSERT INTO sense_prop (tag, sense_id, text, ord, seq)
                   VALUES (?, ?, ?, ?, ?)""",
                ('pos', sense_id, pos_elem.text or '', pos_idx, seq)
            )
        
        # Insert misc
        for misc_idx, misc_elem in enumerate(sense_elem.findall('misc')):
            conn.execute(
                """INSERT INTO sense_prop (tag, sense_id, text, ord, seq)
                   VALUES (?, ?, ?, ?, ?)""",
                ('misc', sense_id, misc_elem.text or '', misc_idx, seq)
            )


# ============================================================================
# KANJIDIC Loading
# ============================================================================

def load_kanjidic(path: Optional[str] = None, progress_callback=None):
    """
    Load KANJIDIC2 XML into the database.
    
    Args:
        path: Path to KANJIDIC2 XML file (gzipped or plain).
        progress_callback: Optional callback(current, total) for progress.
    """
    path = str(path or KANJIDIC_PATH)
    
    # Also check for .gz version
    if not os.path.exists(path) and os.path.exists(path + '.gz'):
        path = path + '.gz'
    
    if not os.path.exists(path):
        raise FileNotFoundError(f"KANJIDIC not found at: {path}")
    
    # Create schema if needed
    create_schema()
    
    # Open file (handle gzip by extension or magic bytes)
    if path.endswith('.gz') or is_gzip_file(path):
        import gzip
        f = gzip.open(path, 'rb')
    else:
        f = open(path, 'rb')
    
    try:
        conn = get_connection()
        kanji_loaded = 0
        
        # Parse XML
        context = ET.iterparse(f, events=('end',))
        
        for event, elem in context:
            if elem.tag == 'character':
                _load_kanjidic_entry(conn, elem)
                kanji_loaded += 1
                
                if progress_callback and kanji_loaded % 500 == 0:
                    progress_callback(kanji_loaded, None)
                
                elem.clear()
        
        conn.commit()
        
        if progress_callback:
            progress_callback(kanji_loaded, kanji_loaded)
        
        return kanji_loaded
    finally:
        f.close()


def _load_kanjidic_entry(conn, char_elem):
    """Load a single KANJIDIC character."""
    literal = char_elem.findtext('literal', '')
    
    if not literal:
        return
    
    # Get misc info
    misc = char_elem.find('misc')
    grade = None
    strokes = None
    freq = None
    jlpt = None
    
    if misc is not None:
        grade_elem = misc.find('grade')
        if grade_elem is not None and grade_elem.text:
            grade = int(grade_elem.text)
        
        stroke_elem = misc.find('stroke_count')
        if stroke_elem is not None and stroke_elem.text:
            strokes = int(stroke_elem.text)
        
        freq_elem = misc.find('freq')
        if freq_elem is not None and freq_elem.text:
            freq = int(freq_elem.text)
        
        jlpt_elem = misc.find('jlpt')
        if jlpt_elem is not None and jlpt_elem.text:
            jlpt = int(jlpt_elem.text)
    
    # Insert kanji
    cursor = conn.execute(
        """INSERT OR REPLACE INTO kanji 
           (character, grade, strokes, freq, jlpt)
           VALUES (?, ?, ?, ?, ?)""",
        (literal, grade, strokes, freq, jlpt)
    )
    kanji_id = cursor.lastrowid
    
    # Get readings
    rmgroup = char_elem.find('reading_meaning')
    if rmgroup is not None:
        rmgroup = rmgroup.find('rmgroup')
    
    if rmgroup is not None:
        # On readings
        for reading in rmgroup.findall("reading[@r_type='ja_on']"):
            if reading.text:
                conn.execute(
                    """INSERT INTO kanji_reading (kanji_id, reading, type)
                       VALUES (?, ?, ?)""",
                    (kanji_id, reading.text, 'on')
                )
        
        # Kun readings
        for reading in rmgroup.findall("reading[@r_type='ja_kun']"):
            if reading.text:
                conn.execute(
                    """INSERT INTO kanji_reading (kanji_id, reading, type)
                       VALUES (?, ?, ?)""",
                    (kanji_id, reading.text, 'kun')
                )
        
        # Meanings
        for ord_idx, meaning in enumerate(rmgroup.findall('meaning')):
            lang = meaning.get('m_lang', 'en')
            if lang == 'en' and meaning.text:
                conn.execute(
                    """INSERT INTO kanji_meaning (kanji_id, meaning, ord)
                       VALUES (?, ?, ?)""",
                    (kanji_id, meaning.text, ord_idx)
                )


# ============================================================================
# Conjugation Helpers
# ============================================================================

def is_kana_only(text: str) -> bool:
    """Check if text is kana-only (no kanji)."""
    for char in text:
        code = ord(char)
        # CJK Unified Ideographs
        if 0x4E00 <= code <= 0x9FFF:
            return False
        # CJK Extension A
        if 0x3400 <= code <= 0x4DBF:
            return False
    return True


def _migrate_conj_lookup(conn, next_seq: int) -> int:
    """
    Migrate data from conj_lookup to main tables.
    Returns the next available seq number.
    """
    print(f"Migrating conjugations starting at seq {next_seq}...")

    # Get all conjugation entries
    cursor = conn.execute("""
        SELECT text, reading, seq, conj_type, pos, neg, fml, source_text, source_reading
        FROM conj_lookup
        ORDER BY text, reading, seq
    """)
    rows = cursor.fetchall()

    # Group by (text, reading)
    form_groups: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for row in rows:
        key = (row['text'], row['reading'])
        form_groups[key].append({
            'source_seq': row['seq'],
            'conj_type': row['conj_type'],
            'pos': row['pos'],
            'neg': row['neg'],
            'fml': row['fml'],
            'source_text': row['source_text'],
            'source_reading': row['source_reading'],
        })

    # Prepare batches
    entries_batch = []
    kana_batch = []
    kanji_batch = []
    conj_batch = []
    prop_batch = []

    # Cache intermediate roots
    intermediate_roots = {}

    for (text, reading), sources in form_groups.items():
        new_seq = next_seq
        next_seq += 1

        # Create entry
        entries_batch.append((new_seq, '', 0, 0, 1, 0))

        # Create text entries
        if is_kana_only(text):
            kana_batch.append((new_seq, text, 0, None, '', 0, 0))
        else:
            kana_batch.append((new_seq, reading, 0, None, '', 0, 0))
            kanji_batch.append((new_seq, text, 0, None, '', 0, 0, reading))

        seen_props = set()

        for src in sources:
            source_seq = src['source_seq']
            prop_key = (source_seq, src['conj_type'], src['pos'],
                       src['neg'], src['fml'])

            if prop_key in seen_props:
                continue
            seen_props.add(prop_key)

            # Determine root and via
            if source_seq >= CONJ_SEQ_START:
                if source_seq not in intermediate_roots:
                    row = conn.execute("SELECT from_seq FROM conjugation WHERE seq=?", (source_seq,)).fetchone()
                    intermediate_roots[source_seq] = row[0] if row else source_seq

                root_seq = intermediate_roots[source_seq]
                via_seq = source_seq
            else:
                root_seq = source_seq
                via_seq = None

            # Create conjugation link
            # Note: id is AUTOINCREMENT, so we don't specify it in batch
            # But we need id for conj_prop link.
            # We must execute ONE BY ONE or get IDs somehow.
            # SQLite doesn't support returning IDs from executemany easily.
            # So we will do single inserts for conjugation/prop.
            pass

    # Batch insert entries and text
    conn.executemany(
        "INSERT INTO entry (seq, content, root_p, n_kanji, n_kana, primary_nokanji) VALUES (?, ?, ?, ?, ?, ?)",
        entries_batch
    )
    conn.executemany(
        "INSERT INTO kana_text (seq, text, ord, common, common_tags, conjugate_p, nokanji) VALUES (?, ?, ?, ?, ?, ?, ?)",
        kana_batch
    )
    if kanji_batch:
        conn.executemany(
            "INSERT INTO kanji_text (seq, text, ord, common, common_tags, conjugate_p, nokanji, best_kana) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            kanji_batch
        )

    # Insert conjugation links one by one to get IDs
    # Re-iterate to preserve order
    for (text, reading), sources in form_groups.items():
        # Find the seq we assigned earlier
        # Since we iterated form_groups in same order, we could map it
        # But let's look it up by text/reading to be safe?
        # Actually we computed new_seq linearly.
        # Let's rebuild the map or just re-do the logic in a cleaner way.
        pass

    # To avoid double iteration, let's do it properly:
    # We assigned seqs sequentially starting from input next_seq.
    current_seq_idx = 0
    start_seq = next_seq - len(form_groups)

    for (text, reading), sources in form_groups.items():
        new_seq = start_seq + current_seq_idx
        current_seq_idx += 1

        seen_props = set()
        for src in sources:
            source_seq = src['source_seq']
            prop_key = (source_seq, src['conj_type'], src['pos'],
                       src['neg'], src['fml'])

            if prop_key in seen_props:
                continue
            seen_props.add(prop_key)

            if source_seq >= CONJ_SEQ_START:
                if source_seq not in intermediate_roots:
                    row = conn.execute("SELECT from_seq FROM conjugation WHERE seq=?", (source_seq,)).fetchone()
                    intermediate_roots[source_seq] = row[0] if row else source_seq
                root_seq = intermediate_roots[source_seq]
                via_seq = source_seq
            else:
                root_seq = source_seq
                via_seq = None

            cursor = conn.execute(
                "INSERT INTO conjugation (seq, from_seq, via) VALUES (?, ?, ?)",
                (new_seq, root_seq, via_seq)
            )
            conj_id = cursor.lastrowid

            conn.execute(
                "INSERT INTO conj_prop (conj_id, conj_type, pos, neg, fml) VALUES (?, ?, ?, ?, ?)",
                (conj_id, src['conj_type'], src['pos'], 1 if src['neg'] else 0, 1 if src['fml'] else 0)
            )

            # Also insert source map
            conn.execute(
                "INSERT INTO conj_source_map (conj_id, text, reading) VALUES (?, ?, ?)",
                (conj_id, src['source_text'], src['source_reading'])
            )

    return next_seq


# ============================================================================
# Conjugation Loading (Main)
# ============================================================================

def generate_conjugations(progress_callback=None):
    """
    Generate all conjugated forms from dictionary entries.
    
    For each verb and adjective entry, generates all possible
    conjugations and stores them in the database.
    Also handles secondary conjugations (recursive).
    """
    from himotoki.conjugations import is_conjugatable
    
    conn = get_connection()
    
    # Add index on conj_source_map.text for fast lookup
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_conj_source_text 
        ON conj_source_map(text)
    """)
    
    # Create temp lookup table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conj_lookup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            reading TEXT NOT NULL,
            seq INTEGER NOT NULL,
            conj_type INTEGER NOT NULL,
            pos TEXT NOT NULL,
            neg INTEGER,
            fml INTEGER,
            source_text TEXT NOT NULL,
            source_reading TEXT NOT NULL,
            FOREIGN KEY (seq) REFERENCES entry(seq)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conj_lookup_text ON conj_lookup(text)")
    
    # Clear existing conjugation data
    print("Clearing existing conjugation tables...")
    conn.execute("DELETE FROM conj_lookup")
    conn.execute("DELETE FROM conj_source_map")
    conn.execute("DELETE FROM conj_prop")
    conn.execute("DELETE FROM conjugation")
    conn.execute(f"DELETE FROM kana_text WHERE seq >= {CONJ_SEQ_START}")
    conn.execute(f"DELETE FROM kanji_text WHERE seq >= {CONJ_SEQ_START}")
    conn.execute(f"DELETE FROM entry WHERE seq >= {CONJ_SEQ_START}")

    # -------------------------------------------------------------------------
    # Level 1: Primary Conjugations (from root entries)
    # -------------------------------------------------------------------------
    print("Generating primary conjugations...")
    
    # Group entries by seq and collect all POS tags for that entry
    entries = query("""
        SELECT DISTINCT e.seq, sp.text as pos
        FROM entry e
        JOIN sense_prop sp ON sp.seq = e.seq
        WHERE sp.tag = 'pos' AND e.seq < ?
    """, (CONJ_SEQ_START,))
    
    pos_map = defaultdict(set)
    for row in entries:
        seq = row[0]
        pos = _normalize_pos(row[1])
        if pos and is_conjugatable(pos):
            pos_map[seq].add(pos)
    
    total_entries = len(pos_map)
    processed = 0
    
    for seq, pos_tags in pos_map.items():
        for pos in pos_tags:
            # Get forms
            kanji_forms = query("SELECT text FROM kanji_text WHERE seq = ? ORDER BY ord", (seq,))
            kana_forms = query("SELECT text FROM kana_text WHERE seq = ? ORDER BY ord", (seq,))
            
            # Generate for kanji
            for kf in kanji_forms:
                kanji_text = kf[0]
                kana_reading = kana_forms[0][0] if kana_forms else None
                _generate_entry_conjugations(conn, seq, kanji_text, kana_reading, pos)
            
            # Generate for kana
            for rf in kana_forms:
                kana_text = rf[0]
                _generate_entry_conjugations(conn, seq, kana_text, kana_text, pos)
        
        processed += 1
        if progress_callback and processed % 5000 == 0:
            progress_callback(processed, total_entries)
    
    # Migrate Level 1
    next_seq = _migrate_conj_lookup(conn, CONJ_SEQ_START)

    # -------------------------------------------------------------------------
    # Level 2: Secondary Conjugations (recursive)
    # -------------------------------------------------------------------------
    print("Generating secondary conjugations...")

    # Clear lookup for next pass
    conn.execute("DELETE FROM conj_lookup")

    # Find Level 1 entries that can be conjugated further
    # These are entries in the conjugation table whose conj_type is in SECONDARY_CONJ_TYPES_FROM
    cursor = conn.execute(f"""
        SELECT DISTINCT c.seq, kt.text, kt_kana.text, cp.conj_type
        FROM conjugation c
        JOIN conj_prop cp ON c.id = cp.conj_id
        LEFT JOIN kanji_text kt ON c.seq = kt.seq AND kt.ord = 0
        LEFT JOIN kana_text kt_kana ON c.seq = kt_kana.seq AND kt_kana.ord = 0
        WHERE cp.conj_type IN ({','.join(map(str, SECONDARY_CONJ_TYPES_FROM))})
          AND c.via IS NULL
    """)

    rows = cursor.fetchall()
    print(f"Found {len(rows)} entries for secondary conjugation")

    for row in rows:
        seq = row[0]
        text = row[1] or row[2]  # Prefer kanji, fallback to kana
        reading = row[2] or row[1]
        conj_type = row[3]

        # Determine POS for the conjugated form
        # Causative-su (53) -> v5s, others -> v1
        new_pos = 'v5s' if conj_type == 53 else 'v1'

        _generate_entry_conjugations(conn, seq, text, reading, new_pos)

    # Migrate Level 2
    next_seq = _migrate_conj_lookup(conn, next_seq)

    conn.commit()
    
    if progress_callback:
        progress_callback(total_entries, total_entries)
    
    return next_seq - CONJ_SEQ_START


def _normalize_pos(pos_text: str) -> Optional[str]:
    """Convert JMdict POS description to short tag."""
    pos_text = pos_text.lower() if pos_text else ''
    
    # Pass through valid short tags if already normalized
    if pos_text in {
        'v1', 'v1-s', 'v5k', 'v5k-s', 'v5g', 'v5s', 'v5t', 'v5n', 'v5b', 'v5m',
        'v5r', 'v5r-i', 'v5aru', 'v5u', 'v5u-s', 'vk', 'vs-i', 'vs-s', 'copula',
        'adj-i', 'adj-ix'
    }:
        return pos_text

    pos_text = pos_text.replace("'", "'").replace("'", "'").replace('"', "'")
    
    if 'ichidan' in pos_text:
        return 'v1-s' if 'kureru' in pos_text else 'v1'
    
    if 'iku' in pos_text and 'yuku' in pos_text and 'special' in pos_text:
        return 'v5k-s'
    
    if 'godan' in pos_text:
        if "'ku'" in pos_text or "ku ending" in pos_text:
            return 'v5k-s' if ('iku' in pos_text or 'special' in pos_text) else 'v5k'
        elif "'gu'" in pos_text or "gu ending" in pos_text: return 'v5g'
        elif "'su'" in pos_text or "su ending" in pos_text: return 'v5s'
        elif "'tsu'" in pos_text or "tsu ending" in pos_text: return 'v5t'
        elif "'nu'" in pos_text or "nu ending" in pos_text: return 'v5n'
        elif "'bu'" in pos_text or "bu ending" in pos_text: return 'v5b'
        elif "'mu'" in pos_text or "mu ending" in pos_text: return 'v5m'
        elif "'ru'" in pos_text or "ru ending" in pos_text:
            return 'v5r-i' if 'irregular' in pos_text else 'v5r'
        elif 'aru' in pos_text: return 'v5aru'
        elif "'u'" in pos_text or "u ending" in pos_text:
            return 'v5u-s' if 'special' in pos_text else 'v5u'
    
    if 'suru' in pos_text:
        if 'included' in pos_text or 'special' in pos_text: return 'vs-i'
        if '-suru' in pos_text: return 'vs-s'
        return 'vs-i'
    
    if 'kuru' in pos_text: return 'vk'
    if 'copula' in pos_text: return 'copula'
    if 'adjective' in pos_text:
        if '-i' in pos_text or 'keiyoushi' in pos_text:
            return 'adj-ix' if ('yoi' in pos_text or 'ii' in pos_text) else 'adj-i'
    
    return None


def _generate_entry_conjugations(conn, seq: int, text: str, reading: str, pos: str) -> int:
    """Generate all conjugations for a single dictionary entry."""
    from himotoki.conjugations import get_conjugation_rules, fix_iku_conjugation
    
    rules = get_conjugation_rules(pos)
    if not rules:
        return 0
    
    count = 0
    reading = reading or text
    
    for rule in rules:
        if (rule.conj_type == 1 and rule.neg == False and 
            rule.fml == False and rule.stem_chars == 0):
            continue
        
        conj_text = rule.apply(text, is_kana=(text == reading))
        conj_reading = rule.apply(reading, is_kana=True)
        
        if pos == 'v5k-s' and text.endswith('く'):
            conj_text = fix_iku_conjugation(text, conj_text, rule)
            conj_reading = fix_iku_conjugation(reading, conj_reading, rule)
        
        if conj_text == text and conj_reading == reading:
            continue
        
        conn.execute("""
            INSERT INTO conj_lookup 
            (text, reading, seq, conj_type, pos, neg, fml, source_text, source_reading)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            conj_reading, conj_reading, seq,
            rule.conj_type, pos,
            1 if rule.neg else (0 if rule.neg == False else None),
            1 if rule.fml else (0 if rule.fml == False else None),
            text, reading
        ))
        count += 1
        
        if text != reading:
            okurigana_len = 0
            for i in range(1, min(len(text), len(reading)) + 1):
                if text[-i] == reading[-i]:
                    okurigana_len = i
                else:
                    break
            
            kanji_stem = text[:-okurigana_len] if okurigana_len > 0 else (text[0] if text else '')
            
            if kanji_stem:
                reading_stem_len = len(reading) - okurigana_len
                new_okurigana = conj_reading[reading_stem_len:] if len(conj_reading) > reading_stem_len else conj_reading
                kanji_form = kanji_stem + new_okurigana
                
                if kanji_form != conj_reading and kanji_form != text:
                    conn.execute("""
                        INSERT INTO conj_lookup 
                        (text, reading, seq, conj_type, pos, neg, fml, source_text, source_reading)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        kanji_form, conj_reading, seq,
                        rule.conj_type, pos,
                        1 if rule.neg else (0 if rule.neg == False else None),
                        1 if rule.fml else (0 if rule.fml == False else None),
                        text, reading
                    ))
                    count += 1
    
    return count


def load_conjugations(path: Optional[str] = None):
    """Legacy wrapper."""
    return generate_conjugations()


# ============================================================================
# Best Readings
# ============================================================================

def update_best_readings():
    """Update best_kana and best_kanji fields."""
    conn = get_connection()
    conn.execute("""
        UPDATE kanji_text 
        SET best_kana = (
            SELECT kt.text FROM kana_text kt 
            WHERE kt.seq = kanji_text.seq 
            ORDER BY COALESCE(kt.common, 999), kt.ord 
            LIMIT 1
        )
    """)
    conn.execute("""
        UPDATE kana_text
        SET best_kanji = (
            SELECT kt.text FROM kanji_text kt
            WHERE kt.seq = kana_text.seq AND kt.nokanji = 0
            ORDER BY COALESCE(kt.common, 999), kt.ord
            LIMIT 1
        )
        WHERE nokanji = 0
    """)
    conn.commit()


# ============================================================================
# Download Helpers
# ============================================================================

def is_gzip_file(path: str) -> bool:
    try:
        with open(path, 'rb') as f:
            return f.read(2) == b'\x1f\x8b'
    except Exception:
        return False


def download_jmdict(target_path: Optional[str] = None):
    import urllib.request
    url = "http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz"
    target = str(target_path or JMDICT_PATH)
    if not target.endswith('.gz'): target = target + '.gz'
    os.makedirs(os.path.dirname(target), exist_ok=True)
    print(f"Downloading JMdict from {url}...")
    urllib.request.urlretrieve(url, target)
    print(f"Saved to {target}")
    return target


def download_kanjidic(target_path: Optional[str] = None):
    import urllib.request
    url = "http://www.edrdg.org/kanjidic/kanjidic2.xml.gz"
    target = str(target_path or KANJIDIC_PATH)
    if not target.endswith('.gz'): target = target + '.gz'
    os.makedirs(os.path.dirname(target), exist_ok=True)
    print(f"Downloading KANJIDIC2 from {url}...")
    urllib.request.urlretrieve(url, target)
    print(f"Saved to {target}")
    return target


# ============================================================================
# Full Initialization
# ============================================================================

def init_database(jmdict_path: Optional[str] = None,
                  kanjidic_path: Optional[str] = None,
                  download: bool = False,
                  progress_callback=None):
    """Initialize the database with all required data."""
    jmdict_path = jmdict_path or JMDICT_PATH
    kanjidic_path = kanjidic_path or KANJIDIC_PATH
    
    if download:
        if not os.path.exists(jmdict_path): download_jmdict(jmdict_path)
        if not os.path.exists(kanjidic_path): download_kanjidic(kanjidic_path)
    
    create_schema()
    
    print("Loading JMdict...")
    jmdict_count = load_jmdict(jmdict_path, progress_callback)
    print(f"Loaded {jmdict_count} entries")
    
    print("Loading KANJIDIC...")
    kanjidic_count = load_kanjidic(kanjidic_path, progress_callback)
    print(f"Loaded {kanjidic_count} kanji")
    
    print("Updating best readings...")
    update_best_readings()
    
    print("Loading conjugations...")
    conj_count = load_conjugations()
    print(f"Loaded {conj_count} conjugation rules")
    
    print("Database initialization complete!")
    return {
        'jmdict_entries': jmdict_count,
        'kanji_count': kanjidic_count,
        'conjugations': conj_count,
    }


def database_exists() -> bool:
    if not os.path.exists(DB_PATH): return False
    try:
        count = query_single("SELECT COUNT(*) FROM entry")
        return count is not None and count > 0
    except Exception:
        return False
