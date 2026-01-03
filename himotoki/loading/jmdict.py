"""
JMDict XML Parser for himotoki.
Ports ichiran's dict-load.lisp JMDict loading functionality.
"""

from typing import Optional, Iterator, List, Tuple, Any, Dict
from dataclasses import dataclass
from pathlib import Path
import logging
import re

from lxml import etree

from himotoki.db.connection import get_session, session_scope
from himotoki.db.models import (
    Entry, KanjiText, KanaText, Sense, Gloss, SenseProp, RestrictedReading
)

logger = logging.getLogger(__name__)


# Entity replacements for JMDict abbreviations
# These map the full entity text to abbreviations (entity names)
# Built by parse_entity_definitions()
ENTITY_REPLACEMENTS: Dict[str, str] = {}


def parse_entity_definitions(xml_path: Path) -> Dict[str, str]:
    """
    Parse entity definitions from JMDict DTD.
    Returns a mapping from expanded entity values to their short names.
    
    In ichiran, fix-entities replaces entity values with the entity names.
    For example, "noun (common) (futsuumeishi)" (the expanded value of &n;)
    gets replaced with just "n".
    
    This function builds a reverse mapping so we can convert expanded
    values back to their entity names when storing in the database.
    """
    global ENTITY_REPLACEMENTS
    
    # Read the file and extract entity definitions from DOCTYPE
    entities = {}
    with open(xml_path, 'rb') as f:
        # Read until we find the end of DOCTYPE
        content = b''
        for line in f:
            content += line
            if b']>' in line:
                break
    
    # Parse entity definitions: <!ENTITY name "value">
    pattern = rb'<!ENTITY\s+([\w-]+)\s+"([^"]*)">'
    for match in re.finditer(pattern, content):
        name = match.group(1).decode('utf-8')
        value = match.group(2).decode('utf-8')
        # Skip standard XML entities
        if name not in ('lt', 'gt', 'amp', 'apos', 'quot'):
            # Map expanded value -> entity name (for reverse lookup)
            entities[value] = name
    
    ENTITY_REPLACEMENTS = entities
    return entities


def fix_entity_value(text: str) -> str:
    """
    Convert an expanded entity value back to its short entity name.
    
    For example:
        "noun (common) (futsuumeishi)" -> "n"
        "Ichidan verb" -> "v1"
    
    This matches ichiran's fix-entities behavior.
    """
    return ENTITY_REPLACEMENTS.get(text, text)


def node_text(element: etree._Element) -> str:
    """
    Get all text content from an element and its children.
    Equivalent to ichiran's node-text function.
    """
    return ''.join(element.itertext())


def get_element_text(parent: etree._Element, tag: str) -> Optional[str]:
    """Get text from first child element with given tag."""
    elem = parent.find(tag)
    if elem is not None:
        return node_text(elem)
    return None


def get_elements_text(parent: etree._Element, tag: str) -> List[str]:
    """Get text from all child elements with given tag."""
    return [node_text(elem) for elem in parent.findall(tag)]


@dataclass
class ParsedReading:
    """Represents a parsed kanji or kana reading."""
    text: str
    common: Optional[int]  # None means :null in ichiran
    nokanji: bool
    pri_tags: str
    restrictions: List[str]  # re_restr or ke_restr elements
    skip: bool  # True if should be skipped (outdated kana)


def parse_reading(elem: etree._Element, text_tag: str, pri_tag: str) -> ParsedReading:
    """
    Parse a k_ele or r_ele element.
    
    Args:
        elem: The k_ele or r_ele element
        text_tag: 'keb' for kanji, 'reb' for kana
        pri_tag: 'ke_pri' for kanji, 're_pri' for kana
    
    Returns:
        ParsedReading with extracted data
    """
    reading_text = get_element_text(elem, text_tag) or ""
    
    # Check for outdated kana (re_inf with "ok" entity)
    # After entity expansion, "ok" becomes "out-dated or obsolete kana usage"
    # We convert it back to "ok" using fix_entity_value
    skip = False
    for inf in elem.findall('re_inf'):
        inf_value = fix_entity_value(node_text(inf))
        if inf_value == 'ok':
            skip = True
            break
    
    # Check for nokanji marker
    nokanji = len(elem.findall('re_nokanji')) > 0
    
    # Get restrictions (re_restr for kana, ke_restr for kanji)
    restr_tag = 're_restr' if text_tag == 'reb' else 'ke_restr'
    restrictions = get_elements_text(elem, restr_tag)
    
    # Get priority tags and calculate commonness
    common = None
    pri_tags_list = []
    for pri in elem.findall(pri_tag):
        pri_text = node_text(pri)
        pri_tags_list.append(pri_text)
        if common is None:
            common = 0
        # Extract frequency ranking from nf tags
        if pri_text.startswith('nf'):
            try:
                common = int(pri_text[2:])
            except ValueError:
                pass
    
    pri_tags = ''.join(f'[{tag}]' for tag in pri_tags_list)
    
    return ParsedReading(
        text=reading_text,
        common=common,
        nokanji=nokanji,
        pri_tags=pri_tags,
        restrictions=restrictions,
        skip=skip
    )


