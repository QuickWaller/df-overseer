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

## In discussion: designing the learning loop (2026-09-17)

**Not designed yet, by the user's own assessment.** No code; do not start
building from this section. The design is being settled one question at a time
with the user.

**Agreed so far** (→ `decisions/DECISIONS.md` 2026-09-17):
- Doctrine sources carry per-source provenance; `verified` needs a 53.16 live
  or game-data source; a pytest validator enforces it (built).
- `get_doctrine`, read-only, with a topic index (agreed, not built).
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
reader or revision type, no chronicle, no ledger rows and no scheduler.

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

## In flight: production model designed, audited, and four streams dispatched (2026-09-18)

**Design is settled on paper and nothing is built.** Six register rows dated
2026-09-18 carry the decisions; the diagrams are in an artifact (URL in the
session, not committed). Read `research/2026-09-18-production-graph.md` for
the formalism and `research/2026-09-18-production-figures.md` for the figures
before touching any of it.

**The short version:** a directed hypergraph in plain SQLite, **seven** tables
(`production_node`, `_class`, `material_reaction_product`, `_process`,
`_flow`, `_attribute`, `_observation`). A node is an item type crossed with a
material; processes consume classes and produce specifics, so routes are
generated rather than authored, and the join table plus a two-pass extraction
exist because 42% of product lines inherit their material at job time.
**Four** consumption semantics (consumed, occupied for the job, occupied until
released, modified in place), because a barrel is freed by drinking rather
than by brewing, and the glaze reactions have no product row at all. The
static graph is placeless: move, install and trade are all generated at query
time. Material policy is banded and lives in **doctrine**, not in the graph,
which is what removes the need for a solver cost vector.

**The rule that governs all of it:** four quadrants, and quadrant 4
(happiness effects, interruption behaviour, time lost to needs) never enters a
formula, only appears as an unattributed residual. Demand is exact, supply
capacity is not, so every question is posed from the demand side.

**Both feasibility audits are in** (`research/2026-09-18-schema-extraction-
static.md`, `-live.md`) and the spec is corrected from them. Headlines: node
identity needed a material join table and a two-pass extraction because 42% of
product lines inherit their material; `consumption` needed a fourth value;
the observation key had to become an absolute tick because
`ReadCurrentTick()` resets annually. Nine of twelve live facts are exactly
readable, job claims are a plain flag, and cancellation announcements turned
out to be a lossy hint rather than a shortcut.

**Four build streams dispatched 2026-09-18**, no two sharing a file:
- **Doctrine** — **DONE and merged.** Six `prior` entries, new `material`
  topic, 307 passed / 1 skipped.
- **Lever-gap tools** — `orders.create` learns a `bucket` job and friends;
  new `stockpile list`/`links`. Deploys to VM 103, dry runs only.
- **`production/` package** — seven tables, two-pass extraction, offline.
- **Doc drift pass** — seven new traps from the audits, plus `ROADMAP.md`,
  `AGENT-ARCHITECTURE.md`, `MEMORY-ARCHITECTURE.md`, `CLAUDE.md` status.

### Live fort state, read-only, 2026-09-18 at tick 227160 (paused)

Read directly this session. **This corrects two claims I made earlier today.**

- **The fort owns three usable buckets** (ids 81, 149, 150: empty,
  unforbidden, unclaimed, no holder). Two more are `trader=true`, held by the
  caravan's yak pack animals. There is no bucket shortage.
- **Nobody is injured.** The "1 of 15 unconscious" from the live audit is a
  **sleeping miner**: `pain=0`, `wounds=0`, `current_job=Sleep`.
- **Fort-owned stock**: logs 3, seeds 60, **drink 0, prepared meals 0**, raw
  plants 8, boulders 0. Food is 8 raw plants for 15 citizens.
- **Thirst** is staggered across three bands, worst 23,391 against a roughly
  three-week (~25,200 tick) drink interval, consistent with the `WaterSource`
  zone working. Not in danger.
- **Farm plot 4 exists**, plump helmet set for all four seasons, and **25
  `PlantSeeds` jobs are queued**, 2 claimed. Claim state is uninformative:
  the fort has run 151 ticks since they appeared.
- **The still (workshop 5) is still `exists=false`** with its
  `ConstructBuilding` job 366 **suspended**, and the fort owns 3 logs.
- `autolabor` is **enabled**, so labour counts (PLANT 2, BREWER 1, COOK 1,
  CARPENTER 1, DIAGNOSE 1, `FEED_WATER_WOUNDED` 0) are its live allocation,
  not a configuration. Hand-setting a labour takes it off autolabor fort-wide
  and permanently, so that lever is contested. → `docs/PRODUCTION-MODEL.md`
  §13.
