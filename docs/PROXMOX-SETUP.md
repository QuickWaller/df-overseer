# Proxmox access setup

Commands to run **on the Proxmox host as root**. Creates a pool, a
minimum-privilege role, a user, and a privilege-separated API token scoped so
it cannot touch anything outside the pool.

Replace `<NODE>` and `<STORAGE>` with your values (`pvesh get /nodes`,
`pvesh get /storage`).

## 1. Pool

```bash
pveum pool add df-overseer --comment "df-overseer managed VMs"
```

## 2. Custom role

Deliberately **excludes** `VM.Allocate` and `VM.Clone` — the overseer manages
the VM it is given; it cannot create or destroy VMs. Also excludes everything
under `Sys.Modify`, `Realm.*`, `User.*` and `Permissions.*`.

```bash
pveum role add DFOverseer --privs \
  "VM.Audit,VM.Config.CPU,VM.Config.Disk,VM.Config.Memory,\
VM.Config.Network,VM.Config.Options,VM.Console,VM.Monitor,\
VM.PowerMgmt,VM.Snapshot,VM.Snapshot.Rollback"
```

If `VM.Snapshot.Rollback` is rejected on your version, drop it and check
`pveum role list` for the exact name — snapshot privileges have moved between
releases.

## 3. User and token

```bash
pveum user add df-overseer@pve --comment "Automation user for df-overseer"

# --privsep 1 means the token starts with ZERO privileges and needs its own
# ACLs. A leaked token then cannot do what the user can.
pveum user token add df-overseer@pve api --privsep 1
```

**The secret is printed once and never again.** Capture it straight into
`infra/local.env` as `PVE_TOKEN_SECRET`.

## 4. ACLs

With `privsep=1`, a token's effective permissions are the **intersection** of
the user's and the token's, so both need granting.

```bash
# Pool — the VM management surface
pveum acl modify /pool/df-overseer --user  df-overseer@pve       --role DFOverseer
pveum acl modify /pool/df-overseer --token 'df-overseer@pve!api' --role DFOverseer

# Node — read-only host stats for the watchdog (CPU/RAM/load).
# Node privileges cannot be granted on a pool path.
pveum acl modify /nodes/<NODE> --user  df-overseer@pve       --role PVEAuditor
pveum acl modify /nodes/<NODE> --token 'df-overseer@pve!api' --role PVEAuditor

# Storage — snapshots need space allocation
pveum acl modify /storage/<STORAGE> --user  df-overseer@pve       --role PVEDatastoreUser
pveum acl modify /storage/<STORAGE> --token 'df-overseer@pve!api' --role PVEDatastoreUser
```

## 5. Tailscale on the Proxmox host

```bash
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up --hostname=prodesk --advertise-tags=tag:server
```

The overseer holds no Tailscale identity of its own — it runs on an
already-enrolled machine (`wills-laptop`) and uses that machine's access.
Tighten with tailnet ACLs so only that machine can reach port 8006 if you want
a second boundary.

## 6. Create the VM, assign it to the pool

Create the DF VM by hand (see `docs/PURPOSE.md` for the spec: 2–4 vCPU pinned,
8 GB RAM, 40 GB disk), then:

```bash
pveum pool modify df-overseer --vms <VMID>
```

Nothing outside this pool is visible to the token.

## 7. Verify — from the client, not the host

```bash
curl -k -H "Authorization: PVEAPIToken=df-overseer@pve!api=<SECRET>" \
  "https://<PVE_HOST>:8006/api2/json/pool/df-overseer"
```

Then confirm the boundary actually holds — **this should fail**:

```bash
curl -k -H "Authorization: PVEAPIToken=df-overseer@pve!api=<SECRET>" \
  "https://<PVE_HOST>:8006/api2/json/nodes/<NODE>/qemu/<SOME_OTHER_VMID>/status/current"
```

A permission scheme is only verified once you have watched it *deny* something.

## Revoking

```bash
pveum user token remove df-overseer@pve api
```
