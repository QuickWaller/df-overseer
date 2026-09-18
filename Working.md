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
- `get_doctrine`, read-only, with a topic index (agreed; **built 2026-09-19** as `doctrine.get`, consultant only, not yet deployed).
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

## Live fort state, read-only, 2026-09-18 at tick 227160 (paused)

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
- `autolabor` is **enabled**, so labour counts are its live allocation, not a
  configuration: PLANT 2, BREWER 1, COOK 1, CARPENTER 1, DIAGNOSE 18 on 1,
  SURGERY 19 on 1, RECOVER_WOUNDED 24 on 1, and **`FEED_WATER_CIVILIANS` 23
  on all 15**. Hand-setting a labour takes it off autolabor fort-wide and
  permanently, so that lever is contested. → `docs/PRODUCTION-MODEL.md` §13.
- **Corrected the same day:** an earlier entry here said
  `FEED_WATER_WOUNDED` was enabled on 0. That token does not exist, and the
  probe could not tell a missing field from a real zero. There is **no labour
  gap in the water chain**. `BIND_WOUND` and `DRESS_WOUNDS` are not real
  tokens either.
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


### The fort cannot drink, and the pond cannot be dug to (2026-09-18, tick 235668, paused)

**Supersedes the thirst line above.** Measured exactly across two reads: tick
227160 thirst 23,391; tick 233463 thirst 29,694. **Delta tick 6,303 = delta
thirst 6,303 across all 15 citizens**, so `thirst_timer` increments exactly 1
per tick and **nobody drank at all**. Top thirst is now 31,899. The earlier
"not in danger" reading was wrong: the `WaterSource` zone is active but
unreachable.

**Why.** The pond is a sunken bowl. Decoded tile shapes: z168 is 142 WALL, 26
RAMP, 1 FLOOR, **0 walkable**, with 27 water tiles all at least 3 deep and
**zero water tiles having any walkable neighbour**. z169 above is 134 walkable,
100 FLOOR, 26 RAMP_TOP, 0 wet.

**Digging does not fix it, proven not assumed.** A ramp was first designated at
z168; the user corrected the level, and investigation showed z168 has **0
walkable tiles near the pond**, so no miner could stand there to dig it. It was
cleared and a Channel designated at z169 on a floor tile with 3 walkable
neighbours. One supervised unpause with a remote watchdog: designation dug,
z168 wet went **27 to 28**, z168 walkable stayed **0**. The new tile simply
flooded. The user reached the same conclusion independently: **go for a well.**

**The well's blocker, from `df-overseer-well find 1 "Activity Zone #1" 20`:**
a viable site one tile from the zone, water depth 6, not salt, **stagnant
true** (a well on it gives unhappy thoughts; survivable). Requirements against
fort-owned stock: **BUCKET 3 and CHAIN 3 present, BLOCKS 0 and TRAPPARTS 0
absent.** The fort owns 3 logs and 0 boulders, and stone is at z167 behind the
half-designated stair.

That is a three-deep chain and exactly the shape `production/blocker.py` was
built to report: drink -> WELL -> BLOCKS + TRAPPARTS -> stone -> stair to z167
-> not dug.

**Dispatched, not resolved:** `handoffs/2026-09-18-well-unblock.md`. Its first
task is to settle from this install's own raws whether a mechanism can be made
from wood, because that single fact chooses between the wood route (3 logs) and
the stone route (finish the stair, mine, build mason's and mechanic's). Done
means thirst falling across two reads, not a well existing.

**Also open, unresolved:** the `PlantSeeds` queue drained 25 to 13 with no
seed-stock change and no plants appearing. The user reports the farm is
genuinely half-sown and still being sown, so this is a **measurement
discrepancy in our read**, not a stalled fort. The still's job 366 was
unsuspended this session; the user reports it reads suspended again.
## Current state, 2026-09-15: archived

