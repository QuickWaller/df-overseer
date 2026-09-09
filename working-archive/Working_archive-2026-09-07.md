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

## HANDOVER - 2026-09-08 (evening), archived 2026-09-09

Moved wholesale, not because it was wrong, but because the embark-testing
thread it describes as "genuinely incomplete" was substantially continued
and superseded the same week (2026-09-09) — see `Working.md`'s current
handover for where that thread actually stands now. Kept in full because
the research, the incident writeup, and the live-view build detail below
are all still accurate history, just no longer the current state.

**State at a glance.** VM 103 (`df-colony-01`, `192.168.2.201`) is fully
installed, verified, and running DF under systemd with a generated world
(`POCKET ISLAND`, seed 658085253) — the first thing in this project to run
unattended. **No fort exists yet**; nobody has embarked. On top of that,
this session added two new capabilities: periodic screenshot capture
(verified working) and a start on scripted, blind embark automation
(genuinely unfinished, paused mid-test). Full detail on both is in
`decisions/DECISIONS.md`'s 2026-09-08 rows.

**Commit state.** Many local commits this session, ending at `91419d7`.
Working tree clean. Not pushed anywhere, in either `df-automation` or
`willsmith-portfolio` — publishing needs its own go-ahead per the Rules
section, every time.

**Embark-automation: researched, live-testing genuinely incomplete.**
`research/2026-09-08-embark-automation.md` nails the screen sequence,
keybindings for the confirmed part of the flow, and the success check, all
from primary sources (real shipped DFHack scripts), not guesses. The one
real gap — how "Start" on the title screen reaches a fresh embark, as
opposed to continuing/reclaiming — has no installed script to crib from and
needs live, polled testing. That testing started (`pre-embark-test-2026-09-08`
VM snapshot taken first) and got one `SELECT` sent to the title screen
before an unrelated infra incident interrupted it. DF's title screen was
believed at the time to sit "one level into the Start submenu" — this was
later found stale (2026-09-09): the incident's cascading service restart
had actually relaunched `dwarfort` from scratch, resetting the title screen
entirely. See `Working.md`'s current handover for the corrected state and
everything that followed from it.

**Incident: `df-xvfb.service` crash-looped for ~14 minutes (47+ restarts)
against its own stale lock file, cascading into `df-fortress.service`; root
cause was an orphaned manual Xvfb process, not the embark testing that
surfaced it.** Discovered mid-way through live-testing the embark-automation
sequence, when a `gui.simulateInput` call returned "Could not connect to
localhost:5000." The timeline clears the test of blame: `journalctl` showed
the crash loop started at 04:18:42, before the first simulated key of this
session was sent. Root cause, found by checking for orphaned processes:
`install_df.py start` (the manual path, used once at the very start of this
session before switching to systemd) launches Xvfb via `setsid nohup ... &`,
fully outside systemd's process tree, and `install_df.py stop` only kills
`dwarfort`, never Xvfb. That manual Xvfb (started ~03:56) was never cleaned
up, so every later `df-xvfb.service` start attempt failed against a real
listener already on `:99` (not a merely-stale lock file at first read —
`/tmp/.X99-lock` and the socket were real, but the process behind them was
orphaned and invisible to `systemctl status`). `Restart=on-failure` on the
xvfb unit then retried forever against a failure it could never fix on its
own, and `df-fortress.service` cycled as a downstream dependency of a unit
that never came up clean. Fixed two ways: killed the orphan (`kill -9`) to
clear the immediate incident, verified stable and `install_df.py verify`
all-green afterward; and added a defensive
`ExecStartPre=-/bin/rm -f /tmp/.X%(displaynum)s-lock /tmp/.X11-unix/X%(displaynum)s`
to `XVFB_UNIT` in `scripts/install_df.py` so a *stale-lock-only* version of
this failure (no live orphan, just leftover files from an unclean death)
self-heals rather than crash-looping. No fort existed yet and no game state
was at risk at any point; the incident was entirely infra-layer.
`pre-embark-test-2026-09-08` VM snapshot (taken before this incident) was
not needed and is still in place.