- **`growdur` for plump helmet is 300** and live `grow_counter` values are in
  the tens of thousands, so they are not the same unit and **the harvest clock
  is not computable until the unit is settled**. One observation of a planted
  crop settles it.

**Parked by the user, deliberately:** trade (a transient hyperedge inserted
when a caravan is present, so it needs nothing now); rooms and
room-dependent furniture requirements; per-stockpile sites (coarse areas
first); the solver itself, pending a sensitivity check that may show we never
needed it; the mixed-integer question (build a rail line or not), which is
the only thing the missing haul-tier figures block.

**The uncomfortable gap:** nothing in this design executes anything. Work
orders carry standing conditions, so the keep-on-hand band is expressible in
DF's own mechanism today, but the rest has no hands. `proposal-0001` was
accepted and never executed; better diagnosis on an unexecuted loop widens
that gap rather than closing it.

**Next concrete step:** read both research reports when they land, fix the
schema on paper where they say it cannot be populated, then decide whether
extraction is worth building before execution exists.

## Current state, 2026-09-15: archived

Moved wholesale to [`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md) on 2026-09-18, superseded by
HANDOVER 2026-09-17 and the production-model work above.

## HANDOVER 2026-09-17 (read this first after a /clear)

**The 2026-09-16 handover (the production-gap discovery, the stocks/labor-race
fix, the knowledge-scope audit, and the start of the farm-and-water work)
moved wholesale to
[`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md).**
Everything below is today's outcome and what's still open.

**Uniboslan drinks and grows food for the first time.** Paused, tick
**227008**, year 30, 15 citizens, no deaths, `dwarfmode/Default` focus (no
dialog up), the last state every stream today independently re-verified
live before touching anything. Nothing is running right now.

