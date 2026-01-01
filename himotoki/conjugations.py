"""
Japanese verb and adjective conjugation system for Himotoki.

This module implements Japanese conjugation rules from scratch,
generating all conjugated forms for verbs and adjectives.

Conjugation Types:
    1  - Non-past (dictionary form / present-future)
    2  - Past (~た form)
    3  - Conjunctive (~て form)
    4  - Provisional (~ば form)
    5  - Potential
    6  - Passive
    7  - Causative
    8  - Causative-Passive
    9  - Volitional (~う/~よう form)
    10 - Imperative
    11 - Conditional (~たら form)
    12 - Alternative (~たり form)
    13 - Continuative (stem form)
    50 - Adverbial (adjective ~く form)
    51 - Adjective Stem
    52 - Negative Stem
    53 - Causative (~す form for godan)
    54 - Old/literary form
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from enum import IntEnum

from himotoki.characters import test_word, as_hiragana


# ============================================================================
# Conjugation Type Constants
# ============================================================================

class ConjType(IntEnum):
    """Conjugation type IDs matching Ichiran's system."""
    NON_PAST = 1
    PAST = 2
    CONJUNCTIVE = 3  # te-form
    PROVISIONAL = 4  # eba-form
    POTENTIAL = 5
    PASSIVE = 6
    CAUSATIVE = 7
    CAUSATIVE_PASSIVE = 8
    VOLITIONAL = 9
    IMPERATIVE = 10
    CONDITIONAL = 11  # tara-form
    ALTERNATIVE = 12  # tari-form
    CONTINUATIVE = 13  # stem/masu-stem
    ADVERBIAL = 50  # adjective ku-form
    ADJ_STEM = 51
    NEG_STEM = 52
    CAUSATIVE_SU = 53
    LITERARY = 54
    DESIDERATIVE = 55  # ~たい (want to)


CONJ_DESCRIPTIONS = {
    ConjType.NON_PAST: "Non-past",
    ConjType.PAST: "Past (~ta)",
    ConjType.CONJUNCTIVE: "Conjunctive (~te)",
    ConjType.PROVISIONAL: "Provisional (~eba)",
    ConjType.POTENTIAL: "Potential",
    ConjType.PASSIVE: "Passive",
    ConjType.CAUSATIVE: "Causative",
    ConjType.CAUSATIVE_PASSIVE: "Causative-Passive",
    ConjType.VOLITIONAL: "Volitional",
    ConjType.IMPERATIVE: "Imperative",
    ConjType.CONDITIONAL: "Conditional (~tara)",
    ConjType.ALTERNATIVE: "Alternative (~tari)",
    ConjType.CONTINUATIVE: "Continuative (~i)",
    ConjType.ADVERBIAL: "Adverbial (~ku)",
    ConjType.ADJ_STEM: "Adjective Stem",
    ConjType.NEG_STEM: "Negative Stem (~nai)",
    ConjType.CAUSATIVE_SU: "Causative (~su)",
    ConjType.LITERARY: "Old/literary form",
    ConjType.DESIDERATIVE: "Desiderative (~たい)",
}


def get_conj_description(conj_type: int) -> str:
    """Get human-readable description of conjugation type."""
    return CONJ_DESCRIPTIONS.get(conj_type, f"Type {conj_type}")


# ============================================================================
# Conjugation Rule Definition
# ============================================================================

@dataclass
class ConjugationRule:
    """
    A single conjugation rule.
    
    Attributes:
        pos: Part of speech (e.g., 'v1', 'v5k', 'adj-i')
        conj_type: Conjugation type ID
        neg: True if negative form, False if affirmative, None if N/A
        fml: True if formal/polite, False if plain, None if N/A
        stem_chars: Number of characters to remove from end
        okurigana: Suffix to add (kana form)
        okurigana_kanji: Suffix for kanji form (if different)
    """
    pos: str
    conj_type: int
    neg: Optional[bool]
    fml: Optional[bool]
    stem_chars: int
    okurigana: str
    okurigana_kanji: str = ""
    
    def apply(self, word: str, is_kana: bool = True) -> str:
        """
        Apply this conjugation rule to a word.
        
        Args:
            word: Base word to conjugate.
            is_kana: True if word is in kana, False if kanji.
            
        Returns:
            Conjugated form.
        """
        if not word:
            return word
        
        # Remove stem characters from end
        if self.stem_chars > 0 and len(word) >= self.stem_chars:
            stem = word[:-self.stem_chars]
        else:
            stem = word
        
        # Add okurigana
        suffix = self.okurigana if is_kana or not self.okurigana_kanji else self.okurigana_kanji
        return stem + suffix


