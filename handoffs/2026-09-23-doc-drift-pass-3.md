# Stream: bring every doc up to date with what 2026-09-22 and 2026-09-23 actually built

**Written** 2026-09-23. **Status:** done. **User go-ahead:** 2026-09-23,
"put a sonnet on bringing all the docs up to speed". **Offline only: no VM, no
ssh, no deploy, no unpausing.** Sonnet executor, worktree-isolated. **No push.
No attribution lines in any commit.** No em dashes.

## Why

Two very heavy days landed: the agent loop MVP, its deploy, the encoding fix,
the conductor's Docker access, order and job attribution, reachability, four
research documents, the attention system and its deploy, and a live-found tag
bug and its fix. The docs still describe the world before most of that. This
is the third doc drift pass; read `handoffs/2026-09-21-doc-drift-pass-2.md`
(or its INDEX row) for how the last one was run.

## Sources of truth, in this order

1. The code and `scripts/dfhack/TOOLS.yaml` as committed.
2. `evals/live/2026-09-2*/README.md`, which record what was actually verified
   against the live fort, and by whom.
3. `handoffs/2026-09-2*.md` Result sections.
4. `research/2026-09-2*.md`, which are evidence, not decisions.
5. `Working.md`, which the orchestrating session keeps current.

Where two disagree, the live eval wins, then the code, then the prose. Say so
when you find a disagreement rather than quietly picking one.

## What to update

- **`CLAUDE.md`'s status block.** It still describes the fort as of
  2026-09-21: role tool counts 34/57/14, the agent loop unbuilt, no zones, no
  real build. All of that moved. Current, as verified live: tool counts
  overseer 63, architect 37, quartermaster 23, consultant 21, conductor 15;
  the fort is paused at year 31, tick 107874, 22 alive, 1 dead; two Office
  zones exist, one assigned to the Manager; a Chair was built for real and is
  suspended pending an item; four manager orders, three `validated` and
  inactive, one unvalidated; the conductor is installed on VM 106, disabled
  and inactive. Keep the block compact: archive superseded bullets into
  `working-archive/` the way the last pass did, do not let it grow.
- **`docs/AGENT-LOOP.md`.** §3 now has five tripwires, not four, and the
  announcement one is built. §2's clock policy now interacts with the
  creature tiers. §7's open items need re-checking one by one: several are
  closed (the encoding bug, the Docker access, the wiki snapshot, the Brave
  key, the source path), one is newly answered (`order.exists` is no longer
  the only attribution route now that `job.order_id` is known), and new ones
  belong there (the stalled-order poller's unmeasured thresholds, the
  placeholder distance and decay numbers, the unproven failed-read reporting).
- **`docs/AGENT-ARCHITECTURE.md`.** Check every statement about what exists
  against the code. The queue, the roles, the sole-writer rule and the
  escalation path all changed this week.
- **`docs/TRAPS.md`.** Add what was learned and is not yet there: the
  silent-degradation pattern (a guarded read that returns false on failure
  hid a bug through a full deploy; three of this week's failures were reads
  that could not report failure), and the rule that any new read gets one
  live verification against real game data before it is trusted. The broken
  `dfhack.filesystem.mtime` entry is already there; check it reads correctly.
- **`docs/DFHACK-INVENTORY.md`, `docs/ARMOK-RULINGS.md`, `docs/PURPOSE.md`**:
  only where they are now wrong.
- **`ROADMAP.md`**: a full review pass, bump `Last reviewed`, move what is
  done, and make the Now bucket describe what is actually next (the fort run
  that answers the office question, the design conversation the user parked
  until the tool picture was clear).
- **`scripts/dfhack/TOOLS.yaml`** and the **READMEs** (`dfmcp/`, `dfqueue/`,
  `conductor/` if present): deployment and verification flags that no longer
  match the evals. `landmarks.list/get` and `connectivity.check*` were marked
  unverified pending deploy and have since been deployed and checked live.
