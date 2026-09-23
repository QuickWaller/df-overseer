"""One real Architect run: propose a working office for the Manager.

Uses the conductor's own DockerOpenClawRunner so the charter (SOUL.md)
handling matches every previous real run. Read-only role: it has no write
tools and the fort stays paused.
"""
import asyncio
import glob
import json
from pathlib import Path

from conductor.runner import DockerOpenClawRunner

REPO = Path(glob.glob("/opt/df-*/")[0])

PROMPT = (
    "Uniboslan, year 31. The fort is PAUSED and you are read-only: you propose, "
    "you never act.\n\n"
    "OBJECTIVE: the Manager must have a working office, so that manager work "
    "orders actually dispatch. At present they do not dispatch.\n\n"
    "YOUR TASK: work out where and how to achieve that on this fort, and write "
    "exactly one proposal describing it, including any digging or construction "
    "it needs and the order those steps must happen in.\n\n"
    "BEFORE YOU PROPOSE: read the doctrine available to you about rooms, and use "
    "your own read tools to inspect what this fort actually has right now. Do not "
    "assume what exists or what is already correct; check it. If something you "
    "need cannot be determined from the tools, say so in the proposal rather than "
    "guessing.\n\n"
    "RULES: exactly one call to your propose tool, with a complete record and a "
    "falsifiable prediction. Never emit a raw coordinate; refer to places by the "
    "landmark names the tools give you. "
    "POLICY: any room you propose must be fully enclosed by walls, and its finished surfaces should be at least smoothed."
)


async def main() -> None:
    runner = DockerOpenClawRunner(
        pinned_config_dir=Path("/opt/openclaw/conductor/pinned-configs"),
        openclaw_state_dir=Path("/opt/openclaw/config"),
        workspace_root=Path("/opt/openclaw"),
        secrets_env_file=Path("/opt/openclaw/secrets/openclaw_secrets.env"),
    )
    charter = (REPO / "agents" / "architect" / "role.md").read_text(encoding="utf-8")
    result = await runner.run(
        "architect", PROMPT,
        model="deepseek/deepseek-v4-pro",
        timeout_seconds=2700.0,
        charter=charter,
    )
    print(json.dumps({
        "ok": result.ok,
        "status": result.status,
        "timed_out": result.timed_out,
        "cost_usd": result.cost_usd,
        "wall_clock_seconds": round(result.wall_clock_seconds, 1),
        "tool_summary": result.tool_summary,
        "error": result.error,
        "final_answer": result.final_answer,
    }, indent=2)[:6000])


asyncio.run(main())
