# The Consultant's offline wiki: design

**Status: design, 2026-09-24. Nothing here is built.** Evidence for every factual
claim about the wiki is in `research/2026-09-24-wiki-mirror-feasibility.md` (marks
**[V]** verified, **[I]** inferred, **[U]** unverified); this document cites it as
"the research note" and repeats a mark only where a decision hangs on it.
Handoff: `handoffs/2026-09-24-consultant-wiki-design.md`. Agreed direction:
register 2026-09-22, "The whole wiki, kept current by incremental updates, is
agreed but deferred".

## 1. What this is for, and the one rule that governs it

The Consultant's good answers this session and its errors (an Engraver labor named
Mason, "angry ghost" overstated as lethal, a tier table from memory) are the errors
a retrieval layer over the **current** wiki fixes. Today `knowledge.wiki_lookup`
serves a 20 to 30 page curated JSON snapshot that was never built
(`DEFAULT_WIKI_SNAPSHOT_PATH is None`), so it refuses every call and the role falls
back to Brave search and a live fetch, which depends on the network and can land on
old-game namespaces.

The governing rule, from `docs/MEMORY-ARCHITECTURE.md` ("The version-namespace trap"):
**no result may ever let an old-game page, or a stale copy, read as current 53.16
knowledge.** Every result carries its version, its revision, its fetch time and its
freshness, and a copy that cannot prove it is fresh says so on every result.
Everything retrieved is a `prior` at most, never `verified` (the same ceiling
`agents/consultant/sites.yaml` states), and retrieved text is data, never
instructions.

## 2. Sources and scope

### 2.1 Included

| source | what | version label | in |
|---|---|---|---|
| **DF wiki, main namespace (ns 0)** | 4,450 non-redirect pages, 16.1 MB wikitext **[V]** | `game_version` = the wiki's own `Template:Current/version`, read at pull time (it says `53.16` today **[V]**), `is_current = 1` | slice 1 |
| **DF wiki, `Template` namespace (ns 10)** | at least 1,000 templates **[V]**; needed to read parameter-carrying pages, stored, not searchable | n/a | slice 2 |
| **DFHack documentation** | the installed 53.16-r1.1 tree on VM 103 (see 2.4) | `53.16-r1.1`, `source_kind = game-data` | later slice |

### 2.2 Older namespaces: exclude by default, tag if ever added

The wiki keeps one namespace per game version **[V]**: `DF2014` (0.47.05), `v0.34`
(0.34.11), `v0.31`, `40d`, `23a`, and a `Masterwork` mod namespace. Each of the
three measured old namespaces has at least 1,500 pages, so the old games together
outnumber the current main namespace. Decision:

- **Excluded, never fetched:** `40d`, `23a`, `v0.31`, `v0.34`, `Masterwork` (a mod;
  its pages must never read as vanilla), and all Talk, User, File, Category, Help,
  `Utility`, `Modification`, `Tutorial`, `Bloodline`, `Unused`, `Module` and project
  namespaces. Forums and the general web stay out of scope, reached only through the
  existing `web.search` and `web.fetch` tools.
