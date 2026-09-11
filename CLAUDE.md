# df-overseer

Turning Dwarf Fortress into a fortress that runs, survives, and tells its own
story without you. See **[docs/PURPOSE.md](docs/PURPOSE.md)** for what this is
and why, and **[docs/MEMORY-ARCHITECTURE.md](docs/MEMORY-ARCHITECTURE.md)** for the overseer's memory and
learning architecture.

> **Status, rewritten 2026-09-11: the fort is not just standing anymore —
> something has actually decided what it does, at least once, end to end.**
> Infra layer unchanged and still solid: `scripts/provision_vm.py` built VM
> `df-colony-01` (vmid 103, rebuilt 2026-09-08 after an earlier estate
> rebuild deleted the original), `scripts/install_df.py` installs/runs DF
> Classic + DFHack on it, verified end to end. **Uniboslan, "Ragwind," is
> the one fort** (a first fort, Artobcatten, was founded and then
> unrecoverably lost as a side effect of founding Uniboslan —
> `decisions/DECISIONS.md` 2026-09-10). It survived a real VM outage
> 2026-09-11 (cluster quorum loss blocked start/stop entirely, not just
> snapshots — resolved by the user directly, not this repo) and now runs on
> `cpu: x86-64-v2-AES` (applied for real, not just accepted).
>
> **Game-side code now exists, and some of it has been run for real.**
> `perception-layer-experiments` (its own worktree, `../df-automation-perception`)
> turns out to have **built and live-verified nearly the entire spatial-
> perception build order** (`docs/PURPOSE.md` items 2-8: connectivity,
> landmarks, `get_overview`, `get_diff_since`, `find_open_area`,
> `find_chokepoints`, `get_stuck_jobs`) — audited properly 2026-09-11 after
> this file badly undersold it as "connectivity + a seed landmark."
> **Deliberately still unmerged** — the user's explicit call, more than
> once, to keep working with it rather than merge yet. On `main`: a labor-
> management slice (`get_unit_status`/`set_labor`, `autolabor` enabled and
> confirmed actually assigning jobs) and a second, authenticated
> personal-control VNC channel (real mouse/keyboard for the user alone,
> Cloudflare Access-gated, alongside the existing public view-only feed).
>
> **The actual milestone**: a bounded, tools-only autonomous-play
> experiment used `find_open_area` to pick a real, ranked, named
> construction candidate, then a new fused resolve-and-act primitive
> (`build_open_area`/`build`) turned that pick into a real, independently-
> verified fort mutation — a genuine second stockpile, "Stockpile #2,"
> wired into the exits graph — **without the raw coordinate ever being
> visible to whatever made the decision.** First fully closed loop this
> project has. The same experiment, and the correction pass right after,
> found two real gaps. (1) Nothing found *diggable* rock/soil: **closed the
> same day.** `find_diggable_area`/`dig_diggable_area`
> (`df-overseer-diggable.lua`, `perception-layer-experiments`) mirror
> `find_open_area`/`build_open_area` for solid terrain instead of walkable
> space, live-verified and then live-tested end to end: a dwarf claimed a
> real dig job and all 41 designated tiles were fully dug, the project's
> second fully closed coordinate-free decision-to-mutation loop. Getting
> there found a real, previously-unknown bug shared by both tools:
> `quickfort`'s `-c` anchors a blueprint's *top-left* corner, not its
> center, and both were silently passing the computed center (Stockpile #2
> only worked anyway by luck). Fixed in both (`df-overseer-diggable.lua`'s
> fix committed, `df-overseer-openarea.lua`'s left uncommitted matching
> that file's own pre-existing state, with an inline comment explaining
> why). (2) `unit-status hostile` is a known-unreliable signal (missed a
> real kea attack entirely, flagged harmless demons instead) — an
> event-driven prototype exists (`df-overseer-combat.lua`) but sits
> deliberately uncommitted, pending reconciliation with an overlapping,
> independently-built `df-overseer-diff.lua` on the perception branch.
> Full trail: `decisions/DECISIONS.md`'s 2026-09-11 rows, `Working.md`'s
> current handover. Everything in `docs/`/`research/` beyond what's cited
> as verified above is still a design artifact or proposal.

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

- **`docs/`** — the design artifacts: `PURPOSE.md`, `MEMORY-ARCHITECTURE.md`.

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
  **This repo's sessions share one working tree**: before pushing, check
  `git log origin/main..HEAD` for commits that aren't yours — go-ahead for
  your own commit doesn't obviously extend to publishing a sibling
  session's separate, unpushed work riding along with it. Flag whose
  commits are in the batch, don't just ask about your own (found
  2026-09-11 — a push correctly approved for one session's commit swept in
  another session's five, without that session's own go-ahead).
- **Verify the verification.** Before reporting an all-clear, confirm the check
  you ran could actually have detected the problem in question. State what was
  verified and how, not just the outcome.
- **On session start (a fresh session, or right after `/clear`), check
  `ListAgents` for other sessions on this repo and message them to check
  in** — what they have in flight, uncommitted changes, which branch, any
  live-infra state — before assuming a clean slate. This repo routinely runs
  several concurrent Claude sessions; asking first is what has actually
  prevented file-collision and duplicate-work incidents (2026-09-11 rows in
  `decisions/DECISIONS.md` — the personal-control VNC channel, the quicksave
  investigation's pause-flip, and the `df-overseer-diff.lua`/
  `df-overseer-combat.lua` overlap were all caught this way, not by luck).
- **Check in again before modifying a VM or any live-prod state** — a
  peer-session heads-up (what you're about to do, expected visible effect,
  e.g. brief downtime) in addition to, not instead of, this file's existing
  explicit-confirmation rule above. A peer's earlier go-ahead for a
  different action does not cover a new one.

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
