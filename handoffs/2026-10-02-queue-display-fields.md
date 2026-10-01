# Handoff: queue display fields (titles, labels, urgency, hold codes)

Date: 2026-10-02. **Executor, Sonnet, worktree. Offline only: build and test,
deploy nothing.**

## Why

The stream page board (`handoffs/2026-10-02-stream-board.md`, a sibling
stream) shows each project by name, description and urgency, and each job
by a short label and state. The queue does not record those yet. Design
`research/2026-10-01-stream-page-design.md` §3.3 items 6 and 7 specifies
most of them; urgency is new (register 2026-10-02, "Stream page look").

## Tasks, in order (commit after each)

1. **Schema** (`dfqueue/schema.py`), all optional, validated at write time:
   - `project`: `public_title` (60 chars max), `public_rationale` (one or
     two sentences, 300 chars max), `urgency` (`normal` / `elevated` /
     `high`).
   - `amend` and `abandon`: `public_rationale`.
   - each step (in `project.steps` and `amend.steps`): `label` (24 chars
     max, short and imperative, e.g. "Smooth walls", "Place bed"; the
     mockup's labels are the model).
   - `observation` results: a held target may carry `hold_code` from the
     closed vocabulary in design §3.3 item 7. Public text for each code in
     a new data file `dfqueue/public_text.yaml`, loaded once; an unknown
     code is refused at write time.
   - Public fields go through the same coordinate and safety checks other
     public text gets (`_find_coordinate` and friends). An amend that
     changes only a step's `label` must not count as a changed step for the
     fresh-id rule; decide and test this explicitly.
2. **MCP tools** (`dfmcp/queue_tools.py`): expose the new fields on the
   write tools that create these records, with descriptions short enough
   that a model fills them in correctly. Tool counts per role must not
   change.
3. **Who writes them.** The Overseer writes `project`/`amend`/`abandon`, so
   its charter (`agents/overseer/role.md`) gains a short paragraph: always
   set `public_title`, `public_rationale`, `urgency` and a `label` per step;
   what each urgency level means (high: lives or the fort at risk;
   elevated: blocks other work or a need running short; normal:
   everything else). Proposers (architect, quartermaster) get one line
   suggesting a title in the proposal summary. Where the code records a
   hold, set `hold_code`.
4. **Tests**: validation of each field (length, enum, unknown hold code,
   coordinates refused), old records without the fields still valid, the
   label-only amend case, MCP tool schemas.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then
  after each task.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- **Touched surfaces:** `dfqueue/schema.py`, `dfqueue/store.py` (only if
  needed), `dfqueue/public_text.yaml`, `dfmcp/queue_tools.py`,
  `agents/*/role.md`, their tests. Not `web/stream/*`, `dfqueue/feed.py`,
  `dfqueue/feed_status.py` (the sibling stream owns those).
- Public repo: no hostnames, IPs or tokens. No em dashes in prose. No
  attribution lines in commits.

## Done when

`python -m pytest` and `dfmcp/tests` in `.venv-dfmcp` green (report the
counts), and a Result section appended here naming every field, its
limits, and anything left open.
