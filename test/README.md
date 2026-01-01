# Himotoki Evaluation Framework

This directory contains tools for evaluating Himotoki's Japanese text segmentation accuracy by comparing it against Ichiran.

## Structure

- `sentences.json`: A collection of test sentences categorized by linguistic features.
- `evaluator.py`: The main evaluation script.
- `report.md`: The generated evaluation report (created after running the script).

## Usage

### Connectivity Check
Verify that the Ichiran Docker container is running and Himotoki is accessible:
```bash
python3 test/evaluator.py --check
```

### Run Full Benchmark
Execute the full evaluation suite and generate a report:
```bash
python3 test/evaluator.py
```

### Test Single Sentence
```bash
python3 test/evaluator.py --sentence "猫が食べる"
```

## Metrics
The evaluator measures **Exact Match Similarity**. A sentence is considered a match only if Himotoki's list of tokens is identical to Ichiran's.