# ============================================================================
# Godan (五段) Verb Conjugation - "u" ending verbs
# ============================================================================

# Godan verb endings and their stem transformations
# Maps: ending -> (a-row, i-row, u-row, e-row, o-row)
GODAN_STEMS = {
    'う': ('わ', 'い', 'う', 'え', 'お'),
    'く': ('か', 'き', 'く', 'け', 'こ'),
    'ぐ': ('が', 'ぎ', 'ぐ', 'げ', 'ご'),
    'す': ('さ', 'し', 'す', 'せ', 'そ'),
    'つ': ('た', 'ち', 'つ', 'て', 'と'),
    'ぬ': ('な', 'に', 'ぬ', 'ね', 'の'),
    'ぶ': ('ば', 'び', 'ぶ', 'べ', 'ぼ'),
    'む': ('ま', 'み', 'む', 'め', 'も'),
    'る': ('ら', 'り', 'る', 'れ', 'ろ'),
}

# Te-form / Ta-form sound changes for godan verbs
# Maps: ending -> (te-form suffix, ta-form suffix)
GODAN_TE_TA = {
    'う': ('って', 'った'),
    'く': ('いて', 'いた'),
    'ぐ': ('いで', 'いだ'),
    'す': ('して', 'した'),
    'つ': ('って', 'った'),
    'ぬ': ('んで', 'んだ'),
    'ぶ': ('んで', 'んだ'),
    'む': ('んで', 'んだ'),
    'る': ('って', 'った'),
}


def get_godan_stem(word: str, row: int) -> str:
    """
    Get godan verb stem for a specific vowel row.
    
    Args:
        word: Godan verb in dictionary form.
        row: 0=a, 1=i, 2=u, 3=e, 4=o
        
    Returns:
        Word with ending changed to specified row.
    """
    if not word:
        return word
    
    ending = word[-1]
    if ending in GODAN_STEMS:
        return word[:-1] + GODAN_STEMS[ending][row]
    return word


