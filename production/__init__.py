"""The production and logistics model: schema, store, and the two-pass
extractor. See `docs/PRODUCTION-MODEL.md` for the design and
`handoffs/2026-09-18-production-package.md` for this package's own brief.

Named `production` deliberately, checked before use: nothing on this
project's `sys.path` (stdlib, PyYAML, or any package already in this repo)
is named `production`, so this package shadows nothing, the same class of
trap `mcp/` and `queue/` would have been (`CLAUDE.md`).
"""
