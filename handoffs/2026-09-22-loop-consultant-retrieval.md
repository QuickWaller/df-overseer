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

(executor fills in)
