# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-08-28 (evening)

**State at a glance.** The game side is now *reproducible*, not just running.
`scripts/install_df.py` installs, verifies, runs and backs up DF on VM 104, and
every command has been exercised against the live machine. That was the
precondition for the hardware work, so the only thing still holding the
hardware sequence is a decision the user has not made. `origin/main` is
`d2af0f3`, pushed clean, working tree clean. VM 104 is up with DF running and
RPC answering.

### What changed this session

**The DF install is scripted and verified.** `scripts/install_df.py`:
`install`, `verify`, `start`, `stop`, `gen`, `saves`, `backup`. Idempotent,
driven over SSH from the workstation, reusing `provision_vm.py`'s `ssh_guest`
and `.env` discipline. `--dry-run` prints the exact remote script without
connecting to anything, which is what allowed it to be tested offline before it
touched a machine. Full detail is in the archived section; the short version is
that offline testing passed and then **running it against 104 found four bugs
offline testing could not**, three of which were checks that could not fail.

**We are on `<tailnet-a>`.** The user switched mid-session. The Proxmox host
and VM 104 are reachable right now. Switching back gives `gitea`, `secrets` and
the tenant hosts; it is a real either/or, one at a time.

**The host had rebooted and nothing came back.** Host booted approximately
2026-08-27 23:32. VM 104 was found **stopped**, contradicting the previous
handover's "should be as described". It was started, verified and left running.

**Docs reconciled and pushed.** `docs/PURPOSE.md`, `CLAUDE.md`'s status blurb,
`infra/README.md`, `memory/MEMORY.md`, `decisions/DECISIONS.md`, and the
gitignored `infra/local.df-vm-install.md`, which is the authoritative record for
everything VM-specific.

### Decisions still owed by the user

**1. Reinstall or rebuild.** Full Proxmox reinstall on the ProDesk, or rebuild
the `df-overseer` pool and VMs on the existing install? Asked again this
session and **explicitly not answered**. It gates cluster creation, because a
reinstall must happen before a cluster exists, so nothing in the hardware
sequence can be scheduled until it lands. Do not infer an answer from silence.

**2. Deleting the test worlds.** Eight now (`region1`-`region8`; 7 and 8 were
created testing `gen`) plus a stale 4 KB `save/current`. Destructive, so it was
left alone.

### Things a next session will otherwise get wrong

**Verify VM 104 rather than assuming it.** This is now twice in two sessions
that the VM was not in the state the handover predicted. `install_df.py verify`
is the cheap check and takes seconds.

**DF ignores SIGTERM.** There is no graceful shutdown: every stop waits the
full timeout and then needs SIGKILL. Once a fort is live, saving before
stopping is mandatory, not optional. This is the single biggest constraint on
the systemd work.

**`onboot` is not set on VM 104.** The problem is bigger than "the game does
not survive a reboot": the **VM itself** does not come back after a host
reboot. Separate one-line fix from the systemd units, not yet made because it
changes VM config rather than repo state.

**`dfhack-run` output is not plain text.** It colours output even when stdout
is not a tty and ends with a bare `\x1b[0m` on its own line, so `tail -n1`
returns the escape sequence. With the game down it prints `Could not connect to
localhost:5000`, which is **non-empty**: any readiness or health check that
merely tests for output will pass against a dead game. `install_df.py`'s
`dfhack_lua()` helper handles both; anything new talking to `dfhack-run` needs
the same treatment.

**A check that cannot fail is not a check.** Three of the four bugs this
session were that shape, and it is the same lesson as the 2026-08-28 leak-scan
entry in `DECISIONS.md`. Before reporting an all-clear, prove the check can go
red.

**`-gen` still fails silently** roughly a quarter of the time, and it was
reproduced again this session. Success is the region directory existing, never
the exit code. `save/current` **survives a failed run**, so its presence proves
nothing on its own: compare its mtime across the attempt. `install_df.py gen`
does all of this already.

