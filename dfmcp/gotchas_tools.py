"""Native ("server-side") MCP tools: `gotchas.get` and `gotchas.write`.

The two shared tools of the confidence-and-gotchas design
(`docs/BUILDING-TOOL.md`, decision 8, contract C3). Two tools in total, not
two per tool, to keep every role's tool list short.

- **`gotchas.get`** expands a gotcha: by id, or every entry of one tool
  (optionally narrowed to a kind, a list or a status). Results in tool calls
  carry only short titles; the full text, the status and the recorded
  outcomes come from here. Added `handoffs/2026-10-02-tool-descriptions-split.md`:
  a call naming `tool` also returns that tool's `guide` (the operating detail
  -- arguments, defaults, cautions, known traps -- that used to live in the
  MCP description, now sent only on demand), so reading a tool's guide and
  its gotchas together is one call, matching `agents/CONFIDENCE-LEGEND.md`'s
  "before using a medium-confidence tool" instruction. A tool with no guide
  yet (a native tool, or a real tool this manifest has not been filled in
  for) simply gets no `<guide>` element; this is never an error. Added
  `handoffs/2026-10-02-wiki-check-test.md` task 4: `gotchas.get` and
  `gotchas.write` now carry guides of their own (`_GET_GUIDE`, `_WRITE_GUIDE`
  below, the same `ToolGuide` shape `dfmcp/registry.py` uses for a
  TOOLS.yaml-backed command), so `gotchas.get(tool="gotchas.write")` or
  `gotchas.get(tool="gotchas.get")` answers "how do I use this tool" the same
  way it would for any other -- the two largest MCP descriptions on the
  overseer's list no longer have to carry that detail on every request.
- **`gotchas.write`** has two modes chosen by whether `id` is passed. Without
  it, it writes a **new** entry about a tool: the server chooses the id and
  sets the status `proposed`, and stamps the writing role, the run and the
  time. With `id`, it **appends an outcome** (`worked` / `did_not_work`) to
  that existing entry, append-only, never overwriting. That is the "mark the
  outcome" half of the experiment protocol without a third tool.

## Served the way `doctrine.get` is

Not in `scripts/dfhack/TOOLS.yaml`: neither calls DFHack. Defined by hand as
`NativeTool`s with explicit JSON schemas, merged into the same registry
through `registry.load_registry`'s `native_tools=`, and enforced through the
one `Roster.check(role, tool_id)` boundary. See `dfmcp/doctrine_tools.py`'s
docstring for the reasoning, which applies unchanged, including why
`knowledge_scope` is deliberately not set: these read and write this
project's own notes about its tools, never fort or world state.

## Who may write

The tool has no `sole_writer_only` restriction: every role that is granted
`gotchas.write` in its `tools.yaml` may write. That grant is the orchestrator's
call (`handoffs/2026-09-21-building-tool-server.md` recommends which roles).
`role`, `id`, `status`, `created_at` and `run_id` are never arguments a caller
can set; `dfmcp/server.py` stamps them and every handler refuses a stray key,
the same enforcement `queue_tools` uses (`additionalProperties: false` in the
schema is defence in depth, not the boundary).

## Validation is in the store, refusals are tool errors

The write-time rules (tool exists in the registry, a title of the form
"condition: hazard", size limits, near-duplicates, a per-run cap) live in
`dfmcp/gotchas_store.py` beside the storage, as `dfqueue/schema.py` sits beside
`dfqueue/store.py`. This module only turns their refusals into `isError`
results. A missing or malformed store is refused the same way, never answered
with an empty list.

## Gotcha text is untrusted

Every entry is written by an agent and is later read by other agents, inside
their prompts. Titles are restricted to one plain line with no markup
characters, everything is XML-escaped when rendered, and every rendering of a
`proposed` entry carries a warning that it is an unconfirmed experiment. The
standing rule text (`agents/CONFIDENCE-LEGEND.md`) says gotchas inform judgement
and never override instructions. None of this makes a hostile note harmless; it
makes it visible as a note.

## SQLite runs off the event loop; writes are serialised

Same as `dfmcp/queue_tools.py`: every store call is `asyncio.to_thread`, and
writes additionally hold the server's one `asyncio.Lock`. The store's own
`BEGIN IMMEDIATE` is what makes concurrent writers from other processes safe;
the lock only avoids blocking a thread pool worker on SQLite's busy timeout.
"""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from xml.sax.saxutils import escape, quoteattr

