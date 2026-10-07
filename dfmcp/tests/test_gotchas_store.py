"""Direct tests of `dfmcp.gotchas_store`: the append-only SQLite store behind
`gotchas.get` / `gotchas.write`. Imports nothing from the MCP SDK, so it runs
under the ambient interpreter as well as `.venv-dfmcp`."""

from __future__ import annotations

import json
import sqlite3
import threading

import pytest

from dfmcp import gotchas_store as gs

TOOLS = {"building.build", "building.find", "workshop.build"}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "gotchas.sqlite3"
    gs.init_store(path)
    return path


def _entry(**over):
    rec = {
        "tool": "building.build",
        "kind": None,
        "list": "gotcha",
        "title": "placing a workshop in a desert biome: the build stalls without water",
        "body": "In a desert the builder never gets a path to the site; pick a site near a landmark.",
        "call_excerpt": "building.build Masons NearWagon",
        "written_by_role": "architect",
        "run_id": "run-1",
    }
    rec.update(over)
    return rec


def _add(db, **over):
    return gs.add_entry(db, _entry(**over), known_tools=TOOLS)


# --------------------------------------------------------------------------
# Failing loudly
# --------------------------------------------------------------------------


class TestOpening:
    def test_absent_store_is_refused_not_created(self, tmp_path):
        path = tmp_path / "nope.sqlite3"
        with pytest.raises(gs.GotchaStoreError, match="not found"):
            gs.get_entry(path, "gotcha-0001")
        with pytest.raises(gs.GotchaStoreError, match="not found"):
            gs.add_entry(path, _entry(), known_tools=TOOLS)
        assert not path.exists()

    def test_malformed_store_is_refused(self, tmp_path):
        path = tmp_path / "junk.sqlite3"
        path.write_bytes(b"this is not a sqlite database at all" * 20)
        with pytest.raises(gs.GotchaStoreError, match="malformed"):
            gs.check_store(path)

    def test_empty_sqlite_file_is_malformed_not_an_empty_store(self, tmp_path):
        path = tmp_path / "empty.sqlite3"
        sqlite3.connect(path).close()
        with pytest.raises(gs.GotchaStoreError, match="malformed"):
            gs.entries_for_tool(path, "building.build")

    def test_wrong_schema_version_is_refused(self, db):
        conn = sqlite3.connect(db)
        conn.execute("UPDATE schema_version SET version = 99")
        conn.commit()
        conn.close()
        with pytest.raises(gs.GotchaStoreError, match="schema_version 99"):
            gs.check_store(db)

    def test_init_needs_an_existing_directory(self, tmp_path):
        with pytest.raises(gs.GotchaStoreError, match="does not exist"):
            gs.init_store(tmp_path / "missing-dir" / "g.sqlite3")

    def test_init_is_idempotent_on_a_valid_store_and_keeps_data(self, db):
        _add(db)
        gs.init_store(db)
        assert len(gs.entries_for_tool(db, "building.build")) == 1

    def test_init_refuses_a_file_that_is_not_a_store(self, tmp_path):
        path = tmp_path / "other.sqlite3"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE unrelated (x)")
        conn.commit()
        conn.close()
        with pytest.raises(gs.GotchaStoreError):
            gs.init_store(path)


# --------------------------------------------------------------------------
# Ids, status, records
# --------------------------------------------------------------------------


