"""
Command-line interface for Himotoki.

Provides commands for analyzing, romanizing, and
working with Japanese text.
"""

import argparse
import json
import sys
from typing import Optional

from himotoki import (
    romanize, romanize_word, simple_segment, dict_segment,
    as_hiragana, as_katakana, normalize
)
from himotoki.characters import split_sentences, split_paragraphs
from himotoki.dict import reading_str, get_senses_str
from himotoki.dict_load import (
    init_database, database_exists,
    download_jmdict, download_kanjidic
)
from himotoki.deromanize import romaji_to_hiragana, romaji_to_katakana
from himotoki.kanji import all_kanji_info, estimate_text_difficulty


def cmd_romanize(args):
    """Romanize Japanese text."""
    text = args.text
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    
    if not text:
        print("Error: No text provided", file=sys.stderr)
        return 1
    
    result = romanize(text, method=args.method)
    print(result)
    return 0


def cmd_segment(args):
    """Segment Japanese text into words."""
    text = args.text
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    
    if not text:
        print("Error: No text provided", file=sys.stderr)
        return 1
    
    if args.json:
        results = dict_segment(text, limit=args.limit)
        output = []
        
        for words, score in results:
            path = {
                'score': score,
                'words': [w.to_dict() for w in words]
            }
            output.append(path)
        
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        words = simple_segment(text, limit=args.limit)
        
        for word in words:
            if word.type == 'gap':
                print(f"  {word.text} (unrecognized)")
            else:
                reading = reading_str(word)
                senses = ""
                if word.seq and not args.brief:
                    seq = word.seq if isinstance(word.seq, int) else word.seq[0]
                    senses = get_senses_str(seq)
                
                print(f"• {reading}")
                if senses:
                    for line in senses.split('\n'):
                        print(f"    {line}")
    
    return 0


def cmd_analyze(args):
    """Analyze Japanese text (segment + romanize)."""
    text = args.text
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    
    if not text:
        print("Error: No text provided", file=sys.stderr)
        return 1
    
    # Segment
    words = simple_segment(text)
    
    # Build output
    print(f"Input: {text}")
    print(f"Romanization: {romanize(text)}")
    print()
    print("Words:")
    
    for word in words:
        reading = reading_str(word)
        romaji = romanize_word(word.kana if isinstance(word.kana, str) else word.kana[0])
        
        if word.type == 'gap':
            print(f"  ? {word.text}")
        else:
            print(f"  • {reading} [{romaji}]")
            
            if word.seq and not args.brief:
                seq = word.seq if isinstance(word.seq, int) else word.seq[0]
                senses = get_senses_str(seq)
                for line in senses.split('\n')[:3]:  # First 3 senses
                    print(f"      {line}")
    
    return 0


def cmd_kana(args):
    """Convert between romaji and kana."""
    text = args.text
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    
    if not text:
        print("Error: No text provided", file=sys.stderr)
        return 1
    
    if args.hiragana:
        print(romaji_to_hiragana(text))
    elif args.katakana:
        print(romaji_to_katakana(text))
    elif args.romaji:
        print(romanize(text))
    else:
        # Default: romaji to hiragana
        print(romaji_to_hiragana(text))
    
    return 0


def cmd_kanji(args):
    """Get kanji information."""
    text = args.text
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    
    if not text:
        print("Error: No text provided", file=sys.stderr)
        return 1
    
    kanji_list = all_kanji_info(text)
    
    if args.json:
        output = []
        for k in kanji_list:
            output.append({
                'char': k.char,
                'grade': k.grade,
                'strokes': k.strokes,
                'freq': k.freq,
                'jlpt': k.jlpt,
                'on': k.readings_on,
                'kun': k.readings_kun,
                'meanings': k.meanings,
            })
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if not kanji_list:
            print("No kanji found in text.")
            return 0
        
        for k in kanji_list:
            print(f"\n{k.char}")
            print(f"  Grade: {k.grade or 'N/A'}, Strokes: {k.strokes or 'N/A'}, JLPT: {k.jlpt or 'N/A'}")
            if k.readings_on:
                print(f"  On: {', '.join(k.readings_on[:5])}")
            if k.readings_kun:
                print(f"  Kun: {', '.join(k.readings_kun[:5])}")
            if k.meanings:
                print(f"  Meaning: {', '.join(k.meanings[:5])}")
    
    return 0


