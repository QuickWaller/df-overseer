"""The labor join over the real wire, on the building tool's real result shapes.

The same harness `test_gotchas_server.py` uses: the actual MCP SDK client
against the in-process ASGI app, the repo's real registry and roster, and a fake
DFHack that serves the tool's output as bytes. Fixtures are `building_shapes.py`
(the Lua tool's field names). What this proves that `test_labor_join_real_shapes`
cannot: the array result survives the server's `{"result": [...]}` wrapping, the
Well gap reaches an agent through a real `call_tool`, and the tool's own first
text block is untouched. Skipped, like its sibling, where the pinned SDK is not
importable (the ambient interpreter); it runs in `.venv-dfmcp`.
"""

from __future__ import annotations

import pytest

from dfmcp.tests import building_shapes as bs
from dfmcp.tests.test_gotchas_server import (  # noqa: F401 -- fixtures are used by name
    ARCHITECT_TOKEN,
    OVERSEER_TOKEN,
    _encode_run_command_request,
    c2_stub,
    fake_dfhack,
    gdb,
    make_app,
    make_ok_action,
    mcp_session,
    pool,
    rr,
    texts,
)

pytestmark = pytest.mark.asyncio

DB = "/graph.sqlite3"
NO_REQ_BLOCK = "the result carried no requirements block"


class TestOverTheWire:
    async def test_the_well_gap_reaches_the_agent(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(
            make_ok_action(bs.as_wire(bs.well_find())),
            make_ok_action('{"counts": {"BREWER": 3}, "errors": {}}'),
        )
        stub = c2_stub(labors=("BREWER",))
        app = make_app(rr, pool, tmp_path, gdb, production_db=DB, labors_for_kind=stub)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("building__find", {"kind": "Well", "near_landmark": "Embark Site"})
        assert result.is_error is False
        sc = result.structured_content
        assert sc["gaps"] == [bs.WELL_GAP]
        assert NO_REQ_BLOCK not in sc["gaps_unknown"]
        assert len(sc["result"]) == 5 and sc["result"][0]["gaps"] == [bs.WELL_GAP]
        assert stub.calls == [(DB, "Well")]  # the kind was read from the candidates
        body = texts(result)
        assert body[0] == bs.as_wire(bs.well_find())  # the tool's own first block is untouched
        assert f"<gap>{bs.WELL_GAP}</gap>" in body[1]

    async def test_masons_find_is_clear_and_reads_no_unknown_requirements(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(
            make_ok_action(bs.as_wire(bs.masons_find())),
            make_ok_action('{"counts": {"BREWER": 2}, "errors": {}}'),
        )
        app = make_app(rr, pool, tmp_path, gdb, production_db=DB, labors_for_kind=c2_stub(labors=("BREWER",)))
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("building__find", {"kind": "Masons", "near_landmark": "Embark Site"})
        sc = result.structured_content
        assert sc["gaps"] == [] and sc["gaps_unknown"] == []

    async def test_bed_find_and_farmplot_find(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(
            make_ok_action(bs.as_wire(bs.bed_find())),
            make_ok_action('{"counts": {"BREWER": 2}, "errors": {}}'),
            make_ok_action(bs.as_wire(bs.farm_find())),
            make_ok_action('{"counts": {"BREWER": 2}, "errors": {}}'),
        )
        app = make_app(rr, pool, tmp_path, gdb, production_db=DB, labors_for_kind=c2_stub(labors=("BREWER",)))
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            bed = await session.call_tool("building__find", {"kind": "Bed", "near_landmark": "Embark Site"})
            farm = await session.call_tool("building__find", {"kind": "FarmPlot", "w": 5, "h": 5, "near_landmark": "Embark Site"})
        assert bed.structured_content["gaps"] == [bs.BED_GAP]
        assert farm.structured_content["gaps"] == [] and farm.structured_content["gaps_unknown"] == []

    async def test_an_unknown_graph_answer_keeps_the_well_gap_and_says_unknown(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(make_ok_action(bs.as_wire(bs.well_find())))
        stub = c2_stub(status="unknown", labors=[], reason="the graph has no record of a workshop or furnace kind 'Well'")
        app = make_app(rr, pool, tmp_path, gdb, production_db=DB, labors_for_kind=stub)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("building__find", {"kind": "Well", "near_landmark": "Embark Site"})
        sc = result.structured_content
        assert sc["gaps"] == [bs.WELL_GAP]
        assert sc["operating_labors"]["labors"] is None
        assert any("operating labors are unknown" in u for u in sc["gaps_unknown"])
        assert len(fake_dfhack.received_requests) == 1

    async def test_the_overseers_bed_dry_run_keeps_the_gap_and_reads_filters(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(
            make_ok_action(bs.as_wire(bs.bed_build())),
            make_ok_action('{"counts": {"BREWER": 0}, "errors": {}}'),
        )
        app = make_app(rr, pool, tmp_path, gdb, production_db=DB, labors_for_kind=c2_stub(labors=("BREWER",)))
        async with mcp_session(app, OVERSEER_TOKEN) as session:
            result = await session.call_tool("building__build", {"kind": "Bed", "near_landmark": "Embark Site"})
        assert result.is_error is False
        sc = result.structured_content
        assert sc["gaps"] == [bs.BED_GAP, "nobody has the BREWER labor enabled"]
        assert not any("not in a shape" in u for u in sc["gaps_unknown"])
        assert sc["validation"]["ok"] is True and sc["dry_run"] is True
        assert fake_dfhack.received_requests[0] == _encode_run_command_request(
            "df-overseer-building", ["build", "Bed", "Embark Site"]
        )
