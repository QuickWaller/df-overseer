# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved — don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER — 2026-08-26 late evening, work paused here

**State at a glance:** two streams, neither blocked on the other.

1. **Infrastructure** — **the storage blocker is cleared.** Provisioning has
   not been run past it yet; the next session picks up at `fetch-image`.
   Nothing was created or touched on the host this session, so there is nothing
   to clean up.
2. **Perception eval harness** — *built this session*, offline paths verified,
   **never run against a live model**: this machine has no Anthropic
   credentials and no `ant` CLI. See the section below for exactly what is and
   is not verified.

No agents are running. Nothing has been pushed — there is still no remote.

**Single next concrete step, per stream:** infra runs the four provisioning
commands below, starting with a 596 MB `fetch-image`; the eval harness needs
credentials and one paid run
(`python -m evals.perception.harness.run --limit 20 --out ...`), then a look at
the report before spending on the full 342-cell matrix.

### The storage blocker — CLEARED 2026-08-26

The `import` content type is enabled on `ssd_storage`. **Verified by reading it
back from the live API**, not taken on report:

```
GET /nodes/proxmox/storage  ->  ssd_storage content: iso,import,images
```

Background, kept because the reasoning still applies to the next capability
question: `import-from` refuses an `iso`-class volume, which is what the
downloaded cloud image was, so the whole template build was unscriptable
without this flag. The token could not set it itself and deliberately should
not be able to — confirmed by denial, `GET /storage/ssd_storage` →
`403 (Datastore.Allocate)`. Granting the role `Datastore.Allocate` was the
alternative and was rejected: it permits editing and deleting storage
definitions, far more standing capability than one one-time flag is worth.

`fetch-image` has **not** been re-run since the flag was enabled, so the
download path is unproven beyond the config read above.

### Resume from here

```bash
python scripts/provision_vm.py status         # host memory, next vmid, pool
python scripts/provision_vm.py fetch-image    # 596 MB into import/
python scripts/provision_vm.py build-template # create -> import disk -> template
python scripts/provision_vm.py clone --full --name df-fortress
```

Then: **read `/nodes/<node>/status` live and gate on `available`, not `free`**
→ start → wait for the guest-agent IP →
`ssh -i ~/.ssh/df_overseer_ed25519 -o IdentitiesOnly=yes df@<ip>` → snapshot
`clean-baseline` → install DF Classic + DFHack.

### Perception eval harness — built this session, not yet run for real

Lives in `evals/perception/`. Full rationale, flags, and limitations in
`evals/perception/README.md`; read that before touching it.

**Verified, and how:**

- `python -m evals.perception.harness.selftest` → **selftest OK**. It checks the
  harness's own ground truth by re-deriving answers a second, independent way
  (raw BFS over the connection list, a coordinate sign test for bearings,
  z-levels read straight off the fixtures).
- The selftest was itself checked by **deliberately corrupting the harness and
  confirming it goes red**: bearings forced to `N`, z-relations forced to
  `above`, hop counts forced to `1`, distances forced to a constant, the
  stranded list emptied, and a grader made permissive. All six caught. Two
  earlier versions of those checks **missed** two of the probes — the checks
  were calling the same functions they were meant to be checking — which is why
  they now re-derive from the raw fixture data instead.
- `python -m evals.perception.harness.run --dry-run` builds all 342 cells and
  prints the matrix. Needs no credentials and no SDK.
- The API request/response path is exercised **against a stub client only**:
  that the request assembles with adaptive thinking, a JSON answer schema and
  a cacheable stable prefix, and that a malformed response becomes an error row
  rather than a silent pass.

**NOT verified — do not report otherwise:**

- **No live model call has been made.** No `ANTHROPIC_API_KEY`, no `ant` CLI on
  this machine. Every accuracy claim the harness can make is unmeasured.
- The installed SDK is **`anthropic` 0.32.0**, which predates the API surface
  the runner is written against (`output_config`, adaptive thinking).
  `evals/perception/requirements.txt` pins `anthropic>=1.0`; install it in a
  venv before the first run.

**A finding that already exists, before any run:** `exits_v1` and `prose_v1`
cannot express geometry between landmarks that are *not* directly connected —
they skip `bearing_far` and `zlevel_far`, which `coords_v1` answers. That is a
precise statement of what the agent will never be able to work out for itself
from a briefing, and therefore of which zoom tools it must be handed. The
runner skips those cells rather than scoring them wrong.

**Deliberately not built:** an ASCII-map control arm. Building it would mean
writing the renderer the project committed never to write, and the commitment
is already settled on prior evidence. Reasoning recorded in the README.

**Next, in order:** credentials → `pip install -r
evals/perception/requirements.txt` in a venv → one `--limit 20` run → read the
report → only then the full matrix. Watch the cache line in the report: zero
cache reads would mean the briefing is not serialising byte-identically, which
the whole prefix-caching design depends on.

**The fort ledger schema was NOT started.** It was named alongside the harness
as this stream's work and is still outstanding — it remains the earliest build
item in the learning design, because its schema defines what is learnable.

### Built earlier this session

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
- Host memory was recorded as 13.7 GB used, then 4.8, then ~9.0; it is now
  **10.1 GB used with 5.4 GB *available***. It has moved four times in three
  days and the other VMs are invisible to us — **never size or start from a
  written number**, and gate on `available` rather than `free` (see below).

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
- **Nothing pushed** — no remote configured. 9 local commits on `main`.
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

**BLOCKER (cleared 2026-08-26 — kept for the record):**

Datacenter → Storage → `ssd_storage` → Edit → **Content: add "Import"**.

The cloud image was downloaded as `iso` content, and `import-from` refuses an
`iso` volume — it needs `images` or `import`. `download-url` *does* accept
`content=import`, so once that box was ticked, `provision_vm.py fetch-image`
could re-download the 596 MB image into `import/` and the rest run unattended.
Confirmed by denial that this token could not do it itself: `GET
/storage/ssd_storage` → `403 (Datastore.Allocate)`. Granting the role
`Datastore.Allocate` was the alternative and was rejected — it permits editing
and deleting storage definitions, far more than one flag is worth.

It was re-tested and still failing twice on 2026-08-26 (verbatim: `POST
/nodes/proxmox/storage/ssd_storage/download-url -> 500 {"message":"storage
'ssd_storage' is not configured for content-type 'import'"}`), then enabled by
the user later the same day. Read back from the live API to confirm:
`ssd_storage content: iso,import,images`.

**Then, in order, once unblocked:** `fetch-image` → `build-template` →
`clone --full --name df-fortress` → record `DF_VMID` in `.env` → read
`/nodes/<node>/status` live (gate on `available`, not `free`) → start →
wait for guest-agent IP → SSH in with
`ssh -i ~/.ssh/df_overseer_ed25519 -o IdentitiesOnly=yes df@<ip>` → snapshot
`clean-baseline` → confirm it lists → install DF Classic + DFHack.

**Single next concrete step:** run `python scripts/provision_vm.py
fetch-image` — the flag it was waiting on is now set, but the download itself
has not been attempted since.

## Archived

- Sections for the week of 2026-08-24 (the design phase, the access-layer
  build, and the host-RAM blocker) moved to
  [`working-archive/Working_archive-2026-08-24.md`](working-archive/Working_archive-2026-08-24.md).