from . import gotchas_store as store
from .registry import GuideArgument, ToolGuide

# --------------------------------------------------------------------------
# Tool ids and the default store path
# --------------------------------------------------------------------------

GOTCHAS_GET = "gotchas.get"
GOTCHAS_WRITE = "gotchas.write"

NATIVE_TOOL_IDS = (GOTCHAS_GET, GOTCHAS_WRITE)

#: Absolute and out of tree, like `series_tools.DEFAULT_SERIES_DB_PATH`, so a
#: code redeploy resolving a relative path can never land on it; a plain str
#: because it is a Linux path and the workstation is Windows. The file must
#: exist (created once with `python -m dfmcp.gotchas_store init PATH`); an
#: absent file is refused, never created.
DEFAULT_GOTCHAS_DB_PATH = "/var/lib/dfgotchas/uniboslan.gotchas.sqlite3"


class GotchaToolError(Exception):
    """A `gotchas.*` call is refused: bad arguments, an unknown tool or id, a
    write-time validation refusal, or a missing or malformed store. Always
    caught by `dfmcp.server` and turned into `isError=True`."""


# --------------------------------------------------------------------------
# NativeTool
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NativeTool:
    """Same duck-typed shape as `dfmcp.doctrine_tools.NativeTool`, plus a
    `guide` field (added for the gotchas tools themselves,
    `handoffs/2026-10-02-wiki-check-test.md` task 4): the same `ToolGuide`
    shape `dfmcp/registry.py`'s TOOLS.yaml-backed `Tool` carries. `dfmcp/
    server.py`'s `tool_guides` map is built by duck-typed `getattr(t, "guide",
    None)` over every entry in `registry.all()`, native tools included, so
    giving `gotchas.get`/`gotchas.write` a real `guide` here is picked up with
    no server.py change: `gotchas.get(tool="gotchas.write")` then returns it
    the same way it would for any other tool."""

    id: str
    mutates: bool = False
    sole_writer_only: bool = False
    native: bool = True
    args: Tuple[str, ...] = ()
    guide: Optional[ToolGuide] = None

    def describe(self, role: str) -> Tuple[str, dict]:
        del role  # neither schema depends on the caller
        if self.id == GOTCHAS_GET:
            return _GET_DESCRIPTION, _GET_SCHEMA
        if self.id == GOTCHAS_WRITE:
            return _WRITE_DESCRIPTION, _WRITE_SCHEMA
        raise AssertionError(f"NativeTool.describe: unknown id {self.id!r}")  # pragma: no cover


# NATIVE_TOOLS is built near the end of this module (after `_GET_GUIDE` and
# `_WRITE_GUIDE` exist), since `NativeTool.guide` needs them; see there.

# --------------------------------------------------------------------------
# Descriptions and schemas
# --------------------------------------------------------------------------

_LISTS = list(store.LISTS)
_STATUSES = list(store.STATUSES)

# Short: the MCP description sent to the model on every request. The detail
# this used to carry (the four modes, their field combinations, the
# empty-list-vs-error rule) now lives in `_GET_GUIDE` below, fetched on demand
# through `gotchas.get(tool="gotchas.get")` -- `handoffs/2026-10-02-
# wiki-check-test.md` task 4; before this change this string alone was 1,128
# characters, the second-largest description on the overseer's list.
_GET_DESCRIPTION = (
    "Read the gotchas recorded about a tool, about the run itself, or an index of which tools "
    "have entries. Pass 'id' for one entry, 'tool' for that tool's entries, or 'general: true' "
    "for entries about the run rather than any tool; pass neither for the index. Call "
    "gotchas.get(tool='gotchas.get') for the full mode-by-mode guide."
)

