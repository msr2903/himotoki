#!/usr/bin/env python3
"""
Migrate conjugation data to Ichiran-style format.

This script converts the flat `conj_lookup` table into Ichiran's format:
1. Each unique conjugated form gets its own seq number (starting at 10000000)
2. Conjugated forms are inserted into `kana_text`/`kanji_text` tables
3. `conjugation` table links conjugated seq → original seq
4. `conj_prop` table stores conjugation properties (type, pos, neg, fml)

This matches how Ichiran stores conjugations, making lookups simpler and
avoiding duplicate matches from different source words.
"""

import sqlite3
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Set
import time

# Database path
DB_PATH = Path(__file__).parent / "himotoki" / "data" / "himotoki.db"

# Starting seq for conjugated forms (Ichiran uses 10000000+)
CONJ_SEQ_START = 10000000


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


def migrate_conjugations():
    """Main migration function."""
    print(f"Opening database: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check if migration already done
    cursor.execute("SELECT COUNT(*) FROM conjugation")
    if cursor.fetchone()[0] > 0:
        print("Migration already done (conjugation table not empty)")
        response = input("Drop existing data and re-migrate? [y/N]: ")
        if response.lower() != 'y':
            print("Aborted.")
            return
        print("Dropping existing conjugation data...")
        cursor.execute("DELETE FROM conj_prop")
        cursor.execute("DELETE FROM conjugation")
        # Also remove any entries with seq >= CONJ_SEQ_START
        cursor.execute(f"DELETE FROM kana_text WHERE seq >= {CONJ_SEQ_START}")
        cursor.execute(f"DELETE FROM kanji_text WHERE seq >= {CONJ_SEQ_START}")
        cursor.execute(f"DELETE FROM entry WHERE seq >= {CONJ_SEQ_START}")
        conn.commit()
    
    print("Reading conj_lookup table...")
    cursor.execute("""
        SELECT text, reading, seq, conj_type, pos, neg, fml, source_text, source_reading
        FROM conj_lookup
        ORDER BY text, reading, seq
    """)
    rows = cursor.fetchall()
    print(f"Found {len(rows)} conjugation entries")
    
    # Group by (text, reading) - each unique form gets one new seq
    # Store all the source info for linking
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
    
    print(f"Found {len(form_groups)} unique conjugated forms")
    
    # Assign seq numbers
    next_seq = CONJ_SEQ_START
    form_to_seq: Dict[Tuple[str, str], int] = {}
    
    for key in form_groups:
        form_to_seq[key] = next_seq
        next_seq += 1
    
    print(f"Assigned seq numbers {CONJ_SEQ_START} to {next_seq - 1}")
    
    # Insert into database
    print("Inserting entries...")
    t0 = time.time()
    
    entries_batch = []
    kana_batch = []
    kanji_batch = []
    conj_batch = []
    prop_batch = []
    
    conj_id = 1
    
    for (text, reading), sources in form_groups.items():
        new_seq = form_to_seq[(text, reading)]
        
        # Create entry (minimal, just for the seq to exist)
        entries_batch.append((new_seq, '', 0, 0, 1, 0))
        
        # Determine best common score from sources
        # For now, use None since these are conjugated forms
        common = None
        
        # Insert into kana_text or kanji_text based on text
        if is_kana_only(text):
            kana_batch.append((new_seq, text, 0, common, '', 0, 0))
        else:
            kana_batch.append((new_seq, reading, 0, common, '', 0, 0))
            kanji_batch.append((new_seq, text, 0, common, '', 0, 0, reading))
        
        # Track unique (source_seq, conj_type, pos, neg, fml) combinations
        seen_props: Set[Tuple] = set()
        
        for src in sources:
            prop_key = (src['source_seq'], src['conj_type'], src['pos'], 
                       src['neg'], src['fml'])
            
            if prop_key in seen_props:
                continue
            seen_props.add(prop_key)
            
            # Create conjugation link
            conj_batch.append((conj_id, new_seq, src['source_seq'], None))
            
            # Create conj_prop
            prop_batch.append((
                conj_id,
                src['conj_type'],
                src['pos'],
                1 if src['neg'] else 0,
                1 if src['fml'] else 0,
            ))
            
            conj_id += 1
    
    # Batch insert
    print(f"  Inserting {len(entries_batch)} entries...")
    cursor.executemany(
        "INSERT INTO entry (seq, content, root_p, n_kanji, n_kana, primary_nokanji) VALUES (?, ?, ?, ?, ?, ?)",
        entries_batch
    )
    
    print(f"  Inserting {len(kana_batch)} kana_text entries...")
    cursor.executemany(
        "INSERT INTO kana_text (seq, text, ord, common, common_tags, conjugate_p, nokanji) VALUES (?, ?, ?, ?, ?, ?, ?)",
        kana_batch
    )
    
    if kanji_batch:
        print(f"  Inserting {len(kanji_batch)} kanji_text entries...")
        cursor.executemany(
            "INSERT INTO kanji_text (seq, text, ord, common, common_tags, conjugate_p, nokanji, best_kana) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            kanji_batch
        )
    
    print(f"  Inserting {len(conj_batch)} conjugation entries...")
    cursor.executemany(
        "INSERT INTO conjugation (id, seq, from_seq, via) VALUES (?, ?, ?, ?)",
        conj_batch
    )
    
    print(f"  Inserting {len(prop_batch)} conj_prop entries...")
    cursor.executemany(
        "INSERT INTO conj_prop (conj_id, conj_type, pos, neg, fml) VALUES (?, ?, ?, ?, ?)",
        prop_batch
    )
    
    print("Committing...")
    conn.commit()
    
    t1 = time.time()
    print(f"Migration completed in {t1 - t0:.1f} seconds")
    
    # Verify
    cursor.execute("SELECT COUNT(*) FROM conjugation")
    print(f"Conjugation entries: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM conj_prop")
    print(f"Conj_prop entries: {cursor.fetchone()[0]}")
    cursor.execute(f"SELECT COUNT(*) FROM kana_text WHERE seq >= {CONJ_SEQ_START}")
    print(f"New kana_text entries: {cursor.fetchone()[0]}")
    cursor.execute(f"SELECT COUNT(*) FROM kanji_text WHERE seq >= {CONJ_SEQ_START}")
    print(f"New kanji_text entries: {cursor.fetchone()[0]}")
    
    conn.close()
    print("Done!")


if __name__ == "__main__":
    migrate_conjugations()
