"""
Consolidated constants for Himotoki.

This module provides a single source of truth for:
- Conjugation type IDs and their human-readable names
- Common JMdict sequence numbers (SEQ constants)
- Interned POS tag strings for memory efficiency

All other modules should import from here to avoid duplication.

---

WARNING: SEQ NUMBER STABILITY REQUIREMENT
=========================================
Many constants in this file are JMdict sequence numbers (SEQ_WA, SEQ_SURU, etc.).
These integer IDs are used to identify specific dictionary entries and are used
in logic throughout the codebase (synergies.py, suffixes.py, lookup.py).

IMPORTANT:
- If the JMdict dictionary is rebuilt from a newer source, SEQ numbers may change.
- If SEQ numbers change, the logic using them will silently break (wrong word matches).
- Run `verify_seq_constants(session)` after any dictionary update to detect mismatches.
- Consider migrating to string-based identifiers (e.g., "は-particle") for long-term stability.

---
"""

import sys
from typing import Dict, Set, Tuple, Optional, List


# ============================================================================
# Interned POS Tags (for memory efficiency)
# ============================================================================
# Using sys.intern() ensures each string exists only once in memory.
# These are the most frequently used part-of-speech tags.

POS_TAGS: Dict[str, str] = {
    tag: sys.intern(tag) for tag in [
        'n', 'n-adv', 'n-pref', 'n-suf', 'n-t',
        'v1', 'v1-s', 'v5aru', 'v5b', 'v5g', 'v5k', 'v5k-s', 'v5m', 'v5n',
        'v5r', 'v5r-i', 'v5s', 'v5t', 'v5u', 'v5u-s', 'v5uru', 'vk', 'vs',
        'vs-i', 'vs-s', 'vz', 'vi', 'vt', 'vs-c',
        'adj-i', 'adj-ix', 'adj-na', 'adj-no', 'adj-pn', 'adj-t', 'adj-f',
        'adv', 'adv-to', 'aux', 'aux-v', 'aux-adj',
        'conj', 'cop', 'ctr', 'exp', 'int', 'pn', 'pref', 'prt', 'suf', 'unc',
        # Common sense tags
        'uk', 'arch', 'male', 'fem', 'vulg', 'hon', 'hum', 'col', 'fam',
    ]
}


def intern_pos(pos: str) -> str:
    """Get interned version of POS tag for memory efficiency."""
    return POS_TAGS.get(pos, pos)

# ============================================================================
# Conjugation Type Constants
# ============================================================================

# Standard conjugation types (from conj.csv, matches ichiran)
CONJ_NON_PAST = 1
CONJ_PAST = 2
CONJ_TE = 3
CONJ_PROVISIONAL = 4
CONJ_POTENTIAL = 5
CONJ_PASSIVE = 6
CONJ_CAUSATIVE = 7
CONJ_CAUSATIVE_PASSIVE = 8
CONJ_VOLITIONAL = 9
CONJ_IMPERATIVE = 10
CONJ_CONDITIONAL = 11
CONJ_ALTERNATIVE = 12
CONJ_CONTINUATIVE = 13

# Custom conjugation types (from ichiran's dict-errata.lisp)
# These start at 50 to avoid conflicts with standard types
CONJ_ADVERBIAL = 50
CONJ_ADJECTIVE_STEM = 51
CONJ_NEGATIVE_STEM = 52
CONJ_CAUSATIVE_SU = 53  # Note: Also defined as 14 in some contexts for conjo.csv
CONJ_ADJECTIVE_LITERARY = 54

# Conjugation type names mapping
# Single source of truth - used by output.py, lookup.py, etc.
CONJ_TYPE_NAMES: Dict[int, str] = {
    CONJ_NON_PAST: "Non-past",
    CONJ_PAST: "Past (~ta)",
    CONJ_TE: "Conjunctive (~te)",
    CONJ_PROVISIONAL: "Provisional (~eba)",
    CONJ_POTENTIAL: "Potential",
    CONJ_PASSIVE: "Passive",
    CONJ_CAUSATIVE: "Causative",
    CONJ_CAUSATIVE_PASSIVE: "Causative-Passive",
    CONJ_VOLITIONAL: "Volitional",
    CONJ_IMPERATIVE: "Imperative",
    CONJ_CONDITIONAL: "Conditional (~tara)",
    CONJ_ALTERNATIVE: "Alternative (~tari)",
    CONJ_CONTINUATIVE: "Continuative (~i)",
    # Custom types
    CONJ_ADVERBIAL: "Adverbial",
    CONJ_ADJECTIVE_STEM: "Adjective Stem",
    CONJ_NEGATIVE_STEM: "Negative Stem",
    CONJ_CAUSATIVE_SU: "Causative (~su)",
    CONJ_ADJECTIVE_LITERARY: "Old/Literary",
}


