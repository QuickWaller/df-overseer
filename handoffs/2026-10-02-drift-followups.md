# Handoff: drift system follow-ups (doc audit, daily alert, live tool check)

Date: 2026-10-02. **Executor, Sonnet, worktree.** May install one scheduled
task on this workstation (task 2). No VM writes and no deploys: the
orchestrator deploys after merging.

## Why

`handoffs/2026-10-02-deploy-and-drift-system.md` built the deploy command,
the drift check and a doc-audit brief; the first deploy through them ran
clean (`evals/live/2026-10-02-site-and-tools-deploy/`). Three follow-ups,
user's go-ahead 2026-10-02.

## Tasks, in order (commit after each)

1. **First doc audit.** Follow `.claude/commands/doc-audit.md` exactly. Known
   items to include: `web/stream/README.md` still calls slice S1 "prepared
   offline, not deployed" (it is deployed, with board, site and per-fort
   data); CLAUDE.md's status block has stale deploy and tool-count facts
   (the user parked moving fort-level facts to the site, so leave fort facts
   such as population in place, but point non-fort counts and deploy state at
   `docs/STATE.md`). Fix plain factual drift; list judgment calls in the
   Result without making them. You may edit CLAUDE.md for this task only, and
   only its status block's factual sentences; never its Rules sections.
2. **Daily drift alert.** Install a Windows Task Scheduler task on this
   workstation that runs `python scripts/drift_check_telegram_alert.py` once a
   day (09:00 local, and "run as soon as possible after a missed start" so a
   sleeping machine still checks), working directory the repo root. Use the
   instructions in `docs/RUNBOOK-DEPLOY.md`; fix them if they are wrong. Run
   the script once with `--dry-run` to prove it works from the task's
   context; do not trigger a real send. The script is silent on a clean run;
   confirm that an unreachable host also alerts rather than passing silently,
   and fix it if not. Record the exact task name and how to remove it in the
   runbook.
3. **Live tool lists.** Add `scripts/ops/mcpcall.py` (and anything it needs)
   to the `vm103-dfmcp` target in `infra/deploy-manifest.yaml` and make
   `scripts/drift_check.py` compare per-role live tool ids from the running
   server against the allowlists once it is deployed (it degrades to offline
   counts today). Read how `mcpcall.py` authenticates first; per-role tokens
   stay where they are (read by key, never printed). Test offline.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Read `.env` by key only. Public repo: no hostnames, IPs or tokens. No em
  dashes. No attribution lines in commits.

## Done when

The audit's commits and its judgment-call list, the scheduled task's name
and a `--dry-run` from it, the live-check change with tests, and a Result
section here.

## Result (2026-10-02, executor)

Four commits on this branch: `1d60ce6` (doc audit), `310dbcf` (daily
alert), `78d6f70` (ship mcpcall.py for counts), `8825561` (upgrade the
check to real tool-id comparison, not just counts). `git merge --ff-only
main` was a no-op (already current). All read-only drift checks were run
against the real VM 103/relay hosts via `DF_ENV_FILE` pointed at the main
checkout's `.env` (read by key only, never printed; the worktree has no
`.env` of its own, by design).

### Task 1: doc audit

Ran `python scripts/drift_check.py --write-state` first (clean before this
stream's own changes; `docs/STATE.md` regenerated three more times as later
tasks changed what it reports). `tests/test_doc_facts.py` passed before and
after (CLAUDE.md's tool-count sentence already matched `docs/STATE.md`
exactly going in -- a prior stream had already fixed it).

**Fixed** (commit `1d60ce6`):
- `web/stream/README.md` called slice S1 "prepared offline, not deployed"
  in three places (title, and two status paragraphs). It has been deployed
  and live since 2026-10-02 (`evals/live/2026-10-02-site-and-tools-deploy/`,
  `stream-publisher.timer` active+enabled per `docs/STATE.md`). Updated the
  title and both status paragraphs; left the step-by-step deploy procedure
  itself alone, as the record of what was actually run.
- `docs/RUNBOOK-DEPLOY.md`'s target list named six targets; the manifest
  and `docs/STATE.md` both have seven (`relay-web-operator` was missing).

