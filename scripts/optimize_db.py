#!/usr/bin/env python3
"""Optimize himotoki.db: drop redundant indexes, add covering indexes, clear entry.content, ANALYZE+VACUUM."""

import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def resolve_db_path() -> Path:
    """Resolve DB path like connection.py (HIMOTOKI_DB_PATH, data/himotoki.db, ~/.himotoki)."""
    env_path = os.environ.get("HIMOTOKI_DB_PATH")
    if env_path:
        return Path(env_path)

    user_db = Path.home() / ".himotoki" / "himotoki.db"
    if user_db.exists():
        return user_db

    package_db = PROJECT_ROOT / "data" / "himotoki.db"
    if package_db.exists():
        return package_db

    return package_db


def format_size(size_bytes: int) -> str:
    gb = size_bytes / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.2f} GB"
    mb = size_bytes / (1024 ** 2)
    return f"{mb:.1f} MB"


REDUNDANT_INDEXES = [
    "ix_kanji_text_text",
    "ix_kanji_text_seq",
    "ix_kanji_text_ord",
    "ix_kanji_text_common",
    "ix_kanji_text_text_seq",
    "ix_kana_text_text",
    "ix_kana_text_seq",
    "ix_kana_text_ord",
    "ix_kana_text_common",
    "ix_kana_text_text_seq",
    "ix_conj_source_reading_conj_id_text",
]

NEW_INDEXES = [
    (
        "ix_kanji_text_text_cover",
        "CREATE INDEX IF NOT EXISTS ix_kanji_text_text_cover "
        "ON kanji_text (text, seq, id, ord, common, best_kana)",
    ),
    (
        "ix_kanji_text_seq_ord",
        "CREATE INDEX IF NOT EXISTS ix_kanji_text_seq_ord "
        "ON kanji_text (seq, ord)",
    ),
    (
        "ix_kana_text_text_cover",
        "CREATE INDEX IF NOT EXISTS ix_kana_text_text_cover "
        "ON kana_text (text, seq, id, ord, common, best_kanji)",
    ),
    (
        "ix_kana_text_seq_ord",
        "CREATE INDEX IF NOT EXISTS ix_kana_text_seq_ord "
        "ON kana_text (seq, ord)",
    ),
    (
        "ix_conj_source_reading_conj_id",
        "CREATE INDEX IF NOT EXISTS ix_conj_source_reading_conj_id "
        "ON conj_source_reading (conj_id)",
    ),
]


def main() -> int:
    db_path = resolve_db_path()
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    size_before = db_path.stat().st_size
    print(f"Database: {db_path}")
    print(f"Size before: {format_size(size_before)}")
    print()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    print("Dropping redundant indexes...")
    for idx in REDUNDANT_INDEXES:
        print(f"  DROP INDEX IF EXISTS {idx}")
        cursor.execute(f"DROP INDEX IF EXISTS {idx}")
    conn.commit()

    print()
    print("Creating covering indexes (this may take a few minutes)...")
    for name, sql in NEW_INDEXES:
        print(f"  {name}")
        cursor.execute(sql)
    conn.commit()

    print()
    print("Clearing entry.content...")
    cursor.execute("SELECT COUNT(*) FROM entry WHERE content != ''")
    non_empty = cursor.fetchone()[0]
    print(f"  {non_empty:,} entries with non-empty content")
    cursor.execute("UPDATE entry SET content='' WHERE content != ''")
    conn.commit()
    print(f"  Cleared {cursor.rowcount:,} entries")

    print()
    print("Running ANALYZE...")
    cursor.execute("ANALYZE")
    conn.commit()

    print("Running VACUUM (this may take several minutes)...")
    cursor.execute("VACUUM")
    conn.commit()

    conn.close()

    size_after = db_path.stat().st_size
    saved = size_before - size_after
    print()
    print(f"Size after:  {format_size(size_after)}")
    print(f"Saved:       {format_size(saved)} ({100 * saved / size_before:.1f}%)")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
