"""One test per branch of `extract.derive_consumption`
(`docs/PRODUCTION-MODEL.md` §5), including the fourth, `modified_in_place`,
that the first design's three-value enum had no room for.

Real-corpus verification, 2026-09-19: the spec's "zero exceptions across
159 reactions" claim (`docs/PRODUCTION-MODEL.md` §5) was made by a human
reader, not by running code. This stream ran `derive_consumption` against
all 314 real reagent lines (159 reactions, from the real corpus pulled
read-only from VM 103, not committed to this repo) and found **zero
exceptions**: every line's `(preserve_reagent, not_improved,
reaction_has_product, product_to_container_target)` tuple landed cleanly
in exactly one of the four buckets below, with counts consumed=194,
occupied_until_released=78, occupied_job=38, modified_in_place=4 (the
four real `GLAZE_*` reactions, one `modified_in_place` reagent each,
matching the branch below exactly). Restricted to the 148 reactions this
extractor actually loads into the graph (11 adventure-mode-only reactions
excluded, `docs/PRODUCTION-MODEL.md` audit §5), the same zero-exception
result holds over 292 reagent lines (182/78/28/4). See
`research/2026-09-19-real-corpus-extraction.md` for the full writeup; the
real corpus itself cannot be committed here (game data, this repo is
public), so that verification cannot be re-run as a committed test --
these branch-level unit tests below stay the durable, reproducible
coverage.
"""

from __future__ import annotations

from production import extract, schema


def test_no_preserve_reagent_is_consumed():
    # e.g. the plant in BREW_DRINK_FROM_PLANT, log in carpentry.
    outcome = extract.derive_consumption(
        preserve_reagent=False, not_improved=False,
        reaction_has_product=True, product_to_container_target=False,
    )
    assert outcome == schema.CONSUMED


def test_preserve_and_container_target_is_occupied_until_released():
    # e.g. the barrel/pot in BREW_DRINK_FROM_PLANT: PRESERVE_REAGENT, and
    # its name is the target of a PRODUCT_TO_CONTAINER on the drink product.
    outcome = extract.derive_consumption(
        preserve_reagent=True, not_improved=False,
        reaction_has_product=True, product_to_container_target=True,
    )
    assert outcome == schema.OCCUPIED_UNTIL_RELEASED


def test_preserve_without_container_target_is_occupied_job():
    # e.g. the tool in carpentry: PRESERVE_REAGENT + HAS_EDGE, never named
    # by any PRODUCT_TO_CONTAINER.
    outcome = extract.derive_consumption(
        preserve_reagent=True, not_improved=False,
        reaction_has_product=True, product_to_container_target=False,
    )
    assert outcome == schema.OCCUPIED_JOB


def test_preserve_not_improved_no_product_is_modified_in_place():
    # The four GLAZE_* reactions: PRESERVE_REAGENT + NOT_IMPROVED, and the
    # whole reaction has no [PRODUCT] line to even attach a value to.
    outcome = extract.derive_consumption(
        preserve_reagent=True, not_improved=True,
        reaction_has_product=False, product_to_container_target=False,
    )
    assert outcome == schema.MODIFIED_IN_PLACE


def test_modified_in_place_takes_priority_over_container_target():
    # Degenerate case that should never occur in real raws (a reaction with
    # no PRODUCT line cannot also have a PRODUCT_TO_CONTAINER target), but
    # the branch order should still resolve predictably rather than by
    # accident.
    outcome = extract.derive_consumption(
        preserve_reagent=True, not_improved=True,
        reaction_has_product=False, product_to_container_target=True,
    )
    assert outcome == schema.MODIFIED_IN_PLACE
