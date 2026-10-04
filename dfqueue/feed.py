"""The stream page's data layer: public and operator projections of the
queue, built as pure functions over already-loaded records.

`research/2026-10-01-stream-page-design.md` is the design this implements,
slice S0 (design §8, `handoffs/2026-10-01-stream-page-s0.md`): "everything
that can be built and seen locally with no live access." This module is the
**publisher's core logic**, deliberately kept separate from any live
transport (VM 103's SSH push, a running server) so it can be tested against
static JSONL and used unchanged once a real publisher (slice S1) exists.

## What this module does NOT do

- **It never writes to the queue.** Only reads: `load_records_readonly`
  opens SQLite in read-only mode (`file:...?mode=ro`) and never calls
  `dfqueue.store._connect`, which runs `_ensure_schema` and could create or
  migrate tables on a bare open (design §4.1: "the publisher is read only").
- **It does not add fields to the schema.** Design §3.3 lists several
  additions (`seq`, `run_id`, `reply_to`, `about`, hold codes, `public_title`,
  new kinds `wake`/`run`/`goal`/`review`/`message`/`alarm`) that are not
  stored yet. Everywhere one of those would be read, this module either
  derives the same information from what already exists (§3.4: `reply_to`
  and `thread` for the kinds that already carry a link) or leaves a
  `NAMED GAP` comment and returns `None`/omits the field, never inventing
  data. See the module-level `GAPS` list below for the complete inventory.
- **It does not touch `dfqueue/schema.py` or `dfqueue/store.py`**, per this
  slice's handoff.

## The one item model (design §3.2)

Every record becomes at most one **item**: `seq` (position in append order;
see `GAPS` — a real `seq` column does not exist yet, so this is the
record's position in `rowid` order, which is the best available total order
today but is NOT guaranteed stable across a `VACUUM`, the same caveat design
§3.3 item 1 raises), `id`, `kind`, `role`, `speaker` (a display name),
`tick` (the absolute game tick, from `cycle`), `game_date` (rendered),
`ts`, `reply_to` (derived, §3.4), `thread` (derived, §3.4), `badge`
(derived for proposals only, §6.3).

## Two projections, one allowlist each (design §3.5, §3.6)

`build_public_item` returns `None` for a record that must never appear in
the public feed (`observation`, and any kind with no public text and no
public metadata at all), or a dict whose keys are a strict subset of
`PUBLIC_ITEM_FIELDS` — enforced by an assertion, not just a convention, the
same "allowlist, not a redaction" rule `dfqueue/render.py` already applies
to `ALLOWED_PUBLIC_FIELDS`.

`build_operator_item` carries the full record (minus nothing in this slice —
the call-log `client` field design §3.6 says to drop does not exist yet, S0
has no call-log join at all) plus the same derived fields.

## Safety net: withholding, never editing (design §7.2 layers 3/4)

`find_unsafe_pattern` is this slice's stand-in for the write-time refusal
(layer 3, belongs in `dfqueue/schema.py`, not built in this slice) and the
publish-time canary (layer 4, needs a gitignored `infra/local.*` secrets
list this repo does not ship). Applied here, at publish time, to every piece
of *public* text this module generates or allows through: a hit withholds
the item (`text` becomes `None`, `withheld: true`, `withheld_reason` names
the *category* matched, never the matched text itself) rather than editing
or dropping the item outright. This is deliberately conservative (a false
positive costs one withheld line, same trade `schema.py`'s own coordinate
regex makes) and deliberately NOT the full layer-4 canary (no real secrets
list to check against locally, and there must never be one committed to
this public repo).

## File layout (design §4.2)

`segment_items` splits an item list into immutable, content-hashed 200-item
segments plus one open (mutable-until-closed) remainder; `build_head`
builds the tiny state file the page polls; `write_feed` writes the whole
`data/public/` or `data/operator/` layout to a directory. Deterministic:
the same items always produce the same bytes (design §4.1's "given the same
records the publisher writes the same bytes").
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from . import feed_status
from .schema import (
    ABANDON, ACCEPT, AMEND, ANSWER, ASK, DEFER, ESCALATION, EXECUTED,
    OBSERVATION, PASS, PROJECT, PROPOSAL, REJECT, RULING,
)

# ---- named gaps -----------------------------------------------------------
#
# Read this before trusting any field this module does not carry. Each gap
# names the design section that would close it and which later slice (design
# §8) is expected to build it. Kept as data, in one place, rather than
# scattered "TODO" comments, so a future slice can grep this list to find
# every place S0 stood in for something not yet real.

GAPS = [
    "seq (design §3.3 item 1): not a stored column yet; this module uses "
    "rowid/append order as a stand-in, which store.py's own docstring warns "
    "is not VACUUM-stable. Closed by slice S2.",
    "run_id (design §3.3 item 2): not stamped anywhere yet; operator items "
    "carry run_id: null and no per-item tool-call join. Closed by slice S2.",
    "reply_to/about as STORED fields (design §3.3 items 3-4): a proposal, "
    "pass, ask and escalation have no stored reply_to/about, so this module "
    "can only derive reply_to for the kinds that already carry a native "
    "link (ruling, answer, executed, project, amend, abandon, observation). "
    "A commission's proposal-side reply_to, and any ask/escalation `about`, "
    "read as null until slice S2/S5 add the columns.",
    "hold codes (design §3.3 item 7): read when present (dfqueue.feed_status"
    ".step_hold_text), mapped through dfqueue/public_text.yaml (the sibling "
    "stream's own file, handoffs/2026-10-02-queue-display-fields.md) when "
    "that file exists and names the code. A held step with no hold_code at "
    "all, or a code the yaml file does not (yet) map, still shows as "
    "on-hold on the board, just with no reason text -- never a guessed one.",
    "public_title/label/public_rationale on project, amend, abandon "
    "(design §3.3 item 6): read when present (handoffs/2026-10-02-stream-"
    "board.md). A project/amend/abandon chat item's own `text` is still "
    "null when public_rationale is absent -- no summary fallback for the "
    "chat line, only for projects.json's own display `name` (truncated "
    "summary; see build_projects_view).",
    "new kinds wake/run/goal/review/message/alarm (design §3.3 item 8): no "
    "writer exists for any of them yet, so no real record of these kinds "
    "can appear in a queue export this module reads. This module raises "
    "ValueError on an unrecognised kind rather than silently rendering "
    "nothing, so the day a real one appears in an export it is caught, not "
    "silently dropped.",
    "fort status (design §3.1, feed.status): no per-cycle status push "
    "exists; build_placeholder_status() is the only status.json this slice "
    "can produce.",
    "project step-level counts (dfqueue.store.project_status's own "
    "step_targets-table read): build_projects_view now reports per-step "
    "state and target counts via dfqueue.feed_status.step_board_states, "
    "computed straight from records (executed actions, not the step_targets "
    "table, which this records-only reader never sees) rather than via "
    "store.project_status. The two should always agree where both apply; "
    "they are not cross-checked against each other anywhere.",
    "call-log join (design §3.6): dfmcp's journald call log is not read by "
    "this module at all in S0; operator items carry no per-item tool calls.",
]


# ---- display names ----------------------------------------------------------

#: The user's chosen display name on both the public and operator pages
#: (user's decision, 2026-10-01, relayed mid-stream). One constant, never a
#: scattered literal — every place a `user`/`human`-authored record's
#: speaker name is needed reads this, so the day the `human` roster kind
#: (design §3.3 item 8) exists, only this line changes.
USER_DISPLAY_NAME = "Will"

#: role (as stored in `agents/ROSTER.yaml` and every record's own `role`
#: field) -> the display name shown as the item's speaker. `conductor` shows
#: as "System" per design §6.3 ("Step completions are the System speaking").
ROLE_DISPLAY_NAMES = {
    "overseer": "Overseer",
    "architect": "Architect",
    "consultant": "Consultant",
    "quartermaster": "Quartermaster",
    "conductor": "System",
    "marshal": "Marshal",
    "chronicler": "Chronicler",
    # Not yet a real roster role (design §3.3 item 8's `human` kind) — kept
    # here so a `role: "user"` record, if one is ever hand-built before that
    # roster entry exists, still renders with the right name rather than a
    # raw role string.
    "user": USER_DISPLAY_NAME,
}


def role_display_name(role: Optional[str]) -> str:
    """A speaker's display name, falling back to a capitalised role string
    for anything not in `ROLE_DISPLAY_NAMES` (a disabled or future role)
    rather than raising — an item with an unrecognised role should still
    render, just without a curated name."""
    if not role:
        return "Unknown"
    return ROLE_DISPLAY_NAMES.get(role, role.capitalize())


def humanize_type(type_str: Optional[str]) -> Optional[str]:
    """`workshop_siting` -> `Workshop siting`. Used only as a proposal's
    public `type` label (design §3.5's "type as a label"), never for a tool
    id or any field that could leak call structure."""
    if not type_str:
        return None
    return type_str.replace("_", " ").capitalize()


# ---- game calendar (design §6.2 item 9) -------------------------------------
#
# 1,200 ticks/day, 28-day months, 12 months/year, 403,200 ticks/year — the
# design doc's own figures, itself flagged §11 "not read from this install."
# Kept here as the one place that constant set lives.

TICKS_PER_DAY = 1200
DAYS_PER_MONTH = 28
MONTHS_PER_YEAR = 12
TICKS_PER_YEAR = TICKS_PER_DAY * DAYS_PER_MONTH * MONTHS_PER_YEAR

#: Vanilla Dwarf Fortress month names, in order. **Unverified against this
#: specific install** (design §11's own caveat, carried over unchanged): this
#: is the standard vanilla calendar as commonly known, not read from a live
#: fort.
MONTH_NAMES = (
    "Granite", "Slate", "Felsite", "Hematite", "Malachite", "Galena",
    "Limestone", "Sandstone", "Timber", "Moonstone", "Opal", "Obsidian",
)


def render_game_date(tick: Optional[int]) -> Optional[str]:
    """"12 Limestone, year 31" from an absolute game tick, or `None` if
    `tick` is `None`. The year is the game's own `cur_year`
    (abs tick = cur_year * 403,200 + cur_year_tick, so year = tick // 403,200
    with no offset: 12,746,121 is year 31, tick 246,921); days-of-month are
    1-based."""
    if tick is None:
        return None
    year = tick // TICKS_PER_YEAR
    day_in_year = tick % TICKS_PER_YEAR
    day_of_month = (day_in_year // TICKS_PER_DAY) % DAYS_PER_MONTH
    month_index = (day_in_year // TICKS_PER_DAY) // DAYS_PER_MONTH
    month_index = min(month_index, MONTHS_PER_YEAR - 1)  # defensive clamp
    return f"{day_of_month + 1} {MONTH_NAMES[month_index]}, year {year}"


# ---- reply_to / thread (design §3.4) ----------------------------------------


def compute_reply_to(record: dict) -> Optional[str]:
    """The link this record already carries under another name, per design
    §3.4's list of kinds derivable from an EXISTING field (never a stored
    `reply_to` — that column does not exist, see `GAPS`). `proposal`,
    `pass`, `ask` (unless it names `proposal_id`, its fact-check link) and
    `escalation` have no derivable reply_to today and return `None`,
    matching design §2's own table of "what has no link is exactly what the
    brief suspected."""
    kind = record.get("kind")
    if kind == RULING:
        return record.get("proposal_id")
    if kind == ANSWER:
        return record.get("ask_id")
    if kind == EXECUTED:
        return record.get("ruling_id")
    if kind == PROJECT:
        return record.get("from_ruling")
    if kind in (AMEND, ABANDON, OBSERVATION):
        return record.get("project_id")
    if kind == ASK:
        # `docs/AGENT-ARCHITECTURE.md`'s fact-check exception: an ask that
        # names `proposal_id` IS about that proposal. A plain lookup ask
        # (no `proposal_id`) has no derivable link, same as `pass`.
        return record.get("proposal_id")
    return None


def compute_thread(item_id: str, reply_to_by_id: dict) -> str:
    """Follow `reply_to` to the root, per design §3.4: "Because `reply_to`
    never changes, the thread root never changes, so a published item never
    needs rewriting." Guarded against a cycle (should never occur — every
    reply_to above points strictly backward in append order — but a
    guard costs nothing and a silent infinite loop is worse than a wrong
    answer)."""
    seen = set()
    current = item_id
    while True:
        if current in seen:
            return current  # cycle guard; should not happen
        seen.add(current)
        nxt = reply_to_by_id.get(current)
        if not nxt:
            return current
        current = nxt


# ---- verdict badges (design §6.3) -------------------------------------------

_DECISION_BADGES = {ACCEPT: "accepted", REJECT: "rejected", DEFER: "deferred"}


def build_proposal_badges(records: list[dict]) -> dict:
    """proposal_id -> "pending"/"accepted"/"rejected"/"deferred", the LATEST
    ruling's decision (a `defer` can be followed by another ruling; only
    `accept`/`reject` are final, `dfqueue/store.py`'s own `FINAL_DECISIONS`).
    Records are assumed already in append order (`load_records_readonly`'s
    contract), so "latest" is simply "last seen"."""
    badges: dict[str, str] = {}
    for r in records:
        if r.get("kind") == RULING:
            pid = r.get("proposal_id")
            decision = r.get("decision")
            if pid:
                badges[pid] = _DECISION_BADGES.get(decision, decision)
    return badges


# ---- the unsafe-text check (design §7.2, layers 3/4 stand-in) --------------

_UNSAFE_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("url", re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.\-]{1,15}://\S+")),
    (
        "domain",
        re.compile(
            r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
            r"(?:com|net|org|io|dev|co|app|gov|edu|info|biz|local|lan|"
            r"internal|home|arpa|xyz)\b",
            re.IGNORECASE,
        ),
    ),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("ipv6", re.compile(r"\b[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{0,4}){5,}\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("unix_path", re.compile(r"(?:^|[\s(])/(?:[\w.\-]+/){1,}[\w.\-]+")),
    ("windows_path", re.compile(r"\b[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]+")),
    (
        "markup",
        re.compile(r"<[^>\s]+>|`[^`]+`|\[[^\]]+\]\([^)]+\)"),
    ),
    # A long unbroken run of letters/digits/-/_ — token- or hash-shaped.
    # Conservative length (24) so ordinary long compound words rarely trip
    # it; a false positive here costs one withheld line, never a leak.
    ("token", re.compile(r"\b[A-Za-z0-9_-]{24,}\b")),
)


def find_unsafe_pattern(text: Optional[str]) -> Optional[str]:
    """The name of the first category `text` matches (`"url"`, `"domain"`,
    `"ipv4"`, `"ipv6"`, `"email"`, `"unix_path"`, `"windows_path"`,
    `"markup"`, `"token"`), or `None` if it looks safe to publish. Never
    returns the matched substring itself — the caller must not echo the
    very thing being withheld."""
    if not text:
        return None
    for name, pattern in _UNSAFE_PATTERNS:
        if pattern.search(text):
            return name
    return None


# ---- executed items: which job, how many targets, how it went --------------

#: Words an executed item's `step_outcome` may take. The page words them
#: ("finished", "started", "tried and failed to start"); nothing else about
#: the tool call (its id, arguments, raw detail) is ever public.
STEP_OUTCOMES = ("started", "finished", "failed")


def _steps_by_id(records: list[dict]) -> dict:
    """step id -> the step dict, from every project's first version, then
    each amend's replacement plan in append order (a later version's step of
    the same id wins)."""
    out: dict[str, dict] = {}
    for r in records:
        if r.get("kind") in (PROJECT, AMEND):
            for step in r.get("steps") or []:
                if isinstance(step, dict) and isinstance(step.get("id"), str):
                    out[step["id"]] = step
    return out


def executed_step_info(record: dict, ctx: dict) -> dict:
    """What a public `executed` item may say about its job: `step_label`
    (the agent-written display label, or the humanised tool id, run through
    the same safety net as every other public text; `None` when unsafe or
    when the record names no step), `step_targets` (targets this record
    acted on), `step_total` (the step's literal target count, `None` when
    its targets are dynamic) and `step_outcome` (see `STEP_OUTCOMES`)."""
    step = (ctx.get("steps_by_id") or {}).get(record.get("step_id"))
    label = _safe_public_text(feed_status.step_public_label(step)) if step else None
    actions = [a for a in (record.get("actions") or []) if isinstance(a, dict)]
    targets = sum(len(a.get("targets") or []) for a in actions)
    literal = feed_status._literal_targets(step) if step else None
    if any(a.get("outcome") not in (None, "success") for a in actions):
        outcome = "failed"
    elif actions and all(a.get("target_state") == "done" for a in actions):
        outcome = "finished"
    else:
        outcome = "started"
    return {
        "step_label": label,
        "step_targets": targets,
        "step_total": len(literal) if literal is not None else None,
        "step_outcome": outcome,
    }


# ---- public text per kind (design §3.5) -------------------------------------


def _proposal_public_text(record: dict, ctx: dict) -> Optional[str]:
    return record.get("public_rationale")


def _ruling_public_text(record: dict, ctx: dict) -> Optional[str]:
    decision = record.get("decision")
    label = {"accept": "Accepted", "reject": "Rejected", "defer": "Deferred"}.get(
        decision, (decision or "Ruled").capitalize()
    )
    rationale = record.get("public_rationale")
    if not rationale:
        return label
    # A rationale that already opens with its own verdict ("Rejected: ...")
    # is not prefixed twice.
    if rationale.lower().startswith(label.lower()):
        return rationale
    return f"{label}: {rationale}"


def _executed_public_text(record: dict, ctx: dict) -> Optional[str]:
    # Step labels (design §3.3 item 6, project.steps[].label) do not exist
    # yet (GAPS) — never the tool id or arguments, so this is generic until
    # slice S4.
    return "A step was completed."


def _ask_public_text(record: dict, ctx: dict) -> Optional[str]:
    asker = role_display_name(record.get("role"))
    return f"The {asker} asked the Consultant a question."


def _answer_public_text(record: dict, ctx: dict) -> Optional[str]:
    asks_by_id = ctx.get("records_by_id", {})
    ask = asks_by_id.get(record.get("ask_id"))
    asker = role_display_name(ask.get("role")) if ask else "an advisor"
    return f"The Consultant answered the {asker}'s question."


def _pass_public_text(record: dict, ctx: dict) -> Optional[str]:
    role = role_display_name(record.get("role"))
    return f"The {role} had nothing to propose."


def _escalation_public_text(record: dict, ctx: dict) -> Optional[str]:
    return "The Overseer has asked the user for help."


def _project_amend_abandon_public_text(record: dict, ctx: dict) -> Optional[str]:
    # design §3.3 item 6's `public_rationale`, when the Overseer wrote one.
    # Never a fallback to `summary`, `because` or `reason`, which are
    # written for the model audience, not the public one (design §3.5's own
    # "never public" column) -- the ONE fallback this slice's handoff grants
    # (a truncated `summary` as a display NAME) is projects.json's own
    # concern (see `_public_display_name` below), not this chat line's text.
    return record.get("public_rationale")


PUBLIC_TEXT_BUILDERS = {
    PROPOSAL: _proposal_public_text,
    RULING: _ruling_public_text,
    EXECUTED: _executed_public_text,
    ASK: _ask_public_text,
    ANSWER: _answer_public_text,
    PASS: _pass_public_text,
    ESCALATION: _escalation_public_text,
    PROJECT: _project_amend_abandon_public_text,
    AMEND: _project_amend_abandon_public_text,
    ABANDON: _project_amend_abandon_public_text,
    # OBSERVATION is handled by `build_public_item` returning None before
    # any text builder would be consulted (design §3.5: "no line").
}

#: Every field a public item may ever carry. Enforced by assertion in
#: `build_public_item` — the same "allowlist, not a redaction" contract as
#: `dfqueue/render.py`'s `ALLOWED_PUBLIC_FIELDS`, restated here because this
#: is a distinct item shape (a chat line), not a raw record view.
PUBLIC_ITEM_FIELDS = frozenset({
    "seq", "id", "kind", "role", "speaker", "type", "tick", "game_date",
    "ts", "reply_to", "thread", "text", "badge", "withheld",
    "withheld_reason", "step_label", "step_targets", "step_total",
    "step_outcome",
})

#: Kinds this module knows how to render at all, public or operator side.
#: An unrecognised kind is refused loudly (see `GAPS`'s "new kinds" entry)
#: rather than silently skipped, so a future writer (wake/run/goal/review/
#: message/alarm) is caught the moment it appears in a real export instead
#: of vanishing from the feed.
KNOWN_KINDS = frozenset({
    PROPOSAL, PASS, RULING, EXECUTED, ASK, ANSWER, ESCALATION, PROJECT,
    OBSERVATION, AMEND, ABANDON,
})


def build_public_item(record: dict, *, seq: int, reply_to: Optional[str],
                       thread: str, badge: Optional[str],
                       ctx: dict) -> Optional[dict]:
    """The public view of one record as a chat item, or `None` if this kind
    never appears publicly at all (`observation`: design §3.5, "no line;
    feeds progress only")."""
    kind = record.get("kind")
    if kind not in KNOWN_KINDS:
        raise ValueError(
            f"feed.build_public_item: unrecognised kind {kind!r} — a new "
            "kind (design §3.3 item 8) needs its own public/operator "
            "rendering added here, not a silent pass-through"
        )
    if kind == OBSERVATION:
        return None

    tick = record.get("cycle")
    out: dict[str, Any] = {
        "seq": seq,
        "id": record.get("id"),
        "kind": kind,
        "role": record.get("role"),
        "speaker": role_display_name(record.get("role")),
        "tick": tick,
        "game_date": render_game_date(tick),
        "ts": record.get("ts"),
        "reply_to": reply_to,
        "thread": thread,
        "badge": badge,
    }
    if kind == PROPOSAL:
        out["type"] = humanize_type(record.get("type"))
    if kind == EXECUTED:
        out.update(executed_step_info(record, ctx))

    builder = PUBLIC_TEXT_BUILDERS.get(kind)
    text = builder(record, ctx) if builder else None
    if text is not None:
        unsafe = find_unsafe_pattern(text)
        if unsafe is not None:
            out["text"] = None
            out["withheld"] = True
            out["withheld_reason"] = unsafe
        else:
            out["text"] = text
    else:
        out["text"] = None

    assert set(out) <= PUBLIC_ITEM_FIELDS, (
        f"feed.build_public_item: {kind!r} item carries a field outside "
        f"PUBLIC_ITEM_FIELDS: {set(out) - PUBLIC_ITEM_FIELDS}"
    )
    return out


def build_operator_item(record: dict, *, seq: int, reply_to: Optional[str],
                         thread: str, badge: Optional[str], ctx: Optional[dict] = None) -> dict:
    """The operator view: the full record under `record`, PLUS the same
    flat, kind-dispatchable shape the public item has (`kind`/`id`/`role`/
    `type`/`text`), so page code (the stream board included) can treat a
    public and an operator item identically without special-casing which
    projection it is reading -- it only needs the full `record` for a
    detail an operator specifically wants. `text` reuses the same per-kind
    builder the public item uses (no `find_unsafe_pattern` withholding: the
    operator is a trusted internal viewer, and the raw `record` already
    carries everything anyway); the richer private rationale an operator
    might eventually see instead of the public one is a named gap, not
    built this slice. `run_id` is always `None` in this slice (GAPS — no
    per-run header exists yet); no call-log join exists yet either (GAPS)."""
    kind = record.get("kind")
    if kind not in KNOWN_KINDS:
        raise ValueError(
            f"feed.build_operator_item: unrecognised kind {kind!r}"
        )
    tick = record.get("cycle")
    builder = PUBLIC_TEXT_BUILDERS.get(kind)
    text = builder(record, ctx or {}) if builder else None
    extra = executed_step_info(record, ctx or {}) if kind == EXECUTED else {}
    return {
        **extra,
        "seq": seq,
        "id": record.get("id"),
        "kind": kind,
        "role": record.get("role"),
        "type": humanize_type(record.get("type")) if kind == PROPOSAL else None,
        "text": text,
        "reply_to": reply_to,
        "thread": thread,
        "badge": badge,
        "speaker": role_display_name(record.get("role")),
        "tick": tick,
        "game_date": render_game_date(tick),
        "run_id": None,
        "calls": [],
        "record": record,
    }


# ---- project display fields (design §3.3 item 6/7, handoffs/2026-10-02- --
# ---- stream-board.md) -------------------------------------------------------

#: The closed urgency vocabulary a project may carry (design register
#: 2026-10-02, "Stream page look"). Anything else (missing, misspelled,
#: written by a future role that gets it wrong) reads as unknown, never
#: guessed up or down to the nearest known value.
URGENCY_VALUES = ("normal", "elevated", "high")

#: `name` is a display concern, not a chat line, so it gets its own, more
#: generous budget than a single message — long enough that a truncated
#: `summary` fallback still reads as a sentence fragment, not a word salad.
_DISPLAY_NAME_MAX = 72


def _sanitize_urgency(value: Any) -> Optional[str]:
    """`value` if it is one of `URGENCY_VALUES`, else `None` -- never a
    best-guess normalisation of something close (`"High"`, `"urgent"`)."""
    return value if value in URGENCY_VALUES else None


def _safe_public_text(text: Optional[str]) -> Optional[str]:
    """`text` unless `find_unsafe_pattern` would withhold it, in which case
    `None` -- the same conservative "a false positive costs one withheld
    line" trade the chat-item safety net makes, applied to projects.json's
    own display fields too (they are just as public)."""
    if text is None:
        return None
    return None if find_unsafe_pattern(text) is not None else text


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _public_display_name(record: dict) -> Optional[str]:
    """A project's public display name: `public_title` (design §3.3 item 6)
    when the Overseer wrote one and it looks safe, else a truncated
    `summary` (this handoff's own named fallback -- `summary` is written for
    the model audience, but is the only candidate text a project always
    has, and the user explicitly asked for it as the LAST-resort display
    name, never as the chat line's own body text). `None` only when neither
    exists or both are unsafe."""
    title = _safe_public_text(record.get("public_title"))
    if title:
        return title
    summary = record.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None
    return _safe_public_text(_truncate(summary.strip(), _DISPLAY_NAME_MAX))


def _public_board_steps(records: list[dict], project_id: str) -> list[dict]:
    """`feed_status.step_board_states`'s steps, with the private
    `held_detail` field stripped (public projection never gets the tool's
    raw refusal text — design §3.3 item 7)."""
    steps = feed_status.step_board_states(records, project_id)
    return [{k: v for k, v in s.items() if k != "held_detail"} for s in steps]


# ---- projects.json (design §4.2, §3.4's thread-to-project map) -------------


def build_projects_view(records: list[dict], *, public: bool) -> dict:
    """`{"thread_to_project": {...}, "projects": {...}}`. The
    thread-to-project map lets the page resolve a proposal or ruling's own
    `thread` id to the project it (retroactively) founded, per design §3.4,
    without ever rewriting the proposal/ruling item itself.

    Each project entry carries what the stream board needs (handoffs/
    2026-10-02-stream-board.md): `status` (active/hold/done/abandoned,
    `dfqueue.feed_status.project_board_status`), `name` and `description`
    (the card's own title and one-liner; `description` is the raw
    `public_rationale`, already safety-checked on the public side) and
    `urgency` (sanitised, `None` when unknown), `ruling_id`/`proposal_id`
    (ids only), and `steps` (`dfqueue.feed_status.step_board_states`, public
    copy with `held_detail` stripped). The operator projection additionally
    carries the raw `summary`, `public_title`, `public_rationale`, `urgency`
    as written (even if outside the known enum, so a bad write is visible to
    an operator rather than silently hidden), `abandoned_reason`, and the
    steps' own `held_detail`."""
    reply_to_by_id = {r["id"]: compute_reply_to(r) for r in records if r.get("id")}
    rulings_by_id = {r["id"]: r for r in records if r.get("kind") == RULING and r.get("id")}
    public_text = feed_status.load_public_text() if public else {}

    projects: dict[str, dict] = {}
    thread_to_project: dict[str, str] = {}
    for r in records:
        if r.get("kind") != PROJECT:
            continue
        pid = r["id"]
        thread_to_project[compute_thread(pid, reply_to_by_id)] = pid
        ruling_id = r.get("from_ruling")
        ruling = rulings_by_id.get(ruling_id)
        entry: dict[str, Any] = {
            "id": pid,
            "version": 1,
            "abandoned": False,
            "urgency": _sanitize_urgency(r.get("urgency")) if public else r.get("urgency"),
            "ruling_id": ruling_id,
            "proposal_id": ruling.get("proposal_id") if ruling else None,
        }
        if public:
            entry["name"] = _public_display_name(r)
            entry["description"] = _safe_public_text(r.get("public_rationale"))
        else:
            entry["name"] = r.get("public_title") or r.get("summary")
            entry["description"] = r.get("public_rationale")
            entry["from_ruling"] = ruling_id
            entry["summary"] = r.get("summary")
            entry["public_title"] = r.get("public_title")
            entry["public_rationale"] = r.get("public_rationale")
        projects[pid] = entry

    for r in records:
        kind = r.get("kind")
        pid = r.get("project_id")
        if pid not in projects:
            continue
        if kind == AMEND:
            projects[pid]["version"] += 1
        elif kind == ABANDON:
            projects[pid]["abandoned"] = True
            if not public:
                projects[pid]["abandoned_reason"] = r.get("reason")
            # else: an abandoned project's public reason is `abandon`'s own
            # `public_rationale` (design §3.3 item 6), surfaced through the
            # project's chat item (build_public_item), not duplicated here.

    for pid in projects:
        steps = (
            _public_board_steps(records, pid) if public
            else feed_status.step_board_states(records, pid)
        )
        projects[pid]["steps"] = steps
        projects[pid]["status"] = feed_status.project_board_status(records, pid)
        if public:
            for step in steps:
                if step.get("state") == "hold":
                    text, code = feed_status.step_hold_text(
                        records, pid, step["id"], public_text,
                    )
                    if code:
                        step["hold_code"] = code
                    if text:
                        step["hold_text"] = text
                    # No code at all, or a code with no mapped text yet:
                    # the step still reads "hold" from its own `state` --
                    # never a guessed reason (this handoff's own rule).

    return {"thread_to_project": thread_to_project, "projects": projects}


def build_placeholder_status() -> dict:
    """No `feed.status` push exists yet (design §3.1, GAPS). This is the
    only status.json S0 can honestly produce: a flag the page reads to show
    "no live status yet" rather than fabricating a right-now line."""
    return {
        "available": False,
        "note": (
            "fort status (design §3.1's feed.status tool) is not built "
            "yet; this is local test data with no live source."
        ),
    }


# ---- building the item stream (design §3.2, §3.4) ---------------------------


def build_items(records: list[dict], *, public: bool) -> list[dict]:
    """Every record in `records` (already in append order — the contract
    `load_records_readonly`/`load_records_jsonl` both honour) turned into at
    most one item, public or operator projection per `public`. `seq` is
    1-based position in that order (GAPS: stand-in for a real `seq`
    column)."""
    reply_to_by_id = {r["id"]: compute_reply_to(r) for r in records if r.get("id")}
    badges = build_proposal_badges(records)
    records_by_id = {r["id"]: r for r in records if r.get("id")}
    ctx = {"records_by_id": records_by_id, "steps_by_id": _steps_by_id(records)}

    items: list[dict] = []
    for i, record in enumerate(records, start=1):
        rid = record.get("id")
        reply_to = reply_to_by_id.get(rid)
        thread = compute_thread(rid, reply_to_by_id) if rid else rid
        badge = badges.get(rid) if record.get("kind") == PROPOSAL else None
        if public:
            item = build_public_item(
                record, seq=i, reply_to=reply_to, thread=thread, badge=badge,
                ctx=ctx,
            )
        else:
            item = build_operator_item(
                record, seq=i, reply_to=reply_to, thread=thread, badge=badge,
                ctx=ctx,
            )
        if item is not None:
            items.append(item)
    return items


# ---- segmenting and file layout (design §4.2) -------------------------------

SEGMENT_SIZE = 200


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=None)


