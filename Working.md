# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-09-11 (end of session, written for a `/clear`)

The entire prior handover (2026-09-10's end-of-session summary, plus today's
own VM-outage/quorum incident) is archived wholesale —
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md).
This is a genuinely dense session — read this whole section before doing
anything, not just skimming for the next task.

### State at a glance, verified fresh, not assumed

- **Uniboslan, "Ragwind," is the one fort, healthy.** `pause_state=true`,
  active save `autosave 1`, all 7 citizens (192-198) present and uninjured,
  confirmed live moments before writing this, not carried over from an
  earlier check in this session.
- **VM 103 survived a real outage and came back clean.** Cluster quorum
  loss (SRV-02 down, no QDevice — home-lab's structural gap, not this
  repo's) blocked VM start/stop entirely for a while, a new confirmed
  failure mode beyond the already-documented snapshot-blocking one. User
  restored quorum directly at a root shell (non-persistent override —
  reverts on reboot or if SRV-02 rejoins, watch for quorum-shaped errors
  again). `cpu: x86-64-v2-AES` is now genuinely applied (was accepted
  2026-08-28, never actually run until today).
- **`main` is now even with `origin/main`, nothing outstanding to push.**
  Corrected during a later documentation pass (`git log origin/main..HEAD`
  came back empty, `git rev-parse HEAD`/`origin/main` identical at
  `e8caa41`): the 5 commits once queued here (`b8dd6a9`, `f48a641`,
  `0a47c56`, `89a04d2`, `e8caa41` itself) have all landed on `origin/main`
  since this line was first written. This repo's working tree still carries
  live, uncommitted edits to `Working.md`/`ROADMAP.md`/`decisions/DECISIONS.md`
  (today's find_diggable_area consolidation pass) plus untracked
  `evals/compliance/`, `predictions/`, and `scripts/dfhack/df-overseer-combat.lua`
  from earlier in the session, none of which are on `origin` yet either.
- **The `df-automation-perception` worktree (`perception-layer-experiments`
  branch) has real, working, uncommitted code**: `df-overseer-openarea.lua`
  and `df-overseer-landmarks.lua` gained `build`/`build_open_area` —
  verified live to have actually built a real "Stockpile #2" on Uniboslan.
  **Not committed** — same open question as everything else on that
  branch (below). If you're a fresh session: `cd` there, don't touch
  `main`'s checkout to look at it.
- **`scripts/dfhack/df-overseer-combat.lua` sits untracked in `main`'s
  working tree, deployed live on VM 103, deliberately uncommitted.**
  Event-driven combat/threat detection (`recent-combat`, `since-report`,
  `event-log`), overlaps in design with `df-overseer-diff.lua` on
  `perception-layer-experiments`. **`df-automation-ca` never appeared this
  entire session** — this is still unresolved, not stale, don't delete or
  build on it without checking first.

### The big open decision, asked more than once, still the same answer

**Whether/when `perception-layer-experiments` merges into `main`.** Audited
properly this session (not file-listing guesswork): it has built and
live-verified nearly the whole spatial-perception build order (items 2-8:
connectivity, landmarks, `get_overview`, `get_diff_since`, `find_open_area`,
`find_chokepoints`, `get_stuck_jobs`), all 8 original commits pushed to
`origin/perception-layer-experiments`, plus today's uncommitted
`build`/`build_open_area` addition. **User's explicit, repeated call: not
ready to merge yet, wants to keep working with the branch and see how far
it goes.** Don't merge unilaterally; don't assume this has changed since
the last time it was asked. Whoever picks this up next should ask again
before touching the merge question, not just before merging.

### What actually got built today, compressed (full detail: `decisions/DECISIONS.md`'s 2026-09-11 rows, in order)

1. **Authenticated personal-control VNC channel** — deployed and confirmed
   working. A second, real-mouse-and-keyboard, Cloudflare-Access-gated
   channel for the user alone (`dwarf-fortress-admin.willsmith.nz`),
   completely separate from the existing public view-only feed. **Standing
   caution**: any future `xdotool`/simulated-input use against VM 103
   shares this exact channel and can visibly collide with the user
   actually using it — call it out explicitly first, per
   `docs/DF-UI-AUTOMATION.md`.
2. **Dwarf/labor management, first slice**: `scripts/dfhack/df-overseer-labor.lua`
   (`unit-status`, `labors`, `set-labor`), `autolabor` enabled and
   *confirmed* actually assigning jobs (idle count dropped live during a
   brief unpause). The mechanics half of design commitment #2 exists now;
   nothing yet decides labor policy beyond `autolabor`'s own defaults.
3. **A real kea attack happened and was used as a live test case.** The
   fort's dogs and a citizen killed it. `unit-status hostile` missed the
   entire fight, before/during/after — proven unreliable in *both*
   directions the same day (also flags harmless deep-cavern demons).
   Root cause: `dfhack.units.isDanger`/`isInvader` just aren't the right
   signal for "is my fort under attack right now" — that's an event
   (`get_diff_since`), not a queryable static predicate. Not fixed on
   `main`; a prototype exists (`df-overseer-combat.lua`, see above) but is
   blocked on the branch-overlap question.
4. **The quicksave "silent no-op" was root-caused, not just patched
   around.** `quicksave.lua` pushes an overlay whose real save logic only
   runs on a later game render pass — delay observed 8 to 80+ seconds,
   totally variable. `stderr.log`'s "Invoking:"/"should autosave" lines are
   proven unreliable as a signal in **both** directions (absent for a call
   that worked, and the reverse was already known). **New protocol,
   supersedes everything written before today**: poll the active save
   slot's `world.sav` mtime for up to ~90 seconds; never trust the log
   lines. Full trail: `research/2026-09-11-quicksave-silent-noop.md`.
5. **The `perception-layer-experiments` audit** (see the big decision
   above) — found it does far more than this file used to credit it with.
6. **First real autonomous-play experiment**: a subagent used
   `find_open_area` to pick a genuine, ranked, named construction
   candidate — then correctly **stopped without building anything**,
   because every deployed perception tool deliberately strips coordinates
   before returning them, and nothing bridged "the model picked a good
   spot" to "here's where `quickfort` should anchor." A real, honest
   non-result, not a failure.
7. **Second attempt closed that gap for real.** Built `build_open_area`/
   `build` (fused resolve-and-act — the coordinate exists for one line,
   inside the function, to build `quickfort`'s own argument list, and is
   never returned or printed; verified this directly against the function
   body, not taken on trust). Used it to place a genuine, independently-
   verified new building, **"Stockpile #2,"** on Uniboslan — the first
   fully closed loop this project has: a coordinate-free ranked decision,
   turned into a real, persistent fort mutation, with the raw coordinate
   never once visible to whatever made the decision.
8. **Two real gaps found doing that, both corrected after the user caught
   an overstatement in each, and the first one then closed for real, same
   session**:
   - "Dig a brand-new room" is **not** build order item 9 (that's still
     "find already-open cavern space," a different problem) — nothing in
     the whole spec finds *solid, diggable* terrain at all. Needs a new
     `find_diggable_area` primitive, the mirror of `find_open_area`.
     **Closed later the same session**: built, live-verified, paired with a
     `dig_diggable_area`/`dig` fused resolve-and-act primitive, live-tested
     for real, and (after finding and fixing a genuine coordinate-anchoring
     bug, see below) confirmed working end to end, a dwarf claiming a real
     job and all 41 designated tiles fully dug. Full detail: item 10 below.
   - A diggable candidate with no border on the existing walkable network
     isn't *invalid* (first draft said this, wrong) — it just needs a
     connector tunnel dug too, a pattern this project already uses
     (entrance+connector+room). `find_diggable_area` should score
     connector cost, not hard-reject isolated candidates. **v1 still scopes
     to adjacent-only candidates** (connector-cost scoring is a later
     version, not built this session), documented as such in the file
     itself, not silently.
   - Also found: `rank_candidate_sites` (still unbuilt) needs a
     proximity-to-*named-room-by-kind* scoring term (the concrete case:
     site the brewery near the farming room), distinct from and cheaper
     than the resource-proximity term already spec'd — the landmark graph
     already tags every building's `kind`. All three captured in
     `research/2026-08-25-spatial-perception.md` directly, before anyone
     builds these, not after.
9. **Status banners refreshed**: `CLAUDE.md`'s top banner and
   `docs/PURPOSE.md`'s superseded-notice were both badly stale (still said
   "no game-side code exists"); both rewritten to reflect the above.
10. **`find_diggable_area`/`dig_diggable_area` built, live-verified, and
    (after a real bug was found, root-caused, and fixed) confirmed working
    end to end**: `scripts/dfhack/df-overseer-diggable.lua`,
    `perception-layer-experiments`. Mirrors `find_open_area`/`build_open_area`
    for solid terrain instead of walkable space. Live testing found a real,
    previously-unknown bug shared with `build_open_area`: `quickfort`'s `-c`
    anchors a blueprint's **top-left corner, not its center**, and both
    tools were silently passing the computed center: Stockpile #2 (item 7)
    only worked anyway because its candidate sat in broadly open space, luck
    not correctness. Fixed in both (`df-overseer-diggable.lua`'s fix
    committed, `df-overseer-openarea.lua`'s left uncommitted matching that
    file's own pre-existing state, its own comment explains why). Re-tested
    live after the fix: designation landed at the correct spot, real `Dig`
    jobs appeared and were claimed almost immediately, and all 41 designated
    tiles were fully dug by the next check: **the second fully closed
    coordinate-free decision-to-mutation loop this project has**, after
    Stockpile #2. Full detail archived: see the "Archived" section below.
11. **A second, independent live bug found and fixed the same day, this one
    from a bounded Haiku-driven autonomous-play run**: Haiku called
    `df-overseer-openarea build` with a guessed `z=0` (no tool exposed a
    landmark's own level), which is a real but disconnected part of the map
    (`walkable_group: 15`) — the call silently designated 0 tiles instead of
    erroring. Root cause: `ranked_candidates()` in both
    `df-overseer-openarea.lua` and `df-overseer-diggable.lua` already
    resolves the named landmark's own real Z (`az`) internally but was
    discarding it in favor of a separately-required `z` argument. **Fixed**:
    `z` now defaults to `az` when omitted; an explicit numeric Z (old CLI
    form) still works, shifting later args left by one otherwise. Deployed
    live via `ui-install`, then **live re-verified, read-only only**: `find`
    with Z omitted returns candidates at `walkable_group: 11` (the fort's
    real group, matching `df-overseer-overview`'s `main_group_id: 11`), and
    the old explicit-Z-169 form returns byte-for-byte the same candidates
    for both tools. Fort confirmed undisturbed throughout (`population: 15`,
    `alerts: []`, `get_stuck_jobs` empty). Full detail:
    `decisions/DECISIONS.md`'s 2026-09-11 row, "Found and fixed a second,
    independent live bug...".
12. **A take-stock pass (Opus-authored architecture proposal, then a
    user-pushed correction) found this project's mortality/re-embark premise
    was being undersold, not oversold.** The claim "`mode` unavailable means
    unattended re-embark is blocked" doesn't survive research: `mode`'s
    unavailability is real (re-verified live, three ways) but was never the
    mechanism either real embark actually used. Re-embark is proven twice,
    end to end, no human mouse involved, via `gui/embark-anywhere.lua` plus
    this project's own scripted UI navigation. The real gaps are narrower:
    the unresolved "Confirm"-click race-condition crash (worked around by a
    manual `gdb` ritual, no scripted equivalent), and DF's actual behavior
    at the moment of fort death, never observed and correctly not tested
    against Uniboslan. `unretire-anyone` confirmed irrelevant (adventure
    mode only). `docs/PURPOSE.md`'s open questions corrected to match.
    Full trail: `decisions/DECISIONS.md`'s newest 2026-09-11 row.
    **`df-ai` follow-up, done same day**: read its actual source (cloned,
    not just described) — its fort-death detection is a genuinely usable,
    Lua-reachable technique (watch for a `viewscreen_textviewerst` showing
    one of three literal end-game strings), but its restart mechanism
    can't be trusted to transfer: it targets DF 0.47, predating the v50
    Steam/Premium embark-screen rewrite, so it gives no evidence either way
    on the Confirm-click crash. **User's call, same day: not worth pursuing
    further right now** — the death-detection script stays a documented,
    cheap idea (this note) rather than a queued next step. Thread closed
    unless raised again.

### Durable traps, still true (carried forward; additions marked NEW same as before)

Embark-screen automation mechanics (coordinate frames, `xdotool`
calibration, dead input paths, dialog handling, the click tool's known
flaws) are the permanent, living content of `docs/DF-UI-AUTOMATION.md` —
not duplicated here. This list is everything else: infra, project-wide
gotchas, and fresh findings without another doc home yet.

- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's `memory/tailscale-architecture.md` assigns `df-fortress`/
  `df-colony-01` to `tag:ai-sandbox` — "unattended, possibly LLM-driven,
  lowest trust that isn't internet-facing" — but `runbooks/tailscale-topology.md`
  Phase 5 (the actual hard gate) is still unchecked. **Not this repo's to
  fix** — host-level Tailscale/ACL work, forbidden to any agent by
  home-lab's own rule.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it.**
- **The published hostname is exposed.** The user chose not to rename it;
  `willsmith.nz` is deliberate, not a leak.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified. `hypothesis_id` has no registry.
  `openclaw` vs `hermes-agent` still deferred.**
- **PVE's cloud-init takes only the first label of the VM `name`** —
  `install_df.py`'s `step_hostname` is the only workable route to a
  suffixed guest hostname.
- **`dfhack-run lua -f script.lua ARG1 ARG2` passes arguments via Lua
  varargs (`local x, y = ...`), not a global `arg` table.**
- **DF's save-slot names (`autosave 1/2/3`, `current`) are a shared,
  generic pool, not scoped per fort** — founding a second fort while one
  exists can silently overwrite the first's save (this is how Artobcatten
  was lost). Pull an `install_df.py backup` first, always.
- **A founded fort's own welcome dialog silently blocks all citizen
  activity even when `pause_state` reads `false`.** Always check for an
  undismissed dialog before concluding a fort is stuck.
- **A downstair can't be designated on a grass tile**; a plain floor dig
  beneath a completed stair never becomes a job unless the connecting tile
  is itself a matching stair type — boundary connectivity, not just the
  target tile's state, gates job creation. The same lesson now also
  applies to `find_diggable_area`'s design (above).
- **The fortress-wide job list is `df.global.world.jobs.list`** (linked
  list, `.next`/`.item`), not `df.global.job_list`.
- **`quicksave` is asynchronous and its own log line is not a reliable
  signal in either direction** — see item 4 above. Poll the save slot's
  mtime for up to ~90s.
- **Quicksave rotates forward through the `autosave N` slot pool,
  overwrite-oldest-first, not a fixed round-robin or in-place update** —
  always re-read `cur_savegame.save_dir` fresh, never assume a
  previously-checked slot name is still current.
- **VM 103's SSH host key changes across a full Proxmox stop/start
  cycle** — expected, not a MITM concern, given documented intentional
  restarts; fix with `ssh-keygen -R <ip>` then accept the new key, don't
  just disable host-key checking as a habit.
- NEW: **Every deployed perception-layer tool deliberately strips
  coordinates before returning anything** (`find_open_area`,
  `df-overseer-landmarks.lua`) — by design, matching commitment #1, but
  it means nothing downstream can get a raw position except through a
  fused resolve-and-act primitive built specifically for that purpose
  (`build_open_area`/`build`). Don't expect a coordinate back from any
  perception query; if you need one, an action tool has to compute and
  consume it internally, never return it.
- NEW: **`unit-status hostile` (`dfhack.units.isDanger`/`isInvader`) is
  not a trustworthy fort-defense signal** — proven wrong in both
  directions the same day (flags harmless deep-cavern creatures, misses a
  real on-map attack entirely). Treat its output as "worth a second look,"
  never as "confirmed safe" or "confirmed hostile" on its own.

### Peer sessions and immediate next steps, as of end of session

**Live peer sessions** (check `ListAgents` fresh, this will be stale by the
time you read it): `df-automation-e6` was mid-way through the compliance
eval harness above (an Opus sweep may still be running or may have landed —
check `evals/compliance/results/` and message them rather than assume);
`home-lab-29` was around for the quorum incident, unrelated to this repo's
own work otherwise. `df-automation-ca` (owns `perception-layer-experiments`
in spirit, per its own commits) **never appeared once this entire
session** — if it shows up, it's the one session that can actually settle
the `df-overseer-diff.lua`/`df-overseer-combat.lua` overlap.

**If you're picking this up fresh, in rough priority order**:
1. `ListAgents`, then message whoever's live — per the standing rule in
   `CLAUDE.md`'s Rules section (added today), don't assume a clean slate.
2. **Done, same session, after this was written**: the compliance eval
   harness finished for real — full sweeps against both `claude-opus-5` and
   `deepseek-chat`, a real finding (DeepSeek's `required_word` collapse), a
   cost overrun ($9-13 on Opus) that got corrected (DeepSeek is now the
   default provider), and mechanical prediction grading (`predictions/`)
   built as a follow-on. Archived into
   `working-archive/Working_archive-2026-09-07.md`; nothing left open on
   either thread. Not something a fresh session needs to check on.
3. Re-verify Uniboslan is still paused/healthy before touching it — don't
   trust this document's "State at a glance" as current for more than a
   few minutes past when it was written.
4. **Corrected in a later documentation pass**: `main`'s commits are now
   pushed (`origin/main` matches `HEAD` at `e8caa41`), nothing to ask about
   there. The uncommitted worktree changes (`df-overseer-openarea.lua`,
   `df-overseer-landmarks.lua`) and `combat.lua` are still real, reviewed,
   working, and still need the branch-merge question settled, not more
   investigation.
5. **Done, same session, after this was written**: `find_diggable_area`/
   `dig_diggable_area` were built, live-verified, live-tested, and (after a
   real coordinate-anchoring bug was found and fixed) confirmed working end
   to end: see item 10 in "What actually got built today" above. The
   connector-cost scoring for non-adjacent candidates is still unbuilt
   (v1 scope, documented as such), the clearest next build if this thread
   continues.

### Other open items, carried forward

- **Design commitment #1's absolute wording vs. its actual evidence
  base** — still queued for a `decisions/DECISIONS.md` entry, deliberately
  not written yet (user's call on timing).
- **Live-view ingest (the public screenshot-push leg), still waiting on
  the user.** Once Cloudflare R2 credentials arrive: wire
  `DF_STREAM_INGEST_URL` in `.env`, convert `curl -F` to an S3-compatible
  signed PUT, fill in `IMAGE_BASE` in
  `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, ask
  before pushing/deploying either repo.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

## Archived

- Sections for the week of 2026-08-24 moved to
  [`working-archive/Working_archive-2026-08-24.md`](working-archive/Working_archive-2026-08-24.md).
- 2026-08-27 through 2026-09-08: provisioning build, host-RAM blocker,
  perception eval, fort ledger, VM-start, provisioning-hardening,
  DF-install-scripting, systemd-unit handovers — all moved wholesale to
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
