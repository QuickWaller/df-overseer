"""dfqueue record schema: `proposal`, `pass`, `ruling`, `executed`, `ask`,
`answer`, `escalation`, validated at write time.

Implements `docs/AGENT-ARCHITECTURE.md` §4, "Writes are tool calls; reads are
XML": **a specialist cannot emit prose into the queue.** It calls
`propose(...)` (or, for the Overseer, rules) with typed fields, validated
here, and a malformed record is refused with every error listed rather than
silently accepted or silently trimmed.

Seven record kinds, per §4, `docs/AGENT-LOOP.md` items 4/7, and `agents/*/role.md`:

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

No `plan` record yet (§9's write-ahead-log record, "writes its ordered plan
to the queue before executing"). See `dfqueue/README.md`.

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

import re
from functools import lru_cache
from pathlib import Path

import yaml

from learning import live_signals
from learning.ledger.store import field_source as ledger_field_source
from learning.predictions.schema import PREDICATE_OPS, PRESENCE_OPS

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parent.parent
ROSTER_PATH = REPO_ROOT / "agents" / "ROSTER.yaml"

# ---- record kinds -----------------------------------------------------------

PROPOSAL, PASS, RULING = "proposal", "pass", "ruling"
EXECUTED, ASK, ANSWER = "executed", "ask", "answer"
#: Added handoffs/2026-09-22-loop-conductor-fixes.md item 3.
ESCALATION = "escalation"
KINDS = (PROPOSAL, PASS, RULING, EXECUTED, ASK, ANSWER, ESCALATION)

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

# ---- cost unit vocabulary, small and starting here ---------------------------

DWARF_TICKS = "dwarf_ticks"
COST_UNITS = (DWARF_TICKS,)

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
    ),
    PASS: ("reason",),
    RULING: ("decision", "proposal_id", "reason", "public_rationale"),
    EXECUTED: ("ruling_id", "actions", "notes"),
    ASK: ("question", "proposal_id"),
    ANSWER: ("ask_id", "answer"),
    ESCALATION: ("reason",),
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


def _validate_proposal_fields(record: dict, role, errors: list[str]) -> None:
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


def _validate_action(item, errors: list[str], prefix: str) -> None:
    if not isinstance(item, dict):
        errors.append(f"{prefix}: expected an object")
        return
    known = {"tool", "outcome", "detail"}
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


def _validate_executed_fields(record: dict, errors: list[str]) -> None:
    """`ruling_id`'s existence and its ruling's `decision` (must be
    `accept`) need the rest of the queue, so — same split as `ruling`'s own
    `proposal_id` — that check lives in `store.append()`, not here."""
    if "ruling_id" not in record:
        errors.append("record.ruling_id: required field is missing")
    else:
        rid = record["ruling_id"]
        if not isinstance(rid, str) or not rid:
            errors.append("record.ruling_id: expected a non-empty string")

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
        if kind in (RULING, EXECUTED, ESCALATION):
            writer = sole_writer()
            if role != writer:
                errors.append(
                    f"record.role: only the roster's sole_writer ({writer!r}) may "
                    f"write a {kind}; got {role!r}"
                )
        if kind == ASK and role not in ASK_ROLES:
            errors.append(
                f"record.role: only {ASK_ROLES} may write an ask; got {role!r}"
            )
        if kind == ANSWER and role != ANSWER_ROLE:
            errors.append(
                f"record.role: only {ANSWER_ROLE!r} may write an answer; got {role!r}"
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

    return errors