_GET_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {
            "type": "string",
            "description": (
                "One entry by its id, for example 'gotcha-0004'. Mutually exclusive with every "
                "other argument. Returned whatever its status."
            ),
        },
        "tool": {
            "type": "string",
            "description": (
                "A tool id, for example 'building.build'. Refused if it is not a real tool. "
                "Mutually exclusive with 'general'."
            ),
        },
        "general": {
            "type": "boolean",
            "description": (
                "Pass true (with no 'tool') to list general entries: a gotcha, unexplained error "
                "or vent about the run itself (process, timing, other agents, your own wake-ups), "
                "not about any particular tool. Combine with 'list', 'status', 'include_rejected' "
                "as usual; 'kind' does not apply, since a general entry has none."
            ),
        },
        "kind": {
            "type": "string",
            "description": (
                "Only with 'tool': narrow to one kind token. Entries for that kind and tool-wide "
                "entries are both returned; tool-wide ones apply to every kind."
            ),
        },
        "list": {
            "type": "string",
            "enum": _LISTS,
            "description": "Only with 'tool' or 'general': gotcha (default: all three lists), unexplained or vent.",
        },
        "status": {
            "type": "string",
            "enum": _STATUSES,
            "description": "Only with 'tool' or 'general': narrow to one status.",
        },
        "include_rejected": {
            "type": "boolean",
            "description": "Only with 'tool' or 'general': also return rejected entries (default false).",
        },
    },
}

# Short, for the same reason as `_GET_DESCRIPTION` above: this string alone
# was 1,450 characters, the largest description on the overseer's list. The
# full two-mode explanation (field combinations, the title's required shape,
# the append-only outcome rule) now lives in `_WRITE_GUIDE`, fetched through
# gotchas.get(tool="gotchas.write").
_WRITE_DESCRIPTION = (
    "Record what you learned, for the runs after you: a new gotcha about a tool (or about the "
    "run itself), or an outcome on one you already tried. Pass 'title' and 'body' for a new "
    "entry, or 'id' and 'result' to record whether it worked. Call "
    "gotchas.get(tool='gotchas.write') for the full guide."
)

_WRITE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "tool": {
            "type": "string",
            "description": (
                "New entry, optional: the tool id the note is about, for example "
                "'building.build'. Omit for a general entry about the run itself, not any "
                "particular tool (then 'kind' must also be omitted)."
            ),
        },
        "title": {
            "type": "string",
            "description": (
                "New entry: '<condition>: <hazard>', one plain line, at most "
                f"{store.TITLE_MAX_CHARS} characters. The condition must let a reader judge from "
                "the title alone whether it applies."
            ),
        },
        "body": {
            "type": "string",
            "description": (
                f"New entry: the full note, {store.BODY_MIN_CHARS} to {store.BODY_MAX_CHARS} "
                "characters: what happens, why if you know, and what to do instead. Never a "
                "raw coordinate."
            ),
        },
        "list": {
            "type": "string",
            "enum": _LISTS,
            "description": "New entry: gotcha (default), unexplained or vent.",
        },
        "kind": {
            "type": "string",
            "description": (
                "New entry, optional: a kind token (never a display label) when the note applies "
                "to one kind of a generic tool only. Omit for a note about the whole tool."
            ),
        },
        "call_excerpt": {
            "type": "string",
            "description": (
                f"New entry, optional: a short excerpt of the call that prompted it, at most "
                f"{store.EXCERPT_MAX_CHARS} characters."
            ),
        },
        "id": {
            "type": "string",
            "description": (
                "Outcome mode: the id of an existing gotcha you tried. Do not combine with the "
                "new-entry fields."
            ),
        },
        "result": {
            "type": "string",
            "enum": list(store.RESULTS),
            "description": "Outcome mode, required: did the gotcha fix the problem?",
        },
        "note": {
            "type": "string",
            "description": f"Outcome mode, optional: a few words, at most {store.NOTE_MAX_CHARS} characters.",
        },
    },
}

# --------------------------------------------------------------------------
# Guides (handoffs/2026-10-02-wiki-check-test.md task 4): the detail moved
# out of `_GET_DESCRIPTION`/`_WRITE_DESCRIPTION` above, served the same way a
# TOOLS.yaml-backed tool's `guide` is, through `gotchas.get(tool=...)`.
# --------------------------------------------------------------------------

