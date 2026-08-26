# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved — don't mark it paused. Any session should read this and know what's
actually going on right now.

## 2026-08-26 (afternoon) — provisioning script written; one human step blocks it

**Done:**

- **SSH key generated and documented.** `~/.ssh/df_overseer_ed25519` — ed25519,
  no passphrase, comment `df-overseer`, fingerprint
  `SHA256:nFmogVJU7sqROeOeudZFcpLow+IXOYRystP9ymBZ0sA`. Dedicated rather than
  reusing `claude_vm`, because a shared key makes revocation indivisible. Paths
  in `.env` (`DF_SSH_KEY`, `DF_SSH_PUBKEY`) and in
  `infra/local.example.env`; full record in `memory/proxmox-access.md`.
  Windows note: `chmod 600` is a no-op on NTFS — `icacls /inheritance:r` is
  what actually restricted it.
- **`scripts/pve.py`** — thin Proxmox API client (env loading, task polling
  with log tail on failure, live node-memory read). Python, not bash, for the
  MSYS path-rewriting reason.
- **`scripts/provision_vm.py`** — `status`, `fetch-image`, `build-template`,
  `clone`. Verified working as far as the blocker below.
- **VM sized 6144 MB / 2048 MB balloon, 4 cores** — user's call, taken with
  5.5 GB free on the host.
- Three API facts learned the hard way and recorded in
  `memory/proxmox-access.md`: the network *list* endpoint hides bridges (use
  `vmbr0`, found by direct GET); cloud-init `sshkeys` must be URL-encoded
  *before* form encoding; and `import-from` rejects `iso`-class volumes.

**BLOCKER — one thing only a human with datacenter rights can do:**

Datacenter → Storage → `ssd_storage` → Edit → **Content: add "Import"**.

The cloud image was downloaded as `iso` content, and `import-from` refuses an
`iso` volume — it needs `images` or `import`. `download-url` *does* accept
`content=import`, so once that box is ticked, `provision_vm.py fetch-image`
re-downloads the 596 MB image into `import/` and the rest runs unattended.
Confirmed by denial that this token cannot do it itself: `GET
/storage/ssd_storage` → `403 (Datastore.Allocate)`. Granting the role
`Datastore.Allocate` is the alternative and was rejected — it permits editing
and deleting storage definitions, which is far more than one flag is worth.

**Re-confirmed 2026-08-26 (evening), provisioning run:** `python
scripts/provision_vm.py fetch-image` was run fresh. Same failure, verbatim:

```
POST /nodes/proxmox/storage/ssd_storage/download-url
  -> 500 {"message":"storage 'ssd_storage' is not configured for
          content-type 'import'\n","data":null}
```

Per the run's own instructions, stopped immediately at this gate — no attempt
to work around it, no storage-config changes, no alternate import path tried.
Nothing beyond this was executed: no VM was created or touched this run, so
there is nothing to clean up. `scripts/pve.py` and `scripts/provision_vm.py`
are otherwise unchanged and confirmed still correct as far as this point.

**Then, in order, once unblocked:** `fetch-image` → `build-template` →
`clone --full --name df-fortress` → record `DF_VMID` in `.env` → read
`/nodes/<node>/status` live (do not start if free memory < ~6.5 GB) → start →
wait for guest-agent IP → SSH in with
`ssh -i ~/.ssh/df_overseer_ed25519 -o IdentitiesOnly=yes df@<ip>` → snapshot
`clean-baseline` → confirm it lists → install DF Classic + DFHack.

**Single next concrete step: unchanged.** Still needs the human step —
Datacenter → Storage → `ssd_storage` → Edit → Content: add "Import" — before
any script can proceed past `fetch-image`.

## 2026-08-25 — research and design phase, nothing implemented

The project is in design. No code exists yet; `docs/` and `research/` are the
current output.

**Done:**

- `docs/PURPOSE.md` — purpose statement, six design commitments, scope
  (in/out), streaming plan, memory summary, operating parameters (FPS-cap
  maths, VM spec, anti-decay tool suite), 9-step build order, open questions.
- `docs/MEMORY-ARCHITECTURE.md` — four memory stores, retrieval tools, outcome-tracking
  (not self-critique), cross-fortress learning (scope tags, hypothesis
  promotion, fort ledger), the wiki as a hypothesis source, human input.
- `research/2026-08-25-spatial-perception.md` — 694-line spec. Verdict: the
  model is never shown a map; DF pre-computes most of the graph
  (`getWalkableGroup`, buildings, burrows); 10-tool minimal set; site scoring;
  ~440-token worked briefing.
- Repo adopted `claude-code-managed-repo-template` conventions.

- `research/2026-08-25-learning-architecture.md` — ~7,700 words. Attacked the
  memory design as a strawman and found a real flaw: the evidence counter
  presupposed credit assignment. Verdicts reconciled into
  `docs/MEMORY-ARCHITECTURE.md`; eight new/superseding rows in
  `decisions/DECISIONS.md`.

