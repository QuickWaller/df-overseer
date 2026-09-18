"""One test per branch of `extract.derive_consumption`
(`docs/PRODUCTION-MODEL.md` §5), including the fourth, `modified_in_place`,
that the first design's three-value enum had no room for.
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