def insert_readings(
    session,
    readings: List[ParsedReading],
    table_class,
    seq: int,
    is_kana: bool = False
) -> Tuple[int, bool]:
    """
    Insert kanji or kana readings into database.
    
    Returns:
        Tuple of (count of readings added, primary_nokanji flag)
    """
    primary_nokanji = False
    valid_readings = [r for r in readings if not r.skip]
    
    for ord_num, reading in enumerate(valid_readings):
        if is_kana and reading.nokanji:
            primary_nokanji = True
        
        # Create reading record
        record = table_class(
            seq=seq,
            text=reading.text,
            ord=ord_num,
            common=reading.common,
            nokanji=reading.nokanji if is_kana else False,
            common_tags=reading.pri_tags
        )
        session.add(record)
        
        # Create restriction records (only for kana readings)
        if is_kana:
            for restr_text in reading.restrictions:
                restr = RestrictedReading(
                    seq=seq,
                    reading=reading.text,
                    text=restr_text
                )
                session.add(restr)
    
    return len(valid_readings), primary_nokanji


def insert_sense_traits(
    session,
    sense_elem: etree._Element,
    tag: str,
    sense_id: int,
    seq: int
):
    """
    Insert sense properties for a given tag.
    
    For tags that use entity references (pos, misc, dial, field),
    the expanded values are converted back to entity names.
    """
    # Tags that use entity references and need conversion
    entity_tags = {'pos', 'misc', 'dial', 'field'}
    
    for ord_num, elem in enumerate(sense_elem.findall(tag)):
        text = node_text(elem)
        
        # Convert expanded entity values back to entity names
        if tag in entity_tags:
            text = fix_entity_value(text)
        
        prop = SenseProp(
            sense_id=sense_id,
            tag=tag,
            text=text,
            ord=ord_num,
            seq=seq
        )
        session.add(prop)


# Batch size for sense flushes during bulk loading
_SENSE_BATCH_SIZE = 100
_pending_senses: List[Tuple[Any, List, List]] = []  # (sense, glosses, props)


def insert_senses(session, sense_nodes: List[etree._Element], seq: int):
    """Insert sense, gloss, and sense property records.
    
    Uses deferred relationship building - senses are added immediately
    and related records reference them via relationship, avoiding flush per sense.
    """
    for ord_num, sense_elem in enumerate(sense_nodes):
        # Create sense record - SQLAlchemy will handle the ID
        sense = Sense(seq=seq, ord=ord_num)
        session.add(sense)
        
        # Collect glosses using relationship (no need for explicit sense_id)
        for gloss_ord, gloss_elem in enumerate(sense_elem.findall('gloss')):
            gloss = Gloss(
                text=node_text(gloss_elem),
                ord=gloss_ord
            )
            sense.glosses.append(gloss)
        
        # Collect sense properties using relationship
        for tag in ('pos', 'misc', 'dial', 'field', 's_inf', 'stagk', 'stagr'):
            for prop_ord, elem in enumerate(sense_elem.findall(tag)):
                text = node_text(elem)
                # Convert entity values for relevant tags
                if tag in ('pos', 'misc', 'dial', 'field'):
                    text = fix_entity_value(text)
                prop = SenseProp(
                    tag=tag,
                    text=text,
                    ord=prop_ord,
                    seq=seq
                )
                sense.props.append(prop)


