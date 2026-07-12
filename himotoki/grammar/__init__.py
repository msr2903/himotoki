"""
Grammar rules: synergies, suffixes, splits, counters.
"""

from himotoki.grammar.counters import *  # noqa: F401,F403
from himotoki.grammar.splits import *  # noqa: F401,F403
from himotoki.grammar.synergies import (  # noqa: F401
    Synergy,
    get_synergies,
    get_penalties,
    apply_segfilters,
    get_segment_score_synergy,
    register_synergy,
    register_penalty,
    register_segfilter,
    def_generic_synergy,
    def_generic_penalty,
    def_segfilter_must_follow,
)
from himotoki.grammar.synergy_filters import (  # noqa: F401
    filter_is_noun,
    filter_is_pos,
    filter_in_seq_set,
    filter_in_seq_set_simple,
    filter_is_conjugation,
    filter_is_compound_end,
    filter_is_compound_end_text,
    filter_short_kana,
)
from himotoki.grammar.suffixes import (  # noqa: F401
    init_suffixes,
    is_suffix_cache_ready,
    find_word_suffix,
    could_have_suffix,
    get_suffix_description,
    SUFFIX_SCORES,
    SUFFIX_CONNECTORS,
)
from himotoki.constants import NOUN_PARTICLES  # noqa: F401

