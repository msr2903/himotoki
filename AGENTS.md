# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

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

Finds bugs and creates detailed beads issues for later fixing.

1. **Check status**: `python scripts/llm_eval.py --triage-status`
2. **Find failed entries**: `jq '.[] | select(.pass==false) | {i:.index,s:.sentence}' output/llm_results.json`
3. **Batch research** (optional): Spawn research subagents for multiple entries in parallel
4. **Inspect entry**: `python scripts/check_segments.py <num>` or use subagent report
5. **Reserve entry** (optional): `python scripts/llm_eval.py --reserve <num> --agent-id "triage-1"`
6. **Ask the User**: Use `ask_questions` tool to confirm fix vs skip (waits for user input)
7. **Create issue or skip**:
   - **Skip**: `python scripts/llm_eval.py --skip <num> --reason "explanation"`
   - **Create beads issue**: Use `bd create` (see template below)

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

Picks up issues from beads and implements fixes.

1. **Find available work**: `bd ready` or filter by label `llm-fail`
2. **Claim the issue**: `bd update <id> --status in_progress`
3. **Understand the problem**: Read the issue description, code locations provided
4. **Implement the fix**: Make code changes at the identified locations
5. **Verify locally**:
   ```bash
   python scripts/check_segments.py <num>  # Check segmentation changes
   python scripts/llm_eval.py --rescore <num>  # Verify fix passes
   ```
   Or spawn Test Runner subagent for full validation
6. **Commit and push**: Follow "Landing the Plane" workflow above

#### Running Both Agents Simultaneously

The agents are fully independent:
- **Agent A (Triage)**: Analyzes failed entries, creates beads issues
- **Agent B (Fix)**: Implements fixes, commits, and pushes

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
