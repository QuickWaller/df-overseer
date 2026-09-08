# Working archive — week of 2026-09-07

Section moved wholesale out of `Working.md` on 2026-09-08. The handover below
describes VM 104 and the estate as they stood on 2026-08-30; both were
rebuilt out from under this repo between 2026-09-01 and 2026-09-08 while it
sat quiet (full analysis: `infra/local.2026-09-08-doc-reorg-plan.md`,
gitignored since it quotes home-lab's own infra specifics; a clone of this
public repo will not have it). Nothing here
is summarised or edited; it is kept as the record of what was true and how it
was learned, not as current state.

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

**1. Reinstall or rebuild.** Full Proxmox reinstall on SRV-01, or rebuild
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
Create on SRV-01, join the empty SRV-02.

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
- **SRV-01's RAM slot layout is still unknown.**
- **The SSD out of the Omen has an unverified size.**
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent` still deferred.**
- **DF replay determinism unverified**, and research build item 7 rests on it.
- **`hypothesis_id` has no registry.**

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

---

## HANDOVER - 2026-09-08

Moved wholesale from `Working.md` on 2026-09-08 (later the same day):
the rebuild this handover narrates completed and moved on to worldgen,
DF start, embark-automation research, and a live-view capture build,
all superseding this as current state. Kept as the record of the
rebuild, not as current state.

**State at a glance.** VM 103 (`df-colony-01`) is rebuilt, installed and
verified, but DF itself has not been started yet, so no world exists and
nothing is actually running unattended. The infrastructure this handover
opens with (below) is history now: VM 104 (`df-fortress`) and template 101
were both deleted 2026-09-01, not migrated, while this repo sat quiet since
2026-08-30. The Proxmox host was
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

**Commit state.** Six local commits this session, ending at `cb9560d`.
Working tree is clean. **Not pushed**, that needs its own go-ahead per the
Rules section. The last two are the provisioning work: `4e0f8da` mounts a
`urllib3` retry policy on the API client and names the inquorate trap at the
error, and `cb9560d` deletes the template bake and switches the VM to a
static address assigned at clone time, taking `provision_vm.py` from 724
lines to 533.

**The blocking human step is discharged.** `PVE_TOKEN_SECRET` is in `.env`
and the new pool-scoped identity is **proven from this workstation**:
`provision_vm.py status` returned 12.5 GiB available, next free vmid 102, and
an empty pool. That last point is worth keeping: the pool being empty
independently confirms the 2026-09-01 deletion rather than a token that cannot
see its own VMs. The call also exercised this session's auth-header fix
against the live API, since an unauthenticated client gets `401` rather than
data.

**Spike A is done and it passed clean, first attempt, 2026-09-08.**
`fetch-image` downloaded the pinned image and PVE accepted the checksum;
`build-template` created VM 102, imported the disk, resized to 25G on attempt
1 of 4, and converted to a template **without ever booting it**, which is the
bake deletion working end to end. `DF_TEMPLATE_VMID=102` is recorded in
`.env`.

Four things that were unverified are now verified by that run: the
`checksum`/`checksum-algorithm` spelling on `download-url`, which was the
single least-confident claim in the provisioning research; the new storage
having the `import` content type; the pool-scoped token driving the whole
image-to-template flow; and the auth-header fix under real load.

**Phase H is done: the old identity is retired, 2026-09-08.** The exposed
`df-overseer@pve` token, live since 2026-08-24, no longer exists. Removed at a
root shell on a confirmed-quorate node: token `api`, the user, and both
`DFOverseer`/`DFOverseerNode` roles. Deleting the user took its three ACLs with
it, including a `/sdn/zones/localnetwork` grant that was **not** in this repo's
record and only surfaced because the retirement was checked before it was run,
and a `/nodes/proxmox` binding that had pointed at a node name that stopped
existing on 2026-09-02. Nothing was lost: the new identity already holds
`PVESDNUser` on that same zone. Verified both directions, that the old user,
ACLs and roles are gone **and** that `svc-df-overseer-sandbox@pve` still
exists, then re-ran `provision_vm.py status` to confirm this repo still
authenticates. **Still owed, in home-lab not here:** its
`secrets/registry.md` row goes to `retired` with the date.

**`clone` is done, 2026-09-08: VM 103 `df-colony-01` is up at
`192.168.2.201`.** User supplied `DF_VM_IP=192.168.2.201/24`. `clone --name
df-fortress.internal --full` built VM 103 from template 102 as a full clone
(matching the 2026-08-24 precedent for VM 104), `start --vmid 103` brought it
up, and `install_df.py verify --vmid 103` reached it over SSH with no address
discovery, confirming the static-assignment design works end to end on a real
build. Its FAIL lines are the expected shape for a bare clone (no DF/DFHack,
`init.txt` unset, no swap, no systemd units) — see
`decisions/DECISIONS.md` 2026-09-08 row. `DF_VMID=103` is recorded in `.env`.

**Renamed to `df-colony-01` same day, then the `.internal` convention itself
corrected twice more.** User caught the first problem: "df" already means
Dwarf Fortress, and the literal string `.internal` was showing up in the
Proxmox name field, unlike `subnet-router-01`/`-02`. First fix (wrong):
dropped `.internal` from both the Proxmox name and the guest hostname,
reasoning it was DNS-only. **Corrected by the user against home-lab's actual
convention**: the two fields split, Proxmox's name stays bare
(`df-colony-01`) and `.internal` belongs on the guest's own OS hostname
(`df-colony-01.internal`), matching `subnet-router-01` on both fields. Fixed
by hand, verified, then scripted so it isn't manual next time:
`install_df.py` gained `step_hostname`, run first (now `[1/6]`, the rest
renumbered), reading the VM's Proxmox name over the API and setting
`hostnamectl`/`/etc/hosts` to `<name>.internal`, idempotent. →
`decisions/DECISIONS.md` 2026-09-08 rows (two, the wrong read and the
correction).

**VM 103 fully installed and verified, 2026-09-08.** `install_df.py install`
ran clean (packages, swap, both tarball checksums matched, extraction,
`init.txt`), `install_df.py systemd` installed and enabled
`df-xvfb.service`/`df-fortress.service` for next boot, and
`provision_vm.py set-onboot --enable` set the Proxmox-level `onboot=1`.
`install_df.py verify` reports all checks passed, with only the two expected
`....` lines (no save dir, DF not running — no world generated yet). First
VM to go clone-to-verified purely from this repo's own scripts, no manual
VM 104-era step anywhere. → `decisions/DECISIONS.md` 2026-09-08 row.

**World generated and DF running under systemd, 2026-09-08 — first thing in
this project to run unattended.** `install_df.py gen` produced world 1 on
attempt 1 of 3 (seed 658085253, region present, 692K). Started manually first
to confirm it worked, then deliberately stopped again (`stop --save`;
quicksave was a no-op since no fort has been embarked yet, then needed
SIGKILL after the full SIGTERM timeout, the documented trap behaving exactly
as expected) because a manual instance doesn't survive a reboot. Re-started
via `install_df.py systemd --start`: `verify` now shows `dwarfort` running
(pid 11359), RPC on `127.0.0.1:5000`, not exposed off-box, both units
installed and enabled. → `decisions/DECISIONS.md` 2026-09-08 row.

**Not done yet: no fort exists.** A world was generated and DF is idling at
it, but nobody has embarked. That's the next real step, whenever it's
wanted.

**Embark-automation research done, 2026-09-08** —
`research/2026-09-08-embark-automation.md`, read-only against VM 103. Screen
sequence, keybindings for the confirmed part of the flow, and the success
check are all primary-source-confirmed from installed DFHack scripts (chiefly
`deep-embark.lua` and `gui/embark-anywhere.lua`), not guessed. The one real
gap: how "Start" on the title screen reaches a fresh embark in the existing
region, as opposed to continuing/reclaiming — no installed script exercises
that hop, so it needs live, polled testing (`dfhack.gui.getCurViewscreen()`
after each simulated key) to nail down, ideally against a snapshotted VM
state given the hard-to-reverse-actions rule. → `decisions/DECISIONS.md`
2026-09-08 row. **Next step:** either write and live-test the implementation
script against VM 103, or snapshot the VM first if that live-testing risk is
a concern.

**This research got knocked out twice by an account-wide rate limit** before
finishing on a third resume after an account switch. Worth knowing for any
session that spawns background research agents: a 429 on a background agent
doesn't lose its work if you resume the same agent (by id) rather than
starting fresh — it kept everything it had found across three attempts.

**Live-view capture built and verified on VM 103, 2026-09-08** —
`install_df.py stream` (new subcommand), a systemd timer running `import` on
the Xvfb display every 15s. Verified for real by pulling `latest.png` and
viewing it — genuine DF title screen. Two bugs found and fixed in the same
pass: ImageMagick silently wrote PostScript instead of PNG because the temp
filename didn't end in a recognized extension, and the capture directory was
root-owned while the service runs as `df`. → `decisions/DECISIONS.md`
2026-09-08 row. **Blocked on the ingest side, paused 2026-09-08 — user can't
do the Cloudflare console work right now.** willsmith.nz is a static GitHub
Pages site, no backend, confirmed by `research/2026-09-08-live-viewing.md`.
**Cost check done, not just deferred blind:** for this traffic shape (one
tiny overwritten object, ~175K writes/month, personal-site read volume),
R2's free tier covers it indefinitely — 1M writes/mo and 10GB storage free,
and R2's actual differentiator is **zero egress fees ever**, unlike S3,
which is the one thing that would otherwise scale with viewer traffic. Should
land at $0/month.

**Exact steps for whoever does the Cloudflare console work, so this doesn't
need re-deriving:**
1. R2 → Create bucket, e.g. `df-overseer-stream`.
2. Bucket → Settings → Public access → enable the `r2.dev` public URL
   (simplest option, no custom domain needed). Copy it
   (`https://pub-<hash>.r2.dev`).