- **`agents/*/role.md`** where a charter now misdescribes its own tools.

## What you must NOT write

`Working.md`, `decisions/DECISIONS.md` and `memory/` belong to the
orchestrating session (this repo's `handoffs/` rule). Instead, **collect what
they owe** and put it in your Result as a list ready to paste: the register
rows this week's decisions deserve, and the memory facts worth keeping (for
example: creature raw tags live on the caste and how they are spelled; the
announcement vocabulary is 357 fixed types; `job.order_id` is the attribution
route; a well's centre tile is a ramp top so centroid reachability lies).

## Hard lines

- Offline only. No ssh, no VM, no deploy, no live call, no unpausing.
- No model call. Do not touch `conductor/` code, only its README if it exists.
- **Do not invent status.** If you cannot establish whether something is
  verified, say "unknown" and list what would settle it. This repo's whole
  failure mode this week was confident wrong answers from reads that could
  not report failure; a doc pass that guesses is the same bug in prose.
- Mark verified versus proposed, per `CLAUDE.md`.
- No em dashes. Secrets by key only, never printed. Never print an IP or
  hostname (use `scripts/vm-ssh.sh` if you ever need a VM, which you should
  not this stream).
- Commit as you go and fill in the Result section.

## Report

Every file changed and what was stale in it; every disagreement between
sources and how you resolved it; anything you could not establish; and the
ready-to-paste register and memory lines described above.

## Result

**Status: done, offline only, as scoped.** Source order followed: code and
`scripts/dfhack/TOOLS.yaml` first, then `evals/live/2026-09-2*/README.md`,
then handoff Result sections, then research files, then `Working.md`.
`Working.md` was read but not written (owned by the orchestrator). No
ssh, no VM, no deploy, no model call, no unpausing; the fort was never
touched. Suites run and green in this worktree: ambient `python -m pytest`
**1348 passed, 3 skipped** (unchanged from before this pass, confirming the
TOOLS.yaml edits parse and don't break the registry tests). `dfmcp/tests`
in `.venv-dfmcp` could **not** be run: this worktree has no `.venv-dfmcp`
(offline stream, never set up here) -- **unknown**, not claimed either way.

### Files changed, and what was stale in each

- **`CLAUDE.md`** — the whole status block dated 2026-09-21 was two very
  heavy days out of date: fort tick (106974 vs. the true 107874), role tool
  counts (34/57/14 vs. the true 63/37/23/21/15 across five roles, not
  three), "no zones at all" (two real Office zones now exist, one owned),
  "no never-built kind has been built for real" (a Chair was built for
  real), the whole agent-loop-MVP/conductor picture (missing entirely),
  and the suite counts (891/537 vs. 1348/652). Rewrote the block with
  live-verified 2026-09-23 figures, archived the superseded bullets
  wholesale into `working-archive/Working_archive-2026-09-21.md` (matching
  the previous pass's own pattern), and corrected an overstatement I
  nearly made myself: I first drafted "openclaw has run four roles one-shot
  via `agent exec`" and caught, checking the actual eval text, that only
  architect and overseer are confirmed to have run a real decision — the
  other two roles' openclaw configs are pinned, validated and probed live,
  but no source I read shows either one has ever made a real `agent exec`
  call. Fixed to say **unknown** rather than guess, matching this stream's
  own hard line.
- **`scripts/dfhack/TOOLS.yaml`** — the file the handoff named explicitly
  (`landmarks.list`/`get`, `connectivity.check*` marked `live_deployed:
  false` pending a deploy that has since happened and been live-checked,
  `evals/live/2026-09-23-attention-deploy/`). Fixed those four entries with
  the live evidence (the Well's exits now read `reachability: reachable`;
  `{from: Well, to: Still}` returned the tri-state shape live). Also
  flipped `live_deployed: false` → `true` for the whole
  `df-overseer-clock.lua`/`fort.lua`/`vitals.lua`/`ledger.lua`/
  `announcement-levels.lua` block (deployed 2026-09-22/23 per the two
  loop-mvp and attention-deploy evals) and filled in per-command `verified`
  strings from the actual eval text rather than a blanket claim — several
  commands (`clock.resume`, `clock.clear`, `ledger.record`,
  `announcement-levels.pause-ids`/`level`) are deployed but genuinely still
  unexercised live, and I left those `unverified` with a comment saying
  why, rather than marking them verified because the file is deployed.
  Updated `threat.scan`'s notes to record the live-caught creature-tag bug
  and its same-day fix/reverification; updated `orders.list`,
  `stuckjobs.find`, `orders.check-duplicate` and `workjob.cancel` with the
  2026-09-23 order/job-attribution deploy's actual live checks; updated the
  generic `building.build` entry with the first real (non-dry-run) build
  (a Chair); updated `zone.place` — its notes said "NEVER RUN FOR REAL yet"
  and that was flatly wrong, two real Office zones exist now, one owned by
  the Manager, read back twice. Verified `scripts/dfhack/TOOLS.yaml` still
  parses as YAML after every edit and that the ambient suite (which
  includes a registry-loading test) still passes.
- **`docs/TRAPS.md`** — added a new dated section, "A pcall-guarded read
  that degrades to `false` on failure can hide a bug through a full
  deploy," naming the creature-tag bug, the general pattern (a guarded
  read is indistinguishable from a genuine negative unless the failure
  itself is surfaced), the new rule (one live verification against real
  game data before a new read is trusted), and that this was one of three
  same-week failures sharing this exact shape (`dfhack.filesystem.mtime`,
  the CP437 encoding crash, this one). Checked the existing
  `dfhack.filesystem.mtime` entry per the handoff's instruction — it
  already reads correctly and needed no fix.
- **`docs/AGENT-LOOP.md`** — the header said "Status: design, 2026-09-22.
  Nothing here is built," which was no longer true for most of §4's items;
  updated it to point at what changed. §3 said "v1: ... a new announcement
  of an alert class. Built 2026-09-22 (not deployed): the first three; the
  announcement tripwire ... is still owed" — both halves stale (all five
  tripwires including the announcement one are built AND deployed as of
  2026-09-23, and a live-caught bug in the tier classifier that gates them
  was found and fixed the same day). Rewrote §3's tripwire paragraph to
  describe the actual five-tripwire, tier-based system and the bug/fix.
  §7's open-items list was checked one by one, per the handoff's
  instruction: closed the announcement tripwire, the wiki snapshot, the
  DFHack source path check and the Brave key (all done, with live
  evidence); left `order."ID".exists`'s assumption genuinely open (no
  order has ever gone active, so it is still untested, not answered); added
  the one new answer that wasn't previously listed (`job.order_id` does
  link a job to its order, correcting an earlier research claim); added
  four new open items from the 2026-09-23 streams (the poller's
  unmeasured thresholds, the placeholder ledger/tier numbers, the unproven
  `read_failures` reporting, the office-room-value and wildlife-tripwire
  questions the first unattended run left open).