def get_conj_description(conj_type: int) -> str:
    """Get human-readable description for conjugation type."""
    return CONJ_TYPE_NAMES.get(conj_type, f'Type {conj_type}')


# English glosses for each conjugation step (for breakdown tree)
CONJ_STEP_GLOSSES: Dict[int, str] = {
    CONJ_NON_PAST: "does/is",
    CONJ_PAST: "did/was",
    CONJ_TE: "",
    CONJ_PROVISIONAL: "if",
    CONJ_POTENTIAL: "can do",
    CONJ_PASSIVE: "is done (to)",
    CONJ_CAUSATIVE: "makes do",
    CONJ_CAUSATIVE_PASSIVE: "is made to do",
    CONJ_VOLITIONAL: "let's/will",
    CONJ_IMPERATIVE: "do!",
    CONJ_CONDITIONAL: "if/when",
    CONJ_ALTERNATIVE: "doing things like",
    CONJ_CONTINUATIVE: "and (stem)",
    CONJ_ADVERBIAL: "adverbially",
    CONJ_ADJECTIVE_STEM: "stem",
    CONJ_NEGATIVE_STEM: "not (stem)",
    CONJ_CAUSATIVE_SU: "makes do",
    CONJ_ADJECTIVE_LITERARY: "old/literary",
}


# Weak conjugation forms - these don't contribute as much to scoring
# Format: (conj_type, neg, fml) where None means "any"
# From ichiran's *weak-conj-forms*
WEAK_CONJ_FORMS: List[Tuple[int, Optional[bool], Optional[bool]]] = [
    (CONJ_ADJECTIVE_STEM, None, None),    # Adjective stem
    (CONJ_NEGATIVE_STEM, None, None),     # Negative stem
    (CONJ_CAUSATIVE_SU, None, None),      # Causative (~su)
    (CONJ_ADJECTIVE_LITERARY, None, None),  # Old/literary form
    (CONJ_VOLITIONAL, True, None),        # Volitional negative
]

# Skip conjugation forms - these conjugations should be skipped entirely
# Format: (pos, conj_type, neg, fml) or (conj_type, neg, fml)
# From ichiran's *skip-conj-forms*
SKIP_CONJ_FORMS: List[Tuple] = [
    (CONJ_IMPERATIVE, True, None),     # Imperative negative
    (CONJ_TE, True, True),             # Te-form negative formal
    ('vs-s', CONJ_POTENTIAL, None, None),   # vs-s potential (any)
]


# ============================================================================
# JMdict Sequence Number Constants
# ============================================================================
# These are stable JMdict seq numbers. If JMdict updates these,
# run verify_seq_constants() to check.

# --- Particles ---
SEQ_WA = 2028920           # は (topic marker)
SEQ_GA = 2028930           # が (subject marker)
SEQ_NI = 2028990           # に (dative)
SEQ_DE = 2028980           # で (location/instrument)
SEQ_HE = 2029000           # へ (direction)
SEQ_WO = 2029010           # を (object marker)
SEQ_NO = 1469800           # の (possessive)
SEQ_TO = 1008490           # と (quotative/conditional)
SEQ_MO = 2028940           # も (also)
SEQ_YA = 2028960           # や (and)
SEQ_KA = 2028970           # か (question)
SEQ_YO = 2029090           # よ (emphasis particle)

# --- Compound Particles ---
SEQ_NIHA = 2215430         # には
SEQ_TOHA = 2028950         # とは (as for; regarding)
SEQ_TOKA = 1008530         # とか
SEQ_TOSHITE = 1008590      # として
SEQ_DESAE = 2034520        # でさえ

# --- Other Particles ---
SEQ_DAKE = 1007340         # だけ (only)
SEQ_GORO = 1579080         # ごろ (around time)
SEQ_MADE = 1525680         # まで (until)
SEQ_NADO = 1582300         # など (etc)
SEQ_NOMI = 1009990         # のみ (only)
SEQ_SAE = 1005120          # さえ (even)
SEQ_TTE = 2086960          # って (quoting)
SEQ_KARA = 1002980         # から (from/because)
SEQ_NITOTTE = 1009600      # にとって (for; to; concerning)

# --- Pronouns vs Suffixes (disambiguation needed) ---
SEQ_KIMI = 1247250         # 君 (きみ) - pronoun "you"
SEQ_KUN = 1247260          # 君 (くん) - suffix "Mr."

