# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

## Project Overview

**Himotoki** is a Japanese text segmentation library that breaks sentences into words with readings.

**Key directories:**
- `himotoki/` - Core library (segment.py, splits.py, lookup.py, suffixes.py, conjugation_hints.py)
- `scripts/` - Evaluation tools (llm_eval.py, check_segments.py, llm_report.py)
- `tests/` - Test suite
- `data/` - Dictionary data, skip lists, lock files
- `output/` - Evaluation results (llm_results.json, llm_report.html)

**Current task:** Improve segmentation accuracy by fixing failures in LLM evaluation.

## Agent Onboarding

When starting a new session, run these commands:

```bash
bd onboard                                    # Learn beads issue tracking
python scripts/llm_eval.py --triage-status    # See failed entries & progress
bd ready                                      # Find available work
git log --oneline -5                          # Recent changes context
```

**First-time setup:**
```bash
source .venv/bin/activate                     # Activate Python environment
pip install -e .                              # Install himotoki in dev mode
pytest tests/ -x --tb=short                   # Verify tests pass
```

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

## Codebase Search

Use **chunkhound MCP** for semantic and regex codebase searches. Returns contextualized results with file paths and line numbers.

## Maximizing Agent Autonomy

Agents should work efficiently but **always confirm bug decisions with the user**. Follow these principles:

### Autonomous Decision Framework

