"""The executor's run machinery (dfmcp/executor_run.py, dfmcp/executor_filing.py)
over a fake DFHack world: filing checks, open_project, run_step in order and in
every outcome class, resolve_uncertain, observe, cleanup_project, close.

The fake world implements just enough of the blueprint verbs (reserve, apply,
status, plan, reservations, sites, release, unreserve) to follow the real
declared data in TOOLS.yaml, and it can fail a real call in each way the
conductor must survive: never sent, lost, or landed with the reply lost.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from dfmcp import conductor_tools, doctrine_tools, executor_filing, executor_run, gotchas_tools
from dfmcp import executor_tools as et
from dfmcp import knowledge_tools, queue_tools, series_tools
from dfmcp.executor_run import CallFailed, CallNotSent, CallOutcomeUnknown, ExecEnv
from dfmcp.registry import load_registry
from dfqueue import routing, schema, store
from dfqueue.tests._helpers import make_ruling

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "blueprint" / "bedroom-cell-v1.json"
REAL_YAML = routing.ACTION_TOOLS_PATH
BP = "bedroom-cell-v1"
SHELL, ZONE, BUILD, FINISH = (f"bedroom_cell_v1_{n}" for n in ("shell", "zone", "build", "finish"))


# ---- the fake world -----------------------------------------------------------------


class FakeWorld:
    """State and behaviour of the blueprint verbs. `fail_real` is one of None,
    "notsent" (raised before anything happens), "lost" (raised, nothing
    happened) or "landed" (the effect happens, then the reply is lost)."""

    def __init__(self):
        self.plan = json.loads(FIXTURE.read_text(encoding="utf-8"))["plan"]
        self.reservations: dict = {}
        self.sites: dict = {}
        self.done: set = set()
        self.calls: list = []
        self.fail_real = None
        self.refuse_reserve = False
        self.drift_landmark = False
        self.dry_timeout = False
        self.reserve_without_would_reserve = False
        self.unreserve_error = None
        self.release_error = None
        self.n_res = 0
        self.n_site = 0
        self.shell_dug = False

    # -- helpers
    def real_calls(self, tool=None):
        return [c for c in self.calls if c[1].get("dry_run") == "false" and (tool is None or c[0] == tool)]

    async def call_tool(self, tool, args, *, timeout=None):
        self.calls.append((tool, dict(args)))
        dry = args.get("dry_run") == "true"
        if tool in ("blueprint.reserve", "blueprint.apply", "blueprint.release", "blueprint.unreserve"):
            if dry and self.dry_timeout:
                raise CallOutcomeUnknown("read timed out")
            if not dry:
                if self.fail_real == "notsent":
                    raise CallNotSent("DFHack is unreachable")
                if self.fail_real == "lost":
                    raise CallOutcomeUnknown("connection dropped")
        if tool == "construction.mine-vein-site":
            return self._mine_vein_site(args, dry)
        out = getattr(self, "_" + tool.split(".")[1])(args, dry)
        mutating = tool in ("blueprint.reserve", "blueprint.apply", "blueprint.release", "blueprint.unreserve")
        if mutating and not dry and self.fail_real == "landed":
            raise CallOutcomeUnknown("reply lost after the call ran")
        return out

    # -- verbs
    def _mine_vein_site(self, args, dry):
        """The shape of df-overseer-construction.lua mine_vein: lists, never an ok flag."""
        self.mined = getattr(self, "mined", [])
        out = {"zone_id": args["site_id"], "boundary_ring_tiles": 12, "ore_tiles_found": 2, "already_open": [],
               "refused": list(getattr(self, "mine_refused", [])), "held": list(getattr(self, "mine_held", [])),
               "dry_run": dry, "results": [{"ring_position": 1, "ok": True}]}
        out["designated_tiles"] = 0 if getattr(self, "mine_none_real", False) and not dry else 2
        out["nothing_designated"] = out["designated_tiles"] == 0
        if getattr(self, "mine_none_real", False) and not dry:
            out["refused"] = ["ring tile 1: could not confirm its shape"]
            out["blocked_reason"] = "ring tile 1: could not confirm its shape"
        if not dry:
            self.mined.append(args["site_id"])
        return out

    def _plan(self, args, dry):
        return self.plan

    def _reservations(self, args, dry):
        return {"result": [dict(r) for r in self.reservations.values()]}

    def _sites(self, args, dry):
        return {"result": [{"handle": h, "phases_applied": list(s["phases"]), "reservation": s["res"]}
                           for h, s in self.sites.items()]}

    def _reserve(self, args, dry):
        landmark = "Kiln" if self.drift_landmark else "Well"
        base = {"dry_run": dry, "near_landmark": landmark, "direction": "NE", "distance_tiles": 7,
                "orientation": "none", "level": 0, "footprint": {"width": 5, "height": 5},
                "allowed_kinds": ["bed"], "finish_plan": {"required_cells": 15}}
        if self.refuse_reserve:
            return {**base, "refused": True, "blocked_reason": "overlaps existing res-9"}
        if dry:
            out = {**base, "would_reserve": True}
            if self.reserve_without_would_reserve:
                del out["would_reserve"]
            return out
        self.n_res += 1
        handle = f"res-{self.n_res}"
        self.reservations[handle] = {"handle": handle, "purpose": args["purpose"], "site_handle": None}
        return {**base, "handle": handle}

    def _apply(self, args, dry):
        site, phase = args["site"], args["phase"]
        if phase != SHELL and not self.shell_dug:
            return {"ok": False, "blocked": True, "dry_run": dry,
                    "blocked_reason": "the shell is not finished", "phase": phase}
        if dry:
            return {"ok": True, "dry_run": True, "designated": {"dig_tiles": 25, "zones": 0, "buildings": 0},
                    "finish_plan": {"required_cells": 15}, "phase": phase}
        if site.startswith("res-"):
            self.n_site += 1
            handle = f"site-{self.n_site}"
            self.sites[handle] = {"phases": [phase], "res": site}
            self.reservations[site]["site_handle"] = handle
        else:
            handle = site
            self.sites[handle]["phases"].append(phase)
        return {"ok": True, "dry_run": False, "designated": {"dig_tiles": 25, "zones": 0, "buildings": 0},
                "phase": phase, "site": {"handle": handle}}

    def _status(self, args, dry):
        site, phase = args["site_id"], args.get("phase")
        return {"phase": {"done": (site, phase) in self.done}, "dig": {"state": "none_pending"},
                "finish_state": {"blocked_total": 0}}

    def _release(self, args, dry):
        if self.release_error or args["site_id"] not in self.sites:
            return {"error": self.release_error or f"no site '{args['site_id']}' (see sites)"}
        skipped = [p for p in self.sites[args["site_id"]]["phases"] if p != SHELL]
        del self.sites[args["site_id"]]
        return {"dry_run": False, "released": True, "skipped_phases": skipped}

    def _unreserve(self, args, dry):
        if self.unreserve_error or args["res_id"] not in self.reservations:
            return {"error": self.unreserve_error or f"no reservation '{args['res_id']}'"}
        del self.reservations[args["res_id"]]
        return {"dry_run": False, "released": True}


# ---- fixtures -----------------------------------------------------------------------


def set_routing(monkeypatch, tmp_path, **flags):
    data = yaml.safe_load(REAL_YAML.read_text(encoding="utf-8"))
    data["groups"]["rooms"].update(flags)
    p = tmp_path / "action_tools.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setattr(routing, "ACTION_TOOLS_PATH", p)


@pytest.fixture(scope="module")
def registry():
    return load_registry(native_tools={
        **queue_tools.NATIVE_TOOLS, **doctrine_tools.NATIVE_TOOLS, **series_tools.NATIVE_TOOLS,
        **gotchas_tools.NATIVE_TOOLS, **knowledge_tools.NATIVE_TOOLS, **conductor_tools.NATIVE_TOOLS,
    })


class Rig:
    def __init__(self, tmp_path, registry, monkeypatch):
        self.db = tmp_path / "q.sqlite3"
        self.world = FakeWorld()
        self.lock = asyncio.Lock()
        self.tick = 1000
        self.tripwire = None
        self.clock_error = False
        self.monkeypatch, self.tmp_path = monkeypatch, tmp_path
        self.env = ExecEnv(db_path=self.db, write_lock=self.lock, call_tool=self.world.call_tool,
                           call_dfhack=self.dfhack, registry=registry)
        self.n = 0
        # a legacy ruling first, so the rooms cutover has something to point at
        store.append(self._proposal(legacy=True), self.db, game_tick=1)
        store.append(make_ruling("proposal-0001"), self.db)
        set_routing(monkeypatch, tmp_path, routed=True)
        store.set_cutover(self.db, "legacy", "ruling-0001")
        store.set_cutover(self.db, "rooms", "ruling-0001")

    async def dfhack(self, tool, args):
        if tool == "overview.get":
            return {"tier2": {"in_game_date": f"year 0, month 1, day 1, tick {self.tick}", "alerts": []}}
        if tool == "clock.status":
            if self.clock_error:
                raise RuntimeError("clock unreadable")
            return {"tripwire": self.tripwire}
        raise AssertionError(f"unexpected DFHack read {tool}")

    def _proposal(self, legacy=False):
        from dfqueue.tests._helpers import make_proposal
        self.n += 1
        rec = make_proposal(summary=f"Bedroom number {self.n} " + "x" * self.n,
                            rationale=f"Because dwarf {self.n} sleeps rough " + "y" * self.n)
        rec["type"] = "room_siting"
        return rec

    def proposal_args(self, step, **extra):
        self.n += 1
        a = {
            "type": "room_siting", "summary": f"Bedroom number {self.n} " + "x" * self.n,
            "rationale": f"Because dwarf {self.n} sleeps rough " + "y" * self.n,
            "prediction": {"signal": "fort.population", "op": "gte", "value": 1, "check_after_ticks": 1200},
            "cost": {"estimate": 100, "unit": "dwarf_ticks"}, "suggested_priority": 3,
            "preconditions": [{"landmark": "Well", "state": "exists"}],
            "public_rationale": "A place to sleep for the dwarves.",
            "step": step,
        }
        a.update(extra)
        return a

    async def propose(self, step, role="architect", **extra):
        async def checker(r, record, urgency):
            return await executor_filing.check_filing(self.env, r, record, urgency)

        _t, rec = await queue_tools.call(
            queue_tools.QUEUE_PROPOSE, role, self.proposal_args(step, **extra), db_path=self.db,
            call_dfhack=self.dfhack, write_lock=self.lock, step_checker=checker)
        return rec

    def rule(self, proposal_id, decision="accept"):
        return store.append(make_ruling(proposal_id, decision=decision), self.db)

    async def tool(self, tool_id, **args):
        return await et.call(tool_id, "conductor", args, db_path=self.db, write_lock=self.lock,
                             call_dfhack=self.dfhack, call_tool=self.world.call_tool, registry=self.env.registry)

    # -- common scenario steps
    def reserve_step(self, label="Reserve bedroom"):
        return {"tool": "blueprint.reserve", "args": {"template": BP, "purpose": "bedroom row 1", "site": "Well"},
                "label": label}

    def apply_step(self, site, phase):
        return {"tool": "blueprint.apply", "args": {"template": BP, "phase": phase, "site": site}}

    async def open_room(self, purpose="bedroom row 1", **extra):
        step = self.reserve_step()
        step["args"]["purpose"] = purpose  # a second open room must differ (structural duplicate refusal)
        p = await self.propose(step, phases={"tool": "blueprint.apply", "list": [SHELL, FINISH]},
                               **extra)
        r = self.rule(p["id"])
        _t, out = await self.tool("queue.open_project", ruling_id=r["id"])
        return p, r, out["project_id"]

    async def run(self, pid, sid):
        return (await self.tool("queue.run_step", project_id=pid, step_id=sid))[1]

    def target_states(self, pid, sid):
        return [t["state"] for t in store.target_states(self.db, pid) if t["step_id"] == sid]


@pytest.fixture
def rig(tmp_path, registry, monkeypatch):
    return Rig(tmp_path, registry, monkeypatch)


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


pytestmark = pytest.mark.asyncio


# ---- filing -------------------------------------------------------------------------


async def test_a_good_step_is_dry_run_and_stored_with_a_preview(rig):
    p = await rig.propose(rig.reserve_step(), phases={"tool": "blueprint.apply", "list": [SHELL, FINISH]},
                          urgency="elevated")
    assert p["step"]["args"]["purpose"] == "bedroom row 1"  # stored as proposed; the id is appended at run time
    prev = p["preview"]
    assert prev["verdict"] == "ok" and prev["urgency"] == "elevated"
    assert prev["resolution"]["near_landmark"] == "Well" and prev["fields"]["finish_plan"]["required_cells"] == 15
    dry = [c for c in rig.world.calls if c[0] == "blueprint.reserve"]
    assert len(dry) == 1 and dry[0][1]["dry_run"] == "true" and dry[0][1]["purpose"].endswith("proposal-0000")
    assert not rig.world.reservations  # a dry run changed nothing


async def test_filing_refusals_each_write_nothing(rig):
    before = len(store.load(rig.db))
    step = rig.reserve_step()
    cases = [
        ({**step, "tool": "zone.place", "args": {}}, "declares no verdict"),
        ({**step, "args": {**step["args"], "dry_run": "false"}}, "set by the server"),
        ({"tool": "blueprint.apply", "args": {"template": BP, "phase": SHELL, "site": "res-1",
                                              "allow_stranded": "true"}}, "override argument"),
        ({**step, "args": {"template": BP}}, "missing required argument"),
        ({**step, "args": {**step["args"], "bogus": "1"}}, "unknown argument"),
    ]
    for bad, match in cases:
        with pytest.raises(queue_tools.QueueToolError, match=match):
            await rig.propose(bad)
    with pytest.raises(queue_tools.QueueToolError, match="urgency"):
        await rig.propose(step, urgency="whenever")
    assert len(store.load(rig.db)) == before


async def test_a_refused_dry_run_refuses_the_filing_with_the_tools_reason(rig):
    rig.world.refuse_reserve = True
    with pytest.raises(queue_tools.QueueToolError, match="overlaps existing res-9"):
        await rig.propose(rig.reserve_step())
    assert [r for r in store.load(rig.db) if r["kind"] == "proposal" and "step" in r] == []


async def test_a_dry_run_that_times_out_is_server_busy_file_again(rig):
    rig.world.dry_timeout = True
    with pytest.raises(queue_tools.QueueToolError, match="server busy, file again"):
        await rig.propose(rig.reserve_step())


async def test_an_absent_declared_field_refuses_the_filing(rig):
    rig.world.reserve_without_would_reserve = True
    with pytest.raises(queue_tools.QueueToolError, match="unusable"):
        await rig.propose(rig.reserve_step())


async def test_declared_phases_are_checked_against_the_template(rig):
    for bad, match in (([SHELL, "nope"], "not a phase"), ([FINISH, SHELL], "order"),
                       ([ZONE, FINISH], "twice")):
        with pytest.raises(queue_tools.QueueToolError, match=match):
            await rig.propose(rig.reserve_step(), phases={"tool": "blueprint.apply", "list": bad})
    ok = await rig.propose(rig.reserve_step(), phases={"tool": "blueprint.apply", "list": [SHELL, FINISH]})
    assert ok["phases"]["list"] == [SHELL, FINISH]


async def test_a_first_proposal_may_not_cite_a_handle_an_open_project_issued(rig):
    p, r, pid = await rig.open_room()
    out = await rig.run(pid, f"{pid}/s1")
    assert out["class"] == "success" and out["handle"] == "res-1"
    # a pending first proposal naming an unrelated handle is fine (dry run decides); one an open project
    # issued is refused
    with pytest.raises(queue_tools.QueueToolError, match="issued by open project"):
        await rig.propose(rig.apply_step("res-1", SHELL))


async def test_a_follow_up_must_cite_a_handle_its_project_issued(rig):
    p, r, pid = await rig.open_room()
    await rig.run(pid, f"{pid}/s1")
    with pytest.raises(queue_tools.QueueToolError, match="its own project issued"):
        await rig.propose(rig.apply_step("res-77", SHELL), project_id=pid, after_step=f"{pid}/s1")
    with pytest.raises(queue_tools.QueueToolError, match="its own project issued"):
        await rig.propose(rig.apply_step("Well", SHELL), project_id=pid, after_step=f"{pid}/s1")
    ok = await rig.propose(rig.apply_step("res-1", SHELL), project_id=pid, after_step=f"{pid}/s1")
    assert ok["project_id"] == pid


# ---- open_project / follow-up -------------------------------------------------------


async def test_open_project_uses_the_proposals_urgency_and_refuses_a_second_open(rig):
    p, r, pid = await rig.open_room(urgency="high")
    proj = [x for x in store.load(rig.db) if x["id"] == pid][0]
    assert proj["urgency"] == "high" and proj["steps"][0]["proposal_id"] == p["id"]
    with pytest.raises(queue_tools.QueueToolError, match="already has a project"):
        await rig.tool("queue.open_project", ruling_id=r["id"])
    p2 = await rig.propose(rig.reserve_step())
    r2 = rig.rule(p2["id"])
    _t, out = await rig.tool("queue.open_project", ruling_id=r2["id"])
    assert [x for x in store.load(rig.db) if x["id"] == out["project_id"]][0].get("urgency", "normal") == "normal"


async def test_open_project_refuses_a_ruling_at_or_below_the_cutover(rig):
    with pytest.raises(queue_tools.QueueToolError, match="not routed|cutover|legacy"):
        await rig.tool("queue.open_project", ruling_id="ruling-0001")


# ---- run_step: the whole room, in order ---------------------------------------------


async def test_a_room_end_to_end_reserve_then_shell_then_finish(rig):
    p, r, pid = await rig.open_room()
    s1 = f"{pid}/s1"
    out = await rig.run(pid, s1)
    assert out["class"] == "success" and out["handle"] == "res-1" and out["executed_id"].startswith("executed-")
    # the real call carried the proposal id on the purpose, after a dry run, never before one
    real = rig.world.real_calls("blueprint.reserve")
    assert len(real) == 1 and real[0][1]["purpose"] == f"bedroom row 1 {p['id']}"
    order = [(c[0], c[1].get("dry_run")) for c in rig.world.calls if c[0] == "blueprint.reserve"]
    assert order == [("blueprint.reserve", "true"), ("blueprint.reserve", "true"), ("blueprint.reserve", "false")]
    assert rig.target_states(pid, s1) == ["issued"]
    # a reserve has no progress read: observe completes it
    _t, ob = await rig.tool("queue.observe", project_id=pid, step_id=s1)
    assert ob["state"] == "done" and ob["observation_id"]
    assert rig.target_states(pid, s1) == ["done"]
    # it cannot be run again
    again = await rig.run(pid, s1)
    assert again["class"] == "not_runnable" and any("already succeeded" in x or "done" in x for x in again["reasons"])

    # the shell: a follow-up citing the handle, ruled, applied, run
    f1 = await rig.propose(rig.apply_step("res-1", SHELL), project_id=pid, after_step=s1)
    rig.rule(f1["id"])
    _t, fo = await rig.tool("queue.apply_followup", proposal_id=f1["id"])
    assert fo == {"project_id": pid, "version": 2, "step_id": f"{pid}/s2"}
    out = await rig.run(pid, fo["step_id"])
    assert out["class"] == "success" and out["handle"] == "site-1"
    assert rig.world.reservations["res-1"]["site_handle"] == "site-1"
    _t, ob = await rig.tool("queue.observe", project_id=pid, step_id=fo["step_id"])
    assert ob["state"] == "issued" and ob["recorded"] is True
    _t, ob2 = await rig.tool("queue.observe", project_id=pid, step_id=fo["step_id"])
    assert ob2["state"] == "issued" and ob2["recorded"] is False  # unchanged: no new record
    rig.world.done.add(("site-1", SHELL))
    rig.world.shell_dug = True
    _t, ob3 = await rig.tool("queue.observe", project_id=pid, step_id=fo["step_id"])
    assert ob3["state"] == "done" and rig.target_states(pid, fo["step_id"]) == ["done"]
    # the finish phase cites the site-N handle the shell issued
    f2 = await rig.propose(rig.apply_step("site-1", FINISH), project_id=pid, after_step=fo["step_id"])
    rig.rule(f2["id"])
    _t, fo2 = await rig.tool("queue.apply_followup", proposal_id=f2["id"])
    out = await rig.run(pid, fo2["step_id"])
    assert out["class"] == "success" and out["handle"] == "site-1"
    assert rig.world.sites["site-1"]["phases"] == [SHELL, FINISH]
    # prediction arms only on done, and the project's open-state tracks the declared phases
    assert store.open_projects(rig.db)[0]["phases_remaining"] == 0


async def test_waiting_when_a_prerequisite_is_issued_but_not_done(rig):
    p, r, pid = await rig.open_room()
    await rig.run(pid, f"{pid}/s1")  # issued, not observed done
    f1 = await rig.propose(rig.apply_step("res-1", SHELL), project_id=pid, after_step=f"{pid}/s1")
    rig.rule(f1["id"])
    await rig.tool("queue.apply_followup", proposal_id=f1["id"])
    out = await rig.run(pid, f"{pid}/s2")
    assert out["class"] == "waiting" and rig.world.real_calls("blueprint.apply") == []


async def test_needs_judgment_when_the_dry_run_is_blocked_and_it_is_recorded_once(rig):
    p, r, pid = await rig.open_room()
    await rig.run(pid, f"{pid}/s1")
    await rig.tool("queue.observe", project_id=pid, step_id=f"{pid}/s1")
    f1 = await rig.propose(rig.apply_step("res-1", SHELL), project_id=pid, after_step=f"{pid}/s1")
    rig.rule(f1["id"])
    await rig.tool("queue.apply_followup", proposal_id=f1["id"])
    await rig.run(pid, f"{pid}/s2")
    await rig.tool("queue.observe", project_id=pid, step_id=f"{pid}/s2")
    rig.world.done.add(("site-1", SHELL))
    rig.world.shell_dug = True
    await rig.tool("queue.observe", project_id=pid, step_id=f"{pid}/s2")
    f2 = await rig.propose(rig.apply_step("site-1", FINISH), project_id=pid, after_step=f"{pid}/s2")
    rig.rule(f2["id"])
    await rig.tool("queue.apply_followup", proposal_id=f2["id"])
    # the world says the shell is not finished after all (status said done, apply disagrees)
    rig.world.shell_dug = False
    out = await rig.run(pid, f"{pid}/s3")
    assert out["class"] == "needs_judgment" and "shell is not finished" in out["detail"]
    assert rig.world.real_calls("blueprint.apply") == [rig.world.real_calls("blueprint.apply")[0]]  # only the shell's
    await rig.run(pid, f"{pid}/s3")
    attention = [x for x in store.load(rig.db) if x["kind"] == "observation" and x["step_id"] == f"{pid}/s3"]
    assert len(attention) == 1 and attention[0]["results"][0]["status"] == "contradicted"


async def test_needs_judgment_when_a_reserves_resolution_changed(rig):
    p, r, pid = await rig.open_room()
    rig.world.drift_landmark = True
    out = await rig.run(pid, f"{pid}/s1")
    assert out["class"] == "needs_judgment" and "resolution changed" in out["detail"]
    assert out["changed"]["near_landmark"] == {"was": "Well", "now": "Kiln"}
    assert rig.world.real_calls() == []


async def test_a_pinned_step_skips_the_resolution_check(rig):
    # an apply on a res-N/site-N declares no resolution fields, so drift cannot block it
    spec = rig.env.spec("blueprint.apply")
    assert spec.resolution_fields == ()


# ---- run_step: failure classes -------------------------------------------------------


async def test_not_sent_is_transient_and_the_marker_is_voided(rig):
    p, r, pid = await rig.open_room()
    rig.world.fail_real = "notsent"
    out = await rig.run(pid, f"{pid}/s1")
    assert out["class"] == "transient"
    assert store.unresolved_step_runs(rig.db) == []
    assert [x["status"] for x in store.step_runs(rig.db, pid)] == ["void"]
    rig.world.fail_real = None
    assert (await rig.run(pid, f"{pid}/s1"))["class"] == "success"
    assert len(rig.world.reservations) == 1  # the first attempt never reached the world


async def test_a_real_call_that_may_have_run_is_uncertain_and_is_never_retried_blind(rig):
    p, r, pid = await rig.open_room()
    rig.world.fail_real = "landed"
    out = await rig.run(pid, f"{pid}/s1")
    assert out["class"] == "uncertain" and out["run_id"]
    assert len(rig.world.reservations) == 1
    rig.world.fail_real = None
    again = await rig.run(pid, f"{pid}/s1")
    assert again["class"] == "not_runnable" and any("unresolved" in x for x in again["reasons"])
    assert len(rig.world.real_calls("blueprint.reserve")) == 1  # no second call
    _t, res = await rig.tool("queue.resolve_uncertain", run_id=out["run_id"])
    assert res["class"] == "success" and res["handle"] == "res-1"
    assert rig.target_states(pid, f"{pid}/s1") == ["issued"]
    assert store.issued_handles(rig.db, pid) == ["res-1"]
    assert store.unresolved_step_runs(rig.db) == []


async def test_uncertain_that_did_not_land_resolves_transient_and_the_step_runs_again(rig):
    p, r, pid = await rig.open_room()
    rig.world.fail_real = "lost"
    out = await rig.run(pid, f"{pid}/s1")
    assert out["class"] == "uncertain"
    rig.world.fail_real = None
    _t, res = await rig.tool("queue.resolve_uncertain", run_id=out["run_id"])
    assert res["class"] == "transient"
    again = await rig.run(pid, f"{pid}/s1")
    assert again["class"] == "success" and len(rig.world.reservations) == 1


async def test_an_unreadable_landed_read_leaves_it_unresolved_or_holds_it_on_request(rig):
    p, r, pid = await rig.open_room()
    rig.world.fail_real = "landed"
    out = await rig.run(pid, f"{pid}/s1")
    original = rig.world.call_tool

    async def broken(tool, args, *, timeout=None):
        if tool == "blueprint.reservations":
            raise CallOutcomeUnknown("timed out")
        return await original(tool, args, timeout=timeout)

    rig.env.call_tool = broken
    _t, res = await et.call("queue.resolve_uncertain", "conductor", {"run_id": out["run_id"]}, db_path=rig.db,
                            write_lock=rig.lock, call_dfhack=rig.dfhack, call_tool=broken, registry=rig.env.registry)
    assert res["class"] == "uncertain" and res["held"] is False
    assert len(store.unresolved_step_runs(rig.db)) == 1
    _t, res = await et.call("queue.resolve_uncertain", "conductor", {"run_id": out["run_id"], "hold": True},
                            db_path=rig.db, write_lock=rig.lock, call_dfhack=rig.dfhack, call_tool=broken,
                            registry=rig.env.registry)
    assert res["held"] is True and store.unresolved_step_runs(rig.db) == []
    rig.world.fail_real = None
    held = await rig.run(pid, f"{pid}/s1")
    assert held["class"] == "not_runnable"  # blocked until the project is closed


async def test_a_refusal_that_applied_nothing_is_failed_once_retryable_then_final(rig):
    p, r, pid = await rig.open_room()
    s1 = f"{pid}/s1"
    await rig.run(pid, s1)
    await rig.tool("queue.observe", project_id=pid, step_id=s1)
    f1 = await rig.propose(rig.apply_step("res-1", SHELL), project_id=pid, after_step=s1)
    rig.rule(f1["id"])
    await rig.tool("queue.apply_followup", proposal_id=f1["id"])
    s2 = f"{pid}/s2"
    original = rig.world._apply

    def refusing_real(args, dry):
        if dry:
            return original(args, dry)
        return {"ok": False, "blocked": True, "dry_run": False, "blocked_reason": "the access gate refused"}

    rig.world._apply = refusing_real
    first = await rig.run(pid, s2)
    assert first["class"] == "failed" and first["retryable"] is True
    assert rig.target_states(pid, s2) in ([], ["waiting"])  # still retryable
    second = await rig.run(pid, s2)
    assert second["class"] == "failed" and second["retryable"] is False
    assert rig.target_states(pid, s2) == ["failed"]
    third = await rig.run(pid, s2)
    assert third["class"] == "not_runnable"


async def test_the_tripwire_gates_everything_but_a_high_urgency_project(rig):
    p, r, pid = await rig.open_room()
    rig.tripwire = {"reason": "thirst"}
    out = await rig.run(pid, f"{pid}/s1")
    assert out["class"] == "not_runnable" and any("tripwire" in x for x in out["reasons"])
    rig.tripwire = None
    rig.clock_error = True  # an unreadable clock counts as latched
    assert (await rig.run(pid, f"{pid}/s1"))["class"] == "not_runnable"
    rig.clock_error = False
    p2, r2, pid2 = await rig.open_room(purpose="bedroom row 2", urgency="high")
    rig.tripwire = {"reason": "thirst"}
    assert (await rig.run(pid2, f"{pid2}/s1"))["class"] == "success"


async def test_a_dry_run_that_cannot_complete_at_run_time_is_transient(rig):
    p, r, pid = await rig.open_room()
    rig.world.dry_timeout = True
    out = await rig.run(pid, f"{pid}/s1")
    assert out["class"] == "transient" and rig.world.real_calls() == []
    assert store.step_runs(rig.db, pid) == []


# ---- observe -------------------------------------------------------------------------


async def test_observe_refuses_a_step_that_is_not_issued(rig):
    p, r, pid = await rig.open_room()
    with pytest.raises(queue_tools.QueueToolError, match="not issued"):
        await rig.tool("queue.observe", project_id=pid, step_id=f"{pid}/s1")
    with pytest.raises(queue_tools.QueueToolError, match="not a step"):
        await rig.tool("queue.observe", project_id=pid, step_id=f"{pid}/s9")


async def test_an_unreadable_progress_read_is_unknown_never_done(rig):
    p, r, pid = await rig.open_room()
    s1 = f"{pid}/s1"
    await rig.run(pid, s1)
    await rig.tool("queue.observe", project_id=pid, step_id=s1)
    f1 = await rig.propose(rig.apply_step("res-1", SHELL), project_id=pid, after_step=s1)
    rig.rule(f1["id"])
    await rig.tool("queue.apply_followup", proposal_id=f1["id"])
    await rig.run(pid, f"{pid}/s2")
    original = rig.world.call_tool

    async def broken(tool, args, *, timeout=None):
        if tool == "blueprint.status":
            raise CallOutcomeUnknown("timed out")
        return await original(tool, args, timeout=timeout)

    _t, ob = await et.call("queue.observe", "conductor", {"project_id": pid, "step_id": f"{pid}/s2"}, db_path=rig.db,
                           write_lock=rig.lock, call_dfhack=rig.dfhack, call_tool=broken, registry=rig.env.registry)
    assert ob["state"] == "unknown" and rig.target_states(pid, f"{pid}/s2") == ["issued"]


# ---- cleanup / close -----------------------------------------------------------------


def abandon(rig, pid):
    from dfqueue.tests._helpers import make_abandon
    store.append(make_abandon(pid), rig.db)


async def _room_with_shell(rig):
    p, r, pid = await rig.open_room()
    s1 = f"{pid}/s1"
    await rig.run(pid, s1)
    await rig.tool("queue.observe", project_id=pid, step_id=s1)
    f1 = await rig.propose(rig.apply_step("res-1", SHELL), project_id=pid, after_step=s1)
    rig.rule(f1["id"])
    await rig.tool("queue.apply_followup", proposal_id=f1["id"])
    await rig.run(pid, f"{pid}/s2")
    return pid


async def test_cleanup_releases_what_the_project_issued_then_closes_with_the_results(rig):
    pid = await _room_with_shell(rig)
    with pytest.raises(queue_tools.QueueToolError, match="not an abandoned"):
        await rig.tool("queue.cleanup_project", project_id=pid)
    abandon(rig, pid)
    assert [a["project_id"] for a in store.projects_awaiting_cleanup(rig.db)] == [pid]
    _t, out = await rig.tool("queue.cleanup_project", project_id=pid)
    assert out["released"] == ["site-1"] and out["unreserved"] == ["res-1"] and out["failed"] == []
    assert rig.world.sites == {} and rig.world.reservations == {}
    close = [x for x in store.load(rig.db) if x["kind"] == "close" and x.get("project_id") == pid][0]
    assert close["outcome"] == "abandoned" and {c["handle"] for c in close["cleanup"]} == {"site-1", "res-1"}
    # newest first: the site is released before its reservation is freed
    order = [c[0] for c in rig.world.real_calls()]
    assert order.index("blueprint.release") < order.index("blueprint.unreserve")
    assert store.projects_awaiting_cleanup(rig.db) == []


async def test_a_second_cleanup_treats_already_gone_as_done(rig):
    pid = await _room_with_shell(rig)
    abandon(rig, pid)
    del rig.world.sites["site-1"]  # already released by hand
    _t, out = await rig.tool("queue.cleanup_project", project_id=pid)
    assert out["failed"] == [] and "res-1" in out["unreserved"]
    close = [x for x in store.load(rig.db) if x["kind"] == "close" and x.get("project_id") == pid][0]
    assert {c["handle"]: c["outcome"] for c in close["cleanup"]}["site-1"] == "already_gone"


async def test_a_failed_cleanup_keeps_the_project_open_and_retries_next_pass(rig):
    pid = await _room_with_shell(rig)
    abandon(rig, pid)
    rig.world.release_error = "the site is busy"
    _t, out = await rig.tool("queue.cleanup_project", project_id=pid)
    assert out["failed"] and out["failed"][0]["handle"] == "site-1" and out["close_id"] is None
    assert [a["project_id"] for a in store.projects_awaiting_cleanup(rig.db)] == [pid]
    rig.world.release_error = None
    _t, out = await rig.tool("queue.cleanup_project", project_id=pid)
    assert out["failed"] == [] and out["close_id"]


async def test_close_writes_a_close_record_and_touches_no_game_state(rig):
    p, r, pid = await rig.open_room()
    calls = len(rig.world.calls)
    _t, out = await rig.tool("queue.close", project_id=pid, outcome="completed", reason="idle for 7 game days")
    assert out["close_id"].startswith("close-") and len(rig.world.calls) == calls
    with pytest.raises(queue_tools.QueueToolError, match="project-N"):
        await rig.tool("queue.close", project_id="ruling-0001", outcome="completed", reason="x")
    assert (await rig.run(pid, f"{pid}/s1"))["class"] == "not_runnable"


# ---- execution_state and the WIP definition -------------------------------------------


async def test_execution_state_lists_ready_steps_and_what_finished_since(rig):
    p, r, pid = await rig.open_room()
    _t, st = await rig.tool("queue.execution_state")
    assert [{k: v for k, v in s.items() if k not in ("tool", "args")} for s in st["ready_steps"]] == [
        {"project_id": pid, "step_id": f"{pid}/s1", "urgency": "normal"}]
    assert st["open_projects"][0]["project_id"] == pid
    await rig.run(pid, f"{pid}/s1")
    await rig.tool("queue.observe", project_id=pid, step_id=f"{pid}/s1")
    _t, st = await rig.tool("queue.execution_state", since="observation-0000")
    assert st["ready_steps"] == [] and st["done_since"][0]["step_id"] == f"{pid}/s1"
    last = st["latest_observation_id"]
    _t, st = await rig.tool("queue.execution_state", since=last)
    assert st["done_since"] == []


async def test_pending_brief_wip_equals_the_stores_open_projects(rig):
    p, r, pid = await rig.open_room()
    _t, brief = await queue_tools.call(
        queue_tools.QUEUE_PENDING_BRIEF, "conductor", {}, db_path=rig.db, call_dfhack=rig.dfhack,
        write_lock=rig.lock, fact_reader=None)
    decided = brief["decided"]
    assert decided["wip_count"] == len(store.open_projects(rig.db)) == 1
    assert decided["open_projects"][0]["id"] == pid and decided["open_projects"][0]["urgency"] == "normal"
    await rig.tool("queue.close", project_id=pid, outcome="not_done", reason="test")
    _t, brief = await queue_tools.call(
        queue_tools.QUEUE_PENDING_BRIEF, "conductor", {}, db_path=rig.db, call_dfhack=rig.dfhack,
        write_lock=rig.lock, fact_reader=None)
    assert brief["decided"]["wip_count"] == 0 == len(store.open_projects(rig.db))


# ---- coverage ------------------------------------------------------------------------


async def test_a_follow_up_exactly_the_next_declared_phase_is_covered_once_coverage_is_on(rig):
    set_routing(rig.monkeypatch, rig.tmp_path, routed=True, coverage=True)
    p, r, pid = await rig.open_room()
    s1 = f"{pid}/s1"
    await rig.run(pid, s1)
    await rig.tool("queue.observe", project_id=pid, step_id=s1)
    f1 = await rig.propose(rig.apply_step("res-1", SHELL), project_id=pid, after_step=s1)
    assert f1["covered_by"] == s1  # the next declared phase, the handle issued, after the done step
    _t, fo = await rig.tool("queue.apply_followup", proposal_id=f1["id"])  # no ruling needed
    assert fo["step_id"] == f"{pid}/s2"
    # not covered: the step it follows (s2) is issued but not done
    rig.world.shell_dug = True
    f_bad = await rig.propose(rig.apply_step("res-1", FINISH), project_id=pid, after_step=f"{pid}/s2")
    assert "covered_by" not in f_bad


async def test_a_follow_up_is_not_covered_while_coverage_is_off(rig):
    p, r, pid = await rig.open_room()
    s1 = f"{pid}/s1"
    await rig.run(pid, s1)
    await rig.tool("queue.observe", project_id=pid, step_id=s1)
    f1 = await rig.propose(rig.apply_step("res-1", SHELL), project_id=pid, after_step=s1)
    assert "covered_by" not in f1
    with pytest.raises(queue_tools.QueueToolError, match="neither accepted nor covered"):
        await rig.tool("queue.apply_followup", proposal_id=f1["id"])


# ---- misc contracts ------------------------------------------------------------------


async def test_the_schema_offers_step_fields_only_once_a_group_is_routed(rig):
    props = queue_tools._propose_schema("architect")["properties"]
    assert {"step", "phases", "project_id", "after_step", "public_title", "urgency"} <= set(props)
    set_routing(rig.monkeypatch, rig.tmp_path, routed=False)
    assert "step" not in queue_tools._propose_schema("architect")["properties"]


async def test_a_step_on_an_unrouted_group_is_refused_by_the_store_with_nothing_written(rig):
    set_routing(rig.monkeypatch, rig.tmp_path, routed=False)
    with pytest.raises(queue_tools.QueueToolError, match="not routed yet"):
        await rig.propose(rig.reserve_step())
    assert rig.world.calls == []  # no dry run for a type that is not routed


async def test_run_step_needs_a_dfhack_route(rig):
    with pytest.raises(queue_tools.QueueToolError, match="without a DFHack route"):
        await et.call("queue.run_step", "conductor", {"project_id": "project-1", "step_id": "project-1/s1"},
                      db_path=rig.db, write_lock=rig.lock)


async def test_no_model_role_may_run_a_step(rig):
    for role in ("architect", "overseer", "quartermaster", "consultant"):
        with pytest.raises(queue_tools.QueueToolError, match="only the conductor"):
            await et.call("queue.run_step", role, {"project_id": "p", "step_id": "s"}, db_path=rig.db,
                          write_lock=rig.lock, call_dfhack=rig.dfhack, call_tool=rig.world.call_tool,
                          registry=rig.env.registry)


# ---- the five execution_state additions (handoffs/2026-10-06-execution-state-additions.md) ----


async def test_to_open_lists_an_accepted_routed_ruling_with_no_project_and_its_role(rig):
    p = await rig.propose(rig.reserve_step(), role="architect")
    _t, st = await rig.tool("queue.execution_state")
    assert st["to_open"] == []  # not ruled yet
    r = rig.rule(p["id"])
    _t, st = await rig.tool("queue.execution_state")
    assert st["to_open"] == [{"ruling_id": r["id"], "role": "architect"}]
    await rig.tool("queue.open_project", ruling_id=r["id"])
    _t, st = await rig.tool("queue.execution_state")
    assert st["to_open"] == []  # now it has a project


async def test_to_open_skips_rejected_and_the_legacy_ruling(rig):
    p = await rig.propose(rig.reserve_step())
    rig.rule(p["id"], decision="reject")
    _t, st = await rig.tool("queue.execution_state")
    assert st["to_open"] == []


async def test_to_apply_lists_an_accepted_follow_up_until_it_is_applied(rig):
    p, r, pid = await rig.open_room()
    s1 = f"{pid}/s1"
    await rig.run(pid, s1)
    f1 = await rig.propose(rig.apply_step("res-1", SHELL), project_id=pid, after_step=s1)
    _t, st = await rig.tool("queue.execution_state")
    assert st["to_apply"] == []  # filed, not ruled
    rig.rule(f1["id"])
    _t, st = await rig.tool("queue.execution_state")
    assert st["to_apply"] == [{"proposal_id": f1["id"]}]
    await rig.tool("queue.apply_followup", proposal_id=f1["id"])
    _t, st = await rig.tool("queue.execution_state")
    assert st["to_apply"] == []


async def test_issued_steps_are_listed_until_observed_done(rig):
    p, r, pid = await rig.open_room()
    s1 = f"{pid}/s1"
    _t, st = await rig.tool("queue.execution_state")
    assert st["issued_steps"] == []
    await rig.run(pid, s1)
    _t, st = await rig.tool("queue.execution_state")
    assert st["issued_steps"] == [{"project_id": pid, "step_id": s1}]
    await rig.tool("queue.observe", project_id=pid, step_id=s1)
    _t, st = await rig.tool("queue.execution_state")
    assert st["issued_steps"] == []


async def test_open_projects_carry_role_and_ready_steps_carry_tool_and_args(rig):
    p, r, pid = await rig.open_room()
    _t, st = await rig.tool("queue.execution_state")
    assert st["open_projects"][0]["role"] == "architect"
    (ready,) = st["ready_steps"]
    assert ready["tool"] == "blueprint.reserve" and ready["args"] == rig.reserve_step()["args"]
    # a later step's args (the ore hold reads phase and site) come from the amended plan
    s1 = f"{pid}/s1"
    await rig.run(pid, s1)
    await rig.tool("queue.observe", project_id=pid, step_id=s1)
    f1 = await rig.propose(rig.apply_step("res-1", SHELL), project_id=pid, after_step=s1)
    rig.rule(f1["id"])
    await rig.tool("queue.apply_followup", proposal_id=f1["id"])
    _t, st = await rig.tool("queue.execution_state")
    (ready,) = st["ready_steps"]
    assert ready["step_id"] == f"{pid}/s2" and ready["tool"] == "blueprint.apply"
    assert ready["args"]["phase"] == SHELL and ready["args"]["site"] == "res-1"


async def test_routing_block_matches_the_routing_module(rig):
    _t, st = await rig.tool("queue.execution_state")
    assert st["routing"] == {
        "routed_types": routing.routed_types(), "unrouted_types": routing.unrouted_types(),
        "frozen_types": [t for g in routing.groups() for t in routing.types(g) if routing.is_frozen(t)],
    }
    assert "room_siting" in st["routing"]["routed_types"]
    from conductor.briefing import routing_from_state
    assert routing_from_state(st) == st["routing"]


async def test_execution_state_additions_are_read_only(rig):
    p, r, pid = await rig.open_room()
    await rig.run(pid, f"{pid}/s1")
    before = store.load(rig.db)
    await rig.tool("queue.execution_state")
    assert store.load(rig.db) == before


async def test_conductor_phase_round_trips_the_state_end_to_end(rig):
    """conductor/execute.py's own parser, fed the real tool: it opens the ruled
    proposal, runs its step, reconciles it done and applies a follow-up."""
    from conductor.execute import ExecuteState, run_execute
    from conductor.policy import ExecutionPolicy

    calls = []

    async def call(tool, args):
        calls.append(tool)
        return (await rig.tool(tool, **args))[1]

    p = await rig.propose(rig.reserve_step(), phases={"tool": "blueprint.apply", "list": [SHELL, FINISH]})
    rig.rule(p["id"])
    state = ExecuteState()
    rep = await run_execute(call, ExecutionPolicy(), state, game_tick=100)
    assert not rep.errors and "queue.open_project" in calls and "queue.run_step" in calls
    (proj,) = store.open_projects(rig.db)
    pid, s1 = proj["project_id"], f"{proj['project_id']}/s1"
    assert state.roles[pid] == "architect"
    rep = await run_execute(call, ExecutionPolicy(), state, game_tick=200)
    assert "queue.observe" in calls and rig.target_states(pid, s1) == ["done"]
    f1 = await rig.propose(rig.apply_step("res-1", SHELL), project_id=pid, after_step=s1)
    rig.rule(f1["id"])
    rep = await run_execute(call, ExecutionPolicy(), state, game_tick=300)
    assert "queue.apply_followup" in calls and not rep.errors
    assert any(st["id"] == f"{pid}/s2" for st in store.current_plan_steps(rig.db, pid))


# ---- mining exposed ore (handoffs/2026-10-07-route-ore-mining.md) ----------------------


def mine_step(site="site-1"):
    return {"tool": "construction.mine-vein-site", "args": {"site_id": site}, "label": "Mine the exposed ore"}


async def test_a_dig_order_mining_step_is_dry_run_run_and_observed_done(rig):
    p = await rig.propose(mine_step(), type="dig_order")
    assert p["step"]["tool"] == "construction.mine-vein-site"
    r = rig.rule(p["id"])
    _t, out = await rig.tool("queue.open_project", ruling_id=r["id"])
    pid = out["project_id"]
    res = await rig.run(pid, f"{pid}/s1")
    assert res["class"] == "success" and not res.get("handle")
    real = rig.world.real_calls("construction.mine-vein-site")
    assert len(real) == 1 and real[0][1] == {"site_id": "site-1", "dry_run": "false"}
    assert rig.world.mined == ["site-1"]
    # no progress read is declared, so a step with no handle is done once issued
    _t, ob = await rig.tool("queue.observe", project_id=pid, step_id=f"{pid}/s1")
    assert ob["state"] == "done" and rig.target_states(pid, f"{pid}/s1") == ["done"]
    again = await rig.run(pid, f"{pid}/s1")
    assert again["class"] == "not_runnable"


async def test_a_mining_step_that_leaves_ore_held_or_refused_is_refused_at_filing(rig):
    rig.world.mine_held = ["ring tile 3: held (reservation) -- inside res-1"]
    with pytest.raises(Exception) as ei:
        await rig.propose(mine_step(), type="dig_order")
    assert "refused" in str(ei.value) and "construction.mine-vein-site" in str(ei.value)
    rig.world.mine_held = []
    rig.world.mine_refused = ["ring tile 4: vein classification unknown"]
    with pytest.raises(Exception):
        await rig.propose(mine_step(), type="dig_order")
    assert rig.world.real_calls("construction.mine-vein-site") == []


async def test_a_mining_step_may_not_carry_an_override(rig):
    bad = mine_step()
    bad["args"]["override"] = "because"
    with pytest.raises(Exception):
        await rig.propose(bad, type="dig_order")


async def test_a_real_mining_run_that_designated_nothing_is_a_retryable_failure(rig):
    p = await rig.propose(mine_step(), type="dig_order")
    r = rig.rule(p["id"])
    _t, out = await rig.tool("queue.open_project", ruling_id=r["id"])
    pid = out["project_id"]
    rig.world.mine_none_real = True
    res = await rig.run(pid, f"{pid}/s1")
    assert res["class"] == "failed" and res["retryable"] is True
    assert "could not confirm" in res["detail"]
