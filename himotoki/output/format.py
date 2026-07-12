"""
Main segmentation output entry points and JSON formatting.
"""

import json
from typing import Optional, List, Dict, Any, Union

from sqlalchemy.orm import Session

from himotoki.output.types import WordInfo, WordType, SPECIAL_CONJ_INFO
from himotoki.output.word_info import fill_segment_path
from himotoki.output.meanings import (
    word_info_reading_str,
    get_senses_json,
    get_entry_reading,
    get_root_seq,
    conj_info_json,
)
from himotoki.output.conjugation_display import _get_conjugation_display

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
            # Add gloss from the main word's seq
            glosses = get_senses(session, seq)
            if glosses:
                js['gloss'] = glosses
        
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
        
        # Conjugation info (breakdown tree)
        conj_strs = _get_conjugation_display(session, wi)
        for cs in conj_strs:
            lines.append(cs)
    
    return '\n'.join(lines)
