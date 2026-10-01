"""Build the stream page's local `data/public/` and `data/operator/` files
from a queue export, for `web/stream/` (design
`research/2026-10-01-stream-page-design.md`, slice S0,
`handoffs/2026-10-01-stream-page-s0.md` task 3).

This is the offline stand-in for the real publisher (design section 8,
slice S1): a real publisher would read a live SQLite queue on VM 103 with
`dfqueue.feed.load_records_readonly` and push over SSH. This script instead
reads either a live-shaped SQLite file (same flag, same reader) or a
`records.jsonl` export (`evals/live/*/queue-export/records.jsonl`,
`dfqueue.store.export_jsonl`'s own output shape) and writes straight to a
local directory the page can `fetch()` from a static file server. No
network access, no VM.

**Multiple forts** (register 2026-10-02, "plan for more than one fort"):
every export names ONE fort (`--fort-id`, falling back to the `--db` file's
own stem, since that is already how this repo names a fort's queue file --
`dfqueue/Uniboslan.sqlite3` -- or to `uniboslan` for a `--records` export,
the one real fort this repo automates today, CLAUDE.md's own "Current
state"). Never hard-code a fort id in `web/stream/app.js` itself -- the page
reads `forts.json` and follows whichever fort is marked `current`.

Usage (see `web/stream/README.md` for the full walkthrough)::

    python scripts/export_stream_feed.py \\
        --records evals/live/2026-09-15-overseer-first-ruling/queue-export/records.jsonl \\
        --out-dir web/stream/data

    python scripts/export_stream_feed.py --db dfqueue/Uniboslan.sqlite3 --out-dir web/stream/data

Writes `<out-dir>/public/` and `<out-dir>/operator/`, each holding
`forts.json` (every fort this root has ever been given, this run's fort
marked `current`) and `forts/<fort-id>/`, the full per-fort `data/...`
layout `dfqueue.feed.write_feed` produces (design section 4.2).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dfqueue import feed, site_data  # noqa: E402  (path setup must run first)


def _load(records_path: str | None, db_path: str | None) -> list[dict]:
    if records_path and db_path:
        raise SystemExit("pass --records or --db, not both")
    if records_path:
        return feed.load_records_jsonl(records_path)
    if db_path:
        return feed.load_records_readonly(db_path)
    raise SystemExit("pass one of --records <path/to/records.jsonl> or --db <path/to/fort.sqlite3>")


def _default_fort_id(records_path: str | None, db_path: str | None) -> str:
    if db_path:
        return Path(db_path).stem
    return "uniboslan"  # the one real fort this repo automates (CLAUDE.md's own "Current state")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", help="a records.jsonl export (dfqueue.store.export_jsonl's shape)")
    parser.add_argument("--db", help="a live-shaped SQLite queue file, opened strictly read-only")
    parser.add_argument(
        "--out-dir", default=str(REPO_ROOT / "web" / "stream" / "data"),
        help="parent directory to write public/ and operator/ into (default: web/stream/data)",
    )
    parser.add_argument(
        "--fort-id", default=None,
        help="this export's fort id (default: the --db file's own stem, or 'uniboslan' for --records)",
    )
    parser.add_argument("--fort-name", default="Ragwind", help="this fort's display name (default: Ragwind)")
    parser.add_argument(
        "--fort-status", default="live", choices=["live", "lost"],
        help="this fort's status for forts.json (default: live)",
    )
    parser.add_argument(
        "--gotchas-db",
        help="a live gotcha-store SQLite file (read-only); omit for an honest empty gotchas.json",
    )
    args = parser.parse_args(argv)

    records = _load(args.records, args.db)
    out_dir = Path(args.out_dir)
    fort_id = args.fort_id or _default_fort_id(args.records, args.db)

    # Project-wide data (agents.json/tools.json/gotchas.json), the same
    # across every fort -- built once, written at the top of each
    # projection root (site_data.write_site_data's own docstring).
    agents_json = site_data.build_agents_json(records)
    tools_json = site_data.build_tools_json()
    gotchas_entries = (
        site_data.load_gotchas_readonly(args.gotchas_db) if args.gotchas_db else []
    )

    public_items = feed.build_items(records, public=True)
    public_projects = feed.build_projects_view(records, public=True)
    feed.write_fort_feed(
        public_items, out_dir / "public", fort_id=fort_id, fort_name=args.fort_name,
        fort_status=args.fort_status, projects=public_projects,
        status=feed.build_placeholder_status(),
    )
    site_data.write_site_data(
        out_dir / "public", agents_json=agents_json, tools_json=tools_json,
        gotchas_entries=gotchas_entries, public=True,
    )

    operator_items = feed.build_items(records, public=False)
    operator_projects = feed.build_projects_view(records, public=False)
    feed.write_fort_feed(
        operator_items, out_dir / "operator", fort_id=fort_id, fort_name=args.fort_name,
        fort_status=args.fort_status, projects=operator_projects,
        status=feed.build_placeholder_status(),
    )
    site_data.write_site_data(
        out_dir / "operator", agents_json=agents_json, tools_json=tools_json,
        gotchas_entries=gotchas_entries, public=False,
    )

    print(
        f"Wrote {len(public_items)} public item(s) and {len(operator_items)} "
        f"operator item(s) from {len(records)} record(s) to {out_dir} "
        f"(fort '{fort_id}')"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
