# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-08-28, work paused here

**State at a glance.** The game side is real: DF Classic and DFHack run
headless on VM 104 and answer RPC. The repo is **pushed and public-safe** for
the first time, after a history rewrite that removed host identifiers from
every commit. Work has moved from "get DF running" to a hardware and
clustering project that reshapes what happens next, and one question is
blocking it.

### What changed since the last handover

**The repo went public without leaking the house.** `origin` is GitHub
(`QuickWaller/df-overseer`), not gitea, which had been assumed. A pre-push
scan found host identifiers in the 19 unpushed commits *and* already published
in `memory/proxmox-access.md`: the Proxmox IP, both subnets, the tailnet
router address, and the hostname. User's call was to rewrite and force-push.

- `memory/proxmox-access.md` and `memory/df-vm-install.md` are now
  `infra/local.*`, **gitignored**. A fresh clone does not have them.
  `memory/MEMORY.md` has a "local only" section saying so.
- Committed files use placeholders: `<pve-host>`, `<df-vm-ip>`,
  `<lan-subnet>`, `<tailnet-a>`, `<reserved-mac>`.
- History was rewritten with `git filter-repo` (two passes) and force-pushed.
  `origin/main` is `a820cf8`, 38 commits, in sync with local.
- A pre-rewrite backup bundle was verified and left in the session scratchpad.
  It is **outside the repo and will not survive a machine cleanup**; if the
  rewrite ever needs undoing, that bundle is the only copy.

**Method note worth keeping.** The first "history is clean" check was wrong:
it scanned 1 blob instead of 132 because `rev-list --objects` output was piped
into `cat-file` in a form it could not parse, so it silently passed. A
positive control caught it, and the real scan then found two addresses in
historical `DECISIONS.md` blobs that the first replacement list had missed.
**Any leak scan needs a positive control**, or a scan that sees nothing is
indistinguishable from a repo with nothing in it.

**`provision_vm.py` no longer hardcodes a DHCP reservation.** MACs come from
`DF_MAC_OVERRIDES` in `.env`, parsed to `{vmid: mac}`. Derived MACs are
unchanged (vmid 101 still yields `BC:24:11:00:00:65`).

**`docs/PURPOSE.md` was reconciled against the VM**, not just appended to. It
had claimed nothing was tested against a running game, and that the worldgen
spike was the real memory peak. Both were false and are now corrected, with
build item 0 added for the install and item 1 marked done.

### The hardware and clustering project

**The Omen has been stripped.** Harvested: **2 x 8 GB DDR4-2400** (the plan
assumed 2 x 16), a WiFi card, the panel, a **2 TB 2.5" HDD**, and an SSD of
unverified size. `infra/local.hardware-plan.md` has the destinations.

**The user wants a cluster, explicitly not for HA**, but for the three things
clustering gives you anyway: one UI and API across both boxes, **migration**,
and replicated `/etc/pve` config. Migration is the near-term motivation, since
it is what lets a box be opened without downtime.

**Order of operations, agreed:**

1. Safety net first: repo pushed (**done**), script the DF install (**not
   done**), dump 104 off-host.
2. `dmidecode -t memory` on the ProDesk. Decides add vs replace, and whether
   the spare 8 GB stick has a home at all.
3. **Decide reinstall vs rebuild.** Blocking, see below.
4. `cpu: host` -> `x86-64-v2-AES` in `provision_vm.py`.
5. EliteDesk arrives, set up standalone: second stick, WiFi card, 2 TB in the
   free bay as the backup target.
6. Create the cluster **on the ProDesk**, then join the empty EliteDesk.
7. Qdevice last: HA into a VM, reflash the Pi, `corosync-qnetd`.

### Blocking question, for the user

**Full Proxmox reinstall on the ProDesk, or rebuild the `df-overseer` pool and
VMs on the existing install?** Step 3 gates step 6, because a reinstall must
happen before a cluster exists. Nothing in the hardware sequence can be
scheduled until this is answered.

### Things a next session will otherwise get wrong

**The machine is on the `<tailnet-b>` tailnet, so the Proxmox host and VM 104
are unreachable.** Run `tailscale switch <tailnet-a>` first; the real ids are
in `infra/local.proxmox-access.md`. Switching back gives `gitea`, `secrets`
and the tenant hosts. It is a real either/or, only one at a time.