**Judgment calls found, not made:**
- `Working.md`'s "Parked (user, 2026-10-02)" note says: "After the drift
  system lands, trim only the non-fort parts of CLAUDE.md's status block
  to pointers." The drift system has now landed (this stream and its
  predecessor). CLAUDE.md's status block still hand-writes the per-role
  tool-count numbers rather than pointing at `docs/STATE.md`; that is by
  design today, since `tests/test_doc_facts.py` mechanically parses that
  exact hand-written phrasing. Converting it to a pointer is a real change
  (rewording the sentence AND updating that test's parser), not a
  mechanical fix -- left for the orchestrator/user to decide whether and
  how.
- `ROADMAP.md`'s `**Last reviewed:**` line is 2026-09-25, a week old.
  CLAUDE.md's own cadence is "at least every ~2 weeks," so this is not
  yet due; noting it since it will be soon.
- Working.md's own numbers (e.g. "overseer 87, architect 52...", dated
  2026-09-30) disagree with the current `docs/STATE.md` counts, but every
  instance is inside a dated, past-tense progress note ("today",
  "2026-10-01 progress"), which the doc-audit brief treats as a frozen
  historical claim, not a current-state sentence to correct -- and
  `Working.md` is explicitly not mine to edit regardless.

**Could not verify / outside STATE.md's reach:** nothing blocked this
audit; every check in `.claude/commands/doc-audit.md`'s list had a live
answer available.

### Task 2: daily drift alert

**Bug found and fixed** (commit `310dbcf`): the handoff's own worry was
right. `drift_check_telegram_alert.py` let `drift_check.build_report`'s
`SSHError` (host unreachable) propagate as an uncaught traceback -- no
Telegram message sent at all, which is the one failure mode a daily
unattended check most needs to catch. Now caught and alerted (an error
message instead of a drift report), in both the `--dry-run` and real-send
paths; both covered by new tests
(`test_unreachable_host_alerts_instead_of_crashing_dry_run`,
`test_unreachable_host_alerts_for_real_when_not_dry_run`).

**Task installed**: Windows Task Scheduler, task name
`df-overseer-drift-check`, daily at 09:00 local, `StartWhenAvailable` set
(a sleeping machine still checks once it wakes). `schtasks.exe` has no
flag for this (`schtasks /Create /?` confirmed no such switch exists; it
is a GUI Settings-tab-only option otherwise reachable via XML or the
PowerShell `ScheduledTasks` module), so this was created with
`Register-ScheduledTask` instead -- exact command in
`docs/RUNBOOK-DEPLOY.md`. Its action runs from the **main checkout**
(`C:\website-projects\df-automation`), per the handoff's instruction, not
this worktree (confirmed: `Get-ScheduledTask`'s `Actions` show
`WorkingDirectory = C:\website-projects\df-automation`).

**Proven working**, per the handoff's own instruction not to trigger the
live task (its real action has no `--dry-run`, and would do nothing
visible since the fort was clean when checked): ran the exact registered
action command by hand with `--dry-run` appended --
`"C:\Program Files\Git\bin\bash.exe" -lc "cd /c/website-projects/df-automation && python scripts/drift_check_telegram_alert.py --dry-run"`
-- exit 0, no output (clean at the time). The real task was never
triggered.

**Removal recorded** in `docs/RUNBOOK-DEPLOY.md`:
`Unregister-ScheduledTask -TaskName "df-overseer-drift-check" -Confirm:$false`.

**Heads-up for the orchestrator**: task 3 below (see next section) makes
`vm103-dfmcp` genuinely DRIFT right now (`scripts/ops/mcpcall.py` is in
the manifest but not yet deployed to the host). The installed task's
*next real run* (tomorrow 09:00, or sooner if the machine was asleep at
09:00 today) will find this real drift and send a real Telegram message,
unless `vm103-dfmcp` is deployed before then. This is working as intended
(real drift, real alert) but is worth knowing about rather than being
surprised by.

### Task 3: live tool lists

