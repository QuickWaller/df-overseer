"""`dfmcp.gotchas_tools`: `gotchas.get` and `gotchas.write`, called directly
(no MCP transport, so this runs under the ambient interpreter), plus their
reachability through the real registry and roster boundary.

The through-the-wire version of the same behaviour is in
`test_gotchas_server.py`."""

from __future__ import annotations

import asyncio

import pytest

from dfmcp import gotchas_store as gs
from dfmcp import gotchas_tools as gt
from dfmcp.tests.gotchas_support import build_registry_and_roster
from dfmcp.tools import tool_definitions

KNOWN = ["building.build", "building.find", "landmarks.list", "gotchas.get", "gotchas.write"]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "g.sqlite3"
    gs.init_store(path)
    return path


def _lock():
    return asyncio.Lock()


async def _call(tool_id, arguments, db, *, role="architect", run_id="session-1", lock=None):
    return await gt.call(
        tool_id, role, arguments, db_path=db, known_tools=KNOWN, run_id=run_id,
        write_lock=lock or asyncio.Lock(),
    )


NEW = {
    "tool": "building.build",
    "title": "placing a workshop in a desert biome: the build stalls without water",
    "body": "In a desert the builder never gets a path to the site; pick a site near a landmark.",
}


# --------------------------------------------------------------------------
# Reachable through the real registry and roster
# --------------------------------------------------------------------------


class TestRegistryAndRoster:
    @pytest.fixture
    def rr(self, tmp_path):
        return build_registry_and_roster(tmp_path)

    def test_both_tools_are_in_the_registry_as_native_non_mutating(self, rr):
        registry, _ = rr
        for tool_id in gt.NATIVE_TOOL_IDS:
            tool = registry.get(tool_id)
            assert tool.native and not tool.mutates and not tool.sole_writer_only

    def test_roster_check_allows_a_granted_role_and_refuses_an_ungranted_one(self, rr):
        _, roster = rr
        assert roster.check("architect", "gotchas.write")[0]
        assert roster.check("overseer", "gotchas.get")[0]
        allowed, reason = roster.check("consultant", "gotchas.write")
        assert not allowed and reason  # consultant was not granted it in the test roster

    def test_tool_definitions_list_both_with_hand_written_schemas(self, rr):
        registry, roster = rr
        defs = {d["name"]: d for d in tool_definitions(registry, roster, "architect")}
        for name in ("gotchas__get", "gotchas__write"):
            assert name in defs
            assert defs[name]["inputSchema"]["additionalProperties"] is False
        props = defs["gotchas__write"]["inputSchema"]["properties"]
        # role, status and run are never arguments a caller can set.
        for forbidden in ("role", "status", "run_id", "written_by_role", "created_at"):
            assert forbidden not in props
        assert "id" in props and "result" in props


# --------------------------------------------------------------------------
# gotchas.write
# --------------------------------------------------------------------------


