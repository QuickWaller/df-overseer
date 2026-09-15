# Memory index

Repo memory: context that isn't derivable from the code. One line per file.

- [DFHack environment](dfhack-environment.md) — verified versions, paths,
  script-paths.txt, the remote interface, and which tools are shipped-but-
  unavailable in 53.16. Check this before assuming any DFHack tool works.

- [Agent memory standards](agent-memory-standards.md) — Letta/Mem0/Zep, Anthropic's
  compaction + memory tool stack, where our four stores map onto the standard,
  and why we deliberately don't let the model edit its own memory.

**Eight files below hold 45 decision-register rows that were over 300 words,
moved verbatim out of `decisions/DECISIONS.md` on 2026-09-15 (see that date's
register row for the trim itself). Each register row that moved keeps its
original date, decision and status, with only its reason cell replaced by a
short summary pointing here.**

- [Embark automation](embark-automation.md): the title-screen bootstrap, the
  click-registration and coordinate-frame investigations, both real fort
  foundings (Artobcatten, Uniboslan), and the re-embark automation gap.
- [Live viewing and relay](live-viewing-and-relay.md): screenshot capture, the
  relay VM, the tunnel plus noVNC chain, the Steam-graphics transplant, and
  the personal-control VNC channel.
- [Perception tool builds](perception-tool-builds.md): the spatial-perception
  DFHack tool builds, `docs/PURPOSE.md` build order items 2 through 8, plus
  the branch merge and the combat/diff fold.
- [Autonomous play and tool bugs](autonomous-play-and-tool-bugs.md): the
  bounded autonomous-play experiments on Uniboslan and the real tool bugs
  they found live (coordinate resolution, quickfort anchoring, a guessed Z).
- [Fort operations and incidents](fort-operations-and-incidents.md): labor
  management and autolabor, the missed kea attack, the quicksave root cause,
  the cpu-setting/quorum-loss incident, and a pause_state false alarm.
- [Compliance eval](compliance-eval.md): the doctrine-compliance harness
  build, the DeepSeek provider, and the full 180-cell sweeps against both
  providers, including the Opus cost overrun.
- [Agent architecture and safety](agent-architecture-and-safety.md): the
  pause-vs-throttle game-time argument, why a specialist role's value is
  context partitioning, and the two safety detectors built but not yet run.
- [Infra incidents](infra-incidents.md): a systemd crash loop and a VM-clone
  IP collision, both in this project's own scope, root-caused and fixed.

## Local only, not in this repo

These two are **gitignored** (`infra/local.*`). They are the authoritative
records for their areas, they just cannot be public: both are made almost
entirely of host addresses, hostnames, MACs and pool scopes. If you have
cloned this repo you do not have them, and nothing else here depends on
their contents.

- `infra/local.proxmox-access.md` — the live access layer: host, the
  `DFOverseer` / `DFOverseerNode` roles, the pool/storage/node/SDN scopes, and
  **the three ways a grant silently misses** (wrong privilege / wrong path /
  wrong subject). Verified boundaries, verified snapshot cycle, VM 101's specs.
  Read back from the API, not assumed.
- `infra/local.df-vm-install.md` — the fortress VM's game install: paths, the
  Xvfb headless launch, the save location, silent `-gen` worldgen and its ~25%
  silent-failure rate, and the measured worldgen memory ceiling. Plus the
  2026-08-28 process-lifecycle facts the systemd work was built on: DF
  ignores SIGTERM, `dfhack-run` colours its output and reports a connect error
  as ordinary text, launch to RPC is ~3-10s. And the 2026-08-30 result:
  `df-xvfb.service`/`df-fortress.service` exist, `onboot=1` is set, and a real
  guest reboot proved both come back unattended (host-reboot survival itself
  still untested).
- `infra/local.hardware-plan.md` — the RAM, disk and node plan for the two-box
  cluster, including what was harvested from the stripped Omen.

## See also

The main design artifacts live in `docs/`, not here:

- `docs/PURPOSE.md` — what the project is, design commitments, scope,
  operating parameters, build order.
- `docs/MEMORY-ARCHITECTURE.md` — the *overseer agent's* memory and learning
  design (four stores, hypothesis promotion, the wiki as hypothesis source).
  Not to be confused with this file, which is the *repo's* memory index.

- `learning/ledger/README.md` - the fort ledger: the fifth store, and the
  only one that is built. Explains why the fields are what they are and what
  the schema deliberately cannot do. (Moved under `learning/` 2026-09-12,
  grouped with `learning/predictions/` for their real code coupling.)

Long-form research with citations lives in `research/`.
