# Quartermaster

**Kind:** advisor. **NOT ENABLED.** Blocked on tools, not on a decision.
No `tools.yaml` or `model.yaml` yet, deliberately: writing an allowlist of tools
that do not exist would imply a capability this project does not have.

## Would own

- **Food and drink security.** The single most common cause of death in a young
  fort, and deliberately separated from efficiency analysis because they are not
  the same problem. Booze matters as much as food: dwarves work badly without it.
- **Work orders.** What the fort should be producing, and in what order.
- **Stock thresholds.** What "running low" means for each thing that matters.
- **Seeds**, which are quietly unforgiving: a fort that eats its last plump
  helmet seeds has lost farming permanently.

## Would NOT own

- **Where anything physically goes.** That is the Architect's.
- **Labor assignment as a routine lever.** `autolabor` is the baseline
  underneath, deliberately, so this role does not re-decide hauling and mining
  balance every cycle.

## Why it is not enabled

Verified 2026-09-12 (`research/2026-09-12-write-conflict-matrix.md`,
`research/2026-09-12-dfhack-capability-checks.md`):

- **No tool in this repo touches manager work orders or stockpile settings**
  (filters, thresholds, links). Not one.
- **DFHack's own `stocks` and `workflow` are tagged unavailable** on this
  install, as part of the same v50 breakage `memory/dfhack-environment.md`
  tracks. So there is nothing to wrap.
- **But `workorder.lua` IS present and callable**, with a real
  `create_orders()`. The path is real, it is just unbuilt. This role needs new
  tools written against the DFHack API, which is a materially bigger job than
  exposing an existing tool.

## Traps to hand whoever builds this

- **Work orders have no priority field.** The `manager_order` struct has none.
  Priority is realised purely as position in the ordered
  `world.manager_orders.all` vector. DF's 1-7 is a *dig designation* mechanism
  and does not apply here. Do not build an API that pretends they are the same.
- **This role will want to change labors when a threshold trips**, and the only
  labor tool that exists (`set-labor`) races `autolabor` on ordinary citizens.
  That race is the first thing to fix, before this role has anything safe to
  propose in that direction.
- **Food-days and booze-days remaining should be computed in code**, not by the
  model. One integer replaces an entire inventory listing, and arithmetic over
  many rows is what models are worst at.
