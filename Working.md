# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## NEXT, as of 2026-10-09 (checkpoint 1; read first after a compact)

State: fort paused, operator hold ON, conductor.service disabled (hand-run `--once` only); every role on DeepSeek Flash (Pro is the rollback, backup `.bak-20261009-pre-flash`); cycles take 1 to 4 minutes. suspendmanager and autoslab on, ban-cooking re-applied, quicksave autosave 3 holds suspendmanager on (autoslab needs the next save).

**Done today** (register 2026-10-09 rows; `evals/live/2026-10-09-plan-v2-cycle/README.md`):
- Plan v2 adopted (`fort_plan-0002`, hamlet: bedrooms 1/alive, dining_tables 0.2/alive, dining_seats removed). Its `{min: 4}` floor was lost because the live `plan.write` predated commit ea12ff5 (want mappings).
- Shortage watch turned ON in `conductor/policy.yaml` (silent while the hold is on).
- Loop signals and DeepSeek list-rate costs live on the Board Metrics tab (506fdc0).
- Housekeeping merged: suspendmanager/autoslab gotcha seeds, blank-slab doctrine entry, Planner charter "copy stage targets verbatim", `circulation.graph`/`walk` on Architect (57) and Planner (15) allowlists, deploy target `vm103-dfhack-init` (not yet deployed, pending checks).
- User decisions: holds are briefing lines (3a); code may clean up only our own stale jobs/orders (3b); stock checks stateless (live stock minus margin, fail cleanly and retry, no claim ledger); scarce materials need no ruling (6); no live binding test (5); sessions on openclaw's Gateway now (7), inbox derived from conductor state (8), keep today's run limits 10/20 min (9, so no new loop guard).

