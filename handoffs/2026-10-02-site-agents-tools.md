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
