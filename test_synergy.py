#!/usr/bin/env python
"""Test the synergy scoring system."""

# First, mock the segment objects we need
class MockWord:
    def __init__(self, text, seq=None, common=None):
        self.text = text
        self.seq = seq
        self.common = common
    
    def get_text(self):
        return self.text


class MockSegment:
    def __init__(self, text, seq=None, common=None):
        self.word = MockWord(text, seq, common)
        self.text = text


# Import synergy module
from himotoki.synergies import calculate_synergy, calculate_penalty, score_segment_pair

print("=" * 50)
print("Testing Synergy Scoring")
print("=" * 50)

# Test noun + particle synergy
# Using actual seq numbers from the database
noun = MockSegment("本", seq=1585240)  # 本 (book) - this is a guess, may not be exact
particle_ga = MockSegment("が", seq=2028930)  # が

# We can't test with real seqs without database, so let's just test the structure
print("\nTesting synergy calculation structure...")

synergy = calculate_synergy(noun, particle_ga)
if synergy:
    print(f"Synergy found: +{synergy.score} ({synergy.name})")
else:
    print("No synergy (may need database for POS lookup)")

# Test penalty for consecutive short kana
print("\n" + "=" * 50)
print("Testing Penalty Scoring")
print("=" * 50)

short1 = MockSegment("あ", common=None)
short2 = MockSegment("い", common=None)

penalty = calculate_penalty(short1, short2)
if penalty:
    print(f"Penalty found: {penalty.score} ({penalty.name})")
else:
    print("No penalty found")

# Test combined scoring
print("\n" + "=" * 50)
print("Testing Combined Scoring")
print("=" * 50)

score = score_segment_pair(short1, short2)
print(f"Combined score for 'あ' + 'い': {score}")

normal1 = MockSegment("食べる", common=1)
normal2 = MockSegment("こと", common=1)

score2 = score_segment_pair(normal1, normal2)
print(f"Combined score for '食べる' + 'こと': {score2}")

print("\n" + "=" * 50)
print("All synergy tests completed!")
print("=" * 50)
