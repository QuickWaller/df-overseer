"""New sizeable unused dug space, for the Architect's briefing only.

Register 2026-10-09 "Unused dug space survey". Once a cycle the conductor reads
`openarea.survey` (read-only; connected dug floor that belongs to no room, zone,
stockpile, reservation or corridor). A region that is big enough and square
enough, and that was not in the last remembered set, becomes one briefing line
for the Architect so it can propose reuse instead of digging new rock.

This never wakes anyone: it adds a line to a briefing that is being built for
some other reason. Memory is a small JSON file (`space_survey.json`, beside the
cursor store) holding the ids of the qualifying regions last seen. Ids are
hashes of a region's lowest tile, so a region that changes shape may change id
and read as new once more, which is an acceptable false repeat. Total by
design: a bad read gives no lines and leaves the memory untouched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Mapping, Set, Tuple

#: Tool read each cycle (agents/conductor/tools.yaml).
POLL_TOOL = "openarea.survey"

MAX_LINE_CHARS = 220


def qualifying(report: Any, min_tiles: int, min_rectangularity: float) -> List[Mapping[str, Any]]:
    """Regions of a survey report big and square enough. Anything that is not a
    well-formed report gives `[]`."""
    rows = report.get("regions") if isinstance(report, Mapping) else None
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        if not isinstance(r, Mapping) or not isinstance(r.get("id"), str):
            continue
        tiles, rect = r.get("tiles"), r.get("rectangularity")
        if isinstance(tiles, bool) or not isinstance(tiles, int):
            continue
        if isinstance(rect, bool) or not isinstance(rect, (int, float)):
            continue
        if tiles >= min_tiles and rect >= min_rectangularity:
            out.append(r)
    return out


def line_for(region: Mapping[str, Any]) -> str:
    bbox = region.get("bbox") or {}
    near = region.get("nearest_landmarks") or []
    where = ""
    if near and isinstance(near[0], Mapping):
        n = near[0]
        lvl = n.get("level_offset")
        if lvl == 0:
            lvl_txt = "same level as"
        elif isinstance(lvl, int):
            lvl_txt = f"{abs(lvl)} level(s) {'below' if lvl < 0 else 'above'}"
        else:
            lvl_txt = "near"
        where = f", {lvl_txt} {n.get('name')}, {n.get('distance_tiles')} tiles away"
    corridor = ", touches a corridor" if region.get("touches_corridor") else ""
    return (
        f"Unused dug space {region.get('id')}: {region.get('tiles')} tiles, "
        f"{bbox.get('w')}x{bbox.get('h')}, {region.get('tiles_to_square')} more tiles to square it off"
        f"{where}{corridor}. Consider it before digging new rock."
    )[:MAX_LINE_CHARS]


def new_lines(report: Any, seen: Set[str], min_tiles: int, min_rectangularity: float) -> Tuple[List[str], Set[str]]:
    """(lines for regions not in `seen`, the new remembered set). The new set is
    exactly the qualifying ids now, so a region that vanishes and returns reads
    as new again."""
    good = qualifying(report, min_tiles, min_rectangularity)
    lines = [line_for(r) for r in good if r["id"] not in seen]
    return lines, {r["id"] for r in good}


def load_seen(path: Path) -> Set[str]:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return {str(x) for x in doc.get("seen", [])}
    except (OSError, ValueError, AttributeError):
        return set()


def save_seen(path: Path, seen: Set[str]) -> None:
    Path(path).write_text(json.dumps({"seen": sorted(seen)}), encoding="utf-8")
