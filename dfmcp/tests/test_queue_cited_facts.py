"""Conductor-execution stage 1 (`docs/CONDUCTOR-EXECUTION.md` 2.2 item 4, 3.3):
`relies_on` with server-side reads at filing, and `queue.pending_brief`.

Transport-free like `test_queue_tools.py`: `dfmcp.queue_tools` and
`dfqueue.store` directly, with an injected fact reader, so this runs under the
ambient environment too. The wired role/allowlist checks are in
`test_server.py::TestCitedFacts`.
"""

from __future__ import annotations

import asyncio

import pytest

from dfmcp import queue_tools
from dfqueue import schema, store

pytestmark = pytest.mark.asyncio

_OVERVIEW = {"tier1": {"population": 7}, "tier2": {"in_game_date": "year 1, month 1, day 1, tick 500", "alerts": []}}


async def _dfhack(tool_id, arguments):
    assert tool_id == "overview.get"
    return _OVERVIEW


def _args(**overrides) -> dict:
    args = {
        "type": "workshop_siting",
        "summary": "Site the next workshop on open ground.",
        "rationale": "Shortest hauling path of the candidates offered.",
        "prediction": {"signal": "fort.population", "op": "gte", "value": 1, "check_after_ticks": 1200},
        "cost": {"estimate": 10, "unit": "dwarf_ticks"},
        "suggested_priority": 3,
        "preconditions": [{"landmark": "Wagon", "state": "exists"}],
        "public_rationale": "Puts the workshop near the wagon.",
    }
    args.update(overrides)
    return args


class _Reader:
    """A fact reader over a dict of `(tool, canonical args) -> result`; counts reads."""

    def __init__(self, results):
        self.results = results
        self.calls = []

    async def __call__(self, role, tool, arguments):
        self.calls.append((role, tool, dict(arguments)))
        key = (tool, tuple(sorted(arguments.items())))
        if key not in self.results:
            raise queue_tools.FactReadError(f"{tool}: not readable here")
        value = self.results[key]
        if isinstance(value, Exception):
            raise value
        return value


BED = ("stocks.availability", (("type", "BED"),))


async def _propose(db, role="architect", reader=None, **overrides):
    return await queue_tools.call(
        queue_tools.QUEUE_PROPOSE, role, _args(**overrides), db_path=db, call_dfhack=_dfhack,
        write_lock=asyncio.Lock(), fact_reader=reader,
    )


