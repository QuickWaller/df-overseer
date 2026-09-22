# Roadmap

**Last reviewed:** 2026-09-21, evening (twenty-third pass, targeted: a full re-read of the
Now bucket's top items against `Working.md`, the register and the handoff index after a
day of twelve streams. What moved is recorded in the new top Now item: the building,
gotchas, labor-graph, nobles and zone tools are deployed (tool lists **34/57/14**), a
Manager is appointed and its limit found (the fort has no Office), the labor graph is
filled (5 known / 23 partial / 5 unknown of 33 kinds), and the auto-mode classifier is
configured. The Next and Later buckets were keyword-scanned (building, workshop, zone,
room, manager, nobles, gotcha, labor, workjob, deploy, stockpile, furniture, assess) and
nothing was found that today's work finished; that was a search, not a line-by-line
read. Suite measured 2026-09-21: **891 passed / 3 skipped** ambient, **537** in
`.venv-dfmcp`.)

**Previously reviewed:** 2026-09-21 (twenty-second pass, full re-scan of the Now
bucket against `Working.md`, the register and the handoff index. Four things
had moved since the last pass and are recorded in the new top Now item: the
well was built, the fort lost its first citizen to starvation and was then fed,
the batch deploy went live (tool lists were 25/45/11; **34/57/14 since 2026-09-21**), and the fort's history
is now sampled, stored and served to agents. The Next and Later buckets were
keyword-scanned (doctrine, time series, snapshot, well, deploy, manager,
brew) for anything quietly finished and nothing was found; that was a
search, not a line-by-line read. Older Now items
below are left as written, each already carrying its own supersession note or
now carrying one. Suite measured 2026-09-21: **552 passed / 1 skipped**
ambient, **271** in `.venv-dfmcp`.)

**Previously reviewed:** 2026-09-19 (twenty-first pass, targeted: the drinking
crisis corrects the 2026-09-17 "now drinks" claim, and the production graph
moves from "nothing built" to "built, green and empty" with two streams live.)