- **`DF2014` (0.47.05): off in v1.** Its one legitimate use is "did this change
  since the last pre-Steam game", useful for spotting a stale community belief. If
  added later (slice 9) it is stored with `is_current = 0`, `game_version = '0.47.05'`,
  never returned by `wiki_lookup` or `wiki_search` unless the caller passes
  `include_legacy: true`, and every such result opens with a fixed line: "OLD GAME
  (0.47.05). Not this fort's version." The default can never leak it because
  ingestion is by an allow-list of namespace **ids**, not by a title prefix (the
  current `version_namespace_of` splits on the first colon, a heuristic its own
  docstring flags; ids come from the API's `ns` field instead).

### 2.3 How a page is labelled so an old page can never pass as current

- **The namespace id is the classifier, not the banner.** The wiki's own
  `{{av}}` template (`Template:ArticleVersion`) treats main = current ("some content
  may still need to be updated") and every other namespace = "older version" **[V]**.
  But main-namespace pages can lack the banner **[V]**, so a banner is never read as
  evidence of version.
- A namespace-to-version table lives in data (`wikimirror/namespaces.yaml`, slice 1):
  ns id, wiki name, `game_version` (or `from: Template:Current/version`), `is_current`,
  `ingest: true|false`, `label`. One data row per namespace, no code branch.
- **The lag caveat is part of the label.** Because the wiki says current content
  "may still need to be updated", every current-namespace result carries
  `wiki_note: "Main-namespace wiki content can lag the game; recheck against
  game data."` and `recent_edit: true` when its revision is under 48 hours old
  (a recent edit may be vandalism or an unreviewed change; see 9).
- **Version cross-check.** Each refresh reads `Template:Current/version` and compares
  it with the install's `df` version (`agents/consultant/sites.yaml`, `install.df`).
  Any mismatch sets `meta.version_status = 'wiki_ahead'` or `'wiki_behind'`, and
  every result then says "wiki current version X, this fort runs Y". A change in the
  wiki's current version is a **version bump** (see 4.7).

### 2.4 DFHack documentation: the installed tree, not the public site

For 53.16-r1.1 the published docs are not an exact match: `docs.dfhack.org` has
`53.16-r1` (equal to `stable` at probe time) and **no** `53.16-r1.1` slug, and its
`robots.txt` steers crawlers to `/en/stable/` only **[V]**. The design therefore
**does not crawl `docs.dfhack.org`**. The exact source is the installed DFHack tree
on VM 103, which the existing `dfhack.source_search` and `dfhack.source_read` tools
already serve and which is the authority per `agents/consultant/sites.yaml`.
A later slice adds a `source = 'dfhack'` index over that tree so `knowledge.wiki_search`
can search wiki and DFHack docs with one query and label each result. It carries
`source_kind: game-data`, `game_version: 53.16-r1.1`, refresh only at a DFHack
upgrade (an explicit re-index command, no timer). **[U]:** whether the installed tree
contains `.rst` doc sources and script help text; the slice's first step is one
`dfhack.source_search` call on the VM to check.

## 3. Acquisition

### 3.1 Route: the MediaWiki API, anonymous, read-only

No XML dump is published: `/dumps/` leads nowhere and a wiki search for dump pages
returns nothing **[V]**; a third-party WikiTeam archive was not checked **[U]** and
is not needed. The API is anonymous-readable **[V]**, MediaWiki 1.35.11 **[V]**, no
rate-limit headers and no throttling seen over 51 requests **[V]**. The wiki
publishes no `robots.txt` (the path leads to a nonexistent page) **[V]**. This is
**not** WikiTeam's `dumpgenerator.py`, for the reasons `scripts/build_wiki_snapshot.py`
already records: a whole-history XML mirror is a different job, and this needs
current text only.

### 3.2 Scale of a full pull

Ns 0: 4,450 pages, 14.8 MB without the 1,574 `/raw` stubs, 16.1 MB with **[V]**.
Bodies come at 50 titles per request for anonymous users **[V]** (500 needs a
high-limit right), so about 89 requests for ns 0, about 20 for templates: roughly 110
requests **[I]**. At one request per 2 seconds that is under 4 minutes of wall clock
and about 20 MB of JSON; there is no need for a bulk mechanism. The enumeration
itself (all titles with `lastrevid`, `length`, `touched`) is 9 requests via
`generator=allpages&prop=info&gaplimit=500` **[V]**.

### 3.3 Politeness, identification, licence

- **Identification.** Every request carries
  `User-Agent: df-overseer-wikimirror/<version> (+<contact url from env DFWIKI_UA_CONTACT>; read-only mirror for a hobby project)`.
  The contact value is an environment setting, never committed (public repo), and the
  client **refuses to start without it**. The existing `_USER_AGENT` strings
  (`+https://github.com -- ...`) are placeholders and are replaced.
- **Rate.** At most one request every 2 seconds (twice the probe's 1.2 s), one
  connection, no parallelism. Per-run request budget 400 (a refresh normally uses 5
  to 60), per-day budget 1,500, both counted in the database, exceeded means the run
  aborts with `status = 'budget'`. A full pull has its own budget (800).
- **Backoff.** 429 or 5xx: honour `Retry-After` if present, otherwise wait 5, 30,
  120 seconds, at most 4 tries per request; a 403, or three 429s in one run, aborts
  the run as `blocked` and the copy stays as is (and says it is stale, 5.2).
- **Read only.** GET only; `action=query` and `action=paraminfo` only; no login, no
  edit, no `action=parse` per page. The client has an allow-list of `action` values.
- **Licence and attribution.** The wiki states "MIT and GFDL" **[V]**: contributors
  release under both. The copy carries, in the database metadata and in every result:
  `license: "MIT and GFDL (Dwarf Fortress Wiki contributors)"`, the wiki source
  (`dwarffortresswiki.org`), the page title, the permalink
  `index.php?title=<T>&oldid=<revid>` and a link to the page's history (where the
  authorship credit lives). The digest and any published chronicle that quotes wiki
  text must attribute the same way. **Flag for the user:** the licence page names no
  per-page attribution form, and this reading of GFDL's history requirement [I] is not
  legal advice.

## 4. Staying current

### 4.1 Signals, cheapest first

| signal | what it gives | cost | reach |
|---|---|---|---|
| `list=recentchanges` (anonymous, 500 per request) **[V]** | edits, new pages, moves, deletes with `revid` and `old_revid` | 1 request per run | **90 days** **[V]**, about 28 entries a day over all namespaces **[V]** |
| `list=logevents` `letype=delete\|move` (anonymous) **[V]** | deletes and moves, with `params.target_title` | 1 to 2 requests | not age-pruned **[I]** |
| revid sweep: `generator=allpages&prop=info&gaplimit=500` **[V]** | `lastrevid` for every page | 9 requests for ns 0 | complete, any age |
| `Template:Current/version` | the wiki's current game version | 1 request | now |

### 4.2 Cadence

- **Refresh (recentchanges): every 6 hours**, with a randomised delay of up to 30
  minutes. At about 15 main-namespace edits a day **[V]** each run touches a handful of
  pages; the cost is one feed request plus one body request per 50 changed titles.
  Six hours is not a freshness requirement (the game does not change at wiki
  speed); it is short enough that a dead timer is noticed within a day (5.2).
- **Sweep (backstop): weekly**, and also forced when any of these hold: the recent
  changes cursor is older than 60 days (the feed keeps 90), a refresh failed to
  advance the cursor for more than 7 days, or an operator asks. It closes anything
  the feed missed (a rolled-off or skipped entry).
- **Version-bump re-pull: deliberate, never a timer** (4.7).

### 4.3 What a refresh does (the algorithm)

State in `meta`: `rc_cursor_ts` (the newest timestamp fully processed) and
`rc_cursor_ids` (the rcids seen at that timestamp).

1. Take the run lock (a lock file plus a `refresh_runs` row `status = 'running'`); a
   second concurrent run exits. A stale lock from a crashed run is broken after 2
   hours, recorded.
2. **Feed.** Query `recentchanges` with `rcdir=newer`, `rcstart = rc_cursor_ts minus 10
   minutes` (a replication and clock-skew overlap), `rcnamespace = ingested ids`,
   `rctype=edit|new|log`, `rcprop=title|ids|timestamp|comment|sizes|loginfo`,
   `rclimit=500`, following `rccontinue`. Deduplicate by `rcid` so the overlap is
   harmless. Log entries of other types than `move` and `delete` (`upload`,
   `newusers`, `block`) are dropped.
3. **Also read `logevents` (delete, move)** since the cursor, so a move or delete is
   caught even if its feed entry was on a page the namespace filter hid (a move
   between namespaces appears under the old one).
4. **Fold** the events per page (`pageid`): the last event decides.
   - **edit or new** -> fetch the current body (below).
   - **move** -> rename the row in place (same `pageid`), record the old title as an
     alias, then refetch only if the revision changed. Moving into an excluded
     namespace becomes a **delete** from the mirror's point of view (the page left
     scope). Moving into scope from outside is an **add**.
   - **delete** -> the row becomes a **tombstone** (`state = 'deleted'`,
     `deleted_utc`), its body and every chunk and FTS row are **removed in the same
     transaction**, so a deleted page cannot be served (9).
   - **restore** (the delete log's `restore` action) -> refetch as an add.
   - a page in the changed set that the API returns as `missing` is treated as a
     delete (a race between feed and fetch), and is confirmed by the next sweep.
5. **Fetch bodies** for the edit, new, move and restore set: batches of 50 titles,
   `prop=revisions|info`, `rvprop=ids|timestamp|comment|content`, `rvslots=main`,
   `redirects` off (redirects are stored as redirects, 4.6). Store the **`revid` the
   response returns for each page**, not the feed's `revid`, so a newer edit that
   landed in between is stored as what it is. Skip a page whose stored `revid` is
   already at or above the fetched one (idempotent).
6. **Per batch, one transaction:** update the page row, replace its chunks and FTS
   rows, archive the previous body if the page is cited by doctrine (7.3), append the
   `changes` rows. Commit the batch. A crash between batches leaves a consistent
   database and an unadvanced cursor.
7. **Advance the cursor only after every step succeeded**, to the newest processed
   timestamp. `meta.last_refresh_ok_utc = now`. Write the JSONL and digest (6).
8. Read `Template:Current/version` and compare (2.3).

**On a failure at any step** the transaction of the current batch is rolled back, the
cursor stays put, the run is recorded `failed` with the error class, and the *next*
run repeats the same window (idempotent). The data already committed by earlier
batches stays and is valid.

### 4.4 The revid sweep

Enumerate every in-scope page with `lastrevid` (9 requests for ns 0). Then:
- title missing from the store -> **added** (fetch);
- `lastrevid` greater than stored -> **changed** (fetch);
- stored live title absent from the listing -> confirm with one `titles=` query and a
  `logevents` look-up (delete or move), then tombstone or rename;
- also list redirects (`list=allredirects`) and refresh the alias table.

Sweep-found changes are recorded with `source: sweep`, which is the signal that the
feed missed something (it should be rare; a run of them is a bug or an outage).

### 4.5 Edit, move, delete, restore: what each does to the database

| event | pages row | chunks and FTS | changelog kind |
|---|---|---|---|
| edit | new `revid`, timestamp, sha, `fetched_utc` | replaced | `changed` |
| new page | inserted | inserted | `added` |
| move | `title` changed, old title added to `aliases` | unchanged unless body changed | `moved` |
| delete | tombstone (`state = 'deleted'`), body cleared | **deleted** | `deleted` |
| restore | reinserted | inserted | `restored` |
| page leaves scope (moved to an excluded ns) | tombstone with `reason = 'left_scope'` | deleted | `deleted` |

### 4.6 Redirects

Titles are resolved through a `redirects(from_title, to_title)` table filled from
`list=allredirects` at the first pull and each sweep, and updated from `new` feed
entries. A lookup of a redirect title returns the target page with `resolved_from`
set. A redirect that points outside the ingested namespaces returns a plain message,
"redirects to an excluded namespace", never the old page. **[U]:** how many ns 0
redirects there are; settled in the first pull.

### 4.7 Version bump

`Template:Current/version` changing (say `53.16` to `53.17`) means the main namespace
is being re-edited for a new game, and the install may or may not have moved. The
refresh job **never re-pulls on its own**. It writes a `version_bump` change, sets
`meta.version_status`, and puts a line at the top of the digest. Results then say
"wiki current version 53.17; this fort runs 53.16" until an operator acts. The
deliberate response is a **full re-pull into a new database file**: `wikimirror pull
--full --out <new file>`, verified (5.1 counts and a sample check), then swapped in by
`mv`, keeping the previous file as `.prev` for rollback. The changelog is copied
forward so history is not lost. Doctrine entries citing pages rebuilt in the pull are
flagged by the normal revid check (7).

## 5. Failure, freshness and the network

### 5.1 A full pull is atomic

A full pull writes to a staging file. It is promoted only after: page count within
1% of the enumerated count, no page with a null body, `PRAGMA integrity_check` ok,
an FTS query returns rows for three known-good words, and a manifest is written. A
partial pull can never be promoted, so the reader never sees a half-built copy.

### 5.2 A stale copy says so, on every result

Staleness is **computed by the reader from timestamps at read time**, never stored as
a flag the job must remember to update, so a dead timer, a crashed job and an
unreachable network all read the same way:

| status | condition (defaults, in config) | what results say |
|---|---|---|
| `fresh` | last successful refresh at most 24 hours ago, `version_status` ok | provenance only |
| `stale` | 24 hours to 7 days | "STALE: last refreshed N hours ago; edits since may be missing" |
| `very_stale` | more than 7 days, or never refreshed since the first pull | "VERY STALE: N days; treat every claim as a prior of unknown age" |
| plus a reason | `version_mismatch`, `blocked`, `budget`, `last_run_failed` | appended to the line |

The reader also returns `last_refresh_ok_utc`, `last_refresh_attempt_utc` and the last
error class, so a failing job is visible from the answer, not only from a log. An
empty or unconfigured database is refused loudly (as today), never served as "the
wiki has nothing on this".

### 5.3 The network is down

Each run tries, records `failed(network)`, keeps the data, exits non-zero so systemd
marks it failed. Nothing is deleted or degraded. The reader turns `stale` after 24
hours and `very_stale` after 7 days. When the network returns the next run resumes
from the unmoved cursor, and if the outage exceeded 60 days the forced sweep runs.
The Consultant never blocks on the wiki: `wiki_lookup` and `wiki_search` are local
reads; the existing live `web.fetch` fallback is unchanged and stays labelled a
`prior`.

## 6. The changelog

### 6.1 Machine-readable record

Per refresh, one **run row** and one row per change, in the same SQLite database
(`refresh_runs`, `changes`), and the same rows exported as an append-only JSONL file
`changelog/<YYYY>/<MM>/<run_id>.jsonl` (immutable once written, one JSON object per
line, first line the run header).

Run header:

```json
{"record":"run","run_id":"20260924T060412Z-r","mode":"refresh","started_utc":"...",
 "finished_utc":"...","status":"ok","requests":7,"pages_fetched":12,
 "cursor_from":"2026-09-23T23:58:10Z","cursor_to":"2026-09-24T05:57:31Z",
 "wiki_current_version":"53.16","install_version":"53.16","errors":[]}
```

Change (one per page event):

```json
{"record":"change","run_id":"...","seq":3,"kind":"changed",
 "ns":0,"title":"Trading","page_id":32453,"old_title":null,"new_title":null,
 "old_revid":316204,"new_revid":316240,"wiki_timestamp":"2026-06-25T20:09:11Z",
 "old_len":50888,"new_len":51084,
 "edit_summary":"/* Trade depot */","edit_summary_untrusted":true,
 "source":"recentchanges","detected_utc":"...","cited_by":["seed-entry-id"]}
```

`kind` is one of `added`, `changed`, `moved` (`old_title`, `new_title`), `deleted`
(with `reason`: `deleted` or `left_scope`), `restored`, `redirect_changed`,
`version_bump`. `source` is `recentchanges`, `logevents`, `sweep` or `full_pull`.
`cited_by` lists doctrine entry ids whose cited page this is (7.2). The wiki's own
edit summary is stored **verbatim up to 500 characters and always flagged
untrusted** (any editor writes it; see 9).

### 6.2 Human-readable digest

After each run that changed anything, and at least once a week, a Markdown digest
`digest/<YYYY-MM-DD>.md` plus a `digest/LATEST.md` copy: run status and freshness;
version line (and any bump); counts by kind; a table of changed pages (title, old to
new revid, size delta, edit summary quoted as text in a fenced block, permalink to the
diff `index.php?title=<T>&diff=<new>&oldid=<old>`); moves and deletes; **doctrine
entries now needing a re-read** (7.4); and any run that failed since the last digest.
A quiet run writes no digest, only a `refresh_runs` row.

### 6.3 Storage, retention, and who reads it how

- Where: `/var/lib/dfwiki/` on VM 103 (`df-wiki.sqlite3`, `changelog/`, `digest/`),
  the same convention as the series database's `/var/lib/dfseries/`.
- **Retention:** run and change rows are kept forever (about 30 rows a day **[V]**,
  around 10,000 a year, negligible); JSONL files are kept forever; digests are kept
  for 400 days then deleted by the job. Archived cited-page revisions are kept while
  cited, then 90 days after the citation ends.
- **Consultant:** a new native tool `knowledge.wiki_changes` (slice 7): filters
  `since` (a date or a run id), `title`, `kind`, `cited_only`; returns change records,
  edit summaries framed as untrusted data. Use: "has this changed since I last
  looked" before relying on a page.
- **Doctrine tooling:** reads the `changes` and `pages` tables directly (7).
- **A human:** reads `digest/LATEST.md` on VM 103, or the JSONL, or
  `python -m wikimirror status` (5 lines: freshness, last runs, version status,
  open doctrine flags).

## 7. Doctrine link: a changed page flags, it never edits

### 7.1 Citation format

Doctrine sources (`doctrine/seed.yaml`, a source with `kind: wiki`) gain two optional
fields, validated by `doctrine/validate.py`: **`revid`** (the wiki revision that was
read, an integer) and **`page_ns`** (the namespace id, default 0; the title stays in
`ref`). Existing entries (`read: unrecorded`, no `revid`) stay valid and are simply
reported as uncheckable. New rules the validator adds:
- a `kind: wiki` source with `read: opened` **should** carry `revid` (a warning, then
  an error after the migration slice);
- `describes` must equal the page's `game_version` when the mirror is available to the
  check (a page in `DF2014` cited as `describes: 53.16` is an error);
- `revid` on any non-wiki source is an error.
A wiki source still can never verify (`VERIFYING_KINDS` is unchanged).

### 7.2 The check

`python -m doctrine.wiki_check --db <path> [--doctrine <path>]` (slice 6), read-only,
joins every wiki source with a `revid` against `pages` (through `aliases`, so a move
still finds the page) and yields, per source:

| state | meaning | severity |
|---|---|---|
| `current` | mirror `revid` equals the cited one | none |
| `changed` | mirror `revid` is greater: the page was edited since it was read | re-read |
| `moved` | the cited title now lives under another title | re-read |
| `deleted` | the page is a tombstone | re-read, cited evidence gone |
| `legacy` | the cited page is in a non-current namespace | error for a claim about 53.16 |
| `uncheckable` | no `revid`, or page not in the mirror | informational |

For `changed` it attaches the change records since the cited revid (edit summaries as
untrusted text, size deltas, the diff permalink) and, if the archive holds the cited
revision (7.3), the byte-level diff. `prior` entries get `re-read`; `verified` entries
citing a wiki page get a lower `note` because their evidence is game data (7 leaves
`verified` alone).

### 7.3 Nothing is silently overwritten

When a refresh replaces a page's body and any doctrine source cites that page
(`cited_by` non-empty), the **previous body is first copied to `revision_archive`**
(`page_id`, `revid`, `sha256`, `wikitext`, `archived_utc`) in the same transaction, so
the exact text a doctrine entry was written from is not lost the moment the wiki
changes. The archive is bounded by citations (7.5).

### 7.4 Where the flag surfaces

1. **The refresh digest** (6.2), "Doctrine entries needing a re-read", each with id,
   state, and what changed. Computed at the end of each run.
2. **`doctrine.get`** (slice 7 change to `dfmcp/doctrine_tools.py`): an entry whose
   source is `changed`, `moved`, `deleted` or `legacy` gets a `wiki_flags` field and a
   text line "cited wiki page changed since revision N; re-read before relying on this",
   so any agent reading doctrine sees it at the point of use. The file is already
   re-read per call, and the check joins the live database at call time, so the flag
   needs **no stored state** and cannot go stale.
3. **`python -m wikimirror status`** and the CLI check, for a human.

### 7.5 How a flag clears, and the revisions-are-proposals rule

A flag is never edited away and doctrine is never edited by the job. A person or the
Architect/Overseer path re-reads the page (`knowledge.wiki_lookup`, permalink), and if
the entry still holds, proposes a revision that sets the source's `revid` to the
re-read revision and `accessed` to today; if not, proposes a change to the statement.
The flag clears because `revid` now equals the mirror's. "Still holds" is recorded by
that new `revid`, so the check needs no separate acknowledgement.

## 8. Storage and retrieval

### 8.1 Format: SQLite with FTS5

**SQLite, one file**, over the current single JSON. Reasons: about 6 to 8 thousand
chunks and two full-text indexes are past what loading a JSON dict per call
(`_load_wiki_snapshot` reads and parses the whole file every call) can do well; the
project already runs SQLite for the queue and the series and reads it per call;
transactions give crash safety for the refresh; FTS5 gives ranked search with no new
dependency. `dfmcp/series_tools.py` and `dfqueue/` are the precedent for opening a
runtime database per call from a configured path with no default.

**[U]:** the FTS5 module must be present in the Python that runs on VM 103 and in
the dev environments; slice 1 adds a test that fails loudly if `CREATE VIRTUAL TABLE
... USING fts5` is unavailable, and the build stream must check the VM.

### 8.2 Schema (version 1)

```
meta(key PRIMARY KEY, value)   -- schema_version, source_api, license, ua_version,
                               -- wiki_current_version, install_version, version_status,
                               -- last_full_pull_utc, last_refresh_ok_utc,
                               -- last_refresh_attempt_utc, last_error_class,
                               -- rc_cursor_ts, rc_cursor_ids, last_sweep_utc,
                               -- requests_today_date, requests_today_count
pages(page_id PRIMARY KEY, source, ns, title, revid, rev_timestamp, fetched_utc,
      byte_length, sha256, wikitext, game_version, is_current, kind, state,
      deleted_utc, reason)     -- kind: article|raw|script|editnotice; state: live|deleted
aliases(alias_title, page_id)  -- old titles after a move
redirects(from_title, from_ns, to_title, to_ns)
chunks(chunk_id PRIMARY KEY, page_id, ord, heading_path, text, char_count)
chunks_fts                      -- FTS5 external-content over chunks(text, heading_path),
                                -- tokenizer porter unicode61, plus a title column
refresh_runs(run_id PRIMARY KEY, mode, started_utc, finished_utc, status, requests,
             pages_fetched, cursor_from, cursor_to, error_class, error_detail)
changes(id PRIMARY KEY, run_id, seq, kind, ns, title, page_id, old_title, new_title,
        old_revid, new_revid, wiki_timestamp, old_len, new_len, edit_summary,
        source, detected_utc)
revision_archive(page_id, revid, sha256, wikitext, archived_utc, PRIMARY KEY(page_id, revid))
```

The `source` column is `dfwiki` now and `dfhack` later; `game_version` and
`is_current` are per row and drive every label.

### 8.3 Chunking and text extraction

- Wikitext is split on `==` headings into sections, each keeping its heading path
  ("Trading > Trade depot"), and long sections are split on paragraph boundaries to
  about 2,000 characters. The lead is a section headed "Introduction".
- **The current stripper throws away the facts.** `_strip_markup` in
  `scripts/build_wiki_snapshot.py` drops every `{{...}}`, but pages keep their key
  facts in template parameters (`{{Building|name=Well|construction=...}}`,
  `{{v50_skill|skill=Mason|...}}`) **[V]**. The new text stage flattens a template as
  `Name: key: value; key: value` by default, and a data file
  `wikimirror/template_policy.yaml` lists templates to **drop** (`Quality`, `av`,
  `minorspoiler`, `shortcut`, `raw header`, layout templates) and any per-template
  rendering, so the next template needs a data row, not new code (the
  "tools must be generalisable" rule). Nested templates are flattened to a depth cap of
  4. **[U]:** the ratio of facts kept, measured on the first pull's sample (research
  note, unverified item 3).
- `/raw` pages (1,574, median 214 bytes **[V]**) and `/script`, `/Edit notice` and
  `/entity raw` subpages are `kind` `raw`, `script`, `editnotice`: stored, retrievable
  by exact title, **excluded from `wiki_search` unless asked**, so a search for
  "water buffalo" does not drown in raw-file stubs.
- `wikitext` is stored whole (16 MB) so a re-chunk after a stripper improvement needs
  no network.
- Disk estimate **[I]**: wikitext 16 MB, plain chunks about 12 MB, FTS about 15 MB,
  changelog and archive negligible: **under 100 MB**.

### 8.4 The result contract

Every result (lookup or search) carries, in text and in structured form:

```
title, ns, source, game_version, is_current, revid, rev_timestamp, fetched_utc,
url (permalink with oldid), license, resolved_from (if redirected),
recent_edit (bool), staleness {status, age_hours, last_refresh_ok_utc, reasons},
warnings [ ... fixed wording, 5.2 and 2.3 ... ]
```

It always includes the `<warning>` lines the tool has now (prior at most; check the
version) and adds the staleness line. Text is XML-escaped through the existing
`escape` and `quoteattr` helpers.

### 8.5 How it replaces or extends `knowledge.wiki_lookup` without breaking it

The tool's contract and its tests stay exactly as they are (`dfmcp/tests/test_knowledge_tools.py`
lines 275 to 375, all built on a JSON fixture and the `wiki_snapshot_path` keyword):

