"""
Suffix handler functions for compound word matching.
"""

from typing import Optional, List, Dict, Tuple, Union, Any, Callable

from sqlalchemy.orm import Session

from himotoki.db.models import KanaText
from himotoki.constants import (
    SEQ_SURU,
    BLOCKED_NAI_SEQS, BLOCKED_NAI_X_SEQS,
)

from himotoki.grammar.suffixes import (
    find_word_with_conj_type,
    find_word_with_pos,
    find_word_with_neg_prop,
    find_word_suffix,
)

def _handler_tai(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle たい suffix - want to..."""
    if root == 'い':
        return []
    return find_word_with_conj_type(session, root, 13)  # Continuative


def _handler_ren(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle generic ren'youkei (continuative) suffix."""
    return find_word_with_conj_type(session, root, 13)


def _handler_teren(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle te-form + ren'youkei suffix (e.g., やがる - disdain)."""
    return find_word_with_conj_type(session, root, 13)  # Continuative


def _handler_neg(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle negative stem suffix."""
    from himotoki.lookup import CONJ_NEGATIVE_STEM
    return find_word_with_conj_type(session, root, 13, CONJ_NEGATIVE_STEM)


def _handler_chau(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """
    Handle ちゃう suffix - contracted てしまう (completion).
    
    Ports ichiran's suffix-chau from dict-grammar.lisp.
    The suffix starts with ち or じ (contracted from て or で).
    We reconstruct the te-form by:
    1. Looking at first char of suffix to determine て or で
    2. Concatenating root + て/で to form the te-form
    3. Looking up that te-form in the database
    
    For example: サボっちゃった
    - root = "サボっ"
    - suffix = "ちゃった" (first char is ち → て)
    - lookup "サボっ" + "て" = "サボって" as te-form
    """
    if not suffix:
        return []
    
    # Map first char of suffix to te/de
    first_char = suffix[0]
    if first_char == 'ち':
        te = 'て'
    elif first_char == 'じ':
        te = 'で'
    else:
        return []
    
    # Look up root + te as te-form conjugation
    te_form = root + te
    return find_word_with_conj_type(session, te_form, 3)


def _handler_to_contracted(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """
    Handle とく suffix - contracted ておく (doing in advance).
    
    Ports ichiran's suffix-to from dict-grammar.lisp.
    The suffix starts with と or ど (contracted from て or で).
    We reconstruct the te-form similarly to chau.
    
    For example: 置いとく
    - root = "置い"
    - suffix = "とく" (first char is と → て)  
    - lookup "置い" + "て" = "置いて" as te-form
    """
    if not suffix:
        return []
    
    # Map first char of suffix to te/de
    first_char = suffix[0]
    if first_char == 'と':
        te = 'て'
    elif first_char == 'ど':
        te = 'で'
    else:
        return []
    
    # Look up root + te as te-form conjugation
    te_form = root + te
    return find_word_with_conj_type(session, te_form, 3)


def _handler_te(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle て form suffix."""
    if root == 'で':
        return []
    if not root.endswith('て') and not root.endswith('で'):
        return []
    return find_word_with_conj_type(session, root, 3)  # Te-form


def _handler_teiru(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle ている suffix."""
    if root == 'いて':
        return []
    if not root.endswith('て') and not root.endswith('で'):
        return []
    # First try direct database lookup for te-form
    results = find_word_with_conj_type(session, root, 3)
    if results:
        return results
    # If not found, try to find root as a compound via suffix matching
    # This enables nested compounds like 勉強し続けている (勉強し + 続けて + いる)
    compound_results = find_word_suffix(session, root)
    return compound_results


def _handler_suru(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle する suffix - make verb from noun."""
    return find_word_with_pos(session, root, 'vs')


def _handler_sou(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle そう suffix - looks like.
    
    そう attaches to:
    1. Verb continuative form (ren'youkei): 食べそう, 降りそう
    2. Adjective stem (without い): 美しそう, 高そう
    3. Na-adjective root: 静かそう, 元気そう
    4. Negative なさ form: 情けなさそう
    """
    from himotoki.lookup import CONJ_ADJECTIVE_STEM, CONJ_ADVERBIAL
    if root in ('な', 'よ', 'よさ', 'に', 'き'):
        return []
    
    # Check for なさ ending (negative adjective)
    if root.endswith('なさ'):
        root_patched = root[:-1] + 'い'
        return find_word_with_neg_prop(session, root_patched)
    
    results = find_word_with_conj_type(session, root, 13, CONJ_ADJECTIVE_STEM, CONJ_ADVERBIAL)
    # Filter out なぜる (seq 10195060 for conjugated form) which incorrectly matches なぜ + そう
    # The word なぜ is the interrogative "why", not the verb "to stroke"
    results = [r for r in results if getattr(r, 'seq', None) != 10195060]
    
    # Also check for na-adjectives (静かそう, 元気そう)
    if not results:
        results = find_word_with_pos(session, root, 'adj-na')
    
    return results


def _handler_sugiru(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle すぎる suffix - too much.
    
    すぎる attaches to:
    1. Verb continuative form (ren'youkei): 食べすぎる, 飲みすぎる
    2. Adjective stem (without い): 高すぎる, 美しすぎる
    3. Na-adjective root: 静かすぎる, 元気すぎる
    4. Negative なさ form: 情けなさすぎる
    """
    if root == 'い':
        return []
    
    # Check for なさ ending
    if root.endswith('なさ') or root.endswith('無さ'):
        root_patched = root[:-1] + 'い'
        return find_word_with_neg_prop(session, root_patched)
    
    results = []
    
    # Try verb continuative form (ren'youkei, conj_type=13)
    results.extend(find_word_with_conj_type(session, root, 13))
    
    # Try adjective stem (add い and look for adj-i)
    root_i = root + 'い'
    results.extend(find_word_with_pos(session, root_i, 'adj-i'))
    
    # Try na-adjective root: 静かすぎる, 元気すぎる
    results.extend(find_word_with_pos(session, root, 'adj-na'))
    
    return results


def _handler_sa(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle さ suffix - -ness."""
    from himotoki.lookup import CONJ_ADJECTIVE_STEM
    result = find_word_with_conj_type(session, root, CONJ_ADJECTIVE_STEM)
    result.extend(find_word_with_pos(session, root, 'adj-na'))
    return result


def _handler_rou(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle だろう suffix - probably/conjecture.
    
    だろう attaches to:
    1. Verb dictionary form: 食べるだろう, 行くだろう
    2. Verb past form: 食べただろう
    3. Adjective dictionary form: 高いだろう
    4. Na-adjective root: 静かだろう
    5. Negative form: 食べないだろう
    """
    results = []
    
    # Try dictionary form (direct word lookup)
    results.extend(find_word_with_pos(session, root, 'v1'))
    results.extend(find_word_with_pos(session, root, 'v5'))
    results.extend(find_word_with_pos(session, root, 'adj-i'))
    results.extend(find_word_with_pos(session, root, 'adj-na'))
    
    # Try past form (conj_type=2)
    results.extend(find_word_with_conj_type(session, root, 2))
    
    # Try negative form
    if root.endswith('ない'):
        results.extend(find_word_with_neg_prop(session, root))
    
    return results


def _handler_adv(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle adverbial suffix."""
    from himotoki.lookup import CONJ_ADVERBIAL
    return find_word_with_conj_type(session, root, CONJ_ADVERBIAL)


def _handler_kudasai(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle ください suffix - please do."""
    if not root.endswith('て') and not root.endswith('で'):
        return []
    return find_word_with_conj_type(session, root, 3)


def _handler_teii(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle ていい suffix - ok if."""
    if not root.endswith('て') and not root.endswith('で'):
        return []
    return find_word_with_conj_type(session, root, 3)


def _handler_garu(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle がる suffix - feel/show signs of.
    
    がる attaches to adjective stems:
    1. i-adjective stem: 欲しがる (from 欲しい)
    2. tai-compound stem: 食べたがる (from 食べたい = 食べる + たい)
    3. sou-compound stem: よさそうがる
    """
    from himotoki.lookup import CONJ_ADJECTIVE_STEM
    if root in ('な', 'い', 'よ'):
        return []
    
    result = find_word_with_conj_type(session, root, CONJ_ADJECTIVE_STEM)
    
    # If no direct adjective match, check for tai compound chain
    # e.g., 食べたがる: root='食べた' → root+'い' = '食べたい' → tai compound
    if not result and root.endswith('た'):
        tai_form = root + 'い'  # Reconstruct potential たい form
        tai_results = find_word_suffix(session, tai_form)
        result.extend(tai_results)
    
    # Also check for そ ending (そう + がる)
    if root.endswith('そ'):
        root_patched = root[:-1] + 'う'
        result.extend(find_word_with_suffix(session, root_patched, 'sou'))
    
    return result


def _handler_nade(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle na-adjective て-form (で).
    
    で is the conjunctive/te-form for na-adjectives via copula だ:
    静かで (being quiet; quietly and...), 元気で (being healthy), etc.
    """
    return find_word_with_pos(session, root, 'adj-na')


def _handler_ra(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle ら suffix - plural."""
    if root.endswith('ら'):
        return []
    return find_word_with_pos(session, root, 'pn')


def _handler_ppoi(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle っぽい suffix - -ish / tends to.
    
    っぽい attaches to:
    1. Verb continuative stem: 忘れ + っぽい, 飽き + っぽい
    2. Nouns: 子供 + っぽい, 大人 + っぽい, 水 + っぽい
    3. Na-adjective root: 静か + っぽい
    
    Note: the っ is part of the suffix, so root already has it stripped.
    """
    result = find_word_with_conj_type(session, root, 13)  # Verb continuative
    result.extend(find_word_with_pos(session, root, 'n'))
    result.extend(find_word_with_pos(session, root, 'adj-na'))
    return result


def _handler_mi(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle み suffix - adjective nominalization (-ness).
    
    み converts adjectives to nouns:
    - i-adj: 深い → 深み (depth), 甘い → 甘み (sweetness)
    - na-adj: 静か → 静かみ (quietness)
    
    Root will be the adjective stem (without い for i-adj, or bare form for na-adj).
    """
    from himotoki.lookup import CONJ_ADJECTIVE_STEM
    result = find_word_with_conj_type(session, root, CONJ_ADJECTIVE_STEM)
    result.extend(find_word_with_pos(session, root, 'adj-na'))
    return result


def _handler_tachi(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle たち suffix - plural for people/animals.
    
    たち attaches to nouns and pronouns:
    学生たち, 子供たち, 私たち, 猫たち
    """
    result = find_word_with_pos(session, root, 'n')
    result.extend(find_word_with_pos(session, root, 'pn'))
    return result


def _handler_rashii(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle らしい suffix - seems like.
    
    らしい attaches to:
    1. Verb/adj conjugated forms (conj_type 2)
    2. ら-ending forms (conj_type 11) 
    3. Nouns: 男らしい, 春らしい, 学生らしい
    4. Na-adjective stems: 静からしい
    """
    result = find_word_with_conj_type(session, root, 2)
    result.extend(find_word_with_conj_type(session, root + 'ら', 11))
    # Also try noun lookup for noun+rashii patterns
    result.extend(find_word_with_pos(session, root, 'n'))
    result.extend(find_word_with_pos(session, root, 'adj-na'))
    return result


def _handler_desu(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle です suffix - formal copula."""
    # Negative copula forms (e.g., 〜ないです)
    if root.endswith('ない') or root.endswith('なかった'):
        return find_word_with_neg_prop(session, root)

    # na-adjective + copula (e.g., 大丈夫です, 静かでした)
    if len(root) < 2:
        return []
    return find_word_with_pos(session, root, 'adj-na')


def _handler_desho(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle でしょう suffix - polite conjecture.
    
    でしょう attaches to:
    1. Verb dictionary form: 食べるでしょう
    2. Verb past form: 食べたでしょう
    3. Adjective dictionary form: 高いでしょう
    4. Na-adjective root: 静かでしょう
    5. Negative form: 食べないでしょう
    """
    results = []
    
    # Try dictionary form (direct word lookup)
    results.extend(find_word_with_pos(session, root, 'v1'))
    results.extend(find_word_with_pos(session, root, 'v5'))
    results.extend(find_word_with_pos(session, root, 'adj-i'))
    results.extend(find_word_with_pos(session, root, 'adj-na'))
    
    # Try past form (conj_type=2)
    results.extend(find_word_with_conj_type(session, root, 2))
    
    # Try negative form
    if root.endswith('ない'):
        results.extend(find_word_with_neg_prop(session, root))
    
    return results


def _handler_tosuru(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle とする suffix - try to."""
    return find_word_with_conj_type(session, root, 9)  # Volitional


def _handler_kurai(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle くらい suffix - about/approximately.
    
    くらい attaches to:
    1. Verb dictionary form: 食べるくらい
    2. Verb past form: 食べたくらい
    3. Verb continuative form: 食べくらい (literary)
    4. Noun/pronoun: それくらい
    """
    results = []
    # Try past form
    results.extend(find_word_with_conj_type(session, root, 2))
    # Try continuative form
    results.extend(find_word_with_conj_type(session, root, 13))
    # Try dictionary form (verbs, adjectives)
    results.extend(find_word_with_pos(session, root, 'v1'))
    results.extend(find_word_with_pos(session, root, 'v5'))
    results.extend(find_word_with_pos(session, root, 'adj-i'))
    results.extend(find_word_with_pos(session, root, 'adj-na'))
    return results


def _handler_iadj(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle i-adjective suffix like げ, め."""
    from himotoki.lookup import CONJ_ADJECTIVE_STEM
    return find_word_with_conj_type(session, root, CONJ_ADJECTIVE_STEM)


# Abbreviation handlers

def _find_word_with_neg_prop_filtered(
    session: Session,
    word: str,
    blocked_seqs: set,
    allow_root: bool = False,
) -> List[Any]:
    """
    Find words with negative conjugation property, excluding certain root seqs.
    
    Ports ichiran's filter logic from abbr-nee and abbr-n in dict-grammar.lisp:
    (and (not (find (conj-data-from cdata) '(1577980 1547720)))
         (conj-neg (conj-data-prop cdata)))
    
    Args:
        session: Database session
        word: Word text to search for
        blocked_seqs: Set of from_seq values to exclude
        allow_root: If True, also return root forms
    
    Returns:
        List of word matches with negative conjugation, excluding blocked seqs
    """
    from himotoki.lookup import find_word_with_conj_prop
    
    def filter_fn(cdata):
        # Must be negative form
        if not (cdata.prop and hasattr(cdata.prop, 'neg') and cdata.prop.neg):
            return False
        # Exclude blocked root seqs (居ない, 来ない create problems)
        if cdata.from_seq in blocked_seqs:
            return False
        return True
    
    return find_word_with_conj_prop(session, word, filter_fn, allow_root=allow_root)


def _handler_abbr_nai(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """
    Handle ない abbreviation (ねえ, ねぇ, ねー etc.).
    
    Ports ichiran's abbr-nee from dict-grammar.lisp.
    Blocks いる (SEQ_IRU) and 来る (SEQ_KURU) conjugations to avoid false matches.
    Allows root forms (:allow-root t in ichiran).
    """
    return _find_word_with_neg_prop_filtered(
        session, root + 'ない', BLOCKED_NAI_SEQS, allow_root=True
    )


def _handler_abbr_nai_n(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """
    Handle ん contraction (nai-n suffix).
    
    Ports ichiran's abbr-n from dict-grammar.lisp.
    Blocks いる (SEQ_IRU) and 来る (SEQ_KURU) conjugations to avoid false matches.
    Does NOT allow root forms (differs from abbr-nee).
    
    Example: 考えてん should NOT match 考えていないん (negative of いる).
    Instead, it should match 考えて + ん separately.
    """
    return _find_word_with_neg_prop_filtered(
        session, root + 'ない', BLOCKED_NAI_SEQS, allow_root=False
    )


def _handler_abbr_nx(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """
    Handle ず/ざる/ぬ abbreviation (nai-x suffix).
    
    Ports ichiran's abbr-nx from dict-grammar.lisp.
    Blocks する (SEQ_SURU) and 富む (SEQ_TOMU) conjugations.
    Special case: せ -> しない (for する).
    """
    if root == 'せ':
        from himotoki.grammar.splits import find_word_conj_of
        return find_word_conj_of(session, 'しない', SEQ_SURU)
    
    from himotoki.lookup import find_word_with_conj_prop
    
    def filter_fn(cdata):
        # Must be negative form
        if not (cdata.prop and hasattr(cdata.prop, 'neg') and cdata.prop.neg):
            return False
        # Exclude blocked words (する, 富む)
        if cdata.from_seq in BLOCKED_NAI_X_SEQS:
            return False
        return True
    
    return find_word_with_conj_prop(session, root + 'ない', filter_fn)


def _handler_abbr_nakereba(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle なきゃ/なくちゃ abbreviation."""
    from himotoki.lookup import find_word_full
    return find_word_full(session, root + 'なければ')


def _handler_abbr_shimasho(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle ましょ abbreviation (of ましょう - polite volitional)."""
    from himotoki.lookup import find_word_full
    return find_word_full(session, root + 'ましょう')


def _handler_abbr_dewanai(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle じゃない abbreviation."""
    from himotoki.lookup import find_word_full
    return find_word_full(session, root + 'ではない')


def _handler_abbr_eba(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle conditional abbreviations (りゃ, きゃ, etc.)."""
    from himotoki.lookup import find_word_full
    # Map abbreviation to full conditional form
    suffix_map = {
        'ちゃ': 'てば',
        'りゃ': 'れば',
        'きゃ': 'けば',
        'ぎゃ': 'げば',
        'にゃ': 'ねば',
        'びゃ': 'べば',
        'みゃ': 'めば',
        'しゃ': 'せば',
    }
    full_suffix = suffix_map.get(suffix)
    if full_suffix:
        return find_word_full(session, root + full_suffix)
    return []


def _handler_abbr_ii(session: Session, root: str, suffix: str, kf: Optional[KanaText]) -> List[Any]:
    """Handle ええ abbreviation for いい."""
    from himotoki.lookup import find_word_full
    return find_word_full(session, root + 'いい')


# Mapping of suffix keywords to handlers
SUFFIX_HANDLERS: Dict[str, Callable] = {
    'tai': _handler_tai,
    'ren': _handler_ren,
    'ren+': _handler_ren,
    'ren-': _handler_ren,
    'neg': _handler_neg,
    'te': _handler_te,
    'teiru': _handler_teiru,
    'teiru+': _handler_teiru,
    'te+space': _handler_te,
    'suru': _handler_suru,
    'sou': _handler_sou,
    'sou+': _handler_sou,
    'sugiru': _handler_sugiru,
    'sa': _handler_sa,
    'adv': _handler_adv,
    'kudasai': _handler_kudasai,
    'teii': _handler_teii,
    'garu': _handler_garu,
    'teren': _handler_teren,
    'ra': _handler_ra,
    'rashii': _handler_rashii,
    'desu': _handler_desu,
    'tosuru': _handler_tosuru,
    'kurai': _handler_kurai,
    'iadj': _handler_iadj,
    'mi': _handler_mi,
    'nade': _handler_nade,
    'ppoi': _handler_ppoi,
    'tachi': _handler_tachi,
    'chau': _handler_chau,  # Contracted てしまう with te-reconstruction
    'to': _handler_to_contracted,  # Contracted ておく with te-reconstruction
    # Abbreviations - each has distinct behavior matching ichiran
    'nai': _handler_abbr_nai,      # ねえ, ねぇ, ねー - allows root forms
    'nai-x': _handler_abbr_nx,     # ず, ざる, ぬ - blocks する
    'nai-n': _handler_abbr_nai_n,  # ん contraction - blocks いる/来る, no root
    'nakereba': _handler_abbr_nakereba,
    'shimashou': _handler_abbr_shimasho,
    'dewanai': _handler_abbr_dewanai,
    'teba': _handler_abbr_eba,
    'reba': _handler_abbr_eba,
    'keba': _handler_abbr_eba,
    'geba': _handler_abbr_eba,
    'neba': _handler_abbr_eba,
    'beba': _handler_abbr_eba,
    'meba': _handler_abbr_eba,
    'seba': _handler_abbr_eba,
    'ii': _handler_abbr_ii,
}
