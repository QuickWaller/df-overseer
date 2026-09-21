"""`dfmcp.tool_guidance`: the confidence level and gotcha titles every
DFHack-backed result carries (contract C3), and where the labor join attaches.

Transport-free: `enrich` takes the plain `structured` value the server would
return, so the array-output trap (`docs/TRAPS.md`) is tested here on the exact
shapes the server produces (`{"result": [...]}` for an array, None for an
error), and again over the real wire in `test_gotchas_server.py`."""

from __future__ import annotations

import pytest
import yaml

from dfmcp import gotchas_store as gs
from dfmcp import labor_join as lj
from dfmcp import tool_guidance as tg
from dfmcp.confidence import parse_confidence

pytestmark = pytest.mark.asyncio

TOOLS = {"landmarks.list", "building.build", "building.find", "openarea.find"}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "g.sqlite3"
    gs.init_store(path)
    return path


def add(db, tool="landmarks.list", *, kind=None, title, body=None, list_="gotcha", run="r1"):
    return gs.add_entry(
        db,
        {"tool": tool, "kind": kind, "list": list_, "title": title,
         "body": body or f"Body text for {title}, long enough to be valid.",
         "written_by_role": "architect", "run_id": run},
        known_tools=TOOLS, max_new_per_run=100,
    )


def guidance_for(db, cfg=None, **kw):
    cfg = cfg or parse_confidence({"default": "medium", "tools": {}})
    return tg.ToolGuidance(cfg, db, **kw)


async def enrich_obj(g, tool="landmarks.list", args=None, structured=None, is_error=False, **kw):
    return await tg.enrich(tool, args or {}, structured, is_error, guidance=g, labor_join=kw.get("labor_join"))


# --------------------------------------------------------------------------
# Shapes: object, array, error
# --------------------------------------------------------------------------


class TestResultShapes:
    async def test_object_result_keeps_its_keys_and_gains_one_sibling(self, db):
        out, blocks = await enrich_obj(guidance_for(db), structured={"candidates": [1, 2]})
        assert out["candidates"] == [1, 2]
        assert set(out) == {"candidates", "tool_guidance"}
        assert out["tool_guidance"]["confidence"] == "medium"
        assert out["tool_guidance"]["confidence_note"]
        assert len(blocks) == 1 and blocks[0].startswith("<tool_guidance")

    async def test_array_result_keeps_the_wrapped_array_intact_beside_the_guidance(self, db):
        """The array-output trap: the server wraps a bare array as
        {"result": [...]}. Enrichment goes beside `result`, never into it."""
        wrapped = {"result": [{"name": "Wagon"}, {"name": "Well"}]}
        out, _ = await enrich_obj(guidance_for(db), structured=wrapped)
        assert out["result"] == [{"name": "Wagon"}, {"name": "Well"}]
        assert isinstance(out["result"], list)
        assert out["tool_guidance"]["confidence"] == "medium"
        assert wrapped == {"result": [{"name": "Wagon"}, {"name": "Well"}]}  # input not mutated

    async def test_error_result_with_no_structured_content_gets_an_object(self, db):
        out, blocks = await enrich_obj(guidance_for(db), structured=None, is_error=True)
        assert isinstance(out, dict) and set(out) == {"tool_guidance"}
        assert blocks and "confidence=" in blocks[0]

    async def test_error_results_never_get_the_labor_join(self, db):
        joiner = lj.LaborJoin("/x", None, labors_for_kind=lambda *a: 1 / 0)
        out, blocks = await tg.enrich(
            "building.build", {"kind": "Still"}, None, True,
            guidance=guidance_for(db), labor_join=joiner,
        )
        assert set(out) == {"tool_guidance"} and len(blocks) == 1

    async def test_a_scalar_wrapped_result_is_fine(self, db):
        out, _ = await enrich_obj(guidance_for(db), structured={"result": 3})
        assert out["result"] == 3 and "tool_guidance" in out

    async def test_empty_output_gets_guidance(self, db):
        out, blocks = await enrich_obj(guidance_for(db), structured=None, is_error=False)
        assert set(out) == {"tool_guidance"} and blocks

    async def test_nothing_configured_is_a_no_op(self):
        structured = {"a": 1}
        out, blocks = await tg.enrich("x.y", {}, structured, False, guidance=None, labor_join=None)
        assert out is structured and blocks == []


# --------------------------------------------------------------------------
# Confidence and kind
# --------------------------------------------------------------------------