def generate_godan_rules(pos: str, ending: str) -> List[ConjugationRule]:
    """
    Generate all conjugation rules for a godan verb type.
    
    Args:
        pos: POS tag (e.g., 'v5k', 'v5g')
        ending: Verb ending character (e.g., 'く', 'ぐ')
        
    Returns:
        List of ConjugationRule objects.
    """
    rules = []
    stems = GODAN_STEMS.get(ending)
    te_ta = GODAN_TE_TA.get(ending)
    
    if not stems or not te_ta:
        return rules
    
    a_stem, i_stem, u_stem, e_stem, o_stem = stems
    te_suffix, ta_suffix = te_ta
    
    # Non-past (dictionary form) - affirmative plain
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, False, False, 0, ""))
    
    # Non-past negative plain: ~ない
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, False, 1, a_stem + "ない"))
    
    # Non-past affirmative formal: ~ます
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, False, True, 1, i_stem + "ます"))
    
    # Non-past negative formal: ~ません
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, True, 1, i_stem + "ません"))
    
    # Past affirmative plain: ~た
    rules.append(ConjugationRule(pos, ConjType.PAST, False, False, 1, ta_suffix[:-1] if ending == 'す' else ta_suffix.replace(ending, '')))
    # Fix: need to handle て/た forms properly
    te_base = te_suffix[:-1] if te_suffix.endswith('て') else te_suffix[:-1]
    ta_base = ta_suffix[:-1] if ta_suffix.endswith('た') else ta_suffix[:-1]
    
    # Recalculate properly
    if ending == 'す':
        rules[-1] = ConjugationRule(pos, ConjType.PAST, False, False, 1, "した")
    elif ending in ('う', 'つ', 'る'):
        rules[-1] = ConjugationRule(pos, ConjType.PAST, False, False, 1, "った")
    elif ending == 'く':
        rules[-1] = ConjugationRule(pos, ConjType.PAST, False, False, 1, "いた")
    elif ending == 'ぐ':
        rules[-1] = ConjugationRule(pos, ConjType.PAST, False, False, 1, "いだ")
    elif ending in ('ぬ', 'ぶ', 'む'):
        rules[-1] = ConjugationRule(pos, ConjType.PAST, False, False, 1, "んだ")
    
    # Past negative plain: ~なかった
    rules.append(ConjugationRule(pos, ConjType.PAST, True, False, 1, a_stem + "なかった"))
    
    # Past affirmative formal: ~ました
    rules.append(ConjugationRule(pos, ConjType.PAST, False, True, 1, i_stem + "ました"))
    
    # Past negative formal: ~ませんでした
    rules.append(ConjugationRule(pos, ConjType.PAST, True, True, 1, i_stem + "ませんでした"))
    
    # Te-form (conjunctive) affirmative: ~て
    if ending == 'す':
        rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, False, False, 1, "して"))
    elif ending in ('う', 'つ', 'る'):
        rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, False, False, 1, "って"))
    elif ending == 'く':
        rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, False, False, 1, "いて"))
    elif ending == 'ぐ':
        rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, False, False, 1, "いで"))
    elif ending in ('ぬ', 'ぶ', 'む'):
        rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, False, False, 1, "んで"))
    
    # Te-form negative: ~なくて / ~ないで
    rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, True, False, 1, a_stem + "なくて"))
    
    # Provisional (~ば form) affirmative: ~ば
    rules.append(ConjugationRule(pos, ConjType.PROVISIONAL, False, False, 1, e_stem + "ば"))
    
    # Provisional negative: ~なければ
    rules.append(ConjugationRule(pos, ConjType.PROVISIONAL, True, False, 1, a_stem + "なければ"))
    
    # Potential: ~える (e-stem + る)
    rules.append(ConjugationRule(pos, ConjType.POTENTIAL, False, False, 1, e_stem + "る"))
    
    # Potential negative: ~えない
    rules.append(ConjugationRule(pos, ConjType.POTENTIAL, True, False, 1, e_stem + "ない"))
    
    # Passive: ~あれる (a-stem + れる)
    rules.append(ConjugationRule(pos, ConjType.PASSIVE, False, False, 1, a_stem + "れる"))
    
    # Passive negative: ~あれない
    rules.append(ConjugationRule(pos, ConjType.PASSIVE, True, False, 1, a_stem + "れない"))
    
    # Causative: ~あせる (a-stem + せる)
    rules.append(ConjugationRule(pos, ConjType.CAUSATIVE, False, False, 1, a_stem + "せる"))
    
    # Causative negative: ~あせない
    rules.append(ConjugationRule(pos, ConjType.CAUSATIVE, True, False, 1, a_stem + "せない"))
    
    # Causative-Passive: ~あせられる
    rules.append(ConjugationRule(pos, ConjType.CAUSATIVE_PASSIVE, False, False, 1, a_stem + "せられる"))
    
    # Volitional: ~おう (o-stem + う)
    rules.append(ConjugationRule(pos, ConjType.VOLITIONAL, False, False, 1, o_stem + "う"))
    
    # Volitional formal: ~ましょう
    rules.append(ConjugationRule(pos, ConjType.VOLITIONAL, False, True, 1, i_stem + "ましょう"))
    
    # Imperative: ~え (e-stem)
    rules.append(ConjugationRule(pos, ConjType.IMPERATIVE, False, False, 1, e_stem))
    
    # Imperative negative: ~な (dictionary form + な)
    rules.append(ConjugationRule(pos, ConjType.IMPERATIVE, True, False, 0, "な"))
    
    # Conditional (~たら form): same as past + ら
    if ending == 'す':
        rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, False, False, 1, "したら"))
    elif ending in ('う', 'つ', 'る'):
        rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, False, False, 1, "ったら"))
    elif ending == 'く':
        rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, False, False, 1, "いたら"))
    elif ending == 'ぐ':
        rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, False, False, 1, "いだら"))
    elif ending in ('ぬ', 'ぶ', 'む'):
        rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, False, False, 1, "んだら"))
    
    # Conditional negative: ~なかったら
    rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, True, False, 1, a_stem + "なかったら"))
    
    # Alternative (~たり form): same as past + り
    if ending == 'す':
        rules.append(ConjugationRule(pos, ConjType.ALTERNATIVE, False, False, 1, "したり"))
    elif ending in ('う', 'つ', 'る'):
        rules.append(ConjugationRule(pos, ConjType.ALTERNATIVE, False, False, 1, "ったり"))
    elif ending == 'く':
        rules.append(ConjugationRule(pos, ConjType.ALTERNATIVE, False, False, 1, "いたり"))
    elif ending == 'ぐ':
        rules.append(ConjugationRule(pos, ConjType.ALTERNATIVE, False, False, 1, "いだり"))
    elif ending in ('ぬ', 'ぶ', 'む'):
        rules.append(ConjugationRule(pos, ConjType.ALTERNATIVE, False, False, 1, "んだり"))
    
    # Continuative (masu-stem): i-stem
    rules.append(ConjugationRule(pos, ConjType.CONTINUATIVE, None, None, 1, i_stem))
    
    # Negative stem: a-stem (for compounds like ~ない)
    rules.append(ConjugationRule(pos, ConjType.NEG_STEM, None, None, 1, a_stem))
    
    # ==== DESIDERATIVE (~たい - want to) ====
    # Desiderative affirmative: masu-stem + たい
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, False, False, 1, i_stem + "たい"))
    
    # Desiderative negative: masu-stem + たくない
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, True, False, 1, i_stem + "たくない"))
    
    # Desiderative past affirmative: masu-stem + たかった
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, False, True, 1, i_stem + "たかった"))
    
    # Desiderative past negative: masu-stem + たくなかった
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, True, True, 1, i_stem + "たくなかった"))
    
    return rules


