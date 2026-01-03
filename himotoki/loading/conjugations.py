"""
Conjugation loading and generation for himotoki.
Ports ichiran's conjugation system from dict-load.lisp.

Uses CSV files from JMdictDB:
- kwpos.csv: Part of speech definitions
- conj.csv: Conjugation type descriptions
- conjo.csv: Conjugation rules
"""

from typing import Optional, List, Dict, Tuple, Any, Set
from dataclasses import dataclass
from pathlib import Path
import csv
import logging
import multiprocessing as mp
from functools import partial

from himotoki.db.connection import session_scope
from himotoki.db.models import (
    Entry, KanjiText, KanaText, SenseProp,
    Conjugation, ConjProp, ConjSourceReading, RestrictedReading
)

logger = logging.getLogger(__name__)


# Default path for JMdictDB CSV files
DEFAULT_DATA_PATH = Path(__file__).parent.parent.parent / "data"


# Cached data from CSV files
_pos_index: Optional[Dict[str, Tuple[int, str]]] = None
_pos_by_index: Optional[Dict[int, str]] = None
_conj_descriptions: Optional[Dict[int, str]] = None
_conj_rules: Optional[Dict[int, List['ConjugationRule']]] = None


@dataclass
class ConjugationRule:
    """
    Represents a conjugation rule from conjo.csv.
    Equivalent to ichiran's conjugation-rule struct.
    """
    pos: int        # Part of speech ID
    conj: int       # Conjugation type ID
    neg: bool       # Negative form
    fml: bool       # Formal/polite form
    onum: int       # Order number (for multiple rules per conjugation)
    stem: int       # Number of characters to remove from stem
    okuri: str      # Okurigana to add
    euphr: str      # Euphonic change for hiragana
    euphk: str      # Euphonic change for kanji
    
    # Added for reference
    pos2: Optional[str] = None  # Secondary POS (not used much)


# Parts of speech that have conjugation rules
# Note: JMdict uses "cop" (not "cop-da") for copula since ~2023
POS_WITH_CONJ_RULES = [
    "adj-i", "adj-ix", "cop", "v1", "v1-s", "v5aru",
    "v5b", "v5g", "v5k", "v5k-s", "v5m", "v5n", "v5r", "v5r-i", "v5s",
    "v5t", "v5u", "v5u-s", "vk", "vs-s", "vs-i"
]

# Parts of speech that should not be conjugated
DO_NOT_CONJUGATE_POS = ["n", "vs", "adj-na"]

# Specific sequences to not conjugate
DO_NOT_CONJUGATE_SEQ = [2765070, 2835284]

# Conjugation types that trigger secondary conjugation
# These are forms that can be further conjugated (e.g., causative, passive)
SECONDARY_CONJUGATION_TYPES_FROM = [5, 6, 7, 8, 14]  # 14 is causative-su

# Secondary conjugation types to generate
SECONDARY_CONJUGATION_TYPES = [2, 3, 4, 9, 10, 11, 12, 13]

# Conjugation type ID for causative-su
CONJ_CAUSATIVE_SU = 14


def get_data_path() -> Path:
    """Get path to data directory containing CSV files."""
    return DEFAULT_DATA_PATH


def load_pos_index(csv_path: Optional[Path] = None) -> Dict[str, Tuple[int, str]]:
    """
    Load part of speech index from kwpos.csv.
    Maps POS name to (id, description).
    
    Equivalent to ichiran's *pos-index*.
    """
    global _pos_index, _pos_by_index
    
    if csv_path is None:
        csv_path = get_data_path() / "kwpos.csv"
    
    _pos_index = {}
    _pos_by_index = {}
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        next(reader)  # Skip header
        
        for row in reader:
            if len(row) >= 3:
                pos_id = int(row[0])
                pos = row[1]
                description = row[2]
                _pos_index[pos] = (pos_id, description)
                _pos_by_index[pos_id] = pos
    
    return _pos_index


def get_pos_index(pos: str) -> Optional[int]:
    """Get POS ID for a POS name."""
    global _pos_index
    if _pos_index is None:
        load_pos_index()
    entry = _pos_index.get(pos)
    return entry[0] if entry else None


def get_pos_by_index(pos_id: int) -> Optional[str]:
    """Get POS name for a POS ID."""
    global _pos_by_index
    if _pos_by_index is None:
        load_pos_index()
    return _pos_by_index.get(pos_id)


def load_conj_descriptions(csv_path: Optional[Path] = None) -> Dict[int, str]:
    """
    Load conjugation descriptions from conj.csv.
    Maps conjugation type ID to description.
    
    Equivalent to ichiran's *conj-description*.
    """
    global _conj_descriptions
    
    if csv_path is None:
        csv_path = get_data_path() / "conj.csv"
    
    _conj_descriptions = {}
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        next(reader)  # Skip header
        
        for row in reader:
            if len(row) >= 2:
                conj_id = int(row[0])
                description = row[1]
                _conj_descriptions[conj_id] = description
    
    return _conj_descriptions


def get_conj_description(conj_id: int) -> Optional[str]:
    """Get description for a conjugation type."""
    global _conj_descriptions
    if _conj_descriptions is None:
        load_conj_descriptions()
    return _conj_descriptions.get(conj_id)


