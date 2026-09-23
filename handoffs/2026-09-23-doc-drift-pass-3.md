# Stream: bring every doc up to date with what 2026-09-22 and 2026-09-23 actually built

**Written** 2026-09-23. **Status:** dispatched. **User go-ahead:** 2026-09-23,
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

(executor fills in)
