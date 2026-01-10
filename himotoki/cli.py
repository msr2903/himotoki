"""
Command line interface for himotoki.
Matches ichiran-cli functionality.

Usage:
    python -m himotoki.cli "日本語テキスト"
    python -m himotoki.cli -i "日本語テキスト"  # with info
    python -m himotoki.cli -f "日本語テキスト"  # full JSON
    python -m himotoki.cli init-db              # initialize database
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

from himotoki.db.connection import get_session, get_db_path
from himotoki.output import (
    dict_segment, simple_segment,
    segment_to_json, segment_to_text,
    WordType, word_info_reading_str, get_senses_str,
    get_conj_description, get_entry_reading,
    format_conjugation_info,
)
from himotoki.characters import romanize_word


def format_word_info_text(session, word_infos) -> str:
    """Format word info list as text output."""
    lines = []
    
    # Romanized reading line
    romanized_parts = []
    for wi in word_infos:
        kana = wi.kana if isinstance(wi.kana, str) else wi.kana[0] if wi.kana else wi.text
        romanized_parts.append(romanize_word(kana))
    lines.append(' '.join(romanized_parts))
    
    # Individual word info
    for wi in word_infos:
        if wi.type == WordType.GAP:
            continue
        
        lines.append('')
        
        kana = wi.kana if isinstance(wi.kana, str) else wi.kana[0] if wi.kana else wi.text
        romanized = romanize_word(kana)
        lines.append(f"* {romanized}  {word_info_reading_str(wi)}")
        
        if wi.seq:
            senses = get_senses_str(session, wi.seq)
            lines.append(senses)
        
        # Conjugation info
        if wi.conjugations and wi.conjugations != 'root' and wi.seq:
            conj_strs = format_conjugation_info(session, wi.seq, wi.conjugations)
            for cs in conj_strs:
                lines.append(cs)
    
    return '\n'.join(lines)


def init_db_command(args) -> int:
    """Initialize the himotoki database."""
    import os
    
    # Determine paths
    if args.jmdict:
        jmdict_path = Path(args.jmdict)
    else:
        # Check common locations
        for p in [Path('data/JMdict_e.xml'), Path('JMdict_e.xml')]:
            if p.exists():
                jmdict_path = p
                break
        else:
            print("Error: JMdict file not found.", file=sys.stderr)
            print("Download from: http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz", file=sys.stderr)
            print("Or specify path with --jmdict", file=sys.stderr)
            return 1
    
    if args.output:
        db_path = Path(args.output)
    else:
        # Default to data directory
        db_path = Path('data/himotoki.db')
    
    if not jmdict_path.exists():
        print(f"Error: JMdict file not found: {jmdict_path}", file=sys.stderr)
        return 1
    
    # Confirm overwrite
    if db_path.exists() and not args.force:
        print(f"Database already exists: {db_path}")
        response = input("Overwrite? [y/N]: ").strip().lower()
        if response != 'y':
            print("Aborted.")
            return 1
    
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Initializing database...")
    print(f"  JMdict: {jmdict_path}")
    print(f"  Output: {db_path}")
    print()
    
    from himotoki.loading.jmdict import load_jmdict
    
    t0 = time.perf_counter()
    
    def progress(count):
        if count % 50000 == 0:
            print(f"  {count:,} entries loaded...")
    
    try:
        total = load_jmdict(
            xml_path=str(jmdict_path),
            db_path=str(db_path),
            load_extras=True,
            batch_size=5000,
            progress_callback=progress
        )
        
        elapsed = time.perf_counter() - t0
        db_size = os.path.getsize(db_path) / 1024 / 1024
        
        print()
        print(f"✅ Database initialized successfully!")
        print(f"   Entries: {total:,}")
        print(f"   Time: {elapsed:.1f}s ({elapsed/60:.1f} min)")
        print(f"   Size: {db_size:.1f}MB")
        print()
        print("Set HIMOTOKI_DB environment variable to use this database:")
        print(f'  export HIMOTOKI_DB="{db_path.absolute()}"')
        
        return 0
        
    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def main_init_db(args: list) -> int:
    """CLI entry point for init-db subcommand."""
    parser = argparse.ArgumentParser(
        description='Initialize the himotoki database from JMdict',
        prog='himotoki init-db',
    )
    
    parser.add_argument(
        '--jmdict', '-j',
        type=str,
        metavar='PATH',
        help='Path to JMdict XML file (default: data/JMdict_e.xml)',
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        metavar='PATH',
        help='Output database path (default: data/himotoki.db)',
    )
    
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Overwrite existing database without prompting',
    )
    
    parsed = parser.parse_args(args)
    return init_db_command(parsed)


def main_setup(args: list) -> int:
    """CLI entry point for setup subcommand."""
    import argparse as ap
    
    parser = ap.ArgumentParser(
        description='Set up the himotoki database',
        prog='himotoki setup',
    )
    
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Skip confirmation prompt',
    )
    
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Force rebuild even if database exists',
    )
    
    parsed = parser.parse_args(args)
    
    from himotoki.setup import run_setup, is_database_ready, get_db_path, prompt_for_setup
    
    # Check if already set up
    if is_database_ready() and not parsed.force:
        print(f"✅ Database already exists at: {get_db_path()}")
        print("   Use --force to rebuild.")
        return 0
    
    # Prompt for confirmation unless --yes
    if not parsed.yes:
        if not prompt_for_setup():
            return 1
        print()
    
    # Run setup
    success = run_setup(force=parsed.force, confirm=False)
    return 0 if success else 1


def main(args: Optional[list] = None) -> int:
    """Main CLI entry point."""
    # Check for subcommands
    args_list = args if args is not None else sys.argv[1:]
    
    if args_list and args_list[0] == 'setup':
        return main_setup(args_list[1:])
    if args_list and args_list[0] == 'init-db':
        return main_init_db(args_list[1:])
    
    parser = argparse.ArgumentParser(
        description='Command line interface for Himotoki (Japanese Morphological Analyzer)',
        prog='himotoki',
        epilog='Subcommands:\n  himotoki setup      Set up the dictionary database (recommended)\n  himotoki init-db    Initialize database from local JMdict file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        'text',
        nargs='*',
        help='Japanese text to analyze',
    )
    
    parser.add_argument(
        '-i', '--with-info',
        action='store_true',
        help='Print dictionary info for each word',
    )
    
    parser.add_argument(
        '-f', '--full',
        action='store_true',
        help='Full split info as JSON',
    )
    
    parser.add_argument(
        '-l', '--limit',
        type=int,
        default=1,
        metavar='N',
        help='Limit segmentations to N results (default: 1, use with -f)',
    )
    
    parser.add_argument(
        '-d', '--database',
        type=str,
        default=None,
        metavar='PATH',
        help='Path to SQLite database file',
    )
    
    parser.add_argument(
        '-v', '--version',
        action='store_true',
        help='Show version information',
    )
    
    parsed = parser.parse_args(args)
    
    if parsed.version:
        print('himotoki 0.1.0')
        return 0
    
    # Get input text
    text = ' '.join(parsed.text) if parsed.text else ''
    
    if not text:
        parser.print_help()
        return 1
    
    # Get database session - with first-use setup prompt
    db_path = parsed.database
    if db_path is None:
        db_path = get_db_path()
    
    if not db_path or not Path(db_path).exists():
        # First-use experience: prompt for setup
        from himotoki.setup import ensure_database_or_prompt, get_db_path as setup_get_db_path
        
        if not ensure_database_or_prompt():
            print("\nRun 'himotoki setup' when you're ready to initialize the database.", file=sys.stderr)
            return 1
        
        # After setup, get the new database path
        db_path = str(setup_get_db_path())
    
    try:
        session = get_session(db_path)
    except Exception as e:
        print(f'Error connecting to database: {e}', file=sys.stderr)
        return 1
    
    # Initialize suffix cache for compound word detection
    from himotoki.suffixes import init_suffixes
    init_suffixes(session)
    
    try:
        if parsed.full:
            # Full JSON output
            limit = parsed.limit if parsed.limit > 0 else 5
            results = dict_segment(session, text, limit=limit)
            
            # Format as ichiran-compatible JSON
            output = []
            for word_infos, score in results:
                segments = []
                for wi in word_infos:
                    from himotoki.output import word_info_gloss_json
                    kana = wi.kana if isinstance(wi.kana, str) else wi.kana[0] if wi.kana else wi.text
                    romanized = romanize_word(kana)
                    segment_json = word_info_gloss_json(session, wi)
                    segments.append([romanized, segment_json, []])
                output.append([segments, score])
            
            print(json.dumps(output, ensure_ascii=False))
        
        elif parsed.with_info:
            # Text output with dictionary info
            results = dict_segment(session, text, limit=1)
            if results:
                word_infos, score = results[0]
                output = format_word_info_text(session, word_infos)
                print(output)
            else:
                print(text)
        
        else:
            # Simple romanization
            results = dict_segment(session, text, limit=1)
            if results:
                word_infos, score = results[0]
                romanized_parts = []
                for wi in word_infos:
                    kana = wi.kana if isinstance(wi.kana, str) else wi.kana[0] if wi.kana else wi.text
                    romanized_parts.append(romanize_word(kana))
                print(' '.join(romanized_parts))
            else:
                print(text)
        
        return 0
    
    except Exception as e:
        print(f'Error processing text: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()


if __name__ == '__main__':
    sys.exit(main())
