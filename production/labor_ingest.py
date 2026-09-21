"""Ingest the building-tool Lua stream's dump into the production graph, so
`production.labors.labors_for_kind` can answer from the graph alone.

The dump (four JSON files, out of tree because it is game data and this repo is
public) is a bounded read-only read of the live game
(`handoffs/2026-09-21-building-tool-lua.md`, "Deliverable 4"). What this module
takes from it, and what it deliberately does not:

- `job_types.json`: every `df.job_type` with its skill, the skill's labor, the
  per-material overrides and a direct labor. From it: the **job to labor** join
  (done here, from the raw fields, not taken from the dump's own pre-joined
  table) and a **skill to labor** map for the 49 skills some job references.
- `workshop_hosting.json`: for the 33 workshop and furnace kinds, S1 (DFHack's
  hand-written hard-coded job table), S2 (the labors the game's Workers tab
  offers, `profile_labors`) and S3 (every reaction the game lists per kind).
- `quickfort_kinds.json` (optional): only to name the token universe for the
  coverage table.

## What lands in the graph

Everything this module writes carries a `source_ref` starting `dump:`, which is
how a re-run finds and replaces exactly its own rows (idempotent, and it never
touches `production_observation`, nor a row the extractor wrote, except
resetting the `labor` it filled in).

- **Kind attributes** (`production_attribute`, subject `kind:<Token>`): `node`
  (the graph node whose processes the kind hosts), `profile_labors`,
  `building_class`. A kind's node is the raws' own node where reactions the game
  lists for the kind exist in the graph (so `Kiln` and `MagmaKiln` share
  `BUILDING:KILN`, derived from the data, not asserted); a kind no extracted
  reaction reaches gets a constructed node `BUILDING:KIND:<Token>`.
- **Hard-coded job processes** (`is_hardcoded=1`), one per (node, job type,
  task) from S1, id `JOB:<Token>:<JobType>:<task>`. The labor is set **only**
  when the game's job table determines it (see below); otherwise `labor` is
  NULL and a `labor_basis` attribute says why.
- **Unextracted reaction processes**: a reaction the game lists (S3) that the
  extractor did not read (the extractor reads four vanilla files; the game
  loads 293 distinct hosted reactions, the extractor 148) gets a process row
  with a NULL labor and basis `unextracted_reaction`. Omitting them would make
  a kind hosting 104 reactions look as if it hosted 4.
- **Reaction labors**: `extract.py` records a reaction's `[SKILL:...]` (a
  skill, not a labor) as a `skill` attribute. Here it is translated with the
  skill to labor map. A skill with no entry (BREWING, CARPENTRY, POTTERY and
  seven others: the dump maps only skills some job references) leaves the labor
  NULL, with a `labor_candidate` when the skill's name is itself a labor name
  and that labor is in the hosting kind's Workers-tab list.

## When a labor is "determined"

Only from the game's own tables: `job_table_skill` (the job's skill's labor),
`job_table_attr_labor` (a direct labor on the job) or `skill_map`. Never from a
name match or from the Workers-tab list, which are recorded as candidates. Two
further refusals, each left NULL with a reason:

- **Material-dependent**: a job whose only labors are the per-material
  overrides (`skill_stone`, `skill_wood`, `skill_metal`) has no labor that
  applies to *this* task (a leather waterskin is not made with METAL_CRAFT).
- **Contradicts the Workers tab**: the table's labor is not among the labors
  the game's own Workers tab offers for a kind whose list is non-empty. The
  job table is one row per job type and cannot tell a wooden block from a
  stone one, so `ConstructBlocks` is STONECUTTER at both the Mason's and the
  Carpenter's Workshop; the Workers tab lists STONECUTTER for one and not the
  other. Two game-derived sources disagreeing is not a determination.

Run it after the extractor: `extract.py` resets the static tables, and this
module then adds to them. `python -m production.labor_ingest DB DUMP_DIR`.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from . import labors as L
from . import schema, store

DUMP_REF = "dump:"
SYNTH_NODE_PREFIX = "BUILDING:KIND:"


class LaborIngestError(Exception):
    """The dump or the graph is not in a shape this module can ingest honestly.
    Raised rather than papered over."""


# ---- reading the dump ---------------------------------------------------------


def load_dump(dump_dir: str | Path) -> dict:
    d = Path(dump_dir)
    out: dict[str, Any] = {}
    for name, key, required in (
        ("job_types.json", "job_types", True),
        ("workshop_hosting.json", "hosting", True),
        ("quickfort_kinds.json", "quickfort", False),
    ):
        p = d / name
        if not p.is_file():
            if required:
                raise LaborIngestError(f"{p} is missing; the dump needs {name}")
            out[key] = None
            continue
        out[key] = json.loads(p.read_text(encoding="utf-8"))
    return out


def kind_token(entry: dict) -> str:
    """The token the building tool uses: the enum name, or the custom code."""
    name = entry["subtype_name"]
    return name.split(":", 1)[1] if name.startswith("Custom:") else name


def labor_names(job_types: dict) -> set[str]:
    return {x["name"] for x in job_types.get("labors", []) if x.get("name")}


def build_skill_map(job_types: dict, extra: list[dict] | None = None) -> tuple[dict[str, str], set[str]]:
    """`(skill -> labor, skills whose labor is NONE)` from every skill dict a job
    carries, plus optional `extra` `{"skill", "labor"}` pairs (a fuller read of
    `df.job_skill.attrs`). Two different labors for one skill is an error."""
    mapping: dict[str, str] = {}
    none_skills: set[str] = set()

    def add(skill: str, labor: str, where: str) -> None:
        if labor == "NONE":
            none_skills.add(skill)
            return
        if skill in mapping and mapping[skill] != labor:
            raise LaborIngestError(f"skill {skill} maps to both {mapping[skill]} and {labor} ({where})")
        mapping[skill] = labor

    for job in job_types["jobs"]:
        for key in ("skill", "skill_stone", "skill_wood", "skill_metal"):
            s = job.get(key)
            if isinstance(s, dict) and "labor" in s and "skill" in s:
                add(s["skill"], s["labor"], f"job {job.get('name')}")
    for pair in extra or []:
        add(pair["skill"], pair["labor"], "extra skill table")
    return mapping, none_skills


def load_extra_skill_labors(path: str | Path, valid_labors: set[str]) -> list[dict]:
    """A fuller skill to labor table read from the game later, `[{"skill",
    "labor"}, ...]` or `{"skills": [...]}`. Every labor must be a real one."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pairs = data["skills"] if isinstance(data, dict) else data
    for p in pairs:
        if not (isinstance(p, dict) and isinstance(p.get("skill"), str) and isinstance(p.get("labor"), str)):
            raise LaborIngestError(f"skill table entry not of the form {{skill, labor}}: {p!r}")
        if p["labor"] != "NONE" and p["labor"] not in valid_labors:
            raise LaborIngestError(f"skill table names labor {p['labor']!r}, which is not in the game's labor list")
    return pairs


