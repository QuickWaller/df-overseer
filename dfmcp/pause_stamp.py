"""The pause stamp (decision 10, register 2026-10-09).

While the fort is paused, every tool reply an agent receives carries a short
`fort_paused` field, so a model mid-run learns the fort is paused (the only
verified way to reach a model mid-turn). Nothing is added while the game runs.

State source: the game's own `clock.status` (`paused`, a latched `tripwire`,
a `blocking_panel`), read through the server's own DFHack call and cached for
`ttl` seconds, so a burst of tool calls costs at most one extra round trip per
window, shared by concurrent calls. The operator hold lives on the conductor's
host, not here, so the reason names only what the game reports; a bare pause
reads "paused".

Fails open: any error, timeout or odd shape means no stamp, never a failed
call. The failure is cached for the same window so a dead DFHack is not
re-polled on every call.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Mapping, Optional

STATUS_TOOL_ID = "clock.status"
DEFAULT_TTL_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 4.0
FIELD = "fort_paused"
MAX_LEN = 120


def stamp_text(status: Any) -> Optional[str]:
    """The stamp for one `clock.status` result, or None when not paused or unknown. Total."""
    try:
        if not isinstance(status, Mapping) or status.get("paused") is not True:
            return None
        tripwire = status.get("tripwire")
        panel = status.get("blocking_panel")
        if isinstance(tripwire, Mapping) and tripwire.get("reason"):
            why = f"paused, tripwire: {tripwire['reason']}"
        elif isinstance(panel, Mapping) and panel.get("name"):
            why = f"paused, panel open: {panel['name']}"
        else:
            why = "paused"
        return str(why)[:MAX_LEN]
    except Exception:  # noqa: BLE001 -- fail open
        return None


class PauseStamp:
    def __init__(
        self,
        read_status: Callable[[], Awaitable[Any]],
        *,
        ttl: float = DEFAULT_TTL_SECONDS,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._read_status = read_status
        self._ttl = ttl
        self._now = now
        self._value: Optional[str] = None
        self._at: Optional[float] = None
        self._lock: Optional[asyncio.Lock] = None

    async def current(self) -> Optional[str]:
        """The stamp text, or None. Never raises."""
        try:
            if self._fresh():
                return self._value
            if self._lock is None:
                self._lock = asyncio.Lock()
            async with self._lock:
                if self._fresh():
                    return self._value
                try:
                    status = await asyncio.wait_for(self._read_status(), READ_TIMEOUT_SECONDS)
                    self._value = stamp_text(status)
                except Exception:  # noqa: BLE001 -- includes timeout; fail open
                    self._value = None
                self._at = self._now()
                return self._value
        except Exception:  # noqa: BLE001
            return None

    def _fresh(self) -> bool:
        return self._at is not None and (self._now() - self._at) < self._ttl


def apply(result: Any, stamp: Optional[str]) -> Any:
    """Return `result` with the stamp added (a structured field and one short
    text block), or `result` unchanged when there is no stamp. Total."""
    if not stamp:
        return result
    try:
        from mcp import types

        structured = result.structured_content
        if structured is None:
            structured = {}
        elif not isinstance(structured, dict):
            structured = {"result": structured}
        structured = {**structured, FIELD: stamp}
        return types.CallToolResult(
            content=[*result.content, types.TextContent(type="text", text=f'{FIELD}: "{stamp}"')],
            structuredContent=structured,
            isError=result.is_error,
        )
    except Exception:  # noqa: BLE001 -- fail open
        return result
