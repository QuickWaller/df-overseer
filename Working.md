# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## Current state, 2026-09-24 evening (read this first)

**The office exists and the game accepts it.** Carved into stone off the Still, all 15 ring walls smooth, floor deliberately left rough (v1 template gap, fixed for next time in `office-room-v2`), a stone throne inside, Office zone 13 owned by the Manager (unit 345, both link directions confirmed live). The user confirmed in the game that it looks right and the nobles screen accepts it. Our own read disagreed (`nobles requirements MANAGER` said `not_met`) because `getRoomDescription` returns empty on this fort even for an accepted room, a **false negative in the proxy**, now fixed: an empty description alone can no longer resolve to `not_met` (it needs independent evidence, i.e. no qualifying furniture inside the zone, from the new `zone contents` read). Deployed and live-verified.

**Manager orders still do not dispatch.** `nobles verify MANAGER` is `consistent: true` (a live, resolved appointment; this rules out the Consultant's top-ranked cause). A direct Mason's job (no manager involved) dispatched and was worked normally. The four manager orders (0–2 hand-validated 2026-09-19, 3 still `validated: false`) never produce a job with a populated `order_id`, across ~5000 fort ticks over two runs. **User's ruling: set this aside** ("sometimes the bro is having a nap or some chow, don't worry about it"); revisit only if it still doesn't move after a proper stretch of running.

**The ghost (Kadol Zulbanurdim, unit 454, a Forlorn haunt) has been laid to rest. Resolved, not in progress.** Memorial slab ruled out (no tool can queue the engraving job); a coffin was built (building 14), but DF requires a **Tomb zone over the coffin** to receive a body, and `zone place` lacked the furniture-exemption flag `zone find` already had. Fixed (`zone place ... AROUND_FURNITURE`), deployed and live-verified: dry run confirmed the coffin at `distance_tiles: 0`, real placement created Tomb zone 16 owning building 14 (coffin site not moved, per the user's ruling that this experimental fort's coffin site doesn't need to be optimal). A bounded unpause (2,041 of a 6000-tick budget) then showed, in direct struct reads not inference: corpse item 2804 moved into building 14, unit 454's `flags3.ghostly` flipped `true` → `false` and it left the active-unit list, and the game generated its own report: "Kadol Zulbanurdim, Ghostly Gem Setter has been put to rest." Full detail in `evals/live/2026-09-24-ghost-slab/README.md` Stage D. **The coffin's known-suboptimal site (chosen by a haul-distance heuristic that doesn't apply to a one-time placement, see the ranking-system decision below) is now load-bearing** — a live Tomb zone sits on it; relocating it later is a new zone+building operation, not a simple move.

**Both pending fixes are deployed and live-verified**: `zone place`'s `AROUND_FURNITURE` flag (above) and `jobs_claimed_by_a_worker` (returned `null` for a site with zero jobs, indistinguishable from a failed read; now returns `0`). Deployed via `git -c core.autocrlf=false archive`, sha256-verified twice, `dfmcp-server` restarted (`df-fortress`/`df-xvfb` untouched). Live role tool counts unchanged in shape before/after (overseer 79, architect 49, quartermaster 24, conductor 15); **consultant reads 27 live, not the 28 recorded below** — not caused by this deploy (same both sides of it), not yet investigated, worth a look next session.

**The site-ranking system needs a real redesign, not a patch.** `ranked_rects` (df-overseer-zone.lua) is one static sort: furniture-match, then a kind-level `prefer_indoors` boolean with no per-situation override, then raw distance to a caller-picked landmark — the same mechanism for a production building's stockpile proximity and a one-time furniture placement with no ongoing relationship to what it's near. User's call: this connects to an earlier, undesigned district/zoning idea (areas of the fort designated for production, living, misc) and needs a dedicated, in-depth design session with an Opus model and the user, together with the broader openclaw architecture — not an incremental ranker patch. → `ROADMAP.md` Later bucket, `decisions/DECISIONS.md` 2026-09-24.

**The Consultant's wiki mirror is built, deployed to VM 103 and holds its first real pull; the Consultant does not read it yet.** `wikimirror/` (S1 to S6, merged) deployed 2026-09-24 as `/opt/df/wikimirror/`, run by a new unprivileged `dfwiki` user, env in root-owned `/etc/dfwiki.env` (contact: the project's public GitHub URL, user's go-ahead). First full pull: 109 of 800 requests, about 5 minutes, 4,450 of 4,450 pages, 15,251 chunks (204 degraded on 129 pages), 59 MB, promoted after its own 5.1 checks; one manual refresh ran ok (sweep, 20 requests). Orchestrator re-checked on the VM: integrity ok, 4,450 pages, Office and Tomb present. **Not done, and needs its own confirmed step:** the `dfmcp-server` switch-over (point `MCP_SERVER_WIKI_SNAPSHOT` at `/var/lib/dfwiki/df-wiki.sqlite3`, restart, and a read-permission decision, since `dfmcp-server` runs as `df` and the directory is `dfwiki`-only, 750) and the refresh/sweep timers (S8). The user's one-week hold on recent edits applies from here on. The old 30-page JSON snapshot is backed up, not deleted. A small follow-up is still owed for four gaps S6 found in S1's `store.py` (see register). -> `evals/live/2026-09-24-wiki-mirror-deploy/`.

**df-ai researched for the districting design** (`research/2026-09-24-df-ai-fort-planner.md`): one fixed hand-authored plan placed by random retry against a pass/fail checklist, abandons the fort on failure, no distance or adjacency solving, no growth, last commit 2022-10-10 for DF 0.47.05 (head hash verified by the orchestrator). Transfers: named room templates with typed exits, tags as a map-free district primitive, hard checks kept separate from site choice, a periodic recheck and a per-room status vocabulary. It is not the answer to adjacency; one more pass (facility layout's relationship chart and block layout, land-use zoning, a map-free district representation) is the remaining gap before the design session.

**The Consultant was asked two real questions today and judged well** (ghost handling, then order-dispatch diagnosis), see `evals/live/2026-09-24-consultant-*/`. One critique that stuck: its ghost answer buried the Tomb-zone requirement inside a throwaway clause rather than flagging it as a distinct hard mechanic, the same pattern it *did* call out correctly for the Office/Chair case. Worth remembering when judging future answers.

**Other live findings, not yet acted on:**
- The office ring includes an unmined hematite vein, smoothed instead of mined out. No harm done (smoothing doesn't destroy ore) but it needs mining and a constructed wall built after. The verb and the material read don't currently distinguish ore from ordinary stone, noted for later, not fixed.
- Design thoughts from the user, recorded as open, not decided: rooms need not always be smoothed or enclosed (agent/kind judgement call); doors are per-kind policy, not a blanket rule; a "remove furniture → smooth → replace furniture" later-hands capability is needed; dormitories are a candidate second template.
- Two self-pauses during an early run were never explained (no tripwire, no advisory); did not recur in later runs. Watch for it.

**Deployed and live-verified today, in order:** surface perception layer + furniture-aware ranking; access fix (`zone find`/`apply` orientation, stall detection) + `release`; the owner tool (`zone assign-owner`/`clear-owner`); the room-proxy fix + `zone contents`; the blueprint status fixes (`dig_progress`, `shell_done`) + the runner `final` envelope fix; `zone place`'s `AROUND_FURNITURE` flag + `jobs_claimed_by_a_worker`'s zero-vs-null fix, live-checked by placing the ghost's Tomb zone for real.

**Pushed to `origin/main`** at `275700d` (75 commits, all one author, checked before push): today's full day of work plus everything queued since the last push.

**Still open:** the tiling generator for `bedroom-cell-v1`; burrow confinement ruling; `df-overseer-breach.lua` header and ROADMAP line correction; leaked key rotation (below); the site-ranking redesign (above, gated on a dedicated Opus session); consultant's live-vs-recorded tool count discrepancy (27 read live vs. 28 recorded, unrelated to today's deploy, not investigated); the small wiki S1 follow-up (four gaps in `store.py`); the wiki `dfmcp-server` switch-over and timers (needs its own go-ahead); wiki S7/S8 not yet dispatched; the districting prior-art pass (relationship chart, land-use zoning, map-free representation); the ore/hematite fix (mine the vein, build a constructed wall, deferred by the user).

**Archived this pass:** everything before today's work (the agent-loop MVP design history, the learning-loop discussion, and older handovers) moved wholesale to [`working-archive/Working_archive-2026-09-24.md`](working-archive/Working_archive-2026-09-24.md); the file was 1091 lines, well past the 400-line threshold, and none of it was still-open work.

## Open: rotate leaked keys (2026-09-17)

A session ran `cat .env | grep -v SECRET` while looking up the VM 103 SSH
user, breaking the "read secrets by the key you need" rule — it printed
`ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`, and
`CLOUDFLARE_TUNNEL_TOKEN_ADMIN` into the session transcript in full. User's
call: rotate later, not urgent, but don't lose the item. → decisions/DECISIONS.md
2026-09-17.

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
- 2026-09-24: everything from "In design: the agent loop MVP" through "HANDOVER — archived" (the agent-loop MVP design phase and its later additions, the learning-loop discussion, the 2026-09-23 loop-closed handover and its streams, and the 2026-09-21 handover) moved wholesale to [`working-archive/Working_archive-2026-09-24.md`](working-archive/Working_archive-2026-09-24.md); the file was 1091 lines. None of the moved content was still-open work. Everything still open (the office, the ghost, the wiki mirror, deploy backlog, ore, design thoughts) is in the current-state section at the top, freshly written rather than carried forward line by line, since almost none of the old text was still accurate.
