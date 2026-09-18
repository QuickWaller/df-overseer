"""Native ("server-side") MCP tool: `doctrine.get`.

The first thing that reads `doctrine/seed.yaml`. Per that file's own header
comment and `CLAUDE.md`: "the doctrine tier from
docs/MEMORY-ARCHITECTURE.md, which is designed but not built... nothing
reads it yet." This module is that reader, and only that reader: read-only,
no revision path, no write of any kind. Doctrine revisions are proposals
through the queue by agreed design (`Working.md`, "In discussion: designing
the learning loop", 2026-09-17: "Doctrine revisions are proposals; the
Overseer can accept, reject, defer, amend..."); this module never writes
`doctrine/seed.yaml` and has no code path that could.

## Why this is not in `scripts/dfhack/TOOLS.yaml`

Same reasoning as `dfmcp/queue_tools.py`'s own docstring, restated because it
applies here unchanged: `doctrine.get` calls no DFHack command, runs no Lua
script, and touches no fort state at all -- it reads a YAML file that ships
in this repo. `registry.py`'s canonical-id scheme and `tools.py`'s
argv-construction heuristic both exist to turn a DFHack CLI signature into a
JSON schema; neither question is meaningful for a tool with no CLI
signature. So, exactly like the four `queue.*` tools, this one is defined
here, by hand, as a `NativeTool` with an **explicit, hand-written JSON
schema**, merged into the same `dfmcp.registry.Registry` additively via
`registry.load_registry`'s `native_tools=` kwarg, and enforced through the
exact same `Roster.check(role, tool_id)` boundary as every DFHack tool and
every `queue.*` tool. One boundary, not a second permission path.

## Reuses `doctrine/validate.py`'s validation, does not re-implement it

`doctrine/validate.py`'s own module docstring says it is "the first thing
that reads `doctrine/`" and exists "to keep the data well-formed for
whenever something does" -- this is that something. `_load_entries` below
opens and `yaml.safe_load`s the file exactly once (there is no way around
that: `validate.validate()` only ever returns an error list, never the
parsed data alongside it, so getting both without parsing twice means
parsing here and handing the *already-parsed* data to `validate.validate()`
for every structural check -- required fields, closed enums, the
verified-needs-a-53.16-source rule, duplicate ids). Every validation rule
itself still lives in exactly one place. If a future caller wants
"parse and validate" as one call, that belongs in `doctrine/validate.py`
itself (e.g. a `load(path) -> list[dict]` that raises on error) rather than
being invented a second time here; flagged in this stream's report rather
than done here, since `doctrine/validate.py` is outside this stream's
touched surfaces.

A malformed or missing `doctrine/seed.yaml` is a **hard, loud failure**
(`DoctrineToolError`, caught by `dfmcp.server` the same way
`queue_tools.QueueToolError` already is, and turned into `isError=True`),
never an empty result and never a quiet fallback. Silently serving nothing
from a broken doctrine file would look exactly like "there is no doctrine on
this" -- the one failure mode this whole tool exists to prevent (see the
next section).

## The property that matters most: status and sources survive, unflattened

This project has repeatedly caught itself losing a claim's provenance on the
way to using it: an illustrative "11 days" quoted back as measured data,
three `universal` doctrine entries marked `verified` on one pond's evidence
before the provenance format existed. `doctrine/seed.yaml`'s header exists
specifically to stop that, with a `status` (`prior`/`verified`/`refuted`) and
a `sources` list (never a single blob) on every entry. A reader that
collapsed those into one string, or silently dropped `refuted` entries,
would industrialise exactly the failure the format was built to catch. So:

- Every entry this module returns -- by id, by topic, or (implicitly, as
  counts) in the topic index -- carries its `status` as a first-class,
  highly visible field (an XML attribute in the text form, a top-level key
  in the structured form), never buried in prose.
- Every entry's `sources` list is returned whole: each source's `kind`,
  `ref`, `describes`, `read` and `accessed` (where present) survive
  separately, never joined into a sentence. A `prior` built on one
  `kind: user, read: recalled` source and a `verified` entry citing a
  `kind: live-read, describes: "53.16", read: opened` source must be
  distinguishable by inspecting the response alone, with no need to cross-
  reference `doctrine/seed.yaml` itself.
- A `prior` or `refuted` entry gets an explicit `<warning>` line (text form)
  / no special structured field beyond `status` itself (the structured
  `status` value is already unambiguous for a machine reader; the `warning`
  text exists for a model reading the XML form, which is what actually gets
  put in a prompt -- `docs/AGENT-ARCHITECTURE.md` §4's own reasoning for
  XML: "the form models handle most reliably").
- A **by-id** lookup always returns the entry regardless of status --
  the caller named that id explicitly, so there is no ambiguity to protect
  against by hiding it, and hiding it would itself be the silent-drop
  failure this module exists to avoid.
- A **by-topic** lookup omits `refuted` entries by default (an agent asking
  "what do I know about drink" should not be handed a refuted claim as if it
  were live guidance), but the response **always** states how many were
  omitted, even when that number is zero, via a structural `omitted_refuted`
  field/attribute that can never be silently absent. Pass
  `include_refuted: true` to get them anyway, still clearly labelled
  `status="refuted"` with their warning.
- The **topic index** never omits anything: it reports a `prior`/`verified`/
  `refuted` breakdown per topic unconditionally, so even the index alone
  cannot be read as "these topics have no refuted history."

## `knowledge_scope`: deliberately not set, and why

Every DFHack-backed `Tool` in the registry carries a `knowledge_scope`
(`player_visible` / `player_derivable` / `omniscient` -- `registry.py`,
decisions/DECISIONS.md 2026-09-16, "agents may only know what a vanilla
player could know"). `dfmcp.roles` rule 7 refuses to load any role granted a
tool tagged `omniscient`, and treats a **missing** `knowledge_scope`
attribute as simply not this rule's concern (`roles.py`, the comment on rule
7: "a native (non-DFHack) tool such as `queue.propose`... carries no
`knowledge_scope` at all -- it reads and writes `dfqueue`'s own ledger,
never fort/world state, so it is not this rule's concern").

The same reasoning applies to `doctrine.get`, considered deliberately rather
than assumed: `knowledge_scope` classifies a *live read of fort/world
state* by how a vanilla player could have come to know it -- a screen the
game shows (`player_visible`), a safe computation over such a screen
(`player_derivable`), or neither (`omniscient`, forbidden everywhere).
`doctrine.get` never reads fort or world state at all; it reads this
project's own curated, human/agent-authored corpus of game-mechanics
knowledge, each entry carrying its *own* provenance already (which is a
different, and stronger, disclosure than a live-state visibility tag would
give it -- a `knowledge_scope` tag says "how a player could see this kind of
fact"; a doctrine entry's `sources` say exactly which fact, from exactly
which source, read how, on what date). Forcing one of the three values onto
this tool would misrepresent what the data even is: `player_derivable`
specifically means "a safe computation over player-visible facts," and nine
of this file's current entries are `prior` (received knowledge, not
computed from anything visible in this fort at all) or `refuted` (kept
*because* they are not to be trusted as a fact about anything). So, exactly
like `queue.propose`/`queue.pass`/`queue.rule`/`queue.pending`: no
`knowledge_scope` attribute is set on this module's `NativeTool`, and this
paragraph is the deliberate reasoning the brief asked for, not an oversight.

One open question flagged here rather than solved here (content curation of
`doctrine/seed.yaml` is outside this stream's touched surfaces): a doctrine
entry could in principle be built on a source that a live-state
`knowledge_scope: omniscient` tool once produced, which would let a role
without that tool learn the same fact secondhand through doctrine. Nothing
in the current 27 entries appears to do this (sources cite raws, in-repo
research docs, `plotinfo`/`overview.get`-shaped live reads, user recall and
wiki -- no entry's source is one of this registry's own `omniscient`-tagged
commands), but this module has no mechanism to detect or prevent it if a
future doctrine entry did. Worth a deliberate decision by whoever curates
`doctrine/seed.yaml` next, not assumed away here.

## Where the file lives at runtime

`doctrine_path` is a parameter to `call()`, exactly mirroring how
`dfmcp/queue_tools.py`'s `db_path` is threaded through from
`dfmcp/server.py`'s `ServerConfig`, not a module-level constant baked at
import time. Unlike `queue_db` (which has no default because it is
runtime-written data that a code redeploy must never be able to clobber --
`ServerConfig`'s own docstring), `doctrine/seed.yaml` is checked into this
repo, read-only from this module's point of view, and travels with the code
on every deploy -- so `DEFAULT_DOCTRINE_PATH` below (mirroring
`registry.DEFAULT_TOOLS_YAML`'s own in-tree default) is a sensible default,
overridable via `MCP_SERVER_DOCTRINE_PATH` for a deploy layout that differs.
See this stream's report for exactly what VM 103's deploy needs (the file
must exist at that path on the server; the stream that build this did not
deploy).

The file is re-read on every `doctrine.get` call, not cached: it is small
(27 entries, single-digit KB), so the cost is negligible, and caching would
mean a doctrine edit needs a server restart to take effect, which is a
worse trade for a knowledge base people are meant to keep correcting.
"""

