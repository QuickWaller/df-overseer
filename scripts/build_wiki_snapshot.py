#!/usr/bin/env python3
"""Builds the local Dwarf Fortress Wiki snapshot `dfmcp.knowledge_tools`'
`knowledge.wiki_lookup` reads (`docs/MEMORY-ARCHITECTURE.md`, "Get it
offline, don't fetch live": "a month-long unattended run should not depend
on the network... Pre-ingest rather than live-fetch").

## Route chosen, and why not WikiTeam's `dumpgenerator.py`

The handoff (`handoffs/2026-09-22-loop-consultant-retrieval.md`) named
WikiTeam's `dumpgenerator.py` as "the documented route" and asked this
stream to choose and justify. `dumpgenerator.py` is built to mirror an
entire wiki (every page, every revision, images, a full XML dump meant for
long-term preservation) -- the handoff explicitly said **not** to do that
in this stream ("do not download the whole wiki"), and `knowledge.wiki_lookup`
only ever needs a curated, capped set of pages (the wiki's own MediaWiki API
docs already call this out: `--exnamespaces` to skip what you don't want is
WikiTeam's own accommodation for a partial pull, not the tool's default
shape). Pulling in `dumpgenerator.py` as a dependency for a few dozen pages
would be the "heavy dependency" the handoff said to avoid without saying
why not; this script instead talks to the same underlying interface
WikiTeam itself uses -- the wiki's own MediaWiki `action=parse` API -- with
nothing beyond the stdlib (`urllib.request`, `json`), for a handful of named
pages rather than the whole site. If this project later wants a genuinely
complete mirror, `dumpgenerator.py` is still the right tool for that
different job; this script is not a smaller reimplementation of it, it is a
different, narrower job.

## Snapshot format

A single JSON file:

```json
{
  "generated_utc": "2026-09-22T00:00:00Z",
  "source_api": "https://dwarffortresswiki.org/api.php",
  "pages": {
    "<exact page title>": {
      "version_namespace": "current" | "<wiki namespace prefix>",
      "url": "https://dwarffortresswiki.org/index.php/<title>",
      "fetched_utc": "...",
      "sections": [{"heading": "...", "text": "..."}, ...]
    }
  }
}
```

JSON over a second WikiTeam-shaped XML dump or a SQLite file: it is human-
readable for review before deploy, diffable in git if ever checked in as a
fixture, and `knowledge_tools._load_wiki_snapshot` already treats it as the
one, whole unit to load per call (`dfmcp/series_tools.py`'s reasoning for
re-opening SQLite per call does not apply here -- this file is small and
static between rebuilds, not a store something else keeps appending to).

## Version namespace: a stated heuristic, not a verified classification

`version_namespace_of` takes the text before a title's first `:` as the
namespace (e.g. `"DF2014:Well"` -> `"DF2014"`), and `"current"` for a title
with no colon. **This is a heuristic on the title string, not a query
against the wiki's own registered namespace list**
(`action=query&meta=siteinfo&siprop=namespaces` would give the authoritative
answer, and this script does not call it, to keep this stream's real network
use to the small, named set of pages it actually fetches). A title that
happens to contain a colon for an unrelated reason (rare, but real wiki
titles do this) would be misclassified. Flagged here rather than solved:
whoever runs a real build should spot-check namespace assignment against a
few known pages before trusting it, and `knowledge_tools`' own result
always carries whatever this script wrote, so a wrong classification is at
least visible, not silently smoothed over.

## Politeness

`_MIN_FETCH_INTERVAL_SECONDS` throttles real fetches to be a considerate,
infrequent caller of a community-run wiki -- this runs a handful of times
total (on a version bump), never per-agent-turn.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

DEFAULT_API_URL = "https://dwarffortresswiki.org/api.php"
DEFAULT_INDEX_URL = "https://dwarffortresswiki.org/index.php"

_USER_AGENT = "df-overseer-wiki-snapshot-builder/0.1 (+https://github.com -- offline snapshot builder, run rarely)"
_MIN_FETCH_INTERVAL_SECONDS = 1.0
_MAX_SECTION_CHARS = 4000

# Fetches a page's raw wikitext: (title, api_url) -> wikitext.
FetchWikitext = Callable[[str, str], str]

_SECTION_RE = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$", re.MULTILINE)


class SnapshotBuildError(Exception):
    """A page could not be fetched or parsed. Always names the title."""


# --------------------------------------------------------------------------
# Real fetch (the only network code in this module)
# --------------------------------------------------------------------------

_last_fetch_monotonic = [0.0]


def real_fetch_wikitext(title: str, api_url: str = DEFAULT_API_URL) -> str:
    """GETs `action=parse&prop=wikitext` for `title`. Raises
    SnapshotBuildError naming the title for a missing page, a network
    failure, or a response missing the expected shape."""
    elapsed = time.monotonic() - _last_fetch_monotonic[0]
    if elapsed < _MIN_FETCH_INTERVAL_SECONDS:
        time.sleep(_MIN_FETCH_INTERVAL_SECONDS - elapsed)
    _last_fetch_monotonic[0] = time.monotonic()

    qs = urllib.parse.urlencode({
        "action": "parse", "page": title, "prop": "wikitext",
        "format": "json", "redirects": "1",
    })
    url = f"{api_url}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read()
    except urllib.error.URLError as exc:
        raise SnapshotBuildError(f"{title!r}: could not reach {api_url}: {exc}") from exc

    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise SnapshotBuildError(f"{title!r}: response was not valid JSON: {exc}") from exc

    if "error" in data:
        raise SnapshotBuildError(f"{title!r}: wiki API error: {data['error']}")
    try:
        return data["parse"]["wikitext"]["*"]
    except (KeyError, TypeError) as exc:
        raise SnapshotBuildError(f"{title!r}: response missing parse.wikitext.* : {data!r}") from exc


# --------------------------------------------------------------------------
# Wikitext -> sections. Light markup stripping, not a full wikitext parser
# (the handoff: "no heavy dependency without saying why" -- a real wikitext
# parser is a much larger dependency than this tool needs; the excerpts are
# read by a model, which tolerates residual markup far better than a
# strict renderer would).
# --------------------------------------------------------------------------


def _strip_markup(text: str) -> str:
    # [[target|display]] or [[target]] -> display or target
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    # '''bold''', ''italic''
    text = re.sub(r"'''('')?", "", text)
    text = re.sub(r"''", "", text)
    # {{template|...}} -- drop entirely, wikitext templates rarely carry
    # reader-facing prose worth an excerpt
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    # <ref>...</ref> and other simple tags
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    # Collapse runs of blank lines/whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sections(wikitext: str) -> List[dict]:
    """Splits on `== Heading ==`-style headers (any depth 2-6 `=`). Text
    before the first header, if any and non-empty, becomes a section headed
    "Introduction". Each section's text is markup-stripped and capped to
    `_MAX_SECTION_CHARS`."""
    matches = list(_SECTION_RE.finditer(wikitext))
    sections: List[dict] = []

    intro_end = matches[0].start() if matches else len(wikitext)
    intro = _strip_markup(wikitext[:intro_end])
    if intro:
        sections.append({"heading": "Introduction", "text": intro[:_MAX_SECTION_CHARS]})

    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(wikitext)
        body = _strip_markup(wikitext[body_start:body_end])
        if body:
            sections.append({"heading": heading, "text": body[:_MAX_SECTION_CHARS]})

    return sections


def version_namespace_of(title: str) -> str:
    """See module docstring, "Version namespace: a stated heuristic"."""
    if ":" in title:
        prefix, _, _rest = title.partition(":")
        prefix = prefix.strip()
        if prefix:
            return prefix
    return "current"


def page_url(title: str, index_url: str = DEFAULT_INDEX_URL) -> str:
    return f"{index_url}/{urllib.parse.quote(title.replace(' ', '_'))}"


# --------------------------------------------------------------------------
# Building the snapshot
# --------------------------------------------------------------------------


def build_snapshot(
    titles: List[str], *,
    fetch: Optional[FetchWikitext] = None,
    api_url: str = DEFAULT_API_URL,
    index_url: str = DEFAULT_INDEX_URL,
    now: Optional[Callable[[], datetime]] = None,
) -> dict:
    """Builds the full snapshot dict for `titles`. `fetch` defaults to
    `real_fetch_wikitext` (the only real network path); tests inject a fake
    returning canned wikitext, so this function and everything it calls
    (`split_sections`, `version_namespace_of`) are exercised with no network
    access. Raises SnapshotBuildError (naming the title) if any page fails
    to fetch -- a partial snapshot silently missing a requested page would
    be worse than refusing to write one at all."""
    fetcher = fetch if fetch is not None else real_fetch_wikitext
    clock = now if now is not None else (lambda: datetime.now(timezone.utc))

    pages: Dict[str, dict] = {}
    for title in titles:
        wikitext = fetcher(title, api_url)
        pages[title] = {
            "version_namespace": version_namespace_of(title),
            "url": page_url(title, index_url),
            "fetched_utc": clock().isoformat(timespec="seconds"),
            "sections": split_sections(wikitext),
        }

    return {
        "generated_utc": clock().isoformat(timespec="seconds"),
        "source_api": api_url,
        "pages": pages,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a local Dwarf Fortress Wiki snapshot for knowledge.wiki_lookup. "
            "Fetches only the named pages, never the whole wiki -- pass every page "
            "you want, one at a time, deliberately."
        ),
    )
    parser.add_argument("titles", nargs="+", help="Exact wiki page titles to fetch, e.g. Well \"DF2014:Well\"")
    parser.add_argument("--out", required=True, help="Output snapshot JSON path")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    args = parser.parse_args(argv)

    try:
        snapshot = build_snapshot(args.titles, api_url=args.api_url, index_url=args.index_url)
    except SnapshotBuildError as exc:
        print(f"build_wiki_snapshot: {exc}", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(snapshot['pages'])} page(s) to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