def cmd_difficulty(args):
    """Estimate text difficulty."""
    text = args.text
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    
    if not text:
        print("Error: No text provided", file=sys.stderr)
        return 1
    
    stats = estimate_text_difficulty(text)
    
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(f"JLPT Level Estimate: N{stats['jlpt_estimate']}")
        print(f"School Grade Level: {stats['level']:.1f}")
        print(f"Total Kanji: {stats.get('total_kanji', 0)}")
        print(f"Unique Kanji: {stats.get('unique_kanji', 0)}")
        print(f"Complexity: {stats['complexity']:.2%}")
    
    return 0


def cmd_sentences(args):
    """Split text into sentences."""
    text = args.text
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    
    if not text:
        print("Error: No text provided", file=sys.stderr)
        return 1
    
    sentences = split_sentences(text, keep_punctuation=not args.strip)
    
    if args.json:
        output = {
            'count': len(sentences),
            'sentences': sentences
        }
        if args.analyze:
            # Add word analysis for each sentence
            analyzed = []
            for sent in sentences:
                words = simple_segment(sent)
                analyzed.append({
                    'sentence': sent,
                    'romaji': romanize(sent),
                    'words': [w.to_dict() for w in words]
                })
            output['analyzed'] = analyzed
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"Found {len(sentences)} sentence(s):\n")
        for i, sentence in enumerate(sentences, 1):
            if args.number:
                print(f"{i}. {sentence}")
            else:
                print(f"• {sentence}")
            
            if args.romanize:
                print(f"  → {romanize(sentence)}")
            
            if args.analyze:
                words = simple_segment(sentence)
                word_strs = []
                for w in words:
                    if w.type == 'gap':
                        word_strs.append(f"[{w.text}]")
                    else:
                        word_strs.append(w.text)
                print(f"  Words: {' | '.join(word_strs)}")
            
            if not args.compact:
                print()
    
    return 0


