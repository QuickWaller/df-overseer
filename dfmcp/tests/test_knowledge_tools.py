"""Direct, transport-free tests of `dfmcp.knowledge_tools`, in the same
style as `dfmcp/tests/test_doctrine_tools.py`/`test_series_tools.py`: this
module imports nothing from `mcp` (the SDK), only `dfmcp.knowledge_tools`
and stdlib, so it runs under the ambient environment too, not only
`.venv-dfmcp`.

No real network call happens anywhere in this file. `web.search` and
`web.fetch` are exercised through an injected `http_get` fake (the seam
`dfmcp.knowledge_tools.call` was built with, exactly like
`dfmcp/tests/test_dfhack_client.py` fakes the DFHack RPC layer rather than
opening a real socket). The one exception that talks real sockets is
`test_real_http_get_fetches_from_a_local_server`, which starts a throwaway
`http.server` bound to 127.0.0.1 -- entirely offline, and it doubles as
proof that `_check_url_safe` really does refuse that same loopback address
when asked to *fetch* it (as opposed to a test server we are choosing to
trust for the plumbing check).

Properties under test throughout, per this stream's brief
(`handoffs/2026-09-22-loop-consultant-retrieval.md`): every web-sourced
result is labelled a prior at most and never silently trusted as
instructions; `web.fetch` refuses private/loopback/link-local targets;
`knowledge.wiki_lookup` always carries a page's version_namespace and never
serves an empty result silently for a missing snapshot; `dfhack.source_*`
confines every path to its configured root.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

from dfmcp import knowledge_tools as kt
from dfmcp.registry import load_registry



# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


def _brave_ok(results):
    def fake(url, headers, timeout):
        assert "X-Subscription-Token" in headers
        assert url.startswith(kt.BRAVE_SEARCH_ENDPOINT)
        body = json.dumps({"web": {"results": results}}).encode("utf-8")
        return 200, {}, body
    return fake


def _fixed_response(status, headers, body):
    def fake(url, req_headers, timeout):
        return status, headers, body
    return fake


_NO_THROTTLE = 0.0  # min_interval override so tests don't sleep


# --------------------------------------------------------------------------
# web.search
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_search_happy_path_carries_site_guidance_and_prior_warning():
    fake = _brave_ok([
        {"title": "Well", "url": "https://dwarffortresswiki.org/index.php/Well", "description": "A well article."},
    ])
    text, structured = await kt._web_search(
        "consultant", {"query": "well"}, brave_api_key="fakekey1234567890", http_get=fake,
        sites=kt._load_sites(kt.DEFAULT_SITES_PATH), min_interval=_NO_THROTTLE,
    )
    assert structured["count"] == 1
    result = structured["results"][0]
    assert result["url"] == "https://dwarffortresswiki.org/index.php/Well"
    assert result["site"]["kind"] == "wiki"
    assert "prior at most" in text
    assert "<web_search" in text


@pytest.mark.asyncio
async def test_web_search_missing_brave_key_refused():
    with pytest.raises(kt.KnowledgeToolError, match="BRAVE_SEARCH_API_KEY"):
        await kt._web_search(
            "consultant", {"query": "well"}, brave_api_key=None,
            http_get=_brave_ok([]), sites=[], min_interval=_NO_THROTTLE,
        )


@pytest.mark.asyncio
async def test_web_search_missing_query_refused():
    with pytest.raises(kt.KnowledgeToolError, match="query"):
        await kt._web_search(
            "consultant", {}, brave_api_key="fakekey1234567890",
            http_get=_brave_ok([]), sites=[], min_interval=_NO_THROTTLE,
        )


@pytest.mark.asyncio
async def test_web_search_unknown_argument_refused():
    with pytest.raises(kt.KnowledgeToolError, match="unexpected"):
        await kt._web_search(
            "consultant", {"query": "well", "bogus": 1}, brave_api_key="fakekey1234567890",
            http_get=_brave_ok([]), sites=[], min_interval=_NO_THROTTLE,
        )


@pytest.mark.parametrize("count", [0, 11, -1])
@pytest.mark.asyncio
async def test_web_search_count_out_of_range_refused(count):
    with pytest.raises(kt.KnowledgeToolError, match="count"):
        await kt._web_search(
            "consultant", {"query": "well", "count": count}, brave_api_key="fakekey1234567890",
            http_get=_brave_ok([]), sites=[], min_interval=_NO_THROTTLE,
        )


@pytest.mark.asyncio
async def test_web_search_non_200_status_refused_and_never_includes_key():
    fake = _fixed_response(401, {}, b'{"error": "invalid token"}')
    with pytest.raises(kt.KnowledgeToolError) as exc:
        await kt._web_search(
            "consultant", {"query": "well"}, brave_api_key="fakekey1234567890",
            http_get=fake, sites=[], min_interval=_NO_THROTTLE,
        )
    assert "fakekey1234567890" not in str(exc.value)
    assert "401" in str(exc.value)


@pytest.mark.asyncio
async def test_web_search_invalid_json_refused():
    fake = _fixed_response(200, {}, b"not json")
    with pytest.raises(kt.KnowledgeToolError, match="not valid JSON"):
        await kt._web_search(
            "consultant", {"query": "well"}, brave_api_key="fakekey1234567890",
            http_get=fake, sites=[], min_interval=_NO_THROTTLE,
        )


@pytest.mark.asyncio
async def test_web_search_result_without_a_known_site_has_no_site_guidance():
    fake = _brave_ok([{"title": "X", "url": "https://some-random-blog.example/post", "description": "d"}])
    _text, structured = await kt._web_search(
        "consultant", {"query": "x"}, brave_api_key="fakekey1234567890", http_get=fake,
        sites=kt._load_sites(kt.DEFAULT_SITES_PATH), min_interval=_NO_THROTTLE,
    )
    assert structured["results"][0]["site"] is None


# --------------------------------------------------------------------------
# web.fetch
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_fetch_extracts_text_and_strips_script_and_style():
    body = b"<html><head><style>.x{}</style></head><body><script>evil()</script><h1>Hi</h1><p>Some text.</p></body></html>"
    fake = _fixed_response(200, {"Content-Type": "text/html; charset=utf-8"}, body)
    text, structured = await kt._web_fetch("consultant", {"url": "https://example.com/page"}, http_get=fake, sites=[])
    assert structured["text"] == "Hi Some text."
    assert structured["is_untrusted"] is True
    assert "UNTRUSTED DATA" in text
    assert "evil()" not in structured["text"]


@pytest.mark.asyncio
async def test_web_fetch_truncates_long_text():
    long_text = "word " * 5000
    body = f"<html><body><p>{long_text}</p></body></html>".encode("utf-8")
    fake = _fixed_response(200, {"Content-Type": "text/html"}, body)
    _text, structured = await kt._web_fetch("consultant", {"url": "https://example.com/"}, http_get=fake, sites=[])
    assert structured["truncated"] is True
    assert len(structured["text"]) <= kt._MAX_FETCH_TEXT_CHARS


@pytest.mark.parametrize("bad_url", [
    "http://127.0.0.1/",
    "http://192.0.2.1/",  # RFC 5737 TEST-NET-1: still ipaddress.is_private, no real host (docs/TRAPS.md convention)
    "http://169.254.169.254/",       # common cloud-metadata address
    "http://[::1]/",
    "ftp://example.com/",
    "not-a-url",
])
@pytest.mark.asyncio
async def test_web_fetch_refuses_unsafe_or_bad_scheme_urls(bad_url):
    with pytest.raises(kt.KnowledgeToolError):
        await kt._web_fetch("consultant", {"url": bad_url}, http_get=_fixed_response(200, {}, b""), sites=[])


@pytest.mark.asyncio
async def test_web_fetch_unknown_argument_refused():
    with pytest.raises(kt.KnowledgeToolError, match="unexpected"):
        await kt._web_fetch("consultant", {"url": "https://example.com/", "x": 1}, http_get=_fixed_response(200, {}, b""), sites=[])


@pytest.mark.asyncio
async def test_check_url_safe_accepts_a_public_looking_resolution():
    """_check_url_safe itself, with socket.getaddrinfo mocked to a public
    address -- no real DNS lookup, still exercising the real resolve-then-
    classify path rather than only the IP-literal short-circuit the other
    tests use."""
    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]  # a public IPv4 (example.com's old address)
    with patch("dfmcp.knowledge_tools.socket.getaddrinfo", return_value=fake_infos):
        hostname = kt._check_url_safe("https://example.com/")
    assert hostname == "example.com"


@pytest.mark.asyncio
async def test_check_url_safe_refuses_when_resolution_is_private():
    fake_infos = [(2, 1, 6, "", ("192.0.2.5", 0))]  # RFC 5737 TEST-NET-1, still ipaddress.is_private
    with patch("dfmcp.knowledge_tools.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(kt.KnowledgeToolError, match="private"):
            kt._check_url_safe("https://internal.example/")


# --------------------------------------------------------------------------
# A real (loopback-only) HTTP round trip, to exercise _real_http_get and
# prove the SSRF guard blocks the exact address it would otherwise fetch.
# --------------------------------------------------------------------------


class _EchoHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = b"<html><body><p>hello from loopback</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002 -- silence test server logging
        pass


@pytest.fixture
def local_server():
    server = HTTPServer(("127.0.0.1", 0), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_real_http_get_fetches_from_a_local_server(local_server):
    host, port = local_server
    status, headers, body = kt._real_http_get(f"http://{host}:{port}/", {}, 5.0)
    assert status == 200
    assert b"hello from loopback" in body
    assert "text/html" in headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_web_fetch_refuses_the_same_local_server_via_the_ssrf_guard(local_server):
    """The SSRF guard, not just a hand-picked private literal, actually
    blocks the concrete loopback server test_real_http_get_fetches_from_a_
    local_server just proved reachable."""
    host, port = local_server
    with pytest.raises(kt.KnowledgeToolError, match="private/loopback"):
        await kt._web_fetch(
            "consultant", {"url": f"http://{host}:{port}/"},
            http_get=kt._real_http_get, sites=[],
        )


# --------------------------------------------------------------------------
# knowledge.wiki_lookup
# --------------------------------------------------------------------------


@pytest.fixture
def wiki_snapshot(tmp_path: Path) -> Path:
    snap = tmp_path / "wiki_snapshot.json"
    snap.write_text(json.dumps({
        "generated_utc": "2026-09-22T00:00:00Z",
        "pages": {
            "Well": {
                "version_namespace": "current",
                "url": "https://dwarffortresswiki.org/index.php/Well",
                "sections": [
                    {"heading": "Requirements", "text": "A well needs a water source below it."},
                    {"heading": "Construction", "text": "Build with blocks, a bucket, a chain, and mechanisms."},
                ],
            },
            "DF2014:Well": {
                "version_namespace": "DF2014",
                "url": "https://dwarffortresswiki.org/index.php/DF2014:Well",
                "sections": [{"heading": "Old", "text": "pre-v50 content"}],
            },
        },
    }), encoding="utf-8")
    return snap


@pytest.mark.asyncio
async def test_wiki_lookup_index_when_no_title_given(wiki_snapshot):
    _text, structured = await kt._wiki_lookup("consultant", {}, wiki_snapshot_path=str(wiki_snapshot))
    assert structured["count"] == 2
    titles = {p["title"] for p in structured["pages"]}
    assert titles == {"Well", "DF2014:Well"}


@pytest.mark.asyncio
async def test_wiki_lookup_by_title_is_case_insensitive_and_carries_namespace(wiki_snapshot):
    text, structured = await kt._wiki_lookup("consultant", {"title": "well"}, wiki_snapshot_path=str(wiki_snapshot))
    assert structured["title"] == "Well"
    assert structured["version_namespace"] == "current"
    assert structured["returned_count"] == 2
    assert "version_namespace" in text


@pytest.mark.asyncio
async def test_wiki_lookup_old_namespace_page_is_distinguishable(wiki_snapshot):
    _text, structured = await kt._wiki_lookup("consultant", {"title": "DF2014:Well"}, wiki_snapshot_path=str(wiki_snapshot))
    assert structured["version_namespace"] == "DF2014"


@pytest.mark.asyncio
async def test_wiki_lookup_section_query_filters_headings(wiki_snapshot):
    _text, structured = await kt._wiki_lookup(
        "consultant", {"title": "Well", "section_query": "construction"}, wiki_snapshot_path=str(wiki_snapshot),
    )
    assert structured["returned_count"] == 1
    assert structured["sections"][0]["heading"] == "Construction"


@pytest.mark.asyncio
async def test_wiki_lookup_max_sections_caps_and_reports_omitted(wiki_snapshot):
    _text, structured = await kt._wiki_lookup(
        "consultant", {"title": "Well", "max_sections": 1}, wiki_snapshot_path=str(wiki_snapshot),
    )
    assert structured["returned_count"] == 1
    assert structured["omitted_count"] == 1


@pytest.mark.asyncio
async def test_wiki_lookup_unknown_title_refused_not_empty(wiki_snapshot):
    with pytest.raises(kt.KnowledgeToolError, match="no page titled"):
        await kt._wiki_lookup("consultant", {"title": "Nonexistent Page"}, wiki_snapshot_path=str(wiki_snapshot))


@pytest.mark.asyncio
async def test_wiki_lookup_no_snapshot_configured_refused():
    with pytest.raises(kt.KnowledgeToolError, match="no wiki snapshot configured"):
        await kt._wiki_lookup("consultant", {}, wiki_snapshot_path=None)


@pytest.mark.asyncio
async def test_wiki_lookup_missing_snapshot_file_refused(tmp_path):
    with pytest.raises(kt.KnowledgeToolError, match="not found"):
        await kt._wiki_lookup("consultant", {}, wiki_snapshot_path=str(tmp_path / "missing.json"))


@pytest.mark.asyncio
async def test_wiki_lookup_malformed_json_refused(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(kt.KnowledgeToolError, match="not valid JSON"):
        await kt._wiki_lookup("consultant", {}, wiki_snapshot_path=str(bad))


@pytest.mark.asyncio
async def test_wiki_lookup_non_utf8_file_refused_not_a_raw_unicode_error(tmp_path):
    # A binary SQLite file mistakenly configured under a non-.sqlite3 name (so
    # `_is_sqlite_mirror` does not route it to the mirror reader) must not let
    # `UnicodeDecodeError` escape as a raw, unhandled MCP error.
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"SQLite format 3\x00\xff\xfe\x00\x01binary-not-utf8\x80\x81")
    with pytest.raises(kt.KnowledgeToolError, match="not valid UTF-8"):
        await kt._wiki_lookup("consultant", {}, wiki_snapshot_path=str(bad))


@pytest.mark.asyncio
async def test_wiki_lookup_missing_pages_key_refused(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"generated_utc": "x"}), encoding="utf-8")
    with pytest.raises(kt.KnowledgeToolError, match="'pages'"):
        await kt._wiki_lookup("consultant", {}, wiki_snapshot_path=str(bad))


# --------------------------------------------------------------------------
# dfhack.source_search / dfhack.source_read
# --------------------------------------------------------------------------


@pytest.fixture
def dfhack_source_root(tmp_path: Path) -> Path:
    root = tmp_path / "hack"
    (root / "scripts").mkdir(parents=True)
    (root / "docs" / "docs" / "tools").mkdir(parents=True)
    (root / "scripts" / "df-overseer-well.lua").write_text(
        "-- df-overseer-well.lua\nfunction well_build(x, y)\n  print('building well')\nend\n"
        "function well_find()\n  return {}\nend\n",
        encoding="utf-8",
    )
    (root / "docs" / "docs" / "tools" / "well.txt").write_text(
        "well\n====\nBuilds a well.\nTags: unavailable\n", encoding="utf-8",
    )
    return root


@pytest.mark.asyncio
async def test_source_search_finds_fixed_string_match(dfhack_source_root):
    _text, structured = await kt._source_search(
        "consultant", {"pattern": "well_build"}, dfhack_source_root=str(dfhack_source_root),
    )
    assert structured["returned_count"] == 1
    assert structured["matches"][0]["path"] == "scripts/df-overseer-well.lua"
    assert structured["matches"][0]["line"] == 2


@pytest.mark.asyncio
async def test_source_search_regex_mode(dfhack_source_root):
    _text, structured = await kt._source_search(
        "consultant", {"pattern": r"well_\w+\(", "regex": True}, dfhack_source_root=str(dfhack_source_root),
    )
    paths_and_lines = {(m["path"], m["line"]) for m in structured["matches"]}
    assert ("scripts/df-overseer-well.lua", 2) in paths_and_lines
    assert ("scripts/df-overseer-well.lua", 5) in paths_and_lines


@pytest.mark.asyncio
async def test_source_search_invalid_regex_refused(dfhack_source_root):
    with pytest.raises(kt.KnowledgeToolError, match="invalid regex"):
        await kt._source_search(
            "consultant", {"pattern": "(unclosed", "regex": True}, dfhack_source_root=str(dfhack_source_root),
        )


@pytest.mark.asyncio
async def test_source_search_path_prefix_restricts_scope(dfhack_source_root):
    _text, structured = await kt._source_search(
        "consultant", {"pattern": "unavailable", "path_prefix": "docs"}, dfhack_source_root=str(dfhack_source_root),
    )
    assert structured["returned_count"] == 1
    assert structured["matches"][0]["path"] == "docs/docs/tools/well.txt"


@pytest.mark.asyncio
async def test_source_search_max_matches_caps_and_flags_truncated(dfhack_source_root):
    (dfhack_source_root / "scripts" / "many.lua").write_text("\n".join("needle" for _ in range(10)), encoding="utf-8")
    _text, structured = await kt._source_search(
        "consultant", {"pattern": "needle", "max_matches": 3}, dfhack_source_root=str(dfhack_source_root),
    )
    assert structured["returned_count"] == 3
    assert structured["truncated"] is True


@pytest.mark.asyncio
async def test_source_read_returns_requested_line_range(dfhack_source_root):
    _text, structured = await kt._source_read(
        "consultant", {"path": "scripts/df-overseer-well.lua", "start_line": 2, "end_line": 3},
        dfhack_source_root=str(dfhack_source_root),
    )
    assert structured["lines"] == [
        {"n": 2, "text": "function well_build(x, y)"},
        {"n": 3, "text": "  print('building well')"},
    ]
    assert structured["total_lines"] == 7


@pytest.mark.asyncio
async def test_source_read_missing_file_refused(dfhack_source_root):
    with pytest.raises(kt.KnowledgeToolError, match="no such file"):
        await kt._source_read("consultant", {"path": "scripts/nope.lua"}, dfhack_source_root=str(dfhack_source_root))


@pytest.mark.parametrize("bad_path", ["../outside.lua", "/etc/passwd", "scripts/../../outside.lua"])
@pytest.mark.asyncio
async def test_source_read_path_traversal_refused(dfhack_source_root, bad_path):
    with pytest.raises(kt.KnowledgeToolError):
        await kt._source_read("consultant", {"path": bad_path}, dfhack_source_root=str(dfhack_source_root))


@pytest.mark.asyncio
async def test_source_search_or_read_without_configured_root_refused():
    with pytest.raises(kt.KnowledgeToolError, match="no DFHack source root configured"):
        await kt._source_search("consultant", {"pattern": "x"}, dfhack_source_root=None)
    with pytest.raises(kt.KnowledgeToolError, match="no DFHack source root configured"):
        await kt._source_read("consultant", {"path": "x"}, dfhack_source_root=None)


@pytest.mark.asyncio
async def test_source_root_that_does_not_exist_refused(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(kt.KnowledgeToolError, match="does not exist"):
        await kt._source_search("consultant", {"pattern": "x"}, dfhack_source_root=str(missing))


@pytest.mark.asyncio
async def test_source_read_span_is_capped(dfhack_source_root):
    with pytest.raises(kt.KnowledgeToolError, match="end_line"):
        await kt._source_read(
            "consultant", {"path": "scripts/df-overseer-well.lua", "start_line": 1, "end_line": 1000},
            dfhack_source_root=str(dfhack_source_root),
        )


# --------------------------------------------------------------------------
# call(): dispatch and unknown-id assertion
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_dispatches_each_known_tool_id(wiki_snapshot, dfhack_source_root):
    text, _structured = await kt.call(
        kt.WIKI_LOOKUP, "consultant", {}, wiki_snapshot_path=str(wiki_snapshot),
    )
    assert "<wiki_index" in text

    text, _structured = await kt.call(
        kt.DFHACK_SOURCE_SEARCH, "consultant", {"pattern": "well_build"}, dfhack_source_root=str(dfhack_source_root),
    )
    assert "<dfhack_source_search" in text

    text, _structured = await kt.call(
        kt.DFHACK_SOURCE_READ, "consultant", {"path": "scripts/df-overseer-well.lua"}, dfhack_source_root=str(dfhack_source_root),
    )
    assert "<dfhack_source_read" in text

    text, _structured = await kt.call(
        kt.WEB_SEARCH, "consultant", {"query": "well"}, brave_api_key="fakekey1234567890",
        http_get=_brave_ok([]),
    )
    assert "<web_search" in text

    text, _structured = await kt.call(
        kt.WEB_FETCH, "consultant", {"url": "https://example.com/"},
        http_get=_fixed_response(200, {"Content-Type": "text/html"}, b"<p>hi</p>"),
    )
    assert "<web_fetch" in text


@pytest.mark.asyncio
async def test_call_defaults_http_get_to_the_real_implementation(local_server):
    """call() with no http_get override falls back to _real_http_get, which
    the SSRF guard runs ahead of -- proven by refusing the exact throwaway
    local server test_real_http_get_fetches_from_a_local_server proved
    reachable, entirely offline."""
    host, port = local_server
    with pytest.raises(kt.KnowledgeToolError, match="private/loopback"):
        await kt.call(kt.WEB_FETCH, "consultant", {"url": f"http://{host}:{port}/"})


# --------------------------------------------------------------------------
# registry.py wiring: NATIVE_TOOLS merges cleanly, no id collisions
# --------------------------------------------------------------------------


def test_native_tools_merge_into_the_registry_without_collision():
    reg = load_registry(native_tools=kt.NATIVE_TOOLS)
    for tool_id in kt.NATIVE_TOOL_IDS:
        assert tool_id in reg
        assert reg.get(tool_id) is kt.NATIVE_TOOLS[tool_id]
    assert "overview.get" in reg  # the real manifest's own tools are still there


def test_no_native_tool_here_sets_mutates_or_knowledge_scope():
    """Per this module's own docstring: read-only, and knowledge_scope is
    deliberately never set (roles.py rule 7 treats a missing attribute as
    'not this rule's concern', never as omniscient)."""
    for tool in kt.NATIVE_TOOLS.values():
        assert tool.mutates is False
        assert getattr(tool, "knowledge_scope", None) is None


def test_describe_returns_a_schema_for_every_id():
    for tool_id, tool in kt.NATIVE_TOOLS.items():
        description, schema = tool.describe("consultant")
        assert isinstance(description, str) and description
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
