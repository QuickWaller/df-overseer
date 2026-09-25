# Handoff: df-overseer-breach.lua header and ROADMAP line correction

Date: 2026-09-25. **Executor, Sonnet, worktree-isolated. Docs/comments only.**

`Working.md` "Still open" lists "`df-overseer-breach.lua` header and ROADMAP
line correction". Find what is wrong: read the header comment of
`scripts/dfhack/df-overseer-breach.lua`, compare it against the script's actual
behaviour and its register/decision entries (grep `decisions/DECISIONS.md` and
`Working.md`/`working-archive/` for "breach"), and find the ROADMAP.md line that
mentions it. Correct the header comment and the ROADMAP line so they match the
code and decisions. If the intended correction is genuinely ambiguous, stop
and report the two readings instead of choosing.

## Rules
- Do not change any Lua logic, only the header comment. Run the Lua-logic
  tests if any cover this file, before and after.
- Touched surfaces: `scripts/dfhack/df-overseer-breach.lua` (comment only) and
  the one line in `ROADMAP.md`.
- `git merge --ff-only main` first. Do NOT write `Working.md`, `decisions/`,
  `memory/` or `handoffs/INDEX.md`; you own only this doc's Result section.
- No em dashes in prose. **No attribution lines in commit messages.**
- Commit; do not push. Stop and report on any refusal.

## Result

(pending)