**DECIDE YOURSELF** (don't ask):
- Implementation approach when issue description is clear
- Commit message wording
- Which files to change based on root cause analysis
- Test verification strategy

**ALWAYS ASK USER** (use `ask_questions` tool):
- Whether to fix or skip ANY bug - always get confirmation
- Before creating any beads issue
- Before skipping any entry

### Skip/Fix Pattern Reference

Use these patterns to **suggest** actions to the user, but always confirm:

**Common Skip Patterns** (suggest skip, confirm with user):

| Pattern | Suggested Reason |
|---------|------------------|
| Proper noun reading | `Proper noun - multiple valid readings` |
| Counter ambiguity | `Counter expression - valid alternative` |
| Stylistic particle | `Stylistic choice - both valid` |
| Archaic reading | `Archaic reading - dictionary limitation` |
| Compound boundary | `Compound boundary - subjective split` |

**Common Fix Patterns** (suggest fix approach, confirm with user):

| Pattern | Suggested Action |
|---------|------------------|
| Missing suffix | Add suffix to `himotoki/suffixes.py` |
| Wrong POS tag | Update POS mapping in `himotoki/lookup.py` |
| Missing dictionary entry | Add to custom dictionary |
| Conjugation error | Fix in `himotoki/conjugation_hints.py` |

### Error Recovery

**Git conflicts:**
```bash
git stash && git pull --rebase && git stash pop
# If conflict persists, resolve manually then continue
```

**Test failures after fix:**
1. Check if failure is related to your change
2. If unrelated, note it and continue
3. If related, revert and try different approach

**Push rejected:**
```bash
git pull --rebase && git push  # Retry
# If still fails, check for large files (>100MB)
```

**Chunkhound lock error:**
```bash
kill $(lsof -t .chunkhound/db.wal) 2>/dev/null
rm -f .chunkhound/db.wal
```

### Batch Processing

Process in batches to maximize throughput:

**Triage Agent:**
- Analyze 5-10 entries before asking user for batch confirmation
- Group similar failures together
- Present: "Found 3 suffix issues, 2 reading issues. Auto-fix suffixes, ask about readings?"

**Fix Agent:**
- Implement up to 3 related fixes before committing
- Run tests once after batch, not after each fix
- Single commit for related fixes with detailed message

### Progress Checkpoints

Save state frequently to avoid losing work:

```bash
# After every 3-5 items processed
git add -A && git stash  # Checkpoint work

# Before long operations
bd sync  # Ensure beads state is saved

# After major progress
git commit -m "WIP: <what's done so far>" --no-verify
```

### Escalation Thresholds

Only escalate after exhausting these options:

1. **Search first**: Use chunkhound to find similar patterns in codebase
2. **Check history**: `git log --oneline -20` for recent related changes
3. **Try both approaches**: If unsure, implement simpler one first
4. **Timebox**: Spend max 5 minutes researching before deciding

**Escalate when:**
- Two valid approaches with different tradeoffs
- Change requires domain knowledge you lack
- Risk of breaking unrelated functionality

## LLM Accuracy Evaluation

This project includes an LLM-based evaluation system to verify Himotoki's segmentation accuracy.

### Quick Reference

```bash
# Run full evaluation (510 sentences)
python scripts/llm_eval.py

# Run quick subset (50 sentences)
python scripts/llm_eval.py --quick

# Test a single sentence
python scripts/llm_eval.py --onesentence "猫が食べる"

# Mock mode (no API calls)
python scripts/llm_eval.py --quick --mock

# Retry entries that had LLM errors
python scripts/llm_eval.py --retry-failed

# Rescore a specific entry after fixing a bug
python scripts/llm_eval.py --rescore 5
python scripts/llm_eval.py --rescore "5,12,47"  # Batch rescore

# Check segmentation changes (no LLM, fast)
python scripts/check_segments.py             # Check all, show only changes
python scripts/check_segments.py 5           # Check entry #5
python scripts/check_segments.py 1-10        # Check range
python scripts/check_segments.py --show-all  # Show all entries

# Generate HTML report
python scripts/llm_report.py
```

### Skip List Management

Skip entries that can't be fixed (known issues, edge cases):

```bash
# Skip an entry with reason
python scripts/llm_eval.py --skip 42 --reason "Known particle ambiguity"

# Remove from skip list
python scripts/llm_eval.py --unskip 42

# List all skipped entries
python scripts/llm_eval.py --list-skipped
```

Skipped entries are stored in `data/llm_skip.json` and excluded from pass/fail counts.

### Baseline Comparison

Track progress by comparing against a saved baseline:

```bash
# Save current results as baseline
python scripts/llm_eval.py --save-baseline

# Compare current run against baseline
python scripts/llm_eval.py --compare-baseline
```

Shows improved, regressed, and unchanged entries with score deltas.

### Export to Beads

Create beads issues from failed entries:

```bash
# Preview what issues would be created
python scripts/llm_eval.py --export-issues --dry-run

# Create issues with custom label
python scripts/llm_eval.py --export-issues --issue-label "llm-fail"
```

### Run History

View evaluation history over time:

```bash
# Show recent runs
python scripts/llm_eval.py --show-history

# Don't log this run to history
python scripts/llm_eval.py --quick --no-history
```

History is stored in `output/llm_history.jsonl`.

### Workflow for Fixing Bugs

The bug-fixing process is split into **two independent agents** that can run simultaneously:

#### Multi-Agent Coordination

```bash
# Check triage pipeline status
python scripts/llm_eval.py --triage-status

# Reserve an entry for triage (prevents duplicate work)
python scripts/llm_eval.py --reserve 42 --agent-id "triage-1"

# Release a reservation
python scripts/llm_eval.py --release 42

# Export issues (auto-deduplicates, tracks in lock file)
python scripts/llm_eval.py --export-issues
python scripts/llm_eval.py --export-issues --no-dedup  # Skip deduplication
```

Lock file: `data/llm_triage_lock.json` - tracks reserved and issued entries.

#### Subagents for Acceleration

Use `runSubagent` to spawn autonomous research tasks. Subagents run to completion and return a report.

**Research Subagent** - Pre-analyze failed entries before triage:
```
runSubagent(
  description: "Analyze entry 42",
  prompt: "Research LLM eval entry #42:
    1. Read entry from output/llm_results.json
    2. Search codebase with chunkhound for relevant code
    3. Identify root cause
    Return: failure type, affected files with line numbers, 
    recommended action (fix/skip), suggested issue description"
)
```

**Test Runner Subagent** - Validate fixes don't break other things:
```
runSubagent(
  description: "Run test suite",
  prompt: "Run pytest and report results:
    1. Run: pytest tests/ -v
    2. If failures, read failing test files and identify cause
    3. Return: pass/fail count, failure details with file:line"
)
```

**Impact Analysis Subagent** - Find all code affected by a change:
```
runSubagent(
  description: "Impact analysis for splits.py",
  prompt: "Find all code that depends on himotoki/splits.py:
    1. Search for imports of splits
    2. Find functions that call split-related code
    3. Return: dependency graph, test files that cover this code"
)
```

**Code Review Subagent** - Review changes before commit:
```
runSubagent(
  description: "Review staged changes",
  prompt: "Review git staged changes:
    1. Run: git diff --cached
    2. Check for: style issues, missing tests, potential bugs
    3. Return: approval or list of concerns with file:line"
)
```

#### Agent 1: Bug Search Agent (Triage)

Finds bugs and creates detailed beads issues for later fixing. **Always confirm with user before any action.**

1. **Check status**: `python scripts/llm_eval.py --triage-status`
2. **Show failed entries to user**: `jq '[to_entries[] | select(.value.llm_score.verdict != "pass") | {idx: .key, sentence: .value.sentence, score: .value.llm_score.overall_score, issues: .value.llm_score.issues}] | .[0:20]' output/llm_results.json`
3. **Ask user which entries to analyze**: Use `ask_questions` - "Found X failed entries. Which should I analyze?"
4. **For each approved entry**:
   a. Analyze: Use chunkhound to find relevant code, identify root cause
   b. Present findings to user with `ask_questions`:
      - Create beads issue (suggest fix approach)
      - Skip with reason (suggest reason from patterns)
      - Investigate more
   c. Wait for user confirmation
   d. Execute user's decision: Skip or create issue as directed
5. **Repeat** for next entry user wants to analyze

**Issue Template for Beads:**
```bash
bd create "LLM eval #<num>: <short description>" \
  --description "## Problem
<What is wrong with the segmentation/reading/etc>

## Sentence
\`<original sentence>\`

## Current Output
<paste segments from report>

## Expected Output
<what it should be>

## Root Cause Analysis
<why this is happening - use chunkhound to find relevant code>

## Code Locations
- <file>:<line> - <description of what needs to change>

## How to Verify
\`\`\`bash
python scripts/check_segments.py <num>
python scripts/llm_eval.py --rescore <num>
\`\`\`
" --labels llm-fail
```

#### Agent 2: Bug Fix Agent (Implementation)

Picks up issues from beads and implements fixes. **Work continuously** until queue is empty or session ending.

1. **Batch claim**: `bd ready` - claim 3-5 related issues at once
2. **Group by file**: Sort issues by affected code location
3. **Implement fixes** in batches (same-file changes together)
4. **Run tests once** after batch: `pytest tests/ -x --tb=short`
5. **Verify fixes**: `python scripts/llm_eval.py --rescore "<n1>,<n2>,<n3>"`
6. **Commit batch** with detailed message listing all fixes
7. **Push** and pick up next batch
8. **On failure**: Revert problematic fix, continue with others

**Continuous Loop:**
```
while issues_available and not session_ending:
    batch = claim_next_3_issues()
    for issue in batch:
        implement_fix(issue)
    run_tests()
    if tests_pass:
        commit_and_push(batch)
    else:
        identify_failing_fix()
        revert_that_fix()
        commit_and_push(working_fixes)
```

#### Running Both Agents Simultaneously

The agents are fully independent:
- **Agent A (Triage)**: Analyzes entries, auto-classifies, batches user questions
- **Agent B (Fix)**: Implements fixes in batches, continuous push loop

Coordination happens through:
- **beads issues**: Work queue between triage and fix agents
- **triage lock file**: Prevents duplicate triage work


### Output Files

- `output/llm_results.json` - Raw evaluation results
- `output/llm_baseline.json` - Saved baseline for comparison
- `output/llm_history.jsonl` - Run history log
- `output/llm_report.html` - HTML report (for humans)
- `data/llm_skip.json` - Skip list with reasons
- `data/llm_triage_lock.json` - Multi-agent triage coordination (reserved/issued entries)
