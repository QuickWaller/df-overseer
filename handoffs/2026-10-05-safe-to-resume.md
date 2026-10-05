# Handoff: an explicit "safe to resume" verdict, and pause alerts on the site

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no unpause, no deploys.** Start only after
`handoffs/2026-10-05-stuck-job-watch.md` has merged (both touch `conductor/`).

## Why (user's calls, 2026-10-05)

The pause watchdog (`handoffs/2026-10-05-pause-safety.md`,
`conductor/pause_watch.py`) wakes the Overseer for an unexplained pause and
currently treats a clean, un-escalated Overseer run as the decision to
resume, copied from the tripwire branch. The user agreed that silence is not
consent here: an unexplained pause may be a threat nobody looked at, and a
clean run cannot tell "it is fine" from "I did not get to it". The register
rule already stands that decisions are read from tool calls, never from
prose (`agents/overseer/role.md`, Escalation).

Also agreed: until Telegram exists, alerts go to the site's live status strip,
and a pause the watchdog attributes to a human is shown there too, so the
user can see it noticed and is waiting. Timings stay as they are (600 s
grace, 1800 s alert interval).

## Tasks, in order (commit after each)

1. **Plan, written here.** Where the verdict lives (preferred: a small
   Overseer-only MCP tool, e.g. `pause.verdict` with `resume: true|false`
   and a required one-line reason, recorded where the conductor can read it
   mechanically for that run, the same way it detects `queue.escalate`).
   The Overseer gets no resume power: the conductor still does the resume,
   once, with the tick verified, and never over a tripwire or escalation.
2. **Build it.** Watchdog rule: after an `unexplained_pause` Overseer run,
   resume only on an explicit `resume: true` verdict from that run; a
   `false` verdict, no verdict, or an escalation keeps the fort paused and
   raises an alert. Update the decision table in the pause-safety handoff
   and `docs/TRAPS.md` if it states the old rule. Charter: one short
   paragraph in `agents/overseer/role.md` saying when and how to give the
   verdict.
3. **Alerts on the site.** The conductor's status block (`conductor/status.py`
   `pause_watch`) already carries the watchdog's state; carry an `alert`
   (reason, since) and a `waiting_on_human` flag through to the publisher's
   live strip (`dfqueue/live.py`, public-safe text only through the feed's
   safety net) and show it in the strip on `web/stream/` in the existing
   status colours (an alert in the red state shade, waiting in the hold
   shade). Keep the strip one line. Bump the asset version.
4. **Tests**: watchdog decisions for each verdict case, the tool's role gate
   (Overseer only), the strip's rendering in the node tests on the real
   `app.js`, and a headless check at 1280x700, no console errors.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early and after
  every milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`.
- Touched surfaces: `conductor/pause_watch.py` and its wiring, `conductor/status.py`,
  `dfmcp/` (the new tool only; not `gotchas_store.py`),
  `agents/overseer/tools.yaml`, `agents/overseer/role.md` (one paragraph),
  `scripts/dfhack/TOOLS.yaml` only if the tool registry needs the entry there,
  `dfqueue/live.py` (strip fields only), `web/stream/` (strip only),
  `docs/TRAPS.md`, tests, tool-count docs.
- No armok powers. Public repo: no hostnames, IPs or tokens. No em dashes.
  No attribution lines in commits.
- Full ambient suite and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Done when

The verdict tool, the watchdog rule, the charter paragraph and the strip
alerts built with tests, deploy targets listed, and a Result section here.
