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

from dfqueue import live  # noqa: E402

WEB = REPO_ROOT / "web" / "stream"
FIXTURE = WEB / "fixtures" / "board-demo.jsonl"


def _call(now: float, age_s: float, role: str, tool: str) -> dict:
    return {"ts": now - age_s, "role": role, "tool": tool, "is_error": False}


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
    for side, public in (("public", True), ("operator", False)):
        built = live.build_live(calls, now, public=public, conductor=conductor)
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
