# Handoff: structured tool guides

Date: 2026-10-02. **Executor, Sonnet, worktree. Offline only: build and test,
deploy nothing.**

## Why

`handoffs/2026-10-02-tool-descriptions-split.md` gave every TOOLS.yaml
command a `summary` and a `guide`. The guides came out as one paragraph of
prose each, in no fixed order. The user wants a set structure (register
2026-10-02, "Structured tool guides"): easier to scan on the site, and the
same order every time for an agent. The user and the orchestrator will keep
refining the wording by hand, so each section must be its own field.

## The structure

Replace each command's `guide` string with a `guide` mapping:

```yaml
guide:
  arguments:            # in call order; empty list when the tool takes none
    - name: TEMPLATE
      required: true
      default: null     # or the default, as a string
      meaning: A template id from blueprint.plan.
  returns: >-
    What comes back and how to read it, one or two sentences.
  before_a_real_run:    # dry-run rules, refusals, override flags; may be empty
    - DRY_RUN defaults to true; only an explicit "false" designates.
  traps:                # known ways the tool misleads; may be empty
    - quickfort can report success while designating nothing, so read `read_back`.
```

Who may use a tool is not repeated (it comes from the allowlists).

## Tasks, in order (commit after each)

1. Schema and loader: `dfmcp/registry.py` parses the mapping into
   `Tool.guide` (a small dataclass or dict, your choice, documented) and
   keeps a `Tool.guide_text()` that renders the sections as plain text in
   the fixed order (headings "Arguments", "Returns", "Before a real run",
   "Traps"; arguments one per line as `NAME (required|optional, default X):
   meaning`). `gotchas.get` returns that rendered text exactly where it
   returns the guide today. The registry test requires every command to
   have `arguments` (list), `returns` (non-empty), `before_a_real_run`
   and `traps` (lists).
2. Convert all 109 commands from the current prose `guide` (and `notes`
   or the Lua header where the prose is unclear). Every caution in today's
   guide must land in one of the four sections: repeat the caveat audit
   from the previous handoff against the new fields and report it.
3. `dfqueue/site_data.py`'s `build_tools_json`: add `guide_sections`
   (the four sections as JSON) beside the existing `guide` (now the
   rendered text), so the website can show a table. Do not touch
   `web/stream/*`: the orchestrator renders it.
4. Plain English, no file paths, dates, handoff names or em dashes in any
   guide text.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- **Touched surfaces:** `scripts/dfhack/TOOLS.yaml`, `dfmcp/registry.py`,
  `dfmcp/tools.py`, `dfmcp/gotchas_tools.py`, `dfqueue/site_data.py`
  (`build_tools_json` only), their tests. Not `web/stream/*`.
- Edit TOOLS.yaml with a round-trip that preserves every other field and
  comment byte for byte, as the previous stream did.
- Public repo: no hostnames, IPs or tokens. No attribution lines in
  commits.

## Done when

`dfmcp/tests` in `.venv-dfmcp` and the dfqueue tests green (report counts),
per-role tool counts unchanged, the caveat audit result, and a Result
section here naming any command whose sections you are unsure of.

## Result

Done: all four tasks, for every one of the 109 TOOLS.yaml commands.

