"""Turns the registry (registry.py) and the roster (roles.py) into MCP tool
definitions, and turns a validated MCP tool call back into the exact DFHack
command line (`dfhack-run lua -f <script> <verb> <args...>` minus the
`dfhack-run lua -f` part, which is the transport's job, not this module's).

Transport-independent by design: this module never imports an MCP SDK and
does not know what HTTP is. It is a pure function of the registry and the
roster, both themselves pure functions of YAML already in this repo (see
mcp/README.md). Nothing here calls DFHack, opens a socket, or touches a VM.

## Tool names vs canonical ids

Canonical ids (`openarea.build`) contain a dot. MCP/Anthropic tool names
generally may not: the widely-enforced pattern is `^[a-zA-Z0-9_-]{1,128}$`.
So every id gets a distinct MCP-legal *name*, built once at load time as a
pair of dictionaries (id -> name, name -> id) by `build_tool_names`. The
reverse direction is a dict lookup, never string surgery (never
`name.replace("__", ".")`): a future script short name that happened to
contain the separator would silently map two ids onto one name if the
reverse were derived by parsing the name instead of looked up. A name
collision (two ids producing the same name) is a hard error at load time,
matching registry.py's own id-collision behaviour.

The current transform is `id.replace(".", "__")`
(`openarea.build` -> `openarea__build`), verified against the real manifest's
full 27-id table in `mcp/tests/test_tools.py`: every id contains only
lowercase letters, digits and hyphens either side of exactly one dot, so the
transform always lands inside `^[a-zA-Z0-9_-]{1,128}$` and always keeps ids
distinguishable by name. If `TOOLS.yaml` ever grows an id with more than one
dot or with `__` inside a script/verb segment, `build_tool_names` will raise
rather than silently mint an ambiguous name.

## Tool definitions: what the description must carry

Per docs/AGENT-ARCHITECTURE.md §10, agents inherit stated reliability rather
than inventing it, so `tool_definitions`'s description for each tool states,
from the manifest and nowhere else:

- what the command does (`Tool.description`, i.e. TOOLS.yaml's `notes`),
- whether it mutates fort state,
- its verification status, stated plainly when it is NOT verified. This is
  the one CLAUDE.md and docs/TRAPS.md have already paid for once
  (`unit-status hostile` trusted beyond its evidence): `Tool.is_verified` is
  deliberately conservative (False for a missing field, not just for the
  literal "unverified"), and this module never upgrades that into a clean
  bill of health. An unverified tool's description says so in plain words.

`tool_definitions(registry, roster, role)` filters through
`Roster.check(role, tool_id)` -- never by re-reading a role's tools.yaml
directly -- so the returned list is exactly what that role may actually call.

## Input schemas: a documented heuristic, not knowledge

`TOOLS.yaml` carries no argument types, only signature text like
`"build W H [LEVEL] NEAR_LANDMARK BLUEPRINT_FILE [RANK] [RADIUS_TILES]"`.
`Tool.args` already tokenises the part after the verb; this module turns
each token into a JSON-Schema property:

- `[BRACKETED]` means optional (`required: false`); a bare token is required.
- **Type is a documented heuristic.** `_INTEGER_ARG_NAMES` below is the one
  explicit table of argument names this module treats as `"integer"`;
  everything else defaults to `"string"`. It was built by reading, not
  guessing: every name in it was confirmed against the actual `tonumber(...)`
  call in the owning .lua script's dispatch code (the sweep is recorded in
  `mcp/tests/test_tools.py`). If `TOOLS.yaml` grows a new integer-valued
  argument, add its name here -- this table does not derive itself from
  anything and a missing entry silently (if harmlessly) falls back to
  `"string"`, which DFHack's own `tonumber()` on the Lua side will then
  usually still accept since numerals parse fine as strings.
- **Two argument tokens in the real manifest are not names at all: they are
  literal choices** (`"on|off"` in `labor.set-labor`, and
  `"[idle|injured|military|hostile]"` in `labor.unit-status`). These are
  detected by the `|` in the token, turned into a `"string"` property with an
  explicit `enum` of the choices, and given a synthesised name (the choices
  joined with `_`, e.g. `on_off`) since the manifest gives them no other
  name. Flagged here rather than silently mis-typed as a normal identifier.
- **One further wrinkle the heuristic table doesn't cover: a repeated name
  within one signature.** `connectivity.check-units UNIT_ID UNIT_ID` has two
  positional arguments that are both literally named `UNIT_ID` in the
  manifest (a "from" unit and a "to" unit). JSON-Schema properties must be
  unique, so `_arg_specs_for_tool` suffixes a repeated name with `_1`, `_2`,
  ... in signature order (`unit_id_1`, `unit_id_2`). This is the single
  source of truth for that naming, used identically by both
  `tool_definitions` and `argv_for_call`, so the two can never disagree about
  which name means which position.

Sweep result over the real, current manifest (27 tools): every argument
token is one of a plain `UPPER_CASE` placeholder, or one of the two
literal-choice tokens named above. Nothing else was found that this table
does not confidently cover.

## Optional groups and repeated arguments

Added 2026-09-21 (`handoffs/2026-09-21-optional-and-variadic-args.md`).
Two forms beyond `NAME` and `[NAME]`, and nothing else:

- **`[A B]`, an all-or-nothing optional group.** The registry keeps a
  bracketed run as one token. Each member becomes its own flat, optional,
  separately typed and described property (`w`, `h`), never a nested object,
  so an existing caller passing `{"w": 3, "h": 3}` is unchanged and a model
  sees the same flat shape it always did. The pairing is enforced in
  `argv_for_call`: one member without the others is an `ArgumentError`
  naming the group and the missing member, never a silent default. A group
  counts as ONE optional slot for the gap check below.
- **`NAME...` (required, one or more) and `[NAME...]` (optional), a repeated
  argument.** It must be the last token (anything after it would be
  ambiguous on a positional command line), becomes an `array` property named
  like any other token (`LABOR...` -> `labor`), and is expanded into one
  argv word per item. Each item gets the same type, boolean, and shell-
  metacharacter checks as a single value. A bare scalar is accepted as a
  one-item array (the same meaning, and it is what a caller written against
  the old one-labor signature sends); an empty array is missing for a
  required argument and omitted for an optional one.

A token that is none of these (`[w`, `LAB OR`, `A..B`) is a `ToolSchemaError`
when the schema or argv is built, not a property with a junk name.

**Why the gap check needs a declaration for groups.** The rule below (a
later optional cannot be given while an earlier one is omitted) stops a
positional command line from silently shifting. An omitted `[W H]` followed
by a given `LEVEL` is exactly that shape, and for a purely positional CLI it
would put LEVEL in W's slot. `df-overseer-building.lua` is not purely
positional: it reads up to three leading numbers after KIND and decides what
they are by how many there are (1 = LEVEL, 2 = W H, 3 = W H LEVEL). So it is
safe to leave `[W H]` out while giving LEVEL, and only that CLI can say so.
A command opts in with `skippable: ["[W H]"]` in TOOLS.yaml (validated by the
registry against the signature); everything without the key keeps the strict
rule, so a future group on a positional CLI cannot shift arguments by
accident.

## Argument descriptions: another table, not per-tool YAML

Added 2026-09-14 (`handoffs/2026-09-14-relative-level-args.md`), closing a
gap the same stream found live: the schema gave the model an argument named
`z` with **no description at all**, so nothing told a caller it was an
absolute DF map coordinate (Uniboslan's own map runs z 0-185) rather than
something small and relative -- a live probe called `diggable.find` with
`z=0/-1/-2/-3/-4`, all nowhere near the fort, got `[]` every time, and wrongly
concluded there was nothing to dig. `z` is now `LEVEL`, an offset relative to
the landmark's own level (see the Lua scripts' own headers), but the deeper
problem -- a schema with no per-argument descriptions at all -- would have
undersold ANY renamed argument the same way. `_ARG_DESCRIPTIONS` is one
table, keyed by the same raw manifest token `_parse_arg_token` already
reads (`"LEVEL"`, `"NEAR_LANDMARK"`, `"W"`, ...), living right next to it
rather than in `TOOLS.yaml` -- adding a `description:` field per command
there would mean re-typing near-identical prose once per tool instead of
once per argument shape, and would drift the way a copy-pasted comment
always does. A token with no entry gets no `"description"` key in its
schema property (never an empty string) -- the same "harmless, honest gap"
default `_INTEGER_ARG_NAMES` uses for type. Covered as of this stream:
`LEVEL`, `NEAR_LANDMARK`, `RADIUS_TILES`, `W`, `H`, `RANK`, `BLUEPRINT_FILE`
-- every argument name in `openarea.*`/`diggable.*`/`chokepoints.find`, the
three tools this stream touched, plus the ones shared widely enough
(`W`/`H`/`RANK`) to be worth describing once. Every entry states plainly
that the argument is never a raw coordinate, where that's true.

## Turning a call back into argv: the one real trap

Ground truth for the shape, confirmed by reading the dispatch code of every
one of the 12 `scripts/dfhack/df-overseer-*.lua` files (not assumed from
one): each script ends with `local args = {...}; local cmd = args[1]`, so
DFHack scripts receive **Lua varargs, not a global `arg` table**
(`docs/TRAPS.md`), and `args[1]` is always the verb. `overview.get` is
therefore `["df-overseer-overview", "get"]`; `openarea.build` is
`["df-overseer-openarea", "build", W, H, ...]` in the manifest's own
signature order.

**Positional optionals cannot be skipped out of order.** If a caller
supplies a later optional argument (e.g. `RANK`) while omitting an earlier
one in the signature (e.g. `LEVEL`), there is no way to express that on a
positional command line without silently shifting every argument after it
into the wrong slot -- which is exactly the class of bug this project has
already paid for twice (the `quickfort -c` top-left-vs-centre bug,
`decisions/DECISIONS.md` 2026-09-11). So `argv_for_call` raises a specific
`ArgumentError` naming both the blocking (omitted) and the triggering
(supplied) argument, rather than guessing a shift. This check only concerns
optional arguments relative to each other: a required argument positioned
after an optional one (e.g. `NEAR_LANDMARK` after `[LEVEL]` in
`openarea.build`) is validated independently and does not interact with the
gap check.

`argv_for_call` also rejects: any argument name not in the tool's schema,
any missing required argument, and any string-typed value containing a
shell metacharacter (`_SHELL_METACHAR_RE`) -- these values become literal
words on a command line run against a live game host, so smuggling a `;` or
a backtick through a string argument is exactly the kind of thing this layer
exists to catch before it reaches a transport this module has never heard of.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .registry import Registry, Tool
from .roles import Roster

# --------------------------------------------------------------------------
# Tool names
# --------------------------------------------------------------------------

_NAME_SEPARATOR = "__"
_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


class ToolSchemaError(Exception):
    """A structural problem building tool names or schemas from the registry.

    Always a hard failure at build time, matching registry.py's and roles.py's
    own style: a bad manifest must not silently produce a wrong or ambiguous
    MCP surface.
    """


def _tool_name(tool_id: str) -> str:
    """"openarea.build" -> "openarea__build". A pure, deterministic function
    of the id. See this module's docstring for why "__" and why the reverse
    direction is never derived from this by string surgery."""
    return tool_id.replace(".", _NAME_SEPARATOR)


def build_tool_names(registry: Registry) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Build (id -> name, name -> id) once, over every id in the registry.

    Raises ToolSchemaError if a generated name is not MCP-legal, or if two
    ids produce the same name. Both are load-time hard errors: a silently
    wrong or ambiguous tool name is worse than refusing to start.
    """
    id_to_name: Dict[str, str] = {}
    name_to_id: Dict[str, str] = {}
    for tool_id in registry.ids():
        name = _tool_name(tool_id)
        if not _TOOL_NAME_RE.match(name):
            raise ToolSchemaError(
                f"generated tool name {name!r} for id {tool_id!r} does not match "
                f"the MCP-legal pattern {_TOOL_NAME_RE.pattern!r}"
            )
        if name in name_to_id:
            raise ToolSchemaError(
                f"tool name collision: both {tool_id!r} and {name_to_id[name]!r} "
                f"produce the name {name!r}"
            )
        id_to_name[tool_id] = name
        name_to_id[name] = tool_id
    return id_to_name, name_to_id


