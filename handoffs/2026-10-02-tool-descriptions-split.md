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
