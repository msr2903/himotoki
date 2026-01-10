"""
Conjugation hints for learner-friendly vocabulary output.

This module provides human-readable explanations for common Japanese
grammar patterns. Used by VocabularyResult to add conjugation_hint field.
"""

from typing import Optional, Dict, List, Tuple

# =============================================================================
# Compound Phrases (indexed by first character for fast lookup)
# =============================================================================

# Multi-token grammar phrases that should be grouped together
# Key: first token, Value: list of (full_phrase, meaning)
COMPOUND_PHRASES: Dict[str, List[Tuple[str, str]]] = {
    # === か patterns ===
    "か": [
        ("かどうか", "whether or not"),
        ("かのように", "as if; as though"),
        ("かもしれない", "might; may; possibly"),
        ("かもしれません", "might; may (polite)"),
    ],
    # === こと patterns (N5-N4) ===
    "こと": [
        ("ことにする", "decide to"),
        ("ことになる", "it's been decided; will end up"),
        ("ことができる", "can; be able to"),
        ("ことがある", "sometimes; have experienced"),
    ],
    # === な patterns ===
    "な": [
        ("なければならない", "must; have to"),
        ("なければいけない", "must; have to"),
        ("なければなりません", "must (polite)"),
        ("なくてはならない", "must; have to"),
        ("なくてはいけない", "must; have to"),
        ("ないといけない", "must; have to"),
        ("なきゃ", "must (casual)"),
        ("なくちゃ", "must (casual)"),
        ("ないわけにはいかない", "must; have no choice but to"),
    ],
    # === なきゃ patterns ===
    "なきゃ": [
        ("なきゃいけない", "must; have to (casual)"),
        ("なきゃだめ", "must; have to (casual)"),
        ("なきゃならない", "must; have to (casual)"),
    ],
    # === と patterns ===
    "と": [
        ("といけない", "must (if not...)"),
        ("というのは", "what ~ means is"),
        ("ということだ", "it means that; I heard that"),
        ("ところだ", "about to; just did"),
    ],
    # === て patterns ===
    "て": [
        ("てはいけない", "must not; may not"),
        ("てはいけません", "must not (polite)"),
        ("てはだめ", "must not (casual)"),
        ("てもいい", "may; it's okay to"),
        ("てもいいですか", "may I...?"),
        ("ても", "even if; even though"),
        ("てたまらない", "unbearably; extremely"),
        ("てならない", "can't help but feel"),
        ("てほしい", "want someone to do"),
        ("ている", "~ing; currently"),
        ("ていた", "was ~ing"),
        ("ていない", "not ~ing"),
        ("てしまう", "completely; accidentally"),
        ("てしまった", "ended up; regrettably did"),
    ],
    # === は patterns ===
    "は": [
        ("はいけない", "must not"),
        ("はだめ", "must not (casual)"),
    ],
    # === ほど patterns ===
    "ほど": [
        ("ほど", "the more... the more"),
    ],
    # === わけ patterns ===
    "わけ": [
        ("わけだ", "no wonder; that's why"),
        ("わけがない", "no way that; impossible"),
        ("わけではない", "doesn't mean that"),
        ("わけにはいかない", "can't possibly; mustn't"),
    ],
    # === ば patterns ===
    "ば": [
        ("ばよかった", "should have; wish I had"),
        ("ばいい", "should; ought to"),
        ("ばかり", "just; only; nothing but"),
    ],
    # === た patterns ===
    "た": [
        ("たばかり", "just did"),
        ("たことがある", "have done before"),
        ("たことがない", "have never done"),
        ("たほうがいい", "had better"),
        ("たい", "want to"),
        ("たかった", "wanted to"),
        ("たくない", "don't want to"),
    ],
    # === に patterns ===
    "に": [
        ("において", "in; at; regarding"),
        ("に対して", "towards; regarding"),
        ("について", "about; concerning"),
        ("によって", "by means of; depending on"),
        ("にとって", "for; to (someone)"),
        ("にしても", "even if; even though"),
        ("にちがいない", "must be; no doubt"),
        ("にすぎない", "merely; nothing but"),
    ],
    # === の patterns ===
    "の": [
        ("のに", "although; even though"),
        ("ので", "because; since"),
        ("のだ", "it is that; the fact is"),
        ("のです", "it is that (polite)"),
    ],
    # === そ patterns ===
    "そ": [
        ("そうだ", "I heard that; seems like"),
        ("そうです", "I heard that (polite)"),
        ("そうにない", "unlikely to; doesn't seem"),
    ],
    # === よ patterns ===
    "よ": [
        ("ようにする", "to make sure to"),
        ("ようになる", "to come to; to become able"),
        ("ようとする", "try to; be about to"),
        ("ようがない", "no way to; cannot"),
    ],
    # === ざ patterns ===
    "ざ": [
        ("ざるをえない", "can't help but; have to"),
    ],
    # === し patterns ===
    "し": [
        ("しかない", "have no choice but to"),
        ("しかたがない", "can't be helped"),
    ],
    # === せ patterns ===
    "せ": [
        ("せいだ", "because of (negative cause)"),
        ("せいで", "because of (negative cause)"),
    ],
    # === お patterns ===
    "お": [
        ("おかげだ", "thanks to (positive cause)"),
        ("おかげで", "thanks to (positive cause)"),
    ],
    # === ど patterns ===
    "ど": [
        ("どころか", "far from; let alone"),
        ("どころではない", "not in a position to"),
    ],
    # === だ patterns ===
    "だ": [
        ("だけでなく", "not only... but also"),
    ],
    # === ちゃ patterns (casual contractions) ===
    "ちゃ": [
        ("ちゃう", "end up doing (casual)"),
        ("ちゃった", "ended up doing"),
        ("ちゃいけない", "must not (casual)"),
        ("ちゃだめ", "must not (casual)"),
    ],
    # === じゃ patterns ===
    "じゃ": [
        ("じゃない", "isn't"),
        ("じゃないですか", "isn't it?"),
    ],
    # === らしい patterns ===
    "らしい": [
        ("らしい", "seems like; apparently"),
        ("らしいです", "seems like (polite)"),
    ],
    # === みたい patterns ===
    "みたい": [
        ("みたいだ", "seems like; looks like"),
        ("みたいです", "seems like (polite)"),
    ],
    # === ため patterns ===
    "ため": [
        ("ために", "in order to; for the sake of"),
    ],
    # === よう patterns (additional) ===
    "よう": [
        ("ような", "like; such as"),
        ("ように", "so that; in order to"),
        ("ようだ", "seems like; appears"),
    ],
    # === がち patterns ===
    "がち": [
        ("がちだ", "tend to; prone to"),
    ],
    # === かけ patterns ===
    "かけ": [
        ("かける", "start doing; partially do"),
    ],
    # === きれ patterns ===
    "きれ": [
        ("きれる", "can do completely"),
        ("きれない", "cannot finish; unbearable"),
    ],
    # === づらい patterns ===
    "づらい": [
        ("づらい", "hard to (physical/habitual)"),
    ],
    # === にくい patterns ===
    "にくい": [
        ("にくい", "hard to; difficult to"),
    ],
    # === やすい patterns ===
    "やすい": [
        ("やすい", "easy to"),
    ],
    # === すぎ patterns ===
    "すぎ": [
        ("すぎる", "too much; excessively"),
        ("すぎた", "was too much"),
    ],
    # === ながら patterns ===
    "ながら": [
        ("ながら", "while doing; although"),
    ],
    # === まま patterns ===
    "まま": [
        ("まま", "as is; in the state of"),
        ("ままだ", "is still in the state of"),
    ],
}


def get_conjugation_hint(text: str) -> Optional[str]:
    """
    Look up a conjugation hint for the given text.
    
    Args:
        text: The word or phrase text to look up
        
    Returns:
        A human-readable hint string if found, None otherwise
        
    Example:
        >>> get_conjugation_hint("なければならない")
        "must; have to"
        >>> get_conjugation_hint("てもいい")
        "may; it's okay to"
    """
    if not text:
        return None
    
    # Check compound phrases (indexed by first char)
    first_char = text[0]
    if first_char in COMPOUND_PHRASES:
        for phrase, meaning in COMPOUND_PHRASES[first_char]:
            # Exact match or text ends with the phrase
            if text == phrase or text.endswith(phrase):
                return meaning
    
    # Also check for suffix patterns anywhere in the text
    for key, patterns in COMPOUND_PHRASES.items():
        for phrase, meaning in patterns:
            if phrase in text and len(phrase) >= 2:
                return meaning
    
    return None


def get_all_hints() -> Dict[str, str]:
    """Get all conjugation hints as a flat dictionary."""
    result = {}
    for patterns in COMPOUND_PHRASES.values():
        for phrase, meaning in patterns:
            result[phrase] = meaning
    return result
