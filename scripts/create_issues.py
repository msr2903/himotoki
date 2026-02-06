#!/usr/bin/env python3
"""Create beads issues for all uncovered failing LLM eval entries."""
import json
import subprocess
import sys

RESULTS_FILE = "output/llm_results.json"

# Entries that already have per-entry issues (from open beads)
ALREADY_COVERED = {1, 61, 65, 95, 100, 178, 239, 254, 261, 290, 380, 397, 403, 417, 460, 466, 477, 495, 503}

# Systemic issue IDs for linking
SYSTEMIC = {
    "pos": "himotoki-4ps",
    "source_text": "himotoki-dxj",
    "over_group": "himotoki-mla",
    "reading": "himotoki-tta",
    "conj_type": "himotoki-bg3",
    "n_interjection": "himotoki-0fjp",
    "de_copula": "himotoki-lxbp",
    "yo_adj": "himotoki-3hdy",
}


def classify_issues(issues: list[str]) -> list[str]:
    """Classify issues into systemic categories."""
    cats = set()
    for iss in issues:
        il = iss.lower()
        if any(k in il for k in ["pos", "empty"]):
            cats.add("pos")
        if any(k in il for k in ["source_text", "dictionary form", "lemma"]):
            cats.add("source_text")
        if any(k in il for k in ["single token", "over", "coarse", "unsegment", "not split", "not.*split"]):
            cats.add("over_group")
        if any(k in il for k in ["reading", "kana", "ないず"]):
            cats.add("reading")
        if any(k in il for k in ["conj_type", "conjugation type", "conjugation.*null"]):
            cats.add("conj_type")
    return sorted(cats)


def make_title(idx: int, issues: list[str], sentence: str) -> str:
    """Create a short title from the first issue."""
    first = issues[0] if issues else "unknown issue"
    # Truncate to ~60 chars
    if len(first) > 60:
        first = first[:57] + "..."
    return f"LLM eval #{idx}: {first}"


def make_description(idx: int, score: float, sentence: str, issues: list[str], categories: list[str]) -> str:
    """Create issue description."""
    issue_list = "\n".join(f"- {iss[:120]}" for iss in issues[:5])
    cat_list = ", ".join(categories) if categories else "unique"
    return (
        f"Entry #{idx} (score {score})\n"
        f"Sentence: {sentence[:60]}\n"
        f"Categories: {cat_list}\n"
        f"Issues:\n{issue_list}"
    )


def create_issue(idx, score, sentence, issues):
    """Create a single beads issue."""
    categories = classify_issues(issues)

    # Determine priority based on score
    if score >= 60:
        priority = "P2"
    else:
        priority = "P3"

    title = make_title(idx, issues, sentence)
    desc = make_description(idx, score, sentence, issues, categories)

    # Build deps from systemic categories
    deps = []
    for cat in categories:
        if cat in SYSTEMIC:
            deps.append(f"discovered-from:{SYSTEMIC[cat]}")

    cmd = [
        "bd", "create", title,
        "--labels", "llm-fail",
        "--priority", priority,
        "--description", desc,
    ]
    if deps:
        cmd.extend(["--deps", deps[0]])  # Only first dep to keep it simple

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        # Extract issue ID from output
        for line in result.stdout.splitlines():
            if "Created issue:" in line:
                issue_id = line.split("Created issue:")[-1].strip()
                return issue_id
    else:
        print(f"  ERROR: {result.stderr.strip()}", file=sys.stderr)
    return None


def main():
    with open(RESULTS_FILE) as f:
        results = json.load(f)

    # Get all failing entries
    failing = []
    for i, entry in enumerate(results):
        if entry.get("llm_score", {}).get("verdict") != "pass":
            idx = i + 1
            if idx not in ALREADY_COVERED:
                issues_raw = entry.get("llm_score", {}).get("issues", [])
                issues = []
                for iss in issues_raw:
                    if isinstance(iss, dict):
                        issues.append(iss.get("issue", str(iss)))
                    else:
                        issues.append(str(iss))
                failing.append({
                    "idx": idx,
                    "score": entry["llm_score"].get("overall_score", 0),
                    "sentence": entry["sentence"],
                    "issues": issues,
                })

    print(f"Creating issues for {len(failing)} uncovered entries...")

    created = 0
    errors = 0
    for entry in failing:
        issue_id = create_issue(
            entry["idx"], entry["score"],
            entry["sentence"], entry["issues"]
        )
        if issue_id:
            created += 1
            print(f"  [{created}/{len(failing)}] #{entry['idx']} → {issue_id}")
        else:
            errors += 1
            print(f"  [{created}/{len(failing)}] #{entry['idx']} FAILED")

    print(f"\nDone: {created} created, {errors} errors, {len(failing)} total")


if __name__ == "__main__":
    main()
