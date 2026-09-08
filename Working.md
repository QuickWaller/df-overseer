# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-09-08

**State at a glance.** Nothing from this project runs anywhere right now.
VM 104 (`df-fortress`) and template 101 were both deleted 2026-09-01, not
migrated, while this repo sat quiet since 2026-08-30. The Proxmox host was
reinstalled 2026-09-02 and renamed `SRV-01`; a two-node cluster `citadel`
formed 2026-09-01 and `SRV-01` rejoined it cleanly 2026-09-06. This project
got its own dedicated pool-scoped storage on 2026-09-08. The next action is a
**rebuild from this repo's own scripts** (`fetch-image` -> `build-template` ->
`clone`), not a restore of anything, and it is genuinely cheap: both pieces
were always meant to be reconstitutible this way, confirmed by reading the
code rather than assumed. Full analysis behind this handover:
`infra/local.2026-09-08-doc-reorg-plan.md` (gitignored: it quotes home-lab's
own infra specifics, so it lives under `infra/local.*` rather than `docs/`; a
clone of this public repo will not have it).

**Commit state.** Six local commits this session, ending at `cb9560d`.
Working tree is clean. **Not pushed**, that needs its own go-ahead per the
Rules section. The last two are the provisioning work: `4e0f8da` mounts a
`urllib3` retry policy on the API client and names the inquorate trap at the
error, and `cb9560d` deletes the template bake and switches the VM to a
static address assigned at clone time, taking `provision_vm.py` from 724
lines to 533.

**The blocking human step is discharged.** `PVE_TOKEN_SECRET` is in `.env`
and the new pool-scoped identity is **proven from this workstation**:
`provision_vm.py status` returned 12.5 GiB available, next free vmid 102, and
an empty pool. That last point is worth keeping: the pool being empty
independently confirms the 2026-09-01 deletion rather than a token that cannot
see its own VMs. The call also exercised this session's auth-header fix
against the live API, since an unauthenticated client gets `401` rather than
data.

**Spike A is done and it passed clean, first attempt, 2026-09-08.**
`fetch-image` downloaded the pinned image and PVE accepted the checksum;
`build-template` created VM 102, imported the disk, resized to 25G on attempt
1 of 4, and converted to a template **without ever booting it**, which is the
bake deletion working end to end. `DF_TEMPLATE_VMID=102` is recorded in
`.env`.

Four things that were unverified are now verified by that run: the
`checksum`/`checksum-algorithm` spelling on `download-url`, which was the
single least-confident claim in the provisioning research; the new storage
having the `import` content type; the pool-scoped token driving the whole
image-to-template flow; and the auth-header fix under real load.

**Phase H is done: the old identity is retired, 2026-09-08.** The exposed
`df-overseer@pve` token, live since 2026-08-24, no longer exists. Removed at a
root shell on a confirmed-quorate node: token `api`, the user, and both
`DFOverseer`/`DFOverseerNode` roles. Deleting the user took its three ACLs with
it, including a `/sdn/zones/localnetwork` grant that was **not** in this repo's
record and only surfaced because the retirement was checked before it was run,
and a `/nodes/proxmox` binding that had pointed at a node name that stopped
existing on 2026-09-02. Nothing was lost: the new identity already holds
`PVESDNUser` on that same zone. Verified both directions, that the old user,
ACLs and roles are gone **and** that `svc-df-overseer-sandbox@pve` still
exists, then re-ran `provision_vm.py status` to confirm this repo still
authenticates. **Still owed, in home-lab not here:** its
`secrets/registry.md` row goes to `retired` with the date.

**`clone` is done, 2026-09-08: VM 103 `df-colony-01` is up at
`192.168.2.201`.** User supplied `DF_VM_IP=192.168.2.201/24`. `clone --name
df-fortress.internal --full` built VM 103 from template 102 as a full clone
(matching the 2026-08-24 precedent for VM 104), `start --vmid 103` brought it
up, and `install_df.py verify --vmid 103` reached it over SSH with no address
discovery, confirming the static-assignment design works end to end on a real
build. Its FAIL lines are the expected shape for a bare clone (no DF/DFHack,
`init.txt` unset, no swap, no systemd units) — see
`decisions/DECISIONS.md` 2026-09-08 row. `DF_VMID=103` is recorded in `.env`.