class TestAddEntry:
    def test_store_chooses_the_id_and_status_is_proposed(self, db):
        rec = _add(db)
        assert rec["id"] == "gotcha-0001"
        assert rec["status"] == "proposed"
        assert rec["outcomes"] == []
        assert rec["written_by_role"] == "architect"
        assert rec["run_id"] == "run-1"
        assert rec["created_at"]

    def test_caller_cannot_supply_id_or_status(self, db):
        rec = _add(db, id="gotcha-0042", status="accepted")
        assert rec["id"] == "gotcha-0001"
        assert rec["status"] == "proposed"

    def test_ids_count_per_list(self, db):
        a = _add(db)
        v = _add(
            db, list="vent", title="asking for a room of any kind: no tool builds rooms",
            body="Nothing in my tool list builds a room; I wanted a bedroom.",
        )
        b = _add(
            db, title="digging into an aquifer layer: the channel floods and stays flooded",
            body="A channel cut through the aquifer floods; dig above it instead.",
        )
        assert (a["id"], v["id"], b["id"]) == ("gotcha-0001", "vent-0001", "gotcha-0002")

    def test_record_shape_matches_contract_c3(self, db):
        rec = _add(db, kind="Masons")
        assert set(rec) == {
            "id", "tool", "kind", "list", "title", "body", "status", "created_at",
            "written_by_role", "run_id", "call_excerpt", "outcomes",
        }
        assert rec["kind"] == "Masons"

    def test_concurrent_writers_never_collide_on_an_id(self, db):
        errors = []
        titles = [
            "placing a still beside a drain: the barrel jobs never start",
            "queueing a mason job before any boulder exists: the job idles forever",
            "asking for a trade depot in a cavern: the wagon path is blocked",
        ]
        bodies = [
            "The still needs its own barrel supply before brewing begins in earnest.",
            "Nothing is cut until stone is dragged in from a mined-out stockpile.",
            "Merchants need a clear approach on the surface, cavern sites never qualify.",
        ]

        def worker(i):
            try:
                gs.add_entry(
                    db, _entry(title=titles[i], body=bodies[i], run_id=f"run-{i}"), known_tools=TOOLS
                )
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert errors == []
        ids = sorted(r["id"] for r in gs.entries_for_tool(db, "building.build"))
        assert ids == ["gotcha-0001", "gotcha-0002", "gotcha-0003"]


# --------------------------------------------------------------------------
# Validation refusals
# --------------------------------------------------------------------------


class TestRefusals:
    def test_unknown_tool_is_refused(self, db):
        with pytest.raises(gs.GotchaStoreError, match="not a tool in this server's registry"):
            _add(db, tool="nonsense.tool")

    @pytest.mark.parametrize(
        "title, fragment",
        [
            ("Masons workshop", "condition"),
            ("hazard: y", "at least two words"),
            ("x" * 130 + ": boom", "too long"),
            ("placing a workshop somewhere:", "hazard"),
            ("short: t", "too short"),
            ("placing a workshop:\nmultiline hazard", "one plain line"),
            ("placing <b>a workshop</b> here: hazard", "one plain line"),
        ],
    )
    def test_bad_titles_are_refused(self, db, title, fragment):
        with pytest.raises(gs.GotchaStoreError, match=fragment):
            _add(db, title=title)
        assert gs.entries_for_tool(db, "building.build") == []

    def test_oversized_and_undersized_bodies_are_refused(self, db):
        with pytest.raises(gs.GotchaStoreError, match="body is too long"):
            _add(db, body="x" * (gs.BODY_MAX_CHARS + 1))
        with pytest.raises(gs.GotchaStoreError, match="body is too short"):
            _add(db, body="tiny")

    def test_oversized_excerpt_is_refused(self, db):
        with pytest.raises(gs.GotchaStoreError, match="call_excerpt is too long"):
            _add(db, call_excerpt="x" * (gs.EXCERPT_MAX_CHARS + 1))

    def test_bad_list_and_kind_are_refused(self, db):
        with pytest.raises(gs.GotchaStoreError, match="list must be one of"):
            _add(db, list="rant")
        with pytest.raises(gs.GotchaStoreError, match="kind token"):
            _add(db, kind="Stoneworker's Workshop")

    def test_every_problem_is_listed_and_nothing_is_written(self, db):
        with pytest.raises(gs.GotchaStoreError) as exc:
            _add(db, tool="nope", title="bad", body="x", list="rant")
        text = str(exc.value)
        for fragment in ("registry", "title", "body", "list must be"):
            assert fragment in text
        assert gs.tool_index(db) == {}

    def test_near_duplicate_title_is_refused_and_names_the_existing_id(self, db):
        first = _add(db)
        with pytest.raises(gs.GotchaStoreError, match=first["id"]):
            _add(
                db,
                title="Placing a workshop in a desert biome: the build stalls without water!",
                body="Completely different body text about something else entirely, long enough.",
            )

    def test_near_duplicate_body_is_refused(self, db):
        first = _add(db)
        with pytest.raises(gs.GotchaStoreError, match="near-duplicate"):
            _add(
                db,
                title="asking for a smelter beside a magma vent: the vent floods the site",
                body=first["body"],
            )

    def test_a_rejected_entry_still_blocks_its_duplicate(self, db):
        first = _add(db)
        gs.set_status(db, first["id"], "rejected", by="maintainer")
        with pytest.raises(gs.GotchaStoreError, match="near-duplicate"):
            _add(db)

    def test_same_title_on_another_tool_or_list_is_not_a_duplicate(self, db):
        _add(db)
        _add(db, tool="building.find")
        _add(db, list="unexplained")
        assert len(gs.entries_for_tool(db, "building.build")) == 2

    def test_per_run_cap(self, db):
        titles = [
            "placing a still beside a drain: the barrel jobs never start",
            "queueing a mason job before any boulder exists: the job idles forever",
            "asking for a trade depot in a cavern: the wagon path is blocked",
            "building a farm on bare rock: nothing can be planted there",
        ]
        bodies = [
            "The still needs its own barrel supply before brewing begins in earnest.",
            "Nothing is cut until stone is dragged in from a mined-out stockpile.",
            "Merchants need a clear approach on the surface, cavern sites never qualify.",
            "Only soil tiles take a crop, so check the tile material before placing a plot.",
        ]
        for i in range(gs.NEW_ENTRIES_PER_RUN):
            _add(db, title=titles[i], body=bodies[i])
        with pytest.raises(gs.GotchaStoreError, match="per-run cap"):
            _add(db, title=titles[3], body=bodies[3])
        # A different run is unaffected.
        _add(db, title=titles[3], body=bodies[3], run_id="run-2")