class TestRelyOnAtFiling:
    async def test_values_and_the_filing_tick_are_stored(self, tmp_path):
        db = tmp_path / "q.sqlite3"
        reader = _Reader({BED: {"available_units": 3}})
        _, written = await _propose(db, reader=reader, relies_on=[
            {"tool": "stocks.availability", "args": {"type": "BED"}, "field": "available_units"},
        ])
        assert written["relies_on"][0]["field"] == "available_units"
        assert written["cited"] == [{
            "tool": "stocks.availability", "args": {"type": "BED"}, "field": "available_units",
            "value": 3, "tick": written["cycle"],
        }]
        assert reader.calls == [("architect", "stocks.availability", {"type": "BED"})]
        assert store.load(db)[0]["cited"] == written["cited"]

    async def test_no_relies_on_means_no_reads_and_no_cited(self, tmp_path):
        reader = _Reader({})
        _, written = await _propose(tmp_path / "q.sqlite3", reader=reader)
        assert "cited" not in written and reader.calls == []

    async def test_dotted_paths_and_list_indexes(self, tmp_path):
        reader = _Reader({("stocks.food-drink", ()): {"rows": [{"count": 9}], "drink": {"units": 40}}})
        _, written = await _propose(tmp_path / "q.sqlite3", reader=reader, relies_on=[
            {"tool": "stocks.food-drink", "field": "rows.0.count"},
            {"tool": "stocks.food-drink", "field": "drink.units"},
        ])
        assert [c["value"] for c in written["cited"]] == [9, 40]

    @pytest.mark.parametrize("result,fragment", [
        ({"other": 1}, "is not in the result"),
        ({"available_units": {"a": 1}}, "not a single number"),
        ({"available_units": None}, "not a single number"),
        ({"available_units": "x" * 200}, "not a single number"),
    ])
    async def test_unusable_citations_refuse_and_write_nothing(self, tmp_path, result, fragment):
        db = tmp_path / "q.sqlite3"
        reader = _Reader({BED: result})
        with pytest.raises(queue_tools.QueueToolError) as exc:
            await _propose(db, reader=reader, relies_on=[
                {"tool": "stocks.availability", "args": {"type": "BED"}, "field": "available_units"},
            ])
        assert fragment in str(exc.value) and "relies_on[0]" in str(exc.value)
        assert not db.exists() or store.load(db) == []

    async def test_a_reader_that_refuses_refuses_the_filing(self, tmp_path):
        db = tmp_path / "q.sqlite3"
        reader = _Reader({BED: queue_tools.FactReadError("stocks.availability: not on your allowlist")})
        with pytest.raises(queue_tools.QueueToolError, match="not on your allowlist"):
            await _propose(db, reader=reader, relies_on=[
                {"tool": "stocks.availability", "args": {"type": "BED"}, "field": "available_units"},
            ])
        assert not db.exists() or store.load(db) == []

    async def test_no_reader_means_citations_cannot_be_read(self, tmp_path):
        with pytest.raises(queue_tools.QueueToolError, match="cannot be read"):
            await _propose(tmp_path / "q.sqlite3", reader=None, relies_on=[{"tool": "t.x", "field": "f"}])

    async def test_more_than_six_or_malformed_entries_refuse(self, tmp_path):
        reader = _Reader({})
        with pytest.raises(queue_tools.QueueToolError, match="at most 6"):
            await _propose(tmp_path / "q.sqlite3", reader=reader,
                           relies_on=[{"tool": "t.x", "field": "f"}] * 7)
        with pytest.raises(queue_tools.QueueToolError, match="relies_on"):
            await _propose(tmp_path / "q.sqlite3", reader=reader, relies_on=[{"tool": "t.x"}])
        with pytest.raises(queue_tools.QueueToolError, match="relies_on"):
            await _propose(tmp_path / "q.sqlite3", reader=reader, relies_on=[{"tool": "t.x", "field": "f", "extra": 1}])
        assert reader.calls == []

    async def test_a_timeout_is_a_distinct_busy_refusal(self, tmp_path, monkeypatch):
        monkeypatch.setattr(queue_tools, "FILING_READ_TIMEOUT_SECONDS", 0.05)

        async def slow(role, tool, arguments):
            await asyncio.sleep(1)

        db = tmp_path / "q.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="server busy, file again"):
            await _propose(db, reader=slow, relies_on=[{"tool": "t.x", "field": "f"}])
        assert not db.exists() or store.load(db) == []

    async def test_a_caller_cannot_supply_cited(self, tmp_path):
        with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
            await _propose(tmp_path / "q.sqlite3", reader=_Reader({}), cited=[])

    async def test_schema_requires_one_cited_entry_per_relies_on(self):
        record = {"relies_on": [{"tool": "t.x", "field": "f"}], "cited": []}
        errors = []
        schema._validate_fact_list(record, "relies_on", errors, cited=False)
        assert errors == []
        full = {"kind": "proposal", **_args(), "role": "architect", "cycle": 1, "snapshot": "tick-1",
                "relies_on": record["relies_on"], "cited": []}
        assert any("one entry per relies_on" in e for e in schema.validate(full))


async def _file(db, role, summary, reader, relies_on=None, **overrides):
    extra = {"relies_on": relies_on} if relies_on else {}
    _, written = await _propose(db, role=role, reader=reader, summary=summary, **extra, **overrides)
    return written


async def _brief(db, reader, role="conductor", **args):
    return await queue_tools.call(
        queue_tools.QUEUE_PENDING_BRIEF, role, args, db_path=db, call_dfhack=_dfhack,
        write_lock=asyncio.Lock(), fact_reader=reader,
    )


