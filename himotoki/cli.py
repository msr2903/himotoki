"""
Command line interface for himotoki.
Matches ichiran-cli functionality.

Usage:
    python -m himotoki.cli "日本語テキスト"
    python -m himotoki.cli -i "日本語テキスト"  # with info
    python -m himotoki.cli -f "日本語テキスト"  # full JSON
"""

import argparse
import json
import sys
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


def main(args: Optional[list] = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Command line interface for Himotoki (Japanese Morphological Analyzer)',
        prog='himotoki',
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
    
    # Get database session
    db_path = parsed.database or get_db_path()
    if not db_path:
        print('Error: No database found. Set HIMOTOKI_DB or use --database.', file=sys.stderr)
        return 1
    
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
