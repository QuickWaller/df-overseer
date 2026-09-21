"""Native ("server-side") MCP tools: `gotchas.get` and `gotchas.write`.

The two shared tools of the confidence-and-gotchas design
(`docs/BUILDING-TOOL.md`, decision 8, contract C3). Two tools in total, not
two per tool, to keep every role's tool list short.

- **`gotchas.get`** expands a gotcha: by id, or every entry of one tool
  (optionally narrowed to a kind, a list or a status). Results in tool calls
  carry only short titles; the full text, the status and the recorded
  outcomes come from here.
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
    """Same duck-typed shape as `dfmcp.doctrine_tools.NativeTool`."""

    id: str
    mutates: bool = False
    sole_writer_only: bool = False
    native: bool = True
    args: Tuple[str, ...] = ()

    def describe(self, role: str) -> Tuple[str, dict]:
        del role  # neither schema depends on the caller
        if self.id == GOTCHAS_GET:
            return _GET_DESCRIPTION, _GET_SCHEMA
        if self.id == GOTCHAS_WRITE:
            return _WRITE_DESCRIPTION, _WRITE_SCHEMA
        raise AssertionError(f"NativeTool.describe: unknown id {self.id!r}")  # pragma: no cover


# `mutates=False` on both, deliberately: `Tool.mutates` means "mutates fort
# state" and nothing wider (see `dfmcp/queue_tools.py`), so an advisor may hold
# `gotchas.write` without contradicting "advisors are read-only".
NATIVE_TOOLS: Dict[str, NativeTool] = {
    GOTCHAS_GET: NativeTool(id=GOTCHAS_GET),
    GOTCHAS_WRITE: NativeTool(id=GOTCHAS_WRITE),
}

# --------------------------------------------------------------------------
# Descriptions and schemas
# --------------------------------------------------------------------------

_LISTS = list(store.LISTS)
_STATUSES = list(store.STATUSES)

_GET_DESCRIPTION = (
    "Read the gotchas recorded about a tool: notes from earlier runs, each titled with the "
    "condition it applies under. Tool results carry only the titles; this returns the full text, "
    "the status (proposed = an unconfirmed experiment, accepted = confirmed, rejected) and every "
    "recorded outcome. Three modes: pass 'id' for exactly one entry; pass 'tool' (optionally "
    "'kind', 'list', 'status') for that tool's entries, where a 'kind' also returns the tool-wide "
    "entries that apply to every kind; pass neither for an index of which tools have entries. An "
    "unknown tool or id is an error, never an empty list: an empty list means 'this real tool has "
    "no such entries'. Rejected entries are left out of a tool listing by default, and the "
    "response always states how many were left out, even when zero. Read-only."
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
                "A tool id, for example 'building.build'. Refused if it is not a real tool."
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
            "description": "Only with 'tool': gotcha (default: all three lists), unexplained or vent.",
        },
        "status": {
            "type": "string",
            "enum": _STATUSES,
            "description": "Only with 'tool': narrow to one status.",
        },
        "include_rejected": {
            "type": "boolean",
            "description": "Only with 'tool': also return rejected entries (default false).",
        },
    },
}

_WRITE_DESCRIPTION = (
    "Record what you learned about a tool, for the runs after you. Two modes, chosen by whether "
    "'id' is passed. NEW ENTRY (no 'id'): pass 'tool', 'title', 'body' and optionally 'list', "
    "'kind', 'call_excerpt'. The server chooses the id, marks it proposed and stamps your role, "
    "the run and the time. The title must state the condition it applies under, in the form "
    "'<condition>: <hazard>' (for example 'placing a workshop in a desert biome: <what goes "
    "wrong>'), on one line, so a reader can tell from the title alone whether it applies. "
    "'list' is gotcha (something worked out to keep in mind next time; the default), unexplained "
    "(an error or mistake you could not explain) or vent (a complaint that the tool is not right "
    "for what you wanted; never evidence). Near-duplicates, oversized text and unknown tools are "
    "refused with reasons, and a run may write only a few new entries. OUTCOME (with 'id'): pass "
    "'id' of an existing gotcha and 'result' (worked or did_not_work), optionally 'note'. This "
    "appends an outcome and never changes the entry; use it after you tried a proposed gotcha. "
    "One outcome per run per entry."
)

_WRITE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "tool": {
            "type": "string",
            "description": "New entry: the tool id the note is about, for example 'building.build'.",
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

_GET_FIELDS = {"id", "tool", "kind", "list", "status", "include_rejected"}
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
        f'id={quoteattr(entry["id"])} tool={quoteattr(entry["tool"])} '
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
    write_lock: "asyncio.Lock",
) -> Tuple[str, dict]:
    del role, run_id, write_lock
    _reject_unknown_arguments(GOTCHAS_GET, arguments, _GET_FIELDS)
    entry_id = _string_arg(GOTCHAS_GET, arguments, "id")
    tool = _string_arg(GOTCHAS_GET, arguments, "tool")
    kind = _string_arg(GOTCHAS_GET, arguments, "kind")
    list_name = _string_arg(GOTCHAS_GET, arguments, "list")
    status = _string_arg(GOTCHAS_GET, arguments, "status")
    include_rejected = arguments.get("include_rejected", False)
    if not isinstance(include_rejected, bool):
        raise GotchaToolError(f"{GOTCHAS_GET}: 'include_rejected' must be a boolean")

    if entry_id is not None:
        others = [n for n in ("tool", "kind", "list", "status") if arguments.get(n) is not None]
        if others:
            raise GotchaToolError(f"{GOTCHAS_GET}: 'id' cannot be combined with {others}")
        entry = await _read(store.get_entry, db_path, entry_id)
        if entry is None:
            raise GotchaToolError(
                f"{GOTCHAS_GET}: no entry with id {entry_id!r}. Pass 'tool' to list a tool's "
                "entries, or nothing for the index."
            )
        return entry_xml(entry), {"entry": entry}

    if tool is None:
        others = [n for n in ("kind", "list", "status") if arguments.get(n) is not None]
        if others:
            raise GotchaToolError(f"{GOTCHAS_GET}: {others} need 'tool' as well")
        index = await _read(store.tool_index, db_path)
        lines = ["<gotcha_index note=\"only tools with at least one entry are listed; a tool not "
                 "listed has none\">"]
        for t in sorted(index):
            for ln in sorted(index[t]):
                counts = " ".join(f'{s}="{n}"' for s, n in sorted(index[t][ln].items()))
                lines.append(f"  <tool id={quoteattr(t)} list={quoteattr(ln)} {counts}/>")
        lines.append("</gotcha_index>")
        return "\n".join(lines), {"tools": index}

    if tool not in set(known_tools):
        raise GotchaToolError(
            f"{GOTCHAS_GET}: {tool!r} is not a tool in this server's registry. Refusing rather "
            "than returning an empty list, which would read as 'no gotchas' instead of 'not a "
            "real tool'."
        )
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
    head = (
        f'<gotchas tool={quoteattr(tool)} kind={quoteattr(kind or "")} returned="{len(visible)}" '
        f'omitted_rejected="{omitted}">'
    )
    lines = [head]
    if omitted:
        lines.append(
            f"  <note>{omitted} rejected entr{'y' if omitted == 1 else 'ies'} left out; pass "
            "include_rejected:true to see them.</note>"
        )
    if not visible:
        lines.append(f"  <note>{tool} is a real tool and has no matching entries.</note>")
    lines.extend(entry_xml(e) for e in visible)
    lines.append("</gotchas>")
    return "\n".join(lines), {
        "tool": tool,
        "kind": kind,
        "returned_count": len(visible),
        "omitted_rejected_count": omitted,
        "entries": visible,
    }


# --------------------------------------------------------------------------
# gotchas.write
# --------------------------------------------------------------------------


async def _write(
    role: str, arguments: Mapping[str, Any], *, db_path, known_tools: Iterable[str], run_id: str,
    write_lock: "asyncio.Lock",
) -> Tuple[str, dict]:
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
    missing = [n for n in ("tool", "title", "body") if arguments.get(n) is None]
    if missing:
        raise GotchaToolError(f"{GOTCHAS_WRITE}: a new entry needs {missing}")
    record = {
        "tool": arguments["tool"],
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
) -> Tuple[str, Optional[dict]]:
    """Dispatch one native call, returning `(text, structured)` for
    `dfmcp.server`, or raising `GotchaToolError` for it to turn into an
    `isError` result. `known_tools` is the registry's ids (a write must name a
    real tool); `run_id` is the server's stamp for "this run" (the MCP session
    id); `write_lock` is the server's one `asyncio.Lock`."""
    handler = _HANDLERS.get(tool_id)
    if handler is None:  # pragma: no cover -- server.py only routes known native ids here
        raise AssertionError(f"gotchas_tools.call: unknown native tool id {tool_id!r}")
    return await handler(
        role, arguments, db_path=Path(db_path), known_tools=known_tools, run_id=run_id,
        write_lock=write_lock,
    )
