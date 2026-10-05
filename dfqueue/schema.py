"""dfqueue record schema: `proposal`, `pass`, `ruling`, `executed`, `ask`,
`answer`, `escalation`, `project`, `observation`, `amend`, `abandon`,
validated at write time.

Implements `docs/AGENT-ARCHITECTURE.md` §4, "Writes are tool calls; reads are
XML": **a specialist cannot emit prose into the queue.** It calls
`propose(...)` (or, for the Overseer, rules) with typed fields, validated
here, and a malformed record is refused with every error listed rather than
silently accepted or silently trimmed.

Nine record kinds, per §4, `docs/AGENT-LOOP.md` items 4/7, `agents/*/role.md`,
and (for `project`/`observation`) `research/2026-09-28-job-dependency-graph.md`:

- **`proposal`** — an advisor's proposed action. The §4 record, field for
  field: `id`, `role`, `cycle`, `snapshot`, `type`, `summary`, `rationale`,
  `prediction`, `cost`, `suggested_priority`, `preconditions`,
  `public_rationale`.
- **`pass`** — an advisor explicitly declining to propose this cycle, with a
  `reason`. `role.md` (architect) makes this a valid, even encouraged,
  outcome: "Say when you would rather do nothing... A cycle with no proposal
  is a valid cycle." Silently doing nothing would erase that from the audit
  log; `pass` keeps it visible.
- **`ruling`** — the Overseer's decision on one proposal: `accept`, `reject`
  or `defer`, plus `proposal_id`, `reason` and `public_rationale`. Only the
  roster's `sole_writer` may write one (§7: single writer; §3: "Specialists
  propose, the Overseer decides").
- **`executed`** — the Overseer's record that an accepted ruling was carried
  out: `ruling_id`, `actions` (the tool ids called and each one's outcome,
  success or failure — a failed execution is a valid record), `notes`.
  Added `docs/AGENT-LOOP.md` item 4, closing the gap that let
  `proposal-0001`'s prediction window elapse before anything could act on
  it: **a proposal's prediction window starts at the first `executed`
  record referencing its ruling, not at the proposal's own write time.**
  Only the roster's `sole_writer` may write one, same restriction as
  `ruling`. See `dfqueue/store.py`, "Execution arms the prediction".
- **`ask`** — a question to the Consultant: `question`, optional
  `proposal_id`. Any of `architect`, `quartermaster` or `overseer` may write
  one (`docs/AGENT-ARCHITECTURE.md` §4, the 2026-09-15 ask exception and the
  2026-09-17 fact-check exception). An `ask` from the Overseer that names a
  `proposal_id` **is** a fact-check: `dfqueue/store.py` refuses a `ruling`
  on that proposal while the fact-check is open (no `answer` yet).
- **`answer`** — the Consultant's answer to one open `ask`: `ask_id`,
  `answer`. Only `consultant` may write one, and only once per `ask` (one
  ask, one answer, no threads). Answers are hypotheses: nothing here
  overrides a graded prediction.
- **`escalation`** — the Overseer alerting the human: `reason`. Added
  `handoffs/2026-09-22-loop-conductor-fixes.md` item 3: a queue record via a
  real tool call (`queue.escalate`, `dfmcp/queue_tools.py`), never free text
  in the Overseer's own final answer, so `conductor/cycle.py` can detect it
  mechanically (against openclaw's own `toolSummary.tools`, never by parsing
  prose) and leave the fort paused. Only the roster's `sole_writer` may
  write one, same restriction as `ruling`/`executed` -- the Overseer is the
  only role with an Escalation section in its charter at all.
- **`project`** -- §9's own write-ahead-log record, "writes its ordered plan
  to the queue before executing" (`docs/AGENT-ARCHITECTURE.md` §9), added
  `handoffs/2026-09-28-dfqueue-project-step-schema.md`: `from_ruling`,
  `objective_id`, `template`, `summary`, `because`, `steps`. Instantiated
  from exactly one accepted ruling (a second `project` for the same
  `from_ruling` is refused); a `steps` block omitted or empty is normalised
  (`normalize_project` below) into one implicit step wrapping the whole
  ruling, so every proposal type keeps working unchanged. Only the roster's
  `sole_writer` may write one, same restriction as `ruling`/`executed`/
  `escalation` -- the design's own rule that the Overseer's ruling
  instantiates the project. Reachable over MCP as `queue.project`
  (write) and `queue.project_status` (read), `dfmcp/queue_tools.py`
  (`handoffs/2026-09-30-project-mcp-tools.md`).
- **`observation`** -- code's own view of the world, one reconcile pass at
  one game tick: `project_id`, `step_id`, `game_tick`, `results` (each a
  `target`/`status`/`reason`, `status` one of `consistent`/`contradicted`/
  `not_observable`). Written only by the `conductor` role, never a model
  (`OBSERVATION_ROLE` below) -- the reconciler that would write these is out
  of scope for `handoffs/2026-09-30-project-mcp-tools.md`; no MCP tool
  exposes a write path for it yet.
- **`amend`** -- `research/2026-09-30-goal-tree-red-team.md` F-3: a new
  numbered plan version of an already-accepted project, written by the
  Overseer only. `project_id` names the original project; `steps` is the
  FULL new step list this version replaces the previous one with (never a
  diff); `replaces`/`adds`/`drops` are declarative bookkeeping naming the
  previous version's step ids this version changes, adds or removes.
  Nothing already written is ever overwritten -- the original `project`
  record and every earlier `amend` stay readable, and a step already
  executed keeps its own `executed` records regardless of which version
  named it. `queue.project_status` reads the LATEST version's `steps` and
  reports its version number.
- **`abandon`** -- same F-3. Marks an already-accepted project (and its
  still-open steps) abandoned with a required `reason`, written by the
  Overseer only. Executed history is untouched; `queue.project_status`
  reports `abandoned` status once one exists for a project, alongside the
  reason.

See `dfqueue/README.md`.

## `prediction.signal` must be a live signal, not a ledger field

A proposal's `prediction.signal` is validated against
**`learning.live_signals`'s** closed registry of mid-fort signals
(`handoffs/2026-09-15-live-signals-sqlite.md`), never against
`learning/ledger/schema.py`'s `FORT_FIELDS`. `op` is checked against
`learning.predictions.schema.PREDICATE_OPS` (the same small closed
vocabulary predictions use) and `value` against the signal's own declared
type; `learning.predictions.schema.validate()` itself is not called here —
this module builds no `learning.predictions` row at all, because a
`dfqueue` proposal's prediction is graded against a live SQLite ledger
(`dfqueue/store.py`, `dfqueue/grade.py`), not the fort ledger.

**A ledger-rooted (end-of-fort) signal is refused, on purpose, with a
message pointing at the right module.** `design.entrance_count`,
`outcome.status` and the like are real, gradeable ledger fields — just not
ones a *proposal* may predict against: those are fort-level claims, and
`learning/predictions/` is where they belong. `dfqueue` detects this case
specifically (via `learning.ledger.store.field_source`) so the refusal reads
as "wrong module for this claim," not as an unexplained typo.

## Coordinates

Design commitment #1 (`docs/PURPOSE.md`): the model is never shown a map, and
coordinates exist only as a code-only field. So every free-text field here
(`summary`, `rationale`, `public_rationale`, `reason`) is scanned for a
raw-coordinate pattern and refused if one appears — a specialist that leaks
`x=12` or `(4, 9, -2)` into its rationale has broken the same commitment as
one shown a rendered map, just later in the pipeline. The regex is
deliberately conservative (it must not flag "5 tiles SE of Embark Site",
"3x3", "level -1" or "priority 4"): a denylist that also catches ordinary
prose would train advisors to write around it rather than to keep using
named landmarks and relative directions (`docs/PURPOSE.md` commitment #3).
"""

from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache
from pathlib import Path

import yaml

from dfmcp.registry import load_registry
from learning import live_signals
from learning.ledger.store import field_source as ledger_field_source
from learning.predictions.schema import PREDICATE_OPS, PRESENCE_OPS

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parent.parent
ROSTER_PATH = REPO_ROOT / "agents" / "ROSTER.yaml"
#: `handoffs/2026-10-02-queue-display-fields.md`: public text for a closed
#: code vocabulary (today just `hold_codes`), one data entry per code, no
#: new code to add one -- the same "one data entry, no new code" rule
#: `tools-must-be-generalisable` applies to tools.
PUBLIC_TEXT_PATH = REPO_ROOT / "dfqueue" / "public_text.yaml"

# ---- record kinds -----------------------------------------------------------

PROPOSAL, PASS, RULING = "proposal", "pass", "ruling"
EXECUTED, ASK, ANSWER = "executed", "ask", "answer"
#: Added handoffs/2026-09-22-loop-conductor-fixes.md item 3.
ESCALATION = "escalation"
#: Added handoffs/2026-09-28-dfqueue-project-step-schema.md, the missing
#: `plan` record `docs/AGENT-ARCHITECTURE.md` §9 and this module's own
#: docstring (above) said was absent. `PROJECT` is the Overseer's ordered
#: plan, written once per accepted ruling, same write-authority restriction
#: as `RULING`/`EXECUTED`/`ESCALATION` (§9: "writes its ordered plan to the
#: queue before executing"). `OBSERVATION` is code's own view of the world,
#: written only by the `conductor` role (never a model), see
#: `OBSERVATION_ROLE` below.
PROJECT, OBSERVATION = "project", "observation"
#: Added handoffs/2026-10-01-queue-bugs-and-amend.md
#: (research/2026-09-30-goal-tree-red-team.md F-3: "nothing can carry a
#: change to an accepted project"). `amend` writes a new numbered plan
#: version of an accepted project's steps -- nothing already written is
#: overwritten, the old version stays readable, and any step already
#: executed keeps its own records regardless of which version named it.
#: `abandon` marks an accepted project (and its still-open steps) abandoned
#: with a reason, leaving executed history untouched. Both restricted to
#: the roster's sole_writer, same rule as RULING/EXECUTED/ESCALATION/PROJECT.
AMEND, ABANDON = "amend", "abandon"
#: Added handoffs/2026-10-05-stage-2a.md (docs/CONDUCTOR-EXECUTION.md 6.1):
#: the executor's record that a project, a ruling or a pending proposal is
#: closed, with an outcome and a reason. Written only by the roster's
#: `executor`.
CLOSE = "close"
KINDS = (
    PROPOSAL, PASS, RULING, EXECUTED, ASK, ANSWER, ESCALATION, PROJECT,
    OBSERVATION, AMEND, ABANDON, CLOSE,
)

