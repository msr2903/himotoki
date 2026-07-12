"""
Output formatting: WordInfo, JSON, and text output.
"""

from himotoki.output.types import *  # noqa: F401,F403
from himotoki.output.meanings import (  # noqa: F401
    reading_str,
    get_entry_reading,
    get_kana_for_entry,
    get_matching_kana_for_kanji,
    get_cached_meanings,
    cache_meanings,
    clear_meanings_cache,
    ReadingsCache,
    collect_seqs_from_path,
    word_info_reading_str,
    has_conjugable_pos,
    get_senses_raw,
    get_senses,
    get_root_seq,
    get_senses_str,
    get_senses_json,
    conj_prop_json,
    conj_info_json,
    populate_meanings,
)
from himotoki.output.word_info import (  # noqa: F401
    word_info_from_word_match,
    word_info_from_segment,
    word_info_from_segment_list,
    word_info_from_text,
    fill_segment_path,
)
from himotoki.output.conjugation_display import (  # noqa: F401
    format_conjugation_info,
    _get_conjugation_display,
    _get_compound_display,
    _extract_suffix,
    _build_conj_chain,
    _collect_via_steps,
    _get_conj_suffix,
    _split_neg_suffix,
)
from himotoki.output.format import (  # noqa: F401
    word_info_gloss_json,
    dict_segment,
    simple_segment,
    segment_to_json,
    segment_to_text,
)
from himotoki.constants import get_conj_description  # noqa: F401

