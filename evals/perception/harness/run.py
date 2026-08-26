"""Run the perception eval: fixtures x representations x questions -> JSONL.

Usage (from the repo root):

    python -m evals.perception.harness.run --dry-run
    python -m evals.perception.harness.run --out results/run1.jsonl
    python -m evals.perception.harness.run --representations exits_v1 coords_v1 \
        --categories bearing route reachability --per-category 5

--dry-run needs no API key and no SDK: it builds every prompt, checks that the
question set is well formed, and prints the matrix and a sample prompt. Run it
before spending anything.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .fixture import Fixture, load_all
from .grade import grade, response_schema
from .questions import UNKNOWN, GENERATORS, Question, build
from .representations import REPRESENTATIONS

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"

# The briefing is the whole of the model's world here. Saying so explicitly is
# not padding: without it, a model will happily answer from what it knows about
# Dwarf Fortress in general, and the eval would be measuring priors, not
# perception. The abstention channel exists so "the briefing does not say" is a
# first-class answer rather than a guess.
RULES = f"""You are the overseer of a Dwarf Fortress fortress. You are given a \
structured briefing describing the fortress. You never see the game screen; the \
briefing is the only thing you know about this fortress.

Answer questions about the fortress using the briefing alone. Do not draw on \
general knowledge about Dwarf Fortress, and do not assume anything the briefing \
does not state.

If the briefing does not contain enough information to answer, say so: return \
the single string "{UNKNOWN}" as your answer (or a list containing only \
"{UNKNOWN}" where a list is required). Guessing is worse than abstaining.

