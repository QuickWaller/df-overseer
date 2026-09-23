"""Guard: every scripts/dfhack/*.lua tool that answers a reachability
question goes through the one shared helper, df-overseer-reachability.lua,
rather than copying dfhack.maps.canWalkBetween/getWalkableGroup logic per
file (handoffs/2026-09-23-landmark-reachability.md item 4: "One shared
helper... Do not copy the logic per tool").

Same static, grep-style approach as tests/test_game_text_utf8_helper.py
(read in full before writing this file, for the established convention):
this repo has no Lua interpreter available in this offline environment (no
`lua`/`lua5.1`/`lua5.3`/`luajit` on PATH, checked this session), so a test
of the real .lua bytes' behaviour has to be structural, not executed. What
this proves: the three files this stream was told to fix
(df-overseer-landmarks.lua, df-overseer-connectivity.lua,
df-overseer-threat.lua) reqscript the shared helper and no longer call the
two raw DFHack primitives themselves. It does NOT prove every other
scripts/dfhack/*.lua file that happens to also read walkable-group state
(df-overseer-breach.lua, df-overseer-harvest.lua, df-overseer-trees.lua,
df-overseer-openarea.lua, df-overseer-diggable.lua,
df-overseer-chokepoints.lua, df-overseer-building.lua, df-overseer-zone.lua,
df-overseer-stocks.lua all call dfhack.maps.getWalkableGroup directly, found
by grep this session) has been migrated -- that is a deliberate, stated
limit of this stream, not an oversight; see this stream's own report/Result
section in the handoff.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts" / "dfhack"

HELPER_FILE = "df-overseer-reachability.lua"

# The three files handoffs/2026-09-23-landmark-reachability.md names as
# "touched surfaces" for this fix. Each must reqscript the helper and must
# not call the raw DFHack primitives itself any more (the helper is the only
# place those calls should live).
FILES_THAT_MUST_USE_THE_HELPER = [
    "df-overseer-landmarks.lua",
    "df-overseer-connectivity.lua",
    "df-overseer-threat.lua",
]

_REQSCRIPT_RE = re.compile(r"""reqscript\(\s*['"]df-overseer-reachability['"]\s*\)""")
_RAW_CANWALKBETWEEN_RE = re.compile(r"dfhack\.maps\.canWalkBetween\b")
_RAW_GETWALKABLEGROUP_RE = re.compile(r"dfhack\.maps\.getWalkableGroup\b")


def _non_comment_lines(text: str):
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("--"):
            continue
        yield lineno, line


def _raw_primitive_hits(text: str):
    hits = []
    for lineno, line in _non_comment_lines(text):
        for pat in (_RAW_CANWALKBETWEEN_RE, _RAW_GETWALKABLEGROUP_RE):
            for m in pat.finditer(line):
                hits.append((lineno, m.group(0)))
    return hits


def test_helper_module_exists_and_exports_expected_functions():
    helper = SCRIPTS_DIR / HELPER_FILE
    assert helper.is_file(), f"expected shared helper at {helper}"
    text = helper.read_text(encoding="utf-8")
    assert "function resolve_group(" in text
    assert "function reachable_between(" in text
    assert "function group_matches(" in text
    # The helper is a library, not a CLI tool: loading it as a module (the
    # reqscript path every caller uses) must be side-effect-free, same guard
    # every other df-overseer-*.lua file in this repo uses.
    assert "if dfhack_flags.module then" in text


def test_helper_itself_is_the_only_place_calling_the_raw_primitives_among_the_three():
    """Within the three files this stream fixed, the raw DFHack primitives
    must not appear in live code any more -- only in the helper they now
    reqscript, and only in comments/docstrings within the fixed files
    themselves (explaining what changed)."""
    for name in FILES_THAT_MUST_USE_THE_HELPER:
        path = SCRIPTS_DIR / name
        assert path.is_file(), f"expected {path} to exist"
        text = path.read_text(encoding="utf-8")

        assert _REQSCRIPT_RE.search(text), (
            f"{name}: does not reqscript '{HELPER_FILE[:-4]}' -- every "
            "reachability-answering tool must use the shared helper "
            "(handoffs/2026-09-23-landmark-reachability.md item 4)"
        )

        hits = _raw_primitive_hits(text)
        assert not hits, (
            f"{name}: still calls a raw DFHack reachability primitive "
            f"directly instead of going through {HELPER_FILE} -- "
            f"{hits}"
        )


def test_helper_file_itself_still_calls_the_real_primitives():
    """Positive control: if df-overseer-reachability.lua ever stopped
    calling the real DFHack accessors (e.g. a bad refactor that emptied the
    functions), the test above would pass vacuously (no file calls them
    directly, because nothing calls them at all). This catches that."""
    helper = SCRIPTS_DIR / HELPER_FILE
    text = helper.read_text(encoding="utf-8")
    hits = _raw_primitive_hits(text)
    kinds = {h[1] for h in hits}
    assert "dfhack.maps.getWalkableGroup" in kinds
    # canWalkBetween is not used by the fixed implementation (group
    # comparison replaces it entirely -- see the helper's own header,
    # "THE FIX" paragraph) -- only asserted absent from the CALLERS above,
    # not required present here.


def test_landmarks_exit_field_is_a_tristate_not_a_bare_boolean():
    """The specific shape change build_exits makes: the old `walkable = ...`
    boolean field is gone, replaced by a `reachability` string field fed
    from the helper's tri-state status."""
    path = SCRIPTS_DIR / "df-overseer-landmarks.lua"
    text = path.read_text(encoding="utf-8")
    assert "walkable = ok_walk and walkable or false" not in text
    assert "reachability = result.status" in text


def test_connectivity_check_functions_return_status_not_bare_boolean():
    path = SCRIPTS_DIR / "df-overseer-connectivity.lua"
    text = path.read_text(encoding="utf-8")
    assert "reachable = dfhack.maps.canWalkBetween" not in text
    assert "reachability.reachable_between(" in text


def test_threat_citizen_groups_and_scan_loop_use_the_shared_resolver():
    path = SCRIPTS_DIR / "df-overseer-threat.lua"
    text = path.read_text(encoding="utf-8")
    assert "reachability.resolve_group(" in text
    assert "reachability.group_matches(" in text
