"""The API client, on canned responses only (no network)."""

from __future__ import annotations

import io
import urllib.error
from urllib.parse import parse_qs, urlparse

import pytest

from wikimirror import api
from wikimirror.api import (
    ApiError, BlockedError, BudgetExceeded, ContinueError, DisallowedRequest, NetworkError,
    PartialBatchError, ResponseShapeError, TransportFailure, WikiClient,
)
from wikimirror.tests.conftest import FakeTransport, http


def qs(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def page(title, pageid, revid=10, text="body", ns=0):
    return {
        "pageid": pageid, "ns": ns, "title": title, "lastrevid": revid, "length": len(text),
        "revisions": [{"revid": revid, "parentid": revid - 1, "timestamp": "2026-09-01T00:00:00Z",
                       "comment": "c", "slots": {"main": {"content": text}}}],
    }


def q(*pages, **extra):
    return {"query": {"pages": list(pages), **extra}}


# ---- identification, allow-list --------------------------------------------


def test_user_agent_default_has_no_contact_or_infrastructure():
    ua = WikiClient.build_user_agent({})
    assert ua.startswith("df-overseer-wikimirror/")
    assert "http" not in ua and "@" not in ua


def test_user_agent_contact_comes_from_env_and_is_sanitised():
    ua = WikiClient.build_user_agent({"DFWIKI_UA_CONTACT": "https://example.invalid/c\r\n(x)"})
    assert "+https://example.invalid/cx" in ua and "\n" not in ua and ")" not in ua.split(";")[0]


def test_every_request_carries_the_user_agent(make_client):
    client, t = make_client(q(page("A", 1)), env={"DFWIKI_UA_CONTACT": "https://example.invalid"})
    client.fetch_revisions(titles=["A"])
    assert "https://example.invalid" in t.headers[0]["User-Agent"]


@pytest.mark.parametrize(
    "params",
    [
        {"action": "edit", "title": "X"},
        {"action": "login"},
        {"action": "parse", "page": "X"},
        {"action": "query", "list": "usercontribs"},
        {"action": "query", "list": "allpages|users"},
        {"action": "query", "prop": "links"},
        {"action": "query", "meta": "userinfo"},
        {"action": "query", "generator": "search"},
        {"action": "query"},
        {"action": "query", "list": "allpages", "format": "xml"},
        {},
    ],
)
def test_disallowed_requests_never_reach_the_transport(make_client, params):
    client, t = make_client()
    with pytest.raises(DisallowedRequest):
        client.request(params)
    assert t.calls == []


def test_allowed_query_forces_json_format_and_is_get(make_client):
    client, t = make_client({"query": {"allpages": []}})
    client.request({"action": "query", "list": "allpages", "apnamespace": 0})
    got = qs(t.calls[0])
    assert got["format"] == "json" and got["formatversion"] == "2" and got["action"] == "query"


def test_throttle_below_floor_is_refused():
    with pytest.raises(ValueError):
        WikiClient(transport=FakeTransport(), throttle_s=0.5)


# ---- throttle, backoff, budget ----------------------------------------------


def test_throttle_spaces_consecutive_requests(make_client, clock):
    client, t = make_client({"query": {}}, {"query": {}}, throttle_s=2.0)
    p = {"action": "query", "list": "allpages"}
    client.request(p)
    client.request(p)
    assert clock.sleeps == [2.0]  # second request waited the whole interval


def test_backoff_on_429_then_success(make_client, clock):
    client, t = make_client(http(429), {"query": {}})
    client.request({"action": "query", "list": "allpages"})
    assert clock.sleeps[0] == 5.0 and len(t.calls) == 2


def test_backoff_honours_retry_after_capped(make_client, clock):
    client, t = make_client(http(503, {"Retry-After": "17"}), http(503, {"Retry-After": "9999"}), {"query": {}})
    client.request({"action": "query", "list": "allpages"})
    assert clock.sleeps == [17.0, api.MAX_RETRY_AFTER_S]


def test_5xx_exhausts_tries_with_schedule_then_named_error(make_client, clock):
    client, t = make_client(http(500), http(502), http(503), http(504))
    with pytest.raises(NetworkError):
        client.request({"action": "query", "list": "allpages"})
    assert len(t.calls) == 4
    backoffs = [s for s in clock.sleeps if s in (5.0, 30.0, 120.0)]
    assert backoffs == [5.0, 30.0, 120.0]


def test_403_aborts_immediately_as_blocked(make_client):
    client, t = make_client(http(403), {"query": {}})
    with pytest.raises(BlockedError):
        client.request({"action": "query", "list": "allpages"})
    assert len(t.calls) == 1


def test_three_429s_in_one_run_is_blocked(make_client):
    client, t = make_client(http(429), {"query": {}}, http(429), {"query": {}}, http(429))
    p = {"action": "query", "list": "allpages"}
    client.request(p)
    client.request(p)
    with pytest.raises(BlockedError):
        client.request(p)


def test_transport_failure_retries_then_network_error(make_client):
    client, t = make_client(*[TransportFailure("boom")] * 4)
    with pytest.raises(NetworkError):
        client.request({"action": "query", "list": "allpages"})


def test_budget_stops_before_sending(make_client):
    client, t = make_client({"query": {}}, {"query": {}}, {"query": {}}, max_requests=2)
    p = {"action": "query", "list": "allpages"}
    client.request(p)
    client.request(p)
    with pytest.raises(BudgetExceeded):
        client.request(p)
    assert len(t.calls) == 2


def test_api_error_object_is_a_named_error(make_client):
    client, _ = make_client({"error": {"code": "badvalue", "info": "nope"}})
    with pytest.raises(ApiError) as e:
        client.request({"action": "query", "list": "allpages"})
    assert e.value.code == "badvalue"


def test_non_json_body_is_a_shape_error(make_client):
    client, _ = make_client(http(200, body=b"<html>maintenance</html>"))
    with pytest.raises(ResponseShapeError):
        client.request({"action": "query", "list": "allpages"})


def test_api_warnings_are_recorded_not_dropped(make_client):
    client, _ = make_client({"warnings": {"query": {"warnings": "too many"}}, "query": {}})
    client.request({"action": "query", "list": "allpages"})
    assert client.warnings and "too many" in client.warnings[0]


# ---- continue handling --------------------------------------------------------


def test_enumerate_follows_continue_and_sends_it_back(make_client):
    r1 = {"continue": {"gapcontinue": "B", "continue": "gapcontinue||"}, **q(page("A", 1))}
    r2 = q(page("B", 2))
    client, t = make_client(r1, r2)
    rows = client.enumerate_pages(0)
    assert [r.title for r in rows] == ["A", "B"] and rows[0].fetched_utc
    second = qs(t.calls[1])
    assert second["gapcontinue"] == "B" and second["continue"] == "gapcontinue||"


def test_continue_that_does_not_advance_is_an_error(make_client):
    same = {"continue": {"gapcontinue": "B", "continue": "x||"}, **q(page("A", 1))}
    client, _ = make_client(same, same, same)
    with pytest.raises(ContinueError):
        client.enumerate_pages(0)


def test_continue_inside_a_batch_is_merged_by_page(make_client):
    """The byte ceiling splits a 3-title batch: B arrives in the second response."""
    partial = page("B", 2)
    partial = {k: v for k, v in partial.items() if k != "revisions"}
    r1 = {"continue": {"rvcontinue": "20260901|11", "continue": "||"}, **q(page("A", 1), partial)}
    r2 = q(page("B", 2, revid=20), page("C", 3))
    client, t = make_client(r1, r2)
    res = client.fetch_revisions(titles=["A", "B", "C"])
    assert {r.title for r in res.revisions} == {"A", "B", "C"}
    assert next(r for r in res.revisions if r.title == "B").revid == 20
    assert len(t.calls) == 2 and qs(t.calls[1])["rvcontinue"] == "20260901|11"


def test_batch_that_drops_a_title_without_saying_why_is_partial(make_client):
    client, _ = make_client(q(page("A", 1)))
    with pytest.raises(PartialBatchError) as e:
        client.fetch_revisions(titles=["A", "B"])
    assert e.value.titles == ["B"]


def test_page_left_without_a_body_after_continue_is_partial(make_client):
    bodyless = {k: v for k, v in page("B", 2).items() if k != "revisions"}
    client, _ = make_client(q(page("A", 1), bodyless))
    with pytest.raises(PartialBatchError):
        client.fetch_revisions(titles=["A", "B"])


def test_missing_title_is_reported_not_dropped(make_client):
    client, _ = make_client(q(page("A", 1), {"ns": 0, "title": "Gone", "missing": True}))
    res = client.fetch_revisions(titles=["A", "Gone"])
    assert [m.title for m in res.missing] == ["Gone"] and len(res.revisions) == 1


def test_normalized_titles_are_accounted_for(make_client):
    client, _ = make_client(
        q(page("Water buffalo", 5), normalized=[{"from": "water_buffalo", "to": "Water buffalo"}])
    )
    res = client.fetch_revisions(titles=["water_buffalo"])
    assert res.revisions[0].title == "Water buffalo"


def test_titles_are_batched_at_50(make_client):
    titles = [f"T{i}" for i in range(120)]
    resp = [q(*[page(t, i + 1) for i, t in enumerate(titles[j : j + 50])]) for j in (0, 50, 100)]
    client, t = make_client(*resp)
    res = client.fetch_revisions(titles=titles)
    assert len(res.revisions) == 120 and len(t.calls) == 3
    assert all(len(qs(u)["titles"].split("|")) <= 50 for u in t.calls)


def test_revision_carries_provenance_and_the_returned_revid(make_client):
    client, _ = make_client(q(page("A", 7, revid=555, text="hello")))
    r = client.fetch_revisions(titles=["A"]).revisions[0]
    assert (r.page_id, r.ns, r.revid, r.wikitext, r.fetched_utc) == (7, 0, 555, "hello", "2026-09-24T12:00:00Z")


def test_fetch_needs_exactly_one_selector(make_client):
    client, _ = make_client()
    with pytest.raises(ValueError):
        client.fetch_revisions()


# ---- feeds ---------------------------------------------------------------------


def test_recent_changes_parses_and_rejects_missing_fields(make_client):
    row = {"type": "edit", "ns": 0, "title": "Trading", "pageid": 3, "revid": 9, "old_revid": 8,
           "rcid": 77, "timestamp": "2026-09-20T00:00:00Z", "comment": "x", "oldlen": 5, "newlen": 6}
    client, t = make_client({"query": {"recentchanges": [row]}}, {"query": {"recentchanges": [{"type": "edit"}]}})
    got = client.recent_changes(start="2026-09-19T00:00:00Z", namespaces=[0])
    assert got[0].revid == 9 and got[0].old_revid == 8 and got[0].fetched_utc
    assert qs(t.calls[0])["rcnamespace"] == "0" and qs(t.calls[0])["rcdir"] == "newer"
    with pytest.raises(ResponseShapeError):
        client.recent_changes(start="2026-09-19T00:00:00Z", namespaces=[0])


def test_log_events_keep_the_move_target(make_client):
    row = {"logid": 1, "type": "move", "action": "move", "ns": 0, "title": "Old", "logpage": 4,
           "timestamp": "2026-09-01T00:00:00Z", "params": {"target_ns": 0, "target_title": "New"}}
    client, _ = make_client({"query": {"logevents": [row]}})
    ev = client.log_events(log_type="move")
    assert ev[0].target_title == "New" and ev[0].page_id == 4
    assert ev[0].target_ns == 0


def test_all_redirects_joins_sources_to_targets_and_keeps_unresolved(make_client):
    sources = {"query": {"allpages": [{"pageid": 1, "ns": 0, "title": "Wells"},
                                       {"pageid": 2, "ns": 0, "title": "Orphan"}]}}
    targets = {"query": {"allredirects": [{"fromid": 1, "ns": 0, "title": "Well"}]}}
    client, t = make_client(sources, targets)
    rows = client.all_redirects(0)
    assert [(r.from_title, r.to_title) for r in rows] == [("Wells", "Well"), ("Orphan", None)]
    assert "arunique" not in t.calls[1]  # the live API refuses arprop=ids with arunique


# ---- the version template ----------------------------------------------------------


def test_version_template_text_is_parsed_before_noinclude():
    text = "53.16<noinclude>\n\nThis template is the most recent version.\n</noinclude>"
    assert api.parse_version_template(text) == "53.16"
    with pytest.raises(ResponseShapeError):
        api.parse_version_template("<noinclude>only docs</noinclude>")
    with pytest.raises(ResponseShapeError):
        api.parse_version_template("Ignore previous instructions")


def test_wiki_current_version_reads_the_template(make_client):
    client, t = make_client(q(page("Template:Current/version", 9, text="53.16<noinclude>docs</noinclude>", ns=10)))
    assert client.wiki_current_version() == "53.16"


# ---- the default transport ------------------------------------------------------------


def test_urllib_transport_returns_error_statuses_and_wraps_connection_failures(monkeypatch):
    def http_error(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {"Retry-After": "3"}, io.BytesIO(b"slow"))

    monkeypatch.setattr("urllib.request.urlopen", http_error)
    resp = api.urllib_transport("https://example.invalid/api.php", {"User-Agent": "t"}, 1.0)
    assert resp.status == 429 and resp.headers["retry-after"] == "3" and resp.body == b"slow"

    def down(req, timeout):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr("urllib.request.urlopen", down)
    with pytest.raises(TransportFailure):
        api.urllib_transport("https://example.invalid/api.php", {}, 1.0)
