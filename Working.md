# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## Open: rotate leaked keys (2026-09-17)

A session ran `cat .env | grep -v SECRET` while looking up the VM 103 SSH
user, breaking the "read secrets by the key you need" rule — it printed
`ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`, and
`CLOUDFLARE_TUNNEL_TOKEN_ADMIN` into the session transcript in full. User's
call: rotate later, not urgent, but don't lose the item. → decisions/DECISIONS.md
2026-09-17.

## In design: the agent loop MVP (2026-09-22)

The user's goal: "design the agent loop, fill in the gaps, let the fort run",
an MVP to improve from what it does. Design lives in `docs/AGENT-LOOP.md`
(register 2026-09-22). **Agreed:** dispatcher plus queue (one-shot
`agent exec` runs woken by a code conductor); clock speed set per wake reason
(full, slowed, paused), from ticks-to-consequence where computable;
`base_fps` a setting the user may lower later. **Defaults not yet confirmed:**
the six build items in its §4 (in-game clock and tripwire script, a
`conductor` dfmcp role, the conductor service on VM 106, an execution record
with prediction windows starting at execution, enabling the Quartermaster, a
Tier 0 briefing). Nothing built.

**Since then, same day:** the roster (Overseer, Architect, Quartermaster,
Consultant), Consultant retrieval (local wiki, DFHack source, Brave web
search, `agents/consultant/sites.yaml`) and the objectives direction (an
Overseer-kept graph with a default flow and deviations, §6) were agreed. Three
offline build streams are dispatched (`handoffs/2026-09-22-loop-*.md`) and one
researcher on objective-graph prior art. **At merge, owed by the orchestrator:**
flip `quartermaster` to enabled in `ROSTER.yaml`; add the README and
`infra/local.example.env` lines the streams report; re-run both suites.

**Held by the user, part of the framework design, not yet started:** how
proposals work end to end: (1) the Overseer proposing to itself, with no
second check; (2) which checks each kind of change needs (tactical,
strategy, agenda, template, doctrine); (3) which revisions count as learning.
**Design input agreed for that conversation (2026-09-22):** one shared
"revisioned knowledge" pattern for doctrine, the agenda template, gotchas,
playbooks and the wiki snapshot: stable entry ids, a revision number,
citations of `entry@rev` (the court judges against what was actually read),
a change log with reasons, and a cited-by index that flags, never edits,
dependents when an entry changes. Not in the MVP; keep entry ids stable
until then.

**All three streams merged locally 2026-09-22** (`375d1f9`, `c0bdd6a`,
`5edd1e4`), each checked against its code, the Quartermaster enabled, owed
lines applied. Suites after the last merge: ambient **1035 passed / 3
skipped**, `.venv-dfmcp` **604 passed**. Nothing deployed, nothing pushed.
Design flags and deploy traps from the streams are in `docs/AGENT-LOOP.md`
§7 (notably `proposal-0001` would grade as a latency miss on first run).

**Conductor built and merged 2026-09-22**, then a pre-deploy fix stream
(the Consultant wake via `queue.overview`, refusals reaching clients as
`isError`, `queue.escalate` as the only escalation route, requirements file).
Suites: ambient **1202 passed / 3 skipped**, `.venv-dfmcp` **623 passed**.
Known gap, explained: no "hostile seen but unreachable" signal. History was
rewritten by home-lab-8e the same day to strip Claude credit; local `main`
is credit-free, 68+ ahead of `origin/main`, fast-forward.

**DEPLOYED 2026-09-22, fort kept paused** (`handoffs/2026-09-22-loop-mvp-deploy.md`,
`evals/live/2026-09-22-loop-mvp-deploy/`), orchestrator re-checked on both VMs:
VM 103 paused, year 31, tick 106974, 100 FPS, `dfmcp-server` active,
`proposal-0001` voided, 30-page wiki snapshot at `/var/lib/dfwiki/`; VM 106
conductor unit **disabled and inactive**, four pinned openclaw configs, no
containers. Role tool counts: overseer 60, architect 35, consultant 21,
quartermaster 21, conductor 13. Dry run: it would wake the quartermaster on
`vital_nearing_threshold` and slow the clock to 10. Two live bugs fixed in
the deploy (the conductor's MCP client against the real SDK, a missing
`diff.since` grant).

