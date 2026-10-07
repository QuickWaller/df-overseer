"""Wake and waste metrics (notebook N0): how often the agents repeat
themselves, how many rounds a wake takes, what it costs, which tools it uses.

Spec: `research/2026-10-07-notebook-design.md` section 2 as corrected by
`research/2026-10-07-notebook-red-team.md` section 3 ("before N0"). Read-only:
both SQLite files are opened `mode=ro` and nothing is ever created, migrated
or written. An absent column or table reads as nothing.

Two entry points:

* `compute(queue_db, runs_db, since=None, ...) -> dict`: pure over the two
  files, returns the **publishable** report (schema below). The stream
  publisher imports this.
* `python -m dfqueue.wake_metrics --queue Q --runs R [--out metrics.json]
  [--text] [--per-wake per_wake.jsonl]`: the CLI.

Published schema, `"schema": "wake_metrics/1"` (bump the integer on any
breaking change; additions are not breaking):

```
{
  "schema": "wake_metrics/1",
  "generated_at": ISO, "since": ISO|null, "until": ISO|null,
  "definitions": {"m1": "...", ...},          # one line each, fixed text
  "totals":   <group>,                        # every wake in range
  "by_role":  {role: <group>},
  "by_day":   {"YYYY-MM-DD": {role: <group>}},  # chart series, sorted keys
  "by_epoch": {epoch_id: {role: <group>}},
  "episodes": {role: {"events", "episodes", "events_per_episode"}},
  "interval": {role: {"r_per_at_risk_wake": {"mean","lo90","hi90","clusters"}}},
  "power":    {"r_rate_per_at_risk_wake", "events_per_episode", "wakes_per_day",
               "n_wakes_per_arm_rr50", "days_rr50"},
  "tool_usage": {role: {"wakes_with_transcript", "calls": {tool_id: n},
                         "unmapped_calls", "never_called": [tool_id]}},
  "wakes": [<per-wake row>],                  # ids and numbers only
  "unattributed": {"proposals", "repeats"},   # records no run wrote
  "notes": [str]                              # fixed strings
}
<group> = {"wakes","killed","at_risk_wakes","m1","m1_wide","m1_struct","m2","m3",
           "m3_cross_role","r","r_per_wake","r_per_at_risk_wake",
           "cost": {"n","mean","median","sum"}, "rounds": {...},
           "rounds_to_first_write": {...}, "orientation_reads": {...},
           "reread_rate", "pass_rate", "tokens": {"input","output",
           "cache_read","reasoning"}, "with_transcript", "truncated"}
<per-wake row> = {"run_id","role","day","epoch","wake_reason","wake_reasons","sweep",
           "status","killed","at_risk","m1","m1_wide","m2","m3","r",
           "cost_usd","rounds","first_write_round","orientation_reads",
           "read_calls","redundant_reads","passed","source"}
```

Safe to publish by construction: every string is an id, a role, a day, an
epoch id, a tool id, a wake-reason keyword or a fixed definition; there are
no tool arguments, results, proposal text, rulings' reasons or thinking.
`tests/test_wake_metrics.py` asserts this over a populated report.

Definitions follow the spec with the red-team's corrections: M1 is
within-role and counted over a window of the role's own wakes (wall days only
when the role has too few runs); an accepted proposal counts as completed
only on a `close` of outcome `completed` or a prediction graded true (an
`executed` record alone is not completion); R counts only on wakes where a
repeat was possible (at-risk) and is summarised per episode as well as per
wake; M3 is same-role, cross-role duplicates are reported separately; killed
runs have no cost and are reported, never zeroed.
"""

from __future__ import annotations

import argparse
import difflib  # noqa: F401  (schema.near_duplicate_reason uses it)
import json
import math
import random
import re
import sqlite3
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from dfqueue import schema

SCHEMA_ID = "wake_metrics/1"

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents"
EPOCHS_PATH = Path(__file__).with_name("wake_epochs.yaml")

ADVISOR_ROLES = ("architect", "quartermaster", "planner")
WINDOW_WAKES = 10          # M1 window, in the role's own wakes
WINDOW_FALLBACK_DAYS = 7   # ... when the role has fewer prior runs than that
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20261007

_DUP_RE = re.compile(r"duplicat|already (queued|pending|open|accepted|ordered)", re.I)
_PROPOSAL_ID_RE = re.compile(r"proposal-\d{4,}")
_SAFE_TOOL_RE = re.compile(r"^[A-Za-z0-9_.\-*]{1,80}$")