# --------------------------------------------------------------------------
# Argument parsing: the documented type/name heuristic
# --------------------------------------------------------------------------

# Every name here was confirmed by reading the owning .lua script's dispatch
# code for a `tonumber(args[n])` call on that position -- not guessed from the
# name looking numeric. See mcp/tests/test_tools.py for the sweep and the
# file:line each entry was checked against. If TOOLS.yaml grows a new
# argument that DFHack-side code treats as numeric, add its name here; a
# missing entry defaults to "string" (see module docstring).
_INTEGER_ARG_NAMES = frozenset(
    {
        "W",
        "H",
        "LEVEL",
        "RANK",
        "RADIUS_TILES",
        "UNIT_ID",
        "REPORT_ID",
        "CURSOR",
        "N",
        "MIN_IDLE_TICKS",
    }
)

_BRACKET_RE = re.compile(r"^\[(.+)\]$")

# One table, keyed by the raw manifest token (upper-case, brackets already
# stripped by the time _parse_arg_token looks it up) -- see the module
# docstring's "Argument descriptions" section for why this lives here rather
# than as a per-command TOOLS.yaml field. A token with no entry here gets no
# "description" key in its schema property at all (never an empty string):
# the same honest-gap default _INTEGER_ARG_NAMES uses for type.
_ARG_DESCRIPTIONS: Dict[str, str] = {
    "POSITION_CODE": (
        "The code of a fortress position exactly as nobles.list shows it, "
        "for example MANAGER, BOOKKEEPER or BROKER. An unknown code is an "
        "error that lists the known ones."
    ),
    "VERSION": (
        "How much the write records: minimal (the default, the two "
        "assignment fields and the position link) or with_event (also the "
        "history event). Leave it out unless minimal fails a nobles.verify."
    ),
    "DRY_RUN": (
        "true (the default) only reports what would change; only the exact "
        "word false makes the change."
    ),
    "LEVEL": (
        "An offset relative to NEAR_LANDMARK's own level, NOT an absolute DF "
        "map coordinate: 0 (the default when omitted) is the landmark's own "
        "level, -1 is one level below it, 1 is one level above it. A level "
        "below the dug-out fort returns nothing until something walkable "
        "exists there -- v1 only returns candidates that border the "
        "existing walkable network."
    ),
    "NEAR_LANDMARK": (
        "The name of an existing landmark to search or act near (see "
        "landmarks.list / landmarks.get for real names). Never a raw "
        "coordinate."
    ),
    "RADIUS_TILES": (
        "How far from NEAR_LANDMARK to search, in tiles. Clamped to a hard "
        "cap of 60 tiles server-side regardless of the value passed."
    ),
    "W": "Width, in tiles, of the region to search or build.",
    "H": "Height, in tiles, of the region to search or build.",
    # Scoped entries ("<script short name>.<TOKEN>") win over the bare token
    # for that script's commands: KIND and W/H mean different things in
    # building, workshop and zone. Added 2026-09-21.
    "building.KIND": (
        "The building kind, exactly as building.list-kinds gives it in its "
        "`token` field (Still, Carpenters, Bed, FarmPlot), or quickfort's own "
        "key such as wl. Never the display label. An unknown kind is an error."
    ),
    "building.FILTER": (
        "Optional. A case-insensitive substring of a kind's token, label or "
        "type (Workshop, Furnace, Bed, Bridge) to narrow the list. A filter "
        "that matches nothing gives an empty list, not an error."
    ),
    "building.W": (
        "Width, in tiles, of the footprint. Optional, and give W and H "
        "together or not at all. Leave both out and the tool uses the kind's "
        "own footprint, read from the game (building.list-kinds shows it). "
        "Pass them only for a variable-size kind such as a farm plot, road or "
        "bridge, within that kind's min..max. A size that is not the kind's "
        "own for a fixed-size kind is an error, and so is leaving both out "
        "for a variable-size kind (the error states its allowed range)."
    ),
    "building.H": (
        "Height, in tiles, of the footprint. Optional, and give W and H "
        "together or not at all. Leave both out for the kind's own "
        "footprint; pass them only for a variable-size kind. A wrong size "
        "for a fixed-size kind is an error."
    ),
    "zone.KIND": (
        "The zone kind, as zone.list-kinds gives it in its token field "
        "(Office, Bedroom, DiningHall, WaterSource), or quickfort's key such "
        "as o. Never the display label. The old water_source still works."
    ),
    "zone.W": (
        "Width in tiles of the zone. Optional; give both W and H or neither. "
        "Leave both out for the kind's default size (zone.list-kinds shows "
        "it). Refused for WaterSource, whose shape follows the water."
    ),
    "zone.H": (
        "Height in tiles of the zone. Optional; give both W and H or "
        "neither. Leave both out for the kind's default size (zone.list-kinds "
        "shows it). Refused for WaterSource, whose shape follows the water."
    ),
    "zone.OWNER": (
        "Optional. A unit id (digits) or a position code (MANAGER, "
        "BOOKKEEPER, SHERIFF). A code reserves the room for whoever holds "
        "the role now or later; a vacant role leaves it suspended. Only "
        "Bedroom, DiningHall, Office and Tomb can have an owner. Check first "
        "with zone.check-owner. Needs RANK, RADIUS_TILES and DRY_RUN given "
        "before it."
    ),
    "zone.FILTER": (
        "Optional substring of a kind's token or label."
    ),
    "zone.AROUND_FURNITURE": (
        "Optional, default false. true admits a site tile occupied by one "
        "of the kind's own qualifying furniture (a Chair for Office, a Bed "
        "for Bedroom, a Table for DiningHall, a Coffin for Tomb -- zone."
        "list-kinds shows each kind's furniture_kinds) instead of rejecting "
        "every occupied tile; any other occupied tile is still rejected. "
        "Refused by name for a kind with no furniture_kinds. Needs "
        "RADIUS_TILES given before it (or left as its default by omitting "
        "it entirely, since it is also optional)."
    ),
    "zone.KIND_FILTER": (
        "Optional, for zone.list. '' means any kind; otherwise a token from "
        "zone.list-kinds (Office, Bedroom, ...). An unknown kind is an "
        "error."
    ),
    "zone.OWNER_FILTER": (
        "Optional, for zone.list. '' means no owner filter; 'owned' or "
        "'unowned' filters by whether an owner-capable zone has one; a "
        "digit string filters to zones owned by that exact unit id."
    ),
    "zone.VALID_FILTER": (
        "Optional, for zone.list. '' means no filter; otherwise one of "
        "not_applicable (the kind carries no room-value concept at all), "
        "met (a real, non-empty room quality reading), not_met (the read "
        "succeeded and came back empty -- a rectangle, not a room) or "
        "cannot_tell (the read itself failed)."
    ),
    "zone.NEAR_LANDMARK_FILTER": (
        "Optional, for zone.list. '' means no proximity filter; otherwise "
        "the name of an existing landmark, narrowing to zones within "
        "RADIUS_TILES of it. Never a raw coordinate."
    ),
    "workshop.KIND": (
        "Which workshop: still, kitchen, mason, mechanic or carpenter."
    ),
    "LABOR": (
        "One or more labor names, exactly as df.unit_labor names them "
        "(MASON, CARPENTER, BREWER), upper case. Give them all in one call. "
        "A name that is not a real labor comes back as null with an error, "
        "never as 0."
    ),
    "RANK": (
        "Which ranked candidate to act on: 1 is the candidate closest to "
        "NEAR_LANDMARK. Defaults to 1 when omitted."
    ),
    "BLUEPRINT_FILE": (
        "A quickfort blueprint filename already deployed under "
        "dfhack-config/blueprints/ on the DF host, e.g. "
        "\"starter-room-5x5.csv\" -- not a path on this repo's own "
        "filesystem, and not a coordinate."
    ),
}