from __future__ import annotations

import copy
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from xml.sax.saxutils import escape, quoteattr

import yaml

from doctrine import validate as doctrine_validate

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOCTRINE_PATH = REPO_ROOT / "doctrine" / "seed.yaml"

# --------------------------------------------------------------------------
# Tool id
# --------------------------------------------------------------------------

DOCTRINE_GET = "doctrine.get"

NATIVE_TOOL_IDS = (DOCTRINE_GET,)


class DoctrineToolError(Exception):
    """A `doctrine.get` call is refused: bad arguments, an unknown topic, an
    unknown id, or `doctrine/seed.yaml` being absent/unreadable/invalid
    against its own validator. Always caught by `dfmcp.server` and turned
    into an MCP tool result with `isError=True` carrying this exception's
    message -- never raised past that boundary, matching how
    `dfmcp.queue_tools.QueueToolError` is already handled
    (`dfmcp/server.py`'s "Denials" note)."""


# --------------------------------------------------------------------------
# NativeTool: what registry.py and roles.py need, duck-typed against Tool
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NativeTool:
    """See this module's docstring for exactly which attributes
    `dfmcp.roles`/`dfmcp.tools` read and why each is shaped the way it is
    -- the same shape as `dfmcp.queue_tools.NativeTool`, defined again here
    rather than shared, because `.describe()` is necessarily specific to
    this module's own tool id (see `dfmcp.queue_tools.NativeTool.describe`,
    which is equally specific to its own four ids)."""

    id: str
    mutates: bool = False
    sole_writer_only: bool = False
    native: bool = True
    args: Tuple[str, ...] = ()

    def describe(self, role: str) -> Tuple[str, dict]:
        # `role` is accepted (dfmcp.tools.tool_definitions always passes it)
        # but unused: unlike queue.propose's type vocabulary, doctrine.get's
        # schema does not depend on who is calling -- the topic list and the
        # id/topic/include_refuted shape are the same for every role that
        # holds this tool.
        del role
        if self.id == DOCTRINE_GET:
            return _GET_DESCRIPTION, _GET_SCHEMA
        raise AssertionError(f"NativeTool.describe: unknown id {self.id!r}")  # pragma: no cover


