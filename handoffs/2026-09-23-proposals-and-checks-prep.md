# Handoff: what a proposal and a check should actually be, now that the loop has run

Date: 2026-09-23. **Researcher. Read-only. No code, no `TOOLS.yaml`, no
deploy, no VM mutation.** The fort is paused with a confirmed quicksave and
stays paused.

Read `CLAUDE.md` first, then `docs/AGENT-ARCHITECTURE.md` (especially §4 and
principle 8), `docs/AGENT-LOOP.md`, `dfqueue/README.md`, and the three live
run records in `evals/live/2026-09-23-*/`.

## Why now

The user parked the proposals-and-checks design conversation deliberately,
saying it should wait until the tool picture was clear. It is clear now, and
more than that, the loop has actually closed: on 2026-09-23 a tool queued a
real direct job, the fort ran three bounded windows unattended, and a Chair
building that had been waiting completed. We would now be designing against
something that has happened rather than something imagined.

This stream does not design the system. It assembles the evidence the design
conversation needs, honestly, including the parts that argue against the
design we already half-believe. The user makes the call afterwards.

## The problem, stated neutrally

An autonomous agent proposes an action. Something must decide whether the
action is allowed, whether it worked, and what to conclude when it did not.
This is not a Dwarf Fortress problem. Per this repo's standing rule, state it
domain-neutrally first, ask which other fields already own it, and read those
before designing. Prior art worth checking includes, at least: database
transactions and their preconditions and postconditions, design by contract,
control theory's setpoint-and-feedback loop, aviation checklists and their
challenge-response discipline, change management's plan/verify/rollback, and
property-based testing's notion of an invariant that must hold regardless of
input. Take what fits and say plainly what does not.

## Questions, in priority order

1. **What has a proposal actually been, so far?** `proposal-0001` is the only
   proposal any role has ever written for real, and it was voided rather than
   graded because its 1200-tick prediction window elapses in well under a
   minute at the fort's 100 FPS cap. Read it and the grader. What did its
   shape get right, and what did the void expose that was structural rather
   than bad luck?
2. **What can a check actually read?** This is the question the tool picture
   was blocking. Go through `scripts/dfhack/TOOLS.yaml` and work out what
   classes of postcondition are genuinely checkable with the tools that exist
   today: existence and state of a building, a job, an order, an item in
   stock, a zone, a unit's vitals, a tripwire's state. Be concrete and be
   honest about the gaps. A check that cannot be evaluated is worse than no
   check, because it reads as a guarantee.
3. **What did the three live runs show about predictions?** The Chair run is
   the useful one: a direct job ran to completion and the building claimed the
   item, while four manager orders sat unchanged through the whole run. If a
   proposal had predicted "order id 3 goes active", it would have been wrong,
   and the fort would still have got its Chair by another route. What does
   that say about predicting mechanisms versus predicting outcomes?
4. **What is the unit of time a prediction can be made in?** Ticks, fort
   time, windows, or events. The 100 FPS cap means wall-clock is meaningless
   and the void of `proposal-0001` proves it. The bounded-window pattern the
   two unattended runs used is the only time structure that has actually held
   up in practice. Does a prediction window want to be a number of windows?
5. **Who checks, and when?** The roles are Overseer (sole writer), Architect,
   Quartermaster, Consultant, with the conductor holding the clock. Reason
   about whether checking belongs to the writer, to a peer, or to the
   conductor's code, and what each choice costs. Note where the answer is
   forced by principle 8, that the allowlist is the real boundary.
6. **What should happen when a check fails?** Enumerate the options that have
   any support in the prior art you read, from "record and continue" through
   to "revert", and say which are even possible here. Note explicitly that
   reverting a fort action is often not possible at all, and that the
   quicksave is the only real rollback this project has.

## What to produce

`research/2026-09-23-proposals-and-checks.md`, and that file only. Long,
cited, honest about what could not be verified, in the style of the two
existing research specs. Lead with a verdict paragraph the way
`research/2026-09-23-flood-relevance-and-traffic.md` does, then the evidence.

Where you make a recommendation, mark it as a recommendation and give the
strongest argument against it that you found. Where the evidence is thin, say
the evidence is thin. Unknown is never zero.

## Rules

- **Read-only, and the repo is the main source.** You may read live state
  through the existing tools if a question genuinely needs it, but every query
  must be bounded, nothing may be mutated, the fort must not be unpaused, and
  you must quote the command and its output. Never run an unbounded query
  against live DFHack. If in doubt, do not read live at all: almost nothing
  here needs it.
- Use `bash scripts/vm-ssh.sh df '<cmd>'` for any VM command. Do not write
  your own ssh wrapper and do not read an address out of `.env`: four agents
  have leaked a VM address doing exactly that. No address, hostname or token
  in any tracked file, commit message or report.
- `git merge --ff-only main` first.
- You own that one research file and this doc's Result section, nothing else.
  Not `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`; collect owed register lines in your Result.
- No em dashes in prose. **No attribution lines in any commit message**: no
  Co-Authored-By, no "Generated with Claude Code".
- Stop and report on any permission or classifier refusal. Never route around
  one through another agent or session.

## Done means

The research file exists, answers the six questions or says why one cannot be
answered yet, cites prior art from outside this domain, and ends with a short
list of the decisions the user actually has to make, phrased as choices rather
than as a recommendation dressed up as a summary.

## Result

**Status: done.** `research/2026-09-23-proposals-and-checks.md` written,
answering all six questions, citing prior art (design by contract, database
transactions/ACID, control theory setpoint-feedback, aviation
challenge-response, change management plan/verify/rollback, property-based
testing invariants) and ending with five decisions phrased as choices, each
with a recommendation marked as such and its strongest counter-argument.
Read-only throughout: no file on VM 103 was touched, the fort was never
queried live and never unpaused. Every question was answerable from
repo-internal evidence already recorded (the two real proposals, the three
2026-09-23 live run READMEs, `scripts/dfhack/TOOLS.yaml`,
`learning/live_signals.py`, `dfqueue/`, `agents/*/role.md`), so no live
DFHack call was made and `scripts/vm-ssh.sh` was never invoked.

**Verdict, one line:** the project has already independently built two
different classical check shapes (one-shot postcondition predictions via
`dfqueue`, continuous invariants via tripwires) without naming either; the
friction so far (the `proposal-0001` void, the Chair run's mechanism-vs-
outcome finding) comes from anchoring or shape mismatches within a sound
pair of mechanisms, not from either mechanism being wrong.

**Two things worth flagging for whoever picks up the design conversation,
not built or decided here:**

- The `dfqueue.prediction` closed signal vocabulary
  (`learning/live_signals.py`) is much narrower than what is actually
  readable through `scripts/dfhack/TOOLS.yaml` (ten signals versus building
  state, job origin, order status, zone ownership, all readable but not
  gradeable as a `prediction.signal` today). Any design that wants to
  predict outcomes in the sense §3 recommends will need this registry
  extended, which is a schema change this stream did not make (read-only).
- `queue.escalate` has a complete mechanical design and has never fired on
  a real run; every stop condition hit so far has been a tripwire pause or
  an executor's own explicit stop condition instead. Worth a deliberate
  live exercise before the design leans on it as the "check failed, wake a
  human" path.

No register lines are owed beyond what the orchestrating session already
tracks in `Working.md`/`decisions/DECISIONS.md`: this stream touched only
the one research file and this doc's own Result section, per its own
scope line.
