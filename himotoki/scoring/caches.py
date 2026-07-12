"""
LRU caches and cache management for scoring.
"""

from collections import OrderedDict
from typing import Optional, List, Dict, Set

from sqlalchemy import select, and_, func, case
from sqlalchemy.orm import Session

from himotoki.db.models import (
    Entry, Sense, SenseProp, Conjugation,
)

class LRUCache:
    """
    A simple LRU (Least Recently Used) cache with a maximum size.
    
    Uses OrderedDict to maintain insertion/access order. When the cache
    reaches capacity, the least recently used item is evicted.
    
    Thread-safety: This implementation is NOT thread-safe. For multi-threaded
    use, wrap access with a lock.
    """
    
    def __init__(self, maxsize: int):
        self.maxsize = maxsize
        self._cache: OrderedDict = OrderedDict()
    
    def get(self, key, default=None):
        """Get item, moving it to the end (most recently used)."""
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return default
    
    def __contains__(self, key):
        return key in self._cache
    
    def __getitem__(self, key):
        self._cache.move_to_end(key)
        return self._cache[key]
    
    def __setitem__(self, key, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.maxsize:
                # Evict oldest (first) item
                self._cache.popitem(last=False)
        self._cache[key] = value
    
    def __len__(self):
        return len(self._cache)
    
    def keys(self):
        return self._cache.keys()
    
    def clear(self):
        self._cache.clear()


# Conjugation data cache - (seq, from_seq, tuple(conj_ids), tuple(texts)) -> List[ConjData]
_CONJ_DATA_CACHE: LRUCache = LRUCache(maxsize=2048)

# POS cache - seq -> frozenset(posi) for per-seq caching
_POS_SEQ_CACHE: LRUCache = LRUCache(maxsize=4096)

# UK (prefer kana) cache - frozenset(seqs) -> bool
_UK_CACHE: LRUCache = LRUCache(maxsize=1024)

# Word lookup cache - (word, root_only) -> List[WordMatch]
_WORD_CACHE: LRUCache = LRUCache(maxsize=4096)

# Entry cache - seq -> Entry (reduces individual lookups)
_ENTRY_CACHE: LRUCache = LRUCache(maxsize=4096)

# Archaic words cache - populated on first use
_ARCHAIC_CACHE: Optional[Set[int]] = None


def preload_scoring_caches(session: Session, seqs: Set[int]) -> None:
    """
    Batch preload all caches needed for calc_score.
    
    This dramatically reduces cold-start latency by:
    1. Batch loading Entry objects
    2. Batch preloading UK (prefer-kana) status
    3. Batch preloading POS tags
    
    Call this before scoring a batch of segments.
    
    Args:
        session: Database session
        seqs: Set of seq numbers to preload
    """
    global _ENTRY_CACHE, _UK_CACHE, _POS_SEQ_CACHE
    
    if not seqs:
        return
    
    # Filter to seqs not already in entry cache
    missing_seqs = seqs - set(_ENTRY_CACHE.keys())
    
    if missing_seqs:
        # Batch load entries
        entries = session.execute(
            select(Entry).where(Entry.seq.in_(missing_seqs))
        ).scalars().all()
        
        # LRUCache handles eviction automatically
        for entry in entries:
            _ENTRY_CACHE[entry.seq] = entry
    
    # Find seqs not yet in UK cache
    uk_missing = {seq for seq in seqs if frozenset([seq]) not in _UK_CACHE}
    
    if uk_missing:
        # Single batch query for all UK statuses
        uk_seqs = set(session.execute(
            select(SenseProp.seq)
            .where(and_(
                SenseProp.seq.in_(uk_missing),
                SenseProp.tag == 'misc',
                SenseProp.text == 'uk'
            ))
            .distinct()
        ).scalars().all())
        
        # Cache results for all checked seqs
        for seq in uk_missing:
            cache_key = frozenset([seq])
            _UK_CACHE[cache_key] = seq in uk_seqs
    
    # Find seqs not yet in POS cache (now using _POS_SEQ_CACHE)
    pos_missing = {seq for seq in seqs if seq not in _POS_SEQ_CACHE}
    
    if pos_missing:
        # Build archaic senses subquery once
        arch_misc = {'arch', 'obsc', 'rare'}
        arch_senses = (
            select(SenseProp.sense_id)
            .where(and_(
                SenseProp.tag == 'misc',
                SenseProp.text.in_(arch_misc)
            ))
        )
        
        # Batch query for all POS tags (excluding archaic senses)
        pos_results = session.execute(
            select(SenseProp.seq, SenseProp.text)
            .where(and_(
                SenseProp.seq.in_(pos_missing),
                SenseProp.tag == 'pos',
                ~SenseProp.sense_id.in_(arch_senses)
            ))
        ).all()
        
        # Group results by seq
        seq_to_posi: Dict[int, Set[str]] = {seq: set() for seq in pos_missing}
        for seq, pos_text in pos_results:
            seq_to_posi[seq].add(pos_text)
        
        # LRUCache handles eviction automatically
        for seq, posi in seq_to_posi.items():
            _POS_SEQ_CACHE[seq] = frozenset(posi)


def get_cached_entry(session: Session, seq: int) -> Optional[Entry]:
    """
    Get Entry from cache or database.
    Uses _ENTRY_CACHE for faster repeated lookups.
    """
    global _ENTRY_CACHE
    
    if seq in _ENTRY_CACHE:
        return _ENTRY_CACHE[seq]
    
    entry = session.get(Entry, seq)
    
    # LRUCache handles eviction automatically
    if entry:
        _ENTRY_CACHE[seq] = entry
    
    return entry


# ============================================================================
# Archaic Word Detection
# ============================================================================

def build_archaic_cache(session: Session) -> Set[int]:
    """
    Build cache of archaic/obsolete/rare word seqs.
    From ichiran's *is-arch-cache*.
    
    Words where ALL senses are marked arch/obsc/rare are considered archaic.
    A word with even one non-archaic sense is NOT considered archaic.
    """
    arch_misc = {'arch', 'obsc', 'rare'}
    
    # Find seqs where EVERY sense has an arch/obsc/rare tag
    # This is the ichiran logic: 
    # SELECT sense.seq FROM sense
    # LEFT JOIN sense_prop sp ON (... AND sp.text IN ('arch', 'obsc', 'rare'))
    # GROUP BY sense.seq HAVING EVERY(sp.id IS NOT NULL)
    #
    # In SQLAlchemy, we do this by:
    # 1. Get all (seq, sense_id) pairs with their arch tag status
    # 2. Group by seq and check that all senses have the arch tag
    
    from sqlalchemy import func, case, literal_column
    from himotoki.db.models import Sense
    
    # Subquery: for each sense, is it archaic?
    arch_tag_subq = (
        select(SenseProp.sense_id)
        .where(and_(
            SenseProp.tag == 'misc',
            SenseProp.text.in_(arch_misc)
        ))
    )
    
    # Main query: find seqs where ALL senses are in arch_tag_subq
    # We count total senses and archaic senses per seq, keep only where they match
    query = (
        select(Sense.seq)
        .group_by(Sense.seq)
        .having(
            func.count(Sense.id) == func.sum(
                case((Sense.id.in_(arch_tag_subq), 1), else_=0)
            )
        )
    )
    arch_seqs = set(session.execute(query).scalars().all())
    
    # Also add conjugations derived from archaic words
    if arch_seqs:
        conj_query = (
            select(Conjugation.seq)
            .where(Conjugation.from_seq.in_(arch_seqs))
            .distinct()
        )
        conj_seqs = set(session.execute(conj_query).scalars().all())
        arch_seqs |= conj_seqs
    
    return arch_seqs


def is_arch(session: Session, seq_set: Set[int]) -> bool:
    """
    Check if all seqs in seq_set are archaic/obsolete/rare.
    Uses a cached set of archaic word seqs.
    """
    global _ARCHAIC_CACHE
    if _ARCHAIC_CACHE is None:
        _ARCHAIC_CACHE = build_archaic_cache(session)
    
    return all(seq in _ARCHAIC_CACHE for seq in seq_set)


def is_prefer_kana(session: Session, seq_set: List[int]) -> bool:
    """
    Check if entries have 'uk' (usually written in kana) misc tag.
    Cached for performance.
    """
    global _UK_CACHE
    
    cache_key = frozenset(seq_set)
    if cache_key in _UK_CACHE:
        return _UK_CACHE[cache_key]
    
    result = session.execute(
        select(SenseProp)
        .where(and_(
            SenseProp.seq.in_(seq_set),
            SenseProp.tag == 'misc',
            SenseProp.text == 'uk'
        ))
    ).scalars().first() is not None
    
    # LRUCache handles eviction automatically
    _UK_CACHE[cache_key] = result
    
    return result


def get_non_arch_posi(session: Session, seq_set: Set[int]) -> Set[str]:
    """
    Get part-of-speech tags for entries, excluding archaic senses.
    From ichiran's get-non-arch-posi.
    
    Uses per-seq caching for better hit rate when seq_sets overlap.
    """
    global _POS_SEQ_CACHE
    
    # Check if we have all seqs cached
    all_cached = all(seq in _POS_SEQ_CACHE for seq in seq_set)
    
    if all_cached:
        # Combine cached results
        result = set()
        for seq in seq_set:
            result |= _POS_SEQ_CACHE[seq]
        return result
    
    # Find which seqs need to be fetched
    missing_seqs = {seq for seq in seq_set if seq not in _POS_SEQ_CACHE}
    
    if missing_seqs:
        arch_misc = {'arch', 'obsc', 'rare'}
        
        # Subquery to find sense_ids with archaic props
        arch_senses = (
            select(SenseProp.sense_id)
            .where(and_(
                SenseProp.tag == 'misc',
                SenseProp.text.in_(arch_misc)
            ))
        )
        
        # Batch query for all missing seqs
        results = session.execute(
            select(SenseProp.seq, SenseProp.text)
            .where(and_(
                SenseProp.seq.in_(missing_seqs),
                SenseProp.tag == 'pos',
                ~SenseProp.sense_id.in_(arch_senses)
            ))
        ).all()
        
        # Group by seq
        seq_posi: Dict[int, Set[str]] = {seq: set() for seq in missing_seqs}
        for seq, pos_text in results:
            seq_posi[seq].add(pos_text)
        
        # LRUCache handles eviction automatically
        for seq, posi in seq_posi.items():
            _POS_SEQ_CACHE[seq] = frozenset(posi)
    
    # Combine results from cache
    result = set()
    for seq in seq_set:
        if seq in _POS_SEQ_CACHE:
            result |= _POS_SEQ_CACHE[seq]
    
    return result
