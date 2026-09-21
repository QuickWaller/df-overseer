# Stream: Consultant retrieval, wiki, DFHack source and Brave web search (agent loop MVP, items 8-9)

**Written** 2026-09-22. **Status:** dispatched. **User go-ahead:** given
2026-09-22 ("go put a sonnet on those"). Offline except **at most 10 real
Brave Search API calls** to prove the integration. **No VM, no deploy, no
model call.** Sonnet executor, worktree-isolated.

## Why

The user wants the Consultant to read the wiki, DFHack's source and the
forums. Today it has only `doctrine.get` and its charter says it "runs on
model priors alone". Decided 2026-09-22 (`docs/AGENT-LOOP.md` §4 items 8-9,
register): a local wiki snapshot lookup (register 2026-09-15: served from a
local snapshot, capped section-level excerpts, not the open web), a read-only
search-and-read tool over DFHack's installed source and docs, and **web search
through the Brave Search API** plus page fetch, all inside dfmcp.

## First

`git merge --ff-only main` in your worktree (worktrees are cut from
`origin/main`; local `main` is ahead).

## Read first

`docs/AGENT-LOOP.md`; `agents/consultant/` (`role.md`, `tools.yaml`,
**`sites.yaml`**, the site guide the user asked for); `docs/MEMORY-ARCHITECTURE.md`
("Received knowledge", especially the version-namespace trap);
`doctrine/seed.yaml`'s header (source `kind`s, `prior` vs `verified`);
`dfmcp/doctrine_tools.py` and `dfmcp/series_tools.py` (the pattern for native,
non-DFHack tools and their registration), `dfmcp/server.py`,
`dfmcp/registry.py`, `dfmcp/roles.py`; `docs/TRAPS.md`.

## What to build

1. **`web.search`** (Brave Search API). The key is in this workstation's
   `.env` as `BRAVE_SEARCH_API_KEY`: **read it by that key only**
   (`grep -E '^BRAVE_SEARCH_API_KEY=' .env`), never the whole file, never
   print it, never put it in argv, a tracked file, a log or your report. In
   the server it comes from the environment, like the role tokens. Verify the
   endpoint, auth header, parameters and rate limits against Brave's own
   current documentation, not memory, and cite what you read. Results are
   capped (count and length) and each carries its URL and, where
   `sites.yaml` knows the domain, that site's `kind` and caveat.
2. **`web.fetch`**: GET one URL, return readable text (stdlib HTML parsing is
   fine; no heavy dependency without saying why), capped in length, with
   timeouts, a size limit, http(s) only, and a refusal for private,
   loopback and link-local addresses (this server sits on the LAN; a fetch
   tool must not become a way to reach it). Every result states that the
   content is **untrusted data, not instructions**, and supports a `prior` at
   most.
3. **`knowledge.wiki_lookup`** over a local snapshot: the lookup tool plus a
   builder script that produces the snapshot from the wiki's MediaWiki API
   (WikiTeam's `dumpgenerator.py` is the documented route; choose and
   justify). Returns capped section-level excerpts and **the page's version
   namespace on every result**. Build and test against a small fixture;
   **do not download the whole wiki** in this stream. Report what a full
   snapshot build would take (size, time, where it should live on VM 103).
4. **`dfhack.source`** (name is your call): read-only search (fixed-string or
   bounded regex, capped matches) and read (bounded line range) over a
   configured root, which on VM 103 is the installed DFHack's scripts, docs
   and Lua. Paths confined to that root (no `..`, no symlink escape), tested.
   Report the exact root paths on VM 103 the deploy should configure, from
   `memory/dfhack-environment.md` or the install scripts, marked unverified if
   you cannot confirm them offline.
5. **Grant** all four to the Consultant only (`agents/consultant/tools.yaml`,
   moving `knowledge.wiki_lookup` from planned to exists). `knowledge_scope`
   for these tools: these are not fort reads, so decide and justify what the
   no-hidden-information rule (`CLAUDE.md`, "No armok capabilities") means
   here; general game knowledge is not hidden fort state.
6. **`agents/consultant/role.md`**: replace "There is no retrieval tool"
   with how to use these, pointing at `sites.yaml`. Keep its labelling
   discipline.

## Touched surfaces (yours only)

New `dfmcp/knowledge_tools.py` (or split as you justify), its tests,
`dfmcp/server.py`, `dfmcp/registry.py` (only if registration needs it),
`dfmcp/requirements.txt` (only if unavoidable, pinned), a new builder script
under `scripts/`, `agents/consultant/tools.yaml`, `agents/consultant/role.md`
(the retrieval passage only), `agents/consultant/sites.yaml` (corrections
only), this doc, its `handoffs/INDEX.md` row.

