"""`production.labor_ingest`: the dump to graph step.

The fixture (`fixtures/labor_dump/`) is a filtered subset of the real dump,
entries verbatim. Every expected value below was read off the real dump and the
real extraction (2026-09-21), not derived from this code: `ConstructBlocks` is
`CUT_STONE` -> STONECUTTER, `ConstructDoor` has skill -1, `MakeFlask` has only a
`skill_metal` override, the Mason's Workshop's Workers tab is
[STONECUTTER, STONE_CARVER], and so on.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from production import labor_ingest as li
from production import labors, schema, store
from production.tests.labor_helpers import FIXTURE_DUMP, build_graph, rows


@pytest.fixture()
def graph(tmp_path):
    path = tmp_path / "graph.sqlite3"
    build_graph(path)
    return path


@pytest.fixture()
def ingested(graph):
    report = li.ingest_dump(graph, FIXTURE_DUMP)
    return graph, report


def _proc(path, pid):
    got = rows(path, "SELECT * FROM production_process WHERE id = ?", (pid,))
    assert len(got) == 1, pid
    return got[0]


def _attr(path, subject, name):
    got = rows(path, "SELECT * FROM production_attribute WHERE subject_id = ? AND name = ?", (subject, name))
    return got[0] if got else None


# ---- job to labor: only from the game's table ---------------------------------


class TestJobLabor:
    def test_skill_labor_is_determined(self, ingested):
        path, _ = ingested
        p = _proc(path, "JOB:Masons:ConstructBlocks:construct blocks")
        assert p["labor"] == "STONECUTTER" and p["is_hardcoded"] == 1
        assert _attr(path, p["id"], "labor_basis")["value"] == "job_table_skill"

    def test_a_job_with_no_table_labor_stays_null_with_a_reason(self, ingested):
        path, _ = ingested
        p = _proc(path, "JOB:Masons:ConstructDoor:construct door")
        assert p["labor"] is None
        basis = _attr(path, p["id"], "labor_basis")
        assert basis["value"] == "undetermined:no_job_table_labor"
        assert basis["status"] == schema.UNAVAILABLE

    def test_override_only_labor_is_material_dependent_not_a_labor(self, ingested):
        path, _ = ingested
        p = _proc(path, "JOB:Leatherworks:MakeFlask:construct waterskin")
        assert p["labor"] is None  # METAL_CRAFT applies only to a metal flask
        assert _attr(path, p["id"], "labor_basis")["value"] == "undetermined:material_dependent"
        cand = _attr(path, p["id"], "labor_candidate")
        assert cand["value"] == "METAL_CRAFT" and cand["status"] == schema.PRIOR

    def test_direct_labor_on_the_job_is_determined(self, ingested):
        path, _ = ingested
        p = _proc(path, "JOB:GlassFurnace:CollectSand:collect sand")
        assert p["labor"] == "HAUL_ITEM"
        assert _attr(path, p["id"], "labor_basis")["value"] == "job_table_attr_labor"

    def test_table_labor_the_workers_tab_does_not_offer_is_refused(self, ingested):
        """ConstructBlocks is STONECUTTER in the job table at the Carpenter's
        Workshop too, but the Carpenter's Workers tab is [CARPENTER, TRAPPER]."""
        path, _ = ingested
        p = _proc(path, "JOB:Carpenters:ConstructBlocks:construct blocks")
        assert p["labor"] is None
        assert _attr(path, p["id"], "labor_basis")["value"] == "undetermined:contradicts_profile"
        assert _attr(path, p["id"], "labor_candidate")["value"] == "STONECUTTER"

    def test_pure_function_cases(self):
        assert li.job_labor(None)[1] == "undetermined:job_not_in_table"
        both = {"skill": {"labor": "COOK"}, "attr_labor": "HAUL_ITEM"}
        assert li.job_labor(both) == (None, "undetermined:labor_conflict", ["COOK", "HAUL_ITEM"])
        same = {"skill": {"labor": "COOK"}, "attr_labor": "COOK"}
        assert li.job_labor(same)[0] == "COOK"
        none_labor = {"skill": {"labor": "NONE"}}
        assert li.job_labor(none_labor)[1] == "undetermined:no_job_table_labor"


# ---- reactions: skill to labor ------------------------------------------------


