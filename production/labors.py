"""Which labors operate a building kind: contract C2 of `docs/BUILDING-TOOL.md`.

`labors_for_kind(db_path, kind_token)` answers from the production graph
alone (the user's decision, register 2026-09-21): a workshop's operating
labors are the labors of the processes it hosts, `production_process.labor`
joined through `workshop_node`. The graph is populated by `extract.py` (the
raws' reactions) and `labor_ingest.py` (a bounded live read of the game's own
job, skill and hosting tables, `handoffs/2026-09-21-building-tool-lua.md`).

## The rule this module exists to keep: unknown is never zero

The silent-zero bug class has shipped five times in this repo (register
2026-09-19). Everything below follows from refusing to return an empty list
where the honest answer is "not known":

- `status: "known"` needs **three** things, not one: the kind hosts at least
  one process, **every** hosted process has a determined labor, and the game's
  own Workers-tab list for the kind (`profile_labors`, DFHack's
  `get_profile_labors`) is non-empty and fully explained by the hosted
  processes. The third condition is the closure check. Job hosting has no
  single complete source (the Lua stream's report: hard-coded hosting covers
  16 of 33 kinds, 66 workshop-like job types are attributed to no kind), so
  "every process we know about has a labor" would say `known` for a kind whose
  hosting list is incomplete. A labor the game offers for the kind that no
  hosted process explains proves the list is incomplete. A kind whose game list
  is empty offers no such check, so it is at best `partial`. The looser
  reading (only the first two conditions) is reported alongside in
  `coverage()` so the cost of the stricter rule is visible.
- `status: "partial"`: at least one labor is determined, but the answer is not
  closed. `labors` holds only the determined ones; `unknown_reason` says what
  is missing. Never present a partial list as the whole.
- `status: "unknown"`: no labor is determined (no such kind in the graph, the
  kind hosts nothing the graph knows, or nothing it hosts has a determined
  labor). `labors` is `[]` **and status is `unknown`**: the caller must read
  the status, never the emptiness. (`dfmcp.labor_join` does: unknown reaches
  the agent as `labors: null`.)

A labor is **determined** only when the game's own tables give it
(`labor_basis` `job_table_*` or `skill_map`, `labor_ingest.py`). A candidate
found by name-matching or by the game's Workers-tab list is recorded as a
`candidate_labor` on the process, never placed in `labors`, because it is an
inference.

## Return shape (C2, plus additive keys)

`{"kind", "labors", "status", "processes": [{"id", "labor" or None,
"source_ref"} + "reason"/"candidate_labor" on an undetermined one],
"unknown_reason"}` and, additively (extra keys are ignored by the C2 consumer):
`profile_labors` (what the game's Workers tab offers for the kind) and
`unexplained_profile_labors` (offered but explained by no hosted process),
`undetermined_process_count`.

## Opening the database under the server's sandbox

`dfmcp-server.service` runs with `ProtectSystem=strict`: it cannot create the
`-wal`/`-shm` files a WAL-mode SQLite needs beside the database, which is
exactly why every `series.*` call failed with "unable to open database file"
until `ReadWritePaths` was added (register 2026-09-20). This module therefore
never uses `store.connect` (that creates the file, sets `journal_mode=WAL` and
runs DDL, all writes). It opens with a read-only URI (`mode=ro`) and, if that
fails with `OperationalError` (the WAL case in a read-only directory), retries
with `immutable=1`, which reads the main file alone and takes no locks. That is
correct only for a file no writer is changing: the graph is built offline and
deployed as a closed file, and `labor_ingest.ingest_dump` finishes by setting
`journal_mode=DELETE` so the deployed file has no WAL to lose. A file that is
absent is an error, never an empty answer.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable

# ---- names shared with labor_ingest (the graph's private vocabulary) ----------

#: `production_attribute.subject_id` for a building kind: `kind:<Token>`.
KIND_PREFIX = "kind:"
#: kind attribute names.
ATTR_NODE = "node"                      # the graph node hosting the kind's processes
ATTR_PROFILE = "profile_labors"         # comma-separated; '' = the game offers none
ATTR_CLASS = "building_class"           # workshop | furnace
#: process attribute names.
ATTR_BASIS = "labor_basis"
ATTR_CANDIDATE = "labor_candidate"
ATTR_ALT = "workshop_alt"               # the extractor's existing name (extract.py)
ATTR_SKILL = "skill"

#: `labor_basis` values that determine a labor.
DETERMINED_BASES = ("job_table_skill", "job_table_attr_labor", "skill_map")
UNDETERMINED_PREFIX = "undetermined:"

BUILDING_PREFIX = "BUILDING:"

#: What each undetermined code means, in plain words. The text is what the
#: caller reads; the code is what the coverage table counts.
REASON_TEXT = {
    "no_job_table_labor": (
        "the game's job table names no skill or labor for this job (the game applies "
        "the labor in code, from the item's material)"
    ),
    "material_dependent": (
        "the job table names a labor only per material (stone, wood or metal), so "
        "which one applies depends on the item made"
    ),
    "skill_not_in_table": (
        "the reaction's skill has no labor in the skill table read from the game "
        "(only skills that some job references were read)"
    ),
    "unextracted_reaction": (
        "the reaction is in the game's reaction table but was not extracted from the "
        "raws, so its skill, and so its labor, are unread"
    ),
    "no_skill_in_raws": "the reaction's raws name no skill",
    "job_not_in_table": "the job type is not in the game's job table read for this graph",
    "labor_conflict": "the job table gives two different labors for this job",
    "skill_labor_none": "the skill's labor in the game's table is NONE",
    "contradicts_profile": (
        "the game's job or skill table gives a labor that the game's own Workers tab does not "
        "offer for this kind (the two game-derived sources disagree, so neither is trusted)"
    ),
}

#: The same codes as short phrases, for the per-kind breakdown in `unknown_reason`.
SHORT_TEXT = {
    "no_job_table_labor": "no labor in the game's job table",
    "material_dependent": "labor depends on the item's material",
    "skill_not_in_table": "skill not in the skill table read",
    "unextracted_reaction": "reaction not extracted from the raws",
    "no_skill_in_raws": "no skill in the raws",
    "job_not_in_table": "job type not in the job table",
    "labor_conflict": "job table gives two labors",
    "skill_labor_none": "the skill's labor is NONE",
    "contradicts_profile": "the table's labor is not one the Workers tab offers for the kind",
    "no_basis_recorded": "no basis recorded",
}


class GraphError(Exception):
    """The graph database could not be read at all (absent, not a graph, locked).
    The server turns any exception here into `unknown`; it is never an empty
    answer."""


def _uri(path: Path, extra: str) -> str:
    return path.resolve().as_uri() + "?" + extra


def open_readonly(db_path: str | Path) -> sqlite3.Connection:
    """Open the graph without writing to it or creating it. See the module
    docstring for why `mode=ro` then `immutable=1`."""
    path = Path(db_path)
    if not path.is_file():
        raise GraphError(f"the production graph database does not exist at {path}")
    last: Exception | None = None
    for extra in ("mode=ro", "mode=ro&immutable=1"):
        try:
            conn = sqlite3.connect(_uri(path, extra), uri=True)
            conn.row_factory = sqlite3.Row
            # Force a real read now: a WAL database in a read-only directory only
            # fails on first use, not on connect.
            conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
            return conn
        except sqlite3.OperationalError as exc:
            last = exc
            try:
                conn.close()  # type: ignore[possibly-undefined]
            except Exception:
                pass
    raise GraphError(f"could not open the production graph read-only at {path}: {last}")


def _split(value: str | None) -> list[str]:
    return [x for x in (value or "").split(",") if x]


def _kind_attr(conn: sqlite3.Connection, token: str, name: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM production_attribute WHERE subject_id = ? AND name = ?",
        (KIND_PREFIX + token, name),
    ).fetchone()
    return None if row is None else row["value"]


def _reason_text(basis: str | None) -> str:
    if not basis or not basis.startswith(UNDETERMINED_PREFIX):
        return "the graph records no basis for this process's labor"
    code, _, detail = basis[len(UNDETERMINED_PREFIX):].partition(":")
    text = REASON_TEXT.get(code, code)
    if code == "skill_not_in_table" and detail:
        return f"{text} (skill {detail})"
    return text


def _reason_code(basis: str | None) -> str:
    if not basis or not basis.startswith(UNDETERMINED_PREFIX):
        return "no_basis_recorded"
    return basis[len(UNDETERMINED_PREFIX):].partition(":")[0]


def _hosted(conn: sqlite3.Connection, node: str) -> list[dict]:
    """Processes hosted at `node`: primary (`workshop_node`) or listed as an
    alternate building (`workshop_alt`, the extractor's convention: the value
    is the node id without its `BUILDING:` prefix)."""
    alt_value = node[len(BUILDING_PREFIX):] if node.startswith(BUILDING_PREFIX) else node
    rows = conn.execute(
        "SELECT p.id, p.labor, p.source_ref, "
        "  (SELECT value FROM production_attribute a WHERE a.subject_id = p.id AND a.name = ?) AS basis, "
        "  (SELECT value FROM production_attribute a WHERE a.subject_id = p.id AND a.name = ?) AS candidate "
        "FROM production_process p "
        "WHERE p.workshop_node = ? "
        "   OR p.id IN (SELECT subject_id FROM production_attribute WHERE name = ? AND value = ?) "
        "ORDER BY p.id",
        (ATTR_BASIS, ATTR_CANDIDATE, node, ATTR_ALT, alt_value),
    ).fetchall()
    out = []
    for r in rows:
        item: dict[str, Any] = {"id": r["id"], "labor": r["labor"], "source_ref": r["source_ref"]}
        if r["labor"] is None:
            item["reason"] = _reason_text(r["basis"])
            if r["candidate"]:
                item["candidate_labor"] = r["candidate"]
        out.append(item)
    return out


def _unknown(kind: str, reason: str, **extra: Any) -> dict:
    return {
        "kind": kind, "labors": [], "status": "unknown", "processes": extra.pop("processes", []),
        "unknown_reason": reason, **extra,
    }


def _breakdown(nulls: Iterable[dict], bases: dict[str, str | None]) -> str:
    counts: dict[str, int] = {}
    details: dict[str, set[str]] = {}
    for p in nulls:
        basis = bases.get(p["id"])
        code = _reason_code(basis)
        counts[code] = counts.get(code, 0) + 1
        if basis and basis.startswith(UNDETERMINED_PREFIX):
            detail = basis[len(UNDETERMINED_PREFIX):].partition(":")[2]
            if detail:
                details.setdefault(code, set()).add(detail)
    parts = []
    for code, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        extra = f": {', '.join(sorted(details[code]))}" if code in details else ""
        parts.append(f"{SHORT_TEXT.get(code, code)}{extra} ({n})")
    return "; ".join(parts)


def labors_for_kind(db_path: str | Path, kind_token: str) -> dict:
    """Contract C2. See the module docstring for the status rules."""
    if not isinstance(kind_token, str) or not kind_token:
        raise ValueError("kind_token must be a non-empty string")
    with closing(open_readonly(db_path)) as conn:
        node = _kind_attr(conn, kind_token, ATTR_NODE)
        if node is None:
            return _unknown(
                kind_token,
                f"the graph has no record of a workshop or furnace kind {kind_token!r}: it holds "
                "hosted-job data only for the workshop and furnace kinds in the game's building "
                "table, so a furniture, construction or unknown kind is not covered, and that is "
                "an absence of data, not an absence of labor",
            )
        profile_raw = _kind_attr(conn, kind_token, ATTR_PROFILE)
        profile = sorted(_split(profile_raw))
        procs = _hosted(conn, node)
        bases = {
            r["subject_id"]: r["value"]
            for r in conn.execute(
                "SELECT subject_id, value FROM production_attribute WHERE name = ?", (ATTR_BASIS,)
            )
        }

    labors = sorted({p["labor"] for p in procs if p["labor"]})
    nulls = [p for p in procs if not p["labor"]]
    unexplained = sorted(set(profile) - set(labors))
    extra = {
        "profile_labors": profile,
        "unexplained_profile_labors": unexplained,
        "undetermined_process_count": len(nulls),
    }

    if not procs:
        return _unknown(
            kind_token,
            "no process is recorded as hosted by this kind (job hosting has no complete source, "
            "so that is missing data, not evidence that the kind needs no labor)"
            + (f"; the game's Workers tab offers {', '.join(profile)}" if profile else ""),
            **extra,
        )
    if not labors:
        return _unknown(
            kind_token,
            f"the kind hosts {len(procs)} process(es) and none has a determined labor: "
            + _breakdown(nulls, bases),
            processes=procs, **extra,
        )

    causes: list[str] = []
    if nulls:
        causes.append(
            f"{len(nulls)} of {len(procs)} hosted processes have no determined labor "
            f"({_breakdown(nulls, bases)})"
        )
    if profile:
        if unexplained:
            causes.append(
                "the game's own Workers tab also offers " + ", ".join(unexplained)
                + " for this kind, which no hosted process explains (so the hosted-job list is "
                "incomplete or those labors are inferences only)"
            )
    else:
        causes.append(
            "the game offers no labor restriction list for this kind, so the completeness of "
            "the hosted-job list cannot be checked, and job hosting has no complete source"
        )
    return {
        "kind": kind_token, "labors": labors,
        "status": "partial" if causes else "known",
        "processes": procs,
        "unknown_reason": "; ".join(causes) if causes else None,
        **extra,
    }


def kind_tokens(db_path: str | Path) -> list[str]:
    """Every kind token the graph holds hosted-job data for."""
    with closing(open_readonly(db_path)) as conn:
        return sorted(
            r["subject_id"][len(KIND_PREFIX):]
            for r in conn.execute(
                "SELECT subject_id FROM production_attribute WHERE name = ?", (ATTR_NODE,)
            )
        )


def coverage(db_path: str | Path, universe: Iterable[str] | None = None) -> dict:
    """The honest coverage table, computed from the graph itself.

    `universe` is the set of kind tokens to grade (for the real run, every
    token in quickfort's building table); absent tokens count as unknown with
    their reason. Returns:

    - `kinds`: `{token: status}`; `by_status`: counts.
    - `literal_known`: kinds that would be `known` under the looser rule (every
      hosted process has a determined labor, no closure check), to show what the
      strict rule costs.
    - `processes`: `{total, determined, undetermined, by_reason}` over every
      process hosted by some kind, `hardcoded` restricted to `is_hardcoded=1`.
    """
    tokens = list(universe) if universe is not None else kind_tokens(db_path)
    kinds: dict[str, str] = {}
    literal_known: list[str] = []
    for t in tokens:
        r = labors_for_kind(db_path, t)
        kinds[t] = r["status"]
        if r["processes"] and r["status"] != "unknown" and r["undetermined_process_count"] == 0:
            literal_known.append(t)
    by_status = {"known": 0, "partial": 0, "unknown": 0}
    for s in kinds.values():
        by_status[s] += 1

    with closing(open_readonly(db_path)) as conn:
        bases = {
            r["subject_id"]: r["value"]
            for r in conn.execute("SELECT subject_id, value FROM production_attribute WHERE name = ?", (ATTR_BASIS,))
        }
        rows = conn.execute("SELECT id, labor, is_hardcoded FROM production_process").fetchall()

    def tally(sel) -> dict:
        chosen = [r for r in rows if sel(r)]
        by_reason: dict[str, int] = {}
        for r in chosen:
            if r["labor"] is None:
                code = _reason_code(bases.get(r["id"]))
                by_reason[code] = by_reason.get(code, 0) + 1
        undetermined = sum(by_reason.values())
        return {
            "total": len(chosen), "determined": len(chosen) - undetermined,
            "undetermined": undetermined, "by_reason": dict(sorted(by_reason.items())),
        }

    return {
        "kinds": kinds,
        "by_status": by_status,
        "literal_known": sorted(literal_known),
        "processes": {
            "all": tally(lambda r: True),
            "hardcoded": tally(lambda r: r["is_hardcoded"] == 1),
            "reaction": tally(lambda r: r["is_hardcoded"] == 0),
        },
    }
