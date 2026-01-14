"""
Synergies and Segfilters module for himotoki.
Ports ichiran's dict-grammar.lisp synergy and segfilter functionality.

SYNERGIES:
Give bonuses to two consecutive words in a path when they form
common grammatical patterns. For example:
- noun + particle: 学校 + で (+10-40)
- na-adjective + な/に: 静か + な (+15)
- to-adverb + と: ゆっくり + と (+10-50)

SEGFILTERS:
Hard constraints that ban certain word combinations that would
otherwise be grammatically invalid. For example:
- Auxiliary verbs must follow continuative form
- ない can't follow は unless it's a proper form
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Union, Any, Callable, Set
from functools import lru_cache

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from himotoki.db.models import KanjiText, KanaText
from himotoki.constants import (
    # Particles
    SEQ_WA, SEQ_GA, SEQ_NI, SEQ_DE, SEQ_HE, SEQ_WO, SEQ_NO, SEQ_TO, SEQ_MO, SEQ_YA, SEQ_KA,
    # Compound particles
    SEQ_NIHA, SEQ_TOHA, SEQ_TOKA, SEQ_TOSHITE, SEQ_DESAE,
    # Other particles
    SEQ_DAKE, SEQ_GORO, SEQ_MADE, SEQ_NADO, SEQ_NOMI, SEQ_SAE, SEQ_TTE, SEQ_KARA, SEQ_NITOTTE,
    # Verbs
    SEQ_SURU, SEQ_IRU, SEQ_KURU,
    # Expressions
    SEQ_NITSURE, SEQ_OSUSUME,
    # Pre-built set
    NOUN_PARTICLES,
)


# ============================================================================
# Filter Caching System
# ============================================================================

# Global filter ID counter for unique identification
_filter_id_counter = 0


def _get_next_filter_id() -> int:
    """Get a unique filter ID."""
    global _filter_id_counter
    _filter_id_counter += 1
    return _filter_id_counter


def cached_filter(filter_fn: Callable) -> Callable:
    """
    Wrap a filter function with segment-level caching.
    
    Each filter gets a unique ID, and results are cached on the segment
    to avoid re-running the same filter on the same segment.
    """
    filter_id = _get_next_filter_id()
    
    def _cached_filter(segment: Any) -> bool:
        # Try to get cached result
        if hasattr(segment, 'get_filter_result'):
            cached = segment.get_filter_result(filter_id)
            if cached is not None:
                return cached
        
        # Compute and cache result
        result = filter_fn(segment)
        
        if hasattr(segment, 'set_filter_result'):
            segment.set_filter_result(filter_id, result)
        
        return result
    
    # Preserve the filter's identity for debugging
    _cached_filter.__name__ = getattr(filter_fn, '__name__', 'cached_filter')
    _cached_filter._filter_id = filter_id
    
    return _cached_filter


# ============================================================================
# Synergy Data Structure
# ============================================================================

@dataclass(slots=True)
class Synergy:
    """Represents a synergy between two adjacent segments."""
    description: str
    connector: str  # Space or empty string between words
    score: int
    start: int  # Position where synergy starts
    end: int  # Position where synergy ends


def get_segment_score_synergy(syn: Synergy) -> int:
    """Get the score value from a synergy."""
    return syn.score


# ============================================================================
# Synergy List and Registration
# ============================================================================

_synergy_list: List[Callable] = []


def register_synergy(func: Callable):
    """Register a synergy function."""
    _synergy_list.append(func)
    return func


# ============================================================================
# Filter Helpers
# ============================================================================

def _filter_is_noun_impl(segment: Any) -> bool:
    """Check if segment is a noun (implementation)."""
    info = getattr(segment, 'info', {})
    kpcl = info.get('kpcl', [False, False, False, False])
    if len(kpcl) < 4:
        kpcl = kpcl + [False] * (4 - len(kpcl))
    k, p, c, l = kpcl
    
    posi = info.get('posi', [])
    noun_pos = {'n', 'n-adv', 'n-t', 'adj-na', 'n-suf', 'pn'}
    
    if (l or k or (p and c)) and noun_pos.intersection(posi):
        return True
    
    # Check for counter
    word = getattr(segment, 'word', None)
    if word and hasattr(word, '__class__') and 'counter' in word.__class__.__name__.lower():
        return bool(info.get('seq_set'))
    
    return False


# Create cached version of filter_is_noun
filter_is_noun = cached_filter(_filter_is_noun_impl)


# Cache for filter_is_pos filters to avoid creating duplicates
_pos_filter_cache: Dict[frozenset, Callable] = {}


def filter_is_pos(*pos_list: str):
    """Create filter for specific parts of speech (cached)."""
    pos_key = frozenset(pos_list)
    if pos_key in _pos_filter_cache:
        return _pos_filter_cache[pos_key]
    
    pos_set = set(pos_list)
    
    def _filter(segment: Any) -> bool:
        info = getattr(segment, 'info', {})
        posi = info.get('posi', [])
        return bool(pos_set.intersection(posi))
    
    result = cached_filter(_filter)
    _pos_filter_cache[pos_key] = result
    return result


# Cache for filter_in_seq_set filters
_seq_filter_cache: Dict[frozenset, Callable] = {}


def filter_in_seq_set(*seqs: int):
    """Create filter for specific sequence numbers (cached)."""
    seq_key = frozenset(seqs)
    if seq_key in _seq_filter_cache:
        return _seq_filter_cache[seq_key]
    
    seq_set = set(seqs)
    
    def _filter(segment: Any) -> bool:
        info = getattr(segment, 'info', {})
        segment_seqs = info.get('seq_set', [])
        return bool(seq_set.intersection(segment_seqs))
    
    result = cached_filter(_filter)
    _seq_filter_cache[seq_key] = result
    return result


# Cache for filter_in_seq_set_simple filters
_seq_simple_filter_cache: Dict[frozenset, Callable] = {}


def filter_in_seq_set_simple(*seqs: int):
    """Filter for seqs, checking that word is not compound (cached)."""
    seq_key = frozenset(seqs)
    if seq_key in _seq_simple_filter_cache:
        return _seq_simple_filter_cache[seq_key]
    
    seq_set = set(seqs)
    
    def _filter(segment: Any) -> bool:
        word = getattr(segment, 'word', None)
        if not word:
            return False
        seq = getattr(word, 'seq', None)
        if isinstance(seq, list):
            return False
        info = getattr(segment, 'info', {})
        segment_seqs = info.get('seq_set', [])
        return bool(seq_set.intersection(segment_seqs))
    
    result = cached_filter(_filter)
    _seq_simple_filter_cache[seq_key] = result
    return result


# Cache for filter_is_conjugation filters
_conj_filter_cache: Dict[int, Callable] = {}


def filter_is_conjugation(conj_type: int):
    """Create filter for specific conjugation type (cached)."""
    if conj_type in _conj_filter_cache:
        return _conj_filter_cache[conj_type]
    
    def _filter(segment: Any) -> bool:
        info = getattr(segment, 'info', {})
        conj = info.get('conj', [])
        for cdata in conj:
            if hasattr(cdata, 'prop') and cdata.prop:
                if getattr(cdata.prop, 'conj_type', None) == conj_type:
                    return True
        return False
    
    result = cached_filter(_filter)
    _conj_filter_cache[conj_type] = result
    return result


# Cache for filter_is_compound_end filters
_compound_end_filter_cache: Dict[frozenset, Callable] = {}


def filter_is_compound_end(*seqs: int):
    """Filter for compound words ending with specific seqs (cached)."""
    seq_key = frozenset(seqs)
    if seq_key in _compound_end_filter_cache:
        return _compound_end_filter_cache[seq_key]
    
    seq_set = set(seqs)
    
    def _filter(segment: Any) -> bool:
        word = getattr(segment, 'word', None)
        if not word:
            return False
        seq = getattr(word, 'seq', None)
        if isinstance(seq, list) and seq:
            return seq[-1] in seq_set
        return False
    
    result = cached_filter(_filter)
    _compound_end_filter_cache[seq_key] = result
    return result


# Cache for filter_is_compound_end_text filters
_compound_end_text_filter_cache: Dict[frozenset, Callable] = {}


def filter_is_compound_end_text(*texts: str):
    """Filter for compound words ending with specific texts (cached)."""
    text_key = frozenset(texts)
    if text_key in _compound_end_text_filter_cache:
        return _compound_end_text_filter_cache[text_key]
    
    text_set = set(texts)
    
    def _filter(segment: Any) -> bool:
        word = getattr(segment, 'word', None)
        if not word:
            return False
        seq = getattr(word, 'seq', None)
        if not isinstance(seq, list):
            return False
        words = getattr(word, 'words', [])
        if words:
            last_word = words[-1]
            text = getattr(last_word, 'text', '')
            return text in text_set
        return False
    
    result = cached_filter(_filter)
    _compound_end_text_filter_cache[text_key] = result
    return result


def filter_short_kana(length: int, except_list: Optional[List[str]] = None):
    """Filter for short kana words."""
    except_set = set(except_list) if except_list else set()
    
    def _filter(segment_list: Any) -> bool:
        segments = getattr(segment_list, 'segments', [])
        if not segments:
            return False
        seg = segments[0]
        
        seg_len = segment_list.end - segment_list.start
        if seg_len > length:
            return False
        
        info = getattr(seg, 'info', {})
        kpcl = info.get('kpcl', [False, False, False, False])
        if kpcl and kpcl[0]:  # Has kanji
            return False
        
        text = getattr(seg, 'text', '') or getattr(seg.word, 'text', '')
        if text in except_set:
            return False
        
        return True
    
    return _filter


# ============================================================================
# Synergy Definitions
# ============================================================================

def def_generic_synergy(
    name: str,
    filter_left: Callable,
    filter_right: Callable,
    description: str,
    score: Union[int, Callable],
    connector: str = " ",
):
    """
    Define a generic synergy between two segment lists.
    """
    def synergy_fn(seg_list_left: Any, seg_list_right: Any) -> List[Tuple]:
        start = seg_list_left.end
        end = seg_list_right.start
        
        # Must be adjacent
        if start != end:
            return []
        
        left_segments = [s for s in seg_list_left.segments if filter_left(s)]
        right_segments = [s for s in seg_list_right.segments if filter_right(s)]
        
        if not left_segments or not right_segments:
            return []
        
        # Calculate score
        if callable(score):
            actual_score = score(seg_list_left, seg_list_right)
        else:
            actual_score = score
        
        # Create synergy
        syn = Synergy(
            description=description,
            connector=connector,
            score=actual_score,
            start=start,
            end=end,
        )
        
        # Return modified segment lists with synergy
        from himotoki.lookup import SegmentList
        new_left = SegmentList(
            segments=left_segments,
            start=seg_list_left.start,
            end=seg_list_left.end,
            matches=seg_list_left.matches,
        )
        new_right = SegmentList(
            segments=right_segments,
            start=seg_list_right.start,
            end=seg_list_right.end,
            matches=seg_list_right.matches,
        )
        
        return [(new_right, syn, new_left)]
    
    register_synergy(synergy_fn)
    return synergy_fn


# Define all synergies
def _init_synergies():
    """Initialize all synergy definitions."""
    
    # Helper to check for specific seq combinations that should NOT get noun+prt synergy
    def not_to_before_wa(left_seg_list: Any, right_seg_list: Any) -> bool:
        """Return False if left is と (SEQ_TO) and right is は (SEQ_WA)."""
        left_seqs = set()
        right_seqs = set()
        for seg in getattr(left_seg_list, 'segments', []):
            info = getattr(seg, 'info', {})
            left_seqs.update(info.get('seq_set', set()))
        for seg in getattr(right_seg_list, 'segments', []):
            info = getattr(seg, 'info', {})
            right_seqs.update(info.get('seq_set', set()))
        # Block synergy if left has と and right has は
        if SEQ_TO in left_seqs and SEQ_WA in right_seqs:
            return False
        return True
    
    # Create a modified filter_is_noun that also checks the right side
    def filter_is_noun_not_to_wa(segment: Any, right_seg_list: Any = None) -> bool:
        if not filter_is_noun(segment):
            return False
        # This will be used via custom synergy below
        return True
    
    # noun + particle (with exclusion for と + は)
    def synergy_noun_particle(seg_list_left: Any, seg_list_right: Any) -> List[Tuple]:
        """Custom noun+particle synergy that excludes と + は."""
        # Check if left is noun
        left_nouns = [s for s in seg_list_left.segments if filter_is_noun(s)]
        if not left_nouns:
            return []
        
        # Check if right is particle
        particle_filter = filter_in_seq_set(*NOUN_PARTICLES)
        right_particles = [s for s in seg_list_right.segments if particle_filter(s)]
        if not right_particles:
            return []
        
        # Check serial
        if seg_list_left.end != seg_list_right.start:
            return []
        
        # Check for と + は case that should be excluded
        if not not_to_before_wa(seg_list_left, seg_list_right):
            return []
        
        # Create synergy
        length = seg_list_right.end - seg_list_right.start
        score = 10 + 4 * length
        
        synergy = Synergy(
            description="noun+prt",
            connector=" ",
            score=score,
            start=seg_list_left.end,
            end=seg_list_right.start,
        )
        
        return [(seg_list_right, synergy, seg_list_left)]
    
    register_synergy(synergy_noun_particle)
    
    # noun + だ
    def_generic_synergy(
        name="synergy-noun-da",
        filter_left=filter_is_noun,
        filter_right=filter_in_seq_set(2089020),  # だ
        description="noun+da",
        score=10,
        connector=" ",
    )
    
    # の + だ/です/なんだ
    def_generic_synergy(
        name="synergy-no-da",
        filter_left=filter_in_seq_set(1469800, 2139720),  # の, ん
        filter_right=filter_in_seq_set(2089020, 1007370, 1928670),  # だ, だった, だろう
        description="no da/desu",
        score=15,
        connector=" ",
    )
    
    # そう + なんだ
    def_generic_synergy(
        name="synergy-sou-nanda",
        filter_left=filter_in_seq_set(2137720),  # そう
        filter_right=filter_in_seq_set(2140410),  # なんだ
        description="sou na n da",
        score=50,
        connector=" ",
    )
    
    # no-adjective + の
    def_generic_synergy(
        name="synergy-no-adjectives",
        filter_left=filter_is_pos("adj-no"),
        filter_right=filter_in_seq_set(1469800),  # の
        description="no-adjective",
        score=15,
        connector=" ",
    )
    
    # na-adjective + な/に
    def_generic_synergy(
        name="synergy-na-adjectives",
        filter_left=filter_is_pos("adj-na"),
        filter_right=filter_in_seq_set(2029110, 2028990),  # な, に
        description="na-adjective",
        score=15,
        connector=" ",
    )
    
    # to-adverb + と
    def_generic_synergy(
        name="synergy-to-adverbs",
        filter_left=filter_is_pos("adv-to"),
        filter_right=filter_in_seq_set(1008490),  # と
        description="to-adverb",
        score=lambda l, r: 10 + 10 * (l.end - l.start),
        connector=" ",
    )
    
    # noun + 中
    def_generic_synergy(
        name="synergy-suffix-chu",
        filter_left=filter_is_noun,
        filter_right=filter_in_seq_set(1620400, 2083570),  # 中
        description="suffix-chu",
        score=12,
        connector="-",
    )
    
    # noun + たち
    # Use dynamic score based on noun length - longer nouns get higher synergy
    # This helps 村人+たち (258+15=273) beat 村+人たち (263)
    def_generic_synergy(
        name="synergy-suffix-tachi",
        filter_left=filter_is_noun,
        filter_right=filter_in_seq_set(1416220),  # たち
        description="suffix-tachi",
        score=lambda l, r: 10 + 5 * (l.end - l.start),  # +5 per character
        connector="-",
    )
    
    # noun + ぶり
    def_generic_synergy(
        name="synergy-suffix-buri",
        filter_left=filter_is_noun,
        filter_right=filter_in_seq_set(1361140),  # ぶり
        description="suffix-buri",
        score=40,
        connector="",
    )
    
    # noun + 性
    def_generic_synergy(
        name="synergy-suffix-sei",
        filter_left=filter_is_noun,
        filter_right=filter_in_seq_set(1375260),  # 性
        description="suffix-sei",
        score=12,
        connector="",
    )
    
    # お + noun (excluding cases where it splits a valid compound like ごみ)
    # Create a combined filter that checks pos AND excludes specific seqs
    def filter_o_noun_right(segment: Any) -> bool:
        """Filter for nouns that can follow お/ご prefix."""
        # Must be a noun
        if not filter_is_pos("n")(segment):
            return False
        # Exclude みの (straw raincoat) to prevent splitting ごみ
        info = getattr(segment, 'info', {})
        seq_set = info.get('seq_set', set())
        excluded_seqs = {1634010, 2845080}  # みの seqs
        if seq_set.intersection(excluded_seqs):
            return False
        return True
    
    def_generic_synergy(
        name="synergy-o-prefix",
        filter_left=filter_in_seq_set(1270190),  # お
        filter_right=filter_o_noun_right,
        description="o+noun",
        score=10,
        connector="",
    )
    
    # 未/不 + noun
    def_generic_synergy(
        name="synergy-kanji-prefix",
        filter_left=filter_in_seq_set(2242840, 1922780, 2423740),  # 未, 不
        filter_right=filter_is_pos("n"),
        description="kanji prefix+noun",
        score=15,
        connector="",
    )
    
    # しちゃ/しては + いけない
    def_generic_synergy(
        name="synergy-shicha-ikenai",
        filter_left=filter_is_compound_end(2028920),  # は
        filter_right=filter_in_seq_set(1000730, 1612750, 1409110, 2829697, 1587610),
        description="shicha ikenai",
        score=50,
        connector=" ",
    )
    
    # しか + negative
    def synergy_shika_negative(seg_list_left: Any, seg_list_right: Any) -> List[Tuple]:
        start = seg_list_left.end
        end = seg_list_right.start
        
        if start != end:
            return []
        
        # Filter left for しか
        filter_shika = filter_in_seq_set(1005460)
        left_segments = [s for s in seg_list_left.segments if filter_shika(s)]
        
        if not left_segments:
            return []
        
        # Filter right for negative conjugation
        right_segments = []
        for seg in seg_list_right.segments:
            info = getattr(seg, 'info', {})
            conj = info.get('conj', [])
            for cdata in conj:
                if hasattr(cdata, 'prop') and cdata.prop and getattr(cdata.prop, 'neg', False):
                    right_segments.append(seg)
                    break
        
        if not right_segments:
            return []
        
        syn = Synergy(
            description="shika+neg",
            connector=" ",
            score=50,
            start=start,
            end=end,
        )
        
        from himotoki.lookup import SegmentList
        new_left = SegmentList(
            segments=left_segments,
            start=seg_list_left.start,
            end=seg_list_left.end,
            matches=seg_list_left.matches,
        )
        new_right = SegmentList(
            segments=right_segments,
            start=seg_list_right.start,
            end=seg_list_right.end,
            matches=seg_list_right.matches,
        )
        
        return [(new_right, syn, new_left)]
    
    register_synergy(synergy_shika_negative)
    
    # の + 通り
    def_generic_synergy(
        name="synergy-no-toori",
        filter_left=filter_in_seq_set(1469800),  # の
        filter_right=filter_in_seq_set(1432920),  # 通り
        description="no toori",
        score=50,
        connector=" ",
    )
    
    # counter + おき
    def_generic_synergy(
        name="synergy-oki",
        filter_left=filter_is_pos("ctr"),
        filter_right=filter_in_seq_set(2854117, 2084550),  # おき
        description="counter+oki",
        score=20,
        connector="",
    )
    
    # かどうか + は (whether or not + topic marker)
    # This prevents misparses like はま+だ instead of は+まだ
    def_generic_synergy(
        name="synergy-kadouka-wa",
        filter_left=filter_in_seq_set(2087300),  # かどうか
        filter_right=filter_in_seq_set(2028920),  # は
        description="kadouka+wa",
        score=30,
        connector=" ",
    )
    
    # particle + common adverb synergy
    # This boosts patterns like は+まだ, には+まだ, も+まだ etc.
    # Common adverbs that follow particles:
    # まだ (1527110): still, yet
    # もう (1010180): already, soon
    # まず (1623080): first of all
    # やはり (2084660): as expected
    # すでに (1303920): already
    # ずっと (1008930): continuously
    # もっと (1010210): more
    # とても (1008550): very
    # かなり (1004920): considerably
    # なかなか (1530760): quite, rather
    # 少し (1340610): a little
    # ちょっと (1008680): a little
    # 全然 (1391950): not at all
    # 絶対 (1391700): absolutely
    # 本当に (1583020): really
    # 実は (1311820): actually
    # 確かに (1208880): certainly
    # 多分 (1397270): probably
    # きっと (1399930): surely
    # たぶん (1397270): probably
    # 結局 (1252670): after all
    # 一応 (2423580): tentatively
    # とりあえず (1541310): for now
    # 相変わらず (1273140): as usual
    # いつも (1216780): always
    # たまに (1623560): occasionally
    # 時々 (1320780): sometimes
    # よく (1544660): often
    # あまり (1010990): not very
    COMMON_ADVERB_SEQS = {
        1527110,  # まだ
        1010180,  # もう
        1623080,  # まず
        2084660,  # やはり
        1303920,  # すでに (既に)
        1008930,  # ずっと
        1010210,  # もっと
        1008550,  # とても
        1004920,  # かなり
        1530760,  # なかなか
        1340610,  # 少し
        1008680,  # ちょっと
        1391950,  # 全然
        1391700,  # 絶対
        1583020,  # 本当に
        1311820,  # 実は
        1208880,  # 確かに
        1397270,  # 多分/たぶん
        1399930,  # きっと
        1252670,  # 結局
        2423580,  # 一応
        1541310,  # とりあえず
        1273140,  # 相変わらず
        1216780,  # いつも
        1623560,  # たまに
        1320780,  # 時々
        1544660,  # よく
        1010990,  # あまり
    }
    
    # Particles that can precede common adverbs
    PARTICLE_SEQS = {
        2028920,  # は
        2028930,  # が
        2028940,  # も
        2028990,  # に
        2028980,  # で
        2215430,  # には
        2028950,  # とは
        1007340,  # だけ
        1525680,  # まで
        1002980,  # から
    }
    
    def_generic_synergy(
        name="synergy-particle-adverb",
        filter_left=filter_in_seq_set(*PARTICLE_SEQS),
        filter_right=filter_in_seq_set(*COMMON_ADVERB_SEQS),
        description="particle+adverb",
        score=20,  # Strong synergy to beat noun+copula patterns
        connector=" ",
    )


# Initialize synergies on module load
_init_synergies()


def get_synergies(seg_list_left: Any, seg_list_right: Any) -> List[Tuple]:
    """
    Get all synergies between two segment lists.
    
    Returns list of (new_right, synergy, new_left) tuples.
    """
    results = []
    for fn in _synergy_list:
        results.extend(fn(seg_list_left, seg_list_right))
    return results


# ============================================================================
# Penalty List and Registration
# ============================================================================

_penalty_list: List[Callable] = []


def register_penalty(func: Callable):
    """Register a penalty function."""
    _penalty_list.append(func)
    return func


def def_generic_penalty(
    name: str,
    test_left: Callable,
    test_right: Callable,
    description: str,
    score: int,
    serial: bool = True,
    connector: str = " ",
):
    """
    Define a generic penalty between two segment lists.
    """
    def penalty_fn(seg_list_left: Any, seg_list_right: Any) -> Optional[Synergy]:
        start = seg_list_left.end
        end = seg_list_right.start
        
        # Check serial requirement
        if serial and start != end:
            return None
        
        if not test_left(seg_list_left):
            return None
        if not test_right(seg_list_right):
            return None
        
        return Synergy(
            description=description,
            connector=connector,
            score=score,
            start=start,
            end=end,
        )
    
    register_penalty(penalty_fn)
    return penalty_fn


# Define penalties
def _init_penalties():
    """Initialize all penalty definitions."""
    
    # と + は should be penalized to prefer compound とは (seq=2028950)
    # The noun+prt synergy gives +14 to と+は which makes it beat とは (24 vs 22)
    # This penalty counteracts that so とは wins
    # NOTE: This must come BEFORE other penalties so it applies first
    def has_seq_simple(seqs: set):
        """Check if segment_list has any of the given seq numbers."""
        def _filter(segment_list: Any) -> bool:
            segments = getattr(segment_list, 'segments', [])
            for seg in segments:
                info = getattr(seg, 'info', {})
                seq_set = info.get('seq_set', set())
                if seqs.intersection(seq_set):
                    return True
            return False
        return _filter
    
    def_generic_penalty(
        name="penalty-to-wa",
        test_left=has_seq_simple({1008490}),  # と
        test_right=has_seq_simple({2028920}),  # は
        description="to+wa-penalty",
        score=-20,
        serial=True,
    )
    
    # に + つれ should be penalized to prefer compound につれ (seq=2136050)
    # につれ has score 36, but に(11)+つれ(40)=51 wins otherwise
    # Need penalty of at least -(51-36)=-15, but make it larger to be safe
    # つれ seqs include: 10351890, 1434020, 10097136, 1559290, 1434120, 10351981
    def_generic_penalty(
        name="penalty-ni-tsure",
        test_left=has_seq_simple({2028990}),  # に
        test_right=has_seq_simple({10351890, 1434020, 10097136, 1559290, 1434120, 10351981}),  # つれ
        description="ni+tsure-penalty",
        score=-30,
        serial=True,
    )
    
    # お + すすめ should be penalized to prefer compound おすすめ (seq=1002150)
    # おすすめ has score 64, but お(10)+すすめ(90)=100 wins otherwise
    # Need penalty of at least -36 to make them equal
    # お seqs: 1343610 (common=12), 1485770 (common=5), 2089690, 2268350, 2603520, 2742870, 2826528
    # すすめ seqs: 1210900 (noun), 10074000 (verb conjugation), 1365980, 1365990
    def_generic_penalty(
        name="penalty-o-susume",
        test_left=has_seq_simple({1343610, 1485770, 2089690, 2268350, 2603520, 2742870, 2826528}),  # お
        test_right=has_seq_simple({1210900, 10074000, 1365980, 1365990}),  # すすめ
        description="o+susume-penalty",
        score=-40,
        serial=True,
    )
    
    # 人がい + たら should be penalized to prefer 人 + が + いたら
    # 人がい is a conjugation of 人がいい (seq=10043332, 2250200)
    # 人がい(120)+たら(68)=188 beats 人(16)+が(11)+いたら(90)=117
    # Need penalty of at least -71 to make them equal
    # たら seqs: 1408160, 1416790, 2029050, 11435516, 11679733
    def_generic_penalty(
        name="penalty-hitogai-tara",
        test_left=has_seq_simple({10043332, 2250200}),  # 人がい / 人がいい
        test_right=has_seq_simple({1408160, 1416790, 2029050, 11435516, 11679733}),  # たら
        description="hitogai+tara-penalty",
        score=-75,
        serial=True,
    )
    
    # ご + みの should be penalized to prefer compound ごみ (seq=1369900)
    # ごみ + の = 12 + 16 = 28
    # ご(10) + みの(12) = 22, plus o+noun synergy(+10) = 32
    # Need penalty of at least -6 to make ごみ + の win (28 > 26)
    # Using -15 to ensure ごみ is strongly preferred
    # ご (honorific prefix): seq=1270190
    # みの: seq=1634010 (straw raincoat), 2845080 (Mino province)
    def_generic_penalty(
        name="penalty-go-mino",
        test_left=has_seq_simple({1270190}),  # ご (honorific prefix)
        test_right=has_seq_simple({1634010, 2845080}),  # みの
        description="go+mino-penalty",
        score=-15,
        serial=True,
    )
    
    # わかん + ない should be penalized to prefer compound わかんない (seq=2158960)
    # わかんない has score 125, but わかん(110)+ない(40)=150 wins otherwise
    # Need penalty of at least -(150-125)=-25 to make わかんない win
    # Using -30 to ensure it's strongly preferred
    # わかん seqs: 10256789, 10256836 (conjugated forms of 分かる)
    # ない seqs: 10452328, 1529520 (negative adjective/suffix)
    def_generic_penalty(
        name="penalty-wakan-nai",
        test_left=has_seq_simple({10256789, 10256836}),  # わかん
        test_right=has_seq_simple({10452328, 1529520}),  # ない
        description="wakan+nai-penalty",
        score=-30,
        serial=True,
    )
    
    # 知らん + けど should be penalized to prefer compound 知らんけど (seq=2856919)
    # 知らんけど exists as a single expression (Kansai dialect "I dunno but")
    # 知らん seqs include various conjugated forms
    # けど seqs: 1004200
    def_generic_penalty(
        name="penalty-shiran-kedo",
        test_left=has_seq_simple({10350776}),  # 知らん (conjugated 知る)
        test_right=has_seq_simple({1004200}),  # けど
        description="shiran+kedo-penalty",
        score=-100,  # Strong penalty since 知らんけど is a specific expression
        serial=True,
    )
    
    # はま + だ should be penalized to prefer は + まだ
    # はま (seq=1490710, beach) + だ (copula) incorrectly beats は + まだ (still)
    # はま+だ gets 66 (with noun+だ synergy), は+まだ gets 51
    # With particle+adverb synergy (+20), は+まだ gets 71
    # But we still need a penalty to be safe: -20 makes はま+だ = 46, safely below 71
    def_generic_penalty(
        name="penalty-hama-da",
        test_left=has_seq_simple({1490710, 2084350}),  # はま (beach, other)
        test_right=has_seq_simple({2089020}),  # だ (copula)
        description="hama+da-penalty",
        score=-20,
        serial=True,
    )
    
    # 人たち after single-kanji word should be penalized when compound word exists
    # 村 + 人たち (263) vs 村人 + たち (258)
    # This penalty makes 村+人たち = 263-10 = 253, so 村人+たち (258) wins
    def penalty_hitotachi_split(seg_list_left: Any, seg_list_right: Any) -> Optional[Synergy]:
        """Penalize single-kanji + 人たち to prefer compound + たち."""
        start = seg_list_left.end
        end = seg_list_right.start
        
        # Must be serial
        if start != end:
            return None
        
        # Check if right is 人たち (seq=1368740)
        segments_right = getattr(seg_list_right, 'segments', [])
        has_hitotachi = False
        for seg in segments_right:
            info = getattr(seg, 'info', {})
            seq_set = info.get('seq_set', set())
            if 1368740 in seq_set:
                has_hitotachi = True
                break
        
        if not has_hitotachi:
            return None
        
        # Check if left is a single-character word (likely kanji that could combine)
        segments_left = getattr(seg_list_left, 'segments', [])
        for seg in segments_left:
            word = getattr(seg, 'word', None)
            if word and hasattr(word, 'text'):
                text = word.text
                if len(text) == 1:
                    # Single character - check if it's kanji
                    from himotoki.characters import is_kanji
                    if is_kanji(text):
                        return Synergy(
                            description="single-kanji+hitotachi-penalty",
                            connector=" ",
                            score=-15,  # Penalty to prefer compound+たち
                            start=start,
                            end=end,
                        )
        
        return None
    
    register_penalty(penalty_hitotachi_split)
    
    # Short kana words together
    def_generic_penalty(
        name="penalty-short",
        test_left=filter_short_kana(1),
        test_right=filter_short_kana(1, except_list=['と']),
        description="short",
        score=-9,
        serial=False,
    )
    
    # Semi-final particle not at end
    def penalty_semi_final(seg_list_left: Any, seg_list_right: Any) -> Optional[Synergy]:
        from himotoki.lookup import SEMI_FINAL_PRT
        
        # Check if left has semi-final particle
        filter_fn = filter_in_seq_set(*SEMI_FINAL_PRT)
        has_semi_final = any(filter_fn(s) for s in seg_list_left.segments)
        
        if not has_semi_final:
            return None
        
        return Synergy(
            description="semi-final not final",
            connector=" ",
            score=-15,
            start=seg_list_left.end,
            end=seg_list_right.start,
        )
    
    register_penalty(penalty_semi_final)


_init_penalties()


def get_penalties(seg_list_left: Any, seg_list_right: Any) -> List[Any]:
    """
    Get penalties between two segment lists.
    
    Returns [seg_right, penalty, seg_left] if penalty applies,
    otherwise [seg_right, seg_left].
    """
    for fn in _penalty_list:
        penalty = fn(seg_list_left, seg_list_right)
        if penalty:
            return [seg_list_right, penalty, seg_list_left]
    
    return [seg_list_right, seg_list_left]


# ============================================================================
# Segfilter List and Registration
# ============================================================================

_segfilter_list: List[Callable] = []


def register_segfilter(func: Callable):
    """Register a segfilter function."""
    _segfilter_list.append(func)
    return func


def def_segfilter_must_follow(
    name: str,
    filter_left: Callable,
    filter_right: Callable,
    allow_first: bool = False,
):
    """
    Define a segfilter where filter_right MUST follow filter_left.
    
    If filter_right matches but filter_left doesn't (and we're not at the start),
    the matching segments are removed.
    """
    def classify(filter_fn: Callable, items: List) -> Tuple[List, List]:
        satisfies = []
        contradicts = []
        for item in items:
            if filter_fn(item):
                satisfies.append(item)
            else:
                contradicts.append(item)
        return satisfies, contradicts
    
    def segfilter_fn(seg_list_left: Optional[Any], seg_list_right: Any) -> List[Tuple]:
        from himotoki.lookup import SegmentList
        
        satisfies_right, contradicts_right = classify(filter_right, seg_list_right.segments)
        
        # If nothing satisfies filter_right, pass through
        if not satisfies_right:
            return [(seg_list_left, seg_list_right)]
        
        # If first position and allowed, pass through
        if allow_first and seg_list_left is None:
            return [(seg_list_left, seg_list_right)]
        
        # If not adjacent, only allow contradicts
        if seg_list_left is None or seg_list_left.end != seg_list_right.start:
            if contradicts_right:
                new_right = SegmentList(
                    segments=contradicts_right,
                    start=seg_list_right.start,
                    end=seg_list_right.end,
                    matches=seg_list_right.matches,
                )
                return [(seg_list_left, new_right)]
            return []
        
        # Check left side
        satisfies_left, contradicts_left = classify(filter_left, seg_list_left.segments)
        
        results = []
        
        # If left has contradicts, allow those with right contradicts
        if contradicts_left and contradicts_right:
            results.append((
                seg_list_left,
                SegmentList(
                    segments=contradicts_right,
                    start=seg_list_right.start,
                    end=seg_list_right.end,
                    matches=seg_list_right.matches,
                ),
            ))
        
        # If left satisfies, allow with right satisfies
        if satisfies_left:
            results.append((
                SegmentList(
                    segments=satisfies_left,
                    start=seg_list_left.start,
                    end=seg_list_left.end,
                    matches=seg_list_left.matches,
                ),
                SegmentList(
                    segments=satisfies_right,
                    start=seg_list_right.start,
                    end=seg_list_right.end,
                    matches=seg_list_right.matches,
                ),
            ))
        
        if not results and contradicts_right:
            results.append((
                seg_list_left,
                SegmentList(
                    segments=contradicts_right,
                    start=seg_list_right.start,
                    end=seg_list_right.end,
                    matches=seg_list_right.matches,
                ),
            ))
        
        return results if results else [(seg_list_left, seg_list_right)]
    
    register_segfilter(segfilter_fn)
    return segfilter_fn


# Define segfilters
def _init_segfilters():
    """Initialize all segfilter definitions."""
    
    # Auxiliary verbs must follow continuative form
    AUX_VERBS = {1342560}  # 初める/そめる
    def_segfilter_must_follow(
        name="segfilter-aux-verb",
        filter_left=filter_is_conjugation(13),  # Continuative
        filter_right=filter_in_seq_set(*AUX_VERBS),
    )
    
    # いる must not follow 終わる (つ + いる conflict)
    def_segfilter_must_follow(
        name="segfilter-tsu-iru",
        filter_left=lambda s: not filter_in_seq_set(2221640)(s),
        filter_right=filter_in_seq_set(1577980),  # いる
        allow_first=True,
    )
    
    # ん/んだ must not follow simple particles
    def_segfilter_must_follow(
        name="segfilter-n",
        filter_left=lambda s: not filter_in_seq_set_simple(*NOUN_PARTICLES)(s),
        filter_right=filter_in_seq_set(2139720, 2849370, 2849387),  # ん, んだ
        allow_first=True,
    )
    
    # を + 枯らす
    def_segfilter_must_follow(
        name="segfilter-wokarasu",
        filter_left=filter_in_seq_set(2029010),  # を
        filter_right=filter_in_seq_set(2087020),
    )
    
    # Bad endings
    def_segfilter_must_follow(
        name="segfilter-badend",
        filter_left=lambda s: False,
        filter_right=filter_is_compound_end_text("ちゃい", "いか", "とか", "とき", "い"),
    )
    
    # じゃない must not follow は compound
    def_segfilter_must_follow(
        name="segfilter-janai",
        filter_left=lambda s: not filter_is_compound_end(2028920)(s),
        filter_right=filter_in_seq_set(1529520, 1296400, 2139720),  # ない, ある, ん
        allow_first=True,
    )
    
    # だ + する (dashi problem)
    def segfilter_dashi_fn(seg_list_left: Optional[Any], seg_list_right: Any) -> List[Tuple]:
        from himotoki.lookup import SegmentList
        
        # Right must be する/して/し
        filter_right = filter_in_seq_set(1157170, 2424740, 1305070)
        satisfies_right = [s for s in seg_list_right.segments if filter_right(s)]
        contradicts_right = [s for s in seg_list_right.segments if not filter_right(s)]
        
        if not satisfies_right:
            return [(seg_list_left, seg_list_right)]
        
        if seg_list_left is None:
            return [(seg_list_left, seg_list_right)]
        
        # Left must not be だ without で
        def left_ok(s):
            info = getattr(s, 'info', {})
            seq_set = info.get('seq_set', [])
            if 2089020 not in seq_set:  # だ
                return True
            if 2028980 in seq_set:  # で
                return True
            return False
        
        satisfies_left = [s for s in seg_list_left.segments if left_ok(s)]
        
        if satisfies_left:
            return [(seg_list_left, seg_list_right)]
        
        if contradicts_right:
            return [(
                seg_list_left,
                SegmentList(
                    segments=contradicts_right,
                    start=seg_list_right.start,
                    end=seg_list_right.end,
                    matches=seg_list_right.matches,
                ),
            )]
        
        return []
    
    register_segfilter(segfilter_dashi_fn)
    
    # Honorifics must follow noun-like words
    HONORIFICS = {1247260}  # 君
    def_segfilter_must_follow(
        name="segfilter-honorific",
        filter_left=lambda s: not filter_in_seq_set(*NOUN_PARTICLES)(s),
        filter_right=filter_in_seq_set(*HONORIFICS),
    )


_init_segfilters()


def apply_segfilters(seg_left: Optional[Any], seg_right: Any) -> List[Tuple]:
    """
    Apply all segfilters to a pair of segment lists.
    
    Returns list of (seg_left, seg_right) pairs that pass all filters.
    """
    splits = [(seg_left, seg_right)]
    
    for segfilter in _segfilter_list:
        new_splits = []
        for seg_l, seg_r in splits:
            new_splits.extend(segfilter(seg_l, seg_r))
        splits = new_splits
    
    return splits
