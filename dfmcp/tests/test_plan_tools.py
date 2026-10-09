"""`plan.write`, `plan.read`, `plan.status` and the Planner role
(handoffs/2026-10-07-planner-p1a.md, research/2026-10-07-planner-design.md).

A fake `call_dfhack` stands in for the fort; the real roster has the planner
disabled until stage P1b, so a fixture roster enables it and a copy of the
agents directory proves its allowlist loads. Runs under the ambient
environment and `.venv-dfmcp` alike.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest
import yaml

from dfmcp import plan_tools, queue_tools
from dfmcp.tests.gotchas_support import ALL_NATIVE_TOOLS
from dfmcp.registry import load_registry
from dfmcp.roles import load_roster
from dfqueue import schema, store
from dfqueue.tests._helpers import make_proposal, make_ruling

pytestmark = pytest.mark.asyncio

_REAL_ROSTER = schema._load_roster
SEASON = 100800
REPO = Path(__file__).resolve().parents[2]

KINDS = [{"token": t} for t in ("Bedroom", "DiningHall", "Office", "Tomb", "Dormitory")]


class Fort:
    """The fort the fake DFHack describes. Everything is a plain attribute so a
    test sets the world it needs."""

    def __init__(self):
        self.tick = 100
        self.alive = 10
        self.bedrooms_furnished = 6
        self.chairs = 4
        self.beds = 0
        self.kinds = KINDS
        self.landmarks = [{"name": "Dining Hall"}, {"name": "Wagon"}]
        self.fail = set()
        self.calls = []

    async def __call__(self, tool_id, arguments):
        self.calls.append((tool_id, dict(arguments)))
        if tool_id in self.fail:
            raise RuntimeError(f"{tool_id} is down")
        if tool_id == "overview.get":
            return {"tier1": {"population": self.alive},
                    "tier2": {"in_game_date": f"year 0, month 1, day 1, tick {self.tick}", "alerts": []}}
        if tool_id == "zone.list-kinds":
            return self.kinds
        if tool_id == "zone.list":
            return {
                "summary": True, "counts_by_kind": {"Bedroom": self.bedrooms_furnished},
                "furnished_by_kind": {"Bedroom": self.bedrooms_furnished},
                "furniture_counts_by_kind": {"DiningHall": {"Chair": self.chairs}},
            }
        if tool_id == "vitals.summary":
            return {"alive": self.alive, "dead_total": 1}
        if tool_id == "landmarks.list":
            return self.landmarks
        if tool_id == "stocks.availability":
            return {"available_units": self.beds} if arguments.get("type") == "BED" else {"error": "unknown type"}
        raise AssertionError(f"unexpected DFHack call {tool_id}")


@pytest.fixture(autouse=True)
def planner_roster(monkeypatch):
    real = _REAL_ROSTER()
    roster = {
        **real,
        "roles": {**real["roles"], "planner": {**real["roles"]["planner"], "enabled": True}},
    }
    monkeypatch.setattr(schema, "_load_roster", lambda: roster)


@pytest.fixture
def fort():
    return Fort()


@pytest.fixture
def db(tmp_path):
    return tmp_path / "queue.sqlite3"


async def _plan(tool, role, args, db, fort):
    text, structured = await plan_tools.call(
        tool, role, args, db_path=db, call_dfhack=fort, write_lock=asyncio.Lock(), fact_reader=None,
    )
    assert json.loads(text) == json.loads(json.dumps(structured, default=str))
    return structured


async def _write(db, fort, args, role="planner"):
    return await _plan(plan_tools.PLAN_WRITE, role, args, db, fort)


async def _queue(tool, role, args, db, fort):
    return await queue_tools.call(
        tool, role, args, db_path=db, call_dfhack=fort, write_lock=asyncio.Lock(),
    )


BEDROOMS = {"id": "bedrooms", "signal": 'zones."Bedroom".furnished', "per": "alive", "want": 1.0,
            "reorder_gap": 2, "owner": "architect", "max_in_flight": 2}
DINING = {"id": "dining_seats", "signal": 'zones."DiningHall".furniture."Chair"', "per": "alive",
          "want": 1.0, "reorder": 0.7, "owner": "architect"}


# ---- registration and boundaries -----------------------------------------------------


async def test_the_plan_tools_are_native_registered_and_never_mutate():
    reg = load_registry(native_tools=ALL_NATIVE_TOOLS)
    for tool_id in plan_tools.NATIVE_TOOL_IDS:
        tool = reg.get(tool_id)
        assert tool.native and not tool.mutates and not tool.sole_writer_only
        description, input_schema = tool.describe("planner")
        assert description and input_schema["additionalProperties"] is False


async def test_only_the_planner_writes_and_only_the_conductor_reads_status(db, fort):
    for role in ("architect", "overseer", "conductor", "quartermaster"):
        with pytest.raises(plan_tools.PlanToolError, match="only the 'planner' may write"):
            await _write(db, fort, {"base_version": 0}, role=role)
    for role in ("planner", "architect", "overseer"):
        with pytest.raises(plan_tools.PlanToolError, match="only the 'conductor' may read plan status"):
            await _plan(plan_tools.PLAN_STATUS, role, {}, db, fort)


async def test_a_plan_error_is_a_queue_tool_error_so_the_server_turns_it_into_isError():
    assert issubclass(plan_tools.PlanToolError, queue_tools.QueueToolError)


async def test_role_and_stamped_fields_are_not_arguments(db, fort):
    for bad in ({"role": "planner"}, {"version": 5}, {"season_index": 1}, {"changes": []}, {"flags": []}):
        with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
            await _write(db, fort, {"base_version": 0, **bad})


async def test_base_version_is_required_and_checked(db, fort):
    with pytest.raises(plan_tools.PlanToolError, match="'base_version' is required"):
        await _write(db, fort, {})
    with pytest.raises(plan_tools.PlanToolError, match="stale base"):
        await _write(db, fort, {"base_version": 3})
    await _write(db, fort, {"base_version": 0})
    fort.tick = SEASON + 5
    with pytest.raises(plan_tools.PlanToolError, match="you sent base_version 0 but the active version is 1"):
        await _write(db, fort, {"base_version": 0, "set": {"targets": [BEDROOMS]}, "reason": "retry"})


# ---- plan.write -----------------------------------------------------------------------


async def test_version_one_with_an_empty_set_adopts_the_default_plan(db, fort):
    out = await _write(db, fort, {"base_version": 0})
    assert out["filed"] and out["version"] == 1 and out["changes"] == [] and out["flags"] == []
    active = store.active_plan(db)
    # the default is the fort roadmap's stage for the fort (10 alive: founding)
    assert [t["id"] for t in active["targets"]] == ["dormitory_beds", "dining_tables"]
    assert active["roadmap_stage"] == "founding"
    assert active["role"] == "planner" and active["season_index"] == 0 and active["cycle"] == 100


async def test_a_dry_run_reports_everything_and_writes_nothing(db, fort):
    typo = {**BEDROOMS, "signal": 'zones."Bedrom".furnished'}
    out = await _write(db, fort, {"base_version": 0, "set": {"targets": [typo]}, "dry_run": True})
    assert out["dry_run"] is True and out["would_file"] is True and out["refusals"] == []
    flag = next(f for f in out["flags"] if f["code"] == "unknown_kind")
    assert flag["nearest"] == "Bedroom" and out["inert_entries"] == ["targets.bedrooms"]
    assert store.active_plan(db) is None


async def test_mistakes_are_accepted_and_flagged_not_refused(db, fort):
    bad = [
        {**BEDROOMS, "signal": 'zones."Bedrom".furnished'},
        {**DINING, "id": "x", "signal": "zones.nope"},
        {**DINING, "id": "y", "want": "lots"},
    ]
    out = await _write(db, fort, {"base_version": 0, "set": {"targets": bad}})
    assert out["filed"] is True
    assert {"unknown_kind", "bad_signal", "bad_threshold"} <= {f["code"] for f in out["flags"]}
    assert sorted(out["inert_entries"]) == ["targets.bedrooms", "targets.x", "targets.y"]
    stored = store.active_plan(db)
    assert len(stored["targets"]) == 3 and stored["flags"] == out["flags"]


async def test_a_coordinate_and_a_shape_error_are_the_only_refusals(db, fort):
    with pytest.raises(queue_tools.QueueToolError, match="raw-coordinate"):
        await _write(db, fort, {"base_version": 0, "set": {"targets": [{**BEDROOMS, "note": "at x=4 y=9"}]}})
    with pytest.raises(plan_tools.PlanToolError, match="expected a list"):
        await _write(db, fort, {"base_version": 0, "set": {"targets": "bedrooms"}})
    with pytest.raises(plan_tools.PlanToolError, match="arrives at stage P2"):
        await _write(db, fort, {"base_version": 0, "set": {"districts": []}})
    assert store.active_plan(db) is None
    dry = await _write(db, fort, {"base_version": 0, "set": {"targets": [{**BEDROOMS, "note": "at x=4 y=9"}]}, "dry_run": True})
    assert dry["would_file"] is False and any("raw-coordinate" in r for r in dry["refusals"])


async def test_the_season_interval_through_the_tool_and_the_fix_only_exemption(db, fort):
    typo = {**BEDROOMS, "signal": 'zones."Bedrom".furnished'}
    await _write(db, fort, {"base_version": 0, "set": {"targets": [typo, DINING]}})
    fort.tick = 5000
    # a change to an unflagged entry is refused, and the dry run says so up front
    other = {"base_version": 1, "set": {"targets": [typo, {**DINING, "want": 2.0}]}, "reason": "more chairs"}
    dry = await _write(db, fort, {**other, "dry_run": True})
    assert dry["would_file"] is False and dry["season"]["ok"] is False
    assert f"opens at tick {SEASON}" in dry["season"]["refusal"]
    with pytest.raises(queue_tools.QueueToolError, match="already has plan version 1"):
        await _write(db, fort, other)
    # fixing only the flagged entry is exempt at any time
    fix = await _write(db, fort, {"base_version": 1, "set": {"targets": [BEDROOMS, DINING]}, "reason": "fix the kind typo"})
    assert fix["version"] == 2 and fix["season"]["reason"] == "fix_only" and fix["flags"] == []
    # a new season is free
    fort.tick = SEASON + 1
    nxt = await _write(db, fort, {"base_version": 2, "set": {"targets": [BEDROOMS]}, "reason": "dining waits"})
    assert nxt["version"] == 3 and nxt["season"]["reason"] == "new_season"


async def test_a_ruled_plan_change_authorises_a_mid_season_version(db, fort):
    await _write(db, fort, {"base_version": 0})
    fort.tick = 3000
    _t, pc = await _queue(queue_tools.QUEUE_PROPOSE, "planner", {
        "type": "plan_change", "summary": "Lower the bedroom target after the siege thinned the fort.",
        "rationale": "Nine citizens died; the want is stale.",
        "prediction": {"signal": "fort.population", "op": "gte", "value": 1, "check_after_ticks": 1200},
        "cost": {"estimate": 1, "unit": "dwarf_ticks"}, "suggested_priority": 2,
        "preconditions": [{"landmark": "Wagon", "state": "exists"}],
        "public_rationale": "The fort shrank, so the plan shrinks.",
    }, db, fort)
    ruling = store.append(make_ruling(pc["id"]), db)
    no_ruling = {"base_version": 1, "set": {"targets": [{**BEDROOMS, "want": 0.5}, DINING]}, "reason": "siege"}
    with pytest.raises(queue_tools.QueueToolError, match="already has plan version 1"):
        await _write(db, fort, no_ruling)
    dry = await _write(db, fort, {**no_ruling, "ruling_id": ruling["id"], "dry_run": True})
    assert dry["would_file"] is True and dry["season"]["reason"] == "ruled"
    out = await _write(db, fort, {**no_ruling, "ruling_id": ruling["id"]})
    assert out["version"] == 2
    assert store.plan_changes_awaiting(db) == []
    bad = await _write(db, fort, {"base_version": 2, "set": {"targets": [BEDROOMS]}, "reason": "again",
                                  "ruling_id": ruling["id"], "dry_run": True})
    assert bad["would_file"] is False and "already authorised" in bad["ruling_problem"]


async def test_relies_on_cites_a_live_signal_and_a_zero_is_a_number(db, fort):
    fort.chairs = 0
    out = await _write(db, fort, {"base_version": 0, "relies_on": [
        {"signal": 'zones."DiningHall".furniture."Chair"'}, {"signal": "fort.population"},
    ]})
    cited = store.active_plan(db)["cited"]
    assert [(c["signal"], c["value"]) for c in cited] == [('zones."DiningHall".furniture."Chair"', 0), ("fort.population", 10)]
    assert out["flags"] == []


async def test_an_unreadable_or_unparseable_citation_is_a_flag_not_a_refusal(db, fort):
    fort.fail.add("overview.get")  # the stamp needs it; give the stamp a working read first
    fort.fail.clear()
    fort.fail.add("vitals.summary")
    out = await _write(db, fort, {"base_version": 0, "relies_on": [{"signal": "nope"}, {"signal": "fort.population"}]})
    assert any(f["code"] == "bad_signal" and f["section"] == "relies_on" for f in out["flags"])
    assert any(f["code"] == "unreadable_citation" for f in out["flags"])
    assert out["filed"] is True


async def test_unreadable_zone_kinds_do_not_block_a_write(db, fort):
    fort.fail.add("zone.list-kinds")
    out = await _write(db, fort, {"base_version": 0})
    assert out["filed"] and [f["code"] for f in out["flags"]] == ["kinds_unchecked"]
    assert out["inert_entries"] == []


async def test_a_dead_dfhack_refuses_the_write_cleanly(db, fort):
    fort.fail.add("overview.get")
    with pytest.raises(queue_tools.QueueToolError):
        await _write(db, fort, {"base_version": 0})
    assert store.active_plan(db) is None


async def test_landmarks_are_read_only_when_a_signal_names_one(db, fort):
    await _write(db, fort, {"base_version": 0, "dry_run": True})
    assert "landmarks.list" not in [c[0] for c in fort.calls]
    t = {**BEDROOMS, "signal": 'landmark."Dinning Hall".exists'}
    out = await _write(db, fort, {"base_version": 0, "set": {"targets": [t]}, "dry_run": True})
    assert "landmarks.list" in [c[0] for c in fort.calls]
    assert any(f["code"] == "unknown_landmark" and f["nearest"] == "Dining Hall" for f in out["flags"])


# ---- plan.read -----------------------------------------------------------------------


async def test_read_before_version_one_returns_the_default_plan(db, fort):
    out = await _plan(plan_tools.PLAN_READ, "planner", {}, db, fort)
    assert out["active_version"] == 0 and [t["id"] for t in out["default"]["targets"]] == ["dormitory_beds", "dining_tables"]
    assert out["roadmap"]["stage"] == "founding"
    assert "base_version 0" in out["note"]


async def test_read_slices_by_role(db, fort):
    drink = {"id": "drink", "signal": 'stocks.availability."DRINK".available_units', "want": 30,
             "reorder_gap": 5, "owner": "quartermaster"}
    await _write(db, fort, {"base_version": 0, "set": {"targets": [BEDROOMS, DINING, drink]}})
    ids = lambda out: [t["id"] for t in out["targets"]]  # noqa: E731
    assert ids(await _plan(plan_tools.PLAN_READ, "planner", {}, db, fort)) == ["bedrooms", "dining_seats", "drink"]
    assert ids(await _plan(plan_tools.PLAN_READ, "overseer", {}, db, fort)) == ["bedrooms", "dining_seats", "drink"]
    assert ids(await _plan(plan_tools.PLAN_READ, "architect", {}, db, fort)) == ["bedrooms", "dining_seats"]
    assert ids(await _plan(plan_tools.PLAN_READ, "quartermaster", {}, db, fort)) == ["bedrooms", "drink"]


async def test_read_a_named_version_a_section_and_history(db, fort):
    await _write(db, fort, {"base_version": 0})
    fort.tick = SEASON + 1
    await _write(db, fort, {"base_version": 1, "set": {"targets": [BEDROOMS]}, "reason": "dining waits"})
    now = await _plan(plan_tools.PLAN_READ, "planner", {"section": "targets"}, db, fort)
    assert now["version"] == 2 and [t["id"] for t in now["targets"]] == ["bedrooms"]
    first = await _plan(plan_tools.PLAN_READ, "planner", {"version": 1}, db, fort)
    assert first["version"] == 1 and first["active_version"] == 2 and len(first["targets"]) == 2
    assert [h["version"] for h in now["history"]] == [2, 1] and now["history"][0]["reason"] == "dining waits"
    with pytest.raises(plan_tools.PlanToolError, match="no plan version 9"):
        await _plan(plan_tools.PLAN_READ, "planner", {"version": 9}, db, fort)
    with pytest.raises(plan_tools.PlanToolError, match="only for the active version"):
        await _plan(plan_tools.PLAN_READ, "planner", {"version": 1, "status": True}, db, fort)


async def test_history_is_bounded_to_eight_lines(db, fort):
    await _write(db, fort, {"base_version": 0})
    for n in range(1, 11):
        fort.tick = n * SEASON + 1
        await _write(db, fort, {"base_version": n, "set": {"targets": [{**BEDROOMS, "want": 1.0 + n / 10}]}, "reason": f"v{n + 1}"})
    out = await _plan(plan_tools.PLAN_READ, "planner", {}, db, fort)
    assert out["active_version"] == 11 and len(out["history"]) == 8 and out["history"][0]["version"] == 11


async def test_the_planner_and_overseer_see_plan_changes_awaiting_others_do_not(db, fort):
    await _write(db, fort, {"base_version": 0})
    pc = store.append(make_proposal(role="planner", type="plan_change", cycle=500, summary="Revise mid season now."), db, game_tick=500)
    ruling = store.append(make_ruling(pc["id"]), db)
    for role, sees in (("planner", True), ("overseer", True), ("architect", False)):
        out = await _plan(plan_tools.PLAN_READ, role, {}, db, fort)
        assert ("plan_changes_awaiting" in out) is sees, role
    assert out.get("plan_changes_awaiting") is None
    out = await _plan(plan_tools.PLAN_READ, "planner", {}, db, fort)
    assert out["plan_changes_awaiting"] == [{"proposal_id": pc["id"], "ruling_id": ruling["id"]}]


# ---- plan.status ---------------------------------------------------------------------


async def test_status_computes_position_in_flight_and_the_derived_bed_input(db, fort):
    await _write(db, fort, {"base_version": 0, "set": {"targets": [BEDROOMS, DINING]}})
    fort.bedrooms_furnished, fort.alive, fort.beds = 6, 10, 0
    a = store.append(make_proposal(role="architect", type="stockpile_siting", serves=["bedrooms"],
                                   summary="Site a bedroom block near the hall."), db, game_tick=100)
    b = store.append(make_proposal(role="architect", type="stockpile_siting", serves=["bedrooms"],
                                   summary="Site a second bedroom block beside the well."), db, game_tick=100)
    out = await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort)
    assert out["active"]["version"] == 1 and out["bootstrap"] is False and out["alive"] == 10
    row = next(t for t in out["targets"] if t["id"] == "bedrooms")
    assert row["on_hand"] == 6 and row["in_flight"] == 2.0 and row["position"] == 8.0
    assert row["state"] == "open"          # 2 short of 10 with the two in flight counted
    assert {s["proposal_id"] for s in row["serving"]} == {a["id"], b["id"]}
    assert row["at_max_in_flight"] is True and row["template"] == "bedroom-cell"
    assert row["inputs"] == [{"item": "bed", "needed": 2.0, "available": 0, "owner": "quartermaster", "short": 2.0}]
    assert out["owners"]["architect"] == {"in_flight": 2, "ceiling": 2}
    dining = next(t for t in out["targets"] if t["id"] == "dining_seats")
    assert dining["on_hand"] == 4 and dining["state"] == "open" and dining["inputs"] == []   # 4 < 0.7 * 10


async def test_status_without_an_in_flight_room_has_no_input_line(db, fort):
    await _write(db, fort, {"base_version": 0, "set": {"targets": [BEDROOMS, DINING]}})
    out = await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort)
    row = next(t for t in out["targets"] if t["id"] == "bedrooms")
    assert row["in_flight"] == 0.0 and row["inputs"] == [] and row["at_max_in_flight"] is False


async def test_status_marks_an_unreadable_signal_unresolved_and_a_flagged_entry_inert(db, fort):
    typo = {**BEDROOMS, "signal": 'zones."Bedrom".furnished'}
    await _write(db, fort, {"base_version": 0, "set": {"targets": [typo, DINING]}})
    fort.fail.add("zone.list")
    out = await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort)
    states = {t["id"]: t["state"] for t in out["targets"]}
    assert states == {"bedrooms": "inert", "dining_seats": "unresolved"}
    inert = next(t for t in out["targets"] if t["id"] == "bedrooms")
    assert inert["flags"][0]["code"] == "unknown_kind" and out["flags"]


async def test_status_before_version_one_says_bootstrap(db, fort):
    out = await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort)
    assert out["active"] is None and out["bootstrap"] is True and "targets" not in out


async def test_status_with_an_unreadable_alive_count_never_invents_a_shortfall(db, fort):
    await _write(db, fort, {"base_version": 0, "set": {"targets": [BEDROOMS, DINING]}})
    fort.fail.add("vitals.summary")
    out = await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort)
    assert {t["state"] for t in out["targets"]} == {"unresolved"} and out["alive"] is None


async def test_read_with_status_is_sliced_to_the_role(db, fort):
    await _write(db, fort, {"base_version": 0, "set": {"targets": [BEDROOMS, DINING]}})
    out = await _plan(plan_tools.PLAN_READ, "architect", {"status": True}, db, fort)
    assert [t["id"] for t in out["status"]["targets"]] == ["bedrooms", "dining_seats"]
    out = await _plan(plan_tools.PLAN_READ, "consultant", {"status": True}, db, fort)
    assert out["status"]["targets"] == [] and out["targets"] == []


# ---- queue.pass and queue.propose through the tool layer ------------------------------


async def test_a_planner_pass_notes_the_review_tick(db, fort):
    await _write(db, fort, {"base_version": 0})
    fort.tick = 7777
    await _queue(queue_tools.QUEUE_PASS, "planner", {"reason": "Targets still fit the fort; nothing to change."}, db, fort)
    assert store.plan_last_reviewed_tick(db) == 7777
    fort.tick = 9999
    await _queue(queue_tools.QUEUE_PASS, "architect", {"reason": "No site worth proposing this wake."}, db, fort)
    assert store.plan_last_reviewed_tick(db) == 7777        # only a Planner pass is a plan review
    out = await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort)
    assert out["last_reviewed_tick"] == 7777


async def test_propose_offers_serves_and_the_planner_a_plan_change_only(db, fort):
    _text, props = queue_tools.NATIVE_TOOLS[queue_tools.QUEUE_PROPOSE].describe("planner")
    assert props["properties"]["type"]["enum"] == ["plan_change"] and "serves" in props["properties"]
    await _write(db, fort, {"base_version": 0, "set": {"targets": [BEDROOMS, DINING]}})
    _t, rec = await _queue(queue_tools.QUEUE_PROPOSE, "architect", {
        "type": "stockpile_siting", "summary": "Site a bedroom block near the hall.", "rationale": "A bedroom shortfall.",
        "prediction": {"signal": "fort.population", "op": "gte", "value": 1, "check_after_ticks": 1200},
        "cost": {"estimate": 5, "unit": "dwarf_ticks"}, "suggested_priority": 3,
        "preconditions": [{"landmark": "Wagon", "state": "exists"}],
        "public_rationale": "Bedrooms for the dwarves.", "serves": ["bedrooms"],
    }, db, fort)
    assert rec["serves"] == ["bedrooms"]


# ---- the Planner role files ------------------------------------------------------------


def _roster_copy(tmp_path):
    agents = tmp_path / "agents"
    shutil.copytree(REPO / "agents", agents)
    manifest = yaml.safe_load((agents / "ROSTER.yaml").read_text(encoding="utf-8"))
    manifest["roles"]["planner"]["enabled"] = True
    (agents / "ROSTER.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return agents


async def test_the_real_roster_has_the_planner_enabled():
    manifest = yaml.safe_load((REPO / "agents" / "ROSTER.yaml").read_text(encoding="utf-8"))
    assert manifest["roles"]["planner"]["enabled"] is True
    assert manifest["roles"]["planner"]["kind"] == "advisor"
    for f in ("role.md", "tools.yaml", "model.yaml"):
        assert (REPO / "agents" / "planner" / f).is_file()
    assert "planner" in load_roster(load_registry(native_tools=ALL_NATIVE_TOOLS)).roles


async def test_the_planner_allowlist_loads_enabled_with_sixteen_non_mutating_tools(tmp_path):
    reg = load_registry(native_tools=ALL_NATIVE_TOOLS)
    roster = load_roster(reg, agents_dir=_roster_copy(tmp_path))
    perms = roster.roles["planner"]
    assert len(perms.read) + len(perms.write) == 16
    assert sorted(perms.read) == sorted([
        "overview.get", "vitals.summary", "zone.list", "zone.list-kinds", "nobles.requirements",
        "blueprint.sites", "queue.project_status", "queue.my_filings", "plan.read",
        "circulation.graph", "circulation.walk", "openarea.survey",
    ])
    assert sorted(perms.write) == ["plan.write", "queue.ask", "queue.pass", "queue.propose"]
    assert not any(reg.get(t).mutates for t in list(perms.read) + list(perms.write))
    assert roster.check("planner", "plan.write")[0] and not roster.check("planner", "plan.status")[0]
    assert not roster.check("planner", "stockpile.list")[0] and not roster.check("planner", "orders.list")[0]


async def test_the_other_roles_grants_after_the_plan_tools(tmp_path):
    reg = load_registry(native_tools=ALL_NATIVE_TOOLS)
    roster = load_roster(reg, agents_dir=_roster_copy(tmp_path))
    for role in ("architect", "quartermaster", "overseer", "planner"):
        assert roster.check(role, "plan.read")[0], role
    assert roster.check("conductor", "plan.read")[0] is False       # P1b grants plan.status to the conductor
    for role in ("architect", "quartermaster", "overseer", "consultant"):
        assert not roster.check(role, "plan.write")[0], role
    assert not roster.check("consultant", "plan.read")[0]


async def test_the_planner_role_card_is_consistent_with_the_server():
    text = (REPO / "agents" / "planner" / "role.md").read_text(encoding="utf-8")
    assert "—" not in text and "–" not in text         # no dashes in prose
    for needle in ("plan.write", "dry_run", "plan_change", "base_version", "queue.pass"):
        assert needle in text
    tools = yaml.safe_load((REPO / "agents" / "planner" / "tools.yaml").read_text(encoding="utf-8"))
    assert tools["role"] == "planner" and tools["write_authority"] == "none"
    model = yaml.safe_load((REPO / "agents" / "planner" / "model.yaml").read_text(encoding="utf-8"))
    assert model["role"] == "planner" and model["cadence"]["rounds_budget"] == 8


async def test_status_shows_the_computed_level_for_a_mapping_want(db, fort):
    mapped = {"id": "bedrooms", "signal": 'zones."Bedroom".furnished',
              "want": {"per_alive": 1.0, "plus": 3, "min": 10, "max": 60}, "reorder_gap": 2, "owner": "architect"}
    await _write(db, fort, {"base_version": 0, "set": {"targets": [mapped]}})
    fort.bedrooms_furnished, fort.alive = 6, 10
    st = await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort)
    assert st["alive"] == 10
    row = next(t for t in st["targets"] if t["id"] == "bedrooms")
    assert row["want"] == mapped["want"] and row["want_units"] == 13.0 and row["state"] == "open"


# ---- synced crop targets (register 2026-10-09, autofarm) ------------------------------

CROP_DEFAULT = {"id": "crop_default", "sync": "autofarm", "crop": "default", "want": 0}
CROP_PLUMP = {"id": "crop_plump_helmet", "sync": "autofarm", "crop": "MUSHROOM_HELMET_PLUMP",
              "want": {"per_alive": 4, "min": 20}}


async def test_a_synced_crop_target_is_accepted_unflagged_and_reported_synced_with_its_number(db, fort):
    out = await _write(db, fort, {"base_version": 0, "set": {"targets": [BEDROOMS, CROP_DEFAULT, CROP_PLUMP]}})
    assert not [f for f in out.get("flags", []) if f.get("inert")]
    fort.alive = 10
    st = await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort)
    rows = {t["id"]: t for t in st["targets"]}
    assert rows["crop_plump_helmet"]["state"] == "synced" and rows["crop_plump_helmet"]["want_units"] == 40.0
    assert rows["crop_plump_helmet"]["crop"] == "MUSHROOM_HELMET_PLUMP" and "owner" not in rows["crop_plump_helmet"]
    assert rows["crop_default"]["want_units"] == 0.0
    assert rows["bedrooms"]["state"] != "synced"


async def test_a_synced_target_needs_no_alive_count_when_its_want_is_a_plain_number(db, fort):
    await _write(db, fort, {"base_version": 0, "set": {"targets": [CROP_DEFAULT]}})
    fort.fail.add("vitals.summary")
    st = await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort)
    assert st["targets"][0]["state"] == "synced" and st["targets"][0]["want_units"] == 0.0
