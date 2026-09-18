# Handoff: `get_doctrine`, the first thing that reads doctrine

Date: 2026-09-19. **Offline build stream. No VM, no SSH, no deploy.**

Read `CLAUDE.md`, then `Working.md`'s section "In discussion: designing the
learning loop" (the parts marked **agreed**), then `doctrine/seed.yaml`'s
header and a handful of entries, then `doctrine/validate.py`, then
`dfmcp/queue_tools.py` **in full**, then this.

## Why this stream exists

`doctrine/seed.yaml` holds the fort's game knowledge, validated, with
per-source provenance and a status on every entry. **Nothing reads it.**
`CLAUDE.md` says so in as many words: "the agents should eventually read;
nothing reads it yet." Today alone it gained entries that would have changed a
live decision: that brewing yields five drinks and returns a seed, that a
`WaterSource` zone's `active` flag says nothing about reachability, that no
mechanism can be made from wood. None of that reaches an agent.

The user already agreed the shape (register 2026-09-17, and `Working.md`):
**`get_doctrine`, read-only, with a topic index.** Agreed, not built. This is
building it, and only it.

## Deliverable

A native MCP tool, `doctrine.get` (or the id `get_doctrine` if the registry's
conventions favour it; follow the existing naming and say which), served
**exactly the way `dfmcp/queue_tools.py` serves `queue.*`**: a hand-written
`NativeTool` with an explicit JSON schema, merged via
`registry.load_registry(native_tools=...)`, enforced through the same
`Roster.check(role, tool_id)` boundary. **One boundary, not a second
permission path.** Read `queue_tools.py`'s docstring on why; the reasons apply
here unchanged.

It must support:

- **By topic**: every entry carrying a topic, using the closed topic list
  `doctrine/validate.py` already enforces. An unknown topic is an **error**,
  never an empty list, because an empty list reads as "no doctrine on this".
- **By id**: one entry.
- **A topic index**: the topics that exist and how many entries each carries,
  so an agent can discover what it can ask about.

## The one property that matters most

**Every entry returned must carry its `status` and its sources, unflattened.**
A `prior` from an unrecorded wiki read and a `verified` entry from this
install's raws must be **unmistakably different** in the output, and a
`refuted` entry must be visibly refuted, not silently dropped and not
presented as current guidance.

This is the whole reason doctrine has provenance. The failure this project
keeps catching itself in is a claim losing its provenance on the way to being
used: an illustrative "11 days" quoted back as data, three `universal` entries
marked `verified` on one pond's evidence. **A reader that strips status would
industrialise that failure.** Consider returning refuted entries only when
asked for explicitly, but if you do, the default output must say that refuted
entries exist and were omitted, rather than hiding that they exist.

## Rules that bite here

- **Read-only.** `.mutates` is `False`. Doctrine revisions are proposals
  through the queue by agreed design; this tool never writes.
- **Reuse `doctrine/validate.py`'s loader** rather than parsing the YAML a
  second way. Two parsers of one file drift.
- **`knowledge_scope`**: every tool carries one. Doctrine is the fort's own
  accumulated knowledge, which is not obviously the same thing as
  `player_derivable`. Read how `roles.py` uses the field, pick deliberately,
  and **write down the reasoning** in the tool's docstring. If none fits, say
  so rather than forcing one.
- **Which roles get it**: make a deliberate, stated choice per role in
  `agents/*/tools.yaml`. The consultant (the "wiki nerd and researcher" role)
  is the obvious reader; say why for each role you grant or withhold.
- **Where doctrine lives at runtime** is a real question: the MCP server runs
  on VM 103, so the tool needs `doctrine/seed.yaml` present there. **Do not
  deploy.** Make the path configurable, default it sensibly, fail loudly if the
  file is absent, and write up what the deploy needs.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- No em dashes in prose.

## Touched surfaces

`dfmcp/doctrine_tools.py` (new), `dfmcp/tests/test_doctrine_tools.py` (new),
whichever of `dfmcp/server.py` / `dfmcp/registry.py` wires native tools in (a
minimal additive change), `agents/*/tools.yaml`, and this handoff doc.

**Do not touch** `doctrine/seed.yaml` or `doctrine/validate.py` (import from
it; if its loader needs a change, report it rather than making it),
`scripts/dfhack/**`, or anything under `production/`.

## Done means

The tool exists and is reachable through the real registry and roster, status
and sources survive to the output unflattened, an unknown topic errors, the
index works, the full suite passes (**382 passed / 1 skipped** right now,
report before and after), and the write-up says exactly what a deploy needs.