# --- Common Verbs ---
SEQ_SURU = 1157170         # する
SEQ_IRU = 1577980          # いる (居る - to be animate)
SEQ_KURU = 1547720         # 来る
SEQ_ARU = 1296400          # ある (to exist)
SEQ_NARU = 1375610         # なる (to become)
SEQ_TOMU = 1496740         # 富む (blocked in nai-x - uncommon)
SEQ_ORU = 1577985          # おる (humble/dialect for いる)
SEQ_OKU = 1421850          # おく (to do in advance)
SEQ_IKU = 1578850          # いく (to go)
SEQ_SHIMAU = 1305380       # しまう (to finish/complete)
SEQ_MORAU = 1535910        # もらう (to receive)
SEQ_ITADAKU = 1587290      # いただく (to receive - humble)
SEQ_KURERU = 1269130       # くれる (to give)
SEQ_MIRU = 1259290         # 見る/みる (to see; try doing)
SEQ_AGERU = 1352320        # 上げる/あげる (to give; do for someone)
SEQ_HOSHII = 1547330       # 欲しい/ほしい (to want someone to)

# --- Honorific/Humble Verb Forms ---
SEQ_ITASU = 1421900        # いたす (humble form of する)
SEQ_SARERU = 2269820       # される (honorific/passive する)
SEQ_SASERU = 1005160       # させる (causative)
SEQ_TOKU = 2108590         # とく (contraction of ておく)

# --- Auxiliary Verbs ---
SEQ_CHAU = 2013800         # ちゃう (contraction of てしまう)
SEQ_CHIMAU = 2210750       # ちまう (contraction of てしまう)
SEQ_TAI = 2017560          # たい (want to)

# --- Adjectives ---
SEQ_NAI = 2029110          # ない (negative adjective)
SEQ_II = 2820690           # いい/良い (good)

# --- Suffix-related ---
SEQ_NIKUI = 2772730        # にくい (hard to)
SEQ_YASUI = 2028620        # やすい (easy to)
SEQ_SUGIRU = 1398990       # すぎる (too much)
SEQ_TSUZUKERU = 1405800    # 続ける (to continue)
SEQ_TSUTSU = 2027910       # つつ (while)
SEQ_NAGARA = 1459640       # ながら (while doing)
SEQ_URU = 1454500          # うる (can - classical)
SEQ_KUDASAI = 1184270      # ください (please do)
SEQ_SOU = 1006610          # そう (looks like)
SEQ_SOU_NI_NAI = 2141080   # そうにない (doesn't seem like)
SEQ_PPOI = 2083720         # っぽい (-ish, tends to)
SEQ_GATAI = 2867504        # がたい (difficult to, hard to)
SEQ_DASU = 1338180         # 出す (to burst out doing / start doing)
SEQ_KIRU = 1384830         # 切る/きる (to do completely)
SEQ_KATA = 1516925         # 方/かた (way of doing)
SEQ_MI = 2258670           # み (-ness, adjective nominalization)
SEQ_YASUI = 1156990        # やすい (easy to, likely to)
SEQ_MAKURU = 1257800       # まくる (to do relentlessly)
SEQ_NAOSU = 1599390        # 直す/なおす (to redo)
SEQ_SOKONAU = 1596510      # 損なう/そこなう (to fail to do)
SEQ_WASURERU = 1519210     # 忘れる/わすれる (to forget to do)
SEQ_OERU = 1332760         # 終える/おえる (to finish doing)
SEQ_ZURAI = 2096480        # づらい (difficult to)
SEQ_GIMI = 1790980         # ぎみ (-like, tending to)
SEQ_PPANASHI = 1008020     # っぱなし (left doing)
SEQ_TACHI = 1416220        # たち (plural suffix)
SEQ_AU = 1284430           # 合う/あう (mutual/reciprocal - do together)
SEQ_KOMU = 1593410         # 込む/こむ (into/thoroughly)
SEQ_HOUDAI = 1516770       # 放題/ほうだい (as much as one likes)
SEQ_OWARU = 1589600        # 終わる/おわる (to finish doing)
SEQ_HAJIMERU = 1307550     # 始める/はじめる (to start doing)
SEQ_TSUKERU = 1331540      # つける (to be accustomed to)
SEQ_YARU = 1012980         # やる (do for someone - casual)
SEQ_MAIRU = 1302070        # まいる (humble going/coming)
SEQ_KUDASARU = 1184280     # くださる (honorific giving/doing for)
SEQ_SASHIAGERU = 1291270   # さしあげる (humble giving/doing for)

# --- Synthetic Entries ---
SEQ_TASOU = 900000         # たそう (synthetic: tai+sou suffix)
SEQ_MOII = 900001          # もいい (synthetic: て+もいい suffix)

