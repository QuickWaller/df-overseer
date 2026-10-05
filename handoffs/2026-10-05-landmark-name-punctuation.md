# Handoff: workshops with an apostrophe in their name cannot be addressed

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no deploys.**

## Why

Live, 2026-10-05 08:30 to 08:40 UTC: the Quartermaster proposed direct barrel
jobs at the Carpenter's Workshop (only two empty barrels; brewing stalls
without more). The Overseer rejected both (ruling-0016, ruling-0017) because
no tool could address the workshop. The MCP server refuses the apostrophe as a
shell metacharacter (`dfmcp/tools.py` around line 873, `_SHELL_METACHAR_RE`),
and the model's fallback "Carpenters Workshop" was refused by the game script
as an unknown workshop. Every landmark whose name has an apostrophe (Carpenter's,
Stoneworker's, Mechanic's Workshop, and any future one) is unreachable by name
through every tool that takes a landmark name.

## What to build (generic, every tool, every name)

- Landmark name matching tolerant of punctuation, case and spacing: one shared
  normaliser used wherever a tool resolves a landmark name (find it: the
  landmark helper in `scripts/dfhack/`, and any Python-side resolution). An
  ambiguous normalised match is refused with the candidates listed, never
  guessed.
- Decide whether the apostrophe can be allowed through the server at all: RPC
  RunCommand passes arguments as a list, not a shell, so check what
  `_SHELL_METACHAR_RE` actually protects against and whether DFHack's own
  argument handling is affected by a quote. Keep the refusal if it is needed;
  the normaliser makes the apostrophe unnecessary either way.
- The refusal text for a forbidden character should say what to do (for
  example, "omit the apostrophe; names match ignoring punctuation").
- Optional, only if trivial and generic: a building-id argument where tools
  already resolve to a building.

## Tasks (commit after each)

1. Plan in the Result section: where names are resolved today, every tool
   affected.
2. Build, with tests (Lua-logic tests run with `lupa`, see CLAUDE.md).
3. Result: built, tests, deploy targets (expect vm103-dfhack-scripts and
   vm103-dfmcp), live check (`workjob.list-jobs` with "Carpenters Workshop"
   resolves).

## Rules

- First step: `git merge --ff-only main`. Commit plan early and after each
  milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`, `docs/CONDUCTOR-EXECUTION*.md`.
- Touched surfaces: `scripts/dfhack/` (the landmark resolution helper and
  callers only), `dfmcp/tools.py` (argument check and its message only), tests,
  this handoff. Not `dfmcp/queue_tools.py`, `dfqueue/`, `conductor/` (another
  stream is building there).
- No armok powers. Public repo: no hostnames, IPs or tokens. No em dashes. No
  attribution lines in commits. Do not touch the live fort.
- Full ambient `python -m pytest` (with `lupa`) and `dfmcp/tests` green.

## Result

(executor fills this in)
