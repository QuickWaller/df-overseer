"""Direct, transport-free tests of `dfmcp.queue_tools`: the two things the
Phase A review found (2026-09-15) that `dfmcp/tests/test_server.py`'s
full-ASGI-app tests do not exercise well -- a storage-layer failure (an
unwritable queue directory, standing in for `ProtectSystem=strict` denying
a write on VM 103) reaching the caller as a refusal rather than a crash,
and the write-serialisation race that moving `dfqueue.store` calls onto
`asyncio.to_thread` introduced.

This module imports nothing from `mcp` (the SDK), only `dfmcp.queue_tools`
and `dfqueue.store` directly, so unlike `test_server.py` it runs under the
ambient environment too, not only `.venv-dfmcp`.
"""

from __future__ import annotations

import asyncio
import re
import time

import pytest

from dfmcp import queue_tools
from dfqueue import store
from learning.predictions.schema import GRADED_TRUE

pytestmark = pytest.mark.asyncio

_OVERVIEW_JSON = {
    "tier1": {"population": 7},
    "tier2": {"in_game_date": "year 1, month 1, day 1, tick 500", "alerts": []},
}


async def _ok_call_dfhack(tool_id: str, arguments: dict):
    assert tool_id == "overview.get"
    return _OVERVIEW_JSON


def _propose_args(**overrides) -> dict:
    args = {
        "type": "workshop_siting",
        "summary": "Site the next workshop on open ground near the Wagon.",
        "rationale": "Shortest hauling path of the candidates offered.",
        "prediction": {"signal": "fort.population", "op": "gte", "value": 1, "check_after_ticks": 1200},
        "cost": {"estimate": 10, "unit": "dwarf_ticks"},
        "suggested_priority": 3,
        "preconditions": [{"landmark": "Wagon", "state": "exists"}],
        "public_rationale": "Puts the workshop near the wagon.",
    }
    args.update(overrides)
    return args


# ==========================================================================
# Storage errors: sqlite3.Error / OSError become QueueToolError, not a crash
# ==========================================================================


