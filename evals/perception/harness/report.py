"""Aggregate a results JSONL into a report.

    python -m evals.perception.harness.report evals/perception/results/run-*.jsonl

The headline number is accuracy on the *shared* question set — the questions
every representation in the file was able to express. Comparing representations
on their full sets would reward coords_v1 for merely being asked more.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def load(paths: list[Path]) -> list[dict]:
    rows = []
    for p in paths:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _pct(n: int, d: int) -> str:
    return "   -  " if not d else f"{100 * n / d:5.1f}%"


def _bar(n: int, d: int, width: int = 20) -> str:
    if not d:
        return " " * width
    filled = round(width * n / d)
    return "#" * filled + "." * (width - filled)


def summarise(rows: list[dict]) -> dict:
    agg: dict = defaultdict(
        lambda: {"n": 0, "correct": 0, "abstained": 0, "near": 0, "errors": 0,
                 "conf_right": [], "conf_wrong": []}
    )
    for r in rows:
        for key in ((r["representation"], "ALL"), (r["representation"], r["category"])):
            a = agg[key]
            a["n"] += 1
            if r.get("error"):
                a["errors"] += 1
                continue
            if r.get("correct"):
                a["correct"] += 1
                if r.get("confidence") is not None:
                    a["conf_right"].append(r["confidence"])
            else:
                if r.get("confidence") is not None:
                    a["conf_wrong"].append(r["confidence"])
                if r.get("abstained"):
                    a["abstained"] += 1
                if r.get("near_miss"):
                    a["near"] += 1
    return agg


def shared_categories(rows: list[dict]) -> set[str]:
    per_rep: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        per_rep[r["representation"]].add(r["category"])
    return set.intersection(*per_rep.values()) if per_rep else set()


def render(rows: list[dict]) -> str:
    if not rows:
        return "no rows"
    out: list[str] = []
    reps = sorted({r["representation"] for r in rows})
    shared = shared_categories(rows)

    out.append(f"{len(rows)} answers | models: {sorted({r['model'] for r in rows})}")
    out.append(f"fixtures: {sorted({r['fixture'] for r in rows})}")
    out.append("")

    out.append("HEADLINE - accuracy on the shared question set")
    out.append(f"  (categories every representation could express: {sorted(shared)})")
    out.append("")
    for rep in reps:
        sub = [r for r in rows if r["representation"] == rep and r["category"] in shared]
        correct = sum(1 for r in sub if r.get("correct"))
        out.append(f"  {rep:<12} {_bar(correct, len(sub))} {_pct(correct, len(sub))}  n={len(sub)}")
    out.append("")

    agg = summarise(rows)
    cats = sorted({r["category"] for r in rows})
    width = max(len(c) for c in cats) + 2

    out.append("BY CATEGORY - correct % (abstained / near-miss / error counts)")
    out.append("")
    header = " " * width + "".join(f"{rep:>26}" for rep in reps)
    out.append(header)
    for cat in cats:
        mark = " " if cat in shared else "*"
        line = f"{mark}{cat:<{width - 1}}"
        for rep in reps:
            a = agg.get((rep, cat))
            if not a or not a["n"]:
                line += f"{'-':>26}"
            else:
                cell = (
                    f"{_pct(a['correct'], a['n'])} "
                    f"({a['abstained']}/{a['near']}/{a['errors']})"
                )
                line += f"{cell:>26}"
        out.append(line)
    out.append("")
    out.append("  * = not in the shared set (some representation could not express it)")
    out.append("  parenthesised: abstentions / near-misses / API errors")
    out.append("")

    out.append("CALIBRATION - mean stated confidence")
    out.append("")
    for rep in reps:
        a = agg[(rep, "ALL")]
        right = statistics.fmean(a["conf_right"]) if a["conf_right"] else float("nan")
        wrong = statistics.fmean(a["conf_wrong"]) if a["conf_wrong"] else float("nan")
        gap = right - wrong
        out.append(
            f"  {rep:<12} when right {right:.2f} | when wrong {wrong:.2f} | "
            f"separation {gap:+.2f}"
        )
    out.append("")
    out.append("  Separation near zero means the model cannot tell when it is lost,")
    out.append("  so a zoom tool it decides to call on its own will not save it.")
    out.append("")

    cache = [r["cache_read_tokens"] for r in rows if r.get("cache_read_tokens") is not None]
    if cache:
        hits = sum(1 for c in cache if c > 0)
        out.append(
            f"CACHE  {hits}/{len(cache)} requests read cached tokens "
            f"({sum(cache):,} total). Zero would mean the briefing is not "
            f"serializing byte-identically."
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("paths", nargs="+", type=Path)
    args = p.parse_args(argv)
    print(render(load(args.paths)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
