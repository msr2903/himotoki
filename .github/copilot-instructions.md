## Issue Tracking

This project uses **bd (beads)** for issue tracking.
Run `bd prime` for workflow context, or install hooks (`bd hooks install`) for auto-injection.

**Quick reference:**
- `bd ready` - Find unblocked work
- `bd create "Title" --type task --priority 2` - Create issue
- `bd close <id>` - Complete work
- `bd sync` - Sync with git (run at session end)

For full workflow details: `bd prime`

How it works:
   • bd prime provides dynamic workflow context (~80 lines)
   • bd hooks install auto-injects bd prime at session start
   • AGENTS.md only needs this minimal pointer, not full instructions

## Codebase Search

This project uses **chuckhound MCP** for efficient codebase searching.

**Quick reference:**
- Use chuckhound MCP to search for code patterns, symbols, and references across the codebase
- Simplifies finding relevant code sections when understanding context or making changes
- Enables faster navigation and discovery of implementation details

**How it works:**
   • Integrates with the workspace for semantic and text-based searches
   • Returns contextualized results with file paths and line numbers
   • Helps identify related code patterns and dependencies