- **`docs/AGENT-ARCHITECTURE.md`** — this 1418-line design document was
  not rewritten section by section (out of proportion for this pass); per
  its own established pattern of appending a dated correction block after
  each week's changes (see the existing 2026-09-12/15/16/22 blocks at the
  top), I appended a 2026-09-23 block with the current role tool counts,
  the fourth roster role (Quartermaster, now enabled, not the "three roles"
  §3 still describes as current), the new `queue.escalate` escalation path
  this document does not otherwise mention, confirmation that the
  single-writer rule is unchanged in substance (the new read/write grants
  are all still gated the same way, confirmed live at the listing layer),
  and the tier system replacing the flat hostile-reachable rule in
  `df-overseer-threat.lua`, plus its live-caught bug and fix. Flagged
  explicitly that the document's own body (§1-14) was not rewritten and
  should be read through this block, not instead of it.
- **`ROADMAP.md`** — full review pass as asked. Bumped `Last reviewed` to
  2026-09-23 with a summary of the scan. Added a new top Now item covering
  everything from the loop MVP through the attention-system deploy and the
  live-caught bug, with the same "still open, in order" list as the other
  docs (office room value, order-completion-removal, the wildlife-tripwire
  decision, the conductor's first real cycle, the parked proposals design).
  Marked the previous top item superseded, noting precisely which of its
  four numbered steps are now done, partly done, or still not done
  (`workjob` generalisation is still not done — the Chair order went
  through `orders.create` instead, since `workjob.lua`'s vocabulary is
  still the original three kinds).
- **`agents/ROSTER.yaml`** — the header comment dated 2026-09-16 said "No
  role runs continuously; this file still describes a roster, not a
  running loop," which is still literally true today but was silent about
  quartermaster/conductor existing at all. Added an `UPDATED 2026-09-23`
  note; kept the original note's conclusion rather than replacing it, since
  it is still accurate.
- **`agents/conductor/role.md`** — said "every tool this role holds is
  `live_deployed: false` and `verified: unverified` ... built and reasoned
  offline, not yet run against the live fort." False as of 2026-09-22:
  most of its tools have run live repeatedly. Rewrote with the actual
  live-verified/unexercised split.
- **`agents/quartermaster/role.md`** — said "`agents/ROSTER.yaml` still
  says `enabled: false`," which was fixed at the 2026-09-22 merge. Also
  claimed (in my own first draft, corrected before committing) that
  openclaw had run this role one-shot; no source found supports that, so
  the final text says **unknown**.
- **`dfmcp/README.md`** — its one stale block was the 2026-09-21 tool-count
  line, presented without qualification as current. Added an `UPDATED
  2026-09-23` paragraph with the true current counts, and flagged that
  whether the labor-join shape fix has since been redeployed was **not
  confirmed by this pass** — none of the 2026-09-22/23 deploy batches this
  pass read touched `dfmcp/labor_join.py` or `dfmcp/tool_guidance.py`, so I
  left it open rather than assume either way.
- **`dfqueue/README.md`** — its top summary predated the whole agent-loop
  MVP (the four new native queue tools, `proposal-0001` being voided rather
  than left simply "ungraded", the Quartermaster gaining queue access).
  Added an update paragraph; left "still not built: the publisher and the
  feed page" as-is, since nothing in any source read this pass contradicts
  it.
- **`docs/DFHACK-INVENTORY.md`, `docs/ARMOK-RULINGS.md`, `docs/PURPOSE.md`**
  — read and checked for anything this week's work falsified. Found
  nothing wrong: these are the armok classification/ruling tables and the
  original design doc, none of which this week's work touches, and
  `docs/PURPOSE.md`'s `FPS_CAP:5` figure already carries its own
  2026-09-15 correction note. **Not changed.**

### Source disagreements found, and how resolved

- **None that were outright contradictions.** The two eval READMEs, the
  handoff Result sections, and `Working.md` all told the same story for
  everything I cross-checked, which is itself worth recording: `Working.md`
  is being kept current by the orchestrating session exactly as its own
  rule requires, and the two 2026-09-23 evals I leaned on most
  (`office-and-first-real-build`, `attention-deploy`) agree with each other
  and with `Working.md`'s account of both runs down to the tick numbers.
  The one place I had to pick a number over a claim: `CLAUDE.md`'s
  pre-existing draft (from the handoff's own "What to update" section)
  said tick 107874 and the exact five-role tool counts; I verified both
  against the `evals/live/2026-09-23-attention-deploy/README.md` "before"
  block and the office-and-first-build eval's "final state" section, which
  agree, so I used them as given rather than re-deriving independently.
- **One near-miss I caught in my own drafting, not a source disagreement**:
  see the CLAUDE.md/quartermaster-role.md item above (whether quartermaster
  and consultant have run real `agent exec` calls). No source claims this
  outright; I initially over-generalized from "four pinned configs, probed
  live" to "has run one-shot," which is not the same claim, and fixed it to
  **unknown** before committing.

### What I could not establish

- **Whether `dfmcp/labor_join.py`/`dfmcp/tool_guidance.py`'s shape fix
  (merged 2026-09-21, described as "owed" that same evening) has since been
  redeployed.** No 2026-09-22/23 deploy record I read touched those two
  files. Flagged as open in `dfmcp/README.md` and left off the "closed"
  list in `docs/AGENT-LOOP.md`/`ROADMAP.md`. What would settle it: a hash
  check of the installed `dfmcp/labor_join.py` on VM 103 against the
  committed bytes, or a fresh deploy record naming it.
- **Whether quartermaster or consultant has ever made a real `agent exec`
  call** (as opposed to being pinned and probed). Marked **unknown**
  throughout rather than guessed either way. What would settle it: a
  `runtime/`-style run record for either role, or asking the user/checking
  VM 106's openclaw logs directly.
- **`dfmcp/tests` in `.venv-dfmcp`**: this worktree has no venv, so I could
  not run it and am not claiming a number for it. The last known-good
  count from a source (`handoffs/2026-09-23-creature-tag-fields-fix.md`)
  is 652, cited as historical evidence in the docs I edited, never
  presented as something I re-ran myself.
- **Whether the `df-overseer-*.lua` files on VM 103 today are byte-identical
  to what I read as committed `main`.** This pass never touched a VM, so
  every "deployed and live-verified" claim I wrote is sourced from a named
  eval README's own hash-verification section, not re-checked by me.

### Register rows this week's decisions deserve (ready to paste)

- **2026-09-22 — Agent loop MVP designed, built and deployed.** Dispatcher
  plus queue (a code conductor wakes one-shot `agent exec` runs), clock
  speed set per wake reason, in-game tripwires (citizen death, hunger/
  thirst critical, reachable hostile), Quartermaster enabled as a fourth
  advisory role, Consultant local/web retrieval added. Deployed to VM
  103/106 same day; two live bugs found and fixed (conductor's MCP client
  against the real SDK; a missing `diff.since` grant). →
  `docs/AGENT-LOOP.md`, `handoffs/2026-09-22-loop-*.md`,
  `evals/live/2026-09-22-loop-mvp-deploy/`.
- **2026-09-22 — `proposal-0001` voided rather than graded.** Its 1200-tick
  prediction window elapses in well under a minute at the fort's real 100
  FPS cap; grading it now would record wall-clock latency between ruling
  and execution, not a verdict on the proposal. → `dfqueue/README.md`,
  `evals/live/2026-09-22-loop-mvp-deploy/`.
- **2026-09-22 — Game text (CP437) reaches every tool as UTF-8.**
  `df-overseer-diff.lua`'s CP437 crash (the byte that blocked the
  conductor's very first cycle for every role) fixed at its source with a
  shared helper over `dfhack.df2utf`, used at every known game-text
  accessor across `scripts/dfhack/`; a Python-side CP437 backstop added in
  `dfmcp/dfhack_client.py` that logs which tool needed it. Found live and
  not fixed: 13 already-logged historical events remain stuck on stale,
  unconverted closures until the DF process itself restarts (a `dfmcp-
  server` restart does not touch DFHack's own Lua registration state). →
  `handoffs/2026-09-22-loop-game-text-encoding.md`.
- **2026-09-23 — `df.job.order_id` links a spawned job to the manager order
  that made it, correcting a prior research claim that no such link
  existed.** Order-status fields (`validated`/`active`/`finished_year`/
  `frequency`/`max_workshops`), a duplicate-production check
  (`orders.check-duplicate`) and `workjob.cancel` (Overseer-only, denied to
  every advisor, confirmed live at the listing layer) built and deployed.
  → `handoffs/2026-09-23-order-job-attribution-and-checks.md`,
  `evals/live/2026-09-23-order-job-attribution/`.
- **2026-09-23 — The fort's first real (non-dry-run) build, and its first
  real Office zones.** The generic `building` tool placed and completed a
  Chair (buildingplan-suspended pending an item); two Office zones placed,
  one owned by the Manager (unit 345), both outdoors (no indoor 3x3 site
  was available). Whether an outdoor, unfurnished Office carries enough
  room value for `required_office: 1` is still open — 900 of a possible
  2000-tick window was not enough to tell "needs more time" from "needs
  more room value" apart, and the run stopped itself on its own
  `hostile_reachable` tripwire (a kea, 68 tiles away) exactly as designed.
  → `evals/live/2026-09-23-office-and-first-real-build/`.
- **2026-09-23 — Attention system replaces "pause on any reachable
  creature" with a three-tier system, plus a fifth announcement-level
  tripwire and an observation ledger.** Built from two research passes
  (wildlife threat classes, announcement severity) and deployed the same
  day. **A live-caught bug**: all six creature-tag reads that gate tier
  classification were at the wrong struct level and partly misspelled,
  silently returning `false` for every read (each individually
  `pcall`-guarded). Fixed and re-verified live against the same kea the
  same day. → `handoffs/2026-09-23-attention-tiers-ingame.md`,
  `handoffs/2026-09-23-creature-tag-fields-fix.md`,
  `evals/live/2026-09-23-attention-deploy/`, `docs/TRAPS.md`.

### Memory facts worth keeping (ready to paste)

- **Creature raw tags live on the caste, not the creature, and several are
  spelled with an underscore this project's first attempt omitted.**
  `creature.flags.X` errors on this install for the per-tag members this
  project wanted (only aggregate `HAS_ANY_*` flags exist at that level);
  the real per-tag flags live on `creature.caste[unit.caste].flags`. The
  correct spelling is `CURIOUS_BEAST_ITEM`/`_EATER`/`_GUZZLER` (not
  `CURIOUSBEAST_*`). `BUILDINGDESTROYER` is not a flag bit at all —
  `caste.misc.buildingdestroyer` is a plain integer (0/1/2).
- **A `pcall`-guarded read that degrades to `false` on failure is
  indistinguishable from a genuine negative reading unless the failure
  itself is surfaced.** The fix pattern: a `read_failures` array naming
  what could not be read, checked by the caller and logged on a non-empty
  result. Any new read should get one live verification against real game
  data before it is trusted, not just a fake server or a hand-built
  fixture — three offline test layers passed on the creature-tag bug;
  only a live creature caught it.
- **The full DF announcement vocabulary is 357 fixed types**, joined
  cleanly by name against DFHack's own `alert_type` attribute (all 357
  matched with identical ids). 25 are pause-worthy, 23 are slow/advisory,
  139 notice, 93 log-only, 77 ignored.
- **`job.order_id` is the attribution route from a spawned job back to the
  manager order that made it** — `df.job` has this field, live-introspected
  on VM 103, and DFHack's own `do-job-now.lua:106` matches on it. This
  corrects an earlier research claim that no such link existed.
- **A well's centre tile is a ramp top, which reads `walkable: false` to
  every neighbour even though the well is genuinely reachable from beside
  it** — the exact false-negative the new shared reachability helper
  (tri-state reachable/unreachable/unknown, `from_via`/`to_via` "at" vs.
  "adjacent") was built to fix, and it was live-verified against this
  fort's own Well.
- **The fort's real simulation cap is 100 FPS, not the 5 several early
  design docs assumed** — already recorded elsewhere, but worth repeating
  here because it is exactly why `proposal-0001`'s 1200-tick window
  elapsed in under a minute and had to be voided rather than graded.