**Schema and loader (task 1).** `dfmcp/registry.py` gained `GuideArgument`
(`name`, `required`, `default`, `meaning`) and `ToolGuide` (`arguments`,
`returns`, `before_a_real_run`, `traps`) dataclasses, a strict `_parse_guide`
that raises `RegistryError` for anything off-schema (wrong types, an unknown
key, a missing `returns`, an argument missing `name`/`meaning`), and
`ToolGuide.guide_text()` rendering the four sections in the fixed order the
handoff specifies ("Arguments"/"Returns"/"Before a real run"/"Traps"; each
argument as `NAME (required|optional, default X): meaning`, an empty-string
documented default such as `MATERIAL_CHOICE`'s falling through to bare
"optional" rather than printing an empty `default )`). `Tool.guide` is now a
`ToolGuide`, not a string. `dfmcp/server.py`'s `tool_guides` map (fed to
`gotchas.get`) now calls `.guide_text()`; `dfqueue/site_data.py`'s
`build_tools_json` sends both the rendered `guide` text (unchanged shape,
still `.guide_text()`) and the new `guide_sections` (the four raw fields, for
the website's table). `web/stream/*` untouched, per the handoff.

**Conversion (task 2).** Every command's prose `guide` replaced with the
structured mapping via a generated pipeline (not hand-typed per command):
argument name/required/default came from the registry's own signature
parsing plus `dfmcp/tools.py`'s existing `_ARG_DESCRIPTIONS` table (227 of
301 arguments already had a maintained meaning there; the other 74 were
written by hand from each command's own prose guide, since
`_ARG_DESCRIPTIONS` is scoped to this project's own established per-argument
language and reusing it keeps a shared argument's wording consistent across
every command that takes it). The old guide prose was split into
returns/before_a_real_run/traps by sentence classification (DRY_RUN/refusal/
override/verification markers routed to before_a_real_run; a short, curated
set of truly misleading-behaviour sentences, read by hand rather than
regex-guessed, routed to traps; everything else defaults to returns). Role-
scoping sentences ("Overseer only", "System-level role only", "the Architect
proposes and previews") were dropped outright, since the handoff's own rule
("who may use a tool is not repeated") matches the existing allowlist-is-the-
boundary principle; double-hyphen dashes were replaced with commas (no em
dashes in guide text, same rule the previous stream followed, carried
forward from argument text that was written for `tools.py`'s developer
audience rather than this guide). `scripts/dfhack/TOOLS.yaml`'s other fields
and every comment are untouched: verified with
`git diff 6f9abfe HEAD -- scripts/dfhack/TOOLS.yaml | grep '^-' | grep -v
'^---'`, confirming every removed line falls inside an old `guide:` block
(the 6-space `guide:` line or its indented body), nothing else.

**Caveat audit (task 2, repeated from the previous handoff).** Re-ran the
previous stream's marker sweep (`DRY_RUN defaults to true`, `refus`,
`ALLOW_STRANDED`, `OVERRIDE`, `no dry-run`, `false negative`), now checking
`summary` + the structured guide's rendered text instead of `summary` +
prose guide. 33 commands flagged; five were real gaps the restructuring
would otherwise have carried forward silently (now fixed, see the second
commit's message for the full list): `building.find`/`build` and
`construction.build`'s `MATERIAL_CHOICE` meaning was generic, missing the
`allow_economic` keyword and the omit-excludes-economic-by-default rule
(`building.build`/`construction.build` also gained the call-scoped-then-
restored trap); `zone.clear-owner` had no `before_a_real_run` at all despite
notes saying it shares `assign-owner`'s refusals; `blueprint.release` and
`blueprint.unreserve`'s `DRY_RUN` argument had copied `blueprint.apply`/
`reserve`'s shared description verbatim, naming `LEVEL`/`RANK`/
`RADIUS_TILES` that neither command has (corrected to each command's own
effect; `release` also gained its missing not-stalled/non-dig-phase
refusal); `clock.set-speed`'s valid range (1 to 1000) was not stated
anywhere in the structured fields. The remaining ~28 flags are confirmed
false positives: every `DRY_RUN defaults to true` one is the same fact
worded as "true (the default) only reports what would change..." (now also
backed by the argument's own structured `default: "true"` field, a stronger
guarantee than prose alone); a few (`threat.scan`, `breach.check`,
`labor.set-labor`, `announcement-levels.slow-ids`) are the substring
"stalled" inside "installed", not a real marker hit; `connectivity.report`'s
"false negative" is historical bug-fix narrative about a problem already
fixed, not a live caveat.

**Tests.** `dfmcp/tests` in a fresh `.venv-dfmcp`
(`python -m venv --system-site-packages .venv-dfmcp` then
`pip install -r dfmcp/requirements.txt pytest`, the documented `fastmcp`/
`mcp` version-conflict warning is expected and non-blocking): **764 passed**
(761 before this stream's own new tests; +3 in `test_registry.py` for
`guide_text()`'s fixed order, empty-section wording and `_parse_guide`'s
hard failures, +1 later for the empty-string-default fix, reconciled against
`git log` as the true count). `dfqueue/tests`: **405 passed** (404 before +1
for `guide_sections` in `test_site_data.py`). Also ran the ambient
`python -m pytest` (lupa already present on this machine's user site-
packages, no scratch install needed) as a repo-wide safety net beyond what
the handoff asked for: **2,430 passed, 3 skipped, 1 failed**. The one
failure, `doctrine/tests/test_wiki_check.py::test_cli_exit_codes`, is the
exact same pre-existing failure the previous stream
(`2026-10-02-tool-descriptions-split.md`) already flagged and traced to the
wikimirror freshness-check CLI (a module neither stream touched), most
likely a wall-clock/freshness-threshold test gone stale against the current
date; not a regression from this stream's work.

**Per-role tool counts**, checked via
`dfqueue.site_data._default_registry()`/`_default_roster()` (the same path
`build_tools_json` and the website use) rather than re-deriving a roster by
hand: **overseer 99, architect 53, consultant 29, quartermaster 25,
conductor 16**, identical before this stream's first commit and after its
last one -- this stream touched no allowlist file (`agents/*/tools.yaml`,
`ROSTER.yaml`), only `guide:` content, so the counts could not have moved;
checked anyway rather than assumed.

**Commands whose sections I am least sure of**, ordered as "worth the
orchestrator's first look":

- **`building.build`**, **`construction.build`** and **`building.find`**:
  the `MATERIAL_CHOICE` economic-material-filter mechanism (enforce for the
  call, read back, restore) is the densest single piece of behaviour in the
  manifest; I rewrote the argument meaning and added a trap, but the
  previous stream's own "least sure" flag on this exact mechanism still
  applies to how much nuance one argument-meaning paragraph can carry.
- **`stocks.availability`**, **`threat.scan`**, **`workjob.queue`**,
  **`zone.find`**/**`zone.place`**, **`nobles.requirements`**,
  **`construction.audit`**, **`blueprint.apply`**/**`blueprint.preview`**:
  each already had a hand-written trap carried over from the previous
  stream's own "least sure" list (apostrophe-in-workshop-name, the
  met/not_met/cannot_tell discipline, the owned-item half-check, and so
  on); I kept the substance but reworded every one to fit the `traps` list's
  one-sentence-per-entry shape, so a close second read against the
  underlying `.lua` source is still worth the orchestrator's time.
- **`labor.quota`**/**`labor.quota-status`**: the guide states the intent
  (autolabor's self-reported count cross-checked against an independent
  read) but not the parsing assumption that both depend on autolabor's own
  CLI text output, unverified live -- same gap the previous stream flagged,
  not newly introduced, but not closed by this stream either, since closing
  it needs a design decision (state the assumption in `traps`, or leave it
  as implementation detail) rather than a mechanical conversion.
- The 74 arguments whose `meaning` I wrote by hand (not already covered by
  `dfmcp/tools.py`'s `_ARG_DESCRIPTIONS` table) are plainer and shorter than
  the covered ones; `orders.create`'s half-dozen optional arguments
  (`FREQUENCY`, `MATERIAL_CATEGORY`, `ITEM_CONDITIONS`, `ORDER_CONDITIONS`,
  ...) are the densest cluster of these and would benefit most from a
  second pass once the live order-creation path has actually been
  exercised.
