"""The labor join against the building tool's real result shapes.

`handoffs/2026-09-21-deploy-building-batch.md` found two gaps the earlier stub
shape hid: `building.find` returns an **array** of candidates, each with its own
`requirements` and `gaps`, and `building.build` returns its material need as
`building_material.filters[]` (each with `need`, `quantity`, `available`,
`stock`). The fixtures in `building_shapes.py` follow the Lua tool's own field
names. The rule under test: **never an all-clear beside a gap**, and unknown is
null plus a reason, never `[]`.

Part one is the join and `enrich` without a transport; part two goes through the
real server over a real MCP client (the harness `test_gotchas_server.py` uses).
"""

from __future__ import annotations

import copy
import json

import pytest

from dfmcp import labor_join as lj
from dfmcp import tool_guidance as tg
from dfmcp.tests import building_shapes as bs

pytestmark = pytest.mark.asyncio

DB = "/graph.sqlite3"


def c2(labors, status="known"):
    return lambda db, kind: {"kind": kind, "labors": list(labors), "status": status, "processes": [], "unknown_reason": None}


def counts(mapping):
    async def count(labors):
        return {"counts": {k: mapping.get(k, 1) for k in labors}, "errors": {}}

    return count


def joiner(labors=("STONECUTTER",), mapping=None, status="known"):
    return lj.LaborJoin(DB, counts(mapping or {}), labors_for_kind=c2(labors, status))


async def enrich(tool, structured, args=None, j=None):
    out, blocks = await tg.enrich(tool, args or {}, structured, False, guidance=None, labor_join=j or joiner())
    return out, blocks


NO_REQ_BLOCK = "the result carried no requirements block"


# --------------------------------------------------------------------------
# building.find: an array of candidates
# --------------------------------------------------------------------------


