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

PROMPT = "This is the Overseer. I need help diagnosing something the game is not telling me, in Dwarf Fortress 53.x with DFHack, one fortress, year 31.\n\nI built an office room for the fortress Manager. The Manager position requires an office of room value 1 (the game's own position requirement field, required_office, reads 1). What I built: a 3x3 Office zone, whose interior contains exactly one chair (a stone throne, constructed and complete, inside the zone's footprint), the room is carved into solid stone, all fifteen wall tiles of the surrounding ring are smoothed, the floor is unsmoothed natural stone floor, and there is one doorless entrance gap in the ring (so it is not fully enclosed). The zone is assigned to the Manager as its owner, confirmed from both the zone side and the unit side. The fortress is currently paused, and has been paused since the chair was completed; a few hundred ticks passed after the zone was placed and before the owner was set.\n\nMy check calls dfhack.buildings.getRoomDescription on the zone. It returns an empty string. On a room that is counted it returns a quality word. I can read no numeric room value anywhere: DFHack exposes nothing numeric for this on my install. The position check therefore reports the Manager's office requirement as not met.\n\nQuestions: (1) Why might getRoomDescription return empty for this room? List every candidate cause you know, ranked by likelihood, and say which are game mechanics and which are artifacts of how the description is computed or cached (for example whether it is recomputed continuously, on a schedule, or only when a dwarf or a menu looks at the room, and whether a paused game affects it). (2) What is the smallest thing I should try first, and what would tell me it worked? (3) What determines whether a room reaches the lowest quality tier, and is a single chair enough on its own, does a door or a table matter, does the floor or wall finish matter at this level? (4) Is anything about my setup wrong, such as the zone footprint versus the chair position, the owner assignment, or enclosure? Label every claim as verified, standard practice, or recall, and say plainly what you do not know."


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
        "envelope_final": (result.raw or {}).get("final") if isinstance(result.raw, dict) else None,
        "raw": result.raw,
    }, indent=2))


asyncio.run(main())
