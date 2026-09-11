"""Run the compliance eval: doctrine size x format x scenario -> JSONL.

Usage (from the repo root):

    python -m evals.compliance.harness.run --dry-run
    python -m evals.compliance.harness.run --out evals/compliance/results/run1.jsonl
    python -m evals.compliance.harness.run --rule-counts 10 40 160 --formats markdown
    python -m evals.compliance.harness.run --provider anthropic --out evals/compliance/results/opus1.jsonl

--dry-run needs no API key and no SDK: it builds every prompt, checks the
matrix is well formed, and prints a sample system/user prompt. Run it before
spending anything. Default matrix at the paper's own rule counts (10, 20, 40,
80, 120, 160) x 3 formats x 10 scenarios is 180 cells; start with --limit.

--provider deepseek (default, DEEPSEEK_API_KEY, `pip install openai` — DeepSeek
speaks the OpenAI-compatible chat-completions API) is the cheap default:
a full 180-cell sweep costs cents. --provider anthropic (ANTHROPIC_API_KEY,
`pip install anthropic`) is fully supported but NOT the default since
2026-09-11 — a single 180-cell Opus sweep with adaptive thinking cost
$9-13 in one session, almost entirely thinking-token output. Pass it
explicitly when a real Claude number is actually needed, not by habit.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .formats import FORMATS
from .providers import OPENAI_COMPATIBLE_PROVIDERS, call_anthropic, call_openai_compatible
from .rules import MAX_RULES, Rule, rule_set
from .scenarios import SCENARIOS, Scenario

DEFAULT_RULE_COUNTS = [10, 20, 40, 80, 120, 160]
DEFAULT_MODEL = {"anthropic": "claude-opus-5", "deepseek": "deepseek-chat"}

# Stable across every cell, so it is the block placed first for prefix caching.
# The "do not mention the doctrine" line matters: without it, a model under
# pressure from many rules tends to satisfy required/banned-word rules by
# quoting the rule text back at the user, which would measure compliance with
# a loophole rather than compliance with the actual constraint.
SYSTEM_PREAMBLE = """You are a helpful assistant answering a user's question directly and \
substantively.

In addition to answering well, you must comply with every doctrine rule listed \
below, for this response. The rules govern only the FORM of your response \
(wording, structure, punctuation) — never let them stop you from actually \
answering the user's question; find a way to satisfy every rule while still \
giving a real, substantive answer. Do not mention, quote, restate, or \
apologize for the doctrine rules in your response — just follow them \
silently."""


@dataclass
class Cell:
    doctrine_size: int
    format: str
    scenario: Scenario
    rules: list[Rule]
    repeat: int


def build_matrix(
    rule_counts: list[int],
    formats: list[str],
    scenarios: list[Scenario],
    repeats: int,
) -> list[Cell]:
    cells: list[Cell] = []
    for n in rule_counts:
        rules = rule_set(n)
        for fmt in formats:
            for sc in scenarios:
                for r in range(repeats):
                    cells.append(Cell(n, fmt, sc, rules, r))
    return cells


def build_system(cell: Cell) -> str:
    rendered = FORMATS[cell.format](cell.rules)
    return (
        f"DOCTRINE ({len(cell.rules)} rules, {cell.format} format) — "
        f"follow every one of these, for this response:\n\n{rendered}"
    )