Previously: 2026-09-18 (twentieth pass, targeted doc-drift pass: added
a new top Now item for the production and logistics model design (settled on
paper, nothing built, two feasibility audits and a figures pass landed the
same day) and pointed the "Game figures database and calculators" Next item
at it. Re-scanned the rest of the Now and Next buckets for anything quietly
finished or stalled: nothing found to change beyond the two items above;
tool counts left to the stream that owned them, now reconciled by the
orchestrator: **24/37/4 deployed and live-verified per role** on 2026-09-19 (was 23/36/4 on 2026-09-18; `stocks.availability` added),
after the bucket-order and stockpile tools. The stale 19/32/4 in the
2026-09-17 entry below is left as written, since that entry records what was
true that day.) Previously: 2026-09-17 (nineteenth pass, targeted: the production-gap
Now item updated to say it is partly closed, since the fort now drinks and has
a farm plot with its crop set (nothing planted yet) and 19/32/4 deployed tools; the still, a trade depot, typed
stockpiles and deeper digging remain unbuilt. Checked and left as-is: the
game-figures-database and wiki-lookup Next items still read correctly.)
Previously: 2026-09-16 (eighteenth pass, targeted: a new top Now item
for the production gap and the building-tools stream, after the fort was found
stopped with no fort-owned food or drink and no tool able to fix it;
`proposal-0001`'s execution demoted behind it.) Previously: 2026-09-16 (seventeenth pass, targeted doc-drift pass: the
Overseer's first ruling landed (`ruling-0001`, `proposal-0001` accepted) and
the Now item's next-steps list updated to mark it done and note the paused
fort as the blocker for execution and grading.) Previously: 2026-09-15 (sixteenth pass, targeted not full: the queue
tools went live, VM 106 went dark and was rebuilt, and incident capture shipped;
the Now item's next steps are renumbered.) Previously: 2026-09-15 (fifteenth pass, targeted not full. It adds a
Now item for the 2026-09-14/15 work: openclaw calling the fort, two architect
charter runs, three live-verified dfmcp fixes, and the SQLite proposal queue
with live-state signals. The feed beside the stream becomes the next visible
goal.) Previously: 2026-09-14 (fourteenth pass, targeted not full: the MCP
server's Now item flipped to DONE once the live smoke test on VM 103 passed
all six checks and the two bugs it found were fixed and re-verified. The next
seam is openclaw calling the server.) Previously: 2026-09-12 (thirteenth pass, end of the MCP-server session:
the one hard blocker is cleared, so the Now bucket's central item is done and
marked; the address-leak item and the openclaw-VM item are both closed; the
`openclaw` row's "still unbuilt: the MCP seam" corrected. What is NOT done and
is now the top of the list: nothing in `dfmcp/` has met a live DFHack, a bound
socket, or a real agent host. Twelfth pass, agent-architecture design phase: Now bucket rewritten after all four research briefs returned, the roster and deployment topology were decided, and the first code landed; added the two missing safety detectors, the set_labor/autolabor race and the address-leak cleanup as Now items. Eleventh pass, post-merge documentation
consistency check: `perception-layer-experiments` merged into `main`
(`f078bf8`) and its worktree deleted, so every bullet below that framed the
branch-merge question as open, or cited the branch/worktree as separate
from `main`, is updated to say so: none of that work itself changed, only
its merge status. `df-overseer-combat.lua` no longer exists as a separate
file (folded into `df-overseer-diff.lua`, `6dd92bb`); no open bullet named
it directly, so nothing else needed touching there. `openclaw` vs
`hermes-agent` checked and left as-is: still a genuinely open, deferred
choice, not resolved by the merge. Tenth pass, 2026-09-11: confirmed the
diggable-area items below are accurately marked DONE and already correctly
placed, not still in progress; fixed a stale "main not yet pushed" claim
elsewhere in this repo's docs. Ninth pass, same day: perception-layer-experiments audited for real, build order items 2-8 are actually done, not just files; first autonomous-play attempt found the coordinate-resolution gap blocking it from closing the loop, closed later the same day, see below)

This file is df-overseer's forward-looking, priority-ordered plan: what's
next and roughly when, across infrastructure, game-side engineering, and the
research build order. It's the one thing the rest of this repo's
documentation doesn't provide: `Working.md` is tactical (what's actively in
motion right now, in detail); `decisions/DECISIONS.md` is retrospective (why
a call was made, once it's made). Each bullet below is one line: what it is,
why it matters, and a pointer to where the real detail already lives. Keep it
that way; if an item needs a paragraph, that paragraph belongs in `Working.md`
or `decisions/DECISIONS.md`, not here.

## Now
<!-- Actively being worked, or the clear immediate next step. -->

- **NEW 2026-09-21, evening: the building blocks are live, and the next job is proving
  them for real; the agent loop is the largest unbuilt piece.** Deployed and
  live-verified on VM 103 today: the generic `building` tool (dry runs only), `labor
  enabled-counts`, `gotchas.*` with static confidence levels, the labor graph and
  join, `nobles` (unit 345 is now MANAGER, verified from both sides), and the
  generalised `zone` tool (18 kinds, optional owner). A supervised unpause showed the
  queued manager orders still do not run: the position needs an **Office** and the
  fort has no zones. Against the user's minimum bar for openclaw, wells are done and
  everything else is unproven or undesigned. In order: **(1)** redeploy the labor-join
  shape fix and check it live; **(2)** place an Office for real, furnish it, and
  watch whether the orders run; **(3)** the first real build of a never-built kind;
  **(4)** generalise `workjob` (DFHack builds reaction jobs generically and jobs have a
  `repeat` flag); **(5)** design assessing dwarves, the food chain end to end,
  stockpile creation, game-clock control and defence; **(6)** only then the agent
  loop and openclaw, which the user tabled. -> `Working.md` HANDOVER 2026-09-21,
  evening, `decisions/DECISIONS.md` 2026-09-21 rows, `handoffs/INDEX.md`.
- **PARTLY SUPERSEDED 2026-09-21, evening, by the item above (kept for the record):**
  the item below, whose step (1) was answered in part (hunger and thirst were read at
  tick 106974 and were nowhere near critical), whose step (3) named an
  appoint-a-Manager tool (built, deployed and tested) and whose Manager premise
  changed (an appointment alone does not start orders; an Office is needed). Its
  steps (2) the supervised run and (4) the apostrophe fix are still open.
- **NEW 2026-09-21: the fort has a well and a history, and the next job is
  reading it properly and giving it a drink that does not depend on luck.**
  Uniboslan is paused at year 31, tick 103055, **22 alive and 1 dead** (unit 454
  starved at tick 15143, when only drinks were being counted). The **well is
  built** (id 8) from blocks and a mechanism the fort made itself through
  `df-overseer-workjob`; a dwarf was caught drinking 1 tile from it, but most
  drinking still comes from a water source nobody has located. The fort's own
  history is now recorded (in-game sampler, one record per game day), stored
  (`dfseries`, reset-aware) and readable by the overseer and consultant
  (`series.*`), all live on VM 103 after the 2026-09-20 batch deploy. What is
  still open, in order: **(1)** read every vital on the live fort, since the
  last recorded hunger read is 73,000 ticks old; **(2)** the supervised run
  (`handoffs/2026-09-18-supervised-run-and-measure.md`), still unrun, mainly for
  the `growdur` unit that blocks the harvest clock; **(3)** brewing, an
  appoint-a-Manager tool, fishing and hunting, and finding the unlocated
  water; **(4)** the MCP apostrophe fix. The loop architecture stays tabled by
  the user. -> `Working.md` HANDOVER 2026-09-21, `decisions/DECISIONS.md`
  2026-09-19 and 2026-09-20 rows, `handoffs/INDEX.md`.
- **SUPERSEDED 2026-09-21 by the item above (kept for the record):** the two
  2026-09-19 items directly below that say the drinking diagnosis is under
  suspicion, that the fort "cannot drink", that the well is blocked three
  levels down, and that "none of today's tool work is deployed". The well is
  built, the tools are deployed and live-verified, and the real corpus was
  extracted and the snapshot assembler built (the production-graph item below
  still says "green and empty": it is now filled, and pointing it at the live
  fort is the supervised run above).

- **UPDATED 2026-09-19 (later the same day): the drinking diagnosis is
  itself under suspicion.** An audit found the 2026-09-17 record has three
  founders demonstrably drinking at that pond with `NastyWater` thoughts,
  while the "zero walkable neighbours" reading below would make that
  impossible. Leading hypothesis: **that reading derived walkability from
  tile *shape*, and the pond is submerged ramps a dwarf may wade across.**
  Until it is checked against `dfhack.maps.getWalkableGroup`, the well plan
  rests on a bad measurement. A **brew route** may be shorter regardless,
  since doctrine holds drink satisfies thirst on its own. What survives: over
  6,303 ticks nobody drank. → `Working.md` HANDOVER 2026-09-19,
  `research/2026-09-19-unverified-claims-audit.md` finding 5.
- **NEW 2026-09-19: six streams merged, and an audit found the project had
  shipped one bug five times.** Landed today: the snapshot assembler (the
  caller that lets the graph see the fort), the water doctrine correction,
  the availability tool (three of four exact deductions now readable), the
  silent-zero fix, and the unverified-claims audit that found the last two.
  **After the `FEED_WATER_WOUNDED` incident this project fixed `set_labor`,
  wrote the lesson into the build spec, and left four copies of the same
  shape in tools the agents call.** Nothing failed to prompt the discovery;
  only the audit closed it. Suite is **382 passed / 1 skipped**. **Owed:
  none of today's tool work is deployed.** → `decisions/DECISIONS.md`
  2026-09-19 rows.
- **NEW 2026-09-19: the fort cannot drink, and the well is blocked three
  levels down.** This corrects the 2026-09-17 item below, which says
  Uniboslan "now drinks". It does not. Measured exactly across two reads:
  delta tick 6,303 equalled delta thirst 6,303 across all 15 citizens, so
  `thirst_timer` increments 1 per tick and **nobody had drunk at all**. The
  `WaterSource` zone is active but unreachable: the pond is a sunken bowl in
  which **zero water tiles have any walkable neighbour**. Digging to it was
  disproven rather than assumed, by digging: a channel at z169 flooded and
  left z168 walkable at 0. The fort needs a **well**, which is blocked on
  BLOCKS 0 and TRAPPARTS 0 against 3 logs and 0 boulders, with stone at z167
  behind the half-designated stair. → `handoffs/2026-09-19-well-unblock.md`,
  `decisions/DECISIONS.md` 2026-09-19, `Working.md`.
- **NEW 2026-09-19: the production graph is built, green and empty, and two
  streams are filling and connecting it.** This supersedes the "designed in
  full, nothing built" item below: `production/` is now 2,182 lines across
  five modules at 364 passed / 1 skipped, covering steps 1 to 5 of the spec's
  build order. Two gaps were then found by auditing the package rather than
  by anything failing. **The extractor has never seen real data** (its stream
  was offline by design and ran against 6 hand-assembled fixture reactions;
  its own write-up says the row counts "are not a coverage claim about the
  real install"), and **nobody wrote the caller**: `blocker.py` and `cover.py`
  are pure functions over a caller-assembled snapshot, but no code assembles
  one, so the graph has never been pointed at this fort. The live proof is
  that the well chain above was walked **by hand**, in exactly the shape
  `blocker.py` returns. The real 159-reaction corpus is now staged out of
  tree, deliberately uncommitted since this repo is public. →
  `handoffs/2026-09-19-real-corpus-extraction.md`,
  `handoffs/2026-09-19-snapshot-assembler.md`.
- **NEW 2026-09-18: the production and logistics model is designed in full,
  nothing built.** `docs/PRODUCTION-MODEL.md` is the build spec (a directed
  hypergraph in plain SQLite, seven tables), corrected by two feasibility
  audits (`research/2026-09-18-schema-extraction-static.md`,
  `research/2026-09-18-schema-extraction-live.md`) and a figures pass
  (`research/2026-09-18-production-figures.md`). Real corrections the audits
  forced: consumption has **four** outcomes, not the three the first design
  named (a fourth, `modified_in_place`, covers the `GLAZE_*` reactions);
  42% of reaction product lines need a material-side join before a node id
  exists, not a straight per-line read; no job-duration figure exists in
  any raw, DFHack doc, or wiki page checked, confirmed a third independent
  time. Supersedes the "Game figures database and calculators" item below
  as the actual design; that item's own text is left as-is beneath this
  note per this file's convention, since the design work it called for now
  has a real spec. → `decisions/DECISIONS.md` 2026-09-18 (six rows),
  `Working.md` (pre-audit summary, now stale on table/consumption counts;
  not rewritten here, out of this pass's touched surfaces).
- **UPDATED 2026-09-17: the production gap is partly closed.** Uniboslan now
  drinks (a `WaterSource` zone placed on a pond fixed a real terrain problem,
  not proven as the sole cause but decisive enough to keep) and has its first
  farm plot, with plump helmet set for all four seasons but nothing planted yet. Water and industry
  tools shipped and deployed the same day: zones, tree felling, manager work
  orders, a well builder, and mason/mechanic/carpenter workshops. Role tool
  lists moved 13/18/4 to **19/32/4**. **Still not built or unblocked:** the
  still (designated, material on hand, no worker took the job across a full
  unpause), a trade depot, typed stockpiles, and a dig tool that can reach
  stone two levels down (blocks blocks and mechanisms). → `Working.md`
  HANDOVER 2026-09-19 (the 2026-09-17 one is archived), `decisions/DECISIONS.md` 2026-09-17 rows. Original
  text follows.
- **NOW, 2026-09-16: build the tools that make a fort produce anything.**
  Uniboslan is stopped behind a popup with zero fort-owned food or drink and
  no farm plot, still, workshop or depot, and **the agents' write surface (dig,
  open-area build, landmark build, labor set) cannot fix any of it** — which is
  the finding, not the fort. Next: decide the rescue path with the user (depot
  and trade, farm and still, or restart — the fort is expendable, the tools are
  the point), then dispatch the building-tools stream from the research's list:
  workshops, farm plots, trade depot, typed stockpiles, manager orders, plus
  the missing read tool that separates fort-owned stores from foreign goods.
  `workorder` is available and `orders import library/basic` is the cheapest
  real win; the `zone` plugin is not available here.
  → `research/2026-09-16-food-and-drink-logistics.md`, `Working.md` handover.

- **NOW, 2026-09-15: wire the proposal queue into dfmcp, then the feed.**
  Done since the last pass:
  - openclaw on VM 106 called the fort and answered correctly;
  - two architect charter runs, with output in `evals/live/`;
  - relative `level` args, `isError` for script errors, and a JSON tool-call
    log, all deployed and verified live on VM 103;
  - `dfqueue/`, a write-time validated proposal queue in SQLite with
    live-state prediction signals and a grader (local code).

  **Next, in order:**
  1. ~~`propose` / `pass` / `ruling` MCP tools~~ **DONE 2026-09-15**, live on
     VM 103; architect run #3 wrote the first real proposal;
  2. ~~the Overseer rules on it~~ **DONE 2026-09-16**: a second openclaw agent
     (Overseer, `deepseek-v4-pro`) accepted `proposal-0001` as `ruling-0001`,
     charter-clean but one sample judging an unattributable prediction sound,
     not evidence of good arbitration;
  3. execute `proposal-0001` and run the grader against its prediction — now
     **deferred behind the building-tools item above**: its 1200-tick window
     elapsed within about a minute of unpausing (real cap `FPS_CAP` 100, not
     the 5 several docs assumed), so grading it records a latency miss rather
     than a verdict (register), and no tool exists that could execute it
     anyway. Left ungraded on purpose; a grader **schedule** is still owed for
     the predictions that follow;
  4. a publisher of §8's allowlisted fields (no delay, user's call);
  5. the stream page with the feed on the right (**public, so its own
     go-ahead**).

  **Also open:** run #2 dropped the proposal format and strayed into
  defensibility, and the DeepSeek key is plaintext on VM 106.
  **Done alongside, 2026-09-15:** VM 106 went dark (cause unknown), was rebuilt
  in place, and incident capture now runs on VMs 103 and 106
  (`docs/RUNBOOK-DARK-GUEST.md`); overseer and consultant MCP tokens rotated.
  → `Working.md`, `decisions/DECISIONS.md` 2026-09-14/15/16.

- **NOW, 2026-09-12: the agent architecture is designed, all four research
  briefs are back, and the first code exists.**
  [`docs/AGENT-ARCHITECTURE.md`](docs/AGENT-ARCHITECTURE.md) is the design:
  one actor (Overseer), read-only advisors that propose rather than act, two
  code components (Sentry, Triage), one append-only queue that is channel,
  audit log and write-ahead log at once, graded urgency with playbooks as
  data, one snapshot per cycle with per-role projections at three tiers, and
  confidence that is tool-stated for facts and measured from graded
  predictions for proposals. 26 register rows carry the reasoning.
  **Research outcome in one line: the central choices survived (single
  writer, no peer chat, per-agent tool scoping is real), several assumptions
  did not** (no host spend cap, lane-serialised fan-out, no breach signal at
  all, a hostile signal blind by construction). **Roster decided, user's
  call: three roles enabled**, Overseer, Architect, Consultant, being the
  ones whose tools exist. **Built and landed:** `agents/` (roster, charters,
  allowlists). **UPDATED 2026-09-12: everything this row called "in progress,
  not yet on `main`" is on `main`** -- the `dfmcp/` registry and role-scoping
  layer, the two safety detectors, and three further modules that did not exist
  when this was written.
  → `docs/AGENT-ARCHITECTURE.md` §14 for what remains open.
- **DONE 2026-09-12: openclaw's VM is provisioned and live.**
  `df-colony-openclaw-01`, vmid 106, static address, 2048 MB, onboot enabled,
  linked clone on SRV-01; verified from inside the guest by SSH rather than
  from the API's status field, and the `guests:` entry owed upstream was handed
  to a live `home-lab` session immediately rather than carried by a handover.
  Found and fixed on the way in: **`provision_vm.py clone` read `DF_VM_IP` and
  nothing else, so it would have assigned the running fort's own address** to
  the new VM and reported success. Address selection is now per guest
  (`--ip-var`) with a pre-clone collision check. → `decisions/DECISIONS.md`
  2026-09-12, `Working.md`.
- **DONE 2026-09-12: the MCP server exists. The project's one hard blocker is
  cleared.** `dfmcp/` is six modules and 136 tests: the tool registry, the
  role/permission seam, MCP tool definitions plus argv construction, bearer
  token to role, a persistent DFHack RPC client with a connection pool, and the
  streamable-HTTP transport tying them together. Built in four parallel Sonnet
  streams against two research briefs. **Verified in the orchestrator session,
  not taken on report: an advisor calling a write tool is refused through a
  real SDK client with the exact reason string intact, and the call provably
  never reaches DFHack.** **DONE 2026-09-14: it has met reality.** The live
  smoke test on VM 103 passed all six checks (after a fix, below), so the
  bound socket, the real SDK, the auth, the per-role listing, the refusal path
  and the DFHack pool are all proven against the running fort. It cost two
  real bugs, both fixed and re-verified live: array tool output broke
  `structuredContent`, and `pyyaml` was unpinned. **The one seam left is
  openclaw actually calling it.** → `handoffs/2026-09-14-mcp-live-smoke-test.md`,
  `Working.md`, `decisions/DECISIONS.md` 2026-09-14.
  Superseded: **Not yet met reality**: no live DFHack, no bound
  socket, no openclaw client. That smoke test is the next concrete step and
  needs a go-ahead, because it touches VM 103. → `Working.md`,
  `handoffs/INDEX.md`, `decisions/DECISIONS.md` 2026-09-12.
- **Superseded, kept for the reasoning. NOW, still the hard blocker: the MCP
  server itself does not exist.**
  `scripts/dfhack/TOOLS.yaml` is a schema, not a server. **Topology decided
  2026-09-12: openclaw gets its own VM (address pre-allocated in home-lab's
  registry); the MCP server and Sentry stay on VM 103 with DF**, because
  DFHack's RPC socket is unauthenticated and must not cross the network.
  **Two requirements locked in before building, because retrofitting them is
  painful:** the tool allowlist is enforced **server-side** (openclaw's own
  per-agent scoping is defence in depth, not the boundary), and **role
  identity is a credential, one token per role**, never a self-declared
  header, or an advisor could claim to be the Overseer and obtain write
  tools. Performance requirements are also settled: hold one persistent
  DFHack RPC connection rather than shelling out per call (3-5x), and batch a
  cycle's reads into one suspend window.
  → `docs/PURPOSE.md` commitment #5, `docs/AGENT-ARCHITECTURE.md` §13, §14.
- **UPDATED 2026-09-12: both safety detectors now exist and are deployed, but
  only one is proven.** `df-overseer-threat.lua` is **verified working on both
  of the failures that motivated it**: it admitted a fox and a weasel purely by
  shared walkable group with no danger flag, and correctly excluded the two
  demons that DO carry danger flags, confirmed by direct query rather than by
  trusting the scan's silence. Reachability gates admission; flags do not.
  `df-overseer-breach.lua` is **INCONCLUSIVE and must be treated as covering
  nothing**: its cheap first stage keys off a block flag that was set on zero
  of 26,784 blocks across 11 polls, on a map whose water is fully settled, so
  that cannot distinguish "DF never sets it" from "nothing changed". **So flood
  response is still covered by nothing**, exactly as before the detector
  existed, and the opportunistic test (rain, or an animal fording water)
  remains the way to settle it. Original text follows.
- **Superseded. NOW, required work rather than polish: two safety detectors do
  not exist.** Verified from DFHack source 2026-09-12. **Water or magma breach
  has no event and no announcement type at all**, a checked negative, so
  **flood response is currently covered by nothing**, and breach is among the
  fastest fort-killers. **Hostile detection has only `INVASION`**, which
  fires for registered invasions and not for ambushes, thieves or wildlife
  turning aggressive, meaning the event layer shares the blind spot the
  polling signal already had. Design insight to build on: **reachability, not
  hostility, is the discriminating feature** (it would have correctly
  excluded the unreachable deep-cavern demons and correctly included the kea).
  → `research/2026-09-12-dfhack-capability-checks.md` §5,
  `docs/AGENT-ARCHITECTURE.md` §4.
- **NOW, a single-writer violation already in production: `set_labor` races
  `autolabor`.** `set-labor` writes `unit.status.labors[code]` directly with
  no coordination, and `autolabor` (live on this fort) exempts only
  military-duty and burrow-restricted units, so a labor change on an ordinary
  citizen will probably be reverted on autolabor's next pass. It is also the
  **only** labor write that exists, and two unbuilt roles will want it.
  **Fix not yet designed.** → `decisions/DECISIONS.md` 2026-09-12,
  `research/2026-09-12-write-conflict-matrix.md`.
- **DONE 2026-09-12: the address leak is closed, with a mechanical guard that
  keeps it closed.** `tests/test_no_leaked_addresses.py` runs in the ordinary
  suite rather than as a per-clone git hook, and was proved by injecting a real
  violation and watching it fail. `working-archive/` deliberately still holds
  real addresses and is excluded, because rewriting a historical record would
  falsify it. Corrected on the way in: there were **3** distinct real
  addresses, not the "four" this row claimed. Original text follows.
- **Superseded. NOW, this public repo leaks internal addresses contrary to its
  own rule.** Four distinct private IPv4 addresses across roughly a dozen tracked
  files, plus `.internal` hostnames, including in `CLAUDE.md` itself, which
  is the file that states the rule. The `scripts/*.py` hits are fine (help
  text and examples). **History is already public, so fixing forward does not
  erase it**; the reason to act is that the rule is deliberate and the drift
  keeps growing, including from this session. Recommended: redact the prose
  and add a mechanical pre-commit guard, since a rule depending on every
  session remembering it has demonstrably failed. Needs the user's call, and
  `CLAUDE.md` is theirs to edit. → `Working.md`.

> **Rewritten 2026-09-10 (sixth pass, end of session).** **Uniboslan,
> "Ragwind," now has real structure**: a first room dug and a stockpile
> placed via `quickfort` blueprints (`blueprints/`), all 7 citizens alive
> and behaving normally, paused and quicksaved. This followed a longer
> arc the same session: the first fort, "Artobcatten," was lost when
> founding Uniboslan overwrote its save (DF's save-slot names turned out
> to be a shared pool, not per-fort); a Proxmox snapshot meant as a safety
> net before playing forward was blocked by cluster quorum (SRV-02 down,
> no QDevice, not this repo's to fix) and worked around with a verified
> `install_df.py backup` instead. A first pass at `check_reachable`/
> `get_connectivity_report` plus an experimental seed landmark were also
> built this session, then deliberately kept off `main` on their own
> branch, `perception-layer-experiments`, at the user's explicit request.
> Full narrative: `working-archive/Working_archive-2026-09-07.md`
> (`Working.md`'s own current handover is now the compacted summary),
> `decisions/DECISIONS.md` 2026-09-10.

- **DONE 2026-09-09/10: DF's built-in modern (Steam-style) graphics are
  working on VM 103, no third-party pack, and now genuinely complete.**
  Research confirmed no free official bundle exists
  (`research/2026-09-09-df-modern-graphics.md`) — but the user's own
  legitimately-purchased Steam copy (local install, DF 53.15) does, and
  `install_df.py graphics` transplants its module folders onto VM 103 over
  scp, never through this repo's git tree. The initial 8-module transplant
  (2026-09-09) missed two real modules that don't share the `_graphics`
  naming suffix — found 2026-09-10 via a full recursive manifest diff, not
  spot-checks: `vanilla_interface` (UI panel/chrome — the actual missing
  panel a user report and external search confirmed) and
  `vanilla_environment` (core terrain: walls/floors/water/fire — used
  throughout real fortress-mode play). `GRAPHICS_MODULES` is now 10
  entries; confirmed visually fixed. → `decisions/DECISIONS.md` 2026-09-09
  and 2026-09-10 rows, `Working.md`.
- **DONE 2026-09-10: the first fort was founded ("Artobcatten,
  Combinedchannel," `region2`), driven entirely through DFHack struct
  writes and simulated clicks** — the "Confirm" step that had blocked
  every attempt so far resolved as a timing/race condition (ran cleanly
  under gdb; root mechanism still unconfirmed). **Superseded 2026-09-10
  (fifth pass): its save was overwritten founding the second fort and is
  gone** — see the row below and `decisions/DECISIONS.md` 2026-09-10
  ("second fort was founded, but the first fort's save was lost").
  → `docs/DF-UI-AUTOMATION.md`, `Working.md`.
- **DONE 2026-09-10 (fifth pass): a second fort was founded, "Uniboslan,
  'Ragwind'," using the text-only sweep — but the first fort's save was
  lost as a side effect.** DF's save-slot names (`autosave 1`/`autosave 2`/
  `current`) turned out to be a shared generic pool, not scoped per fort;
  Artobcatten's save (`autosave 1`) got overwritten by Uniboslan's own
  autosave activity, confirmed via `md5sum`, no backup existed, no
  recovery path found. User chose to accept the loss and move forward with
  Uniboslan, now the one active fort, confirmed reloading correctly under
  normal systemd supervision. **Before founding any further fort: pull an
  `install_df.py backup` of the existing save first** — this install gives
  no guarantee an existing fort's slot survives a new one being founded.
  → `decisions/DECISIONS.md` 2026-09-10, `Working.md` handover.
- **DONE 2026-09-10: root cause of the map-navigation struggle found, and
  the headless-input limitation that caused it fixed.** `find_mm_*` vs
  `neighbor_hover_mm_*`/`warn_mm_*` confirmed as two different coordinate
  frames (the latter world-absolute, live-matched against
  `location.embark_pos_min/max`); `xdotool` real X11 input confirmed as
  the fix for map hover/click/panning, which DFHack's fake input can
  never drive in headless Xvfb. → `research/2026-09-10-embark-screen-rendering-and-coordinates.md`,
  `decisions/DECISIONS.md` 2026-09-10, `Working.md`.
- **DONE 2026-09-10: text-only sweep built and run, second-site candidate
  found, nothing committed.** `df-overseer-ui.lua` gained `embark-mode`/
  `leave-embark-mode`/`hover`; found live that `neighbor_hover_mm_*` only
  updates while `choosing_embark` is `true`. A raster sweep near the
  original Site Finder match found real land and a strong candidate:
  `sx=128 sy=84 ex=131 ey=87` (Temperate Conifer Forest, "Recommended
  size," no aquifer, deep soil, full minerals + flux; hostile goblins
  nearby as the one caution). → `decisions/DECISIONS.md` 2026-09-10,
  `Working.md` handover.
- **DONE 2026-09-10: fixed a Windows-specific SSH command-line truncation
  bug in `provision_vm.ssh_guest`/`install_df.remote()`**, found deploying
  the sweep tool above. Git's MSYS-linked `ssh.exe` silently truncated a
  long command-line argument to ~8182 characters when spawned by Python's
  `subprocess` rather than bash; large payloads now go over stdin
  (`input_data` param). `provision_relay.py` inherits the fix for free. →
  `decisions/DECISIONS.md` 2026-09-10.
- **DONE 2026-09-10 (sixth pass): Uniboslan's first room dug and a
  stockpile placed, via `quickfort` blueprints** (`blueprints/`, four
  files — the first entries in the "Blueprint library" scope item),
  anchored near the experimental seed landmark's coordinates. Applied
  headlessly via `quickfort run <file> -c x,y,z`, matching design
  commitment #4 rather than raw designation writes. Found live: the
  founding-message dialog silently blocks all citizen activity regardless
  of pause state; a downstair can't be designated on grass tiles; a plain
  floor dig beneath a completed stair never becomes a job unless the
  connecting tile is itself a matching stair type; the real job list is
  `df.global.world.jobs.list`, not what the research sketch guessed; and
  DF Classic's 2D engine does have real zoom (`[`/`]` keys), contrary to
  a wrong claim made mid-session. → `decisions/DECISIONS.md` 2026-09-10,
  `working-archive/Working_archive-2026-09-07.md`.
- **DONE 2026-09-10: `check_reachable`/`get_connectivity_report` built —
  the first real perception-layer code, not just bootstrapping.**
  `scripts/dfhack/df-overseer-connectivity.lua`, deployed via
  `install_df.py ui-install` (now generalized to deploy every
  `df-overseer-*.lua` file, not just one hardcoded name).
  `get_connectivity_report()` calls `warn-stranded.lua`'s own
  `getStrandedGroups()` via `reqscript` rather than reimplementing it,
  confirmed live against Uniboslan. `check_reachable()` is an explicit
  stopgap (raw unit ids, not landmark names) pending the landmark system
  (build order item 3). JSON output is deterministically key-sorted for
  free via DFHack's own C++ encoder, satisfying build item 4's requirement
  early. → `docs/PURPOSE.md` build order item 2, `decisions/DECISIONS.md`
  2026-09-10.
- **DONE 2026-09-10, explicitly experimental: seed landmark bootstrap.**
  User caught a real gap — `find_open_area`/`get_connectivity_report` have
  nothing to anchor to on a virgin embark, since burrows/buildings only
  exist once something's been dug or built, and the build order never said
  how the first landmark gets created. Also asked whether the model could
  instead just read a full 3D world representation; answered from this
  repo's own evidence rather than re-litigating (`evals/perception/`
  deliberately never built a full-grid arm, per the cross-domain research
  behind it). `scripts/dfhack/df-overseer-landmarks.lua` seeds one
  landmark ("Embark Site," citizen-position centroid — a wagon-based
  anchor was checked and ruled out empty) via `dfhack.persistent`,
  confirmed live to survive a full save/reload. User's framing: try it as
  an experiment, not a settled design. **Not** the real burrow/building
  enumeration + adjacency-graph system item 3 still calls for. →
  `docs/PURPOSE.md` build order item 3, `decisions/DECISIONS.md`
  2026-09-10.
- **DONE 2026-09-10: reusable menu-automation tool, replacing one-off Lua
  scripts per click.** `scripts/dfhack/df-overseer-ui.lua`
  (`install_df.py ui-install`, then `./dfhack-run df-overseer-ui
  <type|click TEXT|dump>`) plus a screen-atlas reference doc,
  `docs/DF-UI-AUTOMATION.md`, cataloging every DF menu screen driven so far
  with its confirmed fields and working/dead techniques. → `decisions/
  DECISIONS.md` 2026-09-10 row.
- **Live human viewing: done, both LAN and public, user-confirmed working
  end to end.** VM 103's `x11vnc` → reverse SSH tunnel
  (`install_df.py vnc-tunnel`, dedicated `permitopen`-restricted key) →
  relay VM's `websockify`/noVNC (`provision_relay.py webvnc`) → Cloudflare
  Tunnel (`provision_relay.py cloudflared`) → `https://dwarf-fortress.
  willsmith.nz` — confirmed live (`curl` returns HTTP 200, root redirects
  straight into the viewer). Relay is `df-colony-relay-01`
  (`<relay-vm-ip>`, Debian 12, home-lab's Proxmox pool). Feed is
  intentionally unauthenticated (`x11vnc -nopw`) but stays `-viewonly` —
  anyone with the link can watch, nobody can act. Linked live from
  `willsmith-portfolio/public/dwarf-fortress/index.html`.
  → `research/2026-09-09-reverse-vnc-relay.md`,
  `decisions/DECISIONS.md` 2026-09-09 rows, `Working.md`.
- **DONE 2026-09-11: authenticated personal-control VNC channel, deployed
  and confirmed live** — a second, fully separate x11vnc/tunnel/webvnc
  instance (real mouse/keyboard, `dwarf-fortress-admin.willsmith.nz`) gated
  by Cloudflare Access alone (email OTP, the user's own account only), no
  second password. Existing public view-only feed untouched and reconfirmed
  healthy throughout. Two live layers now exist on the one fort: public
  view-only, and this authenticated full-control channel for the user.
  → `decisions/DECISIONS.md` 2026-09-11 rows, `Working.md`.
- **Design commitment #1's absolute wording vs. its evidence base.** The
  core (no rendered map in the model's ongoing spatial reasoning) is
  well-evidenced and shouldn't be relitigated; the literal "not even a
  screenshot, ever" wording may be broader than what
  `research/2026-08-25-spatial-perception.md` actually tested (dense,
  continuously-updating game-world content over many turns, not a static UI
  menu or a one-off human debug glance). Queued for a `decisions/DECISIONS.md`
  entry on the user's own timing, not urgent. → `Working.md` handover.
- **If a write step fails oddly, check quorum before suspecting permissions.**
  The cluster has no QDevice and the second node is unwell, so a single node
  can drop below quorum and make every config write fail with an error that
  reads exactly like a permissions fault. `pvecm status` first, always.

## Next
<!-- Clearly in line, not yet started. -->

- **Whole-wiki snapshot, kept current incrementally** (agreed 2026-09-22, "not
  just yet"): one full pull storing each page's `revid`, then a VM 103 timer
  that reads MediaWiki's `recentchanges` feed and re-fetches only changed,
  moved or deleted pages, with a batched `revid` check as a backstop and a
  deliberate full re-pull on a DF version bump. Doctrine cites the `revid`,
  and pages that change get their citing entries flagged for re-reading, never
  auto-edited. Unverified first: anonymous `recentchanges` access and its
  retention on the DF wiki. The MVP ships a curated 20-30 page snapshot
  instead. -> `decisions/DECISIONS.md` 2026-09-22.

- **DF wiki lookup as a `dfmcp` tool for the Consultant and the Architect**,
  served from a local snapshot, not the open web, returning capped
  section-level excerpts (user's calls 2026-09-15). Fills the Consultant's
  `planned` `knowledge.wiki_lookup`. Follows the queue wiring, which
  establishes server-side (non-DFHack) tools. Then **`ask`/`answer` records**
  so advisors can consult the Consultant without spending their own context.
  → `decisions/DECISIONS.md` 2026-09-15 "DF wiki access" and "Advisors may ask
  the Consultant" rows.

- **Game figures database and calculators** (user's call 2026-09-17): the
  numbers the wiki lookup would only quote as prose (growth times, seed
  return per processing method, drinks per plant) kept as structured rows,
  each with its source, game version and a prior/verified status, plus pure,
  unit-tested calculators served as `dfmcp` read tools (e.g. how much of a
  crop can be cooked without seed stock falling). Seeded first from the
  install's own raws (version-exact), then from research, then from the
  fort's own measurements. Complements the wiki lookup, does not replace it.
  **UPDATED 2026-09-18: this is now a real design, not a sketch**, see the
  Now-bucket production-model item above; the design's own `status`/
  `source_ref` columns are this item's prior/verified vocabulary, made
  concrete. → `decisions/DECISIONS.md` 2026-09-17 "Game figures belong in a
  database", 2026-09-18 rows.

- **Live-view ingest: explicitly shelved, user's call 2026-09-12** (moved
  here from "explicitly not priority right now," distinct from "blocked" —
  it's not waiting on anything technical, the user chose not to prioritize
  it). Screenshot capture itself is built and verified on VM 103
  (`install_df.py stream`); the only missing piece is an R2 bucket + API
  token, cost-checked at $0/month for this traffic shape. Exact setup steps
  and what to do once revisited are in `Working.md`'s live-view
  section. → `decisions/DECISIONS.md` 2026-09-08 row.
- **Spike B.** The `bpg` OpenTofu config with no `ssh` block, its absence
  being the test of whether a pool-scoped token can drive it end to end.
  Spike A (`status` → `fetch-image` → `build-template` on the new token)
  passed clean 2026-09-08, which also discharged home-lab's Phase H.
  → `research/2026-09-08-provisioning-recommendation.md` §7.4, §11.
- **Not extracting a shared provisioning library yet**, decided 2026-09-08: a
  second sandbox project will come one day but none is planned. Adopting an
  externally maintained provider is not the extraction that row declines, and
  would discharge it permanently. → `decisions/DECISIONS.md` 2026-09-08 rows.
- **Re-record the new identity's live scopes into a fresh
  `infra/local.proxmox-access.md`.** The existing file (gitignored) describes
  the retired `df-overseer@pve` identity, read back from the API on
  2026-08-27; the new identity's pool-fence proof (`200` in-pool, `403`
  outside) currently lives only in home-lab. This repo has no equivalent
  record of its own once the old identity retires. → `Working.md` handover.
- **DONE 2026-09-11: `cpu: host` → `x86-64-v2-AES`**, applied to VM 103 for
  real and verified (`cpu=x86-64-v2-AES` confirmed by read-back, fort
  reloaded and confirmed identical afterward: same citizens, same save
  slot, same year). Surfaced a real incident along the way: the cold
  stop/start needed to apply it hit cluster quorum loss (SRV-02 down, no
  QDevice) blocking VM start entirely, not just snapshots as previously
  documented — resolved once the user restored quorum at a root shell;
  not this repo's to fix.
  → `decisions/DECISIONS.md` 2026-08-28 row, `Working.md`.
- **UPDATED 2026-09-11, audited properly (not file-listing guesswork):
  build order items 2-8 are DONE, not "next to build."** `check_reachable`/
  `get_connectivity_report` (item 2), the real landmark system (item 3),
  `get_overview` (item 4), `get_diff_since` via `eventful` (item 5, live
  eventful-callback firing genuinely verified, not just the registration
  calls), `find_open_area` for built terrain (item 6), `find_chokepoints`
  (item 7, first half — `rank_candidate_sites` genuinely blocked, needs
  `resource_summary`/threat data that don't exist yet; **its scoring
  formula's spec now also covers "site the brewery near the farming room"**,
  proximity to another *named room by kind*, not just raw resources —
  addendum added 2026-09-11, `research/2026-08-25-spatial-perception.md`
  §6, before this gets built so it isn't missed), and `get_stuck_jobs`
  (item 8) are all built and verified live against the real fort, all 8
  commits pushed to `origin/perception-layer-experiments`. **Superseded
  2026-09-12: the branch-merge question below is resolved.**
  `perception-layer-experiments` merged into `main` (`f078bf8`, six real
  conflicts resolved deliberately, not auto-accepted); the branch and its
  worktree are deleted. → `Working.md`, `decisions/DECISIONS.md` 2026-09-11
  rows.
- **DONE 2026-09-11: the coordinate-resolution gap found by the first
  autonomous-play attempt is closed** — `build_open_area`/`build` (fused
  resolve-and-act, coordinate never surfaced) on `df-overseer-openarea.lua`,
  `perception-layer-experiments`. Produced the project's first fully
  autonomous, tool-derived, end-to-end fort mutation: a real second
  stockpile now exists on Uniboslan, independently verified against the
  live VM. Also found (empirically, not by inspection) that this doesn't
  extend to digging new rooms — `find_open_area` finds already-open space,
  not diggable rock. **Corrected 2026-09-11, user caught it**: this is
  *not* build order item 9 (that's still "find already-open space," just
  in irregular natural caverns, not rectangles — a different problem).
  It's a genuinely new, unspecified gap: nothing in the whole research
  spec finds a candidate region of *solid* rock/soil to dig into, even
  though `designate_dig`'s own sketch assumes something upstream supplies
  that. See the item below. **Superseded 2026-09-12: merged into `main`
  with the rest of `perception-layer-experiments`, the merge-timing
  question resolved.** → `decisions/DECISIONS.md`
  2026-09-11 ("Closed the coordinate-resolution gap..."), `Working.md`.
- **NEW 2026-09-11, found correcting the row above: no tool anywhere in
  the research spec finds a candidate region of *solid, diggable*
  rock/soil.** `find_open_area` (both `terrain="built"` and the unbuilt
  `terrain="cavern"`) only ever searches *walkable* tiles — confirmed by
  re-reading its own spec, `find_open_area`'s cavern variant is "take the
  set of walkable tiles... sharing a getWalkableGroup id," not solid rock.
  `designate_dig(shape, pos, dims)` is sketched as the actual dig-action
  tool and its own note says "where to dig" should be "closed-loop with
  the landmark system" — but nothing supplies that `pos`. This is
  genuinely unspecified, not just unbuilt: needs something like
  `find_diggable_area(w, h, z, near, radius_tiles) -> ranked candidates`,
  the inverse of `find_open_area` (non-walkable/solid tiles instead of
  walkable ones), before "dig a new room" can close the loop the same way
  today's stockpile-placement fix did. **Second constraint, same
  conversation**: a candidate is only valid if it *borders* the fort's
  existing walkable network (same `getWalkableGroup` `find_open_area`
  already reports) — a mining job needs a dwarf on an adjacent walkable
  tile to dig from, so an unreachable candidate would silently never
  become a job, the exact failure class this project already paid for
  once (`decisions/DECISIONS.md` 2026-09-10, the stair-connectivity dig
  bug). **Corrected right after, user caught this overstatement too**:
  isolated doesn't mean invalid, just "needs a connector tunnel dug too" —
  a normal pattern this project already uses (the original room dig was
  entrance+connector+room, three blueprints). v1 can reasonably return
  only directly-adjacent candidates; a fuller version should score
  non-adjacent ones by connector-tunnel cost and let the model choose,
  not hard-code isolation as a validity failure. →
  `decisions/DECISIONS.md` 2026-09-11 ("Closed the coordinate-resolution
  gap..." correction), `research/2026-08-25-spatial-perception.md`.
- **DONE 2026-09-11: `find_diggable_area` built and live-verified**
  (`scripts/dfhack/df-overseer-diggable.lua`, `perception-layer-experiments`,
  commit `f741cfc`, not pushed), closing the gap the row above found. Enum
  names verified against the actual installed DFHack source, not memory; v1
  scope matches the corrected spec exactly (adjacent-only candidates,
  connector-cost scoring left for a fuller version). **Live-verified against
  VM 103**: a correct negative near the surface embark site (only
  TREE-material walls nearby, correctly excluded) and a correct positive
  underground near Stockpile #1 (5 real ranked SOIL candidates). Still no
  `designate_dig` action tool to actually act on a candidate — the natural
  next piece. **Merged into `main` 2026-09-12** with the rest of
  `perception-layer-experiments`. → `decisions/DECISIONS.md` 2026-09-11,
  `Working.md`.
- **DONE 2026-09-11: `dig_diggable_area`/`dig` built, a real bug found live,
  root-caused, fixed, and re-confirmed working end to end.** First live test
  designated real tiles correctly but at an unreachable location — no dwarf
  ever claimed the job. Root cause (confirmed against quickfort's own docs,
  not guessed): `-c` anchors a blueprint's **top-left**, not center, but the
  code was passing the candidate box's computed *center* — silently
  shifting every real dig/build by `(floor((w-1)/2), floor((h-1)/2))` tiles
  from the box actually validated as reachable. **The identical bug was in
  `build_open_area` too** (Stockpile #2 worked anyway, only by luck — its
  candidates sit inside broadly open space). Both fixed: pass the box's real
  top-left to quickfort, not its center. Re-tested live after the fix:
  designation landed at the correct spot, unpausing produced real claimed
  `Dig` jobs almost immediately, and all 41 designated tiles (this run's 25
  plus leftover from the buggy run) were fully dug by the next check — the
  loop is genuinely closed now, not just mechanically plausible.
  `df-overseer-diggable.lua`'s fix committed (`2d0eb7b`, not pushed at the
  time); `df-overseer-openarea.lua`'s fix applied but left uncommitted,
  matching that file's own pre-existing uncommitted state, flagged in its
  own comment for whoever reconciles it. **Superseded 2026-09-12: both
  files, fixes included, are merged into `main` and pushed** as part of
  `perception-layer-experiments`'s merge (`f078bf8`); the reconciliation
  question the comment flagged is resolved by the merge itself. →
  `decisions/DECISIONS.md` 2026-09-11 ("Root cause found and fixed..."),
  `Working.md`.
- **Measure a running fort's memory over time**, now that one exists
  (`decisions/DECISIONS.md` 2026-09-10, "First fort founded"). Worldgen's
  peak (561 MB) is measured; a fort at year 5 with 100 dwarves is not, and
  this would also give a real number for `TimeoutStopSec`'s quicksave
  margin. → `docs/PURPOSE.md` open questions.
- **DONE 2026-09-11: compliance eval harness built and run at full scale
  against two providers.** `evals/compliance/`, mirroring `evals/perception/`'s
  structure — a ~170-rule synthetic doctrine pool, nested by rule count,
  graded mechanically. `deepseek-chat`'s full sweep is a clean finding:
  perfect-response rate collapses to 0% at n≥40, concentrated almost entirely
  in `required_word` compliance (20.6% at n=160 vs. `banned_word`'s 100%).
  `claude-opus-5`'s sweep found and fixed a real harness bug (`max_tokens`
  too low for adaptive thinking at high N, producing empty responses) but
  **cost $9-13 in the process** — the user's call afterward was to stop
  further Opus spend and make DeepSeek the harness's default provider
  (`--provider anthropic` is now opt-in only). → `decisions/DECISIONS.md`
  2026-09-11 (three rows), `Working.md`, `evals/compliance/README.md`,
  `research/2026-08-25-learning-architecture.md` §7 item 1.
- **Next, deliberately not done without asking first**: a genuinely clean
  `claude-opus-5` collapse curve (more `--repeats`, no empty-response
  artifacts now that `max_tokens` is fixed) — real value, but the cost that
  produced this session's finding is exactly why it needs explicit go-ahead,
  not a default action.

## Later
<!-- Real, worth tracking, but genuinely further out or gated on scale/decisions not yet made. -->

- **Resource claims, proposal variants and computed bundles** for arbitrating
  competing proposals (user's call 2026-09-15). Research brief first
  (resource-constrained scheduling, portfolio selection, inventory and
  logistics); gated on stock and labor reads existing.
  → `decisions/DECISIONS.md` 2026-09-15 "Resource claims" row.

- **`find_open_area` (cavern terrain).** Genuinely hard, deliberately last
  in the build order. → `docs/PURPOSE.md` build order item 9.
- **DONE 2026-09-11: mechanical prediction grading built** (`learning/predictions/`,
  grouped with `learning/ledger/` under one parent 2026-09-12 — real code
  coupling, `predictions/grade.py` imports `ledger.schema`/`ledger.store`
  directly, not just thematic — done while `predictions/` was still
  untracked so it cost a `git mv` instead of a rename later).
  A prediction's `signal` is a dotted path validated at write time against
  `ledger.store.field_source` (refuses anything that doesn't resolve to a
  `MECHANICAL`/`DERIVED` ledger field); grading reads only the ledger row and
  a closed predicate-op vocabulary, never the prediction's own prose.
  **Real, stated limitation**: only ledger-backed signals work — the fort
  dossier (mid-fort state) the research spec also names is still uncoded, so
  the design doc's own "food stores" example can't be expressed yet.
  → `learning/predictions/README.md`, `decisions/DECISIONS.md` 2026-09-11,
  `research/2026-08-25-learning-architecture.md` §7 item 3.
- **The fort ledger's write path** for the remaining fields waits on the
  perception layer existing. → `learning/ledger/README.md`.
- **Re-run the perception eval against real briefings** once `llm-brief.lua`
  exists, replacing today's hand-authored 15-landmark fixtures with the
  actual lossier generator. → `docs/PURPOSE.md` build order item 1's caveat.
- **NOT DOING 2026-09-18: seeded counterfactual rerun harness.** The user's
  call: "i'm not planning on reusing the same seed over and over", so DF
  replay determinism also stays unverified on purpose. It was the only real
  control arm for "doctrine improved outcomes", so those claims stay
  correlational, and the retrospective court plus per-type acceptance
  criteria carry the weight instead. → `decisions/DECISIONS.md` 2026-09-18,
  `research/2026-08-25-learning-architecture.md` §7 item 7.
- **Host-reboot survival test**, re-scoped to whichever VMID the current
  rebuild produces (VM 104 no longer exists). Complicated now by `citadel`'s
  missing QDevice: a reboot of `SRV-01` while `SRV-02` is also down would be
  a real inquorate-cluster test, not just a VM-restart test. Needs the
  user's go-ahead first either way (destructive/hard-to-reverse actions
  rule). → `working-archive/Working_archive-2026-09-07.md`, "Host-reboot
  survival is still unverified".
- **DONE 2026-09-12: the driving-brain choice decided — `openclaw`.**
  User's explicit call, not the originally-planned empirical 30-day
  survival test: `openclaw`'s multi-agent support (flagged as a candidate
  differentiator back on 2026-08-27) is exactly the wanted shape — many
  agents, each a single responsibility, each free to run a different model.
  Closes the 2026-08-25 deferred item. **UPDATED 2026-09-12: the
  multi-agent-by-task decomposition is now designed** (not built) in
  `docs/AGENT-ARCHITECTURE.md`, and it is a different shape from the
  patrol/military, construction/placement, economy split the 2026-08-27 row
  sketched: those became *advisory* roles with no write authority, because
  the same day settled on a single actor. Also settled the same day:
  `openclaw` is the **sole** host, `hermes-agent` is not used even for the
  Overseer. **UPDATED 2026-09-12: the MCP seam is built** (`dfmcp/`, six
  modules, 136 tests), so this row's "still unbuilt: the MCP seam, which
  remains the real blocker" no longer holds. What openclaw now needs is
  configuration against a real endpoint, not a missing dependency.
  → `decisions/DECISIONS.md` 2026-09-12 rows (also 2026-08-25, 2026-08-27).
- **First display to build (game view vs. chronicle e-ink), and the
  time-sliced adventure-mode design.** → `docs/PURPOSE.md` Open Questions.
  (Loop shape and the multi-agent split are no longer open here: both are
  answered by `docs/AGENT-ARCHITECTURE.md`, §4 and §3 respectively.)
- **Dwarf/labor management (`get_unit_status` + labor-assignment action
  tools), not Dwarf Therapist.** A real gap, found 2026-09-11 by checking
  rather than assuming: `docs/PURPOSE.md`'s numbered build order (0-9) is
  entirely spatial/perception primitives — nothing in it covers labor,
  skills, happiness, or mood, even though `get_unit_status` is specced in
  `research/2026-08-25-spatial-perception.md` §5. Dwarf Therapist itself
  doesn't fit this project (GUI-only, needs a rendered window; the fort
  runs headless and unattended); DFHack's own equivalent, `manipulator`,
  is tagged `unavailable` on this install (same v50-transition breakage
  `memory/dfhack-environment.md` already tracks elsewhere). The shape
  that does fit: `get_unit_status` (perception, `dfhack.units`) plus a
  thin `set_labor`-style action tool (design commitment #2 — code does
  the mechanics, model does the judgment), with `autolabor` (available,
  headless, no interaction needed) as a sensible baseline underneath so
  the agent isn't re-deciding routine hauling/mining balance every turn.
  → `decisions/DECISIONS.md` 2026-09-11.
- **DONE 2026-09-11: first slice built and verified live** —
  `scripts/dfhack/df-overseer-labor.lua` (`unit-status`, `labors`,
  `set-labor`), `dfhack.units`-backed, verified against Uniboslan's real
  citizens rather than assumed from docs. The judgment half (an actual
  labor-assignment policy) is still unbuilt.
  → `decisions/DECISIONS.md` 2026-09-11, `Working.md`.
- **DONE 2026-09-11: `autolabor` enabled on Uniboslan as the baseline**,
  user's go-ahead — confirmed genuinely on (not just the enable message),
  confirmed it persists via a real quicksave, explicitly leaves
  military/burrow-assigned dwarves untouched. **CORRECTED 2026-09-12: that
  exemption is real but narrow, and the parenthetical this bullet used to
  carry ("so it doesn't blanket-override the manual primitives above") was an
  overstatement.** `set_labor` writes `unit.status.labors[code]` directly with
  no coordination, so on an *ordinary* citizen it races autolabor and will
  probably lose on autolabor's next pass. Verified at source, not taken on a
  subagent's word. → `decisions/DECISIONS.md` 2026-09-12,
  `research/2026-09-12-write-conflict-matrix.md`. Found along the way: `quicksave` rotates
  forward through the `autosave N` slot pool each call rather than
  overwriting in place — re-read `cur_savegame.save_dir` fresh each time,
  don't assume a previously-checked slot name is still current.
  → `decisions/DECISIONS.md` 2026-09-11, `Working.md`.

## Explicitly not doing
<!-- Deliberate non-goals, so they don't get re-proposed. -->

- **The model is never shown a rendered map.** Not ASCII, not a tile grid,
  not a screenshot; every spatial fact is computed in code and asserted in
  text. Hard commitment, not a preference. → `docs/PURPOSE.md` design
  commitment #1, `research/2026-08-25-spatial-perception.md`.
- **Headless/terminal DF via `PRINT_MODE:TEXT`.** Doesn't exist since v50 in
  either build; "Classic mode" is still SDL. → `decisions/DECISIONS.md`
  2026-08-25 row.
- **DFPlex for multiplayer.** Dead for v50+, and irrelevant anyway: agents
  need structured state over shared RPC, not a rendered view.
  → `decisions/DECISIONS.md` 2026-08-25 row.
- **Adventure mode concurrent with an active fortress.** Playing any mode
  locks the world; time-sliced visiting (agent retires → human adventures →
  agent unretires) works instead and needs no scripting.
  → `decisions/DECISIONS.md` 2026-08-25 row.
- **An ASCII-map control arm in the perception eval.** Would require
  building the rendered-map generator commitment #1 already rules out, and
  the comparison it would produce is already settled by the cited evidence.
  → `decisions/DECISIONS.md` 2026-08-26 row.
