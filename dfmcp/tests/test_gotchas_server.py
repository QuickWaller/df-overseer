"""The gotcha tools, the enrichment and the labor join, over the real MCP
transport: the actual SDK client against the in-process ASGI app, exactly the
harness `test_server.py` uses (its fixtures and helpers are reused).

What this file proves that the transport-free tests cannot:

- an **array** result (the trap in `docs/TRAPS.md`: `structuredContent` must be
  an object) and an **error** result both survive enrichment through the SDK's
  own serialisation, and the tool's own first text block is untouched;
- `gotchas.write` / `gotchas.get` are reachable through the real
  `Roster.check` boundary, stamp role and run from the connection rather than
  from arguments, and refuse a stray `role`;
- the whole loop: an agent writes a proposed gotcha over the wire, the next
  result of that tool carries its title and the standing addendum, and an
  outcome recorded over the wire shows up as a count;
- the labor join on the building tool's result, with the graph function
  stubbed to contract C2 and `labor.enabled-counts` served by the fake DFHack.

The registry and roster are the repo's real ones plus the grants and the
building tool ids the orchestrator has not added yet, in a temp copy
(`gotchas_support.py`), so nothing here edits `TOOLS.yaml` or `agents/`.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

try:
    from dfmcp.server import ServerConfig, build_asgi_app, build_mcp_server, config_from_env
except ImportError as _import_error:  # pragma: no cover -- only in an unpinned environment
    pytest.skip(
        f"needs the mcp 2.x line (dfmcp/requirements.txt); not importable here ({_import_error})",
        allow_module_level=True,
    )

from dfmcp import gotchas_store as gs
from dfmcp.confidence import load_confidence, parse_confidence
from dfmcp.dfhack_client import _encode_run_command_request
from dfmcp.tests.gotchas_support import build_registry_and_roster
from dfmcp.tests.test_dfhack_client import make_fail_action
from dfmcp.tests.test_dfhack_client import make_ok_action as _make_ok_action
from dfmcp.tests.test_server import (  # noqa: F401 -- fixtures are used by name
    _BIND_HOST,
    ARCHITECT_TOKEN,
    OVERSEER_TOKEN,
    TOKENS,
    fake_dfhack,
    mcp_session,
    pool,
)

pytestmark = pytest.mark.asyncio


def make_ok_action(text):
    """`FakeDFHackServer` packs each text fragment behind a one-byte length, so a
    payload over 255 bytes must be split into several fragments (the client
    joins them, as it does for real multi-fragment output)."""
    return _make_ok_action(*[text[i:i + 100] for i in range(0, len(text), 100)])


TITLE = "placing a workshop in a desert biome: the build stalls without water"
BODY = "In a desert the builder never gets a path to the site; pick a site near a landmark."

# A real-shaped bare array, as `df-overseer-landmarks.lua list` prints it.
LANDMARKS_ARRAY = (
    '[{"name": "Wagon", "exits": [{"direction": "E", "distance_tiles": 1, '
    '"to": "Embark Site", "walkable": true}]}]'
)


@pytest.fixture
def rr(tmp_path):
    return build_registry_and_roster(tmp_path)


@pytest.fixture
def gdb(tmp_path):
    path = tmp_path / "gotchas.sqlite3"
    gs.init_store(path)
    return path


def make_app(rr, pool, tmp_path, gdb, *, confidence="default", production_db=None, labors_for_kind=None):
    registry, roster = rr
    if confidence == "default":
        confidence = load_confidence()
    server = build_mcp_server(
        registry, roster, pool, Path(tempfile.mkdtemp()) / "q.sqlite3",
        gotchas_db_path=str(gdb), confidence=confidence,
        production_db_path=production_db, labors_for_kind=labors_for_kind,
    )
    return build_asgi_app(server, TOKENS, bind_host=_BIND_HOST)


def texts(result):
    return [b.text for b in result.content if b.type == "text"]


# --------------------------------------------------------------------------
# Enrichment: object, array, error, and what is left alone
# --------------------------------------------------------------------------


class TestEnrichmentOverTheWire:
    async def test_object_result(self, rr, pool, fake_dfhack, tmp_path, gdb):
        raw = '{"candidates": [{"score": 7, "x": 10, "y": 20, "z": 1}]}'
        fake_dfhack.queue_actions(make_ok_action(raw))
        app = make_app(rr, pool, tmp_path, gdb)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("openarea__find", {"w": 4, "h": 5, "near_landmark": "MainHall"})
        assert result.is_error is False
        sc = result.structured_content
        assert sc["candidates"] == [{"score": 7, "x": 10, "y": 20, "z": 1}]
        assert sc["tool_guidance"]["confidence"] == "medium"
        assert sc["tool_guidance"]["confidence_note"]
        t = texts(result)
        assert t[0] == raw  # the tool's own block is untouched
        assert t[1].startswith("<tool_guidance") and 'confidence="medium"' in t[1]

    async def test_array_result_survives_the_trap(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(make_ok_action(LANDMARKS_ARRAY))
        app = make_app(rr, pool, tmp_path, gdb)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("landmarks__list", {})
        # A protocol-level error would have raised in the client above; it did not.
        assert result.is_error is False
        sc = result.structured_content
        assert isinstance(sc["result"], list) and sc["result"][0]["name"] == "Wagon"
        assert sc["tool_guidance"]["confidence"] == "medium"
        t = texts(result)
        assert json.loads(t[0]) == json.loads(LANDMARKS_ARRAY)
        assert t[1].startswith("<tool_guidance")

    async def test_script_error_result(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(make_ok_action('{"error": "landmark not found: Nowhere"}'))
        app = make_app(rr, pool, tmp_path, gdb)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("landmarks__get", {"name": "Nowhere"})
        assert result.is_error is True
        t = texts(result)
        assert t[0] == "landmark not found: Nowhere"
        assert result.structured_content["tool_guidance"]["confidence"] == "medium"
        assert t[1].startswith("<tool_guidance")

    async def test_argument_error_and_dfhack_failure_are_enriched_too(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(make_fail_action(1))
        app = make_app(rr, pool, tmp_path, gdb)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            bad_args = await session.call_tool("openarea__find", {"w": 4})  # missing required args
            failed = await session.call_tool("landmarks__list", {})
        for r in (bad_args, failed):
            assert r.is_error is True
            assert r.structured_content["tool_guidance"]["confidence"] == "medium"

    async def test_a_roster_denial_is_not_enriched(self, rr, pool, tmp_path, gdb):
        app = make_app(rr, pool, tmp_path, gdb)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("openarea__build", {"w": 4, "h": 5, "near_landmark": "MainHall", "blueprint_file": "x.csv"})
        assert result.is_error is True
        assert result.structured_content is None and len(texts(result)) == 1

    async def test_native_tool_results_are_not_enriched(self, rr, pool, tmp_path, gdb):
        app = make_app(rr, pool, tmp_path, gdb)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("gotchas__get", {})
        assert "tool_guidance" not in (result.structured_content or {})

    async def test_confidence_off_leaves_results_untouched(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(make_ok_action(LANDMARKS_ARRAY))
        app = make_app(rr, pool, tmp_path, gdb, confidence=None)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("landmarks__list", {})
        assert list(result.structured_content) == ["result"] and len(texts(result)) == 1

    async def test_an_unreadable_store_is_said_and_the_result_still_arrives(self, rr, pool, fake_dfhack, tmp_path):
        fake_dfhack.queue_actions(make_ok_action(LANDMARKS_ARRAY))
        app = make_app(rr, pool, tmp_path, tmp_path / "absent.sqlite3")
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("landmarks__list", {})
        assert result.is_error is False
        g = result.structured_content["tool_guidance"]
        assert "not found" in g["gotchas_unavailable"] and "gotchas" not in g
        assert result.structured_content["result"][0]["name"] == "Wagon"

    async def test_the_kind_level_comes_from_the_confidence_file(self, rr, pool, fake_dfhack, tmp_path, gdb):
        cfg = parse_confidence({"default": "medium", "tools": {
            "building.find": {"level": "medium", "kinds": {"Masons": "full"}}}})
        fake_dfhack.queue_actions(make_ok_action(
            '{"kind": {"token": "Masons", "label": "Mason", "type": "Workshop", "subtype": "Masons"},'
            ' "dims": [3, 3], "dry_run": true, "requirements": "unknown"}'
        ))
        app = make_app(rr, pool, tmp_path, gdb, confidence=cfg)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("building__find", {"kind": "Masons", "near_landmark": "Wagon"})
        assert result.structured_content["tool_guidance"]["confidence"] == "full"
        assert fake_dfhack.received_requests[0] == _encode_run_command_request(
            "df-overseer-building", ["find", "Masons", "Wagon"]
        )


# --------------------------------------------------------------------------
# The gotcha tools and the full loop
# --------------------------------------------------------------------------


class TestGotchaLoop:
    async def test_both_tools_are_listed_and_callable_through_the_roster(self, rr, pool, tmp_path, gdb):
        app = make_app(rr, pool, tmp_path, gdb)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            names = {t.name for t in (await session.list_tools()).tools}
        assert {"gotchas__get", "gotchas__write"} <= names

    async def test_write_stamps_role_and_run_from_the_connection(self, rr, pool, tmp_path, gdb):
        app = make_app(rr, pool, tmp_path, gdb)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool(
                "gotchas__write", {"tool": "landmarks.list", "title": TITLE, "body": BODY}
            )
        assert result.is_error is False
        entry = result.structured_content["entry"]
        assert entry["id"] == "gotcha-0001" and entry["status"] == "proposed"
        assert entry["written_by_role"] == "architect"
        assert entry["run_id"].startswith("session-")
        stored = gs.get_entry(gdb, "gotcha-0001")
        assert stored["written_by_role"] == "architect" and stored["run_id"] == entry["run_id"]

    async def test_a_supplied_role_or_status_is_refused_and_nothing_is_written(self, rr, pool, tmp_path, gdb):
        app = make_app(rr, pool, tmp_path, gdb)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            for stray in ("role", "status", "run_id"):
                r = await session.call_tool(
                    "gotchas__write",
                    {"tool": "landmarks.list", "title": TITLE, "body": BODY, stray: "overseer"},
                )
                assert r.is_error is True and "unexpected argument" in texts(r)[0]
        assert gs.tool_index(gdb) == {}

    async def test_validation_refusals_are_tool_errors(self, rr, pool, tmp_path, gdb):
        app = make_app(rr, pool, tmp_path, gdb)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            r = await session.call_tool(
                "gotchas__write", {"tool": "landmarks.list", "title": "Masons", "body": BODY}
            )
            assert r.is_error is True and "condition" in texts(r)[0]
            r = await session.call_tool(
                "gotchas__write", {"tool": "no.such", "title": TITLE, "body": BODY}
            )
            assert r.is_error is True and "registry" in texts(r)[0]
            r = await session.call_tool("gotchas__get", {"tool": "no.such"})
            assert r.is_error is True and "not a tool in this server's registry" in texts(r)[0]

    async def test_per_run_cap_is_per_session(self, rr, pool, tmp_path, gdb):
        app = make_app(rr, pool, tmp_path, gdb)
        entries = [
            ("placing a still beside a drain: the barrel jobs never start",
             "The still needs its own barrel supply before brewing begins in earnest."),
            ("queueing a mason job before any boulder exists: the job idles forever",
             "Nothing is cut until stone is dragged in from a mined-out stockpile."),
            ("asking for a trade depot in a cavern: the wagon path is blocked",
             "Merchants need a clear approach on the surface, cavern sites never qualify."),
            ("building a farm on bare rock: nothing can be planted there",
             "Only soil tiles take a crop, so check the tile material before placing a plot."),
        ]
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            for title, body in entries[:3]:
                r = await session.call_tool("gotchas__write", {"tool": "landmarks.list", "title": title, "body": body})
                assert r.is_error is False
            r = await session.call_tool(
                "gotchas__write", {"tool": "landmarks.list", "title": entries[3][0], "body": entries[3][1]}
            )
            assert r.is_error is True and "per-run cap" in texts(r)[0]
        # A new session is a new run.
        async with mcp_session(make_app(rr, pool, tmp_path, gdb), ARCHITECT_TOKEN) as session:
            r = await session.call_tool(
                "gotchas__write", {"tool": "landmarks.list", "title": entries[3][0], "body": entries[3][1]}
            )
            assert r.is_error is False

    async def test_the_full_loop_write_then_see_the_title_then_mark_the_outcome(
        self, rr, pool, fake_dfhack, tmp_path, gdb
    ):
        # 1. The architect writes a gotcha about a tool.
        async with mcp_session(make_app(rr, pool, tmp_path, gdb), ARCHITECT_TOKEN) as session:
            w = await session.call_tool("gotchas__write", {"tool": "landmarks.list", "title": TITLE, "body": BODY})
        gid = w.structured_content["entry"]["id"]

        # 2. A later run's result of that tool carries the title, not the body.
        fake_dfhack.queue_actions(make_ok_action(LANDMARKS_ARRAY))
        async with mcp_session(make_app(rr, pool, tmp_path, gdb), OVERSEER_TOKEN) as session:
            r = await session.call_tool("landmarks__list", {})
            g = r.structured_content["tool_guidance"]
            assert g["gotchas"] == [{
                "id": gid, "title": TITLE, "status": "proposed",
                "outcomes": {"worked": 0, "did_not_work": 0},
            }]
            assert g["gotcha_addendum"]
            assert BODY not in json.dumps(r.structured_content) and BODY not in "".join(texts(r))
            assert f'id="{gid}"' in texts(r)[1] and "<addendum>" in texts(r)[1]

            # 3. It expands the gotcha, tries it, and marks the outcome.
            full = await session.call_tool("gotchas__get", {"id": gid})
            assert full.structured_content["entry"]["body"] == BODY
            out = await session.call_tool("gotchas__write", {"id": gid, "result": "worked", "note": "site by the wagon"})
            assert out.is_error is False and out.structured_content["outcome_recorded"] is True
            again = await session.call_tool("gotchas__write", {"id": gid, "result": "did_not_work"})
            assert again.is_error is True and "already recorded" in texts(again)[0]

        # 4. The next result shows the recorded outcome as a count.
        fake_dfhack.queue_actions(make_ok_action(LANDMARKS_ARRAY))
        async with mcp_session(make_app(rr, pool, tmp_path, gdb), ARCHITECT_TOKEN) as session:
            r = await session.call_tool("landmarks__list", {})
        assert r.structured_content["tool_guidance"]["gotchas"][0]["outcomes"] == {"worked": 1, "did_not_work": 0}


# --------------------------------------------------------------------------
# The labor join over the wire
# --------------------------------------------------------------------------

BUILD_RESULT = (
    '{"kind": {"token": "Still", "label": "Still", "type": "Workshop", "subtype": "Still"},'
    ' "dims": [3, 3], "site": {"rank": 1, "near_landmark": "Wagon", "direction": "E", "distance_tiles": 4},'
    ' "dry_run": true, "requirements": {"building_material": {"accepts": ["BOULDER", "WOOD", "BLOCKS"],'
    ' "fort_owned": {"BOULDER": 0, "WOOD": 0, "BLOCKS": 0}}}}'
)


def c2_stub(status="known", labors=("BREWER",), reason=None):
    calls = []

    def fn(db_path, kind_token):
        calls.append((db_path, kind_token))
        return {"kind": kind_token, "labors": list(labors), "status": status, "processes": [], "unknown_reason": reason}

    fn.calls = calls
    return fn


class TestLaborJoinOverTheWire:
    async def test_known_labors_counts_and_gaps_reach_the_agent(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(
            make_ok_action(BUILD_RESULT),
            make_ok_action('{"counts": {"BREWER": 0}, "errors": {}}'),
        )
        stub = c2_stub()
        app = make_app(rr, pool, tmp_path, gdb, production_db="/graph.sqlite3", labors_for_kind=stub)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("building__find", {"kind": "Still", "near_landmark": "Wagon"})
        assert result.is_error is False
        sc = result.structured_content
        assert stub.calls == [("/graph.sqlite3", "Still")]
        assert sc["operating_labors"]["labors"] == ["BREWER"]
        assert sc["operating_labors"]["citizens_with_labor"] == {"BREWER": 0}
        assert "nobody has the BREWER labor enabled" in sc["gaps"]
        assert "no BOULDER, WOOD or BLOCKS in the fort to build with" in sc["gaps"]
        assert sc["gaps_unknown"] == []
        # The Lua tool's own facts are all still there.
        assert sc["dims"] == [3, 3] and sc["kind"]["token"] == "Still"
        # The count went out as the server's own labor read, after the tool call.
        assert fake_dfhack.received_requests[1] == _encode_run_command_request(
            "df-overseer-labor", ["enabled-counts", "BREWER"]
        )
        t = texts(result)
        assert t[0] == BUILD_RESULT and t[1].startswith("<operating_context") and t[2].startswith("<tool_guidance")

    async def test_the_overseers_mutating_build_is_joined_too(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(
            make_ok_action(BUILD_RESULT), make_ok_action('{"counts": {"BREWER": 2}, "errors": {}}')
        )
        app = make_app(rr, pool, tmp_path, gdb, production_db="/g", labors_for_kind=c2_stub())
        async with mcp_session(app, OVERSEER_TOKEN) as session:
            result = await session.call_tool("building__build", {"kind": "Still", "near_landmark": "Wagon"})
        assert result.is_error is False
        assert result.structured_content["operating_labors"]["citizens_with_labor"] == {"BREWER": 2}

    async def test_an_unknown_graph_answer_is_null_not_an_empty_list(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(make_ok_action(BUILD_RESULT))
        stub = c2_stub(status="unknown", labors=[], reason="the kind hosts no process in the graph")
        app = make_app(rr, pool, tmp_path, gdb, production_db="/g", labors_for_kind=stub)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("building__find", {"kind": "Still", "near_landmark": "Wagon"})
        sc = result.structured_content
        assert sc["operating_labors"]["status"] == "unknown"
        assert sc["operating_labors"]["labors"] is None
        assert sc["operating_labors"]["unknown_reason"] == "the kind hosts no process in the graph"
        assert any("operating labors are unknown" in u for u in sc["gaps_unknown"])
        assert len(fake_dfhack.received_requests) == 1  # nothing to count, so no labor read

    async def test_a_failed_count_read_is_unknown_never_zero(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(make_ok_action(BUILD_RESULT), make_fail_action(1))
        app = make_app(rr, pool, tmp_path, gdb, production_db="/g", labors_for_kind=c2_stub())
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("building__find", {"kind": "Still", "near_landmark": "Wagon"})
        op = result.structured_content["operating_labors"]
        assert result.is_error is False
        assert op["citizens_with_labor"] == {"BREWER": None}
        assert "nobody has the BREWER labor enabled" not in result.structured_content["gaps"]
        assert any("could not count citizens with the BREWER labor" in u for u in result.structured_content["gaps_unknown"])

    async def test_a_null_count_from_the_lua_read_stays_null(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(
            make_ok_action(BUILD_RESULT),
            make_ok_action('{"counts": {"BREWER": null}, "errors": {"BREWER": "unknown labor token"}}'),
        )
        app = make_app(rr, pool, tmp_path, gdb, production_db="/g", labors_for_kind=c2_stub())
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("building__find", {"kind": "Still", "near_landmark": "Wagon"})
        op = result.structured_content["operating_labors"]
        assert op["citizens_with_labor"] == {"BREWER": None}
        assert op["citizens_with_labor_errors"] == {"BREWER": "unknown labor token"}

    async def test_an_absent_graph_is_unknown_and_never_fails_the_call(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(make_ok_action(BUILD_RESULT))
        # No injected function: the real production.labors, absent or pointed at a missing file.
        app = make_app(rr, pool, tmp_path, gdb, production_db=str(tmp_path / "no-graph.sqlite3"))
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("building__find", {"kind": "Still", "near_landmark": "Wagon"})
        assert result.is_error is False
        op = result.structured_content["operating_labors"]
        assert op["status"] == "unknown" and op["labors"] is None and op["unknown_reason"]
        assert result.structured_content["dims"] == [3, 3]

    async def test_other_tools_are_not_joined(self, rr, pool, fake_dfhack, tmp_path, gdb):
        fake_dfhack.queue_actions(make_ok_action(LANDMARKS_ARRAY))
        stub = c2_stub()
        app = make_app(rr, pool, tmp_path, gdb, production_db="/g", labors_for_kind=stub)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("landmarks__list", {})
        assert "operating_labors" not in result.structured_content and stub.calls == []


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------


class TestConfig:
    async def test_new_paths_have_absolute_out_of_tree_defaults_and_are_overridable(self):
        cfg = config_from_env({"MCP_SERVER_BIND_HOST": "100.64.0.5", "MCP_SERVER_QUEUE_DB": "/q"})
        assert cfg.gotchas_db.startswith("/var/lib/") and cfg.production_db.startswith("/var/lib/")
        assert cfg.confidence_path.endswith("confidence.yaml")
        cfg = config_from_env({
            "MCP_SERVER_BIND_HOST": "100.64.0.5", "MCP_SERVER_QUEUE_DB": "/q",
            "MCP_SERVER_GOTCHAS_DB": "/g.sqlite3", "MCP_SERVER_PRODUCTION_DB": "/p.sqlite3",
            "MCP_SERVER_CONFIDENCE_PATH": "/c.yaml",
        })
        assert (cfg.gotchas_db, cfg.production_db, cfg.confidence_path) == ("/g.sqlite3", "/p.sqlite3", "/c.yaml")
