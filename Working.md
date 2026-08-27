# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-08-27 (night), work paused here

**State at a glance.** The game is on the machine and it runs. VM 104 now has
DF Classic and DFHack installed, running headless, answering RPC, and
generating worlds from the command line without anyone touching a UI. The
two-session-old blocker in front of every game-side item is gone. `docs/`,
memory and the decision register are all reconciled against what is actually
on the VM, so this is a clean point to stop. Local `main` is **16 commits
ahead of origin and unpushed** (the previous handover said 12; it was already
undercounting, so trust `git rev-list --count origin/main..main`, not the
number written in a doc).

### What changed this session

**Swap first.** `/swapfile`, 4 GB, `vm.swappiness=10`, in `/etc/fstab`. It has
never been touched since, which turns out to be the finding rather than the
fix: see the memory numbers below.

**DF v0.53.16 linux64 (build tag `ITCH`) and DFHack 53.16-r1.1** are installed
at `/opt/df/game`. DFHack is the *same version as the Windows install*, so
`memory/dfhack-environment.md` carries over, and an audit against the real
Linux install confirmed it does: all eleven tools it calls unavailable are
unavailable here, every load-bearing tool is available, confirmed at runtime
via `helpdb` and not just from the doc tags. The 2026-08-26 decision to drop
Steam for DF Classic is now tested rather than assumed.

**It runs headless under Xvfb**, which revisits the 2026-08-25 rejection of
headless DF. That rejection was right that no text mode exists, and beside the
point: nobody looks at the window, and a virtual framebuffer satisfies SDL for
a few MB. `dfhack-run lua` executes remotely and the RPC server listens on
`127.0.0.1:5000`. Design commitment #1 is untouched.

**Worlds generate from the command line**: `./dfhack -gen <id> <seed>
"POCKET ISLAND"` runs silently and quits, ~12 seconds for a 17x17 world that
stops at year 30 and saves ~900 KB. Tiny worlds are the user's call for now.

Full detail, including the package list and the exact launch commands, is in
**`memory/df-vm-install.md`**.

**`docs/PURPOSE.md` was reconciled against reality**, not just appended to.
The provenance note, the DF Classic section, the VM sizing paragraph and the
build order all made claims that this session either confirmed or falsified.
The build order gained an item 0 for the install, item 1 is marked done, and
two open questions were replaced: the stale one about repo conventions (long
since adopted) is gone, and embark-scriptability plus a running fort's memory
ceiling are now written down as the real unknowns.

One drift worth knowing about, found while reconciling: both `PURPOSE.md` and
`memory/dfhack-environment.md` cited `FPS_CAP` and `G_FPS_CAP` as
`prefs/init.txt` **lines 22 and 23**. That is true of the Windows install and
wrong for the VM, where they are lines 71 and 75. A script seeking those line
numbers would not error, it would quietly edit the wrong settings. Both docs
now name the tokens and say the numbers differ per install.

### Things a next session will otherwise get wrong

**Saves are not in the game directory.** They are at
`~/.local/share/Bay 12 Games/Dwarf Fortress/save/`. A backup or snapshot script
written against `<df>/data/save`, which is what pre-v50 habit and most
community writeups say, finds nothing and reports success.

**`-gen` fails silently about a quarter of the time.** Two of eight runs exited
1 having generated the whole history into `save/current`, then never renamed it
and never wrote an export, with nothing in `gamelog.txt`, `errorlog.txt`,
stdout or stderr. Detect by the absence of the region directory, never by exit
code, and retry with a fresh seed. Exit 134 is the separate documented abort
for an id that already exists. Not DFHack's doing; it reproduces either way.

**Worldgen is not the memory spike everyone assumed.** Peak RSS **561 MB**
across a whole `POCKET ISLAND` gen, sampled every 0.5s, swap untouched,
available memory never below 2.5 GiB. **This measures worldgen only.** A
long-running fort with hundreds of units is the actual memory question and is
still unmeasured, so 4096 MB is not yet vindicated, just not refuted here.

**Nothing survives a reboot.** Xvfb and DF are both running under
`setsid nohup`. There is no systemd unit yet.

### What a next session should pick up

**1. Systemd units for Xvfb and DF**, plus a save-backup job pointed at the
XDG path. Small, and everything long-running depends on it. A fortress meant
to run a month cannot be held up by a `nohup` from an ssh session.

**2. `check_reachable` / `get_connectivity_report`** (`docs/PURPOSE.md` build
item 2). Copies `warn-stranded.lua`'s working algorithm, and there is now a
real DFHack to run it against. Highest-confidence real code in that list.

**3. Embark, and measure a running fort's memory.** The 4096 MB ceiling is
still an open question and worldgen did not answer it. Embarking also needs
UI driving, which `-gen` neatly avoided, so it is worth finding out early how
much of that is scriptable.

**4. The compliance eval harness, whenever there is an afternoon.** Research
build item 1, "do first, before any fort runs". Needs no game and no agent, so
it is never blocked. Retires the standing caveat that the N=80 doctrine-size
threshold is a single unreplicated study, and reuses the perception harness's
shape, so it is mostly assembly.

**5. Mechanical prediction grading** (research build item 3): compare a
prediction's `signal` field against recorded state at `check_at`. No
prediction-based calibration metric means anything until it exists.

**6. The ledger's write path waits on the perception layer.** `defense_depth`,
`primary_industry` and `surface_footprint` are likeliest to have no clean
mechanical reading; if so they get demoted to `AGENT`.

**7. Re-run the perception eval against real briefings once `llm-brief.lua`
exists.** Today's 99.1% is on generous hand-authored fixtures.

### Operational facts, carried forward

**This machine is on the `aa14` tailnet.** The Proxmox host is only reachable
from there: `tailscale` (<tailnet-router-ip>) advertises `<lan-subnet>/24`, and the
`<tailnet-b-account>` tailnet has no such router. Side effect: `gitea`, `secrets`
and the tenant hosts are unreachable from here until it switches back
(`tailscale switch 1052`).

**`next_vmid()` is the only safe source of a vmid.** VM 102 exists on this host
outside the `df-overseer` pool, so our token cannot see it and `pool_members()`
does not list it. The pool view is not the host view.

**The host cannot fit a 4096 MB VM alongside 104.** It sits at ~3.9 GiB
available with 104 up. `start` enforces this and refuses under 1 GiB headroom;
`set-memory` is the way down, and it refuses on a running VM.

**DHCP pool is `.100`-`.199`.** `DF_BUILD_IP=<build-ip>/24` sits just
outside it and is held only during a template build.

### Housekeeping, carried forward

- **Six test worlds (`region1`-`region6`) are sitting in the save directory**
  from this session's gen runs. Harmless at ~900 KB each; delete when they stop
  being useful.
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
- 2026-08-27 (night): the provisioning-hardening handover, superseded by the
  handover above, moved to the same archive file.
