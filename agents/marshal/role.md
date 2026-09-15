# Marshal

**Kind:** advisor. **NOT ENABLED.** Blocked on a trustworthy threat signal
*and* on write tools. No `tools.yaml` or `model.yaml` yet.

## Would own

- **Military posture, not tactics.** Burrows, squad standing orders, equipment,
  training schedules, whether the bridge is up.
- **Playbooks, which are this role's actual deliverable.** Structured triggers
  and actions the Sentry executes with no model in the loop. See §6.
- **Post-fight work.** Hospital, triage, recovery, replacing losses.

## Would NOT own

- **Real-time tactics.** Explicitly rejected, and not a matter of scope
  preference: DF combat resolves in seconds while an agent round trip is tens of
  seconds, so no agent decision can ever be inside a fight. Everything that
  decides a fight happens before it or after it.
- **Acting.** Like every advisor, it proposes.

## Why it is not enabled: the signal does not exist

This is the sharpest finding of the 2026-09-12 research pass, and it is worth
stating bluntly because it would otherwise be discovered by losing a fort.

- **`unit-status hostile` is verified wrong in both directions.** It missed a
  real kea attack entirely and flagged harmless deep-cavern demons instead
  (`decisions/DECISIONS.md` 2026-09-11).
- **The event layer has the same blind spot, by construction.** `INVASION`
  fires only when DF registers an actual invasion. It does **not** fire for an
  ambush, a lone thief, a sneaking creature, or ordinary wildlife turning
  aggressive (`research/2026-09-12-dfhack-capability-checks.md` §5, read from
  DFHack's own EventManager source).

So the problem is not one unreliable sensor to be recalibrated: neither
`unit-status hostile` nor the event layer is trustworthy on its own. **UPDATED
2026-09-16: a purpose-built replacement now exists and is live-verified**,
`threat.scan` (`decisions/DECISIONS.md` 2026-09-12, "Threat detector
LIVE-VERIFIED") -- reachability-gated, not flag-gated, currently granted to
the Overseer's `tools.yaml` only, not yet to this role. What still blocks
Marshal being enabled is the other half: **no write tools exist for military
posture, squads or burrows**, so even with a trustworthy read signal this
role would have nothing to act through, and its deliverable stays playbooks
until that changes.

- **Water and magma breach has no signal of any kind**, a checked negative
  across both the event enum and the announcement enum. Nearest polling target
  is map-block liquid scanning (`flow_size`/`liquid_type`, triggered off
  `flags.update_liquid`). **`df.global.world.flows`, which an earlier draft of
  this charter named, does not exist under that name**; re-verified 2026-09-12.
  A detector now exists (`df-overseer-breach.lua`) but has never been run, and
  its cheap first stage depends on a flag that nothing in the shipped scripts
  ever reads, only sets. Treat flood response as uncovered until that is
  settled live.

## Traps to hand whoever builds this

- **A playbook must be data, not prose.** Triggers and thresholds as typed
  fields, so they can be tuned mechanically and therefore learned. A paragraph
  of instructions can only be rewritten.
- **Log every reflex firing with its cost and a follow-up check.** You will be
  able to measure cost and false-positive rate. You will **not** be able to
  measure whether a reflex saved the fort, because that needs a counterfactual
  and DF replay determinism is unverified. Since benefit is unprovable and cost
  is measurable, keep the reflex set small and cost-capped.
- **Burrows collide with civilian labor restriction**, and the bridge collides
  with caravan arrival, which the Quartermaster cares about. Those interlocks
  need documenting, not discovering.
