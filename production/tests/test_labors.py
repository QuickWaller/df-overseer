"""`production.labors.labors_for_kind`: contract C2, and the rule that unknown is
never zero.

Statuses are pinned per kind on the committed fixture (a subset of the real
dump plus a graph of real reactions). The reasons for each are asserted, since
a status without its reason is the silent-zero shape this module exists to
avoid."""

from __future__ import annotations

import asyncio
import inspect
import sqlite3

import pytest

from production import labor_ingest as li
from production import labors
from production.tests.labor_helpers import FIXTURE_DUMP, build_graph


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("labors") / "graph.sqlite3"
    build_graph(path)
    li.ingest_dump(path, FIXTURE_DUMP)
    return path


def get(db, kind):
    return labors.labors_for_kind(db, kind)


# ---- C2 shape -----------------------------------------------------------------


def test_signature_is_db_path_then_kind_token():
    assert list(inspect.signature(labors.labors_for_kind).parameters)[:2] == ["db_path", "kind_token"]


@pytest.mark.parametrize("kind", ["Fishery", "Masons", "Still", "Bowyers", "Well", "Smelter", "Carpenters"])
def test_every_result_has_the_c2_keys_and_types(db, kind):
    r = get(db, kind)
    assert r["kind"] == kind
    assert r["status"] in ("known", "partial", "unknown")
    assert isinstance(r["labors"], list) and all(isinstance(x, str) for x in r["labors"])
    assert isinstance(r["processes"], list)
    for p in r["processes"]:
        assert set(p) >= {"id", "labor", "source_ref"}
        assert p["labor"] is None or isinstance(p["labor"], str)
    assert r["unknown_reason"] is None or isinstance(r["unknown_reason"], str)


def test_known_has_no_reason_and_the_others_always_have_one(db):
    for kind in ("Fishery", "Masons", "Still", "Bowyers", "Well", "Smelter", "Kiln"):
        r = get(db, kind)
        assert (r["unknown_reason"] is None) == (r["status"] == "known"), kind


# ---- the three statuses -------------------------------------------------------


def test_known_needs_every_process_determined_and_the_workers_tab_explained(db):
    r = get(db, "Fishery")
    assert r["status"] == "known"
    assert r["labors"] == ["CLEAN_FISH", "DISSECT_FISH", "FISH"]
    assert r["unexplained_profile_labors"] == [] and r["undetermined_process_count"] == 0


def test_a_kind_whose_workers_tab_is_empty_can_never_be_known(db):
    """Smelter: every hosted process has a labor (SMELT), but the game offers no
    Workers-tab list to check the hosted-job list against."""
    r = get(db, "Smelter")
    assert r["undetermined_process_count"] == 0 and r["labors"] == ["SMELT"]
    assert r["status"] == "partial"
    assert "cannot be checked" in r["unknown_reason"]


def test_partial_lists_only_what_is_determined_and_says_what_is_not(db):
    r = get(db, "Masons")
    assert r["status"] == "partial" and r["labors"] == ["STONECUTTER"]
    assert r["unexplained_profile_labors"] == ["STONE_CARVER"]
    by_id = {p["id"]: p for p in r["processes"]}
    door = by_id["JOB:Masons:ConstructDoor:construct door"]
    assert door["labor"] is None and "no skill or labor" in door["reason"]
    assert by_id["JOB:Masons:ConstructBlocks:construct blocks"]["labor"] == "STONECUTTER"


def test_unknown_when_nothing_hosted_has_a_determined_labor(db):
    r = get(db, "Still")
    assert r["status"] == "unknown" and r["labors"] == []
    assert "BREWING" in r["unknown_reason"]
    assert len(r["processes"]) == 3 and all(p["labor"] is None for p in r["processes"])


def test_unknown_labors_is_empty_but_status_is_what_a_caller_must_read(db):
    """An empty list with status unknown must never be mistaken for `known` and
    empty (the game data says no labor applies). No kind here is known-empty."""
    for kind in labors.kind_tokens(db):
        r = get(db, kind)
        assert not (r["status"] == "known" and r["labors"] == []), kind


