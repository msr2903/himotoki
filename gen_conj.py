#!/usr/bin/env python
"""Generate conjugations and populate the conj_lookup table."""

import sys
from himotoki.dict_load import generate_conjugations

def progress(current, total):
    if total:
        pct = (current / total) * 100
        print(f"\rProgress: {current}/{total} entries ({pct:.1f}%)", end="", flush=True)
    else:
        print(f"\rProcessed: {current} entries...", end="", flush=True)

print("Generating conjugations from dictionary entries...")
print("This may take a few minutes for 200k+ entries...")
print()

try:
    count = generate_conjugations(progress_callback=progress)
    print()
    print(f"\nGenerated {count:,} conjugated forms!")
except Exception as e:
    print(f"\nError: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
