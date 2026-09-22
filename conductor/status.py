"""Status and alerts: `docs/AGENT-LOOP.md` build item 1's own bullet --
"a status JSON (state, last cycle, clock level and why, latched tripwire)
and journald lines. An escalation from the Overseer leaves the fort paused
and says so loudly."

Two halves:

- `write_status`: a small, always-overwritten JSON file holding only the
  CURRENT state, not a log -- matching this project's own established
  split between a status snapshot and journald as the real log
  (`dfhack-config/overseer-clock/tripwire_latch.json` is the same shape of
  thing on the DFHack side; `dfmcp/server.py`'s own call log is the
  journald half there). Atomic (temp file + replace), same discipline as
  `conductor/cursors.py`'s `CursorStore.set` -- a status file a monitor
  polls must never be readable half-written.
- `configure_logging`/`log_cycle`: every log record to stderr as one line,
  so under systemd (`Type=simple`) it lands in journald exactly like
  `dfmcp/server.py`'s own `_configure_call_log`. An escalation logs at
  `ERROR`, loud by construction -- `journalctl -u conductor.service -p err`
  finds it without grepping for a magic string.
"""

from __future__ import annotations

import json
import logging
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from conductor.cycle import CycleResult

LOG = logging.getLogger("conductor.status")


def configure_logging(level: int = logging.INFO) -> None:
    """Only `conductor/service.py`'s real entry point calls this -- tests
    see log records through pytest's own capture instead, matching
    `dfmcp/server.py`'s `_configure_call_log`'s own convention."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    root = logging.getLogger("conductor")
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False


def status_from_cycle(result: CycleResult, *, state: str = "running") -> Dict[str, Any]:
    """`state`: the conductor service's own lifecycle word (`"running"`,
    `"starting"`, `"stopped"`) -- distinct from `result.clock_level`, which
    is the FORT's own state, not the service's."""
    return {
        "state": state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_cycle": {
            "cycle_index": result.cycle_index,
            "game_tick": result.game_tick,
            "clock_level": result.clock_level,
            "roles_woken": list(result.roles_woken),
            "dry_run": result.dry_run,
        },
        "tripwire": result.tripwire,
        "escalated": result.escalated,
    }


def write_status(path: "Path | str", status: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            json.dump(status, fh, indent=2, sort_keys=True, default=str)
        Path(tmp_name).replace(path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def log_cycle(result: CycleResult) -> None:
    """One log line per cycle, at the severity the outcome deserves. An
    escalation is the one case this project's own convention (CLAUDE.md's
    "check live state before escalating" memory rule, applied in reverse
    here -- an actual escalation must never read as routine) requires
    `ERROR`, never `WARNING` or `INFO`."""
    if result.tripwire is not None and result.escalated:
        LOG.error(
            "ESCALATION: cycle %s's Overseer run did not resolve the tripwire; "
            "the fort stays PAUSED. tripwire=%s",
            result.cycle_index, result.tripwire,
        )
    elif result.tripwire is not None:
        LOG.warning(
            "cycle %s: tripwire handled and the fort resumed. tripwire=%s",
            result.cycle_index, result.tripwire,
        )
    else:
        LOG.info(
            "cycle %s: clock=%s roles_woken=%s dry_run=%s",
            result.cycle_index, result.clock_level, result.roles_woken, result.dry_run,
        )
