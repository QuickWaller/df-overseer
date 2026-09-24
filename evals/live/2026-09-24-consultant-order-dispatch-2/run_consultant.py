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

PROMPT = "This is the Overseer. I need a COMPACT answer, under 700 words, and please use at most 8 tool calls: prefer knowledge.wiki_lookup and one or two DFHack source reads, and give me your ranked answer as soon as you have one rather than researching exhaustively.\n\nI have a Dwarf Fortress 53.x (DFHack) fortress, year 31, 22 citizens, where manager work orders never dispatch. Verified by direct reads: four manager work orders, created through DFHack's API by our own tooling. Three (make blocks from stone, make mechanisms, brew drink) read validated = true, active = false, no item conditions, any workshop allowed. The fourth (make a throne) reads validated = false. Over 2793 game ticks none produced a job whose order_id links back to an order; the job list held only Sleep and Eat jobs, or nothing. Inputs and capacity read fine: 10 free boulders, 4 blocks, 1 mechanism, complete idle Mason's, Mechanic's and Still workshops, no forbidden stock, and dwarves with the MASON, MECHANIC and BREWER labors enabled. One dwarf (unit 345) holds the manager position; in the game's own screen he is assigned to a 3x3 Office zone with a constructed stone throne in it, but my DFHack read of that room's description is an empty string, so I cannot confirm the game counts it; the position's required office value is 1. He did no job except eating during the run, and is in the highest stress category (a ghost haunts the fort; only one pick exists). I never saw a ManageWorkOrders job (type 195) in censuses taken about every 100 ticks. The fort also paused itself twice, about 110 ticks after each resume, with no visible announcement.\n\nAnswer, in this order: (1) What must be true for a manager order to dispatch a job in this version, and do orders the game validated itself differ from ones created through the API with the validated flag set? (2) The top three causes for my four orders, ranked. (3) The cheapest experiment separating them and what each result means. (4) Any plausible link to the self-pausing. (5) The single first step. Label each claim verified, standard practice or recall, and say what you do not know."


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
