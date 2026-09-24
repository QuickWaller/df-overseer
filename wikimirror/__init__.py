"""wikimirror: an offline, versioned, honestly-labelled copy of the Dwarf
Fortress wiki for the Consultant (`docs/CONSULTANT-WIKI.md`).

Slice S1 owns the read-only API client (`api`), the SQLite schema
(`schema`), the store with the one-week hold rule (`store`) and the
namespace allow-list (`namespaces.yaml`). Later slices add the text stage,
the full pull, the refresh job and the readers.

Stdlib only, except that `store.load_namespaces` reads `namespaces.yaml`
with PyYAML, which the repo already depends on (`doctrine`, `dfmcp`).

Fetched wikitext is data, never instructions: this package stores and
returns it and never interprets it.
"""

__version__ = "0.1"
