# Wiki mirror feasibility: can an offline, regularly updated Dwarf Fortress Wiki copy be built politely?

Date: 2026-09-24. Stream: `handoffs/2026-09-24-consultant-wiki-design.md`. Feeds
`docs/CONSULTANT-WIKI.md`.

**Question.** The register (2026-09-22, "The whole wiki, kept current by
incremental updates, is agreed but deferred") agreed a direction and left three
things unverified: anonymous `recentchanges` access and its retention, whether the
wiki publishes XML dumps, and the wiki's robots rules, terms, API limits and
licence. This note answers those from the real sites, plus the namespace layout for
the current game, a size estimate, and whether DFHack documentation is available
as a versioned source.

**Method and limits.** 51 HTTP GET requests in total (limit 60), at least 1.2
seconds apart, one descriptive User-Agent naming this project and stating the
purpose (`df-overseer-research/0.1 (offline wiki mirror feasibility probe;
read-only; low rate)`), no cookies, no login, no write actions. No 429, 403 or
other refusal was met on any request. Page bodies were fetched only for a
sample of 10 pages (one request, listed in item 4) plus four small template and
policy pages (each under 3 KB). Everything else was metadata (`allpages`,
`recentchanges`, `logevents`, `siteinfo`, `paraminfo`, `prop=info`). One request
was wasted by a duplicate (requests 10 and 11 are identical).

**Confidence marks.** **[V]** verified by a request in the log below.
**[I]** inferred from a verified fact plus MediaWiki behaviour or general
knowledge. **[U]** unverified: not probed, or probed without an answer.

Prior work read first, not repeated: `docs/MEMORY-ARCHITECTURE.md` "Received
knowledge", `scripts/build_wiki_snapshot.py`, `dfmcp/knowledge_tools.py`.

## Answers to the three open items

| # | Question | Answer | Mark |
|---|---|---|---|
| 1 | Anonymous `recentchanges`, and how far back? | **Allowed.** `list=recentchanges` returned 500 entries per request with no credentials (max 500 for anonymous; `paraminfo` says 500 low, 5000 high, request 9). The oldest retained entry at the time of the probe was `2026-06-25T20:09:11Z` (request 5, `rcdir=newer` from 2020), about **90 days** before the probe time `2026-09-24T02:57Z`. That matches MediaWiki's default `$wgRCMaxAge` of 90 days. | V for access and the oldest entry; I for "the 90-day figure is a fixed policy" |
| 2 | Does the wiki publish XML dumps? | **No dump found.** `/dumps/` redirects (301) to a wiki page path `Dumps/` (request 6; the target was not fetched, to stay inside the budget); a wiki search for `dump OR mirror OR download wiki` in the main and project namespaces returned 0 hits (request 8). No `Special:Export`-based bulk path was probed. **The acquisition route is therefore the MediaWiki API**, which is documented as anonymous-readable (item 3). Whether a third-party WikiTeam archive exists (for example on archive.org) was not checked, because that site is outside the probe's allowed contact. | V that `/dumps/` does not list a dump directory and search finds no dump page; U for third-party archives |
| 3a | robots rules | **The wiki publishes no `robots.txt`.** `GET /robots.txt` returns 301 to `http://.../index.php/Robots.txt`, which is a wiki page that does not exist (404, and the 404 page carries `<meta name="robots" content="noindex,nofollow">`), requests 1 and 2. There are therefore no disallow rules to respect, and the design still identifies itself, rate limits and avoids crawling HTML. | V |
| 3b | robots rules, DFHack docs | `docs.dfhack.org/robots.txt` (Read the Docs) reads `User-agent: *` then `Allow: /en/stable/` then a sitemap line; there is no `Disallow` (request 33). The intent is plainly to steer crawlers to `stable`. **The design will not crawl `docs.dfhack.org` versioned paths at all** (see item 8): the installed docs tree and the release tag are exact, need no crawling and respect the intent. | V for the file's text; I for its intent |
| 3c | Terms and licence | The wiki's own licence page (`Dwarf Fortress Wiki:Copyrights`, revid 212313, 2014-11-17, request 7) reads: "You agree, by posting on this wiki, to release all your contributions under the MIT and GFDL licenses. In cases where this is not possible, you agree to not post the contribution on this wiki." `siteinfo` `rightsinfo` returns `GFDL & MIT` linking to that page (request 3). This confirms the register's "MIT + GFDL dual" claim. **A separate terms-of-service or bot policy page was not found** (a search of the project namespace for mirror/dump terms returned nothing; a search is not exhaustive). | V for the licence; U for the absence of a bot policy |
| 3d | API limits | `paraminfo` (requests 9 and 41): `allpages`, `recentchanges`, `revisions`, `allrevisions` all list `limit` max 500 (low) and 5000 (high); `titles`, `pageids` and `revids` are capped at **50 for anonymous** and 500 with the high-limit right. **No `Retry-After` or rate-limit headers were seen** on any response; no throttling was observed at 1.2 s spacing over 51 requests. The server is nginx with Varnish in front (headers `Via: 1.1 dfwiki-web (Varnish/7.2)`, `X-Varnish`), MediaWiki **1.35.11** (request 3). `Cache-Control: private, must-revalidate, max-age=0` on API responses. | V; U for any undisclosed server-side rate limit that a heavier client might hit |

Attribution requirement, from item 3c: the licence text asks contributors to
release under MIT and GFDL. It names no per-page attribution form. A copy should
carry the licence line, the source URL, the page title and revision id with each
page, and a link to the page's history (which is where the GFDL's authorship
credit is kept). **[I]**: GFDL section 4 wants the title, history and authors
retained or pointed to; a per-page link to the wiki's own history satisfies that
by reference. This is not legal advice, and the design flags it for the user.