3. R2 → Manage API tokens → Create API token, scoped to **only this
   bucket**, permission **Object Read & Write**. Copy the Access Key ID,
   Secret Access Key, and the Account ID (on the R2 overview page — needed
   for the S3-compatible endpoint, `https://<account-id>.r2.cloudflarestorage.com`).
4. Hand those four values (account ID, access key, secret, bucket name)
   back to a session working this repo.

**What happens once those land:** wire `DF_STREAM_INGEST_URL` in `.env`, and
— this is the real remaining code work, not just config — convert the
capture script's plain `curl -F` multipart POST to an S3-compatible signed
PUT (`aws s3 cp` via `awscli`, apt-installable, is the simplest route; R2
does not accept a plain multipart POST the way a generic upload endpoint
would). Then fill in `IMAGE_BASE` in `willsmith-portfolio`'s
`public/dwarf-fortress/index.html` with the `r2.dev` URL from step 2, commit,
and — separately gated, ask first — push/deploy.

A standalone viewer page already exists at
`willsmith-portfolio/public/dwarf-fortress/index.html` (committed there
locally, **not pushed** — publishing/deploying needs its own go-ahead per
the Rules section, same as this repo), currently showing "not wired up yet"
instead of a broken image.

**Also mid-flight, paused for this: the embark-automation live-testing**
(`research/2026-09-08-embark-automation.md`'s remaining gap — the
title-to-region hop). One `SELECT` was sent to the title screen before the
Xvfb incident interrupted the session; DF's title screen currently sits one
level into the "Start" submenu (confirmed visually via the stream capture
above — "Start new game in existing world" / "Create new world" options
visible), not back at the bare root menu. Harmless (no world loaded), but
worth knowing before the next `simulateInput` call assumes a fresh title
screen. `pre-embark-test-2026-09-08` VM snapshot is still in place as a
rollback point.

