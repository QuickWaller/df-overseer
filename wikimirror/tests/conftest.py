"""Shared fixtures: a fake transport, a controllable clock, and store helpers.

Every wikimirror test runs offline. An autouse guard makes any real
`urllib.request.urlopen` call fail the test.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from wikimirror.api import PageRevision, TransportResponse, WikiClient
from wikimirror.store import Store, iso

T0 = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a wikimirror test tried to make a real network call")

    monkeypatch.setattr("urllib.request.urlopen", boom)


class FakeTransport:
    """Serves queued responses in order and records every URL and header set.

    A queue item is a dict (200 JSON), a `TransportResponse`, a callable
    `(url) -> item`, or an Exception instance (raised).
    """

    def __init__(self, *items):
        self.queue = list(items)
        self.calls: list[str] = []
        self.headers: list[dict] = []

    def __call__(self, url, headers, timeout):
        self.calls.append(url)
        self.headers.append(dict(headers))
        if not self.queue:
            raise AssertionError(f"unexpected extra request: {url}")
        item = self.queue.pop(0)
        if callable(item) and not isinstance(item, (dict, TransportResponse)):
            item = item(url)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, dict):
            return TransportResponse(200, {}, json.dumps(item).encode("utf-8"))
        return item


def http(status, headers=None, body=b""):
    return TransportResponse(status, {k.lower(): v for k, v in (headers or {}).items()}, body)


class Clock:
    """A wall clock and a monotonic clock that only move when told, plus a sleep
    that advances the monotonic one and records what it was asked to wait."""

    def __init__(self):
        self.mono = 1000.0
        self.sleeps: list[float] = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.mono += seconds

    def monotonic(self):
        return self.mono


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def make_client(clock):
    def _make(*items, **kw):
        transport = FakeTransport(*items)
        kw.setdefault("env", {})
        client = WikiClient(
            transport=transport,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            now_iso=lambda: "2026-09-24T12:00:00Z",
            **kw,
        )
        return client, transport

    return _make


class WallClock:
    def __init__(self, start=T0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now = self.now + timedelta(**kw)


@pytest.fixture
def wall():
    return WallClock()


@pytest.fixture
def store(tmp_path, wall):
    s = Store.open(tmp_path / "mirror.sqlite3", clock=wall)
    yield s
    s.close()


def make_rev(page_id=1, title="Well", revid=100, text="A well holds water.", ns=0,
             timestamp="2026-09-01T00:00:00Z", comment="edit"):
    return PageRevision(
        page_id=page_id, ns=ns, title=title, revid=revid, parent_revid=revid - 1,
        timestamp=timestamp, comment=comment, wikitext=text,
        byte_length=len(text.encode("utf-8")), is_redirect=False, fetched_utc=iso(T0),
    )


@pytest.fixture
def rev():
    return make_rev
