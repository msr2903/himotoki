"""
Scoring algorithm for word segments.
"""

import math
from typing import Optional, List, Dict, Tuple, Union, Any, Set, Callable

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from himotoki.db.models import (
    Entry, KanjiText, KanaText, Sense, SenseProp, ConjProp,
)
from himotoki.characters import (
    has_kanji, mora_length, count_char_class,
)
from himotoki.types import (
    ConjData, WordMatch, CompoundWord, Segment, _is_counter_text,
)
from himotoki.scoring.caches import (
    get_cached_entry, is_arch, is_prefer_kana, get_non_arch_posi,
)
from himotoki.lookup.conj_data import get_conj_data, get_word_conj_data
from himotoki.lookup.constants import SKIP_CONJ_FORMS, WEAK_CONJ_FORMS, SUPPRESS_SINGLE_TOKEN_SEQS

# ============================================================================
# Scoring Constants (ported from ichiran's dict-errata.lisp)
# ============================================================================

# Maximum word length to search for
MAX_WORD_LENGTH = 50

# Score cutoff - words below this score are filtered out
# This must filter out ONLY bad kana spellings, and NOT filter out any kanji spellings
SCORE_CUTOFF = 5

# Length coefficient sequences (from ichiran's *length-coeff-sequences*)
# Format: coefficient for mora length 1, 2, 3, 4, 5...
LENGTH_COEFF_SEQUENCES = {
    'strong': [0, 1, 8, 24, 40, 60],  # Index 0 unused, 1-based
    'weak': [0, 1, 4, 9, 16, 25, 36],
    'tail': [0, 4, 9, 16, 24],
    'ltail': [0, 4, 12, 18, 24],
}

IDENTICAL_WORD_SCORE_CUTOFF = 0.5
GAP_PENALTY = -500
COPULAE: Set[int] = {2089020, 1628500}  # だ, です
SKIP_WORDS: Set[int] = {
    2458040,   # てもいい
    2822120,   # ても良い
    2013800,   # ちゃう
    2108590,   # とく
    2029040,   # ば
    2428180,   # い
    2654250,   # た
    2561100,   # うまいな
    2210270,   # ませんか
    2210710,   # ましょうか
    2257550,   # ない
    2210320,   # ません
    2017560,   # たい
    2394890,   # とる
    2194000,   # であ
    2568000,   # れる/られる
    2537250,   # しようとする
    2760890,   # 三箱
    2831062,   # てる
    2831063,   # てく
    2029030,   # ものの
    2568020,   # せる
    900000,    # たそう (custom)
    11553382,  # となら (continuative of となる "to become") — always と+なら
    11566952,  # となら (continuative of となる "to neighbor") — always と+なら
    2862334,   # 振り出しに戻る - prefer component words (振り出し + に + 戻る)
    1881690,   # 写真を撮る - prefer component words (写真 + を + 撮る)
    2860921,   # 家を出る - prefer component words (家 + を + 出る)
    2862924,   # 悪口(あっこう) - prefer わるぐち reading (seq 1575730)
    10551045,  # 為し(なし) - prefer 無し adjective (seq 1529560)
    10456682,  # 成し(なし) - prefer 無し adjective (seq 1529560)
    1465580,   # 入る(いる) - prefer はいる reading (seq 1465590)
    1751450,   # 精霊(しょうりょう) - prefer せいれい reading (seq 1380230)
    2657130,   # 止まる(とどまる) - prefer とまる reading (seq 1310620)
    2838238,   # こうぜ(校是) - obscure word, clashes with こう+ぜ (volitional+particle)
    2260200,   # にい(新) - uncommon kana reading, clashes with に+い verb patterns
    2254970,   # にい(兄) - uncommon kana reading, clashes with に+い verb patterns
    1774770,   # から傘(からかさ) - uncommon, clashes with から(because)+傘(umbrella)
    10253059,  # うける(浮く potential) - always prefer 受ける (seq 1329590) reading
}
FINAL_PRT: Set[int] = {
    2017770,   # かい
    2425930,   # なの
    2130430,   # け っけ
    2029130,   # ぞ
    2834812,   # ぜ
    2718360,   # がな
    2201380,   # わい
    2722170,   # のう
    2751630,   # かいな
}

