"""The Board's collapsed "Full proposal" block and the agent Transcript tab
(`detailRows`, `fullProposalEl`, `transcriptEl`, `_transcriptTabEl`,
`_receipt` in web/stream/app.js), run through node on the real source text
(skipped without node). handoffs/2026-10-07-transcripts-and-full-proposals.md."""
from dfqueue.tests.test_site_js_threads import _run, P

WALK = r"""
  const seen = []; const walk = (n) => { if (n.textContent) seen.push(n.textContent); n.children.forEach(walk); };
  const tags = []; const walkTags = (n) => { tags.push(n.tag + "." + n.className); n.children.forEach(walkTags); };
"""

DETAIL = {
    "summary": "Dig a stair.", "rationale": None, "preconditions": ["Embark Site: exists", None],
    "prediction": "fort.population gte 1 after 1200 ticks",
    "step": {"tool": "diggable.dig-stair", "args": '{"site":"south"}', "label": None},
    "cited": ["stocks.get drink = 12 (tick 40)"], "withheld": ["rationale", "preconditions"],
}


def test_detail_rows_label_each_part_and_mark_withheld_spans():
    rows = _run("return detailRows(DATA);", DETAIL)
    labels = [r["label"] for r in rows]
    assert labels == ["Summary", "Rationale", "Preconditions", "Prediction", "Step", "Cited facts"]
    assert rows[1]["lines"] == [{"withheld": True}]
    assert rows[2]["lines"] == [{"text": "Embark Site: exists"}, {"withheld": True}]
    assert rows[4]["lines"] == [{"text": "diggable.dig-stair"}, {"text": '{"site":"south"}'}]
    assert _run("return detailRows(undefined);", {}) == [] and _run("return detailRows({});", {}) == []


def test_full_proposal_is_collapsed_and_shows_withheld_as_withheld():
    res = _run(WALK + "const n = fullProposalEl(DATA); walk(n); walkTags(n); return {seen, tags, isOpen: 'open' in n.attrs};", DETAIL)
    assert res["tags"][0] == "details.fx ffull" and res["isOpen"] is False
    assert "Full proposal" in res["seen"] and "(withheld)" in res["seen"]
    assert "Cited facts" in res["seen"] and "Dig a stair." in res["seen"]


def test_a_proposal_receipt_and_post_carry_the_block_and_other_kinds_do_not():
    expr = WALK + r"""
      const page = Object.create(StreamPage.prototype);
      page.projects = { projects: {}, thread_to_project: {} };
      page.runs = null;
      const withDetail = page._receipt({ ...DATA.item, detail: DATA.detail }); walk(withDetail);
      const plain = page._receipt(DATA.item);
      const seenPlain = []; const w2 = (n) => { if (n.textContent) seenPlain.push(n.textContent); n.children.forEach(w2); }; w2(plain);
      return { seen, seenPlain };
    """
    res = _run(expr, {"item": P("proposal-1", 1), "detail": DETAIL})
    assert "Full proposal" in res["seen"] and "Full proposal" not in res["seenPlain"]


TX = {"rounds": [
    {"n": 1, "reasoning": "Check drink.", "text": "Looking.", "usage": {"input": 5, "output": 2},
     "calls": [{"name": "stocks.get", "args": '{"kind":"drink"}', "result": "drink: 12\n[one paragraph withheld]", "error": False},
               {"name": "zone.list", "args": None, "args_withheld": True, "result": None, "error": True}]},
    {"n": 2, "reasoning": None, "text": "Done.", "usage": None, "calls": []},
], "omitted_rounds": 3}


def test_transcript_renders_rounds_calls_collapsed_and_withheld_args():
    res = _run(WALK + "const n = transcriptEl(DATA); walk(n); walkTags(n); return {seen, tags};", TX)
    assert "Round 1" in res["seen"] and "in 5 · out 2" in res["seen"]
    assert "stocks.get" in res["seen"] and "zone.list (failed)" in res["seen"]
    assert '{"kind":"drink"}' in res["seen"] and "(withheld)" in res["seen"]
    assert "3 later rounds left out" in res["seen"]
    # tool calls and reasoning sit in collapsed details, none open
    assert sum(1 for t in res["tags"] if t.startswith("details.fx")) == 3