def load_conj_rules(csv_path: Optional[Path] = None) -> Dict[int, List[ConjugationRule]]:
    """
    Load conjugation rules from conjo.csv.
    Maps POS ID to list of ConjugationRule.
    
    Equivalent to ichiran's *conj-rules*.
    """
    global _conj_rules
    
    if csv_path is None:
        csv_path = get_data_path() / "conjo.csv"
    
    _conj_rules = {}
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        next(reader)  # Skip header
        
        for row in reader:
            if len(row) >= 9:
                pos_id = int(row[0])
                conj_id = int(row[1])
                neg = row[2].lower() == 't' or row[2] == 'true'
                fml = row[3].lower() == 't' or row[3] == 'true'
                onum = int(row[4])
                stem = int(row[5])
                okuri = row[6]
                euphr = row[7]
                euphk = row[8]
                pos2 = row[9] if len(row) > 9 else None
                
                rule = ConjugationRule(
                    pos=pos_id,
                    conj=conj_id,
                    neg=neg,
                    fml=fml,
                    onum=onum,
                    stem=stem,
                    okuri=okuri,
                    euphr=euphr,
                    euphk=euphk,
                    pos2=pos2
                )
                
                if pos_id not in _conj_rules:
                    _conj_rules[pos_id] = []
                _conj_rules[pos_id].append(rule)
    
    return _conj_rules


def get_conj_rules(pos_id: int) -> List[ConjugationRule]:
    """Get conjugation rules for a POS ID."""
    global _conj_rules
    if _conj_rules is None:
        load_conj_rules()
    return _conj_rules.get(pos_id, [])


def is_kana(text: str) -> bool:
    """
    Check if text is entirely kana (hiragana/katakana).
    Equivalent to ichiran's (test-word ... :kana) for the last 2 chars.
    """
    if not text:
        return False
    # Check all characters to determine if word is kana-only
    check_text = text
    for char in check_text:
        code = ord(char)
        # Hiragana: 0x3040-0x309F, Katakana: 0x30A0-0x30FF
        if not (0x3040 <= code <= 0x309F or 0x30A0 <= code <= 0x30FF):
            return False
    return True


def construct_conjugation(word: str, rule: ConjugationRule) -> str:
    """
    Apply a conjugation rule to a word to produce the conjugated form.
    
    Equivalent to ichiran's construct-conjugation function.
    
    Args:
        word: Base form of the word
        rule: Conjugation rule to apply
    
    Returns:
        Conjugated form of the word
    """
    # Determine if word is kana-only
    iskana = is_kana(word)
    
    # Get euphonic changes
    euphr = rule.euphr
    euphk = rule.euphk
    
    # Calculate stem length to remove
    stem = rule.stem
    if iskana and euphr:
        stem += 1
    elif not iskana and euphk:
        stem += 1
    
    # Build conjugated form
    base = word[:-stem] if stem > 0 else word
    euph = euphr if iskana else euphk
    
    return base + euph + rule.okuri


def conjugate_word(word: str, pos: str) -> List[Tuple[ConjugationRule, str]]:
    """
    Get all conjugations for a word with given POS.
    
    Args:
        word: Base form of the word
        pos: Part of speech name
    
    Returns:
        List of (rule, conjugated_form) tuples
    """
    pos_id = get_pos_index(pos)
    if pos_id is None:
        return []
    
    rules = get_conj_rules(pos_id)
    return [(rule, construct_conjugation(word, rule)) for rule in rules]


def get_conjugatable_readings(session, seq: int) -> List[Tuple[str, int, int]]:
    """
    Get readings that can be conjugated for an entry.
    
    Returns:
        List of (text, ord, kanji_flag) tuples
        kanji_flag: 1 for kanji readings, 0 for kana
    """
    # Get kanji readings marked for conjugation
    kanji_readings = session.query(
        KanjiText.text, KanjiText.ord
    ).filter(
        KanjiText.seq == seq,
        KanjiText.conjugate_p == True
    ).all()
    
    # Get kana readings marked for conjugation
    kana_readings = session.query(
        KanaText.text, KanaText.ord
    ).filter(
        KanaText.seq == seq,
        KanaText.conjugate_p == True
    ).all()
    
    result = []
    for text, ord_num in kanji_readings:
        result.append((text, ord_num, 1))
    for text, ord_num in kana_readings:
        result.append((text, ord_num, 0))
    
    return result