- **Drink is solved, in practice.** Every pond is a sunken basin of 6-7/7
  water at z168 with nowhere dry to stand at the water's own level, which is
  why nobody drank unaided (`research/2026-09-17-founders-not-drinking.md`).
  A `WaterSource` zone placed **on the water itself** at z168 (Activity Zone
  #1, still in place) fixed it: one supervised 10 FPS unpause got three
  founders down to z168 and self-serving water (thirst near zero; 197 with no
  caretaker at all, the project's first confirmed self-serve drink), and three
  more picked up a fresh `NastyWater` thought right at the end of the same
  window. **Not proven as the sole cause** (no zoneless control ran), but
  decisive enough that the zone stays. Two open risks: dwarves stand in 6-7/7
  water (deep enough to drown a poor swimmer), and the water is stagnant
  (health effect of the `NastyWater` thought unverified). A well removes both
  and is no longer urgent. → `decisions/DECISIONS.md` 2026-09-17 rows,
  `research/2026-09-17-water-source-zone-test.md`.
  **Correction folded in:** an earlier same-day research pass
  (`research/2026-09-17-pool-reachability.md`) concluded `getWalkableGroup`
  was broken around ramps; its own top-of-file correction note (verified live
  before that doc was committed) found this was wrong: the ramps really are
  underwater, not miscategorised. Read the correction note, not the body, if
  citing that doc.
- **First real food production: the farm plot is built and its crop set.** A 5x5
  `building_farmplotst` at z168 (x100-104, y101-105), `flags.exists=true`,
  all four seasons carry plump helmet (`plant_id=173`), orchestrator-verified
  by direct struct read. **The still is not built.** It is designated at the
  surface (z169, x96-98, y97-99; no free 3x3 floor exists underground once
  the farm plot took the only one). **Material is genuinely thin, not
  clearly ruled out as the blocker**: the build stream's own live read
  claimed 15 wood / 3 boulders / 4 blocks free, but the register's own
  correction (checking `flags.trader`) found the 3 boulders, 4 blocks and 12
  of that wood belong to the caravan, not the fort. Uniboslan actually owns
  **3 logs and nothing else** buildable, which the still's one-generic-item
  requirement can still be met from, but there is no real cushion. Its
  `ConstructBuilding` job (id 366) never got a worker across a full 453s
  unpause (30 samples, every idle citizen instead cycled through
  Drink/Eat/Sleep). `decisions/DECISIONS.md` frames this as the job "reading
  suspended"; the execution stream's own live read only confirms
  "unassigned, never picked up," not a suspend flag specifically; worth
  checking directly before assuming which it is.
  → `research/2026-09-17-farm-still-first-build.md` (handoff Result),
  `decisions/DECISIONS.md` 2026-09-17.
- **Water and industry tools shipped: zones, tree felling, work orders, a
  well builder, and three more workshop kinds.** New: `zone.find/place`,
  `trees.find/fell`, `well.find/build`, `orders.list/create/cancel`;
  `workshop.find/build` extended with mason/mechanic/carpenter plus a
  `building_material` field (verified live: all five workshop kinds accept
  boulder, wood or block interchangeably). Deployed and live-verified
  (hashes, restart, dry runs, and direct proof the new code is running, not a
  stale `reqscript` cache). **Role tool lists: architect 19, overseer 32,
  consultant 4** (up from 13/18/4 this morning). No citizen holds the
  Manager position, so `orders.create`'s effect on a queued order with no
  manager appointed is reported but not enforced, untested against a real
  unpause.
  → `handoffs/2026-09-17-water-and-industry-tools.md`,
  `handoffs/2026-09-17-water-industry-tools-deploy.md`.
- **Seed economics researched; game knowledge now lives in `doctrine/`, not
  here.** Brewing, quarry-bush-bagging and pig-tail papermaking are
  raw-confirmed 100%-guaranteed 1-seed-per-plant returns; cooking returns
  zero, confirmed two ways. Break-even: at least `1/Y` of a harvest (Y =
  plants per tile) must go through a guaranteed-return method, so an
  unskilled, unfertilized farm can cook nothing yet. Figures table ready for
  the game-figures database `ROADMAP.md` now tracks as a Next item.
  `doctrine/seed.yaml` and `docs/TRAPS.md` were both already updated today by
  the streams that found the facts; nothing in this pass contradicted either,
  so neither was touched further.
  → `research/2026-09-17-seed-ratios.md`, `doctrine/seed.yaml`.
- **Stocks tonight** (live-read during the farm-still build, the most recent
  figures anyone has): fort-owned food (raw_edibles) **17 units** (item_count
  4, down from 20 this morning, ordinary consumption from Eat jobs during the
  unpause, nothing deliberate); drink still **0**; prepared_meals **0**;
  seeds **60 total, 35 plump helmet** (the register's own count, one higher
  than the 59/34 an earlier reading gave, not chased).

### START HERE, in priority order

**Authority note, 2026-09-18:** the user granted this session full authority
to push, to change the VM and to act on the fort, explicitly asking not to be
asked per action. Standing exception kept: genuinely unrecoverable loss (the
fort save, the VM itself) still stops and reports. Everything below that was
previously "needs the user's go-ahead" is now simply sequenced work.

**Sequencing rule while streams are live:** only one stream touches VM 103 or
the fort at a time. Two `production/**` streams are also mutually exclusive.

0. **Wait for the lever-gap tools stream, then deploy once.** Deploying from
   `main` carries the merged `dig-stair` fix along with the new tools, so
   there is no reason to deploy twice. Reconcile the `ROADMAP.md` /
   `CLAUDE.md` tool-count mismatch (19/32/4 vs 21/34/4) with the real post-
   deploy numbers at the same time; the doc drift pass deliberately left it
   alone because the counts were another stream's surface.
1. **Then the supervised run**, which is written and waiting:
   `handoffs/2026-09-18-supervised-run-and-measure.md`. Feeds the fort (25
   `PlantSeeds` jobs cannot run while paused, and food is down to 8 raw plants
   for 15 citizens) and settles four known unknowns in one go, including the
   `growdur` unit that currently blocks the harvest clock. Unsuspend the
   still's job 366 as part of it: **the suspension question is answered**, it
   is genuinely DF's `suspend` flag (`susp=true`, verified live today), not an
   unassigned job.
2. **`ban-cooking all`: DONE 2026-09-18.** Kitchen exclusions went 110 to
   1279 (1169 types banned), fort paused at tick 227160 before and after.
   First enforcement `seed-stock-never-falls` has ever had. Note for the
   record: 110 exclusions already existed before today and nobody had
   recorded why.
3. **The stair, after the run.** Remove the orphan z167 UpStair designation,
   then designate the new rank-1 spot for real and dig it. The code fix is
   merged and rides along with the deploy in item 0.
4. **Queued and gated, in `handoffs/`:** the days-of-cover calculator and the
   blocker walk, both waiting on the `production/` package stream and
   mutually exclusive with each other.

**Background on the stair, for whoever picks item 3 up.** Farm and stair
tools were deployed and live-tested 2026-09-17, tool lists live at 21/34/4,
and `farm.set-crop`'s real write and restore on plot 4 worked, read back
through `farm.list`. **The stair did not.** `dig-stair` returned ok for both
halves, but its rank-1 spot sat under the fort's Stockpile and quickfort
silently skips occupied tiles, so z167 holds an orphan UpStair with no
DownStair above it (verified live, tick 227160, paused). The fix, merged
2026-09-17 and not yet deployed, ranks out candidates with a building on
either tile (verified live: the Stockpile tile no longer ranks first), judges
success by reading the designation back, designates the upper half first and
undoes it if the lower fails, and turns failures into real errors rather than
an ok. → `handoffs/2026-09-17-dig-stair-fix.md` Result.

**Fishing research: done 2026-09-17, and its first conclusions reversed.**
A same-day audit found that the "overfishing may not be a real risk" swing
rested on a wiki line its own cited bug contradicts, and that the
"live-verified untouched" population read most likely read the clipping
river's fish, not the pools'. Current position: flowing water restocks,
still water may not (moderate confidence); whether this fort's pools hold
fish at all is open. The original two paragraphs moved wholesale to
`working-archive/Working_archive-2026-09-14.md`. → `doctrine/seed.yaml`
`do-not-overfish` and `uniboslan-pool-fish-unknown`, `decisions/DECISIONS.md`
2026-09-17.

**Open idea, not started:** the user proposed background ground-truth
audits (like the `region-pops` check above) running at fort start and
periodically, compared against agent beliefs/predictions after the fact,
but never exposed to the agents themselves except via player-derivable
signals — the same shape `dfqueue`'s grader already has for predictions.
Blocked on the same "no scheduler exists" gap already on record
(2026-09-16). Not yet placed in `ROADMAP.md`; ask before starting.

### Founders-not-drinking: answered in practice, not in full

The zone fix (above) resolved the symptom. The deeper "why job-assignment
routed founders as `GiveWater` workers and migrants as patients, when
founders were thirstier" question in
`research/2026-09-17-founders-not-drinking.md` is still open (three ranked
hypotheses, none confirmed) but no longer blocks anything: self-serve
drinking now works. Not worth chasing further unless it recurs.

### Not yet done, carried from the 2026-09-15/16 ladder (lower priority than
the list above)

- **A grader schedule.** Nothing runs on one; no Sentry. `proposal-0001`
  remains ungraded on purpose (its window blew before this was ever fixable).
- **The public feed/stream page and `dfqueue.render.public_view` publisher.**
  Not built; needs its own go-ahead once built (public-facing).
- **Architect and Overseer quality**, still n=1 each. `ruling-0001` was
  charter-clean but judged an unattributable prediction sound.
- **Execute a proposal end to end.** Still blocked on no tool building what
  any proposal so far has asked for.

### Open, waiting on the user

- **DeepSeek key in plaintext on VM 106** in
  `/opt/openclaw/config/state/openclaw.sqlite`. openclaw 2026.9.4 has no
  headless way to store it as a reference; `openclaw secrets configure` over
  `ssh -t` might. `sudo rm -rf /opt/openclaw` removes both secrets.
- **PVE token rotation**, deferred by the user. It needs a privileged
  identity, and deleting a token drops its ACLs.
- **Tailscale**, deferred. Until then the LAN bind means tokens are the only
  guard.
- **Two deferred live checks:** whether the frame cap survives a save load,
  and whether an overlay renders in the headless pipeline.

### Owed elsewhere

- **`home-lab` `inventory/services.yaml`: the `dfmcp-server.service` entry is
  written, not committed.** home-lab-fe added it 2026-09-15, marked
  `inferred`, and validated it. It is left in that checkout for the user to
  review and commit. VM 106 owes an entry only once openclaw runs as a service
  (nothing listens today).

### Background, not urgent

- **Project SSH never verifies host identity.** `scripts/provision_vm.py` and
  `scripts/install_df.py` use `StrictHostKeyChecking=no` with throwaway
  known_hosts files. Worth pinning the estate's real keys eventually.
- **The breach detector is inconclusive.** Settle it opportunistically (rain,
  or an animal fording water), never by flooding the fort.
- **The `../openclaw` scaffold** reads `OPENCLAW_CONFIG_DIR` and
  `OPENCLAW_AUTH_PROFILE_SECRET_DIR`, which the image ignores; use
  `OPENCLAW_STATE_DIR` before running it durably.

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
- 2026-09-17: the whole HANDOVER 2026-09-16 section (the production-gap discovery, the stocks/labor-race fix, the knowledge-scope audit, and the day-one farm-and-water work) moved wholesale to the same 2026-09-14 archive file, since the file exceeded the ~400-line threshold. Every still-open item was carried into HANDOVER 2026-09-17 at the top; nothing was summarised or dropped.
