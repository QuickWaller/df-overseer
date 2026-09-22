"""Guard: `df-overseer-fort.lua`'s `fort.quicksave` reports the slot
actually written, never a prediction, and never trusts a DFHack API this
install's own live behaviour disproved.

handoffs/2026-09-22-loop-diff-reregister-quicksave-slot.md, two live findings
on VM 103, in order:

1. The original "issued" reply's prediction (the slot with the oldest
   `world.sav` mtime) was wrong on a real fort (predicted "autosave 1", the
   save landed in "autosave 2",
   evals/live/2026-09-22-loop-game-text-encoding/README.md). First fix:
   report every slot's real mtime via `dfhack.filesystem.mtime` instead of
   guessing.
2. Deploying THAT fix found `dfhack.filesystem.mtime` itself is broken on
   this install: its own doc promises "seconds... or -1 if path does not
   exist"; live-verified against `stat`'s real values (which matched
   wall-clock time), it instead returns huge, nonsensical negative numbers
   (order -1e18 to -5e18) for every real file tested. `io.popen`/
   `os.execute` are sandboxed out of this DFHack Lua environment (confirmed
   live: `pcall(io.popen, ...)` fails), so there is no working fallback
   inside the sandbox. Final fix: drop file mtimes entirely and use the
   handoff's own explicitly sanctioned alternative, "DF's own record of the
   save" (`df.global.world.cur_savegame.save_dir`), live-verified this
   stream to change to the real just-written slot after a real quicksave.

**No Lua interpreter is available in this sandbox** (no `lua`/`lua5.1`
binary, no `lupa` Python binding), the same honest tradeoff
`tests/test_game_text_utf8_helper.py` and `tests/test_diff_reregistration.py`
already document: this is a static, grep-style check over the source text,
not a real Lua VM execution. The live deploy step (this stream's report) is
what actually exercised this against the real DFHack process and the real
filesystem -- including the two live findings above, which a static check
by itself could never have caught.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FORT_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-fort.lua"


def _text() -> str:
    return FORT_LUA.read_text(encoding="utf-8")


def _code_only() -> str:
    """The file with full-line `--` comments stripped, for assertions about
    what the CODE does rather than what the header narrates -- this file's
    header intentionally names every superseded shape (predicted_slot,
    prior_mtimes, dfhack.filesystem.mtime, io.popen) as history, so a plain
    substring check over the whole file would false-positive on the
    docstring, not the code."""
    lines = []
    for line in _text().splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    return "\n".join(lines)


def test_file_exists():
    assert FORT_LUA.is_file()


def test_issued_reply_never_predicts_a_slot():
    code = _code_only()
    # Neither the original oldest-mtime prediction nor the first fix's
    # per-slot-mtime shape (both superseded live, see module docstring)
    # should remain in the CODE (the header narrates both as history).
    assert "predicted_slot" not in code
    assert "oldest_slot(" not in code
    assert "prior_mtimes" not in code
    assert "dfhack.filesystem.mtime" not in code
    assert "SLOT_NAMES" not in code


def test_uses_cur_savegame_save_dir_as_the_sole_truth_signal():
    text = _text()
    assert "df.global.world.cur_savegame.save_dir" in text
    assert "local function current_save_dir()" in text


def test_confirm_reports_the_new_save_dir_only_when_it_actually_changed():
    text = _text()
    assert "local confirmed = current ~= nil and current ~= prior_save_dir" in text
    assert "if confirmed then" in text
    assert "result.slot = current" in text


def test_fort_quicksave_takes_one_optional_prior_save_dir_argument():
    text = _text()
    m = re.search(r"function fort_quicksave\(([^)]*)\)", text)
    assert m, "expected a function fort_quicksave(...) definition"
    params = [p.strip() for p in m.group(1).split(",") if p.strip()]
    assert params == ["prior_save_dir"]


def test_issue_path_fires_quicksave_and_records_the_prior_save_dir():
    text = _text()
    m = re.search(r"local prior = current_save_dir\(\)\s*\n\s*dfhack\.run_command\('quicksave'\)", text)
    assert m, "expected prior_save_dir to be captured before firing quicksave"


def test_current_save_dir_is_pcall_guarded_and_treats_empty_as_nil():
    text = _text()
    m = re.search(r"local function current_save_dir\(\)(.*?)\nend\n", text, re.S)
    assert m, "expected a local function current_save_dir() ... end"
    body = m.group(1)
    assert "pcall(" in body
    assert 'dir == ""' in body


def test_no_shell_out_workaround_left_in_the_file():
    # io.popen/os.execute are confirmed sandboxed out of this DFHack Lua
    # environment (live, this stream) -- the CODE must not depend on either
    # (the header narrates the live finding that ruled them out).
    code = _code_only()
    assert "io.popen" not in code
    assert "os.execute" not in code


def test_usage_string_matches_the_one_arg_signature():
    text = _text()
    m = re.search(r'print\("usage:.*?"\)', text)
    assert m, "expected a print(\"usage: ...\") line"
    usage = m.group(0)
    assert "PRIOR_SAVE_DIR" in usage
    assert "CONFIRM_SLOT" not in usage
    assert "CONFIRM_PRIOR_MTIME" not in usage
    assert "PRIOR_AUTOSAVE" not in usage
