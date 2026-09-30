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
    "hold codes (design §3.3 item 7): a held target's public text needs "
    "dfqueue/public_text.yaml (proposed) and a hold_code field neither of "
    "which exist; this module has no held-target rendering at all yet.",
    "public_title/label/public_rationale on project, amend, abandon "
    "(design §3.3 item 6): not stored yet, so project/amend/abandon items "
    "carry text: null on the public side. Closed by slice S4.",
    "new kinds wake/run/goal/review/message/alarm (design §3.3 item 8): no "
    "writer exists for any of them yet, so no real record of these kinds "
    "can appear in a queue export this module reads. This module raises "
    "ValueError on an unrecognised kind rather than silently rendering "
    "nothing, so the day a real one appears in an export it is caught, not "
    "silently dropped.",
    "fort status (design §3.1, feed.status): no per-cycle status push "
    "exists; build_placeholder_status() is the only status.json this slice "
    "can produce.",
    "project step-level counts/top_blocker (dfqueue.store.project_status): "
    "that function reads store._connect and the step_targets table; this "
    "module's read-only reader only reads the records table, so "
    "projects.json in this slice reports version/abandoned only, not "
    "per-target progress. A read-only equivalent of project_status is left "
    "for slice S1's publisher.",
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
    `tick` is `None`. Years are 1-based (year 0 does not appear in the
    game's own calendar); days-of-month are 1-based."""
    if tick is None:
        return None
    year = tick // TICKS_PER_YEAR
    day_in_year = tick % TICKS_PER_YEAR
    day_of_month = (day_in_year // TICKS_PER_DAY) % DAYS_PER_MONTH
    month_index = (day_in_year // TICKS_PER_DAY) // DAYS_PER_MONTH
    month_index = min(month_index, MONTHS_PER_YEAR - 1)  # defensive clamp
    return f"{day_of_month + 1} {MONTH_NAMES[month_index]}, year {year + 1}"


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


# ---- public text per kind (design §3.5) -------------------------------------


def _proposal_public_text(record: dict, ctx: dict) -> Optional[str]:
    return record.get("public_rationale")


def _ruling_public_text(record: dict, ctx: dict) -> Optional[str]:
    decision = record.get("decision")
    label = {"accept": "Accepted", "reject": "Rejected", "defer": "Deferred"}.get(
        decision, (decision or "Ruled").capitalize()
    )
    rationale = record.get("public_rationale")
    return f"{label}: {rationale}" if rationale else label


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


def _no_public_text(record: dict, ctx: dict) -> Optional[str]:
    # project / amend / abandon: public_title / public_rationale (design
    # §3.3 item 6) are not stored yet — GAPS. Never fall back to `summary`,
    # `because` or `reason`, which are written for the model audience, not
    # the public one (design §3.5's own "never public" column).
    return None


PUBLIC_TEXT_BUILDERS = {
    PROPOSAL: _proposal_public_text,
    RULING: _ruling_public_text,
    EXECUTED: _executed_public_text,
    ASK: _ask_public_text,
    ANSWER: _answer_public_text,
    PASS: _pass_public_text,
    ESCALATION: _escalation_public_text,
    PROJECT: _no_public_text,
    AMEND: _no_public_text,
    ABANDON: _no_public_text,
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
    "withheld_reason",
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
                         thread: str, badge: Optional[str]) -> dict:
    """The operator view: the full record plus the same derived fields.
    `run_id` is always `None` in this slice (GAPS — no per-run header
    exists yet); no call-log join exists yet either (GAPS)."""
    kind = record.get("kind")
    if kind not in KNOWN_KINDS:
        raise ValueError(
            f"feed.build_operator_item: unrecognised kind {kind!r}"
        )
    tick = record.get("cycle")
    return {
        "seq": seq,
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


# ---- projects.json (design §4.2, §3.4's thread-to-project map) -------------


def build_projects_view(records: list[dict], *, public: bool) -> dict:
    """`{"thread_to_project": {...}, "projects": {...}}`. The
    thread-to-project map lets the page resolve a proposal or ruling's own
    `thread` id to the project it (retroactively) founded, per design §3.4,
    without ever rewriting the proposal/ruling item itself.

    Per-target progress (`counts`, `top_blocker`, a `done`/`active` status)
    needs `dfqueue.store.project_status`, which reads `step_targets` through
    `store._connect` — out of scope for this read-records-only module (see
    `GAPS`). This slice reports only `version` (1 plus amend count) and
    `abandoned`/`abandoned_reason` (operator only — `abandoned_reason` is
    the private `reason` field, never public until design §3.3 item 6's
    `public_rationale` on abandon exists)."""
    reply_to_by_id = {r["id"]: compute_reply_to(r) for r in records if r.get("id")}

    projects: dict[str, dict] = {}
    thread_to_project: dict[str, str] = {}
    for r in records:
        if r.get("kind") != PROJECT:
            continue
        pid = r["id"]
        thread_to_project[compute_thread(pid, reply_to_by_id)] = pid
        entry: dict[str, Any] = {"id": pid, "version": 1, "abandoned": False}
        if not public:
            entry["from_ruling"] = r.get("from_ruling")
            entry["summary"] = r.get("summary")
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
            # else: public abandoned-project text is a design §3.3 item 6
            # gap (public_rationale on abandon) — no reason shown yet.

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
    ctx = {"records_by_id": records_by_id}

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
