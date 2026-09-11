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

---

## HANDOVER - 2026-09-09 (end of session)

The full blow-by-blow of this session (a very long, very productive one) is
archived wholesale, not summarized away —
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md),
appended 2026-09-09. Read it if you need to know exactly *how* something
below was found. This handover is the tight, current-state version: what's
true right now, and the one concrete task queued next.

### State at a glance

- **VM 103** (`df-colony-01.internal`, `192.168.2.201`): running DF under
  systemd, real Steam-graphics rendering confirmed working (see below),
  a fresh graphics-enabled world (`region2`) generated with a candidate
  embark site found on it, **still no fort**. Nobody has clicked through
  to actually embark yet — that's the real next DF-side milestone.
- **Relay VM** (`df-colony-relay-01.internal`, vmid 105, `192.168.2.202`,
  Debian 12 bookworm, home-lab's Proxmox pool, `srv-01`): built this
  session, LAN-only, purpose is bridging VM 103's VNC feed toward a future
  public leg.
- **Live LAN viewing is fully built and user-confirmed working end to
  end**: VM 103's `x11vnc` (`df-vnc.service`) → reverse SSH tunnel
  (`df-vnc-tunnel.service`, dedicated `permitopen`-restricted key, VM 103
  dials out, never accepts inbound) → relay's `websockify`/noVNC
  (`df-webvnc.service`) → `http://192.168.2.202:6080/vnc.html`. The user
  opened that URL in a real browser and confirmed it connects and shows
  VM 103's display live.
- **Public leg (Cloudflare Tunnel on the relay) is the one piece not
  built**, deliberately deferred — get LAN infra solid first, agreed
  explicitly, not forgotten.
- **DF's look is now the real, official Steam-style modern graphics,
  confirmed genuinely rendering** — resolved 2026-09-09, see below. Not
  ASCII, not the plain bundled font: actual per-tile sprite art
  transplanted from the user's own purchased Steam copy.

### RESOLVED 2026-09-09: built-in modern (Steam-style) graphics are working on VM 103

**Bottom line**: `research/2026-09-09-df-modern-graphics.md` confirmed
there is no *free* official path — Premium's tileset is proprietary
Kitfox-commissioned art bundled only in the paid build, and free Classic's
`data/vanilla/vanilla_*_graphics`/`vanilla_world_map` module folders ship
as empty `info.txt`-only stubs by design. What actually unblocked this:
the user already owns a legitimate Steam copy locally (confirmed install
at `C:\Program Files (x86)\Steam\steamapps\common\Dwarf Fortress`, version
**53.15**, one patch behind VM 103's pinned 53.16). `install_df.py` gained
a new `graphics` subcommand (`--source PATH`, or `DF_GRAPHICS_SOURCE` in
`.env`) that tars the eight real module folders from that local install,
`scp`s the tarball straight to VM 103, and extracts it over the existing
empty stubs — the asset bytes never touch this repo's git tree, matching
the public-repo/no-committed-binaries convention. Full reasoning,
legitimacy basis, and the version-gap analysis →
`decisions/DECISIONS.md` 2026-09-09 (the graphics-transplant row).

**No mod-selection screen automation was needed.** The task's anticipated
hard problem — DF v50+ graphics modules needing to be opted into a
world's mod list via a UI mod-selection screen before worldgen — turned
out not to apply: VM 103's own `gen_modlist.txt` already listed all eight
`vanilla_*` modules as active with no mod-selection UI ever touched,
confirming they're baked into every worldgen unconditionally, not opt-in
like a Workshop mod. The actual work was pure file-placement (populate
the stub folders DF already reads at render time) plus
`USE_CLASSIC_ASCII:NO` (both already in `scripts/install_df.py`'s
`INIT_SETTINGS`/`GRAPHICS_MODULES`).

**Verified genuinely rendering, not just a setting flipped**: real
screenshots (saved locally at `C:\Users\wills\df-graphics-screenshots\`,
11 files, sequentially numbered) show actual pixel-art sprites — trees,
wave-textured water, mountains, a volcano, sand — on three separate
screens: the world overview, the unzoomed Site Finder panel, and the
zoomed embark-placement map. One honest caveat: `dfhack.screen.readTile`'s
aggregate non-blank-tile count (the exact diagnostic that proved the
original bug) reads back 0 again over the equivalent clean map-only
region in this now-confirmed-working case — that screen's terrain is
drawn via a texture-blit path invisible to `dfhack.screen`'s
character-buffer instrumentation, so that specific check is not a valid
signal either way for this widget; the screenshot is the load-bearing
evidence, not the buffer read.

**This task had been started and interrupted mid-session by an earlier
agent with no final report.** Rather than assume its stopping point, this
session opened by directly inspecting VM 103 (process list, current
viewscreen, `data/vanilla/` module file counts, `prefs/init.txt`) before
doing anything further. That inspection found the interrupted agent had
already correctly finished the graphics transplant, the
`USE_CLASSIC_ASCII:NO` flip, and a full fresh worldgen (`region2`,
discarding the old ASCII-era candidate site per the user's prior
approval) — DF was sitting idle at the title screen, nothing stuck or
mid-write. This session completed the remaining unverified half: the
screenshot confirmation and a fresh Site Finder pass on `region2`.

**Two live follow-up questions from the user (watching via the VNC feed)
were investigated directly, both came back negative**: (1) whether DF's
v50+ button-style menus expose per-screen keyboard hotkeys — checked via
screenshots and `pen.fg` colour dumps on the Site Finder panel, world-map
buttons, and the title menu; no bracketed/underlined/distinctly-coloured
hotkey letter exists anywhere, confirmed via uniform `fg` values, not
just a glance. (2) whether a global keyboard-vs-mouse interface-mode
toggle exists — checked Settings' Video/Game/Keybindings tabs in full
(including scrolling Game to its actual end) and `prefs/init.txt`/
`data/init/d_init_default.txt`; `Keybindings` is a physical-key
**rebinding** screen for named actions already known dead against these
widgets, not a mode switch, and no such toggle exists anywhere. The
existing buffer-scan-and-click mouse automation remains the correct
mechanism. For the Site Finder's search criteria specifically, a direct
struct-field write (`scr.find_param[2] = 0`, the `gui/embark-anywhere.lua`
idiom) proved more robust than hunting for a `+`/`-` button's coordinates,
which don't render as static glyphs on that particular panel.

**Current state**: `region2` (the graphics-enabled world) has a confirmed
candidate embark site (`find_results == 2`, "Match found!", Savagery set
to Calm) — not yet embarked, per instruction. `region1` (the old
ASCII-era world/candidate) still exists on disk, superseded, not deleted.
DF is back under systemd management (`df-fortress.service`/
`df-xvfb.service`, both active) after this session's manual
stop/start/reset cycles — `verify` passes clean.

### Durable traps, still true

- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's `memory/tailscale-architecture.md` assigns `df-fortress`/
  `df-colony-01` to `tag:ai-sandbox` — "unattended, possibly LLM-driven,
  lowest trust that isn't internet-facing" — but `runbooks/tailscale-topology.md`
  Phase 5 (the actual hard gate) is still unchecked. **Not this repo's to
  fix** — host-level Tailscale/ACL work, forbidden to any agent by
  home-lab's own rule.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL.
- **The manual (`start`/`stop`) and systemd-managed paths must not run at
  once** — `install_df.py stop` does not clean up a manually-started
  Xvfb. See archive for the full incident/fix.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it.**
- **The published hostname is exposed.** The user chose not to rename it.
- **`willsmith.nz` is deliberate**, not a leak: the intended public face.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified.**
- **`hypothesis_id` has no registry.**
- **`openclaw` vs `hermes-agent` still deferred.**
- **Tarball checksums are pinned and enforced.**
- **PVE's cloud-init takes only the first label of the VM `name`** —
  `install_df.py`'s `step_hostname` (reused for the relay too) is the only
  workable route to a suffixed guest hostname.
- **Hostname convention has one canonical source: home-lab's `CLAUDE.md`,
  Conventions section.** Cite it, do not restate it here.
- **ImageMagick's `import` infers output format from the file extension.**
  Use an explicit `format:` prefix (`png:path`).
- **On a screen with an actual map viewport, never do a blanket
  full-screen `dfhack.screen.readTile` dump.** Scope scans to the specific
  rows/columns a label search actually needs.
- **`gui.simulateInput`'s generic keys don't work on DF v50+'s native
  button-style menus, and this extends to WASD map-panning too** —
  confirmed dead (pixel-identical before/after screenshots) on
  `choose_start_sitest`'s camera panning specifically, alongside the
  already-known title-screen/region-list menu cases. Mouse clicks
  (buffer-scan for text, compute coordinate, `_MOUSE_L`) are the only
  confirmed-working input method on any of these screens.
- **Site Finder's "Begin" needs at least one non-N/A criterion set, or it
  silently no-ops forever.** Solved this session, see archive for the
  full A/B test.
- **`load-save.lua`'s `sel_menu_line`-on-`viewscreen_titlest` approach
  does not apply to this build.** Tagged `unavailable`, don't re-attempt.
- **A checksum must never pass through an LLM-summarized web fetch** —
  fetch it directly with `curl` and compare byte-for-byte. Learned the
  hard way this session (see `scripts/provision_relay.py`'s comments).
- **`.env` appends must check for a trailing newline first** —
  `install_df.py`'s `_append_env_var()` helper does this; never use a bare
  `open(path, "a")` again (caused a real incident this session: a missing
  trailing newline silently merged `DF_VNC_PASSWORD` onto the end of
  `ANTHROPIC_API_KEY`'s line).

### Other open items, carried forward

- **Design commitment #1's absolute wording vs. its actual evidence
  base** — still queued for a `decisions/DECISIONS.md` entry, deliberately
  not written yet (user's call on timing). This session put a live
  instance of the distinction into practice (screenshots used directly
  for the tileset-debugging work, with the user's explicit go-ahead)
  without writing the formal entry.
- **Live-view ingest (the public screenshot-push leg), still waiting on
  the user.** Once Cloudflare R2 credentials arrive: wire
  `DF_STREAM_INGEST_URL` in `.env`, convert `curl -F` to an S3-compatible
  signed PUT, fill in `IMAGE_BASE` in
  `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, ask
  before pushing/deploying either repo.
- **Cloudflare Tunnel on the relay — live and verified, public URL
  confirmed working end to end.** `https://dwarf-fortress.willsmith.nz/`
  returns HTTP 200 (confirmed via `curl`) and serves the same noVNC bridge
  the relay serves on the LAN. `scripts/provision_relay.py cloudflared`
  installs `cloudflared` from Cloudflare's own apt repo (verified 2026-09-09
  against `pkg.cloudflare.com`'s own index page, fetched directly: current
  method is a `/usr/share/keyrings/` keyring file plus an inline
  `signed-by=` apt line, not the deprecated `apt-key` path) and runs the
  token-based `cloudflared service install <token>` step once
  `CLOUDFLARE_TUNNEL_TOKEN` is in `.env`. Public Hostname in the dashboard:
  `dwarf-fortress.willsmith.nz` -> `http://localhost:6080`, subdomain chosen
  over a `willsmith.nz/dwarf-fortress` path deliberately: Cloudflare
  Tunnel's path-routing only works for a hostname already pointed at that
  tunnel, so a path at the apex would mean re-pointing all of
  `willsmith.nz`'s DNS through the relay and proxying everything else back
  out to GitHub Pages — real added risk (the whole site's uptime tied to
  the relay) for a URL-shape preference. `decisions/DECISIONS.md` 2026-09-09
  rows record the Cloudflare-Tunnel-over-generic-VPS simplification and the
  explicit revisit of both research docs' screenshot-over-VNC
  recommendation for the public leg.

  **Public feed is deliberately unauthenticated (`x11vnc -nopw`), decided
  2026-09-09 once it actually went public** — `install_df.py vnc
  --no-password` drops the `-rfbauth` gate entirely (not just an empty
  password); the feed is still `-viewonly` (confirmed live: `ps aux` on VM
  103 shows `-nopw ... -viewonly`, no keyboard/mouse ever reaches the
  guest), so an anonymous connection can only watch, not act. This is the
  same x11vnc instance the LAN path also uses, so LAN access lost its
  password too as a side effect, trading away a defense-in-depth layer
  against LAN-side snooping specifically (not any control-surface risk) —
  see `cmd_vnc`'s docstring in `scripts/install_df.py` for the full
  reasoning. `DF_VNC_PASSWORD` is still in `.env` but unused while
  `--no-password` is in effect.
  **Root URL now redirects straight to the viewer** instead of a raw
  directory listing (confirmed live 2026-09-09: the stock `novnc` apt
  package ships no `index.html`, so `/` was serving an Apache-style file
  list of `app/`, `core/`, `vendor/`, etc.) — a shared `install_novnc_index`
  helper (`scripts/install_df.py`) drops a meta-refresh redirect to
  `vnc.html?autoconnect=true&resize=scale` into `/usr/share/novnc/`, used by
  both VM 103's own `webvnc` (LAN) and the relay's (public), autoconnect
  only being a safe default because the password gate is actually off.
  Lives in an apt package path, not this repo, so a future `apt upgrade` of
  `novnc` could overwrite it — cheap to re-run `webvnc` if so.
  Link is live in `willsmith-portfolio/public/dwarf-fortress/index.html`
  (pushed, deploy triggered).
- **Actually embark** — a candidate site was found on `region2` (the
  graphics-enabled world, "Match found!") but nobody has embarked. The
  real first-fort milestone.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

## HANDOVER - 2026-09-10 (end of session)

Moved here wholesale, superseded by the same day's later handover in
`Working.md` (which resolved the click-registration mystery below, found
the real multi-click embark mechanism, and found a new reproducible crash
one step further in) — not because this session finished, but per the
archive-cadence rule once superseded.

## HANDOVER - 2026-09-10 (end of session, third handover today)

Moved here wholesale, superseded by the same day's fourth handover in
`Working.md`, which found the root cause of the whole night's
map-navigation confusion (a coordinate-frame mismatch between `find_mm_*`
and `warn_mm_*`/`neighbor_hover_mm_*`) and the `xdotool` real-input fix for
headless map/hover interaction — not because this session finished, but
per the archive-cadence rule once superseded.

The prior handover from earlier the same day is archived wholesale above
this one. **This session founded the first fort.**

### State at a glance

- **The first fort exists: "Artobcatten, Combinedchannel," `region2`,
  running unattended under normal systemd supervision.** `save/autosave 1`
  is the real save (contains `world.sav`). Confirmed via the in-game
  founding message, a screenshot, `gametype == 0` (`DWARF_MAIN`), and a
  successful stop/quicksave/reload cycle through the title screen's new
  "Continue active game" button. This is the project's first standing
  fort — a genuine milestone, not just infrastructure. `CLAUDE.md`'s
  status line updated to say so.
- **The "Confirm" crash from the last handover is resolved — empirically,
  not by root cause.** It's a timing/race condition: running `dwarfort`
  directly under `gdb` (installed fresh, `apt-get install gdb`) with a
  `catch syscall exit_group` breakpoint, the identical click sequence that
  crashed three times at full speed did not crash at all — gdb's `ptrace`
  overhead apparently changes timing enough to dodge whatever the race is.
  The catchpoint never fired (no crash to catch), so **the actual
  mechanism is still unknown**. Two other hypotheses were tested and ruled
  out first, live, with the user watching: a genuine Site-Finder
  "accept/navigate" step being skipped (none exists — checked the real UI
  flow end to end) and a rectangle mismatch between the map click and the
  forced `warn_mm_*` (eliminated by copying the real
  `gui/embark-anywhere.lua`-idiom `neighbor_hover_mm_*` instead — still
  crashed identically). Also settled: `systemctl status` consistently
  showed `code=exited, status=1`, not a signal death — confirmed via the
  `./dfhack` wrapper script's own source that this is `dwarfort` calling
  `exit(1)` itself, so a traditional core dump would never have fired
  anyway. Full evidence trail in `decisions/DECISIONS.md` 2026-09-10 (the
  row titled "First fort founded"), `docs/DF-UI-AUTOMATION.md`.
- **Practical implication for next time**: if a future embark (a second
  fort, a reclaim, etc.) hits this same crash, running it under gdb again
  is the known workaround, not a real fix. Root-causing the actual race
  (verbose DFHack logging, or a breakpoint on the real crash path) is
  worth doing if it recurs, but wasn't necessary tonight.
- **`docs/DF-UI-AUTOMATION.md`'s screen atlas now covers the full chain**
  through `viewscreen_setupdwarfgamest` ("Play now!") and
  `viewscreen_dwarfmodest` (fortress mode), plus the title screen's new
  "Continue active game" button that appears once a save exists.

### Next: nothing is deciding what the fort does yet

The fort is standing, not being played — there is still no perception
layer, no agent, no toolkit for actually running it. `docs/PURPOSE.md`'s
build order (`check_reachable`/`get_connectivity_report` first) is the
next real code to write, unchanged by tonight's milestone; see
`ROADMAP.md`'s "Next" bucket. In the meantime the fort just sits idle
under systemd — nothing is currently driving it turn to turn, and nothing
needs to be: it survives unattended the same way the empty world did
before it.

### Durable traps, still true (additions marked NEW)

- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's `memory/tailscale-architecture.md` assigns `df-fortress`/
  `df-colony-01` to `tag:ai-sandbox` — "unattended, possibly LLM-driven,
  lowest trust that isn't internet-facing" — but `runbooks/tailscale-topology.md`
  Phase 5 (the actual hard gate) is still unchecked. **Not this repo's to
  fix** — host-level Tailscale/ACL work, forbidden to any agent by
  home-lab's own rule.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL. **This
  is now load-bearing, not theoretical** — a real fort has existed since
  2026-09-10 and must be quicksaved before any future stop.
- **The manual (`start`/`stop`) and systemd-managed paths must not run at
  once** — `install_df.py stop` does not clean up a manually-started
  Xvfb. See archive for the full incident/fix.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it.**
- **The published hostname is exposed.** The user chose not to rename it.
- **`willsmith.nz` is deliberate**, not a leak: the intended public face.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified.**
- **`hypothesis_id` has no registry.**
- **`openclaw` vs `hermes-agent` still deferred.**
- **Tarball checksums are pinned and enforced.**
- **PVE's cloud-init takes only the first label of the VM `name`** —
  `install_df.py`'s `step_hostname` (reused for the relay too) is the only
  workable route to a suffixed guest hostname.
- **Hostname convention has one canonical source: home-lab's `CLAUDE.md`,
  Conventions section.** Cite it, do not restate it here.
- **ImageMagick's `import` infers output format from the file extension.**
  Use an explicit `format:` prefix (`png:path`).
- **On a screen with an actual map viewport, never do a blanket
  full-screen `dfhack.screen.readTile` dump.** Scope scans to the specific
  rows/columns a label search actually needs.
- **`gui.simulateInput`'s generic keys don't work on DF v50+'s native
  button-style menus, and this extends to WASD map-panning and all four
  `CURSOR_*` directions too** — confirmed dead (pixel-identical
  before/after, and unchanged struct fields) on `choose_start_sitest`'s
  camera panning and cursor movement specifically, alongside the
  already-known title-screen/region-list menu cases. Mouse clicks
  (buffer-scan for text, compute coordinate, `_MOUSE_L`) remain the only
  confirmed-working input method for menu-style screens.
- **RESOLVED, was flagged NEW last session**: the "off-center clicks don't
  register" theory is disproven — the real cause was a whole-screen text
  scan false-matching an earlier occurrence of the target string. See
  `docs/DF-UI-AUTOMATION.md`. Whenever scanning for button text, scope the
  scan to the specific row/region the real button is known to be on if
  the same or similar text could appear elsewhere on screen first.
- **RESOLVED, was flagged NEW last session**: `df.global.gps.precise_mouse_x/y`
  is a live OS-polled pixel-space mouse position (`enabler`'s
  `get_precise_mouse_coords` vmethod, confirmed via DFHack's own
  `df-structures` source), not a writable struct field — it's clobbered
  by the next poll before a Lua write can affect anything. Don't try
  writing it again for mouse automation; `gps.mouse_x/y` (the character-grid
  position) is the real input.
- **RESOLVED, was flagged NEW earlier today**: The Embark button (row 57)
  resets `warn_mm_*` to `-1,-1,-1,-1` and flips `choosing_embark` to
  `true` when clicked — the committed Site Finder match does not survive
  that click and must be re-applied (along with `warn_flags.GENERIC`)
  after the subsequent map click, not just once up front. Still true and
  load-bearing, just no longer "new."
- **RESOLVED, was flagged NEW earlier today**: clicking "Confirm" crashed
  DF/DFHack outright, three times reproduced, two other hypotheses ruled
  out (a skipped native accept step; a rectangle mismatch). The real cause
  is a **timing/race condition** — running under `gdb` avoided it
  entirely, though the exact mechanism is unconfirmed (the gdb catchpoint
  never actually fired). If this crash recurs on a future embark, running
  it under gdb again is the known workaround. See
  `decisions/DECISIONS.md` 2026-09-10 ("First fort founded") and
  `docs/DF-UI-AUTOMATION.md` for the full trail.
- NEW: **`code=exited, status=1` in `systemctl status` means the process
  called `exit(1)` itself — not a signal death — so a core dump will
  never fire for it.** Distinguish this from `code=killed, status=SIGxxx`
  before spending time on core-dump tooling. Confirmed by reading the
  `./dfhack` wrapper script itself: it captures `dwarfort`'s real exit
  code in `ret=$?` immediately after it exits, and an unrelated `tput
  sgr0` cosmetic call (which fails harmlessly on every shutdown under
  systemd's unset `$TERM`, clean or crashed) does not touch `$ret` before
  the final `exit $ret`.
- NEW: **The title screen gains a "Continue active game" button, above
  "Start new game in existing world," once any save exists** — the
  reliable signal to check for whether a fort has actually been founded,
  rather than inferring it from screen type alone.
- NEW: **A founded fort's real save directory is not necessarily
  "region2" (or whatever `cur_savegame.save_dir` said pre-embark)** — DF
  named it `"autosave 1"` this time. Check
  `df.global.world.cur_savegame.save_dir` on the live fort itself rather
  than assuming it matches the world it was founded in; `region1`/`region2`
  remain pure world-history folders (they gain `unit-*.dat`/`world.dat`
  from worldgen's own history simulation, not from a player fort — don't
  mistake that for fort save data).
- NEW: **`df-overseer-ui.lua`'s `click` self-reported `FAIL` twice this
  session on clicks that had actually worked** (`"Fortress"`,
  `"Skip tutorial"`, `"Okay"`) — its success check (does the scanned text
  disappear) is unreliable when the same screen persists with the text
  still present, or a duplicate match exists elsewhere. Verify with
  `type` or a field read, don't trust its FAIL/PASS report alone. Not yet
  fixed in the script.
- NEW: **Writes to `neighbor_hover_mm_*` alone, and `gps.mouse_x/y` alone
  without an accompanying click in the same call, do not move anything
  visually** — confirmed by direct write-then-screenshot tests. These
  behave like render-loop-derived outputs in practice for at least some
  fields, not authoritative inputs; `zoomed_in` is the opposite case — it
  CAN be set directly and does affect which screen renders next (regional
  vs. local map). Which fields are real inputs vs. render-derived outputs
  is inconsistent and not yet mapped out systematically.
- NEW: **DF's "Re-run finder" confirmation dialog** (triggered by clicking
  "Begin" again once a match already exists) **offers only "P: Pause this
  confirmation" or "Enter: Yes, proceed" — no plain cancel.** `CUSTOM_P`
  dismisses it without losing the existing match (confirmed: `find_mm_*`
  unchanged afterward). Don't press Enter here unless you actually want to
  discard the current match and re-search.
- NEW: **A full-tree file-manifest diff must tab-separate size and path**
  (`find ... -printf '%s\t%P\n'`, split with `awk -F'\t'`), not
  space-separate — `data/vanilla`'s own `examples and notes/` and
  `interaction examples/` folders have spaces in their names and silently
  corrupt a naive `awk '{print $2}'` split, producing false "missing file"
  entries for an unrelated stray word. Both are non-module reference/example
  docs outside the `vanilla_*` naming convention, not real content, so this
  didn't hide a real gap this time, but would have been easy to miss.
- NEW: **`dfhack-run lua -f script.lua ARG1 ARG2` passes arguments via Lua
  varargs (`local x, y = ...`) inside the script, not a global `arg`
  table** — `arg` is nil in this execution context.
- **Site Finder's "Begin" needs at least one non-N/A criterion set, or it
  silently no-ops forever.** Solved 2026-09-09, see archive for the full
  A/B test.
- **`load-save.lua`'s `sel_menu_line`-on-`viewscreen_titlest` approach
  does not apply to this build.** Tagged `unavailable`, don't re-attempt.
- **A checksum must never pass through an LLM-summarized web fetch** —
  fetch it directly with `curl` and compare byte-for-byte.
- **`.env` appends must check for a trailing newline first** —
  `install_df.py`'s `_append_env_var()` helper does this; never use a bare
  `open(path, "a")` again.

### Other open items, carried forward

- **Design commitment #1's absolute wording vs. its actual evidence
  base** — still queued for a `decisions/DECISIONS.md` entry, deliberately
  not written yet (user's call on timing).
- **Live-view ingest (the public screenshot-push leg), still waiting on
  the user.** Once Cloudflare R2 credentials arrive: wire
  `DF_STREAM_INGEST_URL` in `.env`, convert `curl -F` to an S3-compatible
  signed PUT, fill in `IMAGE_BASE` in
  `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, ask
  before pushing/deploying either repo.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

The prior handover from earlier the same day is archived wholesale above
this one. This session picked up its queued task directly, root-caused it,
found the real embark mechanism, and hit a new blocker one step further in.

### State at a glance

- **VM 103**: running DF under systemd, **idle at `viewscreen_titlest`**
  (deliberately left there, not mid-sequence — see below). Still no fort,
  but the path to one is now fully mapped except for one crash.
- **The "click Embark won't register" mystery from the last handover is
  resolved, and the theory it left queued (off-center clicks) is
  disproven.** It was a buffer-scan bug: a whole-screen search for the
  text `"Embark"` matches the help sentence at row 52
  (`Click "Embark" to place your fortress.`) before it ever reaches the
  real button at row 57, so the generic tool was almost certainly clicking
  that sentence, not the button, every time last session. Scoped to the
  exact row, the click registered correctly on the first try — at
  `x=111,y=57` of a 160×60 grid, about as off-center as this screen gets,
  which directly disproves the "clicks near screen-center are more
  reliable" theory. `precise_mouse_x/y` (the field that sat stuck at
  `640,360` all last session) is also resolved: DFHack's own
  `df-structures` source (`df.g_src.graphics.xml`) documents it as a
  live OS-polled pixel-space mouse position (`get_precise_mouse_coords`
  vmethod on `enabler`), not a durable struct field — in headless Xvfb
  there's no real mouse moving, so it just keeps reporting the window's
  center regardless of any Lua write. Full detail in
  `docs/DF-UI-AUTOMATION.md`.
- **The real embark mechanism has two more clicks after "Embark" than
  anyone had mapped**, found by reading `gui/embark-anywhere.lua`'s
  source (the script this project's `force_embark()` idiom was borrowed
  from): click "Embark" → `choosing_embark` flips true and `warn_mm_*`
  resets to `-1,-1,-1,-1` → click anywhere on the local map, then
  re-override `warn_mm_*`/`warn_flags.GENERIC` in the same call → a
  **"Confirm / Abort" bar appears** (previously undocumented) → click
  "Confirm". Drove this live, twice, including one full fresh re-drive
  from the title screen (existing world → Fortress mode → both intro
  dialogs, `"Skip tutorial"` then `"Okay"` — both must be dismissed on a
  fresh attempt or the Embark click lands on the dialog instead).
- **New blocker: clicking "Confirm" crashes DF/DFHack outright.**
  Reproduced identically twice (`systemctl status` shows
  `code=exited, status=1/FAILURE`, not a hang), no core dump, no useful
  line in `stderr.log` beyond routine RPC connection churn. **No save was
  created either time — nothing has been lost.** Untested hypothesis: the
  map click landed on an arbitrary pixel inside the viewport while
  `warn_mm_*` was then force-overridden to an unrelated target rectangle;
  if the engine's finalization path also reads a click-derived index
  (e.g. `neighbor_hover_mm_*`, already confirmed render-derived and
  garbage-valued mid-sequence) independently of `warn_mm_*`, that
  mismatch may be what crashes it. Next thing to try: click at the actual
  pixel position corresponding to the target rectangle, not an arbitrary
  one, so there's no mismatch between "where the click landed" and "what
  got committed."
- Full evidence trail: `decisions/DECISIONS.md` 2026-09-10 (the row
  titled "Embark click-registration mystery resolved..."),
  `docs/DF-UI-AUTOMATION.md`'s updated screen atlas and "Confirm" crash
  section.
- **Also found and documented**: the reusable `df-overseer-ui.lua`
  `click` tool's own success check (does the scanned text disappear) is
  unreliable — it self-reported `FAIL` twice this session on clicks that
  had actually worked (`"Fortress"`, `"Skip tutorial"`, `"Okay"`).
  Treat its `FAIL` as inconclusive, verify with `type` or a field read
  instead. Not yet fixed in the script.

### Queued task for next session: fix the "Confirm" crash

**Do not skip re-verifying state first** — confirm `type` before touching
anything, per "verify the verification." VM 103 was deliberately left
idle at `viewscreen_titlest`, not mid-sequence, so start from the title
screen: `"Start new game in existing world"` → confirm `save_dir ==
"region2"` → `"Fortress"` → dismiss `"Skip tutorial"` and `"Okay"` →
directly write `find_mm_sx/sy/ex/ey = 6,8,9,11`, `find_cur_best_value =
10066`, `warn_mm_* = 6,8,9,11`, `warn_flags.GENERIC = true`, `zoomed_in =
true` (region2's terrain is deterministic, no need to re-run Site
Finder's own search) → click "Embark" at its exact row-57 position (don't
whole-screen-scan for the text) → click the map, re-override
`warn_mm_*`/`warn_flags.GENERIC` → click "Confirm" at its buffer-scanned
position, trying the actual-target-pixel fix above instead of an
arbitrary map-click point this time. If it crashes again identically,
that's a third data point worth treating as a real DF/DFHack bug rather
than something this project's script can work around — consider filing
upstream or trying a manual (human, via the VNC feed) embark once to
confirm whether a real player's mouse hits the same wall, which would
mean this isn't script-automation-specific at all.

### Durable traps, still true (additions marked NEW)

- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's `memory/tailscale-architecture.md` assigns `df-fortress`/
  `df-colony-01` to `tag:ai-sandbox` — "unattended, possibly LLM-driven,
  lowest trust that isn't internet-facing" — but `runbooks/tailscale-topology.md`
  Phase 5 (the actual hard gate) is still unchecked. **Not this repo's to
  fix** — host-level Tailscale/ACL work, forbidden to any agent by
  home-lab's own rule.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL.
- **The manual (`start`/`stop`) and systemd-managed paths must not run at
  once** — `install_df.py stop` does not clean up a manually-started
  Xvfb. See archive for the full incident/fix.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it.**
- **The published hostname is exposed.** The user chose not to rename it.
- **`willsmith.nz` is deliberate**, not a leak: the intended public face.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified.**
- **`hypothesis_id` has no registry.**
- **`openclaw` vs `hermes-agent` still deferred.**
- **Tarball checksums are pinned and enforced.**
- **PVE's cloud-init takes only the first label of the VM `name`** —
  `install_df.py`'s `step_hostname` (reused for the relay too) is the only
  workable route to a suffixed guest hostname.
- **Hostname convention has one canonical source: home-lab's `CLAUDE.md`,
  Conventions section.** Cite it, do not restate it here.
- **ImageMagick's `import` infers output format from the file extension.**
  Use an explicit `format:` prefix (`png:path`).
- **On a screen with an actual map viewport, never do a blanket
  full-screen `dfhack.screen.readTile` dump.** Scope scans to the specific
  rows/columns a label search actually needs.
- **`gui.simulateInput`'s generic keys don't work on DF v50+'s native
  button-style menus, and this extends to WASD map-panning and all four
  `CURSOR_*` directions too** — confirmed dead (pixel-identical
  before/after, and unchanged struct fields) on `choose_start_sitest`'s
  camera panning and cursor movement specifically, alongside the
  already-known title-screen/region-list menu cases. Mouse clicks
  (buffer-scan for text, compute coordinate, `_MOUSE_L`) remain the only
  confirmed-working input method for menu-style screens.
- **RESOLVED, was flagged NEW last session**: the "off-center clicks don't
  register" theory is disproven — the real cause was a whole-screen text
  scan false-matching an earlier occurrence of the target string. See
  `docs/DF-UI-AUTOMATION.md`. Whenever scanning for button text, scope the
  scan to the specific row/region the real button is known to be on if
  the same or similar text could appear elsewhere on screen first.
- **RESOLVED, was flagged NEW last session**: `df.global.gps.precise_mouse_x/y`
  is a live OS-polled pixel-space mouse position (`enabler`'s
  `get_precise_mouse_coords` vmethod, confirmed via DFHack's own
  `df-structures` source), not a writable struct field — it's clobbered
  by the next poll before a Lua write can affect anything. Don't try
  writing it again for mouse automation; `gps.mouse_x/y` (the character-grid
  position) is the real input.
- NEW: **The Embark button (row 57) resets `warn_mm_*` to `-1,-1,-1,-1`
  and flips `choosing_embark` to `true` when clicked** — the committed
  Site Finder match does not survive that click and must be re-applied
  (along with `warn_flags.GENERIC`) after the subsequent map click, not
  just once up front.
- NEW: **Clicking "Confirm" on the post-map-click "Confirm / Abort" bar
  crashes DF/DFHack outright** (`status=1/FAILURE`, no core dump, no
  useful stderr) — reproduced identically twice. No save is created
  either time, so nothing is lost, but the fort still cannot be founded
  this way yet. See `Working.md`'s queued task and `docs/DF-UI-AUTOMATION.md`
  for the untested fix hypothesis (click the actual target pixel, not an
  arbitrary map point).
- NEW: **`df-overseer-ui.lua`'s `click` self-reported `FAIL` twice this
  session on clicks that had actually worked** (`"Fortress"`,
  `"Skip tutorial"`, `"Okay"`) — its success check (does the scanned text
  disappear) is unreliable when the same screen persists with the text
  still present, or a duplicate match exists elsewhere. Verify with
  `type` or a field read, don't trust its FAIL/PASS report alone. Not yet
  fixed in the script.
- NEW: **Writes to `neighbor_hover_mm_*` alone, and `gps.mouse_x/y` alone
  without an accompanying click in the same call, do not move anything
  visually** — confirmed by direct write-then-screenshot tests. These
  behave like render-loop-derived outputs in practice for at least some
  fields, not authoritative inputs; `zoomed_in` is the opposite case — it
  CAN be set directly and does affect which screen renders next (regional
  vs. local map). Which fields are real inputs vs. render-derived outputs
  is inconsistent and not yet mapped out systematically.
- NEW: **DF's "Re-run finder" confirmation dialog** (triggered by clicking
  "Begin" again once a match already exists) **offers only "P: Pause this
  confirmation" or "Enter: Yes, proceed" — no plain cancel.** `CUSTOM_P`
  dismisses it without losing the existing match (confirmed: `find_mm_*`
  unchanged afterward). Don't press Enter here unless you actually want to
  discard the current match and re-search.
- NEW: **A full-tree file-manifest diff must tab-separate size and path**
  (`find ... -printf '%s\t%P\n'`, split with `awk -F'\t'`), not
  space-separate — `data/vanilla`'s own `examples and notes/` and
  `interaction examples/` folders have spaces in their names and silently
  corrupt a naive `awk '{print $2}'` split, producing false "missing file"
  entries for an unrelated stray word. Both are non-module reference/example
  docs outside the `vanilla_*` naming convention, not real content, so this
  didn't hide a real gap this time, but would have been easy to miss.
- NEW: **`dfhack-run lua -f script.lua ARG1 ARG2` passes arguments via Lua
  varargs (`local x, y = ...`) inside the script, not a global `arg`
  table** — `arg` is nil in this execution context.
- **Site Finder's "Begin" needs at least one non-N/A criterion set, or it
  silently no-ops forever.** Solved 2026-09-09, see archive for the full
  A/B test.
- **`load-save.lua`'s `sel_menu_line`-on-`viewscreen_titlest` approach
  does not apply to this build.** Tagged `unavailable`, don't re-attempt.
- **A checksum must never pass through an LLM-summarized web fetch** —
  fetch it directly with `curl` and compare byte-for-byte.
- **`.env` appends must check for a trailing newline first** —
  `install_df.py`'s `_append_env_var()` helper does this; never use a bare
  `open(path, "a")` again.

### Other open items, carried forward

- **Design commitment #1's absolute wording vs. its actual evidence
  base** — still queued for a `decisions/DECISIONS.md` entry, deliberately
  not written yet (user's call on timing).
- **Live-view ingest (the public screenshot-push leg), still waiting on
  the user.** Once Cloudflare R2 credentials arrive: wire
  `DF_STREAM_INGEST_URL` in `.env`, convert `curl -F` to an S3-compatible
  signed PUT, fill in `IMAGE_BASE` in
  `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, ask
  before pushing/deploying either repo.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

The full blow-by-blow of the 2026-09-09 session is archived wholesale —
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md).
This session's own detail lives in this session's tool history, not
archived separately (nothing here exceeded the length that would force
that yet). This handover is the tight, current-state version: what's true
right now, and the one concrete task queued next.

### State at a glance

- **VM 103** (`df-colony-01.internal`, `192.168.2.201`): running DF under
  systemd, idle at `viewscreen_choose_start_sitest` (zoomed in, on
  `region2`), with a confirmed valid Site Finder match (Savagery: Calm,
  `find_mm_sx/sy/ex/ey = 6,8,9,11`, `find_cur_best_value = 10066`) already
  committed into `warn_mm_*`/`warn_flags.GENERIC = true`, and the UI already
  showing "Click 'Embark' to place your fortress." **One click from the
  first fort** — see the queued task below, that click has not been made to
  register yet. Still no fort.
- **Graphics are now genuinely complete**, not just "confirmed rendering."
  2026-09-09's transplant only covered 8 of 10 real `data/vanilla` modules
  (`GRAPHICS_MODULES` in `scripts/install_df.py`). A user-reported missing
  UI panel (later confirmed via external search to be a real expected
  element) led to a full recursive file-manifest diff of *all* of
  `data/vanilla` between the user's Steam install and VM 103, not just
  spot-checks — this found two modules missed because they don't share the
  `_graphics` naming suffix the original list was built around:
  `vanilla_interface` (75 files — UI panel/chrome, including
  `interface_bits_embark.png`, the exact missing panel) and
  `vanilla_environment` (95 files — walls, floors, water, blood, fire,
  ramps: the core terrain tiles used throughout actual fortress-mode play,
  not just this embark screen — would have been a much worse blank-terrain
  bug to hit later). Both added to `GRAPHICS_MODULES` (now 10 entries),
  transplanted, DF restarted, confirmed visually fixed: proper bordered
  panels render everywhere now. `ART_FILES` (11 splash/title/logo assets
  in `data/art`, found missing the same night) also transplanted —
  cosmetic, not confirmed to fix anything specific, just completeness.
- **Public live viewing is fully live and public, not just "built."**
  `https://dwarf-fortress.willsmith.nz` is confirmed working end to end
  (Cloudflare Tunnel → relay → VM 103's noVNC), deliberately
  unauthenticated (`x11vnc -nopw`, still `-viewonly` — anyone with the link
  can watch, nobody can act) with the root URL auto-redirecting straight
  into the viewer. Linked live from `willsmith-portfolio`. Full detail
  already in `decisions/DECISIONS.md` 2026-09-09 rows; nothing more to do
  here.
- **Embark automation was re-driven live, end to end, tonight** — title
  screen → region list → mode select → site selection, confirming the full
  screen sequence exactly matches `research/2026-09-08-embark-automation.md`'s
  predicted chain (`viewscreen_titlest` → `viewscreen_adopt_regionst`
  (loading) → `viewscreen_choose_game_typest` → `viewscreen_update_regionst`
  (loading) → `viewscreen_choose_start_sitest`), plus one screen the
  research hadn't named (`viewscreen_choose_game_typest`, the
  Fortress/Adventurer/Legends picker). The `force_embark()` struct-write
  idiom (`warn_mm_*` = `find_mm_*`, `warn_flags.GENERIC = true`) **partially
  works**: it persists in memory and does flip the UI into the "click
  Embark" sub-mode, but three separate attempts to make the actual Embark
  click register all failed — see the queued task.

### Queued task for next session: make the final "click Embark" register

**Do not restart DF, do not re-run Site Finder, do not re-navigate the
menus.** The state described above (committed match, UI already in the
Embark sub-mode) is exactly where to resume from — confirm with
`./dfhack-run df-overseer-ui type` and `dump` (see below) before touching
anything, per this repo's "verify the verification" rule, since state may
have drifted if DF kept running.

**Read `docs/DF-UI-AUTOMATION.md` first.** A reusable Lua tool,
`scripts/dfhack/df-overseer-ui.lua` (deployed via
`python scripts/install_df.py ui-install`, callable as
`./dfhack-run df-overseer-ui <type|click TEXT|dump>`), was built 2026-09-10
specifically so this and future menu-automation work stops hand-writing a
fresh one-off script over SSH for every click — use it instead of
re-deriving the buffer-scan-and-click technique again. It does not yet
solve the off-center-click problem below; that's the next thing to fix in
it, not around it.

**What's been tried, all unsuccessful, so don't re-attempt these first
without a new idea**:
1. Buffer-scan-and-click on the literal "Embark" button text (the
   technique that reliably works elsewhere on this same screen — Site
   Finder criteria panel, "Skip tutorial", "Okay", "Fortress" all worked
   with retries).
2. A real `_MOUSE_L` click at a screen-pixel position visually estimated
   from a screenshot to land on one of the map's green candidate squares
   (not buffer-verified — the map itself renders via a texture-blit path
   invisible to `dfhack.screen.readTile`, confirmed in the 2026-09-09
   graphics work, so this click's target coordinate was a guess, not a
   scan result).
3. Setting `df.global.gps.mouse_x/mouse_y` **and** a second,
   previously-undiscovered field, `df.global.gps.precise_mouse_x/y`,
   together before the click. `precise_mouse_x/y` was found sitting at a
   fixed `(640, 360)` — suspiciously exactly the center of a 1280×720
   frame — completely unmoved by any of tonight's `gps.mouse_x/y` writes
   despite those writes reading back correctly. This is the most promising
   untested-to-completion lead: **the working theory is that
   `gui.simulateInput`'s `_MOUSE_L` click reliability correlates with
   whether the target is near screen-center** (title screen buttons, mode
   picker: all roughly horizontally centered, worked with retries) **or
   off-center** (the Embark button is bottom-right, the map itself is
   large and mostly off-center: consistently failed) — but setting
   `precise_mouse_x/y` proportionally alongside `mouse_x/y` did NOT
   unblock the Embark click either, so either the scaling/coordinate-space
   conversion used was wrong, or this isn't the actual mechanism and
   something else is.

**Concrete next steps worth trying, not yet attempted**:
- Check whether `precise_mouse_x/y`'s coordinate space is something other
  than the guessed 1280×720 (e.g. a DPI-scaled or letterboxed frame) —
  read DFHack's own source/docs for `gps` rather than inferring from one
  data point.
- Check whether DF actually renders a visible mouse cursor sprite at all
  in this headless Xvfb setup — if it does, a screenshot showing exactly
  where the cursor icon appears vs. where it was set would directly
  confirm or rule out the coordinate-space theory, rather than inferring
  from click success/failure alone.
- Consider whether the map click needs to go through a *different* code
  path than a plain `_MOUSE_L` on `scr` — e.g. a click on a `widget`
  sub-object (`scr.widgets`, seen in the full field dump but never
  explored) rather than the top-level viewscreen.
- If struct-level automation continues to resist, the fallback is a
  genuinely interactive session: the user watching live and directing
  clicks in real time is not available on the current public feed (it's
  `-viewonly`) — re-enabling input for a **private, password-gated**
  session (not the public unauthenticated one) is possible but was not
  set up tonight and would need its own decision, given the security
  reasoning already on record for why the public feed stays view-only.

**Site Finder internals, resolved 2026-09-10, useful context for whoever
continues this**: `research/2026-09-10-site-finder-internals.md` confirms
via DFHack's own `df-structures` that `mm` means "min/max" (in embark
tiles), and via the current DF Wiki page that Site Finder tracks exactly
**one** best-fit candidate (`find_mm_*`/`find_cur_best_value`, scalars,
not a vector) while the map's broader green highlighting is a *separate*
"all acceptable sites" display layer — the other green squares on screen
are real, independently valid sites, just not tracked as a comparable
list anywhere in the struct.

### Durable traps, still true (additions marked NEW)

- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's `memory/tailscale-architecture.md` assigns `df-fortress`/
  `df-colony-01` to `tag:ai-sandbox` — "unattended, possibly LLM-driven,
  lowest trust that isn't internet-facing" — but `runbooks/tailscale-topology.md`
  Phase 5 (the actual hard gate) is still unchecked. **Not this repo's to
  fix** — host-level Tailscale/ACL work, forbidden to any agent by
  home-lab's own rule.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL.
- **The manual (`start`/`stop`) and systemd-managed paths must not run at
  once** — `install_df.py stop` does not clean up a manually-started
  Xvfb. See archive for the full incident/fix.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it.**
- **The published hostname is exposed.** The user chose not to rename it.
- **`willsmith.nz` is deliberate**, not a leak: the intended public face.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified.**
- **`hypothesis_id` has no registry.**
- **`openclaw` vs `hermes-agent` still deferred.**
- **Tarball checksums are pinned and enforced.**
- **PVE's cloud-init takes only the first label of the VM `name`** —
  `install_df.py`'s `step_hostname` (reused for the relay too) is the only
  workable route to a suffixed guest hostname.
- **Hostname convention has one canonical source: home-lab's `CLAUDE.md`,
  Conventions section.** Cite it, do not restate it here.
- **ImageMagick's `import` infers output format from the file extension.**
  Use an explicit `format:` prefix (`png:path`).
- **On a screen with an actual map viewport, never do a blanket
  full-screen `dfhack.screen.readTile` dump.** Scope scans to the specific
  rows/columns a label search actually needs.
- **`gui.simulateInput`'s generic keys don't work on DF v50+'s native
  button-style menus, and this extends to WASD map-panning and all four
  `CURSOR_*` directions too** — confirmed dead (pixel-identical
  before/after, and unchanged struct fields) on `choose_start_sitest`'s
  camera panning and cursor movement specifically, alongside the
  already-known title-screen/region-list menu cases. Mouse clicks
  (buffer-scan for text, compute coordinate, `_MOUSE_L`) remain the only
  confirmed-working input method for menu-style screens.
- NEW: **A `_MOUSE_L` click's reliability appears to depend on whether the
  target is near screen-center or off-center** — unconfirmed as to why,
  but every off-center click attempt on `choose_start_sitest` (the Embark
  button, the map itself) failed tonight while every roughly-centered
  button elsewhere (title screen, mode picker, Site Finder panel) worked
  with retries. See the queued task above for the `precise_mouse_x/y`
  lead.
- NEW: **`df.global.gps.precise_mouse_x/y` is a second, separate
  mouse-position field from `gps.mouse_x/y`** — found sitting at a fixed
  `(640, 360)` all night regardless of `gps.mouse_x/y` writes succeeding.
  Not yet confirmed as load-bearing (setting both together did not fix the
  Embark click), but a real, previously-undocumented field worth
  understanding before more mouse-automation work on this or other
  screens.
- NEW: **Writes to `neighbor_hover_mm_*` alone, and `gps.mouse_x/y` alone
  without an accompanying click in the same call, do not move anything
  visually** — confirmed by direct write-then-screenshot tests. These
  behave like render-loop-derived outputs in practice for at least some
  fields, not authoritative inputs; `zoomed_in` is the opposite case — it
  CAN be set directly and does affect which screen renders next (regional
  vs. local map). Which fields are real inputs vs. render-derived outputs
  is inconsistent and not yet mapped out systematically.
- NEW: **DF's "Re-run finder" confirmation dialog** (triggered by clicking
  "Begin" again once a match already exists) **offers only "P: Pause this
  confirmation" or "Enter: Yes, proceed" — no plain cancel.** `CUSTOM_P`
  dismisses it without losing the existing match (confirmed: `find_mm_*`
  unchanged afterward). Don't press Enter here unless you actually want to
  discard the current match and re-search.