DEFINITIONS = {
    "m1": "repeat proposal: same role and type, summary or rationale near-duplicate of an earlier proposal still open, rejected or accepted-not-completed within the role's last 10 wakes",
    "m1_wide": "m1 plus same role, type, prediction signal and operator (sensitivity only)",
    "m1_struct": "m1 plus same role, type, prediction signal and operator and mostly the same precondition landmarks (sensitivity only)",
    "m2": "repeat defer: a defer whose previous ruling on the proposal was also a defer and nothing about the proposal changed between them",
    "m3": "same-role duplicate: duplicate_of set, or final rejection with a duplicate-style reason",
    "r": "m1 or m3 proposals plus m2 defers written in the wake, each record once",
    "at_risk": "a repeat was possible: advisors with an own proposal open, rejected or accepted-not-completed in window; overseer with a pending proposal already deferred once",
    "rounds": "assistant rounds in the wake, including rounds dropped from the stored transcript",
    "reread": "same read tool, same arguments, no write in between, earlier call succeeded",
    "orientation_reads": "read calls before the first write call",
    "pass_rate": "advisor wakes that filed a pass and no proposal, ask or plan",
}
NOTES = [
    "Runs older than the runs store's retention are gone; per-wake rows are a snapshot, keep them.",
    "Transcript metrics exist only for wakes recorded with a transcript; others read null and are counted.",
    "A transcript is capped; truncated wakes undercount late calls and are flagged.",
    "Killed runs report no cost and are excluded from cost summaries.",
]


# ---- reading (strictly read-only) -----------------------------------------


def _ro(path: "str | Path") -> sqlite3.Connection:
    uri = f"file:{Path(path).resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def read_queue(queue_db: "str | Path") -> Dict[str, Any]:
    """`{"records": [...], "predictions": {record_id: {signal, op, status}}}`.
    Absent file or table gives empties."""
    out: Dict[str, Any] = {"records": [], "predictions": {}}
    try:
        conn = _ro(queue_db)
    except sqlite3.Error:
        return out
    try:
        try:
            for row in conn.execute("SELECT payload FROM records ORDER BY rowid ASC"):
                try:
                    rec = json.loads(row[0])
                except (TypeError, ValueError):
                    continue
                if isinstance(rec, dict):
                    out["records"].append(rec)
        except sqlite3.Error:
            pass
        try:
            for row in conn.execute("SELECT record_id, signal, op, status FROM predictions"):
                out["predictions"][row["record_id"]] = {
                    "signal": row["signal"], "op": row["op"], "status": row["status"]}
        except sqlite3.Error:
            pass
    finally:
        conn.close()
    return out


def read_runs(runs_db: "str | Path") -> List[dict]:
    """Every run row oldest first. Absent file or table gives []; absent
    columns (older stores, no `transcript` or hash columns) read as None."""
    try:
        conn = _ro(runs_db)
    except sqlite3.Error:
        return []
    try:
        try:
            rows = [dict(r) for r in conn.execute("SELECT * FROM runs ORDER BY started_at ASC, run_id ASC")]
        except sqlite3.Error:
            return []
    finally:
        conn.close()
    return rows


