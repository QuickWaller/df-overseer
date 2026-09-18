"""dfseries: the time-series store for sampler output.

Imports contract-format JSONL (`docs/TIMESERIES.md`) into its own SQLite
database, entirely separate from `production/`'s static graph database. See
`dfseries/importer.py` for the import path, `dfseries/timeline.py` for
rollback/lineage handling, and `dfseries/trend.py` for the read side.
"""
