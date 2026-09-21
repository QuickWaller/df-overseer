"""`dfmcp.labor_join`: the server-side labor join, pinned to contract C2.

`production.labors.labors_for_kind` is built by another stream. Until it
merges, every test injects a stub that returns exactly the shape C2 names:

    labors_for_kind(db_path, kind_token) -> {"kind": str, "labors": [str],
      "status": "known" | "partial" | "unknown",
      "processes": [{"id", "labor" or null, "source_ref"}],
      "unknown_reason": str or null}

The rule under test throughout: **unknown is not zero.** `unknown` and
`partial` must reach the agent as unknown, never as an empty list, and a count
the labor read could not make (`null` plus an error, contract C1) is never
read as 0.
"""

from __future__ import annotations

import inspect

import pytest

from dfmcp import labor_join as lj

pytestmark = pytest.mark.asyncio

DB = "/somewhere/production.sqlite3"


def c2(status="known", labors=("BREWER",), reason=None, kind="Still", processes=None):
    return {
        "kind": kind,
        "labors": list(labors),
        "status": status,
        "processes": processes if processes is not None else [
            {"id": "proc-brew", "labor": "BREWER", "source_ref": "reaction_brew.txt"}
        ],
        "unknown_reason": reason,
    }


class Stub:
    """A C2 stub that records how it was called."""

    def __init__(self, result=None, raises=None):
        self.result, self.raises, self.calls = result, raises, []

    def __call__(self, db_path, kind_token):
        self.calls.append((db_path, kind_token))
        if self.raises:
            raise self.raises
        return self.result


def counter(counts=None, errors=None, raises=None):
    calls = []

    async def count_labors(labors):
        calls.append(list(labors))
        if raises:
            raise raises
        return {"counts": counts if counts is not None else {}, "errors": errors or {}}

    count_labors.calls = calls
    return count_labors


GOOD_REQ = {
    "building_material": {
        "accepts": ["BOULDER", "WOOD", "BLOCKS"],
        "fort_owned": {"BOULDER": 3, "WOOD": 0, "BLOCKS": 0},
    }
}


def make(stub, count):
    return lj.LaborJoin(DB, count, labors_for_kind=stub)


# --------------------------------------------------------------------------
# The contract itself
# --------------------------------------------------------------------------


class TestContractC2:
    async def test_stub_is_called_with_db_path_then_kind_token(self):
        stub, count = Stub(c2()), counter({"BREWER": 2})
        await make(stub, count).join("Still", GOOD_REQ)
        assert stub.calls == [(DB, "Still")]

    async def test_the_real_function_matches_the_signature_when_it_exists(self):
        try:
            from production import labors
        except ImportError:
            pytest.skip("production/labors.py (the graph stream) has not merged yet")
        names = list(inspect.signature(labors.labors_for_kind).parameters)
        assert names[:2] == ["db_path", "kind_token"]

    async def test_labor_join_tools_are_the_building_tools(self):
        assert lj.LABOR_JOIN_TOOLS == ("building.find", "building.build")


# --------------------------------------------------------------------------
# Known
# --------------------------------------------------------------------------


class TestKnown:
    async def test_known_labors_with_counts_and_no_gap_when_someone_has_the_labor(self):
        count = counter({"BREWER": 3})
        out = await make(Stub(c2()), count).join("Still", GOOD_REQ)
        op = out["operating_labors"]
        assert op["status"] == "known" and op["labors"] == ["BREWER"]
        assert op["citizens_with_labor"] == {"BREWER": 3}
        assert op["processes"][0]["id"] == "proc-brew"
        assert out["gaps"] == [] and out["gaps_unknown"] == []
        assert count.calls == [["BREWER"]]

    async def test_zero_citizens_with_a_labor_is_a_gap_in_plain_words(self):
        out = await make(Stub(c2()), counter({"BREWER": 0})).join("Still", GOOD_REQ)
        assert out["gaps"] == ["nobody has the BREWER labor enabled"]
        assert out["gaps_unknown"] == []

    async def test_known_and_genuinely_empty_is_an_empty_list_and_needs_no_count(self):
        count = counter()
        out = await make(Stub(c2(labors=[], processes=[])), count).join("Statue", GOOD_REQ)
        assert out["operating_labors"]["status"] == "known"
        assert out["operating_labors"]["labors"] == []
        assert out["operating_labors"]["citizens_with_labor"] is None
        assert count.calls == []
        assert out["gaps"] == [] and out["gaps_unknown"] == []

    async def test_several_labors_are_counted_in_one_call(self):
        count = counter({"MASON": 0, "STONECUTTER": 4})
        out = await make(Stub(c2(labors=["MASON", "STONECUTTER"])), count).join("Masons", GOOD_REQ)
        assert count.calls == [["MASON", "STONECUTTER"]]
        assert out["gaps"] == ["nobody has the MASON labor enabled"]


