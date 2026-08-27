"""What the ledger currently supports concluding, and what it does not.

    python -m ledger.report [path]

This is deliberately not a "findings" tool. At N~20 the honest output is
mostly a statement of how thin the evidence is, so the report leads with
**coverage** (how many forts recorded each feature at all) and shows survival
by feature only underneath it, with the denominators visible.

`decisions/DECISIONS.md` 2026-08-25: "the fort ledger's schema defines what is
learnable." The schema sets that ceiling; this report says how much of it has
actually been reached, which is the number that matters when deciding whether
a comparison is worth making.

**No inference happens here.** Promotion of a hypothesis to doctrine is the
hierarchical Beta-Bernoulli model (research section 3.3, build item 4), which
does not exist yet. Reading a survival difference off this table and calling it
a lesson is exactly the flat-counter mistake the register rejected on
2026-08-25.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import store
from .schema import UNRECORDED

# Below this, a stratum is reported but explicitly marked as not worth
# comparing. The number is a display convention, not a statistical threshold;
# the real threshold comes from the SPRT/credible-interval rule in build
# item 4, which is not built.
THIN = 3


def _bar(n: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return " " * width
    filled = round(width * n / total)
    return "#" * filled + "." * (width - filled)


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else store.DEFAULT_PATH
    rows = store.load(path)

    print(f"fort ledger: {path}")
    print(f"{len(rows)} fort(s) recorded\n")

    if not rows:
        print("The ledger is empty, so nothing is learnable yet.")
        print("This is the expected state until the game side exists: the")
        print("schema was built first on purpose, because section 3.2 warns")
        print("that retrofitting covariates onto old rows defeats the point.")
        return 0

    fields = store.design_fields()

    print("COVERAGE - how many forts recorded each design feature")
    print("(a feature at 0 can never become a lesson, no matter the reasoning)\n")
    cov = store.coverage(rows, fields)
    width = max(len(f) for f in fields)
    for field in fields:
        n = cov[field]
        flag = "" if n else "   <- nothing learnable"
        print(f"  {field:<{width}}  {n:>3}/{len(rows)}  {_bar(n, len(rows))}{flag}")

    ended = [r for r in rows if r["outcome"]["status"] not in ("alive", UNRECORDED)]
    print(f"\n\nSURVIVAL BY FEATURE - {len(ended)} fort(s) that ended")
    print("Descriptive only. Not evidence for or against any hypothesis;")
    print("the evidence model (research 3.3) is not built.\n")

    for field in fields:
        strat = store.stratify(ended, field)
        if not strat.strata:
            continue
        print(f"  {field}")
        for stratum in strat.strata:
            durations = [
                d for d in (
                    s["outcome"]["duration_years"] for s in stratum.rows
                ) if d is not None
            ]
            mean = sum(durations) / len(durations) if durations else float("nan")
            thin = "  (too thin to compare)" if stratum.n < THIN else ""
            print(
                f"      {stratum.value:<22} n={stratum.n:<3} "
                f"mean survival {mean:5.1f} yr{thin}"
            )
        if strat.dropped_unrecorded:
            print(
                f"      [{strat.dropped_unrecorded} fort(s) excluded: "
                f"feature unrecorded]"
            )
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
