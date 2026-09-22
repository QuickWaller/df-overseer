# diff re-registration and true quicksave slot, VM 103, 2026-09-22

Stream: `handoffs/2026-09-22-loop-diff-reregister-quicksave-slot.md`. The
executor stalled after its last live check, so this record was written by the
orchestrating session: it states what the stream's commits contain and what
the orchestrator verified itself against VM 103 after merging. The executor
left no report of its own, and its own intermediate checks (listener counts
after re-registration, the MCP-side `diff.since` call it ran before stalling)
are **not** claimed here, because they were not seen.

## Verified by the orchestrator, after the merge

Commands run over ssh as `df` on VM 103 (address read from `.env` by key,
never printed) and locally:

- `sha256sum` of the installed `df-overseer-diff.lua` and
  `df-overseer-fort.lua` equals the merged committed bytes
  (`git -c core.autocrlf=false show <branch>:<path> | sha256sum`).
- A bounded Lua read of the live DFHack globals:
  `_G.__df_overseer_diff_registered_version` = `2026-09-22-diff-rereg-1`;
  1210 log entries, all `encoding_version == "legacy-converted"`; next id
  1211.
- `df.global.pause_state` true, year 31, tick 106974, `enabler.fps` 100.0,
  before and after; `systemctl is-active dfmcp-server` active.
- Ambient suite 1229 passed / 3 skipped; `.venv-dfmcp` `dfmcp/tests` 630
  passed.

## Findings

1. `dfhack.filesystem.mtime` is broken on this install (documented epoch
   seconds return as large negative numbers; `io.popen` and `os.execute` are
   sandboxed out). `fort.quicksave` now uses DF's own `cur_savegame.save_dir`
   instead. Recorded in `docs/TRAPS.md`, because earlier streams confirmed
   quicksaves by mtime.
2. The old boolean registration guard meant a redeploy never replaced live
   listeners. Version-keyed registration fixes that for every future change
   to a listener, not just this one.

## Owed

A genuinely new event logging UTF-8 through the re-registered listeners.
It needs game time, so it belongs to the first supervised run:
`diff.since <cursor>` over MCP as the conductor, reading a name holding a
CP437 character.