class TestStorageErrorsAreRefusals:
    async def test_propose_against_an_unwritable_directory_is_refused_not_a_crash(self, tmp_path):
        """A file where a directory needs to be, so `dfqueue.store._connect`'s
        own `p.parent.mkdir(parents=True, exist_ok=True)` raises a real
        `NotADirectoryError` (an `OSError` subclass) -- no mocking needed,
        this is the same class of failure `ProtectSystem=strict` denying a
        write would produce on VM 103 (this stream's own Phase B checklist
        flags exactly that gotcha)."""
        blocking_file = tmp_path / "not-a-directory"
        blocking_file.write_text("x", encoding="utf-8")
        bad_db_path = blocking_file / "sub" / "queue.sqlite3"

        with pytest.raises(queue_tools.QueueToolError) as exc:
            await queue_tools.call(
                queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
                db_path=bad_db_path, call_dfhack=_ok_call_dfhack,
                write_lock=asyncio.Lock(),
            )
        assert queue_tools.QUEUE_PROPOSE in str(exc.value)
        assert "queue database is unavailable" in str(exc.value)

    async def test_pending_against_an_unwritable_directory_is_refused_not_a_crash(self, tmp_path):
        blocking_file = tmp_path / "not-a-directory"
        blocking_file.write_text("x", encoding="utf-8")
        bad_db_path = blocking_file / "sub" / "queue.sqlite3"

        with pytest.raises(queue_tools.QueueToolError) as exc:
            await queue_tools.call(
                queue_tools.QUEUE_PENDING, "overseer", {},
                db_path=bad_db_path, call_dfhack=_ok_call_dfhack,
                write_lock=asyncio.Lock(),
            )
        assert "queue database is unavailable" in str(exc.value)

    async def test_a_sqlite_error_from_the_store_is_also_wrapped(self, tmp_path, monkeypatch):
        """Not every storage failure is a bad path -- a real sqlite3.Error
        (a locked file, a corrupt database) must be caught too, not just
        OSError. Simulated directly rather than by actually locking a file
        cross-process, which would be a flaky, platform-dependent test."""
        import sqlite3

        def boom(*args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(store, "append", boom)

        with pytest.raises(queue_tools.QueueToolError) as exc:
            await queue_tools.call(
                queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
                db_path=tmp_path / "queue.sqlite3", call_dfhack=_ok_call_dfhack,
                write_lock=asyncio.Lock(),
            )
        assert "database is locked" in str(exc.value)


# ==========================================================================
# Duplicate-proposal detection: `handoffs/2026-09-28-queue-duplicate-
# proposal-check.md`. Never a refusal -- a near-duplicate is still written,
# flagged with `duplicate_of`, and the tool's own result reports why.
# ==========================================================================


class TestProposeDuplicateDetection:
    async def test_a_near_duplicate_proposal_is_written_and_reported_not_refused(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _first_text, first = await queue_tools.call(
            queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        _second_text, second = await queue_tools.call(
            queue_tools.QUEUE_PROPOSE, "architect",
            _propose_args(summary="Site the next workshop on open ground near the Wagon, please."),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        # Written, not refused: both proposals are in the queue.
        assert store.load(path)[1]["id"] == second["id"]
        # Flagged, and the tool's own result reports which one and why.
        assert second["duplicate_of"] == first["id"]
        assert second["duplicate_reason"]

    async def test_an_unrelated_proposal_of_the_same_type_is_not_flagged(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        await queue_tools.call(
            queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        _text, second = await queue_tools.call(
            queue_tools.QUEUE_PROPOSE, "architect",
            _propose_args(
                summary="Dig a second stairwell down to the ore vein two levels below.",
                rationale="The single stairwell is already a haul bottleneck for miners.",
            ),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "duplicate_of" not in second

    async def test_duplicate_of_cannot_be_smuggled_in_as_a_propose_argument(self, tmp_path):
        """role/id/ts/cycle/snapshot are stamped by the server and refused
        as arguments (`_reject_unknown_arguments`); `duplicate_of` is the
        same kind of server-computed field and must be refused the same way
        -- a caller cannot hand-pick which existing proposal it duplicates."""
        path = tmp_path / "queue.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
            await queue_tools.call(
                queue_tools.QUEUE_PROPOSE, "architect",
                _propose_args(duplicate_of="proposal-0001"),
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )


# ==========================================================================
# Write serialisation: the _next_id race, forced deterministic and fixed
# ==========================================================================


class TestWriteSerialisation:
    async def test_concurrent_raw_appends_without_serialization_can_collide(self, tmp_path, monkeypatch):
        """THE FAILING CASE, run first so its failure is on record before
        the fix's own test claims to pass. Calls `dfqueue.store.append`
        directly through `asyncio.to_thread`, with no lock at all -- the
        exact shape `dfmcp.queue_tools`'s handlers would have if the
        Phase A review's fix were reverted. `store._next_id` is
        monkeypatched to sleep briefly so two concurrent calls are
        deterministically both mid-count when neither has inserted yet,
        rather than relying on timing luck to occasionally reproduce the
        race. This is the failure `_append_locked`'s `write_lock` exists to
        prevent -- see the next test for the same race, through the real
        call path, not reproducing it.
        """
        path = tmp_path / "queue.sqlite3"
        original_next_id = store._next_id

        def slow_next_id(conn, kind):
            time.sleep(0.05)
            return original_next_id(conn, kind)

        monkeypatch.setattr(store, "_next_id", slow_next_id)

        def make_record(i: int) -> dict:
            args = _propose_args(summary=f"Race probe {i}, distinct text so no other field collides.")
            return {
                "kind": "proposal", "role": "architect", "cycle": 1, "snapshot": "tick-1",
                **args,
            }

        async def append_one(i: int):
            return await asyncio.to_thread(store.append, make_record(i), path, game_tick=100)

        results = await asyncio.gather(*(append_one(i) for i in range(5)), return_exceptions=True)

        errors = [r for r in results if isinstance(r, BaseException)]
        oks = [r for r in results if isinstance(r, dict)]
        ids = [r["id"] for r in oks]

        # The race: two concurrent, unserialised appends can compute the
        # same id from `_next_id`'s COUNT(*) before either has inserted, so
        # the second write fails a real UNIQUE constraint (a raw
        # sqlite3.IntegrityError, not a friendly QueueError -- this is
        # `dfqueue.store` used the way it was never meant to be used
        # without an external lock, and this test is what proves that,
        # not an assumption).
        assert errors, (
            f"expected at least one concurrent append to fail on a raw id "
            f"collision without a lock, got {len(oks)} successes and 0 errors "
            f"(ids: {ids}) -- the race did not reproduce this run"
        )

    async def test_concurrent_proposes_through_queue_tools_get_distinct_ids_and_all_land(
        self, tmp_path, monkeypatch
    ):
        """THE PASSING CASE, same forced-slow `_next_id` as the failing case
        above, but now through the real `queue_tools.call` path, which
        serialises every `store.append` behind one shared `asyncio.Lock`
        (`_append_locked`). If this test is run without that lock (e.g. by
        temporarily making `_append_locked` call `store.append` directly,
        unguarded), it fails exactly the way the test above does -- checked
        by hand during this review fix, not asserted here (see this
        stream's report for how)."""
        path = tmp_path / "queue.sqlite3"
        original_next_id = store._next_id

        def slow_next_id(conn, kind):
            time.sleep(0.05)
            return original_next_id(conn, kind)

        monkeypatch.setattr(store, "_next_id", slow_next_id)

        write_lock = asyncio.Lock()

        async def propose_one(i: int):
            args = _propose_args(summary=f"Race probe {i}, distinct text so no other field collides.")
            return await queue_tools.call(
                queue_tools.QUEUE_PROPOSE, "architect", args,
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=write_lock,
            )

        results = await asyncio.gather(*(propose_one(i) for i in range(5)))

        ids = [structured["id"] for _text, structured in results]
        assert len(set(ids)) == 5, f"expected 5 distinct ids, got {ids}"

        written = store.load(path)
        assert len(written) == 5
        assert {r["id"] for r in written} == set(ids)

    async def test_the_write_lock_is_never_held_during_the_dfhack_stamping_call(self, tmp_path):
        """A slow (but eventually successful) call_dfhack must not block a
        second, independent propose from starting its own DFHack call --
        only the store.append portion is meant to serialise. Proven by a
        call_dfhack that blocks on an event the second call sets, then
        waits for both to have started before either finishes: if the lock
        wrongly wrapped the DFHack call too, the second propose's
        call_dfhack would never even start until the first finished
        entirely, and this test would hang until pytest-asyncio's own
        timeout (or deadlock outright under a stricter runner)."""
        path = tmp_path / "queue.sqlite3"
        first_started = asyncio.Event()
        second_started = asyncio.Event()

        async def slow_call_dfhack(tool_id: str, arguments: dict):
            if not first_started.is_set():
                first_started.set()
                # Wait for the second call's own call_dfhack to actually
                # start before letting the first proceed -- only possible
                # if the two DFHack calls run concurrently, i.e. the lock
                # is not held across them.
                await asyncio.wait_for(second_started.wait(), timeout=5)
            else:
                second_started.set()
            return _OVERVIEW_JSON

        write_lock = asyncio.Lock()

        async def propose_one(i: int):
            args = _propose_args(summary=f"Concurrency probe {i}, distinct text.")
            return await queue_tools.call(
                queue_tools.QUEUE_PROPOSE, "architect", args,
                db_path=path, call_dfhack=slow_call_dfhack, write_lock=write_lock,
            )

        results = await asyncio.wait_for(
            asyncio.gather(propose_one(0), propose_one(1)), timeout=5,
        )
        ids = {structured["id"] for _text, structured in results}
        assert len(ids) == 2


# ==========================================================================
# ask / answer / executed -- docs/AGENT-LOOP.md items 4 and 7
# ==========================================================================


async def _propose_and_rule(path, *, decision="accept"):
    """Test helper: write one proposal (architect) and rule on it
    (overseer), through the real queue_tools.call() path, and return
    `(proposal_text, proposal_structured, ruling_text, ruling_structured)`."""
    _p_text, proposal = await queue_tools.call(
        queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
        db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
    )
    _r_text, ruling = await queue_tools.call(
        queue_tools.QUEUE_RULE, "overseer",
        {
            "proposal_id": proposal["id"], "decision": decision,
            "reason": "Charter-clean and worth trying.",
            "public_rationale": "Approved.",
        },
        db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
    )
    return proposal, ruling


class TestExecuted:
    async def test_executed_arms_the_prediction_and_is_overseer_only(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        proposal, ruling = await _propose_and_rule(path)
        await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer",
            {**_project_args(ruling["id"]), "steps": []},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        text, structured = await queue_tools.call(
            queue_tools.QUEUE_EXECUTED, "overseer",
            {
                "ruling_id": ruling["id"],
                "actions": [{"tool": "workshop.build", "outcome": "success"}],
                "notes": "Built as ruled.",
            },
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "<executed" in text
        assert structured["ruling_id"] == ruling["id"]

        due = store.pending_due(path, structured["cycle"] + 1200)
        assert len(due) == 1
        assert due[0]["due_game_tick"] == structured["cycle"] + 1200

    async def test_executed_without_a_project_is_refused_with_a_model_facing_message(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)

        with pytest.raises(queue_tools.QueueToolError) as exc:
            await queue_tools.call(
                queue_tools.QUEUE_EXECUTED, "overseer",
                {
                    "ruling_id": ruling["id"],
                    "actions": [{"tool": "workshop.build", "outcome": "success"}],
                    "notes": "Built as ruled.",
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )
        message = str(exc.value)
        assert "queue.project" in message and "from_ruling" in message
        assert "step_id" in message

    async def test_older_accepted_ruling_gets_a_project_then_executes_with_step_id(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        lock = asyncio.Lock()
        # Refused first (the ruling pre-dates any project, like proposal-0013).
        with pytest.raises(queue_tools.QueueToolError, match="queue.project"):
            await queue_tools.call(
                queue_tools.QUEUE_EXECUTED, "overseer",
                {"ruling_id": ruling["id"],
                 "actions": [{"tool": "construction.mine-vein", "outcome": "success",
                              "targets": ["ring-13-ore-1", "ring-13-ore-2"],
                              "target_state": "done"}],
                 "notes": "x"},
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=lock,
            )
        await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=lock,
        )
        with pytest.raises(queue_tools.QueueToolError, match="step_id: required"):
            await queue_tools.call(
                queue_tools.QUEUE_EXECUTED, "overseer",
                {"ruling_id": ruling["id"],
                 "actions": [{"tool": "construction.mine-vein", "outcome": "success"}],
                 "notes": "x"},
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=lock,
            )
        _text, structured = await queue_tools.call(
            queue_tools.QUEUE_EXECUTED, "overseer",
            {"ruling_id": ruling["id"], "step_id": "s1",
             "actions": [{"tool": "construction.mine-vein", "outcome": "success",
                          "targets": ["ring-13-ore-1", "ring-13-ore-2"],
                          "target_state": "done"}],
             "notes": "x"},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=lock,
        )
        assert structured["step_id"] == "s1"

    async def test_executed_refuses_role_arguments(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)

        with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
            await queue_tools.call(
                queue_tools.QUEUE_EXECUTED, "overseer",
                {
                    "ruling_id": ruling["id"], "role": "architect",
                    "actions": [{"tool": "workshop.build", "outcome": "success"}],
                    "notes": "Trying to smuggle a role argument.",
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_executed_against_a_nonexistent_ruling_is_refused(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="does not refer to an existing ruling"):
            await queue_tools.call(
                queue_tools.QUEUE_EXECUTED, "overseer",
                {
                    "ruling_id": "ruling-9999",
                    "actions": [{"tool": "workshop.build", "outcome": "success"}],
                    "notes": "No such ruling.",
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )


class _AdvancingOverview:
    """A `call_dfhack` fake that answers `overview.get` with `before` until
    `.advanced` is set True, then with `after` -- lets a test write and
    execute a proposal at one game tick, then grade it from a later one,
    exactly the two-reads-in-sequence shape `queue.grade` itself performs
    (once to stamp `queue.executed`'s own cycle, once inside the grading
    pass to read the fort's current tick)."""

    def __init__(self, before: dict, after: dict):
        self._before = before
        self._after = after
        self.advanced = False
        self.calls: list = []

    async def __call__(self, tool_id: str, arguments: dict):
        self.calls.append(tool_id)
        assert tool_id == "overview.get", f"unexpected tool_id {tool_id!r}"
        return self._after if self.advanced else self._before


def _dated_overview(tick: int, *, population: int = 7) -> dict:
    return {
        "tier1": {"population": population},
        "tier2": {"in_game_date": f"year 0, month 1, day 1, tick {tick}", "alerts": []},
    }


class TestGrade:
    """docs/AGENT-LOOP.md item 2, handoffs/2026-09-22-loop-conductor-service.md:
    queue.grade runs dfqueue.grade.run_grading_cycle over MCP. These tests
    exercise the real queue_tools.call() path end to end (propose, rule,
    execute, then grade), never dfqueue.grade directly, so they also prove
    the async/sync call_tool bridge (_grade's own sync_call_tool) actually
    reaches DFHack through the injected call_dfhack."""

    async def test_grades_a_due_prediction_through_the_real_call_path(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        call_dfhack = _AdvancingOverview(_dated_overview(100), _dated_overview(200))
        lock = asyncio.Lock()

        _p_text, proposal = await queue_tools.call(
            queue_tools.QUEUE_PROPOSE, "architect",
            _propose_args(prediction={
                "signal": "fort.population", "op": "gte", "value": 1, "check_after_ticks": 50,
            }),
            db_path=path, call_dfhack=call_dfhack, write_lock=lock,
        )
        _r_text, ruling = await queue_tools.call(
            queue_tools.QUEUE_RULE, "overseer",
            {
                "proposal_id": proposal["id"], "decision": "accept",
                "reason": "Charter-clean.", "public_rationale": "Approved.",
            },
            db_path=path, call_dfhack=call_dfhack, write_lock=lock,
        )
        await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer",
            {**_project_args(ruling["id"]), "steps": []},
            db_path=path, call_dfhack=call_dfhack, write_lock=lock,
        )
        await queue_tools.call(
            queue_tools.QUEUE_EXECUTED, "overseer",
            {
                "ruling_id": ruling["id"],
                "actions": [{"tool": "workshop.build", "outcome": "success"}],
                "notes": "Built as ruled.",
            },
            db_path=path, call_dfhack=call_dfhack, write_lock=lock,
        )
        # due_game_tick = 100 (execution tick) + 50 = 150, still before 100 -- not due yet
        # (current tick is still 100 at this point: call_dfhack has not advanced).

        call_dfhack.advanced = True  # the fort has moved on to tick 200
        text, structured = await queue_tools.call(
            queue_tools.QUEUE_GRADE, "conductor", {},
            db_path=path, call_dfhack=call_dfhack, write_lock=lock,
        )

        assert structured["current_game_tick"] == 200
        assert structured["graded_count"] == 1
        assert structured["graded"][0]["id"]
        assert structured["graded"][0]["status"] == GRADED_TRUE
        assert structured["unexecuted_count"] == 0
        assert "graded_count" in text  # the text block is the same structured payload, printed

        # Idempotent: a second call the same cycle grades nothing more.
        _text2, structured2 = await queue_tools.call(
            queue_tools.QUEUE_GRADE, "conductor", {},
            db_path=path, call_dfhack=call_dfhack, write_lock=lock,
        )
        assert structured2["graded_count"] == 0

    async def test_reports_an_accepted_but_unexecuted_proposal(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        proposal, _ruling = await _propose_and_rule(path)

        _text, structured = await queue_tools.call(
            queue_tools.QUEUE_GRADE, "conductor", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert structured["unexecuted_count"] == 1
        assert structured["unexecuted_proposal_ids"] == [proposal["id"]]
        assert structured["graded_count"] == 0  # never scored as a miss

    async def test_grade_refuses_unexpected_arguments(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
            await queue_tools.call(
                queue_tools.QUEUE_GRADE, "conductor", {"limit": 5},
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_grade_refuses_when_dfhack_is_unreachable(self, tmp_path):
        path = tmp_path / "queue.sqlite3"

        async def _broken_call_dfhack(tool_id, arguments):
            raise RuntimeError("DFHack connection reset")

        with pytest.raises(queue_tools.QueueToolError, match="grading failed"):
            await queue_tools.call(
                queue_tools.QUEUE_GRADE, "conductor", {},
                db_path=path, call_dfhack=_broken_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_grade_against_an_unwritable_directory_is_refused_not_a_crash(self, tmp_path):
        blocking_file = tmp_path / "not-a-directory"
        blocking_file.write_text("x", encoding="utf-8")
        bad_db_path = blocking_file / "sub" / "queue.sqlite3"

        with pytest.raises(queue_tools.QueueToolError, match="queue database is unavailable"):
            await queue_tools.call(
                queue_tools.QUEUE_GRADE, "conductor", {},
                db_path=bad_db_path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )


class TestAskAnswer:
    async def test_a_lookup_ask_from_the_architect_and_the_consultants_answer(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        ask_text, ask = await queue_tools.call(
            queue_tools.QUEUE_ASK, "architect",
            {"question": "Does soil under a workshop ever stall construction?"},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "<ask" in ask_text
        assert "proposal_id" not in ask

        # Before an answer, the Consultant's own queue.pending lists it.
        _pending_text, pending = await queue_tools.call(
            queue_tools.QUEUE_PENDING, "consultant", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert pending["ask_ids"] == [ask["id"]]

        answer_text, answer = await queue_tools.call(
            queue_tools.QUEUE_ANSWER, "consultant",
            {"ask_id": ask["id"], "answer": "No, only its own material requirements matter."},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "<answer" in answer_text
        assert answer["ask_id"] == ask["id"]

        # Answered, so no longer open.
        _pending_text2, pending2 = await queue_tools.call(
            queue_tools.QUEUE_PENDING, "consultant", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert pending2["ask_ids"] == []

    async def test_queue_pending_for_a_non_consultant_role_is_unchanged(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _text, proposal = await queue_tools.call(
            queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        _pending_text, pending = await queue_tools.call(
            queue_tools.QUEUE_PENDING, "overseer", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert pending["proposal_ids"] == [proposal["id"]]
        assert "ask_ids" not in pending

    async def test_a_fact_check_from_the_overseer_blocks_ruling_until_answered(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _p_text, proposal = await queue_tools.call(
            queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        _ask_text, ask = await queue_tools.call(
            queue_tools.QUEUE_ASK, "overseer",
            {"question": "Is this hauling-distance claim right?", "proposal_id": proposal["id"]},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        with pytest.raises(queue_tools.QueueToolError, match="open fact-check"):
            await queue_tools.call(
                queue_tools.QUEUE_RULE, "overseer",
                {
                    "proposal_id": proposal["id"], "decision": "accept",
                    "reason": "Looks right.", "public_rationale": "Approved.",
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

        await queue_tools.call(
            queue_tools.QUEUE_ANSWER, "consultant",
            {"ask_id": ask["id"], "answer": "Confirmed against the live layout."},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        _r_text, ruling = await queue_tools.call(
            queue_tools.QUEUE_RULE, "overseer",
            {
                "proposal_id": proposal["id"], "decision": "accept",
                "reason": "Looks right.", "public_rationale": "Approved.",
            },
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert ruling["decision"] == "accept"

    async def test_ask_refuses_role_argument_smuggling(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
            await queue_tools.call(
                queue_tools.QUEUE_ASK, "architect",
                {"question": "A question.", "role": "overseer"},
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )


# ==========================================================================
# queue.overview: fix 1 (handoffs/2026-09-22-loop-conductor-fixes.md) --
# role-independent, so the conductor (which authenticates as "conductor",
# never "consultant") can see BOTH pending proposals and open asks in one
# read, the whole ask/wake/answer/ruling loop through the conductor's own
# view of the queue.
# ==========================================================================


class TestQueueOverview:
    async def test_the_full_ask_wake_answer_ruling_loop_through_queue_overview(self, tmp_path):
        """The handoff's own test requirement: ask, wake, answer, then the
        ruling going through -- "wake" here means what conductor/triage.py
        actually wakes on: queue.overview's own asks.count, proven at this
        (queue_tools) layer since that is where the signal is produced."""
        path = tmp_path / "queue.sqlite3"
        _p_text, proposal = await queue_tools.call(
            queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        _ask_text, ask = await queue_tools.call(
            queue_tools.QUEUE_ASK, "overseer",
            {"question": "Is this hauling-distance claim right?", "proposal_id": proposal["id"]},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        # ASK: the conductor's own role-independent read sees both halves,
        # regardless of authenticating as "conductor" -- never "consultant"
        # or "overseer", which is exactly what queue.pending could not do.
        _ov_text, overview = await queue_tools.call(
            queue_tools.QUEUE_OVERVIEW, "conductor", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert overview["proposals"]["count"] == 1
        assert overview["proposals"]["proposal_ids"] == [proposal["id"]]
        # WAKE: this is the signal conductor/cycle.py turns into
        # Signals.open_ask_for_consultant -- non-zero, so the Consultant
        # would wake.
        assert overview["asks"]["count"] == 1
        assert overview["asks"]["ask_ids"] == [ask["id"]]

        # The ruling is blocked while this fact-check is open (same
        # invariant TestAskAnswer's own fact-check test proves; re-checked
        # here because queue.overview's own read must agree with it).
        with pytest.raises(queue_tools.QueueToolError, match="open fact-check"):
            await queue_tools.call(
                queue_tools.QUEUE_RULE, "overseer",
                {
                    "proposal_id": proposal["id"], "decision": "accept",
                    "reason": "Looks right.", "public_rationale": "Approved.",
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

        # ANSWER.
        await queue_tools.call(
            queue_tools.QUEUE_ANSWER, "consultant",
            {"ask_id": ask["id"], "answer": "Confirmed against the live layout."},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        # queue.overview now reports no open asks -- the Consultant would
        # not be woken again for this one.
        _ov_text2, overview2 = await queue_tools.call(
            queue_tools.QUEUE_OVERVIEW, "conductor", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert overview2["asks"]["count"] == 0
        assert overview2["proposals"]["count"] == 1  # the proposal is still pending

        # RULING now goes through.
        _r_text, ruling = await queue_tools.call(
            queue_tools.QUEUE_RULE, "overseer",
            {
                "proposal_id": proposal["id"], "decision": "accept",
                "reason": "Looks right.", "public_rationale": "Approved.",
            },
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert ruling["decision"] == "accept"

        # And the proposal is no longer pending, through the same read.
        _ov_text3, overview3 = await queue_tools.call(
            queue_tools.QUEUE_OVERVIEW, "conductor", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert overview3["proposals"]["count"] == 0

    async def test_overview_is_empty_on_a_fresh_queue(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _text, overview = await queue_tools.call(
            queue_tools.QUEUE_OVERVIEW, "conductor", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert overview == {
            "proposals": {"count": 0, "proposal_ids": []},
            "asks": {"count": 0, "ask_ids": [], "to": {}},
        }

    async def test_overview_ignores_the_caller_role_entirely(self, tmp_path):
        """Unlike queue.pending, the role argument changes nothing about
        what this tool returns -- proven by calling it as a role that is
        not even "conductor" and getting the identical structured result."""
        path = tmp_path / "queue.sqlite3"
        await queue_tools.call(
            queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        _t1, as_conductor = await queue_tools.call(
            queue_tools.QUEUE_OVERVIEW, "conductor", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        _t2, as_someone_else = await queue_tools.call(
            queue_tools.QUEUE_OVERVIEW, "architect", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert as_conductor == as_someone_else

    async def test_overview_refuses_unexpected_arguments(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
            await queue_tools.call(
                queue_tools.QUEUE_OVERVIEW, "conductor", {"role": "consultant"},
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_overview_refuses_a_non_positive_limit(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="positive integer"):
            await queue_tools.call(
                queue_tools.QUEUE_OVERVIEW, "conductor", {"limit": 0},
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_overview_against_an_unwritable_directory_is_refused_not_a_crash(self, tmp_path):
        blocking_file = tmp_path / "not-a-directory"
        blocking_file.write_text("x", encoding="utf-8")
        bad_db_path = blocking_file / "sub" / "queue.sqlite3"

        with pytest.raises(queue_tools.QueueToolError, match="queue database is unavailable"):
            await queue_tools.call(
                queue_tools.QUEUE_OVERVIEW, "conductor", {},
                db_path=bad_db_path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )


# ==========================================================================
# queue.escalate: fix 3 (handoffs/2026-09-22-loop-conductor-fixes.md) --
# how the Overseer alerts the human, mechanically, via a real queue record.
# ==========================================================================


class TestQueueEscalate:
    async def test_the_overseer_can_escalate_with_a_reason(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        text, escalation = await queue_tools.call(
            queue_tools.QUEUE_ESCALATE, "overseer",
            {"reason": "An aquifer breach would be required; no playbook covers this."},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "<escalation" in text
        assert escalation["kind"] == "escalation"
        assert escalation["role"] == "overseer"
        assert escalation["reason"] == "An aquifer breach would be required; no playbook covers this."

    async def test_escalate_is_refused_for_a_role_other_than_the_sole_writer(self, tmp_path):
        """dfqueue.schema.validate's own role==sole_writer() check for
        ESCALATION -- the second, write-time layer, independent of
        dfmcp.roles's load-time sole_writer_only check (dfmcp/tests/
        test_roles.py covers that layer)."""
        path = tmp_path / "queue.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="sole_writer"):
            await queue_tools.call(
                queue_tools.QUEUE_ESCALATE, "architect",
                {"reason": "Trying to escalate without being the Overseer."},
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_escalate_refuses_an_empty_reason(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="non-empty string"):
            await queue_tools.call(
                queue_tools.QUEUE_ESCALATE, "overseer", {"reason": ""},
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_escalate_refuses_unexpected_arguments(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
            await queue_tools.call(
                queue_tools.QUEUE_ESCALATE, "overseer",
                {"reason": "x", "public_rationale": "not a field on this record"},
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_an_escalation_does_not_appear_in_queue_pending_or_overview(self, tmp_path):
        """An escalation is not a proposal and not an ask -- it must not
        pollute either count queue.pending/queue.overview report."""
        path = tmp_path / "queue.sqlite3"
        await queue_tools.call(
            queue_tools.QUEUE_ESCALATE, "overseer", {"reason": "x"},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        _text, overview = await queue_tools.call(
            queue_tools.QUEUE_OVERVIEW, "conductor", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert overview["proposals"]["count"] == 0
        assert overview["asks"]["count"] == 0


# ==========================================================================
# queue.project / queue.project_status --
# handoffs/2026-09-30-project-mcp-tools.md, design
# research/2026-09-28-job-dependency-graph.md §4.1/§6.
# ==========================================================================

_COORD_PATTERN = re.compile(
    r"\b[xyz]\s*=\s*-?\d+\b"
    r"|[\(\[]\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*[\)\]]",
    re.IGNORECASE,
)


def _project_args(from_ruling: str, **overrides) -> dict:
    """A two-step project (mine-vein then build, `dfqueue.tests._helpers.
    make_project`'s own worked example, ids kept short and unique per project
    here since several tests write more than one project into the same
    queue)."""
    args = {
        "from_ruling": from_ruling,
        "summary": "Recover the exposed hematite and finish the office ring's walls.",
        "because": (
            "The ring's own smoothing pass exposed a vein tile that a plain "
            "wall would seal."
        ),
        "steps": [
            {
                "id": "s1",
                "tool": "construction.mine-vein",
                "args": {},
                "targets": {"set": ["ring-13-ore-1", "ring-13-ore-2"]},
                "requires": [],
                "trigger": "all_success",
                "prefer_after": [],
                "guards": "default",
            },
            {
                "id": "s2",
                "tool": "construction.build",
                "args": {"kind": "Wall"},
                "targets": {"from_step": "s1", "select": "done"},
                "requires": ["s1"],
                "trigger": "all_done",
                "prefer_after": [],
                "guards": "default",
            },
        ],
    }
    args.update(overrides)
    return args


class TestProject:
    async def test_overseer_creates_a_project_from_an_accepted_ruling(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)

        text, structured = await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "<project" in text
        assert structured["from_ruling"] == ruling["id"]
        assert structured["kind"] == "project"
        assert [s["id"] for s in structured["steps"]] == ["s1", "s2"]

    async def test_project_refuses_a_ruling_with_no_accepted_decision(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path, decision="reject")

        with pytest.raises(queue_tools.QueueToolError, match="not.*accept"):
            await queue_tools.call(
                queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_second_project_for_the_same_ruling_is_refused(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        with pytest.raises(queue_tools.QueueToolError, match="already has a project"):
            await queue_tools.call(
                queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_project_refuses_role_arguments(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)

        with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
            await queue_tools.call(
                queue_tools.QUEUE_PROJECT, "overseer",
                {**_project_args(ruling["id"]), "role": "architect"},
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    # Rule-6 load-time refusal (a non-sole-writer role granted queue.project
    # refuses to load its roster) is covered in
    # dfmcp/tests/test_roles.py::test_rule6_also_restricts_queue_project_to_the_sole_writer,
    # not here: queue_tools.call() itself never consults dfmcp.roles (that
    # check happens one layer up, in dfmcp/server.py, before this module is
    # ever reached). dfqueue.schema's own write-time role check is exercised
    # directly in dfqueue/tests/test_schema.py::test_project_role_restricted_to_sole_writer.

    async def test_project_accepts_public_title_rationale_urgency_and_step_label(self, tmp_path):
        """`handoffs/2026-10-02-queue-display-fields.md`: the new public
        display fields reach `dfqueue.store` through this tool unchanged."""
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)

        args = _project_args(ruling["id"])
        args["steps"][0]["label"] = "Mine the vein"
        args["public_title"] = "Recover the hematite vein"
        args["public_rationale"] = "The ring's own smoothing pass exposed ore."
        args["urgency"] = "elevated"

        _text, structured = await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", args,
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert structured["public_title"] == "Recover the hematite vein"
        assert structured["public_rationale"] == "The ring's own smoothing pass exposed ore."
        assert structured["urgency"] == "elevated"
        assert structured["steps"][0]["label"] == "Mine the vein"

    async def test_project_rejects_a_bad_urgency(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        args = _project_args(ruling["id"])
        args["urgency"] = "urgent"

        with pytest.raises(queue_tools.QueueToolError, match="urgency"):
            await queue_tools.call(
                queue_tools.QUEUE_PROJECT, "overseer", args,
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_project_rejects_a_too_long_public_title(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        args = _project_args(ruling["id"])
        args["public_title"] = "x" * 61

        with pytest.raises(queue_tools.QueueToolError, match="public_title"):
            await queue_tools.call(
                queue_tools.QUEUE_PROJECT, "overseer", args,
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )


class TestProjectStatus:
    async def test_status_renders_one_line_per_project_and_never_a_coordinate(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _p1, r1 = await _propose_and_rule(path)
        _p2, r2 = await _propose_and_rule(
            path,
        )
        await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(r1["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer",
            _project_args(r2["id"], summary="A second, unrelated plan."),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        text, structured = await queue_tools.call(
            queue_tools.QUEUE_PROJECT_STATUS, "overseer", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        lines = text.splitlines()
        assert len(lines) == 2  # one line per project, never the whole graph
        assert structured["count"] == 2
        assert not _COORD_PATTERN.search(text)

    async def test_status_with_project_id_reads_just_that_one(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _p1, r1 = await _propose_and_rule(path)
        _text, project = await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(r1["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        text, structured = await queue_tools.call(
            queue_tools.QUEUE_PROJECT_STATUS, "overseer", {"project_id": project["id"]},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert structured["count"] == 1
        assert structured["project_ids"] == [project["id"]]
        assert text.startswith(project["id"])

    async def test_status_against_a_nonexistent_project_id_is_refused(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="no such project"):
            await queue_tools.call(
                queue_tools.QUEUE_PROJECT_STATUS, "overseer", {"project_id": "project-9999"},
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_status_with_no_projects_at_all(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        text, structured = await queue_tools.call(
            queue_tools.QUEUE_PROJECT_STATUS, "overseer", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert structured["count"] == 0
        assert text == "(no projects)"


class TestExecutedStepId:
    """`queue.executed`'s `step_id` plus per-action `targets`/`target_state`
    (design §4.4's target-level state fold), reachable end to end through
    the real MCP tool layer -- `dfmcp/queue_tools.py`'s own `_EXECUTED_FIELDS`/
    `_EXECUTED_SCHEMA` used to strip `step_id` entirely (refused as an
    'unexpected argument') even though `dfqueue.schema`/`dfqueue.store`
    already supported it end to end."""

    async def test_executed_with_step_id_round_trips_into_the_target_state_fold(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        _p_text, project = await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        step_id = project["steps"][0]["id"]

        text, structured = await queue_tools.call(
            queue_tools.QUEUE_EXECUTED, "overseer",
            {
                "ruling_id": ruling["id"],
                "step_id": step_id,
                "actions": [{
                    "tool": "construction.mine-vein",
                    "outcome": "success",
                    "targets": ["ring-13-ore-1", "ring-13-ore-2"],
                    "target_state": "done",
                }],
                "notes": "Mined both known ore tiles.",
            },
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "<executed" in text
        assert structured["step_id"] == step_id

        status = await asyncio.to_thread(store.project_status, path, project["id"])
        assert status["counts"]["done"] == 2

    async def test_executed_step_id_not_belonging_to_the_project_is_refused(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        with pytest.raises(queue_tools.QueueToolError, match="not a step"):
            await queue_tools.call(
                queue_tools.QUEUE_EXECUTED, "overseer",
                {
                    "ruling_id": ruling["id"],
                    "step_id": "no-such-step",
                    "actions": [{"tool": "construction.mine-vein", "outcome": "success"}],
                    "notes": "Wrong step id.",
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_executed_targets_without_target_state_is_refused(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)

        with pytest.raises(queue_tools.QueueToolError, match="targets.*target_state"):
            await queue_tools.call(
                queue_tools.QUEUE_EXECUTED, "overseer",
                {
                    "ruling_id": ruling["id"],
                    "actions": [{
                        "tool": "construction.mine-vein", "outcome": "success",
                        "targets": ["ring-13-ore-1"],
                    }],
                    "notes": "targets given with no target_state.",
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_executed_refuses_a_tool_mismatched_with_the_steps_own_tool(self, tmp_path):
        """`handoffs/2026-10-01-queue-bugs-and-amend.md` item 2, reachable
        end to end through the real MCP tool layer."""
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        _p_text, project = await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        step_id = project["steps"][0]["id"]

        with pytest.raises(queue_tools.QueueToolError, match="does not match step"):
            await queue_tools.call(
                queue_tools.QUEUE_EXECUTED, "overseer",
                {
                    "ruling_id": ruling["id"],
                    "step_id": step_id,
                    "actions": [{"tool": "workshop.build", "outcome": "success"}],
                    "notes": "Wrong tool for this step.",
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_executed_refuses_a_step_whose_requires_are_unsatisfied(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        _p_text, project = await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        s2 = project["steps"][1]["id"]  # requires s1, never executed yet

        with pytest.raises(queue_tools.QueueToolError, match="not yet satisfied"):
            await queue_tools.call(
                queue_tools.QUEUE_EXECUTED, "overseer",
                {
                    "ruling_id": ruling["id"],
                    "step_id": s2,
                    "actions": [{"tool": "construction.build", "outcome": "success"}],
                    "notes": "s1 never ran.",
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )


class TestAmendAbandon:
    """`handoffs/2026-10-01-queue-bugs-and-amend.md` item 3
    (`research/2026-09-30-goal-tree-red-team.md` F-3), reachable end to end
    through the real MCP tool layer -- `queue.amend`/`queue.abandon`."""

    async def test_amend_writes_a_new_version_and_status_reports_it(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        _p_text, project = await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        text, amend = await queue_tools.call(
            queue_tools.QUEUE_AMEND, "overseer",
            {
                "project_id": project["id"],
                "reason": "s2's wall isn't needed; the tile is already enclosed.",
                "drops": ["s2"],
                "steps": [project["steps"][0]],
            },
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "<amend" in text
        assert amend["kind"] == "amend"

        status_text, structured = await queue_tools.call(
            queue_tools.QUEUE_PROJECT_STATUS, "overseer", {"project_id": project["id"]},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "(v2)" in status_text
        assert structured["count"] == 1

    async def test_amend_refuses_role_arguments(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        _p_text, project = await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
            await queue_tools.call(
                queue_tools.QUEUE_AMEND, "overseer",
                {
                    "project_id": project["id"], "reason": "Testing a stray argument.",
                    "steps": project["steps"], "role": "architect",
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_amend_against_an_unknown_project_is_refused(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="does not refer to an existing project"):
            await queue_tools.call(
                queue_tools.QUEUE_AMEND, "overseer",
                {
                    "project_id": "project-9999", "reason": "No such project.",
                    "steps": [{
                        "id": "s1", "tool": "construction.mine-vein", "targets": {"set": ["t1"]},
                    }],
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_abandon_marks_the_project_abandoned_with_its_reason(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        _p_text, project = await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        text, abandon = await queue_tools.call(
            queue_tools.QUEUE_ABANDON, "overseer",
            {"project_id": project["id"], "reason": "The vein played out."},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "<abandon" in text
        assert abandon["kind"] == "abandon"

        status_text, structured = await queue_tools.call(
            queue_tools.QUEUE_PROJECT_STATUS, "overseer", {"project_id": project["id"]},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "abandoned" in status_text
        assert "The vein played out." in status_text
        assert structured["count"] == 1

    async def test_abandon_refuses_a_second_call(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        _p_text, project = await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        await queue_tools.call(
            queue_tools.QUEUE_ABANDON, "overseer",
            {"project_id": project["id"], "reason": "First abandonment."},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        with pytest.raises(queue_tools.QueueToolError, match="already abandoned"):
            await queue_tools.call(
                queue_tools.QUEUE_ABANDON, "overseer",
                {"project_id": project["id"], "reason": "Second attempt."},
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    # Rule-6 load-time refusal (a non-sole-writer role granted queue.amend/
    # queue.abandon refuses to load its roster) belongs in
    # dfmcp/tests/test_roles.py, alongside queue.project's own equivalent
    # test (not duplicated here); dfqueue.schema's own write-time role check
    # is exercised directly in dfqueue/tests/test_schema.py.

    async def test_amend_accepts_public_rationale(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        _p_text, project = await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        _text, amend = await queue_tools.call(
            queue_tools.QUEUE_AMEND, "overseer",
            {
                "project_id": project["id"],
                "reason": "s2's wall isn't needed; the tile is already enclosed.",
                "public_rationale": "Dropping the wall step; the tile is already enclosed.",
                "drops": ["s2"],
                "steps": [project["steps"][0]],
            },
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert amend["public_rationale"] == "Dropping the wall step; the tile is already enclosed."

    async def test_amend_label_only_change_round_trips_through_the_tool(self, tmp_path):
        """The fresh-id rule's label exclusion (`dfqueue.store._canonical_step_json`),
        exercised end to end through the real MCP tool rather than only
        `dfqueue.tests.test_store` directly."""
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        _p_text, project = await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        s1, s2 = project["steps"][0], dict(project["steps"][1])
        relabelled_s1 = dict(s1)
        relabelled_s1["label"] = "Mine the vein"

        _text, amend = await queue_tools.call(
            queue_tools.QUEUE_AMEND, "overseer",
            {
                "project_id": project["id"],
                "reason": "Labelling the steps for the stream page; nothing else changes.",
                "steps": [relabelled_s1, s2],
            },
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert [s["id"] for s in amend["steps"]] == [s1["id"], s2["id"]]

    async def test_abandon_accepts_public_rationale(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)
        _p_text, project = await queue_tools.call(
            queue_tools.QUEUE_PROJECT, "overseer", _project_args(ruling["id"]),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        _text, abandon = await queue_tools.call(
            queue_tools.QUEUE_ABANDON, "overseer",
            {
                "project_id": project["id"], "reason": "The vein played out.",
                "public_rationale": "The vein played out; nothing left to mine.",
            },
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert abandon["public_rationale"] == "The vein played out; nothing left to mine."
