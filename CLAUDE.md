# df-overseer

Turning Dwarf Fortress into a fortress that runs, survives, and tells its own
story without you. See **[docs/PURPOSE.md](docs/PURPOSE.md)** for what this is
and why, and **[docs/MEMORY-ARCHITECTURE.md](docs/MEMORY-ARCHITECTURE.md)** for the overseer's memory and
learning architecture.

> **Status: design, plus a live infrastructure layer.** The Proxmox access
> layer exists and is verified against the API (`memory/proxmox-access.md`),
> and `scripts/` provisions the VM. Nothing of the *game* side is implemented —
> no perception layer, no agent, no toolkit. Everything in `docs/` and
> `research/` is still a design artifact; claims marked *verified* were checked
> against the local DFHack install, the live API, or a primary source, and the
> rest are proposals.

This repo is managed with Claude Code using a structured memory system,
following the pattern published as
[`claude-code-managed-repo-template`](https://github.com/QuickWaller/claude-code-managed-repo-template)
(MIT) — the conventions below (`Working.md`, `memory/`, `decisions/`, the Rules
section, the `executor`/`researcher` agents) come from that template. Read this
file first in any session.

## Structure

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