class TestWrite:
    pytestmark = pytest.mark.asyncio

    async def test_new_entry_gets_a_server_chosen_id_and_is_proposed(self, db):
        text, structured = await _call(gt.GOTCHAS_WRITE, dict(NEW), db)
        entry = structured["entry"]
        assert entry["id"] == "gotcha-0001" and entry["status"] == "proposed"
        assert entry["written_by_role"] == "architect" and entry["run_id"] == "session-1"
        assert structured["outcome_recorded"] is False
        assert 'status="proposed"' in text and "PROPOSED" in text

    async def test_list_defaults_to_gotcha_and_can_be_vent(self, db):
        _, s = await _call(gt.GOTCHAS_WRITE, dict(NEW), db)
        assert s["entry"]["list"] == "gotcha"
        _, s = await _call(
            gt.GOTCHAS_WRITE,
            {**NEW, "list": "vent", "title": "asking for a bedroom of any size: nothing builds rooms",
             "body": "No tool in my list builds a room, only single buildings and furniture."},
            db, run_id="session-2",
        )
        assert s["entry"]["id"] == "vent-0001"

    async def test_given_an_existing_id_it_appends_an_outcome_and_never_overwrites(self, db):
        _, s = await _call(gt.GOTCHAS_WRITE, dict(NEW), db)
        gid = s["entry"]["id"]
        text, s2 = await _call(
            gt.GOTCHAS_WRITE, {"id": gid, "result": "worked", "note": "site near the wagon"}, db,
            role="overseer", run_id="session-2",
        )
        assert s2["outcome_recorded"] is True
        assert s2["entry"]["title"] == NEW["title"] and s2["entry"]["body"] == NEW["body"]
        assert [o["result"] for o in s2["entry"]["outcomes"]] == ["worked"]
        assert s2["entry"]["outcomes"][0]["role"] == "overseer"
        _, s3 = await _call(
            gt.GOTCHAS_WRITE, {"id": gid, "result": "did_not_work"}, db, run_id="session-3"
        )
        assert [o["result"] for o in s3["entry"]["outcomes"]] == ["worked", "did_not_work"]
        # Still exactly one entry.
        assert len(gs.entries_for_tool(db, "building.build")) == 1

    async def test_outcome_on_an_unknown_id_or_the_wrong_tool_is_refused(self, db):
        with pytest.raises(gt.GotchaToolError, match="no entry"):
            await _call(gt.GOTCHAS_WRITE, {"id": "gotcha-0099", "result": "worked"}, db)
        _, s = await _call(gt.GOTCHAS_WRITE, dict(NEW), db)
        with pytest.raises(gt.GotchaToolError, match="is about 'building.build'"):
            await _call(
                gt.GOTCHAS_WRITE,
                {"id": s["entry"]["id"], "result": "worked", "tool": "building.find"}, db,
            )

    async def test_outcome_needs_a_result_and_cannot_mix_with_new_fields(self, db):
        _, s = await _call(gt.GOTCHAS_WRITE, dict(NEW), db)
        with pytest.raises(gt.GotchaToolError, match="needs 'result'"):
            await _call(gt.GOTCHAS_WRITE, {"id": s["entry"]["id"]}, db, run_id="s2")
        with pytest.raises(gt.GotchaToolError, match="cannot be combined"):
            await _call(
                gt.GOTCHAS_WRITE,
                {"id": s["entry"]["id"], "result": "worked", "title": "x: y"}, db, run_id="s2",
            )

    async def test_result_without_id_is_refused(self, db):
        with pytest.raises(gt.GotchaToolError, match="only apply when recording an outcome"):
            await _call(gt.GOTCHAS_WRITE, {**NEW, "result": "worked"}, db)

    async def test_new_entry_needs_tool_title_body(self, db):
        with pytest.raises(gt.GotchaToolError, match=r"needs \['title', 'body'\]"):
            await _call(gt.GOTCHAS_WRITE, {"tool": "building.build"}, db)

    async def test_role_id_status_and_run_cannot_be_supplied(self, db):
        for stray in ("role", "id_", "status", "run_id", "written_by_role", "created_at"):
            with pytest.raises(gt.GotchaToolError, match="unexpected argument"):
                await _call(gt.GOTCHAS_WRITE, {**NEW, stray: "x"}, db)
        assert gs.tool_index(db) == {}

    async def test_validation_refusals_reach_the_caller_and_write_nothing(self, db):
        cases = [
            ({**NEW, "tool": "no.such.tool"}, "registry"),
            ({**NEW, "title": "Masons workshop"}, "condition"),
            ({**NEW, "body": "x" * 5000}, "too long"),
            ({**NEW, "list": "rant"}, "list must be one of"),
        ]
        for args, fragment in cases:
            with pytest.raises(gt.GotchaToolError, match=fragment):
                await _call(gt.GOTCHAS_WRITE, args, db)
        assert gs.tool_index(db) == {}

    async def test_near_duplicate_and_per_run_cap(self, db):
        await _call(gt.GOTCHAS_WRITE, dict(NEW), db)
        with pytest.raises(gt.GotchaToolError, match="near-duplicate of gotcha-0001"):
            await _call(
                gt.GOTCHAS_WRITE,
                {**NEW, "title": "Placing a workshop in a desert biome: the build stalls without water."},
                db, run_id="session-9",
            )
        more = [
            ("queueing a mason job before any boulder exists: the job idles forever",
             "Nothing is cut until stone is dragged in from a mined-out stockpile."),
            ("asking for a trade depot in a cavern: the wagon path is blocked",
             "Merchants need a clear approach on the surface, cavern sites never qualify."),
        ]
        for title, body in more:
            await _call(gt.GOTCHAS_WRITE, {**NEW, "title": title, "body": body}, db)
        with pytest.raises(gt.GotchaToolError, match="per-run cap"):
            await _call(
                gt.GOTCHAS_WRITE,
                {**NEW, "title": "building a farm on bare rock: nothing can be planted there",
                 "body": "Only soil tiles take a crop, so check the tile material first."}, db,
            )

    async def test_store_problems_are_tool_errors(self, tmp_path):
        with pytest.raises(gt.GotchaToolError, match="not found"):
            await _call(gt.GOTCHAS_WRITE, dict(NEW), tmp_path / "absent.sqlite3")
        junk = tmp_path / "junk.sqlite3"
        junk.write_bytes(b"not sqlite" * 50)
        with pytest.raises(gt.GotchaToolError, match="malformed"):
            await _call(gt.GOTCHAS_WRITE, dict(NEW), junk)

    async def test_concurrent_writes_from_different_runs_get_distinct_ids(self, db):
        lock = _lock()
        titles = [
            "placing a still beside a drain: the barrel jobs never start",
            "queueing a mason job before any boulder exists: the job idles forever",
            "asking for a trade depot in a cavern: the wagon path is blocked",
        ]
        bodies = [
            "The still needs its own barrel supply before brewing begins in earnest.",
            "Nothing is cut until stone is dragged in from a mined-out stockpile.",
            "Merchants need a clear approach on the surface, cavern sites never qualify.",
        ]
        results = await asyncio.gather(*[
            _call(gt.GOTCHAS_WRITE, {**NEW, "title": t, "body": b}, db, run_id=f"session-{i}", lock=lock)
            for i, (t, b) in enumerate(zip(titles, bodies))
        ])
        ids = sorted(r[1]["entry"]["id"] for r in results)
        assert ids == ["gotcha-0001", "gotcha-0002", "gotcha-0003"]