## The current game version and its namespace

- `Template:Current/version` (revid 318803, edited 2026-08-06T00:42:13Z, request
  32) contains exactly `53.16`. This is the wiki's own statement of the current
  version, and it matches this install (DF 53.16). **[V]**
- `Template:ArticleVersion` (revid 306815, aliased as `{{av}}`, requests 30 and
  31) states the convention in code: a page in the **main (unprefixed)
  namespace** shows "This article is about the current version of DF. Note that
  some content may still need to be updated." and puts the page in `Category:Current`;
  a page in any other namespace shows "This article is about an **older version**
  of DF." **[V]** Note the second sentence of the current-version banner: the wiki
  itself says main-namespace content can lag the game. That belongs in the
  Consultant's caution text.
- Pages that lack the `{{av}}` banner exist in the main namespace (for example the
  `Water_buffalo/raw` sample), so the banner is not a reliable classifier; the
  namespace is. **[V]**

`siteinfo` namespaces (request 3). Content-bearing ones, with the wiki's own
`content` flag:

| ns id | name | game version (from `{{av}}` links) | pages, non-redirect, measured |
|---|---|---|---|
| 0 | (main) | current, 53.16 | **4,450** (complete, requests 12 to 19) |
| 116 | `DF2014` | v0.47.05 (the last pre-Steam line) | at least 1,500 (paging capped at 3 requests; lower bound) |
| 114 | `v0.34` | 0.34.11 | at least 1,500 (lower bound) |
| 112 | `v0.31` | 0.31.25 | not measured |
| 106 | `40d` | 0.28.181.40d | at least 1,500 (lower bound) |
| 110 | `23a` | 0.23.130.23a | not measured |
| 1000 | `Masterwork` | a mod, not vanilla | not measured |
| 10 | `Template` | (not a game-version namespace) | at least 1,000 (lower bound) |
| 4 | `Dwarf Fortress Wiki` (Project) | project pages, licence | not measured |

Other namespaces (Talk, User, File, Category, Help, `Utility`, `Modification`,
`Tutorial`, `Bloodline`, `Unused`, `Module`) exist. **[V]** The wiki version
ladder in the template maps to the "main = current, DF2014 = 0.47, v0.34, v0.31,
40d, 23a" order the register and `MEMORY-ARCHITECTURE.md` already assumed. The
`Masterwork` namespace is a **mod's** pages and must never be presented as vanilla
knowledge.

Whole-wiki figures from `siteinfo` `statistics` (request 3): 44,963 pages
(all namespaces, including redirects, talk, files), 10,345 "articles", 333,135
edits, 10,913 files, 38,865 users, **15 active users**, 14 admins. **[V]** The
low active-user count means the edit rate is low and the wiki changes slowly,
which is the premise of a timer-driven mirror.

## Main-namespace corpus size (the measured basis for the estimate)

Full non-redirect main-namespace listing with `lastrevid` and `length` per page,
using `generator=allpages&prop=info` at 500 pages per request (requests 40 and
42 to 49). **[V]**