# ============================================================================
# Ichidan (一段) Verb Conjugation - "ru" ending verbs (える/いる)
# ============================================================================

def generate_ichidan_rules(pos: str = "v1") -> List[ConjugationRule]:
    """
    Generate all conjugation rules for ichidan verbs.
    
    Ichidan verbs drop る and add the conjugation suffix.
    
    Args:
        pos: POS tag (usually 'v1' or 'v1-s')
        
    Returns:
        List of ConjugationRule objects.
    """
    rules = []
    
    # Non-past affirmative plain (dictionary form)
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, False, False, 0, ""))
    
    # Non-past negative plain: ~ない
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, False, 1, "ない"))
    
    # Non-past affirmative formal: ~ます
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, False, True, 1, "ます"))
    
    # Non-past negative formal: ~ません
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, True, 1, "ません"))
    
    # Past affirmative plain: ~た
    rules.append(ConjugationRule(pos, ConjType.PAST, False, False, 1, "た"))
    
    # Past negative plain: ~なかった
    rules.append(ConjugationRule(pos, ConjType.PAST, True, False, 1, "なかった"))
    
    # Past affirmative formal: ~ました
    rules.append(ConjugationRule(pos, ConjType.PAST, False, True, 1, "ました"))
    
    # Past negative formal: ~ませんでした
    rules.append(ConjugationRule(pos, ConjType.PAST, True, True, 1, "ませんでした"))
    
    # Te-form affirmative: ~て
    rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, False, False, 1, "て"))
    
    # Te-form negative: ~なくて
    rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, True, False, 1, "なくて"))
    
    # Provisional affirmative: ~れば
    rules.append(ConjugationRule(pos, ConjType.PROVISIONAL, False, False, 1, "れば"))
    
    # Provisional negative: ~なければ
    rules.append(ConjugationRule(pos, ConjType.PROVISIONAL, True, False, 1, "なければ"))
    
    # Potential: ~られる (can also be ~れる in colloquial)
    rules.append(ConjugationRule(pos, ConjType.POTENTIAL, False, False, 1, "られる"))
    
    # Potential negative: ~られない
    rules.append(ConjugationRule(pos, ConjType.POTENTIAL, True, False, 1, "られない"))
    
    # Passive: ~られる
    rules.append(ConjugationRule(pos, ConjType.PASSIVE, False, False, 1, "られる"))
    
    # Passive negative: ~られない
    rules.append(ConjugationRule(pos, ConjType.PASSIVE, True, False, 1, "られない"))
    
    # Causative: ~させる
    rules.append(ConjugationRule(pos, ConjType.CAUSATIVE, False, False, 1, "させる"))
    
    # Causative negative: ~させない
    rules.append(ConjugationRule(pos, ConjType.CAUSATIVE, True, False, 1, "させない"))
    
    # Causative-Passive: ~させられる
    rules.append(ConjugationRule(pos, ConjType.CAUSATIVE_PASSIVE, False, False, 1, "させられる"))
    
    # Volitional: ~よう
    rules.append(ConjugationRule(pos, ConjType.VOLITIONAL, False, False, 1, "よう"))
    
    # Volitional formal: ~ましょう
    rules.append(ConjugationRule(pos, ConjType.VOLITIONAL, False, True, 1, "ましょう"))
    
    # Imperative: ~ろ / ~よ
    rules.append(ConjugationRule(pos, ConjType.IMPERATIVE, False, False, 1, "ろ"))
    
    # Imperative negative: ~な
    rules.append(ConjugationRule(pos, ConjType.IMPERATIVE, True, False, 0, "な"))
    
    # Conditional: ~たら
    rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, False, False, 1, "たら"))
    
    # Conditional negative: ~なかったら
    rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, True, False, 1, "なかったら"))
    
    # Alternative: ~たり
    rules.append(ConjugationRule(pos, ConjType.ALTERNATIVE, False, False, 1, "たり"))
    
    # Continuative (masu-stem): drop る
    rules.append(ConjugationRule(pos, ConjType.CONTINUATIVE, None, None, 1, ""))
    
    # Negative stem
    rules.append(ConjugationRule(pos, ConjType.NEG_STEM, None, None, 1, ""))
    
    # ==== DESIDERATIVE (~たい - want to) ====
    # Desiderative affirmative: ~たい
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, False, False, 1, "たい"))
    
    # Desiderative negative: ~たくない
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, True, False, 1, "たくない"))
    
    # Desiderative past affirmative: ~たかった
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, False, True, 1, "たかった"))
    
    # Desiderative past negative: ~たくなかった
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, True, True, 1, "たくなかった"))
    
    return rules


