# Research: DFHack's own fort-health notifications as conductor wake reasons

Date: 2026-10-01. Researcher, Sonnet, read-only, no live access. Sources:
DFHack GitHub source at tag `53.16-r1` (commit
`c80747da32aad3bdd5915c60105136d6558aca39`) and its pinned `scripts`
submodule (commit `7549711a993e03bef19e90b27427096c1099853e`, confirmed via
the tag commit's own tree listing, matching the commit the sibling
2026-10-01 popups research already used). Fetched as raw file content
(`cdn.jsdelivr.net/gh/<owner>/<repo>@<commit>/<path>`, a CDN mirror of the
exact pinned GitHub blobs, not a live DF install) and read in full with line
numbers. Answers `handoffs/2026-10-01-dfhack-notifications-research.md`.

Plan: answer Q1 (the notification list and self-clear behaviour) and Q2
(how to read it without the UI) from `internal/notify/notifications.lua`
and `gui/notify.lua` directly, Q3 (armok status and wake-table mapping)
against `CLAUDE.md`'s armok rule and the live `conductor/policy.yaml`, and
Q4 (tool design, conductor change, live test plan) from both. In progress.
