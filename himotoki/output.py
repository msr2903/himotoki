"""
Output formatting module for himotoki.
Ports ichiran's word-info and JSON output functionality.

This module provides:
- WordInfo: Data class for word information output
- get_senses_json: Generate sense/gloss JSON output
- word_info_gloss_json: Generate complete word info JSON
- dict_segment: Main entry point for segmentation with output
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union
from enum import Enum
import json

from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from himotoki.db.models import (
    Entry, KanjiText, KanaText, Sense, Gloss, SenseProp,
    Conjugation, ConjProp, ConjSourceReading,
)
from himotoki.raw_types import RawKanaReading, RawKanjiReading
from himotoki.lookup import (
    Segment, SegmentList, WordMatch, ConjData,
    get_conj_data, find_word,
    get_conj_type_name, get_conj_neg, get_conj_fml, get_source_text,
)
from himotoki.constants import CONJ_TYPE_NAMES, get_conj_description


# ============================================================================
# Enums and Constants
# ============================================================================

class WordType(Enum):
    """Word type classification."""
    KANJI = 'kanji'
    KANA = 'kana'
    GAP = 'gap'


# Special conjugation info for entries that are standalone but represent
# conjugated forms of other entries (like です being formal non-past of だ)
# Format: seq -> (from_seq, conj_type, pos, neg, fml)
SPECIAL_CONJ_INFO: Dict[int, tuple] = {
    1628500: (2089020, 1, 'cop', False, True),  # です = non-past formal of だ
}


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class WordInfo:
    """
    Word information for output.
    Mirrors ichiran's word-info class.
    """
    type: WordType  # :kanji, :kana, or :gap
    text: str  # Surface text
    kana: Union[str, List[str]]  # Reading(s)
    
    # Optional fields
    true_text: Optional[str] = None  # Original text (for proxy text)
    seq: Optional[Union[int, List[int]]] = None  # JMdict sequence number(s)
    conjugations: Optional[Union[List[int], str]] = None  # Conjugation IDs or 'root'
    score: int = 0
    components: List['WordInfo'] = field(default_factory=list)  # For compound words (WordInfo objects)
    compound_texts: List[str] = field(default_factory=list)  # Component texts for suffix compounds
    alternative: bool = False  # True if multiple readings available
    primary: bool = True  # Is this the primary reading
    start: Optional[int] = None
    end: Optional[int] = None
    counter: Optional[List[Any]] = None  # [value, ordinal] for counter words
    skipped: int = 0  # Number of skipped alternatives
    
    # Conjugation info fields
    is_compound: bool = False  # True if this is a compound word
    conj_type: Optional[str] = None  # Human-readable conjugation type
    conj_neg: bool = False  # True if negative form
    conj_fml: bool = False  # True if formal/polite form
    source_text: Optional[str] = None  # Dictionary form for conjugated words
    
    # NEW: Meanings and POS - populated during analysis
    meanings: List[str] = field(default_factory=list)  # List of gloss strings
    pos: Optional[str] = None  # Part of speech (e.g., "[n,vs,vt]")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (for JSON serialization)."""
        return {
            'type': self.type.value.upper(),
            'text': self.text,
            'truetext': self.true_text,
            'kana': self.kana,
            'seq': self.seq,
            'conjugations': 'ROOT' if self.conjugations == 'root' else self.conjugations,
            'score': self.score,
            'components': [c.to_dict() for c in self.components] if self.components else [],
            'compound_texts': self.compound_texts,
            'alternative': self.alternative,
            'primary': self.primary,
            'start': self.start,
            'end': self.end,
            'counter': self.counter,
            'skipped': self.skipped,
            'is_compound': self.is_compound,
            'conj_type': self.conj_type,
            'conj_neg': self.conj_neg,
            'conj_fml': self.conj_fml,
            'source_text': self.source_text,
            'meanings': self.meanings,
            'pos': self.pos,
        }


# ============================================================================
# Reading Formatting
# ============================================================================

def reading_str(kanji: Optional[str], kana: str) -> str:
    """
    Format reading as 'kanji 【kana】' or just 'kana'.
    
    Args:
        kanji: Kanji text (may be None)
        kana: Kana reading
        
    Returns:
        Formatted reading string
    """
    if kanji:
        return f"{kanji} 【{kana}】"
    return kana


def get_entry_reading(session: Session, seq: int) -> str:
    """Get formatted reading for an entry by seq."""
    kanji_text = session.execute(
        select(KanjiText.text)
        .where(and_(KanjiText.seq == seq, KanjiText.ord == 0))
    ).scalars().first()
    
    kana_text = session.execute(
        select(KanaText.text)
        .where(and_(KanaText.seq == seq, KanaText.ord == 0))
    ).scalars().first()
    
    return reading_str(kanji_text, kana_text or '')


