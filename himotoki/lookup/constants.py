"""
Lookup constants (non-scoring).
"""

from typing import Dict, Set

# Parts of speech that can be conjugated
POS_WITH_CONJ_RULES = frozenset([
    'v1', 'v1s', 'v5aru', 'v5b', 'v5g', 'v5k', 'v5k-s', 'v5m', 'v5n',
    'v5r', 'v5r-i', 'v5s', 'v5t', 'v5u', 'v5u-s', 'v5uru', 'vk', 'vs',
    'vs-i', 'vs-s', 'vz', 'adj-i', 'adj-ix', 'adj-na', 'adj-no',
])

# Expression entries that are valid dictionary items but too coarse for our
# segmentation goals. We prefer compositional analysis for these.
SUPPRESS_SINGLE_TOKEN_SEQS: Set[int] = {
    2825978,  # でしょうか -> prefer でしょう + か
}

# Import conjugation constants from central location
from himotoki.constants import (
    CONJ_ADVERBIAL, CONJ_ADJECTIVE_STEM, CONJ_NEGATIVE_STEM,
    CONJ_CAUSATIVE_SU, CONJ_ADJECTIVE_LITERARY,
    CONJ_TYPE_NAMES, WEAK_CONJ_FORMS, SKIP_CONJ_FORMS,
    CONJ_VOLITIONAL, CONJ_TE, CONJ_POTENTIAL, CONJ_IMPERATIVE,
)

