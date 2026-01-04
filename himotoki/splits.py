"""
Split definitions module for himotoki.
Ports ichiran's dict-split.lisp split functionality.

Splits allow compound words to be scored as the sum of their parts.
For example: 一人で → 一人 + で
This helps correctly segment expressions that appear as single entries
in the dictionary but are better understood as compound phrases.

Types of splits:
1. Regular splits (*split_map*): Split during scoring
2. Segment splits (*segsplit_map*): Expand one segment into several during path finding
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Union, Any, Callable, Set
from functools import lru_cache

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from himotoki.db.models import (
    Entry, KanjiText, KanaText, Sense, SenseProp,
    Conjugation, ConjProp,
)
from himotoki.characters import is_kana, as_hiragana


# ============================================================================
# Split Result Types
# ============================================================================

@dataclass
class SplitPart:
    """A part of a split compound word."""
    reading: Any  # WordMatch or similar
    text: str
    
    def __repr__(self):
        return f"<SplitPart({self.text})>"


@dataclass
class SplitResult:
    """
    Result of splitting a word.
    
    Supports three scoring modes via modifiers:
    - Standard (no modifier): Sum of part scores + score_bonus
    - ':score': Direct score addition (score_bonus added directly)
    - ':pscore': Proportional score modification (score_bonus modifies prop_score)
    """
    parts: List[SplitPart]
    score_bonus: int
    modifiers: Set[str] = field(default_factory=set)  # ':score', ':pscore', or empty for standard
    
    def __repr__(self):
        texts = [p.text for p in self.parts]
        mod_str = f", modifiers={self.modifiers}" if self.modifiers else ""
        return f"<SplitResult({' + '.join(texts)}, bonus={self.score_bonus}{mod_str})>"


# ============================================================================
# Split Maps
# ============================================================================

# Main split map: seq -> split function
_split_map: Dict[int, Callable] = {}

# Segment split map: seq -> split function (for expanding segments)
_segsplit_map: Dict[int, Callable] = {}


def register_split(seq: int, func: Callable, is_segsplit: bool = False):
    """Register a split function for a sequence."""
    target_map = _segsplit_map if is_segsplit else _split_map
    target_map[seq] = func


# ============================================================================
# Split Definition Macros
# ============================================================================

def def_simple_split(
    seq: int,
    score: int,
    parts: List[Tuple],
    is_segsplit: bool = False,
):
    """
    Define a simple split for a word.
    
    Args:
        seq: The entry sequence number
        score: Score bonus for this split
        parts: List of (seq, length) or (seq, length, conjugated) tuples
        is_segsplit: If True, register as segment split instead
    
    Each part tuple:
        - seq: Sequence number(s) of the part
        - length: Length of this part (None for rest of string, int for fixed)
        - conjugated: If True, look up conjugated form
    """
    def split_fn(session: Session, reading: Any) -> Optional[SplitResult]:
        text = getattr(reading, 'text', str(reading))
        offset = 0
        result_parts = []
        
        for part_def in parts:
            # Parse part definition
            if len(part_def) == 2:
                part_seqs, part_length = part_def
                conjugated = False
            else:
                part_seqs, part_length, conjugated = part_def
            
            # Ensure seqs is a list
            if not isinstance(part_seqs, (list, tuple)):
                part_seqs = [part_seqs]
            
            # Calculate actual length
            if part_length is None:
                # Rest of string
                part_text = text[offset:]
            elif callable(part_length):
                actual_len = part_length(text, offset)
                if actual_len is None:
                    return None
                part_text = text[offset:offset + actual_len]
            else:
                part_text = text[offset:offset + part_length]
            
            if not part_text:
                return None
            
            # Find the word
            if conjugated:
                words = find_word_conj_of(session, part_text, *part_seqs)
            else:
                words = find_word_seq(session, part_text, *part_seqs)
            
            if not words:
                return None
            
            result_parts.append(SplitPart(reading=words[0], text=part_text))
            
            if part_length is not None:
                if callable(part_length):
                    offset += part_length(text, offset)
                else:
                    offset += part_length
        
        return SplitResult(parts=result_parts, score_bonus=score)
    
    register_split(seq, split_fn, is_segsplit)
    return split_fn


def def_de_split(seq: int, seq_a: int, score: int = 20):
    """
    Define a で split: word that ends with で.
    Common pattern: X + で where X is the main meaning.
    """
    def split_fn(session: Session, reading: Any) -> Optional[SplitResult]:
        text = getattr(reading, 'text', str(reading))
        if not text.endswith('で'):
            return None
        
        main_text = text[:-1]
        de_text = 'で'
        
        # Find main part
        main_words = find_word_seq(session, main_text, seq_a)
        if not main_words:
            return None
        
        # Find で particle
        de_words = find_word_seq(session, de_text, 2028980)
        if not de_words:
            return None
        
        return SplitResult(
            parts=[
                SplitPart(reading=main_words[0], text=main_text),
                SplitPart(reading=de_words[0], text=de_text),
            ],
            score_bonus=score
        )
    
    register_split(seq, split_fn)
    return split_fn


def def_toori_split(seq: int, seq_a: int, score: int = 50, seq_b: int = 1432930):
    """
    Define a 通り split: word + 通り.
    """
    def split_fn(session: Session, reading: Any) -> Optional[SplitResult]:
        text = getattr(reading, 'text', str(reading))
        word_type = getattr(reading, 'word_type', 'kana')
        
        # Only for kanji readings
        if word_type != 'kanji':
            return None
        
        if len(text) < 3:
            return None
        
        main_text = text[:-2]
        toori_text = text[-2:]
        
        # Find main part
        main_words = find_word_seq(session, main_text, seq_a)
        if not main_words:
            return None
        
        # Find 通り
        toori_words = find_word_seq(session, toori_text, seq_b)
        if not toori_words:
            return None
        
        return SplitResult(
            parts=[
                SplitPart(reading=main_words[0], text=main_text),
                SplitPart(reading=toori_words[0], text=toori_text),
            ],
            score_bonus=score
        )
    
    register_split(seq, split_fn)
    return split_fn


# ============================================================================
# Helper Functions
# ============================================================================

def find_word_seq(session: Session, text: str, *seqs: int) -> List[Any]:
    """Find word by text that matches specific sequences."""
    from himotoki.lookup import WordMatch
    
    table = KanaText if is_kana(text) else KanjiText
    
    results = session.execute(
        select(table).where(and_(
            table.text == text,
            table.seq.in_(seqs)
        ))
    ).scalars().all()
    
    return [WordMatch(reading=r) for r in results]


def find_word_conj_of(session: Session, text: str, *seqs: int) -> List[Any]:
    """Find word that is conjugation of specific sequences."""
    from himotoki.lookup import WordMatch
    
    table = KanaText if is_kana(text) else KanjiText
    
    # Direct match
    direct = session.execute(
        select(table).where(and_(
            table.text == text,
            table.seq.in_(seqs)
        ))
    ).scalars().all()
    
    # Conjugation match
    indirect = session.execute(
        select(table)
        .join(Conjugation, table.seq == Conjugation.seq)
        .where(and_(
            table.text == text,
            Conjugation.from_seq.in_(seqs)
        ))
    ).scalars().all()
    
    return [WordMatch(reading=r) for r in direct + indirect]


# ============================================================================
# Split Lookup Functions
# ============================================================================

def get_split(
    session: Session,
    reading: Any,
    conj_of: Optional[List[int]] = None,
) -> Optional[SplitResult]:
    """
    Get split for a reading if one exists.
    
    Args:
        session: Database session
        reading: The reading to split
        conj_of: List of sequence numbers this is conjugated from
    
    Returns:
        SplitResult if split found, None otherwise
    """
    seq = getattr(reading, 'seq', None)
    if seq is None:
        return None
    
    # Try direct match
    split_fn = _split_map.get(seq)
    if split_fn:
        result = split_fn(session, reading)
        if result and all(p.reading for p in result.parts):
            return result
    
    # Try conjugation sources
    if conj_of:
        for cseq in conj_of:
            split_fn = _split_map.get(cseq)
            if split_fn:
                result = split_fn(session, reading)
                if result and all(p.reading for p in result.parts):
                    return result
    
    return None


def get_segsplit(session: Session, segment: Any) -> Optional[Any]:
    """
    Get segment split for expanding a segment.
    
    Args:
        session: Database session
        segment: The segment to expand
    
    Returns:
        New segment with expanded compound, or None
    """
    from himotoki.lookup import Segment
    
    word = segment.word
    seq = getattr(word, 'seq', None)
    if seq is None:
        return None
    
    # Get sequence set from info
    seq_set = segment.info.get('seq_set', [])
    conj_of = seq_set[1:] if len(seq_set) > 1 else []
    
    # Try direct match
    split_fn = _segsplit_map.get(seq)
    if split_fn:
        result = split_fn(session, word)
        if result and all(p.reading for p in result.parts):
            return _create_split_segment(segment, result)
    
    # Try conjugation sources
    for cseq in conj_of:
        split_fn = _segsplit_map.get(cseq)
        if split_fn:
            result = split_fn(session, word)
            if result and all(p.reading for p in result.parts):
                return _create_split_segment(segment, result)
    
    return None


def _create_split_segment(original_segment: Any, split_result: SplitResult) -> Any:
    """Create a new segment from a split result."""
    from himotoki.lookup import Segment, CompoundWord
    
    # Create compound word from parts
    parts = [p.reading for p in split_result.parts]
    text = ''.join(p.text for p in split_result.parts)
    
    # Build kana with spaces
    kana_parts = []
    for p in split_result.parts:
        r = p.reading
        if hasattr(r, 'reading'):
            r = r.reading
        kana_parts.append(getattr(r, 'text', p.text))
    
    compound = CompoundWord(
        primary=parts[0],
        words=parts,
        text=text,
        kana=' '.join(kana_parts),
        score_mod=split_result.score_bonus,
    )
    
    # Create new segment
    new_seg = Segment(
        start=original_segment.start,
        end=original_segment.end,
        word=compound,
        text=text,
        score=original_segment.score + split_result.score_bonus,
        info=dict(original_segment.info),
    )
    
    return new_seg


# ============================================================================
# Split Definitions - Port from dict-split.lisp
# ============================================================================

def init_splits():
    """Initialize all split definitions."""
    global _split_map, _segsplit_map
    
    if _split_map:
        return  # Already initialized
    
    # ======================
    # -de expressions
    # ======================
    def_de_split(1163700, 1576150)    # 一人で
    def_de_split(1611020, 1577100)    # 何で
    def_de_split(1004800, 1628530)    # これで
    def_de_split(2810720, 1004820)    # 此れまでで
    def_de_split(1006840, 1006880)    # その上で
    def_de_split(1530610, 1530600)    # 無断で
    def_de_split(1245390, 1245290)    # 空で
    def_de_split(2719270, 1445430)    # 土足で
    def_de_split(1189420, 2416780)    # 何用で
    def_de_split(1272220, 1592990)    # 交代で
    def_de_split(1311360, 1311350)    # 私費で
    def_de_split(1368500, 1368490)    # 人前で
    def_de_split(1395670, 1395660)    # 全体で
    def_de_split(1417790, 1417780)    # 単独で
    def_de_split(1454270, 1454260)    # 道理で
    def_de_split(1479100, 1679020)    # 半眼で
    def_de_split(1510140, 1680900)    # 別封で
    def_de_split(1518550, 1529560)    # 無しで
    def_de_split(1531420, 1531410)    # 名義で
    def_de_split(1597400, 1585205)    # 力尽くで
    def_de_split(1679990, 2582460)    # 抜き足で
    def_de_split(1682060, 2085340)    # 金ずくで
    def_de_split(1736650, 1611710)    # 水入らずで
    def_de_split(1865020, 1590150)    # 陰で
    def_de_split(1878880, 2423450)    # 差しで
    def_de_split(2126220, 1802920)    # 捩じり鉢巻きで
    def_de_split(2136520, 2005870)    # もう少しで
    def_de_split(2513590, 2513650)    # 詰め開きで
    def_de_split(2771850, 2563780)    # 気にしないで
    def_de_split(2810800, 1587590)    # 今までで
    def_de_split(1343110, 1343100)    # ところで
    def_de_split(1270210, 1001640)    # お陰で
    
    # ======================
    # -通り expressions
    # ======================
    def_toori_split(1260990, 1260670)    # 元通り
    def_toori_split(1414570, 2082450)    # 大通り
    def_toori_split(1424950, 1620400)    # 中通り (ちゅう通り)
    def_toori_split(1424960, 1423310)    # 中通り (なか通り)
    def_toori_split(1820790, 1250090)    # 型通り
    def_toori_split(1489800, 1489340)    # 表通り
    def_toori_split(1523010, 1522150)    # 本通り
    def_toori_split(1808080, 1604890)    # 目通り
    def_toori_split(1368820, 1580640)    # 人通り
    def_toori_split(1550490, 1550190)    # 裏通り
    def_toori_split(1619440, 2069220)    # 素通り
    def_toori_split(1164910, 2821500, seq_b=1432920)  # 一通り
    def_toori_split(1462720, 1461140, seq_b=1432920)  # 二通り
    
    # ======================
    # ど- prefix splits
    # ======================
    _register_do_split(2142710, 1185200)   # ど下手
    _register_do_split(2803190, 1595630)   # どすけべ
    _register_do_split(2142680, 1290210)   # ど根性
    _register_do_split(2523480, 1442750)   # ど田舎
    
    # ======================
    # し- splits (する conjugations)
    # ======================
    _register_shi_split(1005700, 1156990)   # し易い
    _register_shi_split(1005830, 1370760)   # し吹く
    _register_shi_split(1157200, 2772730)   # し難い
    _register_shi_split(1157220, 1195970)   # し過ぎる
    _register_shi_split(1157230, 1284430)   # し合う
    _register_shi_split(1157280, 1370090)   # し尽す
    _register_shi_split(1157310, 1405800)   # し続ける
    _register_shi_split(1304890, 1256520)   # し兼ねる
    _register_shi_split(1304960, 1307550)   # し始める
    _register_shi_split(1305110, 1338180)   # し出す
    _register_shi_split(1305280, 1599390)   # し直す
    _register_shi_split(1305290, 1212670)   # し慣れる
    _register_shi_split(1594300, 1596510)   # し損なう
    _register_shi_split(1594310, 1406680)   # し損じる
    _register_shi_split(1594460, 1372620)   # し遂げる
    _register_shi_split(1594580, 1277100)   # し向ける
    _register_shi_split(2518250, 1332760)   # し終える
    _register_shi_split(1157240, 1600260)   # し残す
    _register_shi_split(1304820, 1207610)   # し掛ける
    _register_shi_split(2858937, 1406690)   # し損ねる
    
    # ======================
    # Complex splits
    # ======================
    
    # なくなる (無くなる)
    def split_nakunaru(session: Session, reading: Any) -> Optional[SplitResult]:
        text = getattr(reading, 'text', str(reading))
        naku = find_word_conj_of(session, text[:2], 1529520)
        naru = find_word_conj_of(session, text[2:], 1375610)
        if naku and naru:
            return SplitResult(
                parts=[
                    SplitPart(reading=naku[0], text=text[:2]),
                    SplitPart(reading=naru[0], text=text[2:]),
                ],
                score_bonus=30
            )
        return None
    register_split(1529550, split_nakunaru)
    
    # という
    def split_toiu(session: Session, reading: Any) -> Optional[SplitResult]:
        text = getattr(reading, 'text', str(reading))
        to = find_word_seq(session, 'と', 1008490)
        iu = find_word_conj_of(session, text[1:], 1587040)
        if to and iu:
            return SplitResult(
                parts=[
                    SplitPart(reading=to[0], text='と'),
                    SplitPart(reading=iu[0], text=text[1:]),
                ],
                score_bonus=20
            )
        return None
    register_split(1922760, split_toiu)
    
    # じゃない
    def split_janai(session: Session, reading: Any) -> Optional[SplitResult]:
        ja = find_word_seq(session, 'じゃ', 2089020)
        nai = find_word_conj_of(session, 'ない', 1529520)
        if ja and nai:
            return SplitResult(
                parts=[
                    SplitPart(reading=ja[0], text='じゃ'),
                    SplitPart(reading=nai[0], text='ない'),
                ],
                score_bonus=10
            )
        return None
    register_split(2755350, split_janai)
    
    # なら
    def split_nara(session: Session, reading: Any) -> Optional[SplitResult]:
        nara = find_word_conj_of(session, 'なら', 2089020)
        if nara:
            return SplitResult(
                parts=[SplitPart(reading=nara[0], text='なら')],
                score_bonus=1
            )
        return None
    register_split(1009470, split_nara)
    
    # 気がつく
    def split_kigatsuku(session: Session, reading: Any) -> Optional[SplitResult]:
        text = getattr(reading, 'text', str(reading))
        ki = find_word_seq(session, '気', 1221520)
        ga = find_word_seq(session, 'が', 2028930)
        tsuku = find_word_conj_of(session, text[2:], 1495740)
        if ki and ga and tsuku:
            return SplitResult(
                parts=[
                    SplitPart(reading=ki[0], text='気'),
                    SplitPart(reading=ga[0], text='が'),
                    SplitPart(reading=tsuku[0], text=text[2:]),
                ],
                score_bonus=100
            )
        return None
    register_split(1591050, split_kigatsuku)
    
    # 気のせい
    def split_kinosei(session: Session, reading: Any) -> Optional[SplitResult]:
        ki = find_word_seq(session, '気', 1221520)
        no = find_word_seq(session, 'の', 1469800)
        sei = find_word_seq(session, 'せい', 1610040)
        if ki and no and sei:
            return SplitResult(
                parts=[
                    SplitPart(reading=ki[0], text='気'),
                    SplitPart(reading=no[0], text='の'),
                    SplitPart(reading=sei[0], text='せい'),
                ],
                score_bonus=100
            )
        return None
    register_split(1221750, split_kinosei)
    
    # ======================
    # Segment splits
    # ======================
    
    # ところが
    def segsplit_tokoroga(session: Session, reading: Any) -> Optional[SplitResult]:
        text = getattr(reading, 'text', str(reading))
        tokoro = find_word_seq(session, text[:-1], 1343100)
        ga = find_word_seq(session, 'が', 2028930)
        if tokoro and ga:
            return SplitResult(
                parts=[
                    SplitPart(reading=tokoro[0], text=text[:-1]),
                    SplitPart(reading=ga[0], text='が'),
                ],
                score_bonus=-10
            )
        return None
    register_split(1008570, segsplit_tokoroga, is_segsplit=True)
    
    # ところで
    def segsplit_tokorode(session: Session, reading: Any) -> Optional[SplitResult]:
        text = getattr(reading, 'text', str(reading))
        tokoro = find_word_seq(session, text[:-1], 1343100)
        de = find_word_seq(session, 'で', 2028980)
        if tokoro and de:
            return SplitResult(
                parts=[
                    SplitPart(reading=tokoro[0], text=text[:-1]),
                    SplitPart(reading=de[0], text='で'),
                ],
                score_bonus=-10
            )
        return None
    register_split(1343110, segsplit_tokorode, is_segsplit=True)
    
    # とは
    def segsplit_toha(session: Session, reading: Any) -> Optional[SplitResult]:
        to = find_word_seq(session, 'と', 1008490)
        ha = find_word_seq(session, 'は', 2028920)
        if to and ha:
            return SplitResult(
                parts=[
                    SplitPart(reading=to[0], text='と'),
                    SplitPart(reading=ha[0], text='は'),
                ],
                score_bonus=-5
            )
        return None
    register_split(2028950, segsplit_toha, is_segsplit=True)
    
    # では
    def segsplit_deha(session: Session, reading: Any) -> Optional[SplitResult]:
        de = find_word_seq(session, 'で', 2028980)
        ha = find_word_seq(session, 'は', 2028920)
        if de and ha:
            return SplitResult(
                parts=[
                    SplitPart(reading=de[0], text='で'),
                    SplitPart(reading=ha[0], text='は'),
                ],
                score_bonus=-5
            )
        return None
    register_split(1008450, segsplit_deha, is_segsplit=True)
    
    # だから
    def segsplit_dakara(session: Session, reading: Any) -> Optional[SplitResult]:
        da = find_word_seq(session, 'だ', 2089020)
        kara = find_word_seq(session, 'から', 1002980)
        if da and kara:
            return SplitResult(
                parts=[
                    SplitPart(reading=da[0], text='だ'),
                    SplitPart(reading=kara[0], text='から'),
                ],
                score_bonus=-5
            )
        return None
    register_split(1007310, segsplit_dakara, is_segsplit=True)


def _register_do_split(seq: int, seq_b: int, score: int = 30):
    """Register a ど- prefix split."""
    def split_fn(session: Session, reading: Any) -> Optional[SplitResult]:
        text = getattr(reading, 'text', str(reading))
        do = find_word_seq(session, 'ど', 2252690)
        rest = find_word_seq(session, text[1:], seq_b)
        if do and rest:
            return SplitResult(
                parts=[
                    SplitPart(reading=do[0], text='ど'),
                    SplitPart(reading=rest[0], text=text[1:]),
                ],
                score_bonus=score
            )
        return None
    register_split(seq, split_fn)


def _register_shi_split(seq: int, seq_b: int, score: int = 30):
    """Register a し- (する conjugation) split."""
    def split_fn(session: Session, reading: Any) -> Optional[SplitResult]:
        text = getattr(reading, 'text', str(reading))
        shi = find_word_conj_of(session, 'し', 1157170)
        rest = find_word_conj_of(session, text[1:], seq_b)
        if shi and rest:
            return SplitResult(
                parts=[
                    SplitPart(reading=shi[0], text='し'),
                    SplitPart(reading=rest[0], text=text[1:]),
                ],
                score_bonus=score
            )
        return None
    register_split(seq, split_fn)


# Initialize on module load
init_splits()


# ============================================================================
# Compound Word Support
# ============================================================================

@dataclass
class CompoundWord:
    """
    A compound word formed by multiple parts.
    Used for split and suffix compound words.
    """
    primary: Any  # Primary word (first part or designated primary)
    words: List[Any]  # All parts
    text: str  # Full text
    kana: str  # Kana reading (may have spaces)
    score_mod: int = 0  # Score modifier
    
    @property
    def seq(self) -> List[int]:
        """Return seq as list for compound words."""
        seqs = []
        for w in self.words:
            if hasattr(w, 'seq'):
                seqs.append(w.seq)
        return seqs
    
    @property
    def word_type(self) -> str:
        """Return the word type of the primary word."""
        if hasattr(self.primary, 'word_type'):
            return self.primary.word_type
        return 'kana'
    
    @property
    def common(self) -> Optional[int]:
        """Return commonness from primary word."""
        if hasattr(self.primary, 'common'):
            return self.primary.common
        return None