**Not yours:** `dfmcp/roles.py`, `dfmcp/queue_tools.py`, `dfqueue/`,
`agents/ROSTER.yaml`, other `agents/*/`, `scripts/dfhack/`,
`infra/local.example.env` and `dfmcp/README.md` (report the lines to add).

## Hard lines

- Brave: at most 10 real calls; key read by name only; nothing secret in any
  file, commit, output or report. Scan every new file for the key with a
  positive control before committing.
- No VM, no SSH, no deploy, no model call. No push.
- Do not write `Working.md`, `decisions/` or `memory/`.
- No em dashes in prose.
- **Commit after each milestone** and extend the Result section as you go.

## Done when

Both suites pass (ambient `python -m pytest`, baseline 891 passed / 3
skipped; `dfmcp/tests` in `.venv-dfmcp`, baseline 537), counts reported, the
real Brave calls made and what they returned (no key), and the Result
section lists what was built, how verified, the deploy steps and lines owed
to files you do not own.

## Result

**DONE 2026-09-22, local code and tests only. No VM, no SSH, no deploy, no
model call, no push.**

### What was built

`dfmcp/knowledge_tools.py` (new): five native MCP tools, granted to the
Consultant only (verified via `roster.check()`, architect/overseer both
refused):

- **`web.search`** -- Brave Search API. Endpoint, header and params
  verified against Brave's own current docs (cited in the module, not
  memory): `https://api.search.brave.com/res/v1/web/search`,
  `X-Subscription-Token` header, `q`/`count` params. Rate limiting docs
  (`X-RateLimit-*` headers, 429 on exceed) read and cited; the free-plan
  exact number was not stated in the page content this stream could read,
  so a conservative 1.1s throttle is used rather than an assumed figure.
  Capped to 1-10 results (below Brave's own max of 20).
- **`web.fetch`** -- GET one URL, stdlib `html.parser` text extraction
  (script/style stripped), capped to 8000 chars / 500KB raw. SSRF guard:
  resolves the hostname and refuses if any resolved address is
  private/loopback/link-local/reserved/multicast/unspecified
  (`ipaddress`'s own classification); redirects are re-checked the same
  way before being followed, capped at 5 hops. Every result states the
  content is untrusted data, never instructions, and a prior at most.
- **`knowledge.wiki_lookup`** -- reads a local JSON snapshot (see builder
  below). Every result states the page's `version_namespace`. Index mode
  (no title) lists every page; an unknown title is refused, never an empty
  result.
- **`dfhack.source_search`** / **`dfhack.source_read`** -- two ids, not one
  `dfhack.source` with a mode switch (a naming call the handoff left open;
  justified in the module docstring: every other tool id in this registry
  is one verb per id). Fixed-string or bounded-regex search, bounded
  line-range read, confined to a configured root (rejects `..`, absolute
  paths, and symlink escape via `os.path.realpath`).

`knowledge_scope` deliberately not set on any of the five (matching
`doctrine_tools`/`queue_tools`' own precedent) -- reasoning for why the
no-hidden-information rule doesn't apply here (none of the five can express
a fort-state read at all; their inputs are a query, a URL, a page title or
a source-tree path) is in the module's own docstring, "knowledge_scope:
deliberately not set, on all five, and why".

`scripts/build_wiki_snapshot.py` (new): the offline snapshot builder.
Chose MediaWiki's own `action=parse` API over stdlib `urllib`, not
WikiTeam's `dumpgenerator.py` -- justified in the module docstring
(`dumpgenerator.py` mirrors a whole wiki; this stream was told not to
download the whole wiki, and only needs a curated, capped page set, so
pulling in that dependency would be the "heavy dependency" the handoff
said to avoid without saying why not). Splits wikitext on `==Heading==`
markers of any depth, strips wikilinks/templates/refs, caps each section
to 4000 chars. **Version namespace is a stated heuristic** (title prefix
before the first `:`), not a verified classification against the wiki's
own registered namespace list -- flagged plainly in the docstring rather
than silently assumed correct.

**No real snapshot was built** (per the handoff, "do not download the
whole wiki in this stream") and **no real DFHack install tree exists on
this Windows workstation** to point `dfhack.source_*` at, so both
`wiki_snapshot_path`/`dfhack_source_root` have no default (matching
`queue_db`'s own no-default precedent) and both tools fail loudly and
specifically (naming the missing env var) rather than serving an empty
result. This mirrors `doctrine_tools`/`series_tools`' own "fail loudly if
missing" pattern.

Fixed a real, pre-existing YAML parse error in `agents/consultant/sites.yaml`
found while loading it (an unquoted "quoted-then-unquoted" scalar on the bug
tracker's `for:` line broke `yaml.safe_load` outright -- every prior stream
that touched this file apparently never actually parsed it). Corrected per
the handoff's "corrections only" permission for that file.

`agents/consultant/tools.yaml`: all five granted under `read:`;
`knowledge.wiki_lookup` moved from `planned` to `exists`.

`agents/consultant/role.md`: replaced "There is no retrieval tool. This
role currently runs on model priors alone" with a section naming which of
the five (plus `doctrine.get`/`series.*`, already held) to reach for per
question type, the version-namespace check, and the untrusted-data rule.
Kept the existing mechanically-certain/community-practice/uncertain
labelling discipline unchanged.

`dfmcp/server.py`: `knowledge_tools` imported and merged into `main()`'s
`native_tools=` dict; `ServerConfig` gained `brave_api_key` (env
`BRAVE_SEARCH_API_KEY`, no `MCP_SERVER_` prefix -- deliberately the exact
name already used in this workstation's `.env`, see below),
`wiki_snapshot_path` (env `MCP_SERVER_WIKI_SNAPSHOT`) and
`dfhack_source_root` (env `MCP_SERVER_DFHACK_SOURCE_ROOT`); dispatch and
`KnowledgeToolError` handling added to `_handle_call_tool`.

### Cross-stream file touches beyond the declared list (flagging loudly)

Granting the five tools in the real `agents/consultant/tools.yaml` meant
every **existing** `dfmcp/tests/*.py` fixture that loads the real `agents/`
roster via `load_registry(native_tools={...})` started failing at roster
load time (`'consultant' read-lists 'web.search', which does not exist in
scripts/dfhack/TOOLS.yaml`) unless `knowledge_tools.NATIVE_TOOLS` was
merged into that same dict -- exactly the same requirement each earlier
native module (`queue`/`doctrine`/`series`/`gotchas`) already imposed on
these same fixtures (`dfmcp/README.md`'s own "native_tools" section says so
explicitly). Fixed the same way, additively, in: `dfmcp/tests/gotchas_support.py`,
`test_auth.py`, `test_doctrine_tools.py`, `test_roles.py`, `test_series_tools.py`,
`test_server.py`, `test_tools.py`, `test_workjob_tool.py`.

**This is not in this stream's declared touched-surfaces list, and
`dfmcp/tests/test_roles.py` is explicitly listed in the sibling
`2026-09-22-loop-clock-conductor-role.md` stream's own touched surfaces.**
Both streams were dispatched the same day and may be running concurrently.
My edit to that file is a small, additive, mechanical change (one import
line plus one dict-merge extension in two existing fixture functions) --
low collision risk, but **the orchestrator should check for a merge
conflict against that stream's branch on `dfmcp/tests/test_roles.py`
specifically** before merging both. I could not avoid this: the "Done when"
bar requires both suites passing, and passing required this fix once
`agents/consultant/tools.yaml` (explicitly mine) granted new native ids.

### Verified

- Both full suites, before and after every commit (see commit messages for
  the exact progression). **Final: ambient `python -m pytest` 957 passed, 3
  skipped (baseline 891/3, +66 new: 51 in `dfmcp/tests/test_knowledge_tools.py`,
  15 in `tests/test_build_wiki_snapshot.py`). `.venv-dfmcp` `dfmcp/tests`: 588
  passed (baseline 537, +51).**
- `roster.check('consultant', <each of the 5 ids>)` all return `(True,
  "granted: read")`; `roster.check('architect'/'overseer', 'web.search')`
  both refused -- proven against the real, loaded `agents/` roster, not
  just the module in isolation.
- SSRF guard proven against a **real** loopback HTTP server
  (`http.server`, offline, in-process): `_real_http_get` fetches it
  successfully, then `web.fetch`'s real default path (no injected fake)
  refuses the exact same address. Also proven with mocked
  `socket.getaddrinfo` returning a public address (accepted) and a private
  one (refused), so the resolve-then-classify path is exercised, not only
  the IP-literal short-circuit.
- **Live Brave Search API smoke test, 2 real calls** (well under the
  10-call cap), run from a throwaway scratchpad script (never committed)
  that reads the key by `BRAVE_SEARCH_API_KEY=` only and never prints it
  (confirmed: only "key length: 31" was printed). Call 1 (`"dwarf fortress
  well construction"`, default count) returned 5 results, 3 correctly
  tagged `site.kind=wiki` (two `dwarffortresswiki.org` pages, one
  `DF2014:`-namespaced) and one `site.kind=forum` (a real reddit.com/r/dwarffortress
  hit). Call 2 (`"dfhack workorder create_orders lua"`, `count=3`) returned
  3 results including `docs.dfhack.org` (tagged `wiki`) and a raw GitHub
  source URL. A follow-on **real** `web.fetch` (not a Brave call) of the
  first result succeeded: HTTP 200, `text/html; charset=UTF-8`, 8000 chars
  of real extracted text -- and that real page's own text happens to state
  "v50 information can now be added to pages in the main namespace... v0.47
  information can still be found in the DF2014 namespace," independently
  confirming the version-namespace model `knowledge.wiki_lookup` encodes.
- A positive-control key scan before every commit that touched a new or
  changed file (`key in text` over each changed file, plus confirming
  `"BRAVE_SEARCH_API_KEY"` the literal env-var name is present as a
  sanity check that the scan itself works) -- no leak found at any commit.
- `tests/test_no_leaked_addresses.py` caught two real RFC1918 literals I'd
  used as generic SSRF-guard test addresses; replaced with RFC 5737
  TEST-NET-1 addresses (`192.0.2.x`), which `ipaddress.is_private` still
  flags (so the SSRF tests still exercise the real classification) and the
  leak guard treats as legitimate.

### What a full wiki snapshot build would take

Unmeasured directly (no real build was run, per the handoff), but derived
from what the live smoke test and the builder's own throttle imply:
- **Time**: `_MIN_FETCH_INTERVAL_SECONDS = 1.0` between fetches is the
  floor; each `action=parse` call itself took well under a second live. A
  **curated set** (the 20-30 pages `docs/MEMORY-ARCHITECTURE.md` names as
  worth the cached prefix -- aquifers, sieges, defence design, fort layout,
  industry chains, FPS) would take roughly 30-60 seconds total, dominated
  by the throttle, not the network. A genuinely comprehensive pull (every
  page a `web.search` might surface, plus every `DF2014:`-namespaced
  counterpart) would be an order of magnitude more pages and therefore
  minutes, still nowhere near WikiTeam's whole-wiki timescale.
- **Size**: each fetched page in the live smoke test's own text-extraction
  path capped at 8000 chars; wikitext (uncapped, pre-strip) is typically
  somewhat larger. A few dozen pages, each a few KB of JSON after section
  splitting and the 4000-char-per-section cap, is very likely low
  single-digit MB total, not a concern for VM 103's disk.
- **Where on VM 103**: no path is deployed or chosen yet. Given
  `MCP_SERVER_WIKI_SNAPSHOT`'s own naming convention (matching
  `MCP_SERVER_SERIES_DB`'s absolute, out-of-tree pattern) I'd suggest
  `/var/lib/dfwiki/snapshot.json`, but this is a recommendation, not a
  decision made here -- **unverified, no path exists on any VM today.**

### VM 103 paths the deploy should configure

- **`MCP_SERVER_DFHACK_SOURCE_ROOT=/opt/df/game/hack`** -- **verified from
  source, not live-confirmed.** Derived from `scripts/install_df.py`'s own
  constants: `GAME_DIR = "/opt/df/game"` (line 72), and
  `cmd_script_install`/`cmd_ui_install` deploy every `df-overseer-*.lua`
  script to `GAME_DIR + "/hack/scripts"` (lines 1440-1441), which is
  DFHack's own stock scripts directory (both this project's and DFHack's
  own scripts live there together, since DFHack extracts directly into
  `GAME_DIR` per `install_df.py`'s DFHack-unpack step). By the same
  install-script logic, DFHack's own docs live at
  `/opt/df/game/hack/docs/docs` (matching `memory/dfhack-environment.md`'s
  confirmed Windows-install layout, `hack/docs/docs/`, which
  `install_df.py`'s DFHack tarball extraction should reproduce identically
  since it is the same DFHack release, just for Linux). **Neither path was
  read live on VM 103 in this stream** (no SSH, per the hard line) -- mark
  this "source-derived, needs a one-line live confirmation"
  (`ls /opt/df/game/hack/scripts /opt/df/game/hack/docs/docs` over SSH)
  before the deploy trusts it blindly.
- **`MCP_SERVER_WIKI_SNAPSHOT`** -- no path exists; see "full wiki snapshot
  build" above. Not configured, not deployed, not verified.
- **`BRAVE_SEARCH_API_KEY`** -- already in this workstation's `.env` (31
  chars); needs copying into VM 103's service environment the same way
  `MCP_ROLE_TOKEN_*` and other secrets already are (`dfmcp-server.service`'s
  own env file, per `infra/README.md`'s existing pattern) -- **not done
  here**, no VM access in this stream.

### Lines owed to files this stream does not own

**`infra/local.example.env`** (not touched; report only), add near the
other `MCP_SERVER_*` entries, after `MCP_SERVER_SERIES_DB`:

```
# Brave Search API key for the Consultant's web.search tool
# (dfmcp/knowledge_tools.py). Real value already lives in this
# workstation's .env; this line documents its existence in the tracked
# template, matching the existing "backfilled" convention for other keys
# this file used to be missing. Get a key at https://brave.com/search/api/.
BRAVE_SEARCH_API_KEY=

# Path to the local Dwarf Fortress Wiki snapshot JSON
# (scripts/build_wiki_snapshot.py builds it; dfmcp/knowledge_tools.py's
# knowledge.wiki_lookup reads it). No safe default: this stream did not
# build one. Optional -- knowledge.wiki_lookup fails loudly, naming this
# variable, until it is set and the file exists.
MCP_SERVER_WIKI_SNAPSHOT=

# Root directory of the installed DFHack build's own scripts/docs/Lua,
# read by dfmcp.knowledge_tools' dfhack.source_search/dfhack.source_read.
# On VM 103, source-derived (not live-confirmed) as /opt/df/game/hack --
# see handoffs/2026-09-22-loop-consultant-retrieval.md's Result section
# for how that path was derived and what would confirm it. Optional --
# both tools fail loudly, naming this variable, until it is set.
MCP_SERVER_DFHACK_SOURCE_ROOT=
```

**`dfmcp/README.md`** (not touched; report only), the "native_tools" note
(around the paragraph that names "the queue, doctrine, series and gotchas
natives... each `NATIVE_TOOLS`; checked against `main()` 2026-09-22")
should be extended to also name `knowledge_tools` (five ids: `web.search`,
`web.fetch`, `knowledge.wiki_lookup`, `dfhack.source_search`,
`dfhack.source_read`), and a line added noting that `agents/consultant/`
now depends on it being present in every test fixture that loads the real
roster (see "Cross-stream file touches" above for exactly which files that
turned out to be, in case a future native module addition needs the same
list).

### Design points worth a second look

- **`dfhack.source` split into two ids** (`dfhack.source_search`/
  `dfhack.source_read`) rather than one tool with a mode switch. I believe
  this is the better call (matches the rest of the registry's one-verb-
  per-id convention), but the handoff literally named it `dfhack.source`
  singular and left the name open, so flagging the deviation explicitly in
  case the orchestrator disagrees.
- **The DNS-rebinding gap in the SSRF guard is real, not just theoretical**
  (module docstring says so plainly): `_check_url_safe` checks the
  resolved address at fetch time, not at TCP-connect time, so a target that
  resolves safely and then re-resolves to a private address between the
  check and the actual connection would slip through. Closing it needs
  connecting to the checked IP directly with a separate Host header, which
  plain `urllib` does not make simple. Judged acceptable for this tool's
  actual threat model (the DF wiki/DFHack docs/forums are not
  attacker-controlled; the real risk this guard is for is an agent handed
  an arbitrary URL inside already-fetched untrusted text), but a real gap,
  not a solved one.
- **Brave's exact free-tier rate limit was not found in the documentation
  pages this stream could read** (the page's own example figures are
  explicitly illustrative, not labelled to a plan) -- the 1.1s throttle is
  conservative, cited from community reporting outside Brave's own docs,
  not from Brave's own stated number. Worth re-checking against the
  account's actual dashboard limits before any high-volume use.
- **`web.search`'s per-process throttle is a module-level mutable list**
  (`_last_brave_call_monotonic`), not per-server-instance state threaded
  through `call()`. Matches this module's own single-process deployment
  (one `dfmcp-server.service`), but would under-throttle if this module
  were ever imported into two separate processes sharing one Brave key.
  Flagged, not fixed -- not a scenario this deploy creates.
