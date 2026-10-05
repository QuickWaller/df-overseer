"""The Board's "Acted" list on job lines and the Lesson panel in a turn, run
through node on the real web/stream/app.js (skipped without node)."""
from dfqueue.tests.test_site_js_threads import _run, P

EXEC = {
    "id": "executed-1", "seq": 3, "kind": "executed", "role": "overseer", "reply_to": "proposal-1",
    "thread": "proposal-1", "step_label": "Dig shell", "step_targets": 2, "step_total": None,
    "step_outcome": "failed", "game_date": "3 Granite, year 31",
    "actions": [
        {"tool": "diggable.dig-stair", "name": "Diggable dig stair", "targets": 2, "outcome": "ok", "reason": None},
        {"tool": "workshop.build", "name": "Workshop build", "targets": 1, "outcome": "failed",
         "reason": "Every barrel is full of plants."},
        {"tool": "trees.fell", "name": "Trees fell", "targets": 0, "outcome": "ok", "reason": None},
    ],
}

WALK = r"""
  const seen = []; const walk = (n) => { if (n.textContent) seen.push(n.textContent); n.children.forEach(walk); };
"""


def test_acted_rows_name_the_tool_target_count_and_outcome():
    rows = _run("return actedRows(DATA.actions);", EXEC)
    assert rows == [
        {"name": "Diggable dig stair", "failed": False, "note": "2 targets · ok"},
        {"name": "Workshop build", "failed": True, "note": "1 target · failed: Every barrel is full of plants."},
        {"name": "Trees fell", "failed": False, "note": "no targets · ok"},
    ]
    assert _run("return actedRows(undefined);", {}) == []


def test_a_job_line_gets_a_collapsed_acted_expander_only_when_it_has_actions():
    expr = WALK + r"""
      const page = Object.create(StreamPage.prototype);
      page.projects = { projects: {}, thread_to_project: {} };
      page.runs = null;
      const withActs = page._receipt(DATA.item);
      walk(withActs);
      const bare = page._receipt({ ...DATA.item, actions: [] });
      return { seen, cls: withActs.className, bareCls: bare.className };
    """
    res = _run(expr, {"item": EXEC})
    assert res["cls"] == "fevent-wrap" and res["bareCls"].startswith("fevent")
    assert "Acted · 3" in res["seen"] and "Workshop build" in res["seen"]
    assert "1 target · failed: Every barrel is full of plants." in res["seen"]


def test_lesson_text_wording():
    cases = [
        {"kind": "new", "title": "Soil never smooths", "result": None},
        {"kind": "outcome", "title": "Two miners", "result": "worked"},
        {"kind": "outcome", "title": "Two miners", "result": "did_not_work"},
        {"kind": "outcome", "title": "Two miners", "result": None},
    ]
    assert _run("return DATA.map(lessonText);", cases) == [
        "Noted: Soil never smooths",
        "Confirmed \u201cTwo miners\u201d worked",
        "Found \u201cTwo miners\u201d did not work",
        "Recorded an outcome on \u201cTwo miners\u201d",
    ]


def test_a_lesson_panel_sits_inside_its_runs_turn_and_only_in_the_threads_it_touched():
    from dfqueue.tests.test_site_js_threads import RUNS, THREAD
    lessons = {"lessons": [
        {"run_id": "run-1", "thread": "proposal-1", "role": "architect", "kind": "new", "gotcha_id": "g1", "title": "Soil never smooths", "result": None, "at": "t"},
        {"run_id": "run-1", "thread": "proposal-9", "role": "architect", "kind": "new", "gotcha_id": "g1", "title": "Soil never smooths", "result": None, "at": "t"},
        {"run_id": "run-2", "thread": "proposal-1", "role": "overseer", "kind": "outcome", "gotcha_id": "g2", "title": "Two miners", "result": "worked", "at": "t"},
    ]}
    expr = WALK + r"""
      const page = Object.create(StreamPage.prototype);
      page.projects = { projects: {}, thread_to_project: {} };
      page.runs = DATA.runs; page.lessons = DATA.lessons;
      const thread = page._conversationEl(DATA.items);
      walk(thread[0]);
      const kinds = []; const walk2 = (n) => { if (n.className === "fkindw") kinds.push(n.textContent); n.children.forEach(walk2); }; walk2(thread[0]);
      return { seen, lessonKinds: kinds.filter((k) => k === "Lesson").length };
    """
    res = _run(expr, {"items": THREAD, "runs": RUNS, "lessons": lessons})
    assert "Noted: Soil never smooths" in res["seen"]
    assert "Confirmed \u201cTwo miners\u201d worked" in res["seen"]
    assert res["lessonKinds"] == 2
