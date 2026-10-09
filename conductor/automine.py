"""The automine pass: the conductor's once-per-cycle call to `automine.scan`.

research/2026-10-09-auto-mine.md, decisions/DECISIONS.md 2026-10-09 "Auto
mining". `automine.scan` (scripts/dfhack/df-overseer-automine.lua) designates
revealed ore and gem tiles next to digs we made, for the game's own automatic
mining, and clears auto mining near a cavern breach. It changes the fort, so it
is conductor code and not a model's tool: `automine.scan` is on the conductor's
allowlist only, and this phase is skipped under an operator hold (it never
runs while the operator keeps the fort paused on purpose, whatever the
`--allow-execution` setting; the hold removes it entirely).

This module is pure plumbing and total. A fault (the tool not deployed, a
refusal, a bad reply) logs and returns a skipped report; it never stops a
cycle and never touches the clock.

The cavern note. A breach is reported after the Overseer has already run this
cycle, so the one-line note is kept in a small state file
(`automine_state.json` beside the cursor store) and shown in the Overseer's
NEXT briefing, then cleared.
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Mapping, Optional

LOG = logging.getLogger("conductor.automine")

TOOL = "automine.scan"
MAX_NOTES = 3
MAX_NOTE_CHARS = 240


@dataclass
class AutomineReport:
    ran: bool = False
    skipped: Optional[str] = None
    designated: int = 0
    in_reservation: int = 0
    cavern_breaches: int = 0
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "ran": self.ran, "skipped": self.skipped, "designated": self.designated,
            "in_reservation": self.in_reservation, "cavern_breaches": self.cavern_breaches,
            "notes": list(self.notes), "error": self.error,
        }


class AutomineStore:
    """`{"notes": [str]}`: cavern notes waiting for the Overseer's next briefing."""

    def __init__(self, path: "Path | str"):
        self.path = Path(path)

    def load(self) -> List[str]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        notes = raw.get("notes") if isinstance(raw, dict) else None
        return [str(n) for n in notes][:MAX_NOTES] if isinstance(notes, list) else []

    def save(self, notes: List[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump({"notes": notes[:MAX_NOTES]}, fh)
            Path(tmp).replace(self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def add(self, note: str) -> None:
        notes = self.load()
        note = note[:MAX_NOTE_CHARS]
        if note not in notes:
            notes.append(note)
        self.save(notes[-MAX_NOTES:])

    def take(self) -> List[str]:
        """The pending notes, cleared. Total: an unreadable store reads empty."""
        notes = self.load()
        if notes:
            try:
                self.save([])
            except OSError:
                LOG.warning("could not clear the automine note store %s", self.path)
        return notes


def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


async def run_automine(
    call: Callable[[str, Mapping[str, Any]], Awaitable[Any]], *, enabled: bool, held: bool,
    escalated: bool, store: Optional[AutomineStore], max_per_call: Optional[int] = None,
) -> AutomineReport:
    """One call per cycle. Skipped when disabled in policy, under any operator
    hold, or after an escalation this cycle."""
    if not enabled:
        return AutomineReport(skipped="disabled in policy")
    if held:
        return AutomineReport(skipped="operator hold")
    if escalated:
        return AutomineReport(skipped="an escalation this cycle")
    args = {"max": max_per_call} if max_per_call else {}
    try:
        reply = await call(TOOL, args)
    except Exception as exc:  # noqa: BLE001 -- total by design
        LOG.warning("automine.scan failed: %s", exc)
        return AutomineReport(skipped="the scan raised", error=str(exc)[:200])
    if not isinstance(reply, Mapping) or reply.get("ok") is False:
        err = reply.get("error") if isinstance(reply, Mapping) else "not a mapping"
        LOG.warning("automine.scan was not ok: %s", err)
        return AutomineReport(skipped="the scan reported an error", error=str(err)[:200])
    rep = AutomineReport(ran=True, designated=_int(reply.get("designated")),
                         in_reservation=_int(reply.get("in_reservation")))
    cavern = reply.get("cavern")
    if isinstance(cavern, Mapping):
        rep.cavern_breaches = _int(cavern.get("breaches"))
        note = str(cavern.get("note") or "").strip()
        if note:
            rep.notes.append(note[:MAX_NOTE_CHARS])
            if store is not None:
                try:
                    store.add(note)
                except Exception:  # noqa: BLE001
                    LOG.exception("could not store the cavern note")
    return rep
