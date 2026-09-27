# Handoff: generalised duplicate-proposal detection in the queue

Date: 2026-09-28. **Executor, Sonnet, worktree-isolated. Code and tests only. NO deploy, no VM, no live call.**

## Context

The 2026-09-28 live conductor cycle (`evals/live/2026-09-25-first-real-conductor-cycle/README.md`,
"Fifth cycle") found a real gap: the Quartermaster filed `proposal-0009`, a
near-duplicate of the still-open `proposal-0007` from three days earlier (both
proposing to queue brewing directly at the Still), without knowing the earlier
one existed. The Overseer caught it on the merits when ruling, but nothing
stopped the duplicate from being written in the first place. Manager orders
already get this kind of check (`orders.check-duplicate`,
`scripts/dfhack/df-overseer-orders.lua`); the queue's own proposals do not.

`dfmcp/gotchas_store.py` already has exactly this shape for a different kind of
record: `near_duplicate_reason(candidate, existing)` decides whether a new
gotcha duplicates an existing one, and the write path
(`dfmcp/gotchas_store.py` around line 510-538) refuses to write a near-duplicate,
citing the existing record's id and status. Read that function and its call site
first; this fix should follow the same shape for proposals, not invent a new one.

## Fix

Add a duplicate check to the proposal write path in `dfqueue/` (read `dfqueue/
schema.py`, `dfqueue/store.py`, and however `dfmcp/queue_tools.py` calls into
them for `queue.propose`). Before writing a new proposal, check it against
**other proposals that are still open** (no ruling yet, or ruled `defer`) for a
near-duplicate: same `type` field and enough overlap in `summary`/`target`
fields to be the same underlying action (generalisable across proposal types,
not hardcoded to "brewing" or "room_siting" — decide the similarity test from
the proposal's own declared fields, the same way `gotchas_store.py`'s check
works from a record's own `tool`/`title` fields, not from a fixed string list).

**Behaviour on a match: do not silently refuse.** Unlike gotchas (which are
advisory notes where a silent refuse is fine), a rejected or silently dropped
proposal write could hide a role's real intent from the Overseer. Instead, the
new proposal should still be written, but flagged with a `duplicate_of` field
naming the existing open proposal's id, so the Overseer's ruling (and the
history) can see the relationship plainly. Add this field to the schema
(`dfqueue/schema.py`) with write-time validation (it must name a real existing
proposal id, or be absent). Report the check's own reasoning in the tool's
result (which existing proposal, why it was judged similar) so a caller who
disagrees can see why.

## Rules

- `git merge --ff-only main` first; this brief is committed on main.
- Touched surfaces: `dfqueue/schema.py`, `dfqueue/store.py`, `dfmcp/queue_tools.py`
  and their tests. Do NOT touch `scripts/dfhack/df-overseer-building.lua`,
  `TOOLS.yaml`, `Working.md`, `decisions/`, `memory/`, `handoffs/INDEX.md` (a
  separate stream owns the building-tool fix).
- `python -m pytest dfqueue` and `dfmcp/tests` in `.venv-dfmcp`; report counts
  before and after. No live call.
- No em dashes in prose. **No attribution lines in commit messages.**
- Commit after the fix. Do not push. Stop and report on any permission refusal.
- Fill in the Result section: what changed, the similarity test you chose and
  why, test counts, anything you could not verify.

## Result

(pending)