| measure | value |
|---|---|
| non-redirect pages | 4,450 |
| of which `/raw` pages (creature and plant raw-file transclusion stubs) | 1,574 (median 214 bytes, total 1.34 MB) |
| of which other pages | 2,876 |
| total wikitext bytes, all 4,450 | 16,134,113 (16.1 MB) |
| wikitext bytes, excluding `/raw` | 14,789,279 (14.8 MB), mean 5,142, median 1,380, 90th percentile 11,546 |
| largest | `Graphics_interface.txt`-style dumps and `Consolidated development` (292,581 bytes), `Creature` (198,501); one `/raw` page is 972,418 bytes |
| content model | all 4,450 are `wikitext` |
| `lastrevid` range | 47,010 to 320,260 (the wiki's newest revision id was 320,263 in `recentchanges`) |
| `touched` range | 2023-02-05 to 2026-09-24 |

Reading it: the main namespace is small. 16 MB of wikitext is 6 to 8 thousand
retrieval chunks at 2 to 3 KB, and a SQLite file of well under 100 MB with a
full-text index **[I]**. A 10-page sample of hand-picked pages (Well, Aquifer,
Ghost, Engraver, Mason, Dwarf, Cavern, Trading, `DF2014:Well`,
`Water_buffalo/raw`; request 29) had 158 KB of wikitext, mean 15.8 KB, which is
**not** representative (I picked important pages); the measured whole-namespace
mean is 3.6 KB. **[V]**

Markup observed in the sample: heavy template use (`{{Quality|Masterwork}}`,
`{{av}}`, `{{Building|name=Well|...}}`, `{{v50_skill|...}}`, `{{Creaturelookup/0|...}}`,
`{{DFtext|...}}`, `{{raw header|...}}`, `{{variation raw|v50:creature_domestic.txt|...}}`),
`[[File:...]]` links, and `==` headings. **The facts a Consultant wants (Well
construction materials, skill labor, creature tokens) are frequently inside
template parameters.** The existing `_strip_markup` in
`scripts/build_wiki_snapshot.py` drops `{{...}}` entirely, which would throw those
away. **[V]** by reading the code against the sample. This is a design point in
`docs/CONSULTANT-WIKI.md`.

Whole-wiki full pull cost, from the numbers above **[I]**: bodies at the
anonymous cap of 50 titles per request is about 89 requests for the main namespace
(4,450 / 50), plus about 20 for 1,000 templates: roughly 110 requests, some
kilobytes each after gzip, a few minutes at one request per two seconds. Each
request returns up to 50 pages of wikitext, so the payload per request averages
about 180 KB, but a request that lands on the very large pages can hit
MediaWiki's per-request byte ceiling; the client must handle a
`continue` in the middle of a batch. **[U]** for that ceiling's exact value.

## The recentchanges feed in practice

Request 4 (500 most recent entries, `rctype=edit|new|log|categorize`) covered
**2026-09-06T23:04Z to 2026-09-24T01:13Z, 18 days**. **[V]**

| measure | value |
|---|---|
| entries in 18 days | 500 (so about 28 per day, all namespaces) |
| main-namespace edits | 278 (about 15 per day) touching **153 distinct titles** |
| type mix | 433 edit, 62 log, 5 new |
| log mix | 41 upload, 13 newusers, 4 upload overwrite, **2 move**, 1 upload revert, 1 block |
| namespaces | 0: 278, 6 (File): 53, 116: 46, 110: 37, 1: 27, 2: 16, 106: 12, 10: 11, 114: 6, 112: 6, 5: 5, 3: 2, 4: 1 |
| deletes | none in the 18-day window; the delete log holds deletions from 2026-09-02 and earlier (request 38) |

Entry shape (an actual entry): `{"type":"edit","ns":0,"title":"Trading","pageid":32453,
"revid":316240,"old_revid":316204,"rcid":466512,"timestamp":"2026-06-25T20:09:11Z"}`,
with `oldlen`, `newlen` and `comment` under `rcprop`. **[V]** `revid` and `old_revid`
are present, which is what the changelog needs.

Consequences **[I]**: a poll every few hours returns tens of entries, so one
request per poll is enough; the feed is far below the 500-per-request cap and far
inside the 90-day retention, so it is a comfortable primary signal.

`logevents` is a second, longer-lived signal. `list=logevents&letype=delete` and
`letype=move` both work anonymously and reach back to at least 2026-09-02 for
deletes and 2026-09-13 to 2026-09-21 for the first three moves shown (requests
38 and 39; only 3 rows each were requested). Move rows carry the target title in
`params.target_title`. **[V]** MediaWiki does not prune the log table by age, so
`logevents` should not be limited to 90 days **[I]**, which makes it the right
place to recover a missed **move or delete** after a long outage. There is no such
recovery for a missed plain **edit** beyond 90 days, which is what the `lastrevid`
sweep is for.

## The revid sweep (backstop) is cheap

`generator=allpages&gapnamespace=0&gapfilterredir=nonredirects&gaplimit=500&prop=info`
returned **500 pages with `lastrevid`, `length` and `touched` in one request**
(requests 40 and 42 to 49: nine requests for all 4,450). The generator-with-500
form is what `paraminfo` lists as `limit: 500`; the 50-title cap applies to
explicit title lists, not to a generator. **[V]** So a full main-namespace revid
sweep costs nine requests and about 1 MB, and can run weekly. Compression
(`--compressed` sent) was not visible in response headers (`Content-Encoding`
absent), so the transfer size figures are uncompressed sizes and may be pessimistic;
whether the server would gzip was not established. **[U]**

## DFHack documentation

| finding | mark |
|---|---|
| `https://docs.dfhack.org/` redirects to `/en/stable/` (Read the Docs, custom domain) | V (request 34) |
| `stable` is titled "DFHack 53.16-r1 documentation" | V (request 35) |
| Versioned slugs exist per release: `53.16-r1`, `53.15-r3`, and so on back to `52.03-r2` (66 entries in the sitemap, which is autogenerated by Read the Docs) | V (request 37) |
| **There is no `53.16-r1.1` slug**: `GET /en/53.16-r1.1/` is a 404 | V (request 36) |
| The installed DFHack is 53.16-r1.1 (register, `agents/consultant/sites.yaml`), a point release of 53.16-r1, so the closest published docs are 53.16-r1 (identical to `stable` at the probe time) | V for the slug facts, I for "point release" |
| The docs are Sphinx built from the `docs/` tree of the DFHack repository (reStructuredText). The installed tree on the game VM already includes the shipped docs, and the existing `dfhack.source_search` tool has `.rst` in its text-suffix list | I from `dfmcp/knowledge_tools.py`; U whether the installed tree contains `.rst` doc sources on this VM (not checked: no VM contact in this stream) |
| A versioned source archive (release tag tarball) is published on GitHub. Not probed: GitHub is outside the probe's allowed contact | U |

Conclusion for the design: the **exact** source for 53.16-r1.1 is the installed
`hack/` tree, already served by `dfhack.source_search` and `dfhack.source_read`. It
does not need mirroring, only indexing, and only if `.rst` docs and script
`help` text are present **[U, to verify at build time on the VM]**. The Read the
Docs site adds nothing the install lacks for this version, and its robots file
points crawlers at `stable`, so it is a fallback for one page at a time, not a
mirror source.

## Request log (the exact requests)

Base for all wiki requests: `https://dwarffortresswiki.org/api.php` unless a path
is shown. `fv2` means `format=json&formatversion=2`.

| # | request | result |
|---|---|---|
| 1 | `GET /robots.txt` | 301 to `/index.php/Robots.txt` |
| 2 | `GET /index.php/Robots.txt` | 404, wiki "no such page", `noindex,nofollow` |
| 3 | `action=query&meta=siteinfo&siprop=general\|namespaces\|statistics\|rightsinfo&fv2` | 200, 7.8 KB. MediaWiki 1.35.11, readonly false, rights `GFDL & MIT`, statistics and 38 namespaces as tabulated |
| 4 | `list=recentchanges&rcprop=title\|ids\|timestamp\|comment\|sizes\|loginfo&rclimit=500&rctype=edit\|new\|log\|categorize&fv2` | 200, 118 KB, 500 entries, 2026-09-06 to 2026-09-24, `continue` present |
| 5 | `list=recentchanges&rcdir=newer&rcstart=2020-01-01T00:00:00Z&rclimit=1&rcprop=title\|timestamp\|ids&fv2` | 200, first entry `2026-06-25T20:09:11Z` (revid 316240) |
| 6 | `GET /dumps/` | 301 to `/index.php/Dumps/` (not followed) |
| 7 | `prop=revisions&rvprop=content\|ids\|timestamp&rvslots=main&titles=Dwarf_Fortress_Wiki:Copyrights&fv2` | 200, the licence text quoted above |
| 8 | `list=search&srsearch=dump OR mirror OR download wiki&srnamespace=4\|0&srlimit=10&fv2` | 200, `totalhits: 0` |
| 9 | `action=paraminfo&modules=query+allpages\|query+recentchanges\|query+revisions\|query+allrevisions&fv2` | 200, limit 500/5000 |
| 10, 11 | `list=allpages&apnamespace=0&apfilterredir=nonredirects&aplimit=500&fv2` (identical duplicate) | 200, 500 rows, first `ASCII art reward`, continue at `Buckwheat` |
| 12 to 19 | the same, following `apcontinue` | 200 each; 500 per page except the last with 450; total **4,450** |
| 20 to 22 | the same for `apnamespace=116` | 3 pages of 500, still continuing: at least 1,500 |
| 23 to 25 | `apnamespace=114` | at least 1,500 |
| 26 to 28 | `apnamespace=106` | at least 1,500 |
| 29 | `prop=revisions&rvprop=content\|ids\|timestamp\|size\|comment&rvslots=main&titles=Well\|Aquifer\|Ghost\|Engraver\|Water_buffalo/raw\|Dwarf\|Cavern\|Trading\|DF2014:Well\|Mason&fv2` | 200, 163 KB, 10 pages (the sample); no warnings |
| 30 | `prop=revisions&...&titles=Template:Av\|Template:Current_version&fv2` | `Template:Av` is a redirect to `Template:ArticleVersion`; `Current_version` missing |
| 31 | `...&titles=Template:ArticleVersion` | 200, 2.8 KB, the version-banner logic quoted above |
| 32 | `...&titles=Template:Current/version\|DF_Wiki:Copyrights` | `Current/version` = `53.16`; the second title is missing (wrong prefix; the project namespace prefix is `Dwarf Fortress Wiki`) |
| 33 | `GET https://docs.dfhack.org/robots.txt` | 200, 80 bytes |
| 34 | `GET https://docs.dfhack.org/` | 302 to `/en/stable/` |
| 35 | `GET https://docs.dfhack.org/en/stable/` | 200, 12.6 KB, "DFHack 53.16-r1 documentation" |
| 36 | `GET https://docs.dfhack.org/en/53.16-r1.1/` | 404 |
| 37 | `GET https://docs.dfhack.org/sitemap.xml` | 200, 66 URLs, versions `latest`, `stable`, `53.16-r1` down to `52.03-r2` and older |
| 38 | `list=logevents&letype=delete&lelimit=3&fv2` | 200, three deletes on 2026-09-02, `continue` present |
| 39 | `list=logevents&letype=move&lelimit=3&fv2` | 200, three moves 2026-09-13 to 2026-09-21 with `params.target_title` |
| 40, 42 to 49 | `generator=allpages&gapnamespace=0&gapfilterredir=nonredirects&gaplimit=500&prop=info&fv2` following `gapcontinue` | 200, 9 requests, 4,450 pages with `lastrevid`, `length`, `touched` |
| 41 | `action=paraminfo&modules=query&fv2` | 200, `titles`, `pageids`, `revids`: 50 low, 500 high |
| 50, 51 | `list=allpages&apnamespace=10&apfilterredir=nonredirects&aplimit=500&fv2` | 2 pages of 500, still continuing: at least 1,000 templates |

Request numbering follows the order of the probe log; two numbers in the table
above group consecutive requests.

## Unverified, and how each would be settled

1. **Whether anonymous body pulls at 50 titles per request are throttled or
   byte-capped.** Settle by the first real pull, with the client logging every
   response header and status. The design assumes a 50-title batch and a
   `continue` inside a batch.
2. **Redirect count and shape** (the wiki has 44,963 pages in total, so many are
   redirects, talk or files). Settle with `list=allredirects` in the first pull; the
   design stores them as an alias table.
3. **Template namespace size and the template dependency of key facts.** At least
   1,000 non-redirect templates. Settle by measuring on the first pull how many of
   the sample's facts survive a stripper that keeps parameter values.
4. **Third-party dumps** (archive.org, WikiTeam). Not needed by this design.
5. **Server-side compression and the wiki's undisclosed bot etiquette.** Ask
   nothing; identify, throttle and back off on 429 or 5xx.
6. **The presence of `.rst` docs and script help in the installed DFHack tree on the
   game VM.** Settle by one `dfhack.source_search` call at deploy time.
7. **Legal reading of the attribution requirement.** Flag for the user.
8. **Whether `Template:Current/version` lags a DF release.** It said 53.16 on
   2026-08-06 and no newer game version was out on the probe date to the best of
   the register's knowledge, but this is the wiki's statement, not the game's. The
   mirror compares it with the install's version and warns on a mismatch (see the
   design).