def conjugate_entry_inner(
    session,
    seq: int,
    conj_types: Optional[List[int]] = None,
    as_posi: Optional[List[str]] = None
) -> Dict[Tuple[int, int], List]:
    """
    Generate conjugation matrix for an entry.
    
    Equivalent to ichiran's conjugate-entry-inner function.
    
    Args:
        session: Database session
        seq: Entry sequence number
        conj_types: Optional list of conjugation types to generate
        as_posi: Optional POS list to use instead of querying
    
    Returns:
        Dictionary mapping (pos_id, conj_id) to 2x2 matrix of readings
        Matrix indexing: [neg][fml] where neg/fml are 0/1
    """
    # Get POS list for entry
    if as_posi:
        posi = as_posi
    else:
        posi = session.query(SenseProp.text).filter(
            SenseProp.tag == 'pos',
            SenseProp.seq == seq
        ).distinct().all()
        posi = [p[0] for p in posi]
    
    # Get readings
    readings = get_conjugatable_readings(session, seq)
    if not readings:
        # Fall back to all readings if none marked for conjugation
        kanji = session.query(KanjiText).filter(KanjiText.seq == seq).all()
        kana = session.query(KanaText).filter(KanaText.seq == seq).all()
        readings = [(k.text, k.ord, 1) for k in kanji] + [(k.text, k.ord, 0) for k in kana]
    
    conj_matrix = {}  # (pos_id, conj_id) -> [[[], []], [[], []]] (neg x fml)
    
    for pos in posi:
        if pos in DO_NOT_CONJUGATE_POS:
            continue
        
        pos_id = get_pos_index(pos)
        if pos_id is None:
            continue
        
        rules = get_conj_rules(pos_id)
        if not rules:
            continue
        
        for text, ord_num, kanji_flag in readings:
            for rule in rules:
                conj_id = rule.conj
                
                # Filter by conjugation types if specified
                if conj_types and conj_id not in conj_types:
                    continue
                
                key = (pos_id, conj_id)
                if key not in conj_matrix:
                    # Create 2x2 matrix: [neg=0/1][fml=0/1]
                    conj_matrix[key] = [[[], []], [[], []]]
                
                conj_text = construct_conjugation(text, rule)
                
                # Add to appropriate cell
                neg_idx = 1 if rule.neg else 0
                fml_idx = 1 if rule.fml else 0
                conj_matrix[key][neg_idx][fml_idx].append(
                    (conj_text, kanji_flag, text, ord_num, rule.onum)
                )
    
    return conj_matrix


def get_all_readings(session, seq: int) -> Set[str]:
    """Get all reading texts for an entry."""
    kanji = session.query(KanjiText.text).filter(KanjiText.seq == seq).all()
    kana = session.query(KanaText.text).filter(KanaText.seq == seq).all()
    return set([k[0] for k in kanji] + [k[0] for k in kana])


def lex_compare(items: List, key_func=lambda x: x) -> List:
    """Sort items lexicographically by key."""
    return sorted(items, key=lambda x: key_func(x))


def insert_conjugation(
    session,
    readings: List[Tuple],
    seq: int,
    from_seq: int,
    pos: str,
    conj_type: int,
    neg: Optional[bool],
    fml: Optional[bool],
    via: Optional[int] = None
) -> bool:
    """
    Insert conjugation records into database.
    
    Equivalent to ichiran's insert-conjugation function.
    
    Args:
        session: Database session
        readings: List of (conj_text, kanji_flag, orig_reading, ord, onum) tuples
        seq: Sequence number for conjugated entry
        from_seq: Source entry sequence number
        pos: Part of speech name
        conj_type: Conjugation type ID
        neg: Negative flag (None for :null)
        fml: Formal flag (None for :null)
        via: Intermediate entry sequence (for secondary conjugations)
    
    Returns:
        True if new entry was created, False otherwise
    """
    # Sort readings and extract source reading pairs
    readings = lex_compare(readings, key_func=lambda x: (x[3], x[4]))
    
    source_readings = []
    kanji_readings = []
    kana_readings = []
    
    for conj_text, kanji_flag, orig_reading, _, _ in readings:
        source_readings.append((conj_text, orig_reading))
        if kanji_flag == 1:
            kanji_readings.append(conj_text)
        else:
            kana_readings.append(conj_text)
    
    if not kana_readings:
        return False
    
    # Remove duplicates
    kanji_readings = list(dict.fromkeys(kanji_readings))
    kana_readings = list(dict.fromkeys(kana_readings))
    
    # Check if entry already exists with these readings
    original_readings = get_all_readings(session, from_seq)
    if via:
        original_readings |= get_all_readings(session, via)
    
    # Find candidate sequences with matching readings
    seq_candidates = []
    # This is a simplified version - full implementation would do the complex SQL query
    # For now, we check if any existing entry has all these readings
    
    # Check for existing conjugated entry
    if from_seq in seq_candidates or (via and via in seq_candidates):
        return False
    
    # Create new entry if needed
    existing_entry = session.query(Entry).filter(Entry.seq == seq).first()
    if not existing_entry:
        # Create entry for conjugated form
        entry = Entry(seq=seq, content="", root_p=False)
        session.add(entry)
        
        # Determine if this conjugation produces further conjugatable forms
        conjugate_p = conj_type in SECONDARY_CONJUGATION_TYPES_FROM
        
        # Add kanji readings
        for ord_num, text in enumerate(kanji_readings):
            kanji = KanjiText(
                seq=seq,
                text=text,
                ord=ord_num,
                common=None,
                conjugate_p=conjugate_p
            )
            session.add(kanji)
        
        # Add kana readings
        for ord_num, text in enumerate(kana_readings):
            kana = KanaText(
                seq=seq,
                text=text,
                ord=ord_num,
                common=None,
                conjugate_p=conjugate_p
            )
            session.add(kana)
    
    # Find or create conjugation record
    conj_query = session.query(Conjugation).filter(
        Conjugation.from_seq == from_seq,
        Conjugation.seq == seq
    )
    if via:
        conj_query = conj_query.filter(Conjugation.via == via)
    else:
        conj_query = conj_query.filter(Conjugation.via.is_(None))
    
    conj = conj_query.first()
    if not conj:
        conj = Conjugation(seq=seq, from_seq=from_seq, via=via)
        session.add(conj)
        session.flush()
    
    # Add conjugation property
    existing_prop = session.query(ConjProp).filter(
        ConjProp.conj_id == conj.id,
        ConjProp.conj_type == conj_type,
        ConjProp.pos == pos,
        ConjProp.neg == neg,
        ConjProp.fml == fml
    ).first()
    
    if not existing_prop:
        prop = ConjProp(
            conj_id=conj.id,
            conj_type=conj_type,
            pos=pos,
            neg=neg,
            fml=fml
        )
        session.add(prop)
    
    # Add source readings
    source_readings = list(dict.fromkeys(source_readings))  # Remove duplicates
    for text, source_text in source_readings:
        existing_sr = session.query(ConjSourceReading).filter(
            ConjSourceReading.conj_id == conj.id,
            ConjSourceReading.text == text,
            ConjSourceReading.source_text == source_text
        ).first()
        
        if not existing_sr:
            sr = ConjSourceReading(
                conj_id=conj.id,
                text=text,
                source_text=source_text
            )
            session.add(sr)
    
    return not existing_entry


