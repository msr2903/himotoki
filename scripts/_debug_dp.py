"""Debug the DP path finding for the となら sentence."""
from himotoki.db.connection import get_session
from himotoki.segment import join_substring_words, get_segment_splits, get_segment_score

session = get_session()
text = '未来なんて誰にも分からないけど君となら歩いていける気がする'
seg_lists = join_substring_words(session, text)

# Find segment lists at positions 13-19
print("=== Segment lists around position 15 ===")
for sl in seg_lists:
    if sl.start >= 13 and sl.start <= 19:
        print(f'SegList [{sl.start}:{sl.end}]: {len(sl.segments)} segments')
        for s in sl.segments[:5]:
            print(f'  {s.get_text()} seq={s.word.seq} score={s.score}')

# Find specific seglists
sl_15 = None
sl_16 = None
for sl in seg_lists:
    if sl.start == 15 and sl.end == 16:
        sl_15 = sl
    elif sl.start == 16 and sl.end == 17:
        sl_16 = sl

# Try get_segment_splits for 君 → と
if sl_15 and sl_16:
    kimi = sl_15.segments[0]
    splits = get_segment_splits(kimi, sl_16)
    print(f'\nSplits from {kimi.get_text()} → SegList[16:17]: {len(splits)}')
    for i, sp in enumerate(splits):
        print(f'  Split {i}:')
        for item in sp:
            score = get_segment_score(item)
            desc = getattr(item, 'description', None)
            text_val = item.get_text() if hasattr(item, 'get_text') else '?'
            name = desc or text_val
            print(f'    {name} score={score}')

# Check if segfilter blocks 君 segments
print('\n=== Segfilter check ===')
from himotoki.synergies import apply_segfilters
if sl_15 and sl_16:
    results = apply_segfilters(sl_15, sl_16)
    print(f'Segfilter results: {len(results)} pairs')
    for new_left, new_right in results:
        left_texts = [s.get_text() for s in new_left.segments] if new_left else []
        right_texts = [s.get_text() for s in new_right.segments]
        print(f'  Left: {left_texts}  Right: {right_texts}')

session.close()
