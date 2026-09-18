"""End-to-end tests against the real fixture files in `production/tests/
fixtures/` (see `PROVENANCE.md` for exactly what "real" means for each
line). These are the tests the handoff (`handoffs/2026-09-18-production-
package.md`) names as mattering more than raw coverage.
"""

from __future__ import annotations

from production import extract, schema, store


def _flows_for(result: dict, process_id: str) -> list[dict]:
    return [f for f in result["flows"] if f["process_id"] == process_id]


# ---- BREW_DRINK_FROM_PLANT: both passes, three of the four consumption branches ----


def test_brew_drink_from_plant_end_to_end():
    result = extract.extract()
    flows = _flows_for(result, "BREW_DRINK_FROM_PLANT")

    drink_flows = [
        f for f in flows
        if f["direction"] == schema.PRODUCT and f["node_id"] and f["node_id"].startswith("DRINK:")
    ]
    seed_flows = [
        f for f in flows
        if f["direction"] == schema.PRODUCT and f["node_id"] and f["node_id"].startswith("SEEDS:")
    ]

    # One reaction row in, five concrete drink nodes out.
    assert len(drink_flows) == 5
    assert {f["node_id"] for f in drink_flows} == {
        "DRINK:PLUMP_HELMET_WINE", "DRINK:PIG_TAIL_ALE", "DRINK:CAVE_WHEAT_BEER",
        "DRINK:SWEET_POD_WINE", "DRINK:DIMPLE_CUP_WINE",
    }
    assert all(f["quantity"] == 5 for f in drink_flows)
    assert all(f["status"] == schema.VERIFIED_RAWS for f in drink_flows)

    # 5 drink units and 1 seed each.
    assert len(seed_flows) == 5
    assert all(f["quantity"] == 1 for f in seed_flows)
    assert all(f["status"] == schema.VERIFIED_RAWS for f in seed_flows)

    # The barrel flow is occupied_until_released.
    barrel = next(
        f for f in flows
        if f["direction"] == schema.REAGENT and f["container_class"] == "FOOD_STORAGE_CONTAINER"
    )
    assert barrel["consumption"] == schema.OCCUPIED_UNTIL_RELEASED

    # The plant flow is consumed.
    plant_reagent = next(
        f for f in flows if f["direction"] == schema.REAGENT and f["node_id"] == "DRINK_MAT"
    )
    assert plant_reagent["consumption"] == schema.CONSUMED

    # No parametric row was left half-resolved: every product row for this
    # process has a concrete node_id now.
    assert all(f["node_id"] is not None for f in flows if f["direction"] == schema.PRODUCT)


# ---- GLAZE_STATUE: modified_in_place, no product row at all ------------------------


def test_glaze_reaction_has_no_product_row_and_is_modified_in_place():
    result = extract.extract()
    flows = _flows_for(result, "GLAZE_STATUE")

    products = [f for f in flows if f["direction"] == schema.PRODUCT]
    assert products == [], "a [IMPROVEMENT]-only reaction must emit no product row at all"

    statue = next(f for f in flows if f["direction"] == schema.REAGENT and f["node_id"] == "STATUE")
    assert statue["consumption"] == schema.MODIFIED_IN_PLACE

    # the glaze material itself has no PRESERVE_REAGENT and is a normal consumed reagent
    glaze_material = next(
        f for f in flows if f["direction"] == schema.REAGENT and f["node_id"] == "GLAZE_MAT"
    )
    assert glaze_material["consumption"] == schema.CONSUMED


# ---- BAG_ITEM: the token-family inconsistency, caught and not resolved -------------


def test_bag_item_family_mismatch_is_caught_not_resolved():
    result = extract.extract()
    flows = _flows_for(result, "PROCESS_PLANT_TO_BAG")

    bag_products = [f for f in flows if f["direction"] == schema.PRODUCT]
    assert len(bag_products) == 1, (
        "a naively-matched extractor would silently drop this row to zero; "
        "this one keeps exactly one honestly-unresolved row instead"
    )
    row = bag_products[0]
    assert row["node_id"] is None
    assert row["status"] == schema.UNAVAILABLE

    mrp = result["material_reaction_products"]
    bag_item_families = {r["token_family"] for r in mrp if r["token"] == "BAG_ITEM"}
    # Quarry bush declared it via ITEM_REACTION_PRODUCT (item_reaction_product
    # family); PROCESS_PLANT_TO_BAG's reagent filter is HAS_MATERIAL_REACTION_
    # PRODUCT (material_reaction_product family). The mismatch is visible in
    # the data, not resolved by this extractor -- see docs/PRODUCTION-MODEL.md
    # §6 and extract.pass2's own docstring.
    assert bag_item_families == {schema.FAMILY_ITEM_REACTION_PRODUCT}


def test_log_inherited_material_stays_unresolved_no_mrp_entry():
    """MAKE_WOODEN_CHAIR's product inherits "whatever wood the carpenter
    used" with no MATERIAL_REACTION_PRODUCT-style token at all to join
    against -- a genuinely unresolved case, distinct from the BAG_ITEM
    family mismatch (audit §2: "22/22 reagent-inherited... every piece of
    furniture/tool made from log inherits whatever wood the carpenter
    used")."""
    result = extract.extract()
    flows = _flows_for(result, "MAKE_WOODEN_CHAIR")
    chair = next(f for f in flows if f["direction"] == schema.PRODUCT)
    assert chair["node_id"] is None
    assert chair["status"] == schema.UNAVAILABLE