def get_kana_for_entry(session: Session, seq: int) -> str:
    """Get the primary kana reading for an entry by seq."""
    kana_text = session.execute(
        select(KanaText.text)
        .where(and_(KanaText.seq == seq, KanaText.ord == 0))
    ).scalars().first()
    
    return kana_text or ''


# ============================================================================
# Global Meanings Cache for Performance
# ============================================================================

# Global cache for meanings and POS data (persists across analyze() calls)
# Format: {seq: (meanings_list, pos_string)}
_MEANINGS_CACHE: Dict[int, tuple] = {}

# Maximum cache size to prevent unbounded memory growth
_MEANINGS_CACHE_MAX_SIZE = 50000


def get_cached_meanings(seq: int) -> Optional[tuple]:
    """Get cached meanings for a seq if available."""
    return _MEANINGS_CACHE.get(seq)


def cache_meanings(seq: int, meanings: List[str], pos: Optional[str]) -> None:
    """Cache meanings for a seq."""
    global _MEANINGS_CACHE
    # Simple LRU-ish: if cache is too large, clear half of it
    if len(_MEANINGS_CACHE) >= _MEANINGS_CACHE_MAX_SIZE:
        # Keep the most recent half (dict preserves insertion order in Python 3.7+)
        items = list(_MEANINGS_CACHE.items())
        _MEANINGS_CACHE = dict(items[len(items) // 2:])
    _MEANINGS_CACHE[seq] = (meanings, pos)


def clear_meanings_cache() -> None:
    """Clear the global meanings cache (for testing)."""
    global _MEANINGS_CACHE
    _MEANINGS_CACHE = {}


# ============================================================================
# Batch Preloading for Performance
# ============================================================================

class ReadingsCache:
    """
    Cache for batch-loaded readings to avoid repeated DB queries.
    
    This significantly improves performance by loading all needed readings
    in a single query instead of one query per word.
    """
    
    def __init__(self):
        self.kanji_readings: Dict[int, str] = {}  # seq -> primary kanji text
        self.kana_readings: Dict[int, str] = {}   # seq -> primary kana text
        self._loaded = False
    
    def preload(self, session: Session, seqs: set) -> None:
        """
        Batch load all kanji and kana readings for the given seqs.
        
        Args:
            session: Database session
            seqs: Set of seq numbers to load
        """
        if not seqs:
            return
        
        # Batch load kanji readings (ord=0 is primary)
        kanji_results = session.execute(
            select(KanjiText.seq, KanjiText.text)
            .where(and_(KanjiText.seq.in_(seqs), KanjiText.ord == 0))
        ).all()
        for seq, text in kanji_results:
            self.kanji_readings[seq] = text
        
        # Batch load kana readings (ord=0 is primary)
        kana_results = session.execute(
            select(KanaText.seq, KanaText.text)
            .where(and_(KanaText.seq.in_(seqs), KanaText.ord == 0))
        ).all()
        for seq, text in kana_results:
            self.kana_readings[seq] = text
        
        self._loaded = True
    
    def get_kanji(self, seq: int) -> Optional[str]:
        """Get cached kanji reading for seq."""
        return self.kanji_readings.get(seq)
    
    def get_kana(self, seq: int) -> str:
        """Get cached kana reading for seq."""
        return self.kana_readings.get(seq, '')
    
    def get_source_text(self, from_seq: int) -> Optional[str]:
        """Get source text (dictionary form) for a conjugation source."""
        # Prefer kanji form, fall back to kana
        kanji = self.kanji_readings.get(from_seq)
        if kanji:
            return kanji
        return self.kana_readings.get(from_seq)


def collect_seqs_from_path(path: list) -> set:
    """
    Collect all seq numbers needed from a path for batch preloading.
    
    This includes:
    - Word seqs
    - Conjugation from_seqs (for source_text lookup)
    
    Args:
        path: List of SegmentLists or Segments
        
    Returns:
        Set of seq numbers to preload
    """
    from himotoki.lookup import CompoundWord
    from himotoki.counters import CounterText
    
    seqs = set()
    
    for item in path:
        if isinstance(item, SegmentList):
            # Get seqs from all segments in the list
            for segment in item.segments:
                _collect_segment_seqs(segment, seqs)
        elif isinstance(item, Segment):
            _collect_segment_seqs(item, seqs)
    
    return seqs


def _collect_segment_seqs(segment: Segment, seqs: set) -> None:
    """Helper to collect seqs from a single segment."""
    from himotoki.lookup import CompoundWord
    from himotoki.counters import CounterText
    
    word = segment.word
    
    # Skip CounterText - they don't have entries
    if isinstance(word, CounterText):
        if word.seq:
            seqs.add(word.seq)
        return
    
    # Add word seq
    if hasattr(word, 'seq') and word.seq:
        seqs.add(word.seq)
    
    # For CompoundWords, add all component seqs
    if isinstance(word, CompoundWord):
        if word.primary and hasattr(word.primary, 'seq'):
            seqs.add(word.primary.seq)
        for w in word.words:
            if hasattr(w, 'seq') and w.seq:
                seqs.add(w.seq)
    
    # Add from_seqs from conjugation data
    conj_data = segment.info.get('conj', []) if segment.info else []
    for cd in conj_data:
        if cd.from_seq:
            seqs.add(cd.from_seq)


def word_info_reading_str(word_info: WordInfo) -> str:
    """Get formatted reading string for WordInfo."""
    if word_info.type == WordType.KANJI or word_info.counter:
        kana = word_info.kana
        if isinstance(kana, list):
            kana = '/'.join(kana)
        return reading_str(word_info.text, kana)
    return reading_str(None, word_info.text)


# ============================================================================
# Sense/Gloss Functions
# ============================================================================

def get_senses_raw(session: Session, seq: Union[int, List[int]]) -> List[Dict[str, Any]]:
    """
    Get raw sense data for an entry.
    
    Args:
        session: Database session
        seq: Entry sequence number or list of sequence numbers (for compound words)
        
    Returns:
        List of sense dicts with ord, gloss, and props
    """
    tags = ['pos', 's_inf', 'stagk', 'stagr', 'field']
    
    # Handle list of seqs (compound words) - use first seq for senses
    if isinstance(seq, list):
        if not seq:
            return []
        seq = seq[0]
    
    # Get glosses grouped by sense
    glosses_query = (
        select(Sense.ord, func.group_concat(Gloss.text, '; '))
        .join(Gloss, Gloss.sense_id == Sense.id, isouter=True)
        .where(Sense.seq == seq)
        .group_by(Sense.id)
        .order_by(Sense.ord)
    )
    glosses = session.execute(glosses_query).all()
    
    # Get properties
    props_query = (
        select(Sense.ord, SenseProp.tag, SenseProp.text)
        .join(SenseProp, SenseProp.sense_id == Sense.id)
        .where(and_(Sense.seq == seq, SenseProp.tag.in_(tags)))
        .order_by(Sense.ord, SenseProp.tag, SenseProp.ord)
    )
    props = session.execute(props_query).all()
    
    # Build sense list
    sense_list = [
        {'ord': ord_val, 'gloss': gloss or '', 'props': {}}
        for ord_val, gloss in glosses
    ]
    
    # Organize props by sense and tag
    for sord, tag, text in props:
        for sense in sense_list:
            if sense['ord'] == sord:
                if tag not in sense['props']:
                    sense['props'][tag] = []
                sense['props'][tag].append(text)
                break
    
    return sense_list


def get_senses(session: Session, seq: Union[int, List[int]]) -> List[Dict[str, Any]]:
    """
    Get senses formatted for output.
    
    Args:
        session: Database session
        seq: Entry sequence number or list (for compound words)
    
    Returns list of dicts with pos_str, gloss, and props.
    """
    result = []
    for sense in get_senses_raw(session, seq):
        props = sense['props']
        pos = props.get('pos', [])
        pos_str = f"[{','.join(pos)}]" if pos else '[]'
        result.append({
            'pos': pos_str,
            'gloss': sense['gloss'],
            'props': props,
        })
    return result


def get_senses_str(session: Session, seq: Union[int, List[int]]) -> str:
    """Get senses as formatted string.
    
    Args:
        session: Database session
        seq: Entry sequence number or list (for compound words)
    """
    lines = []
    rpos = '[]'
    
    for i, sense in enumerate(get_senses(session, seq), 1):
        pos = sense['pos']
        if pos != '[]':
            rpos = pos
        
        gloss = sense['gloss']
        props = sense['props']
        
        info = props.get('s_inf', [])
        rinf = '; '.join(info) if info else None
        
        fields = props.get('field', [])
        rfield = ','.join(fields) if fields else None
        
        parts = [f"{i}. {rpos}"]
        if rfield:
            parts.append(f"{{{rfield}}}")
        if rinf:
            parts.append(f"《{rinf}》")
        parts.append(gloss)
        
        lines.append(' '.join(parts))
    
    return '\n'.join(lines)


def get_senses_json(
    session: Session,
    seq: int,
    pos_list: Optional[List[str]] = None,
    reading: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Get senses as JSON-compatible dicts.
    
    Args:
        session: Database session
        seq: Entry sequence number
        pos_list: Filter to these POS tags
        reading: Filter to senses matching this reading
        
    Returns:
        List of sense dicts for JSON output
    """
    result = []
    rpos = '[]'
    
    for sense in get_senses(session, seq):
        pos = sense['pos']
        if pos != '[]':
            rpos = pos
        
        # POS filtering
        if pos_list:
            lpos = pos[1:-1].split(',') if pos != '[]' else []
            if not any(p in pos_list for p in lpos):
                continue
        
        gloss = sense['gloss']
        props = sense['props']
        
        js = {'pos': rpos, 'gloss': gloss}
        
        # Add field info
        fields = props.get('field', [])
        if fields:
            js['field'] = f"{{{','.join(fields)}}}"
        
        # Add sense info
        info = props.get('s_inf', [])
        if info:
            js['info'] = '; '.join(info)
        
        result.append(js)
    
    return result


# ============================================================================
# Conjugation Info Functions
# ============================================================================

# get_conj_description is now imported from himotoki.constants


def conj_prop_json(prop: ConjProp) -> Dict[str, Any]:
    """Convert conjugation property to JSON dict."""
    js = {
        'pos': prop.pos,
        'type': get_conj_description(prop.conj_type),
    }
    if prop.neg:
        js['neg'] = True
    if prop.fml:
        js['fml'] = True
    return js


def conj_info_json(
    session: Session,
    seq: int,
    conjugations: Optional[List[int]] = None,
    text: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get conjugation info as JSON.
    
    Args:
        session: Database session
        seq: Entry sequence number
        conjugations: Specific conjugation IDs to include
        text: Filter by text
        
    Returns:
        List of conjugation info dicts
    """
    result = []
    
    # Get conjugations
    query = select(Conjugation).where(Conjugation.seq == seq)
    if conjugations and conjugations != 'root':
        query = query.where(Conjugation.id.in_(conjugations))
    
    conjs = session.execute(query).scalars().all()
    
    for conj in conjs:
        # Get properties
        props = session.execute(
            select(ConjProp).where(ConjProp.conj_id == conj.id)
        ).scalars().all()
        
        if not props:
            continue
        
        js = {
            'prop': [conj_prop_json(p) for p in props],
            'reading': get_entry_reading(session, conj.from_seq),
            'gloss': get_senses_json(session, conj.from_seq),
            'readok': True,
        }
        
        result.append(js)
    
    # Check for special conj info for standalone entries that represent conjugated forms
    if not result and seq in SPECIAL_CONJ_INFO:
        from_seq, conj_type, pos, neg, fml = SPECIAL_CONJ_INFO[seq]
        js = {
            'prop': [{
                'pos': pos,
                'type': get_conj_description(conj_type),
                'neg': neg,
                'fml': fml,
            }],
            'reading': get_entry_reading(session, from_seq),
            'gloss': get_senses_json(session, from_seq),
            'readok': True,
        }
        result.append(js)
    
    return result


# ============================================================================
# WordInfo Creation Functions
# ============================================================================

def word_info_from_segment(
    session: Session,
    segment: Segment,
    cache: Optional[ReadingsCache] = None,
) -> WordInfo:
    """
    Create WordInfo from a segment.
    
    Args:
        session: Database session
        segment: Segment with word match
        cache: Optional preloaded readings cache for performance
        
    Returns:
        WordInfo object
    """
    from himotoki.lookup import CompoundWord
    from himotoki.counters import CounterText
    
    word = segment.word
    
    # Handle CounterText specially
    if isinstance(word, CounterText):
        word_type = WordType.KANJI  # Counters are typically kanji
        return WordInfo(
            type=word_type,
            text=segment.get_text(),
            kana=word.kana,
            true_text=word.text,
            seq=word.seq,
            conjugations=[],
            score=int(segment.score),
            start=segment.start,
            end=segment.end,
        )
    
    # Handle CompoundWord specially
    if isinstance(word, CompoundWord):
        word_type = WordType.KANA if word.word_type == 'kana' else WordType.KANJI
        
        # Get conjugation data from segment.info (computed by calc_score)
        # This is the authoritative source for conjugation info
        conj_data = segment.info.get('conj', []) if segment.info else []
        
        # Extract conjugation IDs from conj_data
        # Use conj_id (foreign key to Conjugation.id), not prop.id
        conjugations = None
        if conj_data:
            conj_ids = [cd.prop.conj_id if cd.prop else None for cd in conj_data]
            conj_ids = [cid for cid in conj_ids if cid is not None]
            conjugations = conj_ids if conj_ids else None
        
        # Extract conjugation info directly from conj_data
        conj_type_name = None
        conj_neg = False
        conj_fml = False
        source_text = None
        
        if conj_data:
            # Get the first conjugation data entry (primary conjugation)
            cd = conj_data[0]
            if cd.prop:
                # Get conj_type name from the mapping
                conj_type_name = CONJ_TYPE_NAMES.get(cd.prop.conj_type)
                conj_neg = bool(cd.prop.neg)
                conj_fml = bool(cd.prop.fml)
            
            # Get source_text - prefer kanji form from from_seq, fall back to src_map
            # This matches ichiran's behavior of showing the dictionary form
            if cd.from_seq:
                # Use cache if available, otherwise query DB
                if cache:
                    source_text = cache.get_source_text(cd.from_seq)
                else:
                    # Try to get kanji form first
                    kanji_text = session.execute(
                        select(KanjiText.text)
                        .where(and_(KanjiText.seq == cd.from_seq, KanjiText.ord == 0))
                    ).scalars().first()
                    if kanji_text:
                        source_text = kanji_text
                    else:
                        # Fall back to kana form
                        kana_text = session.execute(
                            select(KanaText.text)
                            .where(and_(KanaText.seq == cd.from_seq, KanaText.ord == 0))
                        ).scalars().first()
                        if kana_text:
                            source_text = kana_text
        else:
            # Fallback: get conjugation info from the CompoundWord itself
            # This handles suffix-created compounds where segment.info doesn't have conj data
            conj_info = word.get_conjugation_info(session)
            if conj_info.get('conj_type') is not None:
                conj_type_name = CONJ_TYPE_NAMES.get(conj_info['conj_type'])
                conj_neg = bool(conj_info.get('neg', False))
                conj_fml = bool(conj_info.get('fml', False))
                source_text = conj_info.get('source_text')
            
            # Also get conjugation IDs from the last word
            if word.conjugations:
                conjugations = word.conjugations
        
        # Get component texts from CompoundWord.components property
        # This returns the text of each word in the compound
        compound_texts = word.components if word.components else []
        
        return WordInfo(
            type=word_type,
            text=segment.get_text(),
            kana=word.kana,  # Use compound's full kana
            true_text=word.text,
            seq=word.seq,  # This is an int for compound words (primary's seq)
            conjugations=conjugations,
            score=int(segment.score),
            start=segment.start,
            end=segment.end,
            is_compound=True,
            compound_texts=compound_texts,
            conj_type=conj_type_name,
            conj_neg=conj_neg,
            conj_fml=conj_fml,
            source_text=source_text,
        )
    
    reading = word.reading
    
    # Determine kana reading
    # Handle both ORM objects (KanjiText/KanaText) and raw namedtuples (RawKanjiReading/RawKanaReading)
    if isinstance(reading, (KanjiText, RawKanjiReading)):
        word_type = WordType.KANJI
        # Get best kana for kanji text - try best_kana attr, then cache, then DB lookup
        kana = reading.best_kana
        if not kana:
            if cache:
                kana = cache.get_kana(word.seq)
            else:
                kana = get_kana_for_entry(session, word.seq)
    else:
        word_type = WordType.KANA
        kana = reading.text
    
    # Get conjugation data from segment.info (computed by calc_score)
    # This is the authoritative source for conjugation info
    conj_data = segment.info.get('conj', []) if segment.info else []
    
    # Extract conjugation IDs for the conjugations field
    conjugations = word.conjugations
    if conjugations is None and conj_data:
        # Use conj_id (foreign key to Conjugation.id), not prop.id
        # This matches ichiran's (conj-id (conj-data-prop cdata))
        conj_ids = [cd.prop.conj_id if cd.prop else None for cd in conj_data]
        conj_ids = [cid for cid in conj_ids if cid is not None]
        conjugations = conj_ids if conj_ids else None
    
    # Extract conjugation info directly from conj_data
    # This avoids re-querying the database and ensures we use the same data
    conj_type_name = None
    conj_neg = False
    conj_fml = False
    source_text = None
    
    if conj_data:
        # Get the first conjugation data entry (primary conjugation)
        cd = conj_data[0]
        if cd.prop:
            # Get conj_type name from the mapping
            conj_type_name = CONJ_TYPE_NAMES.get(cd.prop.conj_type)
            conj_neg = bool(cd.prop.neg)
            conj_fml = bool(cd.prop.fml)
        
        # Get source_text - prefer kanji form from from_seq, fall back to src_map
        # This matches ichiran's behavior of showing the dictionary form
        if cd.from_seq:
            # Use cache if available, otherwise query DB
            if cache:
                source_text = cache.get_source_text(cd.from_seq)
            else:
                # Try to get kanji form first
                kanji_text = session.execute(
                    select(KanjiText.text)
                    .where(and_(KanjiText.seq == cd.from_seq, KanjiText.ord == 0))
                ).scalars().first()
                if kanji_text:
                    source_text = kanji_text
                else:
                    # Fall back to kana form
                    kana_text = session.execute(
                        select(KanaText.text)
                        .where(and_(KanaText.seq == cd.from_seq, KanaText.ord == 0))
                    ).scalars().first()
                    if kana_text:
                        source_text = kana_text
    
    return WordInfo(
        type=word_type,
        text=segment.get_text(),
        kana=kana,
        true_text=word.text,
        seq=word.seq,
        conjugations=conjugations,
        score=int(segment.score),
        start=segment.start,
        end=segment.end,
        is_compound=False,
        conj_type=conj_type_name,
        conj_neg=conj_neg,
        conj_fml=conj_fml,
        source_text=source_text,
    )


def word_info_from_segment_list(
    session: Session,
    segment_list: SegmentList,
    cache: Optional[ReadingsCache] = None,
) -> WordInfo:
    """
    Create WordInfo from a segment list (multiple interpretations).
    
    Args:
        session: Database session
        segment_list: SegmentList with multiple segments
        cache: Optional preloaded readings cache for performance
        
    Returns:
        WordInfo object (possibly with alternatives)
    """
    segments = segment_list.segments
    
    if not segments:
        return WordInfo(
            type=WordType.GAP,
            text='',
            kana='',
            start=segment_list.start,
            end=segment_list.end,
        )
    
    # Create WordInfo for each segment (pass cache)
    wi_list = [word_info_from_segment(session, seg, cache) for seg in segments]
    wi1 = wi_list[0]
    max_score = wi1.score
    
    # Filter out low-scoring alternatives
    cutoff = max_score * 0.67  # SEGMENT_SCORE_CUTOFF
    wi_list = [wi for wi in wi_list if wi.score >= cutoff]
    
    matches = segment_list.matches
    
    if len(wi_list) == 1:
        wi1.skipped = matches - 1
        return wi1
    
    # Multiple alternatives
    kana_list = []
    seq_list = []
    for wi in wi_list:
        if isinstance(wi.kana, list):
            kana_list.extend(wi.kana)
        else:
            kana_list.append(wi.kana)
        if wi.seq:
            if isinstance(wi.seq, list):
                seq_list.extend(wi.seq)
            else:
                seq_list.append(wi.seq)
    
    # Remove duplicates while preserving order
    seen_kana = set()
    unique_kana = []
    for k in kana_list:
        if k not in seen_kana:
            unique_kana.append(k)
            seen_kana.add(k)
    
    return WordInfo(
        type=wi1.type,
        text=wi1.text,
        kana=unique_kana if len(unique_kana) > 1 else (unique_kana[0] if unique_kana else ''),
        seq=seq_list if len(seq_list) > 1 else (seq_list[0] if seq_list else None),
        components=wi_list,
        alternative=True,
        score=wi1.score,
        start=segment_list.start,
        end=segment_list.end,
        skipped=matches - len(wi_list),
    )


def word_info_from_text(text: str) -> WordInfo:
    """Create gap WordInfo for unmatched text."""
    return WordInfo(
        type=WordType.GAP,
        text=text,
        kana=text,
    )


# ============================================================================
# WordInfo JSON Output
# ============================================================================

def word_info_gloss_json(
    session: Session,
    word_info: WordInfo,
    root_only: bool = False,
) -> Dict[str, Any]:
    """
    Generate JSON output for WordInfo.
    
    Args:
        session: Database session
        word_info: WordInfo to convert
        root_only: If True, skip conjugation info
        
    Returns:
        Dict ready for JSON serialization
    """
    js = {
        'reading': word_info_reading_str(word_info),
        'text': word_info.text,
        'kana': word_info.kana,
    }
    
    if word_info.score:
        js['score'] = word_info.score
    
    if word_info.alternative:
        # Multiple interpretations
        js['alternative'] = [
            word_info_gloss_json(session, wi, root_only)
            for wi in word_info.components
        ]
        return js
    
    if word_info.components:
        # Compound word with component WordInfo objects
        js['compound'] = [wi.text for wi in word_info.components]
        js['components'] = [
            word_info_gloss_json(session, wi, root_only)
            for wi in word_info.components
        ]
        return js
    
    # Handle compound words that don't have component WordInfo objects
    # (e.g., from suffix-based compounds where we only have the text)
    if word_info.is_compound:
        seq = word_info.seq
        if seq:
            js['seq'] = seq
        
        # Add compound texts if available (for ichiran compatibility)
        if word_info.compound_texts:
            js['compound'] = word_info.compound_texts
        
        # Build conjugation info directly from WordInfo fields
        # (the conjugation data was already extracted in word_info_from_segment)
        if word_info.conj_type:
            conj_prop = {
                'type': word_info.conj_type,
            }
            if word_info.conj_neg:
                conj_prop['neg'] = True
            if word_info.conj_fml:
                conj_prop['fml'] = True
            
            conj_entry = {
                'prop': [conj_prop],
                'readok': True,
            }
            
            # Add source reading if available
            if word_info.source_text:
                conj_entry['reading'] = word_info.source_text
            
            js['conj'] = [conj_entry]
        
        return js
    
    if word_info.counter:
        # Counter word
        value, ordinal = word_info.counter
        js['counter'] = {'value': value, 'ordinal': ordinal}
        if word_info.seq:
            js['seq'] = word_info.seq
            gloss = get_senses_json(session, word_info.seq, pos_list=['ctr'])
            if gloss:
                js['gloss'] = gloss
        return js
    
    # Regular word
    seq = word_info.seq
    if seq:
        js['seq'] = seq
        
        if root_only or word_info.conjugations is None or word_info.conjugations == 'root':
            gloss = get_senses_json(session, seq)
            if gloss:
                js['gloss'] = gloss
        
        # Get conjugation info
        # Check for regular conjugations OR special conj info for standalone copulae
        # Note: seq can be a list for compound words, so we need to check for hashability
        has_conjugations = word_info.conjugations and word_info.conjugations != 'root'
        has_special_conj = isinstance(seq, int) and seq in SPECIAL_CONJ_INFO
        
        if seq and (has_conjugations or has_special_conj):
            conj = conj_info_json(
                session, seq,
                conjugations=word_info.conjugations if has_conjugations else None,
                text=word_info.true_text,
            )
            if conj:
                js['conj'] = conj
    
    return js


# ============================================================================
# Main Entry Points
# ============================================================================

def fill_segment_path(
    session: Session,
    text: str,
    path: List[SegmentList],
    include_meanings: bool = True,
) -> List[WordInfo]:
    """
    Fill gaps in segment path and convert to WordInfo list.
    
    Args:
        session: Database session
        text: Original text
        path: List of SegmentLists or Segments from find_best_path
        include_meanings: If True, populate meanings field (default True)
        
    Returns:
        List of WordInfo objects covering the entire text
    """
    # Batch preload all readings for performance
    # This reduces N queries to 2 queries (one for kanji, one for kana)
    seqs = collect_seqs_from_path(path)
    cache = ReadingsCache()
    cache.preload(session, seqs)
    
    result = []
    idx = 0
    
    for item in path:
        if isinstance(item, SegmentList):
            segment_list = item
            # Add gap before this segment if needed
            if segment_list.start > idx:
                gap_text = text[idx:segment_list.start]
                result.append(WordInfo(
                    type=WordType.GAP,
                    text=gap_text,
                    kana=gap_text,
                    start=idx,
                    end=segment_list.start,
                ))
            
            # Add the segment (pass cache for optimized lookups)
            result.append(word_info_from_segment_list(session, segment_list, cache))
            idx = segment_list.end
        elif isinstance(item, Segment):
            segment = item
            # Add gap before this segment if needed
            if segment.start > idx:
                gap_text = text[idx:segment.start]
                result.append(WordInfo(
                    type=WordType.GAP,
                    text=gap_text,
                    kana=gap_text,
                    start=idx,
                    end=segment.start,
                ))
            
            # Add the segment (pass cache for optimized lookups)
            result.append(word_info_from_segment(session, segment, cache))
            idx = segment.end
    
    # Add trailing gap if needed
    if idx < len(text):
        gap_text = text[idx:]
        result.append(WordInfo(
            type=WordType.GAP,
            text=gap_text,
            kana=gap_text,
            start=idx,
            end=len(text),
        ))
    
    # Populate meanings if requested
    if include_meanings:
        populate_meanings(session, result)
    
    return result


def populate_meanings(session: Session, word_infos: List[WordInfo]) -> None:
    """
    Populate meanings and pos fields for a list of WordInfo objects.
    
    Uses a global cache to avoid repeated DB queries for the same words.
    Only queries the database for seqs not already in cache.
    
    Args:
        session: Database session
        word_infos: List of WordInfo objects to populate
    """
    # Collect all seqs that need meanings, checking cache first
    seq_to_words: Dict[int, List[WordInfo]] = {}
    uncached_seqs: List[int] = []
    
    for wi in word_infos:
        if wi.seq and wi.type != WordType.GAP:
            # Handle list seqs (compound words) - use first seq
            seq = wi.seq[0] if isinstance(wi.seq, list) else wi.seq
            if seq not in seq_to_words:
                seq_to_words[seq] = []
                # Check if we already have this in cache
                cached = get_cached_meanings(seq)
                if cached is None:
                    uncached_seqs.append(seq)
            seq_to_words[seq].append(wi)
    
    if not seq_to_words:
        return
    
    # Build lookup dicts - start with empty, will populate from cache or DB
    meanings_by_seq: Dict[int, List[str]] = {}
    pos_by_seq: Dict[int, Optional[str]] = {}
    
    # Populate from cache for already-cached seqs
    for seq in seq_to_words.keys():
        cached = get_cached_meanings(seq)
        if cached is not None:
            meanings_by_seq[seq] = cached[0]
            pos_by_seq[seq] = cached[1]
    
    # Only query DB for uncached seqs
    if uncached_seqs:
        # Query all senses and glosses in one go
        senses_query = (
            select(Sense.seq, Sense.ord, func.group_concat(Gloss.text, '; '))
            .join(Gloss, Gloss.sense_id == Sense.id, isouter=True)
            .where(Sense.seq.in_(uncached_seqs))
            .group_by(Sense.id)
            .order_by(Sense.seq, Sense.ord)
        )
        senses_results = session.execute(senses_query).all()
        
        # Query POS for all uncached seqs
        pos_query = (
            select(Sense.seq, SenseProp.text)
            .join(SenseProp, SenseProp.sense_id == Sense.id)
            .where(and_(Sense.seq.in_(uncached_seqs), SenseProp.tag == 'pos', Sense.ord == 0))
            .order_by(Sense.seq, SenseProp.ord)
        )
        pos_results = session.execute(pos_query).all()
        
        # Build meanings by seq from DB results
        for seq, ord_val, gloss in senses_results:
            if seq not in meanings_by_seq:
                meanings_by_seq[seq] = []
            if gloss:
                meanings_by_seq[seq].append(gloss)
        
        # Build POS by seq from DB results
        pos_by_seq_temp: Dict[int, List[str]] = {}
        for seq, pos_text in pos_results:
            if seq not in pos_by_seq_temp:
                pos_by_seq_temp[seq] = []
            pos_by_seq_temp[seq].append(pos_text)
        
        for seq, tags in pos_by_seq_temp.items():
            pos_by_seq[seq] = f"[{','.join(tags)}]"
        
        # Cache the newly loaded data
        for seq in uncached_seqs:
            meanings = meanings_by_seq.get(seq, [])
            pos = pos_by_seq.get(seq)
            cache_meanings(seq, meanings, pos)
    
    # Populate WordInfo objects
    for seq, word_list in seq_to_words.items():
        meanings = meanings_by_seq.get(seq, [])
        pos = pos_by_seq.get(seq)
        for wi in word_list:
            wi.meanings = meanings
            wi.pos = pos


def dict_segment(
    session: Session,
    text: str,
    limit: int = 5,
) -> List[tuple]:
    """
    Segment text and return WordInfo results.
    
    This is the main entry point, equivalent to ichiran's dict-segment.
    
    Args:
        session: Database session
        text: Text to segment
        limit: Maximum number of segmentation results
        
    Returns:
        List of (word_info_list, score) tuples
    """
    from himotoki.segment import segment_text
    
    results = segment_text(session, text, limit=limit)
    
    return [
        (fill_segment_path(session, text, path), score)
        for path, score in results
    ]


def simple_segment(session: Session, text: str, limit: int = 5) -> List[WordInfo]:
    """
    Simple segmentation returning just the best path.
    
    Args:
        session: Database session
        text: Text to segment
        limit: Maximum paths to consider
        
    Returns:
        List of WordInfo for the best segmentation
    """
    results = dict_segment(session, text, limit=limit)
    if results:
        return results[0][0]
    return []


def segment_to_json(
    session: Session,
    text: str,
    limit: int = 5,
) -> List[List[Any]]:
    """
    Segment text and return ichiran-compatible JSON.
    
    This matches the output format of ichiran-cli -f.
    
    Args:
        session: Database session
        text: Text to segment
        limit: Maximum segmentation results
        
    Returns:
        JSON-compatible nested list structure
    """
    from himotoki.characters import romanize_word
    
    results = dict_segment(session, text, limit=limit)
    
    output = []
    for word_infos, score in results:
        segments = []
        for wi in word_infos:
            # [romanized, {word_info_json}, []]
            # The third element is for split info (not yet implemented)
            romanized = romanize_word(wi.kana if isinstance(wi.kana, str) else wi.kana[0] if wi.kana else wi.text)
            segment_json = word_info_gloss_json(session, wi)
            segments.append([romanized, segment_json, []])
        
        output.append([segments, score])
    
    return output


def segment_to_text(
    session: Session,
    text: str,
    limit: int = 1,
) -> str:
    """
    Segment text and return formatted text output.
    
    This matches the output format of ichiran-cli -i.
    
    Args:
        session: Database session
        text: Text to segment
        limit: Maximum segmentation results
        
    Returns:
        Formatted text output
    """
    from himotoki.characters import romanize_word
    
    results = dict_segment(session, text, limit=limit)
    
    if not results:
        return text
    
    word_infos, score = results[0]
    
    lines = []
    
    # Romanized line
    romanized_parts = []
    for wi in word_infos:
        kana = wi.kana if isinstance(wi.kana, str) else wi.kana[0] if wi.kana else wi.text
        romanized_parts.append(romanize_word(kana))
    lines.append(' '.join(romanized_parts))
    
    # Word info lines
    for wi in word_infos:
        if wi.type == WordType.GAP:
            continue
        
        lines.append('')
        
        romanized = romanize_word(wi.kana if isinstance(wi.kana, str) else wi.kana[0] if wi.kana else wi.text)
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


def format_conjugation_info(
    session: Session,
    seq: int,
    conjugations: List[int],
) -> List[str]:
    """Format conjugation info as text lines."""
    result = []
    
    query = select(Conjugation).where(Conjugation.seq == seq)
    if conjugations:
        query = query.where(Conjugation.id.in_(conjugations))
    
    conjs = session.execute(query).scalars().all()
    
    for conj in conjs:
        props = session.execute(
            select(ConjProp).where(ConjProp.conj_id == conj.id)
        ).scalars().all()
        
        for prop in props:
            neg_str = ' Negative' if prop.neg else ' Affirmative'
            fml_str = ' Formal' if prop.fml else ' Plain'
            type_desc = get_conj_description(prop.conj_type)
            
            result.append(f"[ Conjugation: [{prop.pos}] {type_desc}{neg_str}{fml_str}")
            result.append(f"  {get_entry_reading(session, conj.from_seq)} ]")
    
    return result
