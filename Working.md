# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-08-27 (evening), work paused here

**State at a glance.** The provisioning layer is now finished and *proven*,
not just written: a template build produces a VM whose IP the API can report
by itself, and a clone of it comes up as its own machine. That was a detour.
The game side remains entirely unbuilt, and **that is what a next session
should do**. Local `main` is **12 commits ahead of origin and unpushed**.

### What changed this session

Two provisioning gaps were closed, both of which had produced failures that
read as something other than what they were.

1. **MACs are derived from the vmid and pinned at clone time.** Proxmox rolls
   a random MAC whenever a NIC is created, *including on clone*, so deleting
   and rebuilding a VM orphaned its DHCP reservation and the symptom looked
   like "the static IP stopped working". VM 104 keeps its existing
   `<reserved-mac>` via `MAC_OVERRIDES`, matching the reservation the user
   made on the router; new VMs get `BC:24:11:00:hi:lo`.

2. **`qemu-guest-agent` is baked into the template.** The bake boots the VM
   once at 2048 MB, installs over SSH at `DF_BUILD_IP`, proves the agent
   answers, seals cloud-init state and hard-stops. **Template 101 is rebuilt
   at 4096 MB**, so clones no longer need the resize VM 104 needed.

**Both are verified end to end.** Cloning 101 produced VM 105 with a fresh
SSH host key, repopulated `machine-id`, fresh `instance-id`, `cloud-init
status: done` and `qemu-guest-agent` active, **and the API reported its
address (`<pve-host>0`) with no static configuration** — the capability
whose absence forced VM 104 to be found by port-scanning the subnet.

Six bugs surfaced only by running it, all fixed and recorded in
`decisions/DECISIONS.md`: the post-import resize timeout, `/agent/ping` being
POST rather than GET, sealing breaking graceful shutdown, `os.devnull` being
`"nul"` on Windows, and the vmid-collision finding below.

### Operational facts a next session will otherwise get wrong

**This machine is on the `aa14` tailnet.** The Proxmox host is only reachable
from there: `tailscale` (<tailnet-router-ip>) advertises `<lan-subnet>/24`, and the
`<tailnet-b-account>` tailnet has no such router. **Side effect:** `gitea`,
`secrets` and the tenant hosts are unreachable from here until it switches
back (`tailscale switch 1052`).

**`next_vmid()` is the only safe source of a vmid.** Cloning to a hand-picked
`--vmid 102` failed: VM 102 exists on this host *outside* the `df-overseer`
pool, so our token cannot see it (`403 VM.Audit`) and `pool_members()` does
not list it. **The pool view is not the host view.** Never pick an id by eye.

**The host cannot fit a 4096 MB VM alongside 104.** It sits at ~3.8 GiB
available with 104 up. `start` enforces this and refuses under 1 GiB
headroom; `set-memory` is the way down, and it refuses on a running VM.

**DHCP pool is `.100`-`.199`.** `DF_BUILD_IP=<build-ip>/24` sits just
outside it and is held only during a template build.

### What a next session should pick up

**1. Install DF Classic and DFHack on VM 104, and prove they run.** This has
been the recommendation for two sessions and keeps getting displaced. The
guest is bare, so *every* game-side item in `docs/PURPOSE.md`'s build order
is blocked behind it. The 2026-08-26 decision to drop Steam for DF Classic is
still completely untested. And 4096 MB is an unvalidated ceiling: worldgen is
the memory spike and there is no swap. Also check
`memory/dfhack-environment.md`'s claims against the real Linux install; that
file was written against the local Windows DFHack.

**2. Then `check_reachable` / `get_connectivity_report`** (`docs/PURPOSE.md`
build item 2). It copies `warn-stranded.lua`'s working algorithm and is the
highest-confidence real code in that list.

**3. The compliance eval harness, whenever there is an afternoon.** Research
build item 1, described there as "do first, before any fort runs". Needs no
game and no agent, so it is never blocked. It retires the standing caveat
that the N=80 doctrine-size threshold is a single unreplicated study, and it
reuses the perception harness's whole shape, so it is mostly assembly.

**4. Mechanical prediction grading** (research build item 3): compare a
prediction's `signal` field against recorded state at `check_at`. No
prediction-based calibration metric means anything until it exists.

**5. The ledger's write path waits on the perception layer.**
`defense_depth`, `primary_industry` and `surface_footprint` are likeliest to
have no clean mechanical reading; if so they get demoted to `AGENT`.

**6. Re-run the perception eval against real briefings once `llm-brief.lua`
exists.** Today's 99.1% is on generous hand-authored fixtures; the real
generator is lossier.

### Housekeeping, carried forward

- **VM 105 `df-seal-test` is stopped but not destroyed.** It is a linked
  clone created purely to verify sealing and has served its purpose. It needs
  an explicit go-ahead to destroy, which was not given before the session
  ended. Destroy it, or keep it as a cheap DF install target.
- **Add swap to 104**, or consciously decide it does not matter, before
  worldgen is attempted in 4096 MB.
- **Proxmox token not rotated**, pasted into an earlier transcript.
  Datacenter > Permissions > API Tokens > `api` > Remove, re-Add, update
  `PVE_TOKEN_SECRET` in `.env`.
- **Temporary Anthropic key in `.env` expires ~2026-09-03**. Rotate or remove
  after use; do not commit or log it.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent` still deferred.**
- **DF replay determinism unverified**, and the seeded-counterfactual rerun
  harness (research build item 7) rests entirely on it.
- **`hypothesis_id` has no registry.** A typo silently orphans evidence.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

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
- 2026-08-27 (evening): the late-evening handover, superseded by the
  provisioning-hardening handover above, moved to the same archive file.