_GET_GUIDE = ToolGuide(
    arguments=(
        GuideArgument(
            name="id", required=False, default=None,
            meaning=(
                "One entry by its id, for example 'gotcha-0004'. Mutually exclusive with every "
                "other argument. Returned whatever its status."
            ),
        ),
        GuideArgument(
            name="tool", required=False, default=None,
            meaning=(
                "A tool id, for example 'building.build'. Refused if it is not a real tool. "
                "Mutually exclusive with 'general'."
            ),
        ),
        GuideArgument(
            name="general", required=False, default="false",
            meaning=(
                "Pass true (with no 'tool') to list general entries: a gotcha, unexplained error "
                "or vent about the run itself (process, timing, other agents, your own "
                "wake-ups), not about any particular tool. 'kind' does not apply there, since a "
                "general entry has none."
            ),
        ),
        GuideArgument(
            name="kind", required=False, default=None,
            meaning=(
                "Only with 'tool': narrow to one kind token. Entries for that kind and tool-wide "
                "entries are both returned; tool-wide ones apply to every kind."
            ),
        ),
        GuideArgument(
            name="list", required=False, default=None,
            meaning="Only with 'tool' or 'general': gotcha, unexplained or vent. Omit for all three.",
        ),
        GuideArgument(
            name="status", required=False, default=None,
            meaning="Only with 'tool' or 'general': narrow to one status (proposed, accepted, rejected).",
        ),
        GuideArgument(
            name="include_rejected", required=False, default="false",
            meaning="Only with 'tool' or 'general': also return rejected entries.",
        ),
    ),
    returns=(
        "Four modes depending on which argument is given. An 'id' returns exactly one entry. A "
        "'tool' returns that tool's entries (plus a <guide> element with its own operating detail, "
        "when the tool has one) and includes tool-wide entries alongside any 'kind' given. "
        "'general: true' returns entries about the run itself rather than any tool. Neither 'tool' "
        "nor 'general' returns an index of which tools (and whether general entries exist) have at "
        "least one entry. An unknown tool or id is an error, never an empty list, since an empty "
        "list means 'this real tool has no such entries'. Rejected entries are left out of a "
        "listing by default; the response always states how many were left out, even when zero."
    ),
    before_a_real_run=(),
    traps=(
        "Game knowledge (crop and water rules, and the like) belongs in doctrine, read through "
        "the Consultant, never in a gotcha.",
    ),
)

