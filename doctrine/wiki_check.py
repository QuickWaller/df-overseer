"""Read-only check of doctrine's wiki citations against the wiki mirror.

`docs/CONSULTANT-WIKI.md` section 7 (the doctrine link) as amended by section
13 (the one-week hold). A doctrine source of `kind: wiki` may carry a `revid`
(the wiki revision that was read). This module compares that revision with
what the mirror SERVES and reports, per cited page, whether it moved on. It
never edits doctrine: a revision to an entry is a proposal (7.5), and a flag
clears only when a person or the Architect/Overseer path sets a new `revid`.

Served, never latest seen (section 13). Under the hold, the mirror keeps a
served revision and, apart from it, the latest revision it has merely seen.
Readers join on the served one. This check does the same, so "changed" means
"readers now see a different revision than the one the doctrine was written
from". A newer revision that is held but not yet served is reported
separately (`held_newer`) so a re-read can be planned before it goes live.

Silent degradation is the enemy: when the mirror cannot answer (missing file,
locked, unreadable, no successful pull, very stale) a source is reported
`cannot_check` with a reason. It is never reported `unchanged` on the strength
of a mirror that could not tell.

Mirror access is through `wikimirror.store.Store`'s public read helpers only
(`get_page`, `staleness`, `changes_since`, `namespaces`, plus a plain SELECT on
`revision_archive`, for which the store has no getter yet: recorded in the S6
handoff Result). Nothing here writes, opens read-write or touches the network.

The report (`check_doctrine`) is a plain JSON-able dict, the shape S7 consumes:

    {
      "mirror": {"available": bool, "reason": str | None,
                 "freshness": {"status", "age_hours", "reasons",
                               "promotion_overdue"} | None},
      "summary": {<state>: count, ...},          # every state, zero included
      "sources": [<source result>, ...],         # cited sources only
      "uncited": [{"entry_id", "source_index", "ref", "read"}],
      "flags_by_entry": {<entry id>: [<flag>, ...]},   # what doctrine.get attaches
      "needing_reread": [<entry id>, ...],       # digest list, sorted
    }

A source result: entry_id, entry_status, source_index, ref, title, ns,
cited_revid, state, severity, served_revid, latest_revid, held_changes,
held_kinds, newer_held_revid, visible_after, moved_to, page_id,
cited_revision_archived (True/False/None), reason, message.

States: unchanged, changed, held_newer, moved, deleted, legacy, missing,
cannot_check. A flag (the `wiki_flags` item S7 attaches at `doctrine.get`
time) is a source result minus the bookkeeping, present for every state but
`unchanged`; its `severity` is `reread` (changed, moved, deleted), `warn`
(held_newer, legacy, missing), `info` (cannot_check), and drops to `note` for
a `verified` entry whose evidence is game data (7.2).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

STATES = (
    "unchanged",
    "changed",
    "held_newer",
    "moved",
    "deleted",
    "legacy",
    "missing",
    "cannot_check",
)

# A very stale mirror cannot vouch for "unchanged". Anything the mirror still
# says positively (changed, deleted, ...) stays true however old the copy is.
UNTRUSTWORTHY_FRESHNESS = {"very_stale"}

_SEVERITY = {
    "changed": "reread",
    "moved": "reread",
    "deleted": "reread",
    "held_newer": "warn",
    "legacy": "warn",
    "missing": "warn",
    "cannot_check": "info",
}

_REREAD_STATES = {"changed", "moved", "deleted", "held_newer"}


def _served_revid(view: dict[str, Any]) -> int | None:
    """The revision readers are served. NEVER `latest_revid` (section 13)."""
    return view.get("revid")


def _is_pos_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def cited_title(source: dict[str, Any]) -> str:
    return str(source.get("page_title") or source.get("ref") or "").strip()


def cited_ns(source: dict[str, Any]) -> int:
    ns = source.get("page_ns", 0)
    return ns if isinstance(ns, int) and not isinstance(ns, bool) else 0


# ---- the archive (7.3) -----------------------------------------------------------


def read_archived_revision(reader: Any, page_id: int, revid: int) -> dict[str, Any] | None:
    """The archived body of (page, revision), or None if it is not archived.

    A plain SELECT through the store's connection: `revision_archive` has no
    public getter. Returns {"page_id", "revid", "sha256", "wikitext",
    "archived_utc", "intact"}, where `intact` is whether the stored sha256
    matches the stored text.
    """
    conn = getattr(reader, "conn", None)
    if conn is None:
        return None
    row = conn.execute(
        "SELECT page_id, revid, sha256, wikitext, archived_utc FROM revision_archive "
        "WHERE page_id = ? AND revid = ?",
        (page_id, revid),
    ).fetchone()
    if row is None:
        return None
    text = row[3]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None
    return {
        "page_id": row[0],
        "revid": row[1],
        "sha256": row[2],
        "wikitext": text,
        "archived_utc": row[4],
        "intact": text is not None and digest == row[2],
    }


def check_archive(reader: Any, page_id: int, cited_revid: int) -> dict[str, Any]:
    """Section 7.3: the check that a cited page's prior body was archived before
    the served revision changed.

    Call it for a cited page whose served revision is no longer the cited one.
    `archived` is True only if the exact cited revision is in `revision_archive`
    and its bytes still match their hash. A False here means the body a doctrine
    entry was written from is gone: the refresh job failed to call
    `Store.archive_served_revision` for a cited page before promotion.
    """
    got = read_archived_revision(reader, page_id, cited_revid)
    if got is None:
        return {"archived": False, "intact": False, "archived_utc": None}
    return {"archived": True, "intact": got["intact"], "archived_utc": got["archived_utc"]}


def cited_page_ids(entries: Iterable[Any], reader: Any) -> set[int]:
    """Page ids of every page a doctrine wiki source with a `revid` cites, for the
    refresh job's "is this page cited" test before it archives a served body (7.3).
    Pages the mirror cannot resolve are simply absent."""
    out: set[int] = set()
    for _entry, _i, source in _wiki_sources(entries):
        if not _is_pos_int(source.get("revid")):
            continue
        try:
            view = reader.get_page(cited_title(source), ns=cited_ns(source), include_legacy=True)
        except Exception:  # noqa: BLE001 - an unresolvable title is just not cited-and-found
            continue
        if view is not None and view.get("page_id") is not None:
            out.add(view["page_id"])
    return out


# ---- the check ---------------------------------------------------------------------


def _wiki_sources(entries: Iterable[Any]) -> Iterable[tuple[dict, int, dict]]:
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        sources = entry.get("sources")
        if not isinstance(sources, list):
            continue
        for index, source in enumerate(sources):
            if isinstance(source, dict) and source.get("kind") == "wiki":
                yield entry, index, source


def _result(entry: dict, index: int, source: dict, state: str, **extra: Any) -> dict[str, Any]:
    res: dict[str, Any] = {
        "entry_id": entry.get("id"),
        "entry_status": entry.get("status"),
        "source_index": index,
        "ref": source.get("ref"),
        "title": cited_title(source),
        "ns": cited_ns(source),
        "cited_revid": source.get("revid"),
        "state": state,
        "severity": _SEVERITY.get(state),
        "served_revid": None,
        "latest_revid": None,
        "held_changes": 0,
        "held_kinds": [],
        "newer_held_revid": None,
        "visible_after": None,
        "moved_to": None,
        "page_id": None,
        "cited_revision_archived": None,
        "reason": None,
        "message": None,
    }
    res.update(extra)
    if res["severity"] and entry.get("status") == "verified" and state in _REREAD_STATES:
        # 7.2: a verified entry's evidence is game data; the wiki page is context.
        res["severity"] = "note"
    res["message"] = res["message"] or _message(res)
    return res


def _message(r: dict[str, Any]) -> str | None:
    state, title, cited = r["state"], r["title"], r["cited_revid"]
    if state == "unchanged":
        return None
    if state == "changed":
        return (
            f"cited wiki page {title!r} changed since revision {cited} "
            f"(now serving {r['served_revid']}); re-read before relying on this"
        )
    if state == "held_newer":
        return (
            f"a newer revision {r['newer_held_revid']} of cited wiki page {title!r} is held "
            f"and goes live after {r['visible_after']}; plan a re-read of revision {cited}"
        )
    if state == "moved":
        return (
            f"cited wiki page {title!r} now lives under {r['moved_to']!r}; "
            "re-read before relying on this"
        )
    if state == "deleted":
        return f"cited wiki page {title!r} was deleted; the cited evidence is gone"
    if state == "legacy":
        return (
            f"cited wiki page {title!r} is in a legacy (older game) namespace; "
            "it says nothing reliable about this install"
        )
    if state == "missing":
        return f"cited wiki page {title!r} is not in the mirror"
    if state == "cannot_check":
        return f"cannot check cited wiki page {title!r}: {r['reason']}"
    return None


def _held_info(reader: Any, view: dict[str, Any], served: int | None) -> dict[str, Any]:
    held = int(view.get("held_changes") or 0)
    latest = view.get("latest_revid")
    kinds: list[str] = []
    if held:
        fn = getattr(reader, "changes_since", None)
        if fn is not None:
            try:
                kinds = sorted({c["kind"] for c in fn(title=view.get("title"), state="held")})
            except Exception:  # noqa: BLE001 - kinds are decoration; the count is the fact
                kinds = []
    newer = latest if held and _is_pos_int(latest) and (served is None or latest > served) else None
    return {
        "held_changes": held,
        "held_kinds": kinds,
        "latest_revid": latest,
        "newer_held_revid": newer,
        "visible_after": view.get("visible_after"),
    }


def _archive_fields(
    reader: Any, view: dict, cited: int, served: int | None, *, gone: bool = False
) -> dict[str, Any]:
    """`gone`: the served body is no longer readable (a tombstone), so even a
    matching revid needs its archived body."""
    if (served == cited and not gone) or view.get("page_id") is None:
        return {}
    got = check_archive(reader, view["page_id"], cited)
    return {"cited_revision_archived": bool(got["archived"] and got["intact"])}


def _check_source(entry: dict, index: int, source: dict, reader: Any, stale: bool) -> dict[str, Any]:
    title, ns, cited = cited_title(source), cited_ns(source), source["revid"]
    if not title:
        return _result(entry, index, source, "cannot_check", reason="no_title_to_look_up")

    rules = getattr(reader, "namespaces", None) or {}
    rule = rules.get(ns) if isinstance(rules, dict) else None
    if rule is not None and not getattr(rule, "is_current", 1):
        return _result(entry, index, source, "legacy", reason="legacy_namespace")

    try:
        view = reader.get_page(title, ns=ns, include_legacy=True)
    except Exception as exc:  # noqa: BLE001 - any read failure is "cannot tell", said out loud
        return _result(
            entry, index, source, "cannot_check", reason=f"mirror_read_failed: {type(exc).__name__}: {exc}"
        )
    if view is None:
        return _result(entry, index, source, "missing", reason="page_not_in_mirror")

    served = _served_revid(view)
    held = _held_info(reader, view, served)
    base = dict(page_id=view.get("page_id"), served_revid=served, **held)

    if view.get("state") == "deleted":
        return _result(entry, index, source, "deleted", reason="tombstone",
                       **base, **_archive_fields(reader, view, cited, served, gone=True))
    if not view.get("is_current", True):
        return _result(entry, index, source, "legacy", reason="legacy_page", **base)
    if view.get("resolved_from"):
        return _result(entry, index, source, "moved", moved_to=view.get("title"),
                       reason="title_resolves_elsewhere",
                       **base, **_archive_fields(reader, view, cited, served))
    if served is None:
        return _result(entry, index, source, "cannot_check", reason="mirror_has_no_served_revision", **base)
    if served > cited:
        return _result(entry, index, source, "changed", reason="served_revision_newer",
                       **base, **_archive_fields(reader, view, cited, served))
    if served < cited:
        # The doctrine was written from a revision the mirror does not serve yet
        # (read live, or still inside the hold). Not "unchanged": we cannot tell.
        return _result(entry, index, source, "cannot_check", reason="cited_revision_not_yet_served", **base)
    if held["newer_held_revid"] is not None:
        return _result(entry, index, source, "held_newer", reason="newer_revision_held", **base)
    if stale:
        return _result(entry, index, source, "cannot_check", reason="mirror_very_stale", **base)
    return _result(entry, index, source, "unchanged", **base)


def _open_reader(store_reader: Any) -> tuple[Any, str | None, bool]:
    """(reader, unavailable_reason, opened_here). A path is opened read-only."""
    if store_reader is None:
        return None, "no_mirror_configured", False
    if isinstance(store_reader, (str, Path)):
        from wikimirror.schema import SchemaError
        from wikimirror.store import Store, StoreError

        try:
            return Store.open_readonly(store_reader), None, True
        except (StoreError, SchemaError, sqlite3.Error, OSError) as exc:
            return None, f"mirror_unavailable: {type(exc).__name__}: {exc}", False
    return store_reader, None, False


def _freshness(reader: Any) -> tuple[dict[str, Any] | None, str | None]:
    try:
        s = reader.staleness()
    except Exception as exc:  # noqa: BLE001
        return None, f"mirror_freshness_unreadable: {type(exc).__name__}: {exc}"
    return {
        "status": s.get("status"),
        "age_hours": s.get("age_hours"),
        "reasons": list(s.get("reasons") or []),
        "promotion_overdue": s.get("promotion_overdue", 0),
    }, None


def check_doctrine(doctrine_entries: Iterable[Any], store_reader: Any) -> dict[str, Any]:
    """Compare every cited wiki source with the mirror's SERVED revision.

    `doctrine_entries` is the parsed doctrine list. `store_reader` is an open
    `wikimirror.store.Store` (or anything with the same read helpers), a
    path (opened read-only here and closed after), or None. Read-only; never
    edits doctrine; never raises for a mirror problem: those become
    `cannot_check` results.
    """
    entries = list(doctrine_entries or [])
    reader, unavailable, opened_here = _open_reader(store_reader)
    try:
        freshness = None
        if reader is not None:
            freshness, fresh_err = _freshness(reader)
            if fresh_err:
                unavailable = fresh_err
        stale = bool(
            freshness
            and (
                freshness["status"] in UNTRUSTWORTHY_FRESHNESS
                or "never_pulled" in freshness["reasons"]
            )
        )

        sources: list[dict[str, Any]] = []
        uncited: list[dict[str, Any]] = []
        for entry, index, source in _wiki_sources(entries):
            if not _is_pos_int(source.get("revid")):
                uncited.append(
                    {
                        "entry_id": entry.get("id"),
                        "source_index": index,
                        "ref": source.get("ref"),
                        "read": source.get("read"),
                    }
                )
                continue
            if reader is None or unavailable:
                sources.append(_result(entry, index, source, "cannot_check", reason=unavailable))
            else:
                sources.append(_check_source(entry, index, source, reader, stale))
    finally:
        if opened_here:
            reader.close()

    summary = {s: 0 for s in STATES}
    for r in sources:
        summary[r["state"]] += 1
    flags: dict[str, list[dict[str, Any]]] = {}
    for r in sources:
        if r["state"] != "unchanged":
            flags.setdefault(r["entry_id"], []).append(_flag(r))
    rereads = sorted(
        {r["entry_id"] for r in sources if r["state"] in _REREAD_STATES and r["severity"] != "note"}
    )
    return {
        "mirror": {"available": unavailable is None, "reason": unavailable, "freshness": freshness},
        "summary": summary,
        "sources": sources,
        "uncited": uncited,
        "flags_by_entry": flags,
        "needing_reread": rereads,
    }


_FLAG_KEYS = (
    "source_index", "ref", "title", "ns", "cited_revid", "state", "severity", "served_revid",
    "newer_held_revid", "visible_after", "moved_to", "held_kinds", "cited_revision_archived",
    "reason", "message",
)


def _flag(result: dict[str, Any]) -> dict[str, Any]:
    return {k: result[k] for k in _FLAG_KEYS}


def wiki_flags_for_entry(entry: dict[str, Any], store_reader: Any) -> list[dict[str, Any]]:
    """The `wiki_flags` list S7 attaches to one entry at `doctrine.get` time.

    Empty when every cited source is unchanged (or the entry cites no revision).
    Computed from the live mirror on every call: no stored state, so it cannot
    go stale. `cannot_check` flags are included (severity `info`) so a dead
    mirror is visible at the point of use, not silently treated as fine.
    """
    report = check_doctrine([entry], store_reader)
    return report["flags_by_entry"].get(entry.get("id"), [])


# ---- CLI ---------------------------------------------------------------------------


def render_text(report: dict[str, Any]) -> str:
    lines = []
    m = report["mirror"]
    lines.append(
        "mirror: "
        + ("available" if m["available"] else f"UNAVAILABLE ({m['reason']})")
        + (f", freshness {m['freshness']['status']}" if m["freshness"] else "")
    )
    lines.append("summary: " + ", ".join(f"{k}={v}" for k, v in report["summary"].items() if v))
    for r in report["sources"]:
        if r["state"] != "unchanged":
            lines.append(f"  [{r['severity']}] {r['entry_id']}: {r['message']}")
    if report["uncited"]:
        lines.append(f"uncited wiki sources (no revid): {len(report['uncited'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from doctrine.validate import DEFAULT_PATH

    ap = argparse.ArgumentParser(description="Check doctrine wiki citations against the mirror.")
    ap.add_argument("--db", required=True, help="path to the wiki mirror SQLite file")
    ap.add_argument("--doctrine", default=str(DEFAULT_PATH))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    with open(args.doctrine, "r", encoding="utf-8") as fh:
        entries = yaml.safe_load(fh) or []
    report = check_doctrine(entries, args.db)
    print(json.dumps(report, indent=2, default=str) if args.json else render_text(report))
    # Exit 1 when anything needs attention or could not be checked; 0 when all clear.
    bad = report["needing_reread"] or report["summary"]["cannot_check"] or not report["mirror"]["available"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