class TestReactionLabors:
    def test_a_skill_the_dump_maps_becomes_a_labor(self, ingested):
        path, _ = ingested
        assert _proc(path, "BILLON_MAKING")["labor"] == "SMELT"
        assert _attr(path, "BILLON_MAKING", "labor_basis")["value"] == "skill_map"
        assert _proc(path, "ACACIA_BARK_DYE")["labor"] == "PROCESS_PLANT"

    def test_an_unmapped_skill_is_null_not_the_skill_name(self, ingested):
        path, report = ingested
        for rid in ("BREW_DRINK_FROM_PLANT", "MAKE WOODEN CHAIR"):
            assert _proc(path, rid)["labor"] is None
        assert _attr(path, "BREW_DRINK_FROM_PLANT", "labor_basis")["value"] == "undetermined:skill_not_in_table:BREWING"
        assert report["skills_without_labor"]["BREWING"] == 3

    def test_name_match_only_counts_as_a_candidate_when_the_workers_tab_agrees(self, ingested):
        path, _ = ingested
        # GLAZING is a labor name and is in the Kiln's Workers tab: candidate, still NULL.
        assert _proc(path, "GLAZE_STATUE")["labor"] is None
        assert _attr(path, "GLAZE_STATUE", "labor_candidate")["value"] == "GLAZING"
        # BREWING is not a labor name: no candidate at all.
        assert _attr(path, "BREW_DRINK_FROM_PLANT", "labor_candidate") is None
        # CARPENTRY is not a labor name (CARPENTER is): no candidate.
        assert _attr(path, "MAKE WOODEN CHAIR", "labor_candidate") is None

    def test_a_fuller_skill_table_fills_the_gaps_and_is_validated(self, graph, tmp_path):
        good = tmp_path / "skills.json"
        good.write_text(json.dumps({"skills": [
            {"skill": "BREWING", "labor": "BREWER"}, {"skill": "GLAZING", "labor": "GLAZING"},
        ]}))
        report = li.ingest_dump(graph, FIXTURE_DUMP, good)
        assert _proc(graph, "BREW_DRINK_FROM_PLANT")["labor"] == "BREWER"
        assert _attr(graph, "BREW_DRINK_FROM_PLANT", "labor_basis")["value"] == "skill_map"
        assert _proc(graph, "GLAZE_STATUE")["labor"] == "GLAZING"  # in the Kiln's Workers tab too
        assert _attr(graph, "GLAZE_STATUE", "labor_candidate") is None  # no longer only a candidate
        assert report["extra_skill_table"] is True
        # the Still is now partial, not unknown: BREWER is determined, HERBALIST is still unexplained.
        r = labors.labors_for_kind(graph, "Still")
        assert r["status"] == "partial" and r["labors"] == ["BREWER"]
        assert r["unexplained_profile_labors"] == ["HERBALIST"]

    def test_a_table_labor_the_kinds_workers_tab_lacks_is_refused_for_reactions_too(self, graph, tmp_path):
        wrong = tmp_path / "skills.json"
        wrong.write_text(json.dumps([{"skill": "GLAZING", "labor": "CARPENTER"}]))
        li.ingest_dump(graph, FIXTURE_DUMP, wrong)  # CARPENTER is not in the Kiln's Workers tab
        assert _proc(graph, "GLAZE_STATUE")["labor"] is None
        assert _attr(graph, "GLAZE_STATUE", "labor_basis")["value"] == "undetermined:contradicts_profile"

    def test_extra_table_naming_a_labor_that_does_not_exist_is_refused(self, graph, tmp_path):
        bad = tmp_path / "skills.json"
        bad.write_text(json.dumps([{"skill": "BREWING", "labor": "BREWWER"}]))
        with pytest.raises(li.LaborIngestError, match="not in the game's labor list"):
            li.ingest_dump(graph, FIXTURE_DUMP, bad)

    def test_a_skill_with_two_labors_is_an_error(self):
        jt = {"jobs": [
            {"name": "A", "skill": {"skill": "X", "labor": "COOK"}},
            {"name": "B", "skill": {"skill": "X", "labor": "SMELT"}},
        ]}
        with pytest.raises(li.LaborIngestError, match="maps to both"):
            li.build_skill_map(jt)

    def test_extractor_rows_with_a_labor_this_module_did_not_write_are_refused(self, tmp_path):
        """A graph extracted before the skill/labor split holds skill tokens in
        `labor`; reading those as labors is the bug this refuses."""
        path = tmp_path / "old.sqlite3"
        build_graph(path, labor_column={"BREW_DRINK_FROM_PLANT": "BREWING"})
        with pytest.raises(li.LaborIngestError, match="re-run extraction"):
            li.ingest_dump(path, FIXTURE_DUMP)


