"""Local preview of the Board with a cycle "running" (no VM, no network).

Builds `web/stream/data/{public,operator}` from the committed board demo
fixture (`scripts/export_stream_feed.py`), then writes a `status.json` whose
`live` block is built by `dfqueue.live` from a made-up call journal: the
Architect awake for about four minutes, last tool `zone.list`, plus a prior
Overseer run for the idle line. Then serves `web/stream/` on localhost.

    python scripts/preview_stream_live.py            # serve on 8934
    python scripts/preview_stream_live.py --idle     # nobody awake: shows the last-run line
    python scripts/preview_stream_live.py --no-serve # just write the data

Open http://127.0.0.1:8934/index.html (public) and /operator.html (adds cost).
`web/stream/data/` is gitignored. The elapsed time counts up in the browser
from the file's own `elapsed_s`, so reload the script to restart a run.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dfqueue import live, runs as runs_store, site_data  # noqa: E402

WEB = REPO_ROOT / "web" / "stream"
FIXTURE = WEB / "fixtures" / "board-demo.jsonl"


def _call(now: float, age_s: float, role: str, tool: str) -> dict:
    return {"ts": now - age_s, "role": role, "tool": tool, "is_error": False}


DEMO_START = datetime(2025, 12, 31, 23, 55, tzinfo=timezone.utc)
DEMO_END = datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)
DEMO_SUMMARIES = {
    "architect": "Looked over the fort, found no workshop area and filed proposals for the first rooms.",
    "overseer": "Ruled on the open proposals and turned the accepted ones into jobs.",
    "quartermaster": "Checked stocks and asked for food and drink to be stored.",
}
DEMO_READS = {
    "architect": ["overview.get", "overview.get", "zone.list", "tree.find"],
    "overseer": ["queue.pending", "overview.get", "stocks.food-drink"],
    "quartermaster": ["stocks.food-drink", "stocks.food-drink", "overview.get"],
}


# EXAMPLE DATA for the local preview only (see main): what a "Thinking"
# expander might hold on the First bedroom cell project's two posts.
EXAMPLE_THINKING = {
    "proposal-0008": (
        "22 dwarves and not one bed or bedroom zone. Everyone is sleeping on the floor, which stacks "
        "unhappy thoughts every night, so housing is the gap to close after drink.\n\n"
        "Where? The obvious spot is beside the Farm Plot, close to food and the stair. But the farm level "
        "is soil, and gotcha-0001 says smoothing never finishes on soil, so a bedroom there could never be "
        "made nice. One level down is stone: the down-stair dug last week opens it.\n\n"
        "I considered proposing a whole row of cells at once. Too much for two miners, and if the template "
        "is wrong we'd have dug it wrong ten times. One cell first; the Overseer can extend it once a real "
        "dig shows the template works.\n\n"
        "blueprint.plan says bedroom-cell-v1 fits with all 10 tiles reachable. Proposing one cell, stone, "
        "one level below the farm."
    ),
    "ruling-0008": (
        "Checking the Architect's claims before ruling.\n\n"
        "Reachable: blueprint.preview agrees, 10 of 10. Stone, not soil: yes, matches gotcha-0001's "
        "warning about the farm level. Labour: 2 miners. Thin, but nothing else needs them right now; the "
        "brew job is at the Still and needs a brewer, not a miner.\n\n"
        "Beds: stocks show 0. So the plan needs a Make bed job too, and that needs a carpenter's workshop, "
        "which we don't have yet. I nearly rejected on that, but the dig is worth starting anyway: digging "
        "takes days, and the bed can follow once carpentry exists.\n\n"
        "Work in progress is 1 project, under the cap of 3. Accept. Plan: Dig shell, then Make bed, with "
        "the bed waiting on the dig."
    ),
}


def _demo_runs(now: float) -> tuple:
    """Run rows linked to the demo fixture's records by the real
    `records_in_window`, and a made-up call journal in the same window, so
    runs.json (summaries, wake reasons, "what it checked") is built by
    `live.build_runs` exactly as the publisher builds it."""
    records = [json.loads(line) for line in FIXTURE.read_text(encoding="utf8").splitlines() if line.strip()]
    base = DEMO_START.timestamp()
    rows, calls = [], []
    for n, role in enumerate(DEMO_SUMMARIES, start=1):
        linked = runs_store.records_in_window(records, role, DEMO_START.isoformat(), DEMO_END.isoformat())
        rows.append({
            "run_id": f"run-{n:04d}", "role": role, "wake_reason": "routine_review" if role != "overseer" else "ask_open",
            "wake_detail": "demo", "cycle": n, "started_at": DEMO_START.isoformat(), "ended_at": DEMO_END.isoformat(),
            "status": "ok", "ok": 1, "timed_out": 0, "duration_s": 372.4 + n * 40, "cost_usd": 0.05 * n,
            "error": None, "final_answer": DEMO_SUMMARIES[role], "records_json": json.dumps(linked),
        })
        for k, tool in enumerate(DEMO_READS[role]):
            calls.append({"ts": base + 10 + k, "role": role, "tool": tool, "is_error": role == "quartermaster" and k == 1})
    return rows, calls


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--idle", action="store_true", help="nobody awake")
    ap.add_argument("--no-serve", action="store_true")
    ap.add_argument("--port", type=int, default=8934)
    args = ap.parse_args(argv)

    out = WEB / "data"
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "export_stream_feed.py"),
         "--records", str(FIXTURE), "--out-dir", str(out)],
        check=True,
    )

    now = time.time()
    if args.idle:
        calls = [_call(now, 900, "overseer", "overview.get"), _call(now, 600, "overseer", "queue.rule")]
    else:
        calls = [_call(now, 250, "architect", "overview.get"), _call(now, 180, "architect", "tree.find"),
                 _call(now, 40, "architect", "zone.list"), _call(now, 10, "architect", "zone.list")]
    ended = datetime.fromtimestamp(now - 700, timezone.utc).isoformat(timespec="seconds")
    conductor = {
        "running": None if args.idle else {
            "role": "architect", "wake_reason": "ask_open",
            "started_at": datetime.fromtimestamp(now - 250, timezone.utc).isoformat(),
        },
        "last_runs": {"overseer": {"duration_s": 372.4, "cost_usd": 1.84, "wake_reason": "routine_review",
                                   "ok": True, "ended_at": ended}},
    }
    run_rows, run_calls = _demo_runs(now)
    tools_info = {t["id"]: t for t in site_data.build_tools_json()["tools"]}
    record_ts = {json.loads(l)["id"]: json.loads(l)["ts"] for l in FIXTURE.read_text(encoding="utf8").splitlines() if l.strip()}
    for side, public in (("public", True), ("operator", False)):
        built = live.build_live(calls, now, public=public, conductor=conductor, runs=run_rows)
        runs_doc = live.build_runs(run_rows, now, public=public, calls=run_calls, tools=tools_info, record_ts=record_ts)
        for fort_dir in (out / side / "forts").glob("*"):
            (fort_dir / "runs.json").write_text(json.dumps(runs_doc, indent=2), encoding="utf-8")
            print(f"wrote {fort_dir.relative_to(REPO_ROOT)}/runs.json")
        # EXAMPLE DATA, preview only: sample "Thinking" text on the First
        # bedroom cell project's posts, so the expander can be judged
        # (user's ask, 2026-10-05). The real publisher never sends this.
        for open_path in (out / side / "forts").glob("*/open.json"):
            feed = json.loads(open_path.read_text(encoding="utf-8"))
            for item in feed.get("items", []):
                if item.get("id") in EXAMPLE_THINKING:
                    item["thinking"] = EXAMPLE_THINKING[item["id"]]
            open_path.write_text(json.dumps(feed), encoding="utf-8")
        for status_path in (out / side / "forts").glob("*/status.json"):
            status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
            status["live"] = built
            status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
            print(f"wrote live block into {status_path.relative_to(REPO_ROOT)}")

    if args.no_serve:
        return 0
    print(f"http://127.0.0.1:{args.port}/index.html  and  /operator.html   (Ctrl-C to stop)")
    os.chdir(WEB)
    return subprocess.call([sys.executable, "-m", "http.server", str(args.port), "--bind", "127.0.0.1"])


if __name__ == "__main__":
    raise SystemExit(main())
