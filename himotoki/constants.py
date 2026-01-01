"""
Constants for Himotoki - exact 1:1 port from Ichiran.

All sequence numbers are taken directly from Ichiran's dict-grammar.lisp
and dict-errata.lisp files.
"""

from typing import Set

# ============================================================================
# NOUN PARTICLES (from Ichiran's *noun-particles* in dict-grammar.lisp:800-823)
# Particles that naturally follow nouns
# ============================================================================

NOUN_PARTICLES: Set[int] = {
    2028920,   # は
    2028930,   # が
    2028990,   # に
    2028980,   # で
    2029000,   # へ
    1007340,   # だけ
    1579080,   # ごろ
    1525680,   # まで
    2028940,   # も
    1582300,   # など
    2215430,   # には
    1469800,   # の
    1009990,   # のみ
    2029010,   # を
    1005120,   # さえ/すら (appears twice in Ichiran for both readings)
    2034520,   # でさえ
    1008490,   # と
    1008530,   # とか
    1008590,   # として
    2028950,   # とは
    2028960,   # や
    1009600,   # にとって
}


# ============================================================================
# FINAL PARTICLES (from Ichiran's dict-errata.lisp)
# Particles that should only appear at sentence end
# ============================================================================

FINAL_PRT: Set[int] = {
    2017770,   # かい
    2425930,   # なの
    2130430,   # け/っけ
    2029130,   # ぞ
    2834812,   # ぜ
    2718360,   # がな
    2201380,   # わい
    2722170,   # のう
    2751630,   # かいな
}


# ============================================================================
# SEMI-FINAL PARTICLES (from Ichiran's *semi-final-prt*)
# Particles that can appear sentence-finally but also mid-sentence
# Penalty of -15 when not at end
# ============================================================================

SEMI_FINAL_PRT: Set[int] = FINAL_PRT | {
    2029120,   # さ
    2086640,   # し
    2029110,   # な
    2029080,   # ね
    2029100,   # わ
}


# ============================================================================
# SKIP WORDS (from Ichiran's *skip-words* in dict-errata.lisp)
# Suffix-only words that should not start a segment
# ============================================================================

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
    900000,    # たそう (custom entry)
}


# ============================================================================
# COPULAE (from Ichiran)
# ============================================================================

COPULA_DA: int = 2089020        # だ
COPULA_DESU: int = 1628500      # です (also 1007370 alternate)
COPULA_DESU_ALT: int = 1007370  # です (alternate entry)
COPULA_DAROU: int = 1928670     # だろう


# ============================================================================
# AUXILIARY VERBS (from Ichiran's *aux-verbs* in dict-grammar.lisp:1011-1014)
# ============================================================================

AUX_VERBS: Set[int] = {
    1342560,   # 初める/そめる
}


# ============================================================================
# HONORIFICS (from Ichiran's *honorifics* in dict-grammar.lisp:1158)
# ============================================================================

HONORIFICS: Set[int] = {
    1247260,   # 君
}


# ============================================================================
# PARTICLE SEQ NUMBERS (commonly referenced)
# ============================================================================

SEQ_HA: int = 2028920       # は
SEQ_GA: int = 2028930       # が
SEQ_WO: int = 2029010       # を
SEQ_NI: int = 2028990       # に
SEQ_DE: int = 2028980       # で
SEQ_HE: int = 2029000       # へ
SEQ_TO: int = 1008490       # と
SEQ_MO: int = 2028940       # も
SEQ_NO: int = 1469800       # の
SEQ_YA: int = 2028960       # や
SEQ_KA: int = 2028970       # か (or / questioning particle)

SEQ_N: int = 2139720        # ん (contraction of の)
SEQ_NDA: int = 2849370      # んだ
SEQ_NDA_ALT: int = 2849387  # んだ (alternate)


# ============================================================================
# SPECIAL SYNERGY SEQ NUMBERS (from def-generic-synergy definitions)
# ============================================================================

# の + 通り pattern (dict-grammar.lisp:935-939)
SEQ_TOORI: int = 1432920    # 通り

# しか + negative pattern (dict-grammar.lisp:927-933)
SEQ_SHIKA: int = 1005460    # しか

# そう + なんだ pattern (dict-grammar.lisp:851-855)
SEQ_SOU: int = 2137720      # そう
SEQ_NANDA: int = 2140410    # なんだ

# shicha-ikenai pattern (dict-grammar.lisp:919-925)
# Compound ending with は + いけない/いけません/だめ/いかん/いや
SEQ_IKENAI: Set[int] = {
    1000730,   # いけない
    1612750,   # いけません
    1409110,   # だめ
    2829697,   # いかん
    1587610,   # いや
}

# 思う/言う for と splitting (dict-grammar.lisp:1138-1141)
SEQ_OMOU: int = 1589350     # 思う
SEQ_IU: int = 1587040       # 言う
SEQ_NANDATO: int = 2837117  # 何だと

# Basic words
SEQ_NAI: int = 1529520      # ない
SEQ_ARU: int = 1296400      # ある
SEQ_IRU: int = 1577980      # いる