# ---- kinds and nodes ----------------------------------------------------------


class TestKindsAndNodes:
    def test_kind_node_comes_from_the_extracted_reactions_and_twins_share_it(self, ingested):
        path, report = ingested
        assert _attr(path, "kind:Kiln", "node")["value"] == "BUILDING:KILN"
        assert _attr(path, "kind:MagmaKiln", "node")["value"] == "BUILDING:KILN"
        assert _attr(path, "kind:Smelter", "node")["value"] == _attr(path, "kind:MagmaSmelter", "node")["value"]
        assert report["kinds_mapped_to_raws_node"] == 8

    def test_a_kind_no_extracted_reaction_reaches_gets_a_constructed_node(self, ingested):
        path, _ = ingested
        assert _attr(path, "kind:Masons", "node")["value"] == "BUILDING:KIND:Masons"
        node = rows(path, "SELECT * FROM production_node WHERE id = 'BUILDING:KIND:Masons'")[0]
        assert node["kind"] == schema.KIND_BUILDING and node["status"] == schema.MEASURED
        assert node["source_ref"].startswith("dump:")

    def test_every_kind_gets_its_workers_tab_list_even_when_empty(self, ingested):
        path, _ = ingested
        assert _attr(path, "kind:Masons", "profile_labors")["value"] == "STONECUTTER,STONE_CARVER"
        assert _attr(path, "kind:Smelter", "profile_labors")["value"] == ""

    def test_custom_workshops_are_keyed_by_their_custom_code(self):
        assert li.kind_token({"subtype_name": "Custom:SOAP_MAKER"}) == "SOAP_MAKER"
        assert li.kind_token({"subtype_name": "Masons"}) == "Masons"

    def test_reactions_the_extractor_did_not_read_are_added_with_a_null_labor(self, ingested):
        path, report = ingested
        p = _proc(path, "MAKE_ENT12 INK1_BODY")
        assert p["labor"] is None and p["is_hardcoded"] == 0 and p["source_ref"].startswith("dump:s3")
        assert _attr(path, p["id"], "labor_basis")["value"] == "undetermined:unextracted_reaction"
        assert report["unextracted_reactions"] == 3

    def test_a_reaction_hosted_by_two_nodes_lists_the_second_as_workshop_alt(self, ingested):
        path, _ = ingested
        p = _proc(path, "MAKE_ENT12 INK3_VIB")
        assert p["workshop_node"] == "BUILDING:KIND:MetalsmithsForge"
        assert _attr(path, p["id"], "workshop_alt")["value"] == "KIND:MagmaForge"

    def test_twin_kinds_do_not_duplicate_hard_coded_rows(self, ingested):
        path, report = ingested
        melt = rows(path, "SELECT id FROM production_process WHERE id LIKE 'JOB:%MeltMetalObject%'")
        assert len(melt) == 1
        assert report["hardcoded"]["rows"] == 19


# ---- the Mason's Workshop question --------------------------------------------


class TestMasonReconciliation:
    def test_the_data_says_stonecutter_and_not_mason(self, ingested):
        _, report = ingested
        m = report["mason_reconciliation"]
        assert m["construct_blocks_labor"] == "STONECUTTER"
        assert m["masons_workshop_profile_labors"] == ["STONECUTTER", "STONE_CARVER"]
        assert m["masons_workers_tab_offers_MASON"] is False
        assert m["job_types_whose_skill_maps_to_MASON"] == []
        assert m["kinds_whose_workers_tab_offers_MASON"] == []
        assert m["masons_jobs_with_no_table_labor"] == ["ConstructDoor", "ConstructQuern", "ConstructTable"]

    def test_the_masons_answer_is_partial_and_names_what_is_missing(self, ingested):
        path, _ = ingested
        r = labors.labors_for_kind(path, "Masons")
        assert r["status"] == "partial" and r["labors"] == ["STONECUTTER"]
        assert "MASON" not in r["labors"]
        assert r["unexplained_profile_labors"] == ["STONE_CARVER"]
        assert "no labor in the game's job table (3)" in r["unknown_reason"]


# ---- idempotence and what it must not erase -----------------------------------


def _snapshot(path):
    with store.connect(path) as conn:
        return {
            t: sorted(tuple(r) for r in conn.execute(f"SELECT * FROM {t}").fetchall())
            for t in ("production_node", "production_process", "production_attribute", "production_flow")
        }