# Semi-final particles - final, but also have other uses
# From ichiran's *semi-final-prt* (which includes *final-prt*)
SEMI_FINAL_PRT: Set[int] = FINAL_PRT | {
    2029120,   # さ
    2086640,   # し
    2029110,   # な
    2029080,   # ね
    2029100,   # わ
}

# Non-final particles - don't get final bonus
# From ichiran's *non-final-prt*
NON_FINAL_PRT: Set[int] = {
    2139720,   # ん
}
NO_KANJI_BREAK_PENALTY: Set[int] = {
    1169870,   # 飲む
    1198360,   # 会議
    1277450,   # 好き
    2028980,   # で
    1423000,   # 着る
    1164690,   # 一段
    1587040,   # 言う
    2827864,   # なので
}
SEQ_SCORE_BONUS: Dict[int, int] = {
    10044695: 10,  # でしょう (conjugated copula) over spurious 〜で + しょうか paths
}

def length_multiplier(length: int, power: float, len_lim: int) -> float:
    """
    Calculate length multiplier: len^power until len_lim, linear after.
    
    Args:
        length: Word length in mora
        power: Exponent to use
        len_lim: Limit after which growth becomes linear
    
    Returns:
        The multiplier value
    """
    if length <= len_lim:
        return length ** power
    return length * (len_lim ** (power - 1))