- NEW: **A full-tree file-manifest diff must tab-separate size and path**
  (`find ... -printf '%s\t%P\n'`, split with `awk -F'\t'`), not
  space-separate — `data/vanilla`'s own `examples and notes/` and
  `interaction examples/` folders have spaces in their names and silently
  corrupt a naive `awk '{print $2}'` split, producing false "missing file"
  entries for an unrelated stray word. Both are non-module reference/example
  docs outside the `vanilla_*` naming convention, not real content, so this
  didn't hide a real gap this time, but would have been easy to miss.
- NEW: **`dfhack-run lua -f script.lua ARG1 ARG2` passes arguments via Lua
  varargs (`local x, y = ...`) inside the script, not a global `arg`
  table** — `arg` is nil in this execution context.
- **Site Finder's "Begin" needs at least one non-N/A criterion set, or it
  silently no-ops forever.** Solved 2026-09-09, see archive for the full
  A/B test.
- **`load-save.lua`'s `sel_menu_line`-on-`viewscreen_titlest` approach
  does not apply to this build.** Tagged `unavailable`, don't re-attempt.
- **A checksum must never pass through an LLM-summarized web fetch** —
  fetch it directly with `curl` and compare byte-for-byte.
- **`.env` appends must check for a trailing newline first** —
  `install_df.py`'s `_append_env_var()` helper does this; never use a bare
  `open(path, "a")` again.

