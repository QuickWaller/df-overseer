# Working archive — week of 2026-08-24

Sections moved wholesale out of `Working.md` on 2026-08-26 once they reported
themselves finished or were superseded. Nothing here is summarised or edited;
live items were carried forward into `Working.md` rather than left behind.

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

**Access layer is finished and fully verified.** See `infra/local.proxmox-access.md`
for the authoritative record (read back from the API, not assumed).

**Done today:**

- **Diagnosed the `download-url` blocker properly.** `Sys.*` privileges are only
  checked at `/nodes/<node>` or `/` — never against pool or storage paths.
  Adding `Sys.AccessNetwork` to `DFOverseer` did nothing because that role is
  bound only at `/pool` and `/storage`. Fixed with a second narrow role
  `DFOverseerNode` (`Sys.Audit` + `Sys.AccessNetwork`) bound at
  `/nodes/<pve-node>`. **Lesson: diagnose by reading `/access/permissions` for
  granted *paths*, not by inspecting the role's privilege list.**
- `VM.Clone` granted (confirmed missing by test — needed to clone our own
  template) and all five `VM.GuestAgent.*` privileges, including
  `Unrestricted`, which allows command execution inside pool VMs and therefore
  guest provisioning without SSH.
- **Ubuntu 24.04 LTS (`noble`) cloud image downloaded to `<storage>`** —
  596 MB, `<storage>:iso/noble-server-cloudimg-amd64.img`. Ready to import.
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
- Image is present: `<storage>:iso/noble-server-cloudimg-amd64.img` (596 MB)
- `ciuser`, `sshkeys`, `ipconfig0` all confirmed settable
- **SSH key done.** Fresh dedicated keypair generated 2026-08-26:
  `~/.ssh/df_overseer_ed25519` (ed25519, no passphrase, comment `df-overseer`,
  fingerprint `SHA256:nFmogVJU7sqROeOeudZFcpLow+IXOYRystP9ymBZ0sA`). Paths in
  `.env` as `DF_SSH_KEY` / `DF_SSH_PUBKEY`; full record in
  `infra/local.proxmox-access.md`, rationale in `decisions/DECISIONS.md`. Reusing
  `claude_vm` was rejected — a shared key makes revocation indivisible.

**Host RAM moved again — re-read it before sizing the VM.** Live reading this
afternoon: **8.9 GB used / 5.5 GB free** of 15.5 GB, not the 4.8/9.6 recorded
this morning. The other VMs are outside our pool and invisible, so this number
is not ours to predict. **6 GB with a 2 GB balloon floor is now tight, not
comfortable; 4 GB max / 2 GB balloon is the safer call.** Still needs the
user's decision, and the reading should be taken again at creation time.

Two stale sections in `infra/local.proxmox-access.md` were corrected against the
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
  `infra/local.proxmox-access.md` — role `DFOverseer` (17 privileges), scoped to
  `/pool/df-overseer` and `/storage/<storage>`. Credentials in `.env`
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

`POST /nodes/<pve-node>/storage/<storage>/download-url` still returns a bare
`Permission check failed`. **`Datastore.AllocateTemplate` is NOT the problem** —
it was granted and confirmed present (role has 17 privs; effective value is `1`
on `/storage/<storage>`).

Strong hypothesis, untested: `download-url` makes the *host* fetch an arbitrary
URL, which requires **`Sys.AccessNetwork`**. Being a `Sys.*` privilege it likely
must be granted at `/` or `/nodes/<pve-node>`, not on the storage path.

