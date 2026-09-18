"""`production/store.py`'s `write_all`: the reset fix.

`handoffs/2026-09-19-dfseries-store.md`: `write_all(reset=True)`, the
default, used to delete `production_observation` along with the static
graph tables, so every re-extraction erased history. This proves the fix:
`reset=True` still clears the static tables (so re-running the extractor
against a fixture set stays idempotent) but leaves `production_observation`
alone.
"""

from __future__ import annotations

from production import schema, store


def _node(node_id: str) -> dict:
    return {
        "id": node_id, "kind": schema.KIND_ITEM_TYPE, "display_name": node_id,
        "status": schema.VERIFIED_RAWS, "source_ref": "test fixture",
    }


def _observation(abs_tick: int, value: float) -> dict:
    return {
        "abs_tick": abs_tick, "subject_id": "fort", "metric": schema.METRIC_POPULATION,
        "value": value, "status": schema.MEASURED, "source_ref": "test fixture",
    }


def test_reset_clears_static_tables_but_not_observation(tmp_path):
    path = tmp_path / "test.sqlite3"

    store.write_all(
        path,
        nodes=[_node("ITEM:FIRST")],
        observations=[_observation(1_000_000, 15)],
        reset=True,
    )

    with store.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM production_node").fetchone()["n"] == 1
        assert conn.execute("SELECT COUNT(*) AS n FROM production_observation").fetchone()["n"] == 1

    # A second extraction run: a different node set, reset=True (the
    # default), and no new observations -- simulating a re-extraction after
    # the fort has been running and accumulating history in the meantime.
    store.write_all(path, nodes=[_node("ITEM:SECOND")], reset=True)

    with store.connect(path) as conn:
        nodes = conn.execute("SELECT id FROM production_node").fetchall()
        assert [r["id"] for r in nodes] == ["ITEM:SECOND"]  # static table was reset

        observations = conn.execute("SELECT abs_tick, value FROM production_observation").fetchall()
        assert len(observations) == 1  # history survived the reset
        assert observations[0]["abs_tick"] == 1_000_000
        assert observations[0]["value"] == 15


def test_reset_false_still_leaves_everything_including_observation(tmp_path):
    path = tmp_path / "test.sqlite3"

    store.write_all(path, nodes=[_node("ITEM:FIRST")], observations=[_observation(1, 1)], reset=True)
    store.write_all(path, nodes=[_node("ITEM:SECOND")], reset=False)

    with store.connect(path) as conn:
        nodes = conn.execute("SELECT id FROM production_node").fetchall()
        assert {r["id"] for r in nodes} == {"ITEM:FIRST", "ITEM:SECOND"}
        assert conn.execute("SELECT COUNT(*) AS n FROM production_observation").fetchone()["n"] == 1


def test_new_observations_are_appended_not_used_to_replace_existing_ones(tmp_path):
    path = tmp_path / "test.sqlite3"

    store.write_all(path, observations=[_observation(1_000_000, 15)], reset=True)
    store.write_all(path, observations=[_observation(1_001_200, 16)], reset=True)

    with store.connect(path) as conn:
        rows = conn.execute("SELECT abs_tick, value FROM production_observation ORDER BY abs_tick").fetchall()
        assert [(r["abs_tick"], r["value"]) for r in rows] == [(1_000_000, 15.0), (1_001_200, 16.0)]
