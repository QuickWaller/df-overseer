# infra

Everything here describes the *shape* of the deployment. Actual host names,
addresses, tokens and IDs live in `infra/local.env`, which is **gitignored**
(`infra/local.*`). Copy `local.example.env` to `local.env` and fill it in.

This repo is public. Nothing in a committed file should identify the host.

## Access model

The overseer reaches Proxmox over the tailnet. It does **not** hold a Tailscale
identity of its own — it runs on an already-enrolled machine and uses that
machine's network access. Tailscale ACLs are therefore the outer boundary; the
Proxmox token is the inner one.

## Principle: the token cannot leave its pool

Proxmox access is scoped to a single resource pool, granted to an API token with
privilege separation enabled. The token deliberately **cannot create or destroy
VMs** — `VM.Allocate` and `VM.Clone` are excluded. A human creates the VM; the
overseer manages the one it is given.

If the overseer later needs to provision its own VMs, that is a deliberate
privilege expansion with its own decision-register entry, not a quiet addition.

## Setup

See `docs/PROXMOX-SETUP.md` for the commands.