# --- Compound Expressions ---
SEQ_MAE_NOUN = 1392580     # 前/まえ (before - noun reading, not ぜん prefix)
SEQ_HOU_NOUN = 1516930     # 方/ほう (direction - noun reading, not かた)
SEQ_MEN_NOUN = 1584695     # 面/めん (aspect - noun suffix reading, not つら)
SEQ_HITO_NOUN = 1580640    # 人/ひと (person - noun reading, not じん suffix)
SEQ_JIN_SUFFIX = 1366410   # 人/じん (suffix -ian, -er)
SEQ_NAKA_NOUN = 1423310    # 中/なか (inside/middle - noun reading, not ちゅう)
SEQ_SEN_NOUN = 2080730     # 戦/せん (match/game - noun reading, not いくさ)
SEQ_IKUSA_NOUN = 1587140   # 戦/いくさ (war/battle)
SEQ_TOMARU = 1310620       # 止まる/とまる (to stop)
SEQ_TODOMARU = 2657130     # 止まる/とどまる (to stay/remain)
SEQ_KARAI = 1365850        # 辛い/からい (spicy/hot)
SEQ_TSURAI = 1365860       # 辛い/つらい (painful/hard)
SEQ_KADOUKA = 2087300      # かどうか (whether or not)
SEQ_NITSURE = 2136050      # につれ (as; in proportion to)
SEQ_OSUSUME = 1002150      # おすすめ (recommendation)
SEQ_HYAKUEN_SHOP = 2100330 # 百円ショップ
SEQ_DENAITO = 2009070      # でないと (without; but if)
SEQ_MURI_WO_SURU = 2838589 # 無理をする
SEQ_UN_GA_II = 1172620     # 運がいい
SEQ_KI_GA_SURU = 1221540   # 気がする
SEQ_HITO_GA_II = 2250200   # 人がいい

# --- Prefix ---
SEQ_O_PREFIX = 2826528     # お (polite prefix)

# --- Blocked SEQs ---
# Words blocked in specific suffix handlers

# Blocked from nai suffix abbreviation (abbr-nee and abbr-n)
# See ichiran dict-grammar.lisp
BLOCKED_NAI_SEQS: Set[int] = {SEQ_IRU, SEQ_KURU}

# Blocked from nai-x abbreviation (ず, ざる, ぬ)
# する creates せず issues, 富む creates とまず false matches
BLOCKED_NAI_X_SEQS: Set[int] = {SEQ_SURU, SEQ_TOMU}

# --- Particle Sets ---
# Particles that can follow nouns (for noun+particle synergy)
NOUN_PARTICLES: Set[int] = {
    SEQ_WA, SEQ_GA, SEQ_NI, SEQ_DE, SEQ_HE,
    SEQ_DAKE, SEQ_GORO, SEQ_MADE, SEQ_MO,
    SEQ_NADO, SEQ_NIHA, SEQ_NO, SEQ_NOMI,
    SEQ_WO, SEQ_SAE, SEQ_DESAE, SEQ_TO,
    SEQ_TOKA, SEQ_TOSHITE, SEQ_TOHA, SEQ_YA,
    SEQ_NITOTTE,
}


# ============================================================================
# Suffix Descriptions
# ============================================================================
# Human-readable descriptions for particle/suffix seqs

SUFFIX_DESCRIPTION: Dict[int, str] = {
    SEQ_O_PREFIX: 'polite prefix',      # お
    SEQ_DE: 'at / in / by',             # で
    SEQ_KA: 'or / questioning particle', # か
    SEQ_NI: 'to / at / in',             # に
    SEQ_WO: 'indicates direct object of action',  # を
    SEQ_NO: "indicates possessive (...'s)",  # の
    SEQ_TTE: 'quoting particle',        # って
    SEQ_KARA: 'from / because',         # から
}


def verify_seq_constants(session) -> List[str]:
    """
    Verify all SEQ constants still match expected text in database.
    
    Returns:
        List of mismatch descriptions. Empty if all OK.
    """
    from himotoki.db.models import KanaText
    from sqlalchemy import select
    
    # (constant_name, seq, expected_text)
    checks = [
        ('SEQ_WA', SEQ_WA, 'は'),
        ('SEQ_GA', SEQ_GA, 'が'),
        ('SEQ_NI', SEQ_NI, 'に'),
        ('SEQ_DE', SEQ_DE, 'で'),
        ('SEQ_TO', SEQ_TO, 'と'),
        ('SEQ_SURU', SEQ_SURU, 'する'),
        ('SEQ_IRU', SEQ_IRU, 'いる'),
        ('SEQ_KURU', SEQ_KURU, 'くる'),
        ('SEQ_NAI', SEQ_NAI, 'ない'),
    ]
    
    mismatches = []
    for name, seq, expected in checks:
        result = session.execute(
            select(KanaText.text).where(KanaText.seq == seq).limit(1)
        ).scalar()
        if result != expected:
            mismatches.append(f"{name} (seq={seq}): expected '{expected}', got '{result}'")
    
    return mismatches
