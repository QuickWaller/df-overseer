"""The cycle archive: `docs/AGENT-LOOP.md` item 3/build item 1's "Archive"
bullet -- "each cycle under a gitignored `runtime/` directory: the
briefing, each run's JSON envelope, cost, wall-clock, and the clock changes
made. A daily cost total in the log (no spend cap: the user's standing
call)."

One directory per cycle under `root` (the deploy sets this to `runtime/
cycles/` on VM 106 -- see `.gitignore`'s new `runtime/` line and this
stream's report for the exact deploy path), holding:

- `summary.json` -- the cycle's own top-level facts (game tick, clock
  level and why, which roles woke, wall-clock duration).
- `briefings.json` -- every role's own `conductor.briefing.build_briefing`
  output this cycle, keyed by role.
- `clock_changes.json` -- every `clock.*` call the conductor actually made
  this cycle, in order.
- `run-<role>.json` -- one file per role actually launched this cycle, the
  full `RunResult` envelope from `conductor/runner.py` (cost, wall-clock,
  tool calls, final answer).

Nothing here decides WHAT to archive -- `conductor/cycle.py` assembles the
data and calls `write_cycle` once per cycle, so this module stays a plain,
testable file-writer with no DFHack/MCP knowledge of its own.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _json_default(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    raise TypeError(f"not JSON serialisable: {type(obj).__name__}")


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


class CycleArchive:
    """One instance per conductor service run, wrapping `root` (e.g.
    `runtime/cycles`). Not safe for two processes to write the same `root`
    concurrently -- matching this whole package's single-conductor
    assumption (`conductor/cursors.py`'s own docstring makes the same
    point)."""

    def __init__(self, root: "Path | str"):
        self.root = Path(root)

    def cycle_dir(self, cycle_index: int, *, started_at: Optional[str] = None) -> Path:
        """`started_at` (UTC, `YYYYmmddTHHMMSSZ`) is folded into the
        directory name so cycles sort chronologically by name and a service
        restart can never collide two cycles onto the same directory the
        way a bare `cycle_index` counter (reset to 0 on restart) could."""
        started_at = started_at or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return self.root / f"cycle-{cycle_index:06d}-{started_at}"

    def write_cycle(
        self, cycle_index: int, *, summary: Dict[str, Any], briefings: Dict[str, Any],
        clock_changes: List[Dict[str, Any]], role_runs: List[Dict[str, Any]],
        started_at: Optional[str] = None,
    ) -> Path:
        """Write one cycle's full archive. `role_runs` is a list of
        `RunResult`-shaped dicts (`conductor/runner.py`), each carrying its
        own `role` key -- written to `run-<role>.json` so a reader can find
        one role's run without parsing every other role's. Returns the
        directory written, so `conductor/cycle.py` can log its path."""
        cycle_dir = self.cycle_dir(cycle_index, started_at=started_at)
        cycle_dir.mkdir(parents=True, exist_ok=True)

        _write_json(cycle_dir / "summary.json", summary)
        _write_json(cycle_dir / "briefings.json", briefings)
        _write_json(cycle_dir / "clock_changes.json", clock_changes)
        for run in role_runs:
            role = run.get("role") if isinstance(run, dict) else getattr(run, "role", None)
            role = role or "unknown"
            _write_json(cycle_dir / f"run-{role}.json", run)

        return cycle_dir

    def append_daily_cost(self, date: str, cost_usd: Optional[float]) -> float:
        """Add `cost_usd` to `date`'s running total
        (`<root>/cost/<date>.json: {"date", "cost_usd", "unknown_runs"}`) and
        return the new KNOWN total. `cost_usd=None` (a killed or otherwise
        cost-less run) adds nothing to the total and increments
        `unknown_runs` instead: an unknown cost is never recorded as 0.0, so
        the total is a floor, and `daily_unknown_runs` says how many runs it
        does not cover. A durable counter across process restarts, not a
        database."""
        cost_dir = self.root / "cost"
        cost_dir.mkdir(parents=True, exist_ok=True)
        path = cost_dir / f"{date}.json"

        total, unknown = 0.0, 0
        if path.is_file():
            existing = json.loads(path.read_text(encoding="utf-8"))
            total = float(existing.get("cost_usd", 0.0))
            unknown = int(existing.get("unknown_runs", 0))
        if cost_usd is None:
            unknown += 1
        else:
            total += float(cost_usd)

        _write_json(path, {"date": date, "cost_usd": total, "unknown_runs": unknown})
        return total

    def daily_cost(self, date: str) -> float:
        """The known total (a floor when `daily_unknown_runs` is nonzero)."""
        path = self.root / "cost" / f"{date}.json"
        if not path.is_file():
            return 0.0
        return float(json.loads(path.read_text(encoding="utf-8")).get("cost_usd", 0.0))

    def daily_unknown_runs(self, date: str) -> int:
        path = self.root / "cost" / f"{date}.json"
        if not path.is_file():
            return 0
        return int(json.loads(path.read_text(encoding="utf-8")).get("unknown_runs", 0))