class TestConfidence:
    async def test_level_is_per_tool_and_per_kind(self, db):
        cfg = parse_confidence(yaml.safe_load("""
default: medium
tools:
  building.build:
    level: low
    kinds: {Masons: full}
"""))
        g = guidance_for(db, cfg)
        out, _ = await tg.enrich("building.build", {}, {"kind": {"token": "Masons"}}, False, guidance=g, labor_join=None)
        assert out["tool_guidance"]["confidence"] == "full"
        out, _ = await tg.enrich("building.build", {"kind": "Kennel"}, {"ok": 1}, False, guidance=g, labor_join=None)
        assert out["tool_guidance"]["confidence"] == "low"
        out, _ = await tg.enrich("landmarks.list", {}, {"ok": 1}, False, guidance=g, labor_join=None)
        assert out["tool_guidance"]["confidence"] == "medium"

    async def test_the_kind_comes_from_the_result_first_then_the_argument(self):
        assert tg._kind_token({"kind": "Args"}, {"kind": {"token": "FromResult"}}) == "FromResult"
        assert tg._kind_token({"kind": "Args"}, {"result": []}) == "Args"
        assert tg._kind_token({}, None) is None
        assert tg._kind_token({"kind": 5}, {"kind": "notadict"}) is None


# --------------------------------------------------------------------------
# Gotcha titles
# --------------------------------------------------------------------------


class TestGotchaTitles:
    async def test_titles_only_with_status_and_outcome_counts(self, db):
        e = add(db, title="reading landmarks in a cave: the list comes back empty")
        gs.add_outcome(db, e["id"], result="worked", note=None, role="a", run_id="x")
        gs.add_outcome(db, e["id"], result="did_not_work", note=None, role="a", run_id="y")
        out, _ = await enrich_obj(guidance_for(db), structured={"result": []})
        listed = out["tool_guidance"]["gotchas"]
        assert listed == [{
            "id": e["id"], "title": e["title"], "status": "proposed",
            "outcomes": {"worked": 1, "did_not_work": 1},
        }]
        assert "body" not in listed[0]
        assert "Body text" not in str(out)

    async def test_addendum_only_when_a_proposed_gotcha_is_listed(self, db):
        e = add(db, title="reading landmarks in a cave: the list comes back empty")
        out, _ = await enrich_obj(guidance_for(db), structured={"result": []})
        assert out["tool_guidance"]["gotcha_addendum"] == tg.GOTCHA_ADDENDUM
        gs.set_status(db, e["id"], "accepted", by="m")
        out, _ = await enrich_obj(guidance_for(db), structured={"result": []})
        assert out["tool_guidance"]["gotchas"][0]["status"] == "accepted"
        assert "gotcha_addendum" not in out["tool_guidance"]

    async def test_no_gotchas_key_and_no_addendum_when_the_tool_has_none(self, db):
        out, _ = await enrich_obj(guidance_for(db), structured={"a": 1})
        assert "gotchas" not in out["tool_guidance"]
        assert "gotcha_addendum" not in out["tool_guidance"]
        assert "gotchas_unavailable" not in out["tool_guidance"]

    async def test_rejected_unexplained_and_vent_entries_are_not_carried(self, db):
        keep = add(db, title="reading landmarks in a cave: the list comes back empty")
        rej = add(db, title="calling landmarks with a level argument: it is ignored silently")
        gs.set_status(db, rej["id"], "rejected", by="m")
        add(db, list_="unexplained", title="landmarks list at dawn: an odd error appeared once")
        add(db, list_="vent", title="landmarks list is not what I wanted: I needed a map view")
        out, _ = await enrich_obj(guidance_for(db), structured={"result": []})
        assert [g["id"] for g in out["tool_guidance"]["gotchas"]] == [keep["id"]]

    async def test_other_tools_gotchas_are_not_carried(self, db):
        add(db, tool="building.build", title="placing a workshop in a desert biome: the build stalls")
        out, _ = await enrich_obj(guidance_for(db), tool="landmarks.list", structured={"a": 1})
        assert "gotchas" not in out["tool_guidance"]

    async def test_kind_specific_and_tool_wide_apply_to_that_kind_only(self, db):
        wide = add(db, tool="building.build", title="placing any building next to lava: the site is lost")
        mason = add(db, tool="building.build", kind="Masons", title="queueing blocks with no boulder on hand: it idles")
        still = add(db, tool="building.build", kind="Still", title="brewing with no barrels: the job never starts")
        out, _ = await tg.enrich(
            "building.build", {}, {"kind": {"token": "Masons"}}, False, guidance=guidance_for(db), labor_join=None
        )
        assert [g["id"] for g in out["tool_guidance"]["gotchas"]] == [wide["id"], mason["id"]]
        # With no kind known, every entry for the tool is listed (nothing is hidden).
        out, _ = await tg.enrich("building.build", {}, {"ok": 1}, False, guidance=guidance_for(db), labor_join=None)
        assert len(out["tool_guidance"]["gotchas"]) == 3
        assert still["id"] in [g["id"] for g in out["tool_guidance"]["gotchas"]]

    async def test_accepted_sort_first_and_the_list_is_capped_with_a_count(self, db):
        titles = [
            "placing a still beside a drain: the barrel jobs never start",
            "queueing a mason job before any boulder exists: the job idles forever",
            "asking for a trade depot in a cavern: the wagon path is blocked",
            "building a farm on bare rock: nothing can be planted there",
        ]
        bodies = [
            "The still needs its own barrel supply before brewing begins in earnest.",
            "Nothing is cut until stone is dragged in from a mined-out stockpile.",
            "Merchants need a clear approach on the surface, cavern sites never qualify.",
            "Only soil tiles take a crop, so check the tile material before placing a plot.",
        ]
        ids = [add(db, title=t, body=b)["id"] for t, b in zip(titles, bodies)]
        gs.set_status(db, ids[3], "accepted", by="m")
        out, _ = await enrich_obj(guidance_for(db, max_listed=2), structured={"a": 1})
        listed = out["tool_guidance"]["gotchas"]
        assert [g["id"] for g in listed] == [ids[3], ids[0]]
        assert out["tool_guidance"]["gotchas_omitted"] == 2

    async def test_xml_block_lists_titles_escaped_and_marks_unavailable_and_omitted(self, db):
        add(db, title="reading landmarks in a cave & tunnel: the list comes back empty")
        _, blocks = await enrich_obj(guidance_for(db), structured={"a": 1})
        xml = blocks[0]
        assert "cave &amp; tunnel" in xml and "<addendum>" in xml
        assert 'worked="0" did_not_work="0"' in xml