# --------------------------------------------------------------------------
# Unknown and partial must never look like an empty list
# --------------------------------------------------------------------------


class TestUnknownIsNotZero:
    async def test_unknown_reaches_the_agent_as_null_with_a_reason_never_as_a_list(self):
        stub = Stub(c2(status="unknown", labors=[], reason="no process hosted by this kind in the graph"))
        count = counter()
        out = await make(stub, count).join("Kennel", GOOD_REQ)
        op = out["operating_labors"]
        assert op["status"] == "unknown"
        assert op["labors"] is None  # not []
        assert op["citizens_with_labor"] is None
        assert "no process hosted" in op["unknown_reason"]
        assert any("operating labors are unknown" in g for g in out["gaps_unknown"])
        assert count.calls == []

    async def test_unknown_with_no_reason_still_says_so(self):
        out = await make(Stub(c2(status="unknown", labors=[], reason=None)), counter()).join("K", GOOD_REQ)
        assert out["operating_labors"]["labors"] is None
        assert "the graph gave no reason" in out["operating_labors"]["unknown_reason"]

    async def test_partial_keeps_the_known_labors_and_flags_them_incomplete(self):
        stub = Stub(c2(status="partial", labors=["MASON"], reason="two jobs had no labor mapping"))
        out = await make(stub, counter({"MASON": 2})).join("Masons", GOOD_REQ)
        op = out["operating_labors"]
        assert op["status"] == "partial" and op["labors"] == ["MASON"]
        assert op["unknown_reason"] == "two jobs had no labor mapping"
        assert any("only partly known" in g and "two jobs" in g for g in out["gaps_unknown"])
        assert out["gaps"] == []

    async def test_partial_with_a_zero_count_still_reports_the_gap_and_the_caveat(self):
        stub = Stub(c2(status="partial", labors=["MASON"], reason="incomplete"))
        out = await make(stub, counter({"MASON": 0})).join("Masons", GOOD_REQ)
        assert out["gaps"] == ["nobody has the MASON labor enabled"]
        assert any("only partly known" in g for g in out["gaps_unknown"])

    async def test_a_null_count_with_an_error_is_unknown_never_zero(self):
        count = counter({"BREWER": None}, errors={"BREWER": "no such labor token"})
        out = await make(Stub(c2()), count).join("Still", GOOD_REQ)
        assert out["operating_labors"]["citizens_with_labor"] == {"BREWER": None}
        assert out["operating_labors"]["citizens_with_labor_errors"] == {"BREWER": "no such labor token"}
        assert out["gaps"] == []  # NOT "nobody has the BREWER labor"
        assert any("could not count citizens with the BREWER labor" in g for g in out["gaps_unknown"])

    async def test_a_missing_count_key_is_unknown_never_zero(self):
        out = await make(Stub(c2()), counter({})).join("Still", GOOD_REQ)
        assert out["operating_labors"]["citizens_with_labor"] == {"BREWER": None}
        assert out["gaps"] == []
        assert out["gaps_unknown"]

    async def test_a_failed_count_read_makes_every_count_unknown(self):
        out = await make(Stub(c2(labors=["A", "B"])), counter(raises=RuntimeError("dfhack down"))).join("K", GOOD_REQ)
        assert out["operating_labors"]["citizens_with_labor"] == {"A": None, "B": None}
        assert out["gaps"] == []
        assert len(out["gaps_unknown"]) == 2 and "dfhack down" in out["gaps_unknown"][0]

    async def test_a_count_read_of_the_wrong_shape_is_unknown(self):
        async def bad(labors):
            return [1, 2, 3]

        out = await make(Stub(c2()), bad).join("Still", GOOD_REQ)
        assert out["operating_labors"]["citizens_with_labor"] == {"BREWER": None}
        assert out["gaps"] == []

    async def test_a_bool_is_not_a_count(self):
        out = await make(Stub(c2()), counter({"BREWER": True})).join("Still", GOOD_REQ)
        assert out["operating_labors"]["citizens_with_labor"] == {"BREWER": None}

    async def test_a_labor_name_that_is_not_a_token_is_not_counted_and_is_reported(self):
        count = counter({"BREWER": 1})
        out = await make(Stub(c2(labors=["BREWER", "rm -rf"])), count).join("Still", GOOD_REQ)
        assert count.calls == [["BREWER"]]
        assert any("'rm -rf'" in g for g in out["gaps_unknown"])
        assert out["operating_labors"]["labors"] == ["BREWER", "rm -rf"]

    async def test_graph_failures_are_unknown_not_errors_and_not_empty(self):
        for exc in (FileNotFoundError("no such db"), RuntimeError("locked")):
            out = await make(Stub(raises=exc), counter()).join("Still", GOOD_REQ)
            assert out["operating_labors"]["status"] == "unknown"
            assert out["operating_labors"]["labors"] is None
            assert str(exc) in out["operating_labors"]["unknown_reason"]

    async def test_a_result_that_breaks_c2_is_unknown(self):
        bad = [
            None, "text", {"labors": ["X"]}, {"status": "maybe", "labors": []},
            {"status": "known", "labors": "BREWER"}, {"status": "partial", "labors": [1]},
        ]
        for raw in bad:
            out = await make(Stub(raw), counter()).join("Still", GOOD_REQ)
            assert out["operating_labors"]["status"] == "unknown", raw
            assert out["operating_labors"]["labors"] is None, raw

    async def test_no_kind_token_is_unknown(self):
        out = await make(Stub(c2()), counter()).join(None, GOOD_REQ)
        assert out["operating_labors"]["labors"] is None
        assert "no kind token" in out["operating_labors"]["unknown_reason"]

    async def test_missing_production_labors_module_is_unknown(self, monkeypatch, tmp_path):
        def boom():
            raise ImportError("No module named 'production.labors'")

        db = tmp_path / "g.sqlite3"
        db.write_bytes(b"")
        monkeypatch.setattr(lj, "_import_labors_for_kind", boom)
        out = await lj.LaborJoin(str(db), counter()).join("Still", GOOD_REQ)
        assert out["operating_labors"]["status"] == "unknown"
        assert "production.labors is not available" in out["operating_labors"]["unknown_reason"]

    async def test_an_absent_graph_file_is_unknown_and_the_real_reader_is_never_called(self, tmp_path, monkeypatch):
        called = []
        monkeypatch.setattr(lj, "_import_labors_for_kind", lambda: (lambda *a: called.append(a)))
        out = await lj.LaborJoin(str(tmp_path / "absent.sqlite3"), counter()).join("Still", GOOD_REQ)
        assert out["operating_labors"]["status"] == "unknown" and out["operating_labors"]["labors"] is None
        assert "not found" in out["operating_labors"]["unknown_reason"] and called == []
        assert not (tmp_path / "absent.sqlite3").exists()

    async def test_an_existing_graph_file_reaches_the_real_reader(self, tmp_path, monkeypatch):
        db = tmp_path / "g.sqlite3"
        db.write_bytes(b"")
        stub = Stub(c2())
        monkeypatch.setattr(lj, "_import_labors_for_kind", lambda: stub)
        out = await lj.LaborJoin(str(db), counter({"BREWER": 1})).join("Still", GOOD_REQ)
        assert stub.calls == [(str(db), "Still")] and out["operating_labors"]["status"] == "known"

    async def test_join_never_raises(self):
        class Weird:
            def __getitem__(self, k):
                raise RuntimeError("boom")

        out = await make(Stub(c2()), counter({"BREWER": 1})).join("Still", Weird())
        assert "operating_labors" in out