# Conservative and deliberately wide: these values become literal words on a
# command line run against a live game host (see module docstring). Blocks
# shell metacharacters, quotes, backslashes and newlines/carriage returns.
_SHELL_METACHAR_RE = re.compile(r'[;&|`$()<>\\"\'\n\r]')


@dataclass(frozen=True)
class ArgSpec:
    """One argument, resolved from a TOOLS.yaml signature token (a group token
    such as `[W H]` resolves to one ArgSpec per member)."""

    name: str  # JSON-Schema-safe property name, unique within its tool
    raw: str  # the manifest token, verbatim, brackets included (a group's members share the group's)
    required: bool
    json_type: str  # "integer" or "string"; for a repeated argument, the type of each item
    enum: Optional[Tuple[str, ...]] = None
    description: Optional[str] = None  # from _ARG_DESCRIPTIONS, keyed by the raw token
    repeated: bool = False  # `NAME...`: an array property, one argv word per item
    group: Optional[str] = None  # the group token (`[W H]`) this spec belongs to, else None


_PLACEHOLDER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _describe(inner: str, scope: Optional[str]) -> Optional[str]:
    if scope is not None:
        scoped = _ARG_DESCRIPTIONS.get(f"{scope}.{inner}")
        if scoped is not None:
            return scoped
    return _ARG_DESCRIPTIONS.get(inner)