#: A `close` record's `outcome` (docs/CONDUCTOR-EXECUTION.md 6.1).
CLOSE_COMPLETED, CLOSE_NOT_DONE = "completed", "not_done"
CLOSE_ABANDONED, CLOSE_SUPERSEDED = "abandoned", "superseded"
CLOSE_OUTCOMES = (CLOSE_COMPLETED, CLOSE_NOT_DONE, CLOSE_ABANDONED, CLOSE_SUPERSEDED)
#: A `close` names exactly one of these.
CLOSE_TARGET_FIELDS = ("project_id", "proposal_id", "ruling_id")

# ---- ruling decisions ---------------------------------------------------------

ACCEPT, REJECT, DEFER = "accept", "reject", "defer"
RULING_DECISIONS = (ACCEPT, REJECT, DEFER)

# ---- execution action outcomes -------------------------------------------------

SUCCESS, FAILURE = "success", "failure"
EXECUTION_OUTCOMES = (SUCCESS, FAILURE)

# ---- who may write an `ask` --------------------------------------------------
#
# `docs/AGENT-ARCHITECTURE.md` §4: "any advisor may ask the Consultant"
# (2026-09-15) plus "the Overseer may hand a proposal to the Consultant for
# fact-checking before ruling" (2026-09-17). The Consultant itself never
# asks (it answers), and a disabled role has no business writing anything.
ASK_ROLES = ("architect", "quartermaster", "overseer")

#: Only the Consultant may answer. Distinct from `sole_writer()`, which
#: names the Overseer -- this is a second, independent single-role
#: restriction, not the same one reused.
ANSWER_ROLE = "consultant"

#: `observation` is written only by code, never a model (design §4.4:
#: "written only by code, the conductor role, never by a model"). Same
#: single-role-restriction shape as `ANSWER_ROLE`, distinct from
#: `sole_writer()` -- the conductor is `kind: system` in `agents/ROSTER.yaml`,
#: not the sole_writer (the overseer). This is the mechanical enforcement the
#: handoff asked for: a role field is still just a string an MCP token maps
#: to, so this check is the schema-layer half of "never a model-authored
#: field"; the other half is that no model ever holds the conductor's own
#: MCP token (agents/ROSTER.yaml's own comment on the conductor role).
OBSERVATION_ROLE = "conductor"

# ---- project step vocabulary --------------------------------------------------
#
# `research/2026-09-28-job-dependency-graph.md` §4.1-4.2.

#: A step's `trigger`: `all_success` (default) requires every `requires`
#: step to have finished with every target `done`; `all_done` (design
#: §2.2's one kept Airflow trigger rule) relaxes that to "finished, with
#: any outcome" -- "mine the vein" can end with some tiles unmineable and
#: the wall step should still run on the ones that were.
TRIGGER_ALL_SUCCESS, TRIGGER_ALL_DONE = "all_success", "all_done"
TRIGGERS = (TRIGGER_ALL_SUCCESS, TRIGGER_ALL_DONE)

#: The literal sentinel a step's `guards` field may hold instead of a list:
#: "use this tool's own default guard set, no extras" (design §4.1's
#: `guards: default`). A step may otherwise only ADD named guards from the
#: vocabulary on top of the tool's defaults, never remove one (design §6,
#: Architect row: "Cannot remove a default guard").
GUARDS_DEFAULT = "default"

#: Target-level state inside a step (design §4.4's table). `waiting`/`ready`
#: are structural (derived from `requires`, never written by a record
#: directly); `held`/`issued`/`done`/`failed`/`abandoned` are the states an
#: `executed` action's `target_state` may report for a target it names
#: (see `_validate_action` below). This is the closed vocabulary
#: `store.py`'s target-state fold (the `predictions`-style materialised
#: table, design §4.5) is built from.
WAITING, READY, HELD, ISSUED, DONE, FAILED, ABANDONED = (
    "waiting", "ready", "held", "issued", "done", "failed", "abandoned",
)
TARGET_STATES = (WAITING, READY, HELD, ISSUED, DONE, FAILED, ABANDONED)
#: States an `executed` action may itself assert for a target it names.
#: `waiting`/`ready` are never asserted by a record -- they are computed
#: from a step's own `requires` graph at project-creation time.
ACTION_TARGET_STATES = (HELD, ISSUED, DONE, FAILED, ABANDONED)

#: An `observation`'s three-valued read of the world (design §2.3/§4.4,
#: Kubernetes' condition `Status` "True/False/Unknown" adopted by name for
#: this domain): `consistent` (the world matches recorded state),
#: `contradicted` (it does not -- drift, including a rolled-back world),
#: `not_observable` (a read failed or the fact is outside what a player-
#: visible read can determine; never defaults to `consistent`).
OBS_CONSISTENT, OBS_CONTRADICTED, OBS_NOT_OBSERVABLE = (
    "consistent", "contradicted", "not_observable",
)
OBSERVATION_STATUSES = (OBS_CONSISTENT, OBS_CONTRADICTED, OBS_NOT_OBSERVABLE)

# ---- cost unit vocabulary, small and starting here ---------------------------

DWARF_TICKS = "dwarf_ticks"
COST_UNITS = (DWARF_TICKS,)

# ---- public display fields (handoffs/2026-10-02-queue-display-fields.md) -----
#
# The stream page board (`handoffs/2026-10-02-stream-board.md`,
# `research/2026-10-01-stream-page-design.md` §3.3 items 6/7) needs fields
# the queue did not record before: a project's public title and one-line
# rationale, an urgency, a short label per step, and a closed hold-code
# vocabulary for a held target. All optional -- an old record written before
# this stream stays valid unchanged.

#: `urgency` on `project`: `high` (lives or the fort at risk), `elevated`
#: (blocks other work, or a need running short), `normal` (everything else)
#: -- `agents/overseer/role.md` states the same three in those words.
URGENCY_NORMAL, URGENCY_ELEVATED, URGENCY_HIGH = "normal", "elevated", "high"
URGENCIES = (URGENCY_NORMAL, URGENCY_ELEVATED, URGENCY_HIGH)

#: Length limits for the new public fields (handoff's own numbers, chosen
#: for the stream board's card and job-graph layout -- `public_title` is a
#: card title, `public_rationale` is "one or two sentences", a step `label`
#: is "short and imperative", e.g. "Smooth walls", "Place bed").
PUBLIC_TITLE_MAX = 60
PUBLIC_RATIONALE_MAX = 300
STEP_LABEL_MAX = 24

# ---- the closed `type` vocabulary, keyed by role -----------------------------
#
# Drafted from each enabled role's `role.md` "Owns" section, one closed
# vocabulary per role rather than one global one, per §10: "This is why
# `type` must come from a closed vocabulary. Bespoke proposal types never
# accumulate enough samples for a rate." A role that could use another
# role's type would let e.g. an architect's `military_posture` proposals
# pollute the Marshal's (someday) hit-rate stats with samples the Marshal
# never produced. Revise this table as roles are added or their charters
# change; it is data, not policy, so it lives here rather than being derived
# from `role.md` prose at runtime.

ROOM_SITING = "room_siting"
WORKSHOP_SITING = "workshop_siting"
STOCKPILE_SITING = "stockpile_siting"
CORRIDOR = "corridor"
SMOOTHING = "smoothing"
DIG_ORDER = "dig_order"

#: agents/architect/role.md "Owns": "Rooms, workshops, stockpile siting,
#: corridors, smoothing" plus "Dig order."
ARCHITECT_TYPES = (
    ROOM_SITING, WORKSHOP_SITING, STOCKPILE_SITING, CORRIDOR, SMOOTHING,
    DIG_ORDER,
)

WORK_ORDER = "work_order"
CROP_PLAN = "crop_plan"
STOCK_TARGET = "stock_target"

#: `docs/AGENT-LOOP.md` item 5 (`handoffs/2026-09-22-loop-queue-quartermaster.md`
#: "Why", item 5): the Quartermaster's closed vocabulary for the MVP.
#: `work_order` -- a manager order or a direct workshop job, standing repeat
#: orders included. `crop_plan` -- what a farm plot grows, per season.
#: `stock_target` -- a par level or cover-day target for a named item class
#: (`docs/PRODUCTION-MODEL.md` §10). Deliberately NOT included: a labor
#: proposal (`set_labor` still races `autolabor`, unfixed).
QUARTERMASTER_TYPES = (WORK_ORDER, CROP_PLAN, STOCK_TARGET)

