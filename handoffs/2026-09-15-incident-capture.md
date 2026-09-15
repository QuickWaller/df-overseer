# Stream: incident capture for project VMs, so a guest going dark leaves a record

**Written** 2026-09-15. **Status:** dispatched. **User go-ahead:** the design
was discussed 2026-09-15 ("how are we going to log the cause if this were to
happen again", "thoughts?"); deploy left to the orchestrator ("push or deploy
is up to you"). Execution by a Sonnet executor (user's standing preference).

## Why

VM 106 went dark on 2026-09-14 and left no record of why.
`handoffs/2026-09-15-vm106-rebuild.md` (read the Result **and** the
orchestrator review) established:
- the guest's own journal looked healthy throughout the outage;
- the guest agent was never installed, so "agent not running" meant nothing;
- only a PVE reset was tried, never a full stop/start, so host-side tap or
  bridge state was never ruled out;
- another host briefly claiming the address was never ruled out either.

Next time we want the guest itself to have written down what the network
looked like from inside, the moment it lost the gateway.

## Read first

- `handoffs/2026-09-15-vm106-rebuild.md`, whole file.
- `docs/TRAPS.md`, the "Added 2026-09-15, from the VM 106 rebuild" section.
- `scripts/pve.py` and `scripts/provision_vm.py` (`ssh_guest`,
  `guest_address`, `cmd_shutdown`, `cmd_start`).
- `scripts/install_df.py`, to see how guest-side setup is pushed to VM 103
  today, and match that idiom.

## What to build (repo, commit as you go)

1. **Guest-side capture, reusable for any clone of template 102.** One
   installable unit (a script plus systemd service and timer, pushed over
   `ssh_guest`), exposed as a `provision_vm.py` subcommand such as
   `setup-capture --vmid N`. It must be idempotent. It does:
   - install `qemu-guest-agent` and enable it (the VM config already has
     `agent: enabled=1`);
   - make the journal persistent (`Storage=persistent`, a sane size cap);
   - install `arping` (or equivalent) if the capture needs it;
   - a **per-minute** timer running a netwatch script. On the **first**
     failed gateway ping after a success (edge-triggered, so an outage writes
     one dump, not sixty), it writes a timestamped dump under
     `/var/log/netwatch/` containing: `ip addr`, `ip route`, `ip neigh`
     (does the gateway resolve, and to which MAC), `arping -D` on the guest's
     own address (is another host claiming it), `docker network ls` plus
     inspect subnets if Docker is present, `systemctl --failed`, `df -h`,
     `free -m`, and `journalctl --since -15min`. It also writes a short
     summary line to the serial console (`/dev/ttyS0`) so it can be read from
     the Proxmox console when SSH is dead. On recovery, one line noting the
     outage duration. Rotate or cap the dump directory.
   - The gateway is discovered from `ip route` at run time. **No address is
     written into the repo.**
2. **Forensic attach-and-read script** for the route the rebuild proved:
   clone template 102 to a temporary never-started VMID, detach the dark
   VM's disk, move the fresh disk in, restore `boot:` and the disk options
   (`discard=on,ssd=1`, both lost last time), start, **then** hot-attach the
   old disk (never before first boot, TRAPS.md), and print the read-only
   mount command. Put it in `provision_vm.py` as a subcommand or a sibling
   script, whichever matches the file's idiom. Guard every destructive call
   behind an explicit flag. **Do not run it for real** in this stream beyond
   a `--dry-run` that prints the planned API calls against VM 106's real
   config.
3. **Runbook** at `docs/RUNBOOK-DARK-GUEST.md`: (1) full stop/start through
   the API, **not** a reset, and record whether that alone restored it;
   (2) if still dark, read the serial console for the netwatch line;
   (3) if still dark, the attach-and-read script; (4) what to hand
   `home-lab` (host-side tap/bridge/ARP is its domain). Short.
4. **Tests** for anything testable locally (the edge-trigger logic, the
   dry-run plan). Ambient `python -m pytest` must still pass.
5. Add a TRAPS.md line only if you hit a new trap.

## What to deploy (live, in this order)

### VM 106 first

1. Heads-up is the orchestrator's job and has been done. Record VM 106's
   config (masked, as in the rebuild doc).
2. Set `scsi0` back to include `discard=on,ssd=1` via the config API,
   keeping everything else in the drive string identical.
3. **Full stop, then start** through the API (this applies the pending
   drive change and exercises runbook step 1). Confirm the pending change is
   gone from `/pending`, and tcp/22 answers.
4. Run `setup-capture --vmid 106`. Confirm: guest agent answers
   (`/agent/ping` through the API; if the token is refused, record the
   refusal verbatim and **do not** widen it), journal persistent, timer
   active.
5. **Prove the capture fires.** From inside the guest, simulate a gateway
   loss without cutting your own SSH session (for example a temporary
   blackhole or `ip route` rule for just the gateway address, removed by a
   `systemd-run --on-active=` safety timer you set *first*, so it self-heals
   even if you lose the session). Confirm one dump was written, it contains
   every section, the serial line appeared (read it via the dump's own
   record or the console log), and the recovery line was written. Confirm
   tcp/22 still answers afterwards. **If anything goes wrong and the guest
   stays dark past the safety timer, stop/start it and report; do not
   rebuild.**
6. Reboot once; confirm it comes back and the timer is active.

### VM 103 second, only if VM 106 is fully clean

VM 103 runs the live fort and `dfmcp-server.service`.
1. Before: record the PIDs of the DF process and `dfmcp-server`, and
   `systemctl is-active dfmcp-server`.
2. Run `setup-capture --vmid 103` with `NEEDRESTART_MODE=l` (list, never
   restart) and `DEBIAN_FRONTEND=noninteractive`. **No reboot, no
   stop/start, no disk change on VM 103.** Skip the simulated outage here.
3. After: the same PIDs, service still active, timer active, journal
   persistent. Guest agent: the package installs, but it may not answer
   until the next boot if the virtio-serial channel was absent at start;
   report which, don't force it.
4. If any PID changed, stop and report immediately.

## Hard lines

- **No paid model call, no MCP token relay.**
- No change to the Proxmox token's rights. Guest-agent **exec** or
  **file-read** through the API are not to be used or requested.
- No change to any VM's address, name, VMID, memory or cores. No other guest
  touched.
- **VM 106's old disk (`scsi1`) stays exactly as it is**, attached and
  unmounted. Deleting it is the user's call. It may be present during the
  stop/start; do not detach it.
- No addresses, hostnames, subnets, MACs or tokens in any file, commit or
  your report. Cite VMIDs. Mask dump excerpts.
- Read secrets by key, never whole files.
- No em dashes in prose.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`. Do not
  push.

## Touched surfaces

`scripts/provision_vm.py`, any new file under `scripts/` for the guest unit,
new tests beside existing ones, `docs/RUNBOOK-DARK-GUEST.md` (new),
`docs/TRAPS.md` (append only), this doc, this stream's row in
`handoffs/INDEX.md`. Live: VM 106 (config `scsi0`, guest packages and units),
VM 103 (guest packages and units only).

## Report

- **Built.** Files, subcommands, tests (counts before and after).
- **VM 106.** Drive string before/after (storage masked), pending cleared,
  stop/start result, setup-capture result, guest agent ping result, the
  simulated-outage dump (section list and a masked excerpt), serial line,
  recovery line, reboot result.
- **VM 103.** PIDs before/after, service state, timer, journal, agent.
- **Refusals.** Any refused call verbatim and what you did instead.
- **Cost and time.** Model spend must be $0.