**Owed before the first real start:** (1) **text encoding**:
`diff.since` crashes on a CP437 character in a dwarf's name, and no script
converts game text with `dfhack.df2utf`, so any tool emitting names may too
(**DONE 2026-09-22**, `handoffs/2026-09-22-loop-game-text-encoding.md`:
shared `df-overseer-textutil.lua` helper, CP437 backstop in
`dfmcp/dfhack_client.py`, redeployed; unseeded conductor dry run now clean;
orchestrator re-checked the fort paused at tick 106974 and the backstop
firing in the journal. **Residue:** `diff.lua`'s eventful listeners were
registered once per DF process under the old code, so new events still log
raw CP437 until they re-register (DF restart, or a version-keyed
re-registration); the backstop covers it meanwhile. Also found:
`fort.quicksave` predicted the wrong autosave slot this run); (2) **Docker access: DONE 2026-09-22**,
`SupplementaryGroups=docker` in the installed unit only, the `df` account's
own groups unchanged (`handoffs/2026-09-22-loop-conductor-docker-access.md`,
re-checked by the orchestrator); awaiting the user: (3) the tripwire live tests, which
need a brief supervised unpause; (4) a short supervised first cycle.
**Home-lab inventory:** home-lab-8e wrote both `inventory/services.yaml` lines
(the conductor unit on VM 106, openclaw's four roles) on 2026-09-22, validated
but **left uncommitted** in `../home-lab` beside other in-flight changes, for
the user or whoever commits there next.

**Earlier plan, now done:** one deploy stream for everything, running the clock stream's nine live
checks and voiding `proposal-0001`. **The user authorised the deploy to place
the MCP role tokens itself (2026-09-22: "you can do the tokens yourself"),**
including the new quartermaster, consultant and conductor tokens on VM 106.
Rules still hold: read by key name only, never printed or tracked. If the
auto-mode classifier refuses the secret-store write again (it did on
2026-09-15), stop and tell the user; never route it through another session.

## In discussion: designing the learning loop (2026-09-17)

**Not designed yet, by the user's own assessment.** No code; do not start
building from this section. The design is being settled one question at a time
with the user.

**Agreed so far** (→ `decisions/DECISIONS.md` 2026-09-17):
- Doctrine sources carry per-source provenance; `verified` needs a 53.16 live
  or game-data source; a pytest validator enforces it (built).
- `get_doctrine`, read-only, with a topic index (agreed; **built 2026-09-19** as `doctrine.get`, consultant only, **deployed and live-verified 2026-09-20**).
- Doctrine revisions are proposals; the Overseer can accept, reject, defer,
  **amend**, or hand the proposal to another role for querying first.
  Amendments apply directly for tactical and strategy proposals and return to
  the proposer once for doctrine. Research alone can only yield `prior`.
  Applied doctrine changes go in a user digest for now.
- The quartermaster probably becomes necessary, owning strategy from
  inventory and production trends.
- Every proposal must list the doctrine entries it relied on. An empty list
  is valid ("relied on none"); a missing field is not. A miss puts the cited
  entries under suspicion, which is what links grading to revision.
- **A grader limited to code and a closed signal list is too narrow** (user,
  2026-09-17). Candidate under discussion: plain-language predictions written
  before acting, facts gathered by code, and a small jury of different model
  families that sees only the prediction and the facts. Not decided.
- **A retrospective court, not a gatekeeper** (user, 2026-09-17/18): a
  prosecutor and a defence argue whether past proposals succeeded, at
  per-proposal review horizons, batched into sessions. Code grades what a
  signal settles; the court handles what it cannot; "unclear" must be an
  allowed verdict. Adversarial review of a proposal *before* execution was
  judged overkill. Open: who sets the horizons, who judges, what a verdict
  attaches to, and what wakes a session (no scheduler exists).
- **openclaw has no multi-agent primitive worth using** (research
  2026-09-18, not independently confirmed in source: the local checkout is
  scaffolding only). It has native session send/spawn, but the inter-agent
  lane is reported as one concurrent operation, and cron, heartbeat and
  webhook triggers all need a Gateway this project has never run. Hooks
  exist for session and command lifecycle, **not** tool calls, so
  `dfmcp/roles.py` stays the only real safety boundary. No spend cap of
  any kind. Recommendation: keep the dispatcher-plus-queue design, with
  independent one-shot `agent exec` runs. **Pending the user's decision.**
- **Work orders can carry standing policy** (research 2026-09-18): shipped
  conditioned orders exist, `JOB_COMPLETED` needs a one-line extension to
  measure production, and the manager-appointment question needs one
  supervised unpause to settle. None of this fort's current blockers is an
  order problem.
- **Tools carry a confidence level, and their gotchas are learned material**
  (user, 2026-09-21): full means use it, medium means read the description and
  gotchas closely and monitor for success. Part of this loop; each tool keeps
  gotcha, vent and unexplained-error lists; results carry the level and short
  condition-titled gotchas only; agents propose gotchas via the queue; the
  level is static, with no mechanism to raise it (user, 2026-09-21); vent is
  a complaint channel for an agent to say a tool does not fit its need. → `docs/BUILDING-TOOL.md`.
- **The Overseer hands proposals to the consultant for fact-checking** (the
  "wiki nerd and researcher" role) before ruling.
- **A new learning role, separate from but related to the consultant**, name
  TBD: its job is identifying patterns (for example across graded misses
  against cited doctrine) and proposing doctrine revisions. It is both a
  helper and a proposer, callable by other roles and able to call them
  (for example the consultant, to check a source). Not the chronicler, whose
  charter forbids influencing what the fort does. Mechanical parts stay code:
  grading, tallying misses, flagging an entry disputed, applying changes.
  Agents cannot call each other today (one-shot runs, queue as the only
  channel), so the calling mechanism is undesigned.
- **Other roles may propose doctrine revisions too, but must discuss them
  with the learning role first.** Enforced by the queue: such a proposal
  must reference the discussion record, which carries the learning role's
  view to the Overseer. **Scope: doctrinal and learning revisions only**, not
  every revision (tactical and strategy amendments never need it).

**Built today vs missing, checked against code:** predictions are recorded
and there are two graders (`dfqueue/grade.py`, `learning/predictions/`), but
neither has graded a real proposal. There is no evidence model, no doctrine
revision type (the reader, `doctrine.get`, is live), no chronicle and no
scheduler. The fort's history is now stored and readable (`dfseries`, the
`series.*` tools), but nothing consumes it for grading yet.