# ============================================================================
# Irregular Verbs: する and 来る
# ============================================================================

def generate_suru_rules() -> List[ConjugationRule]:
    """Generate conjugation rules for する (to do)."""
    rules = []
    pos = "vs-i"
    
    # Non-past
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, False, False, 0, ""))
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, False, 2, "しない"))
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, False, True, 2, "します"))
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, True, 2, "しません"))
    
    # Past
    rules.append(ConjugationRule(pos, ConjType.PAST, False, False, 2, "した"))
    rules.append(ConjugationRule(pos, ConjType.PAST, True, False, 2, "しなかった"))
    rules.append(ConjugationRule(pos, ConjType.PAST, False, True, 2, "しました"))
    rules.append(ConjugationRule(pos, ConjType.PAST, True, True, 2, "しませんでした"))
    
    # Te-form
    rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, False, False, 2, "して"))
    rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, True, False, 2, "しなくて"))
    
    # Provisional
    rules.append(ConjugationRule(pos, ConjType.PROVISIONAL, False, False, 2, "すれば"))
    rules.append(ConjugationRule(pos, ConjType.PROVISIONAL, True, False, 2, "しなければ"))
    
    # Potential: できる (separate word, but also ~せる)
    rules.append(ConjugationRule(pos, ConjType.POTENTIAL, False, False, 2, "できる"))
    
    # Passive: される
    rules.append(ConjugationRule(pos, ConjType.PASSIVE, False, False, 2, "される"))
    rules.append(ConjugationRule(pos, ConjType.PASSIVE, True, False, 2, "されない"))
    
    # Causative: させる
    rules.append(ConjugationRule(pos, ConjType.CAUSATIVE, False, False, 2, "させる"))
    rules.append(ConjugationRule(pos, ConjType.CAUSATIVE, True, False, 2, "させない"))
    
    # Causative-Passive: させられる
    rules.append(ConjugationRule(pos, ConjType.CAUSATIVE_PASSIVE, False, False, 2, "させられる"))
    
    # Volitional
    rules.append(ConjugationRule(pos, ConjType.VOLITIONAL, False, False, 2, "しよう"))
    rules.append(ConjugationRule(pos, ConjType.VOLITIONAL, False, True, 2, "しましょう"))
    
    # Imperative
    rules.append(ConjugationRule(pos, ConjType.IMPERATIVE, False, False, 2, "しろ"))
    rules.append(ConjugationRule(pos, ConjType.IMPERATIVE, True, False, 0, "な"))
    
    # Conditional
    rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, False, False, 2, "したら"))
    rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, True, False, 2, "しなかったら"))
    
    # Alternative
    rules.append(ConjugationRule(pos, ConjType.ALTERNATIVE, False, False, 2, "したり"))
    
    # Continuative
    rules.append(ConjugationRule(pos, ConjType.CONTINUATIVE, None, None, 2, "し"))
    
    # Desiderative (~たい - want to do)
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, False, False, 2, "したい"))
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, True, False, 2, "したくない"))
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, False, True, 2, "したかった"))
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, True, True, 2, "したくなかった"))
    
    return rules