def _parse_one(
    word: str, *, required: bool, raw: str, group: Optional[str], scope: Optional[str]
) -> ArgSpec:
    """One name inside a token: a placeholder, a literal-choice, or a
    repeated placeholder (`NAME...`)."""
    if "|" in word:
        # A literal-choice token ("on|off", "idle|injured|military|hostile"):
        # not a placeholder name, the actual values DFHack accepts. See
        # module docstring.
        choices = tuple(word.split("|"))
        name = "_".join(choices).lower()
        return ArgSpec(
            name=name, raw=raw, required=required, json_type="string", enum=choices, group=group
        )

    repeated = word.endswith("...")
    base = word[:-3] if repeated else word
    if not _PLACEHOLDER_RE.match(base):
        raise ToolSchemaError(
            f"argument token {raw!r} contains {word!r}, which is not a placeholder name "
            "(letters, digits, underscore), a literal choice (a|b), or a repeated name (NAME...)"
        )
    json_type = "integer" if base in _INTEGER_ARG_NAMES else "string"
    return ArgSpec(
        name=base.lower(),
        raw=raw,
        required=required,
        json_type=json_type,
        description=_describe(base, scope),
        repeated=repeated,
        group=group,
    )


def _parse_arg_tokens(token: str, scope: Optional[str] = None) -> List[ArgSpec]:
    """Every ArgSpec one manifest token stands for: one for `NAME`, `[NAME]`,
    `NAME...` and `[NAME...]`; one per member for a group `[A B]`."""
    required = True
    inner = token
    m = _BRACKET_RE.match(token)
    if m:
        required = False
        inner = m.group(1).strip()
    if "[" in inner or "]" in inner:
        raise ToolSchemaError(f"argument token {token!r}: brackets do not nest or split")
    words = inner.split()
    if not words:
        raise ToolSchemaError(f"argument token {token!r} is empty")
    if len(words) == 1:
        return [_parse_one(words[0], required=required, raw=token, group=None, scope=scope)]
    if required:  # unreachable from the registry (whitespace splits an unbracketed token)
        raise ToolSchemaError(f"argument token {token!r} contains a space outside brackets")
    specs = [
        _parse_one(w, required=False, raw=token, group=token, scope=scope) for w in words
    ]
    for spec, w in zip(specs, words):
        if spec.repeated or spec.enum is not None:
            raise ToolSchemaError(
                f"argument group {token!r}: {w!r} is repeated or a literal choice; a group "
                "holds plain names only"
            )
    return specs


