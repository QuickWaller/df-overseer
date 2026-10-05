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
