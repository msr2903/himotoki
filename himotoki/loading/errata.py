"""
Errata corrections for the himotoki database.
Ports ichiran's dict-errata.lisp functionality.

These corrections are applied after loading JMDict and conjugations
to fix data issues and add missing forms.
"""

import logging
from typing import Optional, List, Tuple
from sqlalchemy import select, update, delete, and_
from sqlalchemy.orm import Session

from himotoki.db.models import (
    Entry, KanjiText, KanaText, Sense, SenseProp, Gloss,
    Conjugation, ConjProp, ConjSourceReading,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================

def add_sense_prop(session: Session, seq: int, sense_ord: int, tag: str, text: str) -> None:
    """Add a sense property to an entry."""
    sense = session.execute(
        select(Sense).where(and_(Sense.seq == seq, Sense.ord == sense_ord))
    ).scalar_one_or_none()
    
    if not sense:
        logger.warning(f"Sense not found: seq={seq}, ord={sense_ord}")
        return
    
    # Check if already exists
    existing = session.execute(
        select(SenseProp).where(and_(
            SenseProp.sense_id == sense.id,
            SenseProp.tag == tag,
            SenseProp.text == text
        ))
    ).scalar_one_or_none()
    
    if existing:
        return
    
    # Get max ord for this tag
    max_ord = session.execute(
        select(SenseProp.ord).where(and_(
            SenseProp.sense_id == sense.id,
            SenseProp.tag == tag
        )).order_by(SenseProp.ord.desc())
    ).scalar() or -1
    
    prop = SenseProp(
        sense_id=sense.id,
        seq=seq,
        tag=tag,
        text=text,
        ord=max_ord + 1
    )
    session.add(prop)


def delete_sense_prop(session: Session, seq: int, tag: str, text: str) -> None:
    """Delete a sense property from an entry."""
    session.execute(
        delete(SenseProp).where(and_(
            SenseProp.seq == seq,
            SenseProp.tag == tag,
            SenseProp.text == text
        ))
    )


def set_common(session: Session, table: str, seq: int, text: str, common: Optional[int]) -> None:
    """Set the common value for a reading."""
    if table == 'kana_text':
        model = KanaText
    elif table == 'kanji_text':
        model = KanjiText
    else:
        raise ValueError(f"Unknown table: {table}")
    
    session.execute(
        update(model).where(and_(
            model.seq == seq,
            model.text == text
        )).values(common=common)
    )


def add_reading(session: Session, seq: int, text: str, common: Optional[int] = None,
                conjugate_p: bool = True) -> None:
    """Add a kana reading to an entry."""
    # Check if already exists
    existing = session.execute(
        select(KanaText).where(and_(KanaText.seq == seq, KanaText.text == text))
    ).scalar_one_or_none()
    
    if existing:
        return
    
    # Get max ord for this seq
    max_ord = session.execute(
        select(KanaText.ord).where(KanaText.seq == seq).order_by(KanaText.ord.desc())
    ).scalar() or -1
    
    reading = KanaText(
        seq=seq,
        text=text,
        ord=max_ord + 1,
        common=common,
        nokanji=False,
    )
    session.add(reading)


def delete_reading(session: Session, seq: int, text: str) -> None:
    """Delete a reading from an entry."""
    session.execute(
        delete(KanaText).where(and_(KanaText.seq == seq, KanaText.text == text))
    )
    session.execute(
        delete(KanjiText).where(and_(KanjiText.seq == seq, KanjiText.text == text))
    )


def set_primary_nokanji(session: Session, seq: int, value: Optional[bool]) -> None:
    """Set the primary_nokanji flag for an entry."""
    session.execute(
        update(Entry).where(Entry.seq == seq).values(primary_nokanji=value)
    )


def delete_conjugation(session: Session, seq: int, from_seq: int) -> None:
    """Delete a conjugation entry and its related data."""
    # Find the conjugation
    conj = session.execute(
        select(Conjugation).where(and_(
            Conjugation.seq == seq,
            Conjugation.from_seq == from_seq
        ))
    ).scalars().all()
    
    if not conj:
        return
    
    conj_ids = [c.id for c in conj]
    
    # Delete related data
    session.execute(
        delete(ConjProp).where(ConjProp.conj_id.in_(conj_ids))
    )
    session.execute(
        delete(ConjSourceReading).where(ConjSourceReading.conj_id.in_(conj_ids))
    )
    session.execute(
        delete(Conjugation).where(Conjugation.id.in_(conj_ids))
    )


# ============================================================================
# Conjugation Errata
# ============================================================================

def add_gozaimasu_conjs(session: Session) -> None:
    """
    Add conjugations for ございます (seqs 1612690, 2253080).
    
    Ports ichiran's add-gozaimasu-conjs function.
    ございます doesn't conjugate normally, so we add forms manually.
    """
    seqs = [1612690, 2253080]  # ございます, ございません
    
    # Conjugation patterns: (conj_type, pos, fml, suffix_replacement)
    # Replace す with the suffix
    patterns = [
        (1, 'exp', True, 'せん'),      # Negative: ございません
        (2, 'exp', False, 'した'),     # Past: ございました
        (3, 'exp', False, 'して'),     # Te-form: ございまして
        (9, 'exp', False, 'しょう'),   # Volitional: ございましょう
        (11, 'exp', False, 'したら'),  # Conditional: ございましたら
        (12, 'exp', False, 'したり'),  # Alternative: ございましたり
    ]
    
    from himotoki.loading.conjugations import get_next_seq
    next_seq = get_next_seq(session)
    
    for base_seq in seqs:
        # Get base readings
        readings = session.execute(
            select(KanaText.text).where(KanaText.seq == base_seq)
        ).scalars().all()
        
        if not readings:
            continue
        
        for conj_type, pos, fml, suffix in patterns:
            # Generate conjugated forms
            for reading in readings:
                if not reading.endswith('す'):
                    continue
                
                conj_text = reading[:-1] + suffix
                
                # Check if conjugated entry already exists
                existing = session.execute(
                    select(KanaText.seq).where(KanaText.text == conj_text)
                ).scalar_one_or_none()
                
                if existing:
                    # Just add conjugation link if entry exists
                    conj_seq = existing
                else:
                    # Create new entry
                    conj_seq = next_seq
                    next_seq += 1
                    
                    entry = Entry(seq=conj_seq, root_p=False)
                    session.add(entry)
                    
                    kana = KanaText(seq=conj_seq, text=conj_text, ord=0, common=0)
                    session.add(kana)
                
                # Check if conjugation already exists
                existing_conj = session.execute(
                    select(Conjugation).where(and_(
                        Conjugation.seq == conj_seq,
                        Conjugation.from_seq == base_seq
                    ))
                ).scalar_one_or_none()
                
                if existing_conj:
                    continue
                
                # Create conjugation entry
                conj = Conjugation(seq=conj_seq, from_seq=base_seq, via=None)
                session.add(conj)
                session.flush()  # Get the ID
                
                # Create conjugation property
                prop = ConjProp(
                    conj_id=conj.id,
                    conj_type=conj_type,
                    pos=pos,
                    neg=(conj_type == 1),  # Negative form
                    fml=fml
                )
                session.add(prop)
                
                # Create source reading mapping
                src_reading = ConjSourceReading(
                    conj_id=conj.id,
                    text=conj_text,
                    source_text=reading
                )
                session.add(src_reading)
    
    logger.info("Added ございます conjugations")


def add_custom_suru_verbs(session: Session) -> None:
    """
    Add custom する-verb entries that exist in Ichiran's extra.xml but not JMdict.
    
    These are common expressions that need to be recognized as single units.
    """
    from himotoki.loading.conjugations import get_next_seq
    
    # Custom する-verbs to add: (text, kanji, glosses)
    # お掛け is used in お手数をおかけして (to cause trouble)
    custom_entries = [
        ('おかけ', 'お掛け', ['to cause', 'to sit', 'to spend (time)']),
    ]
    
    next_seq = get_next_seq(session)
    
    for kana_text, kanji_text, glosses in custom_entries:
        # Check if entry already exists
        existing = session.execute(
            select(KanaText.seq).where(KanaText.text == kana_text)
        ).scalar_one_or_none()
        
        if existing:
            logger.debug(f"Custom entry '{kana_text}' already exists at seq {existing}")
            continue
        
        seq = next_seq
        next_seq += 1
        
        # Create entry
        entry = Entry(seq=seq, root_p=True, n_kanji=1, n_kana=1, primary_nokanji=True)
        session.add(entry)
        
        # Create kanji text
        kanji = KanjiText(seq=seq, text=kanji_text, ord=0, common=0)
        session.add(kanji)
        
        # Create kana text
        kana = KanaText(seq=seq, text=kana_text, ord=0, common=0, conjugate_p=True, nokanji=True)
        session.add(kana)
        
        # Create sense with vs (suru-verb) pos
        sense = Sense(seq=seq, ord=0)
        session.add(sense)
        session.flush()  # Get sense.id
        
        # Add pos tag: vs (noun taking the aux verb suru)
        pos_prop = SenseProp(sense_id=sense.id, seq=seq, tag='pos', text='vs', ord=0)
        session.add(pos_prop)
        
        # Add misc tags: uk (usually kana), hum (humble)
        uk_prop = SenseProp(sense_id=sense.id, seq=seq, tag='misc', text='uk', ord=0)
        session.add(uk_prop)
        hum_prop = SenseProp(sense_id=sense.id, seq=seq, tag='misc', text='hum', ord=1)
        session.add(hum_prop)
        
        # Add glosses
        for i, gloss_text in enumerate(glosses):
            gloss = Gloss(sense_id=sense.id, text=gloss_text, ord=i)
            session.add(gloss)
        
        logger.debug(f"Added custom entry '{kana_text}' at seq {seq}")
    
    logger.info(f"Added {len(custom_entries)} custom する-verb entries")


def add_synthetic_suffix_entries(session: Session) -> None:
    """
    Add synthetic entries for suffixes that don't exist in JMdict.
    
    These are entries that Ichiran expects for suffix handling but aren't
    in the standard JMdict data. They are referenced by their seq numbers
    in dict-grammar.lisp.
    
    Ports the following from ichiran's dict-errata.lisp:
    - seq 900000: たそう (tasou) - combined tai+sou suffix
    """
    # Synthetic suffix entries: (seq, text, description)
    synthetic_entries = [
        (900000, 'たそう', 'looking like wanting to... (tai+sou suffix)'),
    ]
    
    for seq, text, description in synthetic_entries:
        # Check if entry already exists
        existing = session.execute(
            select(Entry).where(Entry.seq == seq)
        ).scalar_one_or_none()
        
        if existing:
            logger.debug(f"Synthetic entry seq={seq} '{text}' already exists")
            continue
        
        # Create entry
        entry = Entry(seq=seq, root_p=True, n_kanji=0, n_kana=1, primary_nokanji=True)
        session.add(entry)
        
        # Create kana text
        kana = KanaText(seq=seq, text=text, ord=0, common=0, conjugate_p=False, nokanji=True)
        session.add(kana)
        
        # Create sense with suf (suffix) pos
        sense = Sense(seq=seq, ord=0)
        session.add(sense)
        session.flush()  # Get sense.id
        
        # Add pos tag: suf (suffix)
        pos_prop = SenseProp(sense_id=sense.id, seq=seq, tag='pos', text='suf', ord=0)
        session.add(pos_prop)
        
        # Add gloss
        gloss = Gloss(sense_id=sense.id, text=description, ord=0)
        session.add(gloss)
        
        logger.debug(f"Added synthetic suffix entry seq={seq} '{text}'")
    
    logger.info(f"Added {len(synthetic_entries)} synthetic suffix entries")


def add_deha_ja_readings(session: Session) -> None:
    """
    Add じゃ readings for では forms.
    
    Ports ichiran's add-deha-ja-readings function.
    For conjugated forms of だ (2089020) that start with では,
    add corresponding じゃ readings.
    """
    DA_SEQ = 2089020
    
    # Find conjugated entries from だ with では readings
    deha_list = session.execute(
        select(Conjugation.seq, KanaText.text).distinct().where(and_(
            Conjugation.from_seq == DA_SEQ,
            KanaText.seq == Conjugation.seq,
            KanaText.text.like('では%')
        ))
    ).all()
    
    for seq, deha_text in deha_list:
        ja_text = 'じゃ' + deha_text[2:]  # Replace では with じゃ
        add_reading(session, seq, ja_text)
    
    # Also add じゃ source readings for conjugation mappings
    deha_src_readings = session.execute(
        select(ConjSourceReading.conj_id, ConjSourceReading.text, ConjSourceReading.source_text)
        .join(Conjugation, Conjugation.id == ConjSourceReading.conj_id)
        .where(and_(
            Conjugation.from_seq == DA_SEQ,
            ConjSourceReading.text.like('では%')
        ))
    ).all()
    
    for conj_id, text, source_text in deha_src_readings:
        ja_text = 'じゃ' + text[2:]
        
        # Check if already exists
        existing = session.execute(
            select(ConjSourceReading).where(and_(
                ConjSourceReading.conj_id == conj_id,
                ConjSourceReading.text == ja_text
            ))
        ).scalar_one_or_none()
        
        if existing:
            continue
        
        # Calculate source text (replace では with じゃ if applicable)
        if source_text.startswith('では'):
            ja_source = 'じゃ' + source_text[2:]
        else:
            ja_source = source_text
        
        src_reading = ConjSourceReading(
            conj_id=conj_id,
            text=ja_text,
            source_text=ja_source
        )
        session.add(src_reading)
    
    logger.info("Added じゃ readings for では forms")


# ============================================================================
# Counter POS Adjustments (from add-errata-counters)
# ============================================================================

# Format: (seq, sense_ord, pos_tag)
# These entries need 'ctr' (counter) POS tag added
COUNTER_POS_ENTRIES = [
    (1427420, 0, 'ctr'),  # 丁目
    (1397450, 0, 'ctr'),  # 組
    (1397450, 1, 'ctr'),  # 組
    (1351270, 0, 'ctr'),  # 章
    (1351270, 1, 'n'),    # 章
    (1490430, 0, 'ctr'),  # 秒
    (1490430, 1, 'ctr'),  # 秒
    (2020680, 0, 'ctr'),  # 時
    (1502840, 0, 'ctr'),  # 分
    (1502840, 1, 'ctr'),  # 分
    (1373990, 0, 'ctr'),  # 世紀
    (1281690, 0, 'ctr'),  # 行
    (1281690, 1, 'n'),    # 行
    (1042610, 1, 'ctr'),  # キロ
    (1042610, 2, 'ctr'),  # キロ
    (1100610, 0, 'ctr'),  # パーセント
    (1411070, 0, 'ctr'),  # 袋
    (1411070, 1, 'n'),    # 袋
    (1328810, 0, 'ctr'),  # 種
    (1284220, 0, 'ctr'),  # 号
    (1284220, 1, 'n'),    # 号
    (1284220, 1, 'n-suf'),  # 号
    (1482360, 0, 'ctr'),  # 番地
    (2022640, 0, 'ctr'),  # 番
    (1175570, 0, 'ctr'),  # 円
    (1175570, 1, 'n'),    # 円
    (1315130, 0, 'ctr'),  # 字
    (1315130, 1, 'n'),    # 字
    (1199640, 0, 'ctr'),  # 回転
    (1047880, 0, 'ctr'),  # ケース
    (1047880, 1, 'n'),    # ケース
    (1244080, 0, 'ctr'),  # 区
    (1244080, 1, 'ctr'),  # 区
    (1239700, 0, 'ctr'),  # 曲
    (1294940, 0, 'ctr'),  # 才/歳
    (1294940, 1, 'suf'),  # 才/歳
    (1575510, 0, 'ctr'),  # コマ
    (1575510, 1, 'n'),    # コマ
    (1505390, 0, 'ctr'),  # 文字
    (1101700, 0, 'ctr'),  # パック
    (1120410, 0, 'ctr'),  # ページ
    (1956400, 0, 'ctr'),  # 集
    (1333450, 0, 'ctr'),  # 週
    (1480050, 0, 'ctr'),  # 反
    (1480050, 1, 'ctr'),  # 反
    (1480050, 2, 'ctr'),  # 反
    (1956530, 0, 'ctr'),  # 寸
    (1324110, 0, 'ctr'),  # 尺
    (1324110, 1, 'n'),    # 尺
    (1382450, 0, 'ctr'),  # 石
    (1382450, 1, 'ctr'),  # 石
    (1253800, 1, 'ctr'),  # 桁
    (1297240, 0, 'ctr'),  # 作
    (1368480, 0, 'ctr'),  # 人前
    (1732510, 1, 'ctr'),  # 番手
    (1732510, 2, 'ctr'),  # 番手
    (2086480, 1, 'ctr'),  # 頭身
    (1331080, 0, 'ctr'),  # 周忌
    # From dated errata functions
    (1445160, 0, 'ctr'),  # 度 (jan18)
    (1468900, 0, 'ctr'),  # 年生 (mar18)
    (1241380, 0, 'ctr'),  # 斤 (mar18)
    (1241380, 1, 'ctr'),  # 斤 (mar18)
    (1658480, 0, 'ctr'),  # apr19
    (1468900, 0, 'ctr'),  # 年生 (jan20)
    (1469050, 0, 'ctr'),  # 年度 (jan20)
    (1469050, 1, 'ctr'),  # 年度 (jan20)
    (1469050, 2, 'ctr'),  # 年度 (jan20)
    (1284270, 0, 'ctr'),  # 号車 (jan20)
    (1315920, 0, 'ctr'),  # 時間 (apr20) - added as new sense
    (1220540, 0, 'ctr'),  # apr20
    (1220540, 3, 'ctr'),  # apr20
    (1220540, 4, 'ctr'),  # apr20
    (1220540, 5, 'ctr'),  # apr20
    (1220540, 6, 'ctr'),  # apr20
    (2842087, 0, 'ctr'),  # パー (apr20)
    (1613860, 0, 'ctr'),  # 回戦 (jan21)
    (1613860, 1, 'ctr'),  # 回戦 (jan21)
    (2145410, 0, 'ctr'),  # 間 (jan21)
    (1138570, 1, 'ctr'),  # ラウンド (jan25)
    (1138570, 2, 'ctr'),  # ラウンド (jan25)
    (1138570, 3, 'ctr'),  # ラウンド (jan25)
]

# Counter POS entries to delete
DELETE_COUNTER_POS_ENTRIES = [
    (1215240, 'ctr'),  # jan21
    (1240530, 'ctr'),  # 玉 (jan22)
    (1138570, 'ctr'),  # ラウンド sense 0 (jan25)
]


# ============================================================================
# Primary Nokanji Adjustments
# ============================================================================

# Entries where primary_nokanji should be set to None/False
PRIMARY_NOKANJI_CLEAR = [
    1538900,  # ただ
    1580640,  # 人
    1289030,  # いまいち
    1374550,  # すごい (feb17)
    1591900,  # きれい (feb17)
    1000230,  # あかん (feb17)
    1517810,  # もやし (feb17)
    1585410,  # まま (feb17)
    1258330,  # いぬ (jan18)
    1588930,  # おかず (jan18)
    1565440,  # mar18
    1631830,  # くせに (jan19)
    1409110,  # apr19
    2081610,  # apr19 (was added by mistake)
    1495000,  # まずい (jan20)
    1756600,  # がんもどき (jul20)
]


# ============================================================================
# Conjugation Deletions
# ============================================================================

# Format: (seq, from_seq)
# seq = conjugated form, from_seq = source/root form
CONJUGATION_DELETIONS = [
    (2029110, 2257550),  # delete adj stem conjugation: な from ない
    (2086640, 2684620),  # delete adj stem conjugation: し from しい
]


# ============================================================================
# Additional Common Adjustments from Dated Errata
# ============================================================================

# These are additional common adjustments from add-errata-feb17 through add-errata-jan25
ADDITIONAL_COMMON_ADJUSTMENTS = [
    # feb17
    ('kana_text', 2136890, 'とする', None),
    ('kana_text', 2100900, 'となる', None),
    ('kana_text', 1006200, 'すべき', None),
    ('kana_text', 2683060, 'なのです', None),
    ('kana_text', 2683060, 'なんです', None),
    ('kana_text', 1001200, 'おい', None),
    ('kana_text', 1001200, 'おおい', None),
    ('kanji_text', 1441840, '伝い', 0),
    ('kanji_text', 1409140, '身体', 0),
    ('kanji_text', 2830705, '身体', None),
    ('kana_text', 1009040, 'どきっと', 0),
    ('kana_text', 2261300, 'するべき', None),
    ('kana_text', 2215430, 'には', None),
    ('kana_text', 2210140, 'まい', None),
    ('kana_text', 2192950, 'なさい', None),
    ('kana_text', 2143350, 'かも', None),
    ('kana_text', 2106890, 'そのよう', None),
    ('kana_text', 2084040, 'すれば', None),
    ('kana_text', 2036080, 'うつ', None),
    ('kana_text', 1922760, 'という', None),
    ('kana_text', 1632520, 'ふん', None),
    ('kana_text', 1631750, 'がる', None),
    ('kana_text', 1394680, 'そういう', None),
    ('kana_text', 1208840, 'かつ', None),
    ('kana_text', 1011430, 'べき', None),
    ('kana_text', 1008340, 'である', None),
    ('kana_text', 1007960, 'ちんちん', None),
    ('kana_text', 1301230, 'さんなん', None),
    ('kanji_text', 1311010, '氏', 20),
    ('kana_text', 1311010, 'うじ', 20),
    ('kanji_text', 2101130, '氏', 21),
    ('kana_text', 1155180, 'いない', 10),
    ('kanji_text', 1609450, '思いきって', 0),
    ('kanji_text', 1309320, '思いきる', 0),
    ('kana_text', 1312880, 'メス', 15),
    ('kana_text', 1312880, 'めす', None),
    ('kana_text', 2061540, 'ぶっちゃける', 0),
    ('kana_text', 2034520, 'ですら', 0),
    ('kana_text', 1566210, 'いずれ', 9),
    ('kanji_text', 1000420, '彼の', None),
    ('kanji_text', 2219590, '元', 10),
    ('kana_text', 2219590, 'もと', 10),
    ('kana_text', 1394760, 'さほど', 0),
    ('kana_text', 1529560, 'なし', 10),
    ('kana_text', 1436830, 'ていない', None),
    ('kana_text', 1057580, 'さぼる', 0),
    ('kanji_text', 1402420, '走り', None),
    ('kana_text', 1402420, 'はしり', None),
    ('kana_text', 1209540, 'かる', None),
    ('kana_text', 1244840, 'かる', None),
    ('kana_text', 1280640, 'こうは', 0),
    ('kana_text', 1158960, 'いほう', 0),
    # jan18
    ('kanji_text', 2067770, '等', None),
    ('kana_text', 2067770, 'ら', None),
    ('kanji_text', 1242230, '近よる', 38),
    ('kanji_text', 1315120, '字', 0),
    ('kana_text', 1315120, 'あざ', 0),
    ('kanji_text', 1315130, '字', 5),
    ('kana_text', 1315130, 'じ', 0),
    ('kana_text', 1005530, 'しっくり', 0),
    ('kana_text', 1554850, 'りきむ', None),
    ('kana_text', 2812650, 'ゲー', 0),
    ('kana_text', 2083340, 'やろう', 0),
    ('kana_text', 2083340, 'やろ', 0),
    ('kana_text', 1008730, 'とろ', None),
    ('kana_text', 1457840, 'ないかい', None),
    ('kana_text', 2829697, 'いかん', 0),
    ('kana_text', 2157330, 'おじゃま', 9),
    ('kana_text', 1199800, 'かいらん', None),
    ('kana_text', 2719580, 'いらん', 0),
    ('kana_text', 1808040, 'めちゃ', 0),
    ('kana_text', 1277450, 'すき', 9),
    ('kana_text', 1006460, 'ズレる', 0),
    ('kanji_text', 1522290, '本会議', 0),
    ('kana_text', 1522290, 'ほんかいぎ', 0),
    ('kana_text', 1220570, 'きたい', 10),
    ('kana_text', 1221020, 'きたい', 11),
    ('kana_text', 2083990, 'ならん', 0),
    ('kanji_text', 2518850, '切れ', 0),
    ('kanji_text', 1221900, '基地外', 0),
    ('kana_text', 1379380, 'せいと', 10),
    ('kanji_text', 1203280, '外に', None),
    ('kanji_text', 1383690, '後継ぎ', 0),
    ('kana_text', 2083600, 'すまん', 0),
    # mar18
    ('kana_text', 1207610, 'かける', 0),
    ('kanji_text', 1236100, '強いる', None),
    ('kana_text', 1236100, 'しいる', None),
    ('kana_text', 1451750, 'おんなじ', 0),
    ('kanji_text', 2068330, '事故る', 0),
    ('kana_text', 1579260, 'きのう', 2),
    ('kanji_text', 2644980, '柔らかさ', 0),
    ('kana_text', 2644980, 'やわらかさ', 0),
    ('kana_text', 2083610, 'ベタ', 0),
    ('kana_text', 2083610, 'べた', 0),
    ('kana_text', 1119610, 'ベタ', None),
    ('kana_text', 1004840, 'コロコロ', 0),
    ('kana_text', 1257040, 'ケンカ', 0),
    ('kana_text', 1633840, 'ごとき', 0),
    # aug18
    ('kana_text', 1593870, 'さらう', 0),
    ('kana_text', 2141690, 'ふざけんな', 0),
    ('kana_text', 1214770, 'かん', None),
    ('kanji_text', 1214770, '観', None),
    ('kanji_text', 2082780, '意味深', 0),
    ('kana_text', 2209180, 'とて', 0),
    ('kana_text', 1574640, 'ロバ', 0),
    # jan19
    ('kanji_text', 2017470, '塗れ', 0),
    ('kana_text', 2722660, 'すげぇ', 0),
    # apr19
    ('kanji_text', 1538750, '癒やす', 0),
    ('kanji_text', 1538750, '癒す', 0),
    ('kana_text', 1538750, 'いやす', 0),
    ('kana_text', 2147610, 'いなくなる', 0),
    ('kana_text', 1346290, 'マス', 37),
    # jan20
    ('kana_text', 1715710, 'みたところ', None),
    ('kana_text', 2841254, 'からって', None),
    ('kana_text', 2028950, 'とは', None),
    ('kanji_text', 1292400, '再開', 13),
    ('kana_text', 1292400, 'さいかい', 13),
    ('kana_text', 1306200, 'しよう', 10),
    ('kana_text', 2056930, 'つまらなさそう', 0),
    ('kanji_text', 1164710, '一段落', None),
    ('kana_text', 1570220, 'すくむ', 0),
    ('kana_text', 1352130, 'うえ', 1),
    ('kana_text', 1502390, 'もん', 0),
    ('kana_text', 2780660, 'もん', 0),
    ('kana_text', 2653620, 'がち', 0),
    ('kana_text', 2653620, 'ガチ', 0),
    ('kana_text', 1135480, 'モノ', None),
    ('kana_text', 1003000, 'カラカラ', 0),
    # apr20
    ('kana_text', 1225940, 'アリ', 0),
    ('kana_text', 1568080, 'ふくろう', 0),
    ('kana_text', 1025450, 'ウイルス', None),
    ('kana_text', 1025450, 'ウィルス', None),
    ('kana_text', 1004320, 'こうゆう', 0),
    ('kana_text', 1580290, 'おとめ', 0),
    ('kana_text', 2842087, 'パー', 0),
    # jul20
    ('kana_text', 2101130, 'し', None),
    ('kanji_text', 1982860, '代', 0),
    ('kana_text', 1367020, 'ひとけ', 0),
    ('kana_text', 1002190, 'おしり', 0),
    ('kana_text', 2085020, 'もどき', 0),
    # jan21
    ('kana_text', 2124820, 'コロナウイルス', None),
    ('kana_text', 2846738, 'なん', None),
    ('kana_text', 2083720, 'っぽい', None),
    ('kanji_text', 1012980, '遣る', None),
    # may21
    ('kana_text', 2848303, 'てか', 0),
    ('kanji_text', 1979920, '貴方', None),
    # jan22
    ('kana_text', 2008650, 'そうした', None),
    ('kana_text', 1001840, 'おにいちゃん', 0),
    ('kana_text', 1806840, 'がいそう', None),
    ('kana_text', 1639750, 'こだから', None),
    # dec23
    ('kana_text', 1625620, 'はいかん', None),
    ('kana_text', 1625610, 'はいかん', None),
    ('kana_text', 1681460, 'はいかん', None),
    ('kanji_text', 2855480, '乙女', 0),
    ('kana_text', 2855480, 'おとめ', 0),
    ('kana_text', 1930050, 'バラす', 0),
    ('kana_text', 1582460, 'ないかい', None),
    ('kana_text', 1202300, 'かいが', 0),
    ('kanji_text', 1328740, '狩る', 0),
    ('kana_text', 1009610, 'にも', 0),
    # jan25
    ('kana_text', 1001120, 'うんち', 0),
    ('kana_text', 1511600, 'かたかな', 0),
    ('kana_text', 1056400, 'サウンドトラック', 0),
    ('kana_text', 1510640, 'へん', 5),
    # jan26 - boost compound expressions to beat suffix splits
    ('kana_text', 2009070, 'でないと', 0),  # "without; but if" - beat suffix でない + と
]


# ============================================================================
# Additional UK Adjustments from Dated Errata
# ============================================================================

# Additional UK deletions from dated errata
ADDITIONAL_DELETE_UK_ENTRIES = [
    2021030,  # 摂る（とる）(feb17)
    1586730,  # 粗 (あら) (feb17)
    1441400,  # 点く （つく）(feb17)
    1303400,  # 撒く/まく (jan18)
    1434020,  # 吊る/つる (jan18)
    1196520,  # かすむ (jan18)
    1414190,  # 大人しい (jan18)
    1896380,  # 出 (mar18)
    1157000,  # 易しい (mar18)
    1576360,  # 逸れる (mar18)
    1598660,  # とかす (aug18)
    1604890,  # 目 (jan19)
    1632980,  # jan20
    1715710,  # jan20
    1426680,  # 虫 (jan21)
    1547720,  # 来る (may21)
    1495770,  # 付ける (may21)
    2611890,  # 蒔く (may21)
    2854117,  # おき (dec23)
    2859257,  # あれ (dec23)
    1198890,  # 解く (dec23)
]

# Additional UK additions from dated errata
ADDITIONAL_ADD_UK_ENTRIES = [
    (1569590, 0),  # 痙攣 けいれん (feb17)
    (1590540, 0),  # 仮名 かな (feb17)
    (1430200, 0),  # いただき (feb17)
    (1188380, 0),  # なんでもかんでも (jan18)
    (1258330, 0),  # いぬ (jan18)
    (2217330, 0),  # わい (jan18)
    (1238460, 0),  # そば (mar18)
    (1527140, 0),  # aug18
    (1208870, 0),  # かなう (aug18)
    (2756830, 0),  # jan19
    (1615340, 0),  # apr19
    (1346290, 3),  # マス (apr19)
    (1565100, 0),  # jan20
    (1219510, 0),  # apr20
    (1616370, 0),  # apr20
    (2679820, 0),  # しっぽく (jan21)
    (1590390, 0),  # かたどる (jan21)
    (1586290, 0),  # あげく (jul20)
    (1257260, 0),  # いやがらせ (jul20)
    (2217330, 0),  # ワイ (jul20)
    (1180540, 0),  # おっす (dec23)
    (2826371, 0),  # いつなりと (dec23)
]


# ============================================================================
# Additional Reading Adjustments from Dated Errata
# ============================================================================

ADDITIONAL_ADD_READINGS = [
    (1029150, 'えっち', None),  # feb17
    (1363740, 'マネ', 9),  # feb17
    (1384840, 'キレ', 0),  # jan18
    (1008370, 'デカい', 0),  # jan19
    (1572760, 'クドい', None),  # jan19
    (1003620, 'ギュっと', None),  # jan19
    (1593170, 'コケる', None),  # jan20
    (2722640, 'オケ', None),  # aug18
    (1103270, 'ぱんつ', None),  # jul20
    (1566420, 'ハメる', None),  # jan22
    (1161240, 'いっかねん', None),  # jan22
    (1089590, 'どんまい', None),  # may21
    (2081610, 'タテ', None),  # counters
]

ADDITIONAL_DELETE_READINGS = [
    (2424520, '去る者は追わず、来たる者は拒まず'),  # jan19
    (2570040, '朝焼けは雨、夕焼けは晴れ'),  # jan19
    (2833961, '梅は食うとも核食うな、中に天神寝てござる'),  # jan19
    (2834318, '二人は伴侶、三人は仲間割れ'),  # jan19
    (2834363, '墨は餓鬼に磨らせ、筆は鬼に持たせよ'),  # jan19
    (1299960, 'さんかい'),  # counters
    (2028930, 'ヶ'),  # jan25 (kana_text)
    (2028930, 'ケ'),  # jan25 (kana_text)
]


# ============================================================================
# Additional POS Adjustments from Dated Errata
# ============================================================================

ADDITIONAL_POS_DELETIONS = [
    (2122310, 'pos', 'prt'),  # え (feb17)
    (1245280, 'pos', 'adj-no'),  # 空 から (jan20)
    (1392570, 'pos', 'adj-no'),  # 前 ぜん (jan20)
    (2647210, 'pos', 'suf'),  # jan20
    (1188270, 'pos', 'pn'),  # 何か (jan22)
]

ADDITIONAL_POS_ADDITIONS = [
    (1429740, 0, 'suf'),  # 長 (jan20)
    (1429740, 1, 'n'),  # 長 (jan20)
    (1956530, 1, 'n'),  # 寸 (apr20)
    (1411570, 0, 'vs'),  # 変わり映え (jan21)
    (1188270, 0, 'n'),  # 何か (jan22)
    (1247260, 0, 'n-suf'),  # 君 くん (jan22)
]


# ============================================================================
# Misc Adjustments
# ============================================================================

# Entries to remove 'arch' (archaic) tag
DELETE_ARCH_ENTRIES = [
    (1270350, 'misc', 'arch'),  # ござる (jan19)
    (2217330, 'misc', 'arch'),  # jul20
]

# Entries to add 'obsc' (obscure) tag
ADD_OBSC_ENTRIES = [
    (2510160, 0, 'obsc'),  # 鬱ぐ (jan20)
]

# Entries to remove 'rare' tag
DELETE_RARE_ENTRIES = [
    (2826371, 'misc', 'rare'),  # いつなりと (dec23)
]


# ============================================================================
# UK (Usually Kana) Adjustments
# ============================================================================

# Entries where "uk" (usually kana) should be removed
# This prevents hiragana forms from being preferred over kanji
DELETE_UK_ENTRIES = [
    1611000,  # 生る
    1305070,  # 仕手 (して)
    1583470,  # 品 (しな)
    1446760,  # しな
    1302910,  # だし
    2802220,  # う
    1535790,  # もち
    2119750,  # なんだ
    2220330,  # つ
    1207600,  # かけ
    1399970,  # かく
    2094480,  # らい
    2729170,  # いる
    1580640,  # 人
    1569440,  # かし
    2423450,  # さし
    1578850,  # 行く
    1609500,  # 罹る
    1444150,  # 吐く
    1546640,  # 要る
    1314490,  # ことなく
    2643710,  # やす
    1611260,  # はねる
    2208960,  # かける
    1155020,  # もって
    1208240,  # かっこ
    1207590,  # かかる
    1279680,  # かまう
    1469810,  # ないし
    1474370,  # むく
    1609300,  # うたう
    1612920,  # ひく
    2827450,  # まめ
    1333570,  # たかる
    1610400,  # つける
    2097190,  # つく
]

# Entries where "uk" (usually kana) should be added
ADD_UK_ENTRIES = [
    (1394680, 0),  # そういう
    (2272830, 0),  # すごく
    (1270680, 0),  # ごめんなさい
    (1541560, 0),  # ありがたい
    (1739410, 1),  # わけない
    (1207610, 0),  # かける
    (2424410, 0),  # やつめ
    (1387080, 0),  # セミ
    (1509350, 0),  # くせ
    (1637460, 0),  # はやる
]


def apply_uk_adjustments(session: Session) -> None:
    """Apply usually-kana (uk) adjustments."""
    # Original deletions
    for seq in DELETE_UK_ENTRIES:
        delete_sense_prop(session, seq, "misc", "uk")
    
    # Additional deletions from dated errata
    for seq in ADDITIONAL_DELETE_UK_ENTRIES:
        delete_sense_prop(session, seq, "misc", "uk")
    
    # Original additions
    for seq, sense_ord in ADD_UK_ENTRIES:
        add_sense_prop(session, seq, sense_ord, "misc", "uk")
    
    # Additional additions from dated errata
    for seq, sense_ord in ADDITIONAL_ADD_UK_ENTRIES:
        add_sense_prop(session, seq, sense_ord, "misc", "uk")
    
    total_deletions = len(DELETE_UK_ENTRIES) + len(ADDITIONAL_DELETE_UK_ENTRIES)
    total_additions = len(ADD_UK_ENTRIES) + len(ADDITIONAL_ADD_UK_ENTRIES)
    logger.info(f"Applied {total_deletions} uk deletions and {total_additions} uk additions")


# ============================================================================
# Common Score Adjustments
# ============================================================================

# Format: (table, seq, text, common_value)
# None means :null in ichiran (remove common flag)
COMMON_ADJUSTMENTS = [
    ('kana_text', 1310920, 'したい', None),
    ('kana_text', 1159430, 'いたい', None),
    ('kana_text', 1523060, 'ほんと', 2),
    ('kana_text', 1577100, 'なん', 2),
    ('kana_text', 1012440, 'めく', None),
    ('kana_text', 1005600, 'しまった', None),
    ('kana_text', 2139720, 'ん', 0),
    ('kana_text', 1309910, 'してい', 0),
    ('kana_text', 1311320, 'してい', 0),
    ('kana_text', 1423310, 'なか', 1),
    ('kanji_text', 1245280, '空', 0),
    ('kana_text', 1308640, 'しない', 0),
    ('kana_text', 1579130, 'ことし', 0),
    ('kana_text', 2084660, 'いなくなった', 0),
    ('kana_text', 1570850, 'すね', None),
    ('kana_text', 1470740, 'のうち', 0),
    ('kana_text', 1156100, 'いいん', 0),
    ('kana_text', 1472480, 'はいいん', None),
    ('kana_text', 1445000, 'としん', 0),
    ('kana_text', 1408100, 'たよう', 0),
    ('kana_text', 2409180, 'ような', 0),
    ('kana_text', 1524550, 'まいそう', None),
    ('kana_text', 1925750, 'そうする', None),
    ('kana_text', 1587780, 'いる', None),
    ('kana_text', 1322180, 'いる', None),
    ('kana_text', 1391500, 'いる', None),
    ('kanji_text', 1606560, '分かる', 11),
    ('kana_text', 1606560, 'わかる', 11),
    ('kanji_text', 1547720, '来る', 11),
    ('kana_text', 1547720, 'くる', 11),
    ('kana_text', 2134680, 'それは', 0),
    ('kana_text', 2134680, 'そりゃ', 0),
    ('kana_text', 1409140, 'からだ', 0),
    ('kana_text', 1552120, 'ながす', None),
    ('kana_text', 1516930, 'ほう', 1),
    ('kana_text', 1518220, 'ほうが', None),
    ('kana_text', 1603340, 'ほうが', None),
    ('kana_text', 1158400, 'いどう', None),
    ('kana_text', 1157970, 'いどう', None),
    ('kana_text', 1599900, 'になう', None),
    ('kana_text', 1465590, 'はいる', None),
    ('kana_text', 1535930, 'とい', 0),
    ('kana_text', 1472480, 'はいらん', None),
    ('kanji_text', 2019640, '杯', 20),
    ('kana_text', 1416220, 'たち', 10),
    ('kana_text', 1402900, 'そうなん', None),
    ('kana_text', 1446980, 'いたむ', None),
    ('kana_text', 1432710, 'いたむ', None),
    ('kana_text', 1632670, 'かむ', None),
    ('kana_text', 1224090, 'きが', 40),
    ('kana_text', 1534470, 'もうこ', None),
    ('kana_text', 1739410, 'わけない', 0),
    ('kanji_text', 1416860, '誰も', 0),
    ('kana_text', 2093030, 'そっか', 0),
    ('kanji_text', 1001840, 'お兄ちゃん', 0),
    ('kanji_text', 1341350, '旬', 0),
    ('kana_text', 1188790, 'いつか', 0),
    ('kana_text', 1582900, 'もす', None),
    ('kana_text', 1577270, 'セリフ', 0),
    ('kana_text', 1375650, 'せいか', 0),
    ('kanji_text', 1363540, '真逆', None),
    ('kana_text', 1632200, 'どうか', 0),
    ('kanji_text', 1920245, '何の', 0),
    ('kana_text', 2733410, 'だよね', 0),
    ('kana_text', 1234260, 'ともに', 0),
    ('kanji_text', 2242840, '未', 0),
    ('kana_text', 1246890, 'リス', 0),
    ('kana_text', 1257270, 'やらしい', 0),
    ('kana_text', 1343100, 'とこ', 0),
    ('kana_text', 1529930, 'むこう', 14),
    ('kanji_text', 1317910, '自重', 30),
    ('kana_text', 1586420, 'あったかい', 0),
    ('kana_text', 1214190, 'かんない', None),
    ('kana_text', 1614320, 'かんない', None),
    ('kana_text', 1517220, 'ほうがい', None),
    ('kana_text', 1380990, 'せいなん', None),
    ('kana_text', 1280630, 'こうなん', None),
    ('kana_text', 1289620, 'こんなん', None),
    ('kana_text', 1204090, 'がいまい', None),
    ('kana_text', 1459170, 'ないほう', None),
    ('kana_text', 2457920, 'ですか', None),
    ('kana_text', 1228390, 'すいもの', None),
    ('kana_text', 1423240, 'きもの', 0),
    ('kana_text', 1212110, 'かんじ', 0),
    ('kana_text', 1516160, 'たから', 0),
    ('kana_text', 1575510, 'コマ', 0),
    ('kanji_text', 1603990, '街', 0),
    ('kana_text', 1548520, 'からむ', None),
    ('kana_text', 2174250, 'もしや', 0),
    ('kana_text', 1595080, 'のく', None),
    ('kana_text', 1309950, 'しどう', 0),
    ('kana_text', 1524860, 'まくら', 9),
    ('kanji_text', 1451770, '同じよう', 30),
    ('kana_text', 1244210, 'くない', 0),
    ('kana_text', 1898260, 'どうし', 11),
    ('kanji_text', 1407980, '多分', 1),
    ('kana_text', 1579630, 'なのか', None),
    ('kana_text', 1371880, 'すいてき', None),
    ('kana_text', 1008420, 'でしょ', 0),
    ('kana_text', 1928670, 'だろ', 0),
    ('kanji_text', 1000580, '彼', None),
    ('kana_text', 1546380, 'ようと', 0),
    ('kana_text', 2246510, 'なさそう', 0),
    ('kanji_text', 2246510, '無さそう', 0),
    ('kana_text', 1579110, 'きょう', 2),
    ('kana_text', 1235870, 'きょう', None),
    ('kana_text', 1587200, 'いこう', 11),
    ('kana_text', 1158240, 'いこう', 0),
    ('kana_text', 1534440, 'もうまく', None),
    ('kana_text', 1459400, 'ないよう', 0),
    ('kana_text', 1590480, 'カッコ', 0),
    ('kana_text', 1208240, 'カッコ', 0),
    ('kana_text', 1495770, 'つける', 11),
    ('kana_text', 1610400, 'つける', 12),
    ('kana_text', 1495740, 'つく', 11),
    ('kanji_text', 1495740, '付く', 11),
    # につれ - boost to prefer compound over に+つれ split
    ('kana_text', 2136050, 'につれ', 0),
    # おすすめ - boost to prefer compound over お+すすめ split
    # お(10)+すすめ(90)=91(capped) beats おすすめ(64), need common=0 for high score
    ('kana_text', 1002150, 'おすすめ', 0),
    # 百円ショップ - boost compound (seq=2100330) 
    # Need to boost both kanji and kana forms to beat counter parsing (百円 + ショップ = 353)
    ('kana_text', 2100330, 'ひゃくえんショップ', 0),
    ('kanji_text', 2100330, '百円ショップ', 0),
    # でないと - boost compound (seq=2009070) to beat でない+と split with suffixes
    ('kana_text', 2009070, 'でないと', 0),
    # 無理をする - boost compound expression (seq=2838589)
    # Need both kana and kanji forms for proper inheritance
    ('kana_text', 2838589, 'むりをする', 0),
    ('kanji_text', 2838589, '無理をする', 0),
    # 運がいい - boost compound expression (seq=1172620)
    # Need both kana and kanji forms for proper inheritance in conjugated forms
    ('kana_text', 1172620, 'うんがいい', 0),
    ('kana_text', 1172620, 'うんがよい', 0),
    ('kanji_text', 1172620, '運がいい', 0),
    ('kanji_text', 1172620, '運が良い', 0),
    ('kanji_text', 1172620, '運がよい', 0),
    # 気がする - boost compound (seq=1221540)
    # Need both kana and kanji forms
    ('kana_text', 1221540, 'きがする', 0),
    ('kanji_text', 1221540, '気がする', 0),
    # なぜ (verb - to stroke) demoted to prevent なぜそう compound from beating なぜ (why) + そう
    # seq=10195060 is the verb form that creates the unwanted compound
    ('kana_text', 10195060, 'なぜ', None),
]


def apply_common_adjustments(session: Session) -> None:
    """Apply commonness score adjustments."""
    # Original adjustments
    for table, seq, text, common in COMMON_ADJUSTMENTS:
        set_common(session, table, seq, text, common)
    
    # Additional adjustments from dated errata
    for table, seq, text, common in ADDITIONAL_COMMON_ADJUSTMENTS:
        set_common(session, table, seq, text, common)
    
    total = len(COMMON_ADJUSTMENTS) + len(ADDITIONAL_COMMON_ADJUSTMENTS)
    logger.info(f"Applied {total} common score adjustments")


# ============================================================================
# Reading Adjustments
# ============================================================================

# Readings to add: (seq, text, common)
ADD_READINGS = [
    (2015370, 'ワシ', None),
    (1202410, 'カニ', None),
    (2145800, 'イラ', None),
    (1517840, 'ハチ', None),
    (2029080, 'ねぇ', None),
    (2089020, 'じゃ', 0),  # だ -> じゃ
]

# Readings to delete: (seq, text)
DELETE_READINGS = [
    (1247250, 'キミ'),
    (1521960, 'ボツ'),
    (2145800, 'いら'),
    (2067160, 'たも'),
    (2423450, 'サシ'),
    (2574600, 'どうなん'),
]


def apply_reading_adjustments(session: Session) -> None:
    """Apply reading additions and deletions."""
    # Original additions
    for seq, text, common in ADD_READINGS:
        add_reading(session, seq, text, common)
    
    # Additional additions from dated errata
    for seq, text, common in ADDITIONAL_ADD_READINGS:
        add_reading(session, seq, text, common)
    
    # Original deletions
    for seq, text in DELETE_READINGS:
        delete_reading(session, seq, text)
    
    # Additional deletions from dated errata
    for seq, text in ADDITIONAL_DELETE_READINGS:
        delete_reading(session, seq, text)
    
    total_additions = len(ADD_READINGS) + len(ADDITIONAL_ADD_READINGS)
    total_deletions = len(DELETE_READINGS) + len(ADDITIONAL_DELETE_READINGS)
    logger.info(f"Applied {total_additions} reading additions and {total_deletions} deletions")


# ============================================================================
# POS Adjustments
# ============================================================================

def apply_pos_adjustments(session: Session) -> None:
    """Apply POS tag adjustments."""
    # Original adjustments
    # なの -> add prt POS
    add_sense_prop(session, 2425930, 0, 'pos', 'prt')
    # わね -> add prt POS
    add_sense_prop(session, 2457930, 0, 'pos', 'prt')
    # とん -> remove adv-to POS
    delete_sense_prop(session, 2629920, 'pos', 'adv-to')
    
    # Additional POS deletions from dated errata
    for seq, tag, text in ADDITIONAL_POS_DELETIONS:
        delete_sense_prop(session, seq, tag, text)
    
    # Additional POS additions from dated errata
    for seq, sense_ord, pos in ADDITIONAL_POS_ADDITIONS:
        add_sense_prop(session, seq, sense_ord, 'pos', pos)
    
    logger.info("Applied POS adjustments")


def apply_counter_pos_adjustments(session: Session) -> None:
    """Apply counter POS tag additions."""
    for seq, sense_ord, pos in COUNTER_POS_ENTRIES:
        add_sense_prop(session, seq, sense_ord, 'pos', pos)
    
    for seq, pos in DELETE_COUNTER_POS_ENTRIES:
        delete_sense_prop(session, seq, 'pos', pos)
    
    logger.info(f"Applied {len(COUNTER_POS_ENTRIES)} counter POS additions")


def apply_primary_nokanji_adjustments(session: Session) -> None:
    """Apply primary_nokanji flag adjustments."""
    for seq in PRIMARY_NOKANJI_CLEAR:
        set_primary_nokanji(session, seq, False)  # Use False instead of None (column is NOT NULL)
    
    logger.info(f"Applied {len(PRIMARY_NOKANJI_CLEAR)} primary_nokanji adjustments")


def apply_conjugation_deletions(session: Session) -> None:
    """Apply conjugation deletions."""
    for seq, from_seq in CONJUGATION_DELETIONS:
        delete_conjugation(session, seq, from_seq)
    
    logger.info(f"Applied {len(CONJUGATION_DELETIONS)} conjugation deletions")


def apply_misc_adjustments(session: Session) -> None:
    """Apply miscellaneous tag adjustments."""
    # Delete 'arch' tags
    for seq, tag, text in DELETE_ARCH_ENTRIES:
        delete_sense_prop(session, seq, tag, text)
    
    # Add 'obsc' tags
    for seq, sense_ord, text in ADD_OBSC_ENTRIES:
        add_sense_prop(session, seq, sense_ord, 'misc', text)
    
    # Delete 'rare' tags
    for seq, tag, text in DELETE_RARE_ENTRIES:
        delete_sense_prop(session, seq, tag, text)
    
    logger.info("Applied misc tag adjustments")


# ============================================================================
# Main Entry Point
# ============================================================================

def add_errata(session: Session) -> None:
    """
    Apply all errata corrections to the database.
    
    This should be called after loading JMDict and conjugations.
    Ports ichiran's add-errata function.
    """
    logger.info("Applying errata corrections...")
    
    # Custom entries (must be added first, before conjugations)
    add_custom_suru_verbs(session)
    add_synthetic_suffix_entries(session)
    
    # Conjugation-related errata
    add_gozaimasu_conjs(session)
    add_deha_ja_readings(session)
    
    # Data adjustments
    apply_uk_adjustments(session)
    apply_common_adjustments(session)
    apply_reading_adjustments(session)
    apply_pos_adjustments(session)
    apply_counter_pos_adjustments(session)
    apply_primary_nokanji_adjustments(session)
    apply_conjugation_deletions(session)
    apply_misc_adjustments(session)
    
    session.commit()
    logger.info("Errata corrections complete")
