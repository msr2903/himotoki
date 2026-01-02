import sqlite3
import os
import shutil
from himotoki.dict_load import generate_conjugations, create_schema, SCHEMA_SQL
from himotoki.settings import DB_PATH

# Use a temporary DB
TEST_DB = "test_conjugations.db"
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

# Override DB_PATH via environment variable or monkeypatching if necessary
# But himotoki.conn likely uses DB_PATH from settings.
# Let's mock get_connection in himotoki.dict_load and himotoki.conn if needed.
# However, settings.py might just read env var.
# Let's check settings.py first. It usually defines DB_PATH.
# Assuming I can't easily change it, I will swap the file.

ORIG_DB = "himotoki/data/himotoki.db"
BACKUP_DB = "himotoki/data/himotoki.db.bak"

if os.path.exists(ORIG_DB):
    shutil.move(ORIG_DB, BACKUP_DB)

# Create a minimal test DB at the location himotoki expects
conn = sqlite3.connect(ORIG_DB)
conn.executescript(SCHEMA_SQL)

# Insert a sample entry: 食べる (taberu) - v1
# Seq: 1358280
conn.execute("INSERT INTO entry (seq, content, root_p, n_kanji, n_kana, primary_nokanji) VALUES (1358280, '', 1, 1, 1, 0)")
conn.execute("INSERT INTO kanji_text (seq, text, ord, common, conjugate_p) VALUES (1358280, '食べる', 0, 1, 1)")
conn.execute("INSERT INTO kana_text (seq, text, ord, common, conjugate_p) VALUES (1358280, 'たべる', 0, 1, 1)")
conn.execute("INSERT INTO sense (seq, ord) VALUES (1358280, 0)")
sense_id = conn.execute("SELECT id FROM sense WHERE seq=1358280").fetchone()[0]
conn.execute("INSERT INTO sense_prop (tag, sense_id, text, ord, seq) VALUES ('pos', ?, 'v1', 0, 1358280)", (sense_id,))

# Insert sample entry: 行く (iku) - v5k-s
# Seq: 1284460 (Note: there are multiple entries for iku, 1162230 is common)
# Let's use 1162230
conn.execute("INSERT INTO entry (seq, content, root_p, n_kanji, n_kana, primary_nokanji) VALUES (1162230, '', 1, 1, 1, 0)")
conn.execute("INSERT INTO kanji_text (seq, text, ord, common, conjugate_p) VALUES (1162230, '行く', 0, 1, 1)")
conn.execute("INSERT INTO kana_text (seq, text, ord, common, conjugate_p) VALUES (1162230, 'いく', 0, 1, 1)")
conn.execute("INSERT INTO sense (seq, ord) VALUES (1162230, 0)")
sense_id = conn.execute("SELECT id FROM sense WHERE seq=1162230").fetchone()[0]
conn.execute("INSERT INTO sense_prop (tag, sense_id, text, ord, seq) VALUES ('pos', ?, 'v5k-s', 0, 1162230)", (sense_id,))

# Insert sample entry: 書く (kaku) - v5k
# Seq: 1326460
conn.execute("INSERT INTO entry (seq, content, root_p, n_kanji, n_kana, primary_nokanji) VALUES (1326460, '', 1, 1, 1, 0)")
conn.execute("INSERT INTO kanji_text (seq, text, ord, common, conjugate_p) VALUES (1326460, '書く', 0, 1, 1)")
conn.execute("INSERT INTO kana_text (seq, text, ord, common, conjugate_p) VALUES (1326460, 'かく', 0, 1, 1)")
conn.execute("INSERT INTO sense (seq, ord) VALUES (1326460, 0)")
sense_id = conn.execute("SELECT id FROM sense WHERE seq=1326460").fetchone()[0]
conn.execute("INSERT INTO sense_prop (tag, sense_id, text, ord, seq) VALUES ('pos', ?, 'v5k', 0, 1326460)", (sense_id,))

conn.commit()
conn.close()

try:
    print("Running generate_conjugations...")
    count = generate_conjugations()
    print(f"Generated {count} conjugations.")

    # Verification
    conn = sqlite3.connect(ORIG_DB)

    # Check conjugation table
    count = conn.execute("SELECT COUNT(*) FROM conjugation").fetchone()[0]
    print(f"Conjugation entries: {count}")

    # Check for specific forms
    # 食べた (tabeta) - Past
    res = conn.execute("""
        SELECT c.seq, kt.text, cp.conj_type
        FROM conjugation c
        JOIN kanji_text kt ON c.seq = kt.seq
        JOIN conj_prop cp ON c.id = cp.conj_id
        WHERE kt.text = '食べた'
    """).fetchone()
    if res:
        print(f"Found 食べた: seq={res[0]}, conj_type={res[2]}")
    else:
        print("ERROR: 食べた not found!")

    # Check for 行って (itte) - Te-form of Iku (v5k-s)
    # v5k-s should conjugate to 行って (itte), NOT 行いて (iite)
    res = conn.execute("""
        SELECT c.seq, kt.text, cp.conj_type
        FROM conjugation c
        JOIN kanji_text kt ON c.seq = kt.seq
        JOIN conj_prop cp ON c.id = cp.conj_id
        WHERE kt.text = '行って'
    """).fetchone()
    if res:
        print(f"Found 行って: seq={res[0]}, conj_type={res[2]}")
    else:
        print("ERROR: 行って not found!")

    # Check for secondary conjugation: 食べられる (taberareru) - Passive (or Potential)
    # Potential of v1 is rule-based, Passive is rule-based.
    # But Secondary Conjugation might generate Causative-Passive: 食べさせられる
    # Causative (7) of v1: 食べさせる (v1)
    # Passive (6) of 食べさせる: 食べさせられる

    # Check for 食べさせる (Causative)
    res = conn.execute("""
        SELECT c.seq, kt.text
        FROM conjugation c
        JOIN kanji_text kt ON c.seq = kt.seq
        JOIN conj_prop cp ON c.id = cp.conj_id
        WHERE kt.text = '食べさせる' AND cp.conj_type = 7
    """).fetchone()
    if res:
        print(f"Found 食べさせる: seq={res[0]}")
    else:
        print("ERROR: 食べさせる not found!")

    # Check for 食べさせられる (Causative-Passive)
    # This comes from secondary conjugation of 食べさせる
    res = conn.execute("""
        SELECT c.seq, kt.text
        FROM conjugation c
        JOIN kanji_text kt ON c.seq = kt.seq
        JOIN conj_prop cp ON c.id = cp.conj_id
        WHERE kt.text = '食べさせられる'
    """).fetchone()
    if res:
        print(f"Found 食べさせられる: seq={res[0]}")
    else:
        print("WARNING: 食べさせられる not found (Secondary conjugation might not be covering this or rules differ)")

    # Check 書ける (potential of kaku)
    res = conn.execute("""
        SELECT c.seq, kt.text
        FROM conjugation c
        JOIN kanji_text kt ON c.seq = kt.seq
        JOIN conj_prop cp ON c.id = cp.conj_id
        WHERE kt.text = '書ける'
    """).fetchone()
    if res:
        print(f"Found 書ける: seq={res[0]}")
    else:
        print("ERROR: 書ける not found!")

    conn.close()

finally:
    # Restore DB
    if os.path.exists(BACKUP_DB):
        shutil.move(BACKUP_DB, ORIG_DB)
    elif os.path.exists(ORIG_DB):
        os.remove(ORIG_DB)
