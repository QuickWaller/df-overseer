# Deploy and live check: queue fixes, amend/abandon, buildingplan material filter

Date: 2026-10-01. Repo `f2058dd` deployed to VM 103 with
`scripts/ops/deploy-vm103.sh 2026-10-01-ab`: 14 files, hashes verified on
arrival and at the install path, no CRLF, SQLite online backup and file
backups under the tag's backup directory. Imports and `doctrine.validate`
passed in the server venv; `dfmcp-server` restarted `active`. The fort stayed
paused throughout; nothing in it was built or changed.

## Queue (handoffs/2026-10-01-queue-bugs-and-amend.md)

- Role tool counts over a real MCP client: overseer 89 (was 87: `queue__amend`,
  `queue__abandon`), architect 52, consultant 29, quartermaster 24,
  conductor 16.
- `queue.abandon` on a nonexistent project, as the overseer: refused before
  any write ("does not refer to an existing project"). As the architect:
  refused by the allowlist. `queue.project_status`: "(no projects)".
- Not exercised live: a real amend or abandon (it would leave permanent test
  records in the fort's queue); the offline suites cover the logic.

## Material filter (handoffs/2026-10-01-buildingplan-material-filter.md)

**Found live: the write is a silent no-op.** A dry run of `building.build`
for a constructed wall (`Cw`) near the Well reported
`filter_material_names: ["WOOD", "material_0_243"]`. A reversible
`dfhack-run lua` check (`bpcheck.lua` here) on Construction/Wall filter 0:

| Step | Enabled materials |
|---|---|
| before | 367 of 367 |
| set `WOOD`, `material_0_243` (what the tool writes) | 367: both names dropped, filter unrestricted |
| set `shale` (the real `MaterialInfo:toString()` name of 0:243) | 1 |
| set `{}` (restore) | 367 of 367 |

Cause: `buildingplan.cpp:918-921` keeps only names in its `mat_cache`, keyed
by `MaterialInfo::toString()`; an empty result resets the filter to
unrestricted (`:926`). The offline stub accepted any name, so the tests could
not see it. Also confirmed: the tool's own read of `getMaterialFilter`
(`props.enabled == "true"`) is correct, and `df.construction_type` reverse
lookup works (`Wall` = 1). The deployed code is harmless meanwhile (it writes
names that are dropped, then restores). Sent back to the stream to build the
list from buildingplan's own vocabulary and read it back after writing.

My own first read of the check miscounted (it treated each returned table as
true); corrected by reading `props.enabled`, as recorded above.
