# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved — don't mark it paused. Any session should read this and know what's
actually going on right now.

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