**Live-view screenshot capture built and verified on VM 103**, ingest
paused on the user. `research/2026-09-08-live-viewing.md` recommends
periodic screenshot push over VNC or video; `install_df.py stream`
implements the capture half, verified for real by pulling `latest.png` off
the VM and viewing it (genuine DF title screen, correct size). Two real
bugs found and fixed in the same pass, both now baked into the script:
ImageMagick's `import` silently writing PostScript instead of PNG for a
`.tmp`-extension temp file (fixed with an explicit `png:` prefix), and a
root-owned capture directory against a `User=df` service (fixed by chowning
in the same setup script). Blocked on the ingest side: willsmith.nz is a
static GitHub Pages site with no backend, so screenshots need somewhere
else to land. Cost-checked (should be $0/month) and the exact Cloudflare R2
setup steps are recorded in `decisions/DECISIONS.md`'s 2026-09-08 row, but
the user couldn't do the console work at the time, so this was paused, not
stuck. A standalone viewer page was added to `willsmith-portfolio` at
`public/dwarf-fortress/index.html` (committed there locally, not pushed),
honestly showing "not wired up yet" rather than a broken image.

**Cross-session: home-lab-43's `CLAUDE.md` addition was accepted and
committed.** Verified against home-lab's own 2026-08-27 decision before
accepting — see `decisions/DECISIONS.md`. It declares home-lab as source of
truth for estate IDs and sets an obligation: any future guest
create/delete/resize/re-address here must update `home-lab/inventory/` the
same turn. Nothing in that session triggered the obligation.

---

# 2026-09-09 handover, moved wholesale on 2026-09-09

Moved out of `Working.md` because the section exceeded the ~400-line archive
threshold, not because anything below is wrong or superseded — this is the
full, blow-by-blow record of a very long, very productive session. The fresh
`Working.md` handover written the same day summarizes the durable outcomes;
this is the detail behind them, kept for a future session that needs to
understand exactly how something was found, not just that it was.

## HANDOVER - 2026-09-09

**State at a glance.** VM 103 (`df-colony-01`, `192.168.2.201`) is still
fully installed, verified, running DF under systemd, world generated
(`POCKET ISLAND`/`Thadar Thran, "The Planets of Dawning"`, seed 658085253).
**Still no fort**, but this session drove real, live progress through the
actual embark-flow UI for the first time — title screen → world/region list
→ game-type picker → world map → DF's native Site Finder panel — before
getting stuck on one specific button. Everything below is live-tested
against VM 103 this session, not research or inference. The 2026-09-08
evening handover (VM rebuild, worldgen, the Xvfb incident, live-view
capture build) is archived wholesale —
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
— since its embark-testing thread, the part that was still open, is what
this handover supersedes.

