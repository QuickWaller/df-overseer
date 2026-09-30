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

Usage (see `web/stream/README.md` for the full walkthrough)::

    python scripts/export_stream_feed.py \\
        --records evals/live/2026-09-15-overseer-first-ruling/queue-export/records.jsonl \\
        --out-dir web/stream/data

    python scripts/export_stream_feed.py --db dfqueue/Uniboslan.sqlite3 --out-dir web/stream/data

Writes `<out-dir>/public/` and `<out-dir>/operator/`, each the full
`data/...` layout `dfqueue.feed.write_feed` produces (design section 4.2).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dfqueue import feed  # noqa: E402  (path setup must run first)


def _load(records_path: str | None, db_path: str | None) -> list[dict]:
    if records_path and db_path:
        raise SystemExit("pass --records or --db, not both")
    if records_path:
        return feed.load_records_jsonl(records_path)
    if db_path:
        return feed.load_records_readonly(db_path)
    raise SystemExit("pass one of --records <path/to/records.jsonl> or --db <path/to/fort.sqlite3>")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", help="a records.jsonl export (dfqueue.store.export_jsonl's shape)")
    parser.add_argument("--db", help="a live-shaped SQLite queue file, opened strictly read-only")
    parser.add_argument(
        "--out-dir", default=str(REPO_ROOT / "web" / "stream" / "data"),
        help="parent directory to write public/ and operator/ into (default: web/stream/data)",
    )
    args = parser.parse_args(argv)

    records = _load(args.records, args.db)
    out_dir = Path(args.out_dir)

    public_items = feed.build_items(records, public=True)
    public_projects = feed.build_projects_view(records, public=True)
    feed.write_feed(
        public_items, out_dir / "public", projects=public_projects,
        status=feed.build_placeholder_status(),
    )

    operator_items = feed.build_items(records, public=False)
    operator_projects = feed.build_projects_view(records, public=False)
    feed.write_feed(
        operator_items, out_dir / "operator", projects=operator_projects,
        status=feed.build_placeholder_status(),
    )

    print(
        f"Wrote {len(public_items)} public item(s) and {len(operator_items)} "
        f"operator item(s) from {len(records)} record(s) to {out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