def generate_kuru_rules() -> List[ConjugationRule]:
    """Generate conjugation rules for 来る/くる (to come)."""
    rules = []
    pos = "vk"
    
    # Non-past
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, False, False, 0, ""))
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, False, 2, "こない"))
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, False, True, 2, "きます"))
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, True, 2, "きません"))
    
    # Past
    rules.append(ConjugationRule(pos, ConjType.PAST, False, False, 2, "きた"))
    rules.append(ConjugationRule(pos, ConjType.PAST, True, False, 2, "こなかった"))
    rules.append(ConjugationRule(pos, ConjType.PAST, False, True, 2, "きました"))
    rules.append(ConjugationRule(pos, ConjType.PAST, True, True, 2, "きませんでした"))
    
    # Te-form
    rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, False, False, 2, "きて"))
    rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, True, False, 2, "こなくて"))
    
    # Provisional
    rules.append(ConjugationRule(pos, ConjType.PROVISIONAL, False, False, 2, "くれば"))
    rules.append(ConjugationRule(pos, ConjType.PROVISIONAL, True, False, 2, "こなければ"))
    
    # Potential: 来られる/これる
    rules.append(ConjugationRule(pos, ConjType.POTENTIAL, False, False, 2, "こられる"))
    
    # Passive: 来られる
    rules.append(ConjugationRule(pos, ConjType.PASSIVE, False, False, 2, "こられる"))
    
    # Causative: 来させる
    rules.append(ConjugationRule(pos, ConjType.CAUSATIVE, False, False, 2, "こさせる"))
    
    # Causative-Passive: 来させられる
    rules.append(ConjugationRule(pos, ConjType.CAUSATIVE_PASSIVE, False, False, 2, "こさせられる"))
    
    # Volitional
    rules.append(ConjugationRule(pos, ConjType.VOLITIONAL, False, False, 2, "こよう"))
    rules.append(ConjugationRule(pos, ConjType.VOLITIONAL, False, True, 2, "きましょう"))
    
    # Imperative
    rules.append(ConjugationRule(pos, ConjType.IMPERATIVE, False, False, 2, "こい"))
    rules.append(ConjugationRule(pos, ConjType.IMPERATIVE, True, False, 0, "な"))
    
    # Conditional
    rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, False, False, 2, "きたら"))
    rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, True, False, 2, "こなかったら"))
    
    # Alternative
    rules.append(ConjugationRule(pos, ConjType.ALTERNATIVE, False, False, 2, "きたり"))
    
    # Continuative
    rules.append(ConjugationRule(pos, ConjType.CONTINUATIVE, None, None, 2, "き"))
    
    # Desiderative (~たい - want to come)
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, False, False, 2, "きたい"))
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, True, False, 2, "きたくない"))
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, False, True, 2, "きたかった"))
    rules.append(ConjugationRule(pos, ConjType.DESIDERATIVE, True, True, 2, "きたくなかった"))
    
    return rules


# ============================================================================
# I-Adjective (形容詞) Conjugation
# ============================================================================

