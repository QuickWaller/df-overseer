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
