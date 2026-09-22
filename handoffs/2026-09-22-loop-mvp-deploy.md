# Stream: deploy the agent loop MVP to VM 103 and VM 106, fort kept paused

**Written** 2026-09-22. **Status:** dispatched. **User go-ahead:** 2026-09-22,
"deploy it all, keep it paused and then come back to me", and "have a sonnet
do it". Token placement authorised earlier the same day ("you can do the
tokens yourself"). **Live work on VMs 103 and 106.** Sonnet executor,
worktree-isolated. **No push. No attribution lines in any commit** (no
Co-Authored-By, no "Generated with Claude Code": the user's instruction).

## Why

The agent loop MVP is built and merged on local `main` (`docs/AGENT-LOOP.md`;
five streams: `handoffs/2026-09-22-loop-*.md`). This stream puts all of it on
the VMs and proves it as far as it can go **without the fort ever running**.
The user reviews the result before anything unpauses.

## First

`git merge --ff-only main` in your worktree. Then read, in full: `CLAUDE.md`;
`docs/TRAPS.md`; `handoffs/2026-09-21-deploy-building-batch.md` (the last
deploy: the exact mechanics, backup layout, hash checks and what went wrong);
the **Result sections** of all five `handoffs/2026-09-22-loop-*.md` (each
lists its own deploy steps and live checks; the fixes stream amends the
conductor stream's); `evals/live/2026-09-15-overseer-first-ruling/README.md`
(how openclaw is configured and run on VM 106, its traps, and how tokens were
placed); `infra/local.example.env`, `infra/conductor.example.env`,
`infra/conductor.service.example`.

## Hard lines

- **The fort is paused now and stays paused.** Never unpause, not even
  briefly. `clock.resume` is never called. Any live check that needs game
  time (the tripwire's true-negative and positive tests) is **not run**: write
  it down as owed, with the exact commands.
- **Quicksave before the first action on VM 103**, and confirm it landed by
  the slot mtime (`docs/TRAPS.md`). Stop if it did not land.
- **No unbounded query against the live DFHack process** (`docs/TRAPS.md`).
- **Secrets:** read every secret by its key name only (`grep -E '^KEY='`),
  never a whole file; never print one, never put one in argv, a tracked file,
  a log, a report or this workstation's disk. New tokens are generated on a
  VM and moved VM to VM (`scp -3` or an ssh pipe, as earlier streams did).
  Brave's key comes from this workstation's `.env` by name
  (`BRAVE_SEARCH_API_KEY`) over stdin. **If the auto-mode classifier refuses
  a secret write, stop that step and report it; do not route around it and
  never ask another session to do it.**
- **The conductor is installed and dry-run only.** `--dry-run --once`, no
  model call, no clock change. Do not `enable` or `start` its unit for real.
- No model call of any kind (no `agent exec`). `openclaw mcp probe` and
  config validation are fine ($0).
- Hash **committed** bytes (`git -c core.autocrlf=false archive` / `show`),
  never the working copy.
- Back up everything you replace, in a dated directory, as the last deploy
  did.
- Genuinely unrecoverable loss (the fort save, a VM) stops and reports.
- Do not write `Working.md`, `decisions/` or `memory/`. No em dashes.
- Commit your report as you go (in `evals/live/2026-09-22-loop-mvp-deploy/`
  and this doc's Result section).

## What to do

**VM 103**
1. Read the fort's state first (paused, tick, alive/dead, worst hunger and
   thirst). Quicksave, confirm it by mtime.
2. Deploy from committed `main`: `dfmcp/`, `dfqueue/`, `learning/`,
   `agents/`, the new and changed `scripts/dfhack/*.lua` and `TOOLS.yaml`, per
   the last deploy's mechanics. Hash-verify every file.
3. Service env: `MCP_ROLE_TOKEN_QUARTERMASTER` and `MCP_ROLE_TOKEN_CONDUCTOR`
   (newly generated), `BRAVE_SEARCH_API_KEY`, `MCP_SERVER_DFHACK_SOURCE_ROOT`
   (confirm the real path first: `ls` the scripts and docs directories under
   it), `MCP_SERVER_WIKI_SNAPSHOT`.
4. Build a **curated wiki snapshot** with `scripts/build_wiki_snapshot.py`:
   the 20 to 30 pages `docs/MEMORY-ARCHITECTURE.md` names (aquifers, sieges,
   defence, fort layout, industry chains, food, drink, farming, wells, water,
   the Manager and nobles, workshops, stockpiles, FPS), polite throttle. Place
   it on VM 103 at the configured path.
5. **Back up the queue database**, then let the migration run (schema 1 to 2)
   and check that the existing rows still read correctly.
6. **Void `proposal-0001`** with `python -m dfqueue.store` and the note:
   "Voided 2026-09-22 by the user's decision (register): its 1200-tick window
   elapsed from ruling-to-execution latency at the real 100 FPS, before any
   tool could execute it; grading it would record latency, not the proposal."
   Read it back.
7. Restart `dfmcp-server`, confirm active, and **list every role's tools over
   a real MCP client** (overseer, architect, quartermaster, consultant,
   conductor). Report the counts and check the key grants: the conductor
   holds clock, quicksave, vitals, `queue.overview`, `queue.grade`; the
   Overseer holds `queue.escalate` and **not** `clock.resume`; only the
   Consultant holds the five retrieval tools.
8. **Paused-safe live checks**, all over MCP as the conductor or the right
   role: `clock.status`; `clock.set-speed` 10 then back to 100, confirmed by
   reading `df.global.enabler.fps` independently; `clock.pause` on an already
   paused fort; `clock.resume` refused while a tripwire is latched is **not**
   tested (it would need a trip), so record it as owed; `clock.arm` then
   `clock.disarm` (confirm it arms and disarms, with no game time passing);
   `fort.quicksave` with its confirm call; `vitals.summary` against the state
   you read in step 1; `queue.overview`; `queue.grade` (it must not grade the
   voided proposal); one `web.search` and one `web.fetch`; one
   `knowledge.wiki_lookup`; one `dfhack.source_search`.
9. Re-read the fort's state. It must be paused, at the same tick.

**VM 106**
10. Place the MCP tokens openclaw needs (overseer and architect already
    exist; add quartermaster and consultant) in its secrets env file, by key.
11. One pinned openclaw configuration per role (architect, quartermaster,
    consultant, overseer), each with its own `systemAgent.agentId` and a
    `tools.allow` matching its `agents/<role>/tools.yaml`, per the conductor
    stream's Result. `openclaw config validate` each, then `openclaw mcp
    probe` each against the live server and compare the counts with step 7.
12. Install the conductor: its own venv from `conductor/requirements.txt`,
    `conductor.env` from the example (`MCP_ROLE_TOKEN_CONDUCTOR` placed by
    key, `base_fps` 100, `think_fps` 10), the systemd unit installed but
    **not enabled or started**, Docker socket access confirmed.
13. Run `--dry-run --once` by hand and capture its output: what it read,
    who it would wake and why, what clock level it would choose. No model
    call, no clock change.
14. Leave nothing listening that was not there before.

## Report (this doc's Result section, plus `evals/live/2026-09-22-loop-mvp-deploy/README.md`)

Fort state before and after (must match, paused); every file deployed and
its hash result; backups' location; per-role tool counts; each live check's
result; the void read-back; the dry-run output; every refusal met, verbatim;
**what is owed before the first real start**, as exact commands (the
tripwire's true-negative and positive tests, a short supervised first
cycle); the home-lab lines owed (`inventory/services.yaml`: the conductor
unit on VM 106, openclaw now configured for four roles), with the commands
you actually ran.

## Result

(executor fills in)
