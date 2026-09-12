# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.


## Agent architecture design phase — started 2026-09-12

The design/research phase the handover below anticipated, which then produced
working code. **Current state: design written and revised against four research
briefs; `agents/` and `mcp/` built with 26 passing tests; two safety detectors
built, one live-verified working and one inconclusive.** The MCP server itself,
the Sentry, Triage, the queue, snapshots and playbooks are not started.

### START HERE next session, in priority order

Everything below this block is detail and reasoning. This is the brief.

1. **Build the MCP server.** It is the one hard blocker: nothing else can
   progress without it, and every design requirement it must satisfy is already
   settled and written down (server-side allowlist enforcement, one token per
   role, one persistent DFHack RPC connection rather than shelling out per call,
   batch a cycle's reads into one suspend window). `mcp/registry.py` and
   `mcp/roles.py` are the authorisation half and are done and tested; what is
   missing is the transport and the DFHack client.
2. **Then one supervised end-to-end cycle**: the Overseer making a single real
   decision through the seam. **This is the first thing that would advance the
   project's actual thesis**, as opposed to its foundations. Nothing today did.
3. **Fix the `set_labor`/`autolabor` race.** Small, and it is a single-writer
   violation live in production right now.
4. **The breach question**, opportunistically: wait for rain or an animal
   fording water rather than deliberately flooding the fort.

**Do not start by writing more design.** Today produced a great deal of it and
the ratio is already uncomfortable: a 14-section architecture over a tool surface
that is 18-of-25 read-only. The architecture doc is a target, not a plan.

**CORRECTED 2026-09-12, user caught this:** an earlier version of this brief
said openclaw's VM needed the `home-lab` session before it could be provisioned.
**Wrong. Provisioning is entirely this repo's own.** `scripts/provision_vm.py
clone` exists, the pool-scoped token holds `VM.Clone`, and `.env` carries
`PVE_NODE`, `PVE_POOL`, `DF_TEMPLATE_VMID` and `DF_VMID`. That is the whole point
of the sandbox pool. Two separate things had been conflated:
- **Provisioning: ours, and unblocked right now.** The IP allocation that *was* a
  genuine prerequisite is already done and written on home-lab's side.
- **Recording it: theirs, and only AFTER the fact.** What is owed is the
  `guests:` entry in `inventory/hosts/SRV-01.yaml` with the real VMID, plus
  `inventory/services.yaml` if a service moves. A post-hoc record, not a gate.

There is a real argument for provisioning while a `home-lab` session is awake, so
the inventory obligation is discharged immediately rather than being carried by a
handover.

**One thing still needing the user rather than a session:** nothing. The
address-leak cleanup and its `CLAUDE.md` edits were authorised 2026-09-12 and
delegated.

### Done this session

- **[`docs/AGENT-ARCHITECTURE.md`](docs/AGENT-ARCHITECTURE.md) written**, the
  full design: 8 principles, 5 components (2 of them code with no model in
  them), a 6-role roster, the communication protocol, the information
  architecture, graded urgency, write authority, reliability, recording and
  learning, modularity, explicit non-goals, and open questions. It is a design
  artifact and says so at the top.
- **Extensive new rows in `decisions/DECISIONS.md`, all dated 2026-09-12**
  (`grep -c '^| 2026-09-12 |'` for the live count; a hand-maintained number
  here drifted three times in one session, so it is deliberately not restated). The doc is the design; the rows
  are why each call was made, including the ones that were later corrected.
- **`ROADMAP.md` updated**: two new Now items (the architecture, and the MCP
  server as the standing blocker), and three stale items corrected where the
  design closed them.
- **`agents/` scaffolding built**, the first non-document artifact of this phase:
  `ROSTER.yaml` (the single file you edit to change the roster), a `README.md`
  stating the file contract, full three-file sets (`role.md`, `tools.yaml`,
  `model.yaml`) for the three enabled roles, and charters for the three
  disabled ones. **Tool allowlists reference real `TOOLS.yaml` ids**, each
  tagged `exists` or `planned`, so the file cannot silently imply a capability
  this project lacks. The disabled roles deliberately have **no** `tools.yaml`
  or `model.yaml`, for the same reason, and each charter names exactly what
  blocks it plus the traps for whoever builds it.

### The shape that was settled, in one paragraph

One actor (**Overseer**, sole writer, strongest model). Read-only
**specialists** (Architect, Quartermaster, Marshal, Consultant, Chronicler)
that may call exactly one write tool, `propose`. Two code components: a
**Sentry** (reflexes, graded escalation, status publishing) and **Triage**
(diff plus thresholds each heartbeat, so a quiet cycle costs zero tokens).
Latency is answered by **playbooks executed as code**, not by more actors.
Communication is one append-only queue that is channel, audit log and
write-ahead log at once; writes are tool calls with typed fields, reads render
as XML; no peer-to-peer chat in v1. One snapshot per cycle, per-role
projections, three information tiers. Confidence is **tool-stated for facts**
(`MECHANICAL`/`DERIVED`/`HEURISTIC`) and **measured from graded predictions**
for proposals; self-reported confidence is never a decision input.

### Research: all four briefs back, all folded into the doc and register

1. `research/2026-09-12-write-conflict-matrix.md` — **back**, findings below.
2. `research/2026-09-12-openclaw-primitives.md` — **back.** The design's
   biggest risk cleared: **per-agent models and per-agent tool scoping are real
   features**, so principle 8 is enforceable and §11 stands. But four
   constraints landed: **no hard spend cap in the host** (budget enforcement is
   ours plus provider-side caps), **fan-out is lane-serialised** at roughly 30s
   per target so waking five specialists may cost minutes, **the only external
   push wake is an authenticated HTTP hooks endpoint** (that is how the Sentry
   reaches the Overseer), and **host crash recovery does not cover external
   side effects**, which makes the write-ahead queue the actual recovery
   mechanism. Also **corrected a 2026-08-25 register claim**: openclaw's
   exponential retry backoff does not hold for heartbeat. Recorded as
   reported-by-brief, not independently confirmed here.
3. `research/2026-09-12-multi-agent-architecture-prior-art.md` — **back.**
   No-peer-chat **survived review** on convergent multi-source evidence, with
   one doctrine-backed v2 relaxation identified (read-only cross-advisor
   visibility without authority). Produced the best reframe of the session:
   **this is a blackboard system and we had rebuilt only a third of one**; the
   missing piece is an **explicit advisor scheduler**, now named inside Triage.
   Calibration method settled: Brier plus a coarse reliability diagram now,
   track-record weighting next, reference-class forecasting explicitly
   deferred.
4. `research/2026-09-12-dfhack-capability-checks.md` — **back. All six settled
   from source** at the matching version tag (53.16-r1.1), five with high
   confidence. Frame cap: **yes**, but it slows agent tool calls too, because
   DFHack's suspend window is tick-gated, so the throttle tier is a latency
   trap and pausing may actually beat it (unmeasured). Overlay: **yes** and
   headlessly drivable. **`dfhack-run` concurrency: safe, unordered,
   tick-gated**, which **kills the throughput argument for partitioning write
   authority** and also source-confirms the root cause of the previously
   unexplained 45-80s command delay. Priorities: 1-7 for digs, **list position
   for work orders** (no priority field exists). Wake vocabulary: **five of
   nine real; `breach` has no signal at all, and `hostile_detected` only fires
   on registered invasions**. `dfhack.persistent`: no internal locking, 7
   integer slots per entry, whole-file rewrite per save.

### Findings already in from the write-conflict audit

- **`set_labor` already races `autolabor` on ordinary citizens.** Verified at
  source (`df-overseer-labor.lua` writes `unit.status.labors[code]` directly,
  no coordination), not taken on the subagent's word. autolabor exempts only
  military-duty and burrow-restricted units, so the exemption is real but
  narrow. `ROADMAP.md`'s parenthetical claiming autolabor "doesn't
  blanket-override the manual primitives" was an overstatement and is
  corrected in place. **This is a single-writer violation that exists in
  production today**, before any roster is built. **Fix not yet designed.**
- **The Quartermaster and Chronicler roles have essentially no tool surface.**
  Neither manager work orders nor stockpile settings (filters, thresholds,
  links) have any tool in this repo, and DFHack's `stocks`/`workflow` are
  tagged `unavailable` on this install, so the "work orders plus stockpile
  settings is a disjoint write domain" hypothesis is **untestable rather than
  confirmed**. No tool writes a chronicle entry anywhere.
- **18 of 25 existing subcommands are pure reads**; only 7 mutate (3 via
  `quickfort -c`, 1 direct labor write, 3 via the UI input path). The three
  quickfort mutators are cleanly sliceable and mutually disjoint by
  construction; the three UI-path writers are the least sliceable of all,
  since their mutation target is whatever screen happens to be focused.
- **Two read-only tools share one unpartitioned `_G` table** across all
  callers: a shared-resource hazard for concurrent *readers*, even under a
  single writer.

### Next concrete step

**All four briefs are in and fully folded into `docs/AGENT-ARCHITECTURE.md`,
`decisions/DECISIONS.md` (25 rows today) and `memory/dfhack-environment.md`.
The design is no longer the blocker: the tool surface is.** Three things gate
any build, in this order.

1. **The MCP server still does not exist**, and it needs per-role identity and
   scoping designed in from the start. **Topology decided 2026-09-12 (user
   confirmed both halves): openclaw gets its own new VM on SRV-01; the MCP
   server and the Sentry stay on VM 103 with DF**, because DFHack's RPC socket
   is unauthenticated and must not cross the network. MCP over HTTP on the
   tailnet, never public. **Two requirements recorded before the server exists,
   deliberately**: the allowlist is enforced **server-side** (openclaw's own
   per-agent scoping is defence in depth, not the boundary, since client-side
   enforcement is not enforcement), and **role identity is a credential, one
   token per role**, never a self-declared header, or the Architect could
   assert it is the Overseer and obtain write tools. → `docs/AGENT-ARCHITECTURE.md`
   §13.

   **IN PROGRESS:** the transport-independent half is being built now in an
   isolated worktree: `mcp/registry.py` (loads `TOOLS.yaml`, canonical tool ids,
   preserves each tool's own verified/unverified status) and `mcp/roles.py`
   (resolves `ROSTER.yaml` plus per-role allowlists, with **hard load-time
   errors**, notably that any role other than `sole_writer` holding a mutating
   tool fails to load). Includes rewriting the three `tools.yaml` files from raw
   signature strings to canonical ids.
2. **DECIDED: v1 enables three roles, Overseer plus Architect plus Consultant**
   (user's call 2026-09-12, over this session's narrower recommendation of
   Overseer alone). These are the three whose tools exist. Quartermaster,
   Marshal and Chronicler keep charters and directories but stay disabled, so
   enabling one is a config change. **Consequence to carry forward: the
   advisor scheduler is load-bearing from day one**, not at some future scale,
   because with three agents the host's ~30s-per-target send serialisation
   shows up immediately.

3. **UPDATED: both safety detectors are now built and landed, and neither has
   ever been run.** `scripts/dfhack/df-overseer-threat.lua` (`scan`) and
   `scripts/dfhack/df-overseer-breach.lua` (`check`), plus their `TOOLS.yaml`
   entries, both tagged `live_deployed: false` / `verified: unverified`.
   Reviewed here rather than accepted on report: coordinate discipline is
   correct and both carry the `--@module = true` guard.
   **THE THING TO KNOW: the breach detector may be inert.** Every observed use
   of `block.flags.update_liquid` in the installed build's shipped scripts
   *sets* it and nothing reads it, so whether DF's own simulation raises it
   during natural liquid movement is unverified. Its cheap stage-1 trigger
   depends on that flag. **Until settled live, treat flood response as covered
   by nothing, exactly as before the detector existed**, because a detector
   that never fires invites the same false confidence `unit-status hostile`
   already cost this project. Also corrected along the way:
   `df.global.world.flows` does not exist, and this session had repeated that
   error into the design doc and a role charter; all corrected, with a §10
   correction appended to the research brief.
   **LIVE VERIFICATION DONE 2026-09-12** (user granted VM authority; fort
   saved and backed up first, health identical before and after, 15 citizens,
   0 wounds, re-paused and confirmed).
   **Threat detector: VERIFIED WORKING on both motivating failures.** `scan`
   returned a fox and a weasel, both admitted purely by shared walkable group
   with no danger flag; and the two `DEMON_4` units that DO have
   `isDanger`/`isGreatDanger` set were correctly absent, confirmed by direct
   raw query rather than by trusting the scan's silence (walkable group 0,
   109-115 tiles from any landmark). Reachability gates admission, flags do
   not. Both documented failures corrected in one tool.
   **Breach detector: INCONCLUSIVE, so treat flood response as still covered
   by nothing.** `update_liquid` was set on zero of 26,784 blocks on all 11
   polls including through an 85s unpaused window, but the map's water is
   fully settled (`flow_size=7`), so this cannot distinguish "DF never sets
   it" from "DF sets it only on change, and nothing changed". The limits
   (no breach, no dig, no magma) deliberately forbade creating the one
   condition that would settle it. Stage-1 cost measured and cheap: ~0.057s
   CPU for the full block scan. Future route that respects the limits: an
   opportunistic test during rain or an animal fording water.
   **One real bug found and fixed**: `designation.liquid_type` is a Lua
   boolean, not the `df.tile_liquid` enum, so the magma comparison was always
   false and severity could never reach `critical`. Fixed with a deliberate
   dual check, because this install's own `spawn-liquid.lua` hedges the same
   field both ways.

   Superseded text, kept for the reasoning: **two safety detectors did not
   exist and were required work, not polish.**
   **A breach poller**: no DFHack event or announcement type exists for water
   or magma breach at all (a checked negative), so **flood response is
   currently covered by nothing**, and breach is among the fastest
   fort-killers. **A real hostile detector**: `onInvasion` fires only for
   registered invasions, not ambushes, thieves, or wildlife turning
   aggressive, which is the *event layer* having the same blind spot as the
   already-known-unreliable polling signal. Until both exist, the Marshal has
   no trustworthy trigger to write playbooks against.

Also now more urgent than it looked: the **`set_labor`/`autolabor` race**, since
it is the only labor write that exists and two of the four unbuilt roles will
want it.

**Live checks.** The `Core::Update`-while-paused question is **settled, from
source and confirmed live, 2026-09-12: pausing does not stall tool calls.** Ten
round trips against the paused fort all landed between 0.66s and 1.28s, no
stall, tick counter correctly static, fort verified paused before and after and
never unpaused. **Then the user corrected the conclusion drawn from it**, and the
correction is the durable part: the unit is **game time elapsed per decision**,
not wall-clock latency. Game time per cycle is roughly **`f·T + k` ticks** (`f`
frame cap, `T` thinking seconds, `k` tool calls), so lowering `f` shrinks the
thinking term linearly down to a `k`-tick floor. **Throttling does buy thinking
time**; the wall-clock price is paid by the human watching, not the fort. Pause
is the only lever reaching zero. **Choose on cycle shape, not urgency**:
think-heavy cycles throttle well, call-heavy cycles should pause instead. And a
free optimisation nobody had spotted: all suspenders pending at once are
serviced in **one** window, so `k` concurrent calls cost ~1 tick versus ~`k`
sequential, which is a game-time argument for the single-snapshot read pass on
top of the consistency one.
→ `research/2026-09-12-dfhack-capability-checks.md` §9,
`docs/AGENT-ARCHITECTURE.md` §6. **Two remain deliberately unrun, user's call to defer**: whether the
frame cap survives loading a different save in one process (needs a save load on
the live fort, and this project has already lost one fort's save, so not done
casually), and whether an overlay widget renders in the headless Xvfb/VNC
pipeline (only matters if the status banner goes inside the game rather than
beside the stream, and the outside-the-game route is recommended precisely
because it cannot perturb the fort).

### OPEN home-lab obligation: openclaw's VM needs an IP allocated first

**Not yet triggered, deliberately raised early.** The decided topology needs
**one new VM on SRV-01** for `openclaw`. Nothing is created yet, so nothing in
`home-lab/inventory/` is currently wrong, but per this repo's upstream
obligation the IP must be allocated through `home-lab/inventory/ips.yaml`
**before** it is assigned. Skipping that step is exactly how a DF VM's address
came to be in use for a week while registered nowhere (`CLAUDE.md` names the
specific case; deliberately not repeated here, see the redaction note below).

**Routed 2026-09-12 to the live `home-lab-03` session** (this repo is not
authorised to edit home-lab). **Answered:** SRV-01 has comfortable headroom for
one more small guest (checked live: several GB RAM free, moderate load), and its
read is that this need not wait on SRV-02's stability since the two hosts are
unrelated here. **Address: user's call is to stay in the existing 200+ block
rather than reuse the freed `.157`.**

**CLEARED and ALLOCATED 2026-09-12.** The user confirmed directly to
`home-lab-03`, which has written the pre-allocation into `inventory/ips.yaml`
(committed there, not pushed). The address is recorded **only** in this repo's
gitignored `.env` as `OPENCLAW_VM_IP`, per the never-in-a-tracked-file rule; a
commented empty placeholder was added to the tracked
`infra/local.example.env`.

**Mechanism, and it is now a general pattern rather than a one-off:** the
address is static via `ipconfig0` at clone time, **not** a MAC-keyed DHCP
reservation, because df-automation's sandbox VMs do not hold a constant MAC
across rebuilds, so the reservation mechanism home-lab's registry otherwise uses
would not survive one. home-lab has recorded that as the standing pattern for
df-automation-provisioned sandboxes.

**Still owed to home-lab when the VM exists:** the real VMID, so they can add
the `guests:` entry to `inventory/hosts/SRV-01.yaml`. Nothing else outstanding.

Two notes from the episode: the gate was cleared by the user speaking in the
other session, not by this one pushing, which is the correct shape (see the
coordination note below); and the registry turned out to be *ahead* of the
router on the freed address, not behind it, contrary to this session's initial
assumption. **Still owed when the
VM actually exists:** the `guests:` entry in `inventory/hosts/SRV-01.yaml` with
the real VMID and address, and `inventory/services.yaml` if a service moves.
**Recorded here as open so it survives this session ending.**

Target host is SRV-01 deliberately: SRV-02 was crashing roughly every 2.5 hours
as of 2026-09-12, root cause open, and a power-brick swap was confirmed not to
be the fix.

### OPEN: this public repo leaks internal addresses, contrary to its own rule

**Found 2026-09-12**, prompted by the user pasting a router reservation row.
`CLAUDE.md` states the rule twice: "never copy a hostname, address or subnet into
this repo", and infrastructure specifics belong in gitignored `infra/local.*`.
An audit of **tracked** files finds the rule is not being followed.

- **Four distinct private IPv4 addresses** appear across roughly a dozen tracked
  files, including `CLAUDE.md` itself, `ROADMAP.md`, this file,
  `decisions/DECISIONS.md`, three `research/` specs, and
  `working-archive/`.
- **`.internal` hostnames** appear in tracked files too.
- **This session added to the problem today**, copying an address out of
  `CLAUDE.md` into this file's own text. Fixed in place, and the specific
  address is deliberately not repeated in this note.
- **The `scripts/*.py` hits are fine and need no change**: they are help text and
  error-message examples (`provision_vm.py` even uses a different subnet), not
  hardcoded defaults. The problem is entirely in prose.

**Honest limitation of any fix: the history is already public.** These files are
pushed, so scrubbing the working tree does not remove anything from git history,
and rewriting a public repo's history is disruptive and incomplete (clones
exist). The proportionate read is that these are RFC1918 addresses behind a
tailnet, so the real-world value to an attacker is low, and the reason to fix is
that the rule is deliberate and the drift will otherwise keep growing.

**Recommended, not yet done, needs the user's call:** fix forward (redact the
prose, leave history alone) and add a mechanical guard so it cannot recur, for
example a pre-commit check that fails on an IPv4 literal or `.internal` in a
tracked non-example file. Editing `CLAUDE.md` itself is deliberately left to the
user rather than done unilaterally, since it is the instruction file.

### Push authority: granted for one session only, 2026-09-12, now expired

The user granted standing `git push` authority "until end of session" during the
2026-09-12 agent-architecture session. **That grant was scoped to that session
and does not carry forward.** `CLAUDE.md`'s rule stands by default: `git push`
and any deploy need explicit go-ahead each time. A later session reading this
must not treat the line above as inherited permission.

Two boundaries were held under the grant, and are worth keeping if it is ever
granted again: the sibling-commit check still ran before each push, because the
grant covers this session's own work and not publishing a peer session's
unpushed commits; and **deploying to VM 103 was treated as separate and still
requiring a specific ask**, since that touches the live fort rather than the
repo.

### Peer coordination notes

- At the time of the live pause check there was **no peer session** (the
  `home-lab` session present at this session's start had ended), so the
  pre-VM-work heads-up this repo's rules call for had no recipient. Recorded
  rather than skipped silently.
- A new peer, `home-lab-03`, appeared shortly after and **was** given the
  heads-up. It confirmed VM 103 quiet and quorum healthy, and it **deferred an
  outlet-swap test that would have power-cycled SRV-01** (and therefore VM 103
  and the live fort) specifically to avoid disrupting this work. It will give
  lead time before any future attempt, which this session asked for so the fort
  can be quicksaved first. DF ignores SIGTERM, so an abrupt host power loss
  means no save.
- No home-lab inventory obligation arises from any work actually done today:
  nothing was created, deleted, resized or re-addressed.

**Ruled out already, so nobody re-derives it:** one agent per squad (DF combat
resolves faster than an agent round trip, and the threat sensor is verified
unreliable); multiple general writers (no transaction boundary in DF); an
efficiency-analysis agent and a safety-veto agent (both are code);
self-reported confidence as a decision input; publishing raw agent thinking.

**Not yet asked for:** this session's work is committed locally as `500d8ce`
and **not pushed**, which is the only unpushed commit on `main` (the
handover below claimed five; that claim was stale and is corrected there).
Publishing the reasoning stream (§8) is designed but explicitly needs its own
go-ahead, separately.

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
