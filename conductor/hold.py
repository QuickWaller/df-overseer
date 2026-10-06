"""The operator hold (`handoffs/2026-10-05-operator-hold.md`).

A fort the operator keeps paused on purpose must not be treated by the pause
watchdog as something to resolve. The hold is the operator's explicit say-so:
while it stands the conductor never resumes the fort by any route, and a plain
pause takes the ordinary cycle path (roles wake on their usual signals, the
stuck-job watch polls) instead of waiting or waking the Overseer.

Operator only. This module is a CLI (`python -m conductor.hold set|clear|show`)
plus a read-only view for the cycle. There is no MCP tool and no role
allowlist entry for it: an agent cannot set or clear a hold. The hold only
ever REMOVES resume paths, never adds one.

A corrupt or unreadable hold file reads as HELD: the safe error direction is
"never resume", so "reads as no hold" is the one mistake that must not happen.
A missing file is no hold. An optional expiry turns a forgotten hold back into
no hold (and says so in the log).
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

LOG = logging.getLogger("conductor.hold")

HOLD_FILE_NAME = "hold.json"
CURSOR_STORE_ENV = "CONDUCTOR_CURSOR_STORE_PATH"


@dataclass(frozen=True)
class HoldState:
    held: bool = False
    reason: Optional[str] = None
    since: Optional[float] = None
    who: Optional[str] = None
    expires_at: Optional[float] = None
    corrupt: bool = False
    expired: bool = False
    #: The operator allows the execute phase while held (docs/CONDUCTOR-
    #: EXECUTION.md 4.5): routed steps still run, the fort is still never
    #: resumed. Anything but a literal true reads as False, and a corrupt file
    #: never allows it.
    allow_execution: bool = False

    def as_dict(self) -> Optional[Dict[str, Any]]:
        """The block for the status file and the dry-run plan: None when no hold."""
        if not self.held:
            return None
        return {
            "reason": self.reason, "since": self.since, "who": self.who,
            "expires_at": self.expires_at, "corrupt": self.corrupt,
            "allow_execution": self.allow_execution,
        }


NO_HOLD = HoldState()


def _corrupt(path: Path, why: str) -> HoldState:
    LOG.error("operator hold file %s is unreadable (%s); reading it as HELD, never resume", path, why)
    return HoldState(held=True, reason=f"hold file unreadable ({why}); treated as held", corrupt=True)


class HoldStore:
    def __init__(self, path: "Path | str"):
        self.path = Path(path)

    def read(self, now: Optional[float] = None) -> HoldState:
        """Total: never raises. Anything unreadable is a hold."""
        try:
            return self._read(time.time() if now is None else now)
        except Exception as exc:  # noqa: BLE001 -- fail toward never resuming
            return _corrupt(self.path, type(exc).__name__)

    def _read(self, now: float) -> HoldState:
        if not self.path.exists():
            return NO_HOLD
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _corrupt(self.path, "not valid JSON")
        if not isinstance(raw, dict):
            return _corrupt(self.path, "not a JSON object")
        reason, since, who, expires = raw.get("reason"), raw.get("since"), raw.get("who"), raw.get("expires_at")
        if not isinstance(reason, str) or not reason.strip():
            return _corrupt(self.path, "no reason")
        num = (int, float)
        if isinstance(since, bool) or not isinstance(since, num):
            return _corrupt(self.path, "bad since")
        if expires is not None and (isinstance(expires, bool) or not isinstance(expires, num)):
            return _corrupt(self.path, "bad expires_at")
        if expires is not None and now >= expires:
            LOG.warning("operator hold (%r, set by %s) has expired; reading as no hold", reason, who)
            return HoldState(held=False, reason=reason, since=since, who=who, expires_at=expires, expired=True)
        return HoldState(held=True, reason=reason, since=since, who=str(who) if who else None, expires_at=expires,
                         allow_execution=raw.get("allow_execution") is True)

    def set(self, reason: str, *, who: Optional[str] = None, now: Optional[float] = None,
            expires_in_seconds: Optional[float] = None, allow_execution: bool = False) -> HoldState:
        reason = " ".join((reason or "").split())
        if not reason:
            raise ValueError("a hold needs a reason (one line)")
        if expires_in_seconds is not None and expires_in_seconds <= 0:
            raise ValueError("expiry must be positive")
        now = time.time() if now is None else now
        doc = {
            "reason": reason, "since": now, "who": who or _os_user(),
            "expires_at": None if expires_in_seconds is None else now + expires_in_seconds,
            "allow_execution": bool(allow_execution),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2, sort_keys=True)
            Path(tmp_name).replace(self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return self.read(now)

    def clear(self) -> bool:
        """True when a file was removed."""
        if not self.path.exists():
            return False
        self.path.unlink()
        return True


def _os_user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return "operator"


def hold_path_for(cursor_store_path: "Path | str") -> Path:
    """Beside `pause_watch.json` (which sits beside the cursor store)."""
    return Path(cursor_store_path).with_name(HOLD_FILE_NAME)


def _fmt(ts: Optional[float]) -> str:
    return "never" if ts is None else time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))


def describe(state: HoldState) -> str:
    if state.expired:
        return f"no hold (the hold {state.reason!r} set by {state.who} expired {_fmt(state.expires_at)})"
    if not state.held:
        return "no hold"
    tag = " [CORRUPT FILE, read as held]" if state.corrupt else ""
    ex = "; routed steps still run (--allow-execution)" if state.allow_execution else "; no routed steps run"
    return (f"HELD{tag}: {state.reason} (since {_fmt(state.since)}, by {state.who or 'unknown'}, "
            f"expires {_fmt(state.expires_at)}{ex})")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m conductor.hold",
        description="Operator-only hold: keep the fort paused on purpose so the conductor never resumes it.",
    )
    parser.add_argument(
        "--cursor-store", default=os.environ.get(CURSOR_STORE_ENV),
        help=f"the conductor's cursor store path (default: ${CURSOR_STORE_ENV}); hold.json lives beside it",
    )
    parser.add_argument("--file", help="explicit hold file path (overrides --cursor-store)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_set = sub.add_parser("set", help="set a hold")
    p_set.add_argument("--reason", required=True)
    p_set.add_argument("--who", default=None, help="default: the OS user")
    p_set.add_argument("--for-hours", type=float, default=None, help="optional expiry")
    p_set.add_argument(
        "--allow-execution", action="store_true",
        help="let the execute phase run routed steps while held (it still never resumes the fort)",
    )
    sub.add_parser("clear", help="clear the hold")
    sub.add_parser("show", help="show the hold")
    args = parser.parse_args(argv)

    if args.file:
        path = Path(args.file)
    elif args.cursor_store:
        path = hold_path_for(args.cursor_store)
    else:
        parser.error(f"give --cursor-store or --file, or set ${CURSOR_STORE_ENV}")
    store = HoldStore(path)
    if args.cmd == "set":
        try:
            state = store.set(args.reason, who=args.who,
                              expires_in_seconds=None if args.for_hours is None else args.for_hours * 3600,
                              allow_execution=args.allow_execution)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(describe(state))
    elif args.cmd == "clear":
        print("hold cleared" if store.clear() else "there was no hold file")
    else:
        print(describe(store.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
