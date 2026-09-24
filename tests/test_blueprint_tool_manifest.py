"""Manifest, grant and structural checks for the blueprint verb.

handoffs/2026-09-24-blueprint-hands.md. The Lua cannot run in the test suite
(it needs a DFHack process), so these tests pin what can be checked offline,
in the shape of tests/test_surface_tool_manifest.py and
tests/test_zone_tool_manifest.py:

1. Manifest and Lua dispatch agree; every named function exists.
2. Effects and grants. `apply` mutates and is the overseer's alone; the
   Architect gets the four reads and never `apply`. (dfmcp/roles.py rule 2
   refuses a mutating grant to any role but the roster's sole writer, and the
   2026-09-24 register keeps the Architect propose-only.)
3. Design commitment #1: no coordinate reaches a result table, none is
   printed, and the one place a coordinate string is formatted is the
   quickfort call.
4. The surface shim's contract: it works only because df-overseer-surface's
   `find_zone` is a module local that the three reads call and whose result
   they read only x1/y1/x2/y2/z/id off. Pinned here so a rename or a new field
   fails offline instead of silently breaking the re-read on the guest.
5. The soil rule and the order guard are data and mode driven, not per-room:
   no room-kind word appears in the code, and the smoothable material set is
   the one quickfort uses (dig.lua:77-87).
6. The template the verb is built for parses, by an independent Python mirror
   of the Lua's parse rules, to the facts the Lua derives from it.
7. Every argument has a description and the argv for the calls a caller will
   really make comes out in the right positions.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dfmcp.registry import load_registry  # noqa: E402
from dfmcp.roles import load_roster  # noqa: E402
from dfmcp.tools import _arg_specs_for_tool, argv_for_call  # noqa: E402
from dfmcp.queue_tools import NATIVE_TOOLS as QUEUE_NATIVE_TOOLS  # noqa: E402
from dfmcp.doctrine_tools import NATIVE_TOOLS as DOCTRINE_NATIVE_TOOLS  # noqa: E402
from dfmcp.series_tools import NATIVE_TOOLS as SERIES_NATIVE_TOOLS  # noqa: E402
from dfmcp.gotchas_tools import NATIVE_TOOLS as GOTCHAS_NATIVE_TOOLS  # noqa: E402
from dfmcp.knowledge_tools import NATIVE_TOOLS as KNOWLEDGE_NATIVE_TOOLS  # noqa: E402

LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-blueprint.lua"
SURFACE_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-surface.lua"
TEMPLATE_CSV = REPO_ROOT / "blueprints" / "templates" / "bedroom-cell-v1.csv"

READ_IDS = {"blueprint.plan", "blueprint.preview", "blueprint.sites", "blueprint.status"}
APPLY_ID = "blueprint.apply"
ALL_IDS = READ_IDS | {APPLY_ID}


def _text():
    return LUA.read_text(encoding="utf-8")


def _code():
    """The Lua with `--` comments removed."""
    return "\n".join(re.sub(r"--.*$", "", line) for line in _text().splitlines())


def _dispatch_verbs(lua_text):
    return set(re.findall(r'cmd == "([a-z-]+)"', lua_text))


def _all_native_tools():
    return {
        **QUEUE_NATIVE_TOOLS,
        **DOCTRINE_NATIVE_TOOLS,
        **SERIES_NATIVE_TOOLS,
        **GOTCHAS_NATIVE_TOOLS,
        **KNOWLEDGE_NATIVE_TOOLS,
    }


def _roster():
    return load_roster(load_registry(native_tools=_all_native_tools()))


# --- 1. manifest and dispatch ------------------------------------------------


def test_commands_are_in_the_manifest():
    reg = load_registry()
    for tool_id in ALL_IDS:
        assert tool_id in reg, f"{tool_id} missing from scripts/dfhack/TOOLS.yaml"


def test_manifest_and_dispatch_agree():
    reg = load_registry()
    manifest = {t.id.split(".", 1)[1] for t in reg.all() if t.script == "df-overseer-blueprint.lua"}
    assert manifest == {i.split(".", 1)[1] for i in ALL_IDS}
    assert manifest == _dispatch_verbs(_text())


def test_lua_functions_named_in_the_manifest_exist():
    reg = load_registry()
    src = _text()
    for tool_id in ALL_IDS:
        fn = reg.get(tool_id).lua_function
        assert re.search(rf"function\s+{re.escape(fn)}\s*\(", src), f"{tool_id}: {fn!r} not defined"


def test_manifest_signatures_match_the_lua_usage_lines():
    reg = load_registry()
    usage = _text()
    for tool_id in ALL_IDS:
        tool = reg.get(tool_id)
        verb = tool_id.split(".", 1)[1]
        line = f"df-overseer-blueprint {verb}"
        if tool.args:
            line += " " + " ".join(tool.args)
        assert line in usage, tool.command


# --- 2. effects and grants ---------------------------------------------------


def test_only_apply_mutates():
    reg = load_registry()
    for tool_id in READ_IDS:
        tool = reg.get(tool_id)
        assert tool.effect == "read" and not tool.mutates, tool_id
        assert not tool.is_omniscient, tool_id
    apply_tool = reg.get(APPLY_ID)
    assert apply_tool.effect == "mutate" and apply_tool.mutates


def test_no_tool_is_coordinate_bearing_in_the_open():
    reg = load_registry()
    for tool_id in ALL_IDS:
        assert reg.get(tool_id).coordinate_bearing in (False, "internal-only"), tool_id


def test_architect_gets_the_reads_and_never_apply():
    roster = _roster()
    for tool_id in READ_IDS:
        allowed, reason = roster.check("architect", tool_id)
        assert allowed, f"architect should be granted {tool_id}: {reason}"
    allowed, _ = roster.check("architect", APPLY_ID)
    assert not allowed, "the Architect stays propose-only; apply is the overseer's"


def test_overseer_gets_everything():
    roster = _roster()
    for tool_id in ALL_IDS:
        allowed, reason = roster.check("overseer", tool_id)
        assert allowed, f"overseer should be granted {tool_id}: {reason}"


def test_nobody_else_is_granted_any_of_it():
    roster = _roster()
    for role in ("consultant", "quartermaster", "conductor"):
        for tool_id in ALL_IDS:
            allowed, _ = roster.check(role, tool_id)
            assert not allowed, f"{role} must not hold {tool_id}"


# --- 3. no coordinates -------------------------------------------------------


def _body(code, header):
    start = code.index(header)
    end = code.index("\nend", start)
    return code[start:end]


def test_the_only_coordinate_string_is_the_quickfort_call():
    code = _code()
    assert code.count("%d,%d,%d") == 1
    assert "%d,%d,%d" in _body(code, "local function run_quickfort")


def test_nothing_but_the_emit_helpers_prints():
    code = _code()
    for m in re.finditer(r"\bprint\(", code):
        line = code[code.rfind("\n", 0, m.start()) + 1: code.find("\n", m.end())]
        assert ("encode(" in line) or ("USAGE" in line) or ("print(l)" in line), line.strip()


def test_result_tables_carry_no_position_fields():
    """No x/y/z/pos key is ever assigned into a result the caller receives.
    The internal site record ({x, y, z, w, h}) is built in find_new_site and
    stored in state, never assigned into `result`."""
    code = _code()
    for m in re.finditer(r"\bresult(?:\.site)?\.(x|y|z|pos|coord\w*)\s*=", code):
        raise AssertionError("coordinate written into a result: " + m.group(0))
    for header in ("local function site_brief(", "function list_sites(", "function site_status("):
        body = _body(code, header)
        for m in re.finditer(r"[{,]\s*(x|y|z|pos)\s*=", body):
            raise AssertionError(f"{header}: possible coordinate leak: {m.group(0)}")


def test_raw_quickfort_output_is_never_forwarded():
    code = _code()
    assert "output:gmatch" in code and "^  ([^:]-): (%d+)%s*$" in code
    body = _body(code, "local function run_quickfort")
    assert "parse_stats(output)" in body
    assert body.count("output") <= 4


# --- 4. the surface shim contract -------------------------------------------


def test_shim_contract_holds_in_the_surface_layer():
    surface = SURFACE_LUA.read_text(encoding="utf-8")
    assert re.search(r"^local function find_zone\(", surface, re.M), "find_zone must stay a module local"
    for fn in ("enclosure", "finish", "boundary_material"):
        start = surface.index(f"\nfunction {fn}(")
        end = surface.index("\nend", start)
        assert "find_zone(zone_id)" in surface[start:end], fn
    fields = set(re.findall(r"\bb\.([a-z][a-z0-9_]*)", surface))
    supplied = {"x1", "y1", "x2", "y2", "z", "id"}
    assert fields <= supplied, (
        f"surface now reads {fields - supplied} off the zone; "
        "the blueprint verb's rectangle shim does not supply it"
    )
    assert "upvalue_by_name(fns.enclosure, 'find_zone')" in _text()
    assert "shim_restored" in _text()


# --- 5. generic by rule ------------------------------------------------------


def test_no_room_kind_appears_in_code():
    code = _code().lower()
    for word in ("bedroom", "office", "dining", "barracks", "tomb", "farm", "workshop"):
        assert word not in code, f"room-specific word {word!r} in code"


def test_soil_is_not_named_in_code_and_the_smoothable_set_is_quickforts():
    code = _code()
    assert "SOIL" not in code, "the soil rule must fall out of the smoothable set, not a branch"
    m = re.search(r"for _, name in ipairs\(\{([^}]*)\}\)", code)
    names = set(re.findall(r'"([A-Z_]+)"', m.group(1)))
    assert names == {"STONE", "FEATURE", "LAVA_STONE", "MINERAL", "FROZEN_LIQUID"}


def test_order_guard_is_by_mode():
    code = _code()
    m = re.search(r"local NEEDS_DUG_SHELL = \{([^}]*)\}", code)
    assert set(re.findall(r"(\w+) = true", m.group(1))) == {"build", "place", "zone"}


def test_finish_requirement_is_the_blueprints_own_smooth_cells():
    code = _code()
    assert "local SMOOTH_SYMBOL = 's'" in code
    assert "c.text == SMOOTH_SYMBOL" in code


def test_label_is_passed_in_sheet_slash_label_form():
    # a bare label is read by quickfort as a sheet name (research doc, section 1)
    assert "'/' .. label" in _code()


def test_read_failures_are_recorded_not_defaulted():
    code = _code()
    assert "read_failures" in code
    assert "dfhack.printerr" in code
    assert "local function note_failure" in code


def test_blueprint_name_cannot_be_a_path():
    assert "s:match('^[%w_%-]+$')" in _code()


def test_dry_run_flag_reaches_quickfort():
    code = _code()
    assert "argv[#argv + 1] = '-d'" in code
    assert "truthy_dry_run" in code


# --- 6. the template, through an independent mirror of the Lua's parse -------


VALID_MODES = {"dig", "build", "place", "zone", "burrow", "meta", "notes", "ignore", "aliases"}
GRID_MODES = {"dig", "build", "place", "zone", "meta"}


def _py_parse(text):
    sections, cur = [], None
    for line in text.replace("\r", "").split("\n"):
        m = re.match(r"^#([A-Za-z]+)", line)
        if m and m.group(1) in VALID_MODES:
            lab = re.search(r"label\(([^)]*)\)", line)
            cur = {"mode": m.group(1), "label": lab.group(1) if lab else str(len(sections) + 1),
                   "cells": [], "row": 0}
            sections.append(cur)
        elif cur and cur["mode"] in GRID_MODES:
            cur["row"] += 1
            for x, cell in enumerate(line.split(","), 1):
                t = cell.strip()
                if t.startswith("#"):
                    break
                if t and t != "`":
                    cur["cells"].append((x, cur["row"], t))
    return sections


def test_bedroom_template_parses_to_what_the_lua_derives():
    secs = _py_parse(TEMPLATE_CSV.read_text(encoding="utf-8"))
    by = {s["label"]: s for s in secs}
    assert [s["mode"] for s in secs] == ["notes", "dig", "zone", "build", "meta"]
    dig = by["bedroom_cell_v1_shell"]
    assert max(x for x, _, _ in dig["cells"]) == 5 and max(y for _, y, _ in dig["cells"]) == 5
    # 15 wall cells asked to be smoothed: the 16-tile ring minus the entrance gap
    assert sum(1 for _, _, t in dig["cells"] if t == "s") == 15
    carve = [t for _, _, t in dig["cells"] if t in {"d", "h", "u", "j", "i", "r"}]
    assert len(carve) == 10  # 3x3 interior plus the entrance gap... 9 + 1
    zone = by["bedroom_cell_v1_zone"]
    xs = [x for x, _, _ in zone["cells"]]
    ys = [y for _, y, _ in zone["cells"]]
    assert (min(xs), max(xs), min(ys), max(ys)) == (2, 4, 2, 4)  # the 3x3 interior
    meta = by["bedroom_cell_v1_finish"]
    ordered = sorted(meta["cells"], key=lambda c: (c[1], c[0]))
    assert [t.lstrip("/") for _, _, t in ordered] == ["bedroom_cell_v1_zone", "bedroom_cell_v1_build"]


def test_the_template_phases_need_a_dug_shell_by_mode():
    secs = {s["label"]: s for s in _py_parse(TEMPLATE_CSV.read_text(encoding="utf-8"))}
    needs = {"build", "place", "zone"}
    assert secs["bedroom_cell_v1_shell"]["mode"] not in needs
    for label in ("bedroom_cell_v1_zone", "bedroom_cell_v1_build"):
        assert secs[label]["mode"] in needs


# --- 7. arguments and argv ---------------------------------------------------


def test_every_argument_has_a_description():
    reg = load_registry()
    for tool_id in ALL_IDS:
        for spec in _arg_specs_for_tool(reg.get(tool_id)):
            assert spec.description, f"{tool_id}: argument {spec.name} has no description"


def test_argv_for_the_calls_a_caller_makes():
    reg = load_registry()
    apply_tool, preview = reg.get(APPLY_ID), reg.get("blueprint.preview")
    assert argv_for_call(preview, {"template": "bedroom-cell-v1", "phase": "bedroom_cell_v1_shell",
                                   "site": "Well", "level": 0, "rank": 2}) == [
        "df-overseer-blueprint", "preview", "bedroom-cell-v1", "bedroom_cell_v1_shell", "Well", "0", "2"]
    # a real apply against a handle needs nothing after DRY_RUN
    assert argv_for_call(apply_tool, {"template": "bedroom-cell-v1", "phase": "bedroom_cell_v1_finish",
                                      "site": "site-1", "dry_run": "false"}) == [
        "df-overseer-blueprint", "apply", "bedroom-cell-v1", "bedroom_cell_v1_finish", "site-1", "false"]
    # the default (dry) needs no optional at all
    assert argv_for_call(apply_tool, {"template": "t", "phase": "p", "site": "Well"}) == [
        "df-overseer-blueprint", "apply", "t", "p", "Well"]
