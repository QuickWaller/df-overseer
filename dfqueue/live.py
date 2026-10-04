"""The "who is awake" live view's data (handoffs/2026-10-05-board-order-year-
live-view.md task 3, stream page slice S2).

Pure functions plus two small, failure-tolerant readers. The publisher
(`scripts/stream_publisher.py`, on the same host as `dfmcp-server`) calls
them each cycle and folds the result into each projection's `status.json`
under the key `live`.

Two tiers, no new port and no new credential:

- **Tier A, the call journal (live).** `dfmcp-server` logs one JSON line per
  tool call (`dfmcp/server.py::_call_log_line`), to journald. A role is
  "awake" while its newest call is under `AWAKE_WINDOW_S` old; its run began
  at the first call of the unbroken burst (gaps under the window). Only the
  role, the tool id and the timestamps are ever copied: the line's
  `arguments`, `client` and `session_id` are dropped on read.
- **Tier B, a conductor runtime directory (optional).** A local directory
  laid out like the conductor's runtime root (`status.json` plus
  `cycles/cycle-*/{briefings,summary}.json` and `run-<role>.json`) adds the
  wake reason, and a finished run's real wall-clock and cost. Something has
  to put those files on this host; nothing here does (that needs a
  credential or a new MCP tool, left to the orchestrator). Absent, the view
  runs on Tier A alone.

- **Tier C, the conductor's own run reports (best).** `conductor.report`
  (handoffs/2026-10-05-conductor-report.md) stores one row per role run in
  `dfqueue/runs.py`'s store on this host. `read_runs` reads it `mode=ro`;
  `build_live` uses an open run for the strip's wake reason and the newest
  finished run per role for `last_runs`; `build_runs` produces `runs.json`.

Public output carries no cost, no arguments and no host detail. Operator
output adds cost and the call's error flag.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

#: A role is awake while its newest call is younger than this. A model turn
#: with no tool call in it can run a couple of minutes, so this is generous;
#: the cost is that "awake" lingers this long after a run really ends.
AWAKE_WINDOW_S = 240

#: How far back the journal is read. Must exceed the longest run the page
#: should show the start of (the conductor's role timeout is 600 s).
JOURNAL_LOOKBACK_MIN = 30

#: `conductor/status.py::status_running`'s block is ignored once older than this.
RUNNING_BLOCK_MAX_AGE_S = 900

#: A run report with no end older than this is shown as `lost`, not `running`
#: (the conductor died, or its end call failed). The role timeout is 600 s.
RUN_OPEN_MAX_AGE_S = 1200

#: Public `runs.json` carries a run's summary only when this is True AND the
#: text passes `feed.find_unsafe_pattern`. Free model text is the worst case
#: for that pattern check (it catches urls, paths, tokens and markup, not
#: meaning), so flipping this to False is the one switch that makes summaries
#: operator-only.
PUBLIC_SUMMARIES = True
SUMMARY_PUBLIC_MAX = 280
RUNS_LIMIT = 40

_WAKE_REASON_PUBLIC = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

JOURNAL_UNIT = "dfmcp-server.service"
SYSTEM_ROLE = "conductor"


# ---- reading the call journal ----------------------------------------------


def _parse_ts(raw: Any) -> Optional[float]:
    if not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def parse_call_lines(lines: Iterable[str]) -> list[dict]:
    """The `tools/call` lines of a dfmcp journal as minimal call dicts
    (`ts` epoch seconds, `role`, `tool`, `is_error`), oldest first. Anything
    that is not a well-formed call line is skipped. The line's arguments are
    deliberately never carried over."""
    calls = []
    for line in lines:
        line = line.strip()
        if '"tools/call"' not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("event") != "tools/call":
            continue
        ts = _parse_ts(rec.get("ts"))
        role = rec.get("role")
        tool = rec.get("tool_id") or rec.get("tool")
        if ts is None or not isinstance(role, str) or not isinstance(tool, str):
            continue
        calls.append({"ts": ts, "role": role, "tool": tool, "is_error": bool(rec.get("is_error"))})
    calls.sort(key=lambda c: c["ts"])
    return calls


def read_journal_lines(
    *, lookback_min: int = JOURNAL_LOOKBACK_MIN, run: Callable[..., Any] = subprocess.run,
    journalctl: str = "journalctl",
) -> Optional[list[str]]:
    """`dfmcp-server`'s recent journal lines, or `None` when the journal
    cannot be read (not installed, no permission, timed out): the live view
    then reports itself unavailable rather than failing the publisher."""
    cmd = [journalctl, "-u", JOURNAL_UNIT, "-o", "cat", "--no-pager",
           "--since", f"-{int(lookback_min)} min"]
    try:
        proc = run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if getattr(proc, "returncode", 1) != 0:
        return None
    return (proc.stdout or "").splitlines()


# ---- reading the conductor's runtime directory (Tier B) ---------------------


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_conductor_dir(path: "str | Path | None", *, cycles_scanned: int = 6) -> Optional[dict]:
    """`{"running": {...} | None, "last_runs": {role: {...}}}` from a local
    copy of the conductor's runtime root, or `None` when `path` is unset or
    missing. `last_runs[role]` is that role's newest archived run:
    `duration_s`, `cost_usd`, `wake_reason`, `ok`, `timed_out`, `ended_at`."""
    if not path:
        return None
    root = Path(path)
    if not root.is_dir():
        return None
    out: dict = {"running": None, "last_runs": {}}
    status = _load_json(root / "status.json")
    if isinstance(status, dict) and isinstance(status.get("running"), dict):
        out["running"] = status["running"]
    cycles_dir = root / "cycles"
    cycle_dirs = sorted(p for p in cycles_dir.glob("cycle-*") if p.is_dir()) if cycles_dir.is_dir() else []
    for cdir in reversed(cycle_dirs[-cycles_scanned:]):
        briefings = _load_json(cdir / "briefings.json") or {}
        for run_path in sorted(cdir.glob("run-*.json")):
            run = _load_json(run_path)
            if not isinstance(run, dict):
                continue
            role = run.get("role") or run_path.stem[len("run-"):]
            if role in out["last_runs"]:
                continue  # newer cycle already supplied this role
            briefing = briefings.get(role) if isinstance(briefings, dict) else None
            try:
                ended = datetime.fromtimestamp(run_path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
            except OSError:
                ended = None
            out["last_runs"][role] = {
                "duration_s": run.get("wall_clock_seconds"),
                "cost_usd": run.get("cost_usd"),
                "wake_reason": (briefing or {}).get("wake_reason") if isinstance(briefing, dict) else None,
                "ok": run.get("ok"),
                "timed_out": run.get("timed_out"),
                "ended_at": ended,
            }
    return out


# ---- the conductor's run reports (Tier C) -----------------------------------


def read_runs(path: "str | Path | None", limit: int = RUNS_LIMIT) -> Optional[list]:
    """Newest-first run rows from `dfqueue/runs.py`'s store, read-only, or
    `None` when `path` is unset or the store does not exist yet (the tool is
    not deployed, or nothing has reported). Never raises."""
    if not path or not Path(path).is_file():
        return None
    from dfqueue import runs as runs_store
    try:
        return runs_store.read_runs_readonly(path, limit)
    except (sqlite3.Error, OSError):
        return None


def _run_status(row: Mapping[str, Any], now: float) -> str:
    if row.get("ended_at") is None:
        started = _parse_ts(row.get("started_at"))
        return "running" if started is not None and now - started <= RUN_OPEN_MAX_AGE_S else "lost"
    if row.get("timed_out"):
        return "timed_out"
    return "ok" if row.get("ok") else "failed"


def _public_summary(text: Optional[str]) -> Optional[str]:
    """The public form of a run's final answer, or `None` when it must be
    withheld. Checked on the whole text and again on the published cut, so a
    pattern past the cut still withholds."""
    if not PUBLIC_SUMMARIES or not text:
        return None
    from dfqueue import feed
    body = text.replace("\n[truncated]", "").strip()
    if not body or feed.find_unsafe_pattern(body):
        return None
    body = " ".join(body.split())
    if len(body) > SUMMARY_PUBLIC_MAX:
        cut = body[:SUMMARY_PUBLIC_MAX]
        stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        body = cut[: stop + 1] if stop >= 80 else cut.rstrip() + "..."
    return None if feed.find_unsafe_pattern(body) else body


def build_runs(rows: Optional[list], now: float, *, public: bool, limit: int = RUNS_LIMIT) -> Optional[dict]:
    """The `runs.json` payload for one projection, or `None` when there is
    no run store. Newest first. See the handoff's Result for the shape.

    Public per run: `run_id, role, wake_reason` (only if it is a plain code),
    `status, started_at, ended_at, duration_s, records, summary` (see
    `_public_summary`; absent with `summary_withheld: true` when the text was
    held back). Operator adds `wake_detail, cycle, cost_usd, error` and the
    full `final_answer` (as `summary`, uncut)."""
    if rows is None:
        return None
    out_runs = []
    by_thread: dict[str, list[str]] = {}
    for row in rows[:limit]:
        try:
            records = json.loads(row.get("records_json") or "[]")
        except ValueError:
            records = []
        records = [r for r in records if isinstance(r, dict) and r.get("id")]
        wake = row.get("wake_reason")
        entry: dict = {
            "run_id": row.get("run_id"),
            "role": row.get("role"),
            "wake_reason": wake if (not public or (isinstance(wake, str) and _WAKE_REASON_PUBLIC.match(wake))) else None,
            "status": _run_status(row, now),
            "started_at": row.get("started_at"),
            "ended_at": row.get("ended_at"),
            "duration_s": None if row.get("duration_s") is None else round(row["duration_s"]),
            "records": [{"id": r["id"], "kind": r.get("kind"), "thread": r.get("thread") or r["id"]} for r in records],
        }
        answer = row.get("final_answer")
        if public:
            if entry["status"] == "ok" and answer:
                summary = _public_summary(answer)
                if summary is None:
                    entry["summary_withheld"] = True
                else:
                    entry["summary"] = summary
        else:
            entry.update({
                "wake_detail": row.get("wake_detail"), "cycle": row.get("cycle"),
                "cost_usd": row.get("cost_usd"), "error": row.get("error"),
                "summary": answer,
            })
        out_runs.append(entry)
        for r in entry["records"]:
            by_thread.setdefault(r["thread"], [])
            if entry["run_id"] not in by_thread[r["thread"]]:
                by_thread[r["thread"]].append(entry["run_id"])
    return {"available": True, "as_of": _iso(now), "runs": out_runs, "by_thread": by_thread}


# ---- building the view -----------------------------------------------------


def _bursts(role_calls: list[dict], window: float) -> list[list[dict]]:
    """Split one role's time-ordered calls into unbroken bursts."""
    bursts: list[list[dict]] = []
    for call in role_calls:
        if bursts and call["ts"] - bursts[-1][-1]["ts"] <= window:
            bursts[-1].append(call)
        else:
            bursts.append([call])
    return bursts


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def build_live(
    calls: Optional[list[dict]], now: float, *, public: bool,
    conductor: Optional[Mapping[str, Any]] = None, window: float = AWAKE_WINDOW_S,
    runs: Optional[list] = None,
) -> dict:
    """The `live` block for one projection. `calls=None` means the journal
    could not be read. See the module docstring for the rules; every field
    present in the public form is also in the operator form, which adds
    `cost_usd` (a run's cost) and `last_error` (the newest call failed)."""
    base: dict = {"available": False, "as_of": _iso(now), "running": False, "awake": [], "last_runs": {}}
    if calls is None and conductor is None and runs is None:
        base["reason"] = "journal_unreadable"
        return base

    calls = calls or []
    by_role: dict[str, list[dict]] = {}
    for call in calls:
        by_role.setdefault(call["role"], []).append(call)

    awake = []
    last_runs: dict[str, dict] = {}
    running_hint = (conductor or {}).get("running") if conductor else None
    if isinstance(running_hint, dict):
        started = _parse_ts(running_hint.get("started_at"))
        if started is None or now - started > RUNNING_BLOCK_MAX_AGE_S:
            running_hint = None

    system_awake = False
    for role, role_calls in sorted(by_role.items()):
        bursts = _bursts(role_calls, window)
        newest = bursts[-1]
        is_awake = now - newest[-1]["ts"] <= window
        if role == SYSTEM_ROLE:
            system_awake = is_awake
            continue
        if is_awake:
            last = newest[-1]
            entry = {
                "role": role,
                "since": _iso(newest[0]["ts"]),
                "elapsed_s": max(0, round(now - newest[0]["ts"])),
                "last_tool": last["tool"],
                "last_call_at": _iso(last["ts"]),
                "wake_reason": None,
            }
            if not public:
                entry["last_error"] = last["is_error"]
            if isinstance(running_hint, dict) and running_hint.get("role") == role:
                entry["wake_reason"] = running_hint.get("wake_reason")
            awake.append(entry)
        # the newest FINISHED burst is that role's last run, as the calls saw it
        finished = bursts[-2] if is_awake and len(bursts) > 1 else (None if is_awake else newest)
        if finished:
            last_runs[role] = {
                "duration_s": max(0, round(finished[-1]["ts"] - finished[0]["ts"])),
                "ended_at": _iso(finished[-1]["ts"]),
                "wake_reason": None,
                "source": "calls",
            }

    # The conductor's own archive, when a copy is present, has the real
    # wall-clock, the wake reason and the cost, and overrides the call span.
    for role, run in ((conductor or {}).get("last_runs") or {}).items():
        entry = {
            "duration_s": None if run.get("duration_s") is None else round(run["duration_s"]),
            "ended_at": run.get("ended_at"),
            "wake_reason": run.get("wake_reason"),
            "ok": run.get("ok"),
            "source": "archive",
        }
        if not public:
            entry["cost_usd"] = run.get("cost_usd")
        last_runs[role] = entry

    # The conductor's own run reports (Tier C) beat both of the above: an open
    # run supplies the wake reason, the newest finished run per role the
    # last_runs entry (with the run id, so the page can link to runs.json).
    open_runs: dict[str, Mapping[str, Any]] = {}
    seen_closed: set[str] = set()
    for row in runs or []:  # newest first
        role = row.get("role")
        if not isinstance(role, str):
            continue
        if _run_status(row, now) == "running":
            open_runs.setdefault(role, row)
        elif row.get("ended_at") is not None and role not in seen_closed:
            seen_closed.add(role)
            report_entry = {
                "run_id": row.get("run_id"),
                "duration_s": None if row.get("duration_s") is None else round(row["duration_s"]),
                "ended_at": row.get("ended_at"),
                "wake_reason": row.get("wake_reason"),
                "ok": None if row.get("ok") is None else bool(row["ok"]),
                "source": "report",
            }
            if not public:
                report_entry["cost_usd"] = row.get("cost_usd")
            last_runs[role] = report_entry
    for entry in awake:
        run = open_runs.get(entry["role"])
        if run is not None:
            entry["wake_reason"] = run.get("wake_reason")
            entry["run_id"] = run.get("run_id")

    base.update({
        "available": True,
        "running": bool(awake) or system_awake or bool(open_runs),
        "awake": awake,
        "last_runs": last_runs,
        "source": "journal+archive" if conductor else "journal",
    })
    if runs is not None:
        base["source"] = base["source"] + "+reports"
    if calls is None:
        base["source"] = "archive"
    return base


#: Fields that change every publisher cycle without anything real happening;
#: the publisher's change detection must not count them.
_VOLATILE = {"as_of", "elapsed_s"}


def live_hash_payload(live: Optional[dict]) -> Optional[dict]:
    """`live` minus the fields that tick with the wall clock, so an idle
    fort does not republish every five seconds."""
    if live is None:
        return None

    def strip(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: strip(v) for k, v in obj.items() if k not in _VOLATILE}
        if isinstance(obj, list):
            return [strip(v) for v in obj]
        return obj

    return strip(live)
