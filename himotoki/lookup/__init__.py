"""
Word lookup and scoring module for himotoki.
Ports ichiran's dict.lisp word lookup and scoring functionality.

This module provides:
- find_word: Database lookup for words
- calc_score: Complex scoring algorithm for word segments
- Segment/SegmentList: Data structures for word matches
- Length multipliers and scoring coefficients
"""

# Types
from himotoki.types import (
    ConjData,
    WordMatch,
    CompoundWord,
    adjoin_word,
    Segment,
    SegmentList,
)

# Lookup constants
from himotoki.lookup.constants import (
    POS_WITH_CONJ_RULES,
    SUPPRESS_SINGLE_TOKEN_SEQS,
    CONJ_ADVERBIAL,
    CONJ_ADJECTIVE_STEM,
    CONJ_NEGATIVE_STEM,
    CONJ_CAUSATIVE_SU,
    CONJ_ADJECTIVE_LITERARY,
    CONJ_TYPE_NAMES,
    WEAK_CONJ_FORMS,
    SKIP_CONJ_FORMS,
    CONJ_VOLITIONAL,
    CONJ_TE,
    CONJ_POTENTIAL,
    CONJ_IMPERATIVE,
)

# Word lookup
from himotoki.lookup.find_word import (
    find_word,
    find_word_as_hiragana,
    find_word_full,
    find_word_with_conj_prop,
    find_word_with_conj_type,
)

# Conjugation data
from himotoki.lookup.conj_data import (
    BLOCKED_CONJUGATIONS,
    get_conj_data,
    get_word_conj_data,
    get_conj_type_name,
    get_conj_neg,
    get_conj_fml,
    get_source_text,
)

# Scoring (re-exported for backward compatibility)
from himotoki.scoring import (
    LRUCache,
    _CONJ_DATA_CACHE,
    _POS_SEQ_CACHE,
    _UK_CACHE,
    _WORD_CACHE,
    _ENTRY_CACHE,
    _ARCHAIC_CACHE,
    preload_scoring_caches,
    get_cached_entry,
    build_archaic_cache,
    is_arch,
    is_prefer_kana,
    get_non_arch_posi,
    MAX_WORD_LENGTH,
    SCORE_CUTOFF,
    GAP_PENALTY,
    LENGTH_COEFF_SEQUENCES,
    IDENTICAL_WORD_SCORE_CUTOFF,
    SKIP_WORDS,
    COPULAE,
    NO_KANJI_BREAK_PENALTY,
    FINAL_PRT,
    SEMI_FINAL_PRT,
    NON_FINAL_PRT,
    SEQ_SCORE_BONUS,
    length_multiplier,
    length_multiplier_coeff,
    matches_conj_form,
    skip_by_conj_data,
    is_weak_conj_form,
    compare_common,
    kanji_break_penalty,
    calc_score,
    determine_primary_full,
    get_original_text_data,
    apply_score_mod,
    get_entry_posi,
    determine_primary,
    get_original_text_common,
    cull_segments,
    gen_score,
    gap_penalty,
)

__all__ = [
    # Types
    'ConjData', 'WordMatch', 'CompoundWord', 'adjoin_word', 'Segment', 'SegmentList',
    # Constants
    'POS_WITH_CONJ_RULES', 'SUPPRESS_SINGLE_TOKEN_SEQS',
    'CONJ_ADVERBIAL', 'CONJ_ADJECTIVE_STEM', 'CONJ_NEGATIVE_STEM',
    'CONJ_CAUSATIVE_SU', 'CONJ_ADJECTIVE_LITERARY',
    'CONJ_TYPE_NAMES', 'WEAK_CONJ_FORMS', 'SKIP_CONJ_FORMS',
    'CONJ_VOLITIONAL', 'CONJ_TE', 'CONJ_POTENTIAL', 'CONJ_IMPERATIVE',
    'MAX_WORD_LENGTH', 'SCORE_CUTOFF', 'GAP_PENALTY', 'LENGTH_COEFF_SEQUENCES',
    'IDENTICAL_WORD_SCORE_CUTOFF', 'SKIP_WORDS', 'COPULAE', 'NO_KANJI_BREAK_PENALTY',
    'FINAL_PRT', 'SEMI_FINAL_PRT', 'NON_FINAL_PRT', 'SEQ_SCORE_BONUS',
    # Lookup
    'find_word', 'find_word_as_hiragana', 'find_word_full',
    'find_word_with_conj_prop', 'find_word_with_conj_type',
    'BLOCKED_CONJUGATIONS', 'get_conj_data', 'get_word_conj_data',
    'get_conj_type_name', 'get_conj_neg', 'get_conj_fml', 'get_source_text',
    # Scoring
    'LRUCache', '_CONJ_DATA_CACHE', '_POS_SEQ_CACHE', '_UK_CACHE',
    '_WORD_CACHE', '_ENTRY_CACHE', '_ARCHAIC_CACHE',
    'preload_scoring_caches', 'get_cached_entry', 'build_archaic_cache',
    'is_arch', 'is_prefer_kana', 'get_non_arch_posi',
    'length_multiplier', 'length_multiplier_coeff',
    'matches_conj_form', 'skip_by_conj_data', 'is_weak_conj_form',
    'compare_common', 'kanji_break_penalty', 'calc_score',
    'determine_primary_full', 'get_original_text_data',
    'apply_score_mod', 'get_entry_posi', 'determine_primary',
    'get_original_text_common', 'cull_segments', 'gen_score', 'gap_penalty',
]