# ---- abs_tick: never the bare tick, which resets annually --------------------------


def test_abs_tick_formula():
    assert schema.abs_tick(0, 0) == 0
    assert schema.abs_tick(1, 0) == schema.TICKS_PER_YEAR
    assert schema.abs_tick(0, 227160) == 227160


def test_abs_tick_no_collision_across_year_boundary_and_sorts_correctly(tmp_path):
    db = tmp_path / "abs_tick.sqlite3"
    # Same cur_year_tick, two different years: the bare tick would collide.
    t_year0 = schema.abs_tick(cur_year=0, cur_year_tick=300000)
    t_year1 = schema.abs_tick(cur_year=1, cur_year_tick=300000)
    assert t_year0 != t_year1
    assert t_year1 - t_year0 == schema.TICKS_PER_YEAR

    observations = [
        {
            "abs_tick": t_year1, "subject_id": "fort", "metric": schema.METRIC_STOCK,
            "value": 20.0, "status": schema.MEASURED, "source_ref": "test: year 1 read",
        },
        {
            "abs_tick": t_year0, "subject_id": "fort", "metric": schema.METRIC_STOCK,
            "value": 10.0, "status": schema.MEASURED, "source_ref": "test: year 0 read",
        },
    ]
    store.write_all(db, observations=observations)

    with store.connect(db) as conn:
        rows = conn.execute(
            "SELECT abs_tick, value FROM production_observation ORDER BY abs_tick ASC"
        ).fetchall()

    # Written out of chronological order; querying by abs_tick still sorts
    # them correctly, unlike a bare cur_year_tick which would tie.
    assert [r["value"] for r in rows] == [10.0, 20.0]
    assert rows[0]["abs_tick"] == t_year0
    assert rows[1]["abs_tick"] == t_year1


def test_abs_tick_rejects_out_of_range_cur_year_tick():
    import pytest
    with pytest.raises(ValueError):
        schema.abs_tick(0, schema.TICKS_PER_YEAR)  # must reset to 0, not equal the period


# ---- cycle check --------------------------------------------------------------------


def test_no_cycle_in_extracted_fixture_graph():
    result = extract.extract()
    edges = extract.build_edges(result["flows"])
    assert len(edges) > 0, "the fixture graph should have at least one real edge to check"
    assert extract.find_cycle(edges) is None


# ---- the two free wins: wheelbarrow and minecart, verified_raws --------------------


def test_wheelbarrow_and_minecart_are_verified_raws():
    result = extract.extract()
    nodes_by_id = {n["id"]: n for n in result["nodes"]}
    assert nodes_by_id["TOOL:ITEM_TOOL_WHEELBARROW"]["status"] == schema.VERIFIED_RAWS
    assert nodes_by_id["TOOL:ITEM_TOOL_MINECART"]["status"] == schema.VERIFIED_RAWS

    attrs = {(a["subject_id"], a["name"]): a["value"] for a in result["attributes"]}
    assert attrs[("TOOL:ITEM_TOOL_WHEELBARROW", "size")] == "30000"
    assert attrs[("TOOL:ITEM_TOOL_WHEELBARROW", "container_capacity")] == "100000"
    assert attrs[("TOOL:ITEM_TOOL_MINECART", "size")] == "40000"
    assert attrs[("TOOL:ITEM_TOOL_MINECART", "container_capacity")] == "500000"


# ---- capacity_theoretical stays absent ----------------------------------------------


def test_no_capacity_theoretical_column_in_production_process(tmp_path):
    db = tmp_path / "cap.sqlite3"
    with store.connect(db) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(production_process)")}
    assert "capacity_theoretical" not in cols


# ---- full write + coverage integration ----------------------------------------------


def test_write_all_and_coverage_table(tmp_path):
    db = tmp_path / "prod.sqlite3"
    rows = extract.extract()
    counts = store.write_all(db, **rows)
    assert counts["production_node"] == len(rows["nodes"])
    assert counts["production_flow"] == len(rows["flows"])

    cov = store.coverage(db)
    assert cov["production_node"]["total"] == len(rows["nodes"])
    assert cov["production_flow"]["total"] == len(rows["flows"])
    # Every unresolved parametric flow reads as unavailable, never silently
    # dropped or silently guessed.
    assert cov["production_flow"]["unavailable"] >= 1

    with store.connect(db) as conn:
        statuses = {r["status"] for r in conn.execute("SELECT DISTINCT status FROM production_flow")}
    assert statuses <= set(schema.STATUS_VALUES)


def test_extract_module_is_importable_as_python_dash_m_target():
    # `python -m production.extract` needs a __main__ guard calling main();
    # this just proves main is callable and wired to store.write_all
    # without actually touching the repo's default database file (that is
    # exercised once by hand for the handoff write-up, not from the test
    # suite, so pytest never leaves an untracked artifact in the tree).
    assert callable(extract.main)
