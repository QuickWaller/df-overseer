# Handoff: cited facts in proposals, and a briefing without fixed stock lists

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no deploys.**

## Why (user's calls, 2026-10-05, register rows of the same date)

1. **Agents trust each other's facts; they may challenge each other's
   reasoning.** In the 2026-10-05 cycles the Overseer spent its opening
   lookups re-reading drink, barrels, beds and wood to check what the
   proposals claimed. A fact a proposal relies on should be vouched for by the
   system, not re-checked by another agent.
2. **No fixed per-role stock lists in the briefing.** The merged briefing
   build (`handoffs/2026-10-05-better-briefing.md`, merged, not deployed) gives
   every role drink and food and fixed item lists per role
   (`briefing_extras` in `conductor/policy.yaml`) because every measured turn
   read them. That bakes one fort's current crisis into every briefing.

## What to build

**A. Cited facts on proposals (server-vouched).** An optional proposal field
(name it in the plan, e.g. `relies_on`) listing the facts the proposal rests
on, each naming a read tool, its arguments and the field it cites (for
example `stocks.availability` `{type: BARREL}` field `available_units`). At
write time the **server** performs each read itself (it must be a read tool on
the proposer's own allowlist; refuse anything that mutates) and stores the
value it got plus the game tick, so the record holds what the game said, not
what the model typed. Generic: any read tool and any field path, no per-item
code. Bounded: cap the number of facts per proposal and the stored size.

**B. Staleness is mechanical.** When the conductor briefs the Overseer on
pending proposals, it re-reads each cited fact (one read per distinct
tool+arguments per cycle, total: a failed read drops the line) and shows
`cited value at tick T, now value` only when it changed; unchanged facts show
once as cited. No agent is asked to distrust another's fact.

**C. Briefing rework.** Remove the fixed `facts` stock blocks and
`briefing_extras` per-role item lists from the merged build. Keep: vitals
(already carried), the stuck-job lines, stalled orders **only for roles whose
wake reason or allowlist makes them relevant (say which in the plan)**, and a
new **threshold alert** list held as data in `conductor/policy.yaml` (for
example drink per citizen below a floor, prepared meals plus raw edibles per
citizen below a floor): a line appears only while the threshold is crossed.
Adding an alert is one YAML entry naming a read tool, field and threshold, the
same generic shape as A. Keep the conductor's new read grants only if A, B or
C still needs them; update tool counts accordingly.

**D. Charters, one or two lines each.** Proposers (Quartermaster, Architect):
cite the facts the proposal rests on in the new field. Overseer: cited facts
are already vouched for and refreshed by the system; rule on the reasoning,
do not re-read cited facts.

## Tasks, in order (commit after each)

1. First: `git merge --ff-only main`. Plan in this file's Result section:
   field name and schema, which tools are allowed, caps, where the server read
   happens, the alert data shape, what is removed from the merged build.
2. Build A, then B and C, then D.
3. Tests: a cited fact stores the server's value and tick, not a model-supplied
   number; a mutating tool or one outside the proposer's allowlist is refused;
   caps; proposals without the field still validate; staleness line only on
   change; alert appears only past threshold and is data-driven; the removed
   blocks are gone; a failed read never fails a cycle or a proposal write
   (decide: does a failed cited read refuse the proposal or store "unread"? say
   why).
4. Result: built, tests, deploy targets, the exact charter lines added.

## Rules

- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`.
- Touched surfaces: `dfqueue/schema.py`, `dfqueue/store.py` (proposal field
  only), `dfmcp/queue_tools.py` (`queue.propose` and the server-side read
  only; not `gotchas_store.py`), `conductor/briefing.py`, `conductor/cycle.py`
  (wiring), `conductor/policy.yaml`/`policy.py`, `agents/conductor/tools.yaml`,
  `agents/{quartermaster,architect,overseer}/role.md` (one or two lines each),
  their `tools.yaml` descriptions of `queue.propose` only, tests, docs that state
  tool counts, this handoff. Not `web/`, `dfqueue/feed.py`, `conductor/hold.py`,
  `conductor/pause_watch.py`, `runner.py`'s thinking code.
- Tools must be generalisable: no per-item or per-tool branches.
- Never show a model a rendered map. No armok powers. Public repo: no
  hostnames, IPs or tokens. No em dashes. No attribution lines in commits.
- Full ambient `python -m pytest` and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Result

(executor fills this in)
