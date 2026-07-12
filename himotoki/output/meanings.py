"""
Sense/gloss lookups, meanings cache, and reading helpers.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Union

from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from himotoki.db.models import (
    Entry, KanjiText, KanaText, Sense, Gloss, SenseProp,
    Conjugation, ConjProp,
)
from himotoki.constants import get_conj_description
from himotoki.lookup import Segment, SegmentList
from himotoki.output.types import WordType, WordInfo, SPECIAL_CONJ_INFO

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


def get_matching_kana_for_kanji(session: Session, seq: int, kanji_text: str) -> str:
    """
    Get kana reading that best matches the kanji text's suffix pattern.
    
    For conjugated forms, the DB may have multiple kana readings with different
    suffixes (e.g., いわないで and いわなくて for 言わないで). We want the kana
    whose suffix matches the kanji's suffix.
    
    Args:
        session: Database session
        seq: Entry sequence number
        kanji_text: The matched kanji text (e.g., "言わないで")
    
    Returns:
        The best matching kana reading
    """
    # Get all kana readings for this entry
    kana_results = session.execute(
        select(KanaText.text, KanaText.ord)
        .where(KanaText.seq == seq)
        .order_by(KanaText.ord)
    ).all()
    
    if not kana_results:
        return ''
    
    if len(kana_results) == 1:
        return kana_results[0][0]
    
    # For multiple readings, try to match suffix patterns
    # Common confusing pairs: ないで/なくて, ないと/なくと
    # Extract the kana suffix from kanji (last few hiragana chars)
    kanji_suffix = ''
    for char in reversed(kanji_text):
        code = ord(char)
        # Hiragana: 0x3040-0x309F
        if 0x3040 <= code <= 0x309F:
            kanji_suffix = char + kanji_suffix
        else:
            break
    
    if kanji_suffix:
        # Find a kana reading that ends with the same suffix
        for kana, ord_num in kana_results:
            if kana.endswith(kanji_suffix):
                return kana
    
    # Fall back to first reading if no suffix match
    return kana_results[0][0]


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
    from himotoki.grammar.counters import CounterText
    
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
    from himotoki.grammar.counters import CounterText
    
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
    """Get formatted reading string for WordInfo.
    
    For compounds where する is absorbed, merges the kana
    (e.g., 'べんきょう しています' → 'べんきょうしています').
    """
    if word_info.type == WordType.KANJI or word_info.counter:
        kana = word_info.kana
        if isinstance(kana, list):
            kana = '/'.join(kana)
        # Merge kana when する is absorbed into a noun compound
        if word_info.is_compound and word_info.components and isinstance(kana, str):
            kana = _merge_suru_kana(word_info, kana)
        return reading_str(word_info.text, kana)
    return reading_str(None, word_info.text)


def _merge_suru_kana(word_info: WordInfo, kana: str) -> str:
    """Merge kana spaces when する is absorbed into a noun compound.
    
    When the first suffix component is する (or a conjugated form of する),
    remove the space between the noun kana and the verb kana.
    
    'べんきょう しています' → 'べんきょうしています'
    'べんきょう した' → 'べんきょうした'
    """
    if not word_info.components or len(word_info.components) < 2:
        return kana
    
    primary = word_info.components[0]
    suffix = word_info.components[1]
    
    # Only absorb plain する (not させる, される, いたす, etc.)
    # Check if primary has no conjugation (it's a noun)
    if primary.conjugations and primary.conjugations != 'root':
        return kana
    
    suffix_kana = suffix.kana if isinstance(suffix.kana, str) else (suffix.kana[0] if suffix.kana else suffix.text)
    # する or conjugated forms start with し or す
    if suffix_kana and (suffix_kana.startswith("し") or suffix_kana.startswith("す")):
        # Verify it's actually する-based by checking the kana pattern
        # Valid: する, して, した, します, しない, しました, etc.
        # Invalid: しまう (different verb), すぐ (unrelated)
        primary_kana = primary.kana if isinstance(primary.kana, str) else (primary.kana[0] if primary.kana else primary.text)
        expected_prefix = primary_kana + " " + suffix_kana[0]
        if primary_kana and kana.startswith(expected_prefix):
            return kana.replace(primary_kana + " ", primary_kana, 1)
    
    return kana


def has_conjugable_pos(session: Session, seq: int) -> bool:
    """
    Check if a word has a part-of-speech that can be conjugated.
    
    This is used to determine if a dictionary form should have conj_type="Non-past".
    Only returns True for verbs and i-adjectives which have true conjugation forms.
    
    Args:
        session: Database session
        seq: Entry sequence number
        
    Returns:
        True if the word has a conjugable POS (verb or i-adjective)
    """
    if seq is None:
        return False
    
    # Parts of speech that should show "Non-past" for dictionary forms
    # This is more restrictive than POS_WITH_CONJ_RULES because we only want
    # verbs and i-adjectives that have true conjugated forms.
    # Excludes: 
    #   - adj-na, adj-no (which use copula for conjugation)
    #   - vs (verbal nouns that take する - the noun part doesn't conjugate)
    NONPAST_POS = frozenset([
        'v1', 'v1-s', 'v1s', 'v5aru', 'v5b', 'v5g', 'v5k', 'v5k-s', 'v5m', 'v5n',
        'v5r', 'v5r-i', 'v5s', 'v5t', 'v5u', 'v5u-s', 'v5uru', 'vk',
        'vs-i', 'vs-s', 'vz', 'adj-i', 'adj-ix',
        'cop', 'cop-da', 'aux-v',  # Copula and auxiliary verbs
    ])
    
    # Query for POS tags
    pos_results = session.execute(
        select(SenseProp.text)
        .join(Sense, SenseProp.sense_id == Sense.id)
        .where(and_(
            Sense.seq == seq,
            SenseProp.tag == 'pos',
        ))
    ).scalars().all()
    
    # Check if any POS is in the conjugable set
    for pos in pos_results:
        if pos in NONPAST_POS:
            return True
    
    return False
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


def get_root_seq(session: Session, seq: int) -> Optional[int]:
    """Get the root (dictionary form) seq for a conjugated entry.
    
    Walks the conjugation table to find the from_seq (root entry).
    Returns None if no conjugation data found.
    """
    conjs = session.execute(
        select(Conjugation).where(Conjugation.seq == seq)
    ).scalars().all()
    if conjs:
        return conjs[0].from_seq
    return None


def get_senses_str(session: Session, seq: Union[int, List[int]]) -> str:
    """Get senses as formatted string.
    
    If the entry has no senses (e.g., a conjugation-only entry),
    returns an empty string.
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

def _split_copula_compound_for_output(wi: WordInfo) -> List[WordInfo]:
    """Split na-adjective/noun + copula compounds for display output.

    Keeps internal parsing/scoring behavior unchanged while presenting
    user-facing output as separate tokens (e.g., 綺麗 + です + ね).
    """
    if not wi.is_compound or not wi.components or len(wi.components) != 2:
        return [wi]

    primary, suffix = wi.components
    suffix_kana = suffix.kana if isinstance(suffix.kana, str) else (suffix.kana[0] if suffix.kana else suffix.text)
    if suffix_kana not in ('です', 'でした'):
        return [wi]

    # Only split when primary itself is not conjugated (noun/na-adj style usage)
    if primary.conjugations and primary.conjugations != 'root':
        return [wi]

    return [primary, suffix]


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