**Renamed to `df-colony-01` same day: `.internal` is DNS-only, never part of
a name or hostname.** User caught two problems with `df-fortress.internal`:
"df" already means Dwarf Fortress, and unlike `subnet-router-02`, the literal
string `.internal` was showing up in the Proxmox name field. The guest's own
hostname was already the short form (`df-fortress`, cloud-init dropped the
FQDN suffix at first boot), so the bug was cosmetic to Proxmox's name field
only. Fixed on both sides and verified by reading back: Proxmox
`config.name` and the guest's `hostname`/`/etc/hosts` both now read
`df-colony-01`. The 2026-09-08 DECISIONS.md row claiming the OS hostname
should carry `.internal` is superseded, it misread the home-lab convention.
`scripts/` keys everything off `DF_VMID`/`DF_VM_IP`, never the VM name, so
nothing else needed to change.

**Next is `install_df.py install --vmid 103`**, then reapplying
`init.txt`, swap, and the `df-xvfb.service`/`df-fortress.service` units with
`onboot=1` — none of it carries over from the deleted VM 104, per the
"re-scope, don't assume" trap below.

**Provisioning work completed 2026-09-08, steps 1 and 2 of the migration path
in `research/2026-09-08-provisioning-recommendation.md` §11.** Both were
unconditional and independent of the still-open build-tool decision, so most
of the practical benefit is now banked whatever happens to that. Layer 1: the
API client mounts a `urllib3` retry policy, POST deliberately excluded so a
timeout can never create two VMs, and 403/500 now say the cluster may be
inquorate. Layer 0: the template bake is deleted, `qemu-guest-agent` moved
into the guest install, and the VM's address is assigned at clone time rather
than discovered, which retired the derived MACs, the override table and the
router's reservation as a source of truth. `provision_vm.py` went 724 to 533
lines. The base image is pinned by dated serial and sha256, verified
host-side by PVE. Automatic upgrades are disabled on the guest.

**What is still open on provisioning:** whether to move image, template and
clone to OpenTofu with `bpg/proxmox`. Deliberately left at `proposed` in the
register, because the one thing nobody has tested is whether a pool-scoped
token can drive it end to end, and that is what spike B settles. Do not treat
it as decided. → `research/2026-09-08-provisioning-recommendation.md` §7.4.

**Two provisioning claims are believed but untested**, and both have a written
falsifying test. An unbaked template needs no seal (clone twice, compare SSH
host key fingerprints and `machine-id`; if they match, the bake comes back).
And `bpg`'s VMID allocation may use a workstation-local sequence file rather
than `/cluster/nextid`, which would reintroduce the second-source-of-truth
problem the 2026-08-27 `next_vmid()` decision exists to prevent.

**A live bug found and fixed this session, worth internalising the shape
of.** The same-day refactor that made `PVE_POOL`/`PVE_STORAGE` required (see
`decisions/DECISIONS.md` 2026-09-08) briefly left `scripts/pve.py`'s new
`_require()` call sitting where it broke `__init__`'s control flow, which
would have left `self.session` built with no `Authorization` header at all.
Every API call would have gone out unauthenticated and come back `401` on the
very first use of the brand-new token, reading as "the new identity doesn't
work" and sending the next session hunting in the identity/ACL layer instead
of the client code. Fixed and verified with a positive control: the check
fails against the broken code and passes against the fixed code. `pve.py`'s
current state is correct, `_require()` is a normal method and the
`Authorization` header is set unconditionally at the end of `__init__`.

**Quorum can masquerade as a permissions failure.** `citadel` has no QDevice
and the second node is resetting roughly every 2.5 hours. A single node can
drop below quorum on its own, and every config write then fails with an error
that reads exactly like an ACL problem. Run `pvecm status` before suspecting
permissions on any write that fails oddly during the rebuild.

