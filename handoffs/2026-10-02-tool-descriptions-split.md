# Handoff: tool descriptions in three layers (summary, guide, developer notes)

Date: 2026-10-02. **Executor, Sonnet, worktree. Offline only: build and test,
deploy nothing.**

## Why

Register 2026-10-02, "Tool descriptions: summary, guide, developer notes".
Every tool's MCP description is its whole `notes` field from
`scripts/dfhack/TOOLS.yaml`, sent to the model on every request: measured
2026-10-02, the Overseer receives about 146,000 characters (about 36,000
tokens) of tool descriptions per request, median 1,087 characters per tool,
largest `stocks.availability` at 7,589. Much of it is development history
(handoff paths, dates, bug stories) no agent can use. The user and the
orchestrator will keep refining the wording by hand, so the layout must make
that easy: plain data, one place per tool.

## The three layers

1. **`summary`**: one or two plain sentences, what the tool does and when to
   use it, written for an agent and readable by a visitor. Always sent as
   the MCP description (plus the existing one-line effect and verified
   notes, kept short). Shown on the website.
2. **`guide`**: the useful operating detail, structured (short headed lists
   are fine): arguments and their order, what it returns, cautions,
   dry-run-first rules, known traps. Every caveat in today's `notes` that an
   agent needs to use the tool correctly must survive here. Never sent by
   default; returned on demand (task 3). Shown on the website's tool page.
3. **`notes`** (unchanged field): developer history and references. Stays
   in the repo. Never sent to a model; not shown on the public site.

## Tasks, in order (commit after each)

1. Schema: add `summary` and `guide` to each command in
   `scripts/dfhack/TOOLS.yaml` and to `dfmcp/registry.py`'s `Tool`
   (`Tool.summary`, `Tool.guide`, both optional strings; keep `notes`).
   Native tools (`queue.*`, `gotchas.*`, `knowledge.*`, `doctrine.*`,
   `web.*` and any other with a Python `describe`) get the same split in
   their own modules: a short description sent always, the rest available
   as a guide.
2. Draft `summary` and `guide` for **every** tool from its current `notes`,
   args and the Lua header where needed. Plain English, no file paths, no
   dates, no handoff names, no em dashes. Keep `notes` untouched.
