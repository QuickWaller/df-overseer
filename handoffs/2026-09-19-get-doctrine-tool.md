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