**`.env` credential hygiene, mostly resolved 2026-09-08.** `PVE_PASSWORD` is
**deleted**: no script read it, and the credential it named was rotated out
from under it by the 2026-09-02 OS reinstall, so it was dead twice over. The
live value lives in home-lab's own store, not here. No backup file was written
when removing it, deliberately, since a `.env` sidecar is what caused this
session's near-miss. `PVE_USER` and `PVE_FQDN` were read by no code either
and are now **also deleted**, so `.env` was down to 15 keys, all of them live.
Two more went the same way later the same day: `DF_BUILD_IP` and
`DF_MAC_OVERRIDES` were leftover from decisions that already retired the code
reading them, see `decisions/DECISIONS.md` 2026-09-08 row. `.env` is now 13
keys. `ANTHROPIC_API_KEY` is still expired;
the user is minting a replacement. Do not commit or log either.

**Assume the value that grep printed is exposed.** Deleting `PVE_PASSWORD`
required reading `.env`, which put the old password into a session transcript.
It was already superseded by the reinstall so the blast radius is nil, but the
standing convention in this repo is to treat a credential that reaches a
transcript as exposed rather than to reason about whether it mattered.

**Re-scope, don't assume, on `df-xvfb.service`/`df-fortress.service` and
`onboot=1`.** Both were live VM config on the deleted VM 104, not baked into
template 101. They need to be reapplied in full to whatever VMID the rebuild
produces; nothing carries over automatically.

**`infra/local.proxmox-access.md` is stale and nothing else says so.** It is
gitignored, so not a leak, but it is this repo's only "access layer verified"
record and it describes the retired identity (`df-overseer@pve`, roles
`DFOverseer`/`DFOverseerNode`, token `api`), read back from the API on
2026-08-27. The new identity's own proof, the `200`-in-pool/`403`-outside
pool-fence test, lives in home-lab, not here: this repo currently has no
equivalent record of the new identity's live scopes. Worth deciding whether
re-recording that into a fresh version of the file is a Now or a Next item;
not done as part of this pass since the file is gitignored and out of scope
for it.

### Durable traps, still true, not about VM 104 specifically

- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort is
  live; a bare stop takes the full timeout and ends in SIGKILL.
- **The manual (`start`/`stop`) and systemd-managed paths must not run at
  once.** They contend for `:99` and the RPC port.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it** (`cloud-init
  clean`, remove SSH host keys, truncate `machine-id`). The code that enforced
  this went with the bake on 2026-09-08, because a template that is never
  booted has nothing to seal. If anyone reintroduces a boot-before-convert
  step, the seal has to come back with it.
- **The published hostname is exposed.** The user chose not to rename it.
- **`willsmith.nz` is deliberate**, not a leak: the intended public face.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified.**
- **`hypothesis_id` has no registry.**
- **`openclaw` vs `hermes-agent` still deferred.**
- **Tarball checksums are pinned and enforced** as of 2026-09-08;
  `bzip2 -t` catches truncation, the sha256 catches substitution.

### What a next session should pick up

`ROADMAP.md`'s Now bucket is the canonical list. Token pasted, `status`
verified, template and VM rebuilt, VM 103 named `df-colony-01` (not
`.internal`, that's DNS-only, never part of a name or hostname) — all done.
Remaining: `install_df.py install` on VM 103, watch for quorum during
writes, rotate the stale `ANTHROPIC_API_KEY`.

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
- 2026-08-28 (evening): the morning handover (superseded by the one
  above) and the DF-install-scripting section (it reports itself
  finished: the script shipped and was verified against VM 104) moved
  to the same archive file.
- 2026-08-30: the 2026-08-28 (evening) handover, superseded by the handover
  above (systemd units built, tested through a real guest reboot, and
  `onboot` set), moved to the same archive file.
- 2026-09-08: the 2026-08-30 handover moved wholesale to
  [`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md).
  Not superseded content so much as overtaken by events: VM 104 and template
  101 were deleted 2026-09-01 while this repo sat quiet, so the handover
  describing them is now history rather than current state.
