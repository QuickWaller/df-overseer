"""The Board's thread tree, event wording and proposal list (`threadTree`,
`eventLine`, `boardEntries`, and the `_conversationEl` DOM they feed in
web/stream/app.js), run through node on the real source text (skipped without
node). The DOM is a tiny stub, enough for `el()` and the toggle."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "web" / "stream" / "app.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

STUB = r"""
class Node {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.listeners = {}; this.textContent = ""; this.className = ""; this.hidden = false; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "hidden") this.hidden = true; }
  addEventListener(t, f) { this.listeners[t] = f; }
  appendChild(c) { this.children.push(c); return c; }
  querySelector(sel) { const cls = sel.slice(1); const walk = (n) => { for (const c of n.children) { if (c.className.split(" ").includes(cls)) return c; const r = walk(c); if (r) return r; } return null; }; return walk(this); }
  get onclick() { return this.listeners.click; }
  set onclick(f) { this.listeners.click = f; }
}
const document = { createElement: (t) => new Node(t), createElementNS: (n, t) => new Node(t), createTextNode: (t) => { const n = new Node("#text"); n.textContent = t; return n; }, addEventListener() {}, readyState: "loading" };
const window = {}; const location = { hash: "", port: "8000" };
const localStorage = { getItem() { return null; }, setItem() {} };
"""


def _run(expr, data):
    src = APP.read_text(encoding="utf8")
    script = STUB + src + "\n" + (
        "const DATA = %s;\n" % json.dumps(data)
    ) + "console.log(JSON.stringify((function(){ %s })()));" % expr
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "run.js"
        path.write_text(script, encoding="utf8")
        out = subprocess.run(["node", str(path)], capture_output=True, text=True, encoding="utf8")
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def P(i, seq, **kw):
    d = {"id": i, "seq": seq, "kind": "proposal", "role": "architect", "reply_to": None,
         "thread": i, "badge": None, "text": "Why.", "type": "Room siting", "title": None,
         "game_date": "1 Granite, year 31"}
    d.update(kw)
    return d


def R(i, seq, to, thread, text="Accepted: fine."):
    return {"id": i, "seq": seq, "kind": "ruling", "role": "overseer", "reply_to": to,
            "thread": thread, "text": text, "game_date": "2 Granite, year 31"}


# ---- thread tree ---------------------------------------------------------------


THREAD = [
    P("proposal-1", 1, badge="accepted"),
    R("ruling-1", 2, "proposal-1", "proposal-1"),
    {"id": "project-1", "seq": 3, "kind": "project", "role": "overseer", "reply_to": "ruling-1", "thread": "proposal-1"},
    {"id": "ask-1", "seq": 4, "kind": "ask", "role": "architect", "reply_to": "proposal-1", "thread": "proposal-1"},
    {"id": "answer-1", "seq": 5, "kind": "answer", "role": "consultant", "reply_to": "ask-1", "thread": "proposal-1"},
    {"id": "executed-1", "seq": 6, "kind": "executed", "role": "overseer", "reply_to": "ruling-1", "thread": "proposal-1",
     "step_label": "Dig shell", "step_targets": 4, "step_total": 12, "step_outcome": "started"},
]


def test_thread_root_is_the_founding_proposal_and_answers_nest_under_questions():
    tree = _run("const t = threadTree(DATA); return {root: t.root.id, kids: [...t.kids.entries()].map(([k, v]) => [k, v.map((i) => i.id)])};", THREAD)
    assert tree["root"] == "proposal-1"
    kids = dict(tree["kids"])
    assert kids["proposal-1"] == ["ruling-1", "project-1", "ask-1", "executed-1"]
    assert kids["ask-1"] == ["answer-1"]


def test_event_wording_names_the_job_and_counts_targets():
    lines = _run("return DATA.map((i) => eventLine(i, {projects: {}}));", THREAD)
    assert lines[2] == {"cls": " plan", "text": "made this a project"}
    assert lines[5] == {"cls": "", "text": 'started job "Dig shell" · 4 of 12 targets ordered'}
    assert lines[0] is None and lines[1] is None


def test_event_wording_for_finished_failed_and_hold():
    items = [
        {"kind": "executed", "step_label": "Make bed", "step_targets": 1, "step_total": 1, "step_outcome": "finished"},
        {"kind": "executed", "step_label": "Make bed", "step_targets": 1, "step_outcome": "failed"},
        {"kind": "executed"},
        {"kind": "observation", "record": {"step_id": "p/s1", "results": [{"reason": "no stone"}]}},
    ]
    doc = {"projects": {"p": {"id": "p", "steps": [{"id": "p/s1", "label": "Dig shell"}]}}}
    lines = _run("return DATA.items.map((i) => eventLine(i, DATA.doc));", {"items": items, "doc": doc})
    assert lines[0]["text"] == 'finished job "Make bed" · 1 of 1 target done'
    assert lines[1] == {"cls": " fail", "text": 'tried and failed to start job "Make bed" · 1 target ordered'}
    assert lines[2]["text"] == "carried out a job"
    assert lines[3] == {"cls": " hold", "text": 'put job "Dig shell" on hold: no stone'}


# ---- the thread DOM: first-level replies open, deeper ones closed; state survives ---


def test_first_level_open_deeper_closed_toggle_and_survive_a_rerender():
    expr = r"""
      const page = Object.create(StreamPage.prototype);
      page.projects = { projects: {}, thread_to_project: {} };
      const hiddenBoxes = () => { const out = []; const walk = (n) => { if (n.className === "freplies") out.push(n.hidden); n.children.forEach(walk); }; walk(thread[0]); return out; };
      let thread = page._conversationEl(DATA);
      const before = hiddenBoxes();
      const toggle = (() => { let f = null; const walk = (n) => { if (!f && n.className === "ftoggle") f = n; n.children.forEach(walk); }; walk(thread[0]); return f; })();
      const label0 = toggle.querySelector(".ftl").textContent;
      toggle.listeners.click();
      const label1 = toggle.querySelector(".ftl").textContent;
      thread = page._conversationEl(DATA);
      return { before, label0, label1, after: hiddenBoxes() };
    """
    res = _run(expr, THREAD)
    assert res["before"] == [False, True]           # root's replies open, the ask's answer closed
    assert res["label0"] == "- 4 replies"
    assert res["label1"] == "+ 4 replies"
    assert res["after"] == [True, True]             # the closed state survived the re-render


# ---- the board list: every proposal, one entry per thread -------------------------


def test_every_proposal_is_listed_once_and_a_project_replaces_its_proposal():
    items = [
        P("proposal-1", 1, badge="accepted", title="Dig a shell"),
        R("ruling-1", 2, "proposal-1", "proposal-1"),
        P("proposal-2", 3, badge="rejected", role="quartermaster", title="Brew more"),
        R("ruling-2", 4, "proposal-2", "proposal-2", "Rejected: not now."),
        P("proposal-3", 5, badge="deferred"),
        P("proposal-4", 6),
        P("proposal-5", 7, badge="accepted", title="Old room"),
        {"id": "executed-9", "seq": 8, "kind": "executed", "thread": "proposal-5", "reply_to": "ruling-5"},
    ]
    doc = {"thread_to_project": {"proposal-1": "project-1"},
           "projects": {"project-1": {"id": "project-1", "name": "Dig shell (project)", "status": "hold", "steps": [], "description": "d"}}}
    entries = _run("return boardEntries(DATA.items, DATA.doc).map((e) => [e.kind, e.id, e.name, e.state, e.description]);",
                   {"items": items, "doc": doc})
    assert entries == [
        ["proposal", "proposal-5", "Old room", "done", "Why."],
        ["proposal", "proposal-4", "Room siting", "pending", "Why."],
        ["proposal", "proposal-3", "Room siting", "deferred", "Why."],
        ["proposal", "proposal-2", "Brew more", "rejected", "not now."],
        ["project", "project-1", "Dig shell (project)", "hold", "d"],
    ]


def test_project_title_replaces_the_proposal_title_and_follows_a_rename():
    items = [P("proposal-1", 1, badge="accepted", title="Dig a shell")]
    doc = {"thread_to_project": {"proposal-1": "project-1"},
           "projects": {"project-1": {"id": "project-1", "name": "Dig the deep shell", "status": "active", "steps": []}}}
    name = _run("return boardEntries(DATA.items, DATA.doc)[0].name;", {"items": items, "doc": doc})
    assert name == "Dig the deep shell"


def test_a_project_with_no_proposal_in_the_feed_still_gets_an_entry():
    doc = {"thread_to_project": {}, "projects": {"project-9": {"id": "project-9", "name": "Orphan", "status": "abandoned", "steps": []}}}
    e = _run("return boardEntries([], DATA)[0];", doc)
    assert e["name"] == "Orphan" and e["state"] == "done" and e["abandoned"] is True
