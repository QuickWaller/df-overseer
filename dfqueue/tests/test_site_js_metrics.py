"""The Board's Metrics view (`metricsView` and its helpers in web/stream/app.js),
run through node on the real source text (skipped without node), fed a real
`wake_metrics.compute` report from the 2026-10-05..07 fixture window."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from dfqueue import wake_metrics as wm
from dfqueue.tests.test_wake_metrics import EPOCHS, FIXTURE, write_queue, write_runs
from dfqueue.tests.test_site_js_threads import STUB

APP = Path(__file__).resolve().parents[2] / "web" / "stream" / "app.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

# A walker that flattens a stub DOM tree to its text and class names.
WALK = r"""
function walk(n, f) { f(n); (n.children || []).forEach((c) => walk(c, f)); }
function texts(n) { const out = []; walk(n, (x) => { if (x.textContent) out.push(x.textContent); }); return out; }
function classes(n) { const out = []; walk(n, (x) => { const c = x.className || x.attrs["class"]; if (c) out.push(c); }); return out; }
function count(n, tag) { let k = 0; walk(n, (x) => { if (x.tag === tag) k++; }); return k; }
"""


def _run(expr, data):
    src = APP.read_text(encoding="utf8")
    script = STUB + src + WALK + "\n" + ("const DOC = %s;\n" % json.dumps(data)) + (
        "console.log(JSON.stringify((function(){ %s })()));" % expr)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "run.js"
        path.write_text(script, encoding="utf8")
        out = subprocess.run(["node", str(path)], capture_output=True, text=True, encoding="utf8")
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("m")
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    write_queue(tmp / "q.sqlite3", fx["records"], fx["predictions"])
    write_runs(tmp / "r.sqlite3", fx["runs"], fx["transcripts"])
    return wm.compute(tmp / "q.sqlite3", tmp / "r.sqlite3", epochs=EPOCHS)


def test_view_renders_every_chart_and_the_tool_lists(report):
    out = _run("""
      const state = { role: null };
      const v = metricsView(DOC, state, () => {});
      return { svgs: count(v, "svg"), text: texts(v).join(" | "), role: state.role };
    """, report)
    assert out["svgs"] == 4
    for needle in ("Repeats per day", "Rounds per wake", "Cost per wake", "Pass rate", "Never called", "Approximate"):
        assert needle in out["text"], needle
    assert out["role"] == "architect"


def test_thin_numbers_are_called_thin(report):
    out = _run("return texts(metricsView(DOC, { role: null }, () => {})).filter((t) => t.startsWith('Thin'))", report)
    assert out, "the fixture rests on few wakes, so at least one note must say so"


def test_epochs_are_marked_on_the_charts(report):
    out = _run("""
      const v = metricsView(DOC, { role: null }, () => {});
      return { epochs: metricsEpochStarts(DOC), lines: classes(v).filter((c) => c === "mepoch").length };
    """, report)
    assert out["epochs"] and out["epochs"][0]["id"] == EPOCHS[0]["id"]
    assert out["lines"] >= 1


def test_tool_list_is_sorted_and_split_called_vs_never(report):
    role = next(r for r, u in report["tool_usage"].items() if u["calls"])
    out = _run("""
      const el_ = metricsToolList(DOC, %s);
      const ids = []; walk(el_, (x) => { if (x.className === "mtid") ids.push(x.textContent); });
      const ns = []; walk(el_, (x) => { if (x.className === "mtn") ns.push(Number(x.textContent)); });
      return { ids, ns, text: texts(el_).join(" | ") };
    """ % json.dumps(role), report)
    assert out["ns"] == sorted(out["ns"], reverse=True) and out["ids"]
    assert "Never called" in out["text"] and "stored transcript" in out["text"]


def test_missing_or_foreign_document_says_so_plainly():
    out = _run("return [texts(metricsView(null, {}, () => {})).join(' '), texts(metricsView({schema: 'other'}, {}, () => {})).join(' ')]", {})
    assert all("No metrics have been published" in t for t in out)


def test_hollow_points_mark_days_resting_on_few_wakes(report):
    out = _run("""
      const days = metricsDays(DOC);
      const s = metricsSeries(DOC, (g) => (g.cost || {}).mean);
      const svg = metricsLineChart(days, s, [], "usd");
      let thin = 0, solid = 0;
      walk(svg, (x) => { if ((x.className || x.attrs["class"]) === "mdot thin") thin++; else if ((x.className || x.attrs["class"]) === "mdot") solid++; });
      return { thin, solid };
    """, report)
    assert out["thin"] + out["solid"] > 0
