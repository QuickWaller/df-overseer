"""What the prediction log currently shows. No inference, same as `ledger.report`.

    python -m predictions.report [path]

Leads with the count that matters most for trusting anything else here:
**how many predictions are still pending because no ledger row exists for
their fort yet.** A prediction log full of pending rows is not evidence of
anything — it is a statement that grading has not had a chance to run.

**Calibration (build item 6) is not computed here.** A Brier score needs a
model-stated confidence per prediction, which this schema does not carry
(deliberately — `predicate_op`/`predicate_value` is a binary claim, not a
probability). This report's `graded_true`/`graded_false` split is the raw
material a future calibration metric would consume, not the metric itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import store
from .schema import GRADED_FALSE, GRADED_TRUE, PENDING, UNRESOLVABLE


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else store.DEFAULT_PATH
    rows = store.load(path)

    print(f"prediction log: {path}")
    print(f"{len(rows)} prediction(s) registered\n")

    if not rows:
        print("The log is empty. Expected until the game side exists and the")
        print("first decision worth pre-registering a prediction about happens.")
        return 0

    by_status = {s: [r for r in rows if r["status"] == s] for s in
                 (PENDING, GRADED_TRUE, GRADED_FALSE, UNRESOLVABLE)}

    print("STATUS")
    for status, group in by_status.items():
        print(f"  {status:<14} {len(group):>3}")

    graded = len(by_status[GRADED_TRUE]) + len(by_status[GRADED_FALSE])
    if graded:
        hit_rate = 100 * len(by_status[GRADED_TRUE]) / graded
        print(f"\nHIT RATE (graded only, n={graded}): {hit_rate:.1f}% predicted correctly")
        print("Descriptive only — not a calibration score (see module docstring).")

    if by_status[PENDING]:
        print(f"\nPENDING ({len(by_status[PENDING])}) — by fort, so an overdue one is visible")
        by_fort: dict[str, int] = {}
        for r in by_status[PENDING]:
            by_fort[r["fort_id"]] = by_fort.get(r["fort_id"], 0) + 1
        for fort_id, n in sorted(by_fort.items()):
            print(f"  {fort_id:<20} {n}")

    if by_status[UNRESOLVABLE]:
        print(f"\nUNRESOLVABLE ({len(by_status[UNRESOLVABLE])}) — signal never got recorded")
        print("in the ledger for that fort. Worth checking whether the field's")
        print("MECHANICAL claim actually holds (learning/ledger/README.md: 'expect some")
        print("fields to turn out unreadable').")
        for r in by_status[UNRESOLVABLE]:
            print(f"  {r['prediction_id']:<24} signal={r['signal']}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