**VM 104 has not been verified since that switch.** Last confirmed healthy on
2026-08-27 night: Xvfb and `dwarfort` up, RPC answering, swap untouched.
Nothing touched it after, so it should be as described. Confirm, do not
assume.

**`DF_MAC_OVERRIDES` in `.env` is load-bearing.** Without it a rebuilt VM 104
gets a *derived* MAC and drops off its DHCP reservation, which is the exact
failure that cost a session earlier this week. It is gitignored, so it does
not travel with the repo.

**Cluster join order is destructive.** The joining node must have no guests;
joining wipes its guest config. Create on the ProDesk, join the empty
EliteDesk. The reverse loses `df-fortress`.

**A two-node cluster is worse than two standalone hosts** until the qdevice
lands. One node down leaves the survivor unable to start, stop or edit
anything. Running VMs keep running.

**A reset destroys VMs we cannot see.** VM 102 exists on the host outside the
`df-overseer` pool; our token gets `403` on it and `pool_members()` does not
list it. Enumerate as root in the GUI before wiping anything.

**Clusters do not pool RAM.** Two 16 GB nodes are two 16 GB machines with one
login. The DF VM's ceiling is only relieved by sticks in the right slot.

**Saves are not in the game directory.** They are under the XDG data path; see
`infra/local.df-vm-install.md`. A backup script aimed at `<df>/data/save`
copies nothing and reports success.

**`-gen` fails silently about a quarter of the time**, generating the full
history and then writing no export, with nothing in any log. Detect by the
absence of the region directory, never by exit code.

### What a next session should pick up

**1. Script the DF install. Written, not yet run against the VM.** See the
section below.

**2. `cpu: host` -> `x86-64-v2-AES`.** Migration is now a stated goal and that
flag blocks it between a Kaby Lake i7-7700T and a Coffee Lake i5-8500T. Cold
stop/start on 104 to take effect. For DF the loss is nil, it is
single-threaded and not AVX-heavy.

**3. Systemd units for Xvfb and DF**, plus a save-backup job at the XDG path.
Blocked on the tailnet switch. Nothing currently survives a reboot: both are
running under `setsid nohup`.

**4. `check_reachable` / `get_connectivity_report`** (`docs/PURPOSE.md` build
item 2). Copies `warn-stranded.lua`'s algorithm, and there is a real DFHack to
run it against now.

**5. Embark, and measure a running fort's memory.** 4096 MB is still unproven
for a live fort; worldgen answered a different question. Embark also needs UI
driving, which `-gen` avoided, so finding out how much is scriptable matters.

**6. The compliance eval harness.** Research build item 1, "do first, before
any fort runs". No game, no agent, never blocked. Retires the standing caveat
that the N=80 doctrine threshold is a single unreplicated study.

**7. Mechanical prediction grading** (research build item 3): compare a
prediction's `signal` against recorded state at `check_at`. No calibration
metric means anything until it exists.

**8. The ledger's write path waits on the perception layer.** `defense_depth`,
`primary_industry` and `surface_footprint` are likeliest to have no clean
mechanical reading; if so they become `AGENT` fields.

**9. Re-run the perception eval against real briefings once `llm-brief.lua`
exists.** Today's 99.1% is on generous hand-authored fixtures.

### Housekeeping, carried forward

- **The published hostname should be treated as exposed.** The rewrite removed
  it from the repo, it did not un-publish it: GitHub can serve unreferenced
  commits by SHA for a while and any existing clone or fork still has it. The
  user chose not to rename the host. Not secret, just no longer advertised.
- **`willsmith.nz` was deliberately left in** (30 occurrences). It is the
  project's intended public face per `docs/PURPOSE.md`, not a leak.
- **The ProDesk's RAM slot layout is still unknown**, and it decides whether
  the spare 8 GB stick is useful or scrap.
- **The SSD out of the Omen has an unverified size.** Only worth putting in a
  node if it beats the EliteDesk's 239 GB NVMe.
- **Six test worlds (`region1`-`region6`)** are sitting in VM 104's save
  directory. ~900 KB each, delete when done with them.