def get_next_seq(session) -> int:
    """Get next available sequence number."""
    from sqlalchemy import func
    result = session.query(func.max(Entry.seq)).scalar()
    return (result or 0) + 1


# Global counter for fast sequence allocation during loading
_next_seq_counter: int = 0


def _prefetch_entry_data(session, seqs: List[int]) -> Dict[int, Dict]:
    """
    Pre-fetch all data needed for conjugation in a single batch.
    Returns dict mapping seq -> {posi, readings, all_readings}
    """
    # Fetch POS for all entries
    pos_rows = session.query(SenseProp.seq, SenseProp.text).filter(
        SenseProp.tag == 'pos',
        SenseProp.seq.in_(seqs)
    ).all()
    
    pos_by_seq = {}
    for seq, text in pos_rows:
        if seq not in pos_by_seq:
            pos_by_seq[seq] = set()
        pos_by_seq[seq].add(text)
    
    # Fetch conjugatable kanji readings
    kanji_rows = session.query(
        KanjiText.seq, KanjiText.text, KanjiText.ord, KanjiText.conjugate_p
    ).filter(KanjiText.seq.in_(seqs)).all()
    
    # Fetch conjugatable kana readings
    kana_rows = session.query(
        KanaText.seq, KanaText.text, KanaText.ord, KanaText.conjugate_p
    ).filter(KanaText.seq.in_(seqs)).all()
    
    # Build entry data dict
    entry_data = {seq: {'posi': list(pos_by_seq.get(seq, [])), 'readings': [], 'all_readings': set()} for seq in seqs}
    
    for seq, text, ord_num, conjugate_p in kanji_rows:
        entry_data[seq]['all_readings'].add(text)
        if conjugate_p:
            entry_data[seq]['readings'].append((text, ord_num, 1))
    
    for seq, text, ord_num, conjugate_p in kana_rows:
        entry_data[seq]['all_readings'].add(text)
        if conjugate_p:
            entry_data[seq]['readings'].append((text, ord_num, 0))
    
    # Fallback: if no conjugatable readings, use all readings
    for seq in seqs:
        if not entry_data[seq]['readings']:
            # Use all readings as fallback
            for s, text, ord_num, _ in kanji_rows:
                if s == seq:
                    entry_data[seq]['readings'].append((text, ord_num, 1))
            for s, text, ord_num, _ in kana_rows:
                if s == seq:
                    entry_data[seq]['readings'].append((text, ord_num, 0))
    
    return entry_data


def _generate_conjugations_for_entry(seq: int, entry_data: Dict, pos_index: Dict, conj_rules: Dict) -> List[Dict]:
    """
    Generate conjugation data for a single entry (pure computation, no DB).
    Returns list of conjugation dicts ready for insertion.
    """
    data = entry_data.get(seq)
    if not data:
        return []
    
    posi = data['posi']
    readings = data['readings']
    original_readings = data['all_readings']
    
    if not readings:
        return []
    
    conj_matrix = {}  # (pos_id, conj_id) -> [[[], []], [[], []]]
    
    for pos in posi:
        if pos in DO_NOT_CONJUGATE_POS:
            continue
        
        entry = pos_index.get(pos)
        pos_id = entry[0] if entry else None
        if pos_id is None:
            continue
        
        rules = conj_rules.get(pos_id, [])
        if not rules:
            continue
        
        for text, ord_num, kanji_flag in readings:
            for rule in rules:
                conj_id = rule.conj
                key = (pos_id, conj_id)
                if key not in conj_matrix:
                    conj_matrix[key] = [[[], []], [[], []]]
                
                conj_text = construct_conjugation(text, rule)
                neg_idx = 1 if rule.neg else 0
                fml_idx = 1 if rule.fml else 0
                conj_matrix[key][neg_idx][fml_idx].append(
                    (conj_text, kanji_flag, text, ord_num, rule.onum)
                )
    
    # Convert matrix to insertion data
    results = []
    for (pos_id, conj_id), matrix in conj_matrix.items():
        has_neg = bool(matrix[1][0] or matrix[1][1])
        has_fml = bool(matrix[0][1] or matrix[1][1])
        
        pos_entry = None
        for p, (pid, _) in pos_index.items():
            if pid == pos_id:
                pos_entry = p
                break
        if not pos_entry:
            continue
        
        for ii in range(4):
            neg = ii >= 2
            fml = ii % 2 == 1
            
            readings_list = matrix[1 if neg else 0][1 if fml else 0]
            readings_list = [r for r in readings_list if r[0] not in original_readings]
            
            if not readings_list:
                continue
            
            results.append({
                'from_seq': seq,
                'pos': pos_entry,
                'conj_type': conj_id,
                'neg': None if not has_neg else neg,
                'fml': None if not has_fml else fml,
                'readings': readings_list,
            })
    
    return results


