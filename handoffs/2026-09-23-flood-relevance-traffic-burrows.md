# Handoff: flood relevance, and whether traffic designations and burrows are the shared capability

Date: 2026-09-23. **Researcher stream, READ-ONLY.** No code, no deploy, no
mutation of any kind. You may read the live fort on VM 103 (paused) through
existing read tools, and you must read this install's own DFHack source and
Lua. Output is a dated research file plus this doc's Result section.

Read `CLAUDE.md` first (especially "No armok capabilities", "Tools must be
generalisable", "Research before designing from scratch", and the rule that
never puts an address or hostname in a tracked file), then
`scripts/dfhack/df-overseer-breach.lua` (read its whole header, it is the
honest record of what was already tried and why it failed),
`research/2026-09-12-dfhack-capability-checks.md` §5, `docs/TRAPS.md`,
`memory/dfhack-environment.md`, and `scripts/dfhack/df-overseer-zone.lua`
(the shape a zone-like tool takes here).

## The problem, stated domain-neutrally first

A system must notice a spreading physical hazard early enough to act, on a
map where the hazard's own substance is also present harmlessly and
permanently in many places. Presence is not the signal. Two things make a
reading matter: that it is **rising**, and that it is rising **somewhere the
population actually is or goes**. Other fields own this problem already, and
the project rule says to go and read them before designing: flood warning
systems (gauge networks sited on inhabited floodplains, not on every stream),
building fire and gas detection (detector placement by occupancy and egress
route, not uniform coverage), industrial alarm management (the alarm-flood
literature on why uniform alarming destroys operator trust), and mine water
inrush monitoring. Say what each one actually does about siting and
thresholds, cite it, and say which of it transfers here and which does not.

## Why this brief exists now

`df-overseer-breach.lua` exists and is **inconclusive, covering nothing**.
Its cheap stage-1 gate reads `block.flags.update_liquid`, which was set on
**zero of 26,784 blocks across 11 polls** on a map whose water is fully
settled. That cannot distinguish "DF never sets this flag" from "nothing
changed during the poll". Flood response is therefore covered by nothing,
and breach is among the fastest fort-killers. Everything in that file's
header about the real per-tile signal (`designation[x][y].flow_size` and
`.liquid_type`, source-confirmed two ways against this exact install) still
stands and is good work: the gap is the gate and the relevance filter, not
the tile read.

## The user's hypothesis, which this stream exists to test

The user's framing, 2026-09-23, in their words: if we are designating traffic
zones and burrows, "these could be considered areas worthy of flood
detection". The claim underneath it, which you should treat as a hypothesis
to support or refute from evidence rather than as a conclusion to justify:

- **Traffic designations and burrows are the fort's own machine-readable
  statement of where dwarves are and go.** A liquid reading inside that
  footprint is worth waking someone for; the same reading in an unvisited
  cavern is scenery. That makes the footprint both the relevance filter
  (fixing the noise problem) and the poll scope (fixing the cost problem).
- **The same capability is also the response**, which is why the user thinks
  it balances into logistics: traffic designations reroute pathing away from
  a flooding corridor, and a burrow confines dwarves away from an area
  outright. One designation capability would serve hauling efficiency, flood
  reaction and evacuation.

Test it. It is plausible and it may still be wrong in its details: a fort
with no traffic designations at all (this one) would have an empty footprint,
and a breach's whole danger is that it arrives *from* the unvisited dark.
Say so if that is what you find, and say what the footprint should be
instead or in addition (dug-out tiles, rooms, stockpiles, zones, workshop
tiles, the actual paths between them).

## Questions to answer, in priority order

1. **Is there a working rising-liquid signal on this install at all?** Settle
   the `update_liquid` question: read DFHack and DF-structures source for
   what sets that flag and when, and say whether zero-of-26,784 means "DF
   only sets it while liquid is actively being simulated" or something else.
   If the flag is unusable as a gate, what is the cheapest gate that is not?
   A sampled scan of a bounded footprint is a legitimate answer.