**Remaining, in order:**
1. Deploy ea12ff5 (want mappings, in progress), then the Planner re-files `dining_tables` as `{per_alive: 0.2, min: 4}`; user reads the result.
2. Deploy `vm103-dfhack-init` (intended plugin enable set in `onMapLoad.init`) after its checks.
3. Build the stateless stock check (replaces the claim ledger; then `parallel.proposers` on, needs CONDUCTOR_THINKING_STATE_DIR, already set), sessions v1 on the Gateway with the derived inbox, effort per wake reason.
4. User decisions still open: 10, 11, 13, 14; whether the hold blocks the Overseer's direct writes; DFHack rulings (prioritize, work-now, timestream, pop-control); autofarm vs farm.setcrop. Idea under discussion: DF's auto-mine designation (follows revealed ore/gem veins) on our digs or as a prospecting pass, needing a watcher for hazard bands and reservations.
5. Supervised bedroom-block retrofit (user watching), tripwire live check, staged arm (user's yes on the day).

## START HERE 2026-10-08 (late): where we stopped

**Fort:** paused, operator hold ON (no expiry, no routed steps), conductor.service disabled. Manager unit 194 owns office 13; orders validate and run.
**Cycle 3** (first with charters): Planner woke on `roadmap_stage_entered` but TIMED OUT at 600 s (5 turns, 43.5k reasoning tokens, nothing filed); plan is still v1 (default). User said do NOT change the timeout yet. **CORRECTION:** the 'Pro rates confirmed against our bill' check was circular: $0.435/$0.87/$0.003625 are openclaw's hard-coded estimate table, which produces the logged `cost_usd`. DeepSeek's official pricing (peak/off-peak since 2026-08-16) lists Pro off-peak $0.66 miss / $0.022 hit / $1.98 out, double at peak, so the true bill is plausibly 2.2x to 4.4x the logged cost: **Settled 2026-10-08 by the user's DeepSeek console:** $8.19 total since 2026-09-09, 855 requests, 38.9M tokens; the 10/8 bar is about $2.50 against about $0.55 logged that day (console day boundary may not be NZ), so real cost is roughly 3-5x the logged `cost_usd`. A typical wake is about $0.14 off-peak / $0.27 peak, not $0.06; a 3-role cycle about $0.40-0.80. Owed: Metrics cost from DeepSeek's real peak/off-peak rates instead of openclaw's estimate table. Thinking budget research done (`research/2026-10-08-thinking-budget.md`): no token budget exists for V4; only `reasoning_effort` low|high|max (openclaw sends only off/high/max) and per-call `max_tokens`; `agent exec --thinking` per run; openclaw loop detection off by default; no max-turns or cost cap; 5 of 57 runs died at the 600 s wall with 40-45k reasoning tokens; no loops seen (max identical repeat 2); pinned configs name legacy `deepseek-v4-flash` (now routed to V4.1 Flash).
**In flight when the laptop closed (worktree branches; committed work survives, uncommitted may not):**
- attribution by author + `parallel.proposers` + paused-fort retry clock: ALL BUILT AND TESTED (4005 ambient / 1010 dfmcp) on branch worktree-agent-a43dcde47a8ae3cdd HEAD 93f1994, NOT merged or deployed. To land: merge main, push, deploy vm103-dfmcp (by_role in queue.overview) then vm106-conductor, check stamps. Deploying turns the paused retry on (900 s); `parallel.proposers` stays false and needs `CONDUCTOR_THINKING_STATE_DIR` (isolated state) or it runs serially; risk: DFHack pool of 4 may refuse filings as busy under three concurrent proposers;
- thinking-budget research (`research/2026-10-08-thinking-budget.md`): DeepSeek budget parameter, openclaw pass-through, loop guards, Flash vs Pro, per-wake-reason table and A/B plan;
- loop signals on the Metrics tab: BUILT on branch worktree-agent-a15440fc4feb9ab7f (2 wip commits), dfqueue tests 774 + JS 7 pass; owed: full ambient + dfmcp suites, merge main, push, deploy vm103-stream-publisher, relay-web, relay-web-operator. Today's live numbers: no identical-call loops; architect run-0040 had 3 idle rounds; two runs (planner 0039, architect 0037) timed out with nothing filed; reasoning about 37-45k tokens per run.
Check each branch, merge what is done, redeploy shared targets once from main (TRAPS: deploy race).
**Decisions walk-through 2026-10-09 (user paused it; resume at refinements 3a/3b):** answered: item binding 1 (exact items for buildings via counted pools, bound at execution), 2 (material class or specific material, broad by default; specialists via workshop worker list plus pinned orders, verify live incl. autolabor), 3 (foreign jobs named only), 4 (Overseer direct actions through claims, robust and no extra tokens); suspendmanager enabled. **Owed from the DFHack survey (2026-10-09):** quicksave DONE (autosave 3 holds suspendmanager on and the re-ban); decide `onMapLoad.init` under deploy; gotcha: suspendmanager releases deliberate suspensions; rulings on prioritize/work-now/timestream/pop-control; autoslab (recommended now); autofarm vs farm.setcrop. Still open: 3a, 3b, item binding 5-6, sessions 7-11, Planner timeout 12 (Flash fixed it in practice: planner ran in 141 s), thinking/cost 13-15, and whether the hold blocks the Overseer's direct writes. The user asked for fuller explanations per decision. Plan v2: server adopt bug fixed (null stamp); proposal-0034 (plan_change) pending; next cycle settles it.
**User decisions open (older list):** (1) item binding 1-6 (recommended: buildings exact items yes; workshop jobs option A materials only; foreign jobs name only; route consuming Overseer direct actions through claims; live tests only T1 on the live fort; economic/scarce material only when ruled); (2) sessions D1-D5 as listed (local route first; reuse backoff; one budget per role per wake with per-turn waits; pause stamp on tool replies while paused; Opus blind grader, user reviews disagreements plus a capped sample); (3) Planner timeout or tighter task; (4) thinking budget and Flash/Pro per wake reason once the research lands.
**Queued research (user, 2026-10-08, last message):** would this project benefit from decision models? The user meant openclaw's `decisionModel` role (docs page "Decision models": typed choice/score/boolean answers from small classifiers, local ONNX or hosted TypeSafe Jev; added after openclaw 2026.9.5, plugins unpublished; our install is about v2026.9.4). Orchestrator's first view: not now; possible later for fuzzy text triage (picking a thinking-budget level per wake, flagging stale beliefs in rationales, announcement urgency). Separately, deterministic DMN-style decision tables may suit our existing rule data. Candidates: Overseer fast-paths for routine items, model/thinking-budget/timeout per wake reason, and today's scattered rule data (aquifer policy, access rules, thresholds, backoffs) in one testable, auditable form recording which rule fired.
**Queued (user asked 2026-10-08: train models on the DF wiki?):** orchestrator's view: no LLM fine-tune (facts stick poorly, version-mixed and stale, retrieval with revision citations already exists); embedding search over the mirror: user says probably not; a small classifier only later, for a narrow task, labelled from our own runs. Confirm the wiki's licence (believed GFDL and/or CC BY-SA) before any training.
**Next after that:** cycle 4 (Planner adopts hamlet as v2; user reads it; then shortage watch on), sessions v1 (red team's small version), circulation C2/C4/D12 retrofit (supervised), tripwire live check, staged arm.

## Sessions: decided 2026-10-08 (register), design in progress

(Was: owed with the user.) Built per the 2026-10-08 register row. 2026-10-09 decisions 7 (openclaw Gateway now), 8 (inbox derived from conductor state), 9 (keep 10/20 min limits) are in the register.

Do not decide alone. Inputs ready: `research/2026-10-07-session-inbox-options.md`, `research/2026-10-07-openclaw-source-sessions.md`, `evals/live/2026-10-07-openclaw-multiturn/README.md`, `evals/live/2026-10-07-cache-miss-cause/README.md`, `research/2026-10-07-persistent-sessions.md`, `research/2026-10-07-wake-audit.md`. Depending on it: the own-filings briefing block (left on as a trial), Overseer items one-at-a-time vs grouped, where "the fort is paused" goes (briefing line, tool-reply stamp, pushed message).

## START HERE: current state, 2026-10-07 (evening, NZ)

**Fort:** Uniboslan, paused, 24 alive (2 births in a 46-day supervised run today), hunger and thirst fine, tripwire armed on defaults. Operator hold set earlier today (expired or near expiry; check `/tmp/hold.sh show` on VM 106). `conductor.service` disabled and inactive: cycles are hand-run `--once` only. DRINK 0 (well covers water), BED 0 with one planned Bed waiting, BARREL 27.

**Live and deployed today** (register rows dated 2026-10-07 have each decision):
- Rooms routed (deploy 2b): the conductor executes accepted room steps; Overseer 82 tools. Urgency set by the Overseer in its ruling (high only for survival).
- Ore mining routed (`mine-vein-site`, a site mines its own reserved walls). Shore Water Source/Fishing zones (finder offers ground beside water, incl. above a sunken pool). Ask addressing (`to` on asks). Stockpile tool gaps (links-only, containers, materials, health, plan-feed, remove; field paths verified live, writes unverified, on no allowlist).
- P0 bedroom alert (Architect). Unsupplied-building watch (Quartermaster). Wake cleanup safety items (deferred proposals no longer re-wake the Overseer, dead wakes removed, backoff in wakes with stalled after 3, grades wake the proposer, answer wake built but off).
- Planner P1a and P1b deployed DARK: the role exists, its enable commit `2b8c315` is NOT deployed; token and pinned openclaw config not issued. User reads plan v1 before shortfall wakes go on.
- Transcripts captured per run and public on the Board (Transcript tab, loaded on demand); full proposals collapsed in threads; Metrics tab (`dfqueue/wake_metrics.py`, baseline `evals/live/2026-10-07-wake-baseline/`); awake strip stacks per role.
- Own filings: `queue.my_filings` for proposers, and a "your recent filings" briefing block ON AS A TRIAL (switch: `own_filings.recent: 0` in conductor/policy.yaml); whether it stays depends on the session design.
- Orders tool issues valid orders (material defaults from DFHack's order library; `invalid_material` flag). **Live repair done:** cancelled invalid orders 0, 1, 3, 4; created 5 blocks (rock), 6 mechanisms (rock), 7 throne (rock), 8 barrels daily while under 20 (wood); kept 2 (brew x13, user set 13). New orders not yet validated: needs running time to see whether the manager validates them (`evals/live/2026-10-07-manager-orders/README.md`; **corrected 2026-10-08: the user has watched the manager validate orders**, the "never organised" reading was an inference and wrong; the user's reading is that orders were validated but broken; follow-up research `research/2026-10-08-validated-orders-never-run.md`). gotcha-0002 ("manager route stuck") is suspect: correct it once orders are seen to run.

**User's in-game changes, 2026-10-08 (fort unpaused by the user, who is watching the work orders):** appointed a new manager (replacing unit 345), assigned the office to the new manager, and deleted the old work orders (which ones exactly: read `orders.list` once SSH is back). The manager's Study icon was green before the change. **Result: the "must assign a manager for work orders" message is gone. Root cause: our `nobles.appoint` wrote an appointment the game did not accept** (register 2026-10-08). Owed once SSH is back: read-only diff of the game-made appointment vs our tool's writes, then fix or withdraw `nobles.appoint`/`unappoint` (Overseer allowlist), correct gotcha-0002, update records of who the manager is. Planner enable is merged and pushed (`de339e7`, Planner 13 tools, conductor 38); deploys, token, pinned config and the first `--once` cycle wait on Tailscale.

**In flight:** nothing. Filing hygiene and all-wake-reasons are deployed (Phase 0 below) (`handoffs/2026-10-07-filing-hygiene.md`): a proposal repeating an open action (type, step tool, identifying args from `dfqueue/step_identity.yaml`) is refused naming the original, any role; follow-ups exempt; `queue.my_filings asks=true` shows a role's own asks and answer text; the `answer_ready` wake is ON for architect, quartermaster, planner; bedroom alert shows two decimals. Live check after deploy: re-filing an open action is refused; an answered ask shows its text. Then the tripwire live check.

**Designed, not built:** Planner revision 2 (`research/2026-10-07-planner-design.md`, red team done; P2+ later), Logistics role (in that design, stage L), notebook (deferred: metrics then own filings first; `research/2026-10-07-notebook-*.md`), fort dossier and crafting search (`research/2026-10-07-fort-dossier-and-crafting-search.md`; red team `research/2026-10-07-fort-dossier-red-team.md`: direction holds, NOT ready to build. Blockers: DFHack's job table covers only 16 of 33 workshop kinds so the crafting graph cannot be completed from it; landmark reads lack ids, exists flag and level difference, so relations cannot key on handles. Its simpler first path: D0 restated plus a Quartermaster-only in-memory block, tested by paired runs on the same paused fort state into a scratch queue. Its user questions are held for the user).

**Plan of attack for the next session** (written 2026-10-07 for the next orchestrator session and the user; each phase lists its gate, so do them in order and stop at a gate that fails):

*Phase 0, land what is built: DONE 2026-10-07.* All-wake-reasons and filing hygiene merged and deployed to every target, drift-clean (after an SSH outage: Tailscale subnet route acceptance had been switched off on the workstation; turned back on with `tailscale set --accept-routes=true`). Live checks passed: a reworded duplicate of proposal-0024 is refused naming the original (tested on a copy of the live queue); `queue.my_filings asks=true` shows the Architect's four asks and the Consultant's "I cannot read proposals" answers. INDEX and register caught up for every 2026-10-07 stream.

*Phase 1, prove the fort works when running (gate for everything after).*
4. **Tripwire live check** (user said go ahead without watching): `handoffs/2026-10-06-stage-t-tripwire.md` Result, "Live check", steps 1 to 6. Clear the operator hold first (step 3 needs no hold), restore normal thresholds and pause at the end, re-set the hold. Record in `evals/live/<date>-tripwire-live/`.
5. **Did the new manager orders run?** During step 4's resumed time, or a bounded supervised window, read orders 5 to 8: validated? jobs at the Mason's/Mechanic's workshops? blocks/mechanisms/throne made? If yes: correct gotcha-0002 and tell agents standing orders work. If they are validated but make nothing: that is the "validated but broken" shape the user saw on the old orders; use the 2026-10-08 research's cheapest tests. The user wants manager orders fixed before the conductor is armed and left alone. Barrels will not run (27 on hand, order runs below 20).
6. **Bed and drink:** once orders run, the Quartermaster should set standing buffer orders (bed while fewer than 2; drink). If not, check the unsupplied-building wake fired and why the ruling deferred.

*Phase 2, arm the conductor (needs the user's yes at the time).*
7. Staged arm: `conductor.service` enabled with the operator hold ON (agents cycle, nothing executes), watch an hour on the Board Metrics tab (wakes per role, cost per wake, repeat defers, duplicates, rounds). Then lift the hold. Never enable without the user confirming that day.

*Phase 3, supervised firsts (user present or explicitly cleared).*
8. Supervised bedroom end to end: site-4 finish is accepted (proposal-0024; the duplicate 0026 also accepted: close one before executing).
9. Planner bootstrap: issue `MCP_ROLE_TOKEN_PLANNER` (rotation row), pinned openclaw config with exactly the 12 tools, deploy enable commit `2b8c315`, one cycle, user reads plan v1 on the Board, then set `plan.shortfall_watch.enabled: true`.
10. Stockpile write verbs on a throwaway pile (`handoffs/2026-10-07-stockpile-tool-gaps.md` Result plan), before any Logistics work.

*Phase 4, design sessions WITH the user (do not decide alone).*
11. Inbox and session design (section below): the evidence is in; candidate is inbox-as-data plus one Gateway session per role, items pushed one at a time, `/new` between wakes. Settles: own-filings block, Overseer one-at-a-time vs grouped, where "the fort is paused" goes.
12. Fort dossier and crafting search: work through the red team (`research/2026-10-07-fort-dossier-red-team.md`) and its simpler first path; three user questions listed below.

*Phase 5, evidence-driven trims (after about a week of transcripts).*
13. Rerun `python -m dfqueue.wake_metrics` against live copies; compare to `evals/live/2026-10-07-wake-baseline/`. Cut each role's tools to what it called (user: cut hard), Architect and Overseer first.

**Manager orders PROVEN 2026-10-08** (`evals/live/2026-10-08-manager-appointment/`): fixed `nobles.appoint` deployed; the Overseer appointed a manager unaided; orders validate, run and finish once the manager owns an office. MANAGER is now unit 194 (the Overseer's pick), office zone 13 owned by 194; 347 is expedition leader only. Owed: a user decision on who may assign an office owner (`zone.assign-owner` is on no allowlist); `plan.read` fails live (FileNotFoundError for the plans file under the dfmcp install: fix before the Planner bootstrap); `labor.unit-status` idle filter returns non-JSON; correct gotcha-0002.

**Design streams 2026-10-08 (user decisions owed, walk them one at a time):** circulation design `research/2026-10-08-architect-circulation-design.md` + red team `...-circulation-red-team.md` (build after fixes: 4 blockers, cuts; D1-D13 with red-team changes); roadmap role design `research/2026-10-08-roadmap-role-design.md` (the Elder; 10 decisions), red team running. Plan v2 waits for the roadmap (recommended, not yet confirmed by the user). **Aquifer/magma siting policy DEPLOYED** (cdcbc02, drift-clean): `df-overseer-hazard.lua` (policy data; hidden tiles never read, unknown refused only near a revealed hazard band), wired into diggable finders/digs/stairs, blueprint preview/apply/reserve, mine-vein; `df-overseer-digcancel.lua` classifies DIG_CANCEL_DAMP/WARM as `cancelled_by_game`, conductor never retries. Live: zero revealed aquifer tiles on the map, zero cancel reports, so the policy excludes nothing today; live-check owed when a dig first exposes damp stone. **Noble-room watch DEPLOYED** (d53693b, drift-clean, conductor 40 tools): an unmet noble room requirement (status `not_met`, holder owns no zone of that kind) wakes the Architect (`noble_room_unmet`), which joins its own project as a follow-up `zone.assign-owner` step after the zone-creating step, or files a one-step `room_siting` proposal; never OVERRIDE; duplicate refusal now covers assign-owner follow-ups. Dormant today (manager 194 owns office 13); the firing path is proven only by fakes. Overseer allowlist unchanged (82). circulation graph read C1 DONE and deployed (`circulation.graph`/`circulation.walk`, on no allowlist; live 0.1 s over 853 tiles; flags the user's bedroom problem: sites 4, 5, 6 reached through Bedroom #24, rooms open onto each other; no Dining Hall exists, so no dining walks; Office #13 is a separate piece in the window). All user decisions of 2026-10-08 recorded (register). **Circulation hands B2/B3 DEPLOYED** (61002b7): tile-set reservations with a `portal` class (one room plus one corridor may share a portal), multi-level blueprints refused everywhere, generated blueprints registered as `gen-` names and applied through `quickfort.apply_blueprint` data with every existing check (live preview matched the CSV route; one scratch `gen-livecheck-a` left in persistent state, auto-pruned). Orchestrator calls on its forks: generators emit each orientation themselves (the data API has no transform; the finder asks the generator for all four); `blueprint.generate` stays unallowlisted (it writes only the verb's scratch registry), reclassify if a role ever needs it. Owed small: `df-overseer-circulation.lua` should read reservations via `reservations.tiles_of`; reservations header still describes the old wall-only rule. **Room kinds and access gate DEPLOYED** (738e0c0, dfhack-scripts only; vm103-dfmcp picks up `dfqueue/room_kinds.py` on its next deploy): `blueprints/room-kinds.yaml` (13 kinds, rendered to `df-overseer-roomkinds.lua`), circulation reads tile-set reservations, and a code gate (entrance-cell check, not planned-state search) refuses a new room whose entrance opens into a private room or breaks its kind's access rule (D7, D2; D13: the user's bedroom catch is now a check). Live: per-orientation refusals seen, resolver picks a clean orientation. Offices are private by the data, so the graph now also reports Offices #10 and #11 opening onto each other (report only).

**Charters now reach the agents (2026-10-08, register):** `/app/SOUL.md` bind-mounted read-only; a role with no charter refuses to run. Verified live on the Consultant only (reply `# Consultant`, prompt shows the charter); spot-check the other four in the next cycle's retained prompts. First run per role after this is a cache miss. Pause line in every briefing and own-filings block off (08a824a). Season-review settle fixed (b0eb72c). All redeployed together from main 3486589 after a deploy race (TRAPS). Sessions: design + red team done (build the small version: local route, derived items, escalation per turn); five user decisions open.

**Roadmap stage wake fixed twice 2026-10-08** (3c9623b): first cycle owed nothing (first observation taken as baseline); second cycle recorded a phantom Planner pass because `last_reviewed_tick` = max(pass tick, plan filing tick) and the paused fort sat at the plan's own tick. Now only an explicit `queue.pass` tick (`last_pass_tick` in plan.status) settles a roadmap debt. **Owed:** the season-review settle in `conductor/plan_watch.py` reads `last_reviewed_tick` the same way (same phantom-pass flaw on a paused fort). Cycles 1 and 2 cost $0.21 and $0.11 (architect, quartermaster, overseer at $0.05-0.07 per wake, 5-10 min each).

**Roadmap V1 DEPLOYED** (c895488/9000f2d): `fort_roadmap/seed-v1.yaml` (founding/hamlet 20/village 50, targets only), validator, stage from alive with a high-water mark in `<fort db>.roadmap-stage.json` (persisted only by `plan.status`), cross-checked against the game's population flags; `plans/default-v1.yaml` retired; Planner comply-or-explain (`roadmap_ref`, `unexplained_deviation` flag), adopt-only revisions skip the season rule, `roadmap_stage_entered` wake; one ROADMAP line in the Overseer briefing; utilisation (Sleep/Eat/Drink per alive) appended per cycle to `utilisation.jsonl` in the conductor state dir. `screen.read` on the Overseer (83 tools; a live bug, missing `require('json')`, hidden by the test stub, found and fixed). Conductor 41 tools. First hold-on cycle to adopt hamlet as plan v2: run 2026-10-08 by the orchestrator. Next after those: C0 access data (`opens_onto` per kind), C2 graph tools on Architect and Planner allowlists, then D12 retrofit of the bedroom block (supervised).

**Planner live 2026-10-08:** token, pinned config, 13 tools, all targets deployed drift-clean (a0fbe5c; dfhack-scripts redeployed by the orchestrator, so `screen.read` and labor JSON are live). One `--once` cycle ran before the hold-the-cycle message arrived (operator hold was set, nothing executed, fort paused): the Planner filed plan v1 (`fort_plan-0001`) = the unmodified default (bedrooms, dining_seats), no reason, round count not captured. v2 with the structured want shape needs the season rule: next season, or a `plan_change` ruling. plan.read fixed (deploy manifest now ships `plans/`). gotcha-0002 revised live (backup `.bak-20261008` in the gotchas dir). Operator hold set, no expiry.

**Merged 2026-10-08, deployed the same day:** `labor.unit-status` returns JSON; gotcha-0002 corrected text in `gotchas/revisions/gotcha-0002.body.txt` plus a maintainer `revise` CLI (run on VM 103 against the live gotchas DB after deploy, or the live entry stays wrong); policy-args test; `screen.read` (on no allowlist) and resume now names a blocking panel (alert, report only). Live check owed after deploy, with the user watching: open Work Orders, `screen.read` with text, supervised resume shows `blocking_panel`. User questions queued: want shape `{per_alive, plus, min, max}`; who gets `zone.assign-owner`; who gets `screen.read`; may the conductor ever close a panel.

**Lesson 2026-10-08:** an open Work Orders panel (and possibly other info panels) blocks a scripted resume: `supervised-unpause.sh` called resume, the game stayed paused, the script stopped on its stuck-viewscreen rule (user confirmed the panel was the cause). Before arming the conductor, check its resume path handles or reports an open panel. **Standing lessons from today:** agents cannot tell a paused fort from a broken one (fix belongs in the session design); argument names in policy must match the tool schema (a test for this is owed); the deploy tool's Lua target reports drift once when a tool list changes until vm103-dfmcp deploys (ordering effect, harmless); deploys change the tool list and invalidate the prompt cache, so batch them.

**Owed with the user (do not decide alone):** the inbox and session design (section below); fort dossier questions: (1) may Chronicler notes reach deciding agents (designer and red team: no for now); (2) how push vs pull is decided per role (red team: paired runs on a paused fort, not epochs); (3) retire `stockpile.health`/`plan-feed` into one `logistics.gaps` (designer: yes); plus the red team's simpler first path. Also: whether to watch the first order-validation run (orders 5 to 8).

## Open: rotate leaked keys (2026-09-17)

A session ran `cat .env | grep -v SECRET` while looking up the VM 103 SSH
user, breaking the "read secrets by the key you need" rule — it printed
`ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`, and
`CLOUDFLARE_TUNNEL_TOKEN_ADMIN` into the session transcript in full. User's
call: rotate later, not urgent, but don't lose the item. → decisions/DECISIONS.md
2026-09-17.

**The full list now lives in `infra/local.secrets-rotation.md`** (gitignored,
key names only: why, when, where each lives; user's ask 2026-10-05). Add a row
there the moment any secret is exposed. Newest: the admin tunnel token,
exposed again 2026-10-05 via the relay unit that carries it inline.

## Archived

- 2026-10-09: the 2026-09-28 "Current state" and 2026-09-30 handover sections (superseded) moved wholesale to
  [`working-archive/Working_archive-2026-10-05.md`](working-archive/Working_archive-2026-10-05.md).

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
- 2026-09-24: everything from "In design: the agent loop MVP" through "HANDOVER — archived" (the agent-loop MVP design phase and its later additions, the learning-loop discussion, the 2026-09-23 loop-closed handover and its streams, and the 2026-09-21 handover) moved wholesale to [`working-archive/Working_archive-2026-09-24.md`](working-archive/Working_archive-2026-09-24.md); the file was 1091 lines. None of the moved content was still-open work. Everything still open (the office, the ghost, the wiki mirror, deploy backlog, ore, design thoughts) is in the current-state section at the top, freshly written rather than carried forward line by line, since almost none of the old text was still accurate.
- 2026-09-25: the whole "Current state, 2026-09-24 evening" section moved wholesale to [`working-archive/Working_archive-2026-09-25.md`](working-archive/Working_archive-2026-09-25.md): the office, the ghost, and the manager-order question report themselves finished or set aside, and the wiki mirror and districting items are directly superseded by the same day's and 2026-09-25's own later work (the switch-over rollback and reader deploy, the districting prior-art pass completing). Everything still open is in the current-state section at the top, freshly written.
- 2026-09-28: most of the "Current state, 2026-09-25" section moved wholesale to [`working-archive/Working_archive-2026-09-28.md`](working-archive/Working_archive-2026-09-28.md) (the wiki mirror switch-over/reader deploy, the districting prior-art completing, the full conductor redeploy and five-cycle first-real-run narrative through 2026-09-28, the drift audit, and the well/tripwire live-verification): it reported itself finished or superseded throughout, and `decisions/DECISIONS.md` gained matching 2026-09-25/28 rows that had been missing. Everything still open is carried forward in the current-state section at the top, freshly written and tightened per the archive-cadence rule (the old section had grown into one dense paragraph).