def job_labor(job: dict | None) -> tuple[str | None, str, list[str]]:
    """`(labor or None, basis, candidates)` for one job type from the game's job
    table alone. `basis` is a determined-basis name or `undetermined:<code>`."""
    if job is None:
        return None, f"{L.UNDETERMINED_PREFIX}job_not_in_table", []
    skill = job.get("skill") if isinstance(job.get("skill"), dict) else {}
    main = skill.get("labor")
    main = main if main and main != "NONE" else None
    direct = job.get("attr_labor")
    direct = direct if direct and direct != "NONE" else None
    if main and direct and main != direct:
        return None, f"{L.UNDETERMINED_PREFIX}labor_conflict", sorted({main, direct})
    if main:
        return main, "job_table_skill", []
    if direct:
        return direct, "job_table_attr_labor", []
    overrides = sorted({
        job[k]["labor"] for k in ("skill_stone", "skill_wood", "skill_metal")
        if isinstance(job.get(k), dict) and job[k].get("labor") not in (None, "NONE")
    })
    if overrides:
        return None, f"{L.UNDETERMINED_PREFIX}material_dependent", overrides
    return None, f"{L.UNDETERMINED_PREFIX}no_job_table_labor", []


# ---- the Mason's Workshop question -------------------------------------------


def mason_reconciliation(job_types: dict, hosting: dict) -> dict:
    """What the data says about ConstructBlocks and the MASON labor, computed
    from the dump itself (no prose asserted): the report and the tests read this."""
    jobs = {j["name"]: j for j in job_types["jobs"] if j.get("name")}
    cb_labor, cb_basis, _ = job_labor(jobs.get("ConstructBlocks"))
    kinds = {kind_token(k): k for k in hosting["kinds"]}
    masons = kinds.get("Masons", {})
    profile = list(masons.get("s2_profile_labors", []))
    mason_jobs = sorted(
        j["name"] for j in job_types["jobs"] if j.get("name") and any(
            isinstance(j.get(k), dict) and j[k].get("labor") == "MASON"
            for k in ("skill", "skill_stone", "skill_wood", "skill_metal")
        )
    )
    offering_mason = sorted(t for t, k in kinds.items() if "MASON" in k.get("s2_profile_labors", []))
    unlabelled = sorted(
        j["job_type"] for j in masons.get("s1_jobs", [])
        if j["job_type"] != "CustomReaction" and job_labor(jobs.get(j["job_type"]))[0] is None
    )
    return {
        "construct_blocks_labor": cb_labor,
        "construct_blocks_basis": cb_basis,
        "masons_workshop_profile_labors": profile,
        "job_types_whose_skill_maps_to_MASON": mason_jobs,
        "kinds_whose_workers_tab_offers_MASON": offering_mason,
        "masons_jobs_with_no_table_labor": unlabelled,
        "masons_workers_tab_offers_MASON": "MASON" in profile,
    }