TYPE_VOCAB_BY_ROLE: dict[str, tuple[str, ...]] = {
    "architect": ARCHITECT_TYPES,
    # The Overseer arbitrates proposals and writes rulings; it never writes
    # a proposal itself (docs/AGENT-ARCHITECTURE.md §3: "Specialists propose,
    # the Overseer decides"), so it owns no proposal types.
    "overseer": (),
    # agents/consultant/role.md, "Does NOT own": "Any fort-specific
    # decision... Do not propose a build." The consultant answers questions
    # on demand and never proposes, so it gets no proposal types at all: a
    # proposal from this role is refused by construction, not by an
    # incidentally-empty vocabulary.
    "consultant": (),
    # Enabled for the MVP by the user's call, 2026-09-22
    # (`handoffs/2026-09-22-loop-queue-quartermaster.md`), though the role
    # itself stays `enabled: false` in `agents/ROSTER.yaml` until the
    # orchestrator flips it at merge (not this stream's file). The type
    # vocabulary is drafted ahead of that flip, same as every other role's
    # here, so enabling the role is a config change, not a fresh schema
    # decision.
    "quartermaster": QUARTERMASTER_TYPES,
    # Disabled roles (agents/ROSTER.yaml, `enabled: false`): no tool surface
    # exists yet for either of them, so no proposal type is drafted either.
    # The role-enabled check refuses a record from either of these before
    # the type check is even reached; these entries exist so the table
    # stays a complete map of the roster rather than silently defaulting an
    # unlisted role to "anything goes".
    "marshal": (),
    "chronicler": (),
}

# ---- fields, by kind ----------------------------------------------------------

COMMON_FIELDS = ("id", "ts", "kind", "role", "cycle", "snapshot")

KIND_FIELDS: dict[str, tuple[str, ...]] = {
    PROPOSAL: (
        "type", "summary", "rationale", "prediction", "cost",
        "suggested_priority", "preconditions", "public_rationale",
        "duplicate_of", "relies_on", "cited",
        #: handoffs/2026-10-05-stage-2a.md (docs/CONDUCTOR-EXECUTION.md 2.1):
        #: `step` is the one exact action a routed proposal asks for;
        #: `phases` declares the later phases of the same project;
        #: `project_id`/`after_step` make it a follow-up that joins an open
        #: project; `preview` and `covered_by` are server-set.
        #: `public_title` is in the design's 2.1 example (copied to the
        #: project it opens).
        "step", "phases", "project_id", "after_step", "preview", "covered_by",
        "public_title",
    ),
    PASS: ("reason",),
    RULING: ("decision", "proposal_id", "reason", "public_rationale"),
    #: `step_id` added handoffs/2026-09-28-dfqueue-project-step-schema.md:
    #: which step of `from_ruling`'s project this execution is for. Optional
    #: -- a `ruling` whose project has no real steps (see `normalize_project`)
    #: is executed exactly as before, with no `step_id` at all.
    #: `proposal_id` added handoffs/2026-10-05-stage-2a.md: the executor's
    #: step's own proposal (a follow-up's step is not the root ruling's).
    EXECUTED: ("ruling_id", "step_id", "actions", "notes", "proposal_id"),
    ASK: ("question", "proposal_id"),
    ANSWER: ("ask_id", "answer"),
    ESCALATION: ("reason",),
    #: `research/2026-09-28-job-dependency-graph.md` §4.1. `public_title`,
    #: `public_rationale` and `urgency` added
    #: `handoffs/2026-10-02-queue-display-fields.md`, all optional.
    PROJECT: (
        "from_ruling", "objective_id", "template", "summary", "because",
        "steps", "public_title", "public_rationale", "urgency",
    ),
    #: §4.4. One `observation` record reports on one or more targets read at
    #: the same game tick (one reconcile pass, one tick).
    #: `done` and `detail` added handoffs/2026-10-05-stage-2a.md: `done` is
    #: the executor's completion verdict for the step's synthetic target
    #: (flips it `done` and arms the step proposal's prediction).
    OBSERVATION: ("project_id", "step_id", "game_tick", "results", "done", "detail"),
    #: `handoffs/2026-10-01-queue-bugs-and-amend.md` item 3. `steps` is the
    #: FULL new ordered step list this version replaces the previous one
    #: with (never a diff to apply) -- `replaces`/`adds`/`drops` are purely
    #: declarative bookkeeping naming which of the previous version's step
    #: ids this version keeps changed, which of `steps`' own ids are brand
    #: new, and which of the previous version's ids are gone, so a reader
    #: (or a future audit) does not have to diff two step lists by hand to
    #: answer "what changed here".
    #: `public_rationale` added `handoffs/2026-10-02-queue-display-fields.md`,
    #: optional.
    AMEND: (
        "project_id", "steps", "reason", "replaces", "adds", "drops",
        "public_rationale",
    ),
    ABANDON: ("project_id", "reason", "public_rationale"),
    CLOSE: (
        "project_id", "proposal_id", "ruling_id", "outcome", "reason",
        "cleanup",
    ),
}

# ---- the raw-coordinate pattern -----------------------------------------------

_COORDINATE_PATTERN = re.compile(
    r"\b[xyz]\s*=\s*-?\d+\b"                                  # x=12, z = -3
    r"|[\(\[]\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*[\)\]]",       # (4,9,-2) / [4, 9, 2]
    re.IGNORECASE,
)


def _find_coordinate(text: str) -> str | None:
    m = _COORDINATE_PATTERN.search(text)
    return m.group(0) if m else None


# ---- duplicate-proposal detection ----------------------------------------------
#
# `handoffs/2026-09-28-queue-duplicate-proposal-check.md`: `proposal-0009`
# duplicated the still-open `proposal-0007` (both proposing to queue brewing
# directly at the Still) without either advisor knowing the other existed.
# `dfmcp/gotchas_store.py`'s `near_duplicate_reason(candidate, existing)`
# already solves the identical problem for gotchas (same tool/list, near-
# duplicate title or body); this is that same shape, applied to a proposal's
# own declared fields (`summary`, then `rationale`) instead of a gotcha's
# (`title`, then `body`). Deliberately generalised across every proposal
# `type` rather than hardcoded to one action: the caller (`dfqueue/store.py`)
# scopes the candidate pool to proposals of the SAME `type` that are still
# open, and this function only ever compares the two records' own text
# fields, never a fixed string list keyed to a particular type.
#
# Unlike gotchas, a match here is never a refusal (`dfqueue/store.py`'s own
# docstring on `append()`): a duplicate proposal is still written, flagged
# with `duplicate_of`, so the Overseer's ruling sees both and decides on the
# merits, the way `proposal-0009` should have been but was not.

_WORD_RE = re.compile(r"[a-z0-9]+")

#: A candidate proposal is a near-duplicate of an existing one (same `type`,
#: still open) when either bound is reached. Same values and same two-pass
#: shape (word-set Jaccard, then a full sequence-match ratio) as
#: `dfmcp.gotchas_store`'s `TITLE_DUP_JACCARD`/`TITLE_DUP_RATIO`/
#: `BODY_DUP_RATIO` -- not re-imported from there, since a gotcha and a
#: proposal are different record kinds in different packages (this module's
#: own docstring's "no armok tools"-style rule doesn't apply, but crossing
#: `dfmcp` -> `dfqueue` for one constant is a worse coupling than repeating
#: three floats).
SUMMARY_DUP_JACCARD = 0.75
SUMMARY_DUP_RATIO = 0.85
RATIONALE_DUP_RATIO = 0.85


def _normalise_words(text) -> list[str]:
    return _WORD_RE.findall(str(text).lower())


def near_duplicate_reason(candidate: dict, existing: dict) -> str | None:
    """Why `candidate` (a would-be new proposal) is a near-duplicate of
    `existing` (an already-queued proposal), or `None`. Pure and stateless:
    the caller (`dfqueue/store.py`'s `_find_duplicate_proposal`) is what
    scopes the comparison to proposals of the same `type` that are still
    open -- this function only ever reads `summary` and `rationale` off the
    two dicts it is given.

    Checked in order, cheapest and most literal first: an identical summary
    (ignoring case and punctuation), a summary sharing most of its words, a
    summary that is nearly the same text character-for-character, then --
    only if the summaries differ enough to reach here -- a rationale that is
    nearly the same text. A `type` match on its own is not enough: two
    unrelated proposals of the same `type` (two different `workshop_siting`
    proposals for two different workshops) must not collide.
    """
    cw, ew = _normalise_words(candidate.get("summary", "")), _normalise_words(existing.get("summary", ""))
    if cw and cw == ew:
        return "its summary is identical to an existing open proposal's (ignoring case and punctuation)"
    cset, eset = set(cw), set(ew)
    if cset and eset:
        jaccard = len(cset & eset) / len(cset | eset)
        if jaccard >= SUMMARY_DUP_JACCARD:
            return f"its summary shares {jaccard:.0%} of its words with an existing open proposal's"
    if cw and ew and difflib.SequenceMatcher(None, " ".join(cw), " ".join(ew)).ratio() >= SUMMARY_DUP_RATIO:
        return "its summary is nearly the same text as an existing open proposal's"
    cr = " ".join(_normalise_words(candidate.get("rationale", "")))
    er = " ".join(_normalise_words(existing.get("rationale", "")))
    if cr and er and difflib.SequenceMatcher(None, cr, er).ratio() >= RATIONALE_DUP_RATIO:
        return "its rationale is nearly the same text as an existing open proposal's"
    return None


# ---- roster (agents/ROSTER.yaml), read-only ------------------------------------


@lru_cache(maxsize=1)
def _load_roster() -> dict:
    with ROSTER_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def enabled_roles() -> frozenset[str]:
    roster = _load_roster()
    return frozenset(
        name for name, cfg in roster.get("roles", {}).items() if cfg.get("enabled")
    )