_WRITE_GUIDE = ToolGuide(
    arguments=(
        GuideArgument(
            name="tool", required=False, default=None,
            meaning=(
                "New entry, optional: the tool id the note is about, for example "
                "'building.build'. Omit for a general entry about the run itself, not any "
                "particular tool (then 'kind' must also be omitted)."
            ),
        ),
        GuideArgument(
            name="title", required=False, default=None,
            meaning=(
                "New entry: '<condition>: <hazard>', one plain line, at most "
                f"{store.TITLE_MAX_CHARS} characters, naming the condition clearly enough that a "
                "reader can tell from the title alone whether it applies. Required together with "
                "'body' unless 'id' is given (outcome mode)."
            ),
        ),
        GuideArgument(
            name="body", required=False, default=None,
            meaning=(
                f"New entry: the full note, {store.BODY_MIN_CHARS} to {store.BODY_MAX_CHARS} "
                "characters: what happens, why if you know, and what to do instead. Never a raw "
                "coordinate. Required together with 'title' unless 'id' is given."
            ),
        ),
        GuideArgument(
            name="list", required=False, default="gotcha",
            meaning=(
                "New entry: gotcha (something worked out to keep in mind next time), unexplained "
                "(an error or mistake you could not explain) or vent (a complaint that the tool is "
                "not right for what you wanted; never evidence)."
            ),
        ),
        GuideArgument(
            name="kind", required=False, default=None,
            meaning=(
                "New entry, optional: a kind token (never a display label) when the note applies "
                "to one kind of a generic tool only. Omit for a note about the whole tool."
            ),
        ),
        GuideArgument(
            name="call_excerpt", required=False, default=None,
            meaning=(
                f"New entry, optional: a short excerpt of the call that prompted it, at most "
                f"{store.EXCERPT_MAX_CHARS} characters."
            ),
        ),
        GuideArgument(
            name="id", required=False, default=None,
            meaning=(
                "Outcome mode: the id of an existing gotcha you tried. Switches the call from "
                "writing a new entry to appending an outcome; do not combine with the new-entry "
                "fields ('title', 'body', 'list', 'kind', 'call_excerpt')."
            ),
        ),
        GuideArgument(
            name="result", required=False, default=None,
            meaning="Outcome mode, required: did the gotcha fix the problem? worked or did_not_work.",
        ),
        GuideArgument(
            name="note", required=False, default=None,
            meaning=f"Outcome mode, optional: a few words, at most {store.NOTE_MAX_CHARS} characters.",
        ),
    ),
    returns=(
        "Two modes, chosen by whether 'id' is passed. NEW ENTRY (no 'id'): needs 'title' and "
        "'body'; the server chooses the id, marks it proposed, and stamps your role, the run and "
        "the time. OUTCOME (with 'id'): needs 'result'; appends an outcome to that existing entry "
        "and never changes it, so a gotcha stays append-only. Returns the full entry either way."
    ),
    before_a_real_run=(
        "The title must state the condition it applies under, in the form '<condition>: "
        "<hazard>' (for example 'placing a workshop in a desert biome: <what goes wrong>'), so a "
        "reader can tell from the title alone whether it applies.",
        "Game knowledge (crop and water rules, and the like) is never a gotcha; it belongs in "
        "doctrine, written through the Consultant, not here.",
    ),
    traps=(
        "Near-duplicates, oversized text and unknown tools are refused with reasons, and a run "
        "may write only a few new entries.",
        "Passing 'id' together with any new-entry field is refused: combine 'id' with only "
        "'result' (required) and 'note' (optional).",
    ),
)

# `mutates=False` on both, deliberately: `Tool.mutates` means "mutates fort
# state" and nothing wider (see `dfmcp/queue_tools.py`), so an advisor may hold
# `gotchas.write` without contradicting "advisors are read-only".
NATIVE_TOOLS: Dict[str, NativeTool] = {
    GOTCHAS_GET: NativeTool(id=GOTCHAS_GET, guide=_GET_GUIDE),
    GOTCHAS_WRITE: NativeTool(id=GOTCHAS_WRITE, guide=_WRITE_GUIDE),
}

_GET_FIELDS = {"id", "tool", "general", "kind", "list", "status", "include_rejected"}
_NEW_FIELDS = {"tool", "title", "body", "list", "kind", "call_excerpt"}
_OUTCOME_FIELDS = {"id", "result", "note", "tool"}
_WRITE_FIELDS = _NEW_FIELDS | _OUTCOME_FIELDS

# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

PROPOSED_WARNING = (
    "PROPOSED: an unconfirmed experiment written by an agent, not a fact. Try it only if its "
    "title applies to what you are doing and the tool fails without it, then record the outcome "
    "with gotchas.write."
)
REJECTED_WARNING = "REJECTED: kept as a record. Do NOT follow it."


