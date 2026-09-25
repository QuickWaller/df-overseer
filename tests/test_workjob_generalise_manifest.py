"""Manifest and static checks for
handoffs/2026-09-21-workjob-generalise.md: workjob's job vocabulary is now
read live from DFHack's own workshops.getJobs, not a hand-maintained table.

Same convention as tests/test_zone_tool_manifest.py and
tests/test_order_job_attribution_manifest.py: the Lua cannot be executed in
this suite (no DFHack process), so these tests pin what CAN be checked
offline.

1. workjob.list-jobs is registered, has a dispatch branch and a defined
   function; workjob.queue's args gained COUNT; workjob.list is untouched
   (no-arg, still the three legacy tokens).
2. The tool's own point: no second hand-maintained job table. LEGACY_ALIASES
   holds exactly the three backward-compat tokens (blocks/mechanisms/
   brew_drink) -- the old twelve-or-fewer-entry JOB_INFO table is gone.
3. The generic path is real: workshops.getJobs (require('dfhack.workshops'))
   is actually called, not merely mentioned in a comment.
4. df-overseer-stocks.lua's get_availability is reused for item
   availability, not re-derived (CLAUDE.md's generalisability rule).
5. Every new guarded-read site reports failures via read_failures plus
   dfhack.printerr, per docs/TRAPS.md's pcall-degrades-to-false entry --
   never a silent default.
6. No raw coordinate reaches a result table (design commitment #1).
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dfmcp.registry import load_registry  # noqa: E402

WORKJOB_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-workjob.lua"

WORKJOB_IDS = {"workjob.list", "workjob.list-jobs", "workjob.queue", "workjob.cancel"}


def _text(path):
    return path.read_text(encoding="utf-8")


def _dispatch_verbs(lua_text):
    return set(re.findall(r'cmd == "([a-z-]+)"', lua_text))


def test_workjob_commands_are_in_the_manifest():
    reg = load_registry()
    for tool_id in WORKJOB_IDS:
        assert tool_id in reg, f"{tool_id} missing from scripts/dfhack/TOOLS.yaml"


def test_workjob_manifest_and_dispatch_agree():
    reg = load_registry()
    manifest = {t.id.split(".", 1)[1] for t in reg.all() if t.script == "df-overseer-workjob.lua"}
    assert manifest == {i.split(".", 1)[1] for i in WORKJOB_IDS}
    assert manifest == _dispatch_verbs(_text(WORKJOB_LUA))


def test_lua_functions_named_in_the_manifest_exist():
    reg = load_registry()
    src = _text(WORKJOB_LUA)
    for tool_id in WORKJOB_IDS:
        tool = reg.get(tool_id)
        assert re.search(rf"function\s+{re.escape(tool.lua_function)}\s*\(", src), (
            f"{tool_id}: lua_function {tool.lua_function!r} not defined in {WORKJOB_LUA.name}"
        )


def test_list_jobs_is_the_new_command_list_is_untouched():
    reg = load_registry()
    assert reg.get("workjob.list").args == []
    assert reg.get("workjob.list").lua_function == "list_jobs"
    assert reg.get("workjob.list-jobs").args == ["WORKSHOP_LANDMARK_NAME"]
    assert reg.get("workjob.list-jobs").lua_function == "list_workshop_jobs"


def test_queue_args_gained_count_after_the_existing_four():
    reg = load_registry()
    assert reg.get("workjob.queue").args == [
        "JOB", "WORKSHOP_LANDMARK_NAME", "[DRY_RUN]", "[REPEAT]", "[COUNT]",
        "[REAGENT_CHOICE...]",
    ]


def test_cancel_is_unchanged():
    reg = load_registry()
    assert reg.get("workjob.cancel").args == ["JOB_ID", "[DRY_RUN]"]


def test_effects_and_coordinate_bearing():
    reg = load_registry()
    assert reg.get("workjob.list").effect == "read"
    assert reg.get("workjob.list-jobs").effect == "read"
    assert reg.get("workjob.queue").effect == "mutate"
    assert reg.get("workjob.cancel").effect == "mutate"
    for tool_id in WORKJOB_IDS:
        tool = reg.get(tool_id)
        assert tool.coordinate_bearing is False, tool_id
        assert tool.knowledge_scope in ("player_visible", "player_derivable")
        assert not tool.is_omniscient


# --------------------------------------------------------------------------
# The tool's own point: the job vocabulary comes from the game, not a
# second hand-maintained table. A table of twelve (or three, or any fixed
# N) here would mean this stream failed its own stated test.
# --------------------------------------------------------------------------


def test_no_second_hand_maintained_job_table():
    src = _text(WORKJOB_LUA)
    # The header prose is allowed to mention JOB_INFO historically (what
    # this stream removed and why); what must not exist is the table
    # declaration itself.
    assert not re.search(r"^local JOB_INFO\s*=\s*\{", src, flags=re.M), (
        "the old hand-maintained job table (JOB_INFO) should be gone entirely, "
        "replaced by a live read of workshops.getJobs"
    )


def test_legacy_aliases_are_exactly_the_three_backward_compat_tokens():
    src = _text(WORKJOB_LUA)
    m = re.search(r"local LEGACY_ALIASES = \{(.*?)\n\}", src, flags=re.S)
    assert m, "LEGACY_ALIASES table not found"
    body = m.group(1)
    keys = set(re.findall(r"^\s*(\w+)\s*=\s*\{", body, flags=re.M))
    assert keys == {"blocks", "mechanisms", "brew_drink"}


def test_getjobs_is_actually_called_not_just_mentioned():
    src = _text(WORKJOB_LUA)
    assert "require('dfhack.workshops')" in src
    assert "workshops_mod.getJobs" in src


def test_stocks_availability_is_reused_not_rederived():
    src = _text(WORKJOB_LUA)
    assert "reqscript('df-overseer-stocks')" in src
    assert "stocks_mod.get_availability" in src
    # No second per-flag netting engine grown in this file.
    assert "count_availability" not in src
    assert "checked_flag" not in src


# --------------------------------------------------------------------------
# Unknown is never zero: every new guarded-read site reports failures
# explicitly, per docs/TRAPS.md's pcall-degrades-to-false entry.
# --------------------------------------------------------------------------


def test_read_failures_collected_and_relayed_in_list_and_queue():
    src = _text(WORKJOB_LUA)
    list_body = src[src.index("function list_workshop_jobs"): src.index("-- Resolves a requested JOB token")]
    assert "read_failures" in list_body
    assert "dfhack.printerr" in list_body

    queue_body = src[src.index("function queue_job"): src.index("-- Finds a live job by id")]
    assert "read_failures" in queue_body
    assert "dfhack.printerr" in queue_body


def test_job_item_from_spec_reports_read_failures_never_silent_default():
    src = _text(WORKJOB_LUA)
    body = src[src.index("local function job_item_from_spec"): src.index("-- Builds every job_item")]
    assert "read_failures" in body
    # every branch that sets a numeric default also records the failure
    assert body.count("table.insert(read_failures") >= 3


# --------------------------------------------------------------------------
# No raw coordinates in any new result table (design commitment #1)
# --------------------------------------------------------------------------


def test_no_raw_coordinates_in_new_workjob_code():
    src = _text(WORKJOB_LUA)
    tail = src[src.index("-- GENERALISED handoffs/2026-09-21-workjob-generalise.md"):]
    for forbidden in ("x = ", "y = ", "z = ", "pos = ", "coordinate ="):
        for m in re.finditer(re.escape(forbidden), tail):
            line = tail[tail.rfind("\n", 0, m.start()) + 1: tail.find("\n", m.end())]
            assert not re.match(r"^\s+(x|y|z|pos)\s*=", line), f"possible coordinate leak: {line.strip()}"