---

## Report: DONE, 2026-09-19

### The tool

Id: **`doctrine.get`** (canonical scheme match: `queue.pending`, `overview.get`,
`farm.list` are all `noun.verb`; `doctrine.get` follows that, not
`get_doctrine`, which is the MCP-name-after-dot-to-double-underscore form,
`doctrine__get`, that `dfmcp.tools.build_tool_names` derives from it and that
`tools/list`/`tools/call` actually carry on the wire). Read-only,
`mutates=False`, `sole_writer_only=False`. Defined in `dfmcp/doctrine_tools.py`
exactly the way `dfmcp/queue_tools.py` serves `queue.*`: a hand-written
`NativeTool` dataclass, an explicit JSON schema, merged into the registry via
`load_registry(native_tools=...)`, dispatched in `dfmcp/server.py`'s
`_handle_call_tool` under the same `getattr(tool, "native", False)` branch
`queue.*` already used (now split by `tool_id in queue_tools.NATIVE_TOOL_IDS`
vs `tool_id in doctrine_tools.NATIVE_TOOL_IDS`, since that branch was
previously hardcoded to `queue_tools.call` alone), enforced through the same
`Roster.check(role, tool_id)` boundary. No second permission path.

One tool, three modes, chosen by which arguments are set:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "id":     {"type": "string"},
    "topic":  {"type": "string", "enum": ["drink","farming","fishing","food","health","labor","material","seeds","water"]},
    "include_refuted": {"type": "boolean"}
  }
}
```

- `id` set → exactly one entry, whatever its status (refuses if the id does
  not exist).
- `topic` set → every entry filed under that topic, refuted omitted by
  default (refuses if the topic string is outside the closed vocabulary --
  `doctrine/validate.py`'s own `TOPICS`, re-checked in code, not left to the
  JSON Schema `enum` alone, since a client need not validate against the
  schema it was handed).
- Neither set → the topic index: every topic in the closed vocabulary
  (including ones with zero entries today), each with a total count and a
  `prior`/`verified`/`refuted` breakdown.
- `id` and `topic` together is refused, not resolved by preferring one.

### Status and sources: how they survive

Every returned entry keeps its full shape: `id`, `scope`, `status`, `topics`
(list), `sources` (list of full `{kind, ref, describes, read, accessed}`
dicts, never joined into a string), `statement`, `note`. Nothing is
flattened, in either the structured (JSON) or text (XML) form.

Concretely, live-tested through a real MCP client session against the real
`doctrine/seed.yaml` (see Verification below):

```
doctrine.get(id="water-source-zone-for-ponds")
  -> structuredContent.entry.status == "refuted"
  -> text contains: status="refuted" ... <warning>REFUTED: kept only so
     this mistake is not repeated. Do NOT treat as current guidance.</warning>
```

A `prior` entry gets the parallel `<warning>PRIOR: received knowledge, not
yet confirmed by this install's own data...</warning>`; a `verified` entry
gets no warning at all, so the three statuses are visually distinct in the
form that actually lands in a prompt (`docs/AGENT-ARCHITECTURE.md` §4: XML
is "the form models handle most reliably").

Refuted handling specifically:
- **By id**: always returned, regardless of status. The caller named that id
  explicitly; there is no ambiguity to protect against by hiding it.
- **By topic**: refuted entries are left out of the returned list by
  default, but the response **always** carries `omitted_refuted_count`
  (structured) / `omitted_refuted="N"` plus a `<note>` line (text), even
  when `N` is 0 -- so "0 omitted" and "field absent" are never
  indistinguishable. `include_refuted:true` returns them anyway, still
  `status="refuted"` with the warning.
- **Topic index**: never omits anything -- every topic's `refuted` count is
  reported unconditionally, so the index alone cannot be read as "this
  topic has no refuted history."
- **Unknown topic**: refused (`DoctrineToolError`), never an empty list.
  Live-tested: `doctrine.get(topic="nonsense")` -> `isError=true`, message
  names the valid topic list. A *known* topic with zero current entries
  (e.g. `health`) is a valid empty result, distinguishable from an unknown
  one because the caller can check the index first.

### `knowledge_scope`

