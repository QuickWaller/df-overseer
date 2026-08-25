# Memory index

Repo memory: context that isn't derivable from the code. One line per file.

- [DFHack environment](dfhack-environment.md) — verified versions, paths,
  script-paths.txt, the remote interface, and which tools are shipped-but-
  unavailable in 53.16. Check this before assuming any DFHack tool works.

- [Agent memory standards](agent-memory-standards.md) — Letta/Mem0/Zep, Anthropic's
  compaction + memory tool stack, where our four stores map onto the standard,
  and why we deliberately don't let the model edit its own memory.

- [Proxmox access](proxmox-access.md) — **authoritative record** of the live
  access layer: host, role `DFOverseer` and its 16 privileges, the pool/storage
  scopes, verified boundaries (confirmed by denial), verified snapshot cycle,
  and VM 101's specs. Read back from the API, not assumed.

## See also

The main design artifacts live in `docs/`, not here:

- `docs/PURPOSE.md` — what the project is, design commitments, scope,
  operating parameters, build order.
- `docs/MEMORY-ARCHITECTURE.md` — the *overseer agent's* memory and learning
  design (four stores, hypothesis promotion, the wiki as hypothesis source).
  Not to be confused with this file, which is the *repo's* memory index.

Long-form research with citations lives in `research/`.