class TestFindArrays:
    async def test_masons_reads_the_requirements_of_its_candidates_and_has_no_gap(self):
        out, _ = await enrich("building.find", bs.as_structured(bs.masons_find()), {"kind": "Masons"})
        assert out["gaps"] == []
        assert NO_REQ_BLOCK not in out["gaps_unknown"]
        assert out["gaps_unknown"] == []
        assert out["operating_labors"]["labors"] == ["STONECUTTER"]
        assert len(out["result"]) == 5  # the tool's own candidates are untouched

    async def test_well_trapparts_gap_reaches_the_agent_exactly_once(self):
        out, blocks = await enrich("building.find", bs.as_structured(bs.well_find()), {"kind": "Well"})
        assert out["gaps"] == [bs.WELL_GAP]
        assert out["gaps_unknown"] == []
        assert f"<gap>{bs.WELL_GAP}</gap>" in blocks[0]

    async def test_bed_gap(self):
        out, _ = await enrich("building.find", bs.as_structured(bs.bed_find()), {"kind": "Bed"})
        assert out["gaps"] == [bs.BED_GAP]

    async def test_farmplot_has_no_material_filter_and_that_is_not_a_gap_or_an_unknown(self):
        out, _ = await enrich("building.find", bs.as_structured(bs.farm_find()), {"kind": "FarmPlot"})
        assert out["gaps"] == [] and out["gaps_unknown"] == []

    async def test_the_kind_is_taken_from_the_candidates_not_only_the_argument(self):
        seen = []

        def stub(db, kind):
            seen.append(kind)
            return {"kind": kind, "labors": [], "status": "known", "processes": [], "unknown_reason": None}

        j = lj.LaborJoin(DB, counts({}), labors_for_kind=stub)
        await enrich("building.find", bs.as_structured(bs.masons_find()), {"kind": "masons"}, j)
        assert seen == ["Masons"]

    async def test_candidates_that_differ_keep_every_gap(self):
        cands = bs.well_find()
        cands[2]["gaps"] = [bs.WELL_GAP, "the site is a long way from any stockpile"]
        cands[4]["gaps"] = []  # this candidate reports nothing; the others still do
        out, _ = await enrich("building.find", bs.as_structured(cands), {"kind": "Well"})
        assert out["gaps"] == [bs.WELL_GAP, "the site is a long way from any stockpile"]

    async def test_a_gap_on_one_candidate_alone_is_not_dropped(self):
        cands = bs.masons_find()
        cands[3]["gaps"] = ["could not count stock for BLOCKS (see stock errors)"]
        out, _ = await enrich("building.find", bs.as_structured(cands), {"kind": "Masons"})
        assert out["gaps"] == ["could not count stock for BLOCKS (see stock errors)"]

    async def test_a_gap_the_requirements_show_is_found_even_if_no_candidate_reported_it(self):
        cands = bs.well_find()
        for c in cands:
            c["gaps"] = []  # a tool that computed its gaps wrongly must not yield a false all-clear
        out, _ = await enrich("building.find", bs.as_structured(cands), {"kind": "Well"})
        assert out["gaps"] == [bs.WELL_GAP]

    async def test_an_empty_candidate_list_is_unknown_not_clear(self):
        out, _ = await enrich("building.find", {"result": []}, {"kind": "Well"})
        assert out["gaps"] == []
        assert any("no candidates" in u for u in out["gaps_unknown"])

    async def test_a_non_object_candidate_is_unknown(self):
        cands = bs.masons_find()
        cands[1] = "site 2"
        out, _ = await enrich("building.find", bs.as_structured(cands), {"kind": "Masons"})
        assert any("not an object" in u for u in out["gaps_unknown"])

    async def test_candidates_of_different_kinds_are_reported(self):
        cands = bs.masons_find()
        cands[1] = bs.bed_find()[1]
        out, _ = await enrich("building.find", bs.as_structured(cands), {"kind": "Masons"})
        assert any("different kinds" in u for u in out["gaps_unknown"])
        assert bs.BED_GAP in out["gaps"]

    async def test_candidates_without_requirements_are_unknown(self):
        cands = bs.masons_find()
        for c in cands:
            del c["requirements"]
        out, _ = await enrich("building.find", bs.as_structured(cands), {"kind": "Masons"})
        assert out["gaps_unknown"].count(NO_REQ_BLOCK) == 1

    async def test_a_tools_own_object_with_only_a_result_key_is_not_mistaken_for_a_wrapper_unless_it_is_a_list(self):
        out, _ = await enrich("building.find", {"result": "ok"}, {"kind": "Masons"})
        assert NO_REQ_BLOCK in out["gaps_unknown"]

    async def test_a_gaps_field_that_is_not_a_list_is_unknown(self):
        cands = bs.masons_find()
        cands[0]["gaps"] = "needs a lot"
        out, _ = await enrich("building.find", bs.as_structured(cands), {"kind": "Masons"})
        assert any("not a list" in u for u in out["gaps_unknown"])


# --------------------------------------------------------------------------
# building.build: an object with filters[]
# --------------------------------------------------------------------------


class TestBuildObjects:
    async def test_bed_dry_run_keeps_its_gap_and_the_filters_are_readable(self):
        out, _ = await enrich("building.build", bs.bed_build(), {"kind": "Bed"})
        assert out["gaps"] == [bs.BED_GAP]
        assert not any("not in a shape" in u for u in out["gaps_unknown"])
        assert out["validation"]["ok"] is True  # the tool's own facts are untouched

    async def test_masons_dry_run_is_clear(self):
        out, _ = await enrich("building.build", bs.masons_build(), {"kind": "Masons"})
        assert out["gaps"] == [] and out["gaps_unknown"] == []

    async def test_a_labor_gap_is_no_longer_dropped_beside_the_tools_own_gaps(self):
        j = joiner(mapping={"STONECUTTER": 0})
        out, _ = await tg.enrich(
            "building.build", {"kind": "Masons"}, bs.bed_build() | {"kind": bs.MASONS_KIND}, False,
            guidance=None, labor_join=j,
        )
        assert out["gaps"] == [bs.BED_GAP, "nobody has the STONECUTTER labor enabled"]

    async def test_the_tools_own_gaps_come_first_and_unchanged(self):
        j = joiner(mapping={"STONECUTTER": 0})
        out, _ = await enrich("building.build", bs.masons_build() | {"gaps": ["custom note"]}, {"kind": "Masons"}, j)
        assert out["gaps"][0] == "custom note"


