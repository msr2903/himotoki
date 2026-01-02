#!/usr/bin/env python3
import json

with open('comparison_results.json') as f:
    data = json.load(f)

for item in data:
    sentence = item.get('sentence', '')
    if 'ことに' in sentence or 'こと' in sentence:
        print('Sentence:', sentence)
        print('  Ichiran:', item['ichiran_texts'])
        print('  Himotoki:', item['himotoki_texts'])
        print('  Status:', item['status'])
        print()
