# df-overseer

Turning Dwarf Fortress into a fortress that runs, survives, and tells its own
story without you. See **[docs/PURPOSE.md](docs/PURPOSE.md)** for what this is
and why, and **[docs/MEMORY-ARCHITECTURE.md](docs/MEMORY-ARCHITECTURE.md)** for the overseer's memory and
learning architecture.

> **Status: design, plus infrastructure that is scripted, proven, and
> currently standing.** The Proxmox identity this project runs against is
> provisioned outside this repo (see `infra/README.md`);
> `scripts/provision_vm.py` built VM `df-colony-01` (vmid 103) against it on
> 2026-09-08, and `scripts/install_df.py` installed DF Classic and DFHack on
> it, verified end to end (`decisions/DECISIONS.md` 2026-09-08 rows). This is
> a rebuild, not the original: an earlier VM and template, built 2026-08-27,
> were deleted 2026-09-01 in an estate rebuild, and today's VM is a fresh one
> from this repo's own scripts, not a restore. **DF itself has not been
> started and no world exists yet**, so nothing is running unattended; the
> honest claim is that the stack is up and verified, not that a fort is in
> progress. No *code* of the game side is implemented yet: no perception
> layer, no agent, no toolkit. Everything in `docs/` and `research/` is still
> a design artifact; claims marked *verified* were checked against a DFHack
> install, the live API, or a primary source, and the rest are proposals.

This repo is managed with Claude Code using a structured memory system,
following the pattern published as
[`claude-code-managed-repo-template`](https://github.com/QuickWaller/claude-code-managed-repo-template)
(MIT) — the conventions below (`Working.md`, `memory/`, `decisions/`, the Rules
section, the `executor`/`researcher` agents) come from that template. Read this
file first in any session.

## Structure

- **`ROADMAP.md`** (root) — the forward-looking, priority-ordered plan: what's
  next and roughly when, in Now/Next/Later buckets plus an "explicitly not
  doing" list. Complements `Working.md` rather than duplicating it —
  `Working.md` is tactical detail on what's in motion right now, `ROADMAP.md`
  is the strategic list it's drawn from. One line per item: what/why plus a
  pointer into `decisions/DECISIONS.md`, `Working.md`, `docs/`, or `research/`
  for the real detail, never a re-narration. **Update triggers:** a Now-bucket
  item starting or finishing, an explicit user priority call, and a
  lightweight full-review pass at least every ~2 weeks regardless (bump
  `**Last reviewed:**`, actually re-scan for anything quietly finished or
  stalled).

- **`Working.md`** (root) — what's currently in progress. If something is
  tabled, shelved, or paused, remove it rather than marking it paused. Any
  session — fresh, resumed, or accidentally concurrent — should read this file
  and know the current state at a glance. When handing off mid-investigation,
  record what's been **ruled out** and the single **next concrete step**, not
  just the goal.
  **Archive-cadence rule:** archive a `##` section into
  `working-archive/Working_archive-<week-start-date>.md` as soon as *either*
  (a) that section reports itself finished — nothing gated on a human or
  another stream — or (b) the file exceeds roughly 400 lines of in-progress
  material. Move sections wholesale, never summarize or delete; leave a
  one-line pointer.

- **`memory/`** — indexed repo memory: context not derivable from the code.
  `memory/MEMORY.md` is the index. Files split by **scope**, not size.

- **`decisions/DECISIONS.md`** — decision register. Every decision worth
  remembering: **date**, **status**, **reason**. Entries running past ~300
  words get trimmed to a summary plus a pointer into `memory/`.

- **`docs/`** — the design artifacts: `PURPOSE.md`, `MEMORY.md`.

- **`research/`** — dated research specs produced by `researcher` agents.
  Long, cited, and honest about what could not be verified. Read the relevant
  one before designing in its area rather than re-deriving it.

## Upstream obligations

- **`home-lab`** (`../home-lab` — private, permanently; the declared source
  of truth for the physical server estate this repo automates). Cite its IDs
  (`SRV-01`, `DISK-06`, a VMID); **never copy a hostname, address or subnet
  into this repo** — a public repo cannot leak what it does not contain, and
  that separation is the whole reason the IDs exist.

  **Obligation — creating, deleting, resizing or re-addressing a guest here
  makes `home-lab/inventory/` wrong.** In the same turn, not later:
  - allocate the IP through `home-lab/inventory/ips.yaml` *before* assigning
    it — that file is an allocation registry, "consult before assigning,
    update on assignment", and skipping it is how `192.168.2.201` came to be
    in use for a week without being registered anywhere;
  - record the guest change in that host's `inventory/hosts/SRV-0x.yaml`
    `guests:` block, and in `inventory/services.yaml` if a service moved.

  **You are not authorised to edit that repo from here, and it will not
  thank you for trying.** home-lab's own rules forbid reconciling drift
  silently in either direction — writing your observations into its declared
  layer is the specific failure it exists to prevent. Follow the
  consulting-another-repo procedure in `## Rules`: if a session is live in
  `../home-lab`, tell it; otherwise record the obligation in `Working.md` as
  open and say so in your summary, so the user can route it. Anything you do
  send is second-hand there and must arrive with the command you actually
  ran against the live system, not just your conclusion.

  Recorded because it was already decided and never written down:
  `home-lab/decisions/DECISIONS.md` 2026-08-27 accepted that consumption is
  "via a sibling checkout plus one line in the consuming repo's `CLAUDE.md`."
  This is that line. Its eleven-day absence is why VM 103's rebuild sat
  unrecorded in home-lab for a week.

## Rules

- Before proposing or researching an approach, check the decision register —
  don't re-suggest something already tried and rejected without saying so.
  It's fine to resurface a rejected approach, but say that it was rejected
  before and why it's worth revisiting.
- Update `Working.md`, memory, and the decision register as changes happen —
  err toward updating more often rather than batching.
- If the docs and the actual repo state disagree, flag it and suggest a memory
  audit rather than silently patching over it.
- **Memory file scope rule**: a memory file's job is its one-line description
  in `MEMORY.md`. Split on scope drift, not line count. Compress resolved
  narrative into a `DECISIONS.md` entry once settled.
- Destructive or hard-to-reverse actions require explicit confirmation
  regardless of `.claude/settings.json`.
- Treat `git push` and any deploy as outward-facing actions needing explicit
  go-ahead **each time**. Committing locally is fine; publishing is gated.
- **Verify the verification.** Before reporting an all-clear, confirm the check
  you ran could actually have detected the problem in question. State what was
  verified and how, not just the outcome.

## Project-specific rules

- **Research before designing from scratch.** State the problem in
  domain-neutral terms, ask which other fields already own it, and read those.
  This produced the best material in both research specs so far — see
  `decisions/DECISIONS.md` 2026-08-25.
- **Never design anything that shows the model a rendered map.** Not ASCII,
  not a tile grid, not a screenshot. This is a hard commitment, not a
  preference — see `docs/PURPOSE.md` design commitment #1 and
  `research/2026-08-25-spatial-perception.md`.
- **Mark verified vs proposed.** DFHack tool availability changed
  substantially in the v50 transition; several tools are present as files but
  tagged `unavailable`. Check `memory/dfhack-environment.md` before assuming a
  tool works, and check the local install before assuming API surface exists.
- **This repo is public.** Infrastructure specifics (Proxmox host, Coolify,
  IPs, hostnames, tokens) go in gitignored `infra/local.*` with committed
  `infra/local.example.*` counterparts. Never commit the specifics.
