"""The full pull (docs/CONSULTANT-WIKI.md 3.2, 4.7, 5.1, 13): enumerate, fetch, run the
text stage, write a STAGED database with baseline (immediately visible) revisions, verify,
and promote atomically. On any failure the live file is untouched.

Design points a reader should know:

* **Staging and resume.** The staged file is `<out>.staged`. A pull that dies leaves it in
  place with `meta.pull_state = 'in_progress'`. The next pull refuses to start while it
  exists unless the caller says `resume=True` (re-enumerate, skip pages already stored at the
  enumerated revid, fetch the rest) or `discard_staged=True` (delete it, start clean). Nothing
  is ever promoted from a staged file that did not pass verification in the same call.
* **Statistics are recomputed, not persisted.** The pull report aggregates what the text
  stage could not handle. On a resume the already-stored pages are re-run through the (pure,
  offline, deterministic) text stage from their stored wikitext, so the report of a resumed
  pull equals the report of an uninterrupted one and a crash between a batch and a
  bookkeeping write cannot make it wrong.
* **The chunk adapter.** S2's `Chunk` carries a section path tuple and per-chunk degraded
  flags; S1's store keeps `heading_path: str` and no degraded column (and this module may not
  edit either). The path is joined with `SEPARATOR` (the design's "Trading > Trade depot"); the
  degraded flags and the `unlisted_templates` counts are folded into the pull report written
  next to the database, so nothing the text stage flagged is silently lost.
* **Version.** The game version is read once, from `Template:Current/version`, and recorded in
  `meta.game_version`. A version bump is a deliberate re-pull into a new file (4.7); this
  module never runs on its own.
* **Requests.** Only the client's allow-listed reads are used. A full pull is about 110
  requests for the main namespace (research note); the client's per-run budget (default here
  800, the design's full-pull budget) is the backstop.
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from wikimirror import text as textstage
from wikimirror.api import BATCH_SIZE, ENV_UA_CONTACT, PageInfo, WikiClient, WikiApiError
from wikimirror.store import (
    LICENSE, Chunk, PromoteError, PromoteReport, Store, StoreError, iso, ingested_namespace_ids,
    load_namespaces, promote_staged,
)

SEPARATOR = " > "
DEFAULT_BUDGET = 800  # design 3.3: a full pull has its own request budget
DEFAULT_PROBE_WORDS = ("dwarf", "water", "stone")
TOP_UNLISTED = 25
TOP_REASONS = 50
REPORT_SUFFIX = ".pull-report.json"
STAGED_SUFFIX = ".staged"
FALLBACK_CHUNK_TEXT = "(text extraction failed for this page; see the pull report)"


class PullError(RuntimeError):
    """A pull refused to start or failed verification. The live file is untouched."""


class ContactRequired(PullError):
    """A real pull needs DFWIKI_UA_CONTACT (the user-approved politeness rule)."""


class StagedExists(PullError):
    """A staged file from an earlier pull is present; resume it or discard it."""


# ---- guards -------------------------------------------------------------------


def require_contact(env: Mapping[str, str] | None = None) -> str:
    """The politeness rule: a non-dry-run pull refuses to start without a contact."""
    env = os.environ if env is None else env
    contact = (env.get(ENV_UA_CONTACT) or "").strip()
    if not contact:
        raise ContactRequired(
            f"{ENV_UA_CONTACT} is not set: a real pull identifies itself to the wiki. "
            "Set it to a contact URL or address (never committed) and retry. "
            "`--dry-run` does not need it."
        )
    return contact


def staged_path_for(out: str | os.PathLike[str]) -> Path:
    return Path(str(out) + STAGED_SUFFIX)


def report_path_for(out: str | os.PathLike[str]) -> Path:
    return Path(str(out) + REPORT_SUFFIX)


def _remove_db_files(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(str(path) + suffix).unlink(missing_ok=True)


# ---- the chunk adapter --------------------------------------------------------


def adapt_chunks(page: textstage.PageText) -> list[Chunk]:
    """S2 chunks to S1 chunks: the section path joined into one heading string."""
    out = []
    for c in page.chunks:
        path = SEPARATOR.join(p for p in c.section_path if p) or "Introduction"
        out.append(Chunk(path, c.text))
    return out


@dataclass
class PullStats:
    """What the text stage could not handle, aggregated across the whole pull."""

    pages: int = 0
    chunks: int = 0
    degraded_chunks: int = 0
    degraded_pages: int = 0
    unlisted: Counter = field(default_factory=Counter)
    reasons_chunks: Counter = field(default_factory=Counter)
    reasons_pages: Counter = field(default_factory=Counter)
    section_text_lost: list[str] = field(default_factory=list)
    no_chunks: list[str] = field(default_factory=list)
    text_failures: list[dict[str, str]] = field(default_factory=list)
    text_says_redirect: list[str] = field(default_factory=list)

    def add(self, title: str, page: textstage.PageText) -> None:
        self.pages += 1
        self.chunks += len(page.chunks)
        for name, n in page.unlisted_templates.items():
            self.unlisted[name] += n
        if page.degraded_reasons:
            self.degraded_pages += 1
            for r in page.degraded_reasons:
                self.reasons_pages[r] += 1
        lost = False
        for c in page.chunks:
            if c.degraded:
                self.degraded_chunks += 1
            for r in c.degraded_reasons:
                self.reasons_chunks[r] += 1
                if r == "section_text_lost":
                    lost = True
        if lost:
            self.section_text_lost.append(title)
        if not page.chunks:
            self.no_chunks.append(title)
        if page.is_redirect:
            self.text_says_redirect.append(title)

    def add_failure(self, title: str, exc: BaseException) -> None:
        self.pages += 1
        self.chunks += 1
        self.text_failures.append({"title": title, "error": f"{type(exc).__name__}: {exc}"[:300]})

    def to_dict(self) -> dict[str, Any]:
        top = self.unlisted.most_common(TOP_UNLISTED)
        return {
            "pages": self.pages,
            "chunks": self.chunks,
            "degraded_chunks": self.degraded_chunks,
            "degraded_pages": self.degraded_pages,
            "unlisted_templates_distinct": len(self.unlisted),
            "unlisted_templates_total_uses": sum(self.unlisted.values()),
            "unlisted_templates_top": [{"template": k, "count": v} for k, v in top],
            "degraded_reasons_chunks": dict(self.reasons_chunks.most_common(TOP_REASONS)),
            "degraded_reasons_pages": dict(self.reasons_pages.most_common(TOP_REASONS)),
            "section_text_lost_pages": sorted(self.section_text_lost),
            "pages_without_chunks": sorted(self.no_chunks),
            "text_stage_failures": self.text_failures,
            "pages_whose_text_is_a_redirect": sorted(self.text_says_redirect),
        }


def _extract(title: str, wikitext: str, stats: PullStats) -> list[Chunk]:
    """Run the text stage; a raise (a bug: it should never) is recorded, never swallowed."""
    try:
        page = textstage.extract_page(wikitext)
    except Exception as exc:  # noqa: BLE001 - recorded loudly in the report, page kept
        stats.add_failure(title, exc)
        return [Chunk("Introduction", FALLBACK_CHUNK_TEXT)]
    stats.add(title, page)
    return adapt_chunks(page)


# ---- dry run ------------------------------------------------------------------


def plan_pull(client: WikiClient, namespaces: Mapping[int, Any] | None = None) -> dict[str, Any]:
    """Enumerate and report what a pull would fetch. Uses only the enumeration requests
    (about 9 for the main namespace) and writes nothing."""
    rules = namespaces if namespaces is not None else load_namespaces()
    ids = ingested_namespace_ids(rules)
    per_ns: dict[int, int] = {}
    for ns in ids:
        per_ns[ns] = len(client.enumerate_pages(ns))
    pages = sum(per_ns.values())
    fetch_batches = sum(math.ceil(n / BATCH_SIZE) for n in per_ns.values())
    enum_requests = client.requests_made
    # +1 version template read, +2 per namespace for the redirect join (minimum; it pages).
    projected = enum_requests + fetch_batches + 1 + 2 * len(ids)
    return {
        "dry_run": True,
        "namespaces": ids,
        "pages_per_namespace": per_ns,
        "pages": pages,
        "fetch_batches": fetch_batches,
        "requests_used_for_enumeration": enum_requests,
        "projected_total_requests": projected,
        "note": "version read and redirect enumeration are not run in a dry run; the projection "
        "counts them at their minimum. Nothing was written.",
    }


# ---- the pull -----------------------------------------------------------------


@dataclass
class PullResult:
    out: str
    staged: str
    game_version: str
    enumerated: int
    stored: int
    resumed: int
    missing: list[str]
    redirects: int
    requests: int
    report: dict[str, Any]
    report_path: str
    promote: PromoteReport


def _stored_revids(store: Store) -> dict[int, int]:
    rows = store.conn.execute("SELECT page_id, revid FROM pages WHERE state='live'").fetchall()
    return {int(r[0]): int(r[1]) for r in rows if r[1] is not None}


def _open_staged(
    staged: Path, *, resume: bool, discard: bool, clock: Callable[[], datetime] | None,
) -> tuple[Store, bool]:
    """Returns (store, resumed)."""
    if staged.exists():
        if discard:
            _remove_db_files(staged)
        elif resume:
            store = Store.open(staged, create=False, clock=clock)
            state = store.get_meta("pull_state")
            if state not in ("in_progress", "verified"):
                store.close()
                raise StagedExists(
                    f"staged file {staged} is not a resumable pull (pull_state={state!r}); "
                    "discard it with --discard-staged"
                )
            return store, True
        else:
            raise StagedExists(
                f"a staged pull already exists at {staged}. Resume it (--resume) or throw it "
                "away (--discard-staged); a half-built file is never promoted and never silently reused."
            )
    elif resume:
        raise StagedExists(f"--resume given but there is no staged file at {staged}")
    store = Store.open(staged, create=True, clock=clock)
    store.set_meta("pull_state", "in_progress")
    return store, False


def full_pull(
    client: WikiClient,
    out: str | os.PathLike[str],
    *,
    env: Mapping[str, str] | None = None,
    resume: bool = False,
    discard_staged: bool = False,
    probe_words: Sequence[str] = DEFAULT_PROBE_WORDS,
    max_missing: int | None = None,
    batch_size: int = BATCH_SIZE,
    clock: Callable[[], datetime] | None = None,
    min_free_bytes: int | None = None,
    free_bytes_fn: Callable[[str], int] | None = None,
    log: Callable[[str], None] | None = None,
) -> PullResult:
    """Pull the allow-listed namespaces into `<out>.staged`, verify, promote to `out`.

    Raises `PullError` (or a `WikiApiError`, `PromoteError`) on any failure; the live file
    `out` is not touched by anything that raises. A raise leaves the staged file for
    `resume=True` or `discard_staged=True`.
    """
    require_contact(env)
    log = log or (lambda m: None)
    out_p = Path(out)
    staged = staged_path_for(out_p)
    if out_p.parent and not out_p.parent.exists():
        raise PullError(f"output directory does not exist: {out_p.parent}")
    store, resumed_run = _open_staged(staged, resume=resume, discard=discard_staged, clock=clock)
    try:
        return _run(
            client, store, out_p, staged, resumed_run=resumed_run, probe_words=probe_words,
            max_missing=max_missing, batch_size=batch_size, min_free_bytes=min_free_bytes,
            free_bytes_fn=free_bytes_fn, log=log,
        )
    finally:
        store.close()


def _run(
    client: WikiClient, store: Store, out_p: Path, staged: Path, *, resumed_run: bool,
    probe_words: Sequence[str], max_missing: int | None, batch_size: int,
    min_free_bytes: int | None, free_bytes_fn: Callable[[str], int] | None,
    log: Callable[[str], None],
) -> PullResult:
    ids = ingested_namespace_ids(store.namespaces)
    if not ids:
        raise PullError("no namespace is allow-listed for ingestion")
    game_version = client.wiki_current_version()
    if resumed_run:
        prior = store.get_meta("game_version")
        if prior != game_version:
            raise PullError(
                f"the staged pull was for game version {prior!r} but the wiki now says "
                f"{game_version!r}; discard the staged file and start again (design 4.7)"
            )
    else:
        store.set_meta("game_version", game_version)
        store.set_meta("pull_started_utc", iso(store.now()))
    run_id = store.start_run("pull")

    # Enumerate. Redirect pages are not enumerated (nonredirects only); they go in `redirects`.
    infos: list[PageInfo] = []
    seen_ids: set[int] = set()
    for ns in ids:
        for info in client.enumerate_pages(ns):
            if info.ns not in ids:
                raise PullError(f"enumeration returned ns {info.ns} outside the allow-list: {info.title}")
            if info.page_id in seen_ids:
                raise PullError(f"enumeration listed page id {info.page_id} twice ({info.title})")
            seen_ids.add(info.page_id)
            infos.append(info)
    enumerated = len(infos)
    log(f"enumerated {enumerated} pages in namespaces {ids}; game version {game_version}")
    if enumerated == 0:
        raise PullError("the enumeration returned no pages; refusing to build an empty mirror")

    stats = PullStats()
    stored = _stored_revids(store) if resumed_run else {}
    todo = [i for i in infos if stored.get(i.page_id) != i.lastrevid]
    already = [i for i in infos if stored.get(i.page_id) == i.lastrevid]
    if resumed_run:
        log(f"resuming: {len(already)} pages already staged, {len(todo)} to fetch")
    # Re-run the text stage over pages already staged so the report is complete.
    for info in already:
        row = store.conn.execute("SELECT wikitext FROM pages WHERE page_id=?", (info.page_id,)).fetchone()
        _extract(info.title, row[0] or "", stats)

    by_id = {i.page_id: i for i in infos}
    missing: list[str] = []
    moved: list[dict[str, Any]] = []
    fetched_n = 0
    n_batches = math.ceil(len(todo) / batch_size) if todo else 0
    for b in range(n_batches):
        batch = todo[b * batch_size : (b + 1) * batch_size]
        result = client.fetch_revisions(titles=[i.title for i in batch])
        missing.extend(m.title for m in result.missing)
        with store.transaction():
            for rev in result.revisions:
                chunks = _extract(rev.title, rev.wikitext, stats)
                store.apply_revision(
                    rev, chunks=chunks, baseline=True, game_version=game_version,
                    source="full_pull", run_id=run_id,
                )
                info = by_id.get(rev.page_id)
                if info is not None and info.lastrevid != rev.revid:
                    moved.append({"title": rev.title, "enumerated_revid": info.lastrevid, "fetched_revid": rev.revid})
                fetched_n += 1
        log(f"batch {b + 1}/{n_batches}: {fetched_n} pages stored, {len(missing)} missing so far")

    # Every enumerated page must be stored or named missing. Nothing may vanish quietly.
    stored_now = _stored_revids(store)
    missing_set = set(missing)
    unaccounted = [i.title for i in infos if i.page_id not in stored_now and i.title not in missing_set]
    if unaccounted:
        raise PullError(f"{len(unaccounted)} enumerated pages are neither stored nor missing: {unaccounted[:10]}")
    allowed_missing = max_missing if max_missing is not None else max(2, math.ceil(0.01 * enumerated))
    if len(missing) > allowed_missing:
        raise PullError(
            f"{len(missing)} enumerated pages came back missing (allowed {allowed_missing}): {missing[:10]}"
        )

    redirects_report = _store_redirects(client, store, ids, stored_now, by_id)

    now_s = iso(store.now())
    store.set_meta("baseline_utc", now_s)
    store.set_meta("last_full_pull_utc", now_s)
    store.set_meta("license", LICENSE)
    store.set_meta("source", "dwarffortresswiki.org")
    store.set_meta("namespaces_ingested", json.dumps(ids))
    store.set_meta("pull_requests", str(client.requests_made))
    store.finish_run(run_id, "ok", requests=client.requests_made, pages_fetched=fetched_n)
    # A pull is not a refresh: undo the refresh markers `start_run`/`finish_run` maintain, so
    # `status` and `staleness()` describe the baseline honestly (last_full_pull_utc carries it).
    store.set_meta("last_refresh_ok_utc", None)
    store.set_meta("last_refresh_attempt_utc", None)
    store.set_meta("pull_state", "verified")

    report = {
        "generated_utc": now_s,
        "game_version": game_version,
        "database": str(out_p),
        "requests": client.requests_made,
        "client_warnings": list(client.warnings),
        "resumed": resumed_run,
        "enumerated_pages": enumerated,
        "stored_pages": len(stored_now),
        "fetched_this_run": fetched_n,
        "reused_from_staged": len(already),
        "missing_titles": sorted(missing),
        "revid_moved_during_pull": moved,
        "redirects": redirects_report,
        "text_stage": stats.to_dict(),
    }
    staged_report = Path(str(staged) + ".report.json")
    staged_report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    store.close()  # release the file before verification and the swap

    kw: dict[str, Any] = {}
    if min_free_bytes is not None:
        kw["min_free_bytes"] = min_free_bytes
    if free_bytes_fn is not None:
        kw["free_bytes_fn"] = free_bytes_fn
    promoted = promote_staged(
        staged, out_p, expected_page_count=enumerated - len(missing), probe_words=list(probe_words), **kw
    )
    rpath = report_path_for(out_p)
    rpath.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    staged_report.unlink(missing_ok=True)
    _remove_db_files(staged)  # sidecars only; the main file was moved by the promote
    return PullResult(
        out=str(out_p), staged=str(staged), game_version=game_version, enumerated=enumerated,
        stored=len(stored_now), resumed=len(already), missing=sorted(missing),
        redirects=redirects_report["total"], requests=client.requests_made, report=report,
        report_path=str(rpath), promote=promoted,
    )


def _store_redirects(
    client: WikiClient, store: Store, ids: Sequence[int], stored: dict[int, int], by_id: Mapping[int, PageInfo],
) -> dict[str, Any]:
    """Fill the `redirects` table (design 4.6). Unresolved and dangling redirects are reported."""
    live_titles = {
        (int(r[0]), r[1].lower()) for r in store.conn.execute("SELECT ns, title FROM pages WHERE state='live'")
    }
    total = 0
    unresolved: list[str] = []
    dangling: list[dict[str, Any]] = []
    for ns in ids:
        rows = client.all_redirects(ns, target_namespaces=ids)
        with store.transaction():
            for r in rows:
                store.conn.execute(
                    "INSERT OR REPLACE INTO redirects(from_title, from_ns, from_page_id, to_title, to_ns) "
                    "VALUES (?,?,?,?,?)",
                    (r.from_title, r.from_ns, None, r.to_title, r.to_ns),
                )
                total += 1
                if r.to_title is None:
                    unresolved.append(r.from_title)
                elif (r.to_ns, r.to_title.lower()) not in live_titles:
                    dangling.append({"from": r.from_title, "to": r.to_title})
    return {
        "total": total,
        "unresolved_target": sorted(unresolved)[:200],
        "unresolved_target_count": len(unresolved),
        "target_not_in_mirror": dangling[:200],
        "target_not_in_mirror_count": len(dangling),
    }


def format_summary(report: Mapping[str, Any]) -> str:
    ts = report["text_stage"]
    lines = [
        f"game version {report['game_version']}; {report['stored_pages']} pages stored of "
        f"{report['enumerated_pages']} enumerated ({len(report['missing_titles'])} missing); "
        f"{report['requests']} requests",
        f"chunks {ts['chunks']}, degraded chunks {ts['degraded_chunks']} on {ts['degraded_pages']} pages; "
        f"{ts['unlisted_templates_distinct']} unlisted templates ({ts['unlisted_templates_total_uses']} uses)",
        f"pages with section_text_lost: {len(ts['section_text_lost_pages'])}; "
        f"text-stage failures: {len(ts['text_stage_failures'])}",
        f"redirects {report['redirects']['total']} "
        f"({report['redirects']['unresolved_target_count']} unresolved, "
        f"{report['redirects']['target_not_in_mirror_count']} dangling)",
    ]
    return "\n".join(lines)


# ---- status -------------------------------------------------------------------


def database_status(db: str | os.PathLike[str]) -> dict[str, Any]:
    """Read-only summary from the store's own helpers. Raises (never returns an empty ok)
    when the file is missing, unreadable, or not a pulled database."""
    store = Store.open_readonly(db)
    try:
        counts = store.counts()
        stale = store.staleness()
        baseline = store.get_meta("baseline_utc")
        version = store.get_meta("game_version")
        if not baseline or not version or counts["pages_live"] == 0:
            raise StoreError(
                f"{db} opens but holds no baseline (baseline_utc={baseline!r}, game_version={version!r}, "
                f"live pages={counts['pages_live']}); it is not a completed pull"
            )
        return {
            "database": str(db),
            "game_version": version,
            "pages": counts["pages_live"],
            "chunks": counts["chunks"],
            "baseline_utc": baseline,
            "last_refresh_ok_utc": store.get_meta("last_refresh_ok_utc"),
            "held_changes": counts["held"],
            "staleness": stale["status"],
            "staleness_reasons": stale["reasons"],
            "age_hours": stale["age_hours"],
            "promotion_overdue": stale["promotion_overdue"],
        }
    finally:
        store.close()


__all__ = [
    "SEPARATOR", "PullError", "ContactRequired", "StagedExists", "PullResult", "PullStats",
    "adapt_chunks", "database_status", "format_summary", "full_pull", "plan_pull",
    "report_path_for", "require_contact", "staged_path_for", "WikiApiError", "PromoteError",
]
