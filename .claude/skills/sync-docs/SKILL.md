---
name: sync-docs
description: Update CLAUDE.md and README.md to reflect recent code changes using a token-minimal, diff-driven workflow. Use this whenever code changes have just been made or committed in this repo and the docs might be stale — after adding/renaming/removing files, changing CLI flags or exit codes, adding Test Intent actions or assertion types, changing env vars, endpoints, or dependencies. Trigger it when the user says "update the docs", "sync CLAUDE.md", "refresh the README", or simply finishes a feature/refactor, even if they don't explicitly mention documentation.
---

# Sync Docs (token-minimal)

Keep CLAUDE.md and README.md truthful after code changes without re-reading the repo.
The docs describe *interfaces and architecture*, not implementation details — so most
code changes need no doc edit at all, and the job is mostly deciding that cheaply.

## Workflow — cheapest signal first

1. **Find what changed.** Start with the smallest possible view:
   - Uncommitted work: `git diff --stat` (plus `git status --short` for new files)
   - Committed work: `git diff --stat <last-doc-sync-ref>..HEAD` or `git log --oneline -5` to pick the range
   Do NOT read any source file yet.

2. **Filter to doc-relevant changes.** Only these kinds of changes can make the docs stale:
   - Files added, renamed, or removed (the layout trees in both docs list files)
   - CLI interface: flags, arguments, exit-code behavior in `owntest/runner.py` `main()`
   - Test Intent schema: UI actions, API assertion types, top-level intent keys
     (documented in CLAUDE.md, README.md, the runner docstring, and the LLM system
     prompt in `owntest/llm/provider.py` — if the schema changed, check all four agree)
   - Env vars (`OWNTEST_*`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`)
   - HTTP endpoints or data-dir behavior in `app/server.py`
   - `requirements.txt` dependencies
   - Roadmap/limitations items that a change implements or removes
   If nothing in the diff touches these categories, say "docs already accurate" and stop.
   Internal refactors, comment changes, and bug fixes that don't move an interface do
   not belong in the docs.

3. **Read only the relevant hunks.** For each doc-relevant file, read the diff hunks
   (`git diff -- <file>`), not the whole file. Only open the file itself if the hunk
   lacks context you genuinely need (e.g., you must see the full argparse block).

4. **Locate the stale doc lines by grep, not by reading.** Grep CLAUDE.md and README.md
   for the changed identifiers (file name, flag, env var, action name, endpoint path).
   Read only the matched section with offset/limit if you need surrounding context.

5. **Edit surgically.** Fix only the stale lines with Edit. Never rewrite a whole doc
   file with Write — that burns tokens and risks clobbering unrelated sections.
   Match the existing tone and density; these docs are deliberately terse.

6. **Report.** One line per doc edit made (file + what changed), or "docs already
   accurate — no edits needed". If the Test Intent schema changed, explicitly confirm
   the four schema locations (CLAUDE.md, README.md, runner docstring, LLM system
   prompt) are now consistent.

## Token rules

The whole point of this skill is that doc syncing happens often, so each pass must be
cheap. In order of preference: `--stat` → targeted diff hunks → Grep → sectioned Read.
Never read a file the diff doesn't touch. Never fully re-read CLAUDE.md or README.md
when Grep can find the section. Batch independent tool calls in one message.

## Example

Change: `owntest/runner.py` gains a `--retries N` flag.
- `git diff --stat` → only runner.py changed → doc-relevant (CLI interface)
- `git diff -- owntest/runner.py` → see the new argparse line
- Grep `\-\-headed|api-base-url` in README.md/CLAUDE.md → find the command blocks
- Edit: add `--retries` to the runner command examples in both files
- Report: "Added --retries flag to runner command docs in README.md and CLAUDE.md."
