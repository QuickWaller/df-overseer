# Stream: the proposal queue (write-time validated), step 1 of the live-stream feed

**Written** 2026-09-14. **Status:** dispatched. **User go-ahead:** "go ahead",
in reply to the plan below. **Local code and tests only**: no MCP exposure, no
deploy, no VM.

## Why

The user wants a scrolling feed beside the live game stream showing advisor
proposals and Overseer rulings (`decisions/DECISIONS.md` 2026-09-14, "Live-stream
side panel"). Nothing produces that feed yet. `docs/AGENT-ARCHITECTURE.md` §4
already specifies the channel: **one append-only queue per fort, written by
tool calls with typed fields, validated at write time, where a malformed
proposal is refused.** Architect run #2
(`evals/live/2026-09-14-architect-second-charter/`) showed why this has to be
enforced in code: told to use the record format, the model wrote prose instead.

Build order: (1) **this stream**, (2) a publisher of allowlisted fields
(`role`, `type`, `public_rationale`, decision, priority; the user waived §8's
30-60s delay for now), (3) the stream page. Steps 2 and 3 are not in scope.

## Read first

1. `docs/AGENT-ARCHITECTURE.md` §4 ("The queue is the channel", "Writes are
   tool calls; reads are XML", the proposal record and its four fields) and
   the §9/§10 references to the queue as write-ahead log and to hit rates by
   `type`.
2. `learning/predictions/` (`schema.py`, `store.py`, `selftest.py`,
   `README.md`): the **existing** prediction record, its write-time
   validation, the ledger-backed signal check, and the append-only JSONL
   store pattern. Reuse it; do not write a second prediction validator.
3. `learning/ledger/schema.py`: the vocabulary and `unrecorded` conventions.
   Match that house style.
4. `agents/ROSTER.yaml` and `agents/*/role.md`.
5. `dfmcp/roles.py` around its comment on non-DFHack tools ("the queue, the
   sentry endpoint"). Read only, to know what the later `propose` tool will
   plug into. Don't change it.

## What to build

A package **`dfqueue/`** at the repo root. **Not `queue/`**: that shadows
Python's stdlib `queue` for anything run from the repo root, which is the same
trap `dfmcp/` is named to avoid. Say so in its README.

1. **Schema** (`dfqueue/schema.py`), following `learning/`'s style:
   - **Record kinds:** `proposal` (an advisor), `pass` (an advisor
     explicitly declining this cycle, with a reason, since `role.md` makes
     that a valid outcome), and `ruling` (the Overseer only: `accept`,
     `reject` or `defer`, plus `proposal_id`, `reason` and `public_rationale`).
     No `plan` record yet. Note it as the next kind in the README.
   - **Proposal fields** exactly as §4's record: `id`, `role`, `cycle`,
     `snapshot`, `type`, `summary`, `rationale`, `prediction`, `cost`
     (`estimate` > 0, `unit` from a small vocabulary starting
     `dwarf_ticks`), `suggested_priority` (1-7), `preconditions` (a list of
     `{landmark|area, state}`), `public_rationale`. Every text field must be
     non-empty.
   - **The closed `type` vocabulary**, drafted from the architect's `role.md`
     "Owns" and to be revised as roles are added: `room_siting`,
     `workshop_siting`, `stockpile_siting`, `corridor`, `smoothing`,
     `dig_order`. Put it in one table **keyed by role**, so a role can only
     use its own types. The consultant answers questions and doesn't propose,
     so give it no proposal types, and state that reasoning in a comment.
   - **Role checks**: a record's `role` must be an enabled role in
     `agents/ROSTER.yaml`; only the roster's `sole_writer` may write a
     `ruling`; a ruling's `proposal_id` must refer to an existing proposal in
     the same queue.
   - **`prediction`**: build and validate it **through
     `learning/predictions/`'s own validation**, not a copy. If that
     validator refuses spatial signals such as
     `landmarks.<name>.exit_to_<name>.distance_tiles` (run #1's prediction),
     **do not loosen it**. Report exactly which signals it currently accepts,
     because that decides whether any architect proposal can pass today.
   - **Coordinates**: refuse any text field matching a raw-coordinate pattern
     (`x=12`, a bracketed or parenthesised numeric triple, `z=-3`), in line
     with design commitment #1. Keep the regex conservative, and test that
     phrases like "5 tiles SE of Embark Site", "3x3", "level -1" and
     "priority 4" pass.
2. **Store** (`dfqueue/store.py`): append-only JSONL, one file per fort,
   default path `dfqueue/<fort>.jsonl` from the roster's `fort`; tests use a
   temp path. `append(record)` validates and **refuses a malformed record
   with every error listed**, writing nothing. It assigns `id` and a UTC
   `ts` if absent. Also `load()`. Match `learning/predictions/store.py`.
   Don't commit a real queue file.
3. **Rendering** (`dfqueue/render.py`): `to_xml(record)`, the prompt form
   from §4, with values XML-escaped; and `public_view(record)`, which returns
   **only** `role`, `type`, `public_rationale`, the ruling's decision (for a
   ruling) and `suggested_priority`, plus `id`, `ts` and `kind` so the feed
   can order and thread items. Step 2 publishes from this function, so its
   allowlist test matters: add a field to a record and prove it never
   appears.
4. **Tests** (`dfqueue/tests/`, pytest):
   - a valid proposal, pass and ruling round-trip through append, load and
     `to_xml`;
   - each refusal:
     - unknown kind or field;
     - missing or empty required field;
     - `type` not in the role's vocabulary;
     - consultant proposal;
     - non-Overseer ruling;
     - dangling `proposal_id`;
     - priority out of range;
     - cost ≤ 0;
     - coordinate in the rationale;
     - bad prediction.
   - the file is unchanged after any refusal;
   - the public-view allowlist.

   Include **run #1's real proposal**
   (`evals/live/2026-09-14-architect-first-charter/run.json`, the `final`
   field's XML) as a fixture, parsed into a record. Report whether it passes,
   and if not, exactly which checks refuse it.
5. **README** (`dfqueue/README.md`): what it is, the record kinds, the
   vocabulary and how to extend it, the public-view allowlist, and what is
   deliberately not here yet (`plan` records, the `propose` MCP tool, the
   publisher, the feed page).

## Hard lines

- No MCP exposure, no change to `dfmcp/`, no deploy, no VM, no model call.
- Don't change `learning/` behaviour. If reusing it needs a small, genuinely
  additive helper, stop and report it instead of making the change.
- No commits (the orchestrator reviews and commits). Don't edit
  `Working.md`, `decisions/`, `memory/`, `CLAUDE.md`, `docs/` or other
  handoff docs. Add a Result section here and your row in `handoffs/INDEX.md`.

## Report

Executor shape, plus:
- files created;
- the test count, and that the existing suite still passes (ambient
  `python -m pytest`: 127 passed, 1 skipped before; the venv
  `.venv-dfmcp` for `dfmcp/tests` if it matters);
- which prediction signals are currently accepted;
- whether run #1's proposal passes and why;
- anything this brief got wrong.
