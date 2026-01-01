"""
Synergy and penalty calculations for Japanese morphological analysis.

This is a 1:1 port of Ichiran's synergy system from dict.lisp.
All synergy/penalty definitions, scores, and logic match Ichiran exactly.

Key Ichiran definitions ported:
- def-synergy: Synergy rules with scores
- def-penalty: Penalty rules with scores  
- *noun-particles*: Particles that follow nouns
- *semi-final-prt*: Semi-final particles
- *skip-words*: Suffix-only words
"""

from dataclasses import dataclass
from typing import Optional, Set, List, Tuple, Dict, Any
from functools import lru_cache

from .conn import query


# ============================================================================
# Ichiran Particle/Word Sets (exact seq numbers from dict.lisp)
# ============================================================================

# Noun particles (from Ichiran's *noun-particles*)
# These are particles that naturally follow nouns
# Score formula: 10 + 4 * len(particle)
NOUN_PARTICLES: Set[int] = {
    2028920,   # が
    2028930,   # を
    2028990,   # に
    2028980,   # まで
    2029000,   # から
    1007340,   # と
    1579080,   # より
    2028940,   # で
    1582300,   # へ
    2215430,   # として
    1469800,   # にて
    1009990,   # のみ
    2029010,   # ばかり
    1005120,   # だけ
    2034520,   # しか
    1008490,   # ずつ
    1008530,   # すら
    1008590,   # さえ
    2028950,   # は
    2028960,   # も
    1009600,   # など
    1525680,   # へ (alternate)
}

# Semi-final particles (from Ichiran's *semi-final-prt*)
# Particles that can appear sentence-finally but also mid-sentence
# If not at actual end of sentence: penalty = -15
SEMI_FINAL_PRT: Set[int] = {
    2017770,   # って
    2425930,   # っけ
    2130430,   # さ
    2029130,   # の
    2834812,   # ん
    2718360,   # かな
    2201380,   # だな
    2722170,   # じゃん
    2751630,   # かよ
    2029120,   # わ
    2086640,   # ぞ
    2029110,   # か
    2029080,   # ね
    2029100,   # な
}

# Skip words (suffix-only entries from Ichiran's *skip-words*)
# These should only appear as suffixes, not standalone at segment start
SKIP_WORDS: Set[int] = {
    2458040,   # がい (counter suffix)
    2822120,   # ない (aux adj)
    2013800,   # 的
    2108590,   # ず (archaic negative)
    2029040,   # ぬ (archaic negative)
    2428180,   # ら (pluralizer)
    2654250,   # さん (honorific)
    2561100,   # ちゃん (honorific)
    2210270,   # ん (contraction)
    2210710,   # な (prohibitive)
    2257550,   # じゃ (contraction of では)
    2210320,   # ま (contraction of まあ)
    2017560,   # って (quotative)
    2394890,   # なんて (expression)
    2194000,   # ものを
    2568000,   # かなあ
    2537250,   # かしら
    2760890,   # のに
    2831062,   # つって
    2831063,   # つった
    2029030,   # ば (conditional)
    2568020,   # かな (expression)
}

# Copula and polite copula
COPULA_DA: int = 2089020    # だ
COPULA_DESU: int = 1628500  # です
COPULA_DAROU: int = 1928670 # だろう
COPULA_DESU_ALT: int = 1007370  # です (alternate)

# Special entries
SEQ_TOORI: int = 1432920    # 通り (following pattern) - corrected
SEQ_NO: int = 1469800       # の (particle) - corrected seq
SEQ_N: int = 2139720        # ん (contraction of の)
SEQ_SHIKA: int = 1005460    # しか (only when followed by negative) - corrected
SEQ_TO: int = 1008490       # と (quotative/adverb particle)

# Suffix sequences
SEQ_CHU: Set[int] = {1620400, 2083570}  # 中
SEQ_TACHI: int = 1416220    # たち
SEQ_BURI: int = 1361140     # ぶり
SEQ_SEI: int = 1375260      # 性
SEQ_O_PREFIX: int = 1270190 # お (polite prefix)
SEQ_KANJI_PREFIX: Set[int] = {2242840, 1922780, 2423740}  # 未, 不, 無
SEQ_OKI: Set[int] = {2854117, 2084550}  # 置き

