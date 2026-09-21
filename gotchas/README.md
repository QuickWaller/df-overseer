# gotchas/

Static data for the confidence-and-gotchas design (`docs/BUILDING-TOOL.md`).

- `confidence.yaml`: the confidence level per tool (and per kind for the generic
  building tool). Every tool and kind starts at medium. It is a static setting
  edited by us; no code path and no agent can raise a level. Loaded and
  validated by `dfmcp/confidence.py` at server start.
- The gotchas themselves are **not** here. They live in a runtime SQLite store
  outside the tree (`dfmcp/gotchas_store.py`, path `MCP_SERVER_GOTCHAS_DB`),
  because agents write to it while the server runs and a code redeploy must
  never clobber it. Accepted entries are exported to JSONL
  (`python -m dfmcp.gotchas_store export DB OUT_DIR`) and committed here or under
  `evals/live/` when someone decides they are worth keeping in the repo.
- The one shared text every role prompt includes is
  `agents/CONFIDENCE-LEGEND.md`.
