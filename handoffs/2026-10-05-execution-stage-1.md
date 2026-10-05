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

### Plan (committed first)

Built from design section 8.2 stage 1 only; nothing of `step`, `phases`,
`project_id`, routing, timeouts or defer.

1. `relies_on` (0..6 of `{tool, args, field}`) on `queue.propose`. A new
   injected `fact_reader(role, tool, args)` in `dfmcp/queue_tools.py`, built in
   `dfmcp/server.py` from the registry, roster and pool. It reads only
   DFHack-backed, non-mutating tools on the caller's own allowlist; native
   tools (series, queue, doctrine) are refused as citations. `field` is a
   dotted path into the result (list indexes as digits) and must land on a
   scalar. Unreadable, wrong role or missing field refuses with a repair
   message. Filing reads are bounded at 60 s total, timeout giving a distinct
   "server busy, file again" refusal. Stored: `relies_on` as given, plus
   server-set `cited` = `[{tool, args, field, value, tick}]`, both validated
   in `dfqueue/schema.py`.
2. `queue.pending_brief` (conductor only, handler refuses other roles):
   capped at 8 with the true count, per-proposal summary, prediction, cost,
   priority, `duplicate_of`, cited facts refreshed by the same reader using
   the proposer's role (`now` only when changed, "unreadable" flagged,
   identical reads shared), `overlaps` (stage 1 meaning: same type and a
   shared landmark or area in preconditions, since resolution fields come
   with `step` in stage 2), plus a `decided` block (open projects one line
   each, last five rulings). WIP cap is stage 2, so only the count shows.
3. `build_ruling_briefing` in `conductor/briefing.py`: one text prompt in the
   design's fixed order (header, vitals plus threshold alerts, decided,
   pending proposals, other open items, the ask last). Used for the
   Overseer's ordinary wake. The tripwire and unexplained-pause wakes keep
   the JSON briefing (they are not ruling wakes; stage 1 must not alter the
   pause-safety paths). Threshold alerts live in `conductor/policy.yaml`
   (`threshold_alerts`: read tool, args, field, per, below, text) and are
   read once per cycle by generic code; a failed read drops its line. They
   appear for every role (as an `alerts` list in JSON briefings, only when a
   threshold is crossed). The conductor regains `stocks.food-drink` for them.
4. Charter lines in architect, quartermaster (cite in `relies_on`) and
   overseer (rule on reasoning, do not re-read cited facts). Overseer loses
   `stocks.food-drink`, `stocks.seeds`, `stocks.availability`. Tool counts
   updated (STATE.md, tests).
5. Tests; then this Result is completed.

