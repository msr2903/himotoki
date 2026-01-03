"""
Loading package for himotoki.
Contains JMDict XML parser and conjugation rule loaders.
"""

from himotoki.loading.jmdict import load_jmdict, load_entry
from himotoki.loading.conjugations import (
    load_pos_index,
    load_conj_descriptions,
    load_conj_rules,
    ConjugationRule,
)

__all__ = [
    "load_jmdict",
    "load_entry",
    "load_pos_index",
    "load_conj_descriptions",
    "load_conj_rules",
    "ConjugationRule",
]