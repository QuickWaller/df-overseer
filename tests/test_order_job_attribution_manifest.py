"""Manifest and dispatch checks for
handoffs/2026-09-23-order-job-attribution-and-checks.md: order status
fields, job.order_id attribution, the duplicate-production check, and the
workjob.cancel verb.

Same convention as tests/test_zone_tool_manifest.py: the Lua cannot be
executed in this suite (no DFHack process), so these tests pin what CAN be
checked offline.

1. Every new/changed TOOLS.yaml command for df-overseer-orders.lua,
   df-overseer-workjob.lua and df-overseer-stuckjobs.lua has a matching
   dispatch branch in its Lua file and a defined function.
2. `df.job`'s own `order_id` field (this stream's corrected finding) is read
   the same one way in every file that reports job origin -- one shared
   helper (`job_origin`, df-overseer-stuckjobs.lua), not a special case per
   tool (CLAUDE.md's generalisability rule).
3. No `ok and boolean_value or nil` idiom on the new boolean fields
   (validated/active/from_order): that Lua idiom silently turns a real
   `false` into `nil`, which would be exactly backwards for a status bit.
4. workjob.cancel refuses a job with no resolvable workshop holder, rather
   than cancelling it (the "not this fort's own queued work" refusal the
   handoff asks for).
5. No raw coordinate reaches a result table (design commitment #1).
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dfmcp.registry import load_registry  # noqa: E402

ORDERS_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-orders.lua"
WORKJOB_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-workjob.lua"
STUCKJOBS_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-stuckjobs.lua"

ORDERS_IDS = {"orders.list", "orders.create", "orders.cancel", "orders.check-duplicate"}
WORKJOB_IDS = {"workjob.list", "workjob.list-jobs", "workjob.queue", "workjob.cancel"}
# workjob.list-jobs added by handoffs/2026-09-21-workjob-generalise.md
# (dispatched 2026-09-23): the job vocabulary is now read live from DFHack's
# own workshops.getJobs, not a hand-maintained table. See that file's own
# header. This set, and workjob.queue's args below, were updated by that
# stream to keep this manifest test accurate against the file it shares
# with -- the invariants this file actually checks (job_origin reuse, the
# `ok and v or nil` boolean trap, no coordinate leak, workjob.cancel's
# refusal behaviour) are untouched by that stream and still hold.
STUCKJOBS_IDS = {"stuckjobs.find"}


def _text(path):
    return path.read_text(encoding="utf-8")


def _dispatch_verbs(lua_text):
    return set(re.findall(r'cmd == "([a-z-]+)"', lua_text))


def test_orders_commands_are_in_the_manifest():
    reg = load_registry()
    for tool_id in ORDERS_IDS:
        assert tool_id in reg, f"{tool_id} missing from scripts/dfhack/TOOLS.yaml"


def test_workjob_commands_are_in_the_manifest():
    reg = load_registry()
    for tool_id in WORKJOB_IDS:
        assert tool_id in reg, f"{tool_id} missing from scripts/dfhack/TOOLS.yaml"


def test_orders_manifest_and_dispatch_agree():
    reg = load_registry()
    manifest = {t.id.split(".", 1)[1] for t in reg.all() if t.script == "df-overseer-orders.lua"}
    assert manifest == {i.split(".", 1)[1] for i in ORDERS_IDS}
    assert manifest == _dispatch_verbs(_text(ORDERS_LUA))


def test_workjob_manifest_and_dispatch_agree():
    reg = load_registry()
    manifest = {t.id.split(".", 1)[1] for t in reg.all() if t.script == "df-overseer-workjob.lua"}
    assert manifest == {i.split(".", 1)[1] for i in WORKJOB_IDS}
    assert manifest == _dispatch_verbs(_text(WORKJOB_LUA))


def test_lua_functions_named_in_the_manifest_exist():
    reg = load_registry()
    for tool_id, path in [
        *((i, ORDERS_LUA) for i in ORDERS_IDS),
        *((i, WORKJOB_LUA) for i in WORKJOB_IDS),
        *((i, STUCKJOBS_LUA) for i in STUCKJOBS_IDS),
    ]:
        tool = reg.get(tool_id)
        src = _text(path)
        assert re.search(rf"function\s+{re.escape(tool.lua_function)}\s*\(", src), (
            f"{tool_id}: lua_function {tool.lua_function!r} not defined in {path.name}"
        )


def test_check_duplicate_and_cancel_signatures():
    reg = load_registry()
    assert reg.get("orders.check-duplicate").args == ["JOB"]
    assert reg.get("workjob.cancel").args == ["JOB_ID", "[DRY_RUN]"]
    assert reg.get("workjob.queue").args == [
        "JOB", "WORKSHOP_LANDMARK_NAME", "[DRY_RUN]", "[REPEAT]", "[COUNT]",
    ]


def test_effects_and_coordinate_bearing():
    reg = load_registry()
    assert reg.get("orders.check-duplicate").effect == "read"
    assert reg.get("workjob.cancel").effect == "mutate"
    for tool_id in ORDERS_IDS | WORKJOB_IDS | STUCKJOBS_IDS:
        tool = reg.get(tool_id)
        assert tool.coordinate_bearing is False, tool_id
        assert tool.knowledge_scope in ("player_visible", "player_derivable")
        assert not tool.is_omniscient


# --------------------------------------------------------------------------
# job_origin: the one shared attribution helper
# --------------------------------------------------------------------------


def test_job_origin_is_defined_once_in_stuckjobs():
    src = _text(STUCKJOBS_LUA)
    assert len(re.findall(r"^function job_origin\(job\)", src, flags=re.M)) == 1


def test_get_stuck_jobs_and_find_jobs_by_type_both_use_job_origin():
    src = _text(STUCKJOBS_LUA)
    get_stuck = src[src.index("function get_stuck_jobs"): src.index("-- Added handoffs/2026-09-23")]
    find_by_type = src[src.index("function find_jobs_by_type"): src.index("-- Same module-load guard")]
    assert "job_origin(job)" in get_stuck
    assert "job_origin(job)" in find_by_type


def test_workjob_cancel_reuses_stuckjobs_job_origin_not_a_second_implementation():
    src = _text(WORKJOB_LUA)
    assert "reqscript('df-overseer-stuckjobs')" in src
    assert "stuckjobs_mod.job_origin(job)" in src
    # no local re-implementation of the order_id sentinel logic in this file
    assert "job.order_id" not in src


def test_orders_check_duplicate_reuses_find_jobs_by_type():
    src = _text(ORDERS_LUA)
    assert "reqscript('df-overseer-stuckjobs')" in src
    assert "stuckjobs_mod.find_jobs_by_type" in src


# --------------------------------------------------------------------------
# The `ok and boolean or nil` trap: a real regression risk on this stream's
# own new boolean fields (validated/active/from_order).
# --------------------------------------------------------------------------


def test_no_and_or_shortcut_on_the_new_boolean_fields():
    for path, fields in (
        (ORDERS_LUA, ("validated", "active")),
        (STUCKJOBS_LUA, ("from_order",)),
    ):
        src = _text(path)
        for field in fields:
            # the buggy shape: `out.field = ok_x and x or nil` / `field = X and Y or nil`
            assert not re.search(rf"\b{field}\s*=\s*ok_\w+\s+and\s+\w+\s+or\s+nil", src), (
                f"{path.name}: {field!r} looks like it uses the `ok and v or nil` idiom, "
                "which turns a real `false` into `nil`"
            )


# --------------------------------------------------------------------------
# workjob.cancel: refuses non-workshop jobs rather than cancelling them
# --------------------------------------------------------------------------


def test_cancel_job_refuses_jobs_with_no_workshop_holder():
    src = _text(WORKJOB_LUA)
    body = src[src.index("function cancel_job"): src.index("-- Same module-load guard as every other df-overseer-*.lua script.\nif dfhack_flags.module then\n  return\nend\n\nlocal args = {...}\nlocal cmd = args[1]\n\nif cmd == \"list\"")]
    assert "has no workshop holder" in body
    assert "df.building_type.Workshop" in body


# --------------------------------------------------------------------------
# No raw coordinates in any new result table (design commitment #1)
# --------------------------------------------------------------------------


def test_no_raw_coordinates_in_new_orders_code():
    src = _text(ORDERS_LUA)
    tail = src[src.index("function check_duplicate"):]
    for forbidden in ("x = ", "y = ", "z = ", "pos = ", "coordinate ="):
        for m in re.finditer(re.escape(forbidden), tail):
            line = tail[tail.rfind("\n", 0, m.start()) + 1: tail.find("\n", m.end())]
            assert not re.match(r"^\s+(x|y|z|pos)\s*=", line), f"possible coordinate leak: {line.strip()}"


def test_no_raw_coordinates_in_new_workjob_code():
    src = _text(WORKJOB_LUA)
    tail = src[src.index("function cancel_job"):]
    for forbidden in ("x = ", "y = ", "z = ", "pos = ", "coordinate ="):
        for m in re.finditer(re.escape(forbidden), tail):
            line = tail[tail.rfind("\n", 0, m.start()) + 1: tail.find("\n", m.end())]
            assert not re.match(r"^\s+(x|y|z|pos)\s*=", line), f"possible coordinate leak: {line.strip()}"