def _run_async(expr, data):
    """Like `_run`, but `expr` may `await` (the body is an async function)."""
    import json, subprocess, tempfile
    from pathlib import Path
    from dfqueue.tests.test_site_js_threads import APP, STUB
    script = STUB + APP.read_text(encoding="utf8") + "\nconst DATA = %s;\n" % json.dumps(data) + (
        "(async function(){ %s })().then((r) => console.log(JSON.stringify(r)), (e) => { console.error(e); process.exit(1); });" % expr)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "run.js"
        path.write_text(script, encoding="utf8")
        out = subprocess.run(["node", str(path)], capture_output=True, text=True, encoding="utf8")
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


RUNS = [
    {"run_id": "run-0002", "role": "architect", "wake_reason": "routine_review", "started_at": "2026-10-07T10:00:00+00:00",
     "transcript": {"available": True, "size": 20480, "withheld_count": 2}},
    {"run_id": "run-0001", "role": "architect", "started_at": "2026-10-07T09:00:00+00:00"},
    {"run_id": "run-0003", "role": "overseer", "started_at": "2026-10-07T09:00:00+00:00",
     "transcript": {"available": True, "size": 100, "withheld_count": 0}},
]


def test_transcript_tab_lists_runs_collapsed_newest_first_without_fetching():
    expr = WALK + r"""
      globalThis.fetch = async () => { throw new Error("must not fetch before a run is opened"); };
      const page = Object.create(SitePage.prototype);
      page.siteText = { wake_reasons: { routine_review: "Regular check-in" } };
      page.fortRuns = { runs: DATA };
      const n = page._transcriptTabEl("architect"); walk(n);
      const det = n.children.filter((c) => c.tag === "details");
      return { seen, count: det.length, open: det.map((d) => d.attrs.open) };
    """
    res = _run(expr, RUNS)
    assert res["count"] == 1 and res["open"] == [None]
    assert "Regular check-in · 2026-10-07 · 20 KB · 2 withheld" in res["seen"]
    empty = _run("const p = Object.create(SitePage.prototype); p.fortRuns = { runs: [] }; return p._transcriptTabEl('architect').children.length;", {})
    assert empty == 1


def test_opening_a_run_shows_loading_then_the_fetched_transcript_and_caches_it():
    expr = WALK + r"""
      const urls = [];
      globalThis.fetch = async (u) => { urls.push(u); return { ok: true, json: async () => DATA.tx }; };
      const page = Object.create(SitePage.prototype);
      page.dataRoot = "/data/public"; page.fortMeta = { id: "ragwind" }; page.siteText = {};
      page.fortRuns = { runs: DATA.runs };
      const n = page._transcriptTabEl("architect");
      const det = n.children[0]; const holder = det.children[1];
      const before = holder.children.length;
      det.open = true; det.listeners.toggle();
      const loading = holder.children.map((c) => c.textContent);
      await new Promise((r) => setTimeout(r, 0));
      walk(holder);
      det.listeners.toggle(); det.listeners.toggle();
      await new Promise((r) => setTimeout(r, 0));
      return { before, loading, seen, urls, cached: !!page.transcripts["run-0002"] };
    """
    res = _run_async(expr, {"runs": RUNS, "tx": TX})
    assert res["before"] == 0 and res["loading"] == ["Loading transcript..."]
    assert "Round 1" in res["seen"] and "stocks.get" in res["seen"]
    assert res["urls"] == ["/data/public/forts/ragwind/transcripts/run-0002.json"]  # once, though toggled again
    assert res["cached"] is True


def test_a_missing_transcript_file_shows_a_note_and_a_reopen_retries():
    expr = r"""
      let calls = 0;
      globalThis.fetch = async () => { calls += 1; return { ok: false, status: 404, json: async () => ({}) }; };
      const page = Object.create(SitePage.prototype);
      page.dataRoot = "/d"; page.fortMeta = null; page.siteText = {};
      page.fortRuns = { runs: DATA };
      const det = page._transcriptTabEl("architect").children[0]; const holder = det.children[1];
      det.open = true; det.listeners.toggle();
      await new Promise((r) => setTimeout(r, 0));
      const first = holder.children.map((c) => c.textContent);
      det.listeners.toggle();
      await new Promise((r) => setTimeout(r, 0));
      return { first, calls };
    """
    res = _run_async(expr, RUNS)
    assert res["first"] == ["This transcript is no longer available."] and res["calls"] == 2


def test_a_transcript_tab_exists_for_live_roles_only():
    import re
    from dfqueue.tests.test_site_js_threads import APP
    src = APP.read_text(encoding="utf8")
    assert re.search(r'\["turns", "Turns"\], \["transcript", "Transcript"\]', src)
    assert '[["charter", "Charter"]]' in src  # planned roles still see only the charter