Moved wholesale to [`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md) on 2026-09-18, superseded by
HANDOVER 2026-09-19 and the production-model work above.

## HANDOVER 2026-09-19 (read this first after a /clear)

The 2026-09-17 handover is archived in
`working-archive/Working_archive-2026-09-14.md`. Its fort figures were
disproven and its stream list overtaken, but the fishing reversal, the stair
background and the ground-truth idea live only there.

**Authority.** The user granted this session full authority to push, to change
the VM and to act on the fort, explicitly asking not to be asked per action,
and restated it on 2026-09-19 ("this is all dev experiments not production").
Standing exception kept: genuinely unrecoverable loss (the fort save, the VM
itself) still stops and reports.

### The fort, and the one thing that is actually wrong

**ROLLED BACK 2026-09-19. Paused at tick 213622, not 235668.** An unbounded
live DFHack query wedged the command pipe and recovery needed `kill -9`, which
discarded roughly **22,000 ticks** back to a three-day-old quicksave. **Lost:
the 2026-09-17 `WaterSource` zone, the first farm plot, and a stair
designation.** Two standing rules came out of it and are now in
`docs/TRAPS.md`: never run an unbounded query against a live DFHack process,
and **quicksave immediately before any live fort action**, because the cost of
an incident is set by the age of the last save.

**Uniboslan does not drink.** Paused at tick **213622**, year 30, 15 citizens,
zero deaths. Fort-owned after the rollback: **drink 0, prepared meals 0**,
**raw plants 2** (was 8), seeds 60, logs 3, boulders 0, and **15 empty
barrels**.

**The route is brewing, not a well.** Settled from the install's own data:
**no reaction anywhere produces `TRAPPARTS` from wood**, and DFHack's
`stockflow.lua` offers `ConstructMechanisms` only under rock and metal, so the
well needs stone the fort does not have. Brewing needs only a still (1 log of
3) and an empty `FOOD_STORAGE` container, and **the fort already owns 15
barrels**, so the container is free. 2 plants brew to up to 10 drinks
(`brewing-chain-from-raws`, `plump-helmet-is-brewable`, both verified).

**The deliverable is not the drink, it is the two thirst reads.** Whether
alcohol satisfies thirst on this install is still only `prior`, on an
unrecorded wiki read.

Measured across two exact reads: **delta tick 6,303 equalled delta thirst
6,303** across all 15 citizens, so `thirst_timer` rises 1 per tick and nobody
drank in that window. Top thirst 31,899.

**The measurement method is now cleared, but the contradiction is still open.**
`getWalkableGroup` was compared against tile shape and the two **agree** at 0
walkable neighbours, sanity-checked first against all 15 citizens' own
known-walkable positions. So the suspicion below was unfounded and the reading
was sound. **What remains unexplained:** the offered explanation (that a
41-tile dig bridged the network and was lost in the rollback) **does not fit
the dates**, because the rollback happened *after* the zero-walkable
measurement was taken. Either something else removed reachability between
2026-09-17 and 2026-09-19, or that dig never reached the water, or the
2026-09-17 drinking happened elsewhere. Left open deliberately.

**The original suspicion, kept for the record:** An audit found that the 2026-09-17 record has three founders
demonstrably drinking at that pond with `NastyWater` thoughts, while the
2026-09-19 reading says zero water tiles have a walkable neighbour, which
would make that impossible. **Leading hypothesis: the 2026-09-19 reading is
mine and is wrong**, because it derived walkability from tile *shape* while
the pond is a bowl of submerged RAMP tiles a dwarf may wade across. The right
primitive is probably `dfhack.maps.getWalkableGroup`, which
`df-overseer-connectivity.lua` already uses.

**Do not act on the well plan until that is settled.** What survives either
way: nobody drank over that window.

**The brew route may be shorter than the well anyway.** Doctrine
(`alcohol-is-not-food`, status `prior`) holds that drink satisfies thirst on
its own, which would make the whole pond question moot. The fort has 8 raw
plants and 3 logs; the still is designated but unbuilt with its job **366**
reported suspended twice.

### Update, 2026-09-19 morning (read before the list below)

**The fort survived and drinks.** Live read at tick **272606**, paused: **23
citizens alive, 0 dead** (eight migrants arrived), a still exists, drink stock
0. All 15 original citizens (ids 192-198 and 344-353) have thirst at or below
28,922 after roughly 59,000 elapsed ticks, which is only possible if each
drank. The newest eight (453-460) sit at 1,737-2,377 in exact steps of 100,
consistent with arrival, so they are not counted as evidence. **What they drank
is unknown and deliberately not being chased** (user, "idrc"): 2 plants brew at
most 10 drinks, which cannot cover it alone.

**Autosave is fixed** (register 2026-09-19): an in-game `repeat` quicksaves
every 7 game days, persisted in `onMapLoad.init`. Registered, **not yet seen
firing**. A manual quicksave was taken at 272606 and confirmed by slot mtime.

**The well stream and the extraction stream both died on a Sonnet session
limit.** The extraction work was preserved on its branch and the stream has
been resumed. Three streams now running: extraction (resumed), deploy and
live-verify (VM 103), and `get_doctrine`.

**User directions:** blocks come from mining plus a mason's workshop;
drinks must be kept ahead of the plants (`brew-before-plants-run-out`); neither
is the current focus. **The loop itself ("nothing runs on its own") is not
being built unilaterally**: its core architecture is pending the user's
decision, per the learning-loop section above.

### Update, 2026-09-19 afternoon: the fort records its own history

The in-game sampler is live (one record per game day, `docs/TIMESERIES.md`),
`dfseries` stores it, and the two were proven end to end on a real 9-game-day
run. The autosave was seen firing for the first time. **The fort is paused at
tick 283992** and **runs at 100 FPS, not 10**, despite several docs. The user
directed the order: **fix the timer-reset bug, then automatic import, then MCP
tooling**, and is away. Reset fix and auto-import are running; the MCP stream is
written and waits on the reset fix.

### START HERE, in priority order

**Sequencing rule while streams are live:** only one stream touches VM 103 or
the fort at a time. Two `production/` streams may run together **only** when
their file ownership is strictly disjoint and each handoff names the other's
files as forbidden.

**The worktree trap, hit twice now:** a worktree agent is cut from the last
**pushed** commit. Write the handoff, commit, **push**, then dispatch. A local
commit is not enough.

0. **Settle the walkability contradiction, then get the fort drinking**, by
   whichever of brew or well the evidence favours. Running:
   `handoffs/2026-09-19-well-unblock.md`. Done means thirst **falling** across
   two reads, not a well existing.
1. **Deploy the new tools to VM 103 and live-verify them.** Queued behind the
   fort stream. Three things landed undeployed today: `stocks.availability`
   (new), the silent-zero fixes in `trees`/`workshop`/`well`, and the older
   `dig-stair` fix. **`stocks.availability` specifically needs both
   `UNIT_HOLDER` branches exercised** (a known-held item and a known-unheld
   one) before `owned_ref_check.verified_offline` can honestly flip to true.
   Reconcile the `ROADMAP.md` / `CLAUDE.md` tool counts against the real
   post-deploy numbers at the same time.
2. **Fill the graph.** Running:
   `handoffs/2026-09-19-real-corpus-extraction.md`. The extractor had never
   seen real data; 159 real reactions are staged out of tree.
3. **Then the supervised run**, written and waiting:
   `handoffs/2026-09-18-supervised-run-and-measure.md`. Settles four known
   unknowns including the `growdur` unit that blocks the harvest clock.
4. **The stair to z167** stays outstanding unless the fort stream resolves it
   as part of a stone route. Orphan UpStair designation at z167 still present;
   the `dig-stair` fix is merged but undeployed.

### Done today, so do not go looking for it

Six streams merged on 2026-09-19: the snapshot assembler, the water doctrine
correction, the unverified-claims audit, the availability tool, the
silent-zero fix, and (2026-09-18) days-of-cover and the blocker walk. Suite is
**382 passed / 1 skipped**. `production/` is six modules. The visual ledger is
at the artifact URL recorded above.

### Open, waiting on the user

- **The loop architecture**: dispatcher plus queue (independent one-shot
  runs, our scheduler wakes them, roles talk only through the queue)? This
  blocks the biggest gap, "nothing runs on its own".
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
- Worth doing alongside either: a pre-commit or CI check that refuses an IPv4
  literal outside `infra/local.*`, since three leaks were caught by hand on
  2026-09-19 alone and one was already public.
- `infra/local.example.env` and `scripts/provision_vm.py` contain
  `192.168.1.240/24` as an **illustrative example value**, not a real address;
  those are fine and must not be swept up by a filter.

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
