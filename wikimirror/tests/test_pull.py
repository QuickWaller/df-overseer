"""The full pull and its CLI, end to end over a small fake wiki (no network)."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from wikimirror import pull as pullmod
from wikimirror.__main__ import main
from wikimirror.api import NetworkError, TransportResponse, WikiClient
from wikimirror.pull import (
    ContactRequired, PullError, StagedExists, adapt_chunks, database_status, full_pull, plan_pull,
    report_path_for, staged_path_for,
)
from wikimirror.store import PromoteError, Store
from wikimirror.text import extract_page

ENV = {"DFWIKI_UA_CONTACT": "https://example.invalid/contact"}
FIXTURES = Path(__file__).parent / "fixtures" / "wikitext"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def filler(n: int) -> str:
    return f"Dwarves drink water and haul stone in workshop number {n}.\n\n== Notes ==\nThe stone is grey."


class FakeWiki:
    """Answers the allow-listed queries the pull makes, from a dict of pages."""

    def __init__(self):
        self.pages: dict[str, dict] = {}
        self.redirects: dict[str, str] = {}
        self.version = "53.16"
        self.next_id = 100
        self.calls: list[dict] = []
        self.fail_after: int | None = None  # raise after this many fetch requests
        self.fetches = 0
        self.vanish: set[str] = set()  # enumerated but missing at fetch time
        self.bump_on_fetch: dict[str, int] = {}

    def add(self, title, text, ns=0):
        self.next_id += 1
        self.pages[title] = {"pageid": self.next_id, "ns": ns, "title": title, "revid": 1000 + self.next_id, "text": text}

    def __call__(self, url, headers, timeout):
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        self.calls.append(q)
        if q.get("generator") == "allpages":
            ns = int(q["gapnamespace"])
            rows = [
                {"pageid": p["pageid"], "ns": p["ns"], "title": p["title"], "lastrevid": p["revid"],
                 "length": len(p["text"]), "touched": "2026-09-01T00:00:00Z"}
                for p in self.pages.values() if p["ns"] == ns
            ]
            return self._ok({"query": {"pages": rows}})
        if q.get("list") == "allpages":
            rows = [{"pageid": 9000 + i, "ns": 0, "title": t} for i, t in enumerate(sorted(self.redirects))]
            return self._ok({"query": {"allpages": rows}})
        if q.get("list") == "allredirects":
            rows = [{"fromid": 9000 + i, "ns": 0, "title": self.redirects[t]} for i, t in enumerate(sorted(self.redirects))]
            return self._ok({"query": {"allredirects": rows}})
        if "titles" in q:
            titles = q["titles"].split("|")
            if titles == ["Template:Current/version"]:
                return self._ok({"query": {"pages": [{
                    "pageid": 5, "ns": 10, "title": "Template:Current/version", "length": 30,
                    "revisions": [{"revid": 5, "parentid": 4, "timestamp": "2026-09-01T00:00:00Z", "comment": "",
                                   "slots": {"main": {"content": f"{self.version}<noinclude>docs</noinclude>"}}}]}]}})
            self.fetches += 1
            if self.fail_after is not None and self.fetches > self.fail_after:
                raise NetworkError("injected outage")
            out = []
            for t in reversed(titles):  # response order differs from request order
                if t in self.vanish or t not in self.pages:
                    out.append({"ns": 0, "title": t, "missing": True})
                    continue
                p = self.pages[t]
                revid = p["revid"] + self.bump_on_fetch.get(t, 0)
                out.append({"pageid": p["pageid"], "ns": p["ns"], "title": t, "length": len(p["text"]),
                            "revisions": [{"revid": revid, "parentid": revid - 1,
                                           "timestamp": "2026-09-02T00:00:00Z", "comment": "edit",
                                           "slots": {"main": {"content": p["text"]}}}]})
            return self._ok({"query": {"pages": out}})
        raise AssertionError(f"unexpected query {q}")

    @staticmethod
    def _ok(payload):
        return TransportResponse(200, {}, json.dumps(payload).encode("utf-8"))


@pytest.fixture
def wiki():
    w = FakeWiki()
    w.add("Well", fixture("well.wikitext"))
    w.add("Mason", fixture("mason.wikitext"))
    w.add("Ghost", fixture("ghost.wikitext"))
    w.add("Dwarf", fixture("dwarf.wikitext"))
    w.add("Aquifer", fixture("aquifer.wikitext"))
    w.add("Hostile", fixture("hostile.wikitext"))
    w.add("Widget", "{{Zorblax|a=1|b=2}} {{Zorblax|a=3}} {{Frobnicate|x=y}}\n\nA dwarf drinks water near stone.")
    w.add("Colon: Title", "A page in the main namespace whose title has a colon. Water and stone.")
    w.add("Wall", "== Lost ==\n{{#invoke:Foo|bar}}\n\n== Kept ==\nStone walls hold water back from dwarves.")
    w.add("Gone soon", "This one is deleted between enumeration and fetch. Dwarf water stone.")
    w.add("Water buffalo/raw", fixture("water_buffalo_raw.wikitext"))
    w.add("Stone", filler(1))
    w.vanish.add("Gone soon")
    w.redirects = {"Fountain": "Well", "Ghosts": "Ghost", "Nowhere": "Missing target"}
    return w


@pytest.fixture
def client_for(clock):
    def make(wiki, **kw):
        kw.setdefault("env", ENV)
        return WikiClient(transport=wiki, sleep=clock.sleep, monotonic=clock.monotonic,
                          now_iso=lambda: "2026-09-24T12:00:00Z", **kw)
    return make


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---- the happy path -------------------------------------------------------------


def test_end_to_end_pull_makes_a_visible_baseline(tmp_path, wiki, client_for):
    out = tmp_path / "df-wiki.sqlite3"
    res = full_pull(client_for(wiki), out, env=ENV)
    assert out.exists() and not staged_path_for(out).exists()
    assert res.game_version == "53.16"
    assert res.enumerated == 12 and res.stored == 11 and res.missing == ["Gone soon"]

    with Store.open_readonly(out) as s:
        well = s.get_page("Well")
        assert well["state"] == "live" and well["game_version"] == "53.16" and well["is_current"]
        assert well["held_changes"] == 0  # the baseline is visible now, nothing is held
        chunks = s.get_chunks(well["page_id"])
        paths = [c["heading_path"] for c in chunks]
        assert "Introduction" in paths and "Building a well > Placement" in paths
        assert s.get_page("Gone soon") is None
        # a redirect resolves through the redirects table
        assert s.get_page("Fountain")["title"] == "Well"
        # a colon title in ns 0 stays a current main page
        assert s.get_page("Colon: Title")["is_current"]
        # kind is set from the title; raw pages are stored but not searchable by default
        assert s.get_page("Water buffalo/raw")["kind"] == "raw"
        assert all(h["title"] != "Water buffalo/raw" for h in s.search("water"))
        assert s.get_meta("baseline_utc") and s.get_meta("game_version") == "53.16"
        assert s.get_meta("last_refresh_ok_utc") is None  # a pull is not a refresh
        assert s.staleness()["status"] == "fresh"
        assert s.staleness()["reasons"] == []
    manifest = json.loads(Path(str(out) + ".manifest.json").read_text())
    assert manifest["page_count"] == 11


def test_hostile_page_is_stored_as_data_and_flagged(tmp_path, wiki, client_for):
    out = tmp_path / "w.sqlite3"
    full_pull(client_for(wiki), out, env=ENV)
    with Store.open_readonly(out) as s:
        page = s.get_page("Hostile")
        assert page is not None
        text = " ".join(c["text"] for c in s.get_chunks(page["page_id"]))
        assert "<system>" in text or "system" in text  # kept as literal text, never interpreted


def test_report_lists_degraded_and_unlisted_counts(tmp_path, wiki, client_for):
    out = tmp_path / "w.sqlite3"
    res = full_pull(client_for(wiki), out, env=ENV)
    rep = json.loads(report_path_for(out).read_text())
    assert rep == json.loads(json.dumps(res.report))
    ts = rep["text_stage"]
    tops = {t["template"]: t["count"] for t in ts["unlisted_templates_top"]}
    assert tops.get("zorblax") == 2 and tops.get("frobnicate") == 1
    assert ts["unlisted_templates_distinct"] >= 2
    assert ts["degraded_chunks"] >= 1 and ts["degraded_pages"] >= 1
    assert any("invoke" in r for r in ts["degraded_reasons_pages"])
    assert "Wall" in ts["section_text_lost_pages"] or ts["degraded_reasons_chunks"]
    assert rep["missing_titles"] == ["Gone soon"]
    assert rep["redirects"]["total"] == 3
    assert rep["redirects"]["target_not_in_mirror_count"] == 1  # Nowhere -> Missing target
    assert ts["text_stage_failures"] == []
    # the summary is human readable and names the loss
    assert "unlisted templates" in pullmod.format_summary(rep)


def test_report_counts_match_a_direct_text_stage_run(tmp_path, wiki, client_for):
    out = tmp_path / "w.sqlite3"
    res = full_pull(client_for(wiki), out, env=ENV)
    expected = 0
    for title, p in wiki.pages.items():
        if title == "Gone soon":
            continue
        expected += len(extract_page(p["text"]).chunks)
    assert res.report["text_stage"]["chunks"] == expected
    with Store.open_readonly(out) as s:
        assert s.counts()["chunks"] == expected


def test_adapter_joins_section_path_and_defaults_the_lead():
    page = extract_page("Lead words.\n\n== A ==\n=== B ===\nDeep text here.")
    got = adapt_chunks(page)
    assert [c.heading_path for c in got] == ["Introduction", "A > B"]


def test_request_count_is_batched_and_polite(tmp_path, wiki, client_for):
    for i in range(120):
        wiki.add(f"Filler {i}", filler(i))
    out = tmp_path / "w.sqlite3"
    client = client_for(wiki)
    res = full_pull(client, out, env=ENV)
    # 1 version + 1 enumeration + ceil(132/50)=3 fetch batches + 2 per namespace redirect join
    assert res.requests == 1 + 1 + 3 + 2
    assert all(len(c.get("titles", "").split("|")) <= 50 for c in wiki.calls)


def test_dry_run_uses_only_enumeration_and_writes_nothing(tmp_path, wiki, client_for):
    client = client_for(wiki)
    plan = plan_pull(client)
    assert plan["pages"] == 12 and plan["fetch_batches"] == 1
    assert client.requests_made == 1
    assert list(tmp_path.iterdir()) == []


# ---- failure leaves the live file untouched; resume and discard -----------------


def _seed_live(tmp_path, wiki, client_for):
    out = tmp_path / "live.sqlite3"
    full_pull(client_for(wiki), out, env=ENV)
    return out, sha(out), Path(str(out) + ".manifest.json").read_bytes()


def test_failure_mid_pull_leaves_live_file_untouched(tmp_path, wiki, client_for):
    for i in range(120):
        wiki.add(f"Filler {i}", filler(i))
    out, before, manifest = _seed_live(tmp_path, wiki, client_for)
    wiki.fail_after = 2  # the third batch dies
    wiki.fetches = 0
    wiki.add("Extra", filler(999))
    with pytest.raises(NetworkError):
        full_pull(client_for(wiki), out, env=ENV)
    assert sha(out) == before
    assert Path(str(out) + ".manifest.json").read_bytes() == manifest
    assert not Path(str(out) + ".prev").exists()
    assert staged_path_for(out).exists()
    with Store.open_readonly(out) as s:
        assert s.get_page("Extra") is None


def test_second_pull_refuses_while_a_staged_file_exists(tmp_path, wiki, client_for):
    for i in range(120):
        wiki.add(f"Filler {i}", filler(i))
    out = tmp_path / "w.sqlite3"
    wiki.fail_after = 1
    with pytest.raises(NetworkError):
        full_pull(client_for(wiki), out, env=ENV)
    wiki.fail_after = None
    with pytest.raises(StagedExists):
        full_pull(client_for(wiki), out, env=ENV)
    assert not out.exists()


def test_interrupted_pull_can_be_resumed_without_refetching(tmp_path, wiki, client_for):
    for i in range(120):
        wiki.add(f"Filler {i}", filler(i))
    out = tmp_path / "w.sqlite3"
    wiki.fail_after = 2
    with pytest.raises(NetworkError):
        full_pull(client_for(wiki), out, env=ENV)
    assert not out.exists()
    wiki.fail_after = None
    wiki.fetches = 0
    wiki.calls.clear()
    res = full_pull(client_for(wiki), out, env=ENV, resume=True)
    assert res.resumed == 99  # two batches of 50 staged, minus the one vanished title
    fetched_titles = [t for c in wiki.calls if "titles" in c and c["titles"] != "Template:Current/version"
                      for t in c["titles"].split("|")]
    assert len(fetched_titles) == 33  # only the rest (and the vanished title again)
    assert not staged_path_for(out).exists()
    # the resumed report equals an uninterrupted pull's report on the text stage
    out2 = tmp_path / "clean.sqlite3"
    clean = full_pull(client_for(wiki), out2, env=ENV)
    assert res.report["text_stage"] == clean.report["text_stage"]
    with Store.open_readonly(out) as s:
        assert s.counts()["pages_live"] == 131


def test_interrupted_pull_can_be_discarded(tmp_path, wiki, client_for):
    out = tmp_path / "w.sqlite3"
    wiki.fail_after = 0
    with pytest.raises(NetworkError):
        full_pull(client_for(wiki), out, env=ENV)
    wiki.fail_after = None
    assert staged_path_for(out).exists()
    res = full_pull(client_for(wiki), out, env=ENV, discard_staged=True)
    assert res.resumed == 0 and out.exists() and not staged_path_for(out).exists()


def test_resume_with_a_changed_game_version_is_refused(tmp_path, wiki, client_for):
    out = tmp_path / "w.sqlite3"
    wiki.fail_after = 0
    with pytest.raises(NetworkError):
        full_pull(client_for(wiki), out, env=ENV)
    wiki.fail_after = None
    wiki.version = "53.17"
    with pytest.raises(PullError, match="game version"):
        full_pull(client_for(wiki), out, env=ENV, resume=True)


def test_resume_with_no_staged_file_is_refused(tmp_path, wiki, client_for):
    with pytest.raises(StagedExists):
        full_pull(client_for(wiki), tmp_path / "w.sqlite3", env=ENV, resume=True)


def test_too_many_missing_pages_fail_before_promote(tmp_path, wiki, client_for):
    wiki.vanish |= {"Well", "Mason", "Ghost"}
    out = tmp_path / "w.sqlite3"
    with pytest.raises(PullError, match="missing"):
        full_pull(client_for(wiki), out, env=ENV)
    assert not out.exists()


def test_failed_verification_does_not_promote(tmp_path, wiki, client_for):
    out, before, _ = _seed_live(tmp_path, wiki, client_for)
    wiki.add("Extra", filler(7))
    with pytest.raises(PromoteError) as ei:
        full_pull(client_for(wiki), out, env=ENV, probe_words=("dwarf", "zzzznotaword", "water"))
    assert any("zzzznotaword" in r for r in ei.value.reasons)
    assert sha(out) == before


def test_a_real_repull_keeps_the_previous_file(tmp_path, wiki, client_for):
    out, before, _ = _seed_live(tmp_path, wiki, client_for)
    wiki.version = "53.17"
    wiki.add("Extra", filler(7))
    full_pull(client_for(wiki), out, env=ENV)
    assert sha(Path(str(out) + ".prev")) == before
    with Store.open_readonly(out) as s:
        assert s.get_meta("game_version") == "53.17"
        assert s.get_page("Extra") is not None


def test_revid_moving_during_the_pull_is_reported(tmp_path, wiki, client_for):
    wiki.bump_on_fetch["Well"] = 5
    res = full_pull(client_for(wiki), tmp_path / "w.sqlite3", env=ENV)
    assert [m["title"] for m in res.report["revid_moved_during_pull"]] == ["Well"]


def test_text_stage_exception_is_reported_not_swallowed(tmp_path, wiki, client_for, monkeypatch):
    real = pullmod.textstage.extract_page

    def flaky(wikitext, *a, **k):
        if "Zorblax" in wikitext:
            raise RuntimeError("boom")
        return real(wikitext, *a, **k)

    monkeypatch.setattr(pullmod.textstage, "extract_page", flaky)
    res = full_pull(client_for(wiki), tmp_path / "w.sqlite3", env=ENV)
    fails = res.report["text_stage"]["text_stage_failures"]
    assert [f["title"] for f in fails] == ["Widget"]
    with Store.open_readonly(res.out) as s:
        page = s.get_page("Widget")
        assert "extraction failed" in s.get_chunks(page["page_id"])[0]["text"]


# ---- the UA contact refusal ------------------------------------------------------


def test_real_pull_refuses_without_contact(tmp_path, wiki, client_for):
    out = tmp_path / "w.sqlite3"
    with pytest.raises(ContactRequired):
        full_pull(client_for(wiki, env={}), out, env={})
    assert wiki.calls == []  # not one request went out
    assert not out.exists() and not staged_path_for(out).exists()
    with pytest.raises(ContactRequired):
        full_pull(client_for(wiki, env={}), out, env={"DFWIKI_UA_CONTACT": "   "})


# ---- the CLI --------------------------------------------------------------------


def run_cli(argv, wiki, env, clock):
    out, err = io.StringIO(), io.StringIO()

    def factory(**kw):
        return WikiClient(transport=wiki, sleep=clock.sleep, monotonic=clock.monotonic,
                          now_iso=lambda: "2026-09-24T12:00:00Z", **kw)

    code = main(argv, env=env, client_factory=factory, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_cli_pull_refuses_without_contact(tmp_path, wiki, clock):
    code, out, err = run_cli(["pull", "--out", str(tmp_path / "d.sqlite3")], wiki, {}, clock)
    assert code == 2 and "DFWIKI_UA_CONTACT" in err
    assert wiki.calls == []


def test_cli_dry_run_needs_no_contact_and_writes_nothing(tmp_path, wiki, clock):
    code, out, err = run_cli(["pull", "--dry-run", "--out", str(tmp_path / "d.sqlite3")], wiki, {}, clock)
    assert code == 0
    plan = json.loads(out)
    assert plan["dry_run"] is True and plan["pages"] == 12
    assert len(wiki.calls) == 1
    assert list(tmp_path.iterdir()) == []


def test_cli_pull_then_status(tmp_path, wiki, clock):
    db = str(tmp_path / "d.sqlite3")
    code, out, err = run_cli(["pull", "--out", db], wiki, ENV, clock)
    assert code == 0, err
    assert "promoted to" in out
    code, out, err = run_cli(["status", "--db", db], wiki, ENV, clock)
    assert code == 0
    info = json.loads(out)
    assert info["game_version"] == "53.16" and info["pages"] == 11
    assert info["held_changes"] == 0 and info["staleness"] == "fresh" and info["baseline_utc"]
    assert info["last_refresh_ok_utc"] is None


def test_cli_status_fails_on_missing_and_unreadable_and_unpulled(tmp_path, wiki, clock):
    code, out, err = run_cli(["status", "--db", str(tmp_path / "nope.sqlite3")], wiki, ENV, clock)
    assert code == 1 and out == ""
    junk = tmp_path / "junk.sqlite3"
    junk.write_bytes(b"this is not a database" * 100)
    code, out, err = run_cli(["status", "--db", str(junk)], wiki, ENV, clock)
    assert code == 1 and out == ""
    empty = tmp_path / "empty.sqlite3"
    Store.open(empty).close()
    code, out, err = run_cli(["status", "--db", str(empty)], wiki, ENV, clock)
    assert code == 1 and "no baseline" in err and out == ""


def test_cli_staged_exists_is_refused_then_discarded(tmp_path, wiki, clock):
    db = str(tmp_path / "d.sqlite3")
    wiki.fail_after = 0
    code, out, err = run_cli(["pull", "--out", db], wiki, ENV, clock)
    assert code == 1 and "live database untouched" in err
    wiki.fail_after = None
    code, out, err = run_cli(["pull", "--out", db], wiki, ENV, clock)
    assert code == 2 and "--resume" in err
    code, out, err = run_cli(["pull", "--out", db, "--discard-staged"], wiki, ENV, clock)
    assert code == 0, err


def test_cli_needs_an_output_path(wiki, clock):
    code, out, err = run_cli(["pull"], wiki, ENV, clock)
    assert code == 2 and "DFWIKI_DB" in err
    code, out, err = run_cli(["status"], wiki, ENV, clock)
    assert code == 2


def test_cli_budget_exhaustion_is_a_named_failure(tmp_path, wiki, clock):
    db = str(tmp_path / "d.sqlite3")
    code, out, err = run_cli(["pull", "--out", db, "--budget", "2"], wiki, ENV, clock)
    assert code == 1 and "BudgetExceeded" in err
    assert not Path(db).exists()
