

## Shelved 2026-09-24: the fort plan, districts as burrows, and the council

Shelved at the user's call ("i think we may be overcomplicating the burrow thing / i really like it. i like the design / but lets file it away as a potential option for later"). Kept whole rather than summarised, because the reasoning is the valuable part and the user wants it available as an option later. The decisions register carries its own rows for the constitution and for the finding that district-as-burrow is this project's own extension rather than an attested player pattern.

**THE FORT PLAN, agreed 2026-09-24, and the user's view that it is possibly
the most important thing.** The gap it fills: every role is a one-shot
`agent exec` with fresh context, so the Architect reasons from nothing on
every wake and cannot be consistent with itself between runs. `proposal-0002`
sited an office by reasoning from scratch and a later proposal would do the
same, with nothing noticing a contradiction. There is no artefact saying where
the spine runs, what each district is for, or what is reserved. That is how
two offices ended up on the surface.

**How it stays compatible with never showing the model a map:** the pattern
already exists in `zone.lua`'s `ranked_water_bodies`, which keeps real
coordinates server-side and hands the model ranks and names. The plan holds
real geometry in the tool layer; the Architect sees names, levels,
adjacencies and capacities, and can reason about "residential, room for twelve
more bedrooms" without a tile.

**Agreed parts.** Districts (named regions with purpose, capacity and current
occupancy). The spine (the main stair and circulation backbone, the single
most irreversible decision in a fort, made once and recorded rather than
emerging from whatever was dug first). Level assignment, **but corrected by
the user**: one purpose per floor is inefficient, integrated floors work
better, so a **district is a volume, not a level**, and levels remain in the
plan only as a constraint layer (aquifer, magma, what is unsafe to dig), never
as purpose assignment. **Districts map onto burrows**, which is DF's own
structure for exactly this, a named region with dwarves assigned to it;
`plotinfo.burrows.list` exists and this fort has **zero**, so the integration
would be real rather than a parallel model we maintain.

**Reservations, agreed mechanism:** a claimed volume in the plan with a
purpose and an owner, enforced as a **tool-level refusal, not a warning**.
`diggable.dig` checks every designation against reservations and refuses one
that crosses a reservation it does not own, because a warning is something an
agent can reason past and a refusal is not, and dig is the least reversible
action in the game. An explicit override exists, requires naming the
reservation and a reason, and is logged as a **plan amendment rather than a
dig**, so the expensive mistake needs a deliberate act and the deliberate act
leaves a record. Cheap first version needs no new primitive: named regions
with capacity, checked before designation.

**Revision number:** the revisioned-knowledge pattern already agreed for
doctrine, applied to space. Proposals cite `plan@rev`, and outcomes are
recorded against that revision, which is the only way a one-shot role can ever
be told no in a way that survives its own death at the end of the run.

**The user's idea: a representative agent per burrow, arguing for it, as a
council.** Solves something real, since space currently goes to whoever asks
first and there is no mechanism for contention at all. **Cost is the
objection:** a measured role run is about five minutes and 8,312 tokens of
tool definitions before it does anything, so six districts arguing every cycle
is half an hour and real money for a debate usually about nothing. **Agreed
shape: advocacy is lazy.** A representative wakes only on contention, when a
proposal would take its reserved space or its capacity is exceeded, which fits
the conductor's existing wake-on-reason model, costs nothing in the common
case, and means an advocate speaking always signals something genuinely at
stake. It also gives the Overseer, already sole writer and arbitrator by
design, a real arbitration job rather than routine approvals.

**Still open:** whether the Architect authors the plan or whether the humans
author the skeleton once (spine, level constraints, district boundaries, the
irreversible decisions) with the Architect reading it and proposing amendments
inside it. The orchestrating session recommends the second for this fort; the
user has not ruled.

**Also named as Architect gaps, agreed but not designed:** a growth horizon
(it optimises for the fort as it is, not as it will be), a defence posture it
must design around without deciding (`chokepoints.find` exists), a depth
strategy, and a feedback loop, since today a proposal is executed or ignored
and the role never learns which.