# --------------------------------------------------------------------------
# Requirements gaps (materials, containers)
# --------------------------------------------------------------------------


class TestRequirementGaps:
    async def test_no_building_material_at_all_is_a_gap_in_plain_words(self):
        req = {"building_material": {"accepts": ["BOULDER", "WOOD", "BLOCKS"],
                                     "fort_owned": {"BOULDER": 0, "WOOD": 0, "BLOCKS": 0}}}
        out = lj.requirement_gaps(req)
        assert out == {"gaps": ["no BOULDER, WOOD or BLOCKS in the fort to build with"], "gaps_unknown": []}

    async def test_any_one_material_present_is_no_gap(self):
        assert lj.requirement_gaps(GOOD_REQ) == {"gaps": [], "gaps_unknown": []}

    async def test_an_uncountable_material_is_unknown_never_missing(self):
        req = {"building_material": {
            "accepts": ["BOULDER", "WOOD"], "fort_owned": {"BOULDER": 0, "WOOD": None},
            "fort_owned_errors": {"WOOD": "lookup failed"},
        }}
        out = lj.requirement_gaps(req)
        assert out["gaps"] == []
        assert "lookup failed" in out["gaps_unknown"][0]

    async def test_requirements_unknown_is_unknown_not_no_gaps(self):
        out = lj.requirement_gaps("unknown")
        assert out["gaps"] == [] and "unknown for this kind" in out["gaps_unknown"][0]

    async def test_absent_or_wrong_shape_requirements_are_unknown(self):
        assert lj.requirement_gaps(None)["gaps_unknown"]
        assert lj.requirement_gaps(["x"])["gaps_unknown"]
        assert lj.requirement_gaps({"building_material": {"accepts": []}})["gaps_unknown"]
        assert lj.requirement_gaps({"building_material": "lots"})["gaps_unknown"]

    async def test_container_need(self):
        assert lj.requirement_gaps({"needs_container": "barrel", "fort_owned_containers": 0})["gaps"] == [
            "the fort owns no barrel"
        ]
        assert lj.requirement_gaps({"needs_container": "barrel", "fort_owned_containers": 2}) == {
            "gaps": [], "gaps_unknown": []
        }
        out = lj.requirement_gaps({"needs_container": "barrel", "fort_owned_containers": None,
                                   "fort_owned_containers_error": "bad type"})
        assert out["gaps"] == [] and "bad type" in out["gaps_unknown"][0]

    async def test_requirement_gaps_are_kept_even_when_the_labor_graph_is_unknown(self):
        req = {"building_material": {"accepts": ["BOULDER"], "fort_owned": {"BOULDER": 0}}}
        out = await make(Stub(c2(status="unknown", labors=[])), counter()).join("K", req)
        assert out["gaps"] == ["no BOULDER in the fort to build with"]
        assert out["operating_labors"]["labors"] is None


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


class TestRender:
    async def test_xml_carries_unknown_as_unknown(self):
        out = await make(Stub(c2(status="unknown", labors=[], reason="no data")), counter()).join("K", GOOD_REQ)
        xml = lj.render_xml(out)
        assert 'unknown="true"' in xml and "no data" in xml
        assert "<labor " not in xml

    async def test_xml_shows_counts_gaps_and_partial_caution(self):
        stub = Stub(c2(status="partial", labors=["A", "B"], reason="some jobs unmapped"))
        out = await make(stub, counter({"A": 0, "B": None}, errors={"B": "bad"})).join("K", GOOD_REQ)
        xml = lj.render_xml(out)
        assert 'name="A" citizens_with_labor="0"' in xml
        assert 'name="B" citizens_with_labor="unknown"' in xml
        assert "<gap>nobody has the A labor enabled</gap>" in xml
        assert "<caution>" in xml and "some jobs unmapped" in xml