**In flight:** nothing. No agents running.

**Next concrete step:** build the **perception eval harness** — hand-written
briefings, questions with known answers, measure comprehension. No running game
or agent needed, and it tests the project's biggest risk. Build the **fort
ledger schema** alongside it, since schema design determines what is ever
learnable and it is cheap now / painful at twenty rows.

## 2026-08-26 — access layer complete; blocked on host RAM

**Access layer is finished and fully verified.** See `memory/proxmox-access.md`
for the authoritative record (read back from the API, not assumed).

**Done today:**

- **Diagnosed the `download-url` blocker properly.** `Sys.*` privileges are only
  checked at `/nodes/<node>` or `/` — never against pool or storage paths.
  Adding `Sys.AccessNetwork` to `DFOverseer` did nothing because that role is
  bound only at `/pool` and `/storage`. Fixed with a second narrow role
  `DFOverseerNode` (`Sys.Audit` + `Sys.AccessNetwork`) bound at
  `/nodes/proxmox`. **Lesson: diagnose by reading `/access/permissions` for
  granted *paths*, not by inspecting the role's privilege list.**
- `VM.Clone` granted (confirmed missing by test — needed to clone our own
  template) and all five `VM.GuestAgent.*` privileges, including
  `Unrestricted`, which allows command execution inside pool VMs and therefore
  guest provisioning without SSH.
- **Ubuntu 24.04 LTS (`noble`) cloud image downloaded to `ssd_storage`** —
  596 MB, `ssd_storage:iso/noble-server-cloudimg-amd64.img`. Ready to import.
- Node status reads now work, which is how the RAM problem below was found.
- **Decided: drop Steam on the VM, use DF Classic there**; keep playing Steam
  locally. Removes the auto-update-breaks-DFHack hazard, Steam Guard from
  provisioning, and the Steam-Linux-Runtime gotcha.
- Fixed a real bug in `.env`: the Proxmox password contains `$E`, which bash
  expanded to nothing when sourcing. Now single-quoted. Any script sourcing
  `.env` would have hit this.

**~~BLOCKER — host memory~~ RESOLVED same day.**

Was 13.7 GB used / 1.3 GB free. User freed memory; now **4.8 GB used, 9.6 GB
free** of 15.5 GB (swap down to 0.7 GB).

**Recommended VM sizing: 6 GB with a 2 GB balloon floor**, not the 8 GB in
`docs/PURPOSE.md`. 8 GB now fits but would leave only ~1.6 GB for the host —
tight if anything else starts, and it would push into swap. 6 GB is still ~3x
what a small-world fort needs at runtime, leaves generous room for the worldgen
spike (the real peak), is reclaimable when idle, and keeps ~3.6 GB of host
headroom. **Not yet confirmed with the user.**

CPU is fine: **i7-7700T, 4c/8t @ 2.9 GHz.** DF is single-threaded except
line-of-sight, so single-core performance is what matters and this is adequate.

**SUPERSEDED — see the 2026-08-26 (afternoon) section at the top of this file.**
Create the VM from the downloaded cloud image — create VM → `import-from` the `.img` → attach cloud-init drive →
set `ciuser`/`sshkeys`/`ipconfig0` (all confirmed working) → resize disk →
convert to template → clone. Then write `scripts/provision-vm.py` around it.

Ready and confirmed for that step:
- Next free VMID is **101**
- Image is present: `ssd_storage:iso/noble-server-cloudimg-amd64.img` (596 MB)
- `ciuser`, `sshkeys`, `ipconfig0` all confirmed settable
- **SSH key done.** Fresh dedicated keypair generated 2026-08-26:
  `~/.ssh/df_overseer_ed25519` (ed25519, no passphrase, comment `df-overseer`,
  fingerprint `SHA256:nFmogVJU7sqROeOeudZFcpLow+IXOYRystP9ymBZ0sA`). Paths in
  `.env` as `DF_SSH_KEY` / `DF_SSH_PUBKEY`; full record in
  `memory/proxmox-access.md`, rationale in `decisions/DECISIONS.md`. Reusing
  `claude_vm` was rejected — a shared key makes revocation indivisible.

**Host RAM moved again — re-read it before sizing the VM.** Live reading this
afternoon: **8.9 GB used / 5.5 GB free** of 15.5 GB, not the 4.8/9.6 recorded
this morning. The other VMs are outside our pool and invisible, so this number
is not ours to predict. **6 GB with a 2 GB balloon floor is now tight, not
comfortable; 4 GB max / 2 GB balloon is the safer call.** Still needs the
user's decision, and the reading should be taken again at creation time.

Two stale sections in `memory/proxmox-access.md` were corrected against the
live API while doing this: the role listed 16 privileges (it has 24 — `VM.Clone`
and the `VM.GuestAgent.*` set were granted this morning but never written back),
and the host-resources table still carried the 13.7 GB reading that was the
original blocker.

