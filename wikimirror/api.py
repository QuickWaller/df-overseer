"""Allow-listed, read-only MediaWiki API client for the wiki mirror.

`docs/CONSULTANT-WIKI.md` sections 3.3 and 4. What it enforces:

* GET only, `action=query` (and `paraminfo`) only, and only the query modules
  the design names (`list=recentchanges|logevents|allpages|allredirects`,
  `prop=info|revisions`, `meta=siteinfo`, `generator=allpages`). Anything else
  raises `DisallowedRequest` before a request is built. No login, no write.
* A User-Agent from `DFWIKI_UA_CONTACT` (optional contact appended) over a
  project default that carries no personal or infrastructure detail.
* A throttle (never below `MIN_THROTTLE_S`, default 2 s), backoff on 429/5xx
  and the API's own `ratelimited` error (honouring `Retry-After`), abort as
  `BlockedError` on a 403 or a third 429 in one run, and a per-run request
  budget (`BudgetExceeded`).
* `continue` handling, including inside a batch: `query_all` follows the
  continuation and merges page entries by page id, and `fetch_revisions`
  raises `PartialBatchError` if any requested title ends up neither fetched
  nor reported missing. There is no default that looks like "nothing changed".
* An injectable transport (and clock, sleep), so every test runs on canned
  responses. The default transport is `urllib`; this module makes no network
  call unless a caller constructs it without one and issues a request.

Fetched wikitext is data. It is returned, never interpreted.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Sequence

from wikimirror import __version__

API_URL = "https://dwarffortresswiki.org/api.php"
WIKI_BASE = "https://dwarffortresswiki.org"
ENV_UA_CONTACT = "DFWIKI_UA_CONTACT"
DEFAULT_UA = f"df-overseer-wikimirror/{__version__} (read-only mirror for a hobby project)"

MIN_THROTTLE_S = 1.0
DEFAULT_THROTTLE_S = 2.0
DEFAULT_MAX_REQUESTS = 400
BACKOFF_SCHEDULE_S = (5.0, 30.0, 120.0)
MAX_TRIES = 4
MAX_RETRY_AFTER_S = 300.0
MAX_429_PER_RUN = 3
BATCH_SIZE = 50  # anonymous cap on `titles` / `revids`
MAX_CONTINUES = 200

ALLOWED_ACTIONS = frozenset({"query", "paraminfo"})
ALLOWED_LISTS = frozenset({"recentchanges", "logevents", "allpages", "allredirects"})
ALLOWED_PROPS = frozenset({"info", "revisions"})
ALLOWED_METAS = frozenset({"siteinfo"})
ALLOWED_GENERATORS = frozenset({"allpages"})
# Parameters the client itself owns; a caller may not override them.
_FORCED = {"format": "json", "formatversion": "2"}


# ---- errors: every failure is named -----------------------------------------


class WikiApiError(Exception):
    """Base class for every named failure of this client."""


class DisallowedRequest(WikiApiError):
    """The request is outside the read-only allow-list. Nothing was sent."""


class BudgetExceeded(WikiApiError):
    """The per-run request budget is spent. Nothing further was sent."""


class BlockedError(WikiApiError):
    """A 403, or repeated 429s: the wiki is refusing us. Stop the run."""


class NetworkError(WikiApiError):
    """The transport failed or the server kept returning 5xx after backoff."""


class ApiError(WikiApiError):
    """The API answered 200 with an `error` object."""

    def __init__(self, code: str, info: str):
        super().__init__(f"{code}: {info}")
        self.code = code
        self.info = info


class ResponseShapeError(WikiApiError):
    """A response was not JSON, or lacked a field the caller relies on."""


class ContinueError(WikiApiError):
    """The continuation did not advance, or ran past the safety cap."""


class PartialBatchError(WikiApiError):
    """A batch returned fewer pages than asked for and did not say why."""

    def __init__(self, titles: Sequence[str]):
        super().__init__(f"batch incomplete, no body and not reported missing: {sorted(titles)}")
        self.titles = list(titles)


# ---- transport --------------------------------------------------------------


@dataclass(frozen=True)
class TransportResponse:
    status: int
    headers: Mapping[str, str]  # keys lower-cased
    body: bytes


Transport = Callable[[str, Mapping[str, str], float], TransportResponse]


class TransportFailure(Exception):
    """Raised by a transport for a connection-level failure (no HTTP status)."""


def urllib_transport(url: str, headers: Mapping[str, str], timeout: float) -> TransportResponse:
    """The default transport: one GET, HTTP error statuses returned not raised."""
    req = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https constant)
            return TransportResponse(
                resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
            )
    except urllib.error.HTTPError as exc:
        return TransportResponse(
            exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, exc.read() or b""
        )
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise TransportFailure(str(exc)) from exc


# ---- typed results (every one carries provenance) ---------------------------


@dataclass(frozen=True)
class PageInfo:
    """One row of the allpages enumeration (the revid sweep)."""

    page_id: int
    ns: int
    title: str
    lastrevid: int
    length: int
    touched: str | None
    is_redirect: bool
    fetched_utc: str


@dataclass(frozen=True)
class PageRevision:
    """A fetched revision: the unit the store ingests."""

    page_id: int
    ns: int
    title: str
    revid: int
    parent_revid: int | None
    timestamp: str
    comment: str
    wikitext: str
    byte_length: int
    is_redirect: bool
    fetched_utc: str


@dataclass(frozen=True)
class Missing:
    """A requested title the wiki says does not exist (deleted, or a race)."""

    title: str
    fetched_utc: str


@dataclass(frozen=True)
class FetchResult:
    revisions: list[PageRevision]
    missing: list[Missing]
    requests: int


@dataclass(frozen=True)
class RecentChange:
    type: str
    ns: int
    title: str
    page_id: int
    revid: int
    old_revid: int
    rcid: int
    timestamp: str
    comment: str
    old_len: int | None
    new_len: int | None
    log_type: str | None
    log_action: str | None
    target_title: str | None
    fetched_utc: str


@dataclass(frozen=True)
class LogEvent:
    log_id: int
    log_type: str
    action: str
    ns: int
    title: str
    page_id: int
    timestamp: str
    comment: str
    target_title: str | None
    fetched_utc: str
    target_ns: int | None = None


@dataclass(frozen=True)
class Redirect:
    from_title: str
    from_ns: int
    to_title: str | None  # None: no target row found (unresolved, reported)
    to_ns: int | None
    fetched_utc: str


_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")


def parse_version_template(wikitext: str) -> str:
    """Read the game version out of `Template:Current/version`.

    Verified live 2026-09-24: the text is `53.16<noinclude>...documentation...`,
    not the bare `53.16` the research note recorded, so the part before
    `<noinclude>` is the version. Anything that is not dotted digits after that
    is a named error, never a version string of unknown meaning.
    """
    head = wikitext.split("<noinclude>", 1)[0].strip()
    if not _VERSION_RE.match(head):
        raise ResponseShapeError(f"Template:Current/version is not a version number: {head[:60]!r}")
    return head


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def permalink(title: str, revid: int) -> str:
    """Stable per-revision URL (design 3.3 attribution)."""
    return f"{WIKI_BASE}/index.php?title={urllib.parse.quote(title.replace(' ', '_'))}&oldid={int(revid)}"


def history_url(title: str) -> str:
    return f"{WIKI_BASE}/index.php?title={urllib.parse.quote(title.replace(' ', '_'))}&action=history"


def _require(obj: Mapping[str, Any], key: str, what: str) -> Any:
    if key not in obj:
        raise ResponseShapeError(f"{what} lacks required field {key!r}: {sorted(obj)}")
    return obj[key]


# ---- the client -------------------------------------------------------------


@dataclass
class WikiClient:
    transport: Transport | None = None
    api_url: str = API_URL
    throttle_s: float = DEFAULT_THROTTLE_S
    max_requests: int = DEFAULT_MAX_REQUESTS
    timeout_s: float = 30.0
    user_agent: str | None = None
    env: Mapping[str, str] | None = None
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    now_iso: Callable[[], str] = _utcnow_iso

    requests_made: int = field(default=0, init=False)
    warnings: list[str] = field(default_factory=list, init=False)
    _last_request_at: float | None = field(default=None, init=False, repr=False)
    _count_429: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.throttle_s < MIN_THROTTLE_S:
            raise ValueError(
                f"throttle_s={self.throttle_s} is below the politeness floor {MIN_THROTTLE_S}"
            )
        if self.max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        if self.transport is None:
            self.transport = urllib_transport
        if self.user_agent is None:
            self.user_agent = self.build_user_agent(self.env)

    @staticmethod
    def build_user_agent(env: Mapping[str, str] | None = None) -> str:
        """Project default; the contact (never committed) comes from the env."""
        env = os.environ if env is None else env
        contact = (env.get(ENV_UA_CONTACT) or "").strip()
        if not contact:
            return DEFAULT_UA
        # Strip anything that could break the header.
        contact = "".join(ch for ch in contact if ch.isprintable() and ch not in "()\r\n")
        return f"df-overseer-wikimirror/{__version__} (+{contact}; read-only mirror for a hobby project)"

    # -- validation ----------------------------------------------------------

    @staticmethod
    def validate_params(params: Mapping[str, Any]) -> dict[str, str]:
        """Return the outgoing parameters or raise `DisallowedRequest`."""
        out: dict[str, str] = {}
        for key, value in params.items():
            if key in _FORCED and str(value) != _FORCED[key]:
                raise DisallowedRequest(f"parameter {key!r} is fixed by the client")
            out[str(key)] = str(value)
        action = out.get("action")
        if action not in ALLOWED_ACTIONS:
            raise DisallowedRequest(f"action {action!r} is not on the read-only allow-list")
        for key, allowed in (
            ("list", ALLOWED_LISTS),
            ("prop", ALLOWED_PROPS),
            ("meta", ALLOWED_METAS),
            ("generator", ALLOWED_GENERATORS),
        ):
            if key in out:
                for part in out[key].split("|"):
                    if part not in allowed:
                        raise DisallowedRequest(f"{key}={part!r} is not on the allow-list")
        if action == "query" and not any(k in out for k in ("list", "prop", "meta", "generator")):
            raise DisallowedRequest("a query must name list, prop, meta or generator")
        out.update(_FORCED)
        return out

    # -- one request ---------------------------------------------------------

    def _wait_for_throttle(self) -> None:
        if self._last_request_at is not None:
            gap = self.monotonic() - self._last_request_at
            if gap < self.throttle_s:
                self.sleep(self.throttle_s - gap)

    def request(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """One allow-listed GET with throttle, backoff and budget. Returns the JSON."""
        out = self.validate_params(params)
        url = f"{self.api_url}?{urllib.parse.urlencode(out)}"
        headers = {"User-Agent": self.user_agent or DEFAULT_UA, "Accept": "application/json"}
        last_problem = "no attempt made"
        for attempt in range(MAX_TRIES):
            if self.requests_made >= self.max_requests:
                raise BudgetExceeded(
                    f"per-run budget of {self.max_requests} requests is spent"
                )
            self._wait_for_throttle()
            self.requests_made += 1
            self._last_request_at = self.monotonic()
            try:
                resp = self.transport(url, headers, self.timeout_s)  # type: ignore[misc]
            except TransportFailure as exc:
                last_problem = f"transport failure: {exc}"
                self._backoff(attempt, None)
                continue
            status = resp.status
            if status == 403:
                raise BlockedError("HTTP 403 from the wiki: refusing to continue")
            if status == 429:
                self._count_429 += 1
                if self._count_429 >= MAX_429_PER_RUN:
                    raise BlockedError(f"{self._count_429} HTTP 429 responses in one run")
                last_problem = "HTTP 429"
                self._backoff(attempt, resp.headers.get("retry-after"))
                continue
            if 500 <= status < 600:
                last_problem = f"HTTP {status}"
                self._backoff(attempt, resp.headers.get("retry-after"))
                continue
            if status != 200:
                raise NetworkError(f"unexpected HTTP {status}")
            data = self._decode(resp.body)
            err = data.get("error")
            if err is not None:
                code = str(err.get("code", "unknown")) if isinstance(err, dict) else "unknown"
                info = str(err.get("info", err)) if isinstance(err, dict) else str(err)
                if code == "ratelimited":
                    self._count_429 += 1
                    if self._count_429 >= MAX_429_PER_RUN:
                        raise BlockedError("repeated API rate-limit errors in one run")
                    last_problem = "API ratelimited"
                    self._backoff(attempt, None)
                    continue
                raise ApiError(code, info)
            self._note_warnings(data)
            return data
        raise NetworkError(f"gave up after {MAX_TRIES} tries: {last_problem}")

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        if attempt >= MAX_TRIES - 1:
            return  # final try failed; the loop ends and raises
        delay = BACKOFF_SCHEDULE_S[min(attempt, len(BACKOFF_SCHEDULE_S) - 1)]
        if retry_after:
            try:
                delay = min(max(float(retry_after), 0.0), MAX_RETRY_AFTER_S)
            except ValueError:
                pass  # an HTTP-date form: keep the scheduled delay
        self.sleep(delay)

    @staticmethod
    def _decode(body: bytes) -> dict[str, Any]:
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResponseShapeError(f"response body is not JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ResponseShapeError("response JSON is not an object")
        return data

    def _note_warnings(self, data: Mapping[str, Any]) -> None:
        warns = data.get("warnings")
        if warns:
            self.warnings.append(json.dumps(warns, sort_keys=True)[:500])

    # -- continuation --------------------------------------------------------

    def query_all(self, params: Mapping[str, Any], *, max_continues: int = MAX_CONTINUES) -> dict[str, Any]:
        """Follow `continue` to the end and return the merged `query` object.

        Pages (a list under formatversion 2) are merged by page id, so a batch
        split across responses by a byte ceiling comes back whole. Every other
        list under `query` is concatenated in order. A continuation that does
        not change, or exceeds `max_continues`, raises `ContinueError`.
        """
        merged: dict[str, Any] = {}
        current = dict(params)
        seen: set[tuple[tuple[str, str], ...]] = set()
        for _ in range(max_continues + 1):
            data = self.request(current)
            _merge_query(merged, data.get("query", {}))
            cont = data.get("continue")
            if not cont:
                return merged
            if not isinstance(cont, dict):
                raise ResponseShapeError("`continue` is not an object")
            token = tuple(sorted((str(k), str(v)) for k, v in cont.items()))
            if token in seen:
                raise ContinueError(f"continuation did not advance: {dict(cont)}")
            seen.add(token)
            current = {**params, **{str(k): v for k, v in cont.items()}}
        raise ContinueError(f"more than {max_continues} continuations")

    # -- high-level reads ----------------------------------------------------

    def wiki_current_version(self) -> str:
        """The wiki's own statement of the current game version (design 2.3)."""
        result = self.fetch_revisions(titles=["Template:Current/version"])
        if result.missing or not result.revisions:
            raise ResponseShapeError("Template:Current/version is missing or has no revision")
        return parse_version_template(result.revisions[0].wikitext)

    def enumerate_pages(self, namespace: int, *, filterredir: str = "nonredirects", limit: int = 500) -> list[PageInfo]:
        """The revid sweep and the full-pull enumeration: title, lastrevid, length."""
        fetched = self.now_iso()
        q = self.query_all(
            {
                "action": "query",
                "generator": "allpages",
                "gapnamespace": namespace,
                "gapfilterredir": filterredir,
                "gaplimit": limit,
                "prop": "info",
            }
        )
        rows = []
        for page in q.get("pages", []):
            if page.get("missing") or page.get("invalid"):
                raise ResponseShapeError(f"allpages listed a missing/invalid page: {page}")
            rows.append(
                PageInfo(
                    page_id=int(_require(page, "pageid", "allpages page")),
                    ns=int(_require(page, "ns", "allpages page")),
                    title=str(_require(page, "title", "allpages page")),
                    lastrevid=int(_require(page, "lastrevid", "allpages page")),
                    length=int(_require(page, "length", "allpages page")),
                    touched=page.get("touched"),
                    is_redirect=bool(page.get("redirect", False)),
                    fetched_utc=fetched,
                )
            )
        return rows

    def all_redirects(self, source_namespace: int, target_namespaces: Iterable[int] = (0,)) -> list[Redirect]:
        """Redirect pages of `source_namespace` joined to their targets.

        Verified shape (one live probe): `list=allredirects` returns rows of
        `{fromid, ns, title}` where `title` is the TARGET and `ns` the target's
        namespace, filtered by the target namespace (`arnamespace`), with no
        source title; and `arprop=ids` cannot be combined with `arunique`. So the
        source titles come from `list=allpages&apfilterredir=redirects` and the
        two are joined on page id. A redirect page whose page id has no target
        row keeps `to_title = None`: an unresolved redirect is reported, never
        dropped.
        """
        fetched = self.now_iso()
        sources = self.query_all(
            {
                "action": "query",
                "list": "allpages",
                "apnamespace": source_namespace,
                "apfilterredir": "redirects",
                "aplimit": 500,
            }
        ).get("allpages", [])
        targets: dict[int, tuple[str, int]] = {}
        for tns in target_namespaces:
            rows = self.query_all(
                {
                    "action": "query",
                    "list": "allredirects",
                    "arnamespace": tns,
                    "arprop": "title|ids",
                    "arlimit": 500,
                }
            ).get("allredirects", [])
            for row in rows:
                targets[int(_require(row, "fromid", "allredirects row"))] = (
                    str(_require(row, "title", "allredirects row")),
                    int(row.get("ns", tns)),
                )
        out = []
        for row in sources:
            pid = int(_require(row, "pageid", "allpages redirect row"))
            to_title, to_ns = targets.get(pid, (None, None))
            out.append(
                Redirect(
                    from_title=str(_require(row, "title", "allpages redirect row")),
                    from_ns=int(row.get("ns", source_namespace)),
                    to_title=to_title,
                    to_ns=to_ns,
                    fetched_utc=fetched,
                )
            )
        return out

    def recent_changes(
        self,
        *,
        start: str,
        namespaces: Iterable[int],
        types: Iterable[str] = ("edit", "new", "log"),
        limit: int = 500,
    ) -> list[RecentChange]:
        """The recentchanges feed from `start` forward (design 4.3 step 2)."""
        fetched = self.now_iso()
        q = self.query_all(
            {
                "action": "query",
                "list": "recentchanges",
                "rcdir": "newer",
                "rcstart": start,
                "rcnamespace": "|".join(str(int(n)) for n in namespaces),
                "rctype": "|".join(types),
                "rcprop": "title|ids|timestamp|comment|sizes|loginfo",
                "rclimit": limit,
            }
        )
        out = []
        for row in q.get("recentchanges", []):
            out.append(
                RecentChange(
                    type=str(_require(row, "type", "recentchanges row")),
                    ns=int(_require(row, "ns", "recentchanges row")),
                    title=str(_require(row, "title", "recentchanges row")),
                    page_id=int(_require(row, "pageid", "recentchanges row")),
                    revid=int(_require(row, "revid", "recentchanges row")),
                    old_revid=int(_require(row, "old_revid", "recentchanges row")),
                    rcid=int(_require(row, "rcid", "recentchanges row")),
                    timestamp=str(_require(row, "timestamp", "recentchanges row")),
                    comment=str(row.get("comment", "")),
                    old_len=row.get("oldlen"),
                    new_len=row.get("newlen"),
                    log_type=row.get("logtype"),
                    log_action=row.get("logaction"),
                    target_title=(row.get("logparams") or {}).get("target_title"),
                    fetched_utc=fetched,
                )
            )
        return out

    def log_events(self, *, log_type: str, start: str | None = None, limit: int = 500) -> list[LogEvent]:
        """`logevents` for `delete`, `move` or `restore`-style types, oldest first."""
        fetched = self.now_iso()
        params: dict[str, Any] = {
            "action": "query",
            "list": "logevents",
            "letype": log_type,
            "ledir": "newer",
            "leprop": "ids|title|type|timestamp|comment|details",
            "lelimit": limit,
        }
        if start:
            params["lestart"] = start
        q = self.query_all(params)
        out = []
        for row in q.get("logevents", []):
            out.append(
                LogEvent(
                    log_id=int(_require(row, "logid", "logevents row")),
                    log_type=str(_require(row, "type", "logevents row")),
                    action=str(_require(row, "action", "logevents row")),
                    ns=int(_require(row, "ns", "logevents row")),
                    title=str(_require(row, "title", "logevents row")),
                    page_id=int(row.get("logpage", 0)),
                    timestamp=str(_require(row, "timestamp", "logevents row")),
                    comment=str(row.get("comment", "")),
                    target_title=(row.get("params") or {}).get("target_title"),
                    fetched_utc=fetched,
                    target_ns=(
                        int((row.get("params") or {})["target_ns"])
                        if (row.get("params") or {}).get("target_ns") is not None else None
                    ),
                )
            )
        return out

    def fetch_revisions(
        self,
        *,
        titles: Sequence[str] | None = None,
        revids: Sequence[int] | None = None,
    ) -> FetchResult:
        """Bodies for a set of titles (or revids), 50 per request, `continue`-safe.

        Every requested title must come back either with a revision or as
        `missing`; otherwise `PartialBatchError` (never a shorter list that looks
        complete). The revid stored is the one the response returns, not the
        feed's (design 4.3 step 5).
        """
        if (titles is None) == (revids is None):
            raise ValueError("pass exactly one of titles or revids")
        keys: Sequence[Any] = list(titles if titles is not None else revids)  # type: ignore[arg-type]
        revisions: list[PageRevision] = []
        missing: list[Missing] = []
        before = self.requests_made
        for i in range(0, len(keys), BATCH_SIZE):
            batch = keys[i : i + BATCH_SIZE]
            fetched = self.now_iso()
            params: dict[str, Any] = {
                "action": "query",
                "prop": "revisions|info",
                "rvprop": "ids|timestamp|comment|size|content",
                "rvslots": "main",
            }
            if titles is not None:
                params["titles"] = "|".join(str(t) for t in batch)
            else:
                params["revids"] = "|".join(str(int(r)) for r in batch)
            q = self.query_all(params)
            got, gone, unaccounted = _interpret_batch(q, batch if titles is not None else None, fetched)
            if unaccounted:
                raise PartialBatchError(unaccounted)
            if titles is None and not got and not gone and not q.get("badrevids"):
                raise PartialBatchError([str(r) for r in batch])
            if titles is None:
                bad = q.get("badrevids") or {}
                if bad:
                    raise PartialBatchError([f"revid {k}" for k in bad])
            revisions.extend(got)
            missing.extend(gone)
        return FetchResult(revisions, missing, self.requests_made - before)


