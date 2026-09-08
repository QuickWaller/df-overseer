# infra

Everything here describes the *shape* of the deployment. Actual host names,
addresses, tokens and IDs live in `infra/local.*`, which is **gitignored**.

Copy `local.example.env` to **`.env` in the repo root** and fill it in. That is
where `pve.py`'s `load_env()` actually reads from, and where the live values
are. This file previously said `infra/local.env`, which no code has ever read;
corrected 2026-08-28 to describe what the scripts do rather than what the
layout suggests. `infra/local.example.env` is committed on purpose (the
`infra/local.*` ignore rule has an explicit `!infra/local.example.*`
exception), so a fresh clone has a template to fill in.

This repo is public. Nothing in a committed file should identify the host.
Committed files use placeholders (`<pve-host>`, `<df-vm-ip>`, `<lan-subnet>`,
`<tailnet-a>`); the real values are yours and stay local.

Gitignored files you will have if you run this, and will not have if you
cloned it:

| | |
|---|---|
| `.env` (repo root) | host, token, node, storage, SSH keys, `DF_MAC_OVERRIDES`, `DF_VM_IP` |
| `local.proxmox-access.md` | the access layer as read back from the API |
| `local.df-vm-install.md` | the fortress VM's DF + DFHack install, and the verified facts about running it |
| `local.hardware-plan.md` | the RAM/disk/node plan for the two-box cluster |

## Access model

The overseer reaches Proxmox over the tailnet. It does **not** hold a Tailscale
identity of its own — it runs on an already-enrolled machine and uses that
machine's network access. Tailscale ACLs are therefore the outer boundary; the
Proxmox token is the inner one.

## Principle: the pool is the fence, not the role

The token (`svc-<project>-sandbox@pve!build`, scoped to a matching
`<project>-sandbox` pool and storage, plus a narrow node role at
`/nodes/<pve-node>` and an SDN role at `/sdn/zones/localnetwork`) **can create and
destroy VMs, standing and ungated, inside its own pool.** `VM.Allocate` and
`VM.Clone` are both granted (`decisions/DECISIONS.md`, 2026-08-25 and
2026-08-26). Containment comes from the pool boundary, not from a narrow
role: proved by a 200 against its own pool against a 403 against a guest
outside the pool on the same node, which makes that 403 a proof of the pool
fence rather than the node fence.

A privilege reaching outside the pool, such as a second pool or broader node
rights, is still a deliberate expansion with its own decision-register entry,
not a quiet addition.

## Setup

Building the pool, role, user, token and storage is home-lab's job:
`runbooks/project-sandbox.md` in the private `home-lab` repo is the
generalized procedure, and this project is its reference instance. This repo
owns what runs against that identity once built: `.env`, the scripts below,
and the verified facts in `infra/local.*`. `docs/PROXMOX-SETUP.md` is
superseded history, not a live setup guide.

## Scripts

| | |
|---|---|
| `scripts/provision_vm.py` | cloud image to template to VM, and the memory-gated start |
| `scripts/install_df.py` | DF + DFHack onto a VM, plus verify / start / stop / worldgen / save backup |

Both read the repo-root `.env` and hold nothing host-specific themselves.
`install_df.py` additionally takes `--dry-run`, which prints the exact script
it would run inside the guest and connects to nothing, so it can be reviewed
offline. `provision_vm.py` has no equivalent.
