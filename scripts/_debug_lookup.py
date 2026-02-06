"""Temporary debug script to check DB entries."""
from himotoki.db.connection import get_session
from himotoki.db.models import KanaText, KanjiText, Conjugation, ConjProp, Entry, Sense, SenseProp
from sqlalchemy import select, and_

session = get_session()

# Find となら entries
print("=== となら entries ===")
results = session.execute(select(KanaText).where(KanaText.text == 'となら')).scalars().all()
for r in results:
    conj = session.execute(select(Conjugation).where(Conjugation.seq == r.seq)).scalars().first()
    cp = session.execute(select(ConjProp).where(ConjProp.conj_id == conj.id)).scalars().first() if conj else None
    print(f"  seq={r.seq}, from_seq={conj.from_seq if conj else None}, conj_type={cp.conj_type if cp else None}")

# Find と particle
print("\n=== と particle (seq 1008490) ===")
results = session.execute(select(KanaText).where(and_(KanaText.text == 'と', KanaText.seq == 1008490))).scalars().all()
for r in results:
    print(f"  seq={r.seq}")

# Find なら entries
print("\n=== なら entries ===")
results = session.execute(select(KanaText).where(KanaText.text == 'なら')).scalars().all()
for r in results:
    conj = session.execute(select(Conjugation).where(Conjugation.seq == r.seq)).scalars().first()
    cp = session.execute(select(ConjProp).where(ConjProp.conj_id == conj.id)).scalars().first() if conj else None
    print(f"  seq={r.seq}, from_seq={conj.from_seq if conj else None}, conj_type={cp.conj_type if cp else None}")

# Find ないよう entries
print("\n=== ないよう entries ===")
results = session.execute(select(KanaText).where(KanaText.text == 'ないよう')).scalars().all()
for r in results:
    entry = session.execute(select(Entry).where(Entry.seq == r.seq)).scalars().first()
    conj = session.execute(select(Conjugation).where(Conjugation.seq == r.seq)).scalars().first()
    senses = session.execute(select(Sense).where(Sense.seq == r.seq)).scalars().all()
    sense_texts = []
    for s in senses[:2]:
        props = session.execute(select(SenseProp).where(SenseProp.sense_id == s.id)).scalars().all()
        sense_texts.append(f"tag={props[0].tag if props else '?'}")
    from_seq = conj.from_seq if conj else None
    print(f"  seq={r.seq}, from_seq={from_seq}, senses={sense_texts}")

# Find 内容 kanji entry
print("\n=== 内容 entries ===")
results = session.execute(select(KanjiText).where(KanjiText.text == '内容')).scalars().all()
for r in results:
    print(f"  seq={r.seq}")

# Find 田中 entries
print("\n=== 田中 entries ===")
results = session.execute(select(KanjiText).where(KanjiText.text == '田中')).scalars().all()
for r in results:
    print(f"  kanji seq={r.seq}")
results = session.execute(select(KanaText).where(KanaText.text == 'たなか')).scalars().all()
for r in results:
    print(f"  kana seq={r.seq}")

# Find なら for conditional of だ 
print("\n=== なら as conjugation of だ (2089020) ===")
results = session.execute(
    select(KanaText)
    .join(Conjugation, KanaText.seq == Conjugation.seq)
    .where(and_(KanaText.text == 'なら', Conjugation.from_seq == 2089020))
).scalars().all()
for r in results:
    conj = session.execute(select(Conjugation).where(and_(Conjugation.seq == r.seq, Conjugation.from_seq == 2089020))).scalars().first()
    cp = session.execute(select(ConjProp).where(ConjProp.conj_id == conj.id)).scalars().first() if conj else None
    print(f"  seq={r.seq}, conj_type={cp.conj_type if cp else None}")

print("\n=== となる entries (2100900, 2163190) ===")
for from_seq in [2100900, 2163190]:
    entry = session.execute(select(Entry).where(Entry.seq == from_seq)).scalars().first()
    if entry:
        senses = session.execute(select(Sense).where(Sense.seq == from_seq)).scalars().all()
        print(f"  from_seq={from_seq}, n_senses={len(senses)}")

session.close()