**Two of this section's open questions were answered by the production-model
work on 2026-09-18, not by this conversation.** Recorded here because they
were listed as open and no longer are:

- **"Who sets the review horizons"** for the retrospective court. **Material
  class does.** A decision about a consumed good (food, drink) is reviewable
  in days, a keep-on-hand par level in weeks, an insurance level only after
  the threat fires, a reserve floor never, because the whole point of a floor
  is that nothing happens. So the horizon is a property of what the proposal
  was about, derived from the band, rather than a number the proposer picks or
  the court negotiates. → `docs/PRODUCTION-MODEL.md` §10.
- **How an outcome gets attributed** when a proposal misses. The
  four-quadrant rule gives the court a mechanism it did not have: build the
  expectation from Q1 and Q3 (raws and exact reads), and the gap is a
  **residual, reported as unattributed** rather than explained. That splits a
  miss three ways cleanly: the plan was not executed, the plan executed and
  the figures behind it were wrong, or the plan executed on sound figures and
  the objective itself was the wrong choice. Only the third is a
  decision-quality question, and only the third is worth an adversarial
  sitting. → `docs/PRODUCTION-MODEL.md` §3.

**Also relevant, and uncomfortable:** the lever catalogue found that only
four of ten named diagnoses have a tool that can act on them. A court that
reviews proposals the fort could never have executed is grading the wrong
thing, so the catalogue is a prerequisite for the court rather than a
side-quest. → `docs/PRODUCTION-MODEL.md` §13.

**Still open:** exactly which revisions count as "learning" (playbook
thresholds? evidence rules?); the learning role's name; how roles call each
other (referral to the consultant, calls to and from the learning role); how
the learning role decides a run of misses is a pattern without an arbitrary
threshold (research 2026-08-25 already rejected one); the background
ground-truth audit idea (below, under HANDOVER); what `ROADMAP.md` should say
about the learning loop specifically, deliberately not written until the
design settles.

**Next concrete step:** continue the design conversation with the user from
"which revisions count as learning revisions".