**Saves are not in the game directory.** XDG path, resolved from `getent
passwd` so it is right under sudo. Anything aimed at `<df>/data/save` copies
nothing and reports success.

**`DF_MAC_OVERRIDES` in `.env` is load-bearing.** Without it a rebuilt VM 104
gets a derived MAC and drops its DHCP reservation. Gitignored, so it does not
travel with the repo.

**Cluster join order is destructive.** The joining node must have no guests;
joining wipes its guest config. Create on the ProDesk, join the empty
EliteDesk. The reverse loses `df-fortress`.

**A two-node cluster is worse than two standalone hosts** until the qdevice
lands. One node down leaves the survivor unable to start, stop or edit
anything. Running VMs keep running.

**A reset destroys VMs we cannot see.** VM 102 exists on the host outside the
`df-overseer` pool; our token gets `403` and `pool_members()` does not list it.
Enumerate as root in the GUI before wiping anything.

**Clusters do not pool RAM.** Two 16 GB nodes are two 16 GB machines with one
login.

**Our Proxmox token is pool-scoped and cannot run node-level commands.**
Anything like `dmidecode` on the ProDesk needs root SSH to the host, which has
not been established. Check that access exists before planning around it.

### What a next session should pick up

**1. Systemd units for Xvfb and DF, plus `onboot` on 104.** The clear next
step, unblocked, and the one today's findings constrain most: `ExecStop` must
save through `dfhack-run` and `TimeoutStopSec` must be long enough to let it
finish, or every host reboot kills the fort. Nothing currently survives a
reboot at either level.

**2. `cpu: host` -> `x86-64-v2-AES`** in `provision_vm.py`, still set on 104.
Accepted in `DECISIONS.md`, not implemented. Blocks migration between the Kaby
Lake i7-7700T and the Coffee Lake i5-8500T, which is the main reason for
clustering. Cold stop/start to apply, cheap now the install is scripted.

**3. `check_reachable` / `get_connectivity_report`** (`docs/PURPOSE.md` build
item 2). Copies `warn-stranded.lua`'s algorithm, and there is a live DFHack to
run it against.

**4. Embark, and measure a running fort's memory.** 4096 MB is still unproven
for a live fort; worldgen answered a different question (561 MB peak). Embark
needs UI driving, which `-gen` avoided, so how much is scriptable matters.

**5. The compliance eval harness.** Research build item 1, "do first, before
any fort runs". No game, no agent, never blocked.

**6. Mechanical prediction grading** (research build item 3): compare a
prediction's `signal` against recorded state at `check_at`. No calibration
metric means anything until it exists.

**7. The ledger's write path** waits on the perception layer. `defense_depth`,
`primary_industry` and `surface_footprint` are likeliest to have no clean
mechanical reading; if so they become `AGENT` fields.

**8. Re-run the perception eval against real briefings** once `llm-brief.lua`
exists. Today's 99.1% is on generous hand-authored fixtures.

### Housekeeping, carried forward

- **Proxmox token not rotated**, pasted into an earlier transcript.
- **Temporary Anthropic key in `.env` expires ~2026-09-03**, five days out.
  Rotate or remove; do not commit or log it.
- **First off-host save dump taken:** `backups/df-saves-104-*.tar.gz`, 4.1 MB,
  181 entries. `backups/` is gitignored.
- **Tarball checksums recorded** in `infra/local.df-vm-install.md` but **not
  enforced** by the script, which only runs `bzip2 -t`. That catches truncation
  and HTML error pages, not substitution.
- **The published hostname should be treated as exposed.** The rewrite removed
  it from the repo; it did not un-publish it. The user chose not to rename.
- **`willsmith.nz` was deliberately left in.** Intended public face, not a leak.
- **The ProDesk's RAM slot layout is still unknown**, and it decides whether
  the spare 8 GB stick is useful or scrap.
- **The SSD out of the Omen has an unverified size.**
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent` still deferred.**
- **DF replay determinism unverified**, and research build item 7 rests on it.
- **`hypothesis_id` has no registry.** A typo silently orphans evidence.

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