**Provisioning work completed 2026-09-08, steps 1 and 2 of the migration path
in `research/2026-09-08-provisioning-recommendation.md` §11.** Both were
unconditional and independent of the still-open build-tool decision, so most
of the practical benefit is now banked whatever happens to that. Layer 1: the
API client mounts a `urllib3` retry policy, POST deliberately excluded so a
timeout can never create two VMs, and 403/500 now say the cluster may be
inquorate. Layer 0: the template bake is deleted, `qemu-guest-agent` moved
into the guest install, and the VM's address is assigned at clone time rather
than discovered, which retired the derived MACs, the override table and the
router's reservation as a source of truth. `provision_vm.py` went 724 to 533
lines. The base image is pinned by dated serial and sha256, verified
host-side by PVE. Automatic upgrades are disabled on the guest.

**What is still open on provisioning:** whether to move image, template and
clone to OpenTofu with `bpg/proxmox`. Deliberately left at `proposed` in the
register, because the one thing nobody has tested is whether a pool-scoped
token can drive it end to end, and that is what spike B settles. Do not treat
it as decided. → `research/2026-09-08-provisioning-recommendation.md` §7.4.

**Two provisioning claims are believed but untested**, and both have a written
falsifying test. An unbaked template needs no seal (clone twice, compare SSH
host key fingerprints and `machine-id`; if they match, the bake comes back).
And `bpg`'s VMID allocation may use a workstation-local sequence file rather
than `/cluster/nextid`, which would reintroduce the second-source-of-truth
problem the 2026-08-27 `next_vmid()` decision exists to prevent.

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