def sole_writer() -> str:
    return _load_roster()["sole_writer"]


def fort_name() -> str:
    return _load_roster()["fort"]


def executor() -> str:
    """The roster's `executor` (docs/CONDUCTOR-EXECUTION.md 6.1): the code
    role that runs routed steps and writes `project`, `executed`, `amend`,
    `observation` and `close` for them. Never a model."""
    return _load_roster().get("executor") or OBSERVATION_ROLE


# ---- public text (dfqueue/public_text.yaml), read-only -------------------------


@lru_cache(maxsize=1)
def _load_public_text() -> dict:
    with PUBLIC_TEXT_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def hold_codes() -> frozenset[str]:
    """The closed `hold_code` vocabulary (design
    `research/2026-10-01-stream-page-design.md` §3.3 item 7), read from
    `dfqueue/public_text.yaml`'s own keys rather than hardcoded here -- a new
    code is one data entry in that file, not a code change."""
    return frozenset(_load_public_text().get("hold_codes", {}).keys())


# ---- sub-record validation ------------------------------------------------------


def _validate_text_field(record: dict, name: str, errors: list[str]) -> None:
    """A required, non-empty, coordinate-free free-text field."""
    if name not in record:
        errors.append(f"record.{name}: required field is missing")
        return
    value = record[name]
    if not isinstance(value, str) or not value:
        errors.append(f"record.{name}: expected a non-empty string")
        return
    coord = _find_coordinate(value)
    if coord:
        errors.append(
            f"record.{name}: contains a raw-coordinate pattern ({coord!r}); "
            "design commitment #1 forbids coordinates in text fields"
        )


def _validate_optional_text_field(
    record: dict, name: str, errors: list[str], *, max_len: int | None = None
) -> None:
    """An optional, coordinate-free free-text field: absence (or an explicit
    `None`) is not an error, unlike `_validate_text_field` -- added
    `handoffs/2026-10-02-queue-display-fields.md` for the stream page's
    public display fields (`public_title`, `public_rationale`), which an
    old record written before this stream never had. When given, it gets
    the same coordinate scan every public text field gets, plus an optional
    max length."""
    if name not in record or record[name] is None:
        return
    value = record[name]
    if not isinstance(value, str) or not value:
        errors.append(f"record.{name}: expected a non-empty string when given")
        return
    if max_len is not None and len(value) > max_len:
        errors.append(
            f"record.{name}: expected at most {max_len} characters, got {len(value)}"
        )
    coord = _find_coordinate(value)
    if coord:
        errors.append(
            f"record.{name}: contains a raw-coordinate pattern ({coord!r}); "
            "design commitment #1 forbids coordinates in text fields"
        )


def _validate_cost(cost, errors: list[str], prefix: str) -> None:
    if not isinstance(cost, dict):
        errors.append(f"{prefix}: expected an object")
        return
    known = {"estimate", "unit"}
    for key in cost:
        if key not in known:
            errors.append(f"{prefix}.{key}: not a field in the schema")

    if "estimate" not in cost:
        errors.append(f"{prefix}.estimate: required field is missing")
    else:
        v = cost["estimate"]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            errors.append(f"{prefix}.estimate: expected a number")
        elif v <= 0:
            errors.append(f"{prefix}.estimate: must be > 0, got {v!r}")

    if "unit" not in cost:
        errors.append(f"{prefix}.unit: required field is missing")
    elif cost["unit"] not in COST_UNITS:
        errors.append(f"{prefix}.unit: {cost['unit']!r} is not in {COST_UNITS}")


def _validate_preconditions(preconditions, errors: list[str], prefix: str) -> None:
    if not isinstance(preconditions, list):
        errors.append(f"{prefix}: expected a list")
        return
    known = {"landmark", "area", "state"}
    for i, item in enumerate(preconditions):
        p = f"{prefix}.{i}"
        if not isinstance(item, dict):
            errors.append(f"{p}: expected an object")
            continue
        for key in item:
            if key not in known:
                errors.append(f"{p}.{key}: not a field in the schema")

        has_landmark, has_area = "landmark" in item, "area" in item
        if has_landmark == has_area:
            errors.append(f"{p}: exactly one of 'landmark' or 'area' is required")
        else:
            key = "landmark" if has_landmark else "area"
            v = item[key]
            if not isinstance(v, str) or not v:
                errors.append(f"{p}.{key}: expected a non-empty string")

        if "state" not in item:
            errors.append(f"{p}.state: required field is missing")
        else:
            v = item["state"]
            if not isinstance(v, str) or not v:
                errors.append(f"{p}.state: expected a non-empty string")


def _validate_prediction(prediction, errors: list[str], prefix: str) -> None:
    """Validate the wire shape (matching §4's `<prediction signal=... op=...
    value=... check_after_ticks=.../>`) against `learning.live_signals` —
    never a `learning.predictions` row, and never `learning/ledger`'s
    `FORT_FIELDS`. See this module's docstring, "`prediction.signal` must
    be a live signal, not a ledger field."
    """
    if not isinstance(prediction, dict):
        errors.append(f"{prefix}: expected an object")
        return

    known = {"signal", "op", "value", "check_after_ticks"}
    for key in prediction:
        if key not in known:
            errors.append(f"{prefix}.{key}: not a field in the schema")

    required = ("signal", "op", "check_after_ticks")
    missing = [k for k in required if k not in prediction]
    for k in missing:
        errors.append(f"{prefix}.{k}: required field is missing")
    if missing or any(k not in known for k in prediction):
        return  # can't safely validate the rest of a malformed prediction

    check_after_ticks = prediction["check_after_ticks"]
    if isinstance(check_after_ticks, bool) or not isinstance(check_after_ticks, int):
        errors.append(f"{prefix}.check_after_ticks: expected an integer")
    elif check_after_ticks <= 0:
        errors.append(
            f"{prefix}.check_after_ticks: must be > 0, got {check_after_ticks!r}"
        )

    op = prediction["op"]
    if op not in PREDICATE_OPS:
        errors.append(f"{prefix}.op: {op!r} is not in {PREDICATE_OPS}")

    signal = prediction["signal"]
    parsed = None
    if not isinstance(signal, str) or not signal:
        errors.append(f"{prefix}.signal: expected a non-empty string")
    else:
        try:
            parsed = live_signals.parse(signal)
        except live_signals.SignalError as exc:
            if ledger_field_source(signal) is not None:
                errors.append(
                    f"{prefix}.signal: {signal!r} is an end-of-fort ledger field; "
                    "fort-level claims belong in learning/predictions/, not a "
                    "dfqueue proposal"
                )
            else:
                errors.append(f"{prefix}.signal: {exc}")

    value = prediction.get("value")
    is_presence_op = op in PRESENCE_OPS
    if is_presence_op and value is not None:
        errors.append(f"{prefix}.value: must be null when op is {op!r}")
    if not is_presence_op and value is None:
        errors.append(f"{prefix}.value: required (non-null) when op is {op!r}")

    if parsed is not None and not is_presence_op and value is not None:
        if parsed.value_type == live_signals.INTEGER:
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(
                    f"{prefix}.value: signal {signal!r} is integer-valued, "
                    f"got {value!r}"
                )
        elif parsed.value_type == live_signals.BOOLEAN:
            if not isinstance(value, bool):
                errors.append(
                    f"{prefix}.value: signal {signal!r} is boolean-valued, "
                    f"got {value!r}"
                )


#: `docs/CONDUCTOR-EXECUTION.md` 2.1/2.2 item 4: a proposal may cite up to this
#: many facts it rests on; the server reads each at filing.
RELIES_ON_MAX = 6
CITED_VALUE_TEXT_MAX = 80


