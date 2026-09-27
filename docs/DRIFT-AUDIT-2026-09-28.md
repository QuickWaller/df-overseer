# Drift audit: repo vs VM 103, 2026-09-28

Researcher pass on `handoffs/2026-09-28-vm103-vm106-drift-audit.md`. Read-only
against VM 103 (`dfmcp-smoke` tree, confirmed live via
`systemctl show dfmcp-server.service`: `WorkingDirectory=/opt/df/dfmcp-smoke`)
and its game-side `hack/scripts/` tree. No writes, no restarts. No VM 106
files were named in the brief; none were touched.

Method: `git -c core.autocrlf=false show HEAD:<path>` for the committed
bytes, `scripts/vm-ssh.sh df 'cat ...'` / `'sha256sum ...'` for the live copy.
Note: `vm-ssh.sh` scrubs any `df-[a-z0-9-]+`-shaped string from output
(the script's own address-leak guard), which masks the `df-overseer-*`
script names inside file content too, not just addresses. That masking
produced spurious-looking diffs in the five Lua files below; each was
re-checked with the mask normalised out on both sides before concluding.

## Doc/role files: `agents/`, `dfmcp/README.md`, VM behind repo

`agents/ROSTER.yaml`, `agents/conductor/role.md`, `agents/consultant/role.md`,
`agents/consultant/sites.yaml`, `agents/quartermaster/role.md`,
`dfmcp/README.md`.

All six share one live mtime on VM 103: `2026-09-22 01:43:45 UTC`, exactly.
They were deployed once (the 2026-09-22 loop-MVP batch) and never touched by
any deploy since, while the repo kept editing them through 2026-09-23,
2026-09-24 and 2026-09-25.

Per file, what the repo has that the VM doesn't:

- **`ROSTER.yaml`**: only the header comment differs. Repo added an
  "UPDATED 2026-09-23" paragraph recording that quartermaster/conductor
  were enabled and that whether quartermaster/consultant had ever run for
  real was unknown. The VM's actual data (role entries, `enabled: true` for
  quartermaster and conductor) already matches the repo, this is a stale
  narrative comment only, not a functional gap.
- **`conductor/role.md`**: VM still says every conductor tool is
  `live_deployed: false`/`unverified`. Repo has since added the "UPDATED
  2026-09-23" paragraph recording that `clock.*`, `fort.quicksave` and
  `vitals.summary` were live-verified in the 2026-09-22 deploy, and that
  `ledger.read`/`announcement-levels.slow-ids`/`orders.list` were added and
  verified 2026-09-23.
- **`consultant/role.md`** and **`sites.yaml`**: VM predates the wiki-mirror
  work entirely: no `wiki_search`, no staleness/HELD/RECENT-EDIT language,
  no `ask-0001` queue-contents note. Repo reflects the 2026-09-24/25 mirror
  build. This is the most consequential gap: the live consultant's own
  charter still describes the pre-mirror tool surface, even though
  `Working.md` says the mirror switch-over deployed successfully elsewhere.
- **`quartermaster/role.md`**: VM's copy still says `ROSTER.yaml` reads
  `enabled: false` and flipping it is the orchestrator's job, pre-dating
  the actual 2026-09-22 flip. Repo has the "Enabled for the agent-loop MVP"
  paragraph with the 23-tool, live-verified count from 2026-09-23.
- **`dfmcp/README.md`**: VM lacks the 2026-09-23 tool-count update
  (architect 37/overseer 63/quartermaster 23/consultant 21/conductor 15)
  and the labor-join-hash confirmation paragraph; VM still has only the
  2026-09-21 counts (34/57/14).

**Why**: these are documentation files read by humans and by the openclaw
agents on VM 106, not by the `dfmcp-server` process itself, so they weren't
included in the several post-2026-09-22 deploy batches, which shipped Python
tool code and Lua scripts, not `agents/` or the README. No handoff or
decision entry says they were deliberately held back; this looks like an
omission in what each deploy's file list covered, not a decision.

**Recommendation**: redeploy `agents/` and `dfmcp/README.md` from the repo
to `/opt/df/dfmcp-smoke` on the next VM 103 deploy. None of this is
functionally live-breaking (ROSTER.yaml's actual enable flags already match),
but the consultant's live charter describing a tool surface it no longer has
is the one gap worth prioritising.

## Lua scripts: `scripts/dfhack/`, functionally equivalent, VM has one extra trailing newline

`df-overseer-chokepoints.lua`, `df-overseer-diggable.lua`,
`df-overseer-openarea.lua`, `df-overseer-stockpile.lua`,
`df-overseer-ui.lua` (live path: `/opt/df/game/hack/scripts/`).

Raw `diff` against the VM copy looked like extensive drift, but that was
entirely the SSH wrapper's masking of `df-overseer-*` substrings inside
comments and usage strings. After substituting `df-overseer-[a-zA-Z0-9_-]*`
->  a placeholder in the repo copy and `<host>` -> the same placeholder in
the VM copy, every file diffs to **exactly one line**: a trailing blank line
present only in the VM copy (confirmed with `xxd` on the last bytes: repo
ends `...end\n`, VM ends `...end\n\n`). Each VM file also has line count =
repo line count + 1, consistent with just this.

No logic, comment content, or usage string differs. This is the hash
mismatch's actual cause: one extra `\n` at EOF, not a content or behavior
difference.

**Why**: plausibly the CRLF/deploy-method trap this repo already documents
(`git -c core.autocrlf=false git archive` is required; some other deploy path
appended a trailing newline instead of introducing CRLF here), not
confirmed from a handoff record, since no stream mentions touching these
five files' whitespace specifically.

**Recommendation**: leave alone. Functionally equivalent; not worth a
redeploy risk for a trailing-newline byte. If a future deploy touches any of
these five files for a real reason, the newline will resolve itself as a
side effect.

## Not verified

- Which specific deploy step introduced the extra trailing newline in the
  Lua files (no handoff record found; inferred from the byte pattern only).
- Whether VM 106 (openclaw) holds its own stale copy of these `agents/`
  files for the agents that actually read them at `agent exec` time, out of
  scope for this brief (VM 103 only was named), not checked.
