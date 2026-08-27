# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved — don't mark it paused. Any session should read this and know what's
actually going on right now.

## 2026-08-27 (afternoon) — repo pushed public; harness ran live for the first time

**Pushed:** [github.com/QuickWaller/df-overseer](https://github.com/QuickWaller/df-overseer), public, all commits on `main`. `gh` was already authenticated (QuickWaller); no remote existed before this.

**Perception harness ran against a live model for the first time.** User supplied a temporary Anthropic key (expires ~2026-09-03, stored in gitignored `.env`, do not commit or log it; rotate/remove after use). A 20-cell smoke test (`--limit 20`) immediately hit a real bug: every cell failed with the same 400 — `response_schema()`'s `confidence` field carried `minimum`/`maximum` on a `number` type, which the live structured-output validator rejects (the stub-only tests never caught this, exactly the gap the README predicted). Fixed in `harness/grade.py` — dropped the constraint keywords, stated the 0-1 range in the schema `description` instead. Full account in `decisions/DECISIONS.md` 2026-08-27.

**Re-run after the fix: 20/20 succeeded.** 100% accuracy on `coords_v1` (the only representation this particular 20-cell slice covered — `--limit` takes cells in build order, not a stratified sample). Cache reads confirmed non-zero (12/20 requests, 26,738 cached tokens) — the prefix-caching design works. Actual cost: **$0.043** for the successful run (969 input + 26,738 cached-read + 995 output tokens on `claude-opus-5`), essentially free — the pre-fix all-error run cost nothing (400s bill no tokens).

**New project goal, stated by the user:** the eval data and future fortress runs should build toward a public-facing report, not be throwaway. Reversed a repo-state bug that fought this directly: `evals/perception/.gitignore` was silently excluding `results/` from git. Removed it; `evals/perception/results/*.jsonl` is now tracked. See `memory/` for the standing note on this.

**Update, same afternoon — the stratified run happened, and the $5-15 estimate was wrong.** Real per-cell cost is far below the earlier guess (output tokens ran much lower than assumed). Ran a 120-cell stratified slice (`--per-category 1`, all fixtures, all representations — `evals/perception/results/stratified-2026-08-27.jsonl`) for **$0.27 actual**. Result: **first real signal that the core bet holds** — `exits_v1` tied `coords_v1` at 97.4% on the shared question set; see `decisions/DECISIONS.md` 2026-08-27 for the full breakdown, including the `route`-category soft spot and a thin-but-notable calibration difference. Marked `proposed`, not `accepted` — n=1-3/category, small hand-authored fixtures.

**Update, same afternoon — full 342-cell matrix run.** $0.83 actual, zero API errors. Confirms the core bet at real sample size: all three representations 99.1% (n=108 each), `route` rose to 88.9% with more data. **The calibration-separation finding from the 120-cell run did not replicate** — reordered entirely at n=108 (see `decisions/DECISIONS.md` 2026-08-27, both the `accepted` promotion and the retraction entry). Total spend today across all three eval runs: **$1.14**.

**Perception harness status: first build-order item now has real, accepted evidence behind it.** Standing caveats unchanged — still 15-landmark hand-authored fixtures, not the real (lossier) production briefing generator. Re-run against real briefings once `llm-brief.lua` exists. Next build-order item is the **fort ledger schema** (still not started, named three times now).

## HANDOVER — 2026-08-27, work paused here

**State at a glance:** the VM exists. It has never been started.

1. **Infrastructure** — the storage blocker cleared, a second one (SDN) was
   found and cleared, and **the template and the DF VM are both built**. The VM
   is stopped and cannot usefully be started on this host — see below.
2. **Perception eval harness** — built, offline paths verified, **never run
   against a live model.** No Anthropic credentials on this machine.
3. **Fort ledger schema** — still not started. Named twice now as this stream's
   work; it remains the earliest item in the learning design because its schema
   defines what is learnable.

No agents are running. Nothing has been pushed — there is still no remote.

### The three things a next session should pick up

**Update 2026-08-27:** Proxmox was unreachable this session — the tailnet subnet router (`tailscale`, <tailnet-router-ip>, advertising `<lan-subnet>/24`) wasn't in this machine's peer list at all. Cause: a concurrent AgentSecretary agent was using that Tailscale login elsewhere at the same time — transient contention, not a real outage. Retry once that other session is done.

**1. `df-fortress` (VM 104) is built and stopped.** It wants 6144 MB; the host
had **5.4 GB available** at last read. Tight rather than impossible — the
balloon floor is 2048 MB and KVM only backs touched pages — but worth deciding
deliberately rather than just booting it. Either free memory on the host, drop
the VM to 4 GB (a one-line change while stopped), or wait for the second node.

**2. The perception harness needs credentials and one small paid run.**
`python -m evals.perception.harness.run --limit 20 --out ...`, read the report,
*then* decide about the full 342-cell matrix. `pip install -r
evals/perception/requirements.txt` in a venv first — the installed SDK is
`anthropic` 0.32.0 and the runner targets `>=1.0`.

**3. The push is still unanswered.** The user approved "both, provisioning
first"; provisioning is done. There is no git remote, so pushing means
**creating a GitHub repo**, and that needs an explicit **public or private**
answer before anything is created. 11 local commits on `main`.

### Built this session

**Provisioning ran end to end.** Template 101 (`df-overseer-noble-template`) and
VM 104 (`df-fortress`, full clone) both live in the `df-overseer` pool.
`DF_TEMPLATE_VMID=101` and `DF_VMID=104` are in `.env`.

Three problems were hit and fixed on the way:

- **`import` content type** — enabled by the user, verified by reading
  `/nodes/proxmox/storage` back from the API.
- **`.img` rejected by an import-content store.** Canonical ships a qcow2 file
  with an `.img` extension. `download-url` names the destination independently
  of the URL, so `provision_vm.py` now writes it as `.qcow2` on the way in.
- **`SDN.Use` at `/sdn/zones/localnetwork`** — attaching a NIC to `vmbr0` is an
  SDN check in PVE 9, not a VM check. Recorded in `memory/proxmox-access.md`
  along with the trap that cost a round trip: **with privilege separation off,
  an ACL bound to the token is inert — it must be bound to the user.**

### Corrected this session — two bad numbers

- **`node_memory()` read `free`, which is the wrong field.** `free` excludes
  page cache, so it collapsed 5.5 → 1.7 GiB while a 596 MB image and a 25 GB
  disk copy went through the host, with 5.4 GiB available throughout. That
  artefact was reported as another VM eating the host, and the standing
  "do not start below 6.5 GB free" rule was written against the same wrong
  metric — it was unsatisfiable. `node_memory()` now returns
  `(total, used, free, available)` and every call site gates on `available`.
- **Electricity was costed at 30c/kWh.** The NZ average is **39c** (Feb 2026).
  Any running-cost figure written before 2026-08-27 is ~30% low.

### Hardware planning — deliberately not in this repo

A long session on a second Proxmox node, RAM harvesting, a NAS and clustering
is written up in **`infra/local.hardware-plan.md`**, which is gitignored via
`infra/local.*` and **is meant to be deleted** once the hardware is bought.

Two things in it that are repo-relevant if the cluster actually happens, and
should be lifted into `decisions/DECISIONS.md` rather than lost with the file:

- **A two-node Proxmox cluster loses quorum** when either node dies — the
  survivor cannot start or migrate anything. Needs a qdevice or a third node.
- **Cluster join order is destructive.** The joining node must have no guests.
  The cluster must be created on the **existing** ProDesk (which holds 101 and
  104) and the new node joined to it, never the reverse.

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

### Resume from here

```bash
python scripts/provision_vm.py status   # gates on 'available', not 'free'
```

Then, once there is memory headroom: start VM 104 → wait for the guest-agent IP
→ `ssh -i ~/.ssh/df_overseer_ed25519 -o IdentitiesOnly=yes df@<ip>` → snapshot
`clean-baseline` → confirm it lists → install DF Classic + DFHack.

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