**Write the provisioning tooling in Python, not bash** — Git Bash's MSYS layer
rewrites POSIX paths in arguments (`/var/lib/vz/...` became
`C:/Program Files/Git/var/lib/vz/...`), which will silently corrupt any
`import-from` path.

**Still open from before:** token not rotated (user's decision, credentials are
in an earlier transcript); folder still named `df-automation` on disk; DF replay
determinism unverified; compliance-vs-doctrine-size curve unmeasured; nothing
pushed (no remote configured).

## 2026-08-25 (later) — Proxmox access layer built and verified

**Done, all verified against the live API (not assumed):**

- Access layer exists and is recorded authoritatively in
  `memory/proxmox-access.md` — role `DFOverseer` (17 privileges), scoped to
  `/pool/df-overseer` and `/storage/ssd_storage`. Credentials in `.env`
  (gitignored, confirmed untracked).
- **Boundaries verified by denial**, not assumption: cannot enumerate any VM
  outside the pool (`/cluster/resources?type=vm` → `[]`), cannot read template
  102 (`VM.Audit` denied). Recorded in the memory file.
- **Snapshot cycle proven end to end** — create → list → rollback → delete, all
  tasks `OK`, config intact after rollback. The save-rotation and
  roll-back-on-bad-decision design now rests on a tested capability.
- **VM creation, pool placement, and template conversion all proven** via a
  throwaway VM 900 (created, converted to template, destroyed, pool clean).
- VM 101 `ubuntu-lts-template-df` resized 1 core/512 MB → **4 cores/8192 MB**
  (balloon 2048), disk left at 25 GB (growth is easy, shrinking is not).

**Ruled out / superseded:**

- The `/vms/102` + `TemplateClone` grant idea — **superseded**. Building our own
  template is better: no dependency on someone else's artifact, nothing granted
  outside our pool/storage, and the base image becomes reproducible from
  scratch, which is the actual requirement.
- Terraform for VM provisioning — reconsidered when "script can rebuild a fresh
  VM" became a requirement, still rejected: state files are a liability in a
  public repo, the Telmate provider is broken on PVE 9 (demands the removed
  `VM.Monitor`), and every needed API call is already proven working. Use
  Python. `bpg/proxmox` if Terraform is ever revisited.

**NEXT CONCRETE STEP — one blocker, diagnosed but not resolved:**

`POST /nodes/proxmox/storage/ssd_storage/download-url` still returns a bare
`Permission check failed`. **`Datastore.AllocateTemplate` is NOT the problem** —
it was granted and confirmed present (role has 17 privs; effective value is `1`
on `/storage/ssd_storage`).

Strong hypothesis, untested: `download-url` makes the *host* fetch an arbitrary
URL, which requires **`Sys.AccessNetwork`**. Being a `Sys.*` privilege it likely
must be granted at `/` or `/nodes/proxmox`, not on the storage path.

Worth granting deliberately rather than reflexively — it lets the Proxmox host
fetch arbitrary URLs on our behalf, which is SSRF-adjacent. Scope it to
`/nodes/proxmox` if possible.

Once that is resolved, the template build is:
`download Ubuntu cloud image → create VM → import disk → cloud-init → convert to
template → clone`. Ubuntu **noble** (24.04 LTS) cloud image confirmed reachable,
596 MB, HTTP 200:
`https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img`
Then write `scripts/provision-vm.py` around it.

**Gotcha for that script:** Git Bash's MSYS layer rewrites POSIX paths in
arguments (`/var/lib/vz/...` became `C:/Program Files/Git/var/lib/vz/...`).
Write the provisioning tooling in Python, not bash.

**Also outstanding:**

- **Rotate the Proxmox token.** Credentials were pasted into chat and are in the
  session transcript. Datacenter → Permissions → API Tokens → remove/re-add,
  update `.env`. Nothing else changes.
- **VM 101 is a linked clone** of template 102 (`ssd_storage:102/base-102-disk-0
  .qcow2/101/vm-101-disk-0.qcow2`) and dies if 102 is deleted. Moot once we
  build and clone our own template.
- Folder still named `df-automation` on disk while the project is `df-overseer`.
  Rename between sessions — it breaks the working directory.
- Nothing pushed. 5 local commits on `main`, no remote configured.

**Two things to verify before they become load-bearing:** whether DF actually
replays deterministically from a save (the seeded-counterfactual measurement
idea rests entirely on it), and our own compliance-versus-doctrine-size curve
(the N=80 instruction-collapse threshold is a single unreplicated study).

**Ruled out / settled** (see `decisions/DECISIONS.md` for reasons): headless
terminal DF (`PRINT_MODE:TEXT` gone since v50); DFPlex for multiplayer (dead
for v50+); simultaneous adventure + fortress in one world (mode locks the
world); the agent brain living in this repo.

**Open, not blocked:** repo/folder still named `df-automation` on disk while
docs say `df-overseer`; not yet a git repo; `openclaw` vs `hermes-agent`
deliberately deferred; which display to build first.