def entry_xml(entry: Mapping[str, Any]) -> str:
    attrs = (
        f'id={quoteattr(entry["id"])} tool={quoteattr(entry["tool"] or "")} '
        f'general={quoteattr("true" if entry["tool"] is None else "false")} '
        f'kind={quoteattr(entry["kind"] or "")} list={quoteattr(entry["list"])} '
        f'status={quoteattr(entry["status"])} written_by={quoteattr(entry["written_by_role"])} '
        f'created_at={quoteattr(entry["created_at"])}'
    )
    lines = [f"<gotcha {attrs}>"]
    if entry["status"] == store.STATUS_PROPOSED:
        lines.append(f"  <warning>{escape(PROPOSED_WARNING)}</warning>")
    elif entry["status"] == store.STATUS_REJECTED:
        lines.append(f"  <warning>{escape(REJECTED_WARNING)}</warning>")
    lines.append(f"  <title>{escape(entry['title'])}</title>")
    lines.append(f"  <body>{escape(entry['body'])}</body>")
    if entry.get("call_excerpt"):
        lines.append(f"  <call_excerpt>{escape(entry['call_excerpt'])}</call_excerpt>")
    outcomes = entry.get("outcomes") or []
    worked = sum(1 for o in outcomes if o["result"] == store.RESULT_WORKED)
    lines.append(
        f'  <outcomes total="{len(outcomes)}" worked="{worked}" '
        f'did_not_work="{len(outcomes) - worked}">'
    )
    for o in outcomes:
        note = f" note={quoteattr(o['note'])}" if o.get("note") else ""
        lines.append(
            f'    <outcome result={quoteattr(o["result"])} role={quoteattr(o["role"])} '
            f'at={quoteattr(o["at"])}{note}/>'
        )
    lines.append("  </outcomes>")
    lines.append("</gotcha>")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _reject_unknown_arguments(tool_id: str, arguments: Mapping[str, Any], known: set) -> None:
    unknown = sorted(set(arguments) - known)
    if unknown:
        raise GotchaToolError(
            f"{tool_id}: unexpected argument(s) {unknown}; role, status, run and time are "
            f"stamped by the server and cannot be supplied. This tool accepts only {sorted(known)}"
        )


def _string_arg(tool_id: str, arguments: Mapping[str, Any], name: str) -> Optional[str]:
    value = arguments.get(name)
    if value is not None and not isinstance(value, str):
        raise GotchaToolError(f"{tool_id}: {name!r} must be a string, got {value!r}")
    return value


async def _read(fn, *args, **kwargs):
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except store.GotchaStoreError as exc:
        raise GotchaToolError(str(exc)) from exc
    except (sqlite3.Error, OSError) as exc:
        raise GotchaToolError(f"the gotcha store is unavailable: {exc}") from exc


# --------------------------------------------------------------------------
# gotchas.get
# --------------------------------------------------------------------------


async def _get(
    role: str, arguments: Mapping[str, Any], *, db_path, known_tools: Iterable[str], run_id: str,
    write_lock: "asyncio.Lock", tool_guides: Optional[Mapping[str, str]] = None,
) -> Tuple[str, dict]:
    del role, run_id, write_lock
    tool_guides = tool_guides or {}
    _reject_unknown_arguments(GOTCHAS_GET, arguments, _GET_FIELDS)
    entry_id = _string_arg(GOTCHAS_GET, arguments, "id")
    tool = _string_arg(GOTCHAS_GET, arguments, "tool")
    general = arguments.get("general", False)
    if not isinstance(general, bool):
        raise GotchaToolError(f"{GOTCHAS_GET}: 'general' must be a boolean")
    kind = _string_arg(GOTCHAS_GET, arguments, "kind")
    list_name = _string_arg(GOTCHAS_GET, arguments, "list")
    status = _string_arg(GOTCHAS_GET, arguments, "status")
    include_rejected = arguments.get("include_rejected", False)
    if not isinstance(include_rejected, bool):
        raise GotchaToolError(f"{GOTCHAS_GET}: 'include_rejected' must be a boolean")

    if tool is not None and general:
        raise GotchaToolError(f"{GOTCHAS_GET}: 'tool' cannot be combined with 'general'")

    if entry_id is not None:
        others = [n for n in ("tool", "general", "kind", "list", "status") if arguments.get(n) is not None]
        if others:
            raise GotchaToolError(f"{GOTCHAS_GET}: 'id' cannot be combined with {others}")
        entry = await _read(store.get_entry, db_path, entry_id)
        if entry is None:
            raise GotchaToolError(
                f"{GOTCHAS_GET}: no entry with id {entry_id!r}. Pass 'tool' or 'general: true' to "
                "list entries, or nothing for the index."
            )
        return entry_xml(entry), {"entry": entry}

    if general:
        others = [n for n in ("kind",) if arguments.get(n) is not None]
        if others:
            raise GotchaToolError(
                f"{GOTCHAS_GET}: {others} need 'tool' as well; a general entry has no kind"
            )
        return await _list_entries(db_path, tool=None, kind=None, list_name=list_name, status=status,
                                    include_rejected=include_rejected)

    if tool is None:
        others = [n for n in ("kind", "list", "status") if arguments.get(n) is not None]
        if others:
            raise GotchaToolError(f"{GOTCHAS_GET}: {others} need 'tool' (or 'general: true') as well")
        index = await _read(store.tool_index, db_path)
        lines = ["<gotcha_index note=\"only tools with at least one entry are listed; a tool not "
                 "listed has none; general entries (no tool) are listed with an empty id and "
                 "general='true'\">"]
        for t in sorted(index, key=lambda x: (x is not None, x or "")):
            for ln in sorted(index[t]):
                counts = " ".join(f'{s}="{n}"' for s, n in sorted(index[t][ln].items()))
                general_attr = quoteattr("true" if t is None else "false")
                lines.append(
                    f"  <tool id={quoteattr(t or '')} general={general_attr} list={quoteattr(ln)} {counts}/>"
                )
        lines.append("</gotcha_index>")
        return "\n".join(lines), {"tools": index}

    if tool not in set(known_tools):
        raise GotchaToolError(
            f"{GOTCHAS_GET}: {tool!r} is not a tool in this server's registry. Refusing rather "
            "than returning an empty list, which would read as 'no gotchas' instead of 'not a "
            "real tool'."
        )
    return await _list_entries(db_path, tool=tool, kind=kind, list_name=list_name, status=status,
                                include_rejected=include_rejected, guide=tool_guides.get(tool))