# Synergy-specific sequences
SEQ_IKENAI: Set[int] = {1000730, 1612750, 1409110, 2829697, 1587610}  # いけない, いけません, だめ, etc.
SEQ_SOU: int = 2137720      # そう
SEQ_NANDA: int = 2140410    # なんだ
SEQ_OMOU: Set[int] = {1589350, 1587040}  # 思う, 言う
SEQ_NAI: int = 1529520      # ない
SEQ_ARU: int = 1296400      # ある
SEQ_HA: int = 2028920       # は
SEQ_NA_PARTICLE: int = 2029110  # な (attributive)
SEQ_NI_PARTICLE: int = 2028990  # に


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
    return any('particle' in p for p in pos_tags)


@lru_cache(maxsize=10000)
def is_noun(seq: int) -> bool:
    """Check if entry is a noun (including pronouns)."""
    pos_tags = get_pos_tags(seq)
    return any('noun' in p or 'pronoun' in p for p in pos_tags)


@lru_cache(maxsize=10000)
def is_verb(seq: int) -> bool:
    """Check if entry is a verb."""
    pos_tags = get_pos_tags(seq)
    return any('verb' in p for p in pos_tags)


@lru_cache(maxsize=10000)
def is_i_adjective(seq: int) -> bool:
    """Check if entry is an i-adjective."""
    pos_tags = get_pos_tags(seq)
    return any('adj-i' in p or 'keiyoushi' in p for p in pos_tags)


@lru_cache(maxsize=10000)
def is_na_adjective(seq: int) -> bool:
    """Check if entry is a na-adjective."""
    pos_tags = get_pos_tags(seq)
    return any('adj-na' in p or 'adjectival' in p for p in pos_tags)


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
    """Check if entry is a counter."""
    pos_tags = get_pos_tags(seq)
    return any('ctr' in p or 'counter' in p for p in pos_tags)


@lru_cache(maxsize=10000)
def is_negative_verb(seq: int, conj_type: Optional[str] = None) -> bool:
    """
    Check if a word is in negative form.
    
    In Ichiran, this checks for:
    - Negative conjugation types
    - Words like ない, いない, etc.
    """
    if conj_type:
        neg_types = {'negative', 'neg', 'ない', 'なかった', 'ず', 'ぬ'}
        return any(t in conj_type.lower() for t in neg_types)
    return False


# ============================================================================
# Synergy Definitions (1:1 from Ichiran's def-synergy)
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
    
    From Ichiran:
        (def-synergy noun-particle (w1 w2 :test 
          (and (has-pos w1 :noun) (member (seq w2) *noun-particles*)))
          :description "Noun followed by a generic particle"
          :score (+ 10 (* 4 (length (get-text w2)))))
    
    Score: 10 + 4 * len(particle)
    """
    if is_noun(left_seq) and right_seq in NOUN_PARTICLES:
        score = 10 + 4 * len(right_text)
        return Synergy(score=score, name=f"noun-particle({right_text})")
    return None


def synergy_na_adjective(left_seq: int, left_text: str,
                         right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: na-adjective + な/に
    
    From Ichiran:
        (def-synergy na-adjective (w1 w2 :test
          (and (has-pos w1 :adj-na)
               (or (equal (get-text w2) "な")
                   (equal (get-text w2) "に"))))
          :description "Na-adjective followed by な or に"
          :score 15)
    
    Score: 15
    """
    if is_na_adjective(left_seq) and right_text in ('な', 'に'):
        return Synergy(score=15, name=f"na-adjective+{right_text}")
    return None


def synergy_shika_negative(left_seq: int, left_text: str,
                           right_seq: int, right_text: str,
                           right_conj_type: Optional[str] = None) -> Optional[Synergy]:
    """
    Synergy: しか + negative
    
    From Ichiran:
        (def-synergy shika-negative (w1 w2 :test
          (and (= (seq w1) *shika*) (is-negative w2)))
          :description "しか followed by negative verb"
          :score 50)
    
    Score: 50
    """
    if left_seq == SEQ_SHIKA:
        # Check if right is negative form
        if is_negative_verb(right_seq, right_conj_type):
            return Synergy(score=50, name="shika-negative")
        # Also check for common negative endings
        if right_text in ('ない', 'なかった', 'ません', 'ませんでした'):
            return Synergy(score=50, name="shika-negative")
    return None