# --------------------------------------------------------------------------
# The filters, one field at a time
# --------------------------------------------------------------------------


def req_of(*filters, **extra):
    return bs.requirements(list(filters), **extra)


class TestFilterReading:
    async def test_enough_stock_is_no_gap(self):
        assert lj.requirement_gaps(req_of(bs.item_filter(1, "BED", 1))) == {"gaps": [], "gaps_unknown": []}

    async def test_short_stock_is_a_gap_in_the_tools_own_words(self):
        assert lj.requirement_gaps(req_of(bs.item_filter(1, "BLOCKS", 1, quantity=3)))["gaps"] == [
            "needs 3 of BLOCKS, 1 available"
        ]

    async def test_every_short_filter_is_reported(self):
        out = lj.requirement_gaps(req_of(bs.item_filter(1, "BLOCKS", 0), bs.item_filter(2, "CHAIN", 0)))
        assert out["gaps"] == ["needs 1 of BLOCKS, 0 available", "needs 1 of CHAIN, 0 available"]

    async def test_an_uncounted_filter_is_unknown_with_the_reason_never_a_gap(self):
        rec = bs.filter_rec(1, "BUCKET", None, item_type="BUCKET",
                            stock={"BUCKET": {"total": None, "available": None, "error": "availability read failed: boom"}})
        out = lj.requirement_gaps(req_of(rec))
        assert out["gaps"] == []
        assert "could not count stock for BUCKET" in out["gaps_unknown"][0] and "boom" in out["gaps_unknown"][0]

    async def test_a_filter_with_no_countable_type_says_why(self):
        rec = bs.filter_rec(1, "an item matching flags2.screw", None, count_error="the filter has no item type")
        out = lj.requirement_gaps(req_of(rec))
        assert out["gaps"] == [] and "no item type" in out["gaps_unknown"][0]

    async def test_a_size_dependent_quantity_with_none_in_stock_is_a_gap(self):
        rec = bs.filter_rec(1, "BLOCKS", 0, quantity=-1, item_type="BLOCKS")
        assert lj.requirement_gaps(req_of(rec))["gaps"] == [
            "needs some of BLOCKS (the quantity depends on the footprint), 0 available"
        ]

    async def test_a_size_dependent_quantity_with_some_in_stock_is_unknown_not_clear(self):
        rec = bs.filter_rec(1, "BLOCKS", 5, quantity=-1, item_type="BLOCKS")
        out = lj.requirement_gaps(req_of(rec))
        assert out["gaps"] == [] and "depends on the footprint" in out["gaps_unknown"][0]

    async def test_the_getfilters_error_is_unknown(self):
        out = lj.requirement_gaps(req_of(error="getFiltersByType failed: nope"))
        assert out["gaps"] == [] and "nope" in out["gaps_unknown"][0]

    async def test_an_empty_filter_list_with_the_tools_note_is_nothing_needed(self):
        assert lj.requirement_gaps(bs.FARM_REQ) == {"gaps": [], "gaps_unknown": []}

    @pytest.mark.parametrize(
        "bm",
        [
            {"filters": "many"},
            {"filters": [None]},
            {"filters": [{"need": "BED"}]},  # no quantity
            {"filters": [{"quantity": 1, "available": 0}]},  # no need
            {"filters": [{"need": "BED", "quantity": True, "available": 0}]},
            {"filters": [{"need": "BED", "quantity": 1, "available": True}]},
        ],
    )
    async def test_malformed_filters_are_unknown_never_clear(self, bm):
        out = lj.requirement_gaps({"building_material": bm})
        assert out["gaps"] == [] and out["gaps_unknown"]

    async def test_the_older_shape_still_works(self):
        old = {"building_material": {"accepts": ["BOULDER", "WOOD", "BLOCKS"],
                                     "fort_owned": {"BOULDER": 0, "WOOD": 0, "BLOCKS": 0}}}
        assert lj.requirement_gaps(old)["gaps"] == ["no BOULDER, WOOD or BLOCKS in the fort to build with"]

    async def test_combined_gaps_do_not_mutate_or_share_the_callers_list(self):
        own = [bs.BED_GAP]
        lj.combined_gaps([bs.BED_REQ], own)
        assert own == [bs.BED_GAP]


