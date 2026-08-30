# Roadmap

**Last reviewed:** 2026-08-31

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

- **Reinstall or rebuild the Proxmox host?** Full reinstall on the ProDesk vs.
  rebuilding the `df-overseer` pool/VMs on the existing install, still
  unanswered across three sessions. Gates cluster creation; do not infer an
  answer from silence. → `Working.md` "Decisions still owed by the user" #1.
- **Delete the eight test worlds?** `region1`-`region8` plus a stale 4 KB
  `save/current`, destructive so left alone until the user says go.
  → `Working.md` "Decisions still owed by the user" #2.
- **Temporary Anthropic key in `.env` expires ~2026-09-03.** Rotate or
  remove before then; do not commit or log it. → `Working.md` housekeeping.

## Next
<!-- Clearly in line, not yet started. -->

- **`cpu: host` → `x86-64-v2-AES`** in `provision_vm.py`, needed so the two
  cluster hosts (different CPU generations) can migrate VMs between them.
  Accepted, not yet implemented; takes effect on 104's next cold stop/start.
  → `decisions/DECISIONS.md` 2026-08-28 row.
- **`check_reachable` / `get_connectivity_report`.** Copies
  `warn-stranded.lua`'s working algorithm; highest-confidence real code to
  write next. → `docs/PURPOSE.md` build order item 2.
- **Landmark system on burrows + exits-first representation.**
  → `docs/PURPOSE.md` build order item 3.
- **`get_overview` / context tiering with deterministic JSON.** Must sort
  keys: Lua table order isn't guaranteed and a reshuffle silently busts the
  prefix cache every turn. → `docs/PURPOSE.md` build order item 4.
- **`get_diff_since` via `eventful`.** → `docs/PURPOSE.md` build order item 5.
- **`find_open_area` (built terrain), then `find_chokepoints` /
  `rank_candidate_sites`, then `get_stuck_jobs`** (least-verified primitive,
  test in isolation). → `docs/PURPOSE.md` build order items 6-8.
- **Embark, and measure a running fort's memory.** Worldgen's peak (561 MB)
  is measured; a fort at year 5 with 100 dwarves is not, and this would also
  give a real number for `TimeoutStopSec`'s quicksave margin.
  → `docs/PURPOSE.md` open questions.
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
  §7 item 7, `Working.md` housekeeping ("DF replay determinism unverified").
- **Host-reboot survival test itself.** Guest-reboot survival is proven and
  `onboot=1` is set and read back; nobody has power-cycled the physical
  Proxmox host to watch VM 104 come back unattended. Needs the user's
  go-ahead first (destructive/hard-to-reverse actions rule).
  → `Working.md` 2026-08-30 handover, "Host-reboot survival is still
  unverified".
- **Cluster the ProDesk and the incoming EliteDesk**, once the reinstall-vs-
  rebuild decision above lands. Not for HA; buys one API, migration, and
  replicated `/etc/pve`. Gated on a Pi qdevice before it's better than two
  standalone hosts. → `decisions/DECISIONS.md` 2026-08-28 clustering row.
- **The ProDesk's RAM slot layout is still unknown**, and the SSD out of the
  Omen has an unverified size. Both matter once hardware work on the cluster
  starts. → `Working.md` housekeeping.
- **`openclaw` vs `hermes-agent`** as the driving brain, still deferred.
  Tiebreaker is meant to be empirical: which survives 30 days unattended.
  → `decisions/DECISIONS.md` 2026-08-25 row, 2026-08-27 multi-agent-by-task
  row.
- **Loop shape, multi-agent split, first display to build (game view vs.
  chronicle e-ink), and the time-sliced adventure-mode design.**
  → `docs/PURPOSE.md` Open Questions.

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
