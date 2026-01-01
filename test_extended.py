#!/usr/bin/env python3
"""Extended test suite for himotoki synergies and segmentation."""

from himotoki.dict import dict_segment

# Extended test suite - 50 cases
test_cases = [
    # === ORIGINAL PROBLEM CASES ===
    ('静かです', ['静か', 'です']),
    ('天気がいい', ['天気', 'が', 'いい']),
    
    # === COPULA PATTERNS ===
    ('学生です', ['学生', 'です']),
    ('先生です', ['先生', 'です']),
    ('本だ', ['本', 'だ']),
    ('先生だ', ['先生', 'だ']),
    ('元気です', ['元気', 'です']),
    
    # === NOUN + PARTICLE ===
    ('猫が', ['猫', 'が']),
    ('犬を', ['犬', 'を']),
    ('山に', ['山', 'に']),
    ('川で', ['川', 'で']),
    ('友達と', ['友達', 'と']),
    ('家から', ['家', 'から']),
    ('駅まで', ['駅', 'まで']),
    
    # === NOUN + PARTICLE + VERB ===
    ('本を読む', ['本', 'を', '読む']),
    ('水を飲む', ['水', 'を', '飲む']),
    ('日本語を勉強する', ['日本語', 'を', '勉強する']),  # Suru compound
    ('東京に行く', ['東京', 'に', '行く']),
    
    # === PARTICLE + ADJECTIVE ===
    ('本が面白い', ['本', 'が', '面白い']),
    ('空が青い', ['空', 'が', '青い']),
    ('山が高い', ['山', 'が', '高い']),
    ('花が綺麗', ['花', 'が', '綺麗']),
    
    # === TE-FORM PATTERNS ===
    # These are compound forms in Ichiran
    ('食べている', ['食べている']),
    ('食べています', ['食べています']),
    ('見ている', ['見ている']),
    ('読んでいる', ['読んでいる']),
    ('勉強しています', ['勉強しています']),  # Suru + teiru compound
    
    # === NA-ADJECTIVE PATTERNS ===
    ('静かな', ['静か', 'な']),
    ('静かに', ['静か', 'に']),
    ('きれいな', ['きれい', 'な']),
    
    # === BASIC WORDS ===
    ('いい', ['いい']),
    ('大きい', ['大きい']),
    ('小さい', ['小さい']),
    ('新しい', ['新しい']),
    ('古い', ['古い']),
    ('食べる', ['食べる']),
    ('飲む', ['飲む']),
    ('行く', ['行く']),
    ('来る', ['来る']),
    ('する', ['する']),
    
    # === VERB CONJUGATIONS ===
    ('食べます', ['食べます']),
    ('食べた', ['食べた']),
    ('食べない', ['食べない']),
    ('食べて', ['食べて']),
    
    # === I-ADJECTIVE CONJUGATIONS ===
    ('大きかった', ['大きかった']),
    ('小さくない', ['小さくない']),
    
    # === COMMON EXPRESSIONS ===
    ('ありがとう', ['ありがとう']),
    ('すみません', ['すみません']),
    ('おはよう', ['おはよう']),
]

def run_tests():
    passed = 0
    failed = 0
    failures = []

    for text, expected in test_cases:
        try:
            result = dict_segment(text, limit=1)
            if result:
                words, score = result[0]
                actual = [w.text for w in words]
                if actual == expected:
                    passed += 1
                else:
                    failed += 1
                    failures.append((text, expected, actual))
            else:
                failed += 1
                failures.append((text, expected, ['No result']))
        except Exception as e:
            failed += 1
            failures.append((text, expected, [str(e)]))

    print(f'=== Results: {passed}/{passed+failed} tests passed ===')
    print()
    if failures:
        print('Failed tests:')
        for text, expected, actual in failures[:15]:
            print(f'  {text}: expected {expected}, got {actual}')
    else:
        print('All tests passed!')

if __name__ == '__main__':
    run_tests()