NATIVE_TOOLS: Dict[str, NativeTool] = {
    DOCTRINE_GET: NativeTool(id=DOCTRINE_GET, mutates=False, sole_writer_only=False),
}


# --------------------------------------------------------------------------
# Schema and description: hand-written, per this module's docstring
# --------------------------------------------------------------------------

_TOPICS_SORTED = sorted(doctrine_validate.TOPICS)

_GET_DESCRIPTION = (
    "Read this fort's own accumulated, provenance-tagged game knowledge "
    "(doctrine/seed.yaml). Read-only; never writes or proposes a revision. "
    "Three modes, chosen by which arguments are set: pass 'id' for exactly "
    "one entry; pass 'topic' for every entry filed under that topic (an "
    "unknown topic is refused, never an empty list -- an empty list would "
    "read as 'no doctrine on this' when the real answer is 'that is not a "
    "real topic'); pass neither for a topic index (every topic, its total "
    "entry count, and its prior/verified/refuted breakdown). Every entry "
    "returned carries its own 'status' (prior/verified/refuted) and its "
    "full, unflattened 'sources' list -- a prior built on a recalled, "
    "undated source and a verified entry citing this install's own raws "
    "are never presented as equivalent. Refuted entries are omitted from a "
    "topic lookup by default (never from a by-id lookup, and never from the "
    "index's counts); the response always states how many were omitted, "
    "even when zero. Pass include_refuted:true to see them anyway, still "
    "clearly labelled refuted."
)

