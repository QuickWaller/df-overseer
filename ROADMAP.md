# Roadmap

**Last reviewed:** 2026-09-10 (sixth pass — Uniboslan's first room and stockpile dug)

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
- **Next: the real burrow/building enumeration + adjacency graph**
  (`docs/PURPOSE.md` build order item 3's remaining scope) now has
  something real to work against — the stockpile above is a genuine
  `building` object, the first non-seed landmark candidate. Still needs
  to happen on `perception-layer-experiments`, not `main`. If the
  "Confirm"/map-click crash recurs on a future embark, running it under
  gdb again is the known workaround, not a fix. → `Working.md` handover.
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
  straight into the viewer). Relay is `df-colony-relay-01.internal`
  (`192.168.2.202`, Debian 12, home-lab's Proxmox pool). Feed is
  intentionally unauthenticated (`x11vnc -nopw`) but stays `-viewonly` —
  anyone with the link can watch, nobody can act. Linked live from
  `willsmith-portfolio/public/dwarf-fortress/index.html`.
  → `research/2026-09-09-reverse-vnc-relay.md`,
  `decisions/DECISIONS.md` 2026-09-09 rows, `Working.md`.
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

- **Wire up the live-view ingest, blocked on Cloudflare console work only.**
  Screenshot capture itself is built and verified on VM 103
  (`install_df.py stream`); the only missing piece is an R2 bucket + API
  token, cost-checked at $0/month for this traffic shape. Exact setup steps
  and what to do once the credentials land are in `Working.md`'s live-view
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
- **`cpu: host` → `x86-64-v2-AES`** in `provision_vm.py`, needed so the two
  cluster hosts (different CPU generations) can migrate VMs between them.
  Accepted, not yet implemented; takes effect on the rebuilt VM's next cold
  stop/start.
  → `decisions/DECISIONS.md` 2026-08-28 row.
- **`check_reachable` / `get_connectivity_report`.** Copies
  `warn-stranded.lua`'s working algorithm; highest-confidence real code to
  write next. → `docs/PURPOSE.md` build order item 2. **A first pass
  exists on the `perception-layer-experiments` branch** (not merged,
  user's explicit call to keep this experimental and off `main` for now)
  — see `Working.md`'s handover before rebuilding this from scratch.
- **Landmark system on burrows + exits-first representation.**
  → `docs/PURPOSE.md` build order item 3. Same branch has an experimental
  seed-landmark first slice; see `Working.md`.
- **`get_overview` / context tiering with deterministic JSON.** Must sort
  keys: Lua table order isn't guaranteed and a reshuffle silently busts the
  prefix cache every turn. → `docs/PURPOSE.md` build order item 4.
- **`get_diff_since` via `eventful`.** → `docs/PURPOSE.md` build order item 5.
- **`find_open_area` (built terrain), then `find_chokepoints` /
  `rank_candidate_sites`, then `get_stuck_jobs`** (least-verified primitive,
  test in isolation). → `docs/PURPOSE.md` build order items 6-8.
- **Measure a running fort's memory over time**, now that one exists
  (`decisions/DECISIONS.md` 2026-09-10, "First fort founded"). Worldgen's
  peak (561 MB) is measured; a fort at year 5 with 100 dwarves is not, and
  this would also give a real number for `TimeoutStopSec`'s quicksave
  margin. → `docs/PURPOSE.md` open questions.
- **The compliance eval harness.** Cheapest research build item, do before
  any fort runs: load synthetic doctrine at increasing rule counts, measure
  where compliance degrades. No game, no agent, never blocked.
  → `research/2026-08-25-learning-architecture.md` §7 item 1.

## Later
<!-- Real, worth tracking, but genuinely further out or gated on scale/decisions not yet made. -->

- **`find_open_area` (cavern terrain).** Genuinely hard, deliberately last
  in the build order. → `docs/PURPOSE.md` build order item 9.
- **Mechanical prediction grading.** Scripted comparison of a `signal` field
  against recorded state at `check_at`; needed before any prediction-based
  calibration metric means anything. → `research/2026-08-25-learning-architecture.md`
  §7 item 3.
- **The fort ledger's write path** for the remaining fields waits on the
  perception layer existing. → `ledger/README.md`.
- **Re-run the perception eval against real briefings** once `llm-brief.lua`
  exists, replacing today's hand-authored 15-landmark fixtures with the
  actual lossier generator. → `docs/PURPOSE.md` build order item 1's caveat.
- **Seeded counterfactual rerun harness**, the only real answer to the
  control-arm problem for "doctrine improved outcomes" claims. Rests on DF
  replay determinism, which is unverified. → `research/2026-08-25-learning-architecture.md`
  §7 item 7, `Working.md` handover ("DF replay determinism is unverified").
- **Host-reboot survival test**, re-scoped to whichever VMID the current
  rebuild produces (VM 104 no longer exists). Complicated now by `citadel`'s
  missing QDevice: a reboot of `SRV-01` while `SRV-02` is also down would be
  a real inquorate-cluster test, not just a VM-restart test. Needs the
  user's go-ahead first either way (destructive/hard-to-reverse actions
  rule). → `working-archive/Working_archive-2026-09-07.md`, "Host-reboot
  survival is still unverified".
- **`openclaw` vs `hermes-agent`** as the driving brain, still deferred.
  Tiebreaker is meant to be empirical: which survives 30 days unattended.
  → `decisions/DECISIONS.md` 2026-08-25 row, 2026-08-27 multi-agent-by-task
  row.
- **Loop shape, multi-agent split, first display to build (game view vs.
  chronicle e-ink), and the time-sliced adventure-mode design.**
  → `docs/PURPOSE.md` Open Questions.
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
