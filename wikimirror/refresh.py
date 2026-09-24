"""One refresh run of the wiki mirror: the feed, the sweep, the hold, the changelog.

`docs/CONSULTANT-WIKI.md` sections 4.2 to 4.6, 5, 6 and 9, amended by section 13.

The command a timer runs (every 6 hours, with a random delay of up to 30
minutes, `DFWIKI_UA_CONTACT` set in its environment):

    python -m wikimirror.refresh --db /var/lib/dfwiki/df-wiki.sqlite3 --out /var/lib/dfwiki

Exit status 0 only for a run recorded `ok` (or a dry run, or a run skipped
because another one holds the lock); anything else is non-zero and printed.

What a run does, in order:

1. Refuse if another run is `running` and younger than the lock age; break a
   stale one (older than 2 hours) and record it.
2. Record a `refresh_runs` row, then **promote due held changes**
   (`Store.promote_due`, every run, before any network work: it is local, so a
   dead network never freezes the one-week hold).
3. Read the wiki's current version (`Template:Current/version`).
4. Plan. Normally the `recentchanges` feed (edit, new) and `logevents`
   (delete, move) since the cursor minus a 10 minute overlap, folded to one
   target per page. A **sweep** replaces or adds to that when the cursor is
   missing or older than 60 days, no run succeeded for 7 days, the last sweep
   is a week old, an operator asks, or the feed shows something it cannot
   place (a move with no target, a delete it cannot resolve). The sweep lists
   every in-scope page with `lastrevid` and finds pages added, changed,
   renamed or gone.
5. Fetch every changed body (network only; nothing is written yet).
6. Run the text stage on each body (pure).
7. **One transaction** applies everything through the store's hold rule
   (`apply_revision`, `apply_move`, `apply_delete`: every change after the
   baseline is HELD for a week), refreshes the redirect table on a sweep,
   records a version bump, and advances the cursor. Any failure anywhere
   before the commit leaves the database and the cursor exactly as they were;
   the next run repeats the same window (idempotent by revid).
8. Finish the run row, write the changelog JSONL and, when due, the digest.

Deviations from the design text, on purpose:

* One transaction per run, not per batch of 50 (4.3 step 6): bodies are all
  fetched before anything is written, so a network failure writes nothing and
  a write failure rolls back the whole run. The cost is memory for one run's
  bodies (a handful of pages a day, thousands after a long gap).
* The redirect table is refreshed by the sweep only, immediately and not held.
  A redirect created since the last sweep does not resolve until the next one.
* A page that becomes a redirect is held as a delete (reason `deleted`).
* Nothing is guessed: a body the API reports missing after an edit or move
  event is NOT deleted on the spot (a delete event or the sweep decides), a
  sweep that would delete an implausible share of the mirror aborts, and every
  case the store cannot express is a named warning in the run record.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

from wikimirror import changelog, digest
from wikimirror import text as textmod
from wikimirror.api import (
    BlockedError,
    BudgetExceeded,
    PageInfo,
    PageRevision,
    WikiClient,
)
from wikimirror.store import (
    Store,
    StoreError,
    ingested_namespace_ids,
    iso,
    normalize_title,
    parse_iso,
)

# meta keys this module reads or writes (design 8.2). `rc_cursor_ts`, `rc_cursor_ids`
# and `last_sweep_utc` are written here; `last_full_pull_utc` and `install_version`
# are written by the pull (slice S3) or the operator and only read here.
META_CURSOR_TS = "rc_cursor_ts"
META_CURSOR_IDS = "rc_cursor_ids"
META_LAST_SWEEP = "last_sweep_utc"
META_WIKI_VERSION = "wiki_current_version"
META_INSTALL_VERSION = "install_version"
META_VERSION_STATUS = "version_status"
META_LAST_DIGEST = "last_digest_utc"
META_LAST_SUMMARY = "last_run_summary"

_LOG_ACTIONS = {
    "delete": "delete",
    "delete_redir": "delete",
    "restore": "restore",
    "move": "move",
    "move_redir": "move",
}


class RefreshError(RuntimeError):
    """A named refresh failure (no baseline, an implausible sweep, ...)."""


@dataclass
class RefreshConfig:
    overlap: timedelta = timedelta(minutes=10)
    sweep_interval: timedelta = timedelta(days=7)
    stale_cursor: timedelta = timedelta(days=60)
    stall_limit: timedelta = timedelta(days=7)
    lock_break: timedelta = timedelta(hours=2)
    daily_budget: int = 2000
    force_sweep: bool = False
    dry_run: bool = False
    refresh_redirects: bool = True
    absent_floor: int = 25
    absent_fraction: float = 0.02
    max_chunk_chars: int = 2000
    out_dir: str | os.PathLike[str] | None = None
    text_policy: Any = None
    cited_by: Callable[[int], Iterable[str]] | None = None
    doctrine_flags: Callable[[], Iterable[str]] | None = None


@dataclass
class RefreshResult:
    status: str = "ok"  # ok | failed | blocked | locked | dry_run
    run_id: str | None = None
    mode: str = "refresh"
    sweep: bool = False
    sweep_reasons: list[str] = field(default_factory=list)
    cursor_from: str | None = None
    cursor_to: str | None = None
    requests: int = 0
    pages_fetched: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    promotions: list[Any] = field(default_factory=list)
    unlisted_templates: dict[str, int] = field(default_factory=dict)
    degraded_reasons: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error_class: str | None = None
    error_detail: str | None = None
    changelog_path: str | None = None
    digest_path: str | None = None
    plan: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "dry_run", "locked")

    def summary(self) -> dict[str, Any]:
        top = dict(sorted(self.unlisted_templates.items(), key=lambda kv: (-kv[1], kv[0]))[:25])
        return {
            "sweep": self.sweep,
            "sweep_reasons": list(self.sweep_reasons),
            "counts": dict(sorted(self.counts.items())),
            "promoted": len(self.promotions),
            "unlisted_templates_top25": top,
            "unlisted_templates_total": len(self.unlisted_templates),
            "degraded_reasons": dict(sorted(self.degraded_reasons.items())),
            "warnings": list(self.warnings),
        }


# ---- events and the plan ----------------------------------------------------


@dataclass(frozen=True)
class Event:
    kind: str  # edit | new | restore | move | delete
    page_id: int
    ns: int
    title: str
    timestamp: str
    comment: str
    source: str  # recentchanges | logevents
    ident: str  # "rc:<rcid>" or "log:<logid>", for the cursor's seen-id set
    order: int
    revid: int | None = None
    target_title: str | None = None


@dataclass
class FetchItem:
    title: str
    source: str
    reason: str


@dataclass
class DeleteItem:
    page_id: int
    reason: str
    source: str
    timestamp: str | None
    comment: str | None


@dataclass
class Plan:
    fetch: dict[str, FetchItem] = field(default_factory=dict)
    deletes: dict[int, DeleteItem] = field(default_factory=dict)
    sweep_absent: dict[str, int] = field(default_factory=dict)
    redirects: list[Any] | None = None
    newest_ts: str | None = None
    seen_ids: list[tuple[str, str]] = field(default_factory=list)  # (timestamp, ident)

    def add_fetch(self, title: str, source: str, reason: str) -> None:
        key = normalize_title(title)
        if key not in self.fetch:
            self.fetch[key] = FetchItem(title, source, reason)


def _bump(counts: dict[str, int], key: str, n: int = 1) -> None:
    counts[key] = counts.get(key, 0) + n


def _vkey(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


# ---- reading the store ------------------------------------------------------


def _stored_pages(store: Store, ns_ids: list[int]) -> dict[int, Any]:
    marks = ",".join("?" for _ in ns_ids)
    rows = store.conn.execute(f"SELECT * FROM pages WHERE ns IN ({marks})", ns_ids).fetchall()
    return {r["page_id"]: r for r in rows}


def _lookup_page_id(store: Store, title: str, ns: int) -> int | None:
    t = normalize_title(title)
    row = store.conn.execute(
        "SELECT page_id FROM pages WHERE ns = ? AND title = ? COLLATE NOCASE "
        "ORDER BY (state = 'live') DESC LIMIT 1",
        (ns, t),
    ).fetchone()
    if row:
        return int(row[0])
    row = store.conn.execute("SELECT page_id FROM aliases WHERE alias_title = ? COLLATE NOCASE", (t,)).fetchone()
    return int(row[0]) if row else None


def _held_move_to(store: Store, page_id: int, title: str) -> bool:
    return (
        store.conn.execute(
            "SELECT 1 FROM held_changes WHERE page_id = ? AND op = 'move' AND title = ?", (page_id, title)
        ).fetchone()
        is not None
    )


def _decide_sweep(store: Store, cfg: RefreshConfig, now: datetime) -> tuple[bool, bool, list[str], str | None]:
    """(use_feed, sweep, reasons, cursor_ts). Every reason is recorded, never implied."""
    cursor = store.get_meta(META_CURSOR_TS)
    reasons: list[str] = []
    use_feed = True
    if cfg.force_sweep:
        reasons.append("operator_requested")
    if not cursor:
        reasons.append("no_cursor")
        use_feed = False
    else:
        age = now - parse_iso(cursor)
        if age > cfg.stale_cursor:
            reasons.append(f"cursor_older_than_{cfg.stale_cursor.days}_days")
            use_feed = False
    ok = store.get_meta("last_refresh_ok_utc")
    pull = store.get_meta("last_full_pull_utc")
    refs = [parse_iso(x) for x in (ok, pull) if x]
    if not refs or now - max(refs) > cfg.stall_limit:
        reasons.append("no_successful_refresh_for_7_days")
    # The full pull is itself a complete listing, so the first weekly sweep counts from it.
    base = store.get_meta(META_LAST_SWEEP) or pull
    if base is None or now - parse_iso(base) >= cfg.sweep_interval:
        reasons.append("weekly_sweep_due")
    return use_feed, bool(reasons), reasons, cursor


# ---- the feed ---------------------------------------------------------------


def _collect_events(
    client: WikiClient,
    store: Store,
    cfg: RefreshConfig,
    cursor_ts: str,
    ns_ids: list[int],
    plan: Plan,
    counts: dict[str, int],
    warnings: list[str],
) -> list[str]:
    """Read recentchanges and logevents since the cursor into `plan`.

    Returns extra sweep reasons (a feed row this run cannot place asks for a sweep).
    """
    start = iso(parse_iso(cursor_ts) - cfg.overlap)
    seen = set(json.loads(store.get_meta(META_CURSOR_IDS) or "[]"))
    events: list[Event] = []
    ask_sweep: list[str] = []
    order = 0
    newest = None

    def note(ts: str, ident: str) -> None:
        nonlocal newest
        plan.seen_ids.append((ts, ident))
        if newest is None or ts > newest:
            newest = ts

    rc_rows = client.recent_changes(start=start, namespaces=ns_ids)
    rc_log_unmatched: list[Any] = []
    for row in rc_rows:
        ident = f"rc:{row.rcid}"
        _bump(counts, "feed_rows")
        note(row.timestamp, ident)
        if ident in seen:
            _bump(counts, "feed_rows_already_seen")
            continue
        if row.type in ("edit", "new"):
            order += 1
            events.append(
                Event(row.type, row.page_id, row.ns, row.title, row.timestamp, row.comment,
                      "recentchanges", ident, order, revid=row.revid)
            )
        elif row.type == "log" and row.log_type in ("delete", "move"):
            rc_log_unmatched.append(row)
        else:
            _bump(counts, "feed_rows_ignored")

    log_rows = []
    for log_type in ("delete", "move"):
        log_rows.extend(client.log_events(log_type=log_type, start=start))
    log_titles = {(r.log_type, normalize_title(r.title)) for r in log_rows}
    for row in log_rows:
        ident = f"log:{row.log_id}"
        _bump(counts, "log_rows")
        note(row.timestamp, ident)
        if ident in seen:
            _bump(counts, "feed_rows_already_seen")
            continue
        kind = _LOG_ACTIONS.get(row.action)
        if kind is None:
            _bump(counts, "log_rows_ignored")
            continue
        order += 1
        events.append(
            Event(kind, row.page_id, row.ns, row.title, row.timestamp, row.comment, "logevents",
                  ident, order, target_title=row.target_title)
        )
    # A delete or move the feed shows and logevents does not is a disagreement to
    # resolve with the sweep, never to ignore.
    for row in rc_log_unmatched:
        if (row.log_type, normalize_title(row.title)) not in log_titles:
            warnings.append(f"feed_log_row_not_in_logevents:{row.log_type}:{row.title}")
            ask_sweep.append("feed_logevents_disagree")

    _fold(events, store, ns_ids, plan, counts, warnings, ask_sweep)
    plan.newest_ts = newest
    return sorted(set(ask_sweep))


def _fold(
    events: list[Event],
    store: Store,
    ns_ids: list[int],
    plan: Plan,
    counts: dict[str, int],
    warnings: list[str],
    ask_sweep: list[str],
) -> None:
    """Fold the events per page (design 4.3 step 4): the last event decides."""
    by_key: dict[Any, list[Event]] = {}
    for ev in sorted(events, key=lambda e: (e.timestamp, e.order)):
        pid = ev.page_id or _lookup_page_id(store, ev.title, ev.ns)
        key = pid if pid else ("title", ev.ns, normalize_title(ev.title))
        by_key.setdefault(key, []).append(ev)
    for key, evs in by_key.items():
        pid = key if isinstance(key, int) else None
        stored = store.conn.execute("SELECT * FROM pages WHERE page_id = ?", (pid,)).fetchone() if pid else None
        fetch_title: str | None = None
        moved = False
        want_revid = 0
        delete: Event | None = None
        for ev in evs:
            _bump(counts, "events_" + ev.kind)
            if ev.kind in ("edit", "new", "restore"):
                fetch_title, delete = ev.title, None
                want_revid = max(want_revid, ev.revid or 0)
            elif ev.kind == "move":
                if not ev.target_title:
                    warnings.append(f"move_without_target:{ev.title}")
                    ask_sweep.append("move_target_unknown")
                    continue
                fetch_title, delete, moved = ev.target_title, None, True
            elif ev.kind == "delete":
                fetch_title, delete = None, ev
        if len(evs) > 1:
            _bump(counts, "events_folded", len(evs) - 1)
        source = evs[-1].source
        if delete is not None:
            if pid is None:
                warnings.append(f"delete_event_unresolved:{delete.title}")
                ask_sweep.append("delete_unresolved")
            elif stored is not None or delete.ns in ns_ids:
                plan.deletes[pid] = DeleteItem(pid, "deleted", "logevents", delete.timestamp, delete.comment)
            else:
                _bump(counts, "events_out_of_scope")
            continue
        if fetch_title is None:
            continue
        if (
            not moved
            and stored is not None
            and stored["state"] != "deleted"
            and normalize_title(stored["title"]) == normalize_title(fetch_title)
            and (stored["latest_revid"] or stored["revid"] or 0) >= want_revid > 0
            and not any(e.kind == "restore" for e in evs)
        ):
            _bump(counts, "already_current")
            continue
        plan.add_fetch(fetch_title, source, "moved" if moved else "feed")


# ---- the sweep --------------------------------------------------------------


def _plan_sweep(
    client: WikiClient,
    store: Store,
    cfg: RefreshConfig,
    ns_ids: list[int],
    plan: Plan,
    counts: dict[str, int],
) -> None:
    infos: list[PageInfo] = []
    for ns in ns_ids:
        infos.extend(client.enumerate_pages(ns))
    stored = _stored_pages(store, ns_ids)
    active = {pid: r for pid, r in stored.items() if r["state"] in ("live", "pending")}
    listed = {i.page_id: i for i in infos}
    if active and not infos:
        raise RefreshError("sweep_implausible: the wiki listed no pages but the mirror has some")
    for info in infos:
        row = stored.get(info.page_id)
        if row is None:
            plan.add_fetch(info.title, "sweep", "sweep_added")
        elif row["state"] == "deleted":
            plan.add_fetch(info.title, "sweep", "sweep_restored")
        else:
            latest = row["latest_revid"] or row["revid"] or 0
            if info.lastrevid > latest:
                plan.add_fetch(info.title, "sweep", "sweep_changed")
            elif normalize_title(info.title) != normalize_title(row["title"]) and not _held_move_to(
                store, info.page_id, info.title
            ):
                plan.add_fetch(info.title, "sweep", "sweep_renamed")
    absent = [pid for pid in active if pid not in listed]
    limit = max(cfg.absent_floor, int(cfg.absent_fraction * len(active)))
    if len(absent) > limit:
        raise RefreshError(
            f"sweep_implausible: {len(absent)} of {len(active)} mirrored pages are absent from the "
            f"listing (limit {limit}); refusing to hold that many deletes"
        )
    for pid in absent:
        title = active[pid]["title"]
        plan.sweep_absent[normalize_title(title)] = pid
        plan.add_fetch(title, "sweep", "sweep_absent")
    _bump(counts, "sweep_listed", len(infos))
    _bump(counts, "sweep_absent_candidates", len(absent))
    if cfg.refresh_redirects:
        rows: list[Any] = []
        for ns in ns_ids:
            rows.extend(client.all_redirects(ns, target_namespaces=ns_ids))
        plan.redirects = rows
        _bump(counts, "redirects_listed", len(rows))


# ---- applying ---------------------------------------------------------------


def _apply(
    store: Store,
    plan: Plan,
    revs: list[PageRevision],
    missing: list[Any],
    pages_text: dict[int, Any],
    *,
    run_id: str,
    game_version: str,
    ns_ids: list[int],
    counts: dict[str, int],
    warnings: list[str],
    extras: dict[int, dict[str, Any]],
) -> None:
    seq = 0

    def kind_of(change_id: int | None) -> str | None:
        if change_id is None:
            return None
        r = store.conn.execute("SELECT kind FROM changes WHERE id = ?", (change_id,)).fetchone()
        return r[0] if r else None

    def record(res: Any, reason: str | None = None) -> None:
        if res.action == "held":
            k = kind_of(res.change_id)
            _bump(counts, f"held_{k}")
            if reason and res.change_id:
                extras[res.change_id] = {"reason": reason}
        else:
            _bump(counts, res.action)

    for pid, item in sorted(plan.deletes.items()):
        seq += 1
        record(
            store.apply_delete(pid, reason=item.reason, run_id=run_id, seq=seq, source=item.source,
                               wiki_timestamp=item.timestamp, edit_summary=item.comment),
            item.reason,
        )

    for rev in sorted(revs, key=lambda r: (r.page_id, r.revid)):
        item = plan.fetch.get(normalize_title(rev.title))
        source = item.source if item else "recentchanges"
        absent_pid = plan.sweep_absent.get(normalize_title(rev.title))
        if absent_pid is not None and rev.page_id != absent_pid:
            # The old title now belongs to another page (a redirect left behind, or a
            # new page): the page we hold is gone from this title and from the listing.
            seq += 1
            record(store.apply_delete(absent_pid, reason="left_scope", run_id=run_id, seq=seq,
                                      source="sweep", wiki_timestamp=rev.timestamp), "left_scope")
            continue
        stored = store.conn.execute("SELECT * FROM pages WHERE page_id = ?", (rev.page_id,)).fetchone()
        if rev.ns not in ns_ids:
            if stored is not None and stored["state"] != "deleted":
                seq += 1
                record(store.apply_delete(rev.page_id, reason="left_scope", run_id=run_id, seq=seq,
                                          source=source, wiki_timestamp=rev.timestamp,
                                          edit_summary=rev.comment), "left_scope")
            else:
                _bump(counts, "fetched_out_of_scope")
            continue
        if rev.is_redirect:
            if stored is not None and stored["state"] != "deleted":
                seq += 1
                warnings.append(f"became_redirect:{rev.title}")
                record(store.apply_delete(rev.page_id, reason="deleted", run_id=run_id, seq=seq,
                                          source=source, wiki_timestamp=rev.timestamp,
                                          edit_summary=rev.comment), "deleted")
            else:
                _bump(counts, "redirects_seen")
            continue
        pt = pages_text[rev.page_id]
        chunks = [(c.section_path_str, c.text) for c in pt.chunks]
        seq += 1
        res = store.apply_revision(rev, chunks=chunks, source=source, run_id=run_id, seq=seq,
                                   game_version=game_version)
        if res.action == "unchanged":
            if stored is not None and stored["state"] == "deleted":
                # The store compares the revid with the last one seen; a restored page
                # keeps its revid, so the store cannot express the restore. Say so.
                warnings.append(f"restore_not_applied:{rev.title}")
                _bump(counts, "restore_not_applied")
            elif stored is not None and normalize_title(stored["title"]) != normalize_title(rev.title):
                seq += 1
                record(store.apply_move(rev.page_id, rev.title, rev.ns, run_id=run_id, seq=seq,
                                        source=source, wiki_timestamp=rev.timestamp,
                                        edit_summary=rev.comment))
            else:
                _bump(counts, "unchanged")
            continue
        record(res)
        if res.action == "held" and source == "sweep":
            _bump(counts, "sweep_found")

    for m in missing:
        item = plan.fetch.get(normalize_title(m.title))
        pid = plan.sweep_absent.get(normalize_title(m.title))
        if pid is not None:
            seq += 1
            record(store.apply_delete(pid, reason="deleted", run_id=run_id, seq=seq, source="sweep"),
                   "deleted")
        else:
            # An edit or move event whose page is gone by fetch time: a race. A delete
            # event or the sweep decides; deleting on a guess is not allowed.
            warnings.append(f"missing_after_event:{m.title}")
            _bump(counts, "race_missing")


def _refresh_redirects(store: Store, rows: list[Any], ns_ids: list[int], counts: dict[str, int]) -> None:
    marks = ",".join("?" for _ in ns_ids)
    store.conn.execute(f"DELETE FROM redirects WHERE from_ns IN ({marks})", ns_ids)
    for r in rows:
        store.conn.execute(
            "INSERT OR REPLACE INTO redirects(from_title, from_ns, from_page_id, to_title, to_ns) "
            "VALUES (?,?,?,?,?)",
            (r.from_title, r.from_ns, None, r.to_title, r.to_ns),
        )
    _bump(counts, "redirects_written", len(rows))


def _record_version(
    store: Store, run_id: str, wiki_version: str, now_s: str, warnings: list[str], seq: int
) -> None:
    prev = store.get_meta(META_WIKI_VERSION)
    if prev and prev != wiki_version:
        store.conn.execute(
            "INSERT INTO changes(run_id, seq, kind, ns, title, old_title, new_title, source, "
            "detected_utc, state, made_visible_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, seq, "version_bump", 10, "Template:Current/version", prev, wiki_version,
             "refresh", now_s, "visible", now_s),
        )
    store.set_meta(META_WIKI_VERSION, wiki_version)
    install = store.get_meta(META_INSTALL_VERSION)
    if install is None:
        status = "unknown"
        warnings.append("install_version_unset")
    elif install == wiki_version:
        status = "current"
    else:
        try:
            status = "wiki_ahead" if _vkey(wiki_version) > _vkey(install) else "wiki_behind"
        except ValueError:
            status = "wiki_ahead"
            warnings.append(f"install_version_unparseable:{install}")
    store.set_meta(META_VERSION_STATUS, status)


# ---- the run ----------------------------------------------------------------


def _check_lock(store: Store, cfg: RefreshConfig, now: datetime, res: RefreshResult) -> bool:
    """True if this run may proceed. A stale `running` row is broken and recorded."""
    rows = store.conn.execute(
        "SELECT run_id, started_utc FROM refresh_runs WHERE status = 'running'"
    ).fetchall()
    for r in rows:
        if now - parse_iso(r["started_utc"]) < cfg.lock_break:
            res.status = "locked"
            res.warnings.append(f"another_run_in_progress:{r['run_id']}")
            if not cfg.dry_run:
                store.set_meta("last_lock_skip_utc", iso(now))
            return False
    for r in rows:
        store.finish_run(r["run_id"], "failed", error_class="stale_lock_broken",
                         error_detail=f"still 'running' after {cfg.lock_break}; broken by a later run")
        res.warnings.append(f"stale_lock_broken:{r['run_id']}")
    return True


def _daily_headroom(store: Store, cfg: RefreshConfig, now: datetime) -> int:
    today = now.strftime("%Y-%m-%d")
    if store.get_meta("requests_today_date") != today:
        return cfg.daily_budget
    return cfg.daily_budget - int(store.get_meta("requests_today_count", "0") or 0)


def run_refresh(
    store: Store,
    client: WikiClient,
    config: RefreshConfig | None = None,
    *,
    extract: Callable[..., Any] | None = None,
) -> RefreshResult:
    """One refresh run. Never raises for a fetch, store or plan failure: the result
    carries the status and the run row records it. A non-`ok` status must be treated
    as a failure by the caller (`main` exits non-zero)."""
    cfg = config or RefreshConfig()
    extract = extract or textmod.extract_page
    res = RefreshResult()
    now = store.now()
    if not cfg.dry_run and not _check_lock(store, cfg, now, res):
        return res
    use_feed, sweep, sweep_reasons, cursor_ts = _decide_sweep(store, cfg, now)
    res.mode = "sweep" if not use_feed else "refresh"
    res.cursor_from = cursor_ts
    run_id: str | None = None
    if not cfg.dry_run:
        run_id = store.start_run(res.mode, cursor_from=cursor_ts)
        res.run_id = run_id
    original_max = client.max_requests
    requests_before = client.requests_made
    extras: dict[int, dict[str, Any]] = {}
    promote_error: str | None = None
    try:
        if run_id is not None:
            try:
                res.promotions = list(store.promote_due())
                res.counts["promoted"] = len(res.promotions)
            except StoreError as exc:
                promote_error = f"{type(exc).__name__}: {exc}"
                res.warnings.append(f"promote_failed:{exc}")
        _run_body(store, client, cfg, res, run_id, use_feed, sweep, sweep_reasons, cursor_ts,
                  extract, extras, original_max, now)
        if promote_error and res.status == "ok":
            res.status, res.error_class, res.error_detail = "failed", "promote_failed", promote_error
    except BlockedError as exc:
        res.status, res.error_class, res.error_detail = "blocked", "blocked", str(exc)
    except BudgetExceeded as exc:
        res.status, res.error_class, res.error_detail = "failed", "budget", str(exc)
    except Exception as exc:  # noqa: BLE001 - recorded, and the caller exits non-zero
        res.status, res.error_class, res.error_detail = "failed", type(exc).__name__, str(exc)
    finally:
        client.max_requests = original_max
        res.requests = client.requests_made - requests_before
    if cfg.dry_run:
        if res.status == "ok":
            res.status = "dry_run"
        return res
    assert run_id is not None
    store.add_requests_today(res.requests)
    store.finish_run(run_id, res.status, requests=res.requests, pages_fetched=res.pages_fetched,
                     cursor_to=res.cursor_to, error_class=res.error_class,
                     error_detail=(res.error_detail or None) and res.error_detail[:1000])
    store.set_meta(META_LAST_SUMMARY, json.dumps({"run_id": run_id, **res.summary()}))
    _write_outputs(store, cfg, res, run_id, extras)
    return res


def _run_body(
    store: Store, client: WikiClient, cfg: RefreshConfig, res: RefreshResult, run_id: str | None,
    use_feed: bool, sweep: bool, sweep_reasons: list[str], cursor_ts: str | None,
    extract: Callable[..., Any], extras: dict[int, dict[str, Any]], original_max: int, now: datetime,
) -> None:
    ns_ids = ingested_namespace_ids()
    if not store.get_meta("last_full_pull_utc") and not store.counts()["pages_live"]:
        raise RefreshError("no_baseline: the mirror has no pages and no full pull was recorded; run the pull first")
    headroom = _daily_headroom(store, cfg, now)
    if headroom <= 0:
        raise BudgetExceeded(f"daily budget of {cfg.daily_budget} requests already spent")
    client.max_requests = min(original_max, client.requests_made + headroom)

    game_version = client.wiki_current_version()
    plan = Plan()
    counts = res.counts
    warnings = res.warnings
    if use_feed:
        assert cursor_ts is not None
        extra = _collect_events(client, store, cfg, cursor_ts, ns_ids, plan, counts, warnings)
        for reason in extra:
            if reason not in sweep_reasons:
                sweep_reasons.append(reason)
        sweep = sweep or bool(extra)
    if sweep:
        _plan_sweep(client, store, cfg, ns_ids, plan, counts)
    res.sweep, res.sweep_reasons = sweep, list(sweep_reasons)
    res.plan = {
        "fetch_titles": [i.title for i in plan.fetch.values()],
        "deletes": sorted(plan.deletes),
        "sweep_absent": sorted(plan.sweep_absent.values()),
    }
    if cfg.dry_run:
        return

    # 5. Fetch every body first: a network failure here writes nothing.
    revs: list[PageRevision] = []
    missing: list[Any] = []
    titles = [i.title for i in plan.fetch.values()]
    if titles:
        fetched = client.fetch_revisions(titles=titles)
        revs, missing = list(fetched.revisions), list(fetched.missing)
    res.pages_fetched = len(revs)

    # 6. The text stage (pure). Redirects need no text.
    pages_text: dict[int, Any] = {}
    for rev in revs:
        if rev.is_redirect or rev.ns not in ns_ids:
            continue
        kw: dict[str, Any] = {"max_chunk_chars": cfg.max_chunk_chars}
        if cfg.text_policy is not None:
            kw["policy"] = cfg.text_policy
        pt = extract(rev.wikitext, **kw)
        pages_text[rev.page_id] = pt
        for name, n in pt.unlisted_templates.items():
            _bump(res.unlisted_templates, name, n)
        for reason in pt.degraded_reasons:
            _bump(res.degraded_reasons, reason.split(":")[0])

    # 7. One transaction. The cursor moves in the same commit as the data.
    assert run_id is not None
    now_s = iso(store.now())
    cursor_to = cursor_ts
    with store.transaction():
        _apply(store, plan, revs, missing, pages_text, run_id=run_id, game_version=game_version,
               ns_ids=ns_ids, counts=counts, warnings=warnings, extras=extras)
        _record_version(store, run_id, game_version, now_s, warnings, seq=10**6)
        if plan.redirects is not None:
            _refresh_redirects(store, plan.redirects, ns_ids, counts)
        if use_feed:
            if plan.newest_ts and (cursor_ts is None or plan.newest_ts > cursor_ts):
                cursor_to = plan.newest_ts
            ids_floor = iso(parse_iso(cursor_to) - cfg.overlap) if cursor_to else None
            keep = sorted({ident for ts, ident in plan.seen_ids if ids_floor and ts >= ids_floor})
            store.set_meta(META_CURSOR_IDS, json.dumps(keep))
        else:
            # A sweep-only run saw the whole current state; the feed resumes from here.
            cursor_to = iso(now)
            store.set_meta(META_CURSOR_IDS, "[]")
        if cursor_to:
            store.set_meta(META_CURSOR_TS, cursor_to)
        if sweep:
            store.set_meta(META_LAST_SWEEP, iso(now))
    res.cursor_to = cursor_to
    if counts.get("sweep_found") and use_feed:
        warnings.append(f"sweep_found_changes_the_feed_missed:{counts['sweep_found']}")


def _write_outputs(store: Store, cfg: RefreshConfig, res: RefreshResult, run_id: str,
                   extras: dict[int, dict[str, Any]]) -> None:
    if cfg.out_dir is None:
        return
    errors: list[str] = []
    try:
        path = changelog.export_run(store, run_id, cfg.out_dir, summary=res.summary(),
                                    promotions=res.promotions, extras=extras, cited_by=cfg.cited_by)
        res.changelog_path = str(path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"changelog_failed: {type(exc).__name__}: {exc}")
    try:
        now = store.now()
        changed = bool(res.promotions) or bool(
            store.conn.execute("SELECT 1 FROM changes WHERE run_id = ? LIMIT 1", (run_id,)).fetchone()
        )
        loud = [w for w in res.warnings if w != "install_version_unset"]
        if digest.digest_due(store, changed=changed, failed=res.status != "ok" or bool(loud), now=now):
            since = iso(now.replace(hour=0, minute=0, second=0, microsecond=0))
            flags = list(cfg.doctrine_flags()) if cfg.doctrine_flags else None
            text = digest.render_digest(store, since_utc=since, now=now, doctrine_flags=flags,
                                        warnings=res.warnings)
            res.digest_path = str(digest.write_digest(text, cfg.out_dir, now))
            store.set_meta(META_LAST_DIGEST, iso(now))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"digest_failed: {type(exc).__name__}: {exc}")
    if errors:
        # The data is committed; the record of it is not. Say so on the run row.
        res.status = "failed"
        res.error_class = res.error_class or "output_failed"
        res.error_detail = "; ".join(errors)
        res.warnings.extend(errors)
        store.finish_run(run_id, "failed", requests=res.requests, pages_fetched=res.pages_fetched,
                         cursor_to=res.cursor_to, error_class=res.error_class,
                         error_detail=res.error_detail[:1000])


# ---- command line -----------------------------------------------------------


def main(argv: list[str] | None = None, *, client: WikiClient | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m wikimirror.refresh", description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True, help="path to the mirror database (must already exist)")
    ap.add_argument("--out", help="directory holding changelog/ and digest/ (default: none written)")
    ap.add_argument("--budget", type=int, default=400, help="max API requests this run (default 400)")
    ap.add_argument("--daily-budget", type=int, default=2000)
    ap.add_argument("--force-sweep", action="store_true", help="also run the full revid sweep")
    ap.add_argument("--dry-run", action="store_true", help="read the feed and listing, print the plan, write nothing")
    ap.add_argument("--hold-days", type=int, default=7, help="hold in days (default 7; a ruling, change deliberately)")
    args = ap.parse_args(argv)

    if client is None and not os.environ.get("DFWIKI_UA_CONTACT"):
        print("refresh refused: DFWIKI_UA_CONTACT is not set (the wiki asks bots to identify a contact)", file=sys.stderr)
        return 2
    if not Path(args.db).exists():
        print(f"refresh refused: {args.db} does not exist; run the pull first", file=sys.stderr)
        return 2
    cfg = RefreshConfig(daily_budget=args.daily_budget, force_sweep=args.force_sweep,
                        dry_run=args.dry_run, out_dir=args.out)
    if client is None:
        client = WikiClient(max_requests=args.budget)
    store = Store.open(args.db, create=False, hold=timedelta(days=args.hold_days))
    try:
        res = run_refresh(store, client, cfg)
    finally:
        store.close()
    print(json.dumps({"status": res.status, "run_id": res.run_id, "mode": res.mode,
                      "requests": res.requests, "error_class": res.error_class,
                      "error_detail": res.error_detail, **res.summary(),
                      "changelog": res.changelog_path, "digest": res.digest_path,
                      **({"plan": res.plan} if res.plan and args.dry_run else {})}, indent=2))
    return 0 if res.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
