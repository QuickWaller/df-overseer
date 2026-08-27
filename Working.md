# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-08-27 (late evening), work paused here

**State at a glance.** Three things are now true that were not true this
morning: the perception bet is measured and accepted, the fort ledger exists
and is tested, and **the DF VM is running for the first time**. The game side
is still entirely unbuilt, and the guest is a bare Ubuntu with nothing
installed on it. Local `main` is **8 commits ahead of origin and unpushed**.

### Where things stand

1. **Perception eval: done for this phase.** `exits_v1` ties `coords_v1` at
   99.1%, n=108 per representation, `accepted` in the register. $1.14 across
   three live runs. Standing caveat: hand-authored 15-landmark fixtures, not
   the lossier production generator.

2. **Fort ledger: built.** `ledger/`, JSONL, git-tracked, **deliberately
   empty**. `python -m ledger.selftest` passes, including eleven negative
   checks that break each validator rule on purpose. Six decision entries
   record the design calls. Nothing in it is verified against DFHack:
   `schema.MECHANICAL_PATH_VERIFIED` is `False`, and every `MECHANICAL` field
   is still a bet that code can read that value from game state.

3. **VM 104 `df-fortress` is running.** 4096 MB / 2048 balloon, 4 cores,
   Ubuntu 24.04.4, `df@<df-vm-ip>`, SSH key verified. Host sits at 3.2 GiB
   available with it up. Full record in `memory/proxmox-access.md`.

4. **Repo is public** at [github.com/QuickWaller/df-overseer](https://github.com/QuickWaller/df-overseer),
   `gh` authenticated (QuickWaller). **8 local commits are unpushed**, covering
   the ledger, the handover, and the VM work. Push is gated on an explicit
   go-ahead each time, so ask.

### Three operational facts a next session will otherwise get wrong

**This machine is on the `aa14` tailnet now.** The Proxmox host is only
reachable from there: `tailscale` (<tailnet-router-ip>) advertises `<lan-subnet>/24`,
and the `<tailnet-b-account>` tailnet has no such router. Earlier sessions recorded
the unreachability as a transient peer dropout and advised retrying; that
diagnosis was wrong and retrying could never have worked. **Side effect:** this
machine is off the `<tailnet-b-account>` tailnet, so `gitea`, `secrets` and the
tenant hosts are unreachable from here until it switches back
(`tailscale switch 1052`).

**The VM's IP is an unreserved DHCP lease.** Do not pin `<df-vm-ip>`
anywhere. Read it from the guest agent, or reserve it on the router first.

**The template does not install `qemu-guest-agent`.** `agent: enabled=1` only
opens the virtio channel on the Proxmox side; without the package in the guest
every `/agent/*` call returns 500 and the API cannot report an IP. Installed by
hand on 104, but **`cmd_build_template` still has the gap** and the next
template built from it will repeat this. Fixing that is a two-line cloud-init
change and has not been done.

### What a next session should pick up

**1. Install DF Classic and DFHack on the guest, and prove they run.** This is
the recommendation, and it displaces the compliance harness that the previous
handover put first. Three reasons. The guest is bare, so *every* game-side item
in `docs/PURPOSE.md`'s build order is blocked behind this one step. The
2026-08-26 decision to drop Steam in favour of DF Classic is still completely
untested. And 4096 MB is a new, unvalidated ceiling: worldgen is the memory
spike, there is no swap, and whether DF worldgens comfortably in 4 GB is now a
real open question rather than a theoretical one.

Also worth doing while there: check `memory/dfhack-environment.md`'s claims
against the actual install on the VM. That file was written against the local
Windows DFHack, and several tools are recorded as shipped-but-unavailable.

**2. Then `check_reachable` / `get_connectivity_report`** (`docs/PURPOSE.md`
build item 2). It copies `warn-stranded.lua`'s working algorithm and is the
highest-confidence real code in that list.

**3. The compliance eval harness, whenever there is an afternoon.** This is
`research/2026-08-25-learning-architecture.md` build item 1, described there as
"do first, before any fort runs". It needs no game and no agent, so it is never
blocked and can slot in anywhere. It retires a caveat the register has carried
since 2026-08-25: the N=80 doctrine-size threshold is a single unreplicated
study and our own compliance curve is unmeasured. It can reuse the perception
harness's whole shape (matrix runner, JSONL results, `report.py`, cached-prefix
layout), so it is mostly assembly.

It is listed third rather than first only because the VM coming up changed what
is scarce. If the VM turns out to be a time sink, do this instead rather than
grinding.

**4. Mechanical prediction grading** (research build item 3): compare a
prediction's `signal` field against recorded state at `check_at`. Cheap, and no
prediction-based calibration metric means anything until it exists.

**5. The ledger's write path is its real test, and it waits on the perception
layer.** `defense_depth`, `primary_industry` and `surface_footprint` are the
fields likeliest to have no clean mechanical reading; if so they get demoted to
`AGENT` and become colour rather than evidence.

**6. Re-run the perception eval against real briefings once `llm-brief.lua`
exists.** Today's numbers are on generous hand-authored fixtures; the real
generator is lossier (3 nearest neighbours, geometric distance).

### Housekeeping, carried forward

- **Fix `cmd_build_template` to install `qemu-guest-agent`** (see above). New
  this session.
- **Reserve the VM's DHCP lease, or add swap**, or consciously decide neither
  matters. New this session.
- **Proxmox token not rotated**, pasted into an earlier transcript. Datacenter
  > Permissions > API Tokens > `api` > Remove, re-Add, update
  `PVE_TOKEN_SECRET` in `.env`.
- **Temporary Anthropic key in `.env` expires ~2026-09-03** (user-supplied
  2026-08-27). Rotate or remove after use; do not commit or log it.
- **Template 101 is still sized 6144 MB.** Harmless while it is never started,
  but clones inherit it, so the next clone will need the same resize VM 104
  just had.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent` still deferred.** The multi-agent
  decomposition point from 2026-08-27 adds a criterion but does not resolve it.
- **DF replay determinism unverified**, and the seeded-counterfactual rerun
  harness (research build item 7) rests entirely on it.
- **`hypothesis_id` has no registry.** Ledger observations reference
  hypotheses by bare string and nothing checks the id exists. Belongs with
  research build item 4, but a typo before then silently orphans evidence.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. They are fine as structural separators
(aligned definition lists, index lines).

## Archived

- Sections for the week of 2026-08-24 (the design phase, the access-layer
  build, and the host-RAM blocker) moved to
  [`working-archive/Working_archive-2026-08-24.md`](working-archive/Working_archive-2026-08-24.md).
- 2026-08-27: the provisioning-build handover and the 2026-08-26 storage-blocker
  detail (both finished/superseded) moved to the same archive file.
- 2026-08-27 (evening): the afternoon perception-eval section (it reported
  itself finished) and the afternoon handover (superseded by the one above)
  moved to the same archive file.
- 2026-08-27 (late evening): the fort-ledger section and the VM-start
  section, both finished, moved to the same archive file.
