"""The immutable, append-only JSONL changelog of the wiki mirror.

`docs/CONSULTANT-WIKI.md` 6.1, amended by section 13 (the one-week hold).

One file per refresh run, `changelog/<YYYY>/<MM>/<run_id>.jsonl`:

* line 1 is the run header (`"record": "run"`);
* one `"record": "change"` line per change the run recorded (added, changed,
  moved, deleted, restored, version_bump), each carrying its `state`
  (`held` or `visible`) and `visible_after`;
* one `"record": "visible"` line per held change this run made visible
  (promoted after its week). The change line itself is never rewritten: the
  file of the run that fetched it says `held` for ever, and the transition is
  a NEW line in the file of the run that promoted it;
* a last `"record": "end"` line with the record count, so a truncated file is
  detectable.

A file is written once. `export_run` refuses to touch an existing file
(`ChangelogExistsError`), writes through a temporary name and links it into
place, so a crash leaves either no file or a whole one, never a half file
under the final name. Nothing here ever opens a file for append or rewrite.

The wiki's own edit summary is copied verbatim (the store already strips
control characters and bounds it at 500 characters) and every change line
carries `"edit_summary_untrusted": true`: any anonymous editor writes it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from wikimirror.store import Store

CHANGELOG_SUBDIR = "changelog"


class ChangelogError(RuntimeError):
    """Base class for changelog problems."""


class ChangelogExistsError(ChangelogError):
    """The run's changelog file already exists; it is immutable and was not touched."""


class ChangelogFormatError(ChangelogError):
    """A file is not a well-formed changelog (bad JSON, no header, no end record)."""


def run_path(out_dir: str | os.PathLike[str], run_id: str, started_utc: str) -> Path:
    """`<out_dir>/changelog/<YYYY>/<MM>/<run_id>.jsonl`, dated by the run's start."""
    year, month = started_utc[0:4], started_utc[5:7]
    if not (year.isdigit() and month.isdigit()):
        raise ChangelogError(f"unreadable started_utc {started_utc!r}")
    return Path(out_dir) / CHANGELOG_SUBDIR / year / month / f"{run_id}.jsonl"


def _line(obj: Mapping[str, Any]) -> str:
    # ensure_ascii keeps every record on one physical line whatever the text holds.
    return json.dumps(obj, ensure_ascii=True, separators=(",", ":"))


