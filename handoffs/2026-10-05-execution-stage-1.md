# Handoff: conductor-executes stage 1, cited facts and the ruling briefing

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no deploys.** User's go-ahead: register 2026-10-05, "Conductor-executes
revision 3 accepted; stage 0 deployed".

## Why

`docs/CONDUCTOR-EXECUTION.md` revision 3, stage table row 1: proposals cite the
facts they rest on and the server reads them itself; the Overseer gets a
fixed-order briefing (stable first, ask last) built for short, cache-friendly
ruling turns; threshold alerts replace fixed stock lists. This replaces
`handoffs/2026-10-05-cited-facts-briefing.md` (paused, superseded by the
design). Stage 1 must be safe alone: no write path, timeout, routing or defer
behaviour changes (design section 8.2; the defer change is stage 4).

## Read first

The design sections 0, 2.1 to 2.3 (only what stage 1 needs: `relies_on` and
its server reads, not `step`), 3.1 to 3.3, 8.2, and 9 to 10;
`docs/CONDUCTOR-EXECUTION-REDTEAM.md` for anything touching stage 1; the
register's 2026-10-05 rows (agents trust each other's facts; no fixed stock
lists); `research/2026-10-05-procedure-briefing-and-bounded-turns.md` R2;
`dfqueue/schema.py`, `dfqueue/store.py`, `dfmcp/queue_tools.py`
(`queue.propose`, `queue.pending`, `queue.overview`), `dfmcp/roles.py`,
`conductor/briefing.py`, `conductor/cycle.py`, `conductor/policy.yaml`/
`policy.py`, `agents/*/role.md` and `tools.yaml`. Stage 0 has just removed the
old `facts` plumbing; do not bring it back.

## Tasks, in order (commit after each)

1. Plan in this file's Result section: exactly what of the design's stage 1
   you build, and anything the design leaves unclear that you decided.
2. `relies_on` on proposals with server-side reads at filing (read tools on
   the proposer's own allowlist only, mutating tools refused, capped), stored
   value plus tick.
3. `queue.pending_brief` (conductor only) or whatever the design names, giving
   the conductor per-proposal summaries for the Overseer's briefing with
   cited facts refreshed mechanically ("now V" only when changed) and overlap
   flags.
4. The Overseer's ruling briefing in the design's fixed order, with threshold
   alerts held as data in `conductor/policy.yaml` (generic: read tool, field,
   threshold; no per-item code).
5. Charter lines (one or two each): proposers cite facts in `relies_on`; the
   Overseer rules on reasoning and does not re-read cited facts. The Overseer
   loses its stock reads (allowlist), per the design; update every tool count.
6. Tests per the design's acceptance points, then the Result: built, tests,
   deploy targets (expect vm103-dfmcp, vm106-conductor, vm106-agents) and the
   live check (a ruling wake re-fetches no cited fact).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early and after
  every milestone; rate-limit cutoffs are routine.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`, or `docs/CONDUCTOR-EXECUTION*.md`. If the design is
  wrong or unbuildable somewhere, say so in the Result; do not silently
  diverge.
- Touched surfaces: `dfqueue/schema.py`, `dfqueue/store.py`,
  `dfmcp/queue_tools.py` (not `gotchas_store.py`), `dfmcp/roles.py` if a
  conductor-only tool needs it, `conductor/briefing.py`, `conductor/cycle.py`
  (wiring), `conductor/policy.*`, `agents/*/role.md` (one or two lines each),
  `agents/*/tools.yaml`, tool-count tests and docs, this handoff. Not `web/`,
  `dfqueue/feed.py`, `conductor/hold.py`, `pause_watch.py`, `runner.py`.
- Tools must be generalisable. Never show a model a rendered map. No armok
  powers. Public repo: no hostnames, IPs or tokens. No em dashes. No
  attribution lines in commits.
- Full ambient `python -m pytest` and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Result

(executor fills this in)