Read `scripts/ops/mcpcall.py` before changing anything: it authenticates
with a per-role bearer token read by key from
`/opt/df/dfmcp-smoke/.env` (`MCP_ROLE_TOKEN_<ROLE>`), already live on the
host and untouched by this stream; it needs the `mcp` and `httpx2`
packages already installed in `/opt/df/dfmcp-smoke/.venv` from prior
manual smoke-test runs.

- Added `scripts/ops/mcpcall.py` to the `vm103-dfmcp` manifest target
  (commit `78d6f70`). `scripts/drift_check.py` already had a
  `check_live_tool_counts()` that probed for and used this exact file when
  present (built by the predecessor stream, tested offline already) --
  the missing piece really was just shipping the file.
- Went further than count comparison (commit `8825561`), since the
  handoff asked for comparing "per-role live tool **ids** ... against the
  allowlists," and a count-only check would call two roles clean if they
  carried the same number of tools while disagreeing on which ones. Added
  a `names-all` mode to `mcpcall.py` (one `role<TAB>name` line per tool,
  every role, one SSH round trip) and rewrote
  `check_live_tool_counts()` to translate each live MCP name back to a
  tool id via `dfmcp.tools.build_tool_names()`'s `name_to_id` map (the
  module's own documented, sanctioned reverse direction -- never
  "`__`-to-`.`" string surgery, which the module's docstring explicitly
  warns is not safe in general) and diff real id sets per role. A
  mismatch now reports `missing_live`/`extra_live`/`unknown_live_names`
  alongside the two counts (kept for the existing Telegram-alert message
  format, which reads `m['offline']`/`m['live']`).
- Tested offline only, as instructed. New cases in `tests/test_drift_check.py`
  use the REAL roster's tool ids (not stubs) to prove: a genuine id-for-id
  swap with equal counts is still caught
  (`test_check_live_tool_counts_catches_id_level_mismatch_with_equal_counts`),
  a clean real-id dump compares clean, and a role the live dump never
  mentions at all is not itself treated as a mismatch.
- Fixed stale notes in `scripts/drift_check.py`'s module docstring, its
  `check_live_tool_counts()` note string, and `docs/RUNBOOK-DEPLOY.md`
  that said mcpcall.py was "not part of any manifest target" -- it now is,
  but a manifest entry alone does not deploy it; regenerated
  `docs/STATE.md` shows this honestly (`vm103-dfmcp` now DRIFT,
  `missing_on_host: scripts/ops/mcpcall.py`, until a real deploy ships
  it -- see the heads-up above).

### Tests

Targeted suite (`test_drift_check.py`, `test_drift_check_telegram_alert.py`,
`test_deploy.py`, `test_doc_facts.py`): **59 passed**, run twice (once after
each of the last two commits). Broader sweep including every manifest/tool
test (`test_blueprint_tool_manifest.py`,
`test_building_tool_manifest.py`, etc.): **167 passed**. Full ambient
`python -m pytest -q` (the `lupa` package is installed globally on this
workstation, so no Lua-logic tests were skipped by its absence): **2488
passed, 1 failed, 3 skipped** (prior run, before task 3's second commit;
a second full run was kicked off after the id-level rewrite and had not
finished by the time this report was written -- see note below). The one
failure, `doctrine/tests/test_wiki_check.py::test_cli_exit_codes`, is
unrelated to anything this stream touched (a wiki-mirror freshness check
under `doctrine/`) and reproduces in isolation with no stream changes
applied to that area; it looks date-sensitive (the test's mirror
"freshness" math reads `very_stale` against a fixed baseline timestamp,
which naturally ages past whatever threshold the test assumed as real
calendar time moves on) rather than something this stream broke. Flagging
it rather than fixing it, since `doctrine/` is outside this handoff's
scope. CLAUDE.md's own "ambient pytest gives 1845 passed, 3 skipped"
trap note (dated 2026-09-25) is now itself stale by a wide margin (the
suite has grown past 2480 tests since); worth a mention in CLAUDE.md's
traps section at some point, judgment call not made here since that
section is arguably Rules-adjacent, not the status block this task's
scope covers.
