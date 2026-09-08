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

**Commit state.** This session's work is two local commits, `fb96fa0`
(the provisioning research spec) and `1791bc6` (the estate reconciliation plus
two dead-check bugfixes). Working tree is clean. **Not pushed**, that needs its
own go-ahead per the Rules section.

**The one blocking human step.** `.env` is already repointed to the new
identity (`PVE_NODE`, `PVE_POOL`, `PVE_STORAGE`, `PVE_TOKEN_ID` all updated).
`PVE_TOKEN_SECRET` is deliberately left blank: no automation may paste a
secret into a file, so a human has to do this one copy before anything else
in `ROADMAP.md`'s Now bucket can run.

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

**Two more stale values sitting in `.env`, not yet acted on.** `PVE_PASSWORD`
predates the 2026-09-02 reinstall and nothing reads it; it is a credential
with no purpose left. `ANTHROPIC_API_KEY` expired around 2026-09-03. Neither
blocks the rebuild, both are worth rotating out or removing; do not commit or
log either.

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
- **`DF_MAC_OVERRIDES` in `.env` is load-bearing.** Without it a rebuilt VM
  gets a derived MAC and drops its DHCP reservation.
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

`ROADMAP.md`'s Now bucket is the canonical list. Headline order: paste the
token secret, verify with the read-only `status` call, rebuild template then
VM, name the new guest with the `.internal` suffix, watch for quorum during
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