_GET_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {
            "type": "string",
            "description": (
                "Look up exactly one doctrine entry by its stable id. "
                "Refused if no entry has this id. Mutually exclusive with "
                "'topic'; when set, 'include_refuted' has no effect (a "
                "by-id lookup always returns the entry, whatever its "
                "status)."
            ),
        },
        "topic": {
            "type": "string",
            "enum": _TOPICS_SORTED,
            "description": (
                "Every doctrine entry filed under this topic, from the "
                "closed topic vocabulary doctrine/validate.py enforces. "
                "Mutually exclusive with 'id'. A value outside this list "
                "is refused (isError), never an empty result -- see this "
                "tool's own description for why. Call with neither 'id' "
                "nor 'topic' first to see which topics currently have "
                "entries."
            ),
        },
        "include_refuted": {
            "type": "boolean",
            "description": (
                "Only affects a 'topic' lookup. Default false: refuted "
                "entries under that topic are left out of the returned "
                "list, but the response always reports how many were "
                "omitted (0 if none). Set true to get them anyway, still "
                "labelled status=refuted with a warning. No effect on a "
                "by-id lookup (always returned regardless of status) or "
                "the topic index (always reports full status breakdowns)."
            ),
        },
    },
}

_GET_FIELDS = {"id", "topic", "include_refuted"}


# --------------------------------------------------------------------------
# Loading doctrine/seed.yaml -- see module docstring, "Reuses
# doctrine/validate.py's validation, does not re-implement it"
# --------------------------------------------------------------------------


def _json_safe(value: Any) -> Any:
    """`doctrine/seed.yaml`'s `accessed` field is often an unquoted ISO
    date, which PyYAML parses into `datetime.date` -- not JSON-serialisable
    for MCP `structuredContent`, and not what `str()` alone would render
    predictably for the XML text form either (it works, but this makes the
    conversion explicit and total rather than incidental to `str()`'s
    default behaviour). Recurses through dict/list; every other value is
    returned unchanged."""
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _load_entries(doctrine_path: Path) -> List[dict]:
    """Open, parse and validate `doctrine_path`, raising `DoctrineToolError`
    (never returning an empty/partial result) for a missing file, a YAML
    parse error, or any `doctrine.validate.validate` finding. See this
    module's docstring for why parsing happens here rather than a second
    time inside `validate.validate` itself."""
    path = Path(doctrine_path)
    if not path.is_file():
        raise DoctrineToolError(
            f"{DOCTRINE_GET}: doctrine file not found at {path} -- set "
            "MCP_SERVER_DOCTRINE_PATH (or pass doctrine_path explicitly) to "
            "the real location, or deploy doctrine/seed.yaml alongside the "
            "code. Refusing rather than serving an empty doctrine, which "
            "would read as 'this fort has no doctrine' instead of 'the file "
            "is missing'."
        )
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise DoctrineToolError(f"{DOCTRINE_GET}: {path} is not valid YAML: {exc}") from exc

    if data is None:
        data = []

    errors = doctrine_validate.validate(data)
    if errors:
        detail = "; ".join(errors)
        raise DoctrineToolError(
            f"{DOCTRINE_GET}: {path} fails doctrine/validate.py's own validator "
            f"({len(errors)} error(s)), refusing to serve it: {detail}"
        )

    return [_json_safe(entry) for entry in data]


# --------------------------------------------------------------------------
# Indexing and filtering
# --------------------------------------------------------------------------

_STATUS_KEYS = ("prior", "verified", "refuted")


