"""The cutover CLI (`docs/CONDUCTOR-EXECUTION.md` 6.4 and 6.6, deploy 2a).

    python -m conductor.cutover legacy --check     # lists what would close; changes nothing
    python -m conductor.cutover legacy --apply     # sets the cutover, closes every target
    python -m conductor.cutover rooms  --check
    python -m conductor.cutover rooms  --apply

Operator only. Everything is one MCP tool, `queue.cutover`, which holds the
logic (and is the same store call as `queue.close_legacy`): this module only
shows the result and chooses the exit code. The tool never calls DFHack and
touches no game state; a `close` record is the whole effect, so the Board
shows the conductor's closes.

`--check` is the default and never writes. `--apply` is refused here when the
check reports a blocker (the tool refuses too), and re-checks afterwards: an
apply that leaves anything open exits non-zero so a half-finished sweep is
noticed. A crash mid-apply is safe to rerun: the cutover is raise-only and the
sweep closes only what is still open.

Exit codes: 0 ok (check clean, or apply finished with nothing left); 1 blockers
or targets left; 2 usage or the call itself failed.

After `rooms --apply` the operator still flips `routed: true` in
`dfqueue/action_tools.yaml` in the same deploy (2A notes: `set_cutover`, then
`close_legacy` each target, then flip `routed`); this CLI never edits it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence

from conductor.mcp_client import MCPToolError, ToolCaller

GROUPS = ("legacy", "rooms")
_SHOWN = 40


def format_state(state: Mapping[str, Any]) -> List[str]:
    group = state.get("group")
    lines = [f"{group}: cutover {state.get('cutover_set') or 'not set'}"]
    for b in state.get("blockers") or ():
        lines.append(f"  BLOCKER: {b}")
    targets = list(state.get("targets") or ())
    lines.append(f"  {state.get('would_close', len(targets))} target(s) would close")
    for t in targets[:_SHOWN]:
        done = "executed" if t.get("executed") else "not executed"
        lines.append(f"    {t.get('kind')} {t.get('id')} ({done}): {t.get('summary') or ''}".rstrip())
    if len(targets) > _SHOWN:
        lines.append(f"    ... and {len(targets) - _SHOWN} more")
    return lines


async def run(group: str, apply: bool, caller: ToolCaller, out=print) -> int:
    """Check, then (with `apply`) apply and re-check. Returns the exit code."""
    try:
        state = await caller.call_tool("queue.cutover", {"group": group, "apply": False})
    except MCPToolError as exc:
        out(f"error: {exc}")
        return 2
    for line in format_state(state):
        out(line)
    blockers = list(state.get("blockers") or ())
    if not apply:
        out("check only: nothing was changed")
        return 1 if blockers else 0
    if blockers:
        out("not applied: fix the blocker(s) above first")
        return 1
    try:
        done = await caller.call_tool("queue.cutover", {"group": group, "apply": True})
    except MCPToolError as exc:
        out(f"error: apply failed, safe to rerun (the sweep resumes): {exc}")
        return 2
    closed = list(done.get("closed") or ())
    out(f"applied: cutover {done.get('cutover_id') or done.get('cutover_set')}, {len(closed)} closed")
    for c in closed[:_SHOWN]:
        out(f"    {c.get('id')} -> {c.get('close_id')} {c.get('outcome')}")
    try:
        after = await caller.call_tool("queue.cutover", {"group": group, "apply": False})
    except MCPToolError as exc:
        out(f"error: could not re-check afterwards: {exc}")
        return 2
    left = int(after.get("would_close") or 0)
    if left or not done.get("applied"):
        out(f"WARNING: {left} target(s) still open after apply; rerun --apply")
        return 1
    out("re-check: nothing left to close")
    if group == "rooms":
        out("next: flip `routed: true` for rooms in dfqueue/action_tools.yaml in the same deploy")
    return 0


def main(argv: Optional[Sequence[str]] = None, *, caller: Optional[ToolCaller] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m conductor.cutover",
        description="Operator-only: check or apply a cutover. Closes old work under the conductor's name; "
                    "touches no game state.",
    )
    parser.add_argument("group", choices=GROUPS)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="list what would close; change nothing (default)")
    mode.add_argument("--apply", action="store_true", help="set the cutover and close every target")
    parser.add_argument("--env-file", type=Path, default=None, help=".env merged under the real environment")
    args = parser.parse_args(argv)
    if caller is None:
        from conductor.config import ConfigError, load_config
        from conductor.mcp_client import StreamableHTTPMCPClient
        try:
            config = load_config(args.env_file)
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        caller = StreamableHTTPMCPClient(config.mcp_url, config.mcp_conductor_token)
    return asyncio.run(run(args.group, bool(args.apply), caller))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
