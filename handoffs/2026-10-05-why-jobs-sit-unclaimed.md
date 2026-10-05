# Handoff: why the fort's jobs sit unclaimed (read-only diagnosis)

Date: 2026-10-05. **Researcher-style executor, Sonnet, worktree. Read-only
on VM 103: no writes to the game, no labour changes, no unpause, no
deploys.** The fort is paused; keep it so.

## Why

A supervised 5-minute unpause on 2026-10-05 (tick 246921 to 250046, about
2.6 game days; `Working.md`, 2026-10-05 notes) showed the fort not
progressing: two brew jobs at the Still unclaimed all window (1 citizen has
BREWER enabled), the new bedroom's Bed construction suspended, the site-4
digs unclaimed (2 miners), and a Wall construction suspended for about 40,000
ticks. Drink is still 0 for 22 dwarves. Before unattended running, we need
to know why, and whether the fix is a setting (labour policy), a tool gap, or
an agent behaviour.

Read first: the register's 2026-09-30 rows ("set intent, let the game
execute"), `handoffs/2026-10-01-labor-quota.md` (autolabor runs at 53.16-r1;
`labor.quota` sets its per-labour min, max and pool), the Quartermaster's and
Overseer's allowlists (`agents/*/tools.yaml`), `docs/TRAPS.md`.

## Questions to answer, with evidence

1. **Labour.** Is autolabor enabled now? Its per-labour settings for BREWER,
   MINE, CARPENTER, MASON, HAUL_ITEM and anything else these jobs need
   (`labor.quota-status` over MCP, read-only). How many citizens could do
   each job, and what are they doing instead (idle, sleeping, on break, on
   another job)? Use the read tools over `scripts/ops/mcpcall.py` with the
   overseer token and DFHack read-only commands only.
2. **Each stuck job.** For the brew jobs, the Bed, the site-4 digs and the
   old Wall: why exactly is it unclaimed or suspended (no worker with the
   labour, worker busy, missing item or material, unreachable, suspended by
   the game for a reason it states)? `stuckjobs.find` and any job detail the
   tools expose.
3. **Who should have caught it.** Do the agents' briefings include stuck
   jobs (`conductor/briefing.py`)? Did any agent run since 2026-10-02 see
   these and do nothing? Is there a wake reason that should have fired
   (`stuck_job`, `stalled_order` in `conductor/policy.yaml`) and why did it
   not, or did it?
4. **Recommendation.** Ranked fixes, each tagged setting / tool gap / agent
   behaviour, honouring "set intent, let the game execute" (prefer adjusting
   autolabor policy through `labor.quota` over hand-assigning labours), and
   the no-armok rule. Say which an agent could do itself with its current
   tools on the next cycle, and which need a code change.

## Rules

- First step: `git merge --ff-only main`.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Touched surfaces: this handoff (findings and Result) and, if useful, a new
  `evals/live/2026-10-05-stuck-jobs-diagnosis/README.md`. No code.
- Use `DF_ENV_FILE=c:/website-projects/df-automation/.env` for
  `scripts/vm-ssh.sh`; read `.env` by key only. Public repo: no hostnames,
  IPs or tokens. No em dashes. No attribution lines in commits.
- Commit after each answered question.

## Done when

All four questions answered with the commands you ran and what they
returned, and a Result section here.

## Result

Done, read-only, all reads at tick 250046 (fort paused throughout; no writes,
no labour or quota changes). Full evidence and the ranked fixes are in
`evals/live/2026-10-05-stuck-jobs-diagnosis/README.md`.

1. Labour: autolabor on, suspendmanager off, buildingplan on. Hands are not
   the shortage: 20 of 22 citizens idle. BREWER and BUILD_CONSTRUCTION each
   have a single holder (unit 353, idle); MINE has two (192 digging, 346 idle).
2. Stuck jobs: the Bed has no bed item and no order exists to make one;
   the second miner has no pick (one pick in the fort, held by 192; no
   Forge); site-4 dig 2879 waits behind 2872; the Wall is suspended for an
   unrecoverable reason with suspendmanager off; brew 2861 is unclaimed with
   no visible blocker (cause unproven; brew 2860 is now in progress).
3. Nobody could have caught it: the briefing carries no stuck jobs, the
   Quartermaster (the `stuck_job` wake target) lacks `stuckjobs.find`, and
   `job_stalled` is never emitted so `stuck_job` cannot fire; `stalled_order`
   watches manager orders only and none exist. No agent ran after 2026-10-02.
4. Ranked fixes are in the README (bed order now; BREWER min 2 now; briefing
   and wake wiring code change; suspend visibility and unsuspend tool gap;
   second pick needs a Forge).

Note: Working.md's "carpentry still unbuilt" is stale: a Carpenters workshop
exists. A separately modified `dfqueue/feed.py` in this worktree is not part
of this stream and was left uncommitted.
