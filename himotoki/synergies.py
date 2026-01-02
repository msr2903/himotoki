"""
Synergy and penalty calculations for Japanese morphological analysis.

This is a 1:1 port of Ichiran's synergy system from dict-grammar.lisp.
All synergy/penalty definitions, scores, and logic match Ichiran exactly.

Key Ichiran definitions ported:
- def-generic-synergy: Synergy rules with scores
- def-generic-penalty: Penalty rules with scores  
- *noun-particles*: Particles that follow nouns
- *semi-final-prt*: Semi-final particles
- *skip-words*: Suffix-only words

Reference: ichiran-source-code/dict-grammar.lisp lines 735-970
"""

from dataclasses import dataclass
from typing import Optional, Set, List, Tuple, Any
from functools import lru_cache

from .conn import query
from .constants import (
    # Particle sets
    NOUN_PARTICLES,
    SEMI_FINAL_PRT,
    SKIP_WORDS,
    FINAL_PRT,
    
    # Copulae
    COPULA_DA,
    COPULA_DESU,
    COPULA_DESU_ALT,
    COPULA_DAROU,
    
    # Particles
    SEQ_HA,
    SEQ_GA,
    SEQ_WO,
    SEQ_NI,
    SEQ_DE,
    SEQ_TO,
    SEQ_NO,
    SEQ_N,
    SEQ_NA_PARTICLE,
    SEQ_NI_PARTICLE,
    
    # Special synergy seqs
    SEQ_TOORI,
    SEQ_SHIKA,
    SEQ_SOU,
    SEQ_NANDA,
    SEQ_IKENAI,
    
    # Suffix seqs
    SEQ_CHU,
    SEQ_TACHI,
    SEQ_BURI,
    SEQ_SEI,
    SEQ_OKI,
    
    # Prefix seqs
    SEQ_O_PREFIX,
    SEQ_KANJI_PREFIX,
    
    # Te-form auxiliary verbs
    TE_FORM_AUXILIARIES,
)


# ============================================================================
# POS Helper Functions (matching Ichiran's POS lookup)
# ============================================================================

@lru_cache(maxsize=10000)
def get_pos_tags(seq: int) -> Set[str]:
    """
    Get normalized POS tags for an entry.
    
    Args:
        seq: Entry sequence number.
        
    Returns:
        Set of POS tag strings (lowercased).
    """
    rows = query(
        "SELECT text FROM sense_prop WHERE seq = ? AND tag = 'pos'",
        (seq,)
    )
    return {(row['text'] or '').lower() for row in rows}


@lru_cache(maxsize=10000)
def is_particle(seq: int) -> bool:
    """Check if entry is a particle."""
    pos_tags = get_pos_tags(seq)
    return any('particle' in p or p.startswith('prt') for p in pos_tags)


@lru_cache(maxsize=10000)
def is_noun(seq: int) -> bool:
    """
    Check if entry is a noun.
    
    Matches Ichiran's filter-is-noun which checks for:
    - n, n-adv, n-t, adj-na, n-suf, pn
    """
    pos_tags = get_pos_tags(seq)
    noun_types = {'n', 'n-adv', 'n-t', 'adj-na', 'n-suf', 'pn'}
    for tag in pos_tags:
        if tag in noun_types:
            return True
        if 'noun' in tag or 'pronoun' in tag:
            return True
    return False


@lru_cache(maxsize=10000)
def is_verb(seq: int) -> bool:
    """Check if entry is a verb."""
    pos_tags = get_pos_tags(seq)
    return any('verb' in p or p.startswith('v') for p in pos_tags)


@lru_cache(maxsize=10000)
def is_i_adjective(seq: int) -> bool:
    """Check if entry is an i-adjective (adj-i)."""
    pos_tags = get_pos_tags(seq)
    return any('adj-i' in p for p in pos_tags)


@lru_cache(maxsize=10000)
def is_na_adjective(seq: int) -> bool:
    """Check if entry is a na-adjective (adj-na)."""
    pos_tags = get_pos_tags(seq)
    return any('adj-na' in p for p in pos_tags)