# ---- building the rows --------------------------------------------------------


def _node_row(node_id: str, display: str, ref: str) -> dict:
    return {
        "id": node_id, "kind": schema.KIND_BUILDING, "display_name": display,
        "durability": None, "status": schema.MEASURED, "source_ref": ref,
    }


def _attr(subject: str, name: str, value: str, status: str, ref: str) -> dict:
    return {"subject_id": subject, "name": name, "value": value, "unit": None,
            "status": status, "source_ref": ref}


def _cleanup(conn: sqlite3.Connection) -> None:
    """Remove exactly what a previous run wrote (`source_ref` starting `dump:`)
    and reset the `labor` it set on extractor rows."""
    reset_ids = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT a.subject_id FROM production_attribute a "
            "JOIN production_process p ON p.id = a.subject_id "
            "WHERE a.name = ? AND a.source_ref LIKE 'dump:%' AND p.source_ref NOT LIKE 'dump:%'",
            (L.ATTR_BASIS,),
        )
    ]
    conn.executemany("UPDATE production_process SET labor = NULL WHERE id = ?", [(i,) for i in reset_ids])
    conn.execute("DELETE FROM production_attribute WHERE source_ref LIKE 'dump:%'")
    conn.execute("DELETE FROM production_process WHERE source_ref LIKE 'dump:%'")
    conn.execute("DELETE FROM production_node WHERE source_ref LIKE 'dump:%'")


def _check_extractor_rows(conn: sqlite3.Connection) -> None:
    old = conn.execute(
        "SELECT id, labor FROM production_process WHERE is_hardcoded = 0 AND labor IS NOT NULL LIMIT 3"
    ).fetchall()
    if old:
        raise LaborIngestError(
            "the graph has reaction rows with a non-NULL labor that this module did not write "
            f"(for example {old[0]['id']!r}: {old[0]['labor']!r}). Databases extracted before "
            "2026-09-21 hold the raws' [SKILL] token in `labor`; re-run extraction, then this."
        )


