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
    #
    # Node ids are `<item type>:<plant raw id>` (e.g. "DRINK:PLUMP_HELMET"),
    # not the illustrative wine names ("DRINK:PLUMP_HELMET_WINE") this
    # assertion used before 2026-09-19. Real-corpus finding: the fixture's
    # own MATERIAL_REACTION_PRODUCT lines used an invented 3-arg shape
    # (token:item_type:node_suffix) that never matched real DF raws --
    # real MRP lines are token:mat_type:mat_name and carry no item type at
    # all (confirmed against the real 159-reaction corpus; see
    # `research/2026-09-19-real-corpus-extraction.md`). The item type only
    # exists on the *reaction's* PRODUCT line ("DRINK"), which pass2 now
    # combines with the plant's own raw id from the matched material row,
    # instead of trusting a node name the MRP line never actually states.
    assert len(drink_flows) == 5
    assert {f["node_id"] for f in drink_flows} == {
        "DRINK:PLUMP_HELMET", "DRINK:PIG_TAIL", "DRINK:CAVE_WHEAT",
        "DRINK:SWEET_POD", "DRINK:DIMPLE_CUP",
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
    unparsed = rows.pop("unparsed")  # not one of write_all's kwargs
    assert unparsed == [], "the fixture set should have nothing unparsed"
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


# ======================================================================
# Real-corpus regression tests, 2026-09-19.
#
# `research/2026-09-19-real-corpus-extraction.md` ran the two-pass
# extractor against the real 159-reaction vanilla corpus (pulled read-only
# from VM 103 into a session scratchpad, never committed here -- this
# repo is public and the raws are game data, per that stream's handoff).
# It found several real token shapes the hand-assembled fixture subset
# never exercised, each a genuine extract.py bug, not a fixture gap. The
# lines quoted below are a handful of individual tokens (public DF raw
# syntax, not bulk game data) transcribed from that read, cited to the
# real file:line, used here as small inline regression inputs so the fix
# stays covered without adding anything under `production/tests/
# fixtures/` (frozen; out of scope for this stream).
# ======================================================================


def test_no_subtype_sentinel_does_not_leak_into_product_node_id():
    # reaction_smelter.txt (real corpus, 2026-09-19) uses a second, different
    # "no value" sentinel from every other reaction file: "NO_SUBTYPE"
    # instead of "NONE". Before the fix, every one of the 23 real smelter
    # product node ids carried a spurious ":NO_SUBTYPE:" segment, e.g.
    # "BAR:NO_SUBTYPE:COAL" instead of "BAR:COAL", silently verified_raws.
    # reaction_smelter.txt:9-10 (real corpus), BITUMINOUS_COAL_TO_COKE:
    text = (
        "[REACTION:BITUMINOUS_COAL_TO_COKE]\n"
        "\t[BUILDING:SMELTER:NONE]\n"
        "\t[REAGENT:A:1:BOULDER:NO_SUBTYPE:INORGANIC:COAL_BITUMINOUS]\n"
        "\t[PRODUCT:100:9:BAR:NO_SUBTYPE:COAL:COKE][PRODUCT_DIMENSION:150]\n"
        "\t[SKILL:SMELT]\n"
    )
    reactions = extract.parse_reactions(text, "reaction_smelter.txt")
    product = reactions[0]["products"][0]
    node_id = extract._fixed_node_id(
        product["item_type"], product["subtype"], product["mat_source_type"], product["mat_args"],
    )
    # mat_source_type "COAL" is a bare material name (not a PLANT_MAT/METAL/
    # INORGANIC family), so it is the material id directly; "COKE" is a
    # trailing arg this shape doesn't use for the id. The point of this
    # test is the sentinel, not this unrelated bare-material behaviour.
    assert node_id == "BAR:COAL"
    assert "NO_SUBTYPE" not in node_id


def test_metal_ore_reagent_shorthand_keeps_its_material():
    # reaction_smelter.txt:25 and :60-61 (real corpus, 2026-09-19): DF's
    # short REAGENT form for an ore, `[REAGENT:name:qty:METAL_ORE:material]`
    # -- only 4 args total, no subtype/mat-category/mat-args slots of their
    # own; the material lands directly in what this parser treats as the
    # subtype position. Before the fix every metal-ore reagent of every
    # smelting reaction extracted as the identical bare class "METAL_ORE",
    # indistinguishable from every other ore.
    text = (
        "[REACTION:SMELT_COPPER]\n"
        "\t[BUILDING:SMELTER:NONE]\n"
        "\t[REAGENT:B:1:METAL_ORE:COPPER]\n"
        "\t[PRODUCT:100:4:BAR:NONE:METAL:COPPER]\n"
        "[REACTION:SMELT_SILVER]\n"
        "\t[BUILDING:SMELTER:NONE]\n"
        "\t[REAGENT:A:1:METAL_ORE:SILVER]\n"
        "\t[PRODUCT:100:4:BAR:NONE:METAL:SILVER]\n"
    )
    reactions = extract.parse_reactions(text, "reaction_smelter.txt")
    copper_reagent = reactions[0]["reagents"][0]
    silver_reagent = reactions[1]["reagents"][0]
    copper_class, _, _ = extract._reagent_class(copper_reagent)
    silver_class, _, _ = extract._reagent_class(silver_reagent)
    assert copper_class == "METAL_ORE:COPPER"
    assert silver_class == "METAL_ORE:SILVER"
    assert copper_class != silver_class, (
        "before the fix both ores collapsed to the identical bare class 'METAL_ORE'"
    )


def test_bare_material_reagent_lye_is_material_qualified():
    # A second, lower-prevalence (2 real occurrences) instance of the same
    # underlying bug as METAL_ORE: the standard-shape reagent with a bare
    # material name (not a PLANT_MAT/METAL/INORGANIC family) in the
    # mat-category slot, e.g. real `[REAGENT:lye:150:LIQUID_MISC:NONE:LYE]`.
    # `_reagent_class`'s own docstring previously claimed this case
    # returned `(None, None, None)` -- untested, since no fixture exercised
    # it; the real behaviour was actually the lossy bare-item-type
    # fallback, extracting as plain "LIQUID_MISC" regardless of material.
    reagent = {
        "name": "lye", "quantity": "150", "item_type": "LIQUID_MISC",
        "subtype": "NONE", "mat_category": "LYE", "mat_args": [], "flags": [],
    }
    class_name, mechanism, container_class = extract._reagent_class(reagent)
    assert class_name == "LIQUID_MISC:LYE"
    assert mechanism == schema.MECH_ITEM_TYPE_ONLY


def test_get_item_data_from_reagent_in_item_type_position_stays_unavailable():
    # reaction_other.txt:318-330 (real corpus, 2026-09-19), PROCESS_PLANT_
    # TO_BAG. The ONLY occurrence of this shape across all 159 real
    # reactions: GET_ITEM_DATA_FROM_REAGENT sits in the ITEM TYPE position
    # of a 5-arg PRODUCT line, not the material-source position this file
    # otherwise assumes for both GET_*_FROM_REAGENT tokens:
    #   [PRODUCT:100:5:GET_ITEM_DATA_FROM_REAGENT:plant:BAG_ITEM]
    # Before the fix this parsed as item_type="GET_ITEM_DATA_FROM_REAGENT"
    # (an ordinary, non-parametric-looking item type as far as the old
    # `mat_source_type in (...)` check was concerned), so `_fixed_node_id`
    # built a node id straight out of the literal token text and marked it
    # verified_raws -- silently WRONG, not merely unavailable.
    text = (
        "[REACTION:PROCESS_PLANT_TO_BAG]\n"
        "\t[BUILDING:FARMER:CUSTOM_B]\n"
        "\t[REAGENT:plant:1:PLANT:NONE:NONE:NONE]\n"
        "\t\t[HAS_MATERIAL_REACTION_PRODUCT:BAG_ITEM]\n"
        "\t[REAGENT:bag:1:BAG:NONE:NONE:NONE]\n"
        "\t\t[EMPTY]\n"
        "\t\t[PRESERVE_REAGENT]\n"
        "\t[PRODUCT:100:5:GET_ITEM_DATA_FROM_REAGENT:plant:BAG_ITEM]\n"
        "\t\t[PRODUCT_TO_CONTAINER:bag]\n"
    )
    p1 = extract.pass1(
        [(text, "reaction_other.txt")],
        ("[OBJECT:PLANT]\n", "plant_standard.txt"),
        ("[OBJECT:MATERIAL_TEMPLATE]\n", "material_template_default.txt"),
        ("[OBJECT:ITEM]\n", "item_tool.txt"),
    )
    bag_flow = next(f for f in p1["flows"] if f["direction"] == schema.PRODUCT)
    assert bag_flow["node_id"] is None
    assert bag_flow["status"] == schema.UNAVAILABLE
    assert bag_flow["_parametric"] is True
    assert bag_flow["_mat_source_reagent"] == "plant"
    assert bag_flow["_mat_source_token"] == "BAG_ITEM"
    assert bag_flow["_item_type"] is None, (
        "DF's own item type is unresolved for this shape, not derivable "
        "from the product line alone -- must not be fabricated"
    )

    p2 = extract.pass2(p1)
    resolved = next(f for f in p2["flows"] if f["direction"] == schema.PRODUCT)
    assert resolved["node_id"] is None
    assert resolved["status"] == schema.UNAVAILABLE, (
        "no node id may ever be built from the literal token text "
        "'GET_ITEM_DATA_FROM_REAGENT:plant:BAG_ITEM'"
    )


def test_real_material_reaction_product_shape_materialises_by_plant_and_item_type():
    # plant_standard.txt (real corpus, 2026-09-19): MATERIAL_REACTION_
    # PRODUCT's real shape is `token:mat_type:mat_name` (3 args), NOT
    # `token:item_type:node_suffix` as the committed fixture (frozen,
    # `production/tests/fixtures/plant_standard.txt`) assumes -- e.g. real
    # `[MATERIAL_REACTION_PRODUCT:DRINK_MAT:LOCAL_PLANT_MAT:DRINK]`
    # (plant_standard.txt:13) and `[MATERIAL_REACTION_PRODUCT:SEED_MAT:
    # LOCAL_PLANT_MAT:SEED]` (plant_standard.txt:14). Neither arg carries an
    # item type or a fabricated node name; the concrete item only exists
    # once a reaction's own PRODUCT line supplies one (here "DRINK" from
    # the real BREW_DRINK_FROM_PLANT product line, itself quoted verbatim
    # in the committed fixture).
    reaction_text = (
        "[REACTION:BREW_DRINK_FROM_PLANT]\n"
        "\t[BUILDING:STILL:NONE]\n"
        "\t[REAGENT:plant:1:PLANT:NONE:NONE:NONE]\n"
        "\t\t[HAS_MATERIAL_REACTION_PRODUCT:DRINK_MAT]\n"
        "\t[PRODUCT:100:5:DRINK:NONE:GET_MATERIAL_FROM_REAGENT:plant:DRINK_MAT]\n"
        "\t\t[PRODUCT_DIMENSION:150]\n"
    )
    plant_text = (
        "[OBJECT:PLANT]\n"
        "[PLANT:MUSHROOM_HELMET_PLUMP]\n"
        "\t[USE_MATERIAL_TEMPLATE:STRUCTURAL:STRUCTURAL_PLANT_TEMPLATE]\n"
        "\t\t[MATERIAL_REACTION_PRODUCT:DRINK_MAT:LOCAL_PLANT_MAT:DRINK]\n"
        "\t\t[MATERIAL_REACTION_PRODUCT:SEED_MAT:LOCAL_PLANT_MAT:SEED]\n"
    )
    rows = extract.extract_from_sources(
        [(reaction_text, "reaction_other.txt")],
        (plant_text, "plant_standard.txt"),
        ("[OBJECT:MATERIAL_TEMPLATE]\n", "material_template_default.txt"),
        ("[OBJECT:ITEM]\n", "item_tool.txt"),
    )
    drink_flow = next(
        f for f in rows["flows"]
        if f["process_id"] == "BREW_DRINK_FROM_PLANT" and f["direction"] == schema.PRODUCT
    )
    # The real plant's own raw id (MUSHROOM_HELMET_PLUMP), not an invented
    # wine name -- item type (from the reaction) : plant id (from the
    # matched material row).
    assert drink_flow["node_id"] == "DRINK:MUSHROOM_HELMET_PLUMP"
    assert drink_flow["status"] == schema.VERIFIED_RAWS

    node_ids = {n["id"] for n in rows["nodes"]}
    assert "DRINK:MUSHROOM_HELMET_PLUMP" in node_ids
    # The MRP row's own result_node is the MATERIAL this plant's DRINK_MAT
    # token resolves to -- a different, material-kind node from the
    # concrete drink item pass2 builds, both honestly derivable.
    assert "MATERIAL:MUSHROOM_HELMET_PLUMP:DRINK" in node_ids
    mrp = next(r for r in rows["material_reaction_products"] if r["token"] == "DRINK_MAT")
    assert mrp["result_node"] == "MATERIAL:MUSHROOM_HELMET_PLUMP:DRINK"

    drink_class = next(c for c in rows["classes"] if c["class"] == "DRINK")
    assert drink_class["node_id"] == "DRINK:MUSHROOM_HELMET_PLUMP"


def test_category_tokens_captured_on_the_reaction_not_leaked_onto_a_product():
    # reaction_dyes.txt (real corpus, 2026-09-19): CATEGORY/CATEGORY_NAME/
    # CATEGORY_DESCRIPTION sit textually AFTER the last REAGENT/PRODUCT
    # block (98/159 real reactions carry one). Before the fix the generic
    # "attach to whichever reagent/product is currently open" branch
    # silently misattributed every one of them onto the LAST-parsed
    # product's own flags list.
    text = (
        "[REACTION:ACACIA_BARK_DYE]\n"
        "\t[NAME:make acacia bark dye]\n"
        "\t[BUILDING:DYER:NONE]\n"
        "\t[REAGENT:log:1:WOOD:NONE:PLANT_MAT:ACACIA:WOOD]\n"
        "\t[REAGENT:B:1:BAG:NONE:NONE:NONE][EMPTY][PRESERVE_REAGENT]\n"
        "\t[PRODUCT:100:1:POWDER_MISC:NONE:PLANT_MAT:ACACIA:BARK_DYE]"
        "[PRODUCT_DIMENSION:150][PRODUCT_TO_CONTAINER:B]\n"
        "\t[SKILL:PROCESSPLANTS]\n"
        "\t[CATEGORY:MAKE_DYE]\n"
        "\t[CATEGORY_NAME:Make dye]\n"
    )
    reactions = extract.parse_reactions(text, "reaction_dyes.txt")
    reaction = reactions[0]
    assert reaction["category"] == "MAKE_DYE"
    assert reaction["category_name"] == "Make dye"
    last_product_flag_names = {f[0] for f in reaction["products"][-1]["flags"]}
    assert "CATEGORY" not in last_product_flag_names
    assert "CATEGORY_NAME" not in last_product_flag_names
    assert reaction["unparsed"] == []


def test_unparsed_tracking_catches_a_genuinely_orphaned_token():
    # Fabricated (not a real corpus line): a bare flag token with neither a
    # reagent nor a product open, and not one of the recognised reaction-
    # level tokens. Proves the unparsed-line detector this handoff asked
    # for ("if the extractor has no way to report unparsed input, add
    # one") actually fires rather than silently accepting anything.
    text = (
        "[REACTION:MADE_UP_FOR_THIS_TEST]\n"
        "\t[BUILDING:STILL:NONE]\n"
        "\t[SOME_UNKNOWN_RESERVED_FLAG]\n"
        "\t[REAGENT:plant:1:PLANT:NONE:NONE:NONE]\n"
    )
    reactions = extract.parse_reactions(text, "reaction_other.txt")
    reaction = reactions[0]
    assert len(reaction["unparsed"]) == 1
    assert reaction["unparsed"][0]["token"] == "SOME_UNKNOWN_RESERVED_FLAG"
    assert reaction["unparsed"][0]["reason"] == "no open reagent/product to attach to"


def test_a_reactions_skill_is_an_attribute_and_never_written_into_labor():
    """`[SKILL:BREWING]` names a skill; the labor (BREWER) is not in the raws.
    Before 2026-09-21 the skill token was written into `production_process.labor`,
    which a reader would have returned as if it were a labor.
    `production.labor_ingest` resolves skill to labor from the game's own tables."""
    rows = extract.extract()
    brew = next(p for p in rows["processes"] if p["id"] == "BREW_DRINK_FROM_PLANT")
    assert brew["labor"] is None
    skills = [a for a in rows["attributes"] if a["subject_id"] == "BREW_DRINK_FROM_PLANT" and a["name"] == "skill"]
    assert [a["value"] for a in skills] == ["BREWING"]
    assert skills[0]["status"] == schema.VERIFIED_RAWS
    assert all(p["labor"] is None for p in rows["processes"])