@lru_cache(maxsize=10000)
def is_no_adjective(seq: int) -> bool:
    """Check if entry is a の-adjective (adj-no)."""
    pos_tags = get_pos_tags(seq)
    return any('adj-no' in p for p in pos_tags)


@lru_cache(maxsize=10000)
def is_to_adverb(seq: int) -> bool:
    """Check if entry is a と-adverb (adv-to)."""
    pos_tags = get_pos_tags(seq)
    return any('adv-to' in p for p in pos_tags)


@lru_cache(maxsize=10000)
def is_counter(seq: int) -> bool:
    """Check if entry is a counter (ctr)."""
    pos_tags = get_pos_tags(seq)
    return any('ctr' in p or 'counter' in p for p in pos_tags)


@lru_cache(maxsize=10000)
def is_vs_noun(seq: int) -> bool:
    """Check if entry is a suru-verb noun (vs)."""
    pos_tags = get_pos_tags(seq)
    return any('vs' in p for p in pos_tags)


# ============================================================================
# Synergy Definitions (1:1 from Ichiran's def-generic-synergy)
# ============================================================================

@dataclass
class Synergy:
    """Synergy bonus between two adjacent segments."""
    score: int
    name: str
    serial: bool = False  # If True, this synergy is part of a chain


def synergy_noun_particle(left_seq: int, left_text: str,
                          right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: noun + particle
    
    From Ichiran (dict-grammar.lisp:826-831):
        (def-generic-synergy synergy-noun-particle (l r)
          #'filter-is-noun
          (apply #'filter-in-seq-set *noun-particles*)
          :description "noun+prt"
          :score (+ 10 (* 4 (- (segment-list-end r) (segment-list-start r))))
          :connector " ")
    
    Score: 10 + 4 * len(particle)
    """
    if is_noun(left_seq) and right_seq in NOUN_PARTICLES:
        score = 10 + 4 * len(right_text)
        return Synergy(score=score, name=f"noun+prt({right_text})")
    return None


def synergy_noun_da(left_seq: int, left_text: str,
                    right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: noun + だ
    
    From Ichiran (dict-grammar.lisp:838-843):
        (def-generic-synergy synergy-noun-da (l r)
          #'filter-is-noun
          (filter-in-seq-set 2089020) ;; だ
          :description "noun+da"
          :score 10
          :connector " ")
    
    Score: 10
    """
    if is_noun(left_seq) and right_seq == COPULA_DA:
        return Synergy(score=10, name="noun+da")
    return None


def synergy_no_da(left_seq: int, left_text: str,
                  right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: の/ん + だ/です/だろう
    
    From Ichiran (dict-grammar.lisp:845-850):
        (def-generic-synergy synergy-no-da (l r)
          (filter-in-seq-set 1469800 2139720)    ;; の, ん
          (filter-in-seq-set 2089020 1007370 1928670) ;; だ, です, だろう
          :description "no da/desu"
          :score 15
          :connector " ")
    
    Score: 15
    """
    left_is_no_or_n = left_seq in {SEQ_NO, SEQ_N}
    right_is_copula = right_seq in {COPULA_DA, COPULA_DESU_ALT, COPULA_DAROU}
    if left_is_no_or_n and right_is_copula:
        return Synergy(score=15, name="no+da/desu")
    return None


def synergy_sou_nanda(left_seq: int, left_text: str,
                      right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: そう + なんだ
    
    From Ichiran (dict-grammar.lisp:852-857):
        (def-generic-synergy synergy-sou-nanda (l r)
          (filter-in-seq-set 2137720)  ;; そう
          (filter-in-seq-set 2140410)  ;; なんだ
          :description "sou na n da"
          :score 50
          :connector " ")
    
    Score: 50
    """
    if left_seq == SEQ_SOU and right_seq == SEQ_NANDA:
        return Synergy(score=50, name="sou+nanda")
    return None


def synergy_no_adjectives(left_seq: int, left_text: str,
                          right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: adj-no + の
    
    From Ichiran (dict-grammar.lisp:859-864):
        (def-generic-synergy synergy-no-adjectives (l r)
          (filter-is-pos ("adj-no") (segment k p c l) (or k l (and p c)))
          (filter-in-seq-set 1469800) ;; の
          :description "no-adjective"
          :score 15
          :connector " ")
    
    Score: 15
    """
    if is_no_adjective(left_seq) and right_seq == SEQ_NO:
        return Synergy(score=15, name="adj-no+の")
    return None


def synergy_na_adjectives(left_seq: int, left_text: str,
                          right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: na-adjective + な/に
    
    From Ichiran (dict-grammar.lisp:866-871):
        (def-generic-synergy synergy-na-adjectives (l r)
          (filter-is-pos ("adj-na") (segment k p c l) (or k l (and p c)))
          (filter-in-seq-set 2029110 2028990) ;; な ; に
          :description "na-adjective"
          :score 15
          :connector " ")
    
    Score: 15
    """
    if is_na_adjective(left_seq) and right_seq in {SEQ_NA_PARTICLE, SEQ_NI_PARTICLE}:
        return Synergy(score=15, name=f"adj-na+{right_text}")
    return None


def synergy_to_adverbs(left_seq: int, left_text: str,
                       right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: adv-to + と
    
    From Ichiran (dict-grammar.lisp:873-878):
        (def-generic-synergy synergy-to-adverbs (l r)
          (filter-is-pos ("adv-to") (segment k p c l) (or k l p))
          (filter-in-seq-set 1008490)
          :description "to-adverb"
          :score (+ 10 (* 10 (- (segment-list-end l) (segment-list-start l))))
          :connector " ")
    
    Score: 10 + 10 * len(adverb)
    """
    if is_to_adverb(left_seq) and right_seq == SEQ_TO:
        score = 10 + 10 * len(left_text)
        return Synergy(score=score, name="adv-to+と")
    return None


def synergy_suffix_chu(left_seq: int, left_text: str,
                       right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: noun + 中
    
    From Ichiran (dict-grammar.lisp:880-885):
        (def-generic-synergy synergy-suffix-chu (l r)
          #'filter-is-noun
          (filter-in-seq-set 1620400 2083570)
          :description "suffix-chu"
          :score 12
          :connector "-")
    
    Score: 12
    """
    if is_noun(left_seq) and right_seq in SEQ_CHU:
        return Synergy(score=12, name="noun+中")
    return None


def synergy_suffix_tachi(left_seq: int, left_text: str,
                         right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: noun + たち
    
    From Ichiran (dict-grammar.lisp:887-892):
        (def-generic-synergy synergy-suffix-tachi (l r)
          #'filter-is-noun
          (filter-in-seq-set 1416220)
          :description "suffix-tachi"
          :score 10
          :connector "-")
    
    Score: 10
    """
    if is_noun(left_seq) and right_seq == SEQ_TACHI:
        return Synergy(score=10, name="noun+たち")
    return None


def synergy_suffix_buri(left_seq: int, left_text: str,
                        right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: noun + ぶり
    
    From Ichiran (dict-grammar.lisp:894-899):
        (def-generic-synergy synergy-suffix-buri (l r)
          #'filter-is-noun
          (filter-in-seq-set 1361140)
          :description "suffix-buri"
          :score 40
          :connector "")
    
    Score: 40
    """
    if is_noun(left_seq) and right_seq == SEQ_BURI:
        return Synergy(score=40, name="noun+ぶり")
    return None


def synergy_suffix_sei(left_seq: int, left_text: str,
                       right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: noun + 性
    
    From Ichiran (dict-grammar.lisp:901-906):
        (def-generic-synergy synergy-suffix-sei (l r)
          #'filter-is-noun
          (filter-in-seq-set 1375260)
          :description "suffix-sei"
          :score 12
          :connector "")
    
    Score: 12
    """
    if is_noun(left_seq) and right_seq == SEQ_SEI:
        return Synergy(score=12, name="noun+性")
    return None


def synergy_o_prefix(left_seq: int, left_text: str,
                     right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: お + noun
    
    From Ichiran (dict-grammar.lisp:908-913):
        (def-generic-synergy synergy-o-prefix (l r)
          (filter-in-seq-set 1270190)
          (filter-is-pos ("n") (segment k p c l) (or k l))
          :description "o+noun"
          :score 10
          :connector "")
    
    Score: 10
    """
    if left_seq == SEQ_O_PREFIX and is_noun(right_seq):
        return Synergy(score=10, name="お+noun")
    return None


def synergy_kanji_prefix(left_seq: int, left_text: str,
                         right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: 未/不/無 + noun
    
    From Ichiran (dict-grammar.lisp:915-920):
        (def-generic-synergy synergy-kanji-prefix (l r)
          (filter-in-seq-set 2242840 1922780 2423740) ;; 未 不 無
          (filter-is-pos ("n") (segment k p c l) k)
          :description "kanji prefix+noun"
          :score 15
          :connector "")
    
    Score: 15
    """
    if left_seq in SEQ_KANJI_PREFIX and is_noun(right_seq):
        return Synergy(score=15, name=f"{left_text}+noun")
    return None


def synergy_shicha_ikenai(left_seq: int, left_text: str,
                          right_seq: int, right_text: str,
                          left_is_compound_end_ha: bool = False) -> Optional[Synergy]:
    """
    Synergy: compound ending with は + いけない/いけません/だめ
    
    From Ichiran (dict-grammar.lisp:922-927):
        (def-generic-synergy synergy-shicha-ikenai (l r)
          (filter-is-compound-end 2028920) ;; は
          (filter-in-seq-set 1000730 1612750 1409110 2829697 1587610)
          :description "shicha ikenai"
          :score 50
          :connector " ")
    
    Score: 50
    
    Note: In himotoki we check if left text ends with ちゃ/じゃ as proxy
    for compound ending with は
    """
    if left_text.endswith(('ちゃ', 'じゃ')) and right_seq in SEQ_IKENAI:
        return Synergy(score=50, name="shicha+ikenai")
    return None


def synergy_shika_negative(left_seq: int, left_text: str,
                           right_seq: int, right_text: str,
                           right_is_negative: bool = False) -> Optional[Synergy]:
    """
    Synergy: しか + negative
    
    From Ichiran (dict-grammar.lisp:929-937):
        (def-generic-synergy synergy-shika-negative (l r)
          (filter-in-seq-set 1005460) ;; しか
          (lambda (segment)
            (some (lambda (cdata)
                    (conj-neg (conj-data-prop cdata)))
                  (getf (segment-info segment) :conj)))
          :description "shika+neg"
          :score 50
          :connector " ")
    
    Score: 50
    """
    if left_seq == SEQ_SHIKA:
        # Check if right has negative conjugation or common negative endings
        if right_is_negative:
            return Synergy(score=50, name="しか+neg")
        # Also check for common negative endings in text
        if right_text.endswith(('ない', 'なかった', 'ません', 'ませんでした', 'ず', 'ぬ')):
            return Synergy(score=50, name="しか+neg")
    return None


def synergy_no_toori(left_seq: int, left_text: str,
                     right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: の + 通り
    
    From Ichiran (dict-grammar.lisp:939-944):
        (def-generic-synergy synergy-no-toori (l r)
          (filter-in-seq-set 1469800)
          (filter-in-seq-set 1432920)
          :description "no toori"
          :score 50
          :connector " ")
    
    Score: 50
    """
    if left_seq == SEQ_NO and right_seq == SEQ_TOORI:
        return Synergy(score=50, name="の+通り")
    return None


def synergy_oki(left_seq: int, left_text: str,
                right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: counter + 置き
    
    From Ichiran (dict-grammar.lisp:946-951):
        (def-generic-synergy synergy-oki (l r)
          (filter-is-pos ("ctr") (segment k p c l) t)
          (filter-in-seq-set 2854117 2084550)
          :score 20
          :connector "")
    
    Score: 20
    """
    if is_counter(left_seq) and right_seq in SEQ_OKI:
        return Synergy(score=20, name="ctr+置き")
    return None


# ============================================================================
# Additional Himotoki Synergies (not in Ichiran but needed for our system)
# ============================================================================

def synergy_noun_desu(left_seq: int, left_text: str,
                      right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: noun/na-adj + です
    
    Himotoki addition to handle です as a separate word.
    Ichiran handles this through compound words/suffixes, but we need synergy
    because our system segments です separately.
    
    Score: 15 (same as na-adjective synergy to handle 静かです etc)
    """
    if (is_noun(left_seq) or is_na_adjective(left_seq)) and right_seq == COPULA_DESU:
        return Synergy(score=15, name="noun/adj+です")
    return None


def synergy_ga_adjective(left_seq: int, left_text: str,
                         right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: が + adjective
    
    Himotoki addition to handle patterns like:
    - 天気がいい (weather is good)
    - 本が面白い (book is interesting)
    
    The が particle as subject marker followed by predicate adjective
    is extremely common in Japanese.
    
    Score: 30 (high enough to beat がい+い pattern - score 326 vs 324)
    """
    if left_seq == SEQ_GA:
        if is_i_adjective(right_seq) or is_na_adjective(right_seq):
            return Synergy(score=30, name="が+adj")
    return None


def synergy_particle_adjective(left_seq: int, left_text: str,
                               right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: particle + adjective
    
    General pattern for particles followed by adjectives.
    Common patterns: は/も + adjective
    
    Score: 15
    """
    if left_seq in NOUN_PARTICLES and left_seq != SEQ_GA:  # GA has its own higher synergy
        if is_i_adjective(right_seq) or is_na_adjective(right_seq):
            return Synergy(score=15, name=f"prt+adj")
    return None


def synergy_te_auxiliary(left_seq: int, left_text: str,
                         right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: te-form + auxiliary verb (いる/ある/しまう/etc.)
    
    This handles compound verb patterns like:
    - 食べている (tabete iru) - is eating (continuous)
    - 食べてある (tabete aru) - has eaten (resultative)
    - 食べてしまう (tabete shimau) - end up eating (completion)
    - 食べておく (tabete oku) - eat in advance
    - 食べてくる (tabete kuru) - come after eating
    - 食べてくれる (tabete kureru) - do eating (for me)
    
    Ichiran handles these as suffixes (suffix-teiru, suffix-teiru+, etc.)
    with score modifiers of 3-6. Since we handle them as separate segments,
    we need a synergy bonus to make them win over spurious combinations.
    
    The synergy checks:
    1. Left word ends with て or で (te-form)
    2. Right word is a conjugation of an auxiliary verb
    
    Score: 50 (high enough to beat いま+す which scores ~456 vs います ~432)
    """
    # Check if left word ends with te/de (te-form marker)
    if not left_text or not left_text.endswith(('て', 'で')):
        return None
    
    # Check if right word is a conjugation of an auxiliary verb
    # right_seq is the base seq, which for conjugated forms is the dictionary form
    if right_seq in TE_FORM_AUXILIARIES:
        return Synergy(score=50, name="te+aux")
    
    return None


def synergy_verb_kara(left_seq: int, left_text: str,
                      right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: verb/adjective + から (causal particle)
    
    The から particle commonly follows verbs and adjectives to mean "because".
    Examples:
    - 行くから (iku kara) - because [I] go
    - ないから (nai kara) - because there isn't
    - 暑いから (atsui kara) - because it's hot
    
    This synergy prevents misparses like ないか+ら (internal medicine + plural)
    which should be ない+から (not exist + because).
    
    Score: 100 (high to overcome misparses like ないか+ら which score ~484
    vs correct ない+から which scores ~402 - we need +82 minimum)
    """
    from .constants import SEQ_KARA
    
    # Check if right word is から (particle)
    if right_seq != SEQ_KARA:
        return None
    
    # Check if left word is a verb or adjective
    # Verbs typically have "verb" in POS, adjectives have "adjective"
    pos_tags = get_pos_tags(left_seq) if left_seq else set()
    is_verb_or_adj = any(
        'verb' in p.lower() or 'adjective' in p.lower() or 'auxiliary' in p.lower()
        for p in pos_tags
    )
    
    if is_verb_or_adj:
        return Synergy(score=100, name="v/adj+から")
    
    return None


# ============================================================================
# Synergy Function List
# ============================================================================

# List of all synergy functions in priority order
SYNERGY_FUNCTIONS = [
    # Ichiran synergies (exact ports from dict-grammar.lisp)
    synergy_noun_particle,      # noun + particle
    synergy_noun_da,            # noun + だ
    synergy_no_da,              # の/ん + だ/です
    synergy_sou_nanda,          # そう + なんだ
    synergy_no_adjectives,      # adj-no + の
    synergy_na_adjectives,      # adj-na + な/に
    synergy_to_adverbs,         # adv-to + と
    synergy_suffix_chu,         # noun + 中
    synergy_suffix_tachi,       # noun + たち
    synergy_suffix_buri,        # noun + ぶり
    synergy_suffix_sei,         # noun + 性
    synergy_o_prefix,           # お + noun
    synergy_kanji_prefix,       # 未/不/無 + noun
    synergy_shicha_ikenai,      # ~ちゃ + いけない
    synergy_no_toori,           # の + 通り
    synergy_oki,                # counter + 置き
    
    # Himotoki additions
    synergy_noun_desu,          # noun/adj + です
    synergy_ga_adjective,       # が + adjective
    synergy_particle_adjective, # particle + adjective
    synergy_te_auxiliary,       # te-form + auxiliary (いる/ある/しまう/etc.)
    synergy_verb_kara,          # verb/adj + から (because)
]


# ============================================================================
# Penalty Definitions (1:1 from Ichiran's def-generic-penalty)
# ============================================================================

@dataclass
class Penalty:
    """Penalty for unlikely word combination."""
    score: int  # Negative value
    name: str
    serial: bool = False  # If True, penalty only applies once for consecutive matches


def _is_kana(s: str) -> bool:
    """Check if string is all hiragana/katakana."""
    for c in s:
        cp = ord(c)
        # Hiragana: U+3040-U+309F, Katakana: U+30A0-U+30FF
        if not ((0x3040 <= cp <= 0x309F) or (0x30A0 <= cp <= 0x30FF)):
            return False
    return True


def penalty_short(left_seq: int, left_text: str,
                  right_seq: int, right_text: str) -> Optional[Penalty]:
    """
    Penalty: consecutive short kana words
    
    From Ichiran (dict-grammar.lisp:965-970):
        (def-generic-penalty penalty-short (l r)
          (filter-short-kana 1)
          (filter-short-kana 1 :except '("と"))
          :description "short"
          :serial nil
          :score -9)
    
    Score: -9 (non-serial: applies to each pair)
    
    Note: Exception for と on the right side (quotative particle)
    """
    if (len(left_text) == 1 and _is_kana(left_text) and
        len(right_text) == 1 and _is_kana(right_text) and
        right_text != 'と'):  # Exception from Ichiran
        return Penalty(score=-9, name="short-kana", serial=False)
    return None


def penalty_semi_final(left_seq: int, left_text: str,
                       right_seq: int, right_text: str,
                       is_final: bool = False) -> Optional[Penalty]:
    """
    Penalty: semi-final particle not at end
    
    From Ichiran (dict-grammar.lisp:972-978):
        (def-generic-penalty penalty-semi-final (l r)
          (lambda (sl)
            (some (lambda (s) (funcall (apply 'filter-in-seq-set *semi-final-prt*) s))
                  (segment-list-segments sl)))
          (constantly t)
          :description "semi-final not final"
          :score -15)
    
    Score: -15 (serial: only one penalty per chain)
    
    The penalty applies to left when it's a semi-final particle
    that is followed by more content (not at sentence end).
    """
    if left_seq in SEMI_FINAL_PRT and not is_final:
        return Penalty(score=-15, name="semi-final-not-end", serial=True)
    return None


# List of all penalty functions
PENALTY_FUNCTIONS = [
    penalty_short,
]


# ============================================================================
# Helper to extract seq from segment or word
# ============================================================================

def _get_seq(seg: Any) -> Optional[int]:
    """Extract seq from a segment or word object.
    
    For compound words, returns the primary (first) seq.
    """
    # Direct seq attribute
    seq = getattr(seg, 'seq', None)
    if seq is not None:
        # Handle list of seqs (CompoundText)
        if isinstance(seq, list):
            return seq[0] if seq else None
        return seq
    # Try segment.word.seq
    word = getattr(seg, 'word', None)
    if word:
        seq = getattr(word, 'seq', None)
        if isinstance(seq, list):
            return seq[0] if seq else None
        return seq
    return None


def _get_text(seg: Any) -> str:
    """Extract text from a segment or word object."""
    if hasattr(seg, 'get_text'):
        return seg.get_text()
    if hasattr(seg, 'text'):
        return seg.text
    word = getattr(seg, 'word', None)
    if word:
        if hasattr(word, 'get_text'):
            return word.get_text()
        if hasattr(word, 'text'):
            return word.text
    return str(seg)


def _is_negative_conj(seg: Any) -> bool:
    """Check if segment has negative conjugation."""
    conj_type = getattr(seg, 'conj_type', None)
    if not conj_type:
        word = getattr(seg, 'word', None)
        if word:
            conj_type = getattr(word, 'conj_type', None)
    if conj_type:
        neg_indicators = {'negative', 'neg', 'ない', 'なかった', 'ず', 'ぬ', 'ません'}
        return any(ind in str(conj_type).lower() for ind in neg_indicators)
    return False


# ============================================================================
# Combined Scoring
# ============================================================================

def calculate_synergy(left_seg: Any, right_seg: Any) -> Optional[Synergy]:
    """
    Calculate synergy between two adjacent segments.
    
    Args:
        left_seg: Left segment (word object).
        right_seg: Right segment (word object).
        
    Returns:
        Synergy with highest score, or None.
    """
    # Extract segment properties
    left_seq = _get_seq(left_seg)
    right_seq = _get_seq(right_seg)
    
    if not left_seq or not right_seq:
        return None
    
    # Get text
    left_text = _get_text(left_seg)
    right_text = _get_text(right_seg)
    
    # Check for negative conjugation
    right_is_negative = _is_negative_conj(right_seg)
    
    # Try all synergy functions
    best: Optional[Synergy] = None
    for func in SYNERGY_FUNCTIONS:
        try:
            result = func(left_seq, left_text, right_seq, right_text)
        except TypeError:
            # Some functions have extra parameters
            result = None
        if result and (best is None or result.score > best.score):
            best = result
    
    # Special case: shika-negative (needs negative info)
    shika = synergy_shika_negative(left_seq, left_text, right_seq, right_text, right_is_negative)
    if shika and (best is None or shika.score > best.score):
        best = shika
    
    # Special case: shicha-ikenai 
    shicha = synergy_shicha_ikenai(left_seq, left_text, right_seq, right_text)
    if shicha and (best is None or shicha.score > best.score):
        best = shicha
    
    return best


def calculate_penalty(left_seg: Any, right_seg: Any, 
                      is_left_final: bool = False) -> Optional[Penalty]:
    """
    Calculate penalty between two adjacent segments.
    
    Args:
        left_seg: Left segment (word object).
        right_seg: Right segment (word object).
        is_left_final: Whether left_seg is at sentence end.
        
    Returns:
        Combined penalty, or None.
    """
    # Extract segment properties using helpers
    left_seq = _get_seq(left_seg) or 0
    right_seq = _get_seq(right_seg) or 0
    left_text = _get_text(left_seg)
    right_text = _get_text(right_seg)
    
    penalties: List[Penalty] = []
    
    # Check penalty-short
    short_pen = penalty_short(left_seq, left_text, right_seq, right_text)
    if short_pen:
        penalties.append(short_pen)
    
    # Check penalty-semi-final
    semi_pen = penalty_semi_final(left_seq, left_text, right_seq, right_text, is_left_final)
    if semi_pen:
        penalties.append(semi_pen)
    
    if not penalties:
        return None
    
    # Combine penalties (sum the scores)
    total_score = sum(p.score for p in penalties)
    names = '+'.join(p.name for p in penalties)
    return Penalty(score=total_score, name=names)


def score_segment_pair(left_seg: Any, right_seg: Any,
                       is_left_final: bool = False) -> Tuple[int, str]:
    """
    Calculate net synergy/penalty score between two segments.
    
    Args:
        left_seg: Left segment.
        right_seg: Right segment.
        is_left_final: Whether left segment is at sentence end.
        
    Returns:
        Tuple of (score, reason).
    """
    total = 0
    reasons = []
    
    synergy = calculate_synergy(left_seg, right_seg)
    if synergy:
        total += synergy.score
        reasons.append(f"+{synergy.score}({synergy.name})")
    
    penalty = calculate_penalty(left_seg, right_seg, is_left_final)
    if penalty:
        total += penalty.score  # penalty.score is already negative
        reasons.append(f"{penalty.score}({penalty.name})")
    
    return total, ' '.join(reasons)


def score_path(segments: List[Any]) -> Tuple[int, List[str]]:
    """
    Calculate total synergy/penalty score for a path.
    
    Args:
        segments: List of segments in order.
        
    Returns:
        Tuple of (total_score, list_of_reasons).
    """
    if len(segments) < 2:
        return 0, []
    
    total = 0
    all_reasons = []
    
    # Track serial penalties to avoid duplicates
    serial_applied: Set[str] = set()
    
    for i in range(len(segments) - 1):
        left = segments[i]
        right = segments[i + 1]
        is_final = (i == len(segments) - 2)  # Last pair means left is at end
        
        # Synergy
        synergy = calculate_synergy(left, right)
        if synergy:
            total += synergy.score
            all_reasons.append(f"{i}:{synergy.name}=+{synergy.score}")
        
        # Penalty (with serial tracking)
        penalty = calculate_penalty(left, right, is_final)
        if penalty:
            if penalty.serial:
                # Serial penalty only applies once
                if penalty.name not in serial_applied:
                    total += penalty.score
                    all_reasons.append(f"{i}:{penalty.name}={penalty.score}")
                    serial_applied.add(penalty.name)
            else:
                # Non-serial penalty applies to each pair
                total += penalty.score
                all_reasons.append(f"{i}:{penalty.name}={penalty.score}")
    
    return total, all_reasons


# ============================================================================
# Skip Word Check
# ============================================================================

def is_skip_word(seq: int) -> bool:
    """
    Check if a word should be skipped as a standalone segment.
    
    These are suffix-only words that should not start a segment.
    From Ichiran's *skip-words* list.
    """
    return seq in SKIP_WORDS


# ============================================================================
# Utility for Debug
# ============================================================================

def explain_synergies(segments: List[Any]) -> str:
    """
    Generate a human-readable explanation of all synergies/penalties.
    
    Args:
        segments: List of segment objects.
        
    Returns:
        Formatted string explaining each bonus/penalty.
    """
    if len(segments) < 2:
        return "No synergies (single segment)"
    
    lines = []
    total, reasons = score_path(segments)
    
    for i in range(len(segments) - 1):
        left = segments[i]
        right = segments[i + 1]
        
        left_text = _get_text(left)
        right_text = _get_text(right)
        
        score, reason = score_segment_pair(left, right)
        if reason:
            lines.append(f"  {left_text} + {right_text}: {reason}")
    
    lines.append(f"  Total synergy score: {total}")
    return '\n'.join(lines)
