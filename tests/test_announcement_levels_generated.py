"""Regression for scripts/gen_announcement_pause_slow.py and its output,
scripts/dfhack/df-overseer-announcement-levels.lua
(handoffs/2026-09-23-attention-tiers-ingame.md item 2).

Proves three things: (1) the committed .lua file is byte-identical to a
fresh run of the generator -- the drift guard the handoff asked for; (2)
the pause/slow id counts match the severity classification's own bottom
line (25/23); (3) CITIZEN_DEATH (106) and PET_DEATH (107) are both in the
pause set, which is what lets df-overseer-clock.lua's step 4 dual-arm the
existing roster-diff death check for free (see that file's own step-1
comment).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GEN_SCRIPT = REPO_ROOT / "scripts" / "gen_announcement_pause_slow.py"
LUA_PATH = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-announcement-levels.lua"


def _load_generator_module():
    spec = importlib.util.spec_from_file_location("gen_announcement_pause_slow", GEN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_committed_lua_file_matches_a_fresh_regeneration():
    gen = _load_generator_module()
    generated = gen.build_lua_source()
    current = LUA_PATH.read_text(encoding="utf-8")
    assert current == generated, (
        "scripts/dfhack/df-overseer-announcement-levels.lua has drifted from "
        "the generator -- run `python scripts/gen_announcement_pause_slow.py`"
    )


def test_pause_and_slow_counts_match_the_severity_classification_bottom_line():
    gen = _load_generator_module()
    types = gen._load_types()
    pause_ids = [v["id"] for v in types.values() if v.get("level") == "pause"]
    slow_ids = [v["id"] for v in types.values() if v.get("level") == "slow"]
    # research/2026-09-23-announcement-severity.md's own bottom-line table.
    assert len(pause_ids) == 25
    assert len(slow_ids) == 23


def test_citizen_death_and_pet_death_are_pause_level():
    """The dual-arming this stream relies on for item 5 (the death
    tripwire): CITIZEN_DEATH/PET_DEATH must land in PAUSE_REPORT_IDS."""
    gen = _load_generator_module()
    types = gen._load_types()
    assert types["CITIZEN_DEATH"]["id"] == 106
    assert types["CITIZEN_DEATH"]["level"] == "pause"
    assert types["PET_DEATH"]["id"] == 107
    assert types["PET_DEATH"]["level"] == "pause"

    lua_source = LUA_PATH.read_text(encoding="utf-8")
    assert "[106] = \"CITIZEN_DEATH\"" in lua_source
    assert "[107] = \"PET_DEATH\"" in lua_source


def test_slow_ids_are_never_referenced_by_the_pause_table_and_vice_versa():
    gen = _load_generator_module()
    types = gen._load_types()
    pause_ids = {v["id"] for v in types.values() if v.get("level") == "pause"}
    slow_ids = {v["id"] for v in types.values() if v.get("level") == "slow"}
    assert pause_ids.isdisjoint(slow_ids)


def test_ambush_mischievous_is_slow_not_pause():
    """research/2026-09-23-announcement-severity.md S:A.2's own finding,
    the concrete answer to the kea case from the announcement side: DF's
    own naming already separates this from a real ambush."""
    gen = _load_generator_module()
    types = gen._load_types()
    assert types["AMBUSH_MISCHIEVOUS"]["level"] == "slow"