**The real headline: the title-screen mouse-only design question is
resolved, and it didn't need an exception.** Full writeup →
`decisions/DECISIONS.md` 2026-09-09 row. Short version: the title screen's
main menu turned out to be click-only (three different keys tested live,
zero effect, confirmed the process was still actively rendering so it
wasn't a stalled game loop). Rather than hardcode a pixel coordinate read
off a screenshot — a real exception to `docs/PURPOSE.md` commitment #1 — a
four-agent (Opus-orchestrated, Sonnet-executed) research pass
(`research/2026-09-09-title-screen-bootstrap-exception.md`) converged on
"find a way not to need the exception," and one existed: `dfhack.screen.readTile`
returns real character-grid data for every screen tested tonight (not
`nil`-for-TrueType), so `gui/kitchen-info.lua`'s shipped label-locator
technique applies everywhere — scan the buffer for a button's literal text,
click the coordinate *that* scan produces, never one read off an image. New
CLI tool built for this: `install_df.py lua "<code>"` (`scripts/install_df.py`
`cmd_lua`), runs one dfhack-run lua expression and prints full multi-line
output — the existing `dfhack_lua_sh()` helper is `tail -n1`-only, built for
single-value verify checks, not this.

**Live-confirmed screen sequence, all via buffer-scan-and-click, zero images
used for any decision:**
1. Title screen (`viewscreen_titlest`, `mode=MAIN_MENU`) → scanned row 33,
   found "Start new game in existing world" at columns 63-94 (center x=78)
   → clicked → `mode` flipped to `CONTINUE_INACTIVE`, landed on the
   world/region list.
2. World/region list (still `viewscreen_titlest`) → `SELECT` key tested,
   **no effect** (also mouse-only) → scanned row 33 again, found
   "World: Thadar Thran..." at column 41 → clicked (x=55,y=33) → top-of-stack
   flipped to `viewscreen_adopt_regionst`.
3. `viewscreen_adopt_regionst` turned out to be an interactive "Select a
   game type to begin!" screen (Fortress/Adventurer/Legends/Back), not a
   pure loading marker as the original research guessed — confirmed
   `df.game_type.DWARF_MAIN == 0`. Scanned for "Fortress" (row 21, columns
   75-82) → clicked → landed on `viewscreen_choose_start_sitest`,
   `isWorldLoaded()` flipped to `true`.
4. `choose_start_sitest` opened with `choosing_embark=false`,
   `zoomed_in=false` — an earlier sub-stage than
   `gui/embark-anywhere.lua`'s field-write recipe assumes (that recipe
   still applies once `choosing_embark` is true; we're not there yet). Two
   unexpected dialogs appeared in sequence — "Quick start and short
   tutorial?" (clicked "Skip tutorial", row 21) and "On your own!" (a hazard
   warning, clicked "Okay", row 23) — both found and dismissed the same
   buffer-scan way. Landed on the actual world-map overview.
5. Bottom of the world-map screen has three real buttons, found by scanning
   row 57: "Find embark location", "Reclaim/unretire", "Choose origin
   civilization". Clicked "Find embark location" (columns 91-110, center
   x=100) → `doing_site_finder` flipped to `true` → DF's native Site Finder
   panel opened: structured parameters (X/Y Dimension, Savagery, Spirit,
   Elevation, Temperature, Rain, Drainage, Flux Stone Layer, Aquifer
   Light/Heavy, all `+`/`-` adjustable, most defaulting to `N/A` = no
   constraint) plus a `find_results` enum (`None`/`NoResult`/`Partial`/
   `Suitable`) to poll for the outcome. This is exactly the
   pure-structured-criteria path this project wants for site selection —
   confirmed a real, working DFHack-exposed feature, not assumed.

**One boundary-case incident worth recording plainly, not burying**: a
blanket full-screen buffer scan (done to hunt for UI button labels, not
map data) incidentally displayed actual world-map terrain glyphs
(`n`/`V`/`^` forest/mountain symbols) in this session's own tool output,
and — at the user's repeated, explicit request, for the user's own
curiosity, not fed into any reasoning about where to click — real
screenshots of that same world map were also shown directly to the user
this session (`/tmp/debug-shot2.png` through `6.png`, local scratchpad
only, never committed). This is the literal thing commitment #1 names
("not ASCII, not a tile grid, not a screenshot"), so it's recorded here
rather than glossed over. No click or embark decision this session was
ever based on interpreting that terrain — every click coordinate came from
a text-label scan, scoped away from the map viewport once the risk was
noticed. Going forward: scope buffer scans to specific rows/label text,
never a blanket dump, on any screen with an actual map viewport.

**The user separately raised a broader point worth its own follow-up, not
resolved tonight**: whether design commitment #1, as an absolute
("not even a screenshot," no scope carve-outs), is stated more broadly than
the evidence that produced it (LessWrong's DF/Angband testing, BALROG) —
both of which tested *dense, continuously-updating game-world content read
over many turns*, not a static UI menu or a one-off human debugging glance.
The core of the rule (no rendered map in the model's ongoing spatial
reasoning) looks solid and shouldn't be relitigated; the absolute wording
may be broader than that core justifies. **Queued for a `decisions/DECISIONS.md`
entry, deliberately not written yet** — the user wants to come back to it
after other things, not decide it under time pressure mid-session. Still
open as of the end of this session too — see the fresh `Working.md`
handover.

### Durable traps confirmed this session (folded into the fresh handover's list too)

- **`gui.simulateInput`'s generic keys (`SELECT`, `MENU_CONFIRM`,
  `STANDARDSCROLL_*`) do not work on DF v50+'s native button-style menus** —
  confirmed dead on both the title screen and the world/region list, both
  genuinely mouse-only. The working pattern, confirmed live and repeatable:
  scan `dfhack.screen.readTile` for the button's literal text (letters only,
  `ch` 65-122, via `pairs`/`string.find` on a reconstructed row), compute
  the coordinate from that scan, then `df.global.gps.mouse_x/mouse_y = x,y`
  plus `gui.simulateInput(scr, '_MOUSE_L')` in one call. Worked identically
  across five different buttons across three different screens tonight.
