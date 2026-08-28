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

**1. Script the DF install.** Now first, because it is the precondition for
the hardware work: it turns 104 from a thing that must be protected into a
thing that can be rebuilt in twenty minutes. Repo work, so the tailnet does
not block it. Source material is `infra/local.df-vm-install.md`; the traps to
encode are the XDG save path, the silent `-gen` failure, and the package list.

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