# --------------------------------------------------------------------------
# Outcomes: append-only
# --------------------------------------------------------------------------


class TestOutcomes:
    def test_outcome_appends_and_never_overwrites(self, db):
        e = _add(db)
        after = gs.add_outcome(db, e["id"], result="worked", note="fixed it", role="architect", run_id="r1")
        assert [o["result"] for o in after["outcomes"]] == ["worked"]
        after = gs.add_outcome(db, e["id"], result="did_not_work", note=None, role="overseer", run_id="r2")
        assert [o["result"] for o in after["outcomes"]] == ["worked", "did_not_work"]
        assert after["outcomes"][0]["note"] == "fixed it"
        assert after["outcomes"][0]["role"] == "architect"
        # The entry's own text and status are untouched.
        assert after["title"] == e["title"] and after["body"] == e["body"]
        assert after["status"] == "proposed"

    def test_unknown_id_is_refused(self, db):
        with pytest.raises(gs.GotchaStoreError, match="no gotcha entry"):
            gs.add_outcome(db, "gotcha-0099", result="worked", note=None, role="a", run_id="r")

    def test_bad_result_is_refused(self, db):
        e = _add(db)
        with pytest.raises(gs.GotchaStoreError, match="result must be one of"):
            gs.add_outcome(db, e["id"], result="maybe", note=None, role="a", run_id="r")

    def test_one_outcome_per_run_per_entry(self, db):
        e = _add(db)
        gs.add_outcome(db, e["id"], result="worked", note=None, role="a", run_id="r")
        with pytest.raises(gs.GotchaStoreError, match="already recorded"):
            gs.add_outcome(db, e["id"], result="did_not_work", note=None, role="a", run_id="r")

    def test_outcomes_only_on_gotchas_and_not_on_rejected(self, db):
        v = _add(db, list="vent")
        with pytest.raises(gs.GotchaStoreError, match="only on gotchas"):
            gs.add_outcome(db, v["id"], result="worked", note=None, role="a", run_id="r")
        g = _add(db, tool="building.find")
        gs.set_status(db, g["id"], "rejected", by="m")
        with pytest.raises(gs.GotchaStoreError, match="rejected"):
            gs.add_outcome(db, g["id"], result="worked", note=None, role="a", run_id="r")

    def test_per_run_outcome_cap(self, db):
        titles = [
            "placing a still beside a drain: the barrel jobs never start",
            "queueing a mason job before any boulder exists: the job idles forever",
            "asking for a trade depot in a cavern: the wagon path is blocked",
        ]
        bodies = [
            "The still needs its own barrel supply before brewing begins in earnest.",
            "Nothing is cut until stone is dragged in from a mined-out stockpile.",
            "Merchants need a clear approach on the surface, cavern sites never qualify.",
        ]
        ids = [
            _add(db, title=t, body=b, run_id=f"writer-{i}")["id"]
            for i, (t, b) in enumerate(zip(titles, bodies))
        ]
        for i in ids[:2]:
            gs.add_outcome(db, i, result="worked", note=None, role="a", run_id="r", max_per_run=2)
        with pytest.raises(gs.GotchaStoreError, match="per-run cap"):
            gs.add_outcome(db, ids[2], result="worked", note=None, role="a", run_id="r", max_per_run=2)

    def test_outcome_counts_include_zeros(self, db):
        e = _add(db)
        assert gs.outcome_counts(db, [e["id"]]) == {e["id"]: {"worked": 0, "did_not_work": 0}}
        gs.add_outcome(db, e["id"], result="worked", note=None, role="a", run_id="r")
        assert gs.outcome_counts(db, [e["id"]])[e["id"]]["worked"] == 1


