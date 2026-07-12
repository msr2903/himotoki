"""
Regression lock: segmentation texts and path scores for a fixed sentence set.

Snapshot covers ~40 sentences (compounds, counters, conjugations, particles).
Regenerate with a warm DB when intentional scoring changes land:

  HIMOTOKI_DB_PATH=data/himotoki.db python -c "..."  # see scripts or prior commits

If these fail, scoring or candidate generation changed unexpectedly.
"""

import json
from pathlib import Path

import pytest

SNAPSHOT_PATH = Path(__file__).parent / "data" / "score_equivalence_snapshot.json"


@pytest.fixture(scope="module")
def snapshot():
    assert SNAPSHOT_PATH.exists(), f"Missing snapshot: {SNAPSHOT_PATH}"
    data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert len(data) >= 40, f"Expected >=40 snapshot sentences, got {len(data)}"
    return data


def test_score_equivalence_snapshot(db_session, snapshot):
    """Re-analyze snapshot sentences; require identical segments and scores."""
    import himotoki
    from himotoki.suffixes import init_suffixes
    from himotoki.counters import init_counter_cache
    from himotoki.trie import init_word_trie
    from himotoki.lookup import build_archaic_cache

    build_archaic_cache(db_session)
    init_suffixes(db_session)
    init_counter_cache(db_session)
    init_word_trie(db_session)

    for entry in snapshot:
        sentence = entry["sentence"]
        paths = himotoki.analyze(sentence, session=db_session)
        assert paths, f"No paths for {sentence!r}"
        words, score = paths[0]
        segs = [
            (
                w.text,
                w.kana if isinstance(w.kana, str) else "/".join(w.kana) if w.kana else "",
                w.score,
            )
            for w in words
        ]
        assert score == entry["score"], (
            f"Path score mismatch for {sentence!r}: got {score}, expected {entry['score']}"
        )
        assert segs == [tuple(s) for s in entry["segs"]], (
            f"Segment mismatch for {sentence!r}:\n  got {segs}\n  expected {entry['segs']}"
        )