- **The same dead-keyboard pattern extends to WASD map-panning on
  `choose_start_sitest`**, confirmed 2026-09-09 with pixel-identical
  before/after screenshots (not just an unchanged field, which could have
  been the wrong one to watch): `CURSOR_RIGHT`, raw `STRING_A100` ('d'),
  and `STANDARDSCROLL_RIGHT` all had zero visible effect. Mouse clicks work
  fine on the same screen. Likely cause: WASD panning here is raw
  SDL-keyboard-state polling in native code, never reaching the
  interface-key queue `gui.simulateInput` operates at. Not a blocker in
  practice — a single zoom-in click was enough map view to make Begin work
  without needing to pan further.
- **`load-save.lua`'s `sel_menu_line`-on-`viewscreen_titlest` approach does
  not apply to this build.** The script is tagged `unavailable` in
  `memory/dfhack-environment.md`, and the field genuinely does not exist
  here (confirmed by a live error). Don't re-attempt it.

### The full live-viewing build, blow by blow

**Live human viewing: done for the LAN case, via `x11vnc` + noVNC.**
`install_df.py vnc` installs and starts `x11vnc` on VM 103's Xvfb
display as `df-vnc.service` — LAN-only (VM 103 has no public IP
regardless), `-viewonly` (no keyboard/mouse forwarded), password-gated
via `-rfbauth` (password generated with `secrets`, written to gitignored
`.env` as `DF_VNC_PASSWORD`, never printed to the terminal). `install_df.py
webvnc` then bridges it to a plain browser tab via `websockify` +
noVNC's static JS client (`df-webvnc.service`, port 6080) — no VNC
client install needed, same password prompt inside the page. Verified
2026-09-09: `df-vnc.service` and `df-webvnc.service` both `active`, a raw
TCP connect to `192.168.2.201:5900` returned a real RFB handshake, and
`http://192.168.2.201:6080/vnc.html` returns HTTP 200.
→ `decisions/DECISIONS.md` 2026-09-09 rows,
`research/2026-09-08-live-viewing.md` §3b (the design this picked up).