- Arguments unchanged: `title`, `section_query`, `max_sections`, all optional;
  `additionalProperties: false`; unknown key refused.
- With no `title`: the `<wiki_index count=...>` listing with `version_namespace` and
  `section_count` per page (for SQLite, capped to a page listing with a
  `title_prefix` filter added as an **optional** argument, because a 4,450 line index is
  too large to return; the JSON path keeps returning everything).
- With `title`: case-insensitive match, the same structured keys (`title`,
  `version_namespace`, `url`, `returned_count`, `omitted_count`, `sections`), the same
  error strings ("no wiki snapshot configured", "snapshot not found", "is not valid
  JSON", "missing a top-level 'pages'"; unknown title says "no page titled").
- **Dispatch on the file**: `_load_wiki_snapshot` keeps handling a `.json` path
  unchanged; a path ending `.sqlite3` goes to a new reader (`dfmcp/wiki_reader.py`,
  read-only URI `mode=ro`, busy timeout 5 s) that returns the same internal view.
  Existing tests keep passing with no edit; new tests cover SQLite.
- **Additive fields only:** `game_version`, `is_current`, `revid`, `fetched_utc`,
  `staleness`, `license`, `recent_edit`, `permalink`. `version_namespace` keeps its
  current meaning (`current`, or the namespace prefix).
- **New tools**, registered as native tools like the other five (one boundary,
  `Roster.check`): `knowledge.wiki_search` (FTS: `query`, `limit`, `include_raw`,
  `include_legacy`, returns ranked chunk excerpts capped in size, with the result
  contract above; ranking is `bm25` with a title-column boost) and, in slice 7,
  `knowledge.wiki_changes` (6.3). Granting them is a change to
  `agents/consultant/tools.yaml`, and **role tool counts move** (Consultant 21 to 22
  then 23; `CLAUDE.md` and the roster tests state exact counts), which the owning stream
  updates in the same commit.
- `role.md` and `agents/consultant/sites.yaml` change: the caution "A local snapshot ...
  is the first choice; fetch live only when the snapshot lacks it" now names the
  mirror, its staleness statuses and the `version_mismatch` case.

## 9. Failure modes and what to verify

| failure | guard | test |
|---|---|---|
| **Wrong-version page served as current** | ingestion by ns-id allow-list (`namespaces.yaml`); `is_current` per row; legacy hidden unless `include_legacy`; legacy results carry a fixed "OLD GAME" line | fixture with `DF2014:Well`, `40d:Well`, `Masterwork:Well`: ingest keeps only ns 0; a reader test that forcing a legacy row in still yields the OLD GAME line and is hidden by default |
| **`version_namespace` misclassified by title prefix** (the current heuristic) | classify by API `ns` integer, never a colon split | a fixture ns 0 title containing a colon stays `current` |
| **Deleted page lingers and is served** | delete removes chunks and FTS rows in the same transaction as the tombstone; the sweep re-confirms | after a delete event, `wiki_lookup` refuses with "deleted from the wiki on ...", `wiki_search` never returns it, FTS row count drops |
| **Moved page not found or double-served** | in-place rename plus `aliases` | lookup by old title resolves with `resolved_from`; only one live row |
| **Changed page silently overwrites a cited revision** | `revision_archive` copy in the same transaction when `cited_by` is non-empty; doctrine check flags `changed` | change a cited page in a fixture run: archive holds the old text, `wiki_check` says `changed`, a second run without change says nothing new |
| **Poisoned or instruction-bearing page** | fetched text is data: XML-escaped, wrapped with the UNTRUSTED warning (as `web.fetch` does), never reaches a system prompt; the edit summary and page text are truncated and control characters stripped; no tool output is ever executed | a fixture page containing "ignore previous instructions" and a fake `</wiki_page>` tag: output is escaped, warning present, structure not broken |
| **Vandalised or unreviewed recent edit** | `recent_edit` flag on revisions under 48 hours; the changelog shows the edit summary and permalink; a hold window (serve only revisions at least 24 hours old) is a listed future option, not built | a revision timestamped 2 hours ago sets `recent_edit` |
| **Outage during a refresh** | per-batch transaction, cursor advanced last, idempotent by `revid` | kill the process between batches (a fault-injection transport): database integrity ok, cursor unmoved, the next run completes with no duplicates |
| **Network down for days** | last-good data kept; reader computes staleness from timestamps | with the clock advanced 25 hours and 8 days, results say `stale`, `very_stale` |
| **The job is dead, not failing** | staleness is read from `last_refresh_ok_utc`, not from job self-report | remove the timer: results go `stale` on their own |
| **Feed gap over 90 days** | forced sweep when the cursor is over 60 days old; `logevents` for moves and deletes | cursor set 70 days back: the run chooses the sweep and records why |
| **Wiki version bump missed** | version read each run, compared with the install; `wiki_ahead` reason on every result | fixture template flips 53.16 to 53.17: `version_bump` change, status set, digest first line |
| **Blocked or throttled by the wiki** | UA identification, 2 s spacing, budgets, backoff, abort on 403 or repeated 429 | fault-injection transport returning 429 then 403: backoff observed, run `blocked`, data untouched |
| **Disk growth or full disk** | bounded corpus (under 100 MB), retention rules (6.3), refuse to write with under 500 MB free, `VACUUM` after a full pull | a fake free-space value under the limit aborts before any write |
| **Partial full pull promoted** | staging file, promote only after the 5.1 checks | truncated staging fixture fails promotion and leaves the old file |
| **FTS5 missing or the file locked by a writer** | startup check for FTS5; readers open `mode=ro` with a busy timeout; refresh batches are short | reader returns a clear error, not an empty result, when the database is locked past the timeout |
| **Template facts lost by the stripper** | flatten-by-default plus a drop list in data | a `{{Building|...}}` fixture keeps its parameter values in the chunk text |
| **A licence or attribution omission** | `license` and permalink in every result and in `meta`, digest attribution line | result-contract test asserts the fields |
| **Secrets or addresses committed** | contact URL and paths come from environment; `tests/test_no_leaked_addresses.py` runs on docs and examples | that test on every stream's docs |

## 10. Where it runs and how it is deployed

- **The copy and the timer live on VM 103**, beside `dfmcp-server`, which is the
  process that serves the native tools to every role over MCP. The Consultant on VM
  106 is unchanged: it calls `knowledge.wiki_lookup` and `knowledge.wiki_search`
  through the MCP server as it does today; there is no second network path, no file
  sharing, no new port. The job needs outbound HTTPS to the public wiki only; VM 103
  already has the outbound path (`web.fetch` runs from there). Note the standing trap
  (`docs/TRAPS.md`): VM 103 has no network isolation boundary, so the job runs as a
  dedicated unprivileged user (`dfwiki`) with no access to the fort's saves.
- **Why not VM 106:** it would make the agent VM a second data owner and require
  shipping a database across; VM 103 already owns the runtime databases
  (`/var/lib/dfseries/`).
- **Layout:** `/var/lib/dfwiki/{df-wiki.sqlite3, changelog/, digest/, run.lock}`;
  `dfmcp-server`'s environment sets `MCP_SERVER_WIKI_SNAPSHOT=/var/lib/dfwiki/df-wiki.sqlite3`
  (the existing setting, kept for compatibility; a `.sqlite3` suffix selects the
  reader), read access for the dfmcp service user by group. **[U]:** the user and
  group layout on the VM; the deploy stream checks it and does not assume it.
- **Units** follow the series importer precedent: `infra/dfwiki-refresh.service.example`,
  `infra/dfwiki-refresh.timer.example` (every 6 hours, randomised delay),
  `infra/dfwiki-sweep.timer.example` (weekly), `infra/dfwiki.example.env`
  (`DFWIKI_UA_CONTACT`, `DFWIKI_DB`, `DFWIKI_DOCTRINE`, budgets; no real values). Real
  values live in gitignored `infra/local.*`. The repo never contains a hostname, an
  address or a contact URL; `tests/test_no_leaked_addresses.py` guards that.
- **Deploy discipline** (`CLAUDE.md`): ship with `git -c core.autocrlf=false archive`
  (hash committed bytes, never the working copy); treat each deploy, and the first full
  pull, as outward-facing and **gated on the user's explicit go-ahead each time**, with
  a heads-up to any live peer session first (a VM change). The first pull is about 110
  requests, run once by hand and watched, with the results recorded under
  `evals/live/<date>-wiki-mirror-deploy/`. The timers are enabled only after a manual
  refresh run has been verified.
- Doctrine is deployed to VM 103 already for `doctrine.get`; the refresh job reads
  that copy for the digest's flags (`DFWIKI_DOCTRINE`).

## 11. Build plan

Eight streams plus one optional. Each is sized for one Sonnet, lists the files it
alone touches, and no two streams that run concurrently share a file. The package
is `wikimirror/` (top level, alongside `dfmcp/`, `dfqueue/`, `conductor/`). The name
does not shadow anything (the `mcp` and `queue` collisions in `CLAUDE.md` are the
trap to avoid). Stdlib only, no new dependency.

| # | stream | touched files (only these) | needs | wave |
|---|---|---|---|---|
| **S1** | API client, schema, store | `wikimirror/__init__.py`, `api.py` (allow-listed actions, UA from env, throttle, backoff, budgets, injectable transport), `schema.py` (DDL, migrations, FTS5 check), `store.py`, `namespaces.yaml`, `wikimirror/tests/test_api.py`, `test_schema.py`, `test_store.py`, `tests/conftest.py` | none | 1 |
| **S2** | Text stage | `wikimirror/text.py` (wikitext to sections and chunks, template flattening), `template_policy.yaml`, `wikimirror/tests/test_text.py`, `wikimirror/tests/fixtures/wikitext/*` (short excerpts with attribution, from the ten sampled page shapes) | none | 1 |
| **S3** | Full pull and CLI | `wikimirror/pull.py` (enumerate, batch, stage, verify, promote), `__main__.py` (`pull`, `status`), `wikimirror/tests/test_pull.py` | S1, S2 | 2 |
| **S4** | Reader and search tool | `dfmcp/wiki_reader.py` (new), `dfmcp/knowledge_tools.py` (the wiki section only: dispatch, `wiki_search`, staleness, result contract), `dfmcp/tests/test_wiki_reader.py` (new file; the existing `test_knowledge_tools.py` is **not edited** and must pass unchanged), `agents/consultant/tools.yaml`, `agents/consultant/role.md`, `agents/consultant/sites.yaml`, the roster count tests | S1 | 2 |
| **S5** | Refresh, changelog, digest | `wikimirror/refresh.py` (feed, logevents, fold, fetch, transactions, cursor, sweep), `changelog.py` (JSONL export), `digest.py`, `wikimirror/tests/test_refresh.py`, `test_changelog.py` | S1, S2 | 2 |
| **S6** | Doctrine link | `doctrine/validate.py`, `doctrine/wiki_check.py` (new), the header comment only of `doctrine/seed.yaml`, `doctrine/tests/test_validate.py`, `doctrine/tests/test_wiki_check.py` | S1 | 2 |
| **S7** | Changes tool and doctrine flags at point of use | `dfmcp/doctrine_tools.py`, `dfmcp/knowledge_tools.py` (adds `wiki_changes`), `dfmcp/server.py` if config needs a `doctrine`/`wiki` path pass-through, `dfmcp/tests/*` for those, `agents/consultant/tools.yaml`, `role.md` | S4, S5, S6 | 3 |
| **S8** | Deploy artifacts and runbook (the deploy itself is gated) | `infra/dfwiki-refresh.service.example`, `infra/dfwiki-refresh.timer.example`, `infra/dfwiki-sweep.timer.example`, `infra/dfwiki.example.env`, `docs/RUNBOOK-WIKI-MIRROR.md`, `evals/live/<date>-wiki-mirror-deploy/README.md` | S3 (first pull), S5 (timers) | 4 |
| S9 (optional) | DFHack installed-docs index and `DF2014` legacy tier | `wikimirror/dfhack_docs.py`, `wikimirror/legacy.py`, tests, `namespaces.yaml` row change | S4 | later |

S1 and S2 run in parallel (wave 1). S3, S4, S5 and S6 run in parallel (wave 2, all
disjoint: S3 owns `pull.py` and `__main__.py`, S5 owns `refresh.py`, `changelog.py`,
`digest.py`, S4 owns `dfmcp/` and `agents/consultant/`, S6 owns `doctrine/`). S7 runs
after all of them because it edits files S4 also edits (`knowledge_tools.py`,
`tools.yaml`, `role.md`). S8 is last and its deploy step is a gated hand-back.

**The minimum first slice that is useful on its own:** S1, S2, S3, S4, then S8's
first-pull step, in that order. That gives an offline copy of the whole current main
namespace, ranked search, and every result labelled with version, revision, fetch
time and age, with staleness honest from day one: with no refresh job the copy simply
turns `very_stale` after 7 days and says so. It already replaces the never-built
curated snapshot and removes the network dependency. Refresh (S5), the doctrine link
(S6, S7) and the timers follow as separable value.

Each stream must, per repo rules: run the ambient `python -m pytest` and
`tests/test_no_leaked_addresses.py`, update the consultant tool counts it changes,
commit as it goes, and never touch a live VM. The register lines and `Working.md`
edits are the orchestrator's (`handoffs/` rule).

## 12. Open items and assumptions to confirm

1. Attribution wording and the GFDL history requirement (3.3): the user's call.
2. FTS5 presence in the VM's Python (8.1) and the user and group layout for the
   read-only database (10). Verified at deploy, not assumed.
3. Redirect count and template dependence (research note, unverified items 2 and 3).
4. Whether a 50-title body batch hits a byte ceiling on the largest pages (research
   note, item 1): the client must handle a `continue` inside a batch either way.
5. The 24 hour and 7 day staleness thresholds and the 6 hour cadence are defaults
   chosen from the observed edit rate (about 15 main-namespace edits a day **[V]**);
   they are configuration, and the first weeks of `refresh_runs` will show whether
   they fit.
6. Whether to build the hold window against vandalism (9). Not built until a real
   vandalised revision is observed in the changelog.