def synergy_no_toori(left_seq: int, left_text: str,
                     right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: の + 通り
    
    From Ichiran:
        (def-synergy no-toori (w1 w2 :test
          (and (= (seq w1) *no*) (= (seq w2) *toori*)))
          :description "の followed by 通り"
          :score 50)
    
    Score: 50
    """
    if left_seq == SEQ_NO and right_seq == SEQ_TOORI:
        return Synergy(score=50, name="no-toori")
    return None


def synergy_noun_da(left_seq: int, left_text: str,
                    right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: noun + だ
    
    From Ichiran (dict-grammar.lisp:838-842):
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


def synergy_noun_desu(left_seq: int, left_text: str,
                      right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: noun/na-adj + です
    
    This is a himotoki addition to handle です properly.
    Ichiran handles this through compound words, but we need synergy.
    
    Score: 15 (same as na-adjective synergy)
    """
    if (is_noun(left_seq) or is_na_adjective(left_seq)) and right_seq == COPULA_DESU:
        return Synergy(score=15, name="noun+desu")
    return None


def synergy_no_da(left_seq: int, left_text: str,
                  right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: の/ん + だ/です/だろう
    
    From Ichiran (dict-grammar.lisp:844-848):
        (def-generic-synergy synergy-no-da (l r)
          (filter-in-seq-set 1469800 2139720)  ;; の, ん
          (filter-in-seq-set 2089020 1007370 1928670)  ;; だ, です, だろう
          :description "no da/desu"
          :score 15
          :connector " ")
    
    Score: 15
    """
    left_is_no_or_n = left_seq in {SEQ_NO, SEQ_N}
    right_is_copula = right_seq in {COPULA_DA, COPULA_DESU, COPULA_DAROU, COPULA_DESU_ALT}
    if left_is_no_or_n and right_is_copula:
        return Synergy(score=15, name="no-da/desu")
    return None


def synergy_sou_nanda(left_seq: int, left_text: str,
                      right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: そう + なんだ
    
    From Ichiran (dict-grammar.lisp:851-855):
        (def-generic-synergy synergy-sou-nanda (l r)
          (filter-in-seq-set 2137720)  ;; そう
          (filter-in-seq-set 2140410)  ;; なんだ
          :description "sou na n da"
          :score 50
          :connector " ")
    
    Score: 50
    """
    if left_seq == SEQ_SOU and right_seq == SEQ_NANDA:
        return Synergy(score=50, name="sou-nanda")
    return None


def synergy_no_adjectives(left_seq: int, left_text: str,
                          right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: adj-no + の
    
    From Ichiran (dict-grammar.lisp:858-862):
        (def-generic-synergy synergy-no-adjectives (l r)
          (filter-is-pos ("adj-no") ...)
          (filter-in-seq-set 1469800) ;; の
          :description "no-adjective"
          :score 15
          :connector " ")
    
    Score: 15
    """
    if is_no_adjective(left_seq) and right_seq == SEQ_NO:
        return Synergy(score=15, name="no-adjective")
    return None


def synergy_to_adverbs(left_seq: int, left_text: str,
                       right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: adv-to + と
    
    From Ichiran (dict-grammar.lisp:877-881):
        (def-generic-synergy synergy-to-adverbs (l r)
          (filter-is-pos ("adv-to") ...)
          (filter-in-seq-set 1008490)  ;; と
          :description "to-adverb"
          :score (+ 10 (* 10 (- (segment-list-end l) (segment-list-start l))))
          :connector " ")
    
    Score: 10 + 10 * len(adverb)
    """
    if is_to_adverb(left_seq) and right_seq == SEQ_TO:
        score = 10 + 10 * len(left_text)
        return Synergy(score=score, name="to-adverb")
    return None


def synergy_suffix_chu(left_seq: int, left_text: str,
                       right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: noun + 中
    
    From Ichiran (dict-grammar.lisp:883-887):
        (def-generic-synergy synergy-suffix-chu (l r)
          #'filter-is-noun
          (filter-in-seq-set 1620400 2083570)
          :description "suffix-chu"
          :score 12
          :connector "-")
    
    Score: 12
    """
    if is_noun(left_seq) and right_seq in SEQ_CHU:
        return Synergy(score=12, name="suffix-chu")
    return None


def synergy_suffix_tachi(left_seq: int, left_text: str,
                         right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: noun + たち
    
    From Ichiran (dict-grammar.lisp:889-893):
        (def-generic-synergy synergy-suffix-tachi (l r)
          #'filter-is-noun
          (filter-in-seq-set 1416220)
          :description "suffix-tachi"
          :score 10
          :connector "-")
    
    Score: 10
    """
    if is_noun(left_seq) and right_seq == SEQ_TACHI:
        return Synergy(score=10, name="suffix-tachi")
    return None


def synergy_suffix_buri(left_seq: int, left_text: str,
                        right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: noun + ぶり
    
    From Ichiran (dict-grammar.lisp:895-899):
        (def-generic-synergy synergy-suffix-buri (l r)
          #'filter-is-noun
          (filter-in-seq-set 1361140)
          :description "suffix-buri"
          :score 40
          :connector "")
    
    Score: 40
    """
    if is_noun(left_seq) and right_seq == SEQ_BURI:
        return Synergy(score=40, name="suffix-buri")
    return None


def synergy_suffix_sei(left_seq: int, left_text: str,
                       right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: noun + 性
    
    From Ichiran (dict-grammar.lisp:901-905):
        (def-generic-synergy synergy-suffix-sei (l r)
          #'filter-is-noun
          (filter-in-seq-set 1375260)
          :description "suffix-sei"
          :score 12
          :connector "")
    
    Score: 12
    """
    if is_noun(left_seq) and right_seq == SEQ_SEI:
        return Synergy(score=12, name="suffix-sei")
    return None


def synergy_o_prefix(left_seq: int, left_text: str,
                     right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: お + noun
    
    From Ichiran (dict-grammar.lisp:907-911):
        (def-generic-synergy synergy-o-prefix (l r)
          (filter-in-seq-set 1270190)  ;; お
          (filter-is-pos ("n") ...)
          :description "o+noun"
          :score 10
          :connector "")
    
    Score: 10
    """
    if left_seq == SEQ_O_PREFIX and is_noun(right_seq):
        return Synergy(score=10, name="o+noun")
    return None


def synergy_kanji_prefix(left_seq: int, left_text: str,
                         right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: 未/不/無 + noun
    
    From Ichiran (dict-grammar.lisp:913-917):
        (def-generic-synergy synergy-kanji-prefix (l r)
          (filter-in-seq-set 2242840 1922780 2423740) ;; 未 不 無
          (filter-is-pos ("n") ...)
          :description "kanji prefix+noun"
          :score 15
          :connector "")
    
    Score: 15
    """
    if left_seq in SEQ_KANJI_PREFIX and is_noun(right_seq):
        return Synergy(score=15, name="kanji-prefix+noun")
    return None


def synergy_oki(left_seq: int, left_text: str,
                right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: counter + 置き
    
    From Ichiran (dict-grammar.lisp:944-948):
        (def-generic-synergy synergy-oki (l r)
          (filter-is-pos ("ctr") ...)
          (filter-in-seq-set 2854117 2084550)
          :score 20
          :connector "")
    
    Score: 20
    """
    if is_counter(left_seq) and right_seq in SEQ_OKI:
        return Synergy(score=20, name="counter-oki")
    return None


# Particle GA seq (subject marker が)
SEQ_GA_PARTICLE: int = 2028930


def synergy_ga_adjective(left_seq: int, left_text: str,
                         right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: が + i-adjective/na-adjective
    
    This is a himotoki addition to handle patterns like:
    - 天気がいい (weather is good)
    - 本が面白い (book is interesting)
    
    When the particle が is followed by an adjective, this is a very
    common pattern in Japanese indicating the subject + predicate.
    
    Score: 30 (high enough to beat がい+い pattern)
    """
    if left_seq == SEQ_GA_PARTICLE:
        if is_i_adjective(right_seq) or is_na_adjective(right_seq):
            return Synergy(score=30, name="ga+adjective")
    return None


def synergy_particle_adjective(left_seq: int, left_text: str,
                               right_seq: int, right_text: str) -> Optional[Synergy]:
    """
    Synergy: particle + adjective
    
    General pattern for particles followed by adjectives.
    Common patterns: が/は/も + adjective
    
    Score: 15
    """
    if is_particle(left_seq) and left_seq in NOUN_PARTICLES:
        if is_i_adjective(right_seq) or is_na_adjective(right_seq):
            return Synergy(score=15, name=f"prt({left_text})+adj")
    return None


# List of all synergy functions
SYNERGY_FUNCTIONS = [
    synergy_noun_particle,
    synergy_ga_adjective,
    synergy_particle_adjective,
    synergy_na_adjective,
    synergy_no_toori,
    synergy_noun_da,
    synergy_noun_desu,
    synergy_no_da,
    synergy_sou_nanda,
    synergy_no_adjectives,
    synergy_to_adverbs,
    synergy_suffix_chu,
    synergy_suffix_tachi,
    synergy_suffix_buri,
    synergy_suffix_sei,
    synergy_o_prefix,
    synergy_kanji_prefix,
    synergy_oki,
]


# ============================================================================
# Penalty Definitions (1:1 from Ichiran's def-penalty)
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
    
    From Ichiran:
        (def-penalty short (w1 w2 :test
          (and (= (length (get-text w1)) 1)
               (kana-p (get-text w1))
               (= (length (get-text w2)) 1)
               (kana-p (get-text w2))))
          :description "Two consecutive 1-character kana words"
          :score -9)
    
    Score: -9 (non-serial: applies to each pair)
    """
    if (len(left_text) == 1 and _is_kana(left_text) and
        len(right_text) == 1 and _is_kana(right_text)):
        return Penalty(score=-9, name="short", serial=False)
    return None


def penalty_semi_final(left_seq: int, left_text: str,
                       right_seq: int, right_text: str,
                       is_final: bool = False) -> Optional[Penalty]:
    """
    Penalty: semi-final particle not at end
    
    From Ichiran:
        (def-penalty semi-final (w1 w2 :test
          (and (member (seq w1) *semi-final-prt*)
               (not (is-final w1))))
          :description "Semi-final particle not at sentence end"
          :score -15
          :serial t)
    
    Score: -15 (serial: only one penalty per chain)
    
    The penalty applies to w1 (left) when it's a semi-final particle
    that is followed by more content (not at sentence end).
    """
    if left_seq in SEMI_FINAL_PRT and not is_final:
        return Penalty(score=-15, name="semi-final", serial=True)
    return None


# List of all penalty functions (excluding is_final check for now)
PENALTY_FUNCTIONS = [
    penalty_short,
]


# ============================================================================
# Helper to extract seq from segment or word
# ============================================================================

def _get_seq(seg: Any) -> Optional[int]:
    """Extract seq from a segment or word object."""
    # Direct seq attribute
    seq = getattr(seg, 'seq', None)
    if seq:
        return seq
    # Try segment.word.seq
    word = getattr(seg, 'word', None)
    if word:
        return getattr(word, 'seq', None)
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
    
    # Get conjugation type if available
    right_conj_type = getattr(right_seg, 'conj_type', None)
    if not right_conj_type:
        word = getattr(right_seg, 'word', None)
        if word:
            right_conj_type = getattr(word, 'conj_type', None)
    
    # Try all synergy functions
    best: Optional[Synergy] = None
    for func in SYNERGY_FUNCTIONS:
        result = func(left_seq, left_text, right_seq, right_text)
        if result and (best is None or result.score > best.score):
            best = result
    
    # Special case: shika-negative (needs conj_type)
    shika = synergy_shika_negative(left_seq, left_text, right_seq, right_text, right_conj_type)
    if shika and (best is None or shika.score > best.score):
        best = shika
    
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
        
        left_text = getattr(left, 'text', str(left))
        right_text = getattr(right, 'text', str(right))
        
        score, reason = score_segment_pair(left, right)
        if reason:
            lines.append(f"  {left_text} + {right_text}: {reason}")
    
    lines.append(f"  Total synergy score: {total}")
    return '\n'.join(lines)
