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
    for seq in DELETE_UK_ENTRIES:
        delete_sense_prop(session, seq, "misc", "uk")
    
    for seq, sense_ord in ADD_UK_ENTRIES:
        add_sense_prop(session, seq, sense_ord, "misc", "uk")
    
    logger.info(f"Applied {len(DELETE_UK_ENTRIES)} uk deletions and {len(ADD_UK_ENTRIES)} uk additions")


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
]


def apply_common_adjustments(session: Session) -> None:
    """Apply commonness score adjustments."""
    for table, seq, text, common in COMMON_ADJUSTMENTS:
        set_common(session, table, seq, text, common)
    
    logger.info(f"Applied {len(COMMON_ADJUSTMENTS)} common score adjustments")


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
    for seq, text, common in ADD_READINGS:
        add_reading(session, seq, text, common)
    
    for seq, text in DELETE_READINGS:
        delete_reading(session, seq, text)
    
    logger.info(f"Applied {len(ADD_READINGS)} reading additions and {len(DELETE_READINGS)} deletions")


# ============================================================================
# POS Adjustments
# ============================================================================

def apply_pos_adjustments(session: Session) -> None:
    """Apply POS tag adjustments."""
    # なの -> add prt POS
    add_sense_prop(session, 2425930, 0, 'pos', 'prt')
    # わね -> add prt POS
    add_sense_prop(session, 2457930, 0, 'pos', 'prt')
    # とん -> remove adv-to POS
    delete_sense_prop(session, 2629920, 'pos', 'adv-to')
    
    logger.info("Applied POS adjustments")


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
    
    # Conjugation-related errata
    add_gozaimasu_conjs(session)
    add_deha_ja_readings(session)
    
    # Data adjustments
    apply_uk_adjustments(session)
    apply_common_adjustments(session)
    apply_reading_adjustments(session)
    apply_pos_adjustments(session)
    
    session.commit()
    logger.info("Errata corrections complete")