def cmd_init(args):
    """Initialize the database."""
    print("Initializing Himotoki database...")
    
    if database_exists() and not args.force:
        print("Database already exists. Use --force to reinitialize.")
        return 0
    
    try:
        stats = init_database(
            jmdict_path=args.jmdict,
            kanjidic_path=args.kanjidic,
            download=args.download
        )
        print(f"\nInitialization complete!")
        print(f"  Entries: {stats['jmdict_entries']}")
        print(f"  Kanji: {stats['kanji_count']}")
        print(f"  Conjugations: {stats['conjugations']}")
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nUse --download to automatically download dictionary files.")
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_download(args):
    """Download dictionary data."""
    try:
        if args.jmdict or args.all:
            download_jmdict()
        
        if args.kanjidic or args.all:
            download_kanjidic()
        
        print("\nDownload complete!")
        print("Run 'himotoki init' to load the data into the database.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_conjugate(args):
    """Look up conjugated forms to find dictionary entries."""
    from himotoki.dict import lookup_conjugation, get_senses_str
    
    text = args.text
    if not text:
        text = sys.stdin.read().strip()
    
    if not text:
        print("No text provided", file=sys.stderr)
        return 1
    
    results = lookup_conjugation(text)
    
    if not results:
        print(f"No conjugation matches found for: {text}")
        return 0
    
    if args.json:
        import json
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    
    print(f"Conjugation lookup: {text}")
    print("=" * 40)
    
    # Group by source entry
    seen_seqs = set()
    for res in results:
        seq = res['seq']
        if seq in seen_seqs and not args.all:
            continue
        seen_seqs.add(seq)
        
        neg_str = " (negative)" if res['neg'] else ""
        fml_str = " (formal)" if res['fml'] else ""
        
        print(f"\n{res['source_text']} 【{res['source_reading']}】")
        print(f"  Conjugation: {res['conj_desc']}{neg_str}{fml_str}")
        print(f"  POS: {res['pos']}")
        print(f"  Seq: {seq}")
        
        if args.verbose:
            senses = get_senses_str(seq)
            if senses:
                print(f"  Meanings:")
                for line in senses.split('\n'):
                    print(f"    {line}")
    
    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog='himotoki',
        description='Japanese morphological analyzer and romanization tool'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # romanize command
    p_romanize = subparsers.add_parser('romanize', help='Romanize Japanese text')
    p_romanize.add_argument('text', nargs='?', help='Text to romanize')
    p_romanize.add_argument('--method', '-m', default='hepburn',
                           choices=['hepburn', 'simplified', 'traditional', 'modified', 'passport', 'kunrei'],
                           help='Romanization method')
    p_romanize.set_defaults(func=cmd_romanize)
    
    # segment command
    p_segment = subparsers.add_parser('segment', help='Segment text into words')
    p_segment.add_argument('text', nargs='?', help='Text to segment')
    p_segment.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    p_segment.add_argument('--brief', '-b', action='store_true', help='Brief output')
    p_segment.add_argument('--limit', '-l', type=int, default=5, help='Max alternatives')
    p_segment.set_defaults(func=cmd_segment)
    
    # analyze command
    p_analyze = subparsers.add_parser('analyze', help='Analyze Japanese text')
    p_analyze.add_argument('text', nargs='?', help='Text to analyze')
    p_analyze.add_argument('--brief', '-b', action='store_true', help='Brief output')
    p_analyze.set_defaults(func=cmd_analyze)
    
    # kana command
    p_kana = subparsers.add_parser('kana', help='Convert between romaji and kana')
    p_kana.add_argument('text', nargs='?', help='Text to convert')
    p_kana.add_argument('--hiragana', '-H', action='store_true', help='Convert to hiragana')
    p_kana.add_argument('--katakana', '-K', action='store_true', help='Convert to katakana')
    p_kana.add_argument('--romaji', '-r', action='store_true', help='Convert to romaji')
    p_kana.set_defaults(func=cmd_kana)
    
    # kanji command
    p_kanji = subparsers.add_parser('kanji', help='Get kanji information')
    p_kanji.add_argument('text', nargs='?', help='Text containing kanji')
    p_kanji.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    p_kanji.set_defaults(func=cmd_kanji)
    
    # difficulty command
    p_difficulty = subparsers.add_parser('difficulty', help='Estimate text difficulty')
    p_difficulty.add_argument('text', nargs='?', help='Text to analyze')
    p_difficulty.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    p_difficulty.set_defaults(func=cmd_difficulty)
    
    # sentences command
    p_sentences = subparsers.add_parser('sentences', help='Split text into sentences')
    p_sentences.add_argument('text', nargs='?', help='Text to split')
    p_sentences.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    p_sentences.add_argument('--number', '-n', action='store_true', help='Number sentences')
    p_sentences.add_argument('--romanize', '-r', action='store_true', help='Show romanization')
    p_sentences.add_argument('--analyze', '-a', action='store_true', help='Show word analysis')
    p_sentences.add_argument('--strip', '-s', action='store_true', help='Strip punctuation')
    p_sentences.add_argument('--compact', '-c', action='store_true', help='Compact output')
    p_sentences.set_defaults(func=cmd_sentences)
    
    # init command
    p_init = subparsers.add_parser('init', help='Initialize database')
    p_init.add_argument('--jmdict', help='Path to JMdict file')
    p_init.add_argument('--kanjidic', help='Path to KANJIDIC file')
    p_init.add_argument('--download', '-d', action='store_true', 
                       help='Download dictionary files if missing')
    p_init.add_argument('--force', '-f', action='store_true',
                       help='Force reinitialization')
    p_init.set_defaults(func=cmd_init)
    
    # download command
    p_download = subparsers.add_parser('download', help='Download dictionary files')
    p_download.add_argument('--jmdict', action='store_true', help='Download JMdict')
    p_download.add_argument('--kanjidic', action='store_true', help='Download KANJIDIC')
    p_download.add_argument('--all', '-a', action='store_true', help='Download all')
    p_download.set_defaults(func=cmd_download)
    
    # conjugate command
    p_conjugate = subparsers.add_parser('conjugate', help='Look up conjugated forms')
    p_conjugate.add_argument('text', nargs='?', help='Conjugated form to look up')
    p_conjugate.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    p_conjugate.add_argument('--verbose', '-v', action='store_true', help='Show meanings')
    p_conjugate.add_argument('--all', '-a', action='store_true', help='Show all matches')
    p_conjugate.set_defaults(func=cmd_conjugate)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 0
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