Worth granting deliberately rather than reflexively — it lets the Proxmox host
fetch arbitrary URLs on our behalf, which is SSRF-adjacent. Scope it to
`/nodes/<pve-node>` if possible.

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
- **VM 101 is a linked clone** of template 102 (`<storage>:102/base-102-disk-0
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
  `/nodes/<pve-node>/storage` back from the API.
- **`.img` rejected by an import-content store.** Canonical ships a qcow2 file
  with an `.img` extension. `download-url` names the destination independently
  of the URL, so `provision_vm.py` now writes it as `.qcow2` on the way in.
- **`SDN.Use` at `/sdn/zones/localnetwork`** — attaching a NIC to `vmbr0` is an
  SDN check in PVE 9, not a VM check. Recorded in `infra/local.proxmox-access.md`
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
  The cluster must be created on the **existing** SRV-01 (which holds 101 and
  104) and the new node joined to it, never the reverse.

### The storage blocker — CLEARED 2026-08-26

The `import` content type is enabled on `<storage>`. **Verified by reading it
back from the live API**, not taken on report:

```
GET /nodes/<pve-node>/storage  ->  <storage> content: iso,import,images
```

Background, kept because the reasoning still applies to the next capability
question: `import-from` refuses an `iso`-class volume, which is what the
downloaded cloud image was, so the whole template build was unscriptable
without this flag. The token could not set it itself and deliberately should
not be able to — confirmed by denial, `GET /storage/<storage>` →
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
  passphrase. Fingerprint and rationale in `infra/local.proxmox-access.md`; paths
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

Recorded in `infra/local.proxmox-access.md` with the verbatim errors:

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
  `infra/local.example.env`; full record in `infra/local.proxmox-access.md`.
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
  `infra/local.proxmox-access.md`: the network *list* endpoint hides bridges (use
  `vmbr0`, found by direct GET); cloud-init `sshkeys` must be URL-encoded
  *before* form encoding; and `import-from` rejects `iso`-class volumes.

**BLOCKER (cleared 2026-08-26 — kept for the record):**

Datacenter → Storage → `<storage>` → Edit → **Content: add "Import"**.

The cloud image was downloaded as `iso` content, and `import-from` refuses an
`iso` volume — it needs `images` or `import`. `download-url` *does* accept
`content=import`, so once that box was ticked, `provision_vm.py fetch-image`
could re-download the 596 MB image into `import/` and the rest run unattended.
Confirmed by denial that this token could not do it itself: `GET
/storage/<storage>` → `403 (Datastore.Allocate)`. Granting the role
`Datastore.Allocate` was the alternative and was rejected — it permits editing
and deleting storage definitions, far more than one flag is worth.

It was re-tested and still failing twice on 2026-08-26 (verbatim: `POST
/nodes/<pve-node>/storage/<storage>/download-url -> 500 {"message":"storage
'<storage>' is not configured for content-type 'import'"}`), then enabled by
the user later the same day. Read back from the live API to confirm:
`<storage> content: iso,import,images`.

**Then, in order, once unblocked:** `fetch-image` → `build-template` →
`clone --full --name df-fortress` → record `DF_VMID` in `.env` → read
`/nodes/<node>/status` live (gate on `available`, not `free`) → start →
wait for guest-agent IP → SSH in with
`ssh -i ~/.ssh/df_overseer_ed25519 -o IdentitiesOnly=yes df@<ip>` → snapshot
`clean-baseline` → confirm it lists → install DF Classic + DFHack.

**Single next concrete step:** run `python scripts/provision_vm.py
fetch-image` — the flag it was waiting on is now set, but the download itself
has not been attempted since.

*Moved here 2026-08-27 (evening). The perception-eval section below reported itself finished; the handover after it was superseded by the evening handover in `Working.md`. Note there is an earlier section in this file with the same HANDOVER heading, written that morning.*

## 2026-08-27 (afternoon) — repo pushed public; harness ran live for the first time

**Pushed:** [github.com/QuickWaller/df-overseer](https://github.com/QuickWaller/df-overseer), public, all commits on `main`. `gh` was already authenticated (QuickWaller); no remote existed before this.

**Perception harness ran against a live model for the first time.** User supplied a temporary Anthropic key (expires ~2026-09-03, stored in gitignored `.env`, do not commit or log it; rotate/remove after use). A 20-cell smoke test (`--limit 20`) immediately hit a real bug: every cell failed with the same 400 — `response_schema()`'s `confidence` field carried `minimum`/`maximum` on a `number` type, which the live structured-output validator rejects (the stub-only tests never caught this, exactly the gap the README predicted). Fixed in `harness/grade.py` — dropped the constraint keywords, stated the 0-1 range in the schema `description` instead. Full account in `decisions/DECISIONS.md` 2026-08-27.

**Re-run after the fix: 20/20 succeeded.** 100% accuracy on `coords_v1` (the only representation this particular 20-cell slice covered — `--limit` takes cells in build order, not a stratified sample). Cache reads confirmed non-zero (12/20 requests, 26,738 cached tokens) — the prefix-caching design works. Actual cost: **$0.043** for the successful run (969 input + 26,738 cached-read + 995 output tokens on `claude-opus-5`), essentially free — the pre-fix all-error run cost nothing (400s bill no tokens).

**New project goal, stated by the user:** the eval data and future fortress runs should build toward a public-facing report, not be throwaway. Reversed a repo-state bug that fought this directly: `evals/perception/.gitignore` was silently excluding `results/` from git. Removed it; `evals/perception/results/*.jsonl` is now tracked. See `memory/` for the standing note on this.

**Update, same afternoon — the stratified run happened, and the $5-15 estimate was wrong.** Real per-cell cost is far below the earlier guess (output tokens ran much lower than assumed). Ran a 120-cell stratified slice (`--per-category 1`, all fixtures, all representations — `evals/perception/results/stratified-2026-08-27.jsonl`) for **$0.27 actual**. Result: **first real signal that the core bet holds** — `exits_v1` tied `coords_v1` at 97.4% on the shared question set; see `decisions/DECISIONS.md` 2026-08-27 for the full breakdown, including the `route`-category soft spot and a thin-but-notable calibration difference. Marked `proposed`, not `accepted` — n=1-3/category, small hand-authored fixtures.

**Update, same afternoon — full 342-cell matrix run.** $0.83 actual, zero API errors. Confirms the core bet at real sample size: all three representations 99.1% (n=108 each), `route` rose to 88.9% with more data. **The calibration-separation finding from the 120-cell run did not replicate** — reordered entirely at n=108 (see `decisions/DECISIONS.md` 2026-08-27, both the `accepted` promotion and the retraction entry). Total spend today across all three eval runs: **$1.14**.

**Perception harness status: first build-order item now has real, accepted evidence behind it.** Standing caveats unchanged — still 15-landmark hand-authored fixtures, not the real (lossier) production briefing generator. Re-run against real briefings once `llm-brief.lua` exists. Next build-order item is the **fort ledger schema** (still not started, named three times now).

## HANDOVER — 2026-08-27, work paused here

**State at a glance:** repo is public and pushed. Perception eval — the
project's first build-order item — now has full, accepted evidence behind it.
The VM is built and stopped; it has never been started.

1. **Infrastructure** — template 101 and VM 104 (`df-fortress`) are both
   built. The VM is stopped and was not reachable to start this session — see
   below. Nothing else about it changed today.
2. **Perception eval harness — DONE for this phase.** Ran live for the first
   time, hit and fixed a real schema bug, then ran a 120-cell stratified slice
   and the full 342-cell matrix. Core result: `exits_v1` (the actual no-map
   production idiom) ties `coords_v1` (the coordinate control) at 99.1%,
   n=108/representation, **accepted** in the decision register. Total spend
   $1.14 across three live runs. Full account: `decisions/DECISIONS.md`
   2026-08-27 (five entries), and the section above this one in `Working.md`.
3. **Fort ledger schema — still not started.** Named three times now as this
   stream's earliest build item; its schema defines what is learnable. This is
   the next real piece of work.
4. **Repo is now public and pushed:** [github.com/QuickWaller/df-overseer](https://github.com/QuickWaller/df-overseer).
   `gh` was already authenticated (QuickWaller). As of this handover, local
   `main` is a few commits ahead — check `git status` and push if the user
   wants that caught up; push is gated on asking each time regardless.

### What a next session should pick up, in order

**1. Build the fort ledger schema.** Nothing else in the learning design is
checkable without it (`decisions/DECISIONS.md` 2026-08-25: "Fort ledger moved
to earliest build item"). Read `docs/MEMORY-ARCHITECTURE.md` first.

**2. Proxmox VM start — blocked on the same things as before, unchanged:**
memory headroom (VM wants 6144 MB, host had 5.4 GB available at last read;
options are free host RAM, drop the VM to 4 GB while stopped, or wait for the
second node) and the tailnet subnet router being reachable (`tailscale`,
<tailnet-router-ip>, advertising `<lan-subnet>/24` — it dropped out of this
machine's peer list mid-session because a concurrent AgentSecretary agent was
using that Tailscale login elsewhere; transient, not a real outage — just
retry). Resume command: `python scripts/provision_vm.py status` (gates on
`available`, not `free`).

**3. Re-run the perception eval against real briefings once `llm-brief.lua`
exists.** Today's result is on hand-authored, generous 15-landmark fixtures —
the real generator is lossier (3 nearest neighbours only, geometric distance).
That gap is the next validity question, not urgent on its own.

**4. Housekeeping, still carried forward and still untouched:**

- **Proxmox token not rotated** — pasted into an earlier transcript.
  Datacenter → Permissions → API Tokens → `api` → Remove, re-Add, update
  `PVE_TOKEN_SECRET` in `.env`.
- **Temporary Anthropic key in `.env` expires ~2026-09-03** (7 days from
  2026-08-27, user-supplied). Rotate/remove after use; do not commit or log it.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent`** still deferred. New consideration added
  2026-08-27: multi-agent decomposition by spatial task (patrol/military,
  construction/placement, economy as separate specialized agents) — bears on
  the choice because openclaw's multi-agent support is a candidate
  differentiator. Does not resolve it.
- **DF replay determinism unverified**; **our own compliance-vs-doctrine-size
  curve unmeasured** (N=80 threshold is a single unreplicated study).

**Housekeeping this session:** removed `evals/perception/.gitignore`, which
was silently excluding `results/*.jsonl` from git — the user's stated goal is
for experiment data to accumulate toward a public report, so results are now
tracked (`memory/reporting-goal.md`).

Detail on everything before 2026-08-27 (the provisioning build, the storage
and SDN blockers, the RAM-metric and electricity-cost corrections, the
hardware-planning session, and the original harness build) has moved to
[`working-archive/Working_archive-2026-08-24.md`](working-archive/Working_archive-2026-08-24.md)
— it reported itself finished and this file was getting long.

*Moved here 2026-08-27 (late evening). Both sections reported themselves
finished. Their live consequences are carried in the handover in
`Working.md`; the detail is here.*

## 2026-08-27 (evening) - fort ledger built

**The build-order item named three times is done.** `ledger/` holds the schema,
a validating write path, stratification, a coverage report, and a selftest.
`python -m ledger.selftest` passes all checks; `python -m ledger.report` runs.
Six entries in `decisions/DECISIONS.md` 2026-08-27 record the design calls.

**What it is:** JSONL, one row per fort, git-tracked. `forts.jsonl` is empty
and stays that way until the game side exists. That order is deliberate:
section 3.2 of the learning-architecture research warns that retrofitting
covariates onto old rows defeats the purpose, so the fields have to be right
before the first fort rather than after the twentieth.

**Four design calls worth knowing about:**

1. **Orthogonal feature axes**, replacing the design doc's single
   `entrance_design`. You cannot vary one variable when the variable is a
   portmanteau, and build item 8 depends on being able to.
2. **Every field declares a `source`**, and `store.assert_gradeable()` refuses
   to let grading code read `HUMAN` or `AGENT` fields. This makes "never grade
   the agent's account of its own learning" a code-level failure rather than a
   discipline anyone has to remember.
3. **`unrecorded` is dropped by stratification, not pooled**, and the dropped
   count is part of the result so the denominator stays honest.
4. **The vocabulary can record our own failures** (`agent_error`,
   `fps_collapse`, `run_ended_technical`). A schema that cannot record them
   produces a flattering report by construction.

**Standing caveat, and the next real test of this work:** nothing is verified
against DFHack. Every `MECHANICAL` field is a bet that code will be able to
read that value from game state, and `schema.MECHANICAL_PATH_VERIFIED` is
`False` to say so. `defense_depth`, `primary_industry` and `surface_footprint`
are the likeliest to have no clean mechanical reading; if so they get demoted
to `AGENT` and become colour rather than evidence.

**Deliberately not built:** any inference. `report.py` prints coverage and
descriptive survival with denominators visible and says in its own output that
it is not evidence. Hypothesis promotion is the hierarchical Beta-Bernoulli
model (research 3.3, build item 4), which does not exist. Reading a survival
difference off the report and calling it a lesson is exactly the flat-counter
mistake the register rejected on 2026-08-25.

**Housekeeping:** added `.claude/scheduled_tasks.lock` to `.gitignore` (a
machine-local runtime file that was showing up untracked).

**Not pushed.** Local `main` is now several commits ahead of origin. Push is
gated on an explicit go-ahead each time.

## 2026-08-27 (evening) - the VM is running

**VM 104 `df-fortress` booted for the first time.** Dropped to 4096 MB / 2048
MB balloon per the user's call (a cluster with more memory per host is coming,
so sizing around today's 15.5 GiB host is not worth waiting on). It cleared the
host-memory gate with 1.3 GiB headroom where 6144 MB did not.

Verified live, not assumed: Ubuntu 24.04.4, kernel 6.8.0-137, cloud-init
`done`, disk resized to 24 G usable, 4 cores, 3915 MB in the guest, SSH as
`df@<df-vm-ip>` with `DF_SSH_KEY` working.

**The reachability blocker was an account, not an outage.** This machine was
logged into the `<tailnet-b-account>` tailnet, which does not contain the subnet
router. `tailscale switch <tailnet-a>` put it on the tailnet that has `tailscale`
(<tailnet-router-ip>) advertising `<lan-subnet>/24`, and the API answered immediately.
Previous sessions read this as a transient peer dropout and advised retrying;
retrying was never going to work. **Side effect worth knowing: this machine is
now off the `<tailnet-b-account>` tailnet**, so `gitea`, `secrets` and the tenant
hosts are not reachable from here until it switches back.

**Template gap found and worked around.** The template sets `agent: enabled=1`
but never installs `qemu-guest-agent` in the guest, so every `/agent/*` call
returned 500 and the API could not report the VM's IP. VM 104 had to be located
by TCP-scanning `<lan-subnet>/24` for port 22 and probing with the SSH key.
Installed by hand on 104; the API now reads the IP correctly.
**`cmd_build_template` still has the gap** and will reproduce it.

**New tooling:** `scripts/provision_vm.py set-memory` and `start`. `start`
enforces the 2026-08-26 standing rule in code rather than leaving it to
memory: it reads host `available` and refuses when under 1 GiB would remain
(`--force` overrides). `set-memory` refuses to run against a running VM,
because a live `memory` write goes through the balloon driver and would report
a success that did not happen.

**Two things flagged, not fixed:** the IP is an unreserved DHCP lease, so
anything that pins `<df-vm-ip>` will break when it moves; and there is no
swap, which is fine at steady state but leaves no cushion behind the 4 GB
ceiling during worldgen.

---

# Archived 2026-08-27 (evening): the late-evening handover,
superseded by the provisioning-hardening handover of the same day.

## HANDOVER - 2026-08-27 (late evening), work paused here

**State at a glance.** Three things are now true that were not true this
morning: the perception bet is measured and accepted, the fort ledger exists
and is tested, and **the DF VM is running for the first time**. The game side
is still entirely unbuilt, and the guest is a bare Ubuntu with nothing
installed on it. Local `main` is **8 commits ahead of origin and unpushed**.

### Where things stand

1. **Perception eval: done for this phase.** `exits_v1` ties `coords_v1` at
   99.1%, n=108 per representation, `accepted` in the register. $1.14 across
   three live runs. Standing caveat: hand-authored 15-landmark fixtures, not
   the lossier production generator.

2. **Fort ledger: built.** `ledger/`, JSONL, git-tracked, **deliberately
   empty**. `python -m ledger.selftest` passes, including eleven negative
   checks that break each validator rule on purpose. Six decision entries
   record the design calls. Nothing in it is verified against DFHack:
   `schema.MECHANICAL_PATH_VERIFIED` is `False`, and every `MECHANICAL` field
   is still a bet that code can read that value from game state.

3. **VM 104 `df-fortress` is running.** 4096 MB / 2048 balloon, 4 cores,
   Ubuntu 24.04.4, `df@<df-vm-ip>`, SSH key verified. Host sits at 3.2 GiB
   available with it up. Full record in `infra/local.proxmox-access.md`.

4. **Repo is public** at [github.com/QuickWaller/df-overseer](https://github.com/QuickWaller/df-overseer),
   `gh` authenticated (QuickWaller). **8 local commits are unpushed**, covering
   the ledger, the handover, and the VM work. Push is gated on an explicit
   go-ahead each time, so ask.

### Three operational facts a next session will otherwise get wrong

**This machine is on the `<tailnet-a>` tailnet now.** The Proxmox host is only
reachable from there: `tailscale` (<tailnet-router-ip>) advertises `<lan-subnet>/24`,
and the `<tailnet-b-account>` tailnet has no such router. Earlier sessions recorded
the unreachability as a transient peer dropout and advised retrying; that
diagnosis was wrong and retrying could never have worked. **Side effect:** this
machine is off the `<tailnet-b-account>` tailnet, so `gitea`, `secrets` and the
tenant hosts are unreachable from here until it switches back
(`tailscale switch <tailnet-b>`).

**The VM's IP is now a reserved lease** (`<reserved-mac>` ->
`<df-vm-ip>`), reversing what this section said earlier today. Clone-time
MAC pinning (`mac_for_vmid`) means a rebuilt 104 comes back on the same MAC
and therefore the same address, so the reservation survives a delete and
recreate. New VMs get a derived MAC and need their own reservation.

**`qemu-guest-agent` is baked into template 101, and the bake is proven.**
`agent: enabled=1` only opens the virtio channel on the Proxmox side; without
the package in the guest every `/agent/*` call returns 500. The bake boots the
VM once at 2048 MB, installs over SSH at `DF_BUILD_IP` (<build-ip>, outside
the .100-.199 DHCP pool), proves `POST /agent/ping` answers, seals cloud-init
state and hard-stops. Ran end to end on 2026-08-27 after fixing four bugs it
surfaced: see `decisions/DECISIONS.md`. **Template 101 is rebuilt at 4096 MB**,
so clones no longer need the resize VM 104 needed.

### What a next session should pick up

**1. Install DF Classic and DFHack on the guest, and prove they run.** This is
the recommendation, and it displaces the compliance harness that the previous
handover put first. Three reasons. The guest is bare, so *every* game-side item
in `docs/PURPOSE.md`'s build order is blocked behind this one step. The
2026-08-26 decision to drop Steam in favour of DF Classic is still completely
untested. And 4096 MB is a new, unvalidated ceiling: worldgen is the memory
spike, there is no swap, and whether DF worldgens comfortably in 4 GB is now a
real open question rather than a theoretical one.

Also worth doing while there: check `memory/dfhack-environment.md`'s claims
against the actual install on the VM. That file was written against the local
Windows DFHack, and several tools are recorded as shipped-but-unavailable.

**2. Then `check_reachable` / `get_connectivity_report`** (`docs/PURPOSE.md`
build item 2). It copies `warn-stranded.lua`'s working algorithm and is the
highest-confidence real code in that list.

**3. The compliance eval harness, whenever there is an afternoon.** This is
`research/2026-08-25-learning-architecture.md` build item 1, described there as
"do first, before any fort runs". It needs no game and no agent, so it is never
blocked and can slot in anywhere. It retires a caveat the register has carried
since 2026-08-25: the N=80 doctrine-size threshold is a single unreplicated
study and our own compliance curve is unmeasured. It can reuse the perception
harness's whole shape (matrix runner, JSONL results, `report.py`, cached-prefix
layout), so it is mostly assembly.

It is listed third rather than first only because the VM coming up changed what
is scarce. If the VM turns out to be a time sink, do this instead rather than
grinding.

**4. Mechanical prediction grading** (research build item 3): compare a
prediction's `signal` field against recorded state at `check_at`. Cheap, and no
prediction-based calibration metric means anything until it exists.

**5. The ledger's write path is its real test, and it waits on the perception
layer.** `defense_depth`, `primary_industry` and `surface_footprint` are the
fields likeliest to have no clean mechanical reading; if so they get demoted to
`AGENT` and become colour rather than evidence.

**6. Re-run the perception eval against real briefings once `llm-brief.lua`
exists.** Today's numbers are on generous hand-authored fixtures; the real
generator is lossier (3 nearest neighbours, geometric distance).

### Housekeeping, carried forward

- **DONE: the bake works and template 101 is rebuilt with it.** Verified by
  running it: agent answers, MAC pinned, template converted. **The one thing
  still unproven is a clone** -- nothing has been cloned from 101, so sealing
  (fresh machine-id and SSH host keys per clone) is untested. That is the
  next cheap check and it needs a VM booted at reduced memory, since the host
  cannot fit 4096 MB alongside VM 104.
  **Correction:** this file called the fix "a two-line cloud-init change".
  That was wrong and unchecked -- Proxmox cloud-init cannot install packages,
  and the `cicustom` route needs a permission grant plus host filesystem
  access. See `decisions/DECISIONS.md` 2026-08-27.
- **DONE: DHCP lease reserved** (`<reserved-mac>` -> `<df-vm-ip>`), and
  MACs are now derived from the vmid and pinned at clone time so a rebuild
  keeps the reservation. `cmd_clone`'s pinning PUT is **not yet exercised
  against the API** -- no clone has run since.
- **Still open: add swap**, or consciously decide it does not matter before
  worldgen is attempted in 4096 MB.
- **Proxmox token not rotated**, pasted into an earlier transcript. Datacenter
  > Permissions > API Tokens > `api` > Remove, re-Add, update
  `PVE_TOKEN_SECRET` in `.env`.
- **Temporary Anthropic key in `.env` expires ~2026-09-03** (user-supplied
  2026-08-27). Rotate or remove after use; do not commit or log it.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent` still deferred.** The multi-agent
  decomposition point from 2026-08-27 adds a criterion but does not resolve it.
- **DF replay determinism unverified**, and the seeded-counterfactual rerun
  harness (research build item 7) rests entirely on it.
- **`hypothesis_id` has no registry.** Ledger observations reference
  hypotheses by bare string and nothing checks the id exists. Belongs with
  research build item 4, but a typo before then silently orphans evidence.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. They are fine as structural separators
(aligned definition lists, index lines).

---

## HANDOVER - 2026-08-27 (evening): provisioning hardening [archived 2026-08-27, superseded]

**State at a glance.** The provisioning layer is now finished and *proven*,
not just written: a template build produces a VM whose IP the API can report
by itself, and a clone of it comes up as its own machine. That was a detour.
The game side remains entirely unbuilt, and **that is what a next session
should do**. Local `main` is **12 commits ahead of origin and unpushed**.

### What changed this session

Two provisioning gaps were closed, both of which had produced failures that
read as something other than what they were.

1. **MACs are derived from the vmid and pinned at clone time.** Proxmox rolls
   a random MAC whenever a NIC is created, *including on clone*, so deleting
   and rebuilding a VM orphaned its DHCP reservation and the symptom looked
   like "the static IP stopped working". VM 104 keeps its existing
   `<reserved-mac>` via `MAC_OVERRIDES`, matching the reservation the user
   made on the router; new VMs get `BC:24:11:00:hi:lo`.

2. **`qemu-guest-agent` is baked into the template.** The bake boots the VM
   once at 2048 MB, installs over SSH at `DF_BUILD_IP`, proves the agent
   answers, seals cloud-init state and hard-stops. **Template 101 is rebuilt
   at 4096 MB**, so clones no longer need the resize VM 104 needed.

**Both are verified end to end.** Cloning 101 produced VM 105 (since
destroyed, having served its purpose) with a fresh
SSH host key, repopulated `machine-id`, fresh `instance-id`, `cloud-init
status: done` and `qemu-guest-agent` active, **and the API reported its
address (`<clone-ip>`) with no static configuration**, the capability
whose absence forced VM 104 to be found by port-scanning the subnet.

Six bugs surfaced only by running it, all fixed and recorded in
`decisions/DECISIONS.md`: the post-import resize timeout, `/agent/ping` being
POST rather than GET, sealing breaking graceful shutdown, `os.devnull` being
`"nul"` on Windows, and the vmid-collision finding below.

### Operational facts a next session will otherwise get wrong

**This machine is on the `<tailnet-a>` tailnet.** The Proxmox host is only reachable
from there: `tailscale` (<tailnet-router-ip>) advertises `<lan-subnet>/24`, and the
`<tailnet-b-account>` tailnet has no such router. **Side effect:** `gitea`,
`secrets` and the tenant hosts are unreachable from here until it switches
back (`tailscale switch <tailnet-b>`).

**`next_vmid()` is the only safe source of a vmid.** Cloning to a hand-picked
`--vmid 102` failed: VM 102 exists on this host *outside* the `df-overseer`
pool, so our token cannot see it (`403 VM.Audit`) and `pool_members()` does
not list it. **The pool view is not the host view.** Never pick an id by eye.

**The host cannot fit a 4096 MB VM alongside 104.** It sits at ~3.8 GiB
available with 104 up. `start` enforces this and refuses under 1 GiB
headroom; `set-memory` is the way down, and it refuses on a running VM.

**DHCP pool is `.100`-`.199`.** `DF_BUILD_IP=<build-ip>/24` sits just
outside it and is held only during a template build.

### What a next session should pick up

**1. Install DF Classic and DFHack on VM 104, and prove they run.** This has
been the recommendation for two sessions and keeps getting displaced. The
guest is bare, so *every* game-side item in `docs/PURPOSE.md`'s build order
is blocked behind it. The 2026-08-26 decision to drop Steam for DF Classic is
still completely untested. And 4096 MB is an unvalidated ceiling: worldgen is
the memory spike and there is no swap. Also check
`memory/dfhack-environment.md`'s claims against the real Linux install; that
file was written against the local Windows DFHack.

**2. Then `check_reachable` / `get_connectivity_report`** (`docs/PURPOSE.md`
build item 2). It copies `warn-stranded.lua`'s working algorithm and is the
highest-confidence real code in that list.

**3. The compliance eval harness, whenever there is an afternoon.** Research
build item 1, described there as "do first, before any fort runs". Needs no
game and no agent, so it is never blocked. It retires the standing caveat
that the N=80 doctrine-size threshold is a single unreplicated study, and it
reuses the perception harness's whole shape, so it is mostly assembly.

**4. Mechanical prediction grading** (research build item 3): compare a
prediction's `signal` field against recorded state at `check_at`. No
prediction-based calibration metric means anything until it exists.

**5. The ledger's write path waits on the perception layer.**
`defense_depth`, `primary_industry` and `surface_footprint` are likeliest to
have no clean mechanical reading; if so they get demoted to `AGENT`.

**6. Re-run the perception eval against real briefings once `llm-brief.lua`
exists.** Today's 99.1% is on generous hand-authored fixtures; the real
generator is lossier.

### Housekeeping, carried forward

- **Add swap to 104**, or consciously decide it does not matter, before
  worldgen is attempted in 4096 MB.
- **Proxmox token not rotated**, pasted into an earlier transcript.
  Datacenter > Permissions > API Tokens > `api` > Remove, re-Add, update
  `PVE_TOKEN_SECRET` in `.env`.
- **Temporary Anthropic key in `.env` expires ~2026-09-03**. Rotate or remove
  after use; do not commit or log it.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent` still deferred.**
- **DF replay determinism unverified**, and the seeded-counterfactual rerun
  harness (research build item 7) rests entirely on it.
- **`hypothesis_id` has no registry.** A typo silently orphans evidence.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

---

## HANDOVER - 2026-08-27 (night): DF installed on VM 104 [archived 2026-08-28, superseded]

**State at a glance.** The game is on the machine and it runs. VM 104 now has
DF Classic and DFHack installed, running headless, answering RPC, and
generating worlds from the command line without anyone touching a UI. The
two-session-old blocker in front of every game-side item is gone. `docs/`,
memory and the decision register are all reconciled against what is actually
on the VM, so this is a clean point to stop. **Local `main` is unpushed**, well ahead of `origin/main` (`d486e5b`).
Read the count with `git rev-list --count origin/main..main` rather than
trusting a number written in a doc: the previous handover claimed 12 and was
already undercounting by two, and any number stated here goes stale on the
next commit.

### What changed this session

**Swap first.** `/swapfile`, 4 GB, `vm.swappiness=10`, in `/etc/fstab`. It has
never been touched since, which turns out to be the finding rather than the
fix: see the memory numbers below.

**DF v0.53.16 linux64 (build tag `ITCH`) and DFHack 53.16-r1.1** are installed
at `/opt/df/game`. DFHack is the *same version as the Windows install*, so
`memory/dfhack-environment.md` carries over, and an audit against the real
Linux install confirmed it does: all eleven tools it calls unavailable are
unavailable here, every load-bearing tool is available, confirmed at runtime
via `helpdb` and not just from the doc tags. The 2026-08-26 decision to drop
Steam for DF Classic is now tested rather than assumed.

**It runs headless under Xvfb**, which revisits the 2026-08-25 rejection of
headless DF. That rejection was right that no text mode exists, and beside the
point: nobody looks at the window, and a virtual framebuffer satisfies SDL for
a few MB. `dfhack-run lua` executes remotely and the RPC server listens on
`127.0.0.1:5000`. Design commitment #1 is untouched.

**Worlds generate from the command line**: `./dfhack -gen <id> <seed>
"POCKET ISLAND"` runs silently and quits, ~12 seconds for a 17x17 world that
stops at year 30 and saves ~900 KB. Tiny worlds are the user's call for now.

Full detail, including the package list and the exact launch commands, is in
**`infra/local.df-vm-install.md`**.

**`docs/PURPOSE.md` was reconciled against reality**, not just appended to.
The provenance note, the DF Classic section, the VM sizing paragraph and the
build order all made claims that this session either confirmed or falsified.
The build order gained an item 0 for the install, item 1 is marked done, and
two open questions were replaced: the stale one about repo conventions (long
since adopted) is gone, and embark-scriptability plus a running fort's memory
ceiling are now written down as the real unknowns.

One drift worth knowing about, found while reconciling: both `PURPOSE.md` and
`memory/dfhack-environment.md` cited `FPS_CAP` and `G_FPS_CAP` as
`prefs/init.txt` **lines 22 and 23**. That is true of the Windows install and
wrong for the VM, where they are lines 71 and 75. A script seeking those line
numbers would not error, it would quietly edit the wrong settings. Both docs
now name the tokens and say the numbers differ per install.

### Things a next session will otherwise get wrong

**Saves are not in the game directory.** They are at
`~/.local/share/Bay 12 Games/Dwarf Fortress/save/`. A backup or snapshot script
written against `<df>/data/save`, which is what pre-v50 habit and most
community writeups say, finds nothing and reports success.

**`-gen` fails silently about a quarter of the time.** Two of eight runs exited
1 having generated the whole history into `save/current`, then never renamed it
and never wrote an export, with nothing in `gamelog.txt`, `errorlog.txt`,
stdout or stderr. Detect by the absence of the region directory, never by exit
code, and retry with a fresh seed. Exit 134 is the separate documented abort
for an id that already exists. Not DFHack's doing; it reproduces either way.

**Worldgen is not the memory spike everyone assumed.** Peak RSS **561 MB**
across a whole `POCKET ISLAND` gen, sampled every 0.5s, swap untouched,
available memory never below 2.5 GiB. **This measures worldgen only.** A
long-running fort with hundreds of units is the actual memory question and is
still unmeasured, so 4096 MB is not yet vindicated, just not refuted here.

**Nothing survives a reboot.** Xvfb and DF are both running under
`setsid nohup`. There is no systemd unit yet.

### What a next session should pick up

**1. Systemd units for Xvfb and DF**, plus a save-backup job pointed at the
XDG path. Small, and everything long-running depends on it. A fortress meant
to run a month cannot be held up by a `nohup` from an ssh session.

**2. `check_reachable` / `get_connectivity_report`** (`docs/PURPOSE.md` build
item 2). Copies `warn-stranded.lua`'s working algorithm, and there is now a
real DFHack to run it against. Highest-confidence real code in that list.

**3. Embark, and measure a running fort's memory.** The 4096 MB ceiling is
still an open question and worldgen did not answer it. Embarking also needs
UI driving, which `-gen` neatly avoided, so it is worth finding out early how
much of that is scriptable.

**4. The compliance eval harness, whenever there is an afternoon.** Research
build item 1, "do first, before any fort runs". Needs no game and no agent, so
it is never blocked. Retires the standing caveat that the N=80 doctrine-size
threshold is a single unreplicated study, and reuses the perception harness's
shape, so it is mostly assembly.

**5. Mechanical prediction grading** (research build item 3): compare a
prediction's `signal` field against recorded state at `check_at`. No
prediction-based calibration metric means anything until it exists.

**6. The ledger's write path waits on the perception layer.** `defense_depth`,
`primary_industry` and `surface_footprint` are likeliest to have no clean
mechanical reading; if so they get demoted to `AGENT`.

**7. Re-run the perception eval against real briefings once `llm-brief.lua`
exists.** Today's 99.1% is on generous hand-authored fixtures.

### Operational facts, carried forward

**This machine switched to the `<tailnet-b>` (<tailnet-b-account>) tailnet at the end of
this session, so Proxmox and VM 104 are currently unreachable from here.**
The Proxmox host is only reachable from `<tailnet-a>`: `tailscale` (<tailnet-router-ip>)
advertises `<lan-subnet>/24` there, and `<tailnet-b>` has no such router. Run
`tailscale switch <tailnet-a>` before touching the VM or `scripts/provision_vm.py`,
and `tailscale switch <tailnet-b>` to get `gitea`, `secrets` and the tenant hosts
back. Only one at a time; this is a real either/or.

**Consequence for this handover:** the VM was last verified healthy minutes
before the switch (Xvfb and `dwarfort` both up, RPC answering, 2.9 GiB
available, swap untouched). It has not been checked since and nothing was
done to it after that, so it should be exactly as described, but the first
thing a next session should do is switch tailnets and confirm rather than
assume.

**`next_vmid()` is the only safe source of a vmid.** VM 102 exists on this host
outside the `df-overseer` pool, so our token cannot see it and `pool_members()`
does not list it. The pool view is not the host view.

**The host cannot fit a 4096 MB VM alongside 104.** It sits at ~3.9 GiB
available with 104 up. `start` enforces this and refuses under 1 GiB headroom;
`set-memory` is the way down, and it refuses on a running VM.

**DHCP pool is `.100`-`.199`.** `DF_BUILD_IP=<build-ip>/24` sits just
outside it and is held only during a template build.

### Housekeeping, carried forward

- **Six test worlds (`region1`-`region6`) are sitting in the save directory**
  from this session's gen runs. Harmless at ~900 KB each; delete when they stop
  being useful.
- **Proxmox token not rotated**, pasted into an earlier transcript.
  Datacenter > Permissions > API Tokens > `api` > Remove, re-Add, update
  `PVE_TOKEN_SECRET` in `.env`.
- **Temporary Anthropic key in `.env` expires ~2026-09-03**. Rotate or remove
  after use; do not commit or log it.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent` still deferred.**
- **DF replay determinism unverified**, and the seeded-counterfactual rerun
  harness (research build item 7) rests entirely on it.
- **`hypothesis_id` has no registry.** A typo silently orphans evidence.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

---

# Archived 2026-08-28 (evening)

Both sections below moved wholesale from `Working.md`, unedited. The
first was superseded by the evening handover; the second reports itself
finished (the install script shipped and was verified against VM 104).

## HANDOVER - 2026-08-28, work paused here

**State at a glance.** The game side is real: DF Classic and DFHack run
headless on VM 104 and answer RPC. The repo is **pushed and public-safe** for
the first time, after a history rewrite that removed host identifiers from
every commit. Work has moved from "get DF running" to a hardware and
clustering project that reshapes what happens next, and one question is
blocking it.

### What changed since the last handover

**The repo went public without leaking the house.** `origin` is GitHub
(`QuickWaller/df-overseer`), not gitea, which had been assumed. A pre-push
scan found host identifiers in the 19 unpushed commits *and* already published
in `memory/proxmox-access.md`: the Proxmox IP, both subnets, the tailnet
router address, and the hostname. User's call was to rewrite and force-push.

- `memory/proxmox-access.md` and `memory/df-vm-install.md` are now
  `infra/local.*`, **gitignored**. A fresh clone does not have them.
  `memory/MEMORY.md` has a "local only" section saying so.
- Committed files use placeholders: `<pve-host>`, `<df-vm-ip>`,
  `<lan-subnet>`, `<tailnet-a>`, `<reserved-mac>`.
- History was rewritten with `git filter-repo` (two passes) and force-pushed.
  `origin/main` is `a820cf8`, 38 commits, in sync with local.
- A pre-rewrite backup bundle was verified and left in the session scratchpad.
  It is **outside the repo and will not survive a machine cleanup**; if the
  rewrite ever needs undoing, that bundle is the only copy.

**Method note worth keeping.** The first "history is clean" check was wrong:
it scanned 1 blob instead of 132 because `rev-list --objects` output was piped
into `cat-file` in a form it could not parse, so it silently passed. A
positive control caught it, and the real scan then found two addresses in
historical `DECISIONS.md` blobs that the first replacement list had missed.
**Any leak scan needs a positive control**, or a scan that sees nothing is
indistinguishable from a repo with nothing in it.

**`provision_vm.py` no longer hardcodes a DHCP reservation.** MACs come from
`DF_MAC_OVERRIDES` in `.env`, parsed to `{vmid: mac}`. Derived MACs are
unchanged (vmid 101 still yields `BC:24:11:00:00:65`).

**`docs/PURPOSE.md` was reconciled against the VM**, not just appended to. It
had claimed nothing was tested against a running game, and that the worldgen
spike was the real memory peak. Both were false and are now corrected, with
build item 0 added for the install and item 1 marked done.

### The hardware and clustering project

**The Omen has been stripped.** Harvested: **2 x 8 GB DDR4-2400** (the plan
assumed 2 x 16), a WiFi card, the panel, a **2 TB 2.5" HDD**, and an SSD of
unverified size. `infra/local.hardware-plan.md` has the destinations.

**The user wants a cluster, explicitly not for HA**, but for the three things
clustering gives you anyway: one UI and API across both boxes, **migration**,
and replicated `/etc/pve` config. Migration is the near-term motivation, since
it is what lets a box be opened without downtime.

**Order of operations, agreed:**

1. Safety net first: repo pushed (**done**), script the DF install (**not
   done**), dump 104 off-host.
2. `dmidecode -t memory` on SRV-01. Decides add vs replace, and whether
   the spare 8 GB stick has a home at all.
3. **Decide reinstall vs rebuild.** Blocking, see below.
4. `cpu: host` -> `x86-64-v2-AES` in `provision_vm.py`.
5. SRV-02 arrives, set up standalone: second stick, WiFi card, 2 TB in the
   free bay as the backup target.
6. Create the cluster **on SRV-01**, then join the empty SRV-02.
7. Qdevice last: HA into a VM, reflash the Pi, `corosync-qnetd`.

### Blocking question, for the user

**Full Proxmox reinstall on SRV-01, or rebuild the `df-overseer` pool and
VMs on the existing install?** Step 3 gates step 6, because a reinstall must
happen before a cluster exists. Nothing in the hardware sequence can be
scheduled until this is answered.

### Things a next session will otherwise get wrong

**The machine is on the `<tailnet-b>` tailnet, so the Proxmox host and VM 104
are unreachable.** Run `tailscale switch <tailnet-a>` first; the real ids are
in `infra/local.proxmox-access.md`. Switching back gives `gitea`, `secrets`
and the tenant hosts. It is a real either/or, only one at a time.

**VM 104 has not been verified since that switch.** Last confirmed healthy on
2026-08-27 night: Xvfb and `dwarfort` up, RPC answering, swap untouched.
Nothing touched it after, so it should be as described. Confirm, do not
assume.

**`DF_MAC_OVERRIDES` in `.env` is load-bearing.** Without it a rebuilt VM 104
gets a *derived* MAC and drops off its DHCP reservation, which is the exact
failure that cost a session earlier this week. It is gitignored, so it does
not travel with the repo.

**Cluster join order is destructive.** The joining node must have no guests;
joining wipes its guest config. Create on SRV-01, join the empty
SRV-02. The reverse loses `df-fortress`.

**A two-node cluster is worse than two standalone hosts** until the qdevice
lands. One node down leaves the survivor unable to start, stop or edit
anything. Running VMs keep running.

**A reset destroys VMs we cannot see.** VM 102 exists on the host outside the
`df-overseer` pool; our token gets `403` on it and `pool_members()` does not
list it. Enumerate as root in the GUI before wiping anything.

**Clusters do not pool RAM.** Two 16 GB nodes are two 16 GB machines with one
login. The DF VM's ceiling is only relieved by sticks in the right slot.

**Saves are not in the game directory.** They are under the XDG data path; see
`infra/local.df-vm-install.md`. A backup script aimed at `<df>/data/save`
copies nothing and reports success.

**`-gen` fails silently about a quarter of the time**, generating the full
history and then writing no export, with nothing in any log. Detect by the
absence of the region directory, never by exit code.

### What a next session should pick up

**1. Script the DF install. Written, not yet run against the VM.** See the
section below.

**2. `cpu: host` -> `x86-64-v2-AES`.** Migration is now a stated goal and that
flag blocks it between a Kaby Lake i7-7700T and a Coffee Lake i5-8500T. Cold
stop/start on 104 to take effect. For DF the loss is nil, it is
single-threaded and not AVX-heavy.

**3. Systemd units for Xvfb and DF**, plus a save-backup job at the XDG path.
Blocked on the tailnet switch. Nothing currently survives a reboot: both are
running under `setsid nohup`.

**4. `check_reachable` / `get_connectivity_report`** (`docs/PURPOSE.md` build
item 2). Copies `warn-stranded.lua`'s algorithm, and there is a real DFHack to
run it against now.

**5. Embark, and measure a running fort's memory.** 4096 MB is still unproven
for a live fort; worldgen answered a different question. Embark also needs UI
driving, which `-gen` avoided, so finding out how much is scriptable matters.

**6. The compliance eval harness.** Research build item 1, "do first, before
any fort runs". No game, no agent, never blocked. Retires the standing caveat
that the N=80 doctrine threshold is a single unreplicated study.

**7. Mechanical prediction grading** (research build item 3): compare a
prediction's `signal` against recorded state at `check_at`. No calibration
metric means anything until it exists.

**8. The ledger's write path waits on the perception layer.** `defense_depth`,
`primary_industry` and `surface_footprint` are likeliest to have no clean
mechanical reading; if so they become `AGENT` fields.

**9. Re-run the perception eval against real briefings once `llm-brief.lua`
exists.** Today's 99.1% is on generous hand-authored fixtures.

### Housekeeping, carried forward

- **The published hostname should be treated as exposed.** The rewrite removed
  it from the repo, it did not un-publish it: GitHub can serve unreferenced
  commits by SHA for a while and any existing clone or fork still has it. The
  user chose not to rename the host. Not secret, just no longer advertised.
- **`willsmith.nz` was deliberately left in** (30 occurrences). It is the
  project's intended public face per `docs/PURPOSE.md`, not a leak.
- **SRV-01's RAM slot layout is still unknown**, and it decides whether
  the spare 8 GB stick is useful or scrap.
- **The SSD out of the Omen has an unverified size.** Only worth putting in a
  node if it beats the SRV-02's 239 GB NVMe.
- **Six test worlds (`region1`-`region6`)** are sitting in VM 104's save
  directory. ~900 KB each, delete when done with them.
- **Proxmox token not rotated**, pasted into an earlier transcript.
- **Temporary Anthropic key in `.env` expires ~2026-09-03.** Rotate or remove;
  do not commit or log it.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent` still deferred.**
- **DF replay determinism unverified**, and research build item 7 rests on it.
- **`hypothesis_id` has no registry.** A typo silently orphans evidence.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

## DF install scripting - 2026-08-28

`scripts/install_df.py` exists. It turns `infra/local.df-vm-install.md` from
prose into something re-runnable, which is what the hardware sequence was
waiting on: 104 stops being a thing to protect and becomes a thing to rebuild.

**What it does.** `install` (packages, 4 GB swapfile, DF + DFHack tarballs,
`prefs/init.txt`), `verify`, `start`, `stop`, `gen`, `saves`, `backup`. Every
command is idempotent and takes `--vmid`, defaulting to `DF_VMID`. It drives
the guest over SSH from this workstation, reusing `provision_vm.py`'s
`ssh_guest` and `.env` discipline.

**The three traps are encoded as checks, not comments.**

- The XDG save path is resolved from `getent passwd`, so it is right under
  sudo too. `verify` fails if `<game>/data/save` exists, because its presence
  means something has recreated the pre-v50 layout that makes a backup script
  silently copy nothing.
- `gen` decides success by the region directory existing, never by exit code,
  and retries with a fresh seed. It names `save/current` explicitly when it
  finds the orphan, since "generated but never renamed" and "generated
  nothing" are different problems. Exit 134 aborts rather than retrying: that
  one is the documented "world id exists".
- `init.txt` settings are applied and then read back, because `sed` exits 0
  when it matches nothing, so a key renamed between DF versions would
  otherwise be skipped in silence.

**What was verified offline first.** With the VM still unreachable,
`--dry-run` prints each remote script instead of running it, and that is what
got tested before any of it touched a machine:

- All 15 distinct remote scripts pass `bash -n`. The first run of that check
  reported all 15 as failures, which turned out to be WSL's bash failing to
  spawn at all, not a syntax error anywhere. A positive control (a deliberately
  unterminated `if`) then confirmed the check can detect a real error.
- `prefs/init.txt` was run for real against a realistic `init_default.txt`:
  all five settings land, unrelated keys are untouched, and a negative case
  with `PRINT_MODE` deleted confirms the readback fails rather than passing.
- The archive layout detection was run against both a flat and a
  directory-wrapped tarball. `dwarfort` lands at the game root either way. The
  install doc says both archives are flat; the script detects rather than
  assumes, so a future release that wraps them does not bury the game a level
  down.
- The base64 transport was round-tripped with quotes, `$`, brackets and a
  space-bearing path.

**Then it was run against VM 104, and that is what found the real bugs.**
Tailnet switched to `<tailnet-a>` on 2026-08-28. Every command has now been
exercised against the live VM. `verify` is all-PASS including the runtime
checks, `backup` pulled 4.1 MB / 181 entries off the box, `gen` reproduced the
silent worldgen failure and recovered from it, and a full stop/start cycle
works. `install` was then run against the already-installed VM and proved
idempotent end to end: packages no-op, swapfile already active, extract
correctly skipped with "pass --force to replace", init.txt re-applied and read
back. It did re-download both tarballs, because the hand-install kept them
under their upstream names and the script caches them as `df.tar.bz2` and
`dfhack.tar.bz2`; sha256 values for both are now recorded in
`infra/local.df-vm-install.md`.

**Four bugs, none of which offline testing could have found.**

1. **`--vmid` only worked before the subcommand.** argparse puts a top-level
   option there, which contradicted the script's own usage text. Now attached
   to the top level and every subparser, with `SUPPRESS` defaults so the
   subparser's unset value cannot overwrite the one already given.
2. **`dfhack-run` wraps its output in ANSI colour even with stdout not a tty,
   and ends with a bare reset on its own line.** `tail -n1` therefore returned
   `[0m`, so `verify` was comparing an escape sequence against the version
   string and would have called a correct install wrong. Fixed with a shared
   `dfhack_lua()` helper that strips escapes and drops blank lines.
3. **The `start` readiness loop could not fail.** It broke as soon as
   `dfhack_lua` returned anything non-empty, and when the game is not up yet
   `dfhack-run` prints `Could not connect to localhost:5000`, which is
   non-empty. So the loop exited on its first pass and the socket check ran
   against a game under a second old. That is what made a healthy start report
   a 240s timeout. Readiness is now two conditions: the socket is listening,
   and the answer is neither empty nor the connect error. Positive control with
   the game stopped: the loop now runs its full deadline instead of exiting at
   0s.
4. **`gen`'s orphan check was presence-based.** It reported "save/current
   exists, this is the silent -gen failure" whenever `current` was there at
   all, and a stale one from 2026-08-27 was. It now samples the mtime before
   the run and only blames this attempt if it moved. All three branches
   (stale / written-now / absent) tested directly.

**New verified facts about the VM, for `infra/local.df-vm-install.md`.**

- **DF ignores SIGTERM.** Every `stop` waits the full 30s and ends in SIGKILL.
  There is no graceful shutdown, which makes `--save` mandatory rather than
  optional once a fort is live, and means the systemd unit cannot rely on a
  normal stop: it needs a save step and a long `TimeoutStopSec`, or every
  reboot kills the fort.
- **Launch to listening RPC socket is about 3 to 10 seconds**, measured in a
  single session rather than inferred across SSH calls.
- **The silent `-gen` failure is real and reproduced:** one of two attempts on
  world 7 exited 1 with no region directory. The retry with a fresh seed
  succeeded. World 8 succeeded first try.

**The host rebooted and nothing came back.** The host booted at approximately
2026-08-27 23:32, and VM 104 was found **stopped**, not running as the previous
handover assumed. `onboot` is not set on 104, so the problem is larger than the
handover recorded: it is not only that Xvfb and DF do not survive a reboot, the
**VM itself does not**. Whatever the systemd work concludes, `onboot` on 104 is
a separate one-line fix and has not been made, because it changes VM config
rather than repo state.

**Leftovers from this session, for cleanup.** `region7` and `region8` are mine,
from testing `gen`; that makes eight test worlds plus a 4 KB stale
`save/current`. `backups/df-saves-104-*.tar.gz` is the first off-host dump of
104's saves, which also ticks the handover's "dump 104 off-host" safety-net
item. `cpu: host` is still set on 104, so handover item 2 is still open.

**Also landed:** `DF_VM_IP` and `DF_CIUSER` added to
`infra/local.example.env`; `backups/` gitignored.

**Docs reconciled against reality, 2026-08-28.** `docs/PURPOSE.md` (status
header, the Xvfb section now carrying the three process-lifecycle facts, the
worldgen and save sections, and build item 0), `CLAUDE.md`'s status blurb,
`infra/README.md` (including the `.env` correction below and a new Scripts
table), and `memory/MEMORY.md`'s local-only list, which was missing
`local.hardware-plan.md` entirely. The verified facts themselves live in
`infra/local.df-vm-install.md`, which is the authoritative record; the public
docs point at it rather than restating the host specifics.

Everything that would be published was then leak-scanned against identifiers
harvested from the gitignored records, with a positive control proving the scan
could see (20 hits on a known string). Zero real identifiers. One shape-sweep
hit, `tail1234.ts.net` in `local.example.env`, checked and cleared: neither
`prodesk` nor `tail1234` appears anywhere in the real records, and the actual
`PVE_HOST` is not a `.ts.net` name at all. That file is newly public, so it was
worth confirming rather than assuming.

**Not archived yet despite reading as finished:** this section is still gated on
the user for the `onboot` change, deleting the eight test worlds, and the
commit. Per the archive-cadence rule that is "gated on a human", so it stays.

**Two doc/repo mismatches found on the way, one fixed.**

- **Fixed:** `infra/local.example.env` was never tracked. `CLAUDE.md` says the
  `local.example.*` counterparts are committed, but the `infra/local.*` ignore
  rule swallowed them, so a fresh clone got no template at all. Added
  `!infra/local.example.*`. Checked in both directions: git now offers the
  example file, and `local.proxmox-access.md`, `local.df-vm-install.md`,
  `local.hardware-plan.md` and `local.env` all still match the ignore rule.
  Every non-empty value in the example is a safe default (`PVE_PORT=8006`,
  `PVE_TOKEN_ID=df-overseer@pve!api`, `PVE_POOL=df-overseer`, `DF_CIUSER=df`,
  `PVE_TLS_VERIFY=false`), nothing host-specific.
- **Fixed:** `infra/README.md` told you to copy `local.example.env` to
  `local.env`, which no code has ever read: `pve.py`'s `load_env()` reads the
  repo-root `.env`. Resolved in favour of documenting what the scripts actually
  do, since a doc's job is to describe reality and moving the code would have
  been a behaviour change smuggled in under "update docs". If the layout should
  change instead, that is a separate call.

## HANDOVER - 2026-08-28 (evening) [archived 2026-08-30, superseded]

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

**1. Reinstall or rebuild.** Full Proxmox reinstall on SRV-01, or rebuild
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
joining wipes its guest config. Create on SRV-01, join the empty
SRV-02. The reverse loses `df-fortress`.

**A two-node cluster is worse than two standalone hosts** until the qdevice
lands. One node down leaves the survivor unable to start, stop or edit
anything. Running VMs keep running.

**A reset destroys VMs we cannot see.** VM 102 exists on the host outside the
`df-overseer` pool; our token gets `403` and `pool_members()` does not list it.
Enumerate as root in the GUI before wiping anything.

**Clusters do not pool RAM.** Two 16 GB nodes are two 16 GB machines with one
login.

**Our Proxmox token is pool-scoped and cannot run node-level commands.**
Anything like `dmidecode` on SRV-01 needs root SSH to the host, which has
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
- **SRV-01's RAM slot layout is still unknown**, and it decides whether
  the spare 8 GB stick is useful or scrap.
- **The SSD out of the Omen has an unverified size.**
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent` still deferred.**
- **DF replay determinism unverified**, and research build item 7 rests on it.
- **`hypothesis_id` has no registry.** A typo silently orphans evidence.
