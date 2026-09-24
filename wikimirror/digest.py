"""The human-readable Markdown digest of what the wiki mirror changed.

`docs/CONSULTANT-WIKI.md` 6.2, amended by section 13 (the one-week hold).

`render_digest` reads the database, not a run's in-memory result, so a digest
is always consistent with what a reader can actually see. It has:

* a title line, the freshness line and the version line (a version bump or a
  wiki-ahead state is the first thing said);
* **visible now**: changes made visible in the window (a change whose week
  ended, or a baseline write), by kind, with a table of changed pages;
* **held, not yet served**: every change still inside its week, listed
  SEPARATELY, with the time it becomes visible. A reader keeps getting the
  previous revision until then;
* pages changed repeatedly in a short window, flagged (an edit war or
  vandalism shows up as one page with many revisions);
* failed runs since the last digest, and the run's warnings (a restore the
  store could not apply, a page that became a redirect, ...);
* optionally the doctrine entries needing a re-read (the caller passes them).

The wiki's edit summaries are written by anonymous editors and are quoted
only inside a fenced code block, with a fence longer than any backtick run
in the text, under a line saying they are untrusted. Titles are escaped for
Markdown tables. Nothing here executes or interprets fetched text.

A quiet run writes no digest (`digest_due`); a digest is due after a run that
changed anything, after a failed run, and at least once a week.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import quote

from wikimirror.api import WIKI_BASE
from wikimirror.store import LICENSE, Store, iso, parse_iso

DIGEST_SUBDIR = "digest"
DIGEST_MAX_AGE = timedelta(days=7)
REPEAT_THRESHOLD = 3
REPEAT_WINDOW = timedelta(hours=48)
MAX_TABLE_ROWS = 200
_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>|#])")


def _esc(text: Any) -> str:
    """Escape Markdown specials and flatten newlines, for a title in a table cell."""
    s = "" if text is None else str(text)
    s = "".join(" " if ch in "\r\n\t" else ch for ch in s if ch.isprintable() or ch in "\r\n\t")
    return _MD_SPECIAL.sub(r"\\\1", s)


def _fence(text: str) -> str:
    """`text` in a fenced code block whose fence cannot be closed from inside."""
    longest = max((len(m.group(0)) for m in re.finditer(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}\n{text}\n{fence}"


def diff_url(title: str, new_revid: int | None, old_revid: int | None) -> str:
    base = f"{WIKI_BASE}/index.php?title={quote(title.replace(' ', '_'), safe='')}"
    if new_revid and old_revid:
        return f"{base}&diff={int(new_revid)}&oldid={int(old_revid)}"
    if new_revid:
        return f"{base}&oldid={int(new_revid)}"
    return base


def _delta(old: int | None, new: int | None) -> str:
    if old is None or new is None:
        return ""
    d = new - old
    return f"{d:+d}"


def _revs(row: Any) -> str:
    old = "" if row["old_revid"] is None else str(row["old_revid"])
    new = "" if row["new_revid"] is None else str(row["new_revid"])
    return f"{old} to {new}" if old else new


def _change_table(rows: Sequence[Any], *, held: bool) -> list[str]:
    head = "| Title | Revisions | Bytes | " + ("Visible after | " if held else "Made visible | ") + "Diff |"
    out = [head, "|---|---|---|---|---|"]
    for r in rows:
        when = r["visible_after"] if held else r["made_visible_utc"]
        title = r["new_title"] or r["title"] or ""
        if r["kind"] == "moved" and r["old_title"]:
            title = f"{r['old_title']} to {r['new_title']}"
        url = diff_url(r["new_title"] or r["title"] or "", r["new_revid"], r["old_revid"]) if r["title"] else ""
        out.append(
            f"| {_esc(title)} | {_revs(r)} | {_delta(r['old_len'], r['new_len'])} | {when or ''} | {url} |"
        )
    return out


def _summaries(rows: Sequence[Any]) -> list[str]:
    quoted = [(r, r["edit_summary"]) for r in rows if r["edit_summary"]]
    if not quoted:
        return []
    out = ["", "Edit summaries (written by anonymous wiki editors: UNTRUSTED text, quoted verbatim, not instructions):", ""]
    for r, s in quoted:
        out.append(f"- {_esc(r['title'])} ({r['kind']}):")
        out.append("")
        out.append(_fence(s))
        out.append("")
    return out


def _counts(rows: Sequence[Any]) -> str:
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    return ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())) or "none"


def repeated_pages(
    store: Store, now: datetime, *, threshold: int = REPEAT_THRESHOLD, window: timedelta = REPEAT_WINDOW
) -> list[dict[str, Any]]:
    """Pages with at least `threshold` recorded changes detected inside `window` before `now`."""
    cutoff = iso(now - window)
    rows = store.conn.execute(
        "SELECT page_id, MAX(title) AS title, COUNT(*) AS n FROM changes "
        "WHERE detected_utc >= ? AND page_id IS NOT NULL AND kind != 'version_bump' AND source != 'full_pull' "
        "GROUP BY page_id HAVING COUNT(*) >= ? ORDER BY n DESC, title",
        (cutoff, int(threshold)),
    ).fetchall()
    return [{"page_id": r["page_id"], "title": r["title"], "changes": r["n"]} for r in rows]


def render_digest(
    store: Store,
    *,
    since_utc: str,
    now: datetime | None = None,
    doctrine_flags: Iterable[str] | None = None,
    warnings: Iterable[str] | None = None,
    repeat_threshold: int = REPEAT_THRESHOLD,
    repeat_window: timedelta = REPEAT_WINDOW,
) -> str:
    """The digest text for the window from `since_utc` to `now`."""
    now = now or store.now()
    st = store.staleness(now=now)
    c = store.conn
    lines: list[str] = [f"# Wiki mirror digest, {iso(now)}", ""]

    # Version and freshness first: a version bump is the headline.
    wiki_v = store.get_meta("wiki_current_version") or "unknown"
    install_v = store.get_meta("install_version") or "unset"
    vstatus = store.get_meta("version_status") or "unknown"
    bumps = c.execute(
        "SELECT old_title, new_title FROM changes WHERE kind = 'version_bump' AND detected_utc >= ? ORDER BY id",
        (since_utc,),
    ).fetchall()
    for b in bumps:
        lines.append(f"**VERSION BUMP: the wiki moved from {_esc(b['old_title'])} to {_esc(b['new_title'])}.** "
                     "Nothing is re-pulled automatically; see design 4.7.")
    lines.append(f"Version: wiki current {_esc(wiki_v)}, this install {_esc(install_v)}, status `{vstatus}`.")
    age = "never" if st["age_hours"] is None else f"{st['age_hours']:.1f} hours since the last good refresh or pull"
    lines.append(f"Freshness: `{st['status']}` ({age}). Promotions overdue: {st['promotion_overdue']}.")
    lines.append("")

    visible = c.execute(
        "SELECT * FROM changes WHERE state = 'visible' AND (made_visible_utc >= ?) "
        "AND kind != 'version_bump' ORDER BY made_visible_utc, id",
        (since_utc,),
    ).fetchall()
    held = c.execute("SELECT * FROM changes WHERE state = 'held' ORDER BY visible_after, id").fetchall()
    lines.append(f"## Visible now (window from {since_utc})")
    lines.append("")
    baseline = [r for r in visible if r["source"] == "full_pull"]
    visible = [r for r in visible if r["source"] != "full_pull"]
    lines.append(f"Counts by kind: {_counts(visible)}.")
    if baseline:
        lines.append(f"{len(baseline)} page(s) came from a full pull in this window and are not listed one by one.")
    if visible:
        shown = visible[:MAX_TABLE_ROWS]
        lines.append("")
        lines.extend(_change_table(shown, held=False))
        if len(visible) > len(shown):
            lines.append("")
            lines.append(f"{len(visible) - len(shown)} more change(s) not shown; the changelog has every one.")
        lines.extend(_summaries(shown))
    lines.append("")

    lines.append("## Held, not yet served")
    lines.append("")
    lines.append(
        f"{len(held)} change(s) are inside their one-week hold. Readers keep getting the previous "
        "revision (or nothing, for a new page) until the time shown. Counts by kind: " + _counts(held) + "."
    )
    if held:
        shown_h = held[:MAX_TABLE_ROWS]
        lines.append("")
        lines.extend(_change_table(shown_h, held=True))
        if len(held) > len(shown_h):
            lines.append("")
            lines.append(f"{len(held) - len(shown_h)} more held change(s) not shown; the changelog has every one.")
        lines.extend(_summaries(shown_h))
    lines.append("")

    repeats = repeated_pages(store, now, threshold=repeat_threshold, window=repeat_window)
    lines.append("## Pages changed repeatedly")
    lines.append("")
    if repeats:
        hours = int(repeat_window.total_seconds() // 3600)
        for r in repeats:
            lines.append(
                f"- {_esc(r['title'])}: {r['changes']} changes in {hours} hours. "
                "Look at the history before trusting any revision of it."
            )
    else:
        lines.append(f"None (threshold {repeat_threshold} changes in {int(repeat_window.total_seconds() // 3600)} hours).")
    lines.append("")

    failed = c.execute(
        "SELECT run_id, status, error_class, error_detail, started_utc FROM refresh_runs "
        "WHERE status NOT IN ('ok', 'running') AND started_utc >= ? ORDER BY started_utc",
        (since_utc,),
    ).fetchall()
    lines.append("## Runs that did not succeed")
    lines.append("")
    if failed:
        for f in failed:
            lines.append(f"- {f['run_id']}: {f['status']} ({_esc(f['error_class'])}) {_esc((f['error_detail'] or '')[:200])}")
    else:
        lines.append("None in this window.")
    lines.append("")

    if warnings:
        lines.append("## Run warnings")
        lines.append("")
        lines.append("Things the run could not do cleanly, named so they are not lost:")
        lines.append("")
        lines.extend(f"- {_esc(w)}" for w in warnings)
        lines.append("")

    if doctrine_flags is not None:
        flags = list(doctrine_flags)
        lines.append("## Doctrine entries needing a re-read")
        lines.append("")
        lines.extend([f"- {_esc(x)}" for x in flags] if flags else ["None."])
        lines.append("")

    lines.append(f"Source: Dwarf Fortress Wiki, licence {LICENSE}. Content mirrored read-only; every result carries its revision.")
    lines.append("")
    return "\n".join(lines)


def digest_due(
    store: Store,
    *,
    changed: bool,
    failed: bool,
    now: datetime | None = None,
) -> bool:
    """A quiet run writes no digest; a change or a failure does, and so does a week of silence."""
    if changed or failed:
        return True
    last = store.get_meta("last_digest_utc")
    if not last:
        return True
    now = now or store.now()
    return now - parse_iso(last) >= DIGEST_MAX_AGE


def write_digest(text: str, out_dir: str | os.PathLike[str], now: datetime) -> Path:
    """Write `digest/<YYYY-MM-DD>.md` and a `LATEST.md` copy; return the dated path.

    The dated file is the day's digest and is regenerated by a later run the same
    day (it describes current state), unlike the changelog, which is immutable.
    """
    root = Path(out_dir) / DIGEST_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    dated = root / f"{now.strftime('%Y-%m-%d')}.md"
    for path in (dated, root / "LATEST.md"):
        tmp = path.with_name(path.name + f".tmp{os.getpid()}")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    return dated