def _parse_arg_token(token: str) -> ArgSpec:
    """The single ArgSpec of a one-name token (kept for callers and tests
    that only ever see one; a group token raises here, use _parse_arg_tokens)."""
    specs = _parse_arg_tokens(token)
    if len(specs) != 1:
        raise ToolSchemaError(f"argument token {token!r} is a group of {len(specs)}, not one")
    return specs[0]


def _arg_specs_for_tool(tool: Tool) -> List[ArgSpec]:
    """The single source of truth for a tool's argument names, shared by
    tool_definitions (schema) and argv_for_call (argv), so the two can never
    disagree about which name means which position."""
    scope = tool.id.split(".", 1)[0]
    prelim: List[ArgSpec] = []
    for tok in tool.args:
        prelim.extend(_parse_arg_tokens(tok, scope))

    for i, spec in enumerate(prelim):
        if spec.repeated and i != len(prelim) - 1:
            raise ToolSchemaError(
                f"{tool.id}: repeated argument {spec.raw!r} must be the last token of the "
                "signature (anything after it would be ambiguous on a positional command line)"
            )

    counts: Dict[str, int] = {}
    for spec in prelim:
        counts[spec.name] = counts.get(spec.name, 0) + 1

    seen: Dict[str, int] = {}
    specs: List[ArgSpec] = []
    for spec in prelim:
        if counts[spec.name] > 1:
            seen[spec.name] = seen.get(spec.name, 0) + 1
            specs.append(dataclasses.replace(spec, name=f"{spec.name}_{seen[spec.name]}"))
        else:
            specs.append(spec)
    return specs