def length_multiplier_coeff(length: int, coeff_class: str) -> int:
    """
    Get length multiplier from coefficient sequence.
    
    Args:
        length: Word length in mora (1-based)
        coeff_class: One of 'strong', 'weak', 'tail', 'ltail'
    
    Returns:
        The coefficient value for this length
    """
    coeffs = LENGTH_COEFF_SEQUENCES.get(coeff_class)
    if not coeffs:
        return length
    
    if 0 < length < len(coeffs):
        return coeffs[length]
    
    # Linear extrapolation for lengths beyond the table
    last_coeff = coeffs[-1]
    last_idx = len(coeffs) - 1
    return length * (last_coeff // last_idx) if last_idx > 0 else length
def matches_conj_form(prop: ConjProp, forms: List[Tuple]) -> bool:
    """
    Check if a conjugation property matches any of the weak/skip forms.
    From ichiran's test-conj-prop.
    
    Args:
        prop: ConjProp object to test
        forms: List of (conj_type, neg, fml) or (pos, conj_type, neg, fml) tuples
               where None means "any value matches"
    
    Returns:
        True if prop matches any form pattern
    """
    for form in forms:
        if len(form) == 3:
            # (conj_type, neg, fml) format
            pattern = [prop.conj_type, prop.neg, prop.fml]
            if all(
                r is None or l == r
                for l, r in zip(pattern, form)
            ):
                return True
        elif len(form) == 4:
            # (pos, conj_type, neg, fml) format
            if form[0] == prop.pos:
                pattern = [prop.conj_type, prop.neg, prop.fml]
                if all(
                    r is None or l == r
                    for l, r in zip(pattern, form[1:])
                ):
                    return True
    return False


def skip_by_conj_data(conj_data: List[ConjData]) -> bool:
    """
    Check if conjugation data should be skipped entirely.
    From ichiran's skip-by-conj-data.
    
    Returns True if ALL conjugation data matches skip patterns.
    """
    if not conj_data:
        return False
    
    return all(
        cd.prop is not None and matches_conj_form(cd.prop, SKIP_CONJ_FORMS)
        for cd in conj_data
    )


def is_weak_conj_form(conj_data: List[ConjData]) -> bool:
    """
    Check if all conjugations are weak forms (don't contribute as much).
    """
    if not conj_data:
        return False
    
    return all(
        cd.prop is not None and matches_conj_form(cd.prop, WEAK_CONJ_FORMS)
        for cd in conj_data
    )
def compare_common(c1: Optional[int], c2: Optional[int]) -> bool:
    """
    Compare two commonness values.
    Lower is better, 0 is special (very common), None is worst.
    
    Returns True if c1 should be sorted before c2.
    """
    if c2 is None:
        return c1 is not None
    if c2 == 0:
        return c1 is not None and c1 > 0
    if c1 is not None and c1 > 0:
        return c1 < c2
    return False


def kanji_break_penalty(
    kanji_break: List[int],
    score: float,
    info: Optional[Dict] = None,
    text: str = "",
    use_length: Optional[int] = None,
    score_mod: float = 0,
) -> float:
    """
    Apply penalty for breaks within kanji sequences.
    
    Args:
        kanji_break: List of positions where kanji are broken
        score: Current score
        info: Score info dict
        text: Word text
        use_length: Context length if available
        score_mod: Score modifier
    
    Returns:
        Adjusted score
    """
    if not kanji_break:
        return score
    
    # Determine break position type
    end = 'both' if len(kanji_break) > 1 else (
        'beg' if kanji_break[0] == 0 else 'end'
    )
    
    bonus = 0
    ratio = 2
    posi = info.get('posi', []) if info else []
    
    if info:
        seq_set = info.get('seq_set', set())
        
        # Check for no-penalty words
        if seq_set & NO_KANJI_BREAK_PENALTY:
            return score
        
        # Check for special す break
        if end == 'beg' and text.startswith('す'):
            return score
        
        # Adjust bonus based on POS
        if end == 'beg' and 'num' in posi:
            bonus += 5
        elif end == 'beg' and ('suf' in posi or 'n-suf' in posi):
            bonus += 10
        elif end == 'end' and 'pref' in posi:
            bonus += 12
    
    if score >= SCORE_CUTOFF:
        return max(SCORE_CUTOFF, (score // ratio) + bonus)
    return score


def calc_score(
    session: Session,
    word: Union[WordMatch, CompoundWord],
    final: bool = False,
    use_length: Optional[int] = None,
    score_mod: float = 0,
    kanji_break: Optional[List[int]] = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate score for a word match.
    
    This is the core scoring algorithm ported from ichiran's calc-score (dict.lisp lines 777-983).
    
    The scoring system considers:
    - Word type (kanji vs kana)
    - Commonness ranking
    - Part of speech (particles get special handling)
    - Primary/secondary reading status
    - Conjugation status and type
    - Word length
    - Context length (use_length)
    - Kanji break penalties
    - Archaic word detection
    
    Args:
        session: Database session
        word: WordMatch or CompoundWord object to score
        final: True if this is at the end of the text
        use_length: Context length for scoring
        score_mod: Score modifier (for compound words)
        kanji_break: List of kanji break positions
    
    Returns:
        Tuple of (score, info_dict)
    """
    # Handle compound words by scoring the base word with compound properties
    # From ichiran dict.lisp lines 782-794
    if isinstance(word, CompoundWord):
        base_word = word.get_score_base()
        compound_score_mod = word.score_mod
        
        # Both regular compounds and abbreviation compounds use the compound
        # text's mora length for use_length. This creates a penalty when the
        # compound is shorter than the base word (negative difference in
        # length_multiplier_coeff).
        #
        # For abbreviations like とまず (3 mora) from とまない (4 mora):
        # use_length=3, base word len=4, difference=-1 → penalty applied
        compound_use_length = mora_length(word.text)
        
        score, info = calc_score(
            session, base_word,
            use_length=compound_use_length,
            score_mod=compound_score_mod,
        )
        
        # Add compound word conjugation data
        info['conj'] = get_word_conj_data(session, word)
        
        # Apply kanji break penalty if needed
        if kanji_break:
            score = kanji_break_penalty(
                kanji_break, score, 
                info=info, text=base_word.text,
                use_length=compound_use_length, score_mod=compound_score_mod
            )
        
        return score, info
    
    # Check for counter mode (CounterText objects)
    ctr_mode = _is_counter_text(word)
    
    reading = word.reading
    text = word.text
    seq = word.seq
    ord_val = word.ord
    common = word.common
    
    # Fast path: Early termination for skip words (before any DB lookups)
    # This avoids expensive entry lookups and conjugation data retrieval
    if seq in SKIP_WORDS:
        return 0, {}

    # Suppress coarse expression tokens when compositional segmentation exists.
    if seq in SUPPRESS_SINGLE_TOKEN_SEQS:
        return 0, {}
    
    # Fast path: Final particles only score at end of text
    if not final and seq in FINAL_PRT:
        return 0, {}
    
    # Get entry info - counters don't have entries
    # Use cached entry lookup for performance
    entry = None if ctr_mode else get_cached_entry(session, seq)
    if not entry and not ctr_mode:
        return 0, {}
    
    # Basic properties
    score = 1
    prop_score = 0
    
    kanji_p = word.word_type == 'kanji'
    katakana_p = not kanji_p and count_char_class(text, 'katakana') > 0
    
    n_kanji = count_char_class(text, 'kanji')
    word_len = max(1, mora_length(text))
    
    # Conjugation info - counters don't have conjugations
    conj_only = False if ctr_mode else (word.conjugations is not None and word.conjugations != 'root')
    root_p = ctr_mode or (not conj_only and entry and entry.root_p)
    
    # Get conjugation data - counters don't have conjugations
    if ctr_mode:
        conj_data = []
    elif conj_only and isinstance(word.conjugations, list):
        conj_data = get_conj_data(session, seq, conj_ids=word.conjugations, texts=[text])
    elif not word.is_root:
        conj_data = get_conj_data(session, seq, texts=[text])
    else:
        conj_data = []
    
    # Handle secondary conjugations (via forms)
    # If this is nil, delete all secondary conjugations from conj data
    secondary_conj_p = False
    if conj_data:
        if all(cd.via for cd in conj_data):
            secondary_conj_p = True
        else:
            # Remove secondary conjugations from data
            conj_data = [cd for cd in conj_data if not cd.via]
    
    conj_of = [cd.from_seq for cd in conj_data]
    conj_props = [cd.prop for cd in conj_data if cd.prop]
    conj_types = [cp.conj_type for cp in conj_props]
    
    # conj_types_p: True if not all conjugations are weak forms
    # From ichiran: "weak" forms don't contribute to scoring as much
    conj_types_p = (
        root_p or
        use_length is not None or
        not all(matches_conj_form(prop, WEAK_CONJ_FORMS) for prop in conj_props if prop)
    )
    
    # Get part-of-speech info
    seq_set = {seq} | set(conj_of) if seq else set()
    sp_seq_set = [seq] if (seq and root_p and not use_length) else list(seq_set)
    
    # For counters, use 'ctr' as the part of speech
    if ctr_mode:
        prefer_kana = False
        is_arch_p = False
        posi = {'ctr'}
    else:
        # Check for prefer kana (uk - usually written in kana) - cached
        prefer_kana = is_prefer_kana(session, sp_seq_set)
        
        # Check if all entries are archaic
        is_arch_p = is_arch(session, set(sp_seq_set))
        
        # Get part-of-speech (excluding archaic senses) - cached
        posi = get_non_arch_posi(session, seq_set)
    
    # Common properties
    common_p = common is not None
    common_of = common
    particle_p = 'prt' in posi
    semi_final_particle_p = seq in SEMI_FINAL_PRT
    non_final_particle_p = seq in NON_FINAL_PRT
    pronoun_p = 'pn' in posi
    cop_da_p = bool(seq_set & COPULAE)
    
    # Length classification (ichiran lines 836-844)
    # More complex logic based on various conditions
    if kanji_p and not prefer_kana:
        if (root_p and not conj_data) or (use_length and 13 in conj_types):
            len_threshold = 2
        elif common_p and common and 0 < common < 10:
            len_threshold = 2
        elif {3, 9} & set(conj_types) and not use_length:
            len_threshold = 4
        else:
            len_threshold = 3
    else:
        if common_p and common and 0 < common < 10:
            len_threshold = 2
        elif {3, 9} & set(conj_types) and not use_length:
            len_threshold = 4
        else:
            len_threshold = 3
    
    long_p = word_len > len_threshold
    
    # no_common_bonus conditions
    no_common_bonus = (
        particle_p or
        not conj_types_p or
        (not long_p and posi == {'int'})
    )
    
    use_length_bonus = 0
    
    # Check for skip words in conjugation chain
    # Only check the full seq_set (including conjugation sources) for DIRECT word matches,
    # not when scoring a base word from a compound (use_length is set for compounds).
    # This allows abbreviation compounds like とどまらず to score properly even though
    # their source verb (とどまる) is in SKIP_WORDS.
    if use_length is None and seq_set & SKIP_WORDS:
        return 0, {}
    elif seq in SKIP_WORDS:
        # Always skip if the direct seq is in skip words
        return 0, {}
    if not root_p and skip_by_conj_data(conj_data):
        return 0, {}
    
    # Handle inherited commonness and ord from conjugation source (ichiran lines 859-870)
    # This MUST happen BEFORE primary_p determination so that ord_val is correct
    if conj_data and not (ord_val == 0 and common_p):
        orig_texts = get_original_text_data(session, word, conj_data)
        if orig_texts:
            if not common_p:
                conj_of_common = [c for c, o in orig_texts if c is not None]
                if conj_of_common:
                    common = 0
                    common_p = True
                    # Get the "best" common value
                    common_of = sorted(conj_of_common, key=lambda c: (c or 1000, c == 0))[0]
            
            # Update ord if conjugated form has lower ord
            conj_of_ord = min(o for c, o in orig_texts)
            if conj_of_ord < ord_val:
                ord_val = conj_of_ord
    
    # Primary reading check - now with archaic consideration
    # Pass ord_val to use corrected ord from conjugation source
    primary_p = False
    if not is_arch_p:
        primary_p = determine_primary_full(
            session, entry, word, posi, common_p, kanji_p,
            root_p, conj_data, prefer_kana, conj_types_p, cop_da_p, pronoun_p,
            ord_override=ord_val
        )
    
    # Calculate base score (ichiran lines 890-925)
    if primary_p:
        if long_p:
            score += 10
        elif secondary_conj_p and not kanji_p:
            score += 2
        elif common_p and conj_types_p:
            score += 5
        elif prefer_kana or not entry or entry.n_kanji == 0:
            score += 3
        else:
            score += 2
    
    # Particle bonus (lines 896-902)
    if particle_p and (final or not semi_final_particle_p):
        score += 2
        if common_p:
            score += 2 + word_len
        if final and not non_final_particle_p:
            if primary_p:
                score += 5
            elif semi_final_particle_p:
                score += 2
    
    # Commonness bonus (lines 903-918)
    if common_p and not no_common_bonus:
        if secondary_conj_p and not use_length:
            common_bonus = 4 if (kanji_p and primary_p) else 2
        elif long_p or cop_da_p or (root_p and (kanji_p or (primary_p and word_len > 2))):
            if common == 0:
                common_bonus = 10
            elif not primary_p:
                common_bonus = max(15 - (common or 0), 10)
            else:
                common_bonus = max(20 - (common or 0), 10)
        elif kanji_p:
            common_bonus = 8
        elif primary_p:
            common_bonus = 4
        elif word_len > 2 or (common and 0 < common < 10):
            common_bonus = 3
        else:
            common_bonus = 2
        
        # Reduce bonus for continuative form (conj_type 10)
        if common_bonus >= 10 and 10 in conj_types:
            common_bonus -= 4
        
        score += common_bonus
    
    # Length and kanji bonuses (lines 919-926)
    if long_p:
        score = max(word_len, score)
    
    if kanji_p:
        score = max(3 if is_arch_p else 5, score)
        if long_p and (n_kanji > 1 or word_len > 4):
            score += 2
    
    # Counter mode minimum score (ichiran line 926: (when ctr-mode (setf score (max 5 score))))
    if ctr_mode:
        score = max(5, score)

    # Entry-specific score adjustments
    score += SEQ_SCORE_BONUS.get(seq, 0)
    
    # Calculate prop_score and apply length multiplier (lines 927-937)
    prop_score = score
    length_class = 'strong' if (kanji_p or katakana_p) else 'weak'
    score = prop_score * (
        length_multiplier_coeff(word_len, length_class) +
        ((n_kanji - 1) * 5 if n_kanji > 1 else 0)
    )
    
    # Split scoring integration (ichiran lines 927-970)
    # Check for split definition and apply split scoring
    # Note: counters don't use split scoring (ichiran: (unless ctr-mode ...))
    split_info = None
    if not ctr_mode:
        from himotoki.splits import get_split
        split_result = get_split(session, word, conj_of if conj_of else None)
        
        if split_result:
            if ':score' in split_result.modifiers:
                # Direct score addition mode
                score += split_result.score_bonus
                split_info = ('score', split_result.score_bonus)
            elif ':pscore' in split_result.modifiers:
                # Proportional score modification mode
                import math
                new_prop_score = max(1, prop_score + split_result.score_bonus)
                score = math.ceil(score * new_prop_score / prop_score) if prop_score > 0 else score
                prop_score = new_prop_score
                split_info = ('pscore', split_result.score_bonus)
            else:
                # Standard split: sum of part scores + bonus
                split_score = split_result.score_bonus
                part_scores = []
                for i, part in enumerate(split_result.parts):
                    is_last = (i == len(split_result.parts) - 1)
                    # Calculate adjusted use_length for final part
                    part_use_length = None
                    if is_last and use_length:
                        # Subtract mora lengths of preceding parts
                        preceding_mora = sum(
                            mora_length(p.text) for p in split_result.parts[:-1]
                        )
                        part_use_length = use_length - preceding_mora
                    
                    part_score, _ = calc_score(
                        session, part.reading,
                        final=final and is_last,
                        use_length=part_use_length,
                        score_mod=score_mod if is_last else 0,
                    )
                    part_scores.append(part_score)
                    split_score += part_score
                
                score = split_score
                split_info = ('split', split_result.score_bonus, part_scores)
    
    # Apply use_length bonus for context
    if use_length:
        tail_len = use_length - word_len
        tail_class = 'ltail' if (word_len > 3 and (kanji_p or katakana_p)) else 'tail'
        use_length_bonus = prop_score * length_multiplier_coeff(tail_len, tail_class)
        
        if score_mod:
            use_length_bonus += apply_score_mod(score_mod, prop_score, tail_len)
        
        score += use_length_bonus
    
    # Build info dict
    info = {
        'posi': list(posi),
        'seq_set': seq_set,
        'conj': conj_data,
        'common': common_of if common_p else None,
        'score_info': [prop_score, kanji_break, use_length_bonus, split_info],
        'kpcl': [kanji_p or katakana_p, primary_p, common_p, long_p],
    }
    
    # Apply kanji break penalty
    if kanji_break:
        score = kanji_break_penalty(
            kanji_break, score,
            info=info, text=text,
            use_length=use_length, score_mod=score_mod
        )
    
    return score, info


def determine_primary_full(
    session: Session,
    entry: Entry,
    word: WordMatch,
    posi: Set[str],
    common_p: bool,
    kanji_p: bool,
    root_p: bool,
    conj_data: List[ConjData],
    prefer_kana: bool,
    conj_types_p: bool,
    cop_da_p: bool,
    pronoun_p: bool,
    ord_override: Optional[int] = None,
) -> bool:
    """
    Full primary reading determination from ichiran lines 872-888.
    More complete than the simple version.
    
    Args:
        ord_override: If provided, use this ord value instead of word.ord.
                     This is used when the ord has been corrected based on
                     conjugation source data.
    """
    if not entry:
        return True
    
    # Use overridden ord if provided, otherwise use word.ord
    ord_val = ord_override if ord_override is not None else word.ord
    
    # Prefer kana and this is kana reading
    if prefer_kana and conj_types_p and not kanji_p:
        if not entry.primary_nokanji:
            return True
        # Check nokanji flag on reading
        if hasattr(word.reading, 'nokanji') and word.reading.nokanji:
            return True
        # Additional case: common hiragana word with ord=0 should be primary
        # This handles words like きれい that are commonly written in kana
        # but don't have the nokanji flag on the hiragana reading
        if ord_val == 0 and common_p and (word.common == 0 or (word.common is not None and word.common < 10)):
            return True
    
    # Primary if ord=0 or copula
    if ord_val == 0 or cop_da_p:
        if (kanji_p or conj_types_p) and (
            (kanji_p and not prefer_kana) or
            (common_p and pronoun_p) or
            entry.n_kanji == 0
        ):
            return True
    
    # Special case: prefer_kana with kanji, ord=0, but uk is not for first sense
    if prefer_kana and kanji_p and ord_val == 0:
        # Check if uk prop is for ord=0 sense
        first_sense_uk = session.execute(
            select(SenseProp)
            .join(Sense, SenseProp.sense_id == Sense.id)
            .where(and_(
                Sense.seq == entry.seq,
                Sense.ord == 0,
                SenseProp.tag == 'misc',
                SenseProp.text == 'uk'
            ))
        ).scalars().first()
        if not first_sense_uk:
            return True
    
    return False


def get_original_text_data(
    session: Session,
    word: WordMatch,
    conj_data: List[ConjData],
) -> List[Tuple[Optional[int], int]]:
    """
    Get (common, ord) pairs from original (unconjugated) text.
    
    Ports ichiran's get-original-text* function from dict.lisp.
    Extended from get_original_text_common to also return ord.
    
    For secondary conjugations (via forms), this function recursively
    follows the conjugation chain to find the original source text.
    
    Args:
        session: Database session
        word: WordMatch object to get original text for
        conj_data: List of ConjData objects for the word
    
    Returns:
        List of (common, ord) tuples from the original source forms
    """
    return _get_original_text_data_recursive(session, conj_data, [word.text])


def _get_original_text_data_recursive(
    session: Session,
    conj_data: List[ConjData],
    texts: List[str],
) -> List[Tuple[Optional[int], int]]:
    """
    Recursive helper for get_original_text_data.
    
    Follows the conjugation chain through via forms to find the
    ultimate source text and its properties.
    
    Args:
        session: Database session
        conj_data: List of ConjData objects
        texts: List of text forms to look up
    
    Returns:
        List of (common, ord) tuples from the original source forms
    """
    result = []
    for cd in conj_data:
        # Find matching source texts from src_map
        src_texts = []
        for text, src_text in cd.src_map:
            if text in texts:
                src_texts.append(src_text)
        
        if not src_texts:
            continue
        
        if cd.via is None:
            # Direct conjugation - look up the source text in from_seq
            for src_text in src_texts:
                table = KanjiText if has_kanji(src_text) else KanaText
                orig = session.execute(
                    select(table)
                    .where(and_(table.seq == cd.from_seq, table.text == src_text))
                ).scalars().first()
                if orig:
                    result.append((orig.common, orig.ord))
        else:
            # Secondary conjugation (via form) - recursively follow the chain
            # Get conjugation data from via -> from_seq
            via_conj_data = get_conj_data(session, cd.via, from_seq=cd.from_seq)
            if via_conj_data:
                result.extend(_get_original_text_data_recursive(
                    session, via_conj_data, src_texts
                ))
    
    return result


def apply_score_mod(
    score_mod: Union[int, float, callable, List],
    score: float,
    length: int,
) -> float:
    """Apply score modifier."""
    if callable(score_mod):
        return score_mod(score)
    if isinstance(score_mod, list):
        return sum(apply_score_mod(sm, score, length) for sm in score_mod)
    return score * score_mod * length


def get_entry_posi(session: Session, seq_set: Set[int]) -> Set[str]:
    """Get part-of-speech tags for entries."""
    query = (
        select(SenseProp.text)
        .where(and_(
            SenseProp.seq.in_(seq_set),
            SenseProp.tag == 'pos'
        ))
        .distinct()
    )
    results = session.execute(query).scalars().all()
    return set(results)


def determine_primary(
    session: Session,
    entry: Entry,
    word: WordMatch,
    posi: Set[str],
    common_p: bool,
    kanji_p: bool,
    root_p: bool,
    conj_data: List[ConjData],
) -> bool:
    """Determine if this is the primary reading for the entry."""
    if not entry:
        return True
    
    # Check for uk (usually kana) preference
    prefer_kana = session.execute(
        select(SenseProp)
        .where(and_(
            SenseProp.seq == entry.seq,
            SenseProp.tag == 'misc',
            SenseProp.text == 'uk'
        ))
    ).scalars().first() is not None
    
    if prefer_kana and not kanji_p and word.ord == 0:
        return True
    
    # Primary if ord=0 and kanji form or no kanji exists
    if word.ord == 0:
        if kanji_p or entry.n_kanji == 0:
            return True
    
    # Check for pronoun with common reading
    if common_p and 'pn' in posi and word.ord == 0:
        return True
    
    return False


def get_original_text_common(
    session: Session,
    word: WordMatch,
    conj_data: List[ConjData],
) -> Optional[int]:
    """Get commonness from original (unconjugated) text."""
    for cd in conj_data:
        for text, src_text in cd.src_map:
            if text == word.text:
                # Look up the source text
                table = KanjiText if has_kanji(src_text) else KanaText
                orig = session.execute(
                    select(table)
                    .where(and_(table.seq == cd.from_seq, table.text == src_text))
                ).scalars().first()
                if orig and orig.common is not None:
                    return orig.common
    return None
def cull_segments(segments: List[Segment]) -> List[Segment]:
    """
    Filter segments to remove low-scoring duplicates.
    
    Keeps segments scoring at least IDENTICAL_WORD_SCORE_CUTOFF of the max.
    Sorts by score descending, then by commonness ascending.
    """
    if not segments:
        return segments
    
    # Sort by score descending, then by commonness ascending
    # Note: common=0 is the best (most common), so we need to handle it specially
    # since 0 is falsy in Python
    def get_common_key(s):
        common = s.info.get('common') if s.info else None
        if common is None:
            return float('inf')
        return common
    
    segments = sorted(
        segments,
        key=lambda s: (
            -s.score,  # Score descending (higher is better)
            get_common_key(s),  # Commonness ascending (lower is better)
        )
    )
    
    max_score = max(s.score for s in segments)
    cutoff = max_score * IDENTICAL_WORD_SCORE_CUTOFF
    
    # Protect suffix compounds from culling — they carry grammar chain info
    # that dict entries don't have, even when their score is lower
    return [s for s in segments if s.score >= cutoff
            or getattr(s.word, 'is_compound', False)]


def gen_score(
    session: Session,
    segment: Segment,
    final: bool = False,
    kanji_break: Optional[List[int]] = None,
) -> Segment:
    """Generate score for a segment."""
    score, info = calc_score(
        session, segment.word,
        final=final, kanji_break=kanji_break
    )
    segment.score = score
    # Preserve counter flag if it was set
    if segment.info and segment.info.get('counter'):
        info['counter'] = True
    segment.info = info
    return segment


# ============================================================================
# Path Finding Utilities
# ============================================================================

def gap_penalty(start: int, end: int) -> int:
    """Calculate penalty for ungapped text."""
    return (end - start) * GAP_PENALTY
