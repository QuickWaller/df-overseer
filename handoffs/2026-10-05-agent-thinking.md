# Handoff: capture each agent run's thinking and show it on the site

Date: 2026-10-05. **Executor, Sonnet, worktree.** Host access on VM 106 is
read-only **except** what task 2 allows. No deploys.

## Why

The user wants to watch the agents think on the public site before the next
supervised cycle (user's call 2026-10-05, register: summaries and thinking are
public). `handoffs/2026-10-05-thread-run-data.md` found that nothing keeps the
reasoning today: openclaw's `agent exec --json` envelope carries only
`usage.reasoningTokens`, the conductor archives only the final answer, and
openclaw's transcript tables (`transcript_events`, `trajectory_runtime_events`,
`session_transcript_*` in `agents/<role>/agent/openclaw-agent.sqlite` and
`state/openclaw.sqlite`) have 0 rows, because `agent exec` runs an ephemeral
session. How the conductor launches a run: `conductor/runner.py`
(`DockerOpenClawRunner`, the docker command, the bind-mounted state dir
`/opt/openclaw/config`, per-role pinned configs).

## Tasks, in order (commit after each)

1. **Research openclaw, read-only.** From openclaw's own docs and source
   inside its image or install on VM 106 (`docker run --rm <image> ... --help`,
   the package's README/CHANGELOG/config schema, the source under the
   package's install path), find how to get the reasoning text of a run:
   a flag or config to persist session transcripts for `agent exec`, a
   `--json` option that includes reasoning or the full message list, an
   events/trajectory export, or a hook. Note the openclaw version and cite
   file paths for every claim. Write the findings into this handoff before
   building. If no supported route exists, stop and say so; do not patch
   openclaw.
2. **Prove it with one tiny run.** You may run **one or two** real
   `agent exec` runs on VM 106 to prove the route, using the **consultant**
   role's pinned config (read-only tools), through the same transient-unit
   shape the conductor uses (`sudo -n systemd-run --uid=df --gid=df -p
   SupplementaryGroups=docker ...`), with a trivial prompt such as "Reply
   with one sentence about what dwarves drink. Use no tools." Cost is a few
   cents. Do not touch the fort's state, the queue, or any other role. Show
   that the reasoning text comes back.
3. **Build it.** The conductor captures each run's reasoning (capped, e.g.
   12,000 characters, keeping the start and the end with a marker in the
   middle) and sends it in `conductor.report`'s end call as a new `thinking`
   field (`dfmcp/conductor_tools.py`, `dfqueue/runs.py`). The publisher puts
   it on each run in `runs.json` after the feed's `find_unsafe_pattern`
   check (public, per the user's call; a failed check withholds it, like the
   summary). Leave a one-line switch beside `PUBLIC_SUMMARIES` for thinking.
4. **Show it on the page.** A run's thinking covers everything that run did,
   so it belongs on that run's **Summary** reply in the thread, as the
   existing collapsed "Thinking" expander (`web/stream/app.js`). Long text
   scrolls inside the expander (a max height), never the page. Keep the
   approved look; read
   `C:\Users\wills\.claude\projects\c--website-projects-df-automation\memory\site-ui-preferences.md`.
   Update the preview data builder so the preview shows a Summary with
   thinking.
5. **Deploy plan for the orchestrator:** targets (`vm106-conductor`,
   `vm103-dfmcp`, `vm103-stream-publisher`, relay web), restarts, order, and
   any openclaw config change on VM 106 (exact file and line; the
   orchestrator applies it).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Touched surfaces: `conductor/`, `dfmcp/conductor_tools.py`,
  `dfqueue/runs.py`, `dfqueue/live.py`, `scripts/stream_publisher.py`,
  `web/stream/`, `scripts/preview_stream_live.py`, `infra/` (only if an
  openclaw config file is committed there), tests.
- Use `DF_ENV_FILE=c:/website-projects/df-automation/.env` for
  `scripts/vm-ssh.sh`; read `.env` by key only; never print a secret from
  openclaw's config or state. Public repo: no hostnames, IPs or tokens. No em
  dashes. No attribution lines in commits.
- Full ambient suite and `dfmcp/tests` (in `.venv-dfmcp`) green; headless
  check of both pages, no console errors.

## Done when

Findings with citations, the proving run's result, the build with tests, the
deploy plan, and a Result section here.

## Findings (task 1 and 2, executor, 2026-10-05)

openclaw version 2026.9.4 (image `ghcr.io/openclaw/openclaw:latest`, `/app/package.json`).

Supported route: `openclaw agent exec --state-dir <existing dir>` retains sessions and run state
(`/app/docs/cli/agent.md`, "agent exec": "Use `--state-dir <dir>` to retain sessions and other run
state. The directory must already exist ... requires exclusive ownership"). Without it, state is a
temp dir deleted after the run, which is why the transcript tables were empty. `--json` itself has no
reasoning text (envelope fields in the same doc: only `usage.reasoningTokens`). Trajectory capture is
on by default and stored in the per-agent SQLite db (`/app/docs/tools/trajectory.md`, "Capture
storage"); `openclaw sessions export-trajectory` is a documented export (`/app/docs/cli/sessions.md`).
`--thinking <level>` sets the level (`/app/docs/tools/thinking.md`); the default for this model was
`medium` (thinking_level_change event).

Proving run (consultant pinned config, transient unit shape, trivial prompt, no tools): exit 0, cost
about 0.0046 USD, 15 reasoning tokens. With `--state-dir /thinking` (a throwaway host dir mounted
there), `agents/consultant/agent/openclaw-agent.sqlite` held 6 `transcript_events` rows and 7
`trajectory_runtime_events` rows. The assistant message event (`event_json`, `message.content`) has a
`{"type":"thinking","thinking":"<text>"}` block before the `{"type":"text"}` block. So the reasoning
text is retrievable per run from `transcript_events.event_json`. Host writes made: `/tmp/think-proof`,
`/tmp/think-copy`, `/tmp/think-proof.out|err` (all disposable).

Design consequences: state dir must be exclusive per run, so use one per role (or per run) outside the
shared `/opt/openclaw/config` state; the container user is uid 1000, so the dir must be writable by
it. Read the db with node:sqlite inside the image (a read-only mount fails on WAL).