class TestPendingBrief:
    async def test_cited_fact_shows_now_only_when_changed(self, tmp_path):
        db = tmp_path / "q.sqlite3"
        cite = [{"tool": "stocks.availability", "args": {"type": "BED"}, "field": "available_units"}]
        await _file(db, "architect", "A", _Reader({BED: {"available_units": 3}}), relies_on=cite)
        # unchanged
        _, unchanged = await _brief(db, _Reader({BED: {"available_units": 3}}))
        row = unchanged["proposals"][0]["cited"][0]
        assert row["value"] == 3 and "now" not in row and "now_unreadable" not in row
        # changed
        _, changed = await _brief(db, _Reader({BED: {"available_units": 0}}))
        assert changed["proposals"][0]["cited"][0]["now"] == 0
        # unreadable is flagged, never shown as unchanged
        _, broken = await _brief(db, _Reader({}))
        assert broken["proposals"][0]["cited"][0]["now_unreadable"] is True

    async def test_identical_reads_are_shared_and_use_the_proposers_role(self, tmp_path):
        db = tmp_path / "q.sqlite3"
        cite = [{"tool": "stocks.availability", "args": {"type": "BED"}, "field": "available_units"}]
        r = _Reader({BED: {"available_units": 3}})
        await _file(db, "architect", "First proposal text", r, relies_on=cite, preconditions=[{"area": "North", "state": "open"}])
        await _file(db, "quartermaster", "Quite another thing entirely", r, relies_on=cite,
                    type="work_order", preconditions=[{"area": "South", "state": "open"}])
        reader = _Reader({BED: {"available_units": 3}})
        await _brief(db, reader)
        assert sorted(c[0] for c in reader.calls) == ["architect", "quartermaster"]  # one read per role, not per proposal
        r2 = _Reader({BED: {"available_units": 3}})
        await _file(db, "architect", "Third unrelated wording here", r2, relies_on=cite,
                    type="corridor", preconditions=[{"area": "East", "state": "open"}])
        reader = _Reader({BED: {"available_units": 3}})
        await _brief(db, reader)
        assert len([c for c in reader.calls if c[0] == "architect"]) == 1

    async def test_capped_at_eight_with_the_true_count(self, tmp_path):
        db = tmp_path / "q.sqlite3"
        words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]
        for i, w in enumerate(words):
            await _file(db, "architect", f"{w} {w[::-1]} completely distinct {i * 7}", None,
                        rationale=f"{w} unique rationale words {w[::-1]} {i}", type="corridor",
                        preconditions=[{"area": f"Place{i}", "state": "open"}])
        _, out = await _brief(db, None)
        assert out["count"] == 10 and out["shown"] == 8 and out["truncated"] is True
        _, small = await _brief(db, None, limit=3)
        assert small["shown"] == 3 and small["count"] == 10

    async def test_overlap_is_flagged_for_same_type_and_site(self, tmp_path):
        db = tmp_path / "q.sqlite3"
        await _file(db, "architect", "Bedroom row one by the wagon", None)
        await _file(db, "architect", "Smoothing of the entry hall walls", None, type="smoothing",
                    rationale="Different rationale text altogether here.")
        await _file(db, "architect", "Place a second workshop beside it", None,
                    rationale="Entirely other reasoning about haul distance.")
        _, out = await _brief(db, None)
        by_id = {p["id"]: p for p in out["proposals"]}
        assert by_id["proposal-0001"]["overlaps"] == ["proposal-0003"]
        assert by_id["proposal-0003"]["overlaps"] == ["proposal-0001"]
        assert "overlaps" not in by_id["proposal-0002"]  # same site, different type

    async def test_decided_block_lists_recent_rulings(self, tmp_path):
        db = tmp_path / "q.sqlite3"
        await _file(db, "architect", "Ruled one", None)
        await queue_tools.call(
            queue_tools.QUEUE_RULE, "overseer",
            {"proposal_id": "proposal-0001", "decision": "reject", "reason": "no", "public_rationale": "no"},
            db_path=db, call_dfhack=_dfhack, write_lock=asyncio.Lock(),
        )
        _, out = await _brief(db, None)
        assert out["count"] == 0
        assert out["decided"]["recent_rulings"][0]["decision"] == "reject"
        assert out["decided"]["open_projects"] == [] and out["decided"]["wip_count"] == 0

    async def test_only_the_conductor_may_call_it(self, tmp_path):
        for role in ("overseer", "architect", "quartermaster", "consultant"):
            with pytest.raises(queue_tools.QueueToolError, match="only the conductor"):
                await _brief(tmp_path / "q.sqlite3", None, role=role)

    async def test_text_is_bounded(self, tmp_path):
        db = tmp_path / "q.sqlite3"
        await _file(db, "architect", "S" * 200 + " tail words", None, rationale="R" * 5000)
        _, out = await _brief(db, None)
        assert len(out["proposals"][0]["rationale"]) <= queue_tools.BRIEF_RATIONALE_MAX


class TestAllowlistsForStageOne:
    """The Overseer rules on cited facts instead of re-reading stocks; proposers
    keep the reads they cite; only the conductor holds the brief."""

    def _roster(self):
        from dfmcp.registry import load_registry
        from dfmcp.roles import load_roster
        from dfmcp import conductor_tools, doctrine_tools, gotchas_tools, knowledge_tools, series_tools

        native = {
            **queue_tools.NATIVE_TOOLS, **doctrine_tools.NATIVE_TOOLS, **series_tools.NATIVE_TOOLS,
            **gotchas_tools.NATIVE_TOOLS, **knowledge_tools.NATIVE_TOOLS, **conductor_tools.NATIVE_TOOLS,
        }
        return load_roster(load_registry(native_tools=native))

    async def test_overseer_has_no_stock_reads_but_proposers_do(self):
        roster = self._roster()
        stock_reads = ("stocks.food-drink", "stocks.seeds", "stocks.availability")
        for tool in stock_reads:
            assert not roster.roles["overseer"].allows(tool), tool
        for role in ("architect", "quartermaster"):
            for tool in stock_reads:
                assert roster.roles[role].allows(tool), (role, tool)

    async def test_only_the_conductor_holds_pending_brief(self):
        roster = self._roster()
        holders = [r for r, perms in roster.roles.items() if perms.allows(queue_tools.QUEUE_PENDING_BRIEF)]
        assert holders == ["conductor"]

    async def test_per_role_tool_counts(self):
        roster = self._roster()
        counts = {r: len(p.read) + len(p.write) for r, p in roster.roles.items()}
        assert counts["conductor"] == 24 and counts["overseer"] == 98
