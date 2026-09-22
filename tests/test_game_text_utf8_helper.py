"""Guard: a scripts/dfhack/*.lua file that reads game-originated text must
route it through the shared UTF-8 helper.

handoffs/2026-09-22-loop-game-text-encoding.md: `diff.since` crashed the
conductor's first cycle (`'utf-8' codec can't decode byte 0x96'`) on a dwarf
name holding a CP437 character, because no script under scripts/dfhack/
called `dfhack.df2utf` anywhere -- every tool that prints a name, a job, a
building/zone/burrow name, an announcement or a noble title could hit the
same crash. The fix is a single shared helper
(`scripts/dfhack/df-overseer-textutil.lua`, `to_utf8`), reqscript'd by every
file that reads one of the known game-text accessors, and this file is the
regression guard the handoff asks for: "a test or static check that fails
if a script emits a known game-text accessor without the helper (a
grep-style test over scripts/dfhack/ is fine)".

**What this actually proves, stated plainly (coarse by design, not a
code-flow analysis)**: that a file calling one of the known accessors also
reqscript's `df-overseer-textutil` and calls `textutil.to_utf8` at least
once somewhere in the file. It does NOT prove every individual call site is
wrapped -- the real accessor call and its `to_utf8` wrap are often several
lines apart (an `ok, name = pcall(accessor, ...)` pattern, wrapped later
when `name` is used), so a per-line or small-window regex would either miss
real wraps or need to be code-aware enough that it stops being "grep-style".
The per-call-site correctness claim for the files this stream touched is
made by hand in this stream's report (every real call site found and
listed), not by this test. What this test DOES catch reliably: a new file,
or an existing file extended later, that calls a known game-text accessor
and forgets the helper entirely -- exactly the shape of the original bug
(no script anywhere called df2utf), and exactly what would let a *future*
tool "rediscover the bug" instead of getting the fix by calling the helper,
which is the generalisable-tools rule this project holds (CLAUDE.md).

Placed at top level (`tests/`), matching `test_no_leaked_addresses.py`'s
placement rationale: it scans a directory of files as a whole, not one
component's own unit surface.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts" / "dfhack"

# The helper module itself: defines to_utf8 by calling dfhack.df2utf
# directly, and (deliberately) does not reqscript itself.
HELPER_FILE = "df-overseer-textutil.lua"

# Known accessors that return DF's own CP437-encoded game text: a unit's
# generated name, a job's name, a building/zone/burrow's name, a race name,
# a profession name, or a raw announcement/report string. Found by reading
# every scripts/dfhack/*.lua file for this handoff (see the stream's
# report for the full per-file, per-line list) -- this list is the
# vocabulary a future accessor should be added to if it turns out to read
# more game text DFHack stores in CP437.
#
# Deliberately NOT requiring a trailing `(`: this codebase's own convention
# is to pass most of these as a bare function value into `pcall`
# (`pcall(dfhack.buildings.getName, bld)`, never
# `pcall(dfhack.buildings.getName(bld))`), so the accessor name is often
# followed by `,` or `)`, not `(`. An early version of this pattern list
# required `\(` and silently matched nothing in the files that use exactly
# that pcall idiom -- caught by test_accessor_pattern_list_matches_known_call_sites
# below, which is exactly the positive-control failure it exists to catch.
GAME_TEXT_ACCESSOR_PATTERNS = [
    r"dfhack\.job\.getName\b",
    r"dfhack\.translation\.translateName\b",
    r"dfhack\.units\.getReadableName\b",
    r"dfhack\.units\.getVisibleName\b",
    r"dfhack\.units\.getRaceName\b",
    r"dfhack\.units\.getProfessionName\b",
    r"dfhack\.buildings\.getName\b",
    r"dfhack\.burrows\.getName\b",
    r"rep\.text\b",
]
_ACCESSOR_RE = re.compile("|".join(GAME_TEXT_ACCESSOR_PATTERNS))

_REQSCRIPT_TEXTUTIL_RE = re.compile(
    r"""reqscript\(\s*['"]df-overseer-textutil['"]\s*\)"""
)
_USES_HELPER_RE = re.compile(r"\btextutil\.to_utf8\(")


def _lua_files():
    return sorted(p for p in SCRIPTS_DIR.glob("*.lua") if p.name != HELPER_FILE)


def _non_comment_lines(text: str):
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("--"):
            continue
        yield lineno, line


def _accessor_hits(text: str):
    return [
        (lineno, m.group(0))
        for lineno, line in _non_comment_lines(text)
        for m in _ACCESSOR_RE.finditer(line)
    ]


def test_helper_module_exists_and_defines_to_utf8():
    helper = SCRIPTS_DIR / HELPER_FILE
    assert helper.is_file(), f"expected shared helper at {helper}"
    text = helper.read_text(encoding="utf-8")
    assert "function to_utf8(" in text
    assert "dfhack.df2utf" in text


def test_every_file_reading_game_text_reqscripts_and_uses_the_helper():
    violations = []
    for path in _lua_files():
        text = path.read_text(encoding="utf-8")
        hits = _accessor_hits(text)
        if not hits:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if not _REQSCRIPT_TEXTUTIL_RE.search(text):
            violations.append(
                f"{rel}: calls a game-text accessor ({hits[0][1]!r} at line "
                f"{hits[0][0]}) but never reqscript's '{HELPER_FILE[:-4]}'"
            )
            continue
        if not _USES_HELPER_RE.search(text):
            violations.append(
                f"{rel}: reqscript's the helper but never calls "
                "textutil.to_utf8(...) anywhere in the file, despite calling "
                f"a game-text accessor ({hits[0][1]!r} at line {hits[0][0]})"
            )
    if violations:
        pytest.fail(
            "Found scripts/dfhack/*.lua files that read game-originated text "
            "without routing it through the shared df2utf helper "
            "(scripts/dfhack/df-overseer-textutil.lua). Every known "
            "accessor in GAME_TEXT_ACCESSOR_PATTERNS below must be wrapped "
            "with textutil.to_utf8(...) at the point the text is read, per "
            "handoffs/2026-09-22-loop-game-text-encoding.md.\n\n"
            + "\n".join(f"  {v}" for v in violations)
        )


def test_accessor_pattern_list_matches_known_call_sites():
    # Positive control: this repo's own current call sites, so a future
    # edit to GAME_TEXT_ACCESSOR_PATTERNS that accidentally stops matching
    # real code fails here first, not silently.
    expected_nonzero = {
        "df-overseer-diff.lua",
        "df-overseer-connectivity.lua",
        "df-overseer-farm.lua",
        "df-overseer-labor.lua",
        "df-overseer-landmarks.lua",
        "df-overseer-nobles.lua",
        "df-overseer-overview.lua",
        "df-overseer-stuckjobs.lua",
        "df-overseer-threat.lua",
        "df-overseer-workjob.lua",
    }
    found_nonzero = set()
    for path in _lua_files():
        text = path.read_text(encoding="utf-8")
        if _accessor_hits(text):
            found_nonzero.add(path.name)
    missing = expected_nonzero - found_nonzero
    assert not missing, (
        f"Expected these known game-text-reading files to still match the "
        f"accessor patterns, but they didn't (pattern list or file content "
        f"drifted): {sorted(missing)}"
    )
