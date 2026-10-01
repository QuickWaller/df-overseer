"""A read-only equivalent of `dfqueue.store.project_status`, for the stream
page publisher (slice S1, `handoffs/2026-10-01-stream-page-s1-prep.md`,
closing the gap `dfqueue/feed.py`'s own `GAPS` list names: "a read-only
equivalent of `dfqueue.store.project_status` for step-level progress
(S0's named gap), in a new module, without touching `store.py`").

`store.project_status` reads through `store._connect`, which runs
`_ensure_schema` on open and could create or migrate tables -- exactly the
write path design §4.1 forbids a publisher from touching ("the publisher
must open the queue with a read-only SQLite connection, not through
`dfqueue.store._connect`"). This module opens the same database file with
the same `file:...?mode=ro` URI `dfqueue.feed.load_records_readonly` already
uses, then runs the *same* status computation `store.project_status` does.

The computation itself is not re-derived here: `step_status`,
`_current_steps_and_version`, `_step_has_executed_record` and
`PROJECT_ABANDONED` are imported from `store` and called against this
module's own read-only connection. All three take a plain
`sqlite3.Connection` and perform only `SELECT`s -- they have no write side
effects of their own, so importing them is reading `store.py`'s logic, not
touching it (this handoff's own rule is "do not write
`dfqueue/schema.py`, `dfqueue/store.py`"; nothing here edits either file).
Duplicating `project_status`'s own query shape here, rather than its
connection acquisition, is deliberate: a second implementation of "which
step counts as done" would drift from `store.py`'s the first time one of
them changed, which is exactly the two-source-of-truth problem design §4.1
rejects for the publisher pipeline as a whole (one store, one publisher).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

import yaml

from .schema import (
    ABANDON, ABANDONED, AMEND, DONE, EXECUTED, HELD, ISSUED, OBSERVATION,
    PROJECT,
)
from .store import (
    PROJECT_ABANDONED,
    QueueError,
    _current_steps_and_version,
    _step_has_executed_record,
    step_status,
)


def _connect_readonly(path: str | Path) -> sqlite3.Connection:
    """Open `path` strictly read-only, same URI form as
    `dfqueue.feed.load_records_readonly` -- SQLite's own read-only URI mode,
    never `store._connect` (which runs `_ensure_schema`, a write, on open).
    Raises `sqlite3.OperationalError` if the file does not exist, same
    "do not swallow a missing database" choice `feed.load_records_readonly`
    makes."""
    uri = f"file:{Path(path).resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_project_ids_readonly(path: str | Path) -> list[str]:
    """Read-only equivalent of `store.list_project_ids`: every `project`
    record's own id, oldest first (insertion order)."""
    conn = _connect_readonly(path)
    try:
        rows = conn.execute(
            "SELECT id FROM records WHERE kind = ? ORDER BY rowid ASC", (PROJECT,)
        ).fetchall()
    finally:
        conn.close()
    return [r["id"] for r in rows]