**Deliberately not set** -- no attribute on `doctrine_tools.NativeTool`, same
as `queue_tools.NativeTool`. Read `dfmcp/roles.py` rule 7 first: it refuses
to load any role granted a tool tagged `knowledge_scope: omniscient`, and
already treats a *missing* attribute on a native tool as out of scope for
that rule, with its own comment naming `queue.propose` as the precedent
("carries no knowledge_scope at all -- it reads and writes dfqueue's own
ledger, never fort/world state, so it is not this rule's concern").

`knowledge_scope` classifies a live read of fort/world state by how a
vanilla player could have come to know it. `doctrine.get` never reads fort or
world state; it reads this project's own curated, human/agent-authored
corpus, and each entry already carries something *stronger* than a
visibility tag: its own itemised `sources`. Forcing `player_derivable` onto
it would misrepresent the data -- that value specifically means "a safe
computation over player-visible facts," and most of the current 27 entries
are `prior` (received, not computed from anything in this fort) or `refuted`
(kept because they are *not* a fact about anything). The full reasoning is
written into `dfmcp/doctrine_tools.py`'s module docstring, including one
open question flagged rather than solved: a doctrine entry *could* in
principle launder a fact from an `omniscient`-tagged tool's live output to a
role that doesn't hold that tool. Nothing in the current 27 entries appears
to do this, but this module has no mechanism to detect it, and content
curation of `doctrine/seed.yaml` is outside this stream's touched surfaces.
Flagged for whoever curates it next, not assumed away.

### Per-role choice, stated

- **consultant -- granted** (`read`). The obvious case, named in the brief:
  role.md says outright "There is no retrieval tool. This role currently
  runs on model priors alone" and lists exactly the failure class
  (pre-v50 material, confidently wrong) doctrine's provenance tagging
  exists to catch. `doctrine.get` is not the still-`planned`
  `knowledge.wiki_lookup` (a live wiki search) -- it serves this project's
  own already-curated, validated entries. Noted in `tools.yaml` that
  role.md's "no retrieval tool" line is now stale for doctrine specifically,
  though still true for open wiki lookup.
- **architect -- withheld** (`deny`, with reason). Not for lack of use:
  several real entries (`water-source-needs-walkable-neighbour`,
  `sunken-basin-recognition`, `do-not-dig-into-full-basin`,
  `seed-stock-never-falls`) bear directly on the siting/dig-order proposals
  this role writes, and the agreed future design ("every proposal must list
  the doctrine entries it relied on", `Working.md` 2026-09-17) will need it.
  Withheld because that citation field has no home in `dfqueue.schema` yet
  (confirmed by grep -- nothing there mentions doctrine), so granting read
  access now would be an unenforced convention, not a wired requirement.
  This is the strongest candidate for the next doctrine-adjacent stream.
- **overseer -- withheld** (`deny`, with reason). The agreed design already
  routes this: "The Overseer hands proposals to the consultant for
  fact-checking... before ruling" (`Working.md` 2026-09-17). Granting direct
  doctrine access here would duplicate that agreed path rather than use it.
- **quartermaster, marshal, chronicler -- not touched.** All three are
  `enabled: false` in `ROSTER.yaml`, so `load_roster` never reads their
  `tools.yaml` (or, for marshal/chronicler, they have none, deliberately, per
  their own role.md). quartermaster's existing `tools.yaml` is the one place
  this could plausibly have gone (food/drink/seed/material topics sit
  squarely in its future domain), but adding a `deny` entry there would have
  implied a decision to make now about a role that stays out of load's reach
  either way -- left as an explicit open note here instead of touching a
  fourth file for a choice nobody needs enforced yet.

### What a deploy needs

Not done here (offline build stream, no VM, no SSH). Concretely, for VM 103's
`dfmcp-server.service`:

1. **`doctrine/seed.yaml` must exist at the path the server reads.**
   `ServerConfig.doctrine_path` defaults to the in-tree
   `<repo_root>/doctrine/seed.yaml` (safe default, unlike `queue_db`, because
   this file is checked in and travels with every code deploy -- see
   `dfmcp/doctrine_tools.py`'s docstring, "Where the file lives at runtime").
   If the deploy layout ever serves code from one path and data from another,
   set `MCP_SERVER_DOCTRINE_PATH` explicitly (mirrors the existing
   `MCP_SERVER_QUEUE_DB` pattern in `infra/local.example.env` --
   **`infra/local.example.env` was not updated by this stream** since it is
   not in the touched-surfaces list; flagging so the orchestrator adds the
   `MCP_SERVER_DOCTRINE_PATH` line alongside the others there before deploy).
2. **A missing or invalid file fails loudly, not silently.** `doctrine.get`
   raises `DoctrineToolError` -- surfaced as `isError=true` on every call --
   if the path does not exist, is not valid YAML, or fails
   `doctrine.validate.validate`'s own checks (e.g. a `verified` entry with no
   53.16 source). There is no fallback to an empty doctrine set.
3. **No new Python dependency.** `doctrine_tools.py` imports `yaml`
   (already pinned in `dfmcp/requirements.txt`) and `doctrine.validate`
   (stdlib + `yaml` only). No requirements.txt change needed.
4. **No systemd/`ReadWritePaths` change needed.** Unlike `queue_db`
   (write access required), doctrine is read-only from the server's side --
   the existing `ReadOnlyPaths`-style access to the checked-out repo already
   covers it, so this should not hit the `ProtectSystem=strict` gotcha
   `queue_tools.py`'s docstring flags for the queue database.
5. **Restart required for a doctrine edit to take effect on the running
   server process is NOT true** -- the file is re-read on every call (see
   docstring "Where the file lives at runtime"), so a doctrine revision
   merged and pulled onto VM 103 is live on the next `doctrine.get` call,
   no restart needed. (A code change to `doctrine_tools.py` itself would
   still need the normal service restart, same as any other module.)
6. **Not run against a live DFHack process or VM 103 in any way.** Verified
   entirely offline: direct unit tests plus one real, in-process MCP
   client/server/ASGI round trip against `FakeDFHackServer` (see
   Verification below). The exact untouched deploy command is unchanged from
   `infra/dfmcp-server.service.example`; only the new env var above is
   needed alongside it.

### Verification

**Unit level** (`dfmcp/tests/test_doctrine_tools.py`, 26 tests, ambient
env, no `mcp` package needed): by-id (found/unknown/warning text),
by-topic (found/unknown-topic-errors/zero-entries-is-valid/refuted
omission and its stated count/`include_refuted`), the topic index (every
closed topic present, status breakdown never hidden), argument validation
(`id`+`topic` together, unknown argument, wrong type), load failures
(missing file, invalid YAML, fails-the-real-validator), JSON-safety of
`datetime.date` values in `accessed`, a smoke test against the real
`doctrine/seed.yaml`, and roster-wiring tests (`Roster.check` through the
real `agents/*/tools.yaml`, confirming the grant/withhold choices above
actually hold, plus `mutates`/`sole_writer_only`/no-`knowledge_scope`).

**Full ambient suite** (`python -m pytest`, ambient env): **382 passed / 1
skipped before -> 408 passed / 1 skipped after** (exactly +26, the new
file; nothing else changed count).

**Full `dfmcp/tests` under a real `mcp==2.2.0` venv** (built fresh in a
scratchpad-only, throwaway venv per `dfmcp/requirements.txt`, never
touching the shared ambient environment `queue_tools.py`'s own docstring
warns against): **193 passed**, `test_server.py` included (not skipped),
confirming the dispatch-branch change in `_handle_call_tool` does not break
the queue tools it already served.

**Real MCP-protocol round trip** (throwaway script, scratchpad only, not
committed -- built the real registry/roster/`FakeDFHackServer`/ASGI app/MCP
`ClientSession`, exactly mirroring `dfmcp/tests/test_server.py`'s own
fixtures, against the **real `doctrine/seed.yaml`**, all under the same
venv): consultant's `tools/list` includes `doctrine__get`;
`doctrine.get()` (index) returned `drink: {count: 14, prior: 8, verified: 4,
refuted: 2}` (matches a direct count of the real file); `doctrine.get(id=
"water-source-zone-for-ponds")` returned `status="refuted"` with the
`REFUTED` warning in the text; `doctrine.get(topic="nonsense")` came back
`isError=true` naming the valid topic list; architect's and overseer's
`tools/list` do **not** include `doctrine__get`, and a direct call for
either role is refused with the exact `deny` reason text from their
`tools.yaml`. This is the strongest evidence available offline that the new
wiring is correct end to end, not just internally consistent.

### Gap flagged, not fixed (out of touched surfaces)

`doctrine/validate.py` has no `load(path) -> list[dict]` -- only
`validate(source) -> list[str]`. Getting both the parsed data and the
validation result without parsing the YAML twice meant
`dfmcp/doctrine_tools.py`'s `_load_entries` does its own single
`yaml.safe_load`, then hands the already-parsed data to
`doctrine_validate.validate(data)` for every actual check (no validation
rule is reimplemented). If a second caller of `doctrine/seed.yaml` shows up,
`doctrine/validate.py` should probably grow a real `load()` that returns
`(data, errors)` or raises, so neither caller reinvents this. Not done here
per the brief's explicit "do not touch `doctrine/validate.py`."

### Test counts

**382 passed / 1 skipped -> 408 passed / 1 skipped** (ambient, full repo
suite, ` python -m pytest`).
