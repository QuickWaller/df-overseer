# Proxmox setup

**How to build the access layer from nothing.** For what currently *exists* —
the live role, scopes, verified boundaries and VM specs — see
`infra/local.proxmox-access.md`, which is read back from the API rather than assumed.

Target: **Proxmox VE 9.1.1**, node `proxmox`, storage `ssd_storage`.

## Design

- A **dedicated narrow user**, not a shared one.
- **Privilege separation OFF.** Privsep only earns its doubled ACL work when the
  *user* is broad and the *token* should be narrower. Here the user is itself
  narrow, so privsep buys nothing and doubles the setup.
- **Everything scoped to one resource pool.** Access resolves through pool
  *membership* — adding or removing a VM from `df-overseer` is what grants or
  revokes control over it. There are no per-VM grants.
- **`VM.Allocate` granted**, pool-scoped: create and destroy apply only inside
  the pool. Other VMs are unaffected by construction, verified by denial.

### PVE 9 note

`VM.Monitor` **was removed in Proxmox VE 9** and will not appear in the role
editor. Its functions moved to `Sys.Audit`, `Sys.Modify`, and the new
`VM.GuestAgent`. Privilege lists written against PVE 8 — including several
Terraform providers — are wrong on this.

## UI walkthrough

All under **Datacenter → Permissions**.

**1. Pools → Create** — name `df-overseer`

**2. Roles → Create** — name `DFOverseer`, tick all 24:

| Privilege | For |
|---|---|
| `VM.Allocate` | Create and destroy VMs *in the pool* |
| `VM.Audit` | Read config and status |
| `VM.Config.CPU` `.Memory` `.Disk` `.Network` `.Options` | Configure |
| `VM.Config.CDROM` | Mount install media |
| `VM.Config.HWType` | Controller types at creation |
| `VM.Console` | Console / VNC — needed for the display work |
| `VM.PowerMgmt` | Start, stop, reboot |
| `VM.Snapshot` | Save rotation |
| `VM.Snapshot.Rollback` | Roll back after a bad decision |
| `VM.Clone` | Clone *our own* template — confirmed missing by test; it does not reach templates outside the pool |
| `Sys.AccessNetwork` | Present in this role but **inert at this binding** — `Sys.*` is only checked at `/nodes/<node>` or `/`, never against a pool or storage path. Left here rather than removed; the working grant is `DFOverseerNode` below (step 7) |
| `VM.GuestAgent.Audit` `.FileRead` `.FileWrite` `.FileSystemMgmt` | Guest-agent introspection and file operations inside pool VMs |
| `Datastore.AllocateSpace` | Disks and snapshots need space |
| `Datastore.AllocateTemplate` | Convert a built VM into a template |
| `Datastore.Audit` | See what storage exists |
| `Pool.Audit` | **Read the pool's own membership** — without it the overseer cannot discover which VM is its own |

**`VM.GuestAgent.Unrestricted`** — tick this too, but treat it as a large
capability, not a small one alongside the others above: it permits **arbitrary
command execution inside pool VMs**, which is how guest provisioning happens
without SSH or guest networking. Granted knowingly on 2026-08-26; see the
decision register for the reasoning.

Do **not** tick `VM.Migrate`, `Sys.Modify`, `Sys.Console`, `Pool.Allocate`
(that is pool *creation*), or anything under `Realm.*`, `User.*`,
`Permissions.*`.

**3. Users → Add** — user `df-overseer`, realm **Proxmox VE authentication server**

**4. API Tokens → Add** — user `df-overseer@pve`, token ID `api`,
**untick Privilege Separation**

> The secret shows **once**. Put it straight into `.env` as
> `PVE_TOKEN_SECRET` — gitignored. Never into chat or a tracked file.

**5. Permissions → Add → User Permission**
Path `/pool/df-overseer` · User `df-overseer@pve` · Role `DFOverseer`

**6. Permissions → Add → User Permission** (storage is not covered by the pool path)
Path `/storage/ssd_storage` · User `df-overseer@pve` · Role `DFOverseer`

**7. Roles → Create** — name `DFOverseerNode`, tick only `Sys.Audit` and
`Sys.AccessNetwork`.

**8. Permissions → Add → User Permission**
Path `/nodes/proxmox` · User `df-overseer@pve` · Role `DFOverseerNode` ·
**Propagate: on**

This second role exists because of a lesson that cost three wrong diagnoses:
**`Sys.*` privileges are only checked at `/nodes/<node>` or `/`, never against
a pool or storage path.** Putting `Sys.AccessNetwork` in `DFOverseer` (bound
only at `/pool` and `/storage`) does nothing — the privilege exists but is
attached nowhere the node-level check looks. It has to be a separate role
bound at the node path. Full account, including the wrong hypotheses tried
first, is in `infra/local.proxmox-access.md`.

