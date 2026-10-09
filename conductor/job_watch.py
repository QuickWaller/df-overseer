"""Stuck jobs: polled from `stuckjobs.find`, because nothing emits an event.

`conductor/cycle.py` used to set the `stuck_job` wake only from a drained
`diff.since` event of type `job_stalled`; nothing emits that type (the
2026-10-05 diagnosis, `evals/live/2026-10-05-stuck-jobs-diagnosis/`), so a Bed,
two digs, a brew and a Wall sat for days with nobody woken. Same shape as the
stalled-manager-order problem, so the same answer as `conductor/order_watch.py`:
poll each cycle, keep a first-seen clock per item, wake once the item has
held for a threshold, and renotify on a slow cadence rather than every cycle.

What counts as stuck
--------------------
Any job `stuckjobs.find` returns (it lists only jobs with no worker) that has
been seen in that state continuously for at least a threshold of game ticks.
Two classes, thresholds in `conductor/policy.yaml`:

- **unclaimed**: no worker, not suspended.
- **suspended**: `waiting_on == "suspended"`. Often a deliberate wait
  (buildingplan holds a job until an item attaches), so it has its own
  threshold key, but it is still reported: the Bed and the Wall that sat for
  days were both suspended.

Age is measured from the conductor's own first sighting, deliberately not from
the tool's `idle_ticks`: that is time since the job *started*, so a long job
whose worker merely stepped away to sleep would read as old on one poll. A job
that leaves the list (a worker claimed it, it finished or was cancelled) is
dropped from state, so a later stall on a similar job starts a fresh clock.

Keying
------
`stuckjobs.find` returns no job id and no coordinates. The key is the job's
type, detail, building, nearest landmark with direction and distance, and
order id, plus an occurrence index so two identical jobs at one spot stay
distinct. Known weakness: if a nearer landmark appears the job's key changes
and its clock restarts. A `job_id` field on the Lua tool would replace this;
until then the cost is a late wake, never a wrong action (this module only
reports).

This module never unsuspends, reassigns or cancels anything; its output is a
count, some short lines and a wake.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from conductor import backoff

TICKS_PER_GAME_DAY = 1200

UNCLAIMED = "unclaimed"
SUSPENDED = "suspended"

#: Lines named in a wake's detail string (the briefing digest has its own cap).
MAX_DETAIL_LINES = 3


@dataclass(frozen=True)
class StuckJob:
    key: str
    kind: str
    age_ticks: int
    line: str


@dataclass(frozen=True)
class JobWatchResult:
    #: Every job past its threshold this cycle, oldest first.
    stuck: Tuple[StuckJob, ...] = ()
    #: The subset due to wake someone (not notified within the renotify window).
    due: Tuple[StuckJob, ...] = ()

    @property
    def any_due(self) -> bool:
        return bool(self.due)

    @property
    def lines(self) -> List[str]:
        return [j.line for j in self.stuck]

    def wake_detail(self) -> str:
        if not self.due:
            return ""
        shown = "; ".join(j.line for j in self.due[:MAX_DETAIL_LINES])
        extra = len(self.due) - MAX_DETAIL_LINES
        more = f"; and {extra} more" if extra > 0 else ""
        noun = "job" if len(self.due) == 1 else "jobs"
        return f"{len(self.due)} stuck {noun}: {shown}{more}"


class JobWatchStore:
    """`{"jobs": {key: {"first_seen": tick, "last_notified": tick | null}}}`.
    Single-writer like `CursorStore`; a missing file is a fresh state, a
    corrupt one raises (the caller treats that as a failed poll, loudly)."""

    def __init__(self, path: "Path | str"):
        self.path = Path(path)

    def load(self) -> Dict[str, Dict[str, Optional[int]]]:
        if not self.path.is_file():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        jobs = raw.get("jobs") if isinstance(raw, dict) else None
        if not isinstance(jobs, dict):
            raise ValueError(f"{self.path}: expected an object with a 'jobs' object")
        return {str(k): dict(v) for k, v in jobs.items() if isinstance(v, dict)}

    def save(self, jobs: Mapping[str, Mapping[str, Optional[int]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump({"jobs": jobs}, fh, indent=2, sort_keys=True)
            Path(tmp_name).replace(self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _kind(job: Mapping) -> str:
    return SUSPENDED if job.get("waiting_on") == "suspended" else UNCLAIMED


def _base_key(job: Mapping) -> str:
    return "|".join(_text(job.get(f)) for f in (
        "job_type", "detail", "building", "near_landmark", "direction", "distance_tiles", "order_id",
    ))


def _name(job: Mapping) -> str:
    return _text(job.get("detail")) or _text(job.get("job_type")) or "job"


def _where(job: Mapping) -> str:
    landmark = _text(job.get("near_landmark"))
    if not landmark:
        return ""
    dist = job.get("distance_tiles")
    direction = _text(job.get("direction"))
    offset = " ".join(p for p in (f"{dist} tiles" if dist is not None else "", direction) if p)
    return f", {offset} of {landmark}" if offset else f", near {landmark}"


def describe(job: Mapping, kind: str, age_ticks: int) -> str:
    """One short line: `Construct Bed suspended for 3 game days, 4 tiles N of Well`."""
    days = max(1, age_ticks // TICKS_PER_GAME_DAY)
    unit = "game day" if days == 1 else "game days"
    state = "suspended" if kind == SUSPENDED else "unclaimed"
    return f"{_name(job)} {state} for {days} {unit}{_where(job)}"


def evaluate_jobs(
    jobs: Iterable[Mapping],
    *,
    game_tick: Optional[int],
    unclaimed_threshold_ticks: int,
    suspended_threshold_ticks: int,
    renotify_ticks: int,
    store: JobWatchStore,
    dry_run: bool,
    renotify_cap_ticks: int = 100800,
    max_wakes: int = 3,
    retry_tick: Optional[int] = None,
) -> JobWatchResult:
    """One call per cycle over `stuckjobs.find`'s array. A dry run reads state
    but never writes it. `game_tick=None` returns an empty result and leaves
    state alone, as `evaluate_orders` does."""
    if game_tick is None:
        return JobWatchResult()

    state = store.load()
    new_state: Dict[str, Dict[str, Optional[int]]] = {}
    seen_counts: Dict[str, int] = {}
    stuck: List[StuckJob] = []
    due: List[StuckJob] = []

    for job in jobs:
        if not isinstance(job, Mapping):
            continue
        if job.get("auto_followed") or job.get("waiting_on") == "auto_followed":
            # A dig on a tile the game auto-followed onto (research/2026-10-09-auto-mine.md
            # 4.4): not a failure of ours, never a stuck-job wake.
            continue
        base = _base_key(job)
        index = seen_counts.get(base, 0)
        seen_counts[base] = index + 1
        key = f"{base}#{index}"
        kind = _kind(job)

        prior = state.get(key) or {}
        first_seen = prior.get("first_seen")
        if first_seen is None or first_seen > game_tick:
            first_seen = game_tick
        last_notified = prior.get("last_notified")
        # Wakes already sent (conductor/backoff.py); state from before the
        # backoff has a last-notified tick and no count: that was one wake.
        wakes = int(prior.get("wakes") or (1 if last_notified is not None else 0))
        entry: Dict[str, Any] = {
            "first_seen": first_seen, "last_notified": last_notified, "wakes": wakes,
            "stalled": wakes >= max_wakes,
        }
        new_state[key] = entry

        age = max(0, game_tick - first_seen)
        threshold = suspended_threshold_ticks if kind == SUSPENDED else unclaimed_threshold_ticks
        if age < threshold:
            continue

        item = StuckJob(key=key, kind=kind, age_ticks=age, line=describe(job, kind, age))
        stuck.append(item)
        rt = retry_tick if retry_tick is not None else game_tick  # backoff clock (conductor/backoff.py RetryClock)
        rule = backoff.Backoff(renotify_ticks, renotify_cap_ticks, max_wakes)
        rec, is_due, _ = backoff.advance(
            {"last": last_notified or 0, "wakes": wakes, "stalled": entry["stalled"]} if wakes else None,
            rt, rule,
        )
        if is_due:
            due.append(item)
            entry["last_notified"] = rt
            entry["wakes"] = rec["wakes"]
            entry["stalled"] = rec["stalled"]

    if not dry_run:
        store.save(new_state)

    stuck.sort(key=lambda j: -j.age_ticks)
    due.sort(key=lambda j: -j.age_ticks)
    return JobWatchResult(stuck=tuple(stuck), due=tuple(due))


def jobs_from_result(result: Any) -> List[Mapping]:
    """`stuckjobs.find` prints a bare JSON array. Tolerate a dict wrapper
    (`jobs` or `result`) in case a transport ever adds one; anything else is
    an empty list rather than a guess."""
    if isinstance(result, list):
        return [j for j in result if isinstance(j, Mapping)]
    if isinstance(result, Mapping):
        for k in ("jobs", "result"):
            if isinstance(result.get(k), list):
                return [j for j in result[k] if isinstance(j, Mapping)]
    return []