def _worker_generate_batch(args):
    """
    Worker function to generate conjugations for a batch of entries.
    """
    batch_seqs, entry_data, pos_index, conj_rules_data = args
    
    # Reconstruct ConjugationRule objects from serialized data
    conj_rules = {}
    for pos_id, rules_data in conj_rules_data.items():
        conj_rules[pos_id] = [
            ConjugationRule(
                pos=r['pos'], conj=r['conj'], neg=r['neg'], fml=r['fml'],
                onum=r['onum'], stem=r['stem'], okuri=r['okuri'],
                euphr=r['euphr'], euphk=r['euphk'], pos2=r['pos2']
            ) for r in rules_data
        ]
    
    results = []
    for seq in batch_seqs:
        entry_results = _generate_conjugations_for_entry(seq, entry_data, pos_index, conj_rules)
        results.extend(entry_results)
    return results


def _generate_secondary_conjugations_for_entry(
    seq_from: int, via_seq: int, posi: List[str], conj_types: List[int],
    entry_data: Dict, pos_index: Dict, conj_rules: Dict
) -> List[Dict]:
    """
    Generate secondary conjugation data for a single entry (pure computation, no DB).
    """
    data = entry_data.get(via_seq)
    if not data:
        return []
    
    readings = data['readings']
    original_readings = data['all_readings']
    
    if not readings:
        return []
    
    conj_matrix = {}
    
    for pos in posi:
        if pos in DO_NOT_CONJUGATE_POS:
            continue
        
        entry = pos_index.get(pos)
        pos_id = entry[0] if entry else None
        if pos_id is None:
            continue
        
        rules = conj_rules.get(pos_id, [])
        if not rules:
            continue
        
        for text, ord_num, kanji_flag in readings:
            for rule in rules:
                conj_id = rule.conj
                
                # Filter by allowed conj_types for secondary
                if conj_types and conj_id not in conj_types:
                    continue
                
                key = (pos_id, conj_id)
                if key not in conj_matrix:
                    conj_matrix[key] = [[[], []], [[], []]]
                
                conj_text = construct_conjugation(text, rule)
                neg_idx = 1 if rule.neg else 0
                fml_idx = 1 if rule.fml else 0
                conj_matrix[key][neg_idx][fml_idx].append(
                    (conj_text, kanji_flag, text, ord_num, rule.onum)
                )
    
    results = []
    for (pos_id, conj_id), matrix in conj_matrix.items():
        has_neg = bool(matrix[1][0] or matrix[1][1])
        has_fml = bool(matrix[0][1] or matrix[1][1])
        
        pos_entry = None
        for p, (pid, _) in pos_index.items():
            if pid == pos_id:
                pos_entry = p
                break
        if not pos_entry:
            continue
        
        for ii in range(4):
            neg = ii >= 2
            fml = ii % 2 == 1
            
            readings_list = matrix[1 if neg else 0][1 if fml else 0]
            readings_list = [r for r in readings_list if r[0] not in original_readings]
            
            if not readings_list:
                continue
            
            results.append({
                'from_seq': seq_from,
                'via': via_seq,
                'pos': pos_entry,
                'conj_type': conj_id,
                'neg': None if not has_neg else neg,
                'fml': None if not has_fml else fml,
                'readings': readings_list,
            })
    
    return results


def _worker_generate_secondary_batch(args):
    """
    Worker function to generate secondary conjugations for a batch of entries.
    """
    batch_tasks, entry_data, pos_index, conj_rules_data = args
    
    # Reconstruct ConjugationRule objects
    conj_rules = {}
    for pos_id, rules_data in conj_rules_data.items():
        conj_rules[pos_id] = [
            ConjugationRule(
                pos=r['pos'], conj=r['conj'], neg=r['neg'], fml=r['fml'],
                onum=r['onum'], stem=r['stem'], okuri=r['okuri'],
                euphr=r['euphr'], euphk=r['euphk'], pos2=r['pos2']
            ) for r in rules_data
        ]
    
    results = []
    for seq_from, via_seq, posi, conj_type in batch_tasks:
        entry_results = _generate_secondary_conjugations_for_entry(
            seq_from, via_seq, posi, SECONDARY_CONJUGATION_TYPES,
            entry_data, pos_index, conj_rules
        )
        results.extend(entry_results)
    return results


