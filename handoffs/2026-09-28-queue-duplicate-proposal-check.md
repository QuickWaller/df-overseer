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

**Done, code and tests only, no live call.**

Added a `duplicate_of` field to the `proposal` schema (`dfqueue/schema.py`
`KIND_FIELDS[PROPOSAL]`, plus a stateless "non-empty string when given"
check in `_validate_proposal_fields`) and a pure `near_duplicate_reason
(candidate, existing)` function, same shape as `dfmcp/gotchas_store.py`'s:
checks `summary` first (exact match ignoring case/punctuation, then word-set
Jaccard >= 0.75, then a `difflib.SequenceMatcher` ratio >= 0.85), then falls
back to `rationale`'s own ratio >= 0.85. It reads only `summary`/`rationale`
off the two dicts it's given -- generalisable across every proposal `type`,
never a fixed string list. `type` itself is not compared inside this
function; that's the caller's job (see below), so two unrelated proposals
that happen to share a `type` are never compared just because of it.

`dfqueue/store.py`'s `append()` does the scoping and the write-time
decision, mirroring `gotchas_store.add_entry`'s shape but with the opposite
outcome on a match: never a refusal. A new helper, `_find_duplicate_proposal
(conn, record)`, queries every **still-open** proposal (no ruling, or ruled
`defer` only -- exactly `pending_proposals`'s own definition) of the **same
`type`** (an indexed column, no `json_extract` scan needed), oldest first,
and returns the first one `near_duplicate_reason` flags. When one is found,
`append()` sets `record["duplicate_of"]` to the existing proposal's id
before inserting (so it's persisted, visible in the queue's history and to
`queue.pending`/`queue.overview`) and returns the reason as a transient
`duplicate_reason` key on the dict handed back to the caller only -- never
persisted, so a re-read of the queue never carries it. `dfqueue/render.py`
now renders `<duplicate_of>` in a proposal's XML when present, so the
Overseer sees the relationship when ruling. A caller may also set
`duplicate_of` directly (future use); `append()` then validates it names a
real proposal already in the queue (same two-layer pattern as `ruling`'s own
`proposal_id`) instead of running auto-detection.

`dfmcp/queue_tools.py`: `_propose`'s existing `render.to_xml(written),
written` return already carries `duplicate_of`/`duplicate_reason` through to
the tool's `structuredContent` untouched -- no handler code changes needed
beyond documenting the behaviour in `_propose_description`. `duplicate_of`
is deliberately not in `_PROPOSE_FIELDS`, so a caller cannot smuggle in a
hand-picked duplicate id (tested).

**Why `summary`/`rationale`, not a `target` field**: no proposal type in
`TYPE_VOCAB_BY_ROLE` declares a `target` field in the schema (`dfqueue/
schema.py`'s `KIND_FIELDS[PROPOSAL]` has no such key) -- `summary` is the
closest analogue to a gotcha's `title` (a short human description of the
action) and `rationale` to its `body`, so the comparison uses the fields
that actually exist on every proposal, per the brief's own instruction to
derive the test from the proposal's own declared fields.

Checked against `evals/live/2026-09-25-first-real-conductor-cycle/`'s real
`proposal-0009`/`proposal-0007` pair conceptually (not replayed live): both
were `type=work_order` proposals to queue brewing at the Still with
differently-worded summaries -- exactly the reworded-summary case a new test
(`test_near_duplicate_reason_catches_a_reworded_summary_by_word_overlap`)
exercises via the Jaccard path.

**Test counts** (ambient `python -m pytest dfqueue`, `.venv-dfmcp` for
`dfmcp/tests`):
- `dfqueue`: 160 before -> 178 after (+18: 4 schema-validation tests + 5
  pure `near_duplicate_reason` tests + 9 store-level append/pending/render
  tests).
- `dfmcp/tests`: 695 before -> 698 after (+3: written-not-refused-and-
  reported, unrelated-proposal-not-flagged, `duplicate_of` cannot be passed
  as a propose argument). The known flaky race test
  (`test_concurrent_raw_appends_without_serialization_can_collide`) passed
  in this run.

**Not verified**: no live call against VM 103's real queue database (out of
scope per the brief); the exact real text of `proposal-0007`/`proposal-0009`
was not read from the live queue, only inferred from the register's
description of the incident.

Branch: `agent-a927ab57de6add391` (this worktree's own branch), on top of
`main` at `bc59ae3` (fast-forwarded before starting). Commits: one commit
covering schema/store/render/queue_tools plus their tests, message
`dfqueue: flag near-duplicate proposals instead of refusing them, per
2026-09-28 brief`.
