# Chronicler

**Kind:** advisor (writes prose, decides nothing). **NOT ENABLED.**
Blocked on tools. No `tools.yaml` or `model.yaml` yet.

## Would own

- **The history.** The fortress's story, written for humans, in the register of
  a chronicle rather than a changelog.
- **The public-facing output.** `docs/PURPOSE.md`'s stated long-term goal is "a
  history worth reading", and this is the role that produces it. It is also the
  cheapest role in the roster to run.

## Would NOT own

- **Any decision whatsoever.** It observes and narrates. It does not propose
  work, and it must never be in a position where the story it wants to tell
  could influence what the fort does.

## Why it is not enabled

`research/2026-09-12-write-conflict-matrix.md`: **no tool in this repo writes a
chronicle entry anywhere.** The nearest analogue, `df-overseer-diff`'s event log,
is deliberately ephemeral and session-scoped, which is precisely the opposite of
what a chronicle needs.

Note that unlike the Quartermaster and Marshal, this role is not blocked on
anything hard. `docs/PURPOSE.md`'s scope table already lists "Chronicle
(markdown, source of truth)" as **in scope for this repo**. It was always
intended and simply never built, because effort went to perception and infra.
Of the three unenabled roles, this is the cheapest to unblock.

## Notes for whoever builds this

- **Read `docs/MEMORY-ARCHITECTURE.md` first.** It may already specify the
  chronicle's storage shape, and this role should not invent a second one.
- **The chronicle is durable; the event log is not.** Do not build it on top of
  a `_G` table that dies with the DF process.
- **It is a separate record type from the queue.** The queue is what was decided
  and why, machine-readable, for audit. The chronicle is what happened, for
  people. Do not conflate them (§10's four record types).
- **A cheap model is correct here**, and the quality bar is prose, not judgment.