def ingest_dump(
    db_path: str | Path,
    dump_dir: str | Path,
    skill_labors_path: str | Path | None = None,
    *,
    finalize: bool = True,
) -> dict:
    """Ingest the dump into `db_path` (an extracted graph) and return a report.

    `finalize=True` ends with `journal_mode=DELETE` so the deployed file has no
    WAL beside it (`production.labors` opens the file read-only under the
    server's sandbox)."""
    dump = load_dump(dump_dir)
    jt, hosting = dump["job_types"], dump["hosting"]
    jobs = {j["name"]: j for j in jt["jobs"] if j.get("name")}
    valid_labors = labor_names(jt)
    extra = load_extra_skill_labors(skill_labors_path, valid_labors) if skill_labors_path else None
    skill_map, none_skills = build_skill_map(jt, extra)
    kinds = hosting["kinds"]
    tokens = [kind_token(k) for k in kinds]
    if len(set(tokens)) != len(tokens):
        raise LaborIngestError("two kinds in the dump share a token")

    with store.connect(db_path) as conn:
        with conn:
            _cleanup(conn)
            _check_extractor_rows(conn)

            graph_primary = {
                r["id"]: r["workshop_node"]
                for r in conn.execute("SELECT id, workshop_node FROM production_process WHERE is_hardcoded = 0")
            }
            existing_nodes = {r["id"] for r in conn.execute("SELECT id FROM production_node")}

            # -- kind -> node: the raws' node where the game's reactions for the kind are extracted.
            kind_node: dict[str, str] = {}
            node_rows: list[dict] = []
            for k, tok in zip(kinds, tokens):
                observed = {graph_primary[r] for r in k["s3_reactions"] if graph_primary.get(r)}
                if len(observed) > 1:
                    raise LaborIngestError(
                        f"kind {tok}: its reactions sit at more than one graph node {sorted(observed)}"
                    )
                if observed:
                    kind_node[tok] = next(iter(observed))
                else:
                    node = SYNTH_NODE_PREFIX + tok
                    kind_node[tok] = node
                    node_rows.append(_node_row(node, tok, f"dump:workshop_hosting.json#kinds[{tok}] (constructed node)"))
            for row in node_rows:
                if row["id"] in existing_nodes:
                    raise LaborIngestError(f"constructed node {row['id']} collides with an existing node")

            nodes_kinds: dict[str, list[str]] = {}
            for tok, node in kind_node.items():
                nodes_kinds.setdefault(node, []).append(tok)
            profile = {kind_token(k): list(k["s2_profile_labors"]) for k in kinds}

            def profile_at(nodes: list[str]) -> set[str]:
                out: set[str] = set()
                for n in nodes:
                    for tok in nodes_kinds.get(n, []):
                        out.update(profile[tok])
                return out

            attrs: list[dict] = []
            for k, tok in zip(kinds, tokens):
                ref = f"dump:workshop_hosting.json#kinds[{tok}]"
                subject = L.KIND_PREFIX + tok
                attrs.append(_attr(subject, L.ATTR_NODE, kind_node[tok], schema.MEASURED, ref))
                attrs.append(_attr(subject, L.ATTR_PROFILE, ",".join(profile[tok]), schema.MEASURED, ref))
                attrs.append(_attr(subject, L.ATTR_CLASS, k["class"], schema.MEASURED, ref))

            processes: list[dict] = []

            def basis_attrs(pid: str, basis: str, candidates: list[str], ref: str) -> None:
                if basis in L.DETERMINED_BASES:
                    attrs.append(_attr(pid, L.ATTR_BASIS, basis, schema.MEASURED, ref))
                else:
                    attrs.append(_attr(pid, L.ATTR_BASIS, basis, schema.UNAVAILABLE, ref))
                if candidates:
                    attrs.append(_attr(pid, L.ATTR_CANDIDATE, ",".join(candidates), schema.PRIOR, ref))

            # -- hard-coded jobs (S1), one row per (node, job type, task).
            seen: set[tuple[str, str, str]] = set()
            hard_stats = {"rows": 0, "determined": 0}
            for k, tok in zip(kinds, tokens):
                node = kind_node[tok]
                for j in k["s1_jobs"]:
                    if j["job_type"] == "CustomReaction":
                        continue
                    key = (node, j["job_type"], j["name"])
                    if key in seen:
                        continue
                    seen.add(key)
                    pid = f"JOB:{tok}:{j['job_type']}:{j['name']}"
                    ref = f"dump:s1[{tok}]+job_types[{j['job_type']}]"
                    labor, basis, cands = job_labor(jobs.get(j["job_type"]))
                    if labor is not None:
                        allowed = profile_at([node])
                        if allowed and labor not in allowed:
                            cands, labor, basis = [labor], None, f"{L.UNDETERMINED_PREFIX}contradicts_profile"
                    processes.append({
                        "id": pid, "workshop_node": node, "labor": labor,
                        "is_hardcoded": 1, "source_ref": ref,
                    })
                    basis_attrs(pid, basis, cands, ref)
                    hard_stats["rows"] += 1
                    hard_stats["determined"] += labor is not None

            # -- reactions the game lists that the extractor did not read (S3).
            hosting_of: dict[str, list[str]] = {}
            for k, tok in zip(kinds, tokens):
                for r in k["s3_reactions"]:
                    hosting_of.setdefault(r, []).append(tok)
            unextracted = 0
            for rid, toks in sorted(hosting_of.items()):
                if rid in graph_primary:
                    continue
                unextracted += 1
                nodes = list(dict.fromkeys(kind_node[t] for t in toks))
                ref = f"dump:s3[{','.join(toks)}]"
                processes.append({
                    "id": rid, "workshop_node": nodes[0], "labor": None, "is_hardcoded": 0, "source_ref": ref,
                })
                basis_attrs(rid, f"{L.UNDETERMINED_PREFIX}unextracted_reaction", [], ref)
                for extra_node in nodes[1:]:
                    alt = extra_node[len(L.BUILDING_PREFIX):] if extra_node.startswith(L.BUILDING_PREFIX) else extra_node
                    attrs.append(_attr(rid, L.ATTR_ALT, alt, schema.MEASURED, ref))

            # -- the extractor's reactions: skill -> labor.
            skills = {
                r["subject_id"]: r["value"]
                for r in conn.execute("SELECT subject_id, value FROM production_attribute WHERE name = ?", (L.ATTR_SKILL,))
            }
            alts: dict[str, list[str]] = {}
            for r in conn.execute("SELECT subject_id, value FROM production_attribute WHERE name = ?", (L.ATTR_ALT,)):
                alts.setdefault(r["subject_id"], []).append(L.BUILDING_PREFIX + r["value"])
            set_labor: list[tuple[str, str]] = []
            names = valid_labors
            react_stats = {"rows": 0, "determined": 0}
            unmapped_skills: dict[str, int] = {}
            for r in conn.execute(
                "SELECT id, workshop_node FROM production_process WHERE is_hardcoded = 0 AND source_ref NOT LIKE 'dump:%'"
            ).fetchall():
                pid = r["id"]
                react_stats["rows"] += 1
                ref = "dump:job_types.json (skill to labor)"
                nodes = [n for n in [r["workshop_node"], *alts.get(pid, [])] if n]
                allowed = profile_at(nodes)
                skill = skills.get(pid)
                if skill is None:
                    basis_attrs(pid, f"{L.UNDETERMINED_PREFIX}no_skill_in_raws", [], ref)
                    continue
                labor = skill_map.get(skill)
                if labor is None:
                    cands = [skill] if (skill in names and skill in allowed) else []
                    code = "skill_labor_none" if skill in none_skills else f"skill_not_in_table:{skill}"
                    unmapped_skills[skill] = unmapped_skills.get(skill, 0) + 1
                    basis_attrs(pid, f"{L.UNDETERMINED_PREFIX}{code}", cands, ref)
                elif allowed and labor not in allowed:
                    basis_attrs(pid, f"{L.UNDETERMINED_PREFIX}contradicts_profile", [labor], ref)
                else:
                    set_labor.append((labor, pid))
                    basis_attrs(pid, "skill_map", [], ref)
                    react_stats["determined"] += 1
            conn.executemany("UPDATE production_process SET labor = ? WHERE id = ?", set_labor)

            # -- validate and write.
            for label, rows, fn in (
                ("production_node", node_rows, schema.validate_node),
                ("production_process", processes, schema.validate_process),
                ("production_attribute", attrs, schema.validate_attribute),
            ):
                errors = [f"{label}[{i}]: {e}" for i, row in enumerate(rows) for e in fn(row)]
                if errors:
                    raise LaborIngestError("refusing to write invalid rows:\n  " + "\n  ".join(errors[:10]))
            conn.executemany(
                "INSERT INTO production_node (id, kind, display_name, durability, status, source_ref) "
                "VALUES (:id, :kind, :display_name, :durability, :status, :source_ref)", node_rows,
            )
            conn.executemany(
                "INSERT INTO production_process (id, workshop_node, labor, is_hardcoded, source_ref) "
                "VALUES (:id, :workshop_node, :labor, :is_hardcoded, :source_ref)", processes,
            )
            conn.executemany(
                "INSERT INTO production_attribute (subject_id, name, value, unit, status, source_ref) "
                "VALUES (:subject_id, :name, :value, :unit, :status, :source_ref)", attrs,
            )
        if finalize:
            conn.execute("PRAGMA journal_mode=DELETE")

    return {
        "kinds": len(kinds),
        "constructed_nodes": len(node_rows),
        "kinds_mapped_to_raws_node": len(kinds) - len(node_rows),
        "hardcoded": hard_stats,
        "unextracted_reactions": unextracted,
        "extracted_reactions": react_stats,
        "skills_without_labor": dict(sorted(unmapped_skills.items())),
        "skill_map_size": len(skill_map),
        "extra_skill_table": bool(extra),
        "mason_reconciliation": mason_reconciliation(jt, hosting),
    }