# --------------------------------------------------------------------------
# The invariant, over every real shape and every labor answer
# --------------------------------------------------------------------------

FIXTURES = {
    "masons_find": bs.masons_find, "bed_find": bs.bed_find, "well_find": bs.well_find,
    "farm_find": bs.farm_find, "bed_build": bs.bed_build, "masons_build": bs.masons_build,
}


def candidate_gaps(value):
    items = value if isinstance(value, list) else [value]
    return [g for c in items for g in c.get("gaps", [])]


class TestNeverAllClearBesideAGap:
    @pytest.mark.parametrize("name", sorted(FIXTURES))
    @pytest.mark.parametrize("labor_status", ["known", "partial", "unknown"])
    async def test_a_reported_gap_is_never_an_empty_gaps(self, name, labor_status):
        value = FIXTURES[name]()
        j = joiner(labors=() if labor_status == "unknown" else ("STONECUTTER",), status=labor_status, mapping={"STONECUTTER": 2})
        out, _ = await tg.enrich("building.find", {"kind": "X"}, bs.as_structured(value), False, guidance=None, labor_join=j)
        for gap in candidate_gaps(value):
            assert gap in out["gaps"]
        if candidate_gaps(value):
            assert out["gaps"] != []
        # And unknown is a reason, not an empty list.
        if labor_status == "unknown":
            assert out["operating_labors"]["labors"] is None and out["gaps_unknown"]

    async def test_the_graph_being_absent_does_not_hide_the_gap(self, tmp_path):
        j = lj.LaborJoin(str(tmp_path / "absent.sqlite3"), counts({}))
        out, _ = await tg.enrich("building.find", {"kind": "Well"}, bs.as_structured(bs.well_find()), False, guidance=None, labor_join=j)
        assert out["gaps"] == [bs.WELL_GAP]
        assert out["operating_labors"]["labors"] is None

    async def test_a_raising_graph_does_not_hide_the_gap(self):
        def boom(db, kind):
            raise RuntimeError("locked")

        j = lj.LaborJoin(DB, counts({}), labors_for_kind=boom)
        out, _ = await tg.enrich("building.find", {"kind": "Well"}, bs.as_structured(bs.well_find()), False, guidance=None, labor_join=j)
        assert out["gaps"] == [bs.WELL_GAP]

    async def test_no_kind_anywhere_does_not_hide_the_gap(self):
        cands = bs.well_find()
        for c in cands:
            del c["kind"]
        out, _ = await tg.enrich("building.find", {}, bs.as_structured(cands), False, guidance=None, labor_join=joiner())
        assert out["gaps"] == [bs.WELL_GAP]
        assert out["operating_labors"]["labors"] is None

    async def test_the_fixtures_are_not_mutated_by_the_join(self):
        value = bs.well_find()
        before = copy.deepcopy(value)
        await tg.enrich("building.find", {"kind": "Well"}, bs.as_structured(value), False, guidance=None, labor_join=joiner())
        assert value == before

