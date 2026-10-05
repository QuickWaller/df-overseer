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


def test_a_turn_lists_its_records_as_receipts_with_their_verdicts():
    expr = r"""
      const page = Object.create(StreamPage.prototype);
      page.projects = { projects: {}, thread_to_project: {} };
      page.runs = DATA.runs;
      const thread = page._conversationEl(DATA.items);
      const out = []; const walk = (n) => { if (n.className && n.className.startsWith("freceipt ")) out.push(n.className); if (n.className === "freceipt") out.push("plain"); n.children.forEach(walk); }; walk(thread[0]);
      const tags = []; const walk2 = (n) => { if (n.className === "ftag") tags.push(n.textContent); n.children.forEach(walk2); }; walk2(thread[0]);
      return { out, tags };
    """
    res = _run(expr, {"items": THREAD, "runs": RUNS})
    assert "Proposal" in res["tags"] and "Accepted" in res["tags"]
    assert any("r-accepted" in c for c in res["out"])


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


# ---- run summaries and "what it checked" from runs.json (2026-10-05) ----------

RUNS = {
    "by_thread": {"proposal-1": ["run-1", "run-2"]},
    "runs": [
        {"run_id": "run-2", "role": "overseer", "wake_reason": "ask_open", "duration_s": 372, "summary": "Ruled the proposal.",
         "records": [{"id": "ruling-1", "kind": "ruling", "thread": "proposal-1"}]},
        {"run_id": "run-1", "role": "architect", "wake_reason": "routine_review", "duration_s": 42, "summary": "Filed a proposal.",
         "records": [{"id": "proposal-1", "kind": "proposal", "thread": "proposal-1"}]},
        {"run_id": "run-0", "role": "architect", "wake_reason": None, "duration_s": 5, "records": [
            {"id": "proposal-1", "kind": "proposal", "thread": "proposal-1"}]},
    ],
    "calls_by_record": {"proposal-1": [{"tool": "overview.get", "note": "A first look.", "n": 2, "failed": False},
                                       {"tool": "zone.list", "note": None, "n": 1, "failed": True}]},
}


def test_each_run_becomes_a_summary_reply_after_its_last_record_and_blank_ones_are_skipped():
    out = _run("return summaryItems(DATA.items, DATA.runs).map((i) => [i.id, i.role, i.seq, i.when_text, i.text, i.reply_to]);",
               {"items": THREAD, "runs": {**RUNS, "by_thread": {"proposal-1": ["run-1", "run-2", "run-0"]}}})
    assert out == [
        ["run-1:proposal-1", "architect", 1.5, "woke for routine review · 42 s", "Filed a proposal.", "proposal-1"],
        ["run-2:proposal-1", "overseer", 2.5, "woke for ask open · 6 min", "Ruled the proposal.", "proposal-1"],
    ]
    assert _run("return summaryItems(DATA, null).length;", THREAD) == 0


def test_a_run_becomes_a_turn_block_with_its_summary_holding_what_it_wrote():
    expr = r"""
      const page = Object.create(StreamPage.prototype);
      page.projects = { projects: {}, thread_to_project: {} };
      page.runs = DATA.runs;
      const thread = page._conversationEl(DATA.items);
      const text = []; const walk = (n) => { if (n.textContent) text.push(n.textContent); n.children.forEach(walk); }; walk(thread[0]);
      const classes = []; const walk2 = (n) => { classes.push(n.className); n.children.forEach(walk2); }; walk2(thread[0]);
      return { text, turns: classes.filter((c) => c === "fturn").length, tier1: classes.filter((c) => c === "fkids tier-1").length };
    """
    res = _run(expr, {"items": THREAD, "runs": RUNS})
    assert "Filed a proposal." in res["text"] and "Woke for ask open" in res["text"]
    assert any(t.endswith("6 min") for t in res["text"])
    assert "Architect" in res["text"] and "Overseer" in res["text"]
    assert res["turns"] == 2  # one root-level block per run, nothing nested across turns


def test_what_it_checked_comes_from_calls_by_record_with_counts_and_errors():
    rows = _run("return checkRows(DATA.calls_by_record['proposal-1']);", RUNS)
    assert rows == [{"tool": "overview.get", "note": "A first look. · 2 calls"}, {"tool": "zone.list", "note": "errored"}]
    expr = r"""
      const page = Object.create(StreamPage.prototype);
      page.projects = { projects: {}, thread_to_project: {} };
      page.runs = DATA.runs;
      const post = page._threadPost({ ...DATA.items[0], calls: [] });  // the operator feed's empty list
      const seen = []; const walk = (n) => { if (n.textContent) seen.push(n.textContent); n.children.forEach(walk); }; walk(post);
      return seen;
    """
    seen = _run(expr, {"items": THREAD, "runs": RUNS})
    assert "What it checked · 2" in seen and "overview.get" in seen