async def _list_entries(
    db_path, *, tool: Optional[str], kind: Optional[str], list_name: Optional[str],
    status: Optional[str], include_rejected: bool, guide: Optional[str] = None,
) -> Tuple[str, dict]:
    """Shared rendering for a tool's entries and for general entries
    (`tool=None`): same filters, same shape, same rejected-omission rule.

    `guide` (added handoffs/2026-10-02-tool-descriptions-split.md): the
    calling tool's operating-detail text, rendered as a `<guide>` element
    right after the opening tag when present. Always None for a general
    entry (`tool=None`), since a guide is about one tool, not the run."""
    lists = [list_name] if list_name else None
    if list_name is not None and list_name not in store.LISTS:
        raise GotchaToolError(f"{GOTCHAS_GET}: 'list' must be one of {_LISTS}")
    if status is not None and status not in store.STATUSES:
        raise GotchaToolError(f"{GOTCHAS_GET}: 'status' must be one of {_STATUSES}")
    entries = await _read(
        store.entries_for_tool, db_path, tool, kind=kind, lists=lists,
        statuses=[status] if status else None,
    )
    visible = entries if (include_rejected or status == store.STATUS_REJECTED) else [
        e for e in entries if e["status"] != store.STATUS_REJECTED
    ]
    omitted = len(entries) - len(visible)
    if tool is None:
        head = f'<gotchas general="true" returned="{len(visible)}" omitted_rejected="{omitted}">'
    else:
        head = (
            f'<gotchas tool={quoteattr(tool)} kind={quoteattr(kind or "")} returned="{len(visible)}" '
            f'omitted_rejected="{omitted}">'
        )
    lines = [head]
    if guide:
        lines.append(f"  <guide>{escape(guide)}</guide>")
    if omitted:
        lines.append(
            f"  <note>{omitted} rejected entr{'y' if omitted == 1 else 'ies'} left out; pass "
            "include_rejected:true to see them.</note>"
        )
    if not visible:
        subject = "there are" if tool is None else f"{tool} is a real tool and has"
        lines.append(f"  <note>{subject} no matching entries.</note>")
    lines.extend(entry_xml(e) for e in visible)
    lines.append("</gotchas>")
    return "\n".join(lines), {
        "tool": tool,
        "general": tool is None,
        "kind": kind,
        "guide": guide,
        "returned_count": len(visible),
        "omitted_rejected_count": omitted,
        "entries": visible,
    }


# --------------------------------------------------------------------------
# gotchas.write
# --------------------------------------------------------------------------


