"""The autofarm sync: the Planner's crop levels, applied to the game by the conductor.

Register 2026-10-09 ("switch farming to autofarm"), `research/2026-10-09-autofarm-switch.md`.
The Planner owns crop stock levels as plan targets with `sync: autofarm` and a `crop`
(a plant raw token, or `default` for autofarm's default level). Each cycle, in a phase an
operator hold blocks, the conductor reads `plan.status` (the server has already computed
every `want_units` at the current alive count with `dfqueue.plan.want_units`; the
conductor does no arithmetic of its own beyond rounding) and writes the numbers through
the conductor-only `autofarm.set` tool, which also enables the plugin.

- Nothing is written until at least one crop target (other than `default`) exists, so
  autofarm's own default of 50 never runs unreviewed.
- The default level is the `crop: default` target's number; with none, 0 (never plant a
  crop that has no level of its own).
- An inert (flagged) target, one whose number could not be computed (no alive count), or a
  duplicate crop is skipped, with a note; the first target for a crop wins.
- The write is idempotent and is repeated every cycle: that also heals a save reload that
  dropped the plugin's state.
- Total: any failure logs and returns a report, and never stops the cycle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

LOG = logging.getLogger(__name__)

STATUS_TOOL = "plan.status"
SET_TOOL = "autofarm.set"
SYNC_KIND = "autofarm"
DEFAULT_CROP = "default"


@dataclass
class SyncReport:
    ran: bool = False
    skipped: Optional[str] = None
    default: Optional[int] = None
    levels: Dict[str, int] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ran": self.ran, "skipped": self.skipped, "default": self.default,
            "levels": dict(self.levels), "notes": list(self.notes), "error": self.error,
        }


def _level(row: Mapping[str, Any]) -> Optional[int]:
    v = row.get("want_units")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v < 0:
        return None
    return int(round(v))


def levels_from_status(status: Any) -> SyncReport:
    """Pure: the default and per-crop levels the plan's synced targets ask for."""
    rep = SyncReport()
    rows = status.get("targets") if isinstance(status, Mapping) else None
    default: Optional[int] = None
    for row in rows or []:
        if not isinstance(row, Mapping) or row.get("sync") != SYNC_KIND:
            continue
        tid, crop = row.get("id"), row.get("crop")
        if row.get("state") != "synced" or not isinstance(crop, str):
            rep.notes.append(f"{tid}: not applied (state {row.get('state')!r})")
            continue
        level = _level(row)
        if level is None:
            rep.notes.append(f"{tid}: not applied (no usable number this cycle)")
            continue
        if crop == DEFAULT_CROP:
            if default is None:
                default = level
            else:
                rep.notes.append(f"{tid}: a second default target is ignored")
        elif crop in rep.levels:
            rep.notes.append(f"{tid}: {crop} already has a level; this target is ignored")
        else:
            rep.levels[crop] = level
    rep.default = 0 if default is None else default
    return rep


def levels_argument(levels: Mapping[str, int]) -> str:
    return ",".join(f"{crop}={n}" for crop, n in levels.items())


async def run_autofarm_sync(call: Any, enabled: bool, *, held: bool, dry_run: bool = False) -> SyncReport:
    """Read the plan, and apply its synced crop levels. `call(tool, args)` is the
    conductor's tool caller. Never raises."""
    if not enabled:
        return SyncReport(skipped="policy autofarm_sync.enabled is false")
    if held:
        return SyncReport(skipped="operator hold")
    try:
        status = await call(STATUS_TOOL, {})
    except Exception as exc:  # noqa: BLE001 -- total, see module docstring
        LOG.warning("autofarm sync: %s failed; nothing written: %s", STATUS_TOOL, exc)
        return SyncReport(skipped=f"{STATUS_TOOL} failed", error=str(exc))
    rep = levels_from_status(status)
    if not rep.levels:
        rep.skipped = "no crop targets with a usable level"
        return rep
    if dry_run:
        rep.skipped = "dry run"
        return rep
    args = {"default": str(rep.default), "levels": levels_argument(rep.levels)}
    try:
        await call(SET_TOOL, args)
        rep.ran = True
    except Exception as exc:  # noqa: BLE001
        LOG.error("autofarm sync: %s refused: %s", SET_TOOL, exc)
        rep.error = str(exc)
    return rep
