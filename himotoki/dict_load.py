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
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

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
# Conjugation Loading
# ============================================================================

def generate_conjugations(progress_callback=None):
    """
    Generate all conjugated forms from dictionary entries.
    
    For each verb and adjective entry, generates all possible
    conjugations and stores them in the database for reverse lookup.
    
    This allows looking up a conjugated form (e.g., 食べた) and
    finding its dictionary form (食べる).
    """
    from himotoki.conjugations import (
        get_conjugation_rules, is_conjugatable, conjugate_word,
        ConjType, should_conjugate, fix_iku_conjugation
    )
    
    conn = get_connection()
    
    # Add index on conj_source_map.text for fast lookup
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_conj_source_text 
        ON conj_source_map(text)
    """)
    
    # Also create a simple conjugation lookup table
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conj_lookup_reading ON conj_lookup(reading)")
    
    # Clear existing conjugation data
    conn.execute("DELETE FROM conj_lookup")
    conn.execute("DELETE FROM conj_source_map")
    conn.execute("DELETE FROM conj_prop")
    conn.execute("DELETE FROM conjugation")
    
    # Get all entries with their POS
    # Group entries by seq and collect all POS tags for that entry
    entries = query("""
        SELECT DISTINCT e.seq, sp.text as pos
        FROM entry e
        JOIN sense_prop sp ON sp.seq = e.seq
        WHERE sp.tag = 'pos'
    """)
    
    # Build a mapping of seq -> list of POS tags
    pos_map = {}
    for row in entries:
        seq = row[0]
        pos = _normalize_pos(row[1])
        if pos:
            if seq not in pos_map:
                pos_map[seq] = set()
            pos_map[seq].add(pos)
    
    total_entries = len(pos_map)
    processed = 0
    conjugations_added = 0
    
    for seq, pos_tags in pos_map.items():
        for pos in pos_tags:
            if not is_conjugatable(pos):
                continue
            
            # Get kanji and kana forms for this entry
            kanji_forms = query(
                "SELECT text FROM kanji_text WHERE seq = ? ORDER BY ord",
                (seq,)
            )
            kana_forms = query(
                "SELECT text FROM kana_text WHERE seq = ? ORDER BY ord",
                (seq,)
            )
            
            # Generate conjugations for each form
            for kf in kanji_forms:
                kanji_text = kf[0]
                # Find best kana for this kanji
                kana_reading = None
                if kana_forms:
                    kana_reading = kana_forms[0][0]
                
                # Generate all conjugations
                count = _generate_entry_conjugations(
                    conn, seq, kanji_text, kana_reading, pos
                )
                conjugations_added += count
            
            # Also generate for kana-only forms
            for rf in kana_forms:
                kana_text = rf[0]
                count = _generate_entry_conjugations(
                    conn, seq, kana_text, kana_text, pos
                )
                conjugations_added += count
        
        processed += 1
        if progress_callback and processed % 5000 == 0:
            progress_callback(processed, total_entries)
    
    conn.commit()
    
    if progress_callback:
        progress_callback(total_entries, total_entries)
    
    return conjugations_added


def _normalize_pos(pos_text: str) -> Optional[str]:
    """
    Convert JMdict POS description to short tag.
    
    Args:
        pos_text: Full POS description from JMdict.
        
    Returns:
        Short POS tag (e.g., 'v1', 'v5k') or None.
    """
    pos_text = pos_text.lower() if pos_text else ''
    
    # Normalize quotes - JMdict uses various quote styles
    pos_text = pos_text.replace("'", "'").replace("'", "'").replace('"', "'")
    
    # Ichidan verbs
    if 'ichidan' in pos_text:
        if 'kureru' in pos_text:
            return 'v1-s'
        return 'v1'
    
    # Special handling for Iku/Yuku verb
    if 'iku' in pos_text and 'yuku' in pos_text and 'special' in pos_text:
        return 'v5k-s'
    
    # Godan verbs - check for specific endings
    if 'godan' in pos_text:
        # Check for specific consonant endings first (before general 'u ending')
        if "'ku'" in pos_text or "ku ending" in pos_text or "'ku' ending" in pos_text:
            if 'iku' in pos_text or 'special' in pos_text:
                return 'v5k-s'
            return 'v5k'
        elif "'gu'" in pos_text or "gu ending" in pos_text or "'gu' ending" in pos_text:
            return 'v5g'
        elif "'su'" in pos_text or "su ending" in pos_text or "'su' ending" in pos_text:
            return 'v5s'
        elif "'tsu'" in pos_text or "tsu ending" in pos_text or "'tsu' ending" in pos_text:
            return 'v5t'
        elif "'nu'" in pos_text or "nu ending" in pos_text or "'nu' ending" in pos_text:
            return 'v5n'
        elif "'bu'" in pos_text or "bu ending" in pos_text or "'bu' ending" in pos_text:
            return 'v5b'
        elif "'mu'" in pos_text or "mu ending" in pos_text or "'mu' ending" in pos_text:
            return 'v5m'
        elif "'ru'" in pos_text or "ru ending" in pos_text or "'ru' ending" in pos_text:
            if 'irregular' in pos_text:
                return 'v5r-i'
            return 'v5r'
        elif 'aru' in pos_text:
            return 'v5aru'
        # General 'u' ending last (most general pattern)
        elif "'u'" in pos_text or "u ending" in pos_text or "'u' ending" in pos_text:
            if 'special' in pos_text:
                return 'v5u-s'
            return 'v5u'
    
    # Irregular verbs
    if 'suru' in pos_text:
        if 'included' in pos_text or 'special' in pos_text:
            return 'vs-i'
        if '-suru' in pos_text:
            return 'vs-s'
        return 'vs-i'
    
    if 'kuru' in pos_text:
        return 'vk'
    
    # Copula
    if 'copula' in pos_text:
        return 'copula'
    
    # Adjectives
    if 'adjective' in pos_text:
        if '-i' in pos_text or 'keiyoushi' in pos_text:
            if 'yoi' in pos_text or 'ii' in pos_text:
                return 'adj-ix'
            return 'adj-i'
    
    return None


def _generate_entry_conjugations(conn, seq: int, text: str, reading: str, pos: str) -> int:
    """
    Generate all conjugations for a single dictionary entry.
    
    Args:
        conn: Database connection.
        seq: Entry sequence number.
        text: Dictionary form (kanji or kana).
        reading: Kana reading.
        pos: Part of speech tag.
        
    Returns:
        Number of conjugations generated.
    """
    from himotoki.conjugations import (
        get_conjugation_rules, fix_iku_conjugation
    )
    
    rules = get_conjugation_rules(pos)
    if not rules:
        return 0
    
    count = 0
    reading = reading or text
    
    for rule in rules:
        # Skip dictionary form (non-past affirmative plain)
        if (rule.conj_type == 1 and rule.neg == False and 
            rule.fml == False and rule.stem_chars == 0):
            continue
        
        # Apply rule to get conjugated form
        conj_text = rule.apply(text, is_kana=(text == reading))
        conj_reading = rule.apply(reading, is_kana=True)
        
        # Special handling for 行く - ONLY for v5k-s (iku/yuku special class)
        if pos == 'v5k-s' and text.endswith('く'):
            conj_text = fix_iku_conjugation(text, conj_text, rule)
            conj_reading = fix_iku_conjugation(reading, conj_reading, rule)
        
        # Skip if conjugation produces same form as source
        if conj_text == text and conj_reading == reading:
            continue
        
        # Insert the kana form (always)
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
        
        # For kanji words, also insert kanji+kana mixed forms
        # This handles cases like 来る -> 来た (kanji + kana okurigana)
        if text != reading:
            # Calculate okurigana length by comparing text and reading
            # E.g., 来る (くる) -> okurigana is る (1 char), kanji is 来
            #       食べる (たべる) -> okurigana is べる (2 chars), kanji is 食
            #       書く (かく) -> okurigana is く (1 char), kanji is 書
            
            # Find common kana suffix between text and reading (the okurigana)
            okurigana_len = 0
            for i in range(1, min(len(text), len(reading)) + 1):
                if text[-i] == reading[-i]:
                    okurigana_len = i
                else:
                    break
            
            # Kanji stem is the non-okurigana part
            if okurigana_len > 0:
                kanji_stem = text[:-okurigana_len]
            else:
                # No matching okurigana - entire text is kanji
                # Use the first character as kanji stem
                kanji_stem = text[0] if text else ''
            
            if kanji_stem:
                # Calculate okurigana in the conjugated reading
                # Reading stem length = reading length - okurigana_len
                reading_stem_len = len(reading) - okurigana_len
                
                # Okurigana for conjugated form = conjugated reading minus the reading stem
                if len(conj_reading) > reading_stem_len:
                    new_okurigana = conj_reading[reading_stem_len:]
                else:
                    new_okurigana = conj_reading
                
                # Build kanji+kana form
                kanji_form = kanji_stem + new_okurigana
                
                # Only insert if different from the kana form
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
    """
    Load conjugation data.
    
    This is a wrapper that calls generate_conjugations() to
    build conjugations from the JMdict entries.
    
    Args:
        path: Unused (kept for API compatibility).
        
    Returns:
        Number of conjugation entries generated.
    """
    return generate_conjugations()


# ============================================================================
# Best Readings
# ============================================================================

def update_best_readings():
    """
    Update best_kana and best_kanji fields in text tables.
    
    Links kanji entries to their most common kana reading
    and vice versa.
    """
    conn = get_connection()
    
    # Update best_kana for kanji entries
    conn.execute("""
        UPDATE kanji_text 
        SET best_kana = (
            SELECT kt.text FROM kana_text kt 
            WHERE kt.seq = kanji_text.seq 
            ORDER BY COALESCE(kt.common, 999), kt.ord 
            LIMIT 1
        )
    """)
    
    # Update best_kanji for kana entries
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
    """Check if a file is gzip compressed by reading magic bytes."""
    try:
        with open(path, 'rb') as f:
            return f.read(2) == b'\x1f\x8b'
    except Exception:
        return False


def download_jmdict(target_path: Optional[str] = None):
    """
    Download JMdict from the official source.
    
    Args:
        target_path: Where to save the file.
    """
    import urllib.request
    
    url = "http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz"
    target = str(target_path or JMDICT_PATH)
    
    # Ensure target ends with .gz since we're downloading compressed
    if not target.endswith('.gz'):
        target = target + '.gz'
    
    os.makedirs(os.path.dirname(target), exist_ok=True)
    
    print(f"Downloading JMdict from {url}...")
    urllib.request.urlretrieve(url, target)
    print(f"Saved to {target}")
    return target


def download_kanjidic(target_path: Optional[str] = None):
    """
    Download KANJIDIC2 from the official source.
    
    Args:
        target_path: Where to save the file.
    """
    import urllib.request
    
    url = "http://www.edrdg.org/kanjidic/kanjidic2.xml.gz"
    target = str(target_path or KANJIDIC_PATH)
    
    # Ensure target ends with .gz since we're downloading compressed
    if not target.endswith('.gz'):
        target = target + '.gz'
    
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
    """
    Initialize the database with all required data.
    
    Args:
        jmdict_path: Path to JMdict file.
        kanjidic_path: Path to KANJIDIC2 file.
        download: If True, download missing files.
        progress_callback: Optional callback for progress.
    """
    jmdict_path = jmdict_path or JMDICT_PATH
    kanjidic_path = kanjidic_path or KANJIDIC_PATH
    
    # Download if needed
    if download:
        if not os.path.exists(jmdict_path):
            download_jmdict(jmdict_path)
        if not os.path.exists(kanjidic_path):
            download_kanjidic(kanjidic_path)
    
    # Create schema
    create_schema()
    
    # Load data
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
    """Check if the database exists and has data."""
    if not os.path.exists(DB_PATH):
        return False
    
    try:
        count = query_single("SELECT COUNT(*) FROM entry")
        return count is not None and count > 0
    except Exception:
        return False
