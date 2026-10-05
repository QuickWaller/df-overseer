"""The Board's Markdown renderer (`renderMarkdown` in web/stream/app.js), run
through node on the real source text (skipped without node). The DOM is a tiny
stub that records every element created and every attribute set, so the XSS
tests can assert that hostile text never becomes an element or an attribute."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "web" / "stream" / "app.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

STUB = r"""
const CREATED = [];
const ATTRS = [];
class Node {
  constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.textContent = ""; this.className = ""; CREATED.push(tag); }
  setAttribute(k, v) { ATTRS.push(k); }
  addEventListener(t, f) { this.listeners[t] = f; }
  appendChild(c) { this.children.push(c); return c; }
}
const document = { createElement: (t) => new Node(t), createElementNS: (n, t) => new Node(t), createTextNode: (t) => { const n = new Node("#text"); n.textContent = t; return n; }, addEventListener() {}, readyState: "loading" };
const window = {}; const location = { hash: "", port: "8000" };
const localStorage = { getItem() { return null; }, setItem() {} };
function ser(n) {
  if (n.tag === "#text") return n.textContent;
  return "<" + n.tag + ">" + n.children.map(ser).join("") + n.textContent + "</" + n.tag + ">";
}
"""

ALLOWED = {"div", "p", "br", "ul", "ol", "li", "strong", "em", "code", "#text"}


def render(md):
    """-> (serialised tree, tags created, attributes set) for one render."""
    src = APP.read_text(encoding="utf8")
    script = (
        STUB + src + "\nconst IN = %s;\n" % json.dumps(md)
        + "CREATED.length = 0; ATTRS.length = 0;\n"
        + "const root = renderMarkdown(IN);\n"
        + "console.log(JSON.stringify({html: ser(root), created: CREATED, attrs: ATTRS}));"
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "run.js"
        path.write_text(script, encoding="utf8")
        out = subprocess.run(["node", str(path)], capture_output=True, text=True, encoding="utf8")
    assert out.returncode == 0, out.stderr[-2000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    return d["html"], d["created"], d["attrs"]


def html(md):
    return render(md)[0]


def test_paragraphs_and_hard_breaks():
    assert html("one\ntwo\n\nthree") == "<div><p>one<br></br>two</p><p>three</p></div>"


def test_headings_are_small_lines_up_to_three_hashes():
    assert html("# A\n## B\n### C") == "<div><div>A</div><div>B</div><div>C</div></div>"
    assert html("#### D") == "<div><p>#### D</p></div>"


def test_bullets_and_numbers():
    assert html("- a\n* b") == "<div><ul><li>a</li><li>b</li></ul></div>"
    assert html("1. a\n2. b") == "<div><ol><li>a</li><li>b</li></ol></div>"


def test_nested_list_one_level():
    assert html("- a\n  - b\n  - c\n- d") == "<div><ul><li>a<ul><li>b</li><li>c</li></ul></li><li>d</li></ul></div>"


def test_bold_italic_code():
    assert html("**b** *i* _j_ `c`") == "<div><p><strong>b</strong> <em>i</em> <em>j</em> <code>c</code></p></div>"


def test_nesting_and_code_content_is_literal():
    assert html("`**not bold**`") == "<div><p><code>**not bold**</code></p></div>"
    assert html("**a *b* c**") == "<div><p><strong>a <em>b</em> c</strong></p></div>"


def test_unmatched_markers_and_snake_case_stay_literal():
    assert html("2 * 3 and snake_case_name and **open") == "<div><p>2 * 3 and snake_case_name and **open</p></div>"


@pytest.mark.parametrize("text", [
    "| a | b |\n|---|---|",
    "```py\nx = 1\n```",
    "> quote",
    "![i](http://x/y.png)",
])
def test_unsupported_constructs_are_literal_text(text):
    out, created, attrs = render(text)
    assert set(created) <= ALLOWED, created
    assert attrs == []
    assert "table" not in out and "img" not in created


@pytest.mark.parametrize("hostile", [
    "<script>alert(1)</script>",
    '<img src=x onerror="alert(1)">',
    "[x](javascript:alert(1))",
    "&lt;b&gt; &amp; &#60;i&#62;",
    "<b>bold</b> <a href='http://x'>l</a>",
    "**<script>x</script>** and `<img onerror=1>`",
    "- <img src=x onerror=1>\n1. <iframe src=x>",
    "# <svg onload=1>",
])
def test_hostile_text_never_becomes_an_element_or_attribute(hostile):
    out, created, attrs = render(hostile)
    assert set(created) <= ALLOWED, created
    assert attrs == [], attrs


def test_hostile_text_survives_verbatim():
    assert html("<script>alert(1)</script>") == "<div><p><script>alert(1)</script></p></div>"
    assert html("[x](javascript:alert(1))") == "<div><p>[x](javascript:alert(1))</p></div>"
    assert html("&lt;b&gt;") == "<div><p>&lt;b&gt;</p></div>"
    assert html('<img src=x onerror="alert(1)">') == '<div><p><img src=x onerror="alert(1)"></p></div>'