### Other open items, carried forward

- **Design commitment #1's absolute wording vs. its actual evidence
  base** — still queued for a `decisions/DECISIONS.md` entry, deliberately
  not written yet (user's call on timing).
- **Live-view ingest (the public screenshot-push leg), still waiting on
  the user.** Once Cloudflare R2 credentials arrive: wire
  `DF_STREAM_INGEST_URL` in `.env`, convert `curl -F` to an S3-compatible
  signed PUT, fill in `IMAGE_BASE` in
  `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, ask
  before pushing/deploying either repo.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.


## HANDOVER - 2026-09-10 (fourth handover today, superseded above)

The prior handover from earlier the same day is archived wholesale —
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md),
superseded by this one. **This session's big result: the actual root
cause of the whole night's map-navigation struggle, found and fixed.**

### State at a glance

- **The first fort ("Artobcatten, Combinedchannel," `region2`,
  `save/autosave 1`) still exists, safely saved, currently not loaded.**
  Not touched this session. DF is instead sitting mid-navigation on a
  **second, not-yet-committed** embark attempt: `viewscreen_choose_start_sitest`,
  `zoomed_in=true`, `choosing_embark=false`, `warn_mm_* = -1,-1,-1,-1`
  (nothing committed), `location.region_pos = (9,5)`, `find_results=2`
  (stale, from an earlier search). This is a safe, non-fragile idle state
  — nothing will progress or crash on its own while left here. `df-fortress.service`
  is `active` under systemd.
- **Root cause found: two different coordinate frames were being treated
  as one, and that's what actually broke navigation all night, not a
  camera/rendering bug.** `neighbor_hover_mm_*`/`warn_mm_*` are confirmed
  **world-absolute** embark-tile coordinates (live-matched, exactly, against
  `location.embark_pos_min/max`, whose real decompiled names are literally
  `abs_mm_start`/`abs_mm_end`). `find_mm_*` (Site Finder's own match
  output) is a **different, smaller-magnitude, non-absolute** coordinate.
  Every time earlier tonight `warn_mm_*` was force-written directly from
  `find_mm_*` (e.g. `(6,8,9,11)`), that was writing nonsense-scale
  coordinates near the map's origin corner, not the intended site — this
  is *the* explanation for "the same forced numbers landed in wildly
  different real places every time," not a camera/zoom/rendering issue as
  suspected for most of the session. Full trail, live-verified via direct
  struct reads (not inference): `research/2026-09-10-embark-screen-rendering-and-coordinates.md`.
  One sub-question is still open: the wiki's "one region tile = 16×16
  embark tiles" fact gives `region_pos.x*16 + find_mm_sx` matching
  `neighbor_hover_mm_sx` exactly, but the same formula on Y is off by a
  consistent, unexplained 9 (the sample wasn't time-aligned —
  `doing_site_finder` was already `false` when read). **Single recommended
  test, cheap and read-only**: run Site Finder fresh ("Begin"), immediately
  read `find_mm_*` + `neighbor_hover_mm_*` + `location.region_pos` in one
  atomic `dfhack-run lua` call. Not blocking — see below.
- **Separately, and just as important: found why the map itself was
  fundamentally unsteerable all night, and fixed it.** `df.global.gps.precise_mouse_x/y`
  (the real, pixel-level mouse state that map hover-info, map clicks, and
  WASD camera panning all actually depend on, as opposed to
  `gps.mouse_x/y`, the coarse character-grid position DFHack's fake
  `gui.simulateInput` *can* set and which only text buttons need) is
  polled live from the real OS mouse every frame — confirmed via DFHack's
  own `enabler.get_precise_mouse_coords` vmethod. Headless Xvfb has no
  real mouse, so it sat permanently frozen all night regardless of any
  Lua write. **Fix**: install `xdotool` (`apt-get install -y xdotool`,
  not present by default) and drive REAL X11 input against the Xvfb
  display directly — `DISPLAY=:99 xdotool mousemove/keydown/keyup` —
  which genuinely updates `precise_mouse_x/y`, unblocks real hover-info
  readouts, real map clicks, and real WASD panning, none of which
  DFHack's fake input path can ever drive. Calibration, live-confirmed
  exact: the DF window sits at `+0,+40` within the virtual display (no
  window manager; `xwininfo` gives this directly), so
  `precise_mouse_x = real_X11_X` and `precise_mouse_y = real_X11_Y - 40`.
  `xdotool getmouselocation --shell` (needs `DISPLAY=:99` set explicitly —
  not inherited over SSH) is a valid independent cross-check.
- **`xdotool` click reliability**: a bare `mousemove X Y click 1` is
  flaky — confirmed via `xdotool`'s own docs that this build's `click`
  path has **no default inter-step delay**. What worked reliably all
  night: explicit `mousemove` → `sleep 0.3` → `mousedown 1` → `sleep 0.2`
  → `mouseup 1`. Minimum viable hold time was not characterized (untested
  whether shorter holds work); DF's own `G_FPS_CAP:50` (~20ms/frame) is
  offered only as a plausible order-of-magnitude floor, not measured.
- **WASD panning via `xdotool keydown`/`keyup` genuinely works** (unlike
  DFHack's fake-input WASD, confirmed dead again this session, pixel-identical
  screenshots before/after) — but panning speed for this specific tiny
  17×17-embark-tile "pocket" world is very fast relative to hold-time: a
  0.5s hold overshot the entire visible island into open ocean; ~0.05s
  taps gave small, controllable increments. Not calibrated to an exact
  tiles-per-second figure.
- **The visual "green = Site Finder match / red = existing site, can't
  settle / no highlight = valid but not a Finder pick" overlay legend
  was confirmed live by the user watching the actual feed** (matches the
  DF Wiki's "Site finder" page too, pasted in this session). The green
  overlay reliably appeared right after Site Finder's "Begin" but seemed
  to stop rendering after further interaction even though `find_results`/
  `find_mm_*` stayed intact underneath — `doing_site_finder` is the
  best-supported (live-observed, not proven) gate candidate; "we just
  panned away and it was still there" was not ruled out. There is also
  **no rendered mouse cursor sprite at all** in this setup (confirmed by
  the user watching live) — the only visual position feedback is DF's own
  native ~2×2 blue hover-square overlay, confirmed (via a subagent's
  GitHub-code-search of the entire DFHack C++ source, zero hits for
  `neighbor_hover_mm_*`/`warn_mm_*`/`find_mm_*`/`warn_flags` anywhere) to
  be **pure native, closed-source DF engine rendering** — not a DFHack
  overlay, not settable, not readable from any source this project has
  access to. This is a confirmed hard limit, not a gap to keep digging at.
- **Decided approach going forward, agreed with the user**: don't chase
  the visual overlay or try to reproduce `find_mm_*`'s exact transform.
  Since a real `xdotool` click already produces a correct, world-absolute
  `warn_mm_*` directly (confirmed working), do a **text-only sweep**:
  move the real cursor to successive candidate tiles (panning the camera
  to keep pace, so the sweep is also visible to anyone watching the live
  feed — the user specifically wants viewers to see the AI's search
  happening, not just infer it from logs), read the hover-info side panel
  and the placement-warning dialog (both plain character-buffer text,
  already proven 100% reliable all night, zero image dependency, squarely
  within design commitment #1's "never decide from a rendered map" rule),
  and commit the first candidate that matches desired criteria and comes
  back clean (no salt water / aquifer / mountain / "another site" warning).
  **Not yet implemented** — this is the concrete next step.
- **`docs/DF-UI-AUTOMATION.md`'s screen atlas now covers the full chain**
  through `viewscreen_setupdwarfgamest` ("Play now!") and
  `viewscreen_dwarfmodest` (fortress mode), plus the title screen's new
  "Continue active game" button that appears once a save exists.

### Next: implement the text-only sweep, then decide the fort's fate

Two independent threads, in order:
1. **Optionally**, run the one atomic read described above to settle the
   `find_mm_*` transform's Y-axis mystery — cheap, read-only, not
   blocking anything.
2. **Build and run the text-sweep** (see above) to find and commit a
   genuinely good second site — camera panning in sync with the sweep so
   it's visible on the live feed, not just log output.
3. Once a good second fort exists (or if the first one, "Artobcatten," is
   judged good enough after all — it was never actually re-examined
   in detail beyond "mostly ocean, bad"), decide whether to keep both,
   abandon one, or just carry on: the fort is still standing, not being
   played — no perception layer, no agent exists yet. `docs/PURPOSE.md`'s
   build order (`check_reachable`/`get_connectivity_report` first) is the
   next real code to write, unchanged by tonight, see `ROADMAP.md`'s
   "Next" bucket.

### Durable traps, still true (additions marked NEW)

- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's `memory/tailscale-architecture.md` assigns `df-fortress`/
  `df-colony-01` to `tag:ai-sandbox` — "unattended, possibly LLM-driven,
  lowest trust that isn't internet-facing" — but `runbooks/tailscale-topology.md`
  Phase 5 (the actual hard gate) is still unchecked. **Not this repo's to
  fix** — host-level Tailscale/ACL work, forbidden to any agent by
  home-lab's own rule.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL. **This
  is now load-bearing, not theoretical** — a real fort has existed since
  2026-09-10 and must be quicksaved before any future stop.
- **The manual (`start`/`stop`) and systemd-managed paths must not run at
  once** — `install_df.py stop` does not clean up a manually-started
  Xvfb. See archive for the full incident/fix.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it.**
- **The published hostname is exposed.** The user chose not to rename it.
- **`willsmith.nz` is deliberate**, not a leak: the intended public face.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified.**
- **`hypothesis_id` has no registry.**
- **`openclaw` vs `hermes-agent` still deferred.**
- **Tarball checksums are pinned and enforced.**
- **PVE's cloud-init takes only the first label of the VM `name`** —
  `install_df.py`'s `step_hostname` (reused for the relay too) is the only
  workable route to a suffixed guest hostname.
- **Hostname convention has one canonical source: home-lab's `CLAUDE.md`,
  Conventions section.** Cite it, do not restate it here.
- **ImageMagick's `import` infers output format from the file extension.**
  Use an explicit `format:` prefix (`png:path`).
- **On a screen with an actual map viewport, never do a blanket
  full-screen `dfhack.screen.readTile` dump.** Scope scans to the specific
  rows/columns a label search actually needs.
- **`gui.simulateInput`'s generic keys don't work on DF v50+'s native
  button-style menus, and this extends to WASD map-panning and all four
  `CURSOR_*` directions too** — confirmed dead (pixel-identical
  before/after, and unchanged struct fields) on `choose_start_sitest`'s
  camera panning and cursor movement specifically, alongside the
  already-known title-screen/region-list menu cases. Mouse clicks
  (buffer-scan for text, compute coordinate, `_MOUSE_L`) remain the only
  confirmed-working input method for menu-style screens.
- **RESOLVED, was flagged NEW last session**: the "off-center clicks don't
  register" theory is disproven — the real cause was a whole-screen text
  scan false-matching an earlier occurrence of the target string. See
  `docs/DF-UI-AUTOMATION.md`. Whenever scanning for button text, scope the
  scan to the specific row/region the real button is known to be on if
  the same or similar text could appear elsewhere on screen first.
- **RESOLVED, was flagged NEW last session**: `df.global.gps.precise_mouse_x/y`
  is a live OS-polled pixel-space mouse position (`enabler`'s
  `get_precise_mouse_coords` vmethod, confirmed via DFHack's own
  `df-structures` source), not a writable struct field — it's clobbered
  by the next poll before a Lua write can affect anything. Don't try
  writing it again for mouse automation; `gps.mouse_x/y` (the character-grid
  position) is the real input.
- **RESOLVED, was flagged NEW earlier today**: The Embark button (row 57)
  resets `warn_mm_*` to `-1,-1,-1,-1` and flips `choosing_embark` to
  `true` when clicked — the committed Site Finder match does not survive
  that click and must be re-applied (along with `warn_flags.GENERIC`)
  after the subsequent map click, not just once up front. Still true and
  load-bearing, just no longer "new."
- **RESOLVED, was flagged NEW earlier today**: clicking "Confirm" crashed
  DF/DFHack outright, three times reproduced, two other hypotheses ruled
  out (a skipped native accept step; a rectangle mismatch). The real cause
  is a **timing/race condition** — running under `gdb` avoided it
  entirely, though the exact mechanism is unconfirmed (the gdb catchpoint
  never actually fired). If this crash recurs on a future embark, running
  it under gdb again is the known workaround. See
  `decisions/DECISIONS.md` 2026-09-10 ("First fort founded") and
  `docs/DF-UI-AUTOMATION.md` for the full trail.
- NEW: **`find_mm_*` (Site Finder's match output) and
  `neighbor_hover_mm_*`/`warn_mm_*` (the real, committable embark
  rectangle) are two different coordinate frames — never write `find_mm_*`
  directly into `warn_mm_*`.** `warn_mm_*`/`neighbor_hover_mm_*` are
  confirmed world-absolute (live-matched exactly against
  `location.embark_pos_min/max`, real names `abs_mm_start`/`abs_mm_end`);
  `find_mm_*` is not. This was the actual cause of "the same forced
  coordinates landed in wildly different real locations" all night, not a
  camera bug. See `research/2026-09-10-embark-screen-rendering-and-coordinates.md`.
- NEW: **`df.global.gps.precise_mouse_x/y` (real pixel-level mouse state)
  can be made to actually work in headless Xvfb by installing `xdotool`
  and sending it real X11 input** (`DISPLAY=:99 xdotool mousemove/keydown/keyup`
  against the Xvfb display) — this is the fix for map hover-info, map
  clicks, and WASD camera panning, none of which DFHack's fake
  `gui.simulateInput` can ever drive (confirmed: that fake path only
  updates the coarse character-grid `gps.mouse_x/y`, which text buttons
  need but the map does not). Calibration: the DF window sits at `+0,+40`
  within the virtual display (no window manager, `xwininfo` gives this
  directly) — `precise_mouse_x = real_X11_X`, `precise_mouse_y = real_X11_Y - 40`.
  `xdotool getmouselocation --shell` cross-checks this independently
  (needs `DISPLAY=:99` set explicitly, not inherited over SSH).
- NEW: **`xdotool`'s `click` action has no default inter-step delay in
  this version** — a bare `mousemove X Y click 1` is flaky. Use explicit
  `mousemove` → `sleep 0.3` → `mousedown 1` → `sleep 0.2` → `mouseup 1`
  instead; this was empirically reliable all night. Minimum viable hold
  time not characterized.
- NEW: **There is no rendered mouse cursor sprite anywhere in this setup**
  (confirmed live by the user watching the actual feed) — the only visual
  position feedback is DF's native ~2×2 blue hover-square overlay, which
  is confirmed (GitHub-code-search of the entire DFHack C++ source: zero
  hits for `neighbor_hover_mm_*`/`warn_mm_*`/`find_mm_*`/`warn_flags`
  anywhere) to be pure native, closed-source DF rendering — not settable,
  not readable from any source available to this project. Don't spend
  more time trying to locate or drive it directly; use the hover-info
  panel text and placement-warning text instead, both of which are
  reliable and buffer-scannable.
- NEW: **`code=exited, status=1` in `systemctl status` means the process
  called `exit(1)` itself — not a signal death — so a core dump will
  never fire for it.** Distinguish this from `code=killed, status=SIGxxx`
  before spending time on core-dump tooling. Confirmed by reading the
  `./dfhack` wrapper script itself: it captures `dwarfort`'s real exit
  code in `ret=$?` immediately after it exits, and an unrelated `tput
  sgr0` cosmetic call (which fails harmlessly on every shutdown under
  systemd's unset `$TERM`, clean or crashed) does not touch `$ret` before
  the final `exit $ret`.
- NEW: **The title screen gains a "Continue active game" button, above
  "Start new game in existing world," once any save exists** — the
  reliable signal to check for whether a fort has actually been founded,
  rather than inferring it from screen type alone.
- NEW: **A founded fort's real save directory is not necessarily
  "region2" (or whatever `cur_savegame.save_dir` said pre-embark)** — DF
  named it `"autosave 1"` this time. Check
  `df.global.world.cur_savegame.save_dir` on the live fort itself rather
  than assuming it matches the world it was founded in; `region1`/`region2`
  remain pure world-history folders (they gain `unit-*.dat`/`world.dat`
  from worldgen's own history simulation, not from a player fort — don't
  mistake that for fort save data).
- NEW: **`df-overseer-ui.lua`'s `click` self-reported `FAIL` twice this
  session on clicks that had actually worked** (`"Fortress"`,
  `"Skip tutorial"`, `"Okay"`) — its success check (does the scanned text
  disappear) is unreliable when the same screen persists with the text
  still present, or a duplicate match exists elsewhere. Verify with
  `type` or a field read, don't trust its FAIL/PASS report alone. Not yet
  fixed in the script.
- NEW: **Writes to `neighbor_hover_mm_*` alone, and `gps.mouse_x/y` alone
  without an accompanying click in the same call, do not move anything
  visually** — confirmed by direct write-then-screenshot tests. These
  behave like render-loop-derived outputs in practice for at least some
  fields, not authoritative inputs; `zoomed_in` is the opposite case — it
  CAN be set directly and does affect which screen renders next (regional
  vs. local map). Which fields are real inputs vs. render-derived outputs
  is inconsistent and not yet mapped out systematically.
- NEW: **DF's "Re-run finder" confirmation dialog** (triggered by clicking
  "Begin" again once a match already exists) **offers only "P: Pause this
  confirmation" or "Enter: Yes, proceed" — no plain cancel.** `CUSTOM_P`
  dismisses it without losing the existing match (confirmed: `find_mm_*`
  unchanged afterward). Don't press Enter here unless you actually want to
  discard the current match and re-search.
- NEW: **A full-tree file-manifest diff must tab-separate size and path**
  (`find ... -printf '%s\t%P\n'`, split with `awk -F'\t'`), not
  space-separate — `data/vanilla`'s own `examples and notes/` and
  `interaction examples/` folders have spaces in their names and silently
  corrupt a naive `awk '{print $2}'` split, producing false "missing file"
  entries for an unrelated stray word. Both are non-module reference/example
  docs outside the `vanilla_*` naming convention, not real content, so this
  didn't hide a real gap this time, but would have been easy to miss.
- NEW: **`dfhack-run lua -f script.lua ARG1 ARG2` passes arguments via Lua
  varargs (`local x, y = ...`) inside the script, not a global `arg`
  table** — `arg` is nil in this execution context.
- **Site Finder's "Begin" needs at least one non-N/A criterion set, or it
  silently no-ops forever.** Solved 2026-09-09, see archive for the full
  A/B test.
- **`load-save.lua`'s `sel_menu_line`-on-`viewscreen_titlest` approach
  does not apply to this build.** Tagged `unavailable`, don't re-attempt.
- **A checksum must never pass through an LLM-summarized web fetch** —
  fetch it directly with `curl` and compare byte-for-byte.
- **`.env` appends must check for a trailing newline first** —
  `install_df.py`'s `_append_env_var()` helper does this; never use a bare
  `open(path, "a")` again.

### Other open items, carried forward

- **Design commitment #1's absolute wording vs. its actual evidence
  base** — still queued for a `decisions/DECISIONS.md` entry, deliberately
  not written yet (user's call on timing).
- **Live-view ingest (the public screenshot-push leg), still waiting on
  the user.** Once Cloudflare R2 credentials arrive: wire
  `DF_STREAM_INGEST_URL` in `.env`, convert `curl -F` to an S3-compatible
  signed PUT, fill in `IMAGE_BASE` in
  `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, ask
  before pushing/deploying either repo.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.


## HANDOVER - 2026-09-10 (end of session, fifth handover today)

The prior handover from earlier the same day is archived wholesale —
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md),
superseded by this one. **This session's result: a second fort was
founded ("Uniboslan, 'Ragwind'"), the first fort's save ("Artobcatten")
was lost as a side effect (unrecoverable, not a close call), and — after
a file-level backup — Uniboslan was actually played forward: a real room
dug, a real stockpile placed, several genuine DF/DFHack mechanics learned
the hard way.** The text-only sweep also got built and a real Windows SSH
bug got fixed along the way.