def _parse(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---- allowlists and wire names --------------------------------------------


def load_allowlists(agents_dir: "str | Path" = AGENTS_DIR) -> Dict[str, Dict[str, set]]:
    """`{role: {"read": {ids}, "write": {ids}}}` from `agents/<role>/tools.yaml`."""
    import yaml
    out: Dict[str, Dict[str, set]] = {}
    for tools_yaml in sorted(Path(agents_dir).glob("*/tools.yaml")):
        try:
            doc = yaml.safe_load(tools_yaml.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        sections = {}
        for key in ("read", "write"):
            sections[key] = {e["id"] for e in doc.get(key) or [] if isinstance(e, dict) and e.get("id")}
        out[str(doc.get("role") or tools_yaml.parent.name)] = sections
    return out


def wire_to_tool_id(wire: str, known: Iterable[str]) -> Optional[str]:
    """`df-overseer__queue__propose` -> `queue.propose`: drop the server
    prefix (up to the first `__`), then the inverse of
    `conductor.mcp_client.tool_name` (`.` becomes `__`). Returns None when
    the result is not one of `known` ids."""
    if not isinstance(wire, str) or "__" not in wire:
        return None
    rest = wire.split("__", 1)[1]
    known = set(known)
    for cand in (rest.replace("__", ".", 1), rest.replace("__", "."), rest):
        if cand in known:
            return cand
    return None


# ---- epochs ----------------------------------------------------------------


def load_epochs(path: "str | Path | None" = None) -> List[dict]:
    """The hand-kept deploy list `[{id, since}]`, oldest first. Used only
    when runs carry no `charter_hash`/`tools_hash`/`policy_hash`."""
    try:
        import yaml
        doc = yaml.safe_load(Path(path or EPOCHS_PATH).read_text(encoding="utf-8")) or {}
        items = [e for e in doc.get("epochs") or [] if isinstance(e, dict) and e.get("id") and e.get("since")]
        return sorted(items, key=lambda e: str(e["since"]))
    except Exception:  # noqa: BLE001
        return []


def epoch_of(ts: Any, epochs: List[dict], hashes: Optional[tuple] = None) -> str:
    if hashes and any(hashes):
        return "h-" + "-".join((h or "none")[:6] for h in hashes)
    t = _parse(ts)
    chosen = "e0"
    if t is None:
        return chosen
    for e in epochs:
        s = _parse(str(e["since"]))
        if s is not None and s <= t:
            chosen = str(e["id"])
    return chosen


# ---- record-level classification (M1, M2, M3) -----------------------------


class Classified:
    """Per-record flags. `m1[b] = a_id`, `m1_wide[b] = a_id`, `m3[b] = ref`,
    `m3_cross`, `m2[ruling_id] = proposal_id`, plus helpers for at-risk."""

    def __init__(self) -> None:
        self.m1: Dict[str, str] = {}
        self.m1_wide: Dict[str, str] = {}
        self.m1_struct: Dict[str, str] = {}
        self.m1_status: Dict[str, str] = {}
        self.m3: Dict[str, Optional[str]] = {}
        self.m3_cross: set = set()
        self.m2: Dict[str, str] = {}


def _status_at(a_id: str, ts: datetime, rulings_by_prop: dict, closes_by_ruling: dict,
               closes_by_prop: dict, predictions: dict) -> str:
    """open | after_reject | after_accept | completed, for proposal `a_id`
    as of `ts`."""
    last = None
    for r in rulings_by_prop.get(a_id, []):
        rt = _parse(r.get("ts"))
        if rt is not None and rt <= ts and r.get("decision") in ("accept", "reject", "defer"):
            last = r
    if last is None or last["decision"] == "defer":
        return "open"
    if last["decision"] == "reject":
        return "after_reject"
    # accepted: completed only on a close of outcome completed or a true prediction
    for c in closes_by_ruling.get(last["id"], []) + closes_by_prop.get(a_id, []):
        ct = _parse(c.get("ts"))
        if c.get("outcome") == "completed" and ct is not None and ct <= ts:
            return "completed"
    if predictions.get(a_id, {}).get("status") == "graded_true":
        return "completed"
    return "after_accept"


def _index(records: List[dict]) -> dict:
    rulings_by_prop: Dict[str, list] = {}
    closes_by_ruling: Dict[str, list] = {}
    closes_by_prop: Dict[str, list] = {}
    for rec in records:
        k = rec.get("kind")
        if k == "ruling" and rec.get("proposal_id"):
            rulings_by_prop.setdefault(rec["proposal_id"], []).append(rec)
        elif k == "close":
            if rec.get("ruling_id"):
                closes_by_ruling.setdefault(rec["ruling_id"], []).append(rec)
            if rec.get("proposal_id"):
                closes_by_prop.setdefault(rec["proposal_id"], []).append(rec)
    return {"rulings_by_prop": rulings_by_prop, "closes_by_ruling": closes_by_ruling,
            "closes_by_prop": closes_by_prop}


def _window_start(b_ts: datetime, role: str, runs: List[dict]) -> datetime:
    starts = sorted(
        (s for s in (_parse(r.get("started_at")) for r in runs if r.get("role") == role)
         if s is not None and s < b_ts), reverse=True)
    if len(starts) >= WINDOW_WAKES:
        return starts[WINDOW_WAKES - 1]
    return b_ts - timedelta(days=WINDOW_FALLBACK_DAYS)


def _signal_key(rec: dict, predictions: dict) -> Optional[tuple]:
    p = predictions.get(rec.get("id"))
    if p:
        return (p.get("signal"), p.get("op"))
    pred = rec.get("prediction")
    if isinstance(pred, dict) and pred.get("signal"):
        return (pred.get("signal"), pred.get("op"))
    return None


def _landmarks(rec: dict) -> frozenset:
    pre = rec.get("preconditions")
    return frozenset(
        str(p["landmark"]).lower() for p in pre if isinstance(p, dict) and p.get("landmark")
    ) if isinstance(pre, list) else frozenset()


def _struct_match(a: dict, b: dict, sk_a: Optional[tuple], sk_b: Optional[tuple]) -> bool:
    """Same prediction signal and operator, and the preconditions name
    mostly the same landmarks (Jaccard at least 0.5). Catches a paraphrased
    repeat the text rule misses without matching every proposal that shares
    a signal (M1-wide does)."""
    if not sk_a or sk_a != sk_b:
        return False
    la, lb = _landmarks(a), _landmarks(b)
    return bool(la | lb) and len(la & lb) / len(la | lb) >= 0.5


def classify(records: List[dict], predictions: Optional[dict] = None,
             runs: Optional[List[dict]] = None, epochs: Optional[List[dict]] = None) -> Classified:
    """Pure over records. M1 within role, M3 same-role, M2 with the spec's
    change test (a non-ruling record naming the proposal, an answer to an ask
    about it, an epoch boundary)."""
    predictions = predictions or {}
    runs = runs or []
    epochs = epochs or []
    idx = _index(records)
    props = sorted((r for r in records if r.get("kind") == "proposal"), key=lambda r: str(r.get("ts")))
    by_id = {p["id"]: p for p in props}
    out = Classified()

    for i, b in enumerate(props):
        bts = _parse(b.get("ts"))
        if bts is None:
            continue
        wstart = _window_start(bts, b["role"], runs)
        bserves = set(b.get("serves") or [])
        for a in props[:i]:
            if a["role"] != b["role"] or a.get("type") != b.get("type"):
                continue
            ats = _parse(a.get("ts"))
            if ats is None or ats < wstart or ats > bts:
                continue
            status = _status_at(a["id"], bts, idx["rulings_by_prop"], idx["closes_by_ruling"],
                                idx["closes_by_prop"], predictions)
            if status == "completed":
                continue
            text_match = (not (set(a.get("serves") or []) & bserves)
                          and schema.near_duplicate_reason(b, a) is not None)
            if text_match and b["id"] not in out.m1:
                out.m1[b["id"]] = a["id"]
                out.m1_status[b["id"]] = status
            sk_a, sk_b = _signal_key(a, predictions), _signal_key(b, predictions)
            if (text_match or (sk_a and sk_a == sk_b)) and b["id"] not in out.m1_wide:
                out.m1_wide[b["id"]] = a["id"]
            if (text_match or _struct_match(a, b, sk_a, sk_b)) and b["id"] not in out.m1_struct:
                out.m1_struct[b["id"]] = a["id"]

    for p in props:
        ref = p.get("duplicate_of")
        reject_reason = None
        for r in idx["rulings_by_prop"].get(p["id"], []):
            if r.get("decision") == "reject" and _DUP_RE.search(str(r.get("reason") or "")):
                reject_reason = str(r.get("reason"))
        if not ref and reject_reason:
            m = _PROPOSAL_ID_RE.search(reject_reason)
            ref = m.group(0) if m else None
        if p.get("duplicate_of") or reject_reason:
            other = by_id.get(ref) if ref else None
            if other is not None and other["role"] != p["role"]:
                out.m3_cross.add(p["id"])
            else:
                out.m3[p["id"]] = ref

    asks_about: Dict[str, set] = {}
    for rec in records:
        if rec.get("kind") == "ask" and rec.get("proposal_id"):
            asks_about.setdefault(rec["proposal_id"], set()).add(rec["id"])
    for pid, rulings in idx["rulings_by_prop"].items():
        rulings = sorted(rulings, key=lambda r: str(r.get("ts")))
        for prev, cur in zip(rulings, rulings[1:]):
            if not (prev.get("decision") == "defer" and cur.get("decision") == "defer"):
                continue
            lo, hi = _parse(prev.get("ts")), _parse(cur.get("ts"))
            if lo is None or hi is None:
                continue
            changed = False
            for rec in records:
                rt = _parse(rec.get("ts"))
                if rt is None or not (lo < rt < hi):
                    continue
                kind = rec.get("kind")
                if kind != "ruling" and rec.get("proposal_id") == pid:
                    changed = True
                elif kind == "answer" and rec.get("ask_id") in asks_about.get(pid, ()):
                    changed = True
                if changed:
                    break
            if not changed and epoch_of(prev.get("ts"), epochs) != epoch_of(cur.get("ts"), epochs):
                changed = True
            if not changed:
                out.m2[cur["id"]] = pid
    return out


# ---- transcript metrics -----------------------------------------------------


def _canon_args(args: Any) -> str:
    if isinstance(args, str):
        try:
            return json.dumps(json.loads(args), sort_keys=True)
        except ValueError:
            return args
    return json.dumps(args, sort_keys=True, default=str)


def transcript_metrics(transcript_json: Any, role: str, allow: Dict[str, Dict[str, set]],
                       all_known: set) -> Optional[dict]:
    """Rounds, tokens, M5/M5b/M8 and per-tool counts from one stored
    transcript, or None when the run has none."""
    if not transcript_json:
        return None
    try:
        tr = json.loads(transcript_json) if isinstance(transcript_json, str) else transcript_json
        rounds = tr["rounds"]
    except (ValueError, KeyError, TypeError):
        return None
    mine = allow.get(role, {"read": set(), "write": set()})
    known = mine["read"] | mine["write"] | all_known
    writes = {w for w in mine["write"] if not w.startswith("notebook.")}
    reads = mine["read"]
    omitted = int(tr.get("omitted_rounds") or 0)
    tokens = {"input": 0, "output": 0, "cache_read": 0, "reasoning": 0}
    counts: Dict[str, int] = {}
    unmapped = 0
    seen: List[tuple] = []          # (id, canon args, error) for read calls
    last_write_idx = -1
    redundant = read_calls = 0
    orientation = None
    first_write_round = None
    seq = 0
    read_log: List[tuple] = []
    for rd in rounds:
        u = rd.get("usage") or {}
        tokens["input"] += int(u.get("input") or 0)
        tokens["output"] += int(u.get("output") or 0)
        tokens["cache_read"] += int(u.get("cacheRead") or 0)
        tokens["reasoning"] += int(u.get("reasoningTokens") or 0)
        for call in rd.get("calls") or []:
            tid = wire_to_tool_id(call.get("name"), known)
            if tid is None:
                unmapped += 1
                seq += 1
                continue
            counts[tid] = counts.get(tid, 0) + 1
            if tid in writes:
                if first_write_round is None:
                    first_write_round = rd.get("n")
                    orientation = read_calls
                last_write_idx = seq
            elif tid in reads:
                read_calls += 1
                key = (tid, _canon_args(call.get("args")))
                if any(k == key and not err and idx_ > last_write_idx for k, err, idx_ in read_log):
                    redundant += 1
                read_log.append((key, bool(call.get("error")), seq))
            seq += 1
    return {
        "rounds": len(rounds) + omitted, "truncated": omitted > 0, "tokens": tokens,
        "calls": counts, "unmapped": unmapped, "read_calls": read_calls,
        "redundant_reads": redundant,
        "first_write_round": first_write_round,
        "orientation_reads": orientation if first_write_round is not None else read_calls,
    }


# ---- per-wake rows ----------------------------------------------------------


def _run_record_ids(run: dict, records: List[dict]) -> List[str]:
    try:
        listed = json.loads(run.get("records_json") or "[]")
        ids = [r.get("id") for r in listed if isinstance(r, dict) and r.get("id")]
        if ids:
            return ids
    except ValueError:
        pass
    from dfqueue import runs as runs_mod
    if run.get("started_at") and run.get("ended_at"):
        return [r["id"] for r in runs_mod.records_in_window(
            records, run["role"], run["started_at"], run["ended_at"]) if r.get("id")]
    return []


def _at_risk(run: dict, records: List[dict], cls: Classified, idx: dict,
             predictions: dict, runs: List[dict]) -> bool:
    start = _parse(run.get("started_at"))
    if start is None:
        return False
    role = run["role"]
    if role == "overseer":
        for pid, rulings in idx["rulings_by_prop"].items():
            before = [r for r in rulings if (_parse(r.get("ts")) or start) < start]
            if before and before[-1].get("decision") == "defer":
                # still pending at start if its last ruling is a defer
                return True
        return False
    if role not in ADVISOR_ROLES:
        return False
    wstart = _window_start(start, role, runs)
    for p in records:
        if p.get("kind") != "proposal" or p.get("role") != role:
            continue
        pts = _parse(p.get("ts"))
        if pts is None or pts >= start or pts < wstart:
            continue
        if _status_at(p["id"], start, idx["rulings_by_prop"], idx["closes_by_ruling"],
                      idx["closes_by_prop"], predictions) != "completed":
            return True
    return False


SWEEP_GAP_S = 120


def _sweeps(runs: List[dict]) -> Dict[str, int]:
    """`{run_id: sweep}`: runs whose start follows the previous run's end by
    under two minutes are one conductor sweep. `runs.cycle` is not usable
    for this (every `--once` run stores 1), so a sweep is the cluster unit."""
    out: Dict[str, int] = {}
    prev_end: Optional[datetime] = None
    sweep = 0
    for run in sorted(runs, key=lambda r: str(r.get("started_at"))):
        start, end = _parse(run.get("started_at")), _parse(run.get("ended_at"))
        if prev_end is None or start is None or (start - prev_end).total_seconds() > SWEEP_GAP_S:
            sweep += 1
        out[run["run_id"]] = sweep
        if end is not None:
            prev_end = end
    return out


def per_wake_rows(queue: dict, runs: List[dict], cls: Classified, epochs: List[dict],
                  allow: Dict[str, Dict[str, set]]) -> List[dict]:
    records = queue["records"]
    predictions = queue["predictions"]
    idx = _index(records)
    by_id = {r.get("id"): r for r in records}
    all_known = set()
    for sec in allow.values():
        all_known |= sec["read"] | sec["write"]
    sweeps = _sweeps(runs)
    rows = []
    for run in runs:
        if not run.get("ended_at"):
            continue
        role = run["role"]
        ids = _run_record_ids(run, records)
        kinds = [by_id[i].get("kind") for i in ids if i in by_id]
        props = [i for i in ids if by_id.get(i, {}).get("kind") == "proposal"]
        m1 = [i for i in props if i in cls.m1]
        m1w = [i for i in props if i in cls.m1_wide]
        m1s = [i for i in props if i in cls.m1_struct]
        m3 = [i for i in props if i in cls.m3]
        m2 = [i for i in ids if i in cls.m2]
        r_events = set(m1) | set(m3) | set(m2)
        killed = bool(run.get("timed_out")) or run.get("status") == "timeout" or run.get("cost_usd") is None
        tm = transcript_metrics(run.get("transcript"), role, allow, all_known)
        passed = (role in ADVISOR_ROLES and "pass" in kinds
                  and not any(k in ("proposal", "ask", "fort_plan") for k in kinds))
        start = _parse(run.get("started_at"))
        hashes = (run.get("charter_hash"), run.get("tools_hash"), run.get("policy_hash"))
        rows.append({
            "run_id": run["run_id"], "role": role,
            "day": start.date().isoformat() if start else None,
            "epoch": epoch_of(run.get("started_at"), epochs, hashes),
            "wake_reason": _safe_word(run.get("wake_reason")),
            "wake_reasons": _wake_reasons(run),
            "sweep": sweeps.get(run["run_id"]), "status": _safe_word(run.get("status")),
            "killed": killed,
            "at_risk": _at_risk(run, records, cls, idx, predictions, runs),
            "m1": len(m1), "m1_wide": len(m1w), "m1_struct": len(m1s), "m2": len(m2), "m3": len(m3),
            "m3_cross_role": len([i for i in props if i in cls.m3_cross]),
            "r": len(r_events),
            "r_ids": sorted(r_events),
            "cost_usd": None if run.get("cost_usd") is None else float(run["cost_usd"]),
            "rounds": tm["rounds"] if tm else None,
            "truncated": bool(tm and tm["truncated"]),
            "first_write_round": tm["first_write_round"] if tm else None,
            "orientation_reads": tm["orientation_reads"] if tm else None,
            "read_calls": tm["read_calls"] if tm else None,
            "redundant_reads": tm["redundant_reads"] if tm else None,
            "tokens": tm["tokens"] if tm else None,
            "calls": tm["calls"] if tm else None,
            "unmapped_calls": tm["unmapped"] if tm else None,
            "passed": passed,
            "source": "transcript" if tm else "missing",
        })
    return rows


def _wake_reasons(run: dict) -> List[str]:
    """Every reason the run was woken for, as safe words; a run recorded before
    the `wake_reasons` column falls back to its one `wake_reason`."""
    from dfqueue import runs as _runs
    got = [w for w in (_safe_word(r) for r in _runs.decode_wake_reasons(run)) if w]
    return got


def _safe_word(value: Any) -> Optional[str]:
    """A keyword from the conductor's own vocabulary, never free text."""
    if value is None:
        return None
    s = str(value)
    return s if re.fullmatch(r"[A-Za-z0-9_.:\-]{1,64}", s) else "other"


# ---- aggregation ------------------------------------------------------------


def _summ(values: List[float]) -> dict:
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0, "mean": None, "median": None, "sum": 0}
    return {"n": len(vals), "mean": round(sum(vals) / len(vals), 6),
            "median": round(statistics.median(vals), 6), "sum": round(sum(vals), 6)}


def _group(rows: List[dict]) -> dict:
    n = len(rows)
    at_risk = [r for r in rows if r["at_risk"]]
    r_total = sum(r["r"] for r in rows)
    reads = sum(r["read_calls"] or 0 for r in rows)
    redundant = sum(r["redundant_reads"] or 0 for r in rows)
    advisors = [r for r in rows if r["role"] in ADVISOR_ROLES]
    tok = {"input": 0, "output": 0, "cache_read": 0, "reasoning": 0}
    for r in rows:
        for k in tok:
            tok[k] += (r["tokens"] or {}).get(k, 0)
    return {
        "wakes": n,
        "killed": sum(1 for r in rows if r["killed"]),
        "at_risk_wakes": len(at_risk),
        "m1": sum(r["m1"] for r in rows), "m1_wide": sum(r["m1_wide"] for r in rows),
        "m1_struct": sum(r["m1_struct"] for r in rows),
        "m2": sum(r["m2"] for r in rows), "m3": sum(r["m3"] for r in rows),
        "m3_cross_role": sum(r["m3_cross_role"] for r in rows),
        "r": r_total,
        "r_per_wake": round(r_total / n, 4) if n else None,
        "r_per_at_risk_wake": round(sum(r["r"] for r in at_risk) / len(at_risk), 4) if at_risk else None,
        "cost": _summ([r["cost_usd"] for r in rows if not r["killed"]]),
        "rounds": _summ([r["rounds"] for r in rows]),
        "rounds_to_first_write": _summ([r["first_write_round"] for r in rows]),
        "orientation_reads": _summ([r["orientation_reads"] for r in rows]),
        "reread_rate": round(redundant / reads, 4) if reads else None,
        "pass_rate": round(sum(1 for r in advisors if r["passed"]) / len(advisors), 4) if advisors else None,
        "tokens": tok,
        "with_transcript": sum(1 for r in rows if r["source"] == "transcript"),
        "truncated": sum(1 for r in rows if r["truncated"]),
    }


def _by(rows: List[dict], key: str) -> dict:
    out: Dict[str, Dict[str, list]] = {}
    for r in rows:
        out.setdefault(str(r[key]), {}).setdefault(r["role"], []).append(r)
    return {k: {role: _group(g) for role, g in sorted(v.items())} for k, v in sorted(out.items())}


def _episodes(rows: List[dict], records: List[dict], cls: Classified) -> dict:
    """Connected components of R events: M1/M3 link a proposal to the earlier
    one it repeats, M2 attaches a defer to its proposal."""
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    for b, a in cls.m1.items():
        union(b, a)
    for b, a in cls.m3.items():
        if a:
            union(b, a)
    events_by_role: Dict[str, List[str]] = {}
    node_of: Dict[str, str] = {}
    for row in rows:
        for rid in row["r_ids"]:
            node = cls.m2.get(rid, rid)
            node_of[rid] = node
            events_by_role.setdefault(row["role"], []).append(rid)
    out = {}
    for role, ev in sorted(events_by_role.items()):
        comps = {find(node_of[e]) for e in ev}
        out[role] = {"events": len(ev), "episodes": len(comps),
                     "events_per_episode": round(len(ev) / len(comps), 3) if comps else None}
    return out


def _bootstrap(rows: List[dict]) -> Optional[dict]:
    """Cluster bootstrap by conductor sweep of R per at-risk wake, 90% interval."""
    clusters: Dict[Any, List[dict]] = {}
    for r in rows:
        key = r["sweep"] if r["sweep"] is not None else r["run_id"]
        clusters.setdefault(key, []).append(r)
    groups = list(clusters.values())
    num = [sum(x["r"] for x in g if x["at_risk"]) for g in groups]
    den = [sum(1 for x in g if x["at_risk"]) for g in groups]
    if sum(den) == 0:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    k = len(groups)
    stats = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        picks = [rng.randrange(k) for _ in range(k)]
        d = sum(den[i] for i in picks)
        if d:
            stats.append(sum(num[i] for i in picks) / d)
    if not stats:
        return None
    stats.sort()
    return {"mean": round(sum(num) / sum(den), 4),
            "lo90": round(stats[int(0.05 * (len(stats) - 1))], 4),
            "hi90": round(stats[int(0.95 * (len(stats) - 1))], 4), "clusters": k}


def _power(rows: List[dict], episodes: dict) -> dict:
    """Projected sample size to detect a 50% cut in R per at-risk wake at 5%
    one-sided and 80% power, inflated by events per episode (red-team 2)."""
    at_risk = [r for r in rows if r["at_risk"]]
    total_events = sum(r["r"] for r in at_risk)
    out = {"r_rate_per_at_risk_wake": None, "events_per_episode": None, "wakes_per_day": None,
           "n_wakes_per_arm_rr50": None, "days_rr50": None}
    if not at_risk:
        return out
    l0 = total_events / len(at_risk)
    days = {r["day"] for r in rows if r["day"]}
    wpd = len(at_risk) / max(1, len(days))
    ev = sum(e["events"] for e in episodes.values())
    ep = sum(e["episodes"] for e in episodes.values())
    epe = ev / ep if ep else 1.0
    out.update({"r_rate_per_at_risk_wake": round(l0, 4), "events_per_episode": round(epe, 3),
                "wakes_per_day": round(wpd, 3)})
    if l0 > 0:
        l1 = l0 * 0.5
        n = (1.645 + 0.842) ** 2 * (1 / l1 + 1 / l0) / (math.log(0.5) ** 2) * max(1.0, epe)
        out["n_wakes_per_arm_rr50"] = int(math.ceil(n))
        out["days_rr50"] = round(2 * n / wpd, 1) if wpd else None
    return out


def _tool_usage(rows: List[dict], allow: Dict[str, Dict[str, set]]) -> dict:
    out: Dict[str, dict] = {}
    for role in sorted({r["role"] for r in rows}):
        rr = [r for r in rows if r["role"] == role]
        calls: Dict[str, int] = {}
        unmapped = 0
        with_t = 0
        for r in rr:
            if r["calls"] is None:
                continue
            with_t += 1
            unmapped += r["unmapped_calls"] or 0
            for k, v in r["calls"].items():
                if _SAFE_TOOL_RE.match(k):
                    calls[k] = calls.get(k, 0) + v
        sec = allow.get(role, {"read": set(), "write": set()})
        out[role] = {
            "wakes_with_transcript": with_t,
            "calls": dict(sorted(calls.items(), key=lambda kv: (-kv[1], kv[0]))),
            "unmapped_calls": unmapped,
            "never_called": sorted((sec["read"] | sec["write"]) - set(calls)) if with_t else [],
        }
    return out


# ---- the public function ---------------------------------------------------


def compute(queue_db: "str | Path", runs_db: "str | Path", since: Optional[str] = None,
            until: Optional[str] = None, roles: Optional[Iterable[str]] = None,
            epochs: Optional[List[dict]] = None, agents_dir: "str | Path" = AGENTS_DIR,
            now: Optional[datetime] = None) -> dict:
    """The publishable report (schema in the module docstring). Reads both
    databases `mode=ro`; classification always uses the whole history so a
    `since` window does not hide the earlier proposal a later one repeats."""
    queue = read_queue(queue_db)
    runs = read_runs(runs_db)
    epochs = load_epochs() if epochs is None else epochs
    allow = load_allowlists(agents_dir)
    cls = classify(queue["records"], queue["predictions"], runs, epochs)
    rows = per_wake_rows(queue, runs, cls, epochs, allow)
    lo, hi = _parse(since) if since else None, _parse(until) if until else None
    want = set(roles) if roles else None

    def keep(row: dict) -> bool:
        run_start = next((_parse(r.get("started_at")) for r in runs if r["run_id"] == row["run_id"]), None)
        if lo and (run_start is None or run_start < lo):
            return False
        if hi and (run_start is None or run_start > hi):
            return False
        return want is None or row["role"] in want

    rows = [r for r in rows if keep(r)]
    attributed = {i for r in rows for i in r["r_ids"]}
    unattributed_repeats = [i for i in set(cls.m1) | set(cls.m3) if i not in attributed]
    episodes = _episodes(rows, queue["records"], cls)
    public_rows = [{k: v for k, v in r.items() if k not in ("r_ids", "calls", "tokens")} for r in rows]
    for pr, r in zip(public_rows, rows):
        pr["tokens"] = r["tokens"]
    by_role: Dict[str, List[dict]] = {}
    for r in rows:
        by_role.setdefault(r["role"], []).append(r)
    return {
        "schema": SCHEMA_ID,
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "since": since, "until": until,
        "definitions": DEFINITIONS,
        "totals": _group(rows),
        "by_role": {role: _group(g) for role, g in sorted(by_role.items())},
        "by_day": _by(rows, "day"),
        "by_epoch": _by(rows, "epoch"),
        "episodes": episodes,
        "interval": {role: {"r_per_at_risk_wake": _bootstrap(g)} for role, g in sorted(by_role.items())},
        "power": _power(rows, episodes),
        "tool_usage": _tool_usage(rows, allow),
        "wakes": public_rows,
        "unattributed": {"repeats": len(unattributed_repeats)},
        "notes": NOTES,
    }


# ---- text report and CLI ------------------------------------------------------


def render_text(report: dict) -> str:
    def f(v: Any) -> str:
        return "-" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))

    lines = [f"wake metrics ({report['schema']}), generated {report['generated_at']}"]
    t = report["totals"]
    lines.append(f"wakes {t['wakes']}  killed {t['killed']}  at-risk {t['at_risk_wakes']}  "
                 f"with transcript {t['with_transcript']}")
    lines.append("")
    lines.append(f"{'role':14}{'wakes':>6}{'atrisk':>7}{'M1':>4}{'M1w':>5}{'M2':>4}{'M3':>4}{'R':>4}"
                 f"{'R/wake':>8}{'R/risk':>8}{'cost$':>8}{'rounds':>8}{'pass':>7}")
    for role, g in report["by_role"].items():
        lines.append(f"{role:14}{g['wakes']:>6}{g['at_risk_wakes']:>7}{g['m1']:>4}{g['m1_wide']:>5}"
                     f"{g['m2']:>4}{g['m3']:>4}{g['r']:>4}{f(g['r_per_wake']):>8}"
                     f"{f(g['r_per_at_risk_wake']):>8}{f(g['cost']['mean']):>8}"
                     f"{f(g['rounds']['mean']):>8}{f(g['pass_rate']):>7}")
    lines.append("")
    lines.append("episodes: " + "; ".join(
        f"{r} {e['events']} events in {e['episodes']} episodes" for r, e in report["episodes"].items()) or "none")
    p = report["power"]
    lines.append(f"power: R/at-risk wake {f(p['r_rate_per_at_risk_wake'])}, "
                 f"events per episode {f(p['events_per_episode'])}, "
                 f"wakes/day {f(p['wakes_per_day'])}, wakes per arm to see a 50% cut "
                 f"{f(p['n_wakes_per_arm_rr50'])}, about {f(p['days_rr50'])} days")
    lines.append("")
    for role, u in report["tool_usage"].items():
        top = ", ".join(f"{k} x{v}" for k, v in list(u["calls"].items())[:8])
        lines.append(f"{role} tools ({u['wakes_with_transcript']} wakes with transcript, "
                     f"{u['unmapped_calls']} unmapped): {top or 'none'}")
        if u["never_called"]:
            lines.append(f"  never called: {len(u['never_called'])} allowlisted tools")
    lines.append("")
    lines.extend(report["notes"])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m dfqueue.wake_metrics", description=__doc__.split("\n")[0])
    ap.add_argument("--queue", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--roles", help="comma separated")
    ap.add_argument("--epochs", help="a wake_epochs.yaml path")
    ap.add_argument("--out", help="write the JSON report here")
    ap.add_argument("--per-wake", help="write one JSON line per wake here")
    ap.add_argument("--text", action="store_true", help="print the plain-text report")
    args = ap.parse_args(argv)
    report = compute(args.queue, args.runs, since=args.since, until=args.until,
                     roles=args.roles.split(",") if args.roles else None,
                     epochs=load_epochs(args.epochs) if args.epochs else None)
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.per_wake:
        with open(args.per_wake, "w", encoding="utf-8") as fh:
            for row in report["wakes"]:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    if args.text or not args.out:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