class TestIdempotence:
    def test_running_twice_gives_identical_tables(self, graph):
        li.ingest_dump(graph, FIXTURE_DUMP)
        first = _snapshot(graph)
        li.ingest_dump(graph, FIXTURE_DUMP)
        assert _snapshot(graph) == first

    def test_a_rerun_without_the_extra_table_resets_labors_it_set(self, graph, tmp_path):
        extra = tmp_path / "skills.json"
        extra.write_text(json.dumps([{"skill": "BREWING", "labor": "BREWER"}]))
        li.ingest_dump(graph, FIXTURE_DUMP, extra)
        assert _proc(graph, "MAKE_MEAD")["labor"] == "BREWER"
        li.ingest_dump(graph, FIXTURE_DUMP)
        assert _proc(graph, "MAKE_MEAD")["labor"] is None

    def test_observations_survive_ingest(self, graph):
        obs = {"abs_tick": 1_000_000, "subject_id": "fort", "metric": schema.METRIC_POPULATION,
               "value": 22, "status": schema.MEASURED, "source_ref": "test"}
        store.write_all(graph, observations=[obs], reset=False)
        li.ingest_dump(graph, FIXTURE_DUMP)
        li.ingest_dump(graph, FIXTURE_DUMP)
        assert len(rows(graph, "SELECT * FROM production_observation")) == 1

    def test_extractor_rows_are_not_touched_beyond_their_labor(self, graph):
        before = {p["id"]: p for p in rows(graph, "SELECT * FROM production_process WHERE source_ref NOT LIKE 'dump:%'")}
        li.ingest_dump(graph, FIXTURE_DUMP)
        after = {p["id"]: p for p in rows(graph, "SELECT * FROM production_process WHERE source_ref NOT LIKE 'dump:%'")}
        assert set(before) == set(after)
        for pid, row in before.items():
            assert {**after[pid], "labor": None} == {**row, "labor": None}

    def test_a_reextraction_then_ingest_recovers(self, graph):
        li.ingest_dump(graph, FIXTURE_DUMP)
        build_graph(graph)  # write_all(reset=True) wipes the dump rows too
        assert rows(graph, "SELECT * FROM production_attribute WHERE source_ref LIKE 'dump:%'") == []
        li.ingest_dump(graph, FIXTURE_DUMP)
        assert _proc(graph, "BILLON_MAKING")["labor"] == "SMELT"

    def test_finalize_leaves_a_rollback_journal_file(self, graph):
        li.ingest_dump(graph, FIXTURE_DUMP)
        conn = sqlite3.connect(graph)
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        finally:
            conn.close()

    def test_a_missing_dump_file_is_an_error(self, graph, tmp_path):
        with pytest.raises(li.LaborIngestError, match="is missing"):
            li.ingest_dump(graph, tmp_path)


# ---- reconciliation with a wider extractor (handoffs/2026-09-21-extract-remaining-reactions.md) ----

#: A reaction the dump lists for Kiln/MagmaKiln and Masons that the extractor did
#: not read in the fixture graph. The raw text below is a **synthetic** stand-in in
#: the shape of the game's instrument example (`fixtures/extra_reactions/`), used
#: only to give the extractor a reaction of this id; nothing pins its contents to
#: the real world-generated reaction, which is in no raw file.
_GENERATED = (
    "[REACTION:MAKE_ENT12 INK1_BODY]\n"
    "[NAME:make test body]\n"
    "[BUILDING:KILN:NONE]\n"
    "[REAGENT:clay:1:BOULDER:NONE:NONE:NONE]\n"
    "[PRODUCT:100:1:TOOL:SOME BODY:GET_MATERIAL_FROM_REAGENT:clay:NONE]\n"
    "[SKILL:GLAZING]\n"
)


def _add_extracted_reaction(path):
    from production import extract

    empty = ("", "x")
    got = extract.extract_from_sources([(_GENERATED, "reaction_generated.txt")], empty, empty, empty)
    with store.connect(path) as conn, conn:
        conn.executemany(
            "INSERT OR IGNORE INTO production_node (id, kind, display_name, durability, status, source_ref) "
            "VALUES (:id, :kind, :display_name, :durability, :status, :source_ref)", got["nodes"],
        )
        conn.executemany(
            "INSERT INTO production_process (id, workshop_node, labor, is_hardcoded, source_ref) "
            "VALUES (:id, :workshop_node, :labor, :is_hardcoded, :source_ref)", got["processes"],
        )
        conn.executemany(
            "INSERT INTO production_attribute (subject_id, name, value, unit, status, source_ref) "
            "VALUES (:subject_id, :name, :value, :unit, :status, :source_ref)", got["attributes"],
        )


