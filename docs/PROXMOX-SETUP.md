# Proxmox access setup

Target: **Proxmox VE 9.x** at `<pve-host>:8006` (`<pve-hostname>`),
reached over tailnet `aa14` via the subnet router advertising `<lan-subnet>/24`.

The UI walkthrough is the primary path; CLI equivalents are at the bottom.

## Design

- A **dedicated narrow user**, not a shared one.
- **Privilege separation OFF.** Privsep only earns its doubled ACL work when the
  *user* has broad rights and you want the *token* narrower. Here the user is
  itself narrow, so privsep buys nothing.
- **Everything scoped to one resource pool.** The token cannot see, touch, or
  enumerate anything outside `df-overseer`.
- **`VM.Allocate` granted** (decision 2026-08-25) — pool-scoped, so create and
  destroy apply only within `df-overseer`. Other VMs on the host are unaffected
  by construction.

### PVE 9 note

`VM.Monitor` **was removed in Proxmox VE 9** — it will not appear in the role
editor. Its functions moved to `Sys.Audit` (basic KVM monitor), `Sys.Modify`
(beyond informational) and the new `VM.GuestAgent`. None are needed here.

## UI walkthrough

All under **Datacenter → Permissions**.

**1. Pools → Create**
Name: `df-overseer`

**2. Roles → Create**
Name: `DFOverseer`. Tick:

| Privilege | For |
|---|---|
| `VM.Allocate` | Create and destroy VMs *in the pool* |
| `VM.Audit` | Read config and status |
| `VM.Config.CPU` / `.Memory` / `.Disk` / `.Network` / `.Options` | Configure |
| `VM.Config.CDROM` | Mount the install ISO |
| `VM.Config.HWType` | Set disk/NIC controller types at creation |
| `VM.Console` | Console / VNC — needed for the display work |
| `VM.PowerMgmt` | Start, stop, reboot |
| `VM.Snapshot` | Save rotation |
| `VM.Snapshot.Rollback` | Roll back after a bad decision |
| `Datastore.AllocateSpace` | Disks and snapshots need space |
| `Datastore.Audit` | See what storage exists |

Do **not** tick `Sys.Modify`, `Realm.*`, `User.*`, `Permissions.*`, or
`Pool.Allocate` (that is pool *creation*, a different thing).

If `VM.Snapshot.Rollback` isn't in the list, drop it — the name has shifted
between releases and we'll find the right one from the error.

**3. Users → Add**
User name: `df-overseer` · Realm: **Proxmox VE authentication server**

**4. API Tokens → Add**
User: `df-overseer@pve` · Token ID: `api` · **untick Privilege Separation**

> The secret is shown **once**. Paste it straight into `infra/local.env` as
> `PVE_TOKEN_SECRET` — that file is gitignored. Not into chat, which is logged.

**5. Permissions → Add → User Permission**
Path: `/pool/df-overseer` · User: `df-overseer@pve` · Role: `DFOverseer`

**6. Storage grant** — pool paths don't cover storage, so add a second entry:
Path: `/storage/<your-storage>` · User: `df-overseer@pve` · Role: `DFOverseer`

## Expect one or two permission errors, and that is the plan

VMIDs are a **global namespace**, so VM *creation* may demand permission on
`/vms` rather than only the pool, depending on version. Node-level reads (host
CPU/RAM for the watchdog) definitely need a separate grant at `/nodes/proxmox`.

Rather than guessing up front, start with the above. Each failure names the
exact missing privilege, and we add one grant instead of over-provisioning
against imagined needs.

## Verify — including the denial

From the client:

```bash
set -a; . infra/local.env; set +a
AUTH="Authorization: PVEAPIToken=$PVE_TOKEN_ID=$PVE_TOKEN_SECRET"

# should succeed
curl -sk -H "$AUTH" "https://$PVE_HOST:$PVE_PORT/api2/json/pool/$PVE_POOL"

# should be REFUSED — a VM outside the pool
curl -sk -H "$AUTH" \
  "https://$PVE_HOST:$PVE_PORT/api2/json/nodes/$PVE_NODE/qemu/<OTHER_VMID>/status/current"
```

**A permission scheme is only verified once you have watched it deny
something.** A green result from a check that never exercised the boundary is
not evidence.

## Revoking

Datacenter → Permissions → API Tokens → select → Remove. Or:

```bash
pveum user token remove df-overseer@pve api
```

## CLI equivalents

```bash
pveum pool add df-overseer --comment "df-overseer managed VMs"

pveum role add DFOverseer --privs "VM.Allocate,VM.Audit,VM.Config.CPU,VM.Config.Memory,VM.Config.Disk,VM.Config.Network,VM.Config.Options,VM.Config.CDROM,VM.Config.HWType,VM.Console,VM.PowerMgmt,VM.Snapshot,VM.Snapshot.Rollback,Datastore.AllocateSpace,Datastore.Audit"

pveum user add df-overseer@pve --comment "Automation user for df-overseer"
pveum user token add df-overseer@pve api --privsep 0

pveum acl modify /pool/df-overseer  --user df-overseer@pve --role DFOverseer
pveum acl modify /storage/<STORAGE> --user df-overseer@pve --role DFOverseer
```
