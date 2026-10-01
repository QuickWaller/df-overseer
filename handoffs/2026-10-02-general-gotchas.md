# Handoff: general gotchas and vents (no tool named)

Date: 2026-10-02. **Executor, Sonnet, worktree. Offline only: build and test,
deploy nothing.**

## Why

Register 2026-10-02, "General gotchas and vents": an agent may write a
gotcha, vent or unexplained error about how the work goes (process, timing,
other agents, its own wake-ups) without naming a tool. Game knowledge is not
one of these: it belongs in doctrine, through the Consultant.

## Tasks, in order (commit after each)

1. `dfmcp/gotchas_store.py`: an entry may have no tool. Represent it as
   `tool = NULL` (the site stream reads general entries as `tool: null`;
   keep that shape). Migrate the existing SQLite table safely (SQLite cannot
   drop NOT NULL in place: rebuild the table in a transaction, preserving
   every row, id and outcome), idempotent on restart, tested on a copy of a
   populated store. `kind` stays meaningless without a tool: refuse a kind
   with no tool.
2. `dfmcp/gotchas_tools.py`: `gotchas.write` accepts an omitted tool
   (general); `gotchas.get` can ask for general entries (and still returns
   a tool's own entries exactly as today). Tool descriptions say plainly
   what a general entry is for, and that game knowledge goes to the
   Consultant/doctrine instead. Per-role tool counts must not change.
3. `agents/CONFIDENCE-LEGEND.md` (or wherever the shared gotcha guidance
   lives): one or two lines on general entries and the doctrine line.
4. Tests: write and read a general entry, outcomes on it, refusal of a
   kind without a tool, the migration preserving rows, unchanged behaviour
   for tool entries, tool counts unchanged.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- **Touched surfaces:** `dfmcp/gotchas_store.py`, `dfmcp/gotchas_tools.py`,
  `agents/CONFIDENCE-LEGEND.md`, their tests. Not `web/stream/*`,
  `dfqueue/*`, the publisher or export scripts (a sibling stream owns those).
- Public repo: no hostnames, IPs or tokens. No em dashes in prose. No
  attribution lines in commits.

## Done when

`dfmcp/tests` in `.venv-dfmcp` green (report the count), the migration tested
on a populated copy, and a Result section appended here, including the exact
steps the orchestrator runs to migrate the live store on VM 103 at deploy.
