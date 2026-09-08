# Roadmap

**Last reviewed:** 2026-09-08

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

> **Rewritten 2026-09-08.** The previous Now bucket was stale in a way worth
> naming: its top item asked a question ("reinstall or rebuild the Proxmox
> host?") that was answered a week ago, and it had no awareness that this
> project's VM and template were both deleted on 2026-09-01. This repo went
> quiet on 2026-08-30 while the estate underneath it was rebuilt. Full
> analysis: `infra/local.2026-09-08-doc-reorg-plan.md` (gitignored, it quotes
> home-lab's own infra specifics; a clone of this public repo will not have
> it).

> **Identity proven 2026-09-08.** The token secret is in `.env` and
> `provision_vm.py status` answered from this workstation: 12.5 GiB available,
> next free vmid 102, pool empty (which independently confirms the 2026-09-01
> deletion rather than a visibility problem). That call also exercised the
> auth-header fix; an unauthenticated client returns `401`, not data.

> **VM rebuilt, renamed and installed, 2026-09-08.** `clone --full` produced
> VM 103 at the user-supplied `DF_VM_IP=192.168.2.201/24`; renamed to
> `df-colony-01` in Proxmox with `df-colony-01.internal` as its OS hostname
> (`.internal` is DNS-plus-hostname, never the bare Proxmox name — that split
> is now scripted as `install_df.py`'s `step_hostname`). `install_df.py
> install`, `systemd`, and `provision_vm.py set-onboot --enable` all ran
> clean; `verify` reports all checks passed. No world exists yet; DF has not
> been started. → `decisions/DECISIONS.md` 2026-09-08 rows.

- **Generate a world and start DF on VM 103** whenever wanted:
  `install_df.py gen`, then `start`. Nothing runs unattended until this
  happens.
- **If a write step fails oddly, check quorum before suspecting permissions.**
  The cluster has no QDevice and the second node is unwell, so a single node
  can drop below quorum and make every config write fail with an error that
  reads exactly like a permissions fault. `pvecm status` first, always.
- **Rotate or remove the temporary Anthropic key in `.env`.** It expired
  ~2026-09-03 and is now past due — the previous version of this line predicted
  that and did not prevent it, which is the argument for doing it now rather
  than re-dating it. Do not commit or log it.

## Next
<!-- Clearly in line, not yet started. -->

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
  §7 item 7, `Working.md` handover ("DF replay determinism is unverified").
- **Host-reboot survival test**, re-scoped to whichever VMID the current
  rebuild produces (VM 104 no longer exists). Complicated now by `citadel`'s
  missing QDevice: a reboot of `SRV-01` while `SRV-02` is also down would be
  a real inquorate-cluster test, not just a VM-restart test. Needs the
  user's go-ahead first either way (destructive/hard-to-reverse actions
  rule). → `working-archive/Working_archive-2026-09-07.md`, "Host-reboot
  survival is still unverified".
- **`citadel` has no QDevice.** The reinstall-vs-rebuild question that used
  to gate clustering is answered and the cluster already exists; the
  QDevice is the real remaining gap, and until it lands a two-node cluster
  is worse than two standalone hosts (either node down leaves the survivor
  unable to start, stop, or edit anything). → `decisions/DECISIONS.md`
  2026-08-28 clustering row.
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