# --------------------------------------------------------------------------
# Reads, status history, export
# --------------------------------------------------------------------------


class TestReadsAndExport:
    def test_kind_filter_includes_tool_wide_entries(self, db):
        wide = _add(db)
        mason = _add(
            db, kind="Masons", title="queueing blocks at a mason's bench with no boulders: the job idles",
            body="Blocks need a free boulder; mine one before queueing the job at all.",
        )
        _add(
            db, kind="Still", title="brewing at a still with no barrels: the job never starts",
            body="A still needs an empty barrel per brew; make barrels first at a carpenter.",
        )
        ids = [r["id"] for r in gs.entries_for_tool(db, "building.build", kind="Masons")]
        assert ids == [wide["id"], mason["id"]]
        assert len(gs.entries_for_tool(db, "building.build")) == 3

    def test_status_change_is_audited(self, db):
        e = _add(db)
        after = gs.set_status(db, e["id"], "accepted", by="maintainer", note="seen twice")
        assert after["status"] == "accepted"
        conn = sqlite3.connect(db)
        rows = conn.execute("SELECT from_status, to_status, by FROM status_history").fetchall()
        conn.close()
        assert rows == [("proposed", "accepted", "maintainer")]

    def test_tool_index(self, db):
        _add(db)
        assert gs.tool_index(db) == {"building.build": {"gotcha": {"proposed": 1}}}

    def test_export_is_deterministic_and_carries_outcomes(self, db, tmp_path):
        e = _add(db)
        gs.add_outcome(db, e["id"], result="worked", note="ok", role="a", run_id="r")
        gs.export_jsonl(db, tmp_path / "out1")
        gs.export_jsonl(db, tmp_path / "out2")
        a = (tmp_path / "out1" / "gotchas.jsonl").read_bytes()
        assert a == (tmp_path / "out2" / "gotchas.jsonl").read_bytes()
        rec = json.loads(a.decode().splitlines()[0])
        assert rec["id"] == e["id"] and rec["outcomes"][0]["result"] == "worked"

    def test_cli_init_and_export(self, tmp_path, capsys):
        path = tmp_path / "cli.sqlite3"
        assert gs._main(["init", str(path)]) == 0
        assert gs._main(["export", str(path), str(tmp_path / "o")]) == 0
        assert gs._main(["bogus"]) == 2
        assert (tmp_path / "o" / "gotchas.jsonl").exists()


# --------------------------------------------------------------------------
# General entries (register 2026-10-02): tool = NULL
# --------------------------------------------------------------------------


class TestGeneralEntries:
    def test_tool_may_be_omitted_and_reads_back_as_none(self, db):
        rec = _add(db, tool=None)
        assert rec["tool"] is None
        assert rec["kind"] is None
        fetched = gs.get_entry(db, rec["id"])
        assert fetched["tool"] is None

    def test_kind_with_no_tool_is_refused(self, db):
        with pytest.raises(gs.GotchaStoreError, match="kind is meaningless without a tool"):
            _add(db, tool=None, kind="Masons")
        assert gs.tool_index(db) == {}

    def test_empty_string_tool_is_refused_not_treated_as_general(self, db):
        with pytest.raises(gs.GotchaStoreError, match="non-empty string"):
            _add(db, tool="")

    def test_entries_for_tool_none_lists_only_general_entries(self, db):
        g = _add(db, tool=None)
        t = _add(db, title="placing a trade depot off the map edge: wagons cannot reach it",
                 body="A depot more than a few tiles from the edge is unreachable by wagon; keep it close.")
        assert [r["id"] for r in gs.entries_for_tool(db, None)] == [g["id"]]
        assert [r["id"] for r in gs.entries_for_tool(db, "building.build")] == [t["id"]]

    def test_outcomes_duplicate_check_and_tool_index_all_work_on_general_entries(self, db):
        g = _add(db, tool=None)
        after = gs.add_outcome(db, g["id"], result="worked", note=None, role="a", run_id="r")
        assert [o["result"] for o in after["outcomes"]] == ["worked"]
        with pytest.raises(gs.GotchaStoreError, match="near-duplicate"):
            _add(db, tool=None, title=g["title"] + "!")
        assert gs.tool_index(db) == {None: {"gotcha": {"proposed": 1}}}

    def test_same_title_general_and_tool_scoped_is_not_a_duplicate(self, db):
        g = _add(db, tool=None)
        t = _add(db, title=g["title"], body=g["body"])
        assert g["id"] != t["id"]