def _topic_index(entries: List[dict]) -> Dict[str, dict]:
    """Every topic in the closed vocabulary, present or not, so a caller can
    see that a legal topic currently has zero entries rather than confusing
    that with an unknown topic (which `doctrine.get` refuses instead)."""
    index: Dict[str, dict] = {
        topic: {"count": 0, "by_status": {k: 0 for k in _STATUS_KEYS}}
        for topic in _TOPICS_SORTED
    }
    for entry in entries:
        status = entry.get("status")
        for topic in entry.get("topics", []):
            if topic not in index:  # defensive: validate() already refused this
                continue
            index[topic]["count"] += 1
            if status in index[topic]["by_status"]:
                index[topic]["by_status"][status] += 1
    return index


def _entries_for_topic(entries: List[dict], topic: str) -> List[dict]:
    return [e for e in entries if topic in e.get("topics", [])]


def _entry_by_id(entries: List[dict], entry_id: str) -> Optional[dict]:
    for entry in entries:
        if entry.get("id") == entry_id:
            return entry
    return None


# --------------------------------------------------------------------------
# XML rendering -- the form put in a prompt, per docs/AGENT-ARCHITECTURE.md
# §4 ("Records are rendered as XML when placed into a prompt")
# --------------------------------------------------------------------------

_PRIOR_WARNING = (
    "PRIOR: received knowledge, not yet confirmed by this install's own "
    "data. Treat as a hypothesis, not settled guidance."
)
_REFUTED_WARNING = (
    "REFUTED: kept only so this mistake is not repeated. Do NOT treat as "
    "current guidance."
)
_WARNING_BY_STATUS = {"prior": _PRIOR_WARNING, "refuted": _REFUTED_WARNING}


def _source_xml(source: dict) -> str:
    attrs = "".join(
        f" {name}={quoteattr(str(source[name]))}"
        for name in ("kind", "ref", "describes", "read", "accessed")
        if name in source
    )
    return f"    <source{attrs}/>"


def _entry_xml(entry: dict) -> str:
    status = entry.get("status", "")
    lines = [
        f'<doctrine_entry id={quoteattr(str(entry.get("id", "")))} '
        f'scope={quoteattr(str(entry.get("scope", "")))} '
        f'status={quoteattr(str(status))}>'
    ]
    warning = _WARNING_BY_STATUS.get(status)
    if warning:
        lines.append(f"  <warning>{escape(warning)}</warning>")
    lines.append("  <topics>")
    for topic in entry.get("topics", []):
        lines.append(f"    <topic>{escape(str(topic))}</topic>")
    lines.append("  </topics>")
    lines.append(f'  <statement>{escape(str(entry.get("statement", "")))}</statement>')
    if entry.get("note"):
        lines.append(f'  <note>{escape(str(entry["note"]))}</note>')
    lines.append("  <sources>")
    for source in entry.get("sources", []):
        lines.append(_source_xml(source))
    lines.append("  </sources>")
    lines.append("</doctrine_entry>")
    return "\n".join(lines)


def _index_xml(index: Dict[str, dict]) -> str:
    lines = ["<doctrine_index>"]
    for topic in _TOPICS_SORTED:
        stats = index[topic]
        by_status = stats["by_status"]
        lines.append(
            f'  <topic name={quoteattr(topic)} count="{stats["count"]}" '
            f'prior="{by_status["prior"]}" verified="{by_status["verified"]}" '
            f'refuted="{by_status["refuted"]}"/>'
        )
    lines.append("</doctrine_index>")
    return "\n".join(lines)


def _topic_result_xml(topic: str, visible: List[dict], omitted_refuted: int) -> str:
    lines = [
        f'<doctrine_topic name={quoteattr(topic)} returned="{len(visible)}" '
        f'omitted_refuted="{omitted_refuted}">'
    ]
    if omitted_refuted:
        lines.append(
            f"  <note>{omitted_refuted} refuted entr"
            f"{'y' if omitted_refuted == 1 else 'ies'} under this topic "
            "omitted; pass include_refuted:true to see them.</note>"
        )
    for entry in visible:
        lines.append(_entry_xml(entry))
    lines.append("</doctrine_topic>")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Handler
# --------------------------------------------------------------------------