async def _write(
    role: str, arguments: Mapping[str, Any], *, db_path, known_tools: Iterable[str], run_id: str,
    write_lock: "asyncio.Lock", tool_guides: Optional[Mapping[str, str]] = None,
) -> Tuple[str, dict]:
    del tool_guides  # gotchas.write has no use for a tool's guide text
    _reject_unknown_arguments(GOTCHAS_WRITE, arguments, _WRITE_FIELDS)

    async def locked(fn, *args, **kwargs):
        async with write_lock:
            return await _read(fn, *args, **kwargs)

    if arguments.get("id") is not None:
        entry_id = _string_arg(GOTCHAS_WRITE, arguments, "id")
        stray = sorted(set(arguments) & (_NEW_FIELDS - {"tool"}))
        if stray:
            raise GotchaToolError(
                f"{GOTCHAS_WRITE}: passing 'id' records an outcome on an existing gotcha and "
                f"cannot be combined with new-entry fields {stray}. Leave 'id' out to write a new entry."
            )
        if arguments.get("result") is None:
            raise GotchaToolError(
                f"{GOTCHAS_WRITE}: an outcome needs 'result' ({list(store.RESULTS)})"
            )
        existing = await _read(store.get_entry, db_path, entry_id)
        if existing is None:
            raise GotchaToolError(f"{GOTCHAS_WRITE}: no entry with id {entry_id!r}")
        given_tool = arguments.get("tool")
        if given_tool is not None and given_tool != existing["tool"]:
            raise GotchaToolError(
                f"{GOTCHAS_WRITE}: {entry_id} is about {existing['tool']!r}, not {given_tool!r}"
            )
        entry = await locked(
            store.add_outcome, db_path, entry_id, result=arguments.get("result"),
            note=arguments.get("note"), role=role, run_id=run_id,
        )
        return entry_xml(entry), {"entry": entry, "outcome_recorded": True}

    stray = sorted(set(arguments) & {"result", "note"})
    if stray:
        raise GotchaToolError(
            f"{GOTCHAS_WRITE}: {stray} only apply when recording an outcome on an existing "
            "gotcha (pass its 'id')"
        )
    missing = [n for n in ("title", "body") if arguments.get(n) is None]
    if missing:
        raise GotchaToolError(f"{GOTCHAS_WRITE}: a new entry needs {missing}")
    record = {
        "tool": arguments.get("tool"),
        "kind": arguments.get("kind"),
        "list": arguments.get("list", store.LIST_GOTCHA),
        "title": arguments["title"],
        "body": arguments["body"],
        "call_excerpt": arguments.get("call_excerpt"),
        "written_by_role": role,
        "run_id": run_id,
    }
    entry = await locked(store.add_entry, db_path, record, known_tools=list(known_tools))
    return entry_xml(entry), {"entry": entry, "outcome_recorded": False}


_HANDLERS = {GOTCHAS_GET: _get, GOTCHAS_WRITE: _write}


async def call(
    tool_id: str,
    role: str,
    arguments: Mapping[str, Any],
    *,
    db_path,
    known_tools: Iterable[str],
    run_id: str,
    write_lock: "asyncio.Lock",
    tool_guides: Optional[Mapping[str, str]] = None,
) -> Tuple[str, Optional[dict]]:
    """Dispatch one native call, returning `(text, structured)` for
    `dfmcp.server`, or raising `GotchaToolError` for it to turn into an
    `isError` result. `known_tools` is the registry's ids (a write must name a
    real tool); `run_id` is the server's stamp for "this run" (the MCP session
    id); `write_lock` is the server's one `asyncio.Lock`. `tool_guides`
    (added handoffs/2026-10-02-tool-descriptions-split.md), optional: a
    {tool_id: guide text} mapping, used only by `gotchas.get` to attach a
    tool's guide to its gotchas; omitted entirely (default {}) by any caller
    that does not have one, which simply means no call ever returns a guide,
    never an error."""
    handler = _HANDLERS.get(tool_id)
    if handler is None:  # pragma: no cover -- server.py only routes known native ids here
        raise AssertionError(f"gotchas_tools.call: unknown native tool id {tool_id!r}")
    return await handler(
        role, arguments, db_path=Path(db_path), known_tools=known_tools, run_id=run_id,
        write_lock=write_lock, tool_guides=tool_guides or {},
    )