## Archived: production model designed, audited, four streams dispatched (2026-09-18)

Moved to `working-archive/Working_archive-2026-09-14.md` on 2026-09-19: every
stream it dispatched finished. Design lives in `docs/PRODUCTION-MODEL.md`.

## The visual ledger (artifact)

**https://claude.ai/artifact/NK1FMkcA1ev9Wvcas6SBpD** (published 2026-09-19).
The fort's state, the production model's build status, the four quadrants, the
lever table, the four deductions, and a two-route diagram of the well versus
brew chains. **It exists to keep measured facts visibly separate from asserted
ones**, and carries the "things this project got wrong" list deliberately.

The **earlier** artifact (`CQZHQDLRB7hRHWLqYrfmY5`) was published under a
different account and **can no longer be updated from this session**. Do not
try; publish to the URL above instead. Republishing the same scratchpad file
path keeps that URL.


## Archived: live fort state and the 2026-09-19 handover (2026-09-21)

Moved to `working-archive/Working_archive-2026-09-14.md` on 2026-09-21: both
2026-09-18 live-fort sections ("cannot drink", tick 227160/235668) and the whole
HANDOVER 2026-09-19, superseded by the section below. Fort figures in them are
historical.

## Current state, 2026-09-15: archived

Moved wholesale to [`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md) on 2026-09-18, superseded by
HANDOVER 2026-09-19 and the production-model work above.

## HANDOVER 2026-09-21, evening (read this first after a /clear)

The first half of the earlier 2026-09-21 handover (the 2026-09-20 fort figures, the
2026-09-20 deploy note, and the START HERE list with its accumulated status
paragraphs and the long "design gaps" item) moved wholesale to
[`working-archive/Working_archive-2026-09-21.md`](working-archive/Working_archive-2026-09-21.md)
on 2026-09-21 (the file had reached 522 lines). Nothing was summarised there; what
is still true from it is restated below.

**Authority.** The user granted full authority to push, change the VM and act on
the fort ("this is all dev experiments not production"), and asked not to be asked
per action. **Two things changed today:** (1) `CLAUDE.md` still says a push needs
the user's go-ahead each time, and the user's own settings allow `git push` without
a prompt, so **ask before pushing** (a push was made without asking on 2026-09-21
and is recorded as a slip); (2) live VM work is best done in manual mode or with the
`autoMode` block now in the user's settings (below). Standing exception: genuinely
unrecoverable loss (the fort save, the VM itself) stops and reports. Two standing
rules from the rollback are in `docs/TRAPS.md`: never run an unbounded query against
a live DFHack process, and quicksave immediately before any live fort action.

### The fort, re-read live 2026-09-21

Uniboslan, year 31, **paused at tick 106974**, 22 alive and 1 dead (unit 454
starved at tick 15143), 100 FPS when running. At the last poll worst hunger was
39,984 and worst thirst 25,093 (nowhere near critical). **The well is built** (id
8). **MANAGER is held by unit 345** (Tun Konosamem, a Stonecrafter), appointed by
the new `nobles` tool. The fort has **no zones at all, so no Office**, and the three
queued manager orders (ConstructBlocks x1, ConstructMechanisms x1,
`BREW_DRINK_FROM_PLANT` x8, all hand-validated on 2026-09-19) **did not start in a
3,900-tick window**. The user confirmed from play that the Manager needs an office.
Two quicksaves exist from today (`autosave 3` before the appointment, `autosave 2`
after it, 09:25:04Z). Autosave and the sampler run only while unpaused.

**Read hunger, thirst, deaths and stock together before calling it healthy**
(register 2026-09-19).

### Live on VM 103 (deployed 2026-09-21, hash-verified)

Role tool lists **architect 34, overseer 57, consultant 14** (were 25/45/11): the
generic `building` tool (`list-kinds`, `find`, `build`; **dry runs only**),
`labor enabled-counts`, `gotchas.get`/`gotchas.write` (static confidence file,
`tool_guidance` enrichment), the labor graph and join (graph at
`/var/lib/dfproduction/`, **5 known / 23 partial / 5 unknown of 33 kinds**),
`nobles` (`list`, `verify`, `appoint`, `unappoint`) and the generalised `zone` tool
(18 zone kinds, optional owner). New state: `/var/lib/dfgotchas` and one
`ReadWritePaths=/var/lib/dfgotchas` line; backups in
`/opt/df/deploy-backup-2026-09-21-building-batch/`. **Merged, not yet redeployed:**
the labor join's real-shape fix (`dfmcp/labor_join.py`, `dfmcp/tool_guidance.py`).
Fourteen tracked scripts on the VM differ from main by one trailing blank line (the
known artifact); `df-overseer-embark.lua` is on the VM and untracked. **Suite,
measured 2026-09-21:** ambient **891 passed / 3 skipped**; `dfmcp/tests` in
`.venv-dfmcp` **537 passed**.

### Where the MVP stands (the user's minimum bar for openclaw, 2026-09-21)

Build workshops, rooms and furniture, assess dwarves, grow food, build wells.
**Wells: done.** **Workshops:** tool deployed, never built for real (no never-built
kind has been built; reachability of a site is not checked). **Rooms:** the zone tool
is built and deployed; a real placement, the owner assignment and its read-back have
never run; what makes an Office meet a room value is not exposed by the game.
**Furniture:** about 14 kinds dry-run; no way to place furniture inside a given room,
nothing assigns a bed or room to a dwarf. **Assess dwarves:** not designed (what it
feeds into is unanswered). **Grow food:** farm plot tools exist; the fort is fed by
wild gathering; the end-to-end run and the `growdur` unit are unsettled. **Also
missing:** stockpile creation and configuration; a way to run the game forward
safely and watch the vitals continuously; defence; the chronicler; and, biggest, the
agent loop itself (no agent runs as a service, nothing executes an accepted proposal
or grades on a schedule, openclaw is not designed). Order proposed by the orchestrator
(not yet confirmed by the user): prove the tools do real things first, then design
assessment and the food chain, then the loop.

### How the work ran today (process, so it is not re-learned)

Handoff, executor in a worktree, merge, **re-run both suites myself**, record. Two
findings came out "premise wrong" (the 145 reactions are in no raw file; a first
"nothing exists in DFHack" claim was overstated), so live reads beat offline
assumptions. **Worktree agents are created from `origin/main`**, not local HEAD, and
carry their own copy of `.claude/settings.json`: tell every dispatched agent to
`git merge --ff-only main` first. **Auto mode's classifier** refuses live dev-VM work
by its default rules ("Production Deploy", "Remote Shell Writes", "Modify Shared
Resources"); an `autoMode` block (environment, allow, soft_deny, each starting with
`"$defaults"`) was added to the user's `~/.claude/settings.json` on 2026-09-21 and
`claude auto-mode config` shows it merged; its effect is partly evidenced (a live
deploy dispatch and ssh reads went through in auto mode, three specific commands were
still refused). A backup of the previous file is in that session's scratchpad. **Write
scripts with the editor tool**: long shell heredocs containing quotes were rejected at
parse time repeatedly. **Hash committed bytes** (`git -c core.autocrlf=false show
HEAD:path`), not the working copy.

### START HERE, in priority order

**Sequencing rule:** one stream at a time on VM 103 or the fort. Two offline streams
may run together only with strictly disjoint file ownership. Push before dispatching
if the agent must see a commit, or tell it to fast-forward to local `main`.

1. **Redeploy `dfmcp` (labor join shapes) and check it live**: ship
   `dfmcp/labor_join.py` and `dfmcp/tool_guidance.py`, restart `dfmcp-server`, then
   call `building.find` for the Well over the live server and confirm the gap
   `needs 1 of TRAPPARTS, 0 available` reaches the agent. Asked of the user, not yet
   answered.
2. **The Office and Manager test.** Quicksave (confirm by every slot's mtime), place
   an Office with the zone tool (owner `MANAGER`; no fully indoor 3x3 site exists near
   the embark landmark at level 0, so it would be open-air, effect unknown), furnish it
   with the building tool (desk and chair; nothing places furniture inside a zone
   yet), read the room description, then one supervised unpause with the watchdog to
   see whether the queued orders run. Needs the user's go-ahead.
3. **The first real supervised build of a never-built kind** with the building tool
   (a Craftsdwarf's workshop, say): read-back, whether `buildingplan` picks up the
   materials (its state in the running game is unknown).
4. **Generalise `workjob`** (`handoffs/2026-09-21-workjob-generalise.md`, written, not
   dispatched): DFHack's `workshops.getJobs` builds a workshop's job list including
   reaction jobs, and a job has a `repeat` flag (a standing order with no manager).
5. **Design what is undesigned:** assessing dwarves, growing food end to end (re-read
   and trim `handoffs/2026-09-18-supervised-run-and-measure.md`: it is unrun and still
   the way to settle `growdur`, one real job duration with skill, claim state over an
   interval, and `item.age` against the pruned announcement buffer), stockpile
   creation and configuration, game-clock control, defence.
6. **Older open items still true:** a drink that does not depend on luck (brewing:
   `workjob` refuses the container reagent by design; the unlocated water source;
   fishing and hunting); the MCP apostrophe fix (the server refuses `Stoneworker's
   Workshop`); z167 stone (the rollback lost the stair; check before anyone plans on
   it); the `mason` labor in `df-overseer-workshop.lua` is wrong for block work
   (STONECUTTER); two unguarded `items.other.*` patterns crash loudly (hardening).
7. **The harness:** the user wants an overhaul of the auto versus manual setup. The
   `autoMode` fix is applied and partly evidenced; decide with the user whether a
   two-lane policy (offline work in auto mode, live VM work in manual) is still
   wanted.

**Parked ideas and settled rules (2026-09-21):** an **investigator** role (read-only
commands plus reading DFHack's source and docs, both on VM 103; not designed, and raw
`lua` is not read-only); **Dwarf Therapist** as an observation and cross-check tool
for the user (a GUI with no API, so agents cannot call it) and prior art for scoring
dwarves. **No armok capabilities** (`CLAUDE.md`, `docs/ARMOK-RULINGS.md`): the ban is
on powers a player lacks and on hidden information; the classification is
`research/2026-09-21-dfhack-tool-classification.*` and the review is
`research/2026-09-21-armok-review.md`. **Every tool must be generalisable**
(`CLAUDE.md`); `zone`, `building` and `nobles` follow it, `workjob`, `workshop` and
`orders.create` do not yet.

### Open, waiting on the user

- **The loop architecture: UNTABLED 2026-09-22, in design with the user**, see
  "In design: the agent loop MVP" below.
- **Key rotation** for four exposed secrets, deferred by the user ("ill rotate
  them another day"). See the section at the top of this file.

### Owed to home-lab (noted 2026-09-19, user-directed; not writable from here)

This repo may not edit `../home-lab`; route these to a session there or to the
user. Anything sent must carry the command actually run against the live
system, per `CLAUDE.md`'s upstream obligations.

- **`inventory/services.yaml`: add `dfseries-import` on VM 103**
  (`df-colony-01`), beside the existing `dfmcp-server` entry. A systemd
  oneshot service plus a 60s timer, **enabled 2026-09-19 on the user's
  go-ahead, so boot-persistent**. Code at `/opt/df/dfmcp-smoke/dfseries/`,
  database at `/var/lib/dfseries/uniboslan.series.sqlite3`, reads the sampler's
  JSONL under `/opt/df/game/dfhack-config/timeseries/`. Verify with
  `systemctl is-enabled dfseries-import.timer` and `systemctl is-active
  dfseries-import.timer` on VM 103. Full suggested entry in
  `handoffs/2026-09-19-dfseries-auto-import.md`, "What home-lab needs to know".
- **No IP changes**: nothing today allocated or changed an address, so
  `inventory/ips.yaml` is untouched.

### LAN addresses already public in git history (noted 2026-09-19, user-directed)

**Found 2026-09-19** while checking a new write-up for leaks: 
`working-archive/Working_archive-2026-09-07.md` has carried VM 103's and the
relay VM's LAN addresses, plus a VNC port and a noVNC URL, **on GitHub for
weeks**, against this repo's own rule. RFC1918 private addresses, so reachable
only from the home LAN or via the relay: low severity, but a real breach of
the rule, and the kind of detail a public repo exists not to hold.

- **Not yet decided by the user**, deliberately. Two options:
  1. **Redact from here on**: replace them in the current file with
     `<df-vm-ip>`-style placeholders. Cheap and safe, but the addresses remain
     readable in history forever.
  2. **Rewrite history** (`git filter-repo` over those strings, then a force
     push). Actually removes them, but rewrites every commit hash after the
     first occurrence, breaks every existing clone and worktree, and cannot be
     undone once pushed. Needs the user's explicit go-ahead, and every other
     session on this repo stopped first.
- **A guard already exists, and this note wrongly proposed one.**
  `tests/test_no_leaked_addresses.py` (commit `994e8a5`, 2026-09-12) fails the
  suite on any private IPv4 or `.internal` hostname in a tracked file. It
  **deliberately excludes `working-archive/`** as a historical record, which is
  exactly why the 09-07 archive's addresses never tripped it. So the real
  decision is whether that exclusion should stay. It caught this very note on
  2026-09-19, when an earlier draft quoted the illustrative example address
  from `infra/local.example.env` literally; those example values are already
  allowlisted in the `.example` file and `scripts/provision_vm.py`, and are not
  real addresses.

### Background, not urgent

- **Deferred by the user 2026-09-19: trigger import on each sample, not a 60s
  clock.** The 60s timer is correct (records carry their own `abs_tick`; import
  timing only affects freshness) but it lags up to a minute at 100 FPS and
  fires uselessly while paused. The better trigger is a systemd `.path` unit
  fired by the sampler's writes. Catch: a directory watch sees new files, not
  appends, and the file name changes per timeline, so the sampler would touch
  a fixed marker file (`.last_sample`) after each write. Keep the timer as a
  slow fallback. **Not** a DFHack-side hook: that would put external work back
  on the game loop.

- Two unguarded `items.other.*` access patterns (`trees.lua`'s
  `count_fort_owned_axes`, four in `stocks.lua`) **crash loudly** rather than
  silently zeroing. Loud failure is the acceptable end of that spectrum, so
  this is hardening, not a bug.
- The `PlantSeeds` measurement discrepancy: the queue drained 25 to 13 with no
  seed-stock change and no plants appearing, while the user reports the farm is
  genuinely being sown. That is a fault in **our reading**, not the fort.

## HANDOVER — archived

The 2026-09-12 session-end handover moved wholesale to
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
(file was past the ~400-line threshold). Its durable-traps list now lives
permanently at [`docs/TRAPS.md`](docs/TRAPS.md) — **read it there, and add new
traps there rather than here.** Current state is the section above.

## Archived

- Sections through 2026-09-10 (fifth handover) — provisioning build,
  perception eval, fort ledger, systemd units, title-screen bootstrap,
  live-viewing/relay/tunnel, the tileset investigation, Site Finder
  resolution, the embark-flow saga through both forts founded, and the
  seed-landmark bootstrap — all moved wholesale to
  [`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
  as each was superseded or reported itself finished.
- 2026-09-09: the 2026-09-08 (evening) handover moved wholesale to the
  same archive file.
- 2026-09-09 (end of session): this session's full handover (title-screen
  bootstrap resolution, the entire live-viewing/relay/tunnel build, the
  tileset investigation, and the Site Finder "Begin" resolution) moved
  wholesale to the same archive file — exceeded the ~400-line threshold,
  not superseded. The handover above is the tight current-state summary;
  the archive has the full detail.
