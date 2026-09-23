# Handoff: generalise `workjob` over every workshop and job, with a count and repeat

Date: 2026-09-21. Live but read-only on VM 103 (fort paused, dry runs only);
no real job is queued by this stream.

**DISPATCHED 2026-09-23** (user's call: "lets generalise workjob"), after
sitting written but undispatched for two days. Five things changed under it
in the meantime, and they narrow the work rather than widening it:

1. **A `REPEAT` param already landed** on `workjob queue` 2026-09-23
   (`handoffs/2026-09-23-order-job-attribution-and-checks.md` item 6),
   untested live. Deliverable 2 below still stands, but REPEAT is now an
   existing parameter to verify and keep working, not one to invent.
2. **`orders.create` already covers twelve job kinds** (blocks, mechanisms,
   barrels, brew_drink, bucket, bed, door, table, chair, splint, crutch,
   soap) while `workjob` still knows three. That asymmetry is the concrete
   shape of the problem: the fort's Chair had to be ordered through
   `orders.create` on 2026-09-23 because `workjob` had no token for it.
   **Twelve is the floor, not the target**: `getJobs` should make the
   vocabulary the game's, not a second hand-maintained table. If you end up
   with a table of twelve, the stream has failed its own point.
3. **Manager orders are no longer hypothetical.** Two real Office zones
   exist (one owned by the Manager, unit 345) and four manager orders exist,
   none yet active. So the "until manager orders work" framing in Why below
   is softened: both routes will be used together, and the user has said so
   explicitly. Direct jobs remain the route that does not depend on a
   Manager, an Office or room value, which is exactly why this tool matters.
4. **`df.job.order_id` links a spawned job back to its manager order**,
   correcting an earlier research claim. If your generic path touches job
   creation, do not break or fake that field: a direct job legitimately has
   no order, and must not pretend to have one.
5. **Suite baselines have moved** since this doc was written. Current:
   ambient **1348 passed / 3 skipped**, `.venv-dfmcp` **652 passed** (both
   measured 2026-09-23). Report before and after against these, not the
   834/475 figures in Done means below.

Two rules to add to the Rules section below, both learned the hard way since
this doc was written: **use `bash scripts/vm-ssh.sh df '<cmd>'` for every VM
command** (do not write your own ssh wrapper and do not read the address from
`.env` yourself: four separate agents have leaked a VM address doing exactly
that), and **no attribution lines in any commit message** (no Co-Authored-By,
no "Generated with Claude Code"). Also: a concurrent research stream owns
`research/2026-09-23-flood-relevance-and-traffic.md` and touches no code, so
`scripts/dfhack/TOOLS.yaml` is yours alone this cycle.

One warning from the most expensive bug of the week, which your work is
directly exposed to: **a `pcall`-guarded read that returns a default on
failure is indistinguishable from a genuine negative reading.** Six creature
tag reads shipped silently broken that way and passed three offline test
layers, because none held a real creature raw. You will be reading reagents,
job definitions and item fields off live raws. Report unreadable fields
explicitly (the pattern is a `read_failures` array plus `dfhack.printerr`),
and treat `docs/TRAPS.md`'s "A pcall-guarded read..." entry as required
reading before you write a single guarded read.

Read `CLAUDE.md` (especially "Tools must be generalisable"),
`scripts/dfhack/df-overseer-workjob.lua` (the three-job tool this replaces, and
its long header on the DFHack code path it followed),
`handoffs/2026-09-19-workshop-add-job.md`, `handoffs/2026-09-21-nobles-appoint.md`
(why manager orders are not available yet), `scripts/dfhack/df-overseer-building.lua`
and `scripts/dfhack/df-overseer-zone.lua` (the pattern: kinds read from the game,
per-kind policy in data, dry run by default), and `docs/TRAPS.md`, then this.

## Why

Manager orders need an appointed Manager **and an Office**; the user confirmed
from play that the office is required, and the fort has none yet. Until that works
(and for anything a player would do by clicking a workshop), the fort's only way to
make things is a direct job queued at a workshop, which is what `workjob` does. It
knows **three jobs** (blocks at the Masons, mechanisms at the Mechanics, brewing at
the Still), queues **one** at a time, and has no repeat. The user's call
(2026-09-21): we need a proper tool for this. It is also on the known list of
single-instance tools that break the generalisability rule.

## Two facts found on the install that change the design

Both read from this install's own files on 2026-09-21, not yet exercised by the tool:

1. **DFHack already builds a workshop's job list generically.**
   `hack/lua/dfhack/workshops.lua` exposes `getJobs(buildingId, workshopId, customId)`,
   the module behind the game's "add job" menu equivalent. It returns, for any
   workshop or furnace kind, the hard-coded job definitions (name, `job_fields`,
   `items`) **plus every reaction the raws attach to that building**, with each
   reagent converted to a `job_item` by `reagentToJobItem` (the reagent cloned with
   defaults, `reaction_id` and `reagent_index` set), and smelting jobs per ore. The
   existing tool's header claims no DFHack script builds a reaction job's items
   generically; **that is wrong for this install** (`addReactionJobs`). The
   Lua-stream's hosting dump (out of tree, in the scratchpad `building-dump/`)
   already found `getJobs` covers only 16 of 33 kinds for hard-coded jobs, so the
   coverage gap is real and must be measured.
2. **A job carries a `repeat` flag** (also `do_now`, `by_manager`, `suspend`), the
   "repeat" toggle in a workshop's job list. That is a workshop-level standing order
   with no manager. It is the honest answer to "keep making these".

## Deliverables

1. **`list-jobs WORKSHOP`**: for an existing workshop (addressed by landmark name, as
   `workjob` does today), every job the game offers there, from `getJobs`, each with
   a token to pass back, its name, and what it needs (the job's `items` summarised:
   class, quantity, material constraint). Coordinate-free. State plainly which job
   kinds `getJobs` does not cover for that workshop; an unreadable field is `null`
   plus an error, never a default.
2. **`queue WORKSHOP JOB [COUNT] [REPEAT] [DRY_RUN]`**, generic over the job token,
   replacing the three-entry table with `getJobs`. Dry run by default. COUNT is how
   many identical jobs (the workshop cap is 10 queued; refuse above it or over the
   room left, with the reason). REPEAT sets the job's `repeat` flag. Keep the
   existing refusals (wrong workshop, unfinished workshop, full queue) and keep
   refusing, rather than guessing, when a reagent cannot be resolved to a concrete
   item. **Keep the old tokens (`blocks`, `mechanisms`, `brew_drink`) working with
   unchanged results.**
3. **Requirements and honesty in the result**, like the building tool: what the job
   needs, the six-deduction availability of each needed item (reuse
   `stocks.availability`'s logic, do not re-derive it), and any gap ("needs 1
   boulder, 0 available"). A job that can be queued but cannot start is reported.
4. **Read-only live verification on VM 103**: `list-jobs` for every workshop and
   furnace the fort has (Masons, Mechanics, Still, Craftsdwarfs and whatever else
   exists), the coverage gap per kind, dry-run `queue` for at least a hard-coded
   job, a reaction job with a concrete reagent, one with a wildcard reagent (say
   what happens), COUNT and REPEAT, and each refusal; pause state and tick
   identical before and after. Quote the output. **No real job.** If a real job is
   needed to settle a question, write the exact supervised test for the
   orchestrator instead of running it.
5. **Manifest and tests**: `scripts/dfhack/TOOLS.yaml` (new commands in the
   optional-args forms; `knowledge_scope` chosen and justified), tests, and the
   proposed role grants written into the report. Do not edit `agents/**` or
   `dfmcp/**` (report any argument-description text needed for `dfmcp/tools.py`).

## Rules

- You own `scripts/dfhack/df-overseer-workjob.lua`, `scripts/dfhack/TOOLS.yaml`, its
  manifest tests and this doc. Do not touch `dfmcp/**`, `production/**`, `agents/**`
  or `gotchas/**`. One live stream at a time on VM 103; check nothing else is running.
- Live, read-only: never unpause, never queue a real job, bound every scan
  (`docs/TRAPS.md`), run scripts from a scratch path and remove it. Stop and report
  on any classifier refusal; do not route around it. SSH as `df`; read secrets by key
  only; no address, hostname or token in any tracked file.
- Unknown is never zero. Do not write `Working.md`, `decisions/DECISIONS.md`,
  `memory/` or `handoffs/INDEX.md`. **Commit after each milestone** and extend this
  doc's report as you go. No em dashes in prose. Use the Write tool for scratch
  scripts rather than long inline shell heredocs.

## Done means

`workjob` lists and dry-runs every job the game offers at every workshop the fort
has, the old three tokens behave as before, COUNT and REPEAT are supported and their
refusals tested, coverage gaps are named per kind, the manifest and tests agree, the
suites pass (baseline **834 passed / 2 skipped** ambient, **475 passed** in
`.venv-dfmcp`, report before and after), and the write-up says what a real
supervised queue test needs.