Return your answer in the required JSON shape. Set "confidence" to your honest \
probability, between 0 and 1, that your answer is correct."""


@dataclass
class Cell:
    fixture: Fixture
    representation: str
    briefing: str
    question: Question
    repeat: int


def build_matrix(
    fixtures: list[Fixture],
    representations: list[str],
    categories: list[str] | None,
    per_category: int,
    repeats: int,
) -> list[Cell]:
    cells: list[Cell] = []
    for fx in fixtures:
        questions = build(fx, per_category=per_category, categories=categories)
        for rep_name in representations:
            rep = REPRESENTATIONS[rep_name]
            briefing = rep(fx)
            for q in questions:
                # Skip rather than score: a representation that cannot express
                # the fact was never going to answer, and counting that as a
                # wrong answer would make the comparison meaningless.
                if not set(q.needs) <= rep.provides:
                    continue
                for r in range(repeats):
                    cells.append(Cell(fx, rep_name, briefing, q, r))
    return cells


def skipped_summary(fixtures, representations, categories, per_category) -> dict:
    """What each representation cannot express — a finding in its own right."""
    out: dict[str, dict[str, int]] = {}
    for fx in fixtures:
        for q in build(fx, per_category=per_category, categories=categories):
            for rep_name in representations:
                if not set(q.needs) <= REPRESENTATIONS[rep_name].provides:
                    out.setdefault(rep_name, {}).setdefault(q.category, 0)
                    out[rep_name][q.category] += 1
    return out


def ask(client, model: str, effort: str, cell: Cell, max_tokens: int) -> dict:
    q = cell.question
    t0 = time.time()
    row = {
        "fixture": cell.fixture.fixture_id,
        "representation": cell.representation,
        "qid": q.qid,
        "category": q.category,
        "repeat": cell.repeat,
        "model": model,
        "effort": effort,
        "expected": q.answer,
    }
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {"type": "text", "text": RULES, "cache_control": {"type": "ephemeral"}},
                {
                    "type": "text",
                    "text": "FORTRESS BRIEFING\n\n" + cell.briefing,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": q.prompt}],
            thinking={"type": "adaptive"},
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": response_schema(q.answer_type)},
            },
        )
    except Exception as exc:  # noqa: BLE001 - every failure mode becomes a row
        row.update(error=f"{type(exc).__name__}: {exc}", correct=False, seconds=time.time() - t0)
        return row

    # Deliberately no server-side refusal fallback: the eval has to know exactly
    # which model produced each answer, and silently rerouting to another one
    # would corrupt the comparison. A refusal is recorded as an error row.
    if response.stop_reason == "refusal":
        row.update(
            error=f"refusal: {getattr(response.stop_details, 'category', None)}",
            correct=False,
            seconds=time.time() - t0,
        )
        return row

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        row.update(error=f"unparseable response: {text[:200]!r}", correct=False)
        return row

    g = grade(q.grader, q.answer, payload.get("answer"))
    row.update(
        got=payload.get("answer"),
        confidence=payload.get("confidence"),
        correct=g.correct,
        abstained=g.abstained,
        near_miss=g.near_miss,
        note=g.note,
        seconds=round(time.time() - t0, 2),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", None),
    )
    return row


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fixtures", nargs="*", help="fixture ids (default: all)")
    p.add_argument("--representations", nargs="*", default=sorted(REPRESENTATIONS))
    p.add_argument("--categories", nargs="*", help=f"default: all of {sorted(GENERATORS)}")
    p.add_argument("--per-category", type=int, default=3)
    p.add_argument("--repeats", type=int, default=1, help="samples per cell")
    p.add_argument("--model", default="claude-opus-5")
    p.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--max-tokens", type=int, default=16000)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--limit", type=int, help="stop after N cells (smoke tests)")
    p.add_argument("--out", type=Path, help="JSONL results path")
    p.add_argument("--dry-run", action="store_true", help="build prompts, call nothing")
    args = p.parse_args(argv)

    fixtures = load_all(FIXTURE_DIR)
    if args.fixtures:
        fixtures = [f for f in fixtures if f.fixture_id in args.fixtures]
    if not fixtures:
        print("no fixtures matched", file=sys.stderr)
        return 2
    for rep in args.representations:
        if rep not in REPRESENTATIONS:
            print(f"unknown representation {rep!r}", file=sys.stderr)
            return 2

    cells = build_matrix(
        fixtures, args.representations, args.categories, args.per_category, args.repeats
    )
    if args.limit:
        cells = cells[: args.limit]

    skipped = skipped_summary(fixtures, args.representations, args.categories, args.per_category)

    print(f"fixtures:        {', '.join(f.fixture_id for f in fixtures)}")
    print(f"representations: {', '.join(args.representations)}")
    print(f"cells:           {len(cells)}")
    for rep, cats in sorted(skipped.items()):
        detail = ", ".join(f"{c} x{n}" for c, n in sorted(cats.items()))
        print(f"  {rep} cannot express: {detail}")

    if args.dry_run:
        if cells:
            c = cells[0]
            print("\n--- sample system prompt ---")
            print(RULES)
            print("\nFORTRESS BRIEFING\n")
            print(c.briefing)
            print("\n--- sample question ---")
            print(f"[{c.representation} / {c.question.category}] {c.question.prompt}")
            print(f"expected: {c.question.answer!r} (grader: {c.question.grader})")
        return 0

    try:
        import anthropic
    except ImportError:
        print("pip install 'anthropic>=1.0' (see evals/perception/requirements.txt)", file=sys.stderr)
        return 2

    client = anthropic.Anthropic()
    out_path = args.out or Path("evals/perception/results") / f"run-{int(time.time())}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    done = 0
    with out_path.open("w", encoding="utf-8") as fh:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            for row in pool.map(
                lambda c: ask(client, args.model, args.effort, c, args.max_tokens), cells
            ):
                fh.write(json.dumps(row, sort_keys=True) + "\n")
                fh.flush()
                done += 1
                if done % 10 == 0 or done == len(cells):
                    print(f"  {done}/{len(cells)}", file=sys.stderr)

    print(f"\nwrote {done} rows to {out_path}")
    print(f"report with: python -m evals.perception.harness.report {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
