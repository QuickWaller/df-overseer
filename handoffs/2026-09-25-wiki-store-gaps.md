# Handoff: fix the four gaps S6 found in wikimirror/store.py

Date: 2026-09-25. **Executor, Sonnet, worktree-isolated. Code and tests only, no VM, no deploy.**

Find the four gaps: read `handoffs/2026-09-25-wiki-*.md` (the S6 result and any
follow-up notes) and `Working.md` ("Current state"). If you cannot identify
exactly four concrete gaps in `store.py` from those sources, stop and report
what you found rather than guessing.

## Task
Fix each gap in `wikimirror/store.py` with a test that fails before and passes
after. Keep changes minimal; no refactors, no new features. Do not touch the
reader (`wiki_reader.py`) unless a gap requires it, and say so if it does.

## Verify
`python -m pytest wikimirror` (and any test dir that covers store). `lupa` is
not needed. Report pass counts before and after.

## Rules
- `git merge --ff-only main` first; this brief is committed on main.
- Touched surfaces: `wikimirror/store.py` and its tests only.
- Do NOT write `Working.md`, `decisions/`, `memory/` or `handoffs/INDEX.md`;
  you own only this doc's Result section.
- No em dashes in prose. **No attribution lines in commit messages.**
- Commit after each gap fixed. Do not push. Stop and report on any refusal.

## Result

(pending)
