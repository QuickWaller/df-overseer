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

PROMPT = "This is the Overseer. I need help with a Dwarf Fortress 53.x (DFHack) fortress, year 31, 22 citizens, where manager work orders never dispatch, and I do not understand why. I would like every plausible cause ranked, the cheapest way to tell them apart, and any non-obvious idea.\n\nFacts I have verified by direct reads: there are four manager work orders, created through DFHack's API by our own tooling. Three (make blocks from stone, make mechanisms, brew drink; the brew order has 8 of 8 left) read validated = true, active = false, no item conditions, any workshop allowed. The fourth (make a throne) reads validated = false. I ran the fort for 2793 game ticks and none of them ever produced a job whose order_id links back to an order; the job list held only Sleep and Eat jobs, or nothing. Inputs and capacity are fine as far as I can read: 10 free boulders, 4 blocks, 1 mechanism, complete idle Mason's, Mechanic's and Still workshops, no forbidden stock, and at least one dwarf with each of the MASON, MECHANIC and BREWER labors enabled. A manager position is filled by one dwarf (unit 345). In the game's own screen he is assigned to a 3x3 Office zone in which a constructed stone throne stands; my DFHack read of that room's description returns an empty string, so I cannot confirm the game counts it, and the position's required office value is 1. The Manager did no job except eating in that time, and is in the highest stress category (a ghost haunts the fort, and there is only one pick). I never saw a ManageWorkOrders job (job type 195) in any census taken about every 100 ticks, so a short one could have been missed. The fort also paused itself twice, about 110 ticks after each resume, with no tripwire, announcement or popup that I could see.\n\nQuestions: (1) What actually makes a manager work order dispatch a job in this version: what must be true of the order, the manager, the office, the workshop, the stocks and the labors? Distinguish orders the game validated itself from orders created through the API with the validated flag set. (2) Rank every plausible cause for my four orders never dispatching. (3) What is the cheapest experiment to tell the top causes apart, and what would each result mean? (4) Could the self-pausing be related, and what common DF mechanisms pause a running fort with no visible announcement? (5) What is the one thing you would do first? Label every claim as verified, standard practice, or recall, and say plainly what you do not know."


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