def test_a_kind_that_hosts_nothing_is_unknown_not_empty_known(db):
    r = get(db, "Bowyers")
    assert r["status"] == "unknown" and r["labors"] == [] and r["processes"] == []
    assert "missing data, not evidence" in r["unknown_reason"]


def test_an_absent_kind_is_unknown_with_a_reason(db):
    r = get(db, "Well")
    assert r["status"] == "unknown" and r["labors"] == []
    assert "absence of data" in r["unknown_reason"]


def test_candidates_are_shown_but_never_counted_as_labors(db):
    r = get(db, "Kiln")
    assert r["labors"] == []  # GLAZING is only a candidate here (skill not in the table read)
    glaze = next(p for p in r["processes"] if p["id"] == "GLAZE_STATUE")
    assert glaze["labor"] is None and glaze["candidate_labor"] == "GLAZING"


def test_conflicting_sources_are_refused_not_averaged(db):
    r = get(db, "Carpenters")
    block = next(p for p in r["processes"] if p["id"].startswith("JOB:Carpenters:ConstructBlocks"))
    assert block["labor"] is None and "disagree" in block["reason"]
    assert "STONECUTTER" not in r["labors"]
    assert r["labors"] == ["TRAPPER"] and r["unexplained_profile_labors"] == ["CARPENTER"]


# ---- twins, alternates, tokens ------------------------------------------------


def test_twin_kinds_answer_identically(db):
    a, b = get(db, "Smelter"), get(db, "MagmaSmelter")
    assert a["labors"] == b["labors"] and a["status"] == b["status"]
    assert [p["id"] for p in a["processes"]] == [p["id"] for p in b["processes"]]


def test_a_reaction_listed_under_workshop_alt_is_hosted_by_the_second_kind(db):
    first, second = get(db, "MetalsmithsForge"), get(db, "MagmaForge")
    assert [p["id"] for p in first["processes"]] == ["MAKE_ENT12 INK3_VIB"]
    assert [p["id"] for p in second["processes"]] == ["MAKE_ENT12 INK3_VIB"]


def test_tokens_are_exact(db):
    assert get(db, "masons")["status"] == "unknown"  # the tool's tokens are exact enum names
    with pytest.raises(ValueError):
        labors.labors_for_kind(db, "")
    with pytest.raises(ValueError):
        labors.labors_for_kind(db, None)  # type: ignore[arg-type]


# ---- opening the database: read-only, never creating --------------------------


def test_a_missing_database_raises_and_is_not_created(tmp_path):
    missing = tmp_path / "nope.sqlite3"
    with pytest.raises(labors.GraphError, match="does not exist"):
        labors.labors_for_kind(missing, "Still")
    assert not missing.exists()  # store.connect would have created an empty graph here


def test_reading_does_not_modify_the_file(db):
    before = db.read_bytes()
    get(db, "Masons")
    labors.coverage(db)
    assert db.read_bytes() == before