- **Proxmox token not rotated**, pasted into an earlier transcript.
- **Temporary Anthropic key in `.env` expires ~2026-09-03.** Rotate or remove;
  do not commit or log it.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent` still deferred.**
- **DF replay determinism unverified**, and research build item 7 rests on it.
- **`hypothesis_id` has no registry.** A typo silently orphans evidence.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

## DF install scripting - 2026-08-28

`scripts/install_df.py` exists. It turns `infra/local.df-vm-install.md` from
prose into something re-runnable, which is what the hardware sequence was
waiting on: 104 stops being a thing to protect and becomes a thing to rebuild.

**What it does.** `install` (packages, 4 GB swapfile, DF + DFHack tarballs,
`prefs/init.txt`), `verify`, `start`, `stop`, `gen`, `saves`, `backup`. Every
command is idempotent and takes `--vmid`, defaulting to `DF_VMID`. It drives
the guest over SSH from this workstation, reusing `provision_vm.py`'s
`ssh_guest` and `.env` discipline.

**The three traps are encoded as checks, not comments.**

- The XDG save path is resolved from `getent passwd`, so it is right under
  sudo too. `verify` fails if `<game>/data/save` exists, because its presence
  means something has recreated the pre-v50 layout that makes a backup script
  silently copy nothing.
- `gen` decides success by the region directory existing, never by exit code,
  and retries with a fresh seed. It names `save/current` explicitly when it
  finds the orphan, since "generated but never renamed" and "generated
  nothing" are different problems. Exit 134 aborts rather than retrying: that
  one is the documented "world id exists".
- `init.txt` settings are applied and then read back, because `sed` exits 0
  when it matches nothing, so a key renamed between DF versions would
  otherwise be skipped in silence.

**What was verified offline first.** With the VM still unreachable,
`--dry-run` prints each remote script instead of running it, and that is what
got tested before any of it touched a machine:

- All 15 distinct remote scripts pass `bash -n`. The first run of that check
  reported all 15 as failures, which turned out to be WSL's bash failing to
  spawn at all, not a syntax error anywhere. A positive control (a deliberately
  unterminated `if`) then confirmed the check can detect a real error.
- `prefs/init.txt` was run for real against a realistic `init_default.txt`:
  all five settings land, unrelated keys are untouched, and a negative case
  with `PRINT_MODE` deleted confirms the readback fails rather than passing.
- The archive layout detection was run against both a flat and a
  directory-wrapped tarball. `dwarfort` lands at the game root either way. The
  install doc says both archives are flat; the script detects rather than
  assumes, so a future release that wraps them does not bury the game a level
  down.
- The base64 transport was round-tripped with quotes, `$`, brackets and a
  space-bearing path.

**Then it was run against VM 104, and that is what found the real bugs.**
Tailnet switched to `<tailnet-a>` on 2026-08-28. Every command has now been
exercised against the live VM. `verify` is all-PASS including the runtime
checks, `backup` pulled 4.1 MB / 181 entries off the box, `gen` reproduced the
silent worldgen failure and recovered from it, and a full stop/start cycle
works. `install` was then run against the already-installed VM and proved
idempotent end to end: packages no-op, swapfile already active, extract
correctly skipped with "pass --force to replace", init.txt re-applied and read
back. It did re-download both tarballs, because the hand-install kept them
under their upstream names and the script caches them as `df.tar.bz2` and
`dfhack.tar.bz2`; sha256 values for both are now recorded in
`infra/local.df-vm-install.md`.

**Four bugs, none of which offline testing could have found.**

1. **`--vmid` only worked before the subcommand.** argparse puts a top-level
   option there, which contradicted the script's own usage text. Now attached
   to the top level and every subparser, with `SUPPRESS` defaults so the
   subparser's unset value cannot overwrite the one already given.
2. **`dfhack-run` wraps its output in ANSI colour even with stdout not a tty,
   and ends with a bare reset on its own line.** `tail -n1` therefore returned
   `[0m`, so `verify` was comparing an escape sequence against the version
   string and would have called a correct install wrong. Fixed with a shared
   `dfhack_lua()` helper that strips escapes and drops blank lines.
3. **The `start` readiness loop could not fail.** It broke as soon as
   `dfhack_lua` returned anything non-empty, and when the game is not up yet
   `dfhack-run` prints `Could not connect to localhost:5000`, which is
   non-empty. So the loop exited on its first pass and the socket check ran
   against a game under a second old. That is what made a healthy start report
   a 240s timeout. Readiness is now two conditions: the socket is listening,
   and the answer is neither empty nor the connect error. Positive control with
   the game stopped: the loop now runs its full deadline instead of exiting at
   0s.
4. **`gen`'s orphan check was presence-based.** It reported "save/current
   exists, this is the silent -gen failure" whenever `current` was there at
   all, and a stale one from 2026-08-27 was. It now samples the mtime before
   the run and only blames this attempt if it moved. All three branches
   (stale / written-now / absent) tested directly.

**New verified facts about the VM, for `infra/local.df-vm-install.md`.**

- **DF ignores SIGTERM.** Every `stop` waits the full 30s and ends in SIGKILL.
  There is no graceful shutdown, which makes `--save` mandatory rather than
  optional once a fort is live, and means the systemd unit cannot rely on a
  normal stop: it needs a save step and a long `TimeoutStopSec`, or every
  reboot kills the fort.
- **Launch to listening RPC socket is about 3 to 10 seconds**, measured in a
  single session rather than inferred across SSH calls.
- **The silent `-gen` failure is real and reproduced:** one of two attempts on
  world 7 exited 1 with no region directory. The retry with a fresh seed
  succeeded. World 8 succeeded first try.

**The host rebooted and nothing came back.** The host booted at approximately
2026-08-27 23:32, and VM 104 was found **stopped**, not running as the previous
handover assumed. `onboot` is not set on 104, so the problem is larger than the
handover recorded: it is not only that Xvfb and DF do not survive a reboot, the
**VM itself does not**. Whatever the systemd work concludes, `onboot` on 104 is
a separate one-line fix and has not been made, because it changes VM config
rather than repo state.

**Leftovers from this session, for cleanup.** `region7` and `region8` are mine,
from testing `gen`; that makes eight test worlds plus a 4 KB stale
`save/current`. `backups/df-saves-104-*.tar.gz` is the first off-host dump of
104's saves, which also ticks the handover's "dump 104 off-host" safety-net
item. `cpu: host` is still set on 104, so handover item 2 is still open.

**Also landed:** `DF_VM_IP` and `DF_CIUSER` added to
`infra/local.example.env`; `backups/` gitignored.

**Docs reconciled against reality, 2026-08-28.** `docs/PURPOSE.md` (status
header, the Xvfb section now carrying the three process-lifecycle facts, the
worldgen and save sections, and build item 0), `CLAUDE.md`'s status blurb,
`infra/README.md` (including the `.env` correction below and a new Scripts
table), and `memory/MEMORY.md`'s local-only list, which was missing
`local.hardware-plan.md` entirely. The verified facts themselves live in
`infra/local.df-vm-install.md`, which is the authoritative record; the public
docs point at it rather than restating the host specifics.

Everything that would be published was then leak-scanned against identifiers
harvested from the gitignored records, with a positive control proving the scan
could see (20 hits on a known string). Zero real identifiers. One shape-sweep
hit, `tail1234.ts.net` in `local.example.env`, checked and cleared: neither
`prodesk` nor `tail1234` appears anywhere in the real records, and the actual
`PVE_HOST` is not a `.ts.net` name at all. That file is newly public, so it was
worth confirming rather than assuming.

**Not archived yet despite reading as finished:** this section is still gated on
the user for the `onboot` change, deleting the eight test worlds, and the
commit. Per the archive-cadence rule that is "gated on a human", so it stays.

**Two doc/repo mismatches found on the way, one fixed.**

- **Fixed:** `infra/local.example.env` was never tracked. `CLAUDE.md` says the
  `local.example.*` counterparts are committed, but the `infra/local.*` ignore
  rule swallowed them, so a fresh clone got no template at all. Added
  `!infra/local.example.*`. Checked in both directions: git now offers the
  example file, and `local.proxmox-access.md`, `local.df-vm-install.md`,
  `local.hardware-plan.md` and `local.env` all still match the ignore rule.
  Every non-empty value in the example is a safe default (`PVE_PORT=8006`,
  `PVE_TOKEN_ID=df-overseer@pve!api`, `PVE_POOL=df-overseer`, `DF_CIUSER=df`,
  `PVE_TLS_VERIFY=false`), nothing host-specific.
- **Fixed:** `infra/README.md` told you to copy `local.example.env` to
  `local.env`, which no code has ever read: `pve.py`'s `load_env()` reads the
  repo-root `.env`. Resolved in favour of documenting what the scripts actually
  do, since a doc's job is to describe reality and moving the code would have
  been a behaviour change smuggled in under "update docs". If the layout should
  change instead, that is a separate call.

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
- 2026-08-28: the 2026-08-27 night handover (DF installed on VM 104), superseded by
  the handover above, moved to the same archive file.
