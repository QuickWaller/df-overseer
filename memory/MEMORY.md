# Memory index

Repo memory: context that isn't derivable from the code. One line per file.

- [DFHack environment](dfhack-environment.md) — verified versions, paths,
  script-paths.txt, the remote interface, and which tools are shipped-but-
  unavailable in 53.16. Check this before assuming any DFHack tool works.

- [Agent memory standards](agent-memory-standards.md) — Letta/Mem0/Zep, Anthropic's
  compaction + memory tool stack, where our four stores map onto the standard,
  and why we deliberately don't let the model edit its own memory.

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
  silent-failure rate, and the measured worldgen memory ceiling.

## See also

The main design artifacts live in `docs/`, not here:

- `docs/PURPOSE.md` — what the project is, design commitments, scope,
  operating parameters, build order.
- `docs/MEMORY-ARCHITECTURE.md` — the *overseer agent's* memory and learning
  design (four stores, hypothesis promotion, the wiki as hypothesis source).
  Not to be confused with this file, which is the *repo's* memory index.

- `ledger/README.md` - the fort ledger: the fifth store, and the only one
  that is built. Explains why the fields are what they are and what the
  schema deliberately cannot do.

Long-form research with citations lives in `research/`.
