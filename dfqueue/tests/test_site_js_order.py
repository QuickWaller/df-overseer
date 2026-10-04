"""The Board's newest-first grouping (`groupByDay` in web/stream/app.js),
exercised through node on the real source text (skipped without node)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "web" / "stream" / "app.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _run(items, newest_first=True):
    src = APP.read_text(encoding="utf8")
    start = src.index("const DF_MONTHS")
    end = src.index("// ---- job graph layout")
    body = src[start:end]
    script = body + "\nconst items = %s;\nconsole.log(JSON.stringify(groupByDay(items, %s)));" % (
        json.dumps(items), "true" if newest_first else "false")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


ITEMS = [
    {"id": "a", "game_date": "1 Granite, year 31"},
    {"id": "b", "game_date": "1 Granite, year 31"},
    {"id": "c", "game_date": "3 Slate, year 31"},
    {"id": "d", "game_date": "2 Granite, year 32"},
    {"id": "n", "game_date": None},
]


def test_newest_day_group_first_and_newest_entry_first_within_a_group():
    groups = _run(ITEMS)
    assert [g[0] for g in groups] == [None, "2 Granite, year 32", "3 Slate, year 31", "1 Granite, year 31"]
    assert [i["id"] for i in groups[3][1]] == ["b", "a"]


def test_oldest_first_still_available():
    groups = _run(ITEMS, newest_first=False)
    assert groups[0][0] == "1 Granite, year 31"
    assert [i["id"] for i in groups[0][1]] == ["a", "b"]
