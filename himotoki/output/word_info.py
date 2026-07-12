"""
WordInfo creation from segments and path filling helpers.
"""

from typing import Optional, List, Dict, Any, Union

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from himotoki.db.models import KanjiText, KanaText
from himotoki.raw_types import RawKanaReading, RawKanjiReading
from himotoki.lookup import (
    Segment, SegmentList, WordMatch,
    get_conj_type_name, get_conj_neg, get_conj_fml, get_source_text,
    POS_WITH_CONJ_RULES,
)
from himotoki.constants import CONJ_TYPE_NAMES
from himotoki.output.types import WordType, WordInfo, SUPPRESS_CONJ_FOR_PARTICLES, SUPPRESS_CONJ_FOR_NOUNS, SUPPRESS_CONJ_FOR_VERBS
from himotoki.output.meanings import (
    ReadingsCache,
    reading_str,
    get_matching_kana_for_kanji,
    has_conjugable_pos,
    collect_seqs_from_path,
    _collect_segment_seqs,
    populate_meanings,
    _split_copula_compound_for_output,
)

def word_info_from_word_match(
    session: Session,
    word_match,
    cache: Optional[ReadingsCache] = None,
) -> WordInfo:
    """
    Create a simple WordInfo from a WordMatch object.
    Used for creating component WordInfo objects in compound words.
    
    Args:
        session: Database session
        word_match: WordMatch object from suffix/split compounds
        cache: Optional preloaded readings cache for performance
        
    Returns:
        WordInfo object with basic info (text, kana, seq, conjugations)
    """
    reading = word_match.reading
    
    # Determine word type and kana
    if word_match.word_type == 'kanji':
        word_type = WordType.KANJI
        # Get kana from best_kana or matching function
        kana = getattr(reading, 'best_kana', None)
        if not kana:
            kana = get_matching_kana_for_kanji(session, word_match.seq, reading.text)
        if not kana:
            # Last resort - use empty string
            kana = ''
    else:
        word_type = WordType.KANA
        kana = reading.text
    
    # Get conjugation info if available
    conj_type_name = None
    source_text = None
    
    # If there are conjugations, try to get the first one's info
    if word_match.conjugations and word_match.conjugations != 'root':
        conj_ids = word_match.conjugations if isinstance(word_match.conjugations, list) else [word_match.conjugations]
        if conj_ids:
            conj_id = conj_ids[0]
            # Look up conjugation info - Conjugation table, then get props
            from himotoki.db.models import Conjugation
            conj = session.query(Conjugation).filter(Conjugation.id == conj_id).first()
            if conj:
                # Get conj_type from props relationship (not directly on Conjugation)
                if conj.props:
                    prop = conj.props[0]
                    conj_type_name = CONJ_TYPE_NAMES.get(prop.conj_type)
                # Get source text from from_seq
                if conj.from_seq:
                    if cache:
                        source_text = cache.get_source_text(conj.from_seq)
                    else:
                        kanji_text = session.execute(
                            select(KanjiText.text)
                            .where(and_(KanjiText.seq == conj.from_seq, KanjiText.ord == 0))
                        ).scalars().first()
                        source_text = kanji_text
    else:
        # No conjugation data - this is a dictionary form
        # Set conj_type to "Non-past" for verbs and adjectives
        if has_conjugable_pos(session, word_match.seq):
            conj_type_name = "Non-past"
    
    return WordInfo(
        type=word_type,
        text=word_match.text,
        kana=kana,
        seq=word_match.seq,
        conjugations=word_match.conjugations if word_match.conjugations != 'root' else None,
        conj_type=conj_type_name,
        source_text=source_text,
    )


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
    from himotoki.grammar.counters import CounterText
    
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
        
        # Create component WordInfo objects from the underlying WordMatch objects
        # This provides detailed info (including POS) for each part of the compound
        component_word_infos = []
        if hasattr(word, 'words') and word.words:
            for wm in word.words:
                try:
                    comp_wi = word_info_from_word_match(session, wm, cache)
                    component_word_infos.append(comp_wi)
                except Exception:
                    # If we fail to create a component WordInfo, skip it
                    pass
        
        return WordInfo(
            type=word_type,
            text=segment.get_text(),
            kana=word.kana,  # Use compound's full kana
            true_text=word.text,
            seq=word.seq,  # This is an int for compound words (primary's seq)
            conjugations=conjugations,
            score=int(segment.score),
            components=component_word_infos,  # NEW: Component WordInfo objects
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
        # Get best kana for kanji text - try best_kana attr, then suffix matching
        kana = reading.best_kana
        if not kana:
            # Use suffix matching to get correct kana (e.g., ないで vs なくて)
            kanji_text = reading.text
            kana = get_matching_kana_for_kanji(session, word.seq, kanji_text)
    else:
        word_type = WordType.KANA
        kana = reading.text
    
    # Get conjugation data from segment.info (computed by calc_score)
    # This is the authoritative source for conjugation info
    conj_data = segment.info.get('conj', []) if segment.info else []
    
    # Suppress conjugation info for standalone particles
    # These words have their own dictionary meaning as particles, and
    # showing conjugation info (e.g., で as copula て-form) is misleading
    if word.seq in SUPPRESS_CONJ_FOR_PARTICLES:
        conj_data = []
    
    # Suppress conjugation info for nouns that have their own dictionary meaning
    # These are nominalized verb forms that became independent nouns
    if word.seq in SUPPRESS_CONJ_FOR_NOUNS:
        conj_data = []
    
    # Suppress conjugation info for verbs with their own dictionary entries
    # These might look like conjugated forms but are standalone verbs
    if word.seq in SUPPRESS_CONJ_FOR_VERBS:
        conj_data = []
    
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
    else:
        # No conjugation data - this is a dictionary form
        # Set conj_type to "Non-past" for verbs and adjectives
        if has_conjugable_pos(session, word.seq):
            conj_type_name = "Non-past"
    
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
        # Propagate conjugation info from primary alternative
        conjugations=wi1.conjugations,
        conj_type=wi1.conj_type,
        conj_neg=wi1.conj_neg,
        conj_fml=wi1.conj_fml,
        source_text=wi1.source_text,
    )


def word_info_from_text(text: str) -> WordInfo:
    """Create gap WordInfo for unmatched text."""
    return WordInfo(
        type=WordType.GAP,
        text=text,
        kana=text,
    )
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
            wi = word_info_from_segment_list(session, segment_list, cache)
            expanded = _split_copula_compound_for_output(wi)
            result.extend(expanded)
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
            wi = word_info_from_segment(session, segment, cache)
            expanded = _split_copula_compound_for_output(wi)
            result.extend(expanded)
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

