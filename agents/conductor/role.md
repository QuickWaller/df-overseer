# Conductor

**Kind:** system. **Code, never an agent.** No model ever calls the tools
below or reads this file as a prompt; it exists so this role is documented
the same way every other roster entry is, and so `dfmcp/roles.py`'s
structural requirements (a directory, a `role.md`, `tools.yaml`,
`model.yaml`) are satisfied for it too. **Tools:** see `tools.yaml`.

## Why this role exists

`docs/AGENT-LOOP.md` (ss1-3) is the design; this charter narrows it to what
this one role owns. The fort needs something that starts, throttles and
pauses the game clock, quicksaves before any decided action runs, and wakes
the right role at the right speed -- deterministically, auditable, and
correct even if every model-backed role and openclaw itself are down. That
is code's job, not a role woken by a prompt. The conductor SERVICE that will
actually run this loop (`docs/AGENT-LOOP.md` item 3: Python, on VM 106 by
default, launching each role's own one-shot `agent exec` run) is a later,
separate stream; this stream builds only the game-side tools
(`df-overseer-clock.lua`, `df-overseer-fort.lua`, `df-overseer-vitals.lua`)
and the MCP role/token that service will hold.

## Owns

- **The frame cap** (`clock.set-speed`): `base_fps` while nothing is
  time-sensitive, `think_fps` while something is, per the wake-reason policy
  table in `docs/AGENT-LOOP.md` ss2 -- a data table, not a judgment call.
- **Pause and resume** (`clock.pause`/`clock.resume`): pausing is always
  allowed; resuming is refused by the tool itself while a tripwire is
  latched. **This role must never be asked to resume past a live latch
  without the Overseer having cleared it first** -- that is what
  `clock.resume`'s own refusal enforces, not a rule this charter merely
  states.
- **The in-game tripwire watcher** (`clock.arm`/`clock.disarm`/`clock.clear`):
  arms and disarms the periodic in-game check that pauses the fort itself
  on a death, a critical vital, or a reachable hostile, independent of
  whether this service or openclaw is even running (`docs/TRAPS.md`'s wedged-
  pipe incident is exactly why the watcher lives inside the game loop, not
  over SSH).
- **Quicksave before any decided action** (`fort.quicksave`): the existing
  quicksave discipline (`docs/TRAPS.md`), issued by code, never assumed.
- **The per-cycle briefing's Tier 0 read** (`vitals.summary`, `overview.get`,
  `queue.pending`): what gets handed to whichever role wakes this cycle.
- **Triage**: who wakes, if anyone, and at what clock speed. Code rules
  (`docs/AGENT-LOOP.md`'s triage table), not a model's judgment -- a quiet
  cycle wakes nobody and costs nothing.

## Does NOT own

- **Any fort decision.** Every write tool this role holds mutates DFHack's
  own runtime state (the frame cap, the pause flag, the watcher, a save) --
  never a designation, a build, an order, or anything the fort itself will
  remember. `agents/ROSTER.yaml`'s `sole_writer: overseer` is unchanged by
  this role existing.
- **Never unpause past an unresolved tripwire.** Not a charter line alone:
  `dfmcp/roles.py`'s `SYSTEM_CLASS_TOOL_IDS` exception is gated on role
  `kind`, with **no carve-out for the sole_writer**, so granting
  `clock.resume` to `agents/overseer/tools.yaml` (kind: actor) would fail to
  load, not just be against the charter.
- **Model calls of any kind.** See `model.yaml`.

## Confidence and gotchas

Every DFHack-backed tool result carries a `tool_guidance` block (see
`agents/CONFIDENCE-LEGEND.md`). **UPDATED 2026-09-23**: this role's tools
are deployed and live-verified, not merely offline-built. `clock.set-speed`,
`clock.pause`, `clock.status`, `clock.arm`/`disarm`, `fort.quicksave` and
`vitals.summary` were all called live during the 2026-09-22 deploy
(`evals/live/2026-09-22-loop-mvp-deploy/`); `clock.resume` and `clock.clear`
remain genuinely unexercised live (the fort has never been unpaused during
any deploy or run to date) -- see `scripts/dfhack/TOOLS.yaml`'s own
per-command `verified` fields for exact evidence, not a blanket claim here.
The conductor SERVICE itself (`conductor.service` on VM 106) is installed,
Docker-capable and has never run as a live systemd service -- only a
manual, foreground `--dry-run --once`, most recently clean from a real
unseeded cursor after the CP437 encoding fix
(`evals/live/2026-09-22-loop-game-text-encoding/`). This role also now
holds `ledger.read`, `announcement-levels.slow-ids` and `orders.list`
(2026-09-23, for the stalled/blocked order poller), deployed and
live-verified the same day (`evals/live/2026-09-23-attention-deploy/`).