def load_conjugations(progress_callback=None, num_workers: int = None):
    """
    Load conjugations for all entries with conjugatable POS.
    
    Equivalent to ichiran's load-conjugations function.
    Optimized with multiprocessing for parallel conjugation generation.
    
    Args:
        progress_callback: Optional callback for progress updates
        num_workers: Number of worker processes (default: CPU count)
    """
    global _next_seq_counter
    
    from himotoki.db.connection import set_bulk_loading_mode
    
    if num_workers is None:
        num_workers = mp.cpu_count()
    
    # Load cached data (will be shared with workers)
    load_pos_index()
    load_conj_rules()
    
    # Serialize conj_rules for workers (dataclasses -> dicts)
    conj_rules_data = {}
    for pos_id, rules in _conj_rules.items():
        conj_rules_data[pos_id] = [
            {'pos': r.pos, 'conj': r.conj, 'neg': r.neg, 'fml': r.fml,
             'onum': r.onum, 'stem': r.stem, 'okuri': r.okuri,
             'euphr': r.euphr, 'euphk': r.euphk, 'pos2': r.pos2}
            for r in rules
        ]
    
    with session_scope() as session:
        set_bulk_loading_mode(session, enabled=True)
        
        _next_seq_counter = get_next_seq(session)
        
        # Get sequences with conjugatable POS
        seqs = session.query(SenseProp.seq).filter(
            SenseProp.tag == 'pos',
            SenseProp.text.in_(POS_WITH_CONJ_RULES),
            ~SenseProp.seq.in_(DO_NOT_CONJUGATE_SEQ)
        ).distinct().all()
        seqs = [s[0] for s in seqs]
        
        total = len(seqs)
        logger.info(f"Processing {total} entries for conjugations with {num_workers} workers...")
        
        # Pre-fetch all entry data
        logger.info("Pre-fetching entry data...")
        entry_data = _prefetch_entry_data(session, seqs)
        
        # Split into batches for workers
        batch_size = max(100, len(seqs) // (num_workers * 4))
        batches = [seqs[i:i + batch_size] for i in range(0, len(seqs), batch_size)]
        
        logger.info(f"Generating conjugations in {len(batches)} batches...")
        
        # Generate conjugations in parallel
        all_conj_data = []
        with mp.Pool(num_workers) as pool:
            args_list = [(batch, entry_data, _pos_index, conj_rules_data) for batch in batches]
            for i, batch_results in enumerate(pool.imap_unordered(_worker_generate_batch, args_list)):
                all_conj_data.extend(batch_results)
                processed = min((i + 1) * batch_size, total)
                if progress_callback:
                    progress_callback(processed)
                elif (i + 1) % 10 == 0:
                    logger.info(f"Generated {processed}/{total} entries...")
        
        logger.info(f"Inserting {len(all_conj_data)} conjugation records...")
        
        # Bulk insert all conjugations
        for i, conj_data in enumerate(all_conj_data):
            if _insert_conjugation_from_data(session, conj_data, _next_seq_counter):
                _next_seq_counter += 1
            
            if (i + 1) % 10000 == 0:
                session.commit()
                logger.info(f"Inserted {i + 1}/{len(all_conj_data)} conjugations...")
        
        session.commit()
        set_bulk_loading_mode(session, enabled=False)
        logger.info(f"Conjugations complete. {len(all_conj_data)} conjugations inserted.")


def _insert_conjugation_from_data(session, conj_data: Dict, seq: int) -> bool:
    """
    Insert a conjugation from pre-computed data.
    """
    readings = conj_data['readings']
    
    # Group readings by (kanji_flag, ord)
    grouped = {}
    for conj_text, kanji_flag, orig_text, ord_num, onum in readings:
        key = (kanji_flag, ord_num)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append((conj_text, orig_text, onum))
    
    kanji_readings = []
    kana_readings = []
    source_readings = []
    
    for (kanji_flag, ord_num), group in grouped.items():
        group.sort(key=lambda x: x[2])
        best = group[0]
        source_readings.append((best[0], best[1]))
        if kanji_flag:
            kanji_readings.append(best[0])
        else:
            kana_readings.append(best[0])
    
    if not kanji_readings and not kana_readings:
        return False
    
    conjugate_p = conj_data['conj_type'] in SECONDARY_CONJUGATION_TYPES_FROM
    entry = Entry(seq=seq, content='', root_p=False)
    session.add(entry)
    
    for ord_num, text in enumerate(kanji_readings):
        session.add(KanjiText(seq=seq, text=text, ord=ord_num, common=None, conjugate_p=conjugate_p))
    
    for ord_num, text in enumerate(kana_readings):
        session.add(KanaText(seq=seq, text=text, ord=ord_num, common=None, conjugate_p=conjugate_p))
    
    via = conj_data.get('via')
    conj = Conjugation(seq=seq, from_seq=conj_data['from_seq'], via=via)
    session.add(conj)
    
    prop = ConjProp(conj_type=conj_data['conj_type'], pos=conj_data['pos'], neg=conj_data['neg'], fml=conj_data['fml'])
    conj.props.append(prop)
    
    seen = set()
    for text, source_text in source_readings:
        key = (text, source_text)
        if key not in seen:
            seen.add(key)
            sr = ConjSourceReading(text=text, source_text=source_text)
            conj.source_readings.append(sr)
    
    return True


def conjugate_entry_outer_fast(
    session,
    seq: int,
    via: Optional[int] = None,
    conj_types: Optional[List[int]] = None,
    as_posi: Optional[List[str]] = None
):
    """
    Fast version of conjugate_entry_outer for bulk loading.
    Uses global sequence counter and skips existence checks.
    """
    global _next_seq_counter
    
    source_seq = seq
    lookup_seq = via if via else seq
    
    conj_matrix = conjugate_entry_inner(
        session, lookup_seq, conj_types=conj_types, as_posi=as_posi
    )
    
    if not conj_matrix:
        return
    
    # Get original readings (inline query, no function call overhead)
    kanji = session.query(KanjiText.text).filter(KanjiText.seq == lookup_seq).all()
    kana = session.query(KanaText.text).filter(KanaText.seq == lookup_seq).all()
    original_readings = set([k[0] for k in kanji] + [k[0] for k in kana])
    
    for (pos_id, conj_id), matrix in conj_matrix.items():
        has_neg = bool(matrix[1][0] or matrix[1][1])
        has_fml = bool(matrix[0][1] or matrix[1][1])
        
        pos = get_pos_by_index(pos_id)
        if not pos:
            continue
        
        for ii in range(4):
            neg = ii >= 2
            fml = ii % 2 == 1
            
            readings = matrix[1 if neg else 0][1 if fml else 0]
            readings = [r for r in readings if r[0] not in original_readings]
            
            if not readings:
                continue
            
            neg_val = None if not has_neg else neg
            fml_val = None if not has_fml else fml
            
            if insert_conjugation_fast(
                session,
                readings,
                seq=_next_seq_counter,
                from_seq=source_seq,
                pos=pos,
                conj_type=conj_id,
                neg=neg_val,
                fml=fml_val,
                via=via
            ):
                _next_seq_counter += 1


def insert_conjugation_fast(
    session,
    readings: List[Tuple],
    seq: int,
    from_seq: int,
    pos: str,
    conj_type: int,
    neg: Optional[bool],
    fml: Optional[bool],
    via: Optional[int] = None
) -> bool:
    """
    Fast version of insert_conjugation for bulk loading.
    Skips existence checks since we're loading fresh.
    """
    # Group readings by (kanji_flag, ord)
    grouped = {}
    for conj_text, kanji_flag, orig_text, ord_num, onum in readings:
        key = (kanji_flag, ord_num)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append((conj_text, orig_text, onum))
    
    # Select best reading for each group
    kanji_readings = []
    kana_readings = []
    source_readings = []
    
    for (kanji_flag, ord_num), group in grouped.items():
        # Sort by onum and take first
        group.sort(key=lambda x: x[2])
        best = group[0]
        
        source_readings.append((best[0], best[1]))
        if kanji_flag:
            kanji_readings.append(best[0])
        else:
            kana_readings.append(best[0])
    
    if not kanji_readings and not kana_readings:
        return False
    
    # Create entry (no existence check - fresh load)
    conjugate_p = conj_type in SECONDARY_CONJUGATION_TYPES_FROM
    entry = Entry(seq=seq, content='', root_p=False)
    session.add(entry)
    
    # Add kanji readings
    for ord_num, text in enumerate(kanji_readings):
        session.add(KanjiText(seq=seq, text=text, ord=ord_num, common=None, conjugate_p=conjugate_p))
    
    # Add kana readings
    for ord_num, text in enumerate(kana_readings):
        session.add(KanaText(seq=seq, text=text, ord=ord_num, common=None, conjugate_p=conjugate_p))
    
    # Create conjugation record
    conj = Conjugation(seq=seq, from_seq=from_seq, via=via)
    session.add(conj)
    
    # Add conjugation property using relationship (no flush needed)
    prop = ConjProp(conj_type=conj_type, pos=pos, neg=neg, fml=fml)
    conj.props.append(prop)
    
    # Add source readings using relationship
    seen = set()
    for text, source_text in source_readings:
        key = (text, source_text)
        if key not in seen:
            seen.add(key)
            sr = ConjSourceReading(text=text, source_text=source_text)
            conj.source_readings.append(sr)
    
    return True


def conjugate_entry_outer(
    session,
    seq: int,
    via: Optional[int] = None,
    conj_types: Optional[List[int]] = None,
    as_posi: Optional[List[str]] = None
):
    """
    Generate all conjugations for an entry and insert into database.
    
    Equivalent to ichiran's conjugate-entry-outer function.
    
    Args:
        session: Database session
        seq: Entry sequence number (or source seq if via is set)
        via: Intermediate entry sequence (for secondary conjugations)
        conj_types: Optional list of conjugation types to generate
        as_posi: Optional POS list to override entry's POS
    """
    source_seq = seq
    lookup_seq = via if via else seq
    
    conj_matrix = conjugate_entry_inner(
        session, lookup_seq, conj_types=conj_types, as_posi=as_posi
    )
    
    original_readings = get_all_readings(session, lookup_seq)
    next_seq = get_next_seq(session)
    
    for (pos_id, conj_id), matrix in conj_matrix.items():
        # Check if we have any non-empty cells
        has_neg = bool(matrix[1][0] or matrix[1][1])
        has_fml = bool(matrix[0][1] or matrix[1][1])
        
        pos = get_pos_by_index(pos_id)
        if not pos:
            continue
        
        # Iterate over 4 combinations: neg=0/1, fml=0/1
        for ii in range(4):
            neg = ii >= 2
            fml = ii % 2 == 1
            
            neg_idx = 1 if neg else 0
            fml_idx = 1 if fml else 0
            
            readings = matrix[neg_idx][fml_idx]
            
            # Filter out readings that are same as original
            readings = [r for r in readings if r[0] not in original_readings]
            
            if not readings:
                continue
            
            # Use None instead of boolean if form doesn't distinguish
            neg_val = None if not has_neg else neg
            fml_val = None if not has_fml else fml
            
            if insert_conjugation(
                session,
                readings,
                seq=next_seq,
                from_seq=source_seq,
                pos=pos,
                conj_type=conj_id,
                neg=neg_val,
                fml=fml_val,
                via=via
            ):
                next_seq += 1


def load_secondary_conjugations(from_seqs: Optional[List[int]] = None, progress_callback=None, num_workers: int = None):
    """
    Load secondary conjugations (e.g., passive of causative).
    
    Equivalent to ichiran's load-secondary-conjugations function.
    Optimized with multiprocessing for parallel conjugation generation.
    """
    global _next_seq_counter
    
    from himotoki.db.connection import set_bulk_loading_mode
    
    if num_workers is None:
        num_workers = mp.cpu_count()
    
    # Ensure cached data is loaded
    load_pos_index()
    load_conj_rules()
    
    # Serialize conj_rules for workers
    conj_rules_data = {}
    for pos_id, rules in _conj_rules.items():
        conj_rules_data[pos_id] = [
            {'pos': r.pos, 'conj': r.conj, 'neg': r.neg, 'fml': r.fml,
             'onum': r.onum, 'stem': r.stem, 'okuri': r.okuri,
             'euphr': r.euphr, 'euphk': r.euphk, 'pos2': r.pos2}
            for r in rules
        ]
    
    with session_scope() as session:
        set_bulk_loading_mode(session, enabled=True)
        
        if _next_seq_counter == 0:
            _next_seq_counter = get_next_seq(session)
        
        # Build query for conjugations that can have secondary forms
        query = session.query(
            Conjugation.from_seq,
            Conjugation.seq,
            ConjProp.conj_type
        ).join(
            ConjProp, Conjugation.id == ConjProp.conj_id
        ).filter(
            ConjProp.conj_type.in_(SECONDARY_CONJUGATION_TYPES_FROM),
            ~ConjProp.pos.in_(['vs-i', 'vs-s']),
            Conjugation.via.is_(None),
            (ConjProp.neg.is_(None) | (ConjProp.neg == False)),
            (ConjProp.fml.is_(None) | (ConjProp.fml == False))
        ).distinct()
        
        if from_seqs:
            query = query.filter(Conjugation.from_seq.in_(from_seqs))
        
        to_conj = query.all()
        total = len(to_conj)
        logger.info(f"Processing {total} secondary conjugations with {num_workers} workers...")
        
        # Collect all "via" seqs to pre-fetch their data
        via_seqs = list(set([seq for _, seq, _ in to_conj]))
        logger.info(f"Pre-fetching data for {len(via_seqs)} intermediate entries...")
        entry_data = _prefetch_entry_data(session, via_seqs)
        
        # Build secondary conjugation tasks with specific POS
        tasks = []
        for seq_from, seq, conj_type in to_conj:
            pos = 'v5s' if conj_type == CONJ_CAUSATIVE_SU else 'v1'
            tasks.append((seq_from, seq, [pos], conj_type))
        
        # Split into batches
        batch_size = max(100, len(tasks) // (num_workers * 4))
        batches = [tasks[i:i + batch_size] for i in range(0, len(tasks), batch_size)]
        
        logger.info(f"Generating secondary conjugations in {len(batches)} batches...")
        
        # Generate in parallel
        all_conj_data = []
        with mp.Pool(num_workers) as pool:
            args_list = [(batch, entry_data, _pos_index, conj_rules_data) for batch in batches]
            for i, batch_results in enumerate(pool.imap_unordered(_worker_generate_secondary_batch, args_list)):
                all_conj_data.extend(batch_results)
                if (i + 1) % 10 == 0:
                    logger.info(f"Generated {min((i + 1) * batch_size, total)}/{total} secondary entries...")
        
        logger.info(f"Inserting {len(all_conj_data)} secondary conjugation records...")
        
        # Bulk insert
        for i, conj_data in enumerate(all_conj_data):
            if _insert_conjugation_from_data(session, conj_data, _next_seq_counter):
                _next_seq_counter += 1
            
            if (i + 1) % 10000 == 0:
                session.commit()
                logger.info(f"Inserted {i + 1}/{len(all_conj_data)} secondary conjugations...")
        
        session.commit()
        set_bulk_loading_mode(session, enabled=False)
        logger.info(f"Secondary conjugations complete. {len(all_conj_data)} conjugations inserted.")


# Errata hooks (for custom modifications to loaded data)
def errata_conj_description_hook(descriptions: Dict[int, str]):
    """Hook for modifying conjugation descriptions after loading."""
    # Add any custom modifications here
    pass


def errata_conj_rules_hook(rules: Dict[int, List[ConjugationRule]]):
    """Hook for modifying conjugation rules after loading."""
    # Add any custom modifications here
    pass