# --------------------------------------------------------------------------
# Tool definitions
# --------------------------------------------------------------------------


def _tool_description(tool: Tool) -> str:
    parts = [tool.description or "(TOOLS.yaml has no notes for this command)"]
    parts.append("Mutates fort state." if tool.mutates else "Read-only: does not mutate fort state.")
    if tool.is_verified:
        parts.append(f"Verified against a live fort: {tool.verified}.")
    else:
        parts.append(
            "NOT VERIFIED against a live fort as of writing -- treat its output or "
            "effect with caution."
        )
    return " ".join(parts)


def _input_schema(tool: Tool) -> dict:
    properties: Dict[str, dict] = {}
    required: List[str] = []
    for spec in _arg_specs_for_tool(tool):
        prop: Dict[str, Any] = {"type": spec.json_type}
        if spec.enum is not None:
            prop["enum"] = list(spec.enum)
        if spec.repeated:
            prop = {"type": "array", "items": prop}
            if spec.required:
                prop["minItems"] = 1
        if spec.description:
            prop["description"] = spec.description
        properties[spec.name] = prop
        if spec.required:
            required.append(spec.name)
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def tool_definitions(registry: Registry, roster: Roster, role: str) -> List[dict]:
    """MCP tool definitions for exactly the tools `role` may call.

    Filtered through Roster.check(role, tool_id) -- never by re-reading a
    role's tools.yaml directly -- so this is exactly the permission boundary
    mcp/roles.py already enforces, not a second copy of it. Returns [] for an
    unknown role (Roster.check's own behaviour), not an error: whether an
    unknown role is a caller-side bug is this function's caller's call, not
    this module's.
    """
    id_to_name, _ = build_tool_names(registry)
    defs: List[dict] = []
    for tool_id in sorted(registry.ids()):
        allowed, _reason = roster.check(role, tool_id)
        if not allowed:
            continue
        tool = registry.get(tool_id)
        # A "native" (server-side, non-DFHack) tool -- dfmcp/queue_tools.py's
        # queue.propose/pass/rule/pending -- describes itself via `describe`
        # rather than TOOLS.yaml's token heuristic (`_tool_description`/
        # `_input_schema` below assume a DFHack Tool's `.args`/`.notes`/
        # `.verified` shape, which a native tool does not have). Duck-typed
        # on `hasattr` rather than an isinstance/import of dfmcp.queue_tools,
        # so this module stays what its own docstring says it is: a pure
        # function of the registry and the roster, with no dfqueue-specific
        # knowledge of its own. `describe` also takes `role`, because a
        # native tool's schema can depend on the calling role (queue.propose's
        # `type` enum is that role's own closed vocabulary).
        describe = getattr(tool, "describe", None)
        if describe is not None:
            description, input_schema = describe(role)
        else:
            description, input_schema = _tool_description(tool), _input_schema(tool)
        defs.append(
            {
                "name": id_to_name[tool_id],
                "description": description,
                "inputSchema": input_schema,
            }
        )
    return defs


