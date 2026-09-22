"""Guard: `df-overseer-diff.lua`'s eventful listeners re-register on a
version bump, not once per DF process forever.

handoffs/2026-09-22-loop-diff-reregister-quicksave-slot.md: the encoding-fix
stream (evals/live/2026-09-22-loop-game-text-encoding/README.md, "Found
live, not fixed") found that the old guard, a plain boolean
(`_G.__df_overseer_diff_registered`), stayed `true` forever once set, so a
redeploy that changed this file's listener closures never took effect on the
already-running DF process. The fix keys the guard on a version string
instead.

**No Lua interpreter is available in this sandbox** (no `lua`/`lua5.1`
binary, no `lupa` Python binding) to actually execute
`df-overseer-diff.lua`'s registration block and observe re-registration
happen. This file is therefore a static, grep-style check over the source
text, the same honesty tradeoff `tests/test_game_text_utf8_helper.py`
documents for the same reason: it proves the guard is SHAPED correctly
(version-keyed, not boolean; legacy entries marked so they convert exactly
once; the id counter and log are preserved across a re-registration), not
that the shape behaves correctly inside a real Lua VM. The live deploy
step (this stream's report) is what actually exercises re-registration
against the real DFHack process.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIFF_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-diff.lua"


def _text() -> str:
    return DIFF_LUA.read_text(encoding="utf-8")


def test_file_exists():
    assert DIFF_LUA.is_file()


def test_registration_version_constant_exists():
    text = _text()
    m = re.search(r'local REGISTRATION_VERSION\s*=\s*"([^"]+)"', text)
    assert m, "expected a local REGISTRATION_VERSION = \"...\" constant"
    assert m.group(1), "REGISTRATION_VERSION must not be an empty string"


def test_guard_is_version_keyed_not_a_bare_boolean():
    text = _text()
    # The old shape this stream replaced: a bare boolean guard that, once
    # true, is true forever regardless of a redeploy.
    assert "_G.__df_overseer_diff_registered then" not in text
    assert "_G.__df_overseer_diff_registered = true" not in text
    # The new shape: gated on a version comparison.
    assert re.search(
        r"if\s+_G\.__df_overseer_diff_registered_version\s*~=\s*REGISTRATION_VERSION\s+then",
        text,
    ), "expected the registration block gated on a version mismatch check"
    # And the flag is set to the version constant at the end of that block,
    # not a boolean.
    assert "_G.__df_overseer_diff_registered_version = REGISTRATION_VERSION" in text


def test_log_and_id_counter_survive_a_reregistration():
    text = _text()
    # Both must use `or` to preserve any existing value rather than a bare
    # `= {}` / `= 1` that would reset the log and cursor on every version
    # bump (the conductor's cursors depend on the id counter never
    # regressing or the log being wiped out from under an in-flight cursor).
    assert "_G.__df_overseer_diff_log = _G.__df_overseer_diff_log or {}" in text
    assert "_G.__df_overseer_diff_next_id = _G.__df_overseer_diff_next_id or 1" in text


def test_listeners_are_registered_under_stable_named_keys():
    # eventful's documented idiom: eventful.onX.SOME_KEY = function ... end.
    # Reassigning the same key replaces the prior value in-place (a Lua
    # table property), which is what makes re-registration safe rather than
    # layering a second handler under a new key.
    text = _text()
    for on_table in (
        "onJobCompleted",
        "onUnitDeath",
        "onReport",
        "onUnitAttack",
    ):
        assert f"eventful.{on_table}.df_overseer_diff = function" in text, (
            f"expected eventful.{on_table}.df_overseer_diff to be assigned "
            "under this fixed key (not a different key per registration, "
            "which would layer handlers instead of replacing one)"
        )


def test_legacy_entries_are_converted_exactly_once_and_marked():
    text = _text()
    # The one-time legacy-conversion loop: gated on the entry having no
    # encoding_version yet (i.e. it predates this file's own bookkeeping),
    # and it stamps the entry afterward so a future version bump never
    # reconverts it (double-converting an already-UTF-8 string with df2utf
    # mangles it).
    assert "entry.encoding_version == nil" in text
    assert 'entry.encoding_version = "legacy-converted"' in text
    assert "textutil.to_utf8(entry.detail)" in text


def test_fresh_entries_are_stamped_with_the_current_version_at_creation():
    text = _text()
    # log_event() must stamp every new entry with REGISTRATION_VERSION so it
    # can never be mistaken for an unconverted legacy entry by a later
    # version bump's conversion loop.
    m = re.search(r"local function log_event\(entry\)(.*?)end", text, re.S)
    assert m, "expected a local function log_event(entry) ... end"
    body = m.group(1)
    assert "entry.encoding_version = REGISTRATION_VERSION" in body


def test_no_duplicate_registration_version_constants():
    # Sanity: exactly one REGISTRATION_VERSION definition, not one left
    # behind by a partial edit.
    text = _text()
    assert len(re.findall(r"local REGISTRATION_VERSION\s*=", text)) == 1
