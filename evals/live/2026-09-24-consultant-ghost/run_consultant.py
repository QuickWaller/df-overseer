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

PROMPT = "This is the Overseer. I need advice on a situation I do not know how to handle, and I would like your best thinking, including ideas a veteran might not reach for first.\n\nSituation, Dwarf Fortress 53.x with DFHack, one fortress, year 31, 22 citizens alive and 1 dead. The dead citizen was a Gem Setter. A tripwire just fired on an announcement: that dwarf 'has risen and is haunting the fortress' (a ghost). Nobody has been hurt yet and hunger, thirst and stress vitals are unchanged. I do not know whether the body was ever buried, whether a coffin or memorial exists, or where the body is. The fort has very little manufacturing capacity right now: manager work orders are not dispatching, and there is exactly one pick, held by the only working miner. A thieving kea has been stealing items nearby. I cannot see the ghost's location or effects directly.\n\nQuestions: (1) What is a ghost likely to do to this fortress, and how urgent is it? (2) What are all the ways to lay it to rest or neutralise it, ranked by cost and reliability for a fort with my constraints? Include unconventional or cheap options. (3) What would you need to know about this fort before committing to any option, and how would I find out? (4) What is the single thing you would do first?\n\nLabel every claim as verified, standard practice, or recall, and say plainly what you do not know."


async def main() -> None:
    runner = DockerOpenClawRunner(
        pinned_config_dir=Path("/opt/openclaw/conductor/pinned-configs"),
        openclaw_state_dir=Path("/opt/openclaw/config"),
        workspace_root=Path("/opt/openclaw"),
        secrets_env_file=Path("/opt/openclaw/secrets/openclaw_secrets.env"),
    )
    charter = (REPO / "agents" / "consultant" / "role.md").read_text(encoding="utf-8")
    result = await runner.run(
        "consultant", PROMPT,
        model="deepseek/deepseek-v4-pro",
        timeout_seconds=1800.0,
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
        "raw": result.raw,
    }, indent=2))


asyncio.run(main())
