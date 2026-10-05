"""Lessons: the gotchas an agent wrote (or recorded an outcome on) during a
run, matched to that run so the Board can show a LESSON panel in its turn.

Read-only and best-effort, like `dfqueue/runs.py::records_in_window`: a
gotcha entry (`created_at`, `written_by_role`) or an outcome (`at`, `role`,
`result`) belongs to a run when the role matches and the time falls inside
the run's `started_at`..`ended_at` window. Entries come from
`dfqueue.site_data.load_gotchas_readonly` (the publisher's own read-only
view of the store), run rows from `dfqueue.runs.read_runs_readonly`.

`lessons.json` per fort: `{"lessons": [{run_id, thread, role, kind, gotcha_id,
title, result, at}]}`. `kind` is `"new"` (a gotcha written) or `"outcome"`
(an outcome recorded; `result` is `worked` or `did_not_work`, else `null`).
A lesson belongs to every thread its run touched, so it is emitted once per
thread. The public projection skips a lesson whose title fails the same
`find_unsafe_pattern` check the public `gotchas.json` applies (the lesson is
dropped, never edited); the operator projection keeps raw titles.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from dfqueue.feed import find_unsafe_pattern
from dfqueue.runs import _parse


def _threads_of(row: dict) -> list:
    try:
        records = json.loads(row.get("records_json") or "[]")
    except ValueError:
        return []
    seen: list = []
    for r in records:
        if isinstance(r, dict) and r.get("id"):
            t = r.get("thread") or r["id"]
            if t not in seen:
                seen.append(t)
    return seen


def _in_window(ts: Any, start, end) -> bool:
    dt = _parse(ts)
    return dt is not None and start <= dt <= end


def build_lessons(run_rows: Optional[list], gotcha_entries: Optional[list], *, public: bool) -> dict:
    """The `lessons.json` payload. Runs with no touched thread (they wrote no
    record) have nowhere to show a lesson and add none."""
    lessons: list = []
    for row in run_rows or []:
        role = row.get("role")
        start, end = _parse(row.get("started_at")), _parse(row.get("ended_at"))
        if not role or start is None or end is None:
            continue
        threads = _threads_of(row)
        if not threads:
            continue
        for entry in gotcha_entries or []:
            title = entry.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            if public and find_unsafe_pattern(title) is not None:
                continue
            found = []
            if entry.get("written_by_role") == role and _in_window(entry.get("created_at"), start, end):
                found.append(("new", None, entry.get("created_at")))
            for o in entry.get("outcomes") or []:
                if o.get("role") == role and _in_window(o.get("at"), start, end):
                    result = o.get("result") if o.get("result") in ("worked", "did_not_work") else None
                    found.append(("outcome", result, o.get("at")))
            for kind, result, at in found:
                for thread in threads:
                    lessons.append({
                        "run_id": row.get("run_id"), "thread": thread, "role": role,
                        "kind": kind, "gotcha_id": entry.get("id"), "title": title.strip(),
                        "result": result, "at": at,
                    })
    lessons.sort(key=lambda x: (x["at"] or "", x["run_id"] or "", x["thread"]))
    return {"lessons": lessons}