def generate_i_adjective_rules(pos: str = "adj-i") -> List[ConjugationRule]:
    """
    Generate conjugation rules for i-adjectives.
    
    I-adjectives end in い and conjugate by changing the い ending.
    """
    rules = []
    
    # Non-past affirmative (dictionary form)
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, False, False, 0, ""))
    
    # Non-past negative: ~くない
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, False, 1, "くない"))
    
    # Non-past affirmative formal: ~いです
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, False, True, 0, "です"))
    
    # Non-past negative formal: ~くないです / ~くありません
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, True, 1, "くないです"))
    
    # Past affirmative: ~かった
    rules.append(ConjugationRule(pos, ConjType.PAST, False, False, 1, "かった"))
    
    # Past negative: ~くなかった
    rules.append(ConjugationRule(pos, ConjType.PAST, True, False, 1, "くなかった"))
    
    # Past affirmative formal: ~かったです
    rules.append(ConjugationRule(pos, ConjType.PAST, False, True, 1, "かったです"))
    
    # Past negative formal: ~くなかったです
    rules.append(ConjugationRule(pos, ConjType.PAST, True, True, 1, "くなかったです"))
    
    # Te-form: ~くて
    rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, False, False, 1, "くて"))
    
    # Te-form negative: ~くなくて
    rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, True, False, 1, "くなくて"))
    
    # Provisional: ~ければ
    rules.append(ConjugationRule(pos, ConjType.PROVISIONAL, False, False, 1, "ければ"))
    
    # Provisional negative: ~くなければ
    rules.append(ConjugationRule(pos, ConjType.PROVISIONAL, True, False, 1, "くなければ"))
    
    # Conditional: ~かったら
    rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, False, False, 1, "かったら"))
    
    # Conditional negative: ~くなかったら
    rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, True, False, 1, "くなかったら"))
    
    # Alternative: ~かったり
    rules.append(ConjugationRule(pos, ConjType.ALTERNATIVE, False, False, 1, "かったり"))
    
    # Adverbial: ~く
    rules.append(ConjugationRule(pos, ConjType.ADVERBIAL, None, None, 1, "く"))
    
    # Adjective stem: drop い
    rules.append(ConjugationRule(pos, ConjType.ADJ_STEM, None, None, 1, ""))
    
    # Literary/old form: ~き
    rules.append(ConjugationRule(pos, ConjType.LITERARY, None, None, 1, "き"))
    
    # ~さ (nominalization)
    # This creates a noun, handled separately
    
    # ~そう (seems like)
    # Also handled separately as suffix
    
    return rules


# ============================================================================
# Copula だ Conjugation
# ============================================================================

def generate_da_rules() -> List[ConjugationRule]:
    """Generate conjugation rules for the copula だ."""
    rules = []
    pos = "copula"  # Match JMdict POS tag
    
    # Non-past
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, False, False, 0, ""))
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, False, 1, "じゃない"))
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, False, True, 1, "です"))
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, True, 1, "じゃないです"))
    
    # Additional negative forms
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, False, 1, "ではない"))
    rules.append(ConjugationRule(pos, ConjType.NON_PAST, True, True, 1, "ではありません"))
    
    # Past
    rules.append(ConjugationRule(pos, ConjType.PAST, False, False, 1, "だった"))
    rules.append(ConjugationRule(pos, ConjType.PAST, True, False, 1, "じゃなかった"))
    rules.append(ConjugationRule(pos, ConjType.PAST, False, True, 1, "でした"))
    rules.append(ConjugationRule(pos, ConjType.PAST, True, True, 1, "じゃなかったです"))
    
    # Te-form
    rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, False, False, 1, "で"))
    rules.append(ConjugationRule(pos, ConjType.CONJUNCTIVE, True, False, 1, "じゃなくて"))
    
    # Provisional
    rules.append(ConjugationRule(pos, ConjType.PROVISIONAL, False, False, 1, "なら"))
    rules.append(ConjugationRule(pos, ConjType.PROVISIONAL, False, False, 1, "ならば"))
    rules.append(ConjugationRule(pos, ConjType.PROVISIONAL, True, False, 1, "じゃなければ"))
    
    # Volitional
    rules.append(ConjugationRule(pos, ConjType.VOLITIONAL, False, False, 1, "だろう"))
    rules.append(ConjugationRule(pos, ConjType.VOLITIONAL, False, True, 1, "でしょう"))
    
    # Conditional
    rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, False, False, 1, "だったら"))
    rules.append(ConjugationRule(pos, ConjType.CONDITIONAL, True, False, 1, "じゃなかったら"))
    
    return rules


# ============================================================================
# Master Conjugation Rule Registry
# ============================================================================

# POS tags that have conjugation rules
CONJUGATABLE_POS = {
    # Ichidan verbs
    'v1': 'ichidan',
    'v1-s': 'ichidan',
    
    # Godan verbs
    'v5u': 'godan-u',
    'v5u-s': 'godan-u',  # special u-verb (問う)
    'v5k': 'godan-k',
    'v5k-s': 'godan-k',  # iku special
    'v5g': 'godan-g',
    'v5s': 'godan-s',
    'v5t': 'godan-t',
    'v5n': 'godan-n',
    'v5b': 'godan-b',
    'v5m': 'godan-m',
    'v5r': 'godan-r',
    'v5r-i': 'godan-r',  # irregular (ある, etc.)
    'v5aru': 'godan-r',  # ある special
    
    # Irregular verbs
    'vs-i': 'suru',
    'vs-s': 'suru',  # suru with す ending
    'vk': 'kuru',
    
    # Adjectives
    'adj-i': 'i-adj',
    'adj-ix': 'i-adj',  # いい/良い
    
    # Copula
    'cop-da': 'copula',
    'cop': 'copula',
    'copula': 'copula',  # JMdict uses 'copula' POS tag
}

