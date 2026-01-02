import json
with open('comparison_results.json', 'r') as f:
    data = json.load(f)

# Find all mismatches
mismatch_idx = 0
for i, item in enumerate(data):
    if item.get('status') != 'match':
        mismatch_idx += 1
        print(f'Mismatch {mismatch_idx} (index {i}):')
        print(f'  Input: {item["sentence"]}')
        print(f'  Himotoki: {item["himotoki_texts"]}')
        print(f'  Ichiran: {item["ichiran_texts"]}')
        print(f'  Differences: {item.get("differences", "")}')
        print()
