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

Deployed to VM 103 on 2026-09-21 (`handoffs/2026-09-21-deploy-building-batch.md`).
`confidence.yaml` ships with the code and today sets only the default, medium
(its `tools` map is empty). The runtime store is not in git and is created once
by hand: `python -m dfmcp.gotchas_store init <path>` as the service user, in a
directory the unit lists under `ReadWritePaths=`; the server refuses to start
without it. It was empty at deploy, and the write path was tested only against a
temporary copy, so no gotcha has been written to the live store. The architect
and the overseer hold `gotchas.get` and `gotchas.write`; the consultant holds
`gotchas.get` only. The join that adds operating labors to a building result
(`dfmcp/labor_join.py`) needs the production graph database and is described in
`dfmcp/README.md`; a fix to its result shapes is merged and not yet redeployed.