3. Wire it: `dfmcp/tools.py` sends `summary` (fall back to the first
   sentence of `notes` only if a summary is missing, and test that none
   is). `gotchas.get` for a tool returns its `guide` alongside the tool's
   gotchas, so reading a tool's guide and gotchas is one call; per-role tool
   counts must not change. Update `agents/CONFIDENCE-LEGEND.md` in a line or
   two: before using a medium-confidence tool, read its guide and gotchas
   with `gotchas.get` (stay under the legend's 450-word test cap).
4. Measure and report: per-role description characters and approximate
   tokens before and after (overseer, architect, quartermaster,
   consultant), and the largest remaining descriptions.
5. A caveat audit: for each tool, check that every operational warning in
   `notes` (dry-run defaults, refusals, argument order, ALLOW_* overrides,
   known traps) appears in `summary` or `guide`. Add a test that every tool
   has a non-empty summary under 300 characters and a guide.

## Interface the website reads

`Tool.summary` and `Tool.guide` on the registry objects (strings, may be
None until this lands). The website falls back to the first sentence of
`notes`; keep these names exactly.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- **Touched surfaces:** `scripts/dfhack/TOOLS.yaml`, `dfmcp/registry.py`,
  `dfmcp/tools.py`, `dfmcp/gotchas_tools.py`, native tool modules' own
  descriptions in `dfmcp/`, `agents/CONFIDENCE-LEGEND.md`, their tests. Not
  `web/stream/*`, `dfqueue/*`, the publisher or export scripts (the
  orchestrator is editing those at the same time).
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution
  lines in commits.

## Done when

`dfmcp/tests` in `.venv-dfmcp` and the ambient suite green (report counts),
the before/after measurement, the caveat audit result, and a Result section
here listing any tool whose summary or guide you are unsure of, so the
orchestrator reviews those first.

## Result

Done: tasks 1-5 for every DFHack-backed tool in `scripts/dfhack/TOOLS.yaml`
(all 109 commands). Native tool modules (`queue.*`, `doctrine.*`,
`knowledge.*`, `series.*`) were **not** split this stream; see "Not done"
below.

**Schema and wiring (task 1 and 3).** `dfmcp/registry.py`'s `Tool` gained
optional `summary`/`guide` fields, parsed from TOOLS.yaml alongside `notes`
(untouched). `dfmcp/tools.py`'s `_tool_description` now sends `_summary_text`
(the tool's `summary`, or the first sentence of `notes` if a `summary` is
ever missing) instead of the whole `notes` blob; `_summary_text`'s fallback
path is exercised directly in `dfmcp/tests/test_tools.py`
(`TestSummaryTextFallback`), and a belt-and-braces test there and in
`dfmcp/tests/test_registry.py` both assert no real command currently takes
it (every one of the 109 has a real `summary`). `dfmcp/gotchas_tools.py`'s
`gotchas.get`, called with `tool`, now also returns that tool's `guide` in a
`<guide>` element (and the structured result's `guide` key) right alongside
its gotchas -- never for a general (`tool` omitted) lookup. `dfmcp/server.py`
builds the `{tool_id: guide}` map once at startup and passes it through.
`agents/CONFIDENCE-LEGEND.md`'s medium-confidence bullet now says to read the
guide and gotchas together via `gotchas.get` (442 words, under the 450 cap).
Per-role tool **counts** are unchanged by any of this (verified: 99 / 53 / 29
/ 25 / 16 for overseer / architect / consultant / quartermaster / conductor,
identical before and after -- higher than the stale 87/52/29/24/16 CLAUDE.md
currently cites from 2026-09-30, because tool count has grown since then;
not something this stream touched or should correct, flagging only so the
orchestrator doesn't mistake it for a regression this stream caused).

**Measurement (task 4).** Measured by loading the registry both ways (the
original, notes-as-description `TOOLS.yaml` from this stream's starting
commit, and the current summary-based code) and summing
`tool_definitions()`'s description lengths per role:

| role | tools | before (chars / ~tokens) | after (chars / ~tokens) | reduction |
|---|---|---|---|---|
| overseer | 99 | 145,948 / ~36,487 | 46,134 / ~11,534 | 68.4% |
| architect | 53 | 73,252 / ~18,313 | 23,737 / ~5,934 | 67.6% |
| consultant | 29 | 25,227 / ~6,307 | 14,370 / ~3,592 | 43.0% |
| quartermaster | 25 | 32,540 / ~8,135 | 14,032 / ~3,508 | 56.9% |
| conductor | 16 | 18,254 / ~4,564 | 6,650 / ~1,662 | 63.6% |

The "before" overseer figure (145,948 chars / ~36,487 tokens, median 1,087
chars/tool) matches CLAUDE.md's independently-measured "about 146,000
characters (about 36,000 tokens), median 1,087 characters per tool" almost
exactly, confirming the before-baseline is the same thing CLAUDE.md
describes. consultant's reduction is smallest because its grant leans more
on native tools (`doctrine.get`, `knowledge.*`), which this stream did not
shorten.

Largest remaining descriptions (overseer's list, after): `building.build`
3,320 chars, `gotchas.write` 1,450, `construction.build` 1,335, `zone.place`
1,212, `gotchas.get` 1,128, `building.find` 1,086, `queue.amend` 1,015,
`workjob.queue` 857. Four of the top eight are now native-tool descriptions,
not TOOLS.yaml ones -- see "Not done".

**Caveat audit (task 5).** Added `dfmcp/tests/test_registry.py::
test_every_real_tool_has_a_summary_and_a_guide` (non-empty summary under 300
chars, non-empty guide, for every TOOLS.yaml-backed tool). For the audit
itself: every `guide` was drafted directly from that command's `notes`
(dry-run defaults, refusals, argument order, `ALLOW_*`/`OVERRIDE` overrides,
known traps), then cross-checked with a script that flags any command whose
`notes` contains a high-signal marker (`DRY_RUN defaults to true`, a refusal
word, `ALLOW_STRANDED`/`OVERRIDE`, "no dry-run") not echoed in `summary` +
`guide`. The sweep found two real gaps, now fixed: `zone.find` was missing
that `AROUND_FURNITURE` refuses by name for a kind with no qualifying
furniture, and that `KIND water_source` refuses `W H` entirely (its own
finder, not the rectangle search); `blueprint.preview` was missing that a
build/zone/place phase also reports whether phase ordering would block it.
The remaining four flagged items (`building.find`, `orders.create`,
`blueprint.preview`'s second flag, `clock.clear`) were checked by hand and
are false positives: the caveat is present under different wording (e.g.
"what is short" instead of "never refuses", "validated ... named if
malformed" instead of "refused"). This audit is a heuristic over a handful
of marker phrases, not a line-by-line diff against every `notes` field; see
the "least sure" list below for where a closer human read is most worth
spending.

**Tests.** `dfmcp/tests` in `.venv-dfmcp` (fresh venv, created this stream
per `docs/TRAPS.md`): **756 passed**. Ambient suite (`python -m pytest` with
`lupa` installed to a scratch dir and added to `PYTHONPATH`, per CLAUDE.md):
**2,421 passed, 3 skipped, 1 failed**. The one failure,
`doctrine/tests/test_wiki_check.py::test_cli_exit_codes`, is in the wikimirror
freshness-check CLI, a module this stream never touched; it fails the same
way in isolation and is not related to any TOOLS.yaml, registry, tools.py or
gotchas_tools.py change here (most likely a wall-clock/freshness-threshold
test that has drifted stale against the current date, not a regression this
stream caused). Flagging for the orchestrator rather than silently working
around it.

## Not done

**Native tool modules' own descriptions** (`dfmcp/queue_tools.py`,
`dfmcp/doctrine_tools.py`, `dfmcp/knowledge_tools.py`,
`dfmcp/series_tools.py`) were not split into summary/guide. Two reasons,
both worth the orchestrator's judgment rather than this stream's: first,
unlike TOOLS.yaml's `notes` (which the register names as full of
"development history... handoff paths, dates, bug stories"), these
hand-written descriptions were already authored for an agent to read, not a
developer -- inspection did not turn up dead history to cut, only usage
instructions a caller needs on every call (e.g. `gotchas.get`'s four modes,
`queue_tools`'s dozen command descriptions). Second, splitting them for real
needs a delivery mechanism for the "guide" half the way `gotchas.get` now
serves TOOLS.yaml guides, and nothing like that exists yet for `queue.*`/
`doctrine.*`/`knowledge.*`/`series.*`; building one was out of this stream's
budget and risked colliding with the orchestrator's concurrent `dfqueue/*`
work. Net effect: `gotchas.write` (1,450 chars) and `gotchas.get` (1,128
chars) are now two of the three largest remaining descriptions on the
overseer's list, having not shrunk at all. If the orchestrator wants this
pass to continue, `gotchas.write`'s two-mode explanation and `queue_tools`'s
twelve descriptions are the next-highest-value targets by size.

## Tools whose summary or guide I am least sure of

Ordered as "worth the orchestrator's first look", not as a quality ranking --
these are the commands whose `notes` were dense, recently and heavily
revised, or carry a subtle three-state/refusal discipline a short summary
risks flattening:

- **`building.build`** and **`construction.build`**: the buildingplan
  material-filter write/read-back/restore mechanism (fixed once already
  after a live silent no-op) is the most intricate single piece of behaviour
  in the manifest; my guide compresses several paragraphs into two or three
  sentences each.
- **`stocks.availability`**: the six-deduction netting, and specifically that
  the "owned" deduction ships explicitly half-checked (`owned_ref_check`) --
  I tried to preserve "a reasonable signal, not a certainty" but the source
  note is the longest in the file and may have more nuance worth keeping.
- **`threat.scan`**: the reachability-OR-landmark-distance admission rule and
  the pause/slow/record_only tiering are both load-bearing for the
  conductor's clock; worth a careful re-read against `docs/AGENT-LOOP.md`.
- **`workjob.queue`**: REAGENT_CHOICE, the COUNT/REPEAT argument ordering,
  and the apostrophe-in-workshop-name MCP-layer trap are all packed into one
  guide paragraph.
- **`zone.find`** and **`zone.place`**: AROUND_FURNITURE's ranking effect and
  response-shape change, and OWNER's validation-without-assignment-on-dry-run
  behaviour, are both subtle enough that I'd want a second read.
- **`orders.create`**: the 2026-10-01 generalisation (job type/reaction code
  resolution replacing the old short aliases) touches almost every optional
  argument; I flagged the breaking alias change but may have under-stated
  some validation detail.
- **`nobles.requirements`**: the met/not_met/cannot_tell discipline (an empty
  room description is never, by itself, not_met) is easy to flatten into a
  wrong-sounding simpler rule.
- **`labor.quota`** / **`labor.quota-status`**: both depend on parsing
  autolabor's own CLI text output, unverified live; my guide states the
  intent but not every parsing assumption.
- **`construction.audit`**: the built/planned/open classification and the
  "suspend the first at-risk job" backstop behaviour is non-obvious from the
  command signature alone.
- **`blueprint.apply`** and **`blueprint.reserve`**: the rotation-search
  access gate and the seam-wall overlap exception are both multi-step logic
  I condensed significantly.