## Storage: enable the `import` content type

One-time human step, gated on `Datastore.Allocate` at `/storage` — a
privilege this token deliberately does not have (storage definitions are
datacenter configuration, and granting it would let the token edit and delete
storage entirely for the sake of one flag).

`import-from` (the API equivalent of `qm importdisk`) refuses a volume whose
content type is `iso` — it needs `images` or `import`. That matters because
the cloud image the template is built from arrives as a download, and
`download-url` only writes into a content type the storage is configured for.

**UI:** Datacenter → Storage → `ssd_storage` → Edit → Content → add
**"Import"** (leave existing `images`/`iso` content ticked too).

**CLI:**

```bash
pvesm set ssd_storage --content images,iso,import
```

Nothing else about the storage changes. After this, `scripts/provision_vm.py
fetch-image` downloads the cloud image into `import/` and the rest of the
build is scriptable with no host shell access.

## SSH key for the DF VM

Generate a **dedicated** keypair — do not reuse a key from another project:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/df_overseer_ed25519 -N "" -C "df-overseer"
```

- **Dedicated, not shared.** Revocation is indivisible with a shared key —
  rotating it for this project would also lock out whatever else uses it.
- **No passphrase.** Deliberate: the provisioning and overseer loops are meant
  to run unattended for weeks, and a passphrase would require a live human or
  agent present for the whole run.
- **Windows caveat:** `chmod 600` is a no-op on NTFS — the file still reports
  `0644` and nothing is actually restricted. What works is:

  ```powershell
  icacls <path> /inheritance:r /grant:r "$(whoami):R"
  ```

- **`.env` holds paths only** — `DF_SSH_KEY` and `DF_SSH_PUBKEY` — never key
  material. The key itself lives under `~/.ssh` and is never committed.

The fingerprint and full record of this key are in `infra/local.proxmox-access.md`
— not reproduced here.

## Verify — including the denial

```bash
set -a; . ./.env; set +a
AUTH="Authorization: PVEAPIToken=$PVE_TOKEN_ID=$PVE_TOKEN_SECRET"
B="https://$PVE_HOST:$PVE_PORT/api2/json"

curl -sk -H "$AUTH" "$B/version"                    # should succeed
curl -sk -H "$AUTH" "$B/pools/$PVE_POOL"            # should list members
curl -sk -H "$AUTH" "$B/cluster/resources?type=vm"  # should show ONLY pool VMs
curl -sk -H "$AUTH" "$B/nodes/proxmox/qemu/<VMID_OUTSIDE_POOL>/config"  # must FAIL
```

**A permission scheme is only verified once you have watched it deny
something.** A green result from a check that never exercised the boundary is
not evidence of anything. Recorded denials are in `infra/local.proxmox-access.md`.

## CLI equivalents

```bash
pveum pool add df-overseer --comment "df-overseer managed VMs"

pveum role add DFOverseer --privs "VM.Allocate,VM.Audit,VM.Console,VM.Config.CPU,VM.Config.Memory,VM.Config.Disk,VM.Config.Network,VM.Config.Options,VM.Config.CDROM,VM.Config.HWType,VM.PowerMgmt,VM.Snapshot,VM.Snapshot.Rollback,VM.Clone,Sys.AccessNetwork,VM.GuestAgent.Audit,VM.GuestAgent.FileRead,VM.GuestAgent.FileWrite,VM.GuestAgent.FileSystemMgmt,VM.GuestAgent.Unrestricted,Datastore.AllocateSpace,Datastore.AllocateTemplate,Datastore.Audit,Pool.Audit"

pveum role add DFOverseerNode --privs "Sys.Audit,Sys.AccessNetwork"

pveum user add df-overseer@pve --comment "Automation user for df-overseer"
pveum user token add df-overseer@pve api --privsep 0

pveum acl modify /pool/df-overseer      --user df-overseer@pve --role DFOverseer
pveum acl modify /storage/ssd_storage   --user df-overseer@pve --role DFOverseer
pveum acl modify /nodes/proxmox         --user df-overseer@pve --role DFOverseerNode --propagate 1

pvesm set ssd_storage --content images,iso,import
```

## Rotating the token

Datacenter → Permissions → API Tokens → `api` → Remove, then Add again. Update
`PVE_TOKEN_SECRET` in `.env`. Role, ACLs and pool are untouched.

## Once the access layer exists

`scripts/provision_vm.py` (`status` / `fetch-image` / `build-template` /
`clone`) builds the VM from here: downloads the cloud image, builds a
from-scratch template (not a clone of someone else's), and clones it into the
running VM. It is Python rather than bash because Git Bash's MSYS layer
rewrites POSIX-looking arguments into Windows paths — `/var/lib/vz/...` became
a Windows path mid-flag on the command line, which silently corrupts any
storage path or `import-from` value.