- 2026-09-10: the 2026-09-09 (end of session) handover moved wholesale to
  the same archive file, superseded by this session's own handover above
  (Cloudflare Tunnel completion, the graphics-completeness fix, and the
  live embark-flow attempt).
- 2026-09-10 (second handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above (the click-registration mystery resolved, the real embark mechanism
  found, and the new "Confirm" crash).
- 2026-09-10 (third handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — **the first fort was founded**, and the "Confirm" crash resolved
  empirically via gdb.
- 2026-09-10 (fourth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — the `find_mm_*`/`warn_mm_*` coordinate-frame bug found, and
  `xdotool` real-input fix for headless map/hover interaction discovered
  and validated.
- 2026-09-10 (fifth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by the handover at the top
  of this file — the text-only sweep built and run, a Windows-specific SSH
  command-line truncation bug found and fixed in `provision_vm.ssh_guest`/
  `install_df.remote()`, and a strong second-site candidate found
  (`sx=128 sy=84 ex=131 ey=87`), left uncommitted for the user's call.
- 2026-09-10 (end of session): that handover's full continuation (the
  candidate embarked, Artobcatten's save lost as a result, the
  perception-layer branch split, the quorum-blocked snapshot worked
  around with a file backup, and Uniboslan's first room and stockpile dug)
  moved wholesale to the same archive file — exceeded the ~400-line
  threshold, not superseded by new work. The handover at the top of this
  file is the compacted current-state summary; the embark-screen-specific
  durable traps it used to carry were dropped rather than re-copied
  forward, since they're already the permanent living content of
  `docs/DF-UI-AUTOMATION.md`, not duplicated here.
- 2026-09-11: the 2026-09-11 VM-outage/quorum-incident writeup plus the
  entire 2026-09-10 end-of-session handover (VNC control channel, labor
  management/`autolabor`, the kea-combat finding, the quicksave root-cause,
  the perception-branch audit, both autonomous-play experiments, and the
  `find_diggable_area`/reachability corrections) moved wholesale to the
  same archive file — exceeded the ~400-line threshold by a wide margin,
  not superseded by new work. The handover at the top of this file is the
  compacted current-state summary, written deliberately thorough for a
  `/clear`; the archive has the full decision-by-decision detail.
- 2026-09-11 (documentation consistency pass): three fully-self-reporting
  ### threads moved wholesale to the same archive file: the compliance
  eval harness build (done for the session), mechanical prediction grading
  (built, selftested), and the full find_diggable_area/dig_diggable_area
  saga (built, live-verified, live-tested, the quickfort `-c` top-left-vs-
  center bug found and fixed, re-confirmed working end to end). None were
  gated on a human; item 10 in "What actually got built today" above now
  carries the compacted find_diggable_area/dig summary, and
  `decisions/DECISIONS.md`'s 2026-09-11 rows carry the full trail for all
  three.
- 2026-09-12: the entire 2026-09-11 end-of-session handover (the
  branch-merge question, the "what got built" list through item 12, and
  the peer-sessions/next-steps section) moved wholesale to the same
  archive file — the branch-merge question it spent most of its length on
  is resolved (merged, above), so it's fully superseded, not just over
  the line-count threshold. The handover at the top of this file is the
  new compacted current state.
- 2026-09-12 (session end, ahead of a `/clear`): this session's own content
  (the tool manifest build, both coordinate-leak fixes through deploy and
  live-verification, and the quorum correction) moved wholesale to the same
  archive file — it reports itself fully finished, nothing left gated on a
  human except the already-deferred design-commitment-#1 wording entry,
  carried forward unchanged. The handover at the top of this file is the
  fresh compacted current state, including two corrections the archived
  version's own text no longer reflects: both coordinate leaks are now
  fixed/deployed/verified (the archived text still frames them as open in
  a couple of places), and the driving-brain choice (`openclaw`) and
  live-view-ingest shelving are both folded in as settled state rather than
  same-session news.
- 2026-09-15: the whole 2026-09-12 to 09-14 section (the agent architecture design phase, the MCP server build and live smoke test, the durable deploy, openclaw install and first agent calls, both architect charter runs, the relative-LEVEL, isError and call-log fixes, and the dfqueue and live-signals builds) moved wholesale to
  [`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md).
  The file was 893 lines. Every still-open item was carried into the current-state section at the top.
- 2026-09-19: the whole HANDOVER 2026-09-17 section moved wholesale to the 2026-09-14 archive file. Its fort figures (tick 227008, "drink is solved") had been disproven by measurement and its stream list overtaken, but the fishing reversal, the stair background and the ground-truth idea live only there. Every still-open item was carried into HANDOVER 2026-09-19.
- 2026-09-17: the whole HANDOVER 2026-09-16 section (the production-gap discovery, the stocks/labor-race fix, the knowledge-scope audit, and the day-one farm-and-water work) moved wholesale to the same 2026-09-14 archive file, since the file exceeded the ~400-line threshold. Every still-open item was carried into HANDOVER 2026-09-17 at the top; nothing was summarised or dropped.
- 2026-09-21: the 2026-09-18 live-fort sections ("cannot drink") and the whole HANDOVER 2026-09-19 (rollback, walkability contradiction, the deploy and sampler updates, the old START HERE list and "Done today") moved wholesale to the 2026-09-14 archive file; the file was 586 lines. Open items were carried into HANDOVER 2026-09-21.
