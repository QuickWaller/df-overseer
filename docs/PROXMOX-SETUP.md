# Proxmox setup

**How to build the access layer from nothing.** For what currently *exists* —
the live role, scopes, verified boundaries and VM specs — see
`memory/proxmox-access.md`, which is read back from the API rather than assumed.

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

**2. Roles → Create** — name `DFOverseer`, tick all 16:

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
| `Datastore.AllocateSpace` | Disks and snapshots need space |
| `Datastore.Audit` | See what storage exists |
| `Pool.Audit` | **Read the pool's own membership** — without it the overseer cannot discover which VM is its own |

Do **not** tick `Sys.Modify`, `Sys.Console`, `Pool.Allocate` (that is pool
*creation*), `VM.Clone`, `VM.Migrate`, `VM.GuestAgent`, or anything under
`Realm.*`, `User.*`, `Permissions.*`.

**3. Users → Add** — user `df-overseer`, realm **Proxmox VE authentication server**

**4. API Tokens → Add** — user `df-overseer@pve`, token ID `api`,
**untick Privilege Separation**

> The secret shows **once**. Put it straight into `.env` as
> `PVE_TOKEN_SECRET` — gitignored. Never into chat or a tracked file.

**5. Permissions → Add → User Permission**
Path `/pool/df-overseer` · User `df-overseer@pve` · Role `DFOverseer`

**6. Permissions → Add → User Permission** (storage is not covered by the pool path)
Path `/storage/ssd_storage` · User `df-overseer@pve` · Role `DFOverseer`

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
not evidence of anything. Recorded denials are in `memory/proxmox-access.md`.

## CLI equivalents

```bash
pveum pool add df-overseer --comment "df-overseer managed VMs"

pveum role add DFOverseer --privs "VM.Allocate,VM.Audit,VM.Console,VM.Config.CPU,VM.Config.Memory,VM.Config.Disk,VM.Config.Network,VM.Config.Options,VM.Config.CDROM,VM.Config.HWType,VM.PowerMgmt,VM.Snapshot,VM.Snapshot.Rollback,Datastore.AllocateSpace,Datastore.Audit,Pool.Audit"

pveum user add df-overseer@pve --comment "Automation user for df-overseer"
pveum user token add df-overseer@pve api --privsep 0

pveum acl modify /pool/df-overseer      --user df-overseer@pve --role DFOverseer
pveum acl modify /storage/ssd_storage   --user df-overseer@pve --role DFOverseer
```

## Rotating the token

Datacenter → Permissions → API Tokens → `api` → Remove, then Add again. Update
`PVE_TOKEN_SECRET` in `.env`. Role, ACLs and pool are untouched.
