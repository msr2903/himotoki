"""
Output types and constants.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union
from enum import Enum

# ============================================================================
# Enums and Constants
# ============================================================================

class WordType(Enum):
    """Word type classification."""
    KANJI = 'kanji'
    KANA = 'kana'
    GAP = 'gap'


# Special conjugation info for entries that are standalone but represent
# conjugated forms of other entries (like です being formal non-past of だ)
# Format: seq -> (from_seq, conj_type, pos, neg, fml)
SPECIAL_CONJ_INFO: Dict[int, tuple] = {
    1628500: (2089020, 1, 'cop', False, True),  # です = non-past formal of だ
}

# Particle seqs that should NOT display conjugation info even if they match
# conjugated forms. These are standalone particles that happen to look like
# conjugated forms but should be treated as particles in most contexts.
# Example: で (seq 2028980) can be copula だ conjunctive form, but when it's
# matched as a standalone word, it's almost always the case particle.
SUPPRESS_CONJ_FOR_PARTICLES: set = {
    2028980,  # で - case particle (location/means), not copula て-form
}

# Words that have their own standalone dictionary meaning and should NOT
# display as conjugated forms of other verbs, even though the DB links them.
# These are typically nominalized verb forms that became independent nouns.
SUPPRESS_CONJ_FOR_NOUNS: set = {
    1382980,  # 積もり (つもり) - intention/plan noun, not continuative of 積もる
}

# Verbs that have their own dictionary entry but might be mistakenly identified
# as potential or other conjugated forms of different verbs. These should show
# their own glosses, not conjugation info from another verb.
SUPPRESS_CONJ_FOR_VERBS: set = {
    1345930,  # 傷つける - standalone transitive v1, not potential of 傷つく
}


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class WordInfo:
    """
    Word information for output.
    Mirrors ichiran's word-info class.
    """
    type: WordType  # :kanji, :kana, or :gap
    text: str  # Surface text
    kana: Union[str, List[str]]  # Reading(s)
    
    # Optional fields
    true_text: Optional[str] = None  # Original text (for proxy text)
    seq: Optional[Union[int, List[int]]] = None  # JMdict sequence number(s)
    conjugations: Optional[Union[List[int], str]] = None  # Conjugation IDs or 'root'
    score: int = 0
    components: List['WordInfo'] = field(default_factory=list)  # For compound words (WordInfo objects)
    compound_texts: List[str] = field(default_factory=list)  # Component texts for suffix compounds
    alternative: bool = False  # True if multiple readings available
    primary: bool = True  # Is this the primary reading
    start: Optional[int] = None
    end: Optional[int] = None
    counter: Optional[List[Any]] = None  # [value, ordinal] for counter words
    skipped: int = 0  # Number of skipped alternatives
    
    # Conjugation info fields
    is_compound: bool = False  # True if this is a compound word
    conj_type: Optional[str] = None  # Human-readable conjugation type
    conj_neg: bool = False  # True if negative form
    conj_fml: bool = False  # True if formal/polite form
    source_text: Optional[str] = None  # Dictionary form for conjugated words
    
    # NEW: Meanings and POS - populated during analysis
    meanings: List[str] = field(default_factory=list)  # List of gloss strings
    pos: Optional[str] = None  # Part of speech (e.g., "[n,vs,vt]")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (for JSON serialization)."""
        return {
            'type': self.type.value.upper(),
            'text': self.text,
            'truetext': self.true_text,
            'kana': self.kana,
            'seq': self.seq,
            'conjugations': 'ROOT' if self.conjugations == 'root' else self.conjugations,
            'score': self.score,
            'components': [c.to_dict() for c in self.components] if self.components else [],
            'compound_texts': self.compound_texts,
            'alternative': self.alternative,
            'primary': self.primary,
            'start': self.start,
            'end': self.end,
            'counter': self.counter,
            'skipped': self.skipped,
            'is_compound': self.is_compound,
            'conj_type': self.conj_type,
            'conj_neg': self.conj_neg,
            'conj_fml': self.conj_fml,
            'source_text': self.source_text,
            'meanings': self.meanings,
            'pos': self.pos,
        }


@dataclass
class ConjStep:
    """One step in a conjugation breakdown chain."""
    conj_type: str       # e.g., "Passive", "Past (~ta)"
    suffix: str          # e.g., "られる", "た"
    gloss: str           # e.g., "is done (to)", "did/was"
    neg: bool = False    # True if this step is negative
    fml: bool = False    # True if this step is formal/polite


