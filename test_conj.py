#!/usr/bin/env python
"""Test the conjugation system."""

from himotoki.conjugations import get_conjugation_rules, ConjType, conjugate_word

# Test ichidan verb rules
print("=" * 50)
print("Testing Ichidan Verb Conjugation Rules")
print("=" * 50)

rules = get_conjugation_rules('v1')
print(f"Ichidan verb rules: {len(rules)}")
print("\nSample rules:")
for r in rules[:8]:
    neg = "neg" if r.neg else ("aff" if r.neg == False else "-")
    fml = "fml" if r.fml else ("pln" if r.fml == False else "-")
    print(f"  Type {r.conj_type:2d}: {neg}/{fml} -> remove {r.stem_chars} char(s) + '{r.okurigana}'")

# Test conjugating a word
print("\n" + "=" * 50)
print("Conjugating 食べる (taberu - to eat)")
print("=" * 50)

conjugations = conjugate_word('たべる', 'v1')
for form, rule in conjugations[:10]:
    neg = "negative" if rule.neg else ("affirmative" if rule.neg == False else "")
    fml = "formal" if rule.fml else ("plain" if rule.fml == False else "")
    print(f"  {form:12s} - Type {rule.conj_type} ({neg} {fml})")

# Test godan verb rules
print("\n" + "=" * 50)
print("Testing Godan Verb (v5k - く ending)")
print("=" * 50)

rules_v5k = get_conjugation_rules('v5k')
print(f"Godan-k verb rules: {len(rules_v5k)}")

print("\nConjugating 書く (kaku - to write):")
conjugations = conjugate_word('かく', 'v5k')
for form, rule in conjugations[:10]:
    neg = "neg" if rule.neg else ("aff" if rule.neg == False else "")
    print(f"  {form:12s} - Type {rule.conj_type} {neg}")

# Test i-adjective
print("\n" + "=" * 50)
print("Testing I-Adjective Conjugation")
print("=" * 50)

rules_adj = get_conjugation_rules('adj-i')
print(f"I-adjective rules: {len(rules_adj)}")

print("\nConjugating 高い (takai - high/expensive):")
conjugations = conjugate_word('たかい', 'adj-i')
for form, rule in conjugations[:10]:
    neg = "neg" if rule.neg else ("aff" if rule.neg == False else "")
    print(f"  {form:12s} - Type {rule.conj_type} {neg}")

print("\n" + "=" * 50)
print("All tests completed!")
print("=" * 50)
