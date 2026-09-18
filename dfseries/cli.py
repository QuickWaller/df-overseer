"""A small CLI for a human to run against a dfseries database: import
sampler output and read back a trend report. Standard library only
(`argparse`), same rule as the rest of this package.

Usage:

    python -m dfseries.cli import <db-path> <jsonl-file> [<jsonl-file> ...]
    python -m dfseries.cli timelines <db-path>
    python -m dfseries.cli series <db-path> <subject> <metric> [--all] [--start N] [--end N]
    python -m dfseries.cli latest <db-path> <subject> <metric> [--all]
    python -m dfseries.cli rate <db-path> <subject> <metric> [--all] [--start N] [--end N]
    python -m dfseries.cli resets <db-path> <subject> <metric> [--all] [--start N] [--end N]
    python -m dfseries.cli dwarf-day <db-path> <metric> [--all] [--start N] [--end N]
"""

from __future__ import annotations

import argparse
import sys

from . import aggregate, importer, store, timeline, trend


def _lineage(args: argparse.Namespace) -> str:
    return "all" if getattr(args, "all", False) else "current"


def cmd_import(args: argparse.Namespace) -> int:
    with store.connect(args.db) as conn:
        results = importer.import_files(conn, args.files)
    ok = True
    for r in results:
        print(f"{r.path}: {r.events_imported} event(s), {r.metrics_imported} metric(s) imported")
        if r.duplicate_lines:
            print(f"  {len(r.duplicate_lines)} line(s) already imported (skipped)")
        if r.torn_line:
            print(f"  torn final line at {r.torn_line}: will be retried on next import")
        for line_no, reason in r.corrupt_lines:
            print(f"  corrupt line {line_no}: {reason}")
            ok = False
        for line_no, reason in r.refused_lines:
            print(f"  refused line {line_no}: {reason}")
            ok = False
    return 0 if ok else 1


def cmd_timelines(args: argparse.Namespace) -> int:
    with store.connect(args.db) as conn:
        rows = timeline.lineage_summary(conn)
    if not rows:
        print("no timelines imported yet")
        return 0
    for r in rows:
        tip = " (current tip)" if r["is_current_tip"] else f" (superseded from abs_tick {r['cutoff_abs_tick']})"
        print(f"{r['timeline_id']}: starts at {r['start_abs_tick']}, first seen {r['first_wall_utc']}{tip}")
    return 0


def cmd_series(args: argparse.Namespace) -> int:
    with store.connect(args.db) as conn:
        rows = trend.series(
            conn, args.subject, args.metric,
            start_abs_tick=args.start, end_abs_tick=args.end, lineage=_lineage(args),
        )
    if not rows:
        print("no data")
        return 0
    for r in rows:
        flag = " [superseded]" if r["superseded"] else ""
        value = "null" if r["value"] is None else r["value"]
        err = f" ({r['error']})" if r["error"] else ""
        print(f"{r['abs_tick']}: {value} {r['unit'] or ''}{err}{flag}")
    return 0


def cmd_latest(args: argparse.Namespace) -> int:
    with store.connect(args.db) as conn:
        row = trend.latest(conn, args.subject, args.metric, lineage=_lineage(args))
    if row is None:
        print("no data")
        return 0
    value = "null" if row["value"] is None else row["value"]
    print(f"{row['abs_tick']}: {value} {row['unit'] or ''}")
    return 0


def cmd_rate(args: argparse.Namespace) -> int:
    with store.connect(args.db) as conn:
        result = trend.rate(
            conn, args.subject, args.metric,
            start_abs_tick=args.start, end_abs_tick=args.end, lineage=_lineage(args),
        )
    if result.status != trend.MEASURED:
        print(f"unavailable: {result.reason}")
        return 0
    segment_note = f" [{result.segment}]" if result.segment else ""
    print(
        f"{result.value:+.6f} per tick{segment_note}, over {result.tick_span} ticks, "
        f"{result.sample_count} sample(s) used, {result.skipped_nulls} null reading(s) skipped "
        f"(metric_kind={result.metric_kind})"
    )
    if result.reason:
        print(f"  note: {result.reason}")
    return 0