**Explicitly NOT the mechanism for the public willsmith.nz stream, per a
mid-session user note that this will eventually go public.** This VNC/
noVNC path is a persistent, inbound-facing connection — fine for LAN
since VM 103 has no public IP anyway, but the wrong shape for the public
internet: making it internet-reachable (e.g. Tailscale Funnel) would
turn VM 103 into a public-facing endpoint indefinitely, which
`research/2026-09-08-live-viewing.md` §4 already flags as a real,
separate decision, not a small extension of "it already works over
noVNC." **The public leg stays the existing outbound screenshot-push
design** (`install_df.py stream`, ROADMAP.md's Next-bucket R2 item) —
don't conflate the two when picking this back up.

**Open follow-up, deliberately deferred, not forgotten:** the user wants
keyboard/mouse forwarding added later (drop `-viewonly` from
`X11VNC_UNIT` in `scripts/install_df.py` once wanted — a small change,
not a redesign, but worth its own explicit go-ahead given it turns a
passive viewer into an input surface on an already network-boundary-less
VM).

**The relay VM thread, in order:** the user confirmed they want the
public leg to be genuinely live video, not screenshot polling, via a
small public-facing **relay VM** that VM 103 connects *out* to (reverse
VNC), so VM 103 itself never accepts an inbound internet connection —
offered the simpler "point `cmd_stream` at a self-hosted relay instead of
R2" option first, user explicitly chose the harder live-video path
instead. Research (`research/2026-09-09-reverse-vnc-relay.md`, read in
full, not just trusted from the subagent's summary) recommended a
**reverse SSH tunnel**, not a VNC-repeater chain — the repeater approach
(`x11vnc -connect repeater=...`) is real and documented, but the joint
that would make it work end-to-end (websockify/noVNC against a
16-years-untouched Perl repeater script) has no confirmed working
reference anywhere; one real bug report on it ended unresolved. The SSH
tunnel needs no new protocol: VM 103 opens `ssh -R
127.0.0.1:5900:127.0.0.1:5900` to the relay, and the relay's
`websockify`/noVNC point at `localhost:5900` — literally the same command
`cmd_webvnc` already runs today, just against a tunneled port.

**Architecture then evolved further.** The user proposed hosting the
relay inside home-lab's own Proxmox pool (rather than an external VPS)
and fronting it with Cloudflare Tunnel (`cloudflared`, outbound-only, no
public IP or open inbound port on the relay at all) instead of the
research report's draft MVP (a standalone VPS with nginx/certbot/ufw).
That's a real improvement — removes almost all of the report's §6
public-facing-hardening burden, since the relay is never directly
internet-reachable either. Then the user asked whether a shared Caddy
ingress (fronting multiple future public services, not just this one
relay) made sense. **That's estate-wide infrastructure, correctly
identified as home-lab's call, not df-overseer's.** Raised with the live
`home-lab-43` session 2026-09-09 (full context, both shapes named,
explicit that df-overseer isn't deciding this unilaterally).
**`home-lab-43` replied same session: single-purpose relay, not shared
ingress** — home-lab's existing pattern is one Cloudflare Tunnel per app,
embedded in that app's own stack; a shared relay would be new estate-wide
attack surface built ahead of any second real consumer needing it.
Recorded in home-lab's own `decisions/DECISIONS.md` 2026-09-09.

**Relay VM built and SSH-verified.** User chose Alpine for the relay OS
(smaller than Ubuntu, and ruled out LXC for this specific box since it's
slated to eventually be the estate's one internet-facing thing — LXC's
weaker, shared-kernel isolation is the wrong tradeoff there). `home-lab-43`
allocated `192.168.2.202` (`df-colony-relay-01`) same session. **Alpine
hit a real, now-understood blocker**: its `cloud-init` package locks the
account password by default, and Alpine's `openssh` (built without PAM)
refuses pubkey SSH logins on a *locked* account regardless of a
correctly-installed key — confirmed against Alpine's own `README.Alpine`
for the `cloud-init` package (a cheap Sonnet research pass found this,
not guesswork). Network config from the same NoCloud datasource applied
fine; only the user/ssh-key stage was affected — a specific, narrow bug,
not a general cloud-init failure. The clean fixes (`openssh-server-pam` +
`UsePAM yes`, or `lock_passwd: false`) both need a custom cloud-init
snippet, and Proxmox's API has no endpoint to upload snippet content
(confirmed via the Proxmox forums) — the standard workaround is placing
the file on the Proxmox host's filesystem via SSH, which is exactly the
access no agent has here. **Pivoted to Debian 12 (bookworm genericcloud)**
instead of spending more on Alpine — same apt/dpkg ecosystem as
everything else in this project, still much lighter than Ubuntu, and its
cloud-init unlocks the account normally (cross-checked: no equivalent bug
reported anywhere for Debian/Ubuntu, whose `openssh-server` builds with
PAM). Verified end to end: SSH as the `relay` user works cleanly against
`192.168.2.202`.

New script: `scripts/provision_relay.py` — mirrors `provision_vm.py`'s
fetch-image/build-template/clone/start shape but reuses its generic,
non-DF-specific helpers (`read_pubkey`, `wait_for_status`, `resize_disk`,
`destroy_failed_build`) rather than duplicating them. Its own `.env`
prefix (`RELAY_*`), deliberately separate from VM 103's `DF_*` vars, so
rebuilding the relay can never collide with VM 103's config. State:
`RELAY_VM_IP=192.168.2.202/24`, `RELAY_TEMPLATE_VMID=104`
(`relay-debian-12-20260907-2594-template`, never booted, same
never-boot-a-template discipline as the Ubuntu template),
`RELAY_VMID=105` (`df-colony-relay-01`, running, on `srv-01`), 512MB
memory / 256MB balloon / 1 core, 4G disk. `home-lab-43` notified with
vmid/host/IP confirmation, wrote its own guest inventory entry from that,
then caught that the OS hostname (`.internal` convention, applies to any
guest built after 2026-09-06) hadn't been set — fixed by reusing
`install_df.py`'s existing `step_hostname()` rather than writing a new
copy; verified from a fresh SSH connection that `hostnamectl --static`
reports `df-colony-relay-01.internal` and `/etc/hosts` matches.

**websockify/novnc installed on the relay** (plain `apt-get install
websockify novnc`, Debian package versions 0.10.0+dfsg1-4+b1 and
1:1.3.0-1). Confirmed live: `/usr/bin/websockify` present,
`/usr/share/novnc/` populated including `vnc.html` — same layout Ubuntu's
`cmd_webvnc` uses on VM 103.

**Reverse SSH tunnel + relay-side noVNC built and verified end to end —
the LAN live-viewing chain complete.** New `install_df.py vnc-tunnel`
subcommand: generates a dedicated ed25519 keypair on VM 103 itself
(private key never leaves it), installs only the public half on the
relay's `authorized_keys` restricted with
`permitopen="127.0.0.1:5900",no-pty,no-agent-forwarding,no-X11-forwarding`,
and runs `ssh -N -R 127.0.0.1:5900:127.0.0.1:5900` from VM 103 to the
relay as `df-vnc-tunnel.service`. Verified independently from the relay's
own loopback (not VM 103) — connecting to `127.0.0.1:5900` on the relay
returned a real RFB handshake, proving the tunnel genuinely bridges to VM
103's `x11vnc`. New `provision_relay.py webvnc` subcommand installs
`websockify`/noVNC on the relay pointed at that tunneled port — reuses
`install_df.py`'s `NOVNC_UNIT` template, which had to be parameterized
first (`%(depends)s` for the `[Unit]` dependency block): the original
hardcoded `Requires=df-vnc.service`, a unit that exists on VM 103 but not
on the relay, and `Requires=` naming a nonexistent unit would have made
the relay's copy fail to start, not just warn — caught before running it
for real. Verified: `df-webvnc.service` active on the relay,
`http://192.168.2.202:6080/vnc.html` returns HTTP 200, and the user
confirmed the actual in-browser WebSocket→RFB round trip connects and
shows VM 103's display live.

**Question raised and answered this session, worth keeping**: the
reverse SSH tunnel (VM 103 → relay) and Cloudflare Tunnel (relay →
public, still deferred) are not alternatives — they're two different
legs of the same chain and both are meant to be permanent, not one
superseding the other. The SSH tunnel's safety rests on the
`permitopen`-restricted key design, not on "it's LAN-only so it doesn't
matter" — a fully compromised copy of that key should only ever be able
to reach one local port on the relay, nothing else.

**Incident, fixed same session:** the first `DF_VNC_PASSWORD` write used
a bare `open(path, "a").write(...)`, which landed directly on the end of
the `ANTHROPIC_API_KEY` line because `.env` had no trailing newline —
silently merging both values into one unparseable line. Caught by the
user, fixed by splitting the line back apart and verified clean via
`pve.load_env()` (not just eyeballing). `install_df.py` now has an
`_append_env_var()` helper that always checks for and inserts a leading
newline first; the old unguarded pattern should not be copied elsewhere.

### The tileset investigation, blow by blow

**Cosmetic tileset swap applied, purely because it was now visible
through the browser**: `INIT_SETTINGS` in `scripts/install_df.py` gained
`FONT`/`FULLFONT` → `curses_square_16x16.png` and `USE_CLASSIC_ASCII` →
`NO`. Checked live first: this exact DF Classic build (0.53.16) has no
`raw/graphics` folder at all.

**The tileset swap broke world-map rendering entirely, not just
cosmetically.** Re-navigating the embark flow with the new font live, the
user spotted (via the browser VNC view) that the Site Finder's map
viewport was solid black — correctly suspected it could be either a VNC-
chain bug or the tileset change, and asked to compare. Checked three
independent ways: (1) DFHack's own `dfhack.screen.readTile` buffer for
the map viewport read back entirely blank (`ch=0`/space, 4641/4641
tiles) — aggregate counts only, not the actual terrain content, to stay
inside design commitment #1 even for this diagnostic; (2) a screenshot
taken directly off VM 103's Xvfb display via `import` (bypassing the
VNC/relay chain completely) showed the same solid black, ruling out a
VNC-side bug; (3) reverting just `FONT`/`FULLFONT`/`USE_CLASSIC_ASCII` on
the live VM and restarting DF immediately restored full colored terrain
on both the world overview and the Site Finder screen, confirmed by two
more direct screenshots. **The user explicitly authorized looking at
rendered screenshots for this debugging/design purpose** — a live
instance of the open question about whether design commitment #1's
absolute wording is broader than its evidence base; a one-off debugging
comparison, not a change to how the agent will perceive the game during
actual play.

**Isolated the two settings from each other**: applied
`FONT`/`FULLFONT:curses_square_16x16.png` alone, left
`USE_CLASSIC_ASCII:YES` untouched, restarted DF, re-navigated to both the
world overview and the Site Finder screen. Both rendered full colored
terrain correctly, confirmed by direct screenshots — the nicer
square-tile font with a genuinely working map. `USE_CLASSIC_ASCII:NO`
looked like the actual culprit at this point.

**Then the user pushed back, correctly**: they recalled the brief window
with `USE_CLASSIC_ASCII:NO` active looking genuinely good (not just
"different"), and asked whether we'd actually used the built-in modern
graphics before concluding the map couldn't render. Direct test: flipped
`USE_CLASSIC_ASCII:NO` back on and screenshotted the **title screen**
(no map dependency) — the result was a completely different, modern UI:
full-width colored buttons, smooth anti-aliased text, nothing like the
curses-bitmap look. Confirmed real via a wiki search
("dwarffortresswiki.org/index.php/Init.txt/raw/classic"): when
`USE_CLASSIC_ASCII:NO`, DF expects the FONT/FULLFONT tileset image to be
exactly 128×192 pixels (8×12 px tiles) to render "custom tiles" properly.
Checked actual pixel dimensions of every bundled font via `identify`:
`curses_640x300.png` (the **original default**, despite its misleading
name) is exactly 128×192 — matching the spec — while
`curses_square_16x16.png` is 256×256 and `curses_800x600.png` is 160×192,
neither matching.

**Tested the theory: default font + `USE_CLASSIC_ASCII:NO`.** Restarted
DF, re-navigated to the world overview — the menus/info panel rendered
beautifully (confirmed, user agreed: "these graphics are great! so far"),
but **the map viewport was still completely empty** — not even a black
box, nothing at all, confirmed via the same `dfhack.screen.readTile`
buffer-stats technique (0/4641 non-blank tiles again). Tried a second,
very differently-shaped font (256×256 square) and got the identical
blank-map result. Two different font files, two different aspect ratios,
same failure — this rules out "wrong tileset dimensions" as the map's
specific problem, even though tileset dimensions clearly do matter for
menu/UI rendering. Current best-supported conclusion, not yet proven to
the same standard as the dimension finding: the world/embark map is very
likely rendered through a categorically different system than menu
text — real per-tile terrain sprites (`raw/graphics` tile-page +
creature/inorganic graphics tags) — and this build's confirmed-absent
`raw/graphics` folder means that data simply isn't there, regardless of
which font file is loaded. Not independently confirmed against DF's
actual source or a definitive primary source — this is where the
session ended, and it's the exact question handed to next session's
research task (see the fresh `Working.md` handover).

**The user's own words on this, worth keeping verbatim in spirit**: they
don't want the ASCII look, they suspect this is a fixable bug rather than
a fundamental limitation, and they explicitly do NOT want to reach for a
third-party community graphics pack as the first move — they want the
*official* built-in modern graphics (the ones that shipped with the Steam
version) working in this Classic build if at all possible, since a
custom pack is the bigger, riskier fallback, not the first thing to try.

### The Site Finder "Begin" investigation, blow by blow

**Site Finder investigation resumed with a confirmed-good map render.**
Re-navigated to the Site Finder panel (X Dimension=4, Y Dimension=4,
defaults, zoomed in on the map) with the reverted, working font —
`find_results` still `-1` at this point, matching the original stuck
state. Also found, via the screen's own field list
(`dfhack.gui.getCurViewscreen()`, enumerated live rather than guessed):
`find_results`, `find_select`, `find_param` (an `int32_t[]`, presumably
one slot per parameter row), `find_missed_param`, `find_param_list`
(`vector<int32_t>[24]`).

**SOLVED: why the Site Finder's "Begin" button no-ops.** Root cause,
empirically proven, not just theorized: **Begin requires at least one
non-N/A search criterion to be set; with every field left at N/A (the
default, and the exact state last session got stuck in), Begin silently
does nothing at all — no error, no state change, `find_results` stays
`-1` forever.** Proven by direct A/B test: clicking Begin with all-N/A
criteria left `find_results` at `-1`, exactly as before; setting Savagery
to "Untamed wilds" via its `+` button (same proven buffer-scan-and-click
technique) and clicking Begin again immediately flipped `find_results` to
`2`, and a screenshot confirmed **"Match found!"** with a highlighted
site on the map and the bottom buttons changing to "Clear find results" —
a real, complete search result, not a partial or ambiguous one. Exact
enum meaning of `2` not independently confirmed against a structures
definition, but the screenshot's own "Match found!" text makes the
practical meaning unambiguous regardless.

**A real, separate finding along the way**: keyboard simulation
(`gui.simulateInput` with `CURSOR_RIGHT`, raw `STRING_A100` for 'd', and
`STANDARDSCROLL_RIGHT`) has **zero effect** on this screen's WASD
map-panning — confirmed with pixel-identical before/after screenshots,
not just an unchanged field (which could have been the wrong field to
watch). Mouse clicks work fine on the same screen (the zoom-in click, the
`+` button). Best-supported explanation: WASD panning here is very likely
implemented via raw SDL keyboard-state polling in native code, bypassing
the bindable interface-key queue that `gui.simulateInput` operates at
entirely. Worked around by not needing WASD at all: the map was already
usably zoomed in from a single click.

**What a next session should pick up from this thread**: nobody has
actually embarked yet — "Match found!" is a found *candidate site*, not a
founded fortress. The next concrete step is clicking through to actually
accept/embark at the found site (likely an "Embark" button once a match
is highlighted, unexplored this session) — the real first-fort milestone
this whole project has been building toward.

### Other open items carried from before this session, still open after it

- **Design commitment #1's absolute wording vs. its actual evidence base
  — queued for a `decisions/DECISIONS.md` entry, deliberately not written
  yet.** The core (no rendered map in the model's ongoing spatial
  reasoning) is well-evidenced by `research/2026-08-25-spatial-perception.md`
  and shouldn't be relitigated; the literal absolute wording ("not even a
  screenshot," no carve-outs) was generalized from evidence that only
  tested dense, continuously-updating game-world content over many turns,
  not a static UI menu or a one-off human debugging glance. This session
  put a live instance of the distinction into practice (see the tileset
  investigation above) without writing the formal entry — still open.
- **Live-view ingest, still waiting on the user.** Once Cloudflare R2
  credentials (Account ID, Access Key ID, Secret Access Key, bucket name)
  arrive: wire `DF_STREAM_INGEST_URL` in `.env`, convert the capture
  script's `curl -F` to an S3-compatible signed PUT (R2 doesn't accept
  plain multipart POST — `aws s3 cp` via `awscli` is the simplest route),
  fill in `IMAGE_BASE` in
  `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, and ask
  before pushing/deploying either repo.