# ============================================================================
# SUFFIX SEQ NUMBERS (for suffix patterns)
# ============================================================================

# 中 (chu) suffix (dict-grammar.lisp:883-887)
SEQ_CHU: Set[int] = {1620400, 2083570}

# たち suffix (dict-grammar.lisp:889-893)
SEQ_TACHI: int = 1416220

# ぶり suffix (dict-grammar.lisp:895-899)
SEQ_BURI: int = 1361140

# 性 suffix (dict-grammar.lisp:901-905)
SEQ_SEI: int = 1375260

# 置き (oki) pattern with counter (dict-grammar.lisp:944-948)
SEQ_OKI: Set[int] = {2854117, 2084550}


# ============================================================================
# PREFIX SEQ NUMBERS (for prefix patterns)
# ============================================================================

# お (polite prefix) (dict-grammar.lisp:907-911)
SEQ_O_PREFIX: int = 1270190

# 未/不/無 (kanji negative prefixes) (dict-grammar.lisp:913-917)
SEQ_KANJI_PREFIX: Set[int] = {
    2242840,   # 未
    1922780,   # 不
    2423740,   # 無
}


# ============================================================================
# TE-FORM SUFFIX VERBS (for te+iru patterns)
# ============================================================================

# いる (to be, continuous auxiliary) seq=1577980
SEQ_IRU_AUX: int = 1577980

# ある (to exist, resultative auxiliary) seq=1296400  
SEQ_ARU_AUX: int = 1296400

# おる (humble いる) seq=1577985
SEQ_ORU_AUX: int = 1577985

# しまう (completion) seq=1305070 (already defined below)
# くる (to come, continuing action) seq=1547720 (already defined below)
# おく (to do in advance) seq=1421850
SEQ_OKU_AUX: int = 1421850

# いく (to go, starting and continuing) seq=1578850
SEQ_IKU_AUX: int = 1578850

# くれる (to give, asking to do for one) seq=1269130
SEQ_KURERU_AUX: int = 1269130

# もらう (to receive, asking to get someone to do) seq=1535910
SEQ_MORAU_AUX: int = 1535910

# All te-form auxiliary verbs
TE_FORM_AUXILIARIES: Set[int] = {
    1577980,   # いる
    1296400,   # ある
    1577985,   # おる
    1305070,   # しまう
    1547720,   # くる
    1421850,   # おく
    1578850,   # いく
    1269130,   # くれる
    1535910,   # もらう
}

# ============================================================================
# SEGFILTER-SPECIFIC SEQ NUMBERS
# ============================================================================

# segfilter-tsu-iru (dict-grammar.lisp:1019-1022)
SEQ_ITSU: int = 2221640     # いつ

# segfilter-wokarasu (dict-grammar.lisp:1024-1027)
SEQ_WOKARASU: int = 2087020

# segfilter-dashi: する して (dict-grammar.lisp:1147-1152)
SEQ_SURU: int = 1157170     # する
SEQ_SHITE: int = 2424740    # して
SEQ_SHIMAU: int = 1305070   # しまう

# segfilter-dekiru: 出 出来る (dict-grammar.lisp:1154-1157)
SEQ_DE_KANJI: Set[int] = {1896380, 2422860}   # 出
SEQ_KURU: int = 1547720                        # 来る
SEQ_KITERU: int = 2830009                      # 来てる

# segfilter-nohayamete (dict-grammar.lisp:1130-1133)
SEQ_HAYAMERU: int = 1601080  # 早める

# segfilter-totte (dict-grammar.lisp:1142-1145)
SEQ_TTE: int = 2086960      # って


# ============================================================================
# な/に PARTICLES (for na-adjective synergy)
# ============================================================================

SEQ_NA_PARTICLE: int = 2029110  # な (attributive/prohibitive)
SEQ_NI_PARTICLE: int = 2028990  # に


# ============================================================================
# CONJUGATION TYPE CONSTANTS (from Ichiran)
# ============================================================================

CONJ_TYPE_NON_PAST: int = 1           # 非過去
CONJ_TYPE_PAST: int = 2               # 過去
CONJ_TYPE_TE_FORM: int = 3            # て形
CONJ_TYPE_VOLITIONAL: int = 9         # 意志形
CONJ_TYPE_IMPERATIVE: int = 10        # 命令形
CONJ_TYPE_CONDITIONAL: int = 11       # 条件形
CONJ_TYPE_RENYOUKEI: int = 13         # 連用形 (continuative)
CONJ_TYPE_NEGATIVE_STEM: int = 14     # 否定語幹

# Extended conjugation types (from dict-errata.lisp)
CONJ_ADVERBIAL: int = 50              # 副詞形
CONJ_ADJECTIVE_STEM: int = 51         # 形容詞語幹
CONJ_NEGATIVE_STEM: int = 52          # 否定語幹
CONJ_CAUSATIVE_SU: int = 53           # 使役 (~す)
CONJ_ADJECTIVE_LITERARY: int = 54     # 古語形