def project_status_readonly(path: str | Path, project_id: str) -> dict:
    """Read-only equivalent of `store.project_status`: same return shape
    (`project_id`, `summary`, `status`, `version`, `counts`, `top_blocker`,
    and `abandoned_reason` when abandoned), computed the same way, over a
    read-only connection. See the module docstring for why the computation
    itself is imported rather than re-derived."""
    conn = _connect_readonly(path)
    try:
        proj_row = conn.execute(
            "SELECT payload FROM records WHERE id = ? AND kind = ?",
            (project_id, PROJECT),
        ).fetchone()
        if proj_row is None:
            raise QueueError(f"no such project: {project_id!r}")
        project = json.loads(proj_row["payload"])

        abandon_row = conn.execute(
            "SELECT payload FROM records WHERE kind = ? AND "
            "json_extract(payload, '$.project_id') = ?",
            (ABANDON, project_id),
        ).fetchone()

        steps, version = _current_steps_and_version(conn, project)

        rows = conn.execute(
            "SELECT id, step_id, target, state, reason FROM step_targets "
            "WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        ).fetchall()

        counts: dict[str, int] = {}
        top_blocker = None
        rows_by_step: dict = {}
        for r in rows:
            counts[r["state"]] = counts.get(r["state"], 0) + 1
            rows_by_step.setdefault(r["step_id"], []).append(r["state"])
            if top_blocker is None and r["state"] == HELD:
                top_blocker = {
                    "step_id": r["step_id"], "target": r["target"],
                    "reason": r["reason"],
                }

        if abandon_row is not None:
            status = PROJECT_ABANDONED
            abandoned_reason = json.loads(abandon_row["payload"]).get("reason")
        else:
            abandoned_reason = None
            ruling_id = project["from_ruling"]
            all_done = True
            for step in steps:
                if not (
                    isinstance(step, dict)
                    and isinstance(step.get("id"), str)
                    and step["id"]
                ):
                    continue
                own_rows = rows_by_step.get(step["id"], [])
                has_executed = own_rows == [] and _step_has_executed_record(
                    conn, ruling_id, step
                )
                if step_status(own_rows, has_executed) != DONE:
                    all_done = False
                    break
            status = DONE if all_done else "active"
    finally:
        conn.close()

    result = {
        "project_id": project_id,
        "summary": project.get("summary"),
        "status": status,
        "version": version,
        "counts": counts,
        "top_blocker": top_blocker,
    }
    if abandoned_reason is not None:
        result["abandoned_reason"] = abandoned_reason
    return result


def all_project_statuses_readonly(path: str | Path) -> dict[str, dict]:
    """Every project's status, keyed by id -- the publisher's one call per
    feed build, rather than enumerating ids and calling
    `project_status_readonly` once per id itself (same two-step shape
    `store.list_project_ids` plus `store.project_status` already uses, just
    bundled for a single-pass caller)."""
    return {
        pid: project_status_readonly(path, pid)
        for pid in list_project_ids_readonly(path)
    }


# ---- records-only step board state (stream board, handoffs/2026-10-02- ----
# ---- stream-board.md) ------------------------------------------------------
#
# Everything above this line needs a real SQLite file (it reads
# `step_targets`, which only exists once `store.append` has seeded it). The
# stream page's offline fixtures are plain `records.jsonl` -- no database,
# no `step_targets` table -- and `dfqueue.feed.load_records_readonly` itself
# only ever reads the `records` table even when a real database IS given. So
# the board's per-step state is computed here directly from the records
# (`project`/`amend`'s own `steps`, `executed`'s `actions`, `observation`'s
# `results`), never from `step_targets`. This intentionally does not import
# anything from `store.py` below this line -- it is a second, read-only path
# over the same append-only log, not a second copy of the live grader's own
# bookkeeping table.


def _amends_for_project_records(records: list[dict], project_id: str) -> list[dict]:
    """Every `amend` naming `project_id`, oldest first (append order, same
    contract `store._amends_for_project` relies on)."""
    return [
        r for r in records
        if r.get("kind") == AMEND and r.get("project_id") == project_id
    ]


def current_steps_and_version_from_records(
    records: list[dict], project: dict,
) -> tuple[list, int]:
    """Records-only equivalent of `store._current_steps_and_version`: the
    steps in effect right now and that version's number. The original
    project's own `steps` is version 1; the Nth amend (oldest first)
    replaces it wholesale, as version N+1."""
    amends = _amends_for_project_records(records, project.get("id"))
    if not amends:
        return project.get("steps") or [], 1
    return amends[-1].get("steps") or [], len(amends) + 1


def _added_version_map(project: dict, amends: list[dict]) -> dict:
    """step id -> the plan version that first introduced it: 1 for every id
    in the original project's own `steps`, else the version of the first
    amend whose `adds` names it. A step never named in any `adds` (kept
    unchanged from an earlier version, or from the original plan) is never
    in this map past version 1 -- callers treat a missing id as version 1,
    never tagged."""
    added: dict[str, int] = {}
    for step in project.get("steps") or []:
        if isinstance(step, dict) and isinstance(step.get("id"), str) and step["id"]:
            added.setdefault(step["id"], 1)
    for i, amend in enumerate(amends):
        version = i + 2
        for sid in amend.get("adds") or []:
            added.setdefault(sid, version)
    return added


def _literal_targets(step: dict) -> Optional[list[str]]:
    """The step's own fixed target list, or `None` when its `targets` is a
    dynamic `{"from_step": ...}` spec (design §4.3) -- in which case this
    module cannot know the target count without running the game, and the
    board shows no "N of M" at all (the handoff's "target counts... when
    known") rather than a fabricated total."""
    spec = step.get("targets")
    if isinstance(spec, dict) and isinstance(spec.get("set"), list):
        return [str(t) for t in spec["set"]]
    return None


def _target_state_map(records: list[dict], ruling_id: Optional[str]):
    """`(step_id, target) -> (target_state, detail)`, last write wins in
    append order -- the same "upsert" semantics `store._apply_executed_
    target_states` gives `step_targets`, computed here directly from the
    `executed` records instead of that table. Also returns the set of
    step ids (bare `None` for an implicit, step-id-less project) that have
    at least one `executed` record naming them at all, the positive signal
    a step with no literal targets needs to ever read as done (mirrors
    `store._step_has_executed_record`)."""
    states: dict[tuple, tuple] = {}
    executed_steps: set = set()
    if not ruling_id:
        return states, executed_steps
    for r in records:
        if r.get("kind") != EXECUTED or r.get("ruling_id") != ruling_id:
            continue
        executed_steps.add(r.get("step_id"))
        for action in r.get("actions") or []:
            if not isinstance(action, dict):
                continue
            targets = action.get("targets")
            state = action.get("target_state")
            if not targets or state is None:
                continue
            detail = action.get("detail")
            for t in targets:
                states[(r.get("step_id"), str(t))] = (state, detail)
    return states, executed_steps


def _humanize_tool(tool: Optional[str]) -> str:
    """A step's fallback public label when it has no `label` of its own
    (handoff's own instruction: "step label from the step's tool name"; a
    `TOOLS.yaml` display-name table, design §3.3 item 6's longer-term
    answer, is not built -- named gap, see `STEP_BOARD_GAPS`)."""
    if not tool:
        return "Step"
    text = tool.replace(".", " ").replace("-", " ").replace("_", " ").strip()
    if not text:
        return "Step"
    return text[0].upper() + text[1:]


def step_public_label(step: dict) -> str:
    """The step's own `label` (design §3.3 item 6, 24 chars, sibling
    stream's schema addition) when present, else the humanized tool name."""
    label = step.get("label")
    if isinstance(label, str) and label.strip():
        return label
    return _humanize_tool(step.get("tool"))


#: Named gap: `TOOLS.yaml`-sourced display names (design §3.3 item 6's
#: longer-term answer for a step with no `label`) are not read here; the
#: fallback is the tool id itself, humanized, never its arguments.
STEP_BOARD_GAPS = [
    "step_public_label falls back to a humanized tool id, not a TOOLS.yaml "
    "display-name table (design §3.3 item 6's longer-term answer) -- that "
    "table does not exist yet.",
]


def step_board_states(records: list[dict], project_id: str) -> list[dict]:
    """The CURRENT version's steps for `project_id`, each as a board-ready
    dict: `id`, `label`, `requires` (dependency ids), `state` (one of
    `done`/`active`/`ready`/`waiting`/`hold`), and `done`/`total` when the
    step's target count is known. `added_version` is present (and > 1) only
    for a step an amendment introduced.

    State rules (mirrors the mockup's own `layoutJobs`, design §3.3's step
    table):
    - `done`: every known target is `done`/`abandoned` (or, for a step with
      no literal targets, some `executed` record already covers it).
    - `hold`: not done, and some known target reads `held`.
    - `active`: not done or held, but some target has started (`issued`, or
      any already `done` while others are not).
    - `ready`: untouched, and every `requires` id is itself `done`.
    - `waiting`: untouched, with at least one unmet `requires` id.

    Returns `[]` for an unknown project id, or a project with no steps at
    all (the legacy single-implicit-step shape has no job graph to draw)."""
    project = next(
        (r for r in records if r.get("kind") == PROJECT and r.get("id") == project_id),
        None,
    )
    if project is None:
        return []
    amends = _amends_for_project_records(records, project_id)
    steps, _version = current_steps_and_version_from_records(records, project)
    if not steps:
        return []
    added_version = _added_version_map(project, amends)
    ruling_id = project.get("from_ruling")
    target_states, executed_steps = _target_state_map(records, ruling_id)

    per_step: dict[str, dict] = {}
    for step in steps:
        if not (isinstance(step, dict) and isinstance(step.get("id"), str) and step["id"]):
            continue
        sid = step["id"]
        literal = _literal_targets(step)
        held_detail = None
        if literal is not None:
            pairs = [target_states.get((sid, t)) for t in literal]
            states = [p[0] for p in pairs if p is not None]
            total = len(literal)
            done_count = sum(1 for s in states if s in (DONE, ABANDONED))
            has_held = any(s == HELD for s in states)
            has_progress = done_count > 0 or any(s == ISSUED for s in states)
            is_done = total > 0 and done_count == total
            if has_held:
                held_detail = next(
                    (p[1] for p in pairs if p is not None and p[0] == HELD), None,
                )
        else:
            total = done_count = None
            has_held = has_progress = False
            is_done = sid in executed_steps or (
                bool(step.get("implicit")) and None in executed_steps
            )
        per_step[sid] = {
            "total": total, "done_count": done_count, "is_done": is_done,
            "has_held": has_held, "has_progress": has_progress,
            "held_detail": held_detail,
        }

    done_ids = {sid for sid, c in per_step.items() if c["is_done"]}
    out: list[dict] = []
    for step in steps:
        sid = step.get("id")
        c = per_step.get(sid)
        if c is None:
            continue
        if c["is_done"]:
            state = "done"
        elif c["has_held"]:
            state = "hold"
        elif c["has_progress"]:
            state = "active"
        else:
            requires = [r for r in (step.get("requires") or []) if isinstance(r, str)]
            state = "ready" if all(r in done_ids for r in requires) else "waiting"
        entry: dict[str, Any] = {
            "id": sid,
            "label": step_public_label(step),
            "requires": list(step.get("requires") or []),
            "state": state,
        }
        if c["total"] is not None:
            entry["done"] = c["done_count"]
            entry["total"] = c["total"]
        version = added_version.get(sid, 1)
        if version > 1:
            entry["added_version"] = version
        if state == "hold":
            # Private: the `executed` action's own `detail` text for the
            # held target. Never public on its own (it is the tool's raw
            # refusal text, design §3.3 item 7's own "never as the tool's
            # text" rule) -- `dfqueue.feed` strips this for the public
            # projection and uses `step_hold_text`'s `hold_code` lookup
            # instead.
            entry["held_detail"] = c["held_detail"]
        out.append(entry)
    return out


def project_board_status(records: list[dict], project_id: str) -> Optional[str]:
    """One of `active`/`hold`/`done`/`abandoned` for the board's four
    columns (design §3.4's "project status for display", collapsed to the
    four this slice's columns need -- `drafting`/`awaiting decision` have no
    project record yet, so they never reach this function). `None` if
    `project_id` names no project record at all."""
    if any(
        r.get("kind") == ABANDON and r.get("project_id") == project_id
        for r in records
    ):
        return "abandoned"
    project = next(
        (r for r in records if r.get("kind") == PROJECT and r.get("id") == project_id),
        None,
    )
    if project is None:
        return None
    steps = step_board_states(records, project_id)
    if not steps:
        # Legacy implicit-step project: no per-step states to fold, so fall
        # back to the same has-this-run-at-all signal `step_board_states`
        # uses for a step with no literal targets.
        ruling_id = project.get("from_ruling")
        _states, executed_steps = _target_state_map(records, ruling_id)
        return "done" if (None in executed_steps or ruling_id in executed_steps) else "active"
    if all(s["state"] == "done" for s in steps):
        return "done"
    if any(s["state"] == "hold" for s in steps):
        return "hold"
    return "active"


def load_public_text(path: Optional[str | Path] = None) -> dict:
    """`dfqueue/public_text.yaml` (design §3.3 item 7, the sibling stream's
    own file -- `handoffs/2026-10-02-queue-display-fields.md`), a flat
    `{hold_code: public text}` map. Returns `{}` if the file does not exist
    yet rather than raising: this reader must work both before and after
    that file lands, since the two streams run concurrently."""
    p = Path(path) if path is not None else Path(__file__).resolve().parent / "public_text.yaml"
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def step_hold_text(
    records: list[dict], project_id: str, step_id: Optional[str], public_text: dict,
) -> tuple[Optional[str], Optional[str]]:
    """`(public_text_or_None, hold_code_or_None)` for a held step: the most
    recent `observation` naming `project_id`/`step_id` whose `results`
    carries a `hold_code` (design §3.3 item 7, sibling stream's schema
    addition -- absent entirely until that lands, and on any record written
    before it lands). No code found -> `(None, None)`: the caller shows a
    bare "on hold" with no reason, never a guessed one (this handoff's own
    fallback rule)."""
    code = None
    for r in reversed(records):
        if r.get("kind") != OBSERVATION:
            continue
        if r.get("project_id") != project_id or r.get("step_id") != step_id:
            continue
        for result in r.get("results") or []:
            if isinstance(result, dict) and result.get("hold_code"):
                code = result["hold_code"]
                break
        if code:
            break
    if not code:
        return None, None
    return public_text.get(code), code