def segment_name(generation: int, first_seq: int, last_seq: int, body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]
    return f"{generation}-{first_seq}-{last_seq}-{digest}.json"


def segment_items(
    items: list[dict], *, size: int = SEGMENT_SIZE, generation: int = 1,
) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Split `items` (already in `seq` order) into closed, immutable,
    content-hashed segments of exactly `size` items each, plus the open
    remainder (design §4.2/§4.4). Returns `(closed, open_items)`, `closed`
    a list of `(filename, payload)` pairs. Deterministic: the same `items`
    always produce the same filenames and bytes."""
    closed: list[tuple[str, dict]] = []
    i = 0
    n = len(items)
    while n - i >= size:
        chunk = items[i:i + size]
        first_seq, last_seq = chunk[0]["seq"], chunk[-1]["seq"]
        payload = {
            "generation": generation, "first_seq": first_seq,
            "last_seq": last_seq, "items": chunk,
        }
        body = _canonical_json(payload)
        name = segment_name(generation, first_seq, last_seq, body)
        closed.append((name, payload))
        i += size
    return closed, items[i:]


def build_head(
    items: list[dict], *, generation: int, closed_segment_names: list[str],
    open_segment_name: str, seasons_index_name: str, published_at: str,
    state: str = "on",
) -> dict:
    """design §4.2's `head.json`: state, generation, last_seq, published_at,
    the open segment's name, the last 50 closed segments, the season index
    name."""
    last_seq = items[-1]["seq"] if items else 0
    return {
        "state": state,
        "generation": generation,
        "last_seq": last_seq,
        "published_at": published_at,
        "open_segment": open_segment_name,
        "closed_segments": closed_segment_names[-50:],
        "seasons_index": seasons_index_name,
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical_json(payload), encoding="utf-8")


def write_feed(
    items: list[dict], out_dir: Path, *, projects: dict,
    status: Optional[dict] = None, generation: int = 1, state: str = "on",
    published_at: Optional[str] = None,
) -> None:
    """Write one projection's whole `data/<public|operator>/` layout
    (design §4.2) to `out_dir`. Deterministic and idempotent: re-running
    with the same `items` overwrites with byte-identical files (design
    §4.1's rebuild property), except `head.json`'s own `published_at`."""
    out_dir = Path(out_dir)
    closed, open_items = segment_items(items, generation=generation)

    seg_dir = out_dir / "seg"
    for name, payload in closed:
        _write_json(seg_dir / name, payload)

    _write_json(out_dir / "open.json", {"generation": generation, "items": open_items})
    _write_json(
        out_dir / "seasons" / "index.json",
        {"seasons": []},  # design §6.6/§8 slice S7 — not built yet (GAPS)
    )
    head = build_head(
        items, generation=generation,
        closed_segment_names=[name for name, _ in closed],
        open_segment_name="open.json", seasons_index_name="seasons/index.json",
        published_at=published_at or _now_iso(), state=state,
    )
    _write_json(out_dir / "head.json", head)
    _write_json(out_dir / "projects.json", projects)
    if status is not None:
        _write_json(out_dir / "status.json", status)


# ---- multiple forts (register 2026-10-02, "plan for more than one fort") --
#
# The user's own addition to the stream-board handoff, mid-stream: nothing
# in this repo runs more than one fort today (Uniboslan/Ragwind is the only
# one, CLAUDE.md's own "Current state"), but the page's data layout should
# not assume there will only ever be one. `write_feed` above is unchanged
# and still writes exactly one fort's one projection's feed to whatever
# directory it is given; what changes is WHERE a caller points it
# (`<root>/forts/<fort_id>/...` instead of `<root>/...` directly) and that
# `<root>/forts.json` names every fort the page can pick from. Project-wide
# data that is not any one fort's (agents, tools, known gotchas) has no
# home built yet, but lives at `<root>/`, a sibling of `forts/`, never
# inside it -- this layout already leaves that room.


def fort_feed_dir(root_dir: str | Path, fort_id: str) -> Path:
    """Where one fort's feed lives under a projection root
    (`<root>/forts/<fort_id>/`). The one place this path shape is written
    down, so every caller (the export script, a future real publisher,
    their tests) agrees on it."""
    return Path(root_dir) / "forts" / fort_id


def build_forts_index(existing: list[dict], entry: dict) -> list[dict]:
    """Upsert `entry` (`{"id", "name", "status"}`, `status` one of
    `"live"`/`"lost"`) into `existing` (a prior `forts.json`'s own `"forts"`
    list), marking it `current` and every other entry NOT current -- a
    publisher only ever has one fort it is actively exporting, so that fort
    is always the one the page should default to opening. Returns a fresh
    list sorted by id (deterministic output, same rebuild property
    `write_feed`'s own docstring asks for)."""
    by_id = {f["id"]: dict(f) for f in existing if isinstance(f, dict) and f.get("id")}
    by_id[entry["id"]] = {
        "id": entry["id"], "name": entry["name"], "status": entry["status"],
        "current": True,
    }
    for fid, f in by_id.items():
        if fid != entry["id"]:
            f["current"] = False
    return [by_id[fid] for fid in sorted(by_id)]


def read_forts_index(root_dir: str | Path) -> list[dict]:
    """`<root>/forts.json`'s own `"forts"` list, or `[]` if the file does
    not exist yet (the very first export for this root)."""
    path = Path(root_dir) / "forts.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    forts = data.get("forts", [])
    return forts if isinstance(forts, list) else []


def write_forts_index(root_dir: str | Path, forts: list[dict]) -> None:
    _write_json(Path(root_dir) / "forts.json", {"forts": forts})


def write_fort_feed(
    items: list[dict], root_dir: str | Path, *, fort_id: str, fort_name: str,
    fort_status: str, projects: dict, status: Optional[dict] = None,
    generation: int = 1, state: str = "on", published_at: Optional[str] = None,
) -> None:
    """`write_feed`, plus maintaining `<root>/forts.json`: upserts this
    fort as the current one (`build_forts_index`) and writes its feed to
    `fort_feed_dir(root_dir, fort_id)`. The export script and any future
    real publisher call this instead of `write_feed` directly, so the two
    never drift on where a fort's files live."""
    root_dir = Path(root_dir)
    write_feed(
        items, fort_feed_dir(root_dir, fort_id), projects=projects,
        status=status, generation=generation, state=state, published_at=published_at,
    )
    forts = build_forts_index(
        read_forts_index(root_dir),
        {"id": fort_id, "name": fort_name, "status": fort_status},
    )
    write_forts_index(root_dir, forts)


# ---- loading records (read-only; never dfqueue.store._connect) -------------


def load_records_readonly(db_path: str | Path) -> list[dict]:
    """Every record in a live queue's `records` table, in `rowid` order —
    the same order/shape as `dfqueue.store.load()`, but opened strictly
    read-only (`file:...?mode=ro`, SQLite's own read-only URI mode) so this
    publisher-side reader can NEVER create, migrate or write the database,
    unlike `dfqueue.store._connect` (design §4.1's own requirement). Raises
    `sqlite3.OperationalError` if the database or its `records` table does
    not exist — deliberately not swallowed, since a publisher silently
    treating "no database" as "empty queue" would be a worse failure mode
    than crashing loudly."""
    uri = f"file:{Path(db_path).resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT payload FROM records ORDER BY rowid ASC"
        ).fetchall()
    finally:
        conn.close()
    return [json.loads(r["payload"]) for r in rows]


def load_records_jsonl(path: str | Path) -> list[dict]:
    """Every record from a `records.jsonl` export (`evals/live/*/queue-
    export/records.jsonl`, `dfqueue.store.export_jsonl`'s own output shape),
    in file order — the offline stand-in for `load_records_readonly` this
    slice's tests and the export script both use, since no live VM access
    exists here. Blank lines are skipped (matches `export_jsonl`'s own
    trailing-newline style, seen in the real exports)."""
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records