def _run_row(store: Store, run_id: str) -> dict[str, Any]:
    row = store.conn.execute("SELECT * FROM refresh_runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise ChangelogError(f"unknown run {run_id!r}")
    return dict(row)


def build_records(
    store: Store,
    run_id: str,
    *,
    summary: Mapping[str, Any] | None = None,
    promotions: Sequence[Any] = (),
    extras: Mapping[int, Mapping[str, Any]] | None = None,
    cited_by: Any = None,
) -> list[dict[str, Any]]:
    """The records of one run, in file order (header, changes, visible, end).

    `summary`     merged into the header under `summary` (counts, degraded
                  reasons, unlisted templates, warnings).
    `promotions`  `store.Promotion` objects made visible by this run.
    `extras`      per change id extra fields (the delete `reason`).
    `cited_by`    optional `callable(page_id) -> list[str]`; when given, each
                  change line carries `cited_by` (doctrine entries citing the page).
    """
    run = _run_row(store, run_id)
    errors = []
    if run["error_class"]:
        errors.append({"class": run["error_class"], "detail": run["error_detail"]})
    header: dict[str, Any] = {
        "record": "run",
        "run_id": run["run_id"],
        "mode": run["mode"],
        "started_utc": run["started_utc"],
        "finished_utc": run["finished_utc"],
        "status": run["status"],
        "requests": run["requests"],
        "pages_fetched": run["pages_fetched"],
        "cursor_from": run["cursor_from"],
        "cursor_to": run["cursor_to"],
        "wiki_current_version": store.get_meta("wiki_current_version"),
        "install_version": store.get_meta("install_version"),
        "errors": errors,
    }
    if summary:
        header["summary"] = dict(summary)
    records: list[dict[str, Any]] = [header]
    extras = extras or {}
    for r in store.conn.execute(
        "SELECT * FROM changes WHERE run_id = ? ORDER BY seq, id", (run_id,)
    ).fetchall():
        rec: dict[str, Any] = {
            "record": "change",
            "run_id": run_id,
            "change_id": r["id"],
            "seq": r["seq"],
            "kind": r["kind"],
            "ns": r["ns"],
            "title": r["title"],
            "page_id": r["page_id"],
            "old_title": r["old_title"],
            "new_title": r["new_title"],
            "old_revid": r["old_revid"],
            "new_revid": r["new_revid"],
            "wiki_timestamp": r["wiki_timestamp"],
            "old_len": r["old_len"],
            "new_len": r["new_len"],
            "edit_summary": r["edit_summary"],
            "edit_summary_untrusted": True,
            "source": r["source"],
            "detected_utc": r["detected_utc"],
            "state": r["state"],
            "visible_after": r["visible_after"],
            "made_visible_utc": r["made_visible_utc"],
        }
        rec.update(extras.get(r["id"], {}))
        if cited_by is not None and r["page_id"]:
            rec["cited_by"] = list(cited_by(r["page_id"]))
        records.append(rec)
    for p in promotions:
        orig = store.conn.execute("SELECT * FROM changes WHERE id = ?", (p.change_id,)).fetchone()
        rec = {
            "record": "visible",
            "run_id": run_id,
            "change_id": p.change_id,
            "page_id": p.page_id,
            "op": p.op,
            "title": p.title,
            "made_visible_utc": p.made_visible_utc,
        }
        if orig is not None:
            rec.update(
                {
                    "original_run_id": orig["run_id"],
                    "kind": orig["kind"],
                    "old_revid": orig["old_revid"],
                    "new_revid": orig["new_revid"],
                    "detected_utc": orig["detected_utc"],
                }
            )
        records.append(rec)
    records.append({"record": "end", "run_id": run_id, "records": len(records)})
    return records


def write_records(path: str | os.PathLike[str], records: Iterable[Mapping[str, Any]]) -> Path:
    """Write `records` to `path` once. An existing file is never overwritten."""
    path = Path(path)
    if path.exists():
        raise ChangelogExistsError(f"{path} already exists; changelog files are immutable")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    body = "".join(_line(r) + "\n" for r in records)
    try:
        with open(tmp, "x", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.link(tmp, path)  # fails if `path` appeared meanwhile: no overwrite, ever
        except FileExistsError as exc:
            raise ChangelogExistsError(f"{path} appeared while writing; left untouched") from exc
    finally:
        try:
            os.unlink(tmp)  # also clears a stale temp from a crashed earlier attempt
        except OSError:
            pass
    return path


def export_run(
    store: Store,
    run_id: str,
    out_dir: str | os.PathLike[str],
    *,
    summary: Mapping[str, Any] | None = None,
    promotions: Sequence[Any] = (),
    extras: Mapping[int, Mapping[str, Any]] | None = None,
    cited_by: Any = None,
) -> Path:
    """Build and write the run's JSONL; return its path."""
    records = build_records(
        store, run_id, summary=summary, promotions=promotions, extras=extras, cited_by=cited_by
    )
    path = run_path(out_dir, run_id, records[0]["started_utc"])
    return write_records(path, records)


def read_records(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Parse and validate one changelog file. Raises `ChangelogFormatError` on damage."""
    out: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for n, raw in enumerate(fh, 1):
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                raise ChangelogFormatError(f"{path} line {n}: not JSON ({exc})") from exc
    if not out or out[0].get("record") != "run":
        raise ChangelogFormatError(f"{path}: first line is not a run header")
    end = out[-1]
    if end.get("record") != "end" or end.get("records") != len(out) - 1:
        raise ChangelogFormatError(f"{path}: missing or wrong end record (truncated?)")
    return out


def iter_changelog(out_dir: str | os.PathLike[str]) -> list[Path]:
    """Every changelog file under `out_dir`, oldest first by name."""
    root = Path(out_dir) / CHANGELOG_SUBDIR
    return sorted(root.glob("*/*/*.jsonl")) if root.exists() else []
