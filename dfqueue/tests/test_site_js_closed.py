"""Closed work on the Board (web/stream/app.js, run through node on the real
source): a proposal the feed badges `closed` or `completed` is not in the
ongoing lists, carries the closed or completed chip, and its thread ends with
the close as its last item. Reuses the node stub of `test_site_js_threads`."""
from dfqueue.tests.test_site_js_threads import P, R, _run, pytestmark  # noqa: F401

CLOSE_TEXT = "Closed without being carried out."


def _close(seq, text=CLOSE_TEXT):
    return {"id": "close-1", "seq": seq, "kind": "close", "role": "conductor", "reply_to": "ruling-1",
            "thread": "proposal-1", "text": text, "game_date": "9 Granite, year 31"}


def _board(badge, project_status=None):
    items = [
        P("proposal-1", 1, badge=badge, title="Dig a shell"),
        R("ruling-1", 2, "proposal-1", "proposal-1"),
        P("proposal-2", 3, badge="accepted", title="Brew more"),
        R("ruling-2", 4, "proposal-2", "proposal-2"),
        _close(5),
    ]
    doc = {"thread_to_project": {}, "projects": {}}
    if project_status:
        doc = {"thread_to_project": {"proposal-1": "project-1"},
               "projects": {"project-1": {"id": "project-1", "name": "Dig shell", "status": project_status, "steps": []}}}
    return {"items": items, "doc": doc}


def test_a_closed_proposal_is_closed_and_a_completed_one_is_done_neither_ongoing():
    for badge, state in (("closed", "closed"), ("completed", "done")):
        entries = _run("return boardEntries(DATA.items, DATA.doc).map((e) => [e.id, e.state]);", _board(badge))
        assert ["proposal-1", state] in entries
        assert ["proposal-2", "active"] in entries
    # an old badge with no close stays ongoing
    assert ["proposal-1", "active"] in _run(
        "return boardEntries(DATA.items, DATA.doc).map((e) => [e.id, e.state]);", _board("accepted"))


def test_the_close_overrides_a_still_active_project_on_the_board():
    entries = _run("return boardEntries(DATA.items, DATA.doc).map((e) => [e.id, e.state]);",
                   _board("closed", project_status="active"))
    assert ["project-1", "closed"] in entries


def test_the_in_progress_tab_leaves_out_closed_work_and_closed_has_its_own_tab():
    expr = r"""
      const all = boardEntries(DATA.items, DATA.doc);
      const tab = (state) => all.filter((e) => e.state === state).map((e) => e.id);
      return { inProgress: tab("active"), closed: tab("closed"), tabs: BOARD_STATES.map(([l]) => l) };
    """
    res = _run(expr, _board("closed"))
    assert res["inProgress"] == ["proposal-2"] and res["closed"] == ["proposal-1"]
    assert "Closed" in res["tabs"]


def test_closed_and_completed_chips_use_their_own_looks_never_a_glyph():
    expr = r"""
      const c = proposalStateChip("closed"), d = proposalStateChip("completed"), j = projectStateChip("closed");
      return [c.className, c.textContent, d.className, d.textContent, j.className, j.textContent];
    """
    assert _run(expr, None) == [
        "pstate ps-closed", "Closed", "pstate ps-completed", "Completed", "jstate js-closed", "Closed"]


def test_the_closed_card_shows_the_closed_chip():
    expr = r"""
      const page = Object.create(StreamPage.prototype);
      const e = boardEntries(DATA.items, DATA.doc).find((x) => x.id === "proposal-1");
      const card = page._cardEl(e);
      const classes = []; const walk = (n) => { classes.push(n.className); n.children.forEach(walk); }; walk(card);
      return classes.filter((c) => /state/.test(c));
    """
    assert _run(expr, _board("closed")) == ["jstate js-closed"]


def test_the_thread_of_a_closed_proposal_ends_with_the_public_close_text_never_the_reason():
    expr = r"""
      const page = Object.create(StreamPage.prototype);
      page.projects = { projects: {}, thread_to_project: {} };
      page.runs = { runs: [], calls_by_record: {} };
      const thread = page._conversationEl(DATA.items.filter((i) => i.thread === "proposal-1"));
      const text = []; const walk = (n) => { if (n.textContent) text.push(n.textContent); n.children.forEach(walk); }; walk(thread[0]);
      const classes = []; const walk2 = (n) => { classes.push(n.className); n.children.forEach(walk2); }; walk2(thread[0]);
      return { text, classes };
    """
    board = _board("closed")
    board["items"][-1]["record"] = {"reason": "PRIVATE-REASON"}
    res = _run(expr, board)
    assert res["text"][-1] != "PRIVATE-REASON" and "PRIVATE-REASON" not in " ".join(res["text"])
    assert CLOSE_TEXT in res["text"]
    # the last text in the thread is the close's own status line, after the close text
    assert res["text"].index(CLOSE_TEXT) < len(res["text"]) - 1
    assert "fstatusline st-closed" in res["classes"]
    assert res["text"][-3:].count("Closed") >= 1


def test_a_completed_close_shows_a_green_status_line():
    expr = r"""
      const page = Object.create(StreamPage.prototype);
      page.projects = { projects: {}, thread_to_project: {} };
      page.runs = { runs: [], calls_by_record: {} };
      const thread = page._conversationEl(DATA.items.filter((i) => i.thread === "proposal-1"));
      const classes = []; const walk = (n) => { classes.push(n.className); n.children.forEach(walk); }; walk(thread[0]);
      return classes;
    """
    classes = _run(expr, _board("completed"))
    assert "fstatusline st-done" in classes