def test_the_ingested_file_has_no_wal_and_opens_read_only(db, tmp_path):
    assert not db.with_name(db.name + "-wal").exists() and not db.with_name(db.name + "-shm").exists()
    conn = labors.open_readonly(db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM production_attribute")
    finally:
        conn.close()


def test_falls_back_to_immutable_when_read_only_open_fails(db, monkeypatch):
    """The WAL-in-a-read-only-directory case (`ProtectSystem=strict`) fails the
    plain read-only open; the retry must be `immutable=1`."""
    real = sqlite3.connect
    seen: list[str] = []

    def flaky(target, *a, **kw):
        seen.append(target)
        if len(seen) == 1:
            raise sqlite3.OperationalError("unable to open database file")
        return real(target, *a, **kw)

    monkeypatch.setattr(sqlite3, "connect", flaky)
    conn = labors.open_readonly(db)
    conn.close()
    assert "mode=ro" in seen[0] and "immutable" not in seen[0]
    assert "immutable=1" in seen[1]


def test_both_opens_failing_is_a_graph_error_not_an_empty_answer(db, monkeypatch):
    def boom(*a, **kw):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(sqlite3, "connect", boom)
    with pytest.raises(labors.GraphError, match="read-only"):
        labors.labors_for_kind(db, "Still")


def test_a_file_that_is_not_a_graph_is_an_error(tmp_path):
    junk = tmp_path / "junk.sqlite3"
    junk.write_bytes(b"not a database at all" * 20)
    with pytest.raises(labors.GraphError):
        labors.labors_for_kind(junk, "Still")


# ---- the server's consumer ----------------------------------------------------


def test_the_server_join_accepts_the_real_reader_and_never_turns_unknown_into_zero(db):
    """`dfmcp.labor_join` is the C2 consumer. Feed it the real function, not a
    stub: `unknown` must arrive as `labors: null`, `partial` with its caution."""
    from dfmcp import labor_join as lj

    async def counts(names):
        return {"counts": {n: 1 for n in names}, "errors": {}}

    join = lj.LaborJoin(str(db), counts, labors_for_kind=labors.labors_for_kind)

    async def run():
        return (
            await join.join("Fishery", None), await join.join("Masons", None),
            await join.join("Still", None), await join.join("Well", None),
        )

    known, partial, unknown, absent = asyncio.run(run())
    assert known["operating_labors"]["status"] == "known"
    assert known["operating_labors"]["labors"] == ["CLEAN_FISH", "DISSECT_FISH", "FISH"]
    assert partial["operating_labors"]["status"] == "partial"
    assert partial["operating_labors"]["labors"] == ["STONECUTTER"]
    assert any("partly known" in u for u in partial["gaps_unknown"])
    for r in (unknown, absent):
        assert r["operating_labors"]["status"] == "unknown"
        assert r["operating_labors"]["labors"] is None  # not []
        assert r["gaps_unknown"]


# ---- coverage -----------------------------------------------------------------


def test_coverage_counts_match_the_per_kind_answers(db):
    cov = labors.coverage(db)
    assert sum(cov["by_status"].values()) == len(labors.kind_tokens(db)) == 16
    assert cov["kinds"]["Fishery"] == "known" and cov["kinds"]["Still"] == "unknown"
    assert "Smelter" in cov["literal_known"] and cov["kinds"]["Smelter"] == "partial"
    allp = cov["processes"]["all"]
    assert allp["total"] == allp["determined"] + allp["undetermined"]
    assert sum(allp["by_reason"].values()) == allp["undetermined"]
    assert cov["processes"]["hardcoded"]["by_reason"]["no_job_table_labor"] == 5


def test_coverage_over_a_wider_universe_counts_absent_kinds_as_unknown(db):
    cov = labors.coverage(db, ["Fishery", "Well", "Bed"])
    assert cov["by_status"] == {"known": 1, "partial": 0, "unknown": 2}
    assert cov["by_status_hosting_kinds"] == {"known": 1, "partial": 0, "unknown": 0}


def test_a_valid_sqlite_file_that_is_not_a_graph_is_an_error(tmp_path):
    other = tmp_path / "other.sqlite3"
    conn = sqlite3.connect(other)
    conn.execute("CREATE TABLE unrelated (x)")
    conn.commit()
    conn.close()
    with pytest.raises(labors.GraphError, match="could not be read as a graph"):
        labors.labors_for_kind(other, "Still")


def test_an_extracted_graph_the_dump_was_never_ingested_into_answers_unknown(tmp_path):
    """No kind is known and the answer says so, rather than an empty labor list."""
    path = tmp_path / "bare.sqlite3"
    build_graph(path)
    r = labors.labors_for_kind(path, "Still")
    assert r["status"] == "unknown" and r["labors"] == []
    assert labors.kind_tokens(path) == []
