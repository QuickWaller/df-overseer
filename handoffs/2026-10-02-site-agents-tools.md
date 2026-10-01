# Handoff: stream site, Agents, Tools, Forts and a Chronicle stub

Date: 2026-10-02. **Executor, Sonnet, worktree. Offline only: build and test,
deploy nothing.** The orchestrator deploys after checking your work.

## Why

The board is built (`handoffs/2026-10-02-stream-board.md`). The user then
designed the rest of the site in a mockup, iterated many times; it is the
spec: `research/2026-10-02-site-agents-tools-mockup.html`. Open it in a
browser and read its code. Register 2026-10-02, "Site structure", has the
decisions. Build it into `web/stream/` beside the board, same look (Terminal
2 default, Stone 2 behind the toggle, already in `style.css`).

## What to build

1. **Navigation** (as the mockup's header): a fort group (current fort's
   name, **Board**, **Chronicle**) and a project group (**Agents**,
   **Tools**, **Forts**). Hash routes as the mockup (`#board`, `#chronicle`,
   `#chronicle-<fort>`, `#agents`, `#agent-<role>`, `#tools`,
   `#tool-<id>`, `#forts`). The board stays the default view and stays
   exactly as built. **There is one board, always the current fort**; each
   fort has its own chronicle.
2. **Agents** (mockup's `viewAgents`, `agentMap`, `viewAgent`, `toolTree`):
   - Full-width page. Two columns filling the window height: the
     hub-and-spoke map on the left, fixed (it never scrolls); a panel on the
     right. Below 900px they stack.
   - Map: Overseer in the centre, every other role on a ring, one straight
     spoke each, width by message count, planned roles dashed, no labels
     on the spokes. Hover shows the agent's card in the panel (only when no
     agent is open); click opens the agent in the panel and outlines its
     box. Roles and planned roles come from `agents/ROSTER.yaml`, never
     hard-coded in `app.js`; Will and the Executor are the two fixed extras.
   - Panel head (does not scroll): name, kind, model, tool count,
     description, track record. Then three tabs whose body alone scrolls:
     **Tools** (default; a "general" group first, then tool families such
     as `zone`, `construction`, closed by default, families with entries
     listed first; each tool shows its description, a "changes the fort"
     tag, and its gotchas, vents and unexplained errors with author and
     outcomes; counts spelled out: "1 gotcha · 2 vents"), **Recent lines**
     (this agent's lines in the current fort, by game day), **Charter**
     (the `role.md` rendered, then a **Changes** list at the bottom).
   - Description and kind: take them from the charter or a small data
     file, not prose in `app.js`.
3. **Tools** (mockup's `viewTools`, `viewTool`): every tool, grouped by
   area, search, filters by role and by has-gotchas/vents/unexplained,
   role dots, spelled-out counts; a tool page with its entries, effect,
   confidence (from `gotchas/confidence.yaml`), who has it, and the
   confidence legend. Areas are data, not branches.
4. **Forts** (mockup's `viewForts`): one card per fort from `forts.json`
   plus a dashed "Next fort, planned" card. A card opens that fort's
   chronicle, never the board.
5. **Chronicle: a stub.** Port the mockup's Chronicle as a clearly marked
   example (the "example data" tag and a one-line note that the Chronicler
   is not enabled yet): vitals charts, seasons with the Chronicler's
   account, its picked events with "show all", thoughts, the Overseer's
   goal and review, and the lost fort's archive page. Pretend data is fine
   here, kept in one fixture file, never mixed into real data.
6. **Data.** Project-wide data goes at the top level of the published tree,
   outside any `forts/<id>/` folder (the board stream left room for it):
   - `agents.json`: roster, models, per-role tool lists (from
     `agents/*/tools.yaml` via the same loader `dfmcp` uses), charters'
     markdown, charter changes. The VM has no git history, so build charter
     changes at deploy time from `git log` on the workstation into a
     committed or generated file; say which you chose and why.
   - `tools.json`: id, description, effect, area, confidence, roles.
   - `gotchas.json`: read the live gotcha store **read-only** (as the
     publisher reads the queue); `call_excerpt` and anything coordinate
     bearing is operator only; public titles and bodies go through the same
     safety filter as other public text (withhold, never edit).
   - Track record and recent lines come from the current fort's queue
     (proposals, rulings by decision, asks and answers, graded
     predictions). Spoke counts from the same records; anything not
     recorded yet (wake-ups are slice S2) is omitted, not invented.
   - The publisher (`scripts/stream_publisher.py`) and
     `scripts/export_stream_feed.py` write these; same change detection,
     kill switches and read-only guarantees.
7. **General gotchas and vents** need the store to accept an entry with no
   tool, which it does not today (`dfmcp/gotchas_store.py`, `tool TEXT NOT
   NULL`). Do not change the store in this stream. Show the "general"
   group only when such entries exist, and note it in the Result.
8. Bump the asset version; update `web/stream/README.md`.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then
  after each task; agents here get cancelled mid-run.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- **Touched surfaces:** `web/stream/*`, `dfqueue/feed.py`,
  `dfqueue/feed_status.py`, `scripts/stream_publisher.py`,
  `scripts/export_stream_feed.py`, a new site-data module if you need one,
  `infra/local.example.env`, their tests. Not `dfqueue/schema.py`,
  `dfqueue/store.py`, `dfmcp/`, `agents/`.
- Public repo: no hostnames, IPs or tokens. No em dashes in prose. No
  attribution lines in commits. External scripts only from cdnjs or
  jsdelivr, pinned (the mockup uses marked 12.0.2 from cdnjs).
- This page is for humans; the no-rendered-map rule is about models and
  does not apply.

## Done when

- Tests green for the feed, publisher and any new module; tests that the
  public projection of gotchas never carries `call_excerpt` or withheld
  text, and that agents and tools data match the real allowlists (per-role
  counts equal to the live counts: overseer 99, architect 53, consultant
  29, quartermaster 25, conductor 16, or whatever the allowlists say now).
- Rendered headless in both themes at 1900px, 1400px and 375px: Agents
  (map fixed, panel tabs scrolling, hover card, open agent), a tool page,
  Forts, Chronicle stub, Board unchanged. No horizontal page scroll at
  375px. Say exactly what you checked.
- A Result section appended here.

## Result (2026-10-02, executor)

Built on branch `main` of the worktree (commits `9f959d6`, `d3dfb7f`,
`19f478b`, `26427a9`); the orchestrator merges. `git merge --ff-only main`
was run first, as instructed.

### What was built

1. **`dfqueue/site_data.py`** (new module): `build_agents_json`,
   `build_tools_json`, `load_gotchas_readonly` + `build_gotchas_json`,
   `write_site_data`, `charter_changes_from_git` /
   `generate_charter_changes_snapshot` (plus its own tiny CLI,
   `python -m dfqueue.site_data refresh-charter-changes`), and a committed
   fallback snapshot `dfqueue/charter_changes.json`.
2. **`scripts/export_stream_feed.py`** and **`scripts/stream_publisher.py`**
   both now build `agents.json`/`tools.json`/`gotchas.json` and write them
   via `site_data.write_site_data` into the TOP of each projection root
   (`<out>/public/`, `<out>/operator/`, siblings of `forts.json`), with a
   new `--gotchas-db`/`STREAM_PUBLISHER_GOTCHAS_DB` (optional; empty
   `gotchas.json` when omitted). `stream_publisher.py`'s content hash now
   folds in `agents`/`tools`/`gotchas` (minus their own `generated_at`,
   which would otherwise bust the hash every cycle — the exact
   `published_at` trap `compute_content_hash`'s own docstring already
   warned about) so a roster/tool/gotcha change triggers a push like any
   other change would.
3. **`web/stream/app.js`**: a new `SitePage` class (nav + hash router +
   Agents/Tools/Forts/Chronicle), exported alongside the untouched
   `StreamPage`. `index.html`/`operator.html` now instantiate `SitePage`;
   it mounts the original `StreamPage`, unmodified, for `#board`.
4. **`web/stream/style.css`**: a new `.site`/`.sitemain` theme block
   (same token names/values as `.e-wrap`'s, plus `--marshal`/`--chronicler`/
   `--bad`/`--info`/`--grid`/`--chart` the board never needed) and every
   component class the new views use.
5. **`web/stream/fixtures/chronicle-demo.json`**: the Chronicle's one
   fixture file (vitals, two seasons, a lost-fort archive), loaded only by
   the Chronicle/lost-chronicle views and tagged "example data" in the UI.
6. Asset version bumped `v=4` → `v=5` in both HTML files; `web/stream/
   README.md` and `infra/local.example.env` updated.

### Data sources, per view (never hard-coded in `app.js`)

- **Nav fort name**: `forts.json`'s own `current` fort (already existed).
- **Agents**: `agents.json`, built from `agents/ROSTER.yaml` (roles,
  planned roles, `kind`, `summary`, `blocked_on`) and, per enabled role,
  `dfmcp.roles.load_roster`'s real resolved tool list (the SAME loader the
  MCP server itself uses — not a second copy) and `agents/<role>/
  model.yaml`. Track record and spoke counts are counted from the current
  fort's queue records (`proposal`/`ruling`/`ask`/`answer` kinds) — no
  graded-prediction hit rate (would need the separate `predictions` table;
  not built this stream, see Deferred). Charter markdown is `role.md`
  read verbatim; charter changes are real `git log --follow` history on
  that file (see "Charter changes" below). **Recent lines** are NOT in
  `agents.json` at all: `app.js` filters the fort's own already-published
  `open.json` by role, client-side — the same file the Board reads, so no
  second per-role export exists to go out of sync with it.
- **Tools**: `tools.json`, built from the same merged `Registry`
  (`scripts/dfhack/TOOLS.yaml` + every native tool module) plus
  `gotchas/confidence.yaml` (`dfmcp.confidence.load_confidence`) for each
  tool's confidence level/note, and the same `Roster` for its "used by"
  role list. Areas are a small prefix→name table in `site_data.py`
  (`AREAS`), data, not per-tool branches.
- **Gotchas** (both the Tools page and each agent's tool tree): `gotchas.json`,
  read from a live gotcha store read-only (`load_gotchas_readonly`, the
  same `mode=ro` pattern `feed.load_records_readonly` uses — never
  `dfmcp.gotchas_store`'s own `_connect`). The public projection never
  carries the `call_excerpt` key (absent, not null) and withholds
  (`dfqueue.feed.find_unsafe_pattern`) rather than edits an unsafe title/
  body. A general entry (`tool: null`) reads through as `tool: null`,
  never a placeholder string — a sibling stream is relaxing the store's
  own `NOT NULL` constraint for this; this reader does not wait on that
  landing and was mid-stream told to handle it, which it already did by
  construction. Verified live: added a hand-inserted general `vent` row to
  a local test store (bypassing `gotchas_store.add_entry`'s own validation,
  which still requires a tool as of this stream, with a raw schema that
  allows `tool IS NULL`) and confirmed the Architect's panel opens its
  "general" group automatically and shows it (screenshot: architect panel,
  "general · 1 vent").
- **Forts**: the existing `forts.json` (no new data needed); the "Next
  fort, planned" card's copy is static site chrome, not game data.
- **Chronicle**: exactly one fixture file, `web/stream/fixtures/
  chronicle-demo.json`, never touched by any real-data code path; the
  stub tag and a one-line note name the Chronicler as not enabled.

### Charter changes: which choice, and why

Both, as the handoff asked me to decide and say: `charter_changes_from_git`
shells `git log --follow` against `agents/<role>/role.md` and is tried
first (works on the workstation, where `.git` exists); if that returns
nothing (no `.git` reachable — a `git archive` VM deploy, CLAUDE.md's own
"traps" section), the code falls back to a **committed** snapshot,
`dfqueue/charter_changes.json`, generated by this same function and
checked into the repo. Regenerate it with `python -m dfqueue.site_data
refresh-charter-changes` whenever a charter changes; I ran it once, now,
to seed the real history (7 roles, oldest `agents/ROSTER.yaml` scaffolding
commit through today's own `agents: overseer charter sets public display
fields...` commit).

### Test counts

- New: `dfqueue/tests/test_site_data.py`, 16 tests, all passing — covers
  tool-count parity against the live `Roster` (not a hard-coded number:
  the test reads `len(perms.read) + len(perms.write)` from the exact same
  `load_roster` call the server makes, so it tracks an allowlist change
  automatically), roster enabled/planned/blocked_on, conductor-is-code,
  track record arithmetic against `board-demo.jsonl`, the wake-count
  omission, real git-history charter changes, `humanize_model_id`, tool
  areas/confidence/role-dots, and the full gotchas public/operator
  projection contract (no `call_excerpt`, withhold-not-edit, a general
  `tool: null` entry, never creates a missing store, JSON-serialisable).
- Measured today, matching the handoff's own numbers exactly: **overseer
  99, architect 53, consultant 29, quartermaster 25, conductor 16** —
  `python -c` one-liner against `load_registry`/`load_roster`, same merge
  `dfmcp/tests/test_roles.py` uses.
- `tests/test_stream_publisher.py`: 30/30 still green (3 pre-existing
  tests needed `compute_content_hash`'s hash-stability assumption re-
  checked after the `site=` parameter was added — fixed by excluding each
  JSON's own `generated_at` from what gets hashed, root-caused and
  documented in `_site_hash_payload`'s own docstring).
- Full repo, ambient `python` (no `lupa`, so some Lua-logic files skip,
  per CLAUDE.md's own documented trap): **2393 passed, 3 skipped, 1
  failed** in 207s. The one failure, `doctrine/tests/test_wiki_check.py::
  test_cli_exit_codes`, is unrelated to this stream: `git diff be955c7 --
  doctrine/` is empty (this stream never touched that directory), the
  test file's last commit predates this stream entirely, and its own
  output names a time-sensitive condition (`freshness very_stale`) — a
  pre-existing, date-sensitive failure, not a regression this stream
  caused. `dfqueue/` alone: 404 passed.

### What I actually checked in the headless renders, and how

Server: `python -m http.server 8943 --directory web/stream --bind
127.0.0.1` (a non-default port — port 8934, this README's own documented
default, was already answering from a DIFFERENT, stale checkout when I
first tried it: multiple `python -m http.server` processes from other
concurrent sessions were bound to it, and the one that answered served
`app.js?v=4`/`class="page"` content that doesn't exist in this worktree
at all. Documented as a new README caveat so the next person does not
lose time to the same thing). Browser: the workstation's own
`chrome.exe --headless=new`, one fresh `--user-data-dir` per shot (reusing
one caused silent black/blank screenshots from profile-lock contention
early on — also worth knowing).

**Rendered and visually inspected**, both themes, real data
(`board-demo.jsonl` exported with `--gotchas-db` pointed at a locally
built gotcha store carrying one real gotcha and one real vent):

- **Board** (`#board`): unchanged rendering confirmed byte-for-byte
  logic-wise (no edits to `StreamPage`); screenshotted at 1900/1400px,
  both themes — fort name "Ragwind" resolved, cards, mini job graphs, the
  pre-existing internal header/theme toggle all intact.
- **Agents** (`#agents`, `#agent-<role>`, `#agent-<role>-charter`): the
  hub-and-spoke map (Overseer centred, Architect/Consultant/Quartermaster/
  System/Will live, Marshal/Chronicler/Executor dashed-planned, spoke
  width visibly proportional to real counts), opening an agent (outlined
  box, panel replaces the intro, "close" returns), all three tabs (Tools
  53/Recent lines/Charter) with real content — Tools showing the real
  family tree with real gotcha/vent counts, Recent lines showing real
  `board-demo.jsonl` text grouped by game day, Charter rendering
  `role.md` through `marked` with headings/code spans/lists styled and
  every link stripped back to plain text. A planned role
  (`#agent-marshal-charter`) correctly shows only the Charter tab and its
  `blocked_on` prose. (Hover-only "point at an agent" was not exercised —
  headless has no mouse; the identical code path — `_showMapPop` — IS
  exercised by every click-opened agent, so the only untested part is the
  DOM event wiring itself, not the rendering it calls.)
- **Tools** (`#tools`): search box, role-filter chips, has-gotchas/vents/
  unexplained filters, grouped-by-area listing with real role dots and
  counts (138 real tool ids).
- **A tool page** (`#tool-zone.place`): breadcrumb, description, the real
  gotcha I seeded, confidence pill, "used by" role links, the confidence
  legend — on both `index.html` and `operator.html`.
- **Forts** (`#forts`): the one real fort's card plus the dashed "Next
  fort, planned" card.
- **Chronicle** (`#chronicle`) and a **lost fort's archive**
  (`#chronicle-artobcatten`): both tagged "example data", vitals charts,
  seasons, thoughts, "show all events" toggle, the lost-fort account —
  all from the one fixture file.
- **Both themes**: Terminal 2 (default) and Stone 2 (via the header
  toggle, and via a `?theme=` dev-only query param added so a headless
  run can set the theme without a click) screenshotted for every view
  above; Stone 2's light palette renders correctly throughout.

**375px / "no horizontal scroll"**: checked, but not the way the handoff
probably pictured, and I'm flagging the gap honestly rather than silently
reporting a bare pass. Headless Chrome's `--window-size` has an effective
floor: requesting 320/375/400/450/480/500/520px all produced an actual
`window.innerWidth` of **512px** (confirmed with an injected on-page
banner reading `innerWidth`/`scrollWidth`, not just the output PNG's own
pixel dimensions, which DO obey the requested size — Chrome renders the
page at ~512px logical width regardless, then crops the screenshot to the
requested pixel size, which is what made the very first attempt look like
a bad horizontal-overflow bug: real text, laid out for 512px, cropped to
375px of image). I could not get a literal 375px layout out of this CLI
tool. What I verified instead, at the achievable ~512px: `document.
documentElement.scrollWidth === window.innerWidth` (i.e. **zero**
horizontal overflow) on Agents, Tools, a tool page, Forts, Chronicle, AND
the pre-existing Board — all six. While bisecting the very first
(apparent) overflow, I found and fixed one REAL bug along the way: the
Agents map's mobile layout (`@media max-width:900px`) sets `.amap {
min-width: 560px }` so the diagram stays legible and scrolls within its
own box rather than squashing illegibly (ported from the mockup) — but
`.mapstage` and its ancestors had no `min-width: 0`, so a flex item's
default `min-width: auto` (= its content's min-content size) propagated
that 560px demand all the way up to the PAGE, which is a real,
CSS-spec-correct explanation for a real horizontal-scroll bug that would
have shown up on an actual 375-wide phone. Fixed with `min-width: 0` on
`.amapbox`, `.mapstage` and `#site-mapwrap` inside that media query (see
the comment left in `style.css` at that rule). Separately, I reproduced
the IDENTICAL "cut off text" visual artifact on the **pre-existing,
unmodified Board** page at the same simulated width, with the same
`scrollWidth === innerWidth` proof that it isn't real overflow either —
so if this project later gets a tool that truly renders at 375px, the
board is worth a quick re-check for completeness, but it is not something
this stream touched or regressed.

### Unverified or deferred

- **No graded-prediction hit/miss rate** on a role's record. The queue's
  `predictions` table lives separately from the `records` table
  `load_records_readonly`/my track-record code reads; wiring it in is a
  clean, scoped follow-up, not attempted here (time budget).
- **A real screen reader was not run** against the new pages (same honest
  gap the board's own README already states for itself).
- **The agent map's spokes carry no floating text label along the line**
  (the mockup's own halo-text labels showing "proposals 14" etc. beside
  each line); I judged each node's own box (which already names the role
  and, on hover/open, shows the count in its card/stats) sufficient given
  the time this stream had, rather than port the mockup's more elaborate
  per-spoke label placement math.
- **A real screenshot-driven mobile check below ~512px CSS width was not
  possible with this toolchain**, as detailed above; the `scrollWidth`
  proof is the honest substitute I had access to offline.
- **Model names/tool allowlists are unit-tested for count parity, not
  content parity** beyond what the roster tests already assert (e.g. no
  test asserts every individual tool id architect holds, only the count
  and set-equality against the live `Roster` object, which is in fact the
  stronger check — any individual drift would already fail the roster's
  own `test_real_roster_loads`-style tests in `dfmcp/tests/test_roles.py`).
- `web/stream/data/` (my local export + a scratch `demo-gotchas.sqlite3`
  used only for manual verification) is gitignored and was never staged;
  nothing under it is part of this commit history.
