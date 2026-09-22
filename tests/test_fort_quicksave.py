"""Guard: `df-overseer-fort.lua`'s `fort.quicksave` reports the slot
actually written, never a prediction, and resolves the real save directory
even when `dfhack.getSavePath()` reports a phantom path.

handoffs/2026-09-22-loop-diff-reregister-quicksave-slot.md: the encoding-fix
stream found the old "issued" reply's prediction (the slot with the oldest
mtime) wrong on a real fort (predicted "autosave 1", the save landed in
"autosave 2"). This stream's own live deploy check found a second, deeper
bug in the same file: `dfhack.getSavePath()` on VM 103 reports a path
derived from the game's own install directory that does not exist at all
(`/opt/df/game/save/...`); the real save directory is the XDG basedir
(`~/.local/share/Bay 12 Games/Dwarf Fortress/save`), a quirk already
documented in `research/2026-09-11-quicksave-silent-noop.md` and
`docs/TRAPS.md` but never before encoded into a runtime check.

**No Lua interpreter is available in this sandbox** (no `lua`/`lua5.1`
binary, no `lupa` Python binding), the same honest tradeoff
`tests/test_game_text_utf8_helper.py` and `tests/test_diff_reregistration.py`
already document: this is a static, grep-style check over the source text,
not a real Lua VM execution. The live deploy step (this stream's report) is
what actually exercises this against the real DFHack process and the real
filesystem.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FORT_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-fort.lua"


def _text() -> str:
    return FORT_LUA.read_text(encoding="utf-8")


def test_file_exists():
    assert FORT_LUA.is_file()


def test_issued_reply_never_predicts_a_slot():
    text = _text()
    # The old shape this stream replaced: a single predicted slot name and
    # its prior mtime, computed by picking the oldest of the three.
    assert "predicted_slot" not in text
    assert "oldest_slot(" not in text
    assert "local function oldest_slot(" not in text
    # The new shape: every slot's mtime, keyed by name, reported honestly.
    assert "prior_mtimes[name] = slot_mtime(root, name) or -1" in text


def test_confirm_reports_whichever_slot_actually_changed():
    text = _text()
    assert "local changed = {}" in text
    assert "table.insert(changed, name)" in text
    # Never a hardcoded/predicted single-slot answer: the confirmed slot
    # only appears when exactly one slot's mtime moved.
    assert "if #changed == 1 then" in text
    assert 'result.slot = changed[1]' in text


def test_all_or_nothing_three_prior_mtimes_no_mode_literal():
    text = _text()
    # The function signature takes three optional priors, not a separate
    # "mode" flag word -- presence of all three is what selects confirm mode.
    m = re.search(r"function fort_quicksave\(([^)]*)\)", text)
    assert m, "expected a function fort_quicksave(...) definition"
    params = [p.strip() for p in m.group(1).split(",")]
    assert params == ["prior_autosave_1", "prior_autosave_2", "prior_autosave_3"]


def test_save_root_tries_getsavepath_then_falls_back_to_xdg_candidate():
    text = _text()
    # candidate_a: derived from dfhack.getSavePath(), tried first (so a
    # future install where getSavePath() is correct needs no further fix).
    assert 'local candidate_a = path:match(' in text
    assert "dfhack.filesystem.isdir(candidate_a)" in text
    # candidate_b: the documented Bay12 XDG basedir, tried only as a
    # fallback -- never hardcoded as the sole answer, since a future/other
    # install might not need it.
    assert '.local/share/Bay 12 Games/Dwarf Fortress/save' in text
    assert "dfhack.filesystem.isdir(candidate_b)" in text
    assert 'os.getenv("HOME")' in text


def test_save_root_never_silently_assumes_a_directory_exists():
    text = _text()
    # Both candidates must be verified with isdir before being returned --
    # this is exactly the check that was missing before this stream (the
    # old code returned the getSavePath()-derived string unconditionally,
    # even though it does not exist on the real VM).
    m = re.search(r"local function save_root\(\)(.*?)\nend\n", text, re.S)
    assert m, "expected a local function save_root() ... end"
    body = m.group(1)
    assert body.count("dfhack.filesystem.isdir(") == 2


def test_usage_string_matches_the_three_prior_signature():
    text = _text()
    m = re.search(r'print\("usage:.*?"\)', text)
    assert m, "expected a print(\"usage: ...\") line"
    usage = m.group(0)
    assert "PRIOR_AUTOSAVE_1 PRIOR_AUTOSAVE_2 PRIOR_AUTOSAVE_3" in usage
    assert "CONFIRM_SLOT" not in usage
    assert "CONFIRM_PRIOR_MTIME" not in usage
