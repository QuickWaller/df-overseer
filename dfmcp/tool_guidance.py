"""Result enrichment: the confidence level and the gotcha titles every
DFHack-backed tool result carries, plus the labor join for the building tool.

Design: `docs/BUILDING-TOOL.md`, "Confidence per tool and kind" and contract
**C3**. This module is transport-free and takes plain dicts, so it is tested
without the MCP SDK; `dfmcp/server.py` holds the one small hook that applies
it to a `CallToolResult`.

## What an agent sees

A DFHack-backed result (a success, an array, or an error) gains **one sibling
object**, `tool_guidance`:

    {"confidence": "medium",
     "confidence_note": "<a few words>",
     "gotchas": [{"id", "title", "status", "outcomes": {"worked", "did_not_work"}}],
     "gotchas_omitted": <n>,               # only if the list was capped
     "gotcha_addendum": "<standing text>", # only if a proposed one is listed
     "gotchas_unavailable": "<reason>"}    # only if the store could not be read

`gotchas` is present only if the tool has any (proposed and accepted; rejected
are never shown), titles only; the full text comes from `gotchas.get`. The
same content is also rendered as one XML text block appended after the tool's
own text, because a client that shows the model only the text content would
otherwise never see it. The tool's own first text block is untouched.

C3 says "one sibling object" without naming a key; this module puts all four
keys under the single key `tool_guidance` so a tool's own output can never
collide with them. The one place a reader might expect them flat is the top of
the object. That is a reading of the contract, reported for the orchestrator.

## Survives the array-output trap

`docs/TRAPS.md`: `structuredContent` must be a JSON object, so a script that
prints a bare array is wrapped by the server as `{"result": [...]}`. The
enrichment is applied **after** that wrapping and adds a sibling of `result`,
never inside the array. An **error** result has no structured content at all,
so it gets `{"tool_guidance": {...}}` as its structured content and the same
XML block after the error text. Tested on object, array and error results.

## Unknown is not none

If the gotcha store cannot be read (absent, malformed, locked), the result
carries `gotchas_unavailable` with the reason and no `gotchas` key. Silence
would read as "this tool has no gotchas". The tool call itself is never failed
by an enrichment problem: the agent still gets its result, plus the fact that
the gotcha check did not happen.

## A sibling key never overwrites the tool's own output

If a tool's object result already has a key this module wants to add, the
tool's value is kept, the server's is dropped, and `tool_guidance` gains a
`notes` entry naming the collision. The one exception is `gaps` when the tool's
own is a list (the building tool's is): the server's list begins with every
entry of the tool's, so it replaces it as a superset, with a note.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from xml.sax.saxutils import escape, quoteattr

from . import gotchas_store as store
from .confidence import ConfidenceConfig
from .labor_join import LaborJoin, render_xml as render_labor_xml

GUIDANCE_KEY = "tool_guidance"

#: A result lists at most this many gotchas; the rest are counted, never
#: silently dropped. Accepted ones sort first.
MAX_LISTED_GOTCHAS = 10

GOTCHA_ADDENDUM = (
    "A proposed gotcha is an unconfirmed experiment written by another run. Try one only if its "
    "title applies to what you are doing and this tool fails without it, then record the outcome "
    "with gotchas.write (pass its id and worked or did_not_work). Expand any gotcha with gotchas.get."
)

_JOIN_KEYS = ("operating_labors", "gaps", "gaps_unknown")


class ToolGuidance:
    """The confidence file plus the gotcha store, asked once per result."""

    def __init__(self, confidence: ConfidenceConfig, gotchas_db: str | Path, max_listed: int = MAX_LISTED_GOTCHAS):
        self._confidence = confidence
        self._db = Path(gotchas_db)
        self._max = max_listed

    async def build(self, tool_id: str, kind: Optional[str]) -> Dict[str, Any]:
        level = self._confidence.lookup(tool_id, kind)
        out: Dict[str, Any] = {"confidence": level.level, "confidence_note": level.note}
        try:
            entries = await asyncio.to_thread(
                store.entries_for_tool, self._db, tool_id, kind=kind,
                lists=[store.LIST_GOTCHA],
                statuses=[store.STATUS_ACCEPTED, store.STATUS_PROPOSED], with_outcomes=False,
            )
            counts = await asyncio.to_thread(store.outcome_counts, self._db, [e["id"] for e in entries])
        except store.GotchaStoreError as exc:
            out["gotchas_unavailable"] = str(exc)
            return out
        except (sqlite3.Error, OSError) as exc:
            out["gotchas_unavailable"] = f"the gotcha store could not be read: {exc}"
            return out
        entries.sort(key=lambda e: (e["status"] != store.STATUS_ACCEPTED, e["id"]))
        listed = entries[: self._max]
        if listed:
            out["gotchas"] = [
                {"id": e["id"], "title": e["title"], "status": e["status"], "outcomes": counts[e["id"]]}
                for e in listed
            ]
            if len(entries) > len(listed):
                out["gotchas_omitted"] = len(entries) - len(listed)
            if any(e["status"] == store.STATUS_PROPOSED for e in listed):
                out["gotcha_addendum"] = GOTCHA_ADDENDUM
        return out


def render_guidance_xml(guidance: Mapping[str, Any]) -> str:
    lines = [
        f'<tool_guidance confidence={quoteattr(guidance["confidence"])} '
        f'note={quoteattr(guidance["confidence_note"])}>'
    ]
    if "gotchas_unavailable" in guidance:
        lines.append(
            "  <gotchas_unavailable>"
            f"{escape(guidance['gotchas_unavailable'])}</gotchas_unavailable>"
        )
    for g in guidance.get("gotchas", []):
        o = g["outcomes"]
        lines.append(
            f'  <gotcha id={quoteattr(g["id"])} status={quoteattr(g["status"])} '
            f'worked="{o["worked"]}" did_not_work="{o["did_not_work"]}">{escape(g["title"])}</gotcha>'
        )
    if guidance.get("gotchas_omitted"):
        lines.append(f'  <more_gotchas count="{guidance["gotchas_omitted"]}"/>')
    if "gotcha_addendum" in guidance:
        lines.append(f"  <addendum>{escape(guidance['gotcha_addendum'])}</addendum>")
    for note in guidance.get("notes", []):
        lines.append(f"  <note>{escape(note)}</note>")
    lines.append("</tool_guidance>")
    return "\n".join(lines)


def _kind_token(arguments: Mapping[str, Any], structured: Optional[Mapping[str, Any]]) -> Optional[str]:
    """The kind this result is about: the result's own `kind.token` (contract
    C1) when it has one, else the call's `kind` argument."""
    if isinstance(structured, Mapping):
        kind = structured.get("kind")
        if isinstance(kind, Mapping) and isinstance(kind.get("token"), str) and kind["token"]:
            return kind["token"]
    arg = arguments.get("kind")
    return arg if isinstance(arg, str) and arg else None