2. **What exactly can be read about traffic designations and burrows?**
   Field names and types on this install, read from source and confirmed
   against the live paused fort through existing read-only tools. Traffic is
   a per-tile designation (high/normal/low/restricted) that feeds pathfinding
   cost, not a zone; burrows are a real object with members and tiles. Get
   both shapes right, and name what is readable versus what is not.
3. **Can they be written, and is writing them within the rules?** A player
   designates traffic and draws burrows by hand, so a tool that does it is
   not an armok capability on its face, but check the tagged-tool inventory
   and `docs/ARMOK-RULINGS.md` and say so explicitly either way. Reading a
   burrow's membership is plainly fine; confining a dwarf to one is a real
   fort action with real consequences, and the user will want that flagged
   as a decision, not slipped in as a detail.
4. **What is the right footprint for flood relevance?** Argue it from the
   evidence in 1 and 2, not from the hypothesis. Include what it costs to
   compute and whether it must be recomputed per poll or cached.
5. **Severity and thresholds.** The existing file compares against a
   session-scoped last-seen baseline so a well stops triggering. Given the
   attention-tier system that now exists (`pause`/`slow`/`record_only`,
   `research/2026-09-23-wildlife-threat-classes.md`) and the five tripwires
   in `docs/AGENT-LOOP.md` §3, say which liquid findings belong in which
   tier, and be honest that any tick-rate number you give is reasoned rather
   than measured unless you actually measure it.
6. **The logistics half, briefly.** What traffic designations actually do to
   hauling and pathing on this version, and whether a traffic tool would pay
   for itself on logistics alone if the flood case never fires. One section,
   not the bulk of the report.

## Rules

- **Read-only, live.** The fort is paused and must stay paused: never
  unpause, never designate, never create or modify a burrow, never write a
  tile. Bound every scan (`docs/TRAPS.md`); no unbounded query against live
  DFHack. Run any scratch script from a scratch path and remove it.
- **Use `bash scripts/vm-ssh.sh df '<cmd>'` for every VM command.** Do not
  write your own ssh wrapper and do not read the address out of `.env`
  yourself: four separate agents have leaked a VM address doing exactly
  that. Read secrets by key only if you ever need one. No address, hostname
  or token in any tracked file, commit message or report.
- **You own** `research/2026-09-23-flood-relevance-and-traffic.md` (new) and
  this handoff's Result section. **Touch nothing else.** Specifically: do
  not edit any `.lua`, `scripts/dfhack/TOOLS.yaml`, `dfmcp/**`, `agents/**`,
  `Working.md`, `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`.
  A concurrent stream owns `df-overseer-workjob.lua` and `TOOLS.yaml`;
  editing either will collide.
- **Unknown is never zero**, and a checked negative is a finding worth as
  much as a positive. Mark every claim verified (with the command or the
  source file and line) or reasoned. The existing breach file is the
  standard to match for honesty: it names its own unmeasured costs.
- Commit after each milestone and extend the Result section as you go. No em
  dashes in prose. **No attribution lines in any commit message**: no
  Co-Authored-By, no "Generated with Claude Code". Use the Write tool for
  scratch scripts rather than long inline shell heredocs.
- Stop and report on any classifier or permission refusal. Do not route
  around it through another session or agent.

## Done means

A dated research file that: settles whether a usable rising-liquid gate
exists on this install; gives the real readable shape of traffic
designations and burrows, verified against live data; answers the user's
hypothesis with a clear supported-or-refuted verdict and the reasoning;
proposes the relevance footprint and the tier mapping; covers the logistics
case in one section; and lists, separately and plainly, everything it could
not verify and what would settle each one. Cross-domain prior art is cited,
not gestured at. No code is written and nothing on the fort has changed.

## Result

<!-- The stream fills this in as it goes. -->