### State at a glance

- **A second fort exists and is running normally: "Uniboslan, 'Ragwind'"**,
  founded via the text-only sweep, confirmed via the in-game founding
  message and `gametype==0`. Quicksaved, transitioned off the diagnostic
  gdb-wrapped process (used as the crash workaround, see below) onto
  normal `df-fortress.service` systemd supervision, reloaded via the
  title screen's "Continue active game" button, verified via
  `viewscreen_dwarfmodest`'s own header. `df.global.world.cur_savegame.save_dir`
  is `autosave 2`.
- **The first fort, "Artobcatten, Combinedchannel," is gone.** Its actual
  save data lived in `save/autosave 1` (this repo already knew DF doesn't
  name a fort's save after its region — see the durable traps). Founding
  Uniboslan overwrote it: `save/autosave 1/world.sav` and
  `save/autosave 2/world.sav` are now byte-for-byte identical (confirmed
  via `md5sum`), both holding Uniboslan's data. `save/current` is empty,
  `region1`/`region2` are confirmed (again) pure world-gen-history with no
  player-fort data, and this repo's `backups/` directory has never
  actually been used (empty) — no recovery path was found. Told the user
  directly before doing anything else; **the user chose to accept the
  loss and move forward with Uniboslan** rather than pursue a
  Proxmox-snapshot recovery check. Full incident trail:
  `decisions/DECISIONS.md` 2026-09-10 ("second fort was founded, but the
  first fort's save was lost").
- **Extended `df-overseer-ui.lua`** with `embark-mode`, `leave-embark-mode`,
  `hover` — see the durable traps section for the mechanics these
  depend on. Deployed via `install_df.py ui-install`, confirmed working
  live and used to actually find and commit Uniboslan's site.
- **Found and fixed a real, previously-latent Windows-specific SSH bug**
  while deploying the above script: Git's MSYS-linked `ssh.exe` truncates
  a command-line argument to ~8182 characters when spawned by Python's
  `subprocess` (a native Win32 process) but not when spawned by bash.
  Fixed: `provision_vm.ssh_guest` gained `input_data` (pipes a payload
  over stdin instead), `install_df.remote()` uses it. `provision_relay.py`
  inherits the fix for free.
- **A crash, same signature as the first fort's "Confirm" race, recurred
  at a different step** (the map-click step, not Confirm) on the first
  commit attempt for Uniboslan's site — `code=exited, status=1`, no core
  dump, no save created, nothing lost by the crash itself. The known `gdb`
  workaround (run `dwarfort` directly under `gdb` with a `catch syscall
  exit_group` batch script, matching systemd's exact environment) avoided
  it again on retry, same as for the first fort.
- **New finding while retrying under `gdb`**: a real `xdotool` click on a
  genuinely valid, placeable tile went straight through to
  `viewscreen_setupdwarfgamest` with no `warn_mm_*` force-write and no
  separate Confirm click needed at all — unlike the first fort's
  documented flow. Not fully explained; possibly the force-write/Confirm
  dance was compensating for something specific to DFHack's fake input,
  not an inherent property of the flow. Worth revisiting if a third embark
  is ever attempted.
- **New finding, load-bearing for any future second embark**: restarting
  the embark flow from the title screen ("Start new game in existing
  world") did **not** return to the same world/coordinate frame as the
  stale mid-navigation state this session started in — it landed in
  `region1`, not `region2`. The stale `neighbor_hover_mm_*` numbers from
  before the crash pointed at real mountain terrain in this different
  world (DF's own validation correctly flagged it unplaceable), not the
  forest found earlier — a coincidence of matching numbers across
  different worlds, not a bug in the coordinate frame itself. The sweep
  had to be re-run fresh in the world actually reached this time.

### Resolved: pre-playthrough snapshot blocked by cluster quorum, worked around

User asked for a Proxmox snapshot of VM 103 before playing Uniboslan
forward (a safety net, given this session already lost one fort's save
with no backup). `provision_vm.py snapshot --name pre-uniboslan-playthrough`
failed: `unable to open file '/etc/pve/nodes/srv-01/qemu-server/103.conf.tmp...'
- Permission denied`, and a diagnostic `GET /cluster/status` on the same
token also came back `403 Sys.Audit` — matching the repo's own documented
trap ("if a write step fails oddly, check quorum before suspecting
permissions," `ROADMAP.md`) closely enough to check before assuming
anything else. Messaged the live `home-lab-c1` session (df-overseer has
no host shell access to check `pvecm status` itself, only a pool-scoped
API token); **user confirmed directly: SRV-02 is down**, and with no
QDevice on this cluster a single remaining node isn't a majority —
inquorate, exactly as suspected. **Not this repo's to fix** (home-lab
owns cluster/estate infra).

**Worked around rather than blocked on it**: `install_df.py backup`
doesn't touch the Proxmox API at all, just pulls the save directory off
the VM over SSH — ran it, got a real 18MB archive, and verified (not just
trusted the exit code) that it actually contains `autosave 2` (Uniboslan's
real save: unit files, region snapshots, `world.sav`), at
`backups/df-saves-103-20260910-162147.tar.gz`. This is a genuine safety
net, just a file-level one instead of a VM-level one — good enough to
proceed with playing the fort forward.

### Played Uniboslan forward: first room and stockpile, real findings

User's direction: back up first (done — see above), then actually play
the fort forward rather than keep it standing untouched, driving it
directly and documenting as it goes rather than building the framework
first. Result: **Uniboslan now has real structure**, not just seven idle
citizens on open ground.

- **`blueprints/` is now a real directory**, first entries in the
  "Blueprint library" scope item: `starter-entrance-1x1.csv` (one
  downstair), `starter-connector-1x1.csv` (one upstair, the fix for the
  job-creation bug below), `starter-room-5x5.csv` (`#dig`), and
  `starter-stockpile-5x5.csv` (`#place`, Food+Wood+Stone+Furniture+
  Finished Goods+Bars and Blocks). Applied via `quickfort run <file> -c
  x,y,z` — chosen deliberately over raw designation-poking because it
  matches design commitment #4 ("blueprints, not generated coordinates"),
  and `-c`/`--cursor` confirmed to need no interactive map cursor.
  Deployed to the guest via plain `scp` into `dfhack-config/blueprints/`
  (quickfort's own player-blueprint directory) — not through
  `install_df.py`'s script-deploy mechanism, since these are quickfort
  data files, not DFHack Lua scripts.
- **Four real findings, all confirmed live**: (1) the founding "A Dwarven
  Outpost..." dialog silently froze all citizen activity for 40+ real
  seconds even with `pause_state` reading `false` — the user, watching
  the live feed, correctly guessed this before I diagnosed it; dismissing
  it unfroze everything instantly. (2) A downstair can't be designated on
  a grass-covered surface tile ("light grass"/"dark grass") — needed a
  non-grass tile (here, "stone floor") within the room's own footprint.
  (3) **The costly one**: a plain `d` (floor) dig directly beneath an
  already-dug, walkable downstair does not get turned into a job at
  all — `checkDesignationsNow()` correctly reported it unreachable no
  matter how many times it was re-run, because the connecting tile
  specifically needs to be a **matching stair type** (`u`) to link the
  levels for job-creation, not just any walkable-adjacent floor. Fixing
  that one tile immediately created six real jobs from zero. (4) The
  fortress-wide job list is `df.global.world.jobs.list` (a linked-list,
  `.next`/`.item`), not `df.global.job_list` as
  `research/2026-08-25-spatial-perception.md`'s prototype sketch guessed
  (that doc's own §8 flagged this as its one unverified primitive — now
  verified, and the guess was wrong).
- **Also corrected a wrong claim I made mid-session**: told the user DF
  Classic's 2D engine has no zoom; they pushed back, and
  `data/init/interface.txt` directly proved real `ZOOM_IN`/`ZOOM_OUT`
  binds exist (`[`/`]`), confirmed working via real `xdotool` keypresses.
  Don't assert a negative about DF's feature set without checking the
  keybinding file first.
- **End state, paused and quicksaved (confirmed via mtime + file size,
  not just exit code)**: 25/25 room tiles dug, stockpile live, all 7
  citizens alive and behaving normally, Year 30, mid-Summer (month 3, day
  6). Paused deliberately per the user's own suggestion — pause the
  colony when not actively driving it, rather than leave it running
  unwatched. Full trail: `decisions/DECISIONS.md` 2026-09-10.
- **DONE this session**: pulled an `install_df.py backup` of Uniboslan's
  save (used as the pre-playthrough safety net, see above) — the
  "worth deciding" item from the prior draft of this section is resolved.

### Next: the fort's fate, and the real landmark system

1. **`docs/PURPOSE.md` build order item 3's real scope (burrow/building
   enumeration + adjacency graph) now has something real to work
   against** — the stockpile placed this session is a genuine `building`
   object, the first non-seed landmark candidate. Still needs to happen
   on the `perception-layer-experiments` branch, not `main` (see below),
   and is still unstarted beyond the seed landmark.
2. **`check_reachable`/`get_connectivity_report` and the seed landmark
   remain parked on `perception-layer-experiments`** (`107adf1`/`ac7547f`,
   not on `main`), user's explicit call to keep them experimental. The
   live VM still has both scripts deployed regardless of which branch is
   checked out locally.
3. **Not done this session, still open from an earlier handover**: the
   `find_mm_*` Y-axis transform mystery (cheap, read-only, not blocking).
4. **A general "audit the docs for stale info" pass was delegated to a
   Sonnet subagent** at the user's request, running in parallel with this
   handover being written — check its report/diff before trusting this
   handover is the only doc change from this session.

### Durable traps, still true (additions marked NEW)

- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's `memory/tailscale-architecture.md` assigns `df-fortress`/
  `df-colony-01` to `tag:ai-sandbox` — "unattended, possibly LLM-driven,
  lowest trust that isn't internet-facing" — but `runbooks/tailscale-topology.md`
  Phase 5 (the actual hard gate) is still unchecked. **Not this repo's to
  fix** — host-level Tailscale/ACL work, forbidden to any agent by
  home-lab's own rule.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL. **This
  is now load-bearing, not theoretical** — a real fort has existed since
  2026-09-10 and must be quicksaved before any future stop.
- **The manual (`start`/`stop`) and systemd-managed paths must not run at
  once** — `install_df.py stop` does not clean up a manually-started
  Xvfb. See archive for the full incident/fix.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it.**
- **The published hostname is exposed.** The user chose not to rename it.
- **`willsmith.nz` is deliberate**, not a leak: the intended public face.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified.**
- **`hypothesis_id` has no registry.**
- **`openclaw` vs `hermes-agent` still deferred.**
- **Tarball checksums are pinned and enforced.**
- **PVE's cloud-init takes only the first label of the VM `name`** —
  `install_df.py`'s `step_hostname` (reused for the relay too) is the only
  workable route to a suffixed guest hostname.
- **Hostname convention has one canonical source: home-lab's `CLAUDE.md`,
  Conventions section.** Cite it, do not restate it here.
- **ImageMagick's `import` infers output format from the file extension.**
  Use an explicit `format:` prefix (`png:path`).
- **On a screen with an actual map viewport, never do a blanket
  full-screen `dfhack.screen.readTile` dump.** Scope scans to the specific
  rows/columns a label search actually needs.
- **`gui.simulateInput`'s generic keys don't work on DF v50+'s native
  button-style menus, and this extends to WASD map-panning and all four
  `CURSOR_*` directions too** — confirmed dead (pixel-identical
  before/after, and unchanged struct fields) on `choose_start_sitest`'s
  camera panning and cursor movement specifically, alongside the
  already-known title-screen/region-list menu cases. Mouse clicks
  (buffer-scan for text, compute coordinate, `_MOUSE_L`) remain the only
  confirmed-working input method for menu-style screens. **Note the
  exception found this session**: real `xdotool`-driven WASD (not
  DFHack's fake input) does work for camera panning, including while
  `choosing_embark` is `true`.
- **`find_mm_*` (Site Finder's match output) and
  `neighbor_hover_mm_*`/`warn_mm_*` (the real, committable embark
  rectangle) are two different coordinate frames — never write `find_mm_*`
  directly into `warn_mm_*`.** `warn_mm_*`/`neighbor_hover_mm_*` are
  confirmed world-absolute (live-matched exactly against
  `location.embark_pos_min/max`, real names `abs_mm_start`/`abs_mm_end`);
  `find_mm_*` is not. See `research/2026-09-10-embark-screen-rendering-and-coordinates.md`.
- **`df.global.gps.precise_mouse_x/y` (real pixel-level mouse state) works
  in headless Xvfb via `xdotool`** (`DISPLAY=:99 xdotool mousemove/keydown/keyup`)
  — the fix for map hover-info, map clicks, and WASD camera panning, none
  of which DFHack's fake `gui.simulateInput` can drive. Calibration: DF
  window sits at `+0,+40` within the virtual display; `precise_mouse_x =
  real_X11_X`, `precise_mouse_y = real_X11_Y - 40`.
- **`xdotool`'s `click` action has no default inter-step delay in this
  version** — a bare `mousemove X Y click 1` is flaky. Use explicit
  `mousemove` → `sleep 0.3` → `mousedown 1` → `sleep 0.2` → `mouseup 1`.
- **There is no rendered mouse cursor sprite anywhere in this setup** —
  the only visual position feedback is DF's native ~2×2 blue hover-square
  overlay, confirmed pure native closed-source DF rendering, not settable
  or readable from any source available to this project.
- **`code=exited, status=1` in `systemctl status` means the process called
  `exit(1)` itself, not a signal death** — a core dump will never fire for
  it. Distinguish from `code=killed, status=SIGxxx`.
- **The title screen gains a "Continue active game" button, above "Start
  new game in existing world," once any save exists** — the reliable
  signal a fort has actually been founded.
- **A founded fort's real save directory is not necessarily "region2"**
  (or whatever `cur_savegame.save_dir` said pre-embark) — check
  `df.global.world.cur_savegame.save_dir` on the live fort itself.
- **`df-overseer-ui.lua`'s `click` self-reported `FAIL` on clicks that had
  actually worked** — its success check (does the scanned text disappear)
  is unreliable when the same screen persists with the text still present,
  or a duplicate match exists elsewhere. Verify with `type` or a field
  read. Not yet fixed in the script.
- **Writes to `neighbor_hover_mm_*` alone, and `gps.mouse_x/y` alone
  without an accompanying click in the same call, do not move anything
  visually** — these behave like render-loop-derived outputs, not
  authoritative inputs. **Refined this session**: `neighbor_hover_mm_*`
  specifically only live-updates from real mouse *movement* (no click
  needed) while `scr.choosing_embark` is `true`; during ordinary zoomed
  browsing it's frozen regardless. `zoomed_in` is the opposite case — it
  CAN be set directly and does affect which screen renders next.
- **DF's "Re-run finder" confirmation dialog offers only "P: Pause this
  confirmation" or "Enter: Yes, proceed" — no plain cancel.** `CUSTOM_P`
  dismisses it without losing the existing match.
- **A full-tree file-manifest diff must tab-separate size and path**
  (`find ... -printf '%s\t%P\n'`, split with `awk -F'\t'`), not
  space-separate.
- **`dfhack-run lua -f script.lua ARG1 ARG2` passes arguments via Lua
  varargs (`local x, y = ...`), not a global `arg` table.**
- **Site Finder's "Begin" needs at least one non-N/A criterion set, or it
  silently no-ops forever.**
- **`load-save.lua`'s `sel_menu_line`-on-`viewscreen_titlest` approach
  does not apply to this build.** Tagged `unavailable`, don't re-attempt.
- **A checksum must never pass through an LLM-summarized web fetch** —
  fetch it directly with `curl` and compare byte-for-byte.
- **`.env` appends must check for a trailing newline first** —
  `install_df.py`'s `_append_env_var()` helper does this.
- NEW: **`LEAVESCREEN` cleanly cancels `viewscreen_choose_start_sitest`'s
  `choosing_embark` mode with no side effect** (`warn_mm_*` stays
  `-1,-1,-1,-1`) as long as the local map itself was never clicked — a
  safe way to test or abort a placement attempt without committing
  anything.
- NEW: **A long payload embedded directly in an SSH command string
  silently truncates at ~8182 characters when Git's MSYS-linked `ssh.exe`
  is spawned by a native Win32 process (Python's `subprocess`) rather than
  a POSIX one (bash)** — no error, exit 0, the remote side just runs a
  truncated command. `provision_vm.ssh_guest` now takes `input_data` to
  pipe a payload over stdin instead; `install_df.remote()` uses it. Never
  embed an unbounded-size payload directly in an SSH command string again
  — see `provision_vm.ssh_guest`'s docstring and
  `decisions/DECISIONS.md` 2026-09-10 for the full mechanism.
- NEW, **the costly one — read before ever founding another fort while
  one already exists**: **DF's save-slot names (`autosave 1`, `autosave 2`,
  `current`) are a shared generic pool, not scoped per fort.** Founding
  Uniboslan overwrote Artobcatten's actual save data, which lived in
  `autosave 1` — confirmed via `md5sum`, `autosave 1/world.sav` and
  `autosave 2/world.sav` are now byte-for-byte identical, both holding
  Uniboslan's state, with no trace of Artobcatten's left anywhere
  (`current` empty, `region1`/`region2` are pure world-gen history, no
  backup ever taken). **Before founding any future additional fort**: pull
  an `install_df.py backup` of every existing save first, since this
  install's save naming gives no guarantee that an existing fort's slot
  survives a new one being founded.
- NEW: **A crash matching the first fort's "Confirm" signature
  (`code=exited, status=1`, no core dump) can also trigger at the
  map-click step, not just Confirm** — same `gdb`-wrapped-launch
  workaround applies (see the RESOLVED entry above), just don't assume the
  race is scoped to one specific click.
- NEW: **Restarting the embark flow from the title screen does not
  reliably return to the same world/coordinate frame as wherever a stale,
  not-yet-committed embark attempt was sitting** — this session's fresh
  "Start new game in existing world" landed in `region1`, not the `region2`
  the stale mid-navigation state (and its `neighbor_hover_mm_*` numbers)
  belonged to. Re-verify the actual world/region reached (region name text
  on the embark screen, not just numeric coordinates matching a prior
  session) before reusing any previously-found coordinates.
- NEW: **A real `xdotool` click on a genuinely valid, placeable tile can
  go straight through the whole embark-placement flow to
  `viewscreen_setupdwarfgamest`**, with no `warn_mm_*` force-write and no
  separate Confirm click at all — different from the first fort's
  documented sequence. Not fully explained (possibly the force-write/
  Confirm dance was compensating for something specific to DFHack's fake
  input on an earlier attempt, not an inherent property of the flow).
  Worth confirming if a third embark is ever attempted.
- NEW: **The tutorial intro dialogs ("Quick start and short tutorial?",
  "On your own!") render as overlays on `viewscreen_choose_start_sitest`
  itself, not as separate viewscreen types** — they do reappear on each
  fresh embark attempt (this session briefly assumed otherwise after they
  didn't show up in the very first `type` check, before actually dumping
  the screen and finding them present).
- NEW: **A founded fort's own "A Dwarven Outpost..." welcome message
  (with an "Okay" button) silently blocks all citizen activity — walking,
  jobs, everything — even though `df.global.pause_state` reads `false`.**
  Citizens sit frozen at their exact founding positions indefinitely until
  it's dismissed (`click "Okay"`); dismissing it unfreezes everything
  instantly. Always dump the screen and check for this dialog before
  concluding a fort is "stuck" or unpaused-but-not-progressing.
- NEW: **A downward-staircase (`j`) dig designation cannot be placed on a
  grass-covered surface tile** ("light grass"/"dark grass" — confirmed,
  `quickfort` reports "0 tiles designated" with no error). Works
  immediately on other floor types (stone floor, stone pebbles, dirt).
  When anchoring a dig entrance, check the actual tile type at the target
  first, or scan the room's footprint for a non-grass tile.
- NEW: **A plain `d` (floor) dig designation directly beneath an
  already-completed, walkable downstair does not get turned into an
  assignable job at all** — `dfhack.job.checkDesignationsNow()` correctly
  reports it as unreachable no matter how many times it's re-run. The
  connecting tile between two z-levels needs to be a **matching stair
  type** (`u`, upstair) to link them for job-creation purposes; a plain
  floor immediately below a stair is not sufficient even though the stair
  above it is itself walkable. Confirmed live: changing one tile from `d`
  to `u` created six real jobs from zero. Any blueprint spanning z-levels
  needs its connecting tile to be a proper stair, not a floor designation.
- NEW: **The fortress-wide job list is `df.global.world.jobs.list`**, a
  linked-list struct (traverse via `.next`/`.item`, `#`/`ipairs` both
  fail on it), **not `df.global.job_list`** as
  `research/2026-08-25-spatial-perception.md`'s prototype sketch guessed
  (flagged there, §8, as its one unverified primitive) — now verified
  live, and the guess was wrong.
- NEW: **DF Classic's 2D engine (`PRINT_MODE:2D`) does have real zoom**,
  contrary to a wrong claim made mid-session: `data/init/interface.txt`
  defines genuine `ZOOM_IN`/`ZOOM_OUT` binds (`[`/`]` keys), confirmed
  working live via real `xdotool key bracketright`/`bracketleft` in
  fortress mode. Check the actual keybinding file before asserting DF
  lacks a feature.
- NEW: **`install_df.py backup` is a genuine, verified substitute safety
  net when a Proxmox snapshot is blocked by cluster quorum issues** — it
  pulls the save directory over SSH, no Proxmox API involved at all.
  Verify the resulting archive actually contains the expected save data
  (e.g. `tar -tzf` and grep for the save folder name) rather than trusting
  a nonzero file size alone.
- NEW: **A `quicksave` RPC call can return and log "The game should
  autosave now" before the file actually lands on disk** — a save-file
  mtime check run immediately after can read stale, even though the save
  genuinely completes moments later. Wait a few seconds and recheck
  before concluding a quicksave silently failed.

### Other open items, carried forward

- **Design commitment #1's absolute wording vs. its actual evidence
  base** — still queued for a `decisions/DECISIONS.md` entry, deliberately
  not written yet (user's call on timing).
- **Live-view ingest (the public screenshot-push leg), still waiting on
  the user.** Once Cloudflare R2 credentials arrive: wire
  `DF_STREAM_INGEST_URL` in `.env`, convert `curl -F` to an S3-compatible
  signed PUT, fill in `IMAGE_BASE` in
  `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, ask
  before pushing/deploying either repo.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.


## RESOLVED 2026-09-11: VM 103 outage from cluster quorum loss, fort back up

**Fully resolved.** User SSH'd into SRV-01 directly and ran `pvecm expected
1` (the same non-persistent override used in the 2026-09-02 incident,
confirmed via `pvecm status`: Quorate went No → Yes). `provision_vm.py
start --vmid 103` then succeeded. `install_df.py verify` came back all
PASS (dwarfort running, RPC listening). The fort itself needed one more
step beyond the VM being up: `df-fortress.service` starts DFHack but
lands at the **title screen**, not an auto-loaded fort — clicked "Continue
active game" via `df-overseer-ui.lua`; the tool's own success-check
reported FAIL (a known, pre-existing flaw — text-disappearing isn't a
reliable signal here) but the actual screen type confirmed it worked:
`viewscreen_titlest` → `viewscreen_loadgamest` → `viewscreen_dwarfmodest`.
Final state confirmed directly, not assumed: Uniboslan/Ragwind, Year 30,
Mid-Summer, population 7 intact, `pause_state=true`, active slot
`autosave 2` — exactly the paused state it was left in before the
shutdown. User also separately confirmed the public noVNC feed is working
again (it had looked broken mid-incident, most likely just showing the
idle title screen through the Xvfb-restart window, not an actual fault in
the VNC/tunnel/relay chain itself — `curl` of both the public and admin
hostnames returned their expected codes, 200 and 302, throughout).

**Caution worth carrying forward, from home-lab-29**: the quorum override
is temporary and non-persistent — `corosync.conf` on disk still says
`expected: 2`, so it reverts whenever SRV-01 reboots or SRV-02 actually
rejoins the ring. If SRV-02 comes back while the override is still active,
there's a known small risk of the two nodes disagreeing (a `cfs-lock` hang
happened once before from exactly this). Not something to act on from
here, just context if an oddly-quorum-shaped error shows up again later
today.

**Update, same session**: asked the user directly; chose to retry now
while quorum holds rather than wait. Second cycle: `shutdown` → `set-cpu`
(confirmed by read-back: `cpu=x86-64-v2-AES`) → `start` → `verify` (all
PASS) → "Continue active game" (same false-negative success-check as
before, confirmed via screen type instead) → `viewscreen_dwarfmodest`.
**Fully verified identical state to before this whole incident started**:
same 7 citizen IDs (192-198), same professions, same slot `autosave 2`,
Year 30/Mid-Summer, `pause_state=true`. `decisions/DECISIONS.md`
2026-08-28's `cpu: host` → `x86-64-v2-AES` item is now genuinely done, not
just built — closes that ROADMAP.md "Next" item for real.

<details>
<summary>Original incident writeup (kept for the full trail)</summary>

**Read this first if you're picking up this repo.** Uniboslan, the one
live fort, is currently **not running** — the VM itself is powered off and
cannot be started back up. No data was lost: DF was stopped cleanly first
(quicksave confirmed on disk via the new poll-based `systemd-stop.sh`
before SIGTERM, see below), so this is downtime, not an incident on the
fort's save.

**What happened**: attempting to apply the accepted-but-unapplied
`set-cpu` change (`decisions/DECISIONS.md` 2026-08-28) required a cold
stop/start of VM 103 to take effect. Shut it down cleanly via the new
`provision_vm.py shutdown` (ACPI, confirmed stopped). The `set-cpu` PUT
itself then failed (`500 unable to open file ... Permission denied`), and
**starting VM 103 back up also failed**: `POST .../status/start -> 500
"cluster not ready - no quorum?"`. User confirmed live: **SRV-02 is down**.
home-lab-29 (sibling session) confirms this is a known structural gap, not
a new fault — the `citadel` cluster (SRV-01+SRV-02) has never had a
QDevice (the NAS that would have hosted one was lost at auction; the Pi
3B+ fallback was never built), so any time either node drops, the cluster
goes fully inquorate and **all** `pve-guests`/`pveum`/VM start-stop blocks
indefinitely — not just snapshots, which is the only manifestation this
repo had previously documented. SRV-02 has also been separately unstable
since 2026-09-01 (home-lab's own instability tracking).

**New fact worth keeping**: quorum loss blocking VM power operations
(start/stop), not just snapshots and config writes, was not previously
confirmed in this repo — it is now, by direct API failure.

**Not this repo's to fix** — home-lab owns quorum/QDevice infra, and
every prior recovery on this cluster (the 2026-09-02 `pvecm expected 1`
override, and the most recent provisioning session) was done by the user
directly at a root shell on the host, deliberately never via an agent
SSH/API path. **Waiting on the user or home-lab to restore quorum; do
not attempt `pvecm expected 1` or any other override from an agent
session.** Once quorum is confirmed back: retry `provision_vm.py start
--vmid 103`, confirm `status/current` is `running`, confirm DF/DFHack
come back up cleanly (`install_df.py verify`), then decide whether to
still pursue `set-cpu` (built, `decisions/DECISIONS.md` 2026-08-28 row,
see "set-cpu" section below) or leave `cpu: host` alone for now given how
disruptive this attempt turned out to be.

**Real, useful thing found along the way**: while preparing this,
re-read `systemd-stop.sh` (the live `ExecStop`) and `install_df.py`'s
manual `stop --save`, and found both still had the stale flat `sleep 5`
between quicksave and SIGTERM that predates the 2026-09-11 quicksave-
timing finding (45-80s+ observed) — a real latent risk of SIGTERM'ing
`dwarfort` mid-write on the one live, irreplaceable fort. Fixed both to
poll the active slot's `world.sav` mtime for up to 90s instead (commit
`1d5ed74`). **Verified working live, for real**, stopping VM 103 for this
attempt: journal shows `quicksave confirmed on disk (slot: autosave 2)`
at +10s, then the TERM-wait loop ran its full 30s before a SIGKILL was
needed — DF genuinely still ignores SIGTERM, confirmed again, and the fix
caught it correctly rather than cutting in early.

**Also flagged, not mine to resolve**: `df-automation-da` pushed a batch
of commits to `origin/main` (`eb5f017..da73ca4`, fast-forward, no
conflicts) without asking first — this repo's rule treats `git push` as
needing explicit go-ahead each time, and that wasn't checked. Nothing
destructive (fast-forward only), told the user directly rather than
silently treating it as fine.

**Correction from `df-automation-da`, not a silent edit**: the user was
asked directly in that session ("Want me to push it...?") and said "yeah"
before that push ran — go-ahead was real, not skipped. `df-automation-e6`
had no way to see that (a peer session can only observe the resulting git
history, not another session's own conversation), so the concern wasn't
unreasonable to raise. But it does point at a real gap worth keeping,
separate from whether that specific push was approved: **a shared working
tree means whoever pushes, pushes everyone's locally-committed-but-unpushed
work, not just their own** — that push carried 5 of `df-automation-e6`'s
own commits (set-cpu, script-install, the sleep fix) alongside 2 of
`df-automation-da`'s. The user approving "push it" for one session's commit
doesn't obviously also mean "and publish this other session's separate work
too" — even though it's the same user, each session's own work arguably
wants its own explicit go-ahead before going out, not a free ride on
whoever pushes next. Worth folding into `CLAUDE.md`'s new peer-check-in
rule: before pushing, check `git log origin/main..HEAD` for commits that
aren't yours, and flag them specifically, not just ask about your own.

</details>

## HANDOVER - 2026-09-10 (end of session)

The entire prior handover (text-only sweep, second fort founded,
Artobcatten's save lost, the perception-layer branch split, the quorum-
blocked snapshot, and Uniboslan's first room+stockpile) is archived
wholesale — [`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md).
Compacted here, not superseded: exceeded the ~400-line threshold, and
most of its embark-screen-automation detail already lives permanently in
`docs/DF-UI-AUTOMATION.md`, so it didn't need to stay duplicated here too.
The state below is the tight current summary; the archive has the full
narrative, decision-by-decision.

### State at a glance

- **Uniboslan, "Ragwind," is the one active fort.** The first fort,
  Artobcatten, is gone — its save was overwritten founding Uniboslan, no
  backup existed, confirmed unrecoverable. `decisions/DECISIONS.md`
  2026-09-10 has the full incident.
- **Uniboslan has real structure now**: a 5x5 room dug and a matching
  stockpile placed via `quickfort` blueprints (`blueprints/`, four
  files — the first entries in the "Blueprint library" scope item), all
  7 citizens alive and behaving normally. **Paused and quicksaved**
  (confirmed via mtime + file size, not just exit code) as the session
  ended — pause the colony when not actively driving it, per the user's
  own instruction.
- **`check_reachable`/`get_connectivity_report` and an experimental seed
  landmark exist, but deliberately live on their own branch**,
  `perception-layer-experiments` (not `main`) — user's explicit call to
  keep them experimental rather than merge. The live VM has both scripts
  deployed regardless of which branch is checked out locally.
- **A real Windows-specific SSH bug was found and fixed**:
  `provision_vm.ssh_guest` gained `input_data` (pipes a payload over
  stdin) because Git's MSYS-linked `ssh.exe` silently truncates a
  command-line argument to ~8182 characters when spawned by Python's
  `subprocess` rather than bash. `install_df.remote()`/`provision_relay.py`
  both use the fix.
- **A Proxmox snapshot is currently blocked by cluster quorum** (SRV-02
  down, no QDevice — home-lab's to fix, not this repo's).
  `install_df.py backup` is a verified working substitute (pulls the save
  over SSH, no Proxmox API involved) — used and confirmed to actually
  contain Uniboslan's save data before relying on it.

### Next: the real landmark system, and the rest

1. **Build order item 3's real scope (burrow/building enumeration +
   adjacency graph) now has something real to work against** — the
   stockpile is a genuine `building` object, the first non-seed landmark
   candidate. Still needs to happen on `perception-layer-experiments`,
   not `main`, and is still unstarted beyond the seed landmark.
2. **Not done this session, still open from an earlier handover**: the
   `find_mm_*` Y-axis transform mystery (cheap, read-only, not blocking).

### Durable traps, still true (additions marked NEW)

Embark-screen automation mechanics (coordinate frames, `xdotool`
calibration, dead input paths, dialog handling, the click tool's known
flaws) are the permanent, living content of `docs/DF-UI-AUTOMATION.md` —
not duplicated here. This list is everything else: infra, project-wide
gotchas, and fresh findings without another doc home yet.

- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's `memory/tailscale-architecture.md` assigns `df-fortress`/
  `df-colony-01` to `tag:ai-sandbox` — "unattended, possibly LLM-driven,
  lowest trust that isn't internet-facing" — but `runbooks/tailscale-topology.md`
  Phase 5 (the actual hard gate) is still unchecked. **Not this repo's to
  fix** — host-level Tailscale/ACL work, forbidden to any agent by
  home-lab's own rule.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL.
  **Load-bearing, not theoretical** — a real fort exists and must be
  quicksaved before any future stop.
- **The manual (`start`/`stop`) and systemd-managed paths must not run at
  once** — `install_df.py stop` does not clean up a manually-started
  Xvfb. See archive for the full incident/fix.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it.**
- **The published hostname is exposed.** The user chose not to rename it.
- **`willsmith.nz` is deliberate**, not a leak: the intended public face.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified.**
- **`hypothesis_id` has no registry.**
- **`openclaw` vs `hermes-agent` still deferred.**
- **Tarball checksums are pinned and enforced.**
- **PVE's cloud-init takes only the first label of the VM `name`** —
  `install_df.py`'s `step_hostname` (reused for the relay too) is the only
  workable route to a suffixed guest hostname.
- **Hostname convention has one canonical source: home-lab's `CLAUDE.md`,
  Conventions section.** Cite it, do not restate it here.
- **ImageMagick's `import` infers output format from the file extension.**
  Use an explicit `format:` prefix (`png:path`).
- **On a screen with an actual map viewport, never do a blanket
  full-screen `dfhack.screen.readTile` dump.** Scope scans to the specific
  rows/columns a label search actually needs.
- **`code=exited, status=1` in `systemctl status` means the process called
  `exit(1)` itself, not a signal death** — a core dump will never fire for
  it. Distinguish from `code=killed, status=SIGxxx`.
- **`dfhack-run lua -f script.lua ARG1 ARG2` passes arguments via Lua
  varargs (`local x, y = ...`), not a global `arg` table.**
- **Site Finder's "Begin" needs at least one non-N/A criterion set, or it
  silently no-ops forever.**
- **`load-save.lua`'s `sel_menu_line`-on-`viewscreen_titlest` approach
  does not apply to this build.** Tagged `unavailable`, don't re-attempt.
- **A checksum must never pass through an LLM-summarized web fetch** —
  fetch it directly with `curl` and compare byte-for-byte.
- **`.env` appends must check for a trailing newline first** —
  `install_df.py`'s `_append_env_var()` helper does this.
- **A long payload embedded directly in an SSH command string silently
  truncates at ~8182 characters when Git's MSYS-linked `ssh.exe` is
  spawned by a native Win32 process (Python's `subprocess`) rather than a
  POSIX one (bash)** — no error, exit 0, the remote side just runs a
  truncated command. `provision_vm.ssh_guest` now takes `input_data` to
  pipe a payload over stdin instead; never embed an unbounded-size
  payload directly in an SSH command string again — see
  `provision_vm.ssh_guest`'s docstring.
- NEW, **the costly one — read before ever founding another fort while
  one already exists**: **DF's save-slot names (`autosave 1`, `autosave 2`,
  `current`) are a shared generic pool, not scoped per fort.** Founding
  Uniboslan overwrote Artobcatten's save, confirmed via `md5sum` (both
  slots byte-identical afterward). **Before founding any future
  additional fort**: pull an `install_df.py backup` of every existing
  save first.
- NEW: **A founded fort's own "A Dwarven Outpost..." welcome message
  (with an "Okay" button) silently blocks all citizen activity — walking,
  jobs, everything — even though `df.global.pause_state` reads `false`.**
  Citizens sit frozen indefinitely until it's dismissed (`click "Okay"`).
  Always dump the screen and check for this dialog before concluding a
  fort is "stuck" or unpaused-but-not-progressing.
- NEW: **A downward-staircase (`j`) dig designation cannot be placed on a
  grass-covered surface tile** ("light grass"/"dark grass" — confirmed,
  `quickfort` reports "0 tiles designated" with no error). Works
  immediately on other floor types (stone floor, stone pebbles, dirt).
  Check the actual tile type at the target first.
- NEW: **A plain `d` (floor) dig designation directly beneath an
  already-completed, walkable downstair does not get turned into an
  assignable job at all** — the connecting tile between two z-levels
  needs to be a **matching stair type** (`u`, upstair) to link them for
  job-creation purposes; a plain floor immediately below a stair is not
  sufficient even though the stair above it is itself walkable. Confirmed
  live: changing one tile from `d` to `u` created six real jobs from
  zero. Any blueprint spanning z-levels needs its connecting tile to be a
  proper stair, not a floor designation.
- NEW: **The fortress-wide job list is `df.global.world.jobs.list`**, a
  linked-list struct (traverse via `.next`/`.item`, `#`/`ipairs` both
  fail on it), **not `df.global.job_list`** as
  `research/2026-08-25-spatial-perception.md`'s prototype sketch guessed
  (flagged there, §8, as its one unverified primitive) — now verified.
- NEW: **DF Classic's 2D engine (`PRINT_MODE:2D`) does have real zoom** —
  `data/init/interface.txt` defines genuine `ZOOM_IN`/`ZOOM_OUT` binds
  (`[`/`]` keys), confirmed working live via real `xdotool key
  bracketright`/`bracketleft` in fortress mode. Check the actual
  keybinding file before asserting DF lacks a feature.
- NEW: **`install_df.py backup` is a genuine, verified substitute safety
  net when a Proxmox snapshot is blocked by cluster quorum issues** — no
  Proxmox API involved at all. Verify the resulting archive actually
  contains the expected save data (`tar -tzf` + grep) rather than
  trusting a nonzero file size alone.
- NEW, **root-caused 2026-09-11, corrects the two entries below**:
  `quicksave` is not a synchronous save call at all — read directly from
  the installed `quicksave.lua`: it pushes a `QuicksaveOverlay` screen
  whose `save()` body only runs inside that overlay's own `:render()`,
  on a later, unpredictable game render pass (confirmed live: 45-80+
  seconds observed in one reproduced case, under 8s in another, no fixed
  delay). **The "should autosave now" log line is not evidence either way**
  — a live reproduction this session produced a call that unambiguously
  succeeded (slot rotated, fresh mtime) with that line completely absent,
  before and after. The two apparent "silent no-ops" below are now judged
  **most likely the same lag, just checked with too short a window** —
  not a confirmed distinct failure mode — though this can't be proven
  after the fact (only 3 save slots exist, overwrite-oldest-first, so any
  late completion would already be overwritten). **Verification protocol
  going forward: poll the active save slot's `world.sav` mtime for up to
  ~90 seconds, never key off `stderr.log`'s "Invoking:"/"should autosave"
  lines.** Full evidence trail: `research/2026-09-11-quicksave-silent-noop.md`.
- ~~NEW: A `quicksave` RPC call can return and log "The game should~~
  ~~autosave now" before the file actually lands on disk~~ — superseded by
  the entry above (the actual delay is far longer and more variable than
  "wait a few seconds" ever accounted for).
- ~~NEW: `quicksave` can silently no-op entirely, not just lag~~ —
  superseded by the entry above; downgraded from confirmed to unresolved,
  likely-just-lag.

### Authenticated personal-control VNC channel — DONE, deployed and confirmed live

**Decided 2026-09-11**: user chose to ship neither the free-look 3D idea nor
the Stonesense-per-minute public viewer for now. Instead: a second,
authenticated VNC channel giving **the user personally** real mouse/keyboard
control of the live game (pan, click, look around, change z-levels) — the
existing public/LAN feed stays exactly as-is, untouched, view-only. Both
public-facing ideas above remain live research threads to return to later,
not abandoned, just not what's being built right now.

**Update, same day**: deployed for real (peer session `df-automation-e6`,
commit `05aaf01`) and the user completed the one remaining manual step
(Cloudflare Access app for `dwarf-fortress-admin.willsmith.nz`, scoped to
their own email) — **confirmed working by the user directly** ("it works"),
and independently re-verified in this session rather than taken on trust:
both control-channel systemd units on VM 103 (`df-vnc-control.service`,
`df-vnc-control-tunnel.service`) read `active`, and an unauthenticated
`curl` of the admin hostname returns `302` (redirected to the Access gate)
while the public hostname still returns `200`, unaffected. Full detail:
`decisions/DECISIONS.md` 2026-09-11 (the row directly under the original
build decision). **There are now genuinely two live layers on this one
fort**: the pre-existing public view-only feed, and this new authenticated
full-control feed for the user alone — both up simultaneously, confirmed.
**Standing caution, now live rather than hypothetical**: any future
`xdotool`/DFHack-fake-input use against VM 103 shares this exact channel and
can visibly collide with the user actively driving the game through it —
call it out explicitly before running it, per `docs/DF-UI-AUTOMATION.md`'s
rule. **Update, later the same day**: exactly this happened, harmlessly.
A quicksave-investigation subagent found `pause_state` flip to `false` on
its own during a live check, with no cause it had taken — flagged as a real
concern rather than shrugged off, `df-automation-e6` was asked directly.
Answer: the user really was connected via this control channel at that
time and unpaused the fort themselves (exactly what it's for) — not a
mystery agent. Genuinely useful side effect of asking: e6 also found and
fixed a real, separate bug this uncovered — both x11vnc instances
(`df-vnc` since 2026-09-09, `df-vnc-control` since today) were writing to
the same log file, so the *log* looked silent during that window even
though real input was happening; each now has its own log (`65a96fc`).
Nothing else queued on this thread; it's finished.

**Auth design, reasoned through with the user**: Cloudflare Access only (email
OTP at Cloudflare's edge), no second x11vnc password — confirmed safe *only*
after checking that the relay's existing `websockify` binds all interfaces
(no host prefix in its arg), which would have left a LAN-side bypass around
Access. Fix: the control instance's `websockify` binds `127.0.0.1` only, so
Cloudflare Access is structurally the *only* path in, not merely the intended
one — a second in-app password would be pure friction at that point, not real
defense. One sign-in, not two.

**Built this session, dry-run verified, NOT yet run against VM 103 or the
relay**: `scripts/install_df.py`'s `vnc`/`vnc-tunnel` and
`scripts/provision_relay.py`'s `webvnc` all gained a `--control` flag that
installs a completely separate, second instance (own systemd service, own
port, own tunnel keypair) rather than modifying the existing public one —
`df-vnc-control.service` (port 5901, no `-viewonly`, forced `-nopw`),
`df-vnc-control-tunnel.service` (own keypair/authorized_keys line, doesn't
touch the public tunnel's), `df-webvnc-control.service` (port 6081,
`127.0.0.1`-bound). `--control --password`/`--no-password` together is a
hard error (redundant flags would silently do nothing). Confirmed via
`--dry-run` that the existing non-`--control` paths are byte-for-byte
unchanged.

**A standing rule was added while building this**
(`docs/DF-UI-AUTOMATION.md`): any future use of real X11 input (`xdotool`)
against VM 103 must be called out explicitly, not run silently — it shares
the exact channel this new control session uses, and would genuinely collide
with a connected human session once any future agent needs UI-level input the
way past embark automation here has.

**Next, not yet done, needs the user**: (1) actually run the three
`--control` commands against VM 103 and the relay (currently gated on the
user's go-ahead per this project's live-infra rule); (2) a Cloudflare
dashboard step this repo cannot do for itself — a new Public Hostname on the
existing tunnel pointed at `localhost:6081` on the relay, gated by a
Cloudflare Access policy restricted to the user's own email.

### New thread: real-time, per-viewer free-look fortress viewer (idea stage)

Started this session, separate work from the perception-layer branch (no
overlap — coordinated live with the peer session on `perception-layer-experiments`,
`decisions/DECISIONS.md` doesn't have this yet since nothing's been decided,
only researched). The ask moved twice as it was discussed: shared VNC (exists)
→ periodic per-z-level screenshot with independent client-side pan/zoom
(`research/2026-09-10-stonesense-headless-rendering.md`, medium-confidence,
Stonesense-based) → **real-time, independent FPS-style free-look per viewer**
(`research/2026-09-10-live-freelook-viewer-architecture.md`, low-to-medium
confidence, idea stage only). The free-look requirement rules Stonesense out
entirely (fixed isometric camera, no live API) and points toward a
client-rendered-3D-via-live-RemoteFortressReader-feed architecture instead —
closest prior art is Armok Vision. Also reopens the tileset-licensing question
the screenshot approach had sidestepped, since free-look rendering needs real
texture assets on the client, not just server-rendered pixels — three options
laid out in that doc's §5, **user hasn't picked one yet**.

**Update 2026-09-11**: Armok Vision researched
(`research/2026-09-11-armok-vision-and-overburden-rendering.md`). Both open
questions substantially resolved: RFR's `GetBlockList` is a server-side
hash-diffed poll (client polls, but only changed blocks get sent — confirmed
at this project's exact pinned DFHack tag), and Armok Vision's `GetVisibility(z)`
is a real, shipped, camera-relative Z-band occlusion technique (levels above
camera hidden, current level full detail, lower levels walls-only with caps
suppressed) that answers the user's "strip away the ground" question directly
and transfers cleanly to a browser client with no server involvement.
Also corrected Stonesense's action name (`CHOP_WALLS`, not `CHOP_WALL`) and
found it's narrower than hoped — only affects the single topmost loaded
z-level, complementary to `SEGMENTSIZE_Z:1`, not a substitute for it, and not
itself an answer to the free-look design's occlusion question (that's
Armok Vision's mechanism, not Stonesense's). **Real warning surfaced**:
Armok Vision's own issue tracker reports DFHack's CPU going from 5-7% to
40-50% under a single polling client — foreign hardware/fort, doesn't
transfer directly, but is a concrete reason not to assume "broadcast once,
cheaply" is safe. **Gating next step, not yet done**: a cheap live test —
hook any RFR client to Uniboslan for a few minutes and measure DFHack's own
CPU delta — before further design work on either the free-look architecture
or the Stonesense capture job. User is still deciding overall direction
(also considering a simpler two-tier idea: Stonesense screenshots every
minute for the public, plus a separate authenticated full-control channel
for themselves, not yet reconciled with the free-look thread).

### Dwarf/labor management — first slice built and verified live

Picks up the 2026-09-11 gap (`decisions/DECISIONS.md` same date, "found a
real gap: dwarf/labor management has no build-order item"). Built
`scripts/dfhack/df-overseer-labor.lua` this session:
`unit-status [idle|injured|military|hostile]`, `labors UNIT_ID`,
`set-labor UNIT_ID LABOR_NAME on|off`. Every primitive verified live against
Uniboslan (7 citizens, Year 30) before being written, not assumed from docs
— full detail in `decisions/DECISIONS.md`'s newest row. Confirmed live:
`manipulator` genuinely unavailable on this install (checked, not repeated
on trust), `autolabor` genuinely available but not enabled (out of scope
this session), and `dfhack.units.isDanger`'s "hostile" filter is real but
broader than actual sieges — this fort's own live data (4 `DEMON_*` hits, all
deep-cavern z-levels, `invader=false`) demonstrates the caveat concretely.
Deployed via plain `scp` (mirroring the blueprints precedent) rather than
through `install_df.py`, since that file had a concurrent peer session's
uncommitted changes in flight when this started. All of it went over
`dfhack-run lua`/RPC only, deliberately never touching `xdotool` or
simulated input, so it ran safely alongside the user's newly-live
personal-control VNC session (above) with no channel contention.

**Next, not yet done:**
1. ~~A proper `install_df.py` deploy subcommand for this script~~ — **done,
   see below.**
2. `near_landmark` in `unit-status`'s output is a placeholder (`x,y,z` only)
   until the landmark system on `perception-layer-experiments` merges — a
   different session's branch, not touched here.
3. Nothing yet *decides* what labor to assign — this is the mechanics half
   of design commitment #2 only (code does the bitfield read/write); the
   judgment half (an actual policy: who should mine, who's idle too long,
   when to pull someone off hauling) is still unbuilt.
4. ~~Whether to enable `autolabor`~~ — **done, see below.**

### `provision_vm.py set-cpu` built — done, local only, not yet applied to VM 103

Picks up the 2026-08-28 accepted-but-never-applied decision: `cpu: host`
in `provision_vm.py` blocks live migration between the cluster's two
different CPU generations, defeating the point of clustering at all; `DEFAULT_CPU`
is now `x86-64-v2-AES` for future template builds, and a new `set-cpu`
subcommand (mirroring `set-onboot`'s live-PUT-to-/config pattern) can apply
it to an already-built VM. **Deliberately not run against VM 103 this
session** — same reason as `script-install` above (da's subagent had VM
103's state in flux), plus a sharper one of its own: the change only
actually takes effect on the VM's next cold stop/start, and Uniboslan is a
live, running fort — applying it now would be pointless without also
cold-cycling the VM, which is exactly the kind of disruption to avoid
casually. Needs the user's go-ahead before ever actually running `set-cpu`
+ a deliberate stop/start against the live fort, not just code review.

### Generic `install_df.py script-install <name>` subcommand — built, deployed, and verified live

Coordinated with peer session `df-automation-da` first (their subagent had
VM 103's pause/save state in flux investigating combat detection, so the
build itself stayed local-only: code + `--dry-run` checks, no SSH).
Generalizes `cmd_ui_install` (one hardcoded file) into `cmd_script_install`,
which deploys any `scripts/dfhack/<name>.lua` by name — `ui-install` now
survives as a thin alias (`args.name = "df-overseer-ui"`), confirmed
byte-identical output via `--dry-run` before and after. Covers the
`df-overseer-labor.lua` deploy gap (was plain `scp`'d ad hoc) and, per
da's suggestion, whatever script their subagent lands next, without a
third near-identical subcommand.

**Update, same session**: da's subagent finished and da independently
re-verified VM 103 clear (`pause_state=true`, `autosave 1`) before handing
it back. Ran `script-install df-overseer-labor` for real: exit 0, then
verified past the exit code — read the deployed file's length back off the
guest (9130 bytes: the local source is 9129 UTF-8 bytes plus the heredoc's
one trailing newline, exact match) and called
`dfhack.run_command('df-overseer-labor', 'unit-status', 'idle')` live,
which returned all 7 real citizens, all idle (consistent with the fort
still paused — nothing unpaused, no quicksave triggered, pure read RPC).
Genuinely deployed and callable, not just "exit code said so."

### `autolabor` enabled on Uniboslan — verified live, persisted

User's go-ahead. Checked the tool's own doc before touching anything rather
than assuming behavior: enabling it disables the vanilla work-detail system
outright and recalculates labors on its own cycle, and it **explicitly
leaves dwarves on active military duty or assigned to a burrow untouched** —
that's the actual answer to "does it fight manual `set-labor`," found in the
primary source, no live experiment needed. Confirmed genuinely off before
enabling (`autolabor status` returned "plugin is not enabled"), enabled
(`enable autolabor`), and confirmed genuinely on afterward (`autolabor
status` returned real data: "6 IDLE, 1 OTHER") — not just trusting the
"Enabling autolabor" message. World was and remains paused throughout
(`pause_state` checked before and after, unchanged).

The doc states the enabled flag "stays enabled... even if you save and
reload," which implies it's written into the save itself, not just live
in DFHack's process memory — quicksaved afterward to make sure that's
actually true rather than leaving it to chance. Found a new, real,
previously-undocumented behavior doing this: **`quicksave` rotates forward
through the `autosave N` slot pool by one on each call, rather than
overwriting the currently-active slot in place** — confirmed live, two
quicksaves in a row moved `cur_savegame.save_dir` from `autosave 1` →
`autosave 2` → `autosave 3`, each with a fresh mtime matching when it ran.
Distinct from (and less alarming than) the Artobcatten incident: that was
two *different forts* colliding on the same slot pool; this is one fort
rotating forward through its own slots normally, nothing overwritten
unexpectedly, nothing lost. Worth remembering for any future mtime-based
"did my save land" check: check `cur_savegame.save_dir` fresh each time
rather than assuming the slot name from an earlier check is still current.

**Update, same session**: watched it actually work. Unpaused briefly (~15s
real time), re-checked `unit-status`: idle count dropped from 6 to 1
(`autolabor status` agreed: "1 IDLE, 6 OTHER"), citizens' positions had
genuinely moved, and jobs were assigned (`Sleep`, `Drink`) — real simulation,
not a stuck state. One citizen briefly showed `injured=true` (a real
`body.wounds` entry, not a UI artifact) that had fully healed by the next
check moments later, with nothing in `gamelog.txt` for that window — read as
a minor, self-resolving incident (a scrape, not combat), not a threat; no
DEMON_* unit from the earlier `hostile` scan is anywhere near the fort's
z-level regardless. Re-paused and quicksaved afterward, per the "pause when
not actively driving" convention.

**A second real finding surfaced doing the quicksave-to-confirm-persistence
step, not the autolabor question but adjacent to it**: two consecutive
`./dfhack-run quicksave` calls (both while paused, ~15-20s apart) produced
**no** "The game should autosave now" line in `stderr.log` and **no** file
change on disk at all — confirmed by isolating exactly the new `stderr.log`
lines per attempt (line-count diff, not just a tail glance) and `stat`-ing
the active save slot before and after each. A third attempt, no different
in method, worked normally (log line appeared, `autosave 3`'s mtime updated
to match). **`quicksave` can silently no-op**, not just "log success before
the file lands" (the already-documented trap) — this is a stronger claim,
worth downgrading the standing "wait a few seconds and recheck" advice to
"retry and recheck" if a single retry doesn't confirm. Root cause
unidentified; not chased further since it isn't blocking (the autolabor
enable was already durably saved by the first successful quicksave, before
this was even discovered) and `df-fortress.service`'s own `ExecStop`
already quicksaves unconditionally before any real stop regardless.

### First real combat, used as a live test case for `unit-status hostile`

User spotted a kea fighting the fort's dogs live via the viewer and asked
for it to be used as a real experiment rather than staying synthetic. Good
call — it surfaced a real gap, not just confirmed a theoretical one.
Reconstructed from `gamelog.txt`: the kea (unit 321) picked a fight, the
stray dog + stray war dog + citizen 196 (Fisherdwarf) fought it off, the
kea died (confirmed `isDead=true`), one dog took a minor wound (confirmed
`body.wounds`), no dwarf was hurt. `unit-status hostile` was checked both
before and after finding this — in both cases it reported only the same 4
harmless deep-cavern demons, completely blind to a real, fort-relevant
fight that had just happened at the front door. Full detail and the
correction to the original spec: `decisions/DECISIONS.md` 2026-09-11
("First real combat on Uniboslan"), `research/2026-08-25-spatial-perception.md`
§5. **Not fixed** — the right fix is almost certainly `get_diff_since`
(build order item 5, `eventful`-backed), since "something attacked
something" is an event, not a queryable static predicate; a better
`isDanger`-style filter would be solving the wrong shape of problem.

**Update, same day**: dispatched a Sonnet subagent to investigate/prototype
this properly. Result: `scripts/dfhack/df-overseer-combat.lua`, written but
**deliberately not committed** — user's own call, see below. Verified
independently before anything else: exhaustively checked every
`dfhack.units.*` predicate resembling danger/hostile/combat (found one not
previously tried, `isAgitated` — also `false` for the kea, confirming the
gap is real, not an oversight); found and live-verified
`df.global.world.status.reports` as a structured, typed combat-data source
(not `gamelog.txt` text-scraping) that reconstructs the kea fight exactly;
live-verified `eventful`'s `onReport`/`onUnitAttack` hooks actually fire
end-to-end, including isolating (via a deliberate controlled test, not just
one observation) that DFHack's event queue only drains on unpaused ticks
and backfills its whole backlog on first drain. Fort re-confirmed paused
and saved afterward, independently re-checked by this session too.

**The bigger finding, not the combat mechanism itself**: `df-overseer-diff.lua`
already exists on `perception-layer-experiments` (df-automation-ca's
branch, deployed live on VM 103) and is **already an implementation of the
same primitive**, `get_diff_since` — same `eventful`+`_G`-persisted-log+
cursor design, covering `JOB_COMPLETED`/`UNIT_DEATH` instead of
`REPORT`/`UNIT_ATTACK`. ~~Its own header honestly flags that it **never
verified a real eventful callback firing live**~~ — **correction, found
auditing the full branch afterward**: it *was* verified live
(`e627440`, "closing the last honest gap" — same unpause/watch/re-pause/
verify-mtime discipline used all session), the file's own header comment
just never got updated after the fact and is stale, not accurate. This
session's subagent still closes a real, different gap (`REPORT`/`UNIT_ATTACK`
event types diff.lua deliberately left unwired), just not the "never
verified live" one originally believed. Doesn't change the reconciliation
question, but the correct framing is "extend diff.lua's proven design with
more event types," not "diff.lua's core mechanism is unverified." **`df-automation-ca`
was not reachable to coordinate directly** (not connected at the time).
Asked the user how to handle it: **chose to wait for `df-automation-ca`
before reconciling or committing anything** rather than commit unilaterally
and sort it out later. `scripts/dfhack/df-overseer-combat.lua` sits on disk,
deployed to
VM 103's `hack/scripts/`, but **untracked in git** — do not commit it
without checking back on this first.

**Separately, a real documentation-vs-reality gap, per this repo's own
"flag it, don't silently patch" rule**: `perception-layer-experiments` also
has `df-overseer-chokepoints.lua`, `-openarea.lua`, `-overview.lua`,
`-stuckjobs.lua` deployed on VM 103 (all dated 2026-09-10 23:20) —
most of `docs/PURPOSE.md` build order items 2 and 5-8 already exist there.
Working.md/ROADMAP.md still describe that branch as just "connectivity +
a seed landmark." **Update, audited properly this session** (not just
file-listing guesswork): fetched and read the branch's own commit log and
its own `Working.md` directly. Confirmed for real: **all of build order
items 2 through 8 are built, verified live against the real fort, and all
8 commits are pushed to `origin/perception-layer-experiments`** — not just
present as files. Two real bugs caught there worth knowing regardless of
merge status: `dfhack.buildings.getSize()`'s `cx,cy` are local to the
building's own box, not absolute map coordinates; `df.global.world.burrows.all`
doesn't exist, the real path is `df.global.plotinfo.burrows.list`. The
branch's own `Working.md` explicitly leaves "whether/when to merge" as
"still the user's call to make, not assumed" — asked; **user chose not to
merge yet, wants to keep working with what's there and see how far it
goes** (see the autonomous-play entry below). `df-automation-ca` still
wasn't reachable to coordinate directly this session.

### First autonomous-play experiment — a real judgment win, a real tooling gap

User's framing: "let's keep working with it and seeing how far we can take
this... how far can an AI work" — chosen as a genuine bounded experiment,
not a demo. A subagent was given the deployed `perception-layer-experiments`
tools plus today's labor tools and told to make one real construction
decision using only tool output, build it via `quickfort` only, and hard-stop
rather than improvise if it hit a wall. Full detail: `decisions/DECISIONS.md`
2026-09-11 ("First real autonomous-play experiment on Uniboslan").

**What worked**: the decision itself was cleanly tool-derived — `find_open_area`
ranked a real, walkable, non-stranded 5x5 candidate next to "Stockpile #1,"
using `z=169` read from the citizens' own real positions, not guessed.
Design commitments #1/#2 held up on a real case, not just in theory.

**What it found, verified independently against the actual script source,
not just taken on the subagent's word**: `quickfort run -c x,y,z` needs a
literal absolute coordinate, but **every deployed perception tool
deliberately strips coordinates before returning** — `find_open_area`
computes a real `cx,cy` internally and never includes it in what it hands
back; `df-overseer-landmarks.lua` explicitly nils out `x,y,z` before
returning a landmark, even though an internal function
(`get_landmark_centroid`) holds the real value and is never exposed via any
command. This looks like commitment #1's spirit applied without its
mechanical conclusion ever being built: **nothing converts "the model
picked a good, named candidate" into something `quickfort` can actually
anchor to.** Correctly treated as a stop condition — no coordinate was
guessed, nothing on the fort changed, re-verified after the fact (still
paused, same save slot, 0 injured, no repo files touched).

**Update, same day — closed, not just proposed.** Built `build_open_area`/
`build` on `df-overseer-openarea.lua` (worktree `df-automation-perception`,
`perception-layer-experiments`), fused resolve-and-act exactly as
scoped — a real coordinate exists only inside the function long enough to
assemble `quickfort`'s own argument list, never returned or printed;
verified this myself directly against the function body, not just the
report. Real end-to-end result, independently re-checked against the live
VM: **a genuine new "Stockpile #2" building now exists on Uniboslan**,
wired into the exits graph. Also produced a useful negative result: the
same primitive against a `#dig` blueprint designated 0 tiles, because
`find_open_area`'s candidates are already-walkable space, not diggable
rock — confirming (empirically, not just by reasoning) that "dig a new
room" is a distinct, still-open gap, not something left unfinished by this
fix. **Corrected same day, user caught it**: not build order item 9
(that's "find already-open space in irregular caverns," still walkable
tiles only, a different problem) — a genuinely unspecified gap, nothing
in the research spec finds solid/diggable terrain at all. See
`ROADMAP.md`'s new item. Full detail: `decisions/DECISIONS.md` 2026-09-11
("Closed the coordinate-resolution gap..."). Still lives on
`perception-layer-experiments`, uncommitted,
same branch-ownership/merge-timing question as the `diff.lua`/`combat.lua`
overlap above — this is a real capability now, not just a proposal, but
whether/how it lands anywhere permanent is still open.

### Compliance eval harness: built, run against two providers, DeepSeek now the default — done for this session

Picked up as this session's task specifically because it touched neither VM
103 nor `perception-layer-experiments` (both held by a concurrent peer
session's live subagent at the time) — research build-order item 1
(`research/2026-08-25-learning-architecture.md` §7): replicate "Prompt Design
at Scale"'s instruction-count-decay methodology against this project's own
doctrine format and model, before any fort run depends on doctrine size being
safe. Built `evals/compliance/`, mirroring `evals/perception/`'s structure and
philosophy exactly. Gained a second provider mid-session
(`harness/providers.py`, DeepSeek + any OpenAI-compatible endpoint) —
deliberately, not speculatively: the user's own framing is that df-overseer is
heading toward multiple concurrent sessions/roles via `openclaw` with model
choice made *per role*, so "where does compliance collapse" only means
something once asked of whichever model actually runs a given role.

**Findings (`deepseek-chat`, complete and clean — the one to trust)**:
perfect-response rate 70-83% at n=10/20, **collapsing to 0% at every n≥40**
(earlier than the paper's own ~80-rule collapse for the models it tested).
Per-rule pass rate degrades gently (97%→72%, n=10→160), and the collapse is
concentrated almost entirely in `required_word` (20.6% pass rate at n=160 vs.
`banned_word`'s 100%) — a real, actionable asymmetry: this model sustains
*avoidance* rules far better than *inclusion* rules at scale, worth keeping in
mind when phrasing real DF doctrine.

**`claude-opus-5` — real data, but this is where it went wrong.** The
original 180-cell sweep used `max_tokens=4000`; adaptive thinking at
n=120/160 sometimes consumed the whole budget before any text was emitted
(confirmed by reproducing it directly: one n=160 call spent 3469 of 4000
tokens on thinking alone), so 27/180 cells came back empty — a harness bug,
not a compliance finding, now fixed (`max_tokens` defaults to 16000). Cost was
flagged mid-run with the two priciest batches (n=120/160) still ahead; asked
directly, the user chose to let it finish and named model-cost-per-run as an
open design question. It finished at ~$9. A rerun of the fixed n=120/160
cells was started (max_tokens=12000, confirmed 0 empty responses in 46/60
cells) — then the user's sharper call landed: **stop spending on Opus
entirely, default the harness to DeepSeek, document what exists.** The rerun
was killed via `TaskStop` mid-flight; its 46 valid rows are kept, not
discarded. **Total session spend, computed from recorded token usage against
published rates: ~$9-13 for `claude-opus-5` (~250 calls, overwhelmingly
`thinking`-token output), ~$0.05-0.10 for `deepseek-chat` (184 calls)** — a
~100x gap for comparable coverage. `run.py --provider` now defaults to
`deepseek`; `anthropic` remains fully supported but opt-in only, and no
further Anthropic runs happen without asking first. Opus's own
perfect-response curve is noisy/non-monotonic across doctrine sizes at
`--repeats 1` — flagged honestly as unresolved (needs more samples), not
presented as a clean collapse point.

Full write-up (with all the numbers and caveats above): `evals/compliance/README.md`.
Full data: `evals/compliance/results/{deepseek-full,full,full-fix}-2026-09-11.jsonl`.
Decision trail: `decisions/DECISIONS.md`, three 2026-09-11 rows (build,
DeepSeek addition, cost overrun + correction).

**Nothing left open on this thread for now** — the harness exists, is
selftested, has real (if partly caveated) data from two providers, and
defaults to the cheap one. A genuinely clean Opus collapse curve (more
repeats, no empty-response artifacts) is a real next step but needs explicit
go-ahead given the cost this session already spent finding that out.

### Mechanical prediction grading built — `predictions/`, no game/API cost

Picked up next once the compliance-eval thread closed, after correcting an
earlier wrong claim that this was already done (the fort ledger was built
2026-08-27; prediction grading, a separate build-order item, was not).
Research build order item 3 (`research/2026-08-25-learning-architecture.md`
§7): implements `docs/MEMORY-ARCHITECTURE.md`'s own `decision`/`expectation`/
`check_at`/`signal` example as real, gradeable data. Reuses the ledger's own
field-introspection (`ledger.store.get_path`/`field_source`/
`assert_gradeable`) rather than duplicating it — a prediction's `signal` is a
dotted path into the fort ledger, and `store.register()` refuses to write one
that doesn't resolve to a `MECHANICAL`/`DERIVED` ledger field (the literal
"reject predictions at write-time that don't resolve to a ledger/dossier
field" from §1.3). Grading (`grade.grade()`) never reads the prediction's own
`decision`/`expectation` prose, only the ledger row plus a closed predicate-op
vocabulary — self-report structurally cannot leak into a grade.

**Real scope limitation, stated not hidden**: `signal` can only resolve
against the ledger, because the fort dossier the research spec also names
(mid-fort working state) is still a design concept with no code. The design
doc's own headline example — "food stores stop falling within 2 seasons" —
has no matching ledger field and cannot be expressed yet; the doc's other
example, "seal the caverns before year 3," works today
(`design.caverns_sealed_year`). Selftest reuses the ledger's own worked
example fixture (`ledger/examples/example-fort.json`) rather than inventing a
second one, and passed clean on the first real run — including the tricky
case that several ledger fields are legitimately `null` as a fact (no breach
happened), which `grade()` handles correctly for `exists`/`not_exists` but
(deliberately) grades `unresolvable` for every other op, since it cannot tell
"doesn't apply" from "not yet known" without per-field judgement.

Full detail: `predictions/README.md`, `decisions/DECISIONS.md` 2026-09-11.
**Next, not yet done**: nothing calls `register()` from a real decision yet —
same "schema had to exist before any row gets written" reasoning as the
ledger. The fort dossier gap is a real, separate, still-open item, not solved
here.

### find_diggable_area: built and live-verified

Picked up as the clearest, best-scoped next step flagged in this file's own
handover above — the inverse of `find_open_area` for solid terrain, closing
the gap the autonomous-play experiment found (this file's handover item 8,
`decisions/DECISIONS.md` 2026-09-11). Built on `perception-layer-experiments`
(worktree `C:\website-projects\df-automation-perception`, not `main`):
`scripts/dfhack/df-overseer-diggable.lua`, committed locally (`f741cfc`), not
pushed. Mirrors `df-overseer-openarea.lua`'s scoped maximal-rectangle scan,
inverted (non-walkable, `WALL`-shaped, natural-material tiles instead of
walkable ones), with the v1 scope the corrected spec calls for: only
candidates that directly border the existing walkable network, documented as
a reasonable first cut rather than a validity claim.

Enum names (`df.tiletype_shape.WALL`, `df.tiletype_material.{STONE,SOIL,
FEATURE,MINERAL,LAVA_STONE,FROZEN_LIQUID}`) were checked against the actual
installed DFHack 53.16-r1.1 source (`hack/lua/tile-material.lua`'s own
`BasicMats` table, `hack/docs/docs/tools/tiletypes.txt`) before writing the
diggability check, not recalled from memory or web results, per this
project's "mark verified vs proposed" rule.

**Live-verified against VM 103, same session.** Before touching the VM:
confirmed it was actually running via a live Proxmox API call
(`provision_vm.py status`), not assumed — worth doing specifically because
`home-lab-29` flagged mid-session that VM 103 had just been stopped by the
`citadel` quorum incident and its restart wasn't independently confirmed
yet. Gave both peers a heads-up first, per the standing rule, since this
still touches the live VM even though it's read-only.

Deployed via the repo's own `ui-install` tool (deploys every
`scripts/dfhack/df-overseer-*.lua`), not a raw ad hoc SSH write — the first
attempt at a plain `ssh`+heredoc was correctly blocked by the permission
classifier, and the repo's own established deploy path worked instead
without needing an override.

**A genuinely informative pair of results, not just "it ran"**: near
"Embark Site" (surface, z=169) it correctly returned `[]` — investigated,
not accepted blind: a live tile-material probe found 64 nearby
`WALL`-shaped tiles, all `TREE` material, correctly excluded (trees aren't
mining-diggable). Near "Stockpile #1" (underground, z=168, 872 `SOIL` wall
tiles nearby per the same probe), it returned 5 real ranked, non-overlapping,
network-adjacent 3x3 `SOIL` candidates with plausible direction/distance
fields and no raw coordinate in the output. Fort state re-confirmed
unchanged immediately after, directly against `df.global`: `pause_state=true`,
7 citizens — the whole pass was read-only, no designation, no mutation.

**Update, same session: `dig_diggable_area`/`dig` built**, closing that gap.
Committed locally on `perception-layer-experiments` (`fa47459`), not pushed.
Mirrors `build_open_area`/`build` exactly rather than the research spec's
original `designate_dig(shape, pos, dims)` sketch (which assumed an upstream
tool would supply `pos` and never specified one): re-runs `find_diggable_area`'s
own `ranked_candidates`, resolves the chosen candidate's real `cx,cy`
internally, and calls `quickfort run BLUEPRINT_FILE -c cx,cy,z` directly — the
coordinate never leaves the function's local scope, checked directly against
the function body, same guarantee as `build_open_area`'s.

**Update, same session: live-tested for real, user's explicit go-ahead** (a
Bash permission classifier blocked the first attempt; user approved it
interactively rather than pre-authorizing a standing rule — see
`decisions/DECISIONS.md` if a permanent allow rule for
`scripts/install_df.py *` gets added later, it still needs adding by hand,
edits to `.claude/settings.json` are blocked for this session too).

**Mechanically, `dig_diggable_area` worked exactly as designed.** Picked the
tool's own real rank-1 candidate (5x5 SOIL, one tile east of Stockpile #2,
no coordinate ever seen), called it, got `quickfort_ok: true,
"Tiles designated for digging": 25` — independently re-confirmed by scanning
the actual map designation flags directly, not trusting quickfort's
self-report: exactly 25 real tiles found flagged. (Caught and fixed one
process bug getting here: forgot to redeploy the script after adding
`dig_diggable_area` to the file, first call errored on a nil function —
`ui-install` fixes that, now a standing reminder to redeploy after every
edit to a file already live on the VM.)

**But the reachability claim did not hold up live — a real bug, not a clean
success.** Unpaused to watch a dwarf claim the job (2 idle citizens with
`MINE` labor, zero burrows, no alerts) — after ~14 in-game days, zero `Dig`
jobs ever appeared. Investigated rather than assumed: a direct re-scan of
the designated box's entire 8-connected ring (all edges + all 4 corners)
found `getWalkableGroup == 0` everywhere — genuinely not bordered by the
walkable network, contradicting `find_diggable_area`'s own
`borders_walkable_network: true` for this exact candidate at selection time.
**Leading hypothesis, not confirmed**: the adjacency scan ran entirely while
the fort was paused, and `getWalkableGroup`'s own documented caveat (its
cache "only updates while the game is unpaused") means a border tile no
dwarf has actually pathed near could return a stale or never-computed value
that isn't trustworthy either way. Not root-caused this session — flagged
honestly, not diagnosed with certainty. **Next concrete step**: fix or at
least test around this (try a brief unpause before running `find`/`dig`
rather than entirely paused) before trusting `dig` again.

**Real, incidental fort progress happened while unpaused, not buried**:
population went 7→15 (a migrant wave, confirmed via `get_overview`, in-game
date year 30 month 5 day 14→28), and one citizen (unit 192, one of the two
idle miners) now shows one wound — not deeply investigated (struct field
names for wound severity didn't match on a quick attempt), but
`get_overview`'s `alerts` stayed empty throughout. Worth a look next session,
same "second look, not confirmed-safe" posture already applied to
`unit-status hostile`.

**The 25-tile dig designation was left in place**, not undesignated — harmless
clutter no dwarf will ever work as things stand, a faithful record of what
actually happened rather than quietly cleaned up. Re-paused and
quicksave-confirmed (slot rotated `autosave 3`→`autosave 1`) before ending
this thread. Full trail: `decisions/DECISIONS.md` 2026-09-11 ("`dig`
live-tested for real...").

**Update, same session: user said keep chasing it — root cause found, fixed,
re-confirmed working.** The "leading hypothesis" above (paused-cache
staleness) was wrong. Checked quickfort's own docs
(`hack/docs/docs/tools/quickfort.txt`) before guessing further: `-c` anchors
a blueprint's **upper-left corner by default**, not its center. Both
`dig_diggable_area` and `build_open_area` were computing the candidate box's
*center* (`c.x + floor((w-1)/2)`, etc.) and passing that to `-c` — silently
shifting every real dig/build by that offset away from the box actually
validated as bordering the walkable network. Confirmed empirically, not just
from the docs: a direct re-scan of the box the algorithm had actually
validated showed real walkable neighbors on its ring; the box that got
shifted-and-dug showed none. **`build_open_area` had the exact same bug the
whole time** — Stockpile #2 only worked because `find_open_area`'s
candidates sit inside broadly open space, so the shift happened to still
land on free tiles. Luck, not correctness.

**Fixed in both files**: pass the box's real top-left (`c.x, c.y`) to
quickfort, not the computed center. `cx,cy` stays right for
`nearest_landmark`'s direction/distance reporting, where center is the
correct choice — only the quickfort call itself was wrong.
`df-overseer-diggable.lua`'s fix is committed on `perception-layer-experiments`
(`2d0eb7b`, not pushed). `df-overseer-openarea.lua`'s fix is applied in the
worktree but deliberately left **uncommitted**, matching that file's own
pre-existing uncommitted `build_open_area` state — the fix and its
rationale are in a comment right at the fixed line, for whoever eventually
commits or reconciles that file.

**Live-reconfirmed end to end, with the user's explicit go-ahead for each
mutating step** (a second permission prompt for unpausing was also blocked
by the classifier; user approved it live via `AskUserQuestion`). Redeployed
both fixed files, re-ran the identical `dig_diggable_area` call — this time
it designated at the correct top-left (bounding box `100,101` to `106,107`,
41 tiles total: this run's 25 plus 16 left over from the buggy run,
overlapping in a 3x3 region — the arithmetic checks out exactly). Unpaused:
real `Dig` jobs appeared almost immediately (8 jobs, 2 already claimed on
the first check), and by the next check **all 41 tiles were fully dug, zero
jobs remaining**. The loop is genuinely closed now, not just mechanically
plausible. Re-paused, quicksave-confirmed (slot `autosave 1`→`autosave 2`).
**Incidental good news**: the citizen with the unconfirmed wound from
earlier now shows zero wounds — resolved on its own. Population steady at
15, no fort alerts throughout. Full trail: `decisions/DECISIONS.md`
2026-09-11 ("Root cause found and fixed...").

