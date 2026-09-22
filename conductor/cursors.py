"""Per-role diff cursors: `docs/AGENT-ARCHITECTURE.md` §4, "Each role keeps
its own cursor into the diff stream, so a woken specialist receives 'what
changed in your domain since you last woke' rather than a general
briefing." `diff.since CURSOR` (`scripts/dfhack/df-overseer-diff.lua`)
returns `{"cursor": "<new cursor>", "events": [...]}`; nothing in this
project persisted a per-role cursor across cycles before this stream, so
the conductor owns that state: one small JSON file, read at cycle start and
written back after a role's diff has actually been drained and handed to
that role in its briefing.

Deliberately NOT a database: this is small, local, single-writer state (one
conductor process), the same class of thing `dfhack-config/overseer-clock/
tripwire_latch.json` already is on the DFHack side (see
`scripts/dfhack/df-overseer-clock.lua`'s own header for why a file, not
something fancier, is the right amount of mechanism there too).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Dict

#: The initial cursor for a role that has never woken yet. `diff.since`'s
#: own cursor scheme is a monotonic event id starting above 0
#: (`drain_since`'s `e.id > cursor`), so 0 means "everything since the
#: beginning of this fort's recorded events" -- exactly what a role's very
#: first wake should see.
INITIAL_CURSOR = 0


class CursorStoreError(Exception):
    """The cursor file exists but is not valid JSON, or is not a mapping of
    role -> cursor. Never silently treated as "no cursors yet": a corrupt
    file could otherwise cause a role to silently replay its entire event
    history (harmless but wasteful) or, worse, be masked as fresh forever."""


class CursorStore:
    """Reads and writes `path` as `{"role": cursor, ...}`. One instance per
    conductor process; not safe for two processes to share the same path
    concurrently (matching this whole package's single-writer assumption --
    exactly one conductor service is ever meant to run against one fort).
    """

    def __init__(self, path: "Path | str"):
        self.path = Path(path)

    def load(self) -> Dict[str, int]:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CursorStoreError(f"{self.path}: not valid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise CursorStoreError(f"{self.path}: expected a JSON object, got {type(raw).__name__}")
        try:
            return {str(role): int(cursor) for role, cursor in raw.items()}
        except (TypeError, ValueError) as exc:
            raise CursorStoreError(f"{self.path}: every cursor value must be an integer: {exc}") from exc

    def get(self, role: str) -> int:
        return self.load().get(role, INITIAL_CURSOR)

    def set(self, role: str, cursor: int) -> None:
        """Read-modify-write, atomically replacing the file (write to a
        sibling temp file, then `os.replace`) so a crash mid-write never
        leaves a half-written, unparseable cursor file behind -- the same
        atomicity concern `dfqueue.store`'s own `with conn:` transactions
        exist for, applied to a plain file instead of SQLite."""
        cursors = self.load()
        cursors[str(role)] = int(cursor)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp",
        )
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump(cursors, fh, indent=2, sort_keys=True)
            Path(tmp_name).replace(self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def all(self) -> Dict[str, int]:
        return self.load()