def _reject_unknown_arguments(arguments: Mapping[str, Any], known: set) -> None:
    """Same real-enforcement pattern as `dfmcp.queue_tools`'s function of the
    same name: `additionalProperties: false` in the schema is defence in
    depth, not the boundary -- a client need not validate against the
    schema it was handed."""
    unknown = sorted(set(arguments) - known)
    if unknown:
        raise DoctrineToolError(
            f"{DOCTRINE_GET}: unexpected argument(s) {unknown}; accepts only "
            f"{sorted(known)}"
        )


async def _get(
    role: str, arguments: Mapping[str, Any], *, doctrine_path: Path,
) -> Tuple[str, dict]:
    del role  # doctrine content is not role-scoped; access itself is (roles.py)
    _reject_unknown_arguments(arguments, _GET_FIELDS)

    entry_id = arguments.get("id")
    topic = arguments.get("topic")
    include_refuted = bool(arguments.get("include_refuted", False))

    if entry_id is not None and not isinstance(entry_id, str):
        raise DoctrineToolError(f"{DOCTRINE_GET}: 'id' must be a string, got {entry_id!r}")
    if topic is not None and not isinstance(topic, str):
        raise DoctrineToolError(f"{DOCTRINE_GET}: 'topic' must be a string, got {topic!r}")
    if entry_id is not None and topic is not None:
        raise DoctrineToolError(
            f"{DOCTRINE_GET}: pass at most one of 'id' or 'topic', not both "
            f"(got id={entry_id!r}, topic={topic!r})"
        )

    entries = _load_entries(doctrine_path)

    if entry_id is not None:
        entry = _entry_by_id(entries, entry_id)
        if entry is None:
            raise DoctrineToolError(
                f"{DOCTRINE_GET}: no doctrine entry with id {entry_id!r}. Call "
                "with neither 'id' nor 'topic' for the topic index, or a "
                "'topic' to browse."
            )
        return _entry_xml(entry), {"entry": copy.deepcopy(entry)}

    if topic is not None:
        if topic not in doctrine_validate.TOPICS:
            raise DoctrineToolError(
                f"{DOCTRINE_GET}: {topic!r} is not a doctrine topic. Valid "
                f"topics: {_TOPICS_SORTED}. Refusing rather than returning an "
                "empty list, which would read as 'no doctrine on this' "
                "instead of 'that topic does not exist'."
            )
        matching = _entries_for_topic(entries, topic)
        refuted = [e for e in matching if e.get("status") == "refuted"]
        visible = matching if include_refuted else [e for e in matching if e.get("status") != "refuted"]
        omitted_refuted = 0 if include_refuted else len(refuted)
        text = _topic_result_xml(topic, visible, omitted_refuted)
        structured = {
            "topic": topic,
            "returned_count": len(visible),
            "omitted_refuted_count": omitted_refuted,
            "entries": copy.deepcopy(visible),
        }
        return text, structured

    index = _topic_index(entries)
    return _index_xml(index), {"topics": copy.deepcopy(index)}


_HANDLERS = {
    DOCTRINE_GET: _get,
}


async def call(
    tool_id: str, role: str, arguments: Mapping[str, Any], *,
    doctrine_path: Path = DEFAULT_DOCTRINE_PATH,
) -> Tuple[str, Optional[dict]]:
    """Dispatch one native tool call. Returns `(text, structured)` for
    `dfmcp.server` to wrap into a `CallToolResult(isError=False, ...)`, or
    raises `DoctrineToolError` for `dfmcp.server` to turn into
    `isError=True`. Never called for an id outside `NATIVE_TOOL_IDS` --
    `dfmcp.server` only reaches this after confirming `registry.get(tool_id)`
    is a native tool belonging to this module.

    `async def` to match `dfmcp.queue_tools.call`'s shape (so
    `dfmcp/server.py`'s dispatch can `await` either uniformly), even though
    this module does no actual awaiting -- see the module docstring on why
    the file is re-read synchronously rather than pushed to a thread.
    """
    handler = _HANDLERS.get(tool_id)
    if handler is None:  # pragma: no cover -- server.py only routes known native ids here
        raise AssertionError(f"doctrine_tools.call: unknown native tool id {tool_id!r}")
    return await handler(role, arguments, doctrine_path=Path(doctrine_path))
