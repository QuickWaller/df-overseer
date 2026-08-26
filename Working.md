# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved — don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER — 2026-08-26 evening, work paused here

**State at a glance:** the infrastructure layer is built and verified; the game
layer has not been started. One human action, and only one, blocks the next
step. No agents are running. Nothing has been pushed — there is still no
remote.

### The one thing that needs a human

**Datacenter → Storage → `ssd_storage` → Edit → Content → tick "Import"**
(leave `images` and `iso` ticked).

`import-from` refuses an `iso`-class volume, which is what the downloaded cloud
image is. `download-url` *does* accept `content=import`, so this one checkbox
makes the whole template build scriptable with no host shell. The token cannot
do it itself and deliberately should not be able to — confirmed by denial,
`GET /storage/ssd_storage` → `403 (Datastore.Allocate)`. Re-tested against the
live API twice on 2026-08-26; still not enabled. CLI equivalent if preferred:
`pvesm set ssd_storage --content images,iso,import`.

### Resume from here

```bash
python scripts/provision_vm.py status         # host memory, next vmid, pool
python scripts/provision_vm.py fetch-image    # 596 MB into import/
python scripts/provision_vm.py build-template # create -> import disk -> template
python scripts/provision_vm.py clone --full --name df-fortress
```

Then: record `DF_VMID` in `.env` → **read `/nodes/<node>/status` live and do
not start if free memory is under ~6.5 GB** → start → wait for the guest-agent
IP → `ssh -i ~/.ssh/df_overseer_ed25519 -o IdentitiesOnly=yes df@<ip>` →
snapshot `clean-baseline` → install DF Classic + DFHack.

The design-side next step is unchanged and independent of all of this: the
**perception eval harness**, with the **fort ledger schema** alongside it.

### Built this session

- **SSH keypair** `~/.ssh/df_overseer_ed25519` — dedicated, ed25519, no
  passphrase. Fingerprint and rationale in `memory/proxmox-access.md`; paths
  only in `.env` (`DF_SSH_KEY`, `DF_SSH_PUBKEY`).
- **`scripts/pve.py`** — Proxmox API client: env loading, task polling that
  tails the task log on failure, live node-memory read.
- **`scripts/provision_vm.py`** — `status` / `fetch-image` / `build-template` /
  `clone`. Python, not bash: Git Bash's MSYS layer rewrites POSIX-looking
  arguments into Windows paths and would corrupt any storage path.
- **VM sizing decided:** 4 cores, 6144 MB, 2048 MB balloon, 25 GB.
- **Docs reconciled with reality** — `docs/PROXMOX-SETUP.md` (24 privileges,
  the `DFOverseerNode` role, the `import` content type, the SSH-key section),
  `docs/PURPOSE.md` (VM spec, and the Steam-on-the-VM caveat that contradicted
  the DF Classic decision), and the status line in `CLAUDE.md`, which claimed
  nothing was implemented.

### Corrected drift — the docs and the API disagreed in three places

- The role has **24** privileges, not the 16 recorded.
- **VM 101 no longer exists.** The pool is empty and `nextid` is 101, so the
  "linked clone of template 102" fragility is gone with it.
- Host memory was recorded as 13.7 GB used, then 4.8; it is **~9.0 GB used /
  5.5 GB free**. It has moved three times in two days and the other VMs are
  invisible to us — **never size or start from a written number**.

### Three API facts, each learned by failing

Recorded in `memory/proxmox-access.md` with the verbatim errors:

- The network **list** endpoint returns only physical interfaces for this
  token, so the host reads as having no bridges. It has one — `vmbr0`, found
  by fetching it directly. Same shape as the earlier ACL lesson: probe the
  object, don't conclude from an empty list.
- cloud-init `sshkeys` must be **URL-encoded before** the form body is encoded;
  Proxmox validates that the decoded field is still a urlencoded string.
- `import-from` rejects `iso`-class volumes — the blocker above.

### Carried forward, still open

- **Proxmox token not rotated.** Credentials were pasted into an earlier
  transcript. Datacenter → Permissions → API Tokens → `api` → Remove, re-Add,
  update `PVE_TOKEN_SECRET` in `.env`. Nothing else changes.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`. Rename between sessions; it breaks the working directory.
- **Nothing pushed** — no remote configured. 8 local commits on `main`.
- **DF replay determinism unverified** — the seeded-counterfactual measurement
  idea rests entirely on it.
- **Our own compliance-vs-doctrine-size curve unmeasured** — the N=80
  instruction-collapse threshold is a single unreplicated study.
- **`openclaw` vs `hermes-agent`** deliberately deferred; the MCP boundary
  makes it a swap.

### Detail

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

## Archived

- Sections for the week of 2026-08-24 (the design phase, the access-layer
  build, and the host-RAM blocker) moved to
  [`working-archive/Working_archive-2026-08-24.md`](working-archive/Working_archive-2026-08-24.md).