# Godan verb ending characters
GODAN_ENDINGS = {
    'godan-u': 'う',
    'godan-k': 'く',
    'godan-g': 'ぐ',
    'godan-s': 'す',
    'godan-t': 'つ',
    'godan-n': 'ぬ',
    'godan-b': 'ぶ',
    'godan-m': 'む',
    'godan-r': 'る',
}


def get_conjugation_rules(pos: str) -> List[ConjugationRule]:
    """
    Get all conjugation rules for a given POS.
    
    Args:
        pos: Part of speech tag.
        
    Returns:
        List of ConjugationRule objects.
    """
    conj_type = CONJUGATABLE_POS.get(pos)
    
    if not conj_type:
        return []
    
    if conj_type == 'ichidan':
        return generate_ichidan_rules(pos)
    elif conj_type.startswith('godan-'):
        ending = GODAN_ENDINGS.get(conj_type)
        if ending:
            return generate_godan_rules(pos, ending)
    elif conj_type == 'suru':
        return generate_suru_rules()
    elif conj_type == 'kuru':
        return generate_kuru_rules()
    elif conj_type == 'i-adj':
        return generate_i_adjective_rules(pos)
    elif conj_type == 'copula':
        return generate_da_rules()
    
    return []


def is_conjugatable(pos: str) -> bool:
    """Check if a POS has conjugation rules."""
    return pos in CONJUGATABLE_POS


def conjugate_word(word: str, pos: str) -> List[Tuple[str, ConjugationRule]]:
    """
    Generate all conjugations of a word.
    
    Args:
        word: Word to conjugate (in kana or kanji).
        pos: Part of speech.
        
    Returns:
        List of (conjugated_form, rule) tuples.
    """
    rules = get_conjugation_rules(pos)
    is_kana_word = test_word(word, 'kana')
    
    results = []
    for rule in rules:
        conjugated = rule.apply(word, is_kana_word)
        
        # Apply iku/yuku special fix ONLY for v5k-s verbs (not regular v5k)
        if pos == 'v5k-s' and word.endswith('く'):
            conjugated = fix_iku_conjugation(word, conjugated, rule)
        
        if conjugated != word or rule.conj_type == ConjType.NON_PAST:
            results.append((conjugated, rule))
    
    return results


# ============================================================================
# Special Handling
# ============================================================================

# Verbs that should NOT be conjugated (expressions, etc.)
DO_NOT_CONJUGATE_SEQ = {2765070, 2835284}

# POS tags to skip conjugation for
DO_NOT_CONJUGATE_POS = {'n', 'vs', 'adj-na', 'adj-no', 'adv', 'exp'}


def should_conjugate(pos: str, seq: Optional[int] = None) -> bool:
    """
    Check if a word should be conjugated.
    
    Args:
        pos: Part of speech.
        seq: Optional sequence number.
        
    Returns:
        True if the word should be conjugated.
    """
    if pos in DO_NOT_CONJUGATE_POS:
        return False
    
    if seq and seq in DO_NOT_CONJUGATE_SEQ:
        return False
    
    return is_conjugatable(pos)


# Special case for 行く (iku) - uses って/った instead of いて/いた
def fix_iku_conjugation(word: str, conjugated: str, rule: ConjugationRule) -> str:
    """
    Fix 行く conjugation (いく uses って/った, not いて/いた).
    """
    if word.endswith('く') and rule.pos in ('v5k', 'v5k-s'):
        # Check if this might be 行く
        if rule.conj_type in (ConjType.PAST, ConjType.CONJUNCTIVE, 
                              ConjType.CONDITIONAL, ConjType.ALTERNATIVE):
            # Replace いて/いた with って/った
            if conjugated.endswith('いて'):
                return conjugated[:-2] + 'って'
            elif conjugated.endswith('いた'):
                return conjugated[:-2] + 'った'
            elif conjugated.endswith('いたら'):
                return conjugated[:-3] + 'ったら'
            elif conjugated.endswith('いたり'):
                return conjugated[:-3] + 'ったり'
    
    return conjugated
