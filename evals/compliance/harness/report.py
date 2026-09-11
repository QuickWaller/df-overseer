"""Aggregate a results JSONL into a report.

    python -m evals.compliance.harness.report evals/compliance/results/run1.jsonl

The headline is the same shape as "Prompt Design at Scale"'s own: perfect-
response rate against doctrine size. Per-rule pass rate is reported alongside
it because perfect-rate can hit zero well before compliance is actually
uninformative — a model failing 1 of 80 rules and a model failing 40 of 80
both score "0% perfect," and only the per-rule rate tells them apart.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from .rules import BY_ID, rule_set


def load(paths: list[Path]) -> list[dict]:
    rows = []
    for p in paths:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _pct(n: float, d: float) -> str:
    return "   -  " if not d else f"{100 * n / d:5.1f}%"


def _bar(n: float, d: float, width: int = 20) -> str:
    if not d:
        return " " * width
    filled = round(width * n / d)
    return "#" * filled + "." * (width - filled)


def category_breakdown(rows: list[dict]) -> dict[int, dict[str, tuple[int, int]]]:
    """(passed, total) per (doctrine_size, category), reconstructed from
    failed_rule_ids + doctrine_size alone — the exact rule_set for a given
    doctrine_size is deterministic, so it never needs to be stored per row."""
    out: dict[int, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        if r.get("error"):
            continue
        n = r["doctrine_size"]
        failed = set(r.get("failed_rule_ids", []))
        for rule in rule_set(n):
            slot = out[n][rule.category]
            slot[1] += 1
            if rule.id not in failed:
                slot[0] += 1
    return {n: {c: tuple(v) for c, v in cats.items()} for n, cats in out.items()}


def render(rows: list[dict]) -> str:
    """Split by model when a file mixes providers — a Claude-vs-DeepSeek
    comparison needs its own headline curve per model, not one pooled average
    that would just describe whichever model has more rows in the file."""
    if not rows:
        return "no rows"
    models = sorted({r["model"] for r in rows})
    if len(models) == 1:
        return _render_one(rows)
    sections = []
    for m in models:
        sections.append(f"===== {m} =====\n\n{_render_one([r for r in rows if r['model'] == m])}")
    return "\n\n".join(sections)


def _render_one(rows: list[dict]) -> str:
    out: list[str] = []
    sizes = sorted({r["doctrine_size"] for r in rows})
    formats = sorted({r["format"] for r in rows})

    n_errors = sum(1 for r in rows if r.get("error"))
    out.append(f"{len(rows)} responses | models: {sorted({r['model'] for r in rows})}")
    if n_errors:
        out.append(f"  ({n_errors} API errors, excluded from the rates below)")
    out.append("")

    ok = [r for r in rows if not r.get("error")]

    out.append("HEADLINE — perfect-response rate by doctrine size")
    out.append("")
    for n in sizes:
        sub = [r for r in ok if r["doctrine_size"] == n]
        perfect = sum(1 for r in sub if r.get("perfect"))
        out.append(f"  n={n:<4} {_bar(perfect, len(sub))} {_pct(perfect, len(sub))}  n_runs={len(sub)}")
    out.append("")

    out.append("PER-RULE PASS RATE by doctrine size (mean fraction of active rules obeyed)")
    out.append("")
    for n in sizes:
        sub = [r for r in ok if r["doctrine_size"] == n]
        if not sub:
            continue
        rate = sum(r["pass_count"] / r["total"] for r in sub if r.get("total")) / len(sub)
        out.append(f"  n={n:<4} {_bar(rate, 1.0)} {rate * 100:5.1f}%")
    out.append("")

    out.append("BY FORMAT — perfect-response rate (does surface form change the collapse point?)")
    out.append("")
    header = " " * 8 + "".join(f"{fmt:>14}" for fmt in formats)
    out.append(header)
    for n in sizes:
        line = f"n={n:<6}"
        for fmt in formats:
            sub = [r for r in ok if r["doctrine_size"] == n and r["format"] == fmt]
            perfect = sum(1 for r in sub if r.get("perfect"))
            line += f"{_pct(perfect, len(sub)):>14}"
        out.append(line)
    out.append("")

    out.append("BY CATEGORY — pass rate at the largest doctrine size in this file")
    out.append("(which rule types degrade first, not just that degradation happens)")
    out.append("")
    breakdown = category_breakdown(ok)
    largest = max(breakdown) if breakdown else None
    if largest is not None:
        cats = sorted(breakdown[largest].items(), key=lambda kv: kv[1][0] / kv[1][1] if kv[1][1] else 1)
        for cat, (passed, total) in cats:
            out.append(f"  {cat:<22} {_bar(passed, total)} {_pct(passed, total)}  ({passed}/{total})")
    out.append("")

    cache = [r["cache_read_tokens"] for r in ok if r.get("cache_read_tokens") is not None]
    if cache:
        hits = sum(1 for c in cache if c > 0)
        out.append(
            f"CACHE  {hits}/{len(cache)} requests read cached tokens "
            f"({sum(cache):,} total)."
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