# --------------------------------------------------------------------------
# Unknown is not none: an unreadable store is said, not hidden
# --------------------------------------------------------------------------


class TestStoreUnavailable:
    async def test_absent_store_is_reported_and_the_result_still_comes_back(self, tmp_path):
        g = guidance_for(tmp_path / "absent.sqlite3")
        out, blocks = await enrich_obj(g, structured={"candidates": [1]})
        assert out["candidates"] == [1]
        assert "not found" in out["tool_guidance"]["gotchas_unavailable"]
        assert "gotchas" not in out["tool_guidance"]
        assert out["tool_guidance"]["confidence"] == "medium"
        assert "<gotchas_unavailable>" in blocks[0]

    async def test_malformed_store_is_reported(self, tmp_path):
        junk = tmp_path / "junk.sqlite3"
        junk.write_bytes(b"not sqlite at all" * 40)
        out, _ = await enrich_obj(guidance_for(junk), structured={"a": 1})
        assert "malformed" in out["tool_guidance"]["gotchas_unavailable"]


# --------------------------------------------------------------------------
# Collisions and the labor join hook
# --------------------------------------------------------------------------


class TestCollisionsAndJoin:
    async def test_a_tools_own_key_is_never_overwritten(self, db):
        own = {"tool_guidance": "mine", "gaps": ["from the tool"], "requirements": "unknown"}

        def stub(db_path, kind):
            return {"kind": kind, "labors": ["X"], "status": "known", "processes": [], "unknown_reason": None}

        async def count(labors):
            return {"counts": {"X": 1}, "errors": {}}

        joiner = lj.LaborJoin("/x", count, labors_for_kind=stub)
        out, _ = await tg.enrich(
            "building.find", {"kind": "Still"}, own, False, guidance=guidance_for(db), labor_join=joiner
        )
        assert out["tool_guidance"] == "mine" and out["gaps"] == ["from the tool"]
        assert "operating_labors" in out

    async def test_join_applies_to_building_tools_only(self, db):
        calls = []

        def stub(db_path, kind):
            calls.append(kind)
            return {"kind": kind, "labors": [], "status": "known", "processes": [], "unknown_reason": None}

        async def count(labors):  # pragma: no cover
            return {"counts": {}, "errors": {}}

        joiner = lj.LaborJoin("/x", count, labors_for_kind=stub)
        out, blocks = await tg.enrich(
            "landmarks.list", {"kind": "Still"}, {"result": []}, False, guidance=guidance_for(db), labor_join=joiner
        )
        assert "operating_labors" not in out and calls == []
        out, blocks = await tg.enrich(
            "building.build", {}, {"kind": {"token": "Masons"}, "requirements": GOOD}, False,
            guidance=guidance_for(db), labor_join=joiner,
        )
        assert calls == ["Masons"]
        assert set(out) >= {"operating_labors", "gaps", "gaps_unknown", "tool_guidance", "kind", "requirements"}
        assert blocks[0].startswith("<operating_context") and blocks[1].startswith("<tool_guidance")

    async def test_join_works_without_guidance_configured(self):
        def stub(db_path, kind):
            return {"kind": kind, "labors": [], "status": "unknown", "processes": [], "unknown_reason": "no data"}

        async def count(labors):  # pragma: no cover
            return {}

        out, blocks = await tg.enrich(
            "building.find", {"kind": "Kennel"}, {"dims": [5, 5]}, False,
            guidance=None, labor_join=lj.LaborJoin("/x", count, labors_for_kind=stub),
        )
        assert out["operating_labors"]["labors"] is None and out["dims"] == [5, 5]
        assert "tool_guidance" not in out and len(blocks) == 1


GOOD = {"building_material": {"accepts": ["BOULDER"], "fort_owned": {"BOULDER": 2}}}
