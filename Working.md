# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-08-30

**State at a glance.** Item 1 from the previous handover's pick-list is done
and proven, not just written: `df-xvfb.service` and `df-fortress.service`
exist, are enabled, and a **full guest reboot was actually triggered** and
both units came back with DF answering RPC and zero manual steps. `onboot=1`
is set on VM 104 (confirmed by reading the config back), though the
host-reboot case itself remains untested -- only the cheaper guest-reboot
proxy was, deliberately, since rebooting the physical host is a bigger action
than this session took unilaterally. **Committed as two commits, `d275ccc`
(systemd/onboot) and `847ccdf` (ROADMAP.md)**; working tree is clean; **not
pushed** -- that needs its own go-ahead per the Rules section. VM 104 is up,
DF running under systemd, RPC answering. Stayed on whichever tailnet gives
Proxmox/VM access the whole session; never needed to switch.

**`ROADMAP.md` now exists**, following the convention documented in
AgentSecretary's `CLAUDE.md` (a sibling repo at
`c:\website-projects\AgentSecretary`): Now/Next/Later/explicitly-not-doing
buckets, one line per item pointing into `Working.md`/`decisions/`/`docs/`/
`research/` rather than re-narrating. `CLAUDE.md`'s Structure section gained a
matching bullet, including the update triggers (a Now-item starting or
finishing, an explicit user priority call, a full-review pass at least every
~2 weeks). Its Now bucket's "commit this session's changes" item is removed
below, since that update trigger (a Now-item finishing) fired within the same
session that added the file.

### What changed this session

**`install_df.py systemd`** (new command): writes and enables
`df-xvfb.service` + `df-fortress.service`, idempotent, `--start` to also start
now rather than only enabling for next boot. **`provision_vm.py set-onboot
--enable|--disable`** (new command): flips the VM's `onboot` flag with the same
read-back-verify pattern as `set-memory`. Both dry-run clean.

**Four real bugs found by actually exercising the stop/start/reboot cycle**,
not just writing the units -- full detail and the fixes are in
`infra/local.df-vm-install.md`'s new "Verified 2026-08-30" section:

1. `install_df.py stop` never killed the manually-started Xvfb, only
   `dwarfort`. A leftover one squatting on `:99` made `df-xvfb.service`
   crash-loop and destabilized `df-fortress.service` with it.
2. `set -o pipefail` + `systemctl list-unit-files | grep -q` in `verify`'s new
   unit check reported real, enabled units as "not installed" -- `grep -q`'s
   early exit SIGPIPEs the still-writing `systemctl`, and pipefail turns that
   into a reported failure. Fixed with `systemctl is-enabled` directly, no
   pipe.
3. `ExecStop`'s own kill (needed because DF ignores SIGTERM) left the unit
   `failed` after every clean stop: `MainPID` is `./dfhack`, which folds
   dwarfort's kill signal into its own bash exit code (137/143), so
   `SuccessExitStatus=SIGKILL` (a signal name) matched nothing. Fixed with
   `SuccessExitStatus=137 143`.
4. The workstation's SSH transport decodes remote output as cp1252 by
   default; the first UTF-8 character in remote output (`systemctl status`'s
   unit-state bullet) raised `UnicodeDecodeError` and killed the tool. Fixed
   in both `ssh_guest` and `scp_from` with explicit `encoding="utf-8",
   errors="replace"`. This was latent beyond just that one command.

**Measured, not assumed:** `systemctl stop df-fortress` takes 37.8 s end to
end (5 s post-quicksave settle, up to 30 s SIGTERM wait, 2 s SIGKILL settle).
`TimeoutStopSec=180` has wide margin against that, but zero margin has been
tested against an actual live fort's quicksave time -- none has been embarked.

### Decisions still owed by the user

**1. Reinstall or rebuild.** Full Proxmox reinstall on the ProDesk, or rebuild
the `df-overseer` pool and VMs on the existing install? Still **not answered**
across three sessions now. Gates cluster creation. Do not infer an answer from
silence.

**2. Deleting the test worlds.** Eight now (`region1`-`region8`) plus a stale
4 KB `save/current`. Destructive, so still left alone.

### Things a next session will otherwise get wrong

**Verify VM 104 rather than assuming it.** `install_df.py verify` is the cheap
check.

**DF still ignores SIGTERM**, confirmed again this session under systemd's own
kill path, not just the manual one. Once a fort is live, quicksave before stop
is mandatory. `systemd-stop.sh` on the VM does this unconditionally now for
the systemd path; `install_df.py stop --save` is still opt-in for the manual
path.

**The manual (`start`/`stop`) and systemd-managed paths must not run at once.**
Stop one before starting the other, or they contend for `:99` and the RPC
port. `install_df.py start`'s output now says so.

**Host-reboot survival is still unverified.** Guest-reboot survival is proven;
`onboot=1` is set and read back from the API; but nobody has actually power-cycled
the Proxmox host to watch VM 104 come back on its own. That is the one piece
of the original ask not yet end-to-end tested, and doing so needs the user's
go-ahead first (see the Rules section: destructive/hard-to-reverse actions).

**A check that cannot fail is not a check**, again -- bug 2 above is the same
shape as three of the four bugs from 2026-08-28 and the 2026-08-28 leak-scan
`DECISIONS.md` entry. Before reporting an all-clear, prove the check can go
red.

**`onboot` is now `1` on VM 104.** If VM 104 is ever rebuilt from scratch via
`provision_vm.py clone`, re-run `set-onboot --enable` -- it is a live VM
config, not baked into the template.

**`-gen` still fails silently** roughly a quarter of the time. Success is the
region directory existing, never the exit code; `save/current` survives a
failed run and proves nothing by its presence alone.

**Saves are not in the game directory.** XDG path, resolved from `getent
passwd`.

**`DF_MAC_OVERRIDES` in `.env` is load-bearing.** Without it a rebuilt VM 104
gets a derived MAC and drops its DHCP reservation.

**Cluster join order is destructive.** The joining node must have no guests.
Create on the ProDesk, join the empty EliteDesk.

**A two-node cluster is worse than two standalone hosts** until the qdevice
lands.

**A reset destroys VMs we cannot see.** VM 102 exists on the host outside the
`df-overseer` pool; our token gets `403` and does not list it. Enumerate as
root in the GUI before wiping anything.

**Clusters do not pool RAM.**

**Our Proxmox token is pool-scoped and cannot run node-level commands.**

### What a next session should pick up

Same list as `ROADMAP.md`'s Now/Next buckets, which is now the canonical
version of this; kept here only as the short form. Headline items: decide
whether to ask the user for the host-reboot test now or fold it into the
cluster work once decision 1 above lands; `cpu: host` -> `x86-64-v2-AES`;
`check_reachable`/`get_connectivity_report`; embark and measure a running
fort's memory; the compliance eval harness.

### Housekeeping, carried forward

- **Proxmox token not rotated**, pasted into an earlier transcript.
- **Temporary Anthropic key in `.env` expires ~2026-09-03**, three days out now.
  Rotate or remove; do not commit or log it.
- **Tarball checksums recorded** in `infra/local.df-vm-install.md` but **not
  enforced** by the script, which only runs `bzip2 -t`.
- **The published hostname should be treated as exposed.** The user chose not
  to rename.
- **`willsmith.nz` was deliberately left in.** Intended public face, not a leak.
- **The ProDesk's RAM slot layout is still unknown.**
- **The SSD out of the Omen has an unverified size.**
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent` still deferred.**
- **DF replay determinism unverified**, and research build item 7 rests on it.
- **`hypothesis_id` has no registry.**

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
