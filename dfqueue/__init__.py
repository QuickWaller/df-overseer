"""dfqueue: the proposal queue.

One append-only, write-time-validated queue per fort — the channel and audit
log `docs/AGENT-ARCHITECTURE.md` §4 specifies ("The queue is the channel and
the audit log"). See `dfqueue/README.md` for the record kinds, the closed
vocabularies, and what is deliberately not built here yet.
"""
