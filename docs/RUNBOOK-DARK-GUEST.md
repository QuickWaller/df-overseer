# Runbook: a project VM goes dark

For a df-overseer guest (VM 103, VM 106, or any future clone of template
102) that stops answering ping/SSH with no obvious cause. Written after VM
106's 2026-09-14 incident (`handoffs/2026-09-15-vm106-rebuild.md`), whose
rebuild found the cause was never established from the guest's own evidence
-- partly because only a PVE **reset** was tried on the original incident,
never a full stop/start, so host-side tap/bridge state was never ruled out.
This runbook exists so the next one does not repeat that gap.

Work through these in order. Stop as soon as one step restores it, and
record which step worked -- that is the most useful fact this runbook
produces.

## 1. Full stop, then start -- not a reset

Through the PVE API (`scripts/provision_vm.py shutdown --vmid N`, then
`start --vmid N`), or the equivalent config/status calls directly. **Not**
a reset: a reset keeps the same QEMU process and its tap device on the
bridge, while a stop/start recreates both
(`docs/TRAPS.md`, "Added 2026-09-15, from the VM 106 rebuild"). If the
guest is healthy internally but unreachable from outside, this is the
cheap discriminator between a guest-side cause and a host-side one, and it
is also the fastest fix if it works.

Record: did the guest answer ping/tcp22 after the stop/start alone, without
touching the disk at all. If yes, the cause was host-side (tap/bridge/ARP
state), not the guest's own OS or config, and the incident is resolved
without a rebuild.

## 2. Read the serial console for the netwatch line

If `scripts/provision_vm.py setup-capture` has been run on this guest, the
netwatch timer (`scripts/guest-capture/df_netwatch.py`) writes one summary
line to `/dev/ttyS0` the moment it detects the gateway stop answering, and
one more when it recovers. Read it from the Proxmox console
(`agent: enabled=1` and `serial0: socket` are already set on every guest
this repo builds) even with SSH dead -- the whole point of writing to the
serial device rather than only to a file is that it survives a guest with
no working network stack to read that file over.

If the line is there, it names the gateway address the guest tried and the
approximate outage duration; the full dump it refers to
(`/var/log/netwatch/dump-<timestamp>.txt`) is only reachable once SSH (or
the forensic disk read below) is available again.

If step 1's stop/start already fixed it, the timer's own "recovered" line
will confirm the same thing independently.

## 3. Forensic attach-and-read

If the guest is still dark: `scripts/provision_vm.py forensic-attach
--vmid N`. Without `--execute` this only reads the target's live config and
prints the planned sequence -- run it that way first and read the plan
before ever adding `--execute`. The sequence (proved live during the VM 106
rebuild, `handoffs/2026-09-15-vm106-rebuild.md`'s Result): clone template
102 to a temporary never-started vmid, detach the dark VM's disk
(non-destructive), move the temp clone's fresh disk into the dark VM's
place, restore `boot:` and the disk's `discard=on,ssd=1` (both are cleared
by `move_disk` -- `docs/TRAPS.md`), delete the temp vmid, start the VM
clean, and only **after** that first boot completes, hot-attach the old
disk read-only as a second device. **Never attach the old disk before the
fresh disk's first boot** -- both are lineage clones of the same template
and share filesystem UUIDs and `/etc/machine-id`, so the initramfs can
mount the wrong one as root, which looks exactly like a dead network from
the outside (`docs/TRAPS.md`).

Once attached, mount it read-only on the now-running guest
(`mount -o ro,noload /dev/sdb1 /mnt/olddisk` for ext4; `lsblk` first to
confirm which device it landed as) and read
`journalctl --directory=/mnt/olddisk/var/log/journal` for the outage
window, plus `/mnt/olddisk/var/log/netwatch/` if the capture unit had
already been installed on the old disk. `umount` it when done; leave it
attached (unmounted) rather than detaching it -- deleting an old disk is
the user's call, not an automated step's.

## 4. What to hand `home-lab`

If steps 1-3 leave the guest's own logs looking healthy throughout the
outage (clean OS, clean network config, no OOM, no disk-full, no
docker-network collision) and reachability was still lost, the cause is
outside anything this repo's token or access can see: the host's vswitch,
tap device, bridge or ARP table. That is `home-lab`'s domain, not this
repo's -- follow `CLAUDE.md`'s "Upstream obligations" section: cite the
VMID and the exact outage window (never an address), and if a `home-lab`
session is not live, record the open question in `Working.md` rather than
editing anything in `../home-lab` from here.