# --------------------------------------------------------------------------
# Migrating a version-1 store (tool NOT NULL) to version 2 (tool nullable)
# --------------------------------------------------------------------------

_V1_SCHEMA_SQL = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
CREATE TABLE entries (
    id TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    kind TEXT,
    list TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    written_by_role TEXT NOT NULL,
    run_id TEXT NOT NULL,
    call_excerpt TEXT
);
CREATE INDEX idx_entries_tool ON entries(tool, list, status);
CREATE INDEX idx_entries_run ON entries(run_id);
CREATE TABLE outcomes (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL REFERENCES entries(id),
    at TEXT NOT NULL,
    role TEXT NOT NULL,
    run_id TEXT NOT NULL,
    result TEXT NOT NULL,
    note TEXT
);
CREATE INDEX idx_outcomes_entry ON outcomes(entry_id);
CREATE TABLE status_history (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL REFERENCES entries(id),
    at TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    by TEXT NOT NULL,
    note TEXT
);
"""


def _make_v1_store(path):
    """A populated schema-version-1 store (`tool NOT NULL`), built by hand
    with the old DDL so the migration test exercises the real upgrade path,
    not a store `init_store` already created at the current version."""
    conn = sqlite3.connect(path)
    conn.executescript(_V1_SCHEMA_SQL)
    conn.execute("INSERT INTO schema_version (version) VALUES (1)")
    conn.execute(
        "INSERT INTO entries (id, tool, kind, list, title, body, status, created_at, "
        "written_by_role, run_id, call_excerpt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("gotcha-0001", "building.build", "Masons",
         "gotcha", "placing a workshop in a desert biome: the build stalls without water",
         "In a desert the builder never gets a path to the site.", "accepted",
         "2026-09-01T00:00:00+00:00", "architect", "run-1", "building.build Masons NearWagon"),
    )
    conn.execute(
        "INSERT INTO entries (id, tool, kind, list, title, body, status, created_at, "
        "written_by_role, run_id, call_excerpt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("vent-0001", "building.find", None,
         "vent", "asking for a room of any kind: no tool builds rooms",
         "Nothing in my tool list builds a room; I wanted a bedroom.", "proposed",
         "2026-09-02T00:00:00+00:00", "overseer", "run-2", None),
    )
    conn.execute(
        "INSERT INTO outcomes (entry_id, at, role, run_id, result, note) VALUES (?, ?, ?, ?, ?, ?)",
        ("gotcha-0001", "2026-09-03T00:00:00+00:00", "overseer", "run-3", "worked", "confirmed"),
    )
    conn.execute(
        "INSERT INTO status_history (entry_id, at, from_status, to_status, by, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("gotcha-0001", "2026-09-03T00:00:01+00:00", "proposed", "accepted", "maintainer", "seen twice"),
    )
    conn.commit()
    conn.close()


class TestMigrationV1ToV2:
    def test_v1_store_has_tool_not_null(self, tmp_path):
        path = tmp_path / "v1.sqlite3"
        _make_v1_store(path)
        conn = sqlite3.connect(path)
        cols = {r[1]: r for r in conn.execute("PRAGMA table_info(entries)").fetchall()}
        conn.close()
        assert cols["tool"][3] == 1  # notnull flag, before migration

    def test_opening_a_v1_store_migrates_it_and_preserves_every_row(self, tmp_path):
        path = tmp_path / "v1.sqlite3"
        _make_v1_store(path)

        entries = gs.entries_for_tool(path, "building.build")
        assert [e["id"] for e in entries] == ["gotcha-0001"]
        e = entries[0]
        assert e["status"] == "accepted" and e["kind"] == "Masons"
        assert [o["result"] for o in e["outcomes"]] == ["worked"]
        assert e["outcomes"][0]["note"] == "confirmed"

        vents = gs.entries_for_tool(path, "building.find", lists=["vent"])
        assert [v["id"] for v in vents] == ["vent-0001"]

        conn = sqlite3.connect(path)
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        cols = {r[1]: r for r in conn.execute("PRAGMA table_info(entries)").fetchall()}
        status_rows = conn.execute(
            "SELECT from_status, to_status, by FROM status_history"
        ).fetchall()
        conn.close()
        assert version == gs.SCHEMA_VERSION == 2
        assert cols["tool"][3] == 0  # notnull flag cleared
        assert status_rows == [("proposed", "accepted", "maintainer")]

    def test_migration_lets_a_new_general_entry_be_written_afterwards(self, tmp_path):
        path = tmp_path / "v1.sqlite3"
        _make_v1_store(path)
        gs.check_store(path)  # triggers the lazy migration
        rec = gs.add_entry(
            path,
            {
                "tool": None, "list": "gotcha",
                "title": "waking mid-cycle with no fresh tool result: the context is stale",
                "body": "The run resumed mid-cycle and acted on a stale tool result from before "
                "the pause.",
                "written_by_role": "overseer", "run_id": "run-9",
            },
            known_tools={"building.build", "building.find"},
        )
        assert rec["tool"] is None
        assert [r["id"] for r in gs.entries_for_tool(path, "building.build")] == ["gotcha-0001"]

    def test_migration_is_idempotent_on_restart(self, tmp_path):
        path = tmp_path / "v1.sqlite3"
        _make_v1_store(path)
        gs.check_store(path)
        gs.check_store(path)  # second open: already v2, must be a no-op
        entries = gs.entries_for_tool(path, "building.build")
        assert len(entries) == 1
        conn = sqlite3.connect(path)
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        conn.close()
        assert version == 2

    def test_explicit_migrate_store_command_and_cli(self, tmp_path, capsys):
        path = tmp_path / "v1.sqlite3"
        _make_v1_store(path)
        assert gs.migrate_store(path) == 2
        assert gs.migrate_store(path) == 2  # idempotent, run again
        entries = gs.entries_for_tool(path, "building.build")
        assert len(entries) == 1 and entries[0]["outcomes"][0]["result"] == "worked"

        path2 = tmp_path / "v1b.sqlite3"
        _make_v1_store(path2)
        assert gs._main(["migrate", str(path2)]) == 0
        out = capsys.readouterr().out
        assert "schema_version 2" in out

    def test_already_current_store_is_untouched_by_migrate(self, db):
        gs.migrate_store(db)  # a fresh v2 store from init_store: no-op
        conn = sqlite3.connect(db)
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        conn.close()
        assert version == gs.SCHEMA_VERSION


class TestMaintainerRevision:
    """revise_entry: maintainer-only text correction that keeps the id and the
    old text (gotcha-0002 was wrong, 2026-10-08)."""

    def test_revise_keeps_id_and_preserves_old_text(self, db):
        rec = _add(db)
        new = gs.revise_entry(db, rec["id"], "A corrected body that is long enough.", by="m", note="why")
        assert new["id"] == rec["id"]
        assert new["body"] == "A corrected body that is long enough."
        assert new["title"] == rec["title"]
        import sqlite3 as _sq
        conn = _sq.connect(db)
        (note,) = conn.execute("SELECT note FROM status_history WHERE entry_id = ?", (rec["id"],)).fetchone()
        conn.close()
        audit = json.loads(note)
        assert audit["old_body"] == rec["body"] and audit["old_title"] == rec["title"]

    def test_revise_validates_and_unknown_id_refused(self, db):
        rec = _add(db)
        with pytest.raises(gs.GotchaStoreError):
            gs.revise_entry(db, rec["id"], "short", by="m")
        with pytest.raises(gs.GotchaStoreError):
            gs.revise_entry(db, "gotcha-9999", "A corrected body that is long enough.", by="m")

    def test_committed_gotcha_0002_revision_passes_validation(self):
        from pathlib import Path
        p = Path(__file__).resolve().parents[2] / "gotchas" / "revisions" / "gotcha-0002.body.txt"
        body = p.read_text(encoding="utf-8").strip()
        assert gs._text_problems("body", body, gs.BODY_MIN_CHARS, gs.BODY_MAX_CHARS) == []
