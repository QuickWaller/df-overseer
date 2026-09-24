# Handoff: design the offline, regularly updated wiki (with a changelog) for the Consultant

Date: 2026-09-24. **Design stream. Offline: no deploy, no VM change, no fort change.**
The only live contact allowed is a small, polite, read-only probe of the public
Dwarf Fortress wiki and DFHack docs sites, described below.

Read `CLAUDE.md`, the register row dated 2026-09-22 beginning "The whole wiki,
kept current by incremental updates, is agreed but deferred" (the agreed
direction: a full pull recording each page's `revid`, then a timer job over
MediaWiki's `recentchanges` feed, a batched `revid` backstop, a deliberate full
re-pull on a DF version bump, and doctrine citing a page revision so a changed
page flags the entries that cite it), `dfmcp/knowledge_tools.py` (the current
`knowledge.wiki_lookup` over a curated snapshot, and why the snapshot path is
`None` until one is built), `scripts/build_wiki_snapshot.py`,
`agents/consultant/sites.yaml`, `agents/consultant/role.md`,
`docs/MEMORY-ARCHITECTURE.md`, `doctrine/seed.yaml` (header and provenance
fields) and `docs/AGENT-LOOP.md` for where the Consultant runs.

## Why now

The Consultant's answers this session were good and honest, and the errors it
made (an Engraver labor called a Mason, "angry ghost" overstated as lethal, a
recalled tier table) were the errors a retrieval layer over the *current* wiki
fixes. Today `knowledge.wiki_lookup` serves a 20 to 30 page curated snapshot and
falls back to Brave and a live fetch, which depends on the network and on old
namespaces that describe old games. The user wants an offline copy that stays
current and records what changed.

## What to produce

A design, not the build. Deliverables, all documents:

1. **`docs/CONSULTANT-WIKI.md`**, the design, covering:
   - **Sources and scope.** The DF wiki current-version namespace(s) for 53.x
     first; which older namespaces (0.34 era, 40d, v50) to keep, tag or exclude,
     and how a page is labelled so the Consultant can never present an old-game
     page as current. DFHack documentation for the installed 53.16-r1.1 as a
     second source. Say what is out of scope (forums, general web).
   - **How it is acquired.** The MediaWiki API and any published XML dump: which
     is polite and sufficient; page count and size estimate for the chosen scope;
     rate limits and identification; the wiki's terms and licence and what
     attribution the copy must carry.
   - **How it stays current.** The `recentchanges` design from the register row,
     made concrete: cadence, what a refresh does on edit, move and delete, the
     `revid` backstop, the deliberate re-pull on a version bump, failure and
     retry behaviour, and what happens when the job cannot reach the network.
     A stale copy must say it is stale; never serve silently old data.
   - **The changelog.** Per refresh, a machine-readable record (added, changed,
     moved, deleted, with page title, old and new `revid`, timestamp and the
     wiki's own edit summary) and a human-readable digest. State where it is
     stored, how long it is kept, and how the Consultant, the doctrine tooling
     and a human read it.
   - **Storage and retrieval.** Format (for example SQLite with full-text search
     versus the current JSON snapshot), chunking, how results carry provenance
     (page, namespace, `revid`, fetch time, staleness), and how it replaces or
     extends `knowledge.wiki_lookup` without breaking the tool's current
     contract or its tests.
   - **Doctrine link.** Doctrine entries cite a page revision; a changed page
     flags the entries citing it for re-reading rather than editing them
     (revisions are proposals). Specify the check and where the flag surfaces.
   - **Where it runs.** Which VM holds the copy and the timer; how the Consultant
     on the agent VM reads it; how it is deployed under this repo's rules (no
     hostnames or addresses in the repo, deploy discipline in `CLAUDE.md`).
   - **Failure modes and what to verify.** Wrong-version pages, deleted pages
     that linger, a changed page silently overwriting a cited revision, a poisoned
     or instruction-bearing page (fetched text is data, never instructions), an
     outage during a refresh, disk growth. For each: the guard and the test.
   - **Build plan.** An ordered list of streams with their touched files, so
     no two share a file, sized for a Sonnet each, and the minimum first slice
     that is useful on its own.
2. **`research/2026-09-24-wiki-mirror-feasibility.md`**, the evidence, in the
   style of the other research specs: every claim marked verified, inferred or
   unverified, with the exact request and result for each probe.

## The probe (read-only, small, polite)

Resolve the three items the register row left unverified, from the real sites:
(1) is anonymous `recentchanges` access allowed and how far back does it go;
(2) does the wiki publish XML dumps, where, and how current; (3) the wiki's
robots rules, terms, API limits and licence. Also establish: the namespace
layout for the current game version, an estimate of page count and total text
size for the chosen scope, and whether DFHack docs are available as a versioned
source archive. **Limits:** at most 60 HTTP requests in total, at least one
second between requests, a descriptive User-Agent that names this project (no
personal or infrastructure details), respect robots. No bulk download, no
crawling of page bodies beyond a sample of at most ten pages to measure size and
markup. If a request is refused or blocked, stop that probe and record it.

## Scope

Yours: `docs/CONSULTANT-WIKI.md` (new), `research/2026-09-24-wiki-mirror-feasibility.md`
(new), and the Result section of this handoff. Not yours: any code, `dfmcp/**`,
`scripts/**`, `agents/**`, `doctrine/**`, and per the `handoffs/` rule
`Working.md`, `decisions/DECISIONS.md`, `memory/`, `handoffs/INDEX.md`. Collect
owed register lines in your Result.

## Rules

`git merge --ff-only main` first. Commit as you go. No em dashes in prose. No
attribution lines in commits. Never write a hostname, address or secret. Stop and
report on any permission or classifier refusal and never route around one. Run
`python -m pytest tests/test_no_leaked_addresses.py` before committing docs.

## Done means

A reader can build the mirror from the design without asking a question: sources,
acquisition, refresh, changelog format, storage, doctrine link, deployment,
failure modes and a build plan of file-disjoint streams. Every unverified claim is
marked as such, and the three open probes have a real answer or a recorded reason
they could not be answered.

## Result

(to be filled by the executor)