# ---- the coverage table -------------------------------------------------------


def format_coverage(db_path: str | Path, universe: list[str] | None = None) -> str:
    cov = L.coverage(db_path, universe)
    hosting = L.kind_tokens(db_path)
    st = cov["by_status_hosting_kinds"]
    lines = [
        f"workshop and furnace kinds the graph holds hosted-job data for ({len(hosting)}): "
        + ", ".join(f"{s} {n}" for s, n in st.items()),
        "  strict rule: every hosted process determined AND the Workers-tab list non-empty and fully explained",
        f"  known under the looser rule (no closure check): {len(cov['literal_known'])}: "
        + ", ".join(cov["literal_known"]),
    ]
    other = len(cov["kinds"]) - sum(1 for t in cov["kinds"] if t in set(hosting))
    if universe is not None:
        lines.append(f"other tokens in the universe ({other}): all unknown, the graph holds no hosted-job data for them")
    for label in ("hardcoded", "reaction", "all"):
        p = cov["processes"][label]
        lines.append(
            f"processes ({label}): {p['total']} total, {p['determined']} determined, "
            f"{p['undetermined']} undetermined ({p['undetermined_with_candidate']} with an inferred candidate) "
            + json.dumps(p["by_reason"])
        )
    for status in ("known", "partial", "unknown"):
        lines.append(f"{status}: " + ", ".join(t for t in hosting if cov["kinds"].get(t, L.labors_for_kind(db_path, t)["status"]) == status))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("db", help="an extracted production graph (run production.extract first)")
    ap.add_argument("dump_dir", help="the building-dump directory (kept out of the repo)")
    ap.add_argument("--skill-labors", help="optional JSON of a fuller skill to labor table")
    args = ap.parse_args(argv)
    report = ingest_dump(args.db, args.dump_dir, args.skill_labors)
    print(json.dumps(report, indent=2, sort_keys=True))
    universe = None
    q = load_dump(args.dump_dir)["quickfort"]
    if q:
        universe = sorted(k["token"] for k in q)
    print(format_coverage(args.db, universe))
    return 0


if __name__ == "__main__":
    sys.exit(main())