# ---- merging and batch interpretation ---------------------------------------


def _merge_query(into: dict[str, Any], part: Mapping[str, Any]) -> None:
    for key, value in part.items():
        if key == "pages" and isinstance(value, list):
            existing = {p.get("pageid", p.get("title")): p for p in into.get("pages", [])}
            order = [p.get("pageid", p.get("title")) for p in into.get("pages", [])]
            for page in value:
                pk = page.get("pageid", page.get("title"))
                if pk in existing:
                    _merge_page(existing[pk], page)
                else:
                    existing[pk] = dict(page)
                    order.append(pk)
            into["pages"] = [existing[k] for k in order]
        elif isinstance(value, list):
            into.setdefault(key, []).extend(value)
        elif isinstance(value, dict):
            into.setdefault(key, {}).update(value)
        else:
            into[key] = value


def _merge_page(into: dict[str, Any], page: Mapping[str, Any]) -> None:
    for key, value in page.items():
        if key == "revisions":
            have = {r.get("revid") for r in into.get("revisions", [])}
            for rev in value:
                if rev.get("revid") not in have:
                    into.setdefault("revisions", []).append(rev)
        elif key not in into:
            into[key] = value


def _interpret_batch(
    q: Mapping[str, Any], requested: Sequence[str] | None, fetched: str
) -> tuple[list[PageRevision], list[Missing], list[str]]:
    normalized: dict[str, str] = {}
    for n in q.get("normalized", []) or []:
        normalized[str(n.get("from"))] = str(n.get("to"))
    got: list[PageRevision] = []
    gone: list[Missing] = []
    seen_titles: set[str] = set()
    for page in q.get("pages", []):
        title = str(page.get("title", ""))
        if page.get("invalid"):
            raise ResponseShapeError(f"invalid title in batch: {page}")
        if page.get("missing"):
            gone.append(Missing(title, fetched))
            seen_titles.add(title)
            continue
        revs = page.get("revisions") or []
        if not revs:
            continue  # incomplete: reported through `unaccounted` below
        rev = revs[0]
        slot = ((rev.get("slots") or {}).get("main")) or {}
        if "content" not in slot:
            continue
        text = slot["content"]
        got.append(
            PageRevision(
                page_id=int(_require(page, "pageid", "page")),
                ns=int(_require(page, "ns", "page")),
                title=title,
                revid=int(_require(rev, "revid", "revision")),
                parent_revid=rev.get("parentid"),
                timestamp=str(_require(rev, "timestamp", "revision")),
                comment=str(rev.get("comment", "")),
                wikitext=str(text),
                byte_length=int(page.get("length", rev.get("size", len(text.encode("utf-8"))))),
                is_redirect=bool(page.get("redirect", False)),
                fetched_utc=fetched,
            )
        )
        seen_titles.add(title)
    unaccounted: list[str] = []
    if requested is not None:
        for want in requested:
            canon = normalized.get(str(want), str(want))
            canon_alt = canon.replace("_", " ")
            if canon not in seen_titles and canon_alt not in seen_titles:
                unaccounted.append(str(want))
    else:
        unaccounted = []
        for page in q.get("pages", []):
            if not page.get("missing") and not (page.get("revisions") or []):
                unaccounted.append(str(page.get("title", "?")))
    return got, gone, unaccounted
