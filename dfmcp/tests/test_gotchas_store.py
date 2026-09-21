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
