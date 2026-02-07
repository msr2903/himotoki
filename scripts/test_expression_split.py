#!/usr/bin/env python3
"""Test expression decomposition."""

from himotoki.segment import segment_text
from himotoki.db.connection import get_session

def show_best(session, text):
    results = segment_text(session, text, limit=3)
    if results:
        path, score = results[0]
        parts = []
        for item in path:
            if hasattr(item, 'segments'):
                for seg in item.segments:
                    t = getattr(seg, 'text', None) or getattr(seg.word, 'text', '?')
                    parts.append(t)
            elif hasattr(item, 'text'):
                parts.append(item.text)
            else:
                parts.append(f'<{type(item).__name__}>')
        print(f'{text} -> {" + ".join(parts)} (score {score})')

with get_session() as session:
    print("=== Expressions that should be SPLIT ===")
    show_best(session, '涙を流す')
    show_best(session, '剣を抜く')
    show_best(session, '条件を満たす')
    show_best(session, '窓際の席')
    show_best(session, '担任の先生')
    show_best(session, '名前をつけて')
    show_best(session, '関心を持つ')
    
    print()
    print("=== Expressions that should STAY TOGETHER ===")
    show_best(session, 'どうしても')
    show_best(session, 'だろうか')
    show_best(session, 'ありがとうございます')
    show_best(session, 'かもしれない')