# --------------------------------------------------------------------------
# gotchas.get
# --------------------------------------------------------------------------


class TestGet:
    pytestmark = pytest.mark.asyncio

    async def _seed(self, db):
        a = (await _call(gt.GOTCHAS_WRITE, dict(NEW), db))[1]["entry"]
        b = (await _call(
            gt.GOTCHAS_WRITE,
            {**NEW, "kind": "Masons", "title": "queueing blocks with no boulders on hand: the job idles",
             "body": "Blocks need a free boulder; mine one before queueing the job at all."},
            db, run_id="s2",
        ))[1]["entry"]
        await _call(gt.GOTCHAS_WRITE, {"id": a["id"], "result": "worked", "note": "ok"}, db, run_id="s3")
        return a, b

    async def test_by_id_returns_full_text_status_and_outcomes(self, db):
        a, _ = await self._seed(db)
        text, s = await _call(gt.GOTCHAS_GET, {"id": a["id"]}, db)
        assert s["entry"]["body"] == NEW["body"]
        assert s["entry"]["status"] == "proposed"
        assert s["entry"]["outcomes"][0]["result"] == "worked"
        assert NEW["body"] in text and 'worked="1"' in text

    async def test_by_tool_lists_all_entries_with_full_text(self, db):
        a, b = await self._seed(db)
        _, s = await _call(gt.GOTCHAS_GET, {"tool": "building.build"}, db)
        assert [e["id"] for e in s["entries"]] == [a["id"], b["id"]]
        assert s["returned_count"] == 2 and s["omitted_rejected_count"] == 0
        assert all(e["body"] for e in s["entries"])

    async def test_kind_narrows_but_keeps_tool_wide_entries(self, db):
        a, b = await self._seed(db)
        await _call(
            gt.GOTCHAS_WRITE,
            {**NEW, "kind": "Still", "title": "brewing at a still with no barrels: the job never starts",
             "body": "A still needs an empty barrel per brew; make barrels first at a carpenter."},
            db, run_id="s4",
        )
        _, s = await _call(gt.GOTCHAS_GET, {"tool": "building.build", "kind": "Masons"}, db)
        assert [e["id"] for e in s["entries"]] == [a["id"], b["id"]]

    async def test_an_unknown_tool_is_an_error_never_an_empty_list(self, db):
        with pytest.raises(gt.GotchaToolError, match="not a tool in this server's registry"):
            await _call(gt.GOTCHAS_GET, {"tool": "no.such.tool"}, db)

    async def test_a_real_tool_with_no_entries_is_an_empty_list_that_says_so(self, db):
        text, s = await _call(gt.GOTCHAS_GET, {"tool": "landmarks.list"}, db)
        assert s["entries"] == [] and s["returned_count"] == 0
        assert "real tool and has no matching entries" in text

    async def test_unknown_id_is_an_error(self, db):
        with pytest.raises(gt.GotchaToolError, match="no entry with id"):
            await _call(gt.GOTCHAS_GET, {"id": "gotcha-0042"}, db)

    async def test_rejected_are_omitted_by_default_with_a_count_and_shown_on_request(self, db):
        a, b = await self._seed(db)
        gs.set_status(db, b["id"], "rejected", by="maintainer")
        text, s = await _call(gt.GOTCHAS_GET, {"tool": "building.build"}, db)
        assert [e["id"] for e in s["entries"]] == [a["id"]]
        assert s["omitted_rejected_count"] == 1 and 'omitted_rejected="1"' in text
        _, s = await _call(gt.GOTCHAS_GET, {"tool": "building.build", "include_rejected": True}, db)
        assert len(s["entries"]) == 2 and s["omitted_rejected_count"] == 0
        # By id, a rejected entry is always returned, flagged.
        text, s = await _call(gt.GOTCHAS_GET, {"id": b["id"]}, db)
        assert s["entry"]["status"] == "rejected" and "REJECTED" in text

    async def test_index_lists_only_tools_with_entries_and_says_so(self, db):
        await self._seed(db)
        text, s = await _call(gt.GOTCHAS_GET, {}, db)
        assert s["tools"] == {"building.build": {"gotcha": {"proposed": 2}}}
        assert "only tools with at least one entry are listed" in text

    async def test_argument_rules(self, db):
        a, _ = await self._seed(db)
        with pytest.raises(gt.GotchaToolError, match="cannot be combined"):
            await _call(gt.GOTCHAS_GET, {"id": a["id"], "tool": "building.build"}, db)
        with pytest.raises(gt.GotchaToolError, match="need 'tool'"):
            await _call(gt.GOTCHAS_GET, {"kind": "Masons"}, db)
        with pytest.raises(gt.GotchaToolError, match="unexpected argument"):
            await _call(gt.GOTCHAS_GET, {"role": "overseer"}, db)
        with pytest.raises(gt.GotchaToolError, match="'list' must be one of"):
            await _call(gt.GOTCHAS_GET, {"tool": "building.build", "list": "x"}, db)

    async def test_text_is_xml_escaped(self, db):
        await _call(
            gt.GOTCHAS_WRITE,
            {**NEW, "body": "The site is <b>bad</b> & the wagon never arrives; pick another one."}, db,
        )
        text, _ = await _call(gt.GOTCHAS_GET, {"id": "gotcha-0001"}, db)
        assert "&lt;b&gt;bad&lt;/b&gt; &amp;" in text and "<b>" not in text

    async def test_absent_store_is_an_error_not_an_empty_answer(self, tmp_path):
        with pytest.raises(gt.GotchaToolError, match="not found"):
            await _call(gt.GOTCHAS_GET, {"tool": "building.build"}, tmp_path / "absent.sqlite3")