def ask(client, provider: str, model: str, effort: str, cell: Cell, max_tokens: int) -> dict:
    t0 = time.time()
    row = {
        "doctrine_size": cell.doctrine_size,
        "format": cell.format,
        "scenario": cell.scenario.id,
        "repeat": cell.repeat,
        "provider": provider,
        "model": model,
        "effort": effort,
    }
    try:
        if provider == "anthropic":
            result = call_anthropic(
                client, model, effort, SYSTEM_PREAMBLE, build_system(cell),
                cell.scenario.prompt, max_tokens,
            )
        else:
            result = call_openai_compatible(
                client, model, SYSTEM_PREAMBLE, build_system(cell),
                cell.scenario.prompt, max_tokens,
            )
    except Exception as exc:  # noqa: BLE001 - every failure mode becomes a row
        row.update(error=f"{type(exc).__name__}: {exc}", pass_count=0, total=len(cell.rules),
                    perfect=False, seconds=time.time() - t0)
        return row

    if result.error:
        row.update(error=result.error, pass_count=0, total=len(cell.rules),
                    perfect=False, seconds=time.time() - t0)
        return row

    text = result.text
    if not text.strip():
        # A real failure mode, not a fluke: at high doctrine sizes, adaptive
        # thinking can consume the whole max_tokens budget before any text
        # block is emitted (confirmed live, 2026-09-11 — a 160-rule doctrine
        # spent 3469 of a 4000-token budget on thinking alone). Token counts
        # are captured here specifically so this is diagnosable from the row
        # rather than just labelled "empty" — a low max_tokens headroom is
        # visible in the data, not just inferred after the fact.
        row.update(
            error="empty response text", pass_count=0, total=len(cell.rules), perfect=False,
            seconds=time.time() - t0, input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        )
        return row

    failed = [r.id for r in cell.rules if not r.check(text)]
    total = len(cell.rules)
    passed = total - len(failed)
    row.update(
        pass_count=passed,
        total=total,
        perfect=(passed == total),
        failed_rule_ids=failed,
        response_words=len(text.split()),
        seconds=round(time.time() - t0, 2),
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        cache_read_tokens=result.usage.cache_read_tokens,
    )
    return row


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rule-counts", nargs="*", type=int, default=DEFAULT_RULE_COUNTS)
    p.add_argument("--formats", nargs="*", default=sorted(FORMATS))
    p.add_argument("--scenarios", nargs="*", help=f"default: all of {[s.id for s in SCENARIOS]}")
    p.add_argument("--repeats", type=int, default=1, help="samples per cell")
    # Default flipped from "anthropic" to "deepseek" 2026-09-11: a 180-cell
    # Opus sweep with adaptive thinking cost ~$9-13 in one session (mostly
    # thinking-token output), against DeepSeek's full sweep costing cents.
    # Anthropic is still fully supported — pass --provider anthropic
    # explicitly when a real Claude number is actually needed — but nothing
    # should reach for the expensive default by accident.
    p.add_argument("--provider", default="deepseek", choices=["anthropic", *OPENAI_COMPATIBLE_PROVIDERS])
    p.add_argument("--model", help=f"default: {DEFAULT_MODEL} per --provider")
    p.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"],
                    help="Anthropic only; ignored for other providers")
    # 4000 was the original default and is too tight for Anthropic's adaptive
    # thinking at high doctrine sizes: confirmed live 2026-09-11, a 160-rule
    # doctrine spent 3469 of 4000 tokens on thinking alone, and 77% of that
    # run's n=160 cells returned an empty text block (budget exhausted before
    # any answer was emitted) rather than a genuine compliance failure.
    # 16000 matches evals/perception/'s own default for the same reason.
    p.add_argument("--max-tokens", type=int, default=16000)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--limit", type=int, help="stop after N cells (smoke tests)")
    p.add_argument("--out", type=Path, help="JSONL results path")
    p.add_argument("--dry-run", action="store_true", help="build prompts, call nothing")
    args = p.parse_args(argv)
    if not args.model:
        args.model = DEFAULT_MODEL[args.provider]

    for n in args.rule_counts:
        if n > MAX_RULES:
            print(f"--rule-counts: {n} exceeds the pool size ({MAX_RULES})", file=sys.stderr)
            return 2
    for fmt in args.formats:
        if fmt not in FORMATS:
            print(f"unknown format {fmt!r}", file=sys.stderr)
            return 2

    scenarios = SCENARIOS
    if args.scenarios:
        wanted = set(args.scenarios)
        scenarios = [s for s in SCENARIOS if s.id in wanted]
        if not scenarios:
            print("no scenarios matched", file=sys.stderr)
            return 2

    cells = build_matrix(args.rule_counts, args.formats, scenarios, args.repeats)
    if args.limit:
        cells = cells[: args.limit]

    print(f"rule counts:  {args.rule_counts}")
    print(f"formats:      {args.formats}")
    print(f"scenarios:    {[s.id for s in scenarios]}")
    print(f"cells:        {len(cells)}")

    if args.dry_run:
        if cells:
            c = cells[0]
            print("\n--- sample system prompt (block 1, stable) ---")
            print(SYSTEM_PREAMBLE)
            print("\n--- sample system prompt (block 2, doctrine) ---")
            print(build_system(c))
            print("\n--- sample user prompt ---")
            print(f"[{c.format} / n={c.doctrine_size} / {c.scenario.id}] {c.scenario.prompt}")
        return 0

    if args.provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            print("pip install 'anthropic>=1.0' (see evals/compliance/requirements.txt)", file=sys.stderr)
            return 2
        client = anthropic.Anthropic()
    else:
        try:
            import openai
        except ImportError:
            print("pip install openai (DeepSeek speaks the OpenAI-compatible chat-completions API)",
                  file=sys.stderr)
            return 2
        env_var, base_url = OPENAI_COMPATIBLE_PROVIDERS[args.provider]
        import os
        api_key = os.environ.get(env_var)
        if not api_key:
            print(f"{env_var} is not set", file=sys.stderr)
            return 2
        client = openai.OpenAI(api_key=api_key, base_url=base_url)

    out_path = args.out or Path("evals/compliance/results") / f"run-{int(time.time())}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    done = 0
    with out_path.open("w", encoding="utf-8") as fh:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            for row in pool.map(
                lambda c: ask(client, args.provider, args.model, args.effort, c, args.max_tokens), cells
            ):
                fh.write(json.dumps(row, sort_keys=True) + "\n")
                fh.flush()
                done += 1
                if done % 10 == 0 or done == len(cells):
                    print(f"  {done}/{len(cells)}", file=sys.stderr)

    print(f"\nwrote {done} rows to {out_path}")
    print(f"report with: python -m evals.compliance.harness.report {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