# --------------------------------------------------------------------------
# Turning a call back into argv
# --------------------------------------------------------------------------


class ArgumentError(Exception):
    """A tool call's `arguments` dict failed validation.

    Always raised rather than guessed past: an unknown argument, a missing
    required one, an unsafe string value, or the positional-optional gap
    described in this module's docstring are all real, structural problems
    with the call, not something argv_for_call may silently paper over.
    """


def _validate_value(tool_id: str, spec: ArgSpec, value: Any) -> str:
    if isinstance(value, bool):
        # bool is a subclass of int in Python; without this an accidental
        # True/False would silently pass an integer check below.
        raise ArgumentError(f"{tool_id}: {spec.name!r} must not be a boolean, got {value!r}")

    if isinstance(value, (list, tuple, dict)):
        # Only a repeated argument takes a list, and _items_of has already
        # split that into single values by here. str() of a container would
        # otherwise reach the command line as its repr.
        raise ArgumentError(
            f"{tool_id}: {spec.name!r} takes a single value here, got {value!r}"
        )

    if spec.enum is not None:
        text = str(value)
        if text not in spec.enum:
            raise ArgumentError(
                f"{tool_id}: {spec.name!r} must be one of {list(spec.enum)}, got {value!r}"
            )
        return text

    if spec.json_type == "integer":
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str) and re.fullmatch(r"-?\d+", value):
            return value
        raise ArgumentError(f"{tool_id}: {spec.name!r} must be an integer, got {value!r}")

    text = str(value)
    bad = _SHELL_METACHAR_RE.search(text)
    if bad:
        raise ArgumentError(
            f"{tool_id}: {spec.name!r} contains a character not allowed in a DFHack "
            f"command-line argument ({bad.group(0)!r}): {value!r}"
        )
    return text