class TestWiderExtractor:
    def test_the_report_counts_extracted_and_unextracted_game_reactions(self, ingested):
        _, report = ingested
        assert report["game_listed_reactions"] == 13
        assert report["game_listed_reactions_from_raws"] + report["unextracted_reactions"] == report["game_listed_reactions"]
        assert report["unextracted_by_kind"]["Kiln"] == 1

    def test_a_reaction_the_extractor_now_reads_gets_no_dump_row(self, graph):
        _add_extracted_reaction(graph)
        report = li.ingest_dump(graph, FIXTURE_DUMP)
        got = rows(graph, "SELECT * FROM production_process WHERE id = 'MAKE_ENT12 INK1_BODY'")
        assert len(got) == 1 and not got[0]["source_ref"].startswith("dump:")
        assert got[0]["workshop_node"] == "BUILDING:KILN"
        # One fewer than the 3 dump-only reactions when this one was unextracted.
        assert report["unextracted_reactions"] == 2
        assert report["unextracted_by_kind"].get("Kiln", 0) == 0
        assert report["game_listed_reactions_from_raws"] == 11

    def test_its_labor_basis_now_comes_from_its_skill_not_from_being_unextracted(self, graph):
        _add_extracted_reaction(graph)
        li.ingest_dump(graph, FIXTURE_DUMP)
        basis = _attr(graph, "MAKE_ENT12 INK1_BODY", "labor_basis")["value"]
        assert basis == "undetermined:skill_not_in_table:GLAZING"
        assert _attr(graph, "MAKE_ENT12 INK1_BODY", "skill")["value"] == "GLAZING"

    def test_no_reaction_id_appears_twice_in_the_process_table(self, graph):
        _add_extracted_reaction(graph)
        li.ingest_dump(graph, FIXTURE_DUMP)
        li.ingest_dump(graph, FIXTURE_DUMP)
        dupes = rows(graph, "SELECT id, COUNT(*) n FROM production_process GROUP BY id HAVING n > 1")
        assert dupes == []

    def test_rerunning_with_the_wider_extraction_is_idempotent(self, graph):
        _add_extracted_reaction(graph)
        li.ingest_dump(graph, FIXTURE_DUMP)
        first = _snapshot(graph)
        li.ingest_dump(graph, FIXTURE_DUMP)
        assert _snapshot(graph) == first

    def test_a_dump_row_for_a_reaction_is_replaced_when_a_later_run_finds_it_extracted(self, graph):
        li.ingest_dump(graph, FIXTURE_DUMP)
        assert _proc(graph, "MAKE_ENT12 INK1_BODY")["source_ref"].startswith("dump:")
        # The reaction is now extracted (the dump's own row is what a re-ingest
        # cleans up first), so a re-ingest must end with the extractor's row only.
        with store.connect(graph) as conn, conn:
            conn.execute("DELETE FROM production_process WHERE id = 'MAKE_ENT12 INK1_BODY'")
            conn.execute("DELETE FROM production_attribute WHERE subject_id = 'MAKE_ENT12 INK1_BODY'")
        _add_extracted_reaction(graph)
        li.ingest_dump(graph, FIXTURE_DUMP)
        got = rows(graph, "SELECT * FROM production_process WHERE id = 'MAKE_ENT12 INK1_BODY'")
        assert len(got) == 1 and not got[0]["source_ref"].startswith("dump:")

    def test_an_extracted_reaction_the_game_does_not_list_is_reported(self, graph):
        # The fixture graph's reactions are all listed by the dump, so nothing to report.
        assert li.ingest_dump(graph, FIXTURE_DUMP)["extracted_not_listed_by_game"] == []
        with store.connect(graph) as conn, conn:
            conn.execute(
                "INSERT INTO production_process (id, workshop_node, labor, is_hardcoded, source_ref) "
                "VALUES ('MAKE EXAMPLE PHANTOM', 'BUILDING:KILN', NULL, 0, 'reaction_example.txt:1')"
            )
        report = li.ingest_dump(graph, FIXTURE_DUMP)
        assert report["extracted_not_listed_by_game"] == ["MAKE EXAMPLE PHANTOM"]