def cmd_resets(args: argparse.Namespace) -> int:
    with store.connect(args.db) as conn:
        result = trend.resets(
            conn, args.subject, args.metric,
            start_abs_tick=args.start, end_abs_tick=args.end, lineage=_lineage(args),
        )
    print(f"metric_kind={result.metric_kind} rate_per_tick={result.rate_per_tick} evidence={result.rate_evidence}")
    if not result.events and not result.anomalies:
        print("no reset events or anomalies in this window")
        return 0
    for e in result.events:
        if e.kind == trend.EXACT_TICK:
            print(f"  reset at abs_tick {e.abs_tick} (between {e.window_start_abs_tick} and {e.window_end_abs_tick}: {e.from_value} -> {e.to_value})")
        else:
            print(f"  reset somewhere in ({e.window_start_abs_tick}, {e.window_end_abs_tick}] (interval-bounded: {e.from_value} -> {e.to_value})")
    for a in result.anomalies:
        print(f"  ANOMALY between {a.window_start_abs_tick} and {a.window_end_abs_tick}: {a.from_value} -> {a.to_value} ({a.reason})")
    return 0


def cmd_dwarf_day(args: argparse.Namespace) -> int:
    with store.connect(args.db) as conn:
        result = aggregate.dwarf_day_reset_rate(
            conn, args.metric,
            start_abs_tick=args.start, end_abs_tick=args.end, lineage=_lineage(args),
        )
    print(
        f"{result.label}: "
        f"{'n/a (0 dwarf-days observed)' if result.events_per_dwarf_day is None else f'{result.events_per_dwarf_day:.6f}'}"
    )
    print(
        f"  {result.event_count} event(s) ({result.exact_tick_events} exact-tick, "
        f"{result.interval_bounded_events} interval-bounded), {result.anomaly_count} anomaly(ies), "
        f"{result.subjects_observed} subject(s) observed, {result.dwarf_days_observed:.4f} dwarf-day(s)"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dfseries", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="import one or more contract-format JSONL files")
    p_import.add_argument("db")
    p_import.add_argument("files", nargs="+")
    p_import.set_defaults(func=cmd_import)

    p_timelines = sub.add_parser("timelines", help="list known timelines and lineage cutoffs")
    p_timelines.add_argument("db")
    p_timelines.set_defaults(func=cmd_timelines)

    p_series = sub.add_parser("series", help="print a subject's readings of one metric")
    p_series.add_argument("db")
    p_series.add_argument("subject")
    p_series.add_argument("metric")
    p_series.add_argument("--start", type=int, default=None, dest="start")
    p_series.add_argument("--end", type=int, default=None, dest="end")
    p_series.add_argument("--all", action="store_true", help="include superseded samples")
    p_series.set_defaults(func=cmd_series)

    p_latest = sub.add_parser("latest", help="print the latest reading of one metric")
    p_latest.add_argument("db")
    p_latest.add_argument("subject")
    p_latest.add_argument("metric")
    p_latest.add_argument("--all", action="store_true", help="include superseded samples")
    p_latest.set_defaults(func=cmd_latest)

    p_rate = sub.add_parser("rate", help="print a rate over a tick window")
    p_rate.add_argument("db")
    p_rate.add_argument("subject")
    p_rate.add_argument("metric")
    p_rate.add_argument("--start", type=int, default=None, dest="start")
    p_rate.add_argument("--end", type=int, default=None, dest="end")
    p_rate.add_argument("--all", action="store_true", help="include superseded samples")
    p_rate.set_defaults(func=cmd_rate)

    p_resets = sub.add_parser("resets", help="print reset events and anomalies for a subject's metric")
    p_resets.add_argument("db")
    p_resets.add_argument("subject")
    p_resets.add_argument("metric")
    p_resets.add_argument("--start", type=int, default=None, dest="start")
    p_resets.add_argument("--end", type=int, default=None, dest="end")
    p_resets.add_argument("--all", action="store_true", help="include superseded samples")
    p_resets.set_defaults(func=cmd_resets)

    p_dwarf_day = sub.add_parser("dwarf-day", help="print fort-level reset events per dwarf-day for a metric")
    p_dwarf_day.add_argument("db")
    p_dwarf_day.add_argument("metric")
    p_dwarf_day.add_argument("--start", type=int, default=None, dest="start")
    p_dwarf_day.add_argument("--end", type=int, default=None, dest="end")
    p_dwarf_day.add_argument("--all", action="store_true", help="include superseded samples")
    p_dwarf_day.set_defaults(func=cmd_dwarf_day)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