def load_entry(
    session,
    entry_elem: etree._Element,
    if_exists: str = 'skip',
    conjugate_p: bool = False
) -> Optional[int]:
    """
    Load a single entry from parsed XML element.
    
    Args:
        session: Database session
        entry_elem: The <entry> XML element
        if_exists: 'skip' to skip existing entries, 'overwrite' to replace
        conjugate_p: Whether to generate conjugations
    
    Returns:
        The entry sequence number, or None if skipped
    """
    # Get entry sequence number
    seq_elem = entry_elem.find('ent_seq')
    if seq_elem is None:
        logger.warning("Entry missing ent_seq, skipping")
        return None
    
    seq = int(node_text(seq_elem))
    
    # Handle existing entries
    existing = session.query(Entry).filter(Entry.seq == seq).first()
    if existing:
        if if_exists == 'skip':
            return None
        elif if_exists == 'overwrite':
            session.delete(existing)
            session.flush()
    
    # Serialize original content for storage
    content = etree.tostring(entry_elem, encoding='unicode')
    
    # Create entry record
    entry = Entry(seq=seq, content=content, root_p=True)
    session.add(entry)
    
    # Parse kanji readings (k_ele elements)
    kanji_readings = [
        parse_reading(elem, 'keb', 'ke_pri')
        for elem in entry_elem.findall('k_ele')
    ]
    
    # Parse kana readings (r_ele elements)
    kana_readings = [
        parse_reading(elem, 'reb', 're_pri')
        for elem in entry_elem.findall('r_ele')
    ]
    
    # Insert readings
    n_kanji, _ = insert_readings(session, kanji_readings, KanjiText, seq, is_kana=False)
    n_kana, primary_nokanji = insert_readings(session, kana_readings, KanaText, seq, is_kana=True)
    
    # Update entry stats
    entry.n_kanji = n_kanji
    entry.n_kana = n_kana
    entry.primary_nokanji = primary_nokanji
    
    # Parse and insert senses
    sense_elems = entry_elem.findall('sense')
    insert_senses(session, sense_elems, seq)
    
    # Conjugation handling is done separately after all entries are loaded
    
    return seq


def iter_entries(xml_path: Path) -> Iterator[etree._Element]:
    """
    Iterate over entry elements in JMDict XML file.
    Uses iterparse for memory efficiency with large files.
    """
    # Use iterparse with custom entity handling
    context = etree.iterparse(
        str(xml_path),
        events=('end',),
        tag='entry',
        recover=True,
        load_dtd=True,  # Load DTD to resolve entities
        no_network=True
    )
    
    for event, elem in context:
        yield elem
        # Clear element to free memory
        elem.clear()
        # Also clear ancestors
        while elem.getprevious() is not None:
            del elem.getparent()[0]


def load_jmdict(
    xml_path: Path,
    db_path: Optional[Path] = None,
    load_extras: bool = True,
    batch_size: int = 1000,
    progress_callback=None
) -> int:
    """
    Load JMDict XML file into database.
    
    This is the main entry point for loading JMDict data.
    Equivalent to ichiran's load-jmdict function.
    
    Args:
        xml_path: Path to JMDict XML file (e.g., JMdict_e.xml)
        db_path: Optional database path (uses default if not specified)
        load_extras: Whether to load conjugations after entries
        batch_size: Number of entries to commit in each batch
        progress_callback: Optional callback(count) for progress updates
    
    Returns:
        Total number of entries loaded
    """
    # Parse entity definitions from DTD (needed to convert expanded values back to entity names)
    xml_path = Path(xml_path)
    parse_entity_definitions(xml_path)
    logger.info(f"Parsed {len(ENTITY_REPLACEMENTS)} entity definitions from DTD")
    
    # Initialize database connection
    from himotoki.db.connection import init_database, set_bulk_loading_mode
    if db_path:
        init_database(str(db_path), drop_existing=True)
    
    count = 0
    with session_scope() as session:
        # Enable bulk loading mode for faster inserts
        set_bulk_loading_mode(session, enabled=True)
        
        for entry_elem in iter_entries(xml_path):
            seq = load_entry(session, entry_elem)
            if seq is not None:
                count += 1
                
            if count % batch_size == 0:
                session.commit()
                if progress_callback:
                    progress_callback(count)
                else:
                    logger.info(f"{count} entries loaded")
        
        # Final commit and restore normal mode
        session.commit()
        set_bulk_loading_mode(session, enabled=False)
    
    if progress_callback:
        progress_callback(count)
    else:
        logger.info(f"{count} entries total")
    
    # Load extras (conjugations, etc.)
    if load_extras:
        from himotoki.loading.conjugations import load_conjugations, load_secondary_conjugations
        from himotoki.loading.errata import add_errata
        from himotoki.db.connection import get_session
        
        logger.info("Loading conjugations...")
        load_conjugations()
        logger.info("Loading secondary conjugations...")
        load_secondary_conjugations()
        
        logger.info("Applying errata corrections...")
        with get_session() as session:
            add_errata(session)
    
    return count


def get_next_seq(session) -> int:
    """Get the next available sequence number."""
    from sqlalchemy import func
    result = session.query(func.max(Entry.seq)).scalar()
    return (result or 0) + 1