def _is_scalar_fact(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return len(value) <= CITED_VALUE_TEXT_MAX
    return isinstance(value, (bool, int, float))


def _validate_fact_ref(item, errors: list[str], prefix: str, *, cited: bool) -> None:
    if not isinstance(item, dict):
        errors.append(f"{prefix}: expected an object")
        return
    allowed = {"tool", "args", "field"} | ({"value", "tick"} if cited else set())
    for key in item:
        if key not in allowed:
            errors.append(f"{prefix}.{key}: not a field of a {'cited fact' if cited else 'relies_on entry'}")
    for key in ("tool", "field"):
        v = item.get(key)
        if not isinstance(v, str) or not v:
            errors.append(f"{prefix}.{key}: expected a non-empty string")
    if "args" in item and not isinstance(item["args"], dict):
        errors.append(f"{prefix}.args: expected an object when given")
    if cited:
        if "value" not in item or not _is_scalar_fact(item.get("value")):
            errors.append(f"{prefix}.value: expected a number, boolean or short string")
        tick = item.get("tick")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            errors.append(f"{prefix}.tick: expected a non-negative integer")


def _validate_fact_list(record: dict, name: str, errors: list[str], *, cited: bool) -> None:
    if name not in record:
        return
    items = record[name]
    if not isinstance(items, list):
        errors.append(f"record.{name}: expected a list")
        return
    if len(items) > RELIES_ON_MAX:
        errors.append(f"record.{name}: at most {RELIES_ON_MAX} entries, got {len(items)}")
    for i, item in enumerate(items):
        _validate_fact_ref(item, errors, f"record.{name}[{i}]", cited=cited)


#: Largest JSON size, in characters, of a server-set `preview` or an
#: observation's `detail`.
PREVIEW_MAX = 4000


def _args_have_coordinates(value) -> str | None:
    """A raw-coordinate pattern anywhere in a step's `args` (design
    commitment #1: no coordinates in anything a proposer writes)."""
    return _find_coordinate(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _validate_step_spec(step, errors: list[str], prefix: str) -> None:
    """A proposal's `step`: `{tool, args, label?}`, one exact action
    (docs/CONDUCTOR-EXECUTION.md 2.1). Whether the tool is in a routed group,
    takes `DRY_RUN`, and whether the arguments dry-run are the server's
    filing checks (2C), not this stateless one."""
    if not isinstance(step, dict):
        errors.append(f"{prefix}: expected an object")
        return
    for key in step:
        if key not in ("tool", "args", "label"):
            errors.append(f"{prefix}.{key}: not a field of a proposal step")
    tool = step.get("tool")
    if not isinstance(tool, str) or not tool:
        errors.append(f"{prefix}.tool: required, a non-empty string")
    elif tool not in _tool_registry().ids():
        errors.append(
            f"{prefix}.tool: {tool!r} is not a real tool id "
            "(scripts/dfhack/TOOLS.yaml, via dfmcp.registry)"
        )
    if "args" not in step:
        errors.append(f"{prefix}.args: required (an object, possibly empty)")
    elif not isinstance(step["args"], dict):
        errors.append(f"{prefix}.args: expected an object")
    else:
        coord = _args_have_coordinates(step["args"])
        if coord:
            errors.append(
                f"{prefix}.args: contains a raw-coordinate pattern ({coord!r}); "
                "design commitment #1 forbids coordinates in a step"
            )
    label = step.get("label")
    if label is not None:
        if not isinstance(label, str) or not label:
            errors.append(f"{prefix}.label: expected a non-empty string when given")
        elif len(label) > STEP_LABEL_MAX:
            errors.append(
                f"{prefix}.label: expected at most {STEP_LABEL_MAX} characters, "
                f"got {len(label)}"
            )
        elif _find_coordinate(label):
            errors.append(f"{prefix}.label: contains a raw-coordinate pattern")


def _validate_phases_spec(phases, errors: list[str], prefix: str) -> None:
    """`phases: {tool, list}`: the later phases of the same project, in
    order. That each phase exists in the template, and the meta-overlap
    refusal (2.2 item 5), need the template and are the server's (2C)."""
    if not isinstance(phases, dict):
        errors.append(f"{prefix}: expected an object")
        return
    for key in phases:
        if key not in ("tool", "list"):
            errors.append(f"{prefix}.{key}: not a field of phases")
    tool = phases.get("tool")
    if not isinstance(tool, str) or not tool:
        errors.append(f"{prefix}.tool: required, a non-empty string")
    elif tool not in _tool_registry().ids():
        errors.append(f"{prefix}.tool: {tool!r} is not a real tool id")
    names = phases.get("list")
    if not isinstance(names, list) or not names:
        errors.append(f"{prefix}.list: required, a non-empty list of phase names")
    else:
        strs = [n for n in names if isinstance(n, str) and n]
        for i, n in enumerate(names):
            if not isinstance(n, str) or not n:
                errors.append(f"{prefix}.list.{i}: expected a non-empty string")
        if len(set(strs)) != len(strs):
            errors.append(f"{prefix}.list: a phase may be listed once")


def _validate_routed_fields(record: dict, errors: list[str]) -> None:
    """The stage 2 fields of a proposal (shape and combinations only; every
    check that needs the queue, routing or the template is in the store or
    the server)."""
    has_step = "step" in record
    if has_step:
        _validate_step_spec(record["step"], errors, "record.step")
    if "phases" in record:
        _validate_phases_spec(record["phases"], errors, "record.phases")
        if not has_step:
            errors.append("record.phases: needs a step")
        if "project_id" in record:
            errors.append(
                "record.phases: only a first proposal declares phases; a follow-up "
                "joins the phases its project already declared"
            )
    follow = ("project_id" in record, "after_step" in record)
    if follow[0] != follow[1]:
        errors.append("record.project_id and record.after_step: give both or neither")
    for name in ("project_id", "after_step"):
        if name in record and (not isinstance(record[name], str) or not record[name]):
            errors.append(f"record.{name}: expected a non-empty string")
    if follow[0] and not has_step:
        errors.append("record.project_id: a follow-up needs a step")
    if "covered_by" in record:
        v = record["covered_by"]
        if not isinstance(v, str) or not v:
            errors.append("record.covered_by: expected a non-empty string (the server sets it)")
        if not follow[0]:
            errors.append("record.covered_by: only a follow-up can be covered")
    if "preview" in record:
        v = record["preview"]
        if not isinstance(v, dict):
            errors.append("record.preview: expected an object (the server sets it)")
        elif len(json.dumps(v, ensure_ascii=False, sort_keys=True)) > PREVIEW_MAX:
            errors.append(f"record.preview: larger than {PREVIEW_MAX} characters")
        if not has_step:
            errors.append("record.preview: needs a step")
    _validate_optional_text_field(record, "public_title", errors, max_len=PUBLIC_TITLE_MAX)


def _validate_proposal_fields(record: dict, role, errors: list[str]) -> None:
    _validate_routed_fields(record, errors)
    _validate_fact_list(record, "relies_on", errors, cited=False)
    _validate_fact_list(record, "cited", errors, cited=True)
    if "cited" in record and len(record.get("cited") or []) != len(record.get("relies_on") or []):
        errors.append("record.cited: must have one entry per relies_on entry (the server sets it)")
    for name in ("summary", "rationale", "public_rationale"):
        _validate_text_field(record, name, errors)

    if "type" not in record:
        errors.append("record.type: required field is missing")
    else:
        ptype = record["type"]
        if not isinstance(ptype, str) or not ptype:
            errors.append("record.type: expected a non-empty string")
        else:
            vocab = TYPE_VOCAB_BY_ROLE.get(role, ()) if isinstance(role, str) else ()
            if not vocab:
                errors.append(
                    f"record.type: role {role!r} has no proposal-type vocabulary "
                    "(it does not propose)"
                )
            elif ptype not in vocab:
                errors.append(
                    f"record.type: {ptype!r} is not in the proposal-type vocabulary "
                    f"for role {role!r} (allowed: {vocab})"
                )

    if "cost" not in record:
        errors.append("record.cost: required field is missing")
    else:
        _validate_cost(record["cost"], errors, "record.cost")

    if "suggested_priority" not in record:
        errors.append("record.suggested_priority: required field is missing")
    else:
        priority = record["suggested_priority"]
        if isinstance(priority, bool) or not isinstance(priority, int) or not (1 <= priority <= 7):
            errors.append(
                f"record.suggested_priority: expected an integer 1-7, got {priority!r}"
            )

    if "preconditions" not in record:
        errors.append("record.preconditions: required field is missing")
    else:
        _validate_preconditions(record["preconditions"], errors, "record.preconditions")

    if "prediction" not in record:
        errors.append("record.prediction: required field is missing")
    else:
        _validate_prediction(record["prediction"], errors, "record.prediction")

    if "duplicate_of" in record:
        dup = record["duplicate_of"]
        if not isinstance(dup, str) or not dup:
            errors.append(
                "record.duplicate_of: expected a non-empty string when given (the id "
                "of the existing open proposal this one duplicates)"
            )


def _validate_ruling_fields(record: dict, errors: list[str]) -> None:
    if "decision" not in record or record.get("decision") not in RULING_DECISIONS:
        errors.append(
            f"record.decision: {record.get('decision')!r} is not in {RULING_DECISIONS}"
        )

    if "proposal_id" not in record:
        errors.append("record.proposal_id: required field is missing")
    else:
        pid = record["proposal_id"]
        if not isinstance(pid, str) or not pid:
            errors.append("record.proposal_id: expected a non-empty string")

    _validate_text_field(record, "reason", errors)
    _validate_text_field(record, "public_rationale", errors)


def _validate_handle_list(value, errors: list[str], prefix: str) -> None:
    """A non-empty list of non-empty, coordinate-free opaque handle strings
    (target handles, or `game_refs` job/building ids -- both are code-only,
    never a raw coordinate, per design §4.1: "Targets are named code-side by
    opaque handles... never by a coordinate in any field an agent sees.")."""
    if not isinstance(value, list) or not value:
        errors.append(f"{prefix}: expected a non-empty list")
        return
    for i, v in enumerate(value):
        # game_refs may be job/building ids (ints) as well as handle strings.
        if isinstance(v, bool) or not isinstance(v, (str, int)) or v == "":
            errors.append(f"{prefix}.{i}: expected a non-empty string or integer")
            continue
        coord = _find_coordinate(str(v))
        if coord:
            errors.append(
                f"{prefix}.{i}: contains a raw-coordinate pattern ({coord!r}); "
                "design commitment #1 forbids coordinates in this field"
            )


def _validate_action(item, errors: list[str], prefix: str) -> None:
    if not isinstance(item, dict):
        errors.append(f"{prefix}: expected an object")
        return
    known = {"tool", "outcome", "detail", "targets", "game_refs", "target_state"}
    for key in item:
        if key not in known:
            errors.append(f"{prefix}.{key}: not a field in the schema")

    if "tool" not in item:
        errors.append(f"{prefix}.tool: required field is missing")
    else:
        v = item["tool"]
        if not isinstance(v, str) or not v:
            errors.append(f"{prefix}.tool: expected a non-empty string")

    if "outcome" not in item or item.get("outcome") not in EXECUTION_OUTCOMES:
        errors.append(
            f"{prefix}.outcome: {item.get('outcome')!r} is not in {EXECUTION_OUTCOMES}"
        )

    if "detail" in item:
        v = item["detail"]
        if not isinstance(v, str) or not v:
            errors.append(f"{prefix}.detail: expected a non-empty string")
        else:
            coord = _find_coordinate(v)
            if coord:
                errors.append(
                    f"{prefix}.detail: contains a raw-coordinate pattern ({coord!r}); "
                    "design commitment #1 forbids coordinates in text fields"
                )

    # `targets`/`game_refs`/`target_state` added
    # handoffs/2026-09-28-dfqueue-project-step-schema.md item 2 (design
    # §4.4). `targets` and `target_state` are both-or-neither: a
    # `target_state` with no `targets` names nothing, and a `targets` list
    # with no `target_state` leaves the fold unable to say what happened to
    # them (see `store.py`'s target-state fold).
    has_targets, has_state = "targets" in item, "target_state" in item
    if "targets" in item:
        _validate_handle_list(item["targets"], errors, f"{prefix}.targets")
    if has_targets != has_state:
        errors.append(
            f"{prefix}: 'targets' and 'target_state' must be given together "
            "or not at all"
        )
    if has_state:
        v = item["target_state"]
        if v not in ACTION_TARGET_STATES:
            errors.append(
                f"{prefix}.target_state: {v!r} is not in {ACTION_TARGET_STATES}"
            )
    if "game_refs" in item:
        _validate_handle_list(item["game_refs"], errors, f"{prefix}.game_refs")


def _validate_executed_fields(record: dict, errors: list[str]) -> None:
    """`ruling_id`'s existence and its ruling's `decision` (must be
    `accept`) need the rest of the queue, so — same split as `ruling`'s own
    `proposal_id` — that check lives in `store.append()`, not here.
    `step_id`'s existence (must name a real step of `ruling_id`'s own
    project) is the same kind of split, also in `store.append()`."""
    if "ruling_id" not in record:
        errors.append("record.ruling_id: required field is missing")
    else:
        rid = record["ruling_id"]
        if not isinstance(rid, str) or not rid:
            errors.append("record.ruling_id: expected a non-empty string")

    if "step_id" in record:
        sid = record["step_id"]
        if not isinstance(sid, str) or not sid:
            errors.append("record.step_id: expected a non-empty string")

    if "proposal_id" in record:
        pid = record["proposal_id"]
        if not isinstance(pid, str) or not pid:
            errors.append("record.proposal_id: expected a non-empty string")
        elif "step_id" not in record:
            errors.append("record.proposal_id: names a step's proposal, so step_id is needed too")

    if "actions" not in record:
        errors.append("record.actions: required field is missing")
    else:
        actions = record["actions"]
        if not isinstance(actions, list) or not actions:
            errors.append("record.actions: expected a non-empty list")
        else:
            for i, item in enumerate(actions):
                _validate_action(item, errors, f"record.actions.{i}")

    _validate_text_field(record, "notes", errors)


@lru_cache(maxsize=1)
def _tool_registry():
    """`dfmcp.registry.load_registry()`, cached the same way `_load_roster`
    is: this module is re-imported per test process, not per call, and the
    registry is a pure read of `scripts/dfhack/TOOLS.yaml` with no reason to
    reload it per validation. Reused rather than reinvented, per the
    handoff's own instruction: "validate against `scripts/dfhack/TOOLS.yaml`
    or however this codebase already validates a tool reference elsewhere".
    `dfmcp.registry` imports nothing from `dfqueue`, so this import direction
    (`dfqueue` -> `dfmcp.registry`) does not create a cycle -- only
    `dfmcp.queue_tools` imports `dfqueue`, not `dfmcp.registry` itself."""
    return load_registry()


def _validate_target_spec(spec, step_ids: set, errors: list[str], prefix: str) -> None:
    """Design §4.3: a target set is either a literal `set` of opaque handles
    or `{from_step, select}` ("this step's done targets"). Only `select:
    "done"` is built (the design's own worked example); a query-shaped
    target set (§4.3's dynamic-discovery case) is not schema-representable
    yet -- flagged in this stream's Result section, not built here."""
    if not isinstance(spec, dict):
        errors.append(f"{prefix}: expected an object")
        return
    has_set, has_from = "set" in spec, "from_step" in spec
    if has_set == has_from:
        errors.append(f"{prefix}: exactly one of 'set' or 'from_step' is required")
        return
    if has_set:
        for key in spec:
            if key != "set":
                errors.append(f"{prefix}.{key}: not a field when 'set' is given")
        _validate_handle_list(spec["set"], errors, f"{prefix}.set")
    else:
        known = {"from_step", "select"}
        for key in spec:
            if key not in known:
                errors.append(f"{prefix}.{key}: not a field when 'from_step' is given")
        fs = spec["from_step"]
        if not isinstance(fs, str) or not fs:
            errors.append(f"{prefix}.from_step: expected a non-empty string")
        elif fs not in step_ids:
            errors.append(
                f"{prefix}.from_step: {fs!r} is not a step id declared in this project"
            )
        if "select" not in spec:
            errors.append(f"{prefix}.select: required field is missing")
        elif spec["select"] != "done":
            errors.append(f"{prefix}.select: {spec['select']!r} is not in ('done',)")


_IMPLICIT_STEP_TARGETS = {"set": []}


def _validate_step(step, step_ids: set, errors: list[str], prefix: str) -> None:
    """One step of a `project` record (design §4.1). `step_ids` is every
    step id declared anywhere in the same project's `steps` list -- needed
    statelessly (no database) because `requires`/`prefer_after`/`from_step`
    only ever reference a sibling step in the same record."""
    if not isinstance(step, dict):
        errors.append(f"{prefix}: expected an object")
        return

    known = {
        "id", "tool", "args", "targets", "requires", "trigger",
        "prefer_after", "guards", "implicit", "label", "proposal_id",
    }
    for key in step:
        if key not in known:
            errors.append(f"{prefix}.{key}: not a field in the step schema")

    if "id" not in step:
        errors.append(f"{prefix}.id: required field is missing")
    else:
        sid = step["id"]
        if not isinstance(sid, str) or not sid:
            errors.append(f"{prefix}.id: expected a non-empty string")

    implicit = step.get("implicit") is True
    if "implicit" in step and not isinstance(step["implicit"], bool):
        errors.append(f"{prefix}.implicit: expected a boolean")

    if "tool" not in step:
        errors.append(f"{prefix}.tool: required field is missing")
    elif implicit:
        # The auto-synthesised single step of a project whose ruling's
        # proposal carried no `steps` block at all (`normalize_project`
        # below) -- "the whole proposal is the step", not a real granular
        # tool call, so it is deliberately exempt from the real-tool-id
        # check: never free text an agent wrote, only code-generated.
        if step["tool"] is not None:
            errors.append(f"{prefix}.tool: an implicit step's tool must be null")
    else:
        tool = step["tool"]
        if not isinstance(tool, str) or not tool:
            errors.append(f"{prefix}.tool: expected a non-empty string")
        elif tool not in _tool_registry().ids():
            errors.append(
                f"{prefix}.tool: {tool!r} is not a real tool id "
                "(scripts/dfhack/TOOLS.yaml, via dfmcp.registry)"
            )

    if "args" in step and not isinstance(step["args"], dict):
        errors.append(f"{prefix}.args: expected an object")

    if "proposal_id" in step:
        v = step["proposal_id"]
        if not isinstance(v, str) or not v:
            errors.append(f"{prefix}.proposal_id: expected a non-empty string")

    if "targets" not in step:
        errors.append(f"{prefix}.targets: required field is missing")
    elif implicit:
        if step["targets"] != _IMPLICIT_STEP_TARGETS:
            errors.append(
                f"{prefix}.targets: an implicit step's targets must be "
                f"{_IMPLICIT_STEP_TARGETS!r} (nothing tracked at this granularity)"
            )
    else:
        _validate_target_spec(step["targets"], step_ids, errors, f"{prefix}.targets")

    if "requires" in step:
        requires = step["requires"]
        if not isinstance(requires, list):
            errors.append(f"{prefix}.requires: expected a list")
        else:
            for i, r in enumerate(requires):
                if not isinstance(r, str) or not r:
                    errors.append(f"{prefix}.requires.{i}: expected a non-empty string")
                elif r not in step_ids:
                    errors.append(
                        f"{prefix}.requires.{i}: {r!r} is not a step id in this project"
                    )
                elif isinstance(step.get("id"), str) and r == step["id"]:
                    errors.append(f"{prefix}.requires.{i}: a step may not require itself")

    if "trigger" in step and step["trigger"] not in TRIGGERS:
        errors.append(f"{prefix}.trigger: {step['trigger']!r} is not in {TRIGGERS}")

    if "prefer_after" in step:
        pa = step["prefer_after"]
        if not isinstance(pa, list):
            errors.append(f"{prefix}.prefer_after: expected a list")
        else:
            for i, r in enumerate(pa):
                if not isinstance(r, str) or not r:
                    errors.append(f"{prefix}.prefer_after.{i}: expected a non-empty string")
                elif r not in step_ids:
                    errors.append(
                        f"{prefix}.prefer_after.{i}: {r!r} is not a step id in this project"
                    )

    if "guards" in step:
        g = step["guards"]
        if g != GUARDS_DEFAULT:
            if not isinstance(g, list):
                errors.append(
                    f"{prefix}.guards: expected {GUARDS_DEFAULT!r} or a list of guard names"
                )
            else:
                for i, name in enumerate(g):
                    if not isinstance(name, str) or not name:
                        errors.append(f"{prefix}.guards.{i}: expected a non-empty string")

    if "label" in step and step["label"] is not None:
        label = step["label"]
        if not isinstance(label, str) or not label:
            errors.append(f"{prefix}.label: expected a non-empty string when given")
        elif len(label) > STEP_LABEL_MAX:
            errors.append(
                f"{prefix}.label: expected at most {STEP_LABEL_MAX} characters, "
                f"got {len(label)}"
            )
        else:
            coord = _find_coordinate(label)
            if coord:
                errors.append(
                    f"{prefix}.label: contains a raw-coordinate pattern ({coord!r}); "
                    "design commitment #1 forbids coordinates in text fields"
                )


def _find_requires_cycle(steps: list) -> list[str] | None:
    """The first `requires` cycle found (finish-to-start edges only, design
    §2.2's chosen link type), as the offending path, or `None`. Dangling
    references are skipped here -- `_validate_step` already reports those as
    their own error; this only walks edges that point at a real sibling."""
    graph: dict[str, list[str]] = {}
    for s in steps:
        if isinstance(s, dict) and isinstance(s.get("id"), str) and s["id"]:
            reqs = s.get("requires", [])
            graph[s["id"]] = [r for r in reqs if isinstance(r, str)] if isinstance(reqs, list) else []

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = GRAY
        path.append(node)
        for nxt in graph.get(node, []):
            if nxt not in graph:
                continue
            if color.get(nxt) == GRAY:
                return path[path.index(nxt):] + [nxt]
            if color.get(nxt) == WHITE:
                found = visit(nxt)
                if found:
                    return found
        path.pop()
        color[node] = BLACK
        return None

    for node in list(graph):
        if color[node] == WHITE:
            found = visit(node)
            if found:
                return found
    return None


def _validate_project_fields(record: dict, errors: list[str]) -> None:
    if "from_ruling" not in record:
        errors.append("record.from_ruling: required field is missing")
    else:
        v = record["from_ruling"]
        if not isinstance(v, str) or not v:
            errors.append("record.from_ruling: expected a non-empty string")

    for name in ("objective_id", "template"):
        if name in record and record[name] is not None:
            v = record[name]
            if not isinstance(v, str) or not v:
                errors.append(f"record.{name}: expected a non-empty string or null")

    _validate_text_field(record, "summary", errors)
    _validate_text_field(record, "because", errors)
    _validate_optional_text_field(record, "public_title", errors, max_len=PUBLIC_TITLE_MAX)
    _validate_optional_text_field(
        record, "public_rationale", errors, max_len=PUBLIC_RATIONALE_MAX
    )
    if "urgency" in record and record["urgency"] is not None:
        if record["urgency"] not in URGENCIES:
            errors.append(
                f"record.urgency: {record['urgency']!r} is not in {URGENCIES}"
            )

    if "steps" not in record:
        errors.append("record.steps: required field is missing")
        return
    steps = record["steps"]
    if not isinstance(steps, list):
        errors.append("record.steps: expected a list")
        return
    if not steps:
        # `store.normalize_project` fills an absent/empty `steps` in with
        # one implicit step before this function ever runs on the real
        # write path (`store.append()`) -- reaching here with zero steps
        # means a caller validated a raw record directly, skipping
        # normalisation. Refused rather than silently accepted as a
        # zero-step (vacuously "done") project.
        errors.append("record.steps: expected at least one step (see normalize_project)")
        return

    step_ids = {
        s["id"] for s in steps
        if isinstance(s, dict) and isinstance(s.get("id"), str) and s["id"]
    }

    ids_seen = []
    for i, step in enumerate(steps):
        _validate_step(step, step_ids, errors, f"record.steps.{i}")
        if isinstance(step, dict) and isinstance(step.get("id"), str) and step["id"]:
            ids_seen.append(step["id"])

    dupes = sorted({sid for sid in ids_seen if ids_seen.count(sid) > 1})
    if dupes:
        errors.append(f"record.steps: duplicate step ids: {dupes}")

    cycle = _find_requires_cycle([s for s in steps if isinstance(s, dict)])
    if cycle:
        errors.append(f"record.steps: a 'requires' cycle exists: {' -> '.join(cycle)}")


def normalize_project(record: dict) -> dict:
    """Return `record` (a `project` record whose `id` is already assigned)
    with an absent or empty `steps` filled in with exactly one **implicit**
    step -- design §5.3's "a proposal with no steps block is a one-step
    project, so every existing proposal type keeps working unchanged." The
    implicit step wraps the whole ruling's own accepted proposal the way an
    `executed` record already does today (no `step_id`, no per-target
    tracking): its `tool` is `null` and it is exempt from the real-tool-id
    check (`_validate_step`), because it does not represent one granular
    tool call, only "this project is one undecomposed unit of work", the
    same shape execution already had before this stream. Never mutates its
    argument. Called from `store.append()`, after `id` is assigned and
    before `validate()` -- this is normalisation, not validation, so it
    stays in this module for `store.py` and any future caller to share
    rather than being duplicated at each write site.
    """
    record = dict(record)
    if record.get("steps"):
        return record
    record["steps"] = [{
        "id": f"{record['id']}/s1",
        "tool": None,
        "implicit": True,
        "args": {},
        "targets": dict(_IMPLICIT_STEP_TARGETS),
        "requires": [],
        "trigger": TRIGGER_ALL_SUCCESS,
        "prefer_after": [],
        "guards": GUARDS_DEFAULT,
    }]
    return record


def _validate_amend_fields(record: dict, errors: list[str]) -> None:
    """`handoffs/2026-10-01-queue-bugs-and-amend.md` item 3
    (`research/2026-09-30-goal-tree-red-team.md` F-3). `project_id`'s
    existence (must name a real `project` record) and `replaces`/`drops`
    naming real step ids of the PREVIOUS version, `adds` naming ids that
    really are new in THIS version's own `steps`, all need the rest of the
    queue (the previous version's own step ids), so those checks live in
    `store.append()`, not here -- same split as everywhere else in this
    module a reference needs the loaded file.

    `steps` is validated with the same per-step rules a `project`'s own
    `steps` uses (`_validate_step`, id uniqueness, no `requires` cycle) --
    duplicated here rather than sharing `_validate_project_fields` outright,
    since that function's messages and its `normalize_project`-specific
    empty-steps wording are written for a fresh project, not a revision of
    one that already exists.
    """
    if "project_id" not in record:
        errors.append("record.project_id: required field is missing")
    else:
        v = record["project_id"]
        if not isinstance(v, str) or not v:
            errors.append("record.project_id: expected a non-empty string")

    _validate_text_field(record, "reason", errors)
    _validate_optional_text_field(
        record, "public_rationale", errors, max_len=PUBLIC_RATIONALE_MAX
    )

    if "steps" not in record:
        errors.append("record.steps: required field is missing")
        return
    steps = record["steps"]
    if not isinstance(steps, list):
        errors.append("record.steps: expected a list")
        return
    if not steps:
        errors.append(
            "record.steps: expected at least one step (an amendment still "
            "carries the full new plan, never an empty one)"
        )
        return

    step_ids = {
        s["id"] for s in steps
        if isinstance(s, dict) and isinstance(s.get("id"), str) and s["id"]
    }

    ids_seen = []
    for i, step in enumerate(steps):
        _validate_step(step, step_ids, errors, f"record.steps.{i}")
        if isinstance(step, dict) and isinstance(step.get("id"), str) and step["id"]:
            ids_seen.append(step["id"])

    dupes = sorted({sid for sid in ids_seen if ids_seen.count(sid) > 1})
    if dupes:
        errors.append(f"record.steps: duplicate step ids: {dupes}")

    cycle = _find_requires_cycle([s for s in steps if isinstance(s, dict)])
    if cycle:
        errors.append(f"record.steps: a 'requires' cycle exists: {' -> '.join(cycle)}")

    for name in ("replaces", "adds", "drops"):
        if name not in record:
            continue
        v = record[name]
        if not isinstance(v, list):
            errors.append(f"record.{name}: expected a list")
            continue
        for i, item in enumerate(v):
            if not isinstance(item, str) or not item:
                errors.append(f"record.{name}.{i}: expected a non-empty string")


def _validate_abandon_fields(record: dict, errors: list[str]) -> None:
    """`handoffs/2026-10-01-queue-bugs-and-amend.md` item 3. `project_id`'s
    existence needs the rest of the queue (`store.append()`), same split as
    everywhere else in this module a reference needs the loaded file."""
    if "project_id" not in record:
        errors.append("record.project_id: required field is missing")
    else:
        v = record["project_id"]
        if not isinstance(v, str) or not v:
            errors.append("record.project_id: expected a non-empty string")

    _validate_text_field(record, "reason", errors)
    _validate_optional_text_field(
        record, "public_rationale", errors, max_len=PUBLIC_RATIONALE_MAX
    )


def _validate_observation_result(item, errors: list[str], prefix: str) -> None:
    if not isinstance(item, dict):
        errors.append(f"{prefix}: expected an object")
        return
    known = {"target", "status", "reason", "hold_code"}
    for key in item:
        if key not in known:
            errors.append(f"{prefix}.{key}: not a field in the schema")

    if "target" not in item:
        errors.append(f"{prefix}.target: required field is missing")
    else:
        v = item["target"]
        if isinstance(v, bool) or not isinstance(v, (str, int)) or v == "":
            errors.append(f"{prefix}.target: expected a non-empty string or integer")
        else:
            coord = _find_coordinate(str(v))
            if coord:
                errors.append(
                    f"{prefix}.target: contains a raw-coordinate pattern ({coord!r}); "
                    "design commitment #1 forbids coordinates in this field"
                )

    if item.get("status") not in OBSERVATION_STATUSES:
        errors.append(
            f"{prefix}.status: {item.get('status')!r} is not in {OBSERVATION_STATUSES}"
        )

    if "reason" not in item:
        errors.append(f"{prefix}.reason: required field is missing")
    else:
        v = item["reason"]
        if not isinstance(v, str) or not v:
            errors.append(f"{prefix}.reason: expected a non-empty string")
        else:
            coord = _find_coordinate(v)
            if coord:
                errors.append(
                    f"{prefix}.reason: contains a raw-coordinate pattern ({coord!r}); "
                    "design commitment #1 forbids coordinates in text fields"
                )

    if "hold_code" in item and item["hold_code"] is not None:
        hc = item["hold_code"]
        if not isinstance(hc, str) or hc not in hold_codes():
            errors.append(
                f"{prefix}.hold_code: {hc!r} is not in the closed hold-code "
                f"vocabulary (dfqueue/public_text.yaml: {sorted(hold_codes())})"
            )


def _validate_observation_fields(record: dict, errors: list[str]) -> None:
    """`project_id`'s and `step_id`'s existence (must name a real project and
    one of its real steps) needs the rest of the queue, so — same split as
    everywhere else in this module — that check lives in `store.append()`,
    not here."""
    if "project_id" not in record:
        errors.append("record.project_id: required field is missing")
    else:
        v = record["project_id"]
        if not isinstance(v, str) or not v:
            errors.append("record.project_id: expected a non-empty string")

    if "step_id" not in record:
        errors.append("record.step_id: required field is missing")
    else:
        v = record["step_id"]
        if not isinstance(v, str) or not v:
            errors.append("record.step_id: expected a non-empty string")

    if "game_tick" not in record:
        errors.append("record.game_tick: required field is missing")
    else:
        v = record["game_tick"]
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            errors.append("record.game_tick: expected a non-negative integer")

    if "results" not in record:
        errors.append("record.results: required field is missing")
    else:
        results = record["results"]
        if not isinstance(results, list) or not results:
            errors.append("record.results: expected a non-empty list")
        else:
            for i, r in enumerate(results):
                _validate_observation_result(r, errors, f"record.results.{i}")

    if "done" in record and not isinstance(record["done"], bool):
        errors.append("record.done: expected a boolean")
    if "detail" in record:
        d = record["detail"]
        if not isinstance(d, dict):
            errors.append("record.detail: expected an object")
        else:
            blob = json.dumps(d, ensure_ascii=False, sort_keys=True)
            if len(blob) > PREVIEW_MAX:
                errors.append(f"record.detail: larger than {PREVIEW_MAX} characters")
            coord = _find_coordinate(blob)
            if coord:
                errors.append(
                    f"record.detail: contains a raw-coordinate pattern ({coord!r}); "
                    "design commitment #1 forbids coordinates in this field"
                )


def _validate_close_fields(record: dict, errors: list[str]) -> None:
    """`handoffs/2026-10-05-stage-2a.md`: a `close` names exactly one of a
    project, a proposal or a ruling. That the target exists and is not
    already closed needs the queue (`store.append()`)."""
    named = [n for n in CLOSE_TARGET_FIELDS if n in record]
    if len(named) != 1:
        errors.append(
            f"record: a close names exactly one of {CLOSE_TARGET_FIELDS}, got {named}"
        )
    for n in named:
        v = record[n]
        if not isinstance(v, str) or not v:
            errors.append(f"record.{n}: expected a non-empty string")
    if record.get("outcome") not in CLOSE_OUTCOMES:
        errors.append(f"record.outcome: {record.get('outcome')!r} is not in {CLOSE_OUTCOMES}")
    _validate_text_field(record, "reason", errors)
    if "cleanup" in record:
        c = record["cleanup"]
        if not isinstance(c, list):
            errors.append("record.cleanup: expected a list")
        else:
            for i, item in enumerate(c):
                pre = f"record.cleanup.{i}"
                if not isinstance(item, dict):
                    errors.append(f"{pre}: expected an object")
                    continue
                for key in item:
                    if key not in ("handle", "tool", "outcome", "detail"):
                        errors.append(f"{pre}.{key}: not a field of a cleanup result")
                for key in ("handle", "outcome"):
                    if not isinstance(item.get(key), str) or not item.get(key):
                        errors.append(f"{pre}.{key}: required, a non-empty string")
                if "tool" in item and (not isinstance(item["tool"], str) or not item["tool"]):
                    errors.append(f"{pre}.tool: expected a non-empty string")
                if "detail" in item:
                    d = item["detail"]
                    if not isinstance(d, str) or not d:
                        errors.append(f"{pre}.detail: expected a non-empty string")
                    elif _find_coordinate(d):
                        errors.append(f"{pre}.detail: contains a raw-coordinate pattern")


def _validate_ask_fields(record: dict, errors: list[str]) -> None:
    """`proposal_id`'s existence, when present, needs the rest of the queue
    (`store.append()`), same split as `ruling`'s own `proposal_id`."""
    _validate_text_field(record, "question", errors)

    if "proposal_id" in record:
        pid = record["proposal_id"]
        if not isinstance(pid, str) or not pid:
            errors.append("record.proposal_id: expected a non-empty string")


def _validate_answer_fields(record: dict, errors: list[str]) -> None:
    """`ask_id`'s existence, and whether it already has an answer, need the
    rest of the queue (`store.append()`), same split as everywhere else in
    this module a reference needs the loaded file."""
    if "ask_id" not in record:
        errors.append("record.ask_id: required field is missing")
    else:
        aid = record["ask_id"]
        if not isinstance(aid, str) or not aid:
            errors.append("record.ask_id: expected a non-empty string")

    _validate_text_field(record, "answer", errors)


# ---- top-level validation ------------------------------------------------------


def validate(record) -> list[str]:
    """Validate one queue record. Returns a list of errors; empty is valid.

    Stateless: does not check a `ruling`'s `proposal_id` against the rest of
    the queue (that needs the loaded file, so it lives in
    `store.append()`), and does not require `id`/`ts` to already be set
    (the store assigns both before persisting, per §9's write-ahead-log
    pattern — a record can be validated before it has either).
    """
    if not isinstance(record, dict):
        return ["record: expected an object"]

    errors: list[str] = []

    if "kind" not in record:
        errors.append("record.kind: required field is missing")
        return errors
    kind = record["kind"]
    if kind not in KINDS:
        errors.append(f"record.kind: {kind!r} is not in {KINDS}")
        return errors

    known_fields = set(COMMON_FIELDS) | set(KIND_FIELDS[kind])
    for key in record:
        if key not in known_fields:
            errors.append(f"record.{key}: not a field in the {kind} schema")

    for name in ("id", "ts"):
        if name in record:
            v = record[name]
            if not isinstance(v, str) or not v:
                errors.append(f"record.{name}: expected a non-empty string")

    role = record.get("role")
    if "role" not in record or not isinstance(role, str) or not role:
        errors.append("record.role: required field is missing or empty")
        role = None
    else:
        if role not in enabled_roles():
            errors.append(
                f"record.role: {role!r} is not an enabled role in agents/ROSTER.yaml"
            )
        if kind in (RULING, ESCALATION, ABANDON):
            writer = sole_writer()
            if role != writer:
                errors.append(
                    f"record.role: only the roster's sole_writer ({writer!r}) may "
                    f"write a {kind}; got {role!r}"
                )
        if kind in (EXECUTED, PROJECT, AMEND):
            # The executor writes these for routed steps; the store refuses
            # the sole writer for a routed type (it needs the ruling's type).
            writer, runner = sole_writer(), executor()
            if role not in (writer, runner):
                errors.append(
                    f"record.role: only the roster's sole_writer ({writer!r}) or "
                    f"executor ({runner!r}) may write a {kind}; got {role!r}"
                )
        if kind == CLOSE and role != executor():
            errors.append(
                f"record.role: only the roster's executor ({executor()!r}) may "
                f"write a close; got {role!r}"
            )
        if kind == ASK and role not in ASK_ROLES:
            errors.append(
                f"record.role: only {ASK_ROLES} may write an ask; got {role!r}"
            )
        if kind == ANSWER and role != ANSWER_ROLE:
            errors.append(
                f"record.role: only {ANSWER_ROLE!r} may write an answer; got {role!r}"
            )
        if kind == OBSERVATION and role != OBSERVATION_ROLE:
            errors.append(
                f"record.role: only {OBSERVATION_ROLE!r} may write an observation; "
                f"got {role!r}"
            )

    if "cycle" not in record:
        errors.append("record.cycle: required field is missing")
    else:
        cycle = record["cycle"]
        if isinstance(cycle, bool) or not isinstance(cycle, int):
            errors.append("record.cycle: expected an integer")

    if "snapshot" not in record:
        errors.append("record.snapshot: required field is missing")
    else:
        snapshot = record["snapshot"]
        if not isinstance(snapshot, str) or not snapshot:
            errors.append("record.snapshot: expected a non-empty string")

    if kind == PROPOSAL:
        _validate_proposal_fields(record, role, errors)
    elif kind == PASS:
        _validate_text_field(record, "reason", errors)
    elif kind == RULING:
        _validate_ruling_fields(record, errors)
    elif kind == EXECUTED:
        _validate_executed_fields(record, errors)
    elif kind == ASK:
        _validate_ask_fields(record, errors)
    elif kind == ANSWER:
        _validate_answer_fields(record, errors)
    elif kind == ESCALATION:
        _validate_text_field(record, "reason", errors)
    elif kind == PROJECT:
        _validate_project_fields(record, errors)
    elif kind == OBSERVATION:
        _validate_observation_fields(record, errors)
    elif kind == AMEND:
        _validate_amend_fields(record, errors)
    elif kind == ABANDON:
        _validate_abandon_fields(record, errors)
    elif kind == CLOSE:
        _validate_close_fields(record, errors)

    return errors