def _items_of(spec: ArgSpec, value: Any) -> list:
    """A repeated argument's values as a list. A bare scalar is one item (see
    the module docstring); a non-repeated argument is always a single value."""
    if spec.repeated and isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _is_supplied(spec: ArgSpec, arguments: Mapping[str, Any]) -> bool:
    if arguments.get(spec.name) is None:
        return False
    if spec.repeated:
        return len(_items_of(spec, arguments[spec.name])) > 0
    return True


def argv_for_call(tool: Tool, arguments: Mapping[str, Any]) -> List[str]:
    """The exact argv DFHack expects: [script name minus ".lua", verb,
    positional args in signature order]. Raises ArgumentError for anything
    invalid; see this module's docstring for the positional-optional trap and
    for optional groups and repeated arguments."""
    specs = _arg_specs_for_tool(tool)
    arguments = dict(arguments or {})

    known = {spec.name for spec in specs}
    unknown = sorted(set(arguments) - known)
    if unknown:
        raise ArgumentError(
            f"{tool.id}: unknown argument(s) {unknown}; this tool accepts {sorted(known)}"
        )

    supplied = [_is_supplied(spec, arguments) for spec in specs]

    for spec, has in zip(specs, supplied):
        if spec.required and not has:
            more = " (give at least one)" if spec.repeated else ""
            raise ArgumentError(
                f"{tool.id}: missing required argument {spec.name!r} ({spec.raw}){more}"
            )

    # Units: one per single argument, one per optional group. The group is
    # all-or-nothing, and for the gap check below it is one slot.
    units: List[Tuple[str, List[int], bool]] = []  # (raw token, spec indices, required)
    for i, spec in enumerate(specs):
        if spec.group is not None and units and units[-1][0] == spec.group:
            units[-1][1].append(i)
        else:
            units.append((spec.group or spec.raw, [i], spec.required))

    for raw, indices, _required in units:
        if len(indices) < 2:
            continue
        given = [specs[i].name for i in indices if supplied[i]]
        absent = [specs[i].name for i in indices if not supplied[i]]
        if given and absent:
            raise ArgumentError(
                f"{tool.id}: {raw} go together: got {given} without {absent}. Give all of "
                "them, or none to use the default."
            )

    # The positional-optional gap check: optional units only, relative to each
    # other, ignoring required arguments interspersed between them (a
    # required argument is always present by the check above, so it never
    # participates in a "gap"). An omitted unit the manifest declares
    # `skippable` (the CLI works out what was given by how many leading
    # numbers it sees) does not block a later one.
    skippable = set(getattr(tool, "skippable", ()) or ())
    unit_supplied = [any(supplied[i] for i in indices) for _raw, indices, _r in units]
    optional_units = [u for u, (_raw, _idx, required) in enumerate(units) if not required]
    supplied_optionals = [u for u in optional_units if unit_supplied[u]]
    if supplied_optionals:
        last = supplied_optionals[-1]
        for u in optional_units:
            if u >= last:
                break
            if not unit_supplied[u] and units[u][0] not in skippable:
                first_name = specs[units[u][1][0]].name
                last_name = specs[units[last][1][0]].name
                raise ArgumentError(
                    f"{tool.id}: cannot supply {last_name!r} without also supplying the "
                    f"earlier optional argument {first_name!r} ({units[u][0]}) -- DFHack's "
                    "command line is positional and cannot skip a slot. Pass a value for it "
                    "explicitly, or omit both."
                )

    script = tool.script[: -len(".lua")] if tool.script.endswith(".lua") else tool.script
    verb = tool.id.split(".", 1)[1]
    argv = [script, verb]
    for spec, has in zip(specs, supplied):
        if has:
            for item in _items_of(spec, arguments[spec.name]):
                argv.append(_validate_value(tool.id, spec, item))
    return argv
