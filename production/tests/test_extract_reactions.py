"""Reaction-file discovery and the reaction shapes the 145 unextracted reactions have.

`handoffs/2026-09-21-extract-remaining-reactions.md`. The 145 reactions the game
lists that the extractor never read are world-generated instrument reactions and
are in no raw text file, so these tests use the closest real text there is
(`fixtures/extra_reactions/`, verbatim, see its PROVENANCE.md), not a made-up
imitation of the 145.
"""

import pytest

from production import extract, schema

EXTRA = extract.FIXTURES_DIR / "extra_reactions"


def _extract_extra():
    return extract.extract(reaction_files=extract.discover_reaction_files(EXTRA))


def _attrs(rows, subject, name):
    return [a["value"] for a in rows["attributes"] if a["subject_id"] == subject and a["name"] == name]


# ---- discovery ------------------------------------------------------------------


def test_discovery_of_the_fixtures_dir_finds_exactly_the_default_four_in_order():
    found = [p.name for p in extract.discover_reaction_files(extract.FIXTURES_DIR)]
    assert found == list(extract.DEFAULT_REACTION_FILES)


def test_discovery_puts_unknown_files_after_the_defaults_and_sorts_them(tmp_path):
    for name in ("reaction_zeta.txt", "reaction_alpha.txt", "reaction_dyes.txt", "reaction_other.txt", "notes.txt"):
        (tmp_path / name).write_text("[OBJECT:REACTION]\n", encoding="utf-8")
    found = [p.name for p in extract.discover_reaction_files(tmp_path)]
    assert found == ["reaction_other.txt", "reaction_dyes.txt", "reaction_alpha.txt", "reaction_zeta.txt"]


def test_discovery_reads_a_file_reachable_from_two_roots_once(tmp_path):
    (tmp_path / "reaction_a.txt").write_text("[OBJECT:REACTION]\n", encoding="utf-8")
    assert len(extract.discover_reaction_files(tmp_path, tmp_path)) == 1


def test_discovery_of_a_wrong_path_raises_rather_than_returning_nothing(tmp_path):
    with pytest.raises(NotADirectoryError):
        extract.discover_reaction_files(tmp_path / "does_not_exist")


def test_extract_refuses_zero_reaction_files(tmp_path):
    # A wrong directory that exists must not look like a successful empty extraction.
    with pytest.raises(FileNotFoundError):
        extract.extract(fixtures_dir=tmp_path)


def test_default_extract_is_the_same_as_reading_the_four_named_files():
    discovered = extract.extract()
    named = extract.extract(reaction_files=[extract.FIXTURES_DIR / n for n in extract.DEFAULT_REACTION_FILES])
    assert discovered == named


# ---- the summary that proves every reaction is accounted for ---------------------------


def test_summary_accounts_for_every_reaction_in_every_file():
    texts = [extract._read(f) for f in extract.discover_reaction_files(EXTRA)]
    rows = extract.summarise_reaction_files(texts)
    by_name = {r["source"].replace("\\", "/").rsplit("/", 1)[-1]: r for r in rows}
    assert by_name["reaction_instrument_example.txt"]["reactions"] == 4
    assert by_name["reaction_spatter.txt"] == {**by_name["reaction_spatter.txt"], "reactions": 2, "processes": 1, "adventure_only": 1}
    assert by_name["reaction_steam_engine.txt"]["processes"] == 1
    for r in rows:
        assert r["reactions"] == r["processes"] + r["adventure_only"] + r["duplicates"] + r["no_id"]
    assert sum(r["processes"] for r in rows) == len(_extract_extra()["processes"])


def test_a_duplicate_reaction_id_keeps_the_first_and_is_reported(tmp_path):
    first = "[REACTION:SAME_ID]\n[NAME:first]\n[BUILDING:KILN:NONE]\n[SKILL:POTTERY]\n"
    second = "[REACTION:SAME_ID]\n[NAME:second]\n[BUILDING:STILL:NONE]\n"
    (tmp_path / "reaction_a.txt").write_text(first, encoding="utf-8")
    (tmp_path / "reaction_b.txt").write_text(second, encoding="utf-8")
    texts = [extract._read(f) for f in extract.discover_reaction_files(tmp_path)]
    empty = ("", "x")
    rows = extract.extract_from_sources(texts, empty, empty, empty)
    assert [p["id"] for p in rows["processes"]] == ["SAME_ID"]
    assert rows["processes"][0]["workshop_node"] == "BUILDING:KILN"
    assert len(rows["unparsed"]) == 1
    assert "duplicate reaction id" in rows["unparsed"][0]["reason"]
    summary = extract.summarise_reaction_files(texts)
    assert [(r["processes"], r["duplicates"]) for r in summary] == [(1, 0), (0, 1)]


def test_a_reaction_with_no_id_is_reported_not_written():
    empty = ("", "x")
    rows = extract.extract_from_sources([("[REACTION]\n[BUILDING:KILN:NONE]\n", "reaction_x.txt")], empty, empty, empty)
    assert rows["processes"] == []
    assert [u["reason"] for u in rows["unparsed"]] == ["reaction has no id"]


# ---- the instrument reaction shape -------------------------------------------------------