async def enrich(
    tool_id: str,
    arguments: Mapping[str, Any],
    structured: Optional[Dict[str, Any]],
    is_error: bool,
    *,
    guidance: Optional[ToolGuidance],
    labor_join: Optional[LaborJoin],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """`(new_structured, extra_text_blocks)` for one DFHack-backed result.

    `structured` is what the server would return as `structuredContent`
    already (an object, `{"result": ...}` for a non-object, or None for an
    error or empty output). Returns it with the sibling keys added, and the
    XML blocks to append after the tool's own text. A no-op (unchanged,
    `[]`) when neither `guidance` nor `labor_join` is configured."""
    if guidance is None and labor_join is None:
        return structured, []
    out: Dict[str, Any] = dict(structured) if isinstance(structured, dict) else {}
    blocks: List[str] = []
    notes: List[str] = []
    kind = _kind_token(arguments, structured)

    if labor_join is not None and not is_error and tool_id in labor_join.tools:
        joined = await labor_join.join_result(structured, kind)
        for key in _JOIN_KEYS:
            if key == "gaps" and isinstance(out.get(key), list):
                # The joined gaps already start with every gap the tool itself
                # reported (labor_join.combined_gaps), so this is a superset:
                # nothing of the tool's is lost, and the labor gaps the join
                # adds are not dropped beside a tool's own list.
                if joined[key] != out[key]:
                    notes.append("the tool's own 'gaps' was merged with the server's; the tool's entries come first")
                out[key] = joined[key]
            elif key in out:
                notes.append(
                    f"the tool's own result already has a {key!r} key; the server's {key!r} was dropped"
                )
            else:
                out[key] = joined[key]
        blocks.append(render_labor_xml(joined))

    if guidance is not None:
        built = await guidance.build(tool_id, kind)
        if notes:
            built["notes"] = notes
        if GUIDANCE_KEY in out:
            built.setdefault("notes", []).append(
                f"the tool's own result already has a {GUIDANCE_KEY!r} key; the server's was dropped"
            )
        else:
            out[GUIDANCE_KEY] = built
        blocks.append(render_guidance_xml(built))
    return out, blocks
