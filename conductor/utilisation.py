"""Utilisation sampling: how many citizens sleep, eat and drink at once.

Fort roadmap V1, item 6 (`research/2026-10-08-roadmap-role-red-team.md`
finding 1 and section 3). A capacity number in the roadmap ("about a tenth of
a fort sleeps at once", "one fifth eats at once") is a queueing claim, and a
queueing claim can be measured inside one fort: every cycle the conductor
counts the citizens whose `current_job` is a Sleep, Eat or Drink job, per
alive citizen, and appends one row to a series. The Planner reads a summary
in its briefing (peak and 90th percentile); the Elder (V2) reads the series.

The read is `labor.unit-status`, already a one-JSON-object tool (`{filter,
count, citizens: [{id, job, ...}]}`, `scripts/dfhack/df-overseer-labor.lua`),
so this costs one existing read per cycle and adds no tool. A paused fort
holds one instant; a sample is not appended twice for the same game tick, so
a run of cycles on a paused game does not weigh one moment many times.

Pure functions plus one append-only JSONL store. Total by design: a read that
cannot be parsed is `None`, never a zero.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

#: The read each cycle (agents/conductor/tools.yaml).
UNIT_STATUS_TOOL = "labor.unit-status"

#: Job names, as `dfhack.job.getName` prints a citizen's current job, whose
#: concurrent count is the signal. Data: another measure is one more entry.
UTILISATION_JOBS: Dict[str, tuple] = {"sleep": ("Sleep",), "eat": ("Eat",), "drink": ("Drink",)}

#: How many of the newest samples the Planner's summary covers.
SUMMARY_WINDOW = 200


def _valid_alive(alive: Any) -> bool:
    return isinstance(alive, (int, float)) and not isinstance(alive, bool) and alive > 0


def sample(unit_status: Any, alive: Any, tick: Any) -> Optional[dict]:
    """One row from a `labor.unit-status` read: the count of citizens holding
    each measured job and its ratio per alive citizen (`alive` from
    `vitals.summary` when it is a positive number, else the citizens read).
    `None` when the read has no citizen list or the tick is unknown."""
    rows = unit_status.get("citizens") if isinstance(unit_status, Mapping) else None
    if not isinstance(rows, list) or isinstance(tick, bool) or not isinstance(tick, int):
        return None
    n = len(rows)
    denom = float(alive) if _valid_alive(alive) else float(n)
    out: dict = {"tick": tick, "alive": alive if _valid_alive(alive) else None, "citizens": n}
    names = [str(r.get("job")) if isinstance(r, Mapping) else "" for r in rows]
    for kind, job_names in UTILISATION_JOBS.items():
        c = sum(1 for nm in names if nm in job_names)
        out[kind] = c
        out[f"{kind}_per_alive"] = round(c / denom, 4) if denom > 0 else None
    return out


def summarise(samples: Iterable[Mapping]) -> dict:
    """Peak, 90th percentile and latest of each per-alive ratio over the rows
    given, with the row count (a thin series says it is thin)."""
    rows = [s for s in samples if isinstance(s, Mapping)]
    out: dict = {"samples": len(rows)}
    for kind in UTILISATION_JOBS:
        key = f"{kind}_per_alive"
        vals = sorted(
            float(s[key]) for s in rows
            if isinstance(s.get(key), (int, float)) and not isinstance(s.get(key), bool)
        )
        if not vals:
            out[kind] = None
            continue
        last = rows[-1].get(key)
        out[kind] = {
            "peak": vals[-1], "p90": vals[min(len(vals) - 1, int(0.9 * len(vals)))],
            "last": last if isinstance(last, (int, float)) and not isinstance(last, bool) else None,
        }
    if rows:
        out["last_tick"] = rows[-1].get("tick")
    return out


class UtilisationStore:
    """The series, one JSON object per line, beside the cursor store. Append
    only; a torn or unreadable line is skipped on read, never fatal."""

    def __init__(self, path: "Path | str"):
        self.path = Path(path)

    def rows(self) -> List[dict]:
        if not self.path.is_file():
            return []
        out: List[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                out.append(row)
        return out

    def append(self, row: Mapping) -> bool:
        """Append `row` unless the newest row is for the same game tick (a
        paused fort holds one instant; a tick that went backwards after a
        reload is a new instant and is recorded). True when written."""
        existing = self.rows()
        if existing and existing[-1].get("tick") == row.get("tick"):
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
        return True

    def summary(self, window: int = SUMMARY_WINDOW) -> dict:
        return summarise(self.rows()[-window:])