def test_instrument_example_extracts_four_processes_with_their_buildings_and_skills():
    rows = _extract_extra()
    nodes = {p["id"]: p["workshop_node"] for p in rows["processes"]}
    assert nodes["MAKE EXAMPLE DRUM BODY"] == "BUILDING:CRAFTSMAN"
    assert nodes["MAKE EXAMPLE DRUM HEAD"] == "BUILDING:LEATHER"
    assert nodes["MAKE EXAMPLE DRUM"] == "BUILDING:CRAFTSMAN"
    assert nodes["MAKE EXAMPLE WIND"] == "BUILDING:CRAFTSMAN"
    assert _attrs(rows, "MAKE EXAMPLE DRUM BODY", "skill") == ["BONECARVE"]
    assert _attrs(rows, "MAKE EXAMPLE DRUM HEAD", "skill") == ["LEATHERWORK"]
    assert _attrs(rows, "MAKE EXAMPLE WIND", "skill") == ["WOODCRAFT"]
    assert all(p["labor"] is None for p in rows["processes"])
    assert rows["unparsed"] == []


def test_tool_reagents_keep_their_subtype_so_two_different_tools_are_two_classes():
    rows = _extract_extra()
    classes = sorted(
        f["node_id"] for f in rows["flows"]
        if f["process_id"] == "MAKE EXAMPLE DRUM" and f["direction"] == schema.REAGENT
    )
    assert classes == ["TOOL:EXAMPLE DRUM BODY", "TOOL:EXAMPLE DRUM HEAD"]


def test_material_from_reagent_instrument_products_stay_unresolved_not_invented():
    rows = _extract_extra()
    for pid in ("MAKE EXAMPLE DRUM BODY", "MAKE EXAMPLE DRUM", "MAKE EXAMPLE WIND"):
        (product,) = [f for f in rows["flows"] if f["process_id"] == pid and f["direction"] == schema.PRODUCT]
        assert product["node_id"] is None and product["status"] == schema.UNAVAILABLE


def test_improvement_and_description_are_recorded_on_the_reaction():
    rows = _extract_extra()
    assert _attrs(rows, "MAKE EXAMPLE DRUM", "improvement") == [
        "100:instrument:INSTRUMENT_PIECE:BODY:GET_MATERIAL_FROM_REAGENT:drum:NONE",
        "100:instrument:INSTRUMENT_PIECE:HEAD:GET_MATERIAL_FROM_REAGENT:head:NONE",
    ]
    assert _attrs(rows, "MAKE EXAMPLE DRUM", "description") == ["USE_INSTRUMENT:EXAMPLE DRUM"]
    assert _attrs(rows, "MAKE EXAMPLE DRUM BODY", "category") == ["INSTRUMENT_PIECE"]


def test_the_subtype_is_only_carried_for_item_types_that_name_an_item_definition():
    plant_growth = {
        "name": "plant", "quantity": "1", "item_type": "PLANT_GROWTH", "subtype": "LEAVES",
        "mat_category": "PLANT_MAT", "mat_args": ["APPLE", "LEAF"], "flags": [], "line": 1,
    }
    # Unchanged from before this stream: PLANT_GROWTH's subtype is not part of the class id.
    assert extract._reagent_class(plant_growth)[0] == "PLANT_GROWTH:APPLE"
    tool = {**plant_growth, "item_type": "TOOL", "subtype": "ITEM_TOOL_QUIRE", "mat_category": "NONE", "mat_args": []}
    assert extract._reagent_class(tool)[0] == "TOOL:ITEM_TOOL_QUIRE"
    bare = {**tool, "subtype": "NONE"}
    assert extract._reagent_class(bare)[0] == "TOOL"


# ---- shapes DFHack's reactions add ----------------------------------------------------------


def test_steam_engine_reaction_second_building_fuel_and_dimension():
    rows = _extract_extra()
    assert _attrs(rows, "STOKE_BOILER", "workshop_alt") == ["MAGMA_STEAM_ENGINE"]
    assert _attrs(rows, "STOKE_BOILER", "requires_fuel") == ["true"]
    (product,) = [f for f in rows["flows"] if f["process_id"] == "STOKE_BOILER"]
    assert product["node_id"] == "LIQUID_MISC:WATER"
    assert (product["unit"], product["unit_source"]) == (schema.UNIT_VOLUME, schema.UNIT_SOURCE_PRODUCT_DIMENSION)
    assert rows["unparsed"] == []  # a [FUEL] before any reagent is not orphaned


def test_fuel_after_the_product_is_recorded_on_the_reaction_not_the_product():
    # Lines 5 to 11 of the real vanilla reaction_smelter.txt, verbatim (the
    # reconstructed fixtures beside this file carry no [FUEL] at all).
    real = (
        "[REACTION:BITUMINOUS_COAL_TO_COKE]\n"
        "[NAME:make coke from bituminous coal]\n"
        "[BUILDING:SMELTER:NONE]\n"
        "[REAGENT:A:1:BOULDER:NO_SUBTYPE:INORGANIC:COAL_BITUMINOUS]\n"
        "[PRODUCT:100:9:BAR:NO_SUBTYPE:COAL:COKE][PRODUCT_DIMENSION:150]\n"
        "[FUEL]\n"
        "[SKILL:SMELT]\n"
    )
    (reaction,) = extract.parse_reactions(real, "reaction_smelter.txt")
    assert reaction["fuel"] is True
    assert reaction["products"][0]["flags"] == []  # was misfiled here before
    empty = ("", "x")
    rows = extract.extract_from_sources([(real, "reaction_smelter.txt")], empty, empty, empty)
    assert _attrs(rows, "BITUMINOUS_COAL_TO_COKE", "requires_fuel") == ["true"]


def test_adventure_only_reaction_is_skipped_and_counted_not_written():
    rows = _extract_extra()
    assert "SPATTER_ADD_OBJECT_LIQUID" not in {p["id"] for p in rows["processes"]}
    assert "SPATTER_ADD_WEAPON_EXTRACT" in {p["id"] for p in rows["processes"]}