**`.env` credential hygiene, mostly resolved 2026-09-08.** `PVE_PASSWORD` is
**deleted**: no script read it, and the credential it named was rotated out
from under it by the 2026-09-02 OS reinstall, so it was dead twice over. The
live value lives in home-lab's own store, not here. No backup file was written
when removing it, deliberately, since a `.env` sidecar is what caused this
session's near-miss. `PVE_USER` and `PVE_FQDN` were read by no code either
and are now **also deleted**, so `.env` was down to 15 keys, all of them live.
Two more went the same way later the same day: `DF_BUILD_IP` and
`DF_MAC_OVERRIDES` were leftover from decisions that already retired the code
reading them, see `decisions/DECISIONS.md` 2026-09-08 row. `.env` is now 13
keys. `ANTHROPIC_API_KEY` was rotated by the user the same day, 30-day
validity. Do not commit or log it.

**Assume the value that grep printed is exposed.** Deleting `PVE_PASSWORD`
required reading `.env`, which put the old password into a session transcript.
It was already superseded by the reinstall so the blast radius is nil, but the
standing convention in this repo is to treat a credential that reaches a
transcript as exposed rather than to reason about whether it mattered.

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
  once — and `install_df.py stop` does not clean up after `start`.** Confirmed
  the hard way 2026-09-08: `start` launches Xvfb via `setsid nohup ... &`,
  outside systemd entirely, and `stop` only kills `dwarfort`, never that Xvfb.
  A manual Xvfb left running after `stop` becomes an orphan that silently
  poisons every later `systemd --start`: `df-xvfb.service` crash-loops
  forever against a real listener already on `:99` (not just a stale lock —
  `Restart=on-failure` retries a failure it can never fix on its own), and
  `df-fortress.service` cycles as its downstream dependency. Fix if it
  recurs: find and `kill` the orphaned Xvfb process (`ps aux | grep -i xvfb`,
  won't show up correctly in `systemctl status` since it's untracked), then
  `systemctl restart df-xvfb.service df-fortress.service`. A defensive
  `ExecStartPre` lock-file cleanup was added to `XVFB_UNIT` in
  `scripts/install_df.py` the same day, which self-heals the *stale-lock-only*
  version of this failure but not a live orphan. → `decisions/DECISIONS.md`
  2026-09-08 incident row.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it** (`cloud-init
  clean`, remove SSH host keys, truncate `machine-id`). The code that enforced
  this went with the bake on 2026-09-08, because a template that is never
  booted has nothing to seal. If anyone reintroduces a boot-before-convert
  step, the seal has to come back with it.
- **The published hostname is exposed.** The user chose not to rename it.
- **`willsmith.nz` is deliberate**, not a leak: the intended public face.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified.**
- **`hypothesis_id` has no registry.**
- **`openclaw` vs `hermes-agent` still deferred.**
- **Tarball checksums are pinned and enforced** as of 2026-09-08;
  `bzip2 -t` catches truncation, the sha256 catches substitution.
- **PVE's cloud-init takes only the first label of the VM `name` and discards
  everything after the first dot.** This is why VM 103 booted with the plain
  hostname `df-fortress` despite `--name df-fortress.internal`: no `--name`
  spelling can ever deliver a suffixed hostname, which is what makes
  `install_df.py`'s `step_hostname` the only workable route, not merely the
  tidier one. Found by home-lab-43 (a sibling Claude session in
  `home-lab`) reviewing this session's commit; see
  `decisions/DECISIONS.md` 2026-09-08 rows on the `.internal` convention.
- **Hostname convention has one canonical source: home-lab's `CLAUDE.md`,
  Conventions section, "Hostnames: `.internal`, on the OS hostname only."**
  Cite it, do not restate it here or in `DECISIONS.md` — restating it across
  files is exactly what produced two wrong reads of it in one session
  (2026-09-08).

### What a next session should pick up

`ROADMAP.md`'s Now bucket is the canonical list. Token pasted, `status`
verified, template and VM rebuilt, VM 103 named `df-colony-01` in Proxmox
with `df-colony-01.internal` as its OS hostname (`step_hostname` sets this
automatically now), DF/DFHack installed and verified, systemd units enabled
with `onboot=1` — all done. Remaining: generate a world and start DF
(`install_df.py gen`, then `start`) whenever that's wanted, watch for quorum
during writes, rotate the stale `ANTHROPIC_API_KEY`.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.
