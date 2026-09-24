"""`doctrine.wiki_check` against a real (temp) wiki mirror store, offline.

Each report state has a test, plus: an uncited source is listed and never
called unchanged, a missing or unreadable mirror is `cannot_check`, the check
reads the SERVED revision and not the latest seen (with a mutation proving the
test can fail), and the check never writes.
"""

from __future__ import annotations

import hashlib

import pytest

from doctrine import wiki_check
from doctrine.wiki_check import (
    check_archive,
    check_doctrine,
    cited_page_ids,
    read_archived_revision,
    wiki_flags_for_entry,
)
from wikimirror.store import Chunk, Store, iso
from wikimirror.tests.conftest import T0, WallClock, make_rev


@pytest.fixture
def wall():
    return WallClock()


@pytest.fixture
def store(tmp_path, wall):
    s = Store.open(tmp_path / "mirror.sqlite3", clock=wall)
    s.set_meta("last_full_pull_utc", iso(T0))  # a mirror that was pulled: fresh
    yield s
    s.close()


def baseline(s, rev):
    return s.apply_revision(rev, chunks=[Chunk("Intro", rev.wikitext)], baseline=True, game_version="53.16")


def hold(s, rev):
    return s.apply_revision(rev, chunks=[Chunk("Intro", rev.wikitext)], game_version="53.16")


def entry(revid=100, *, eid="well-rule", status="prior", title="Well", **src):
    source = {"kind": "wiki", "ref": title, "describes": "unknown", "read": "opened", "revid": revid}
    source.update(src)
    return {"id": eid, "scope": "universal", "status": status, "topics": ["water"],
            "sources": [source], "statement": "s"}


def only(report):
    assert len(report["sources"]) == 1
    return report["sources"][0]


# ---- each report state -----------------------------------------------------------


def test_unchanged_when_served_revision_equals_cited(store):
    baseline(store, make_rev(revid=100))
    r = only(check_doctrine([entry(100)], store))
    assert r["state"] == "unchanged" and r["served_revid"] == 100 and r["message"] is None
    rep = check_doctrine([entry(100)], store)
    assert rep["flags_by_entry"] == {} and rep["needing_reread"] == []
    assert rep["mirror"]["available"] is True and rep["summary"]["unchanged"] == 1


def test_changed_when_the_served_revision_is_newer_and_body_was_archived(store, wall):
    baseline(store, make_rev(revid=100, text="old body about lye"))
    hold(store, make_rev(revid=101, text="new body about soap"))
    # 7.3: the refresh job archives a cited page's served body before promoting.
    assert store.archive_served_revision(1) is True
    wall.advance(days=7)
    store.promote_due()
    r = only(check_doctrine([entry(100)], store))
    assert r["state"] == "changed" and r["severity"] == "reread"
    assert r["served_revid"] == 101 and r["cited_revid"] == 100
    assert "changed since revision 100" in r["message"] and "re-read" in r["message"]
    assert r["cited_revision_archived"] is True
    got = read_archived_revision(store, 1, 100)
    assert got["wikitext"] == "old body about lye" and got["intact"] is True
    assert check_archive(store, 1, 100)["archived"] is True


def test_changed_reports_when_the_cited_body_was_not_archived(store, wall):
    baseline(store, make_rev(revid=100, text="old body"))
    hold(store, make_rev(revid=101, text="new body"))
    wall.advance(days=7)
    store.promote_due()  # nobody called archive_served_revision: 7.3 was skipped
    r = only(check_doctrine([entry(100)], store))
    assert r["state"] == "changed" and r["cited_revision_archived"] is False
    assert read_archived_revision(store, 1, 100) is None
    assert check_archive(store, 1, 100) == {"archived": False, "intact": False, "archived_utc": None}


def test_a_tampered_archive_is_not_reported_intact(store, wall):
    baseline(store, make_rev(revid=100, text="old body"))
    hold(store, make_rev(revid=101, text="new body"))
    store.archive_served_revision(1)
    store.conn.execute("UPDATE revision_archive SET wikitext = 'edited' WHERE page_id = 1")
    wall.advance(days=7)
    store.promote_due()
    r = only(check_doctrine([entry(100)], store))
    assert r["cited_revision_archived"] is False


def test_held_newer_when_a_newer_revision_is_held_but_not_served(store):
    baseline(store, make_rev(revid=100, text="old"))
    res = hold(store, make_rev(revid=101, text="new"))
    r = only(check_doctrine([entry(100)], store))
    assert r["state"] == "held_newer" and r["severity"] == "warn"
    assert r["served_revid"] == 100 and r["newer_held_revid"] == 101
    assert r["visible_after"] == res.visible_after and r["held_kinds"] == ["changed"]
    assert "plan a re-read" in r["message"]
    assert r["cited_revision_archived"] is None  # served body is still the cited one


def test_reads_the_served_revision_not_the_latest_seen(store, monkeypatch):
    """The mutation: comparing with the latest seen revision instead of the served
    one turns a not-yet-live edit into a false `changed`. The test above asserts
    `held_newer`; under the mutation the same setup gives `changed`."""
    baseline(store, make_rev(revid=100, text="old"))
    hold(store, make_rev(revid=101, text="new"))
    assert only(check_doctrine([entry(100)], store))["state"] == "held_newer"
    monkeypatch.setattr(wiki_check, "_served_revid", lambda view: view["latest_revid"])
    assert only(check_doctrine([entry(100)], store))["state"] == "changed"  # the wrong answer


def test_moved_when_the_cited_title_now_lives_elsewhere(store, wall):
    baseline(store, make_rev(title="Old name", revid=100))
    store.apply_move(1, "New name", 0)
    wall.advance(days=7)
    store.promote_due()
    r = only(check_doctrine([entry(100, title="Old name")], store))
    assert r["state"] == "moved" and r["moved_to"] == "New name" and r["severity"] == "reread"
    assert "New name" in r["message"]


def test_a_pending_move_is_visible_as_held_pending(store):
    baseline(store, make_rev(title="Old name", revid=100))
    store.apply_move(1, "New name", 0)
    r = only(check_doctrine([entry(100, title="Old name")], store))
    assert r["state"] == "unchanged" and r["held_changes"] == 1 and r["held_kinds"] == ["moved"]


def test_deleted_when_the_page_is_a_tombstone(store, wall):
    baseline(store, make_rev(revid=100, text="going away"))
    store.archive_served_revision(1)
    store.apply_delete(1)
    wall.advance(days=7)
    store.promote_due()
    r = only(check_doctrine([entry(100)], store))
    assert r["state"] == "deleted" and r["severity"] == "reread"
    assert r["cited_revision_archived"] is True


def test_legacy_when_the_cited_namespace_is_not_current(store):
    r = only(check_doctrine([entry(100, page_ns=116, page_title="Well")], store))
    assert r["state"] == "legacy" and r["reason"] == "legacy_namespace" and r["severity"] == "warn"


def test_legacy_when_the_page_row_is_not_current(store):
    baseline(store, make_rev(revid=100))
    store.conn.execute("UPDATE pages SET is_current = 0, game_version = '0.47.05' WHERE page_id = 1")
    r = only(check_doctrine([entry(100)], store))
    assert r["state"] == "legacy" and r["reason"] == "legacy_page"


def test_missing_when_the_page_is_not_in_the_mirror(store):
    baseline(store, make_rev(revid=100))
    r = only(check_doctrine([entry(5, title="No such page")], store))
    assert r["state"] == "missing" and r["reason"] == "page_not_in_mirror"


def test_a_page_seen_only_as_a_held_new_page_is_missing_not_unchanged(store):
    hold(store, make_rev(page_id=9, title="Newcomer", revid=500))
    r = only(check_doctrine([entry(500, title="Newcomer")], store))
    assert r["state"] == "missing"


# ---- cannot_check: never "unchanged" -----------------------------------------------


def test_no_mirror_is_cannot_check_for_every_cited_source():
    rep = check_doctrine([entry(100), entry(7, eid="b", title="Alcohol")], None)
    assert [r["state"] for r in rep["sources"]] == ["cannot_check", "cannot_check"]
    assert rep["mirror"]["available"] is False and rep["summary"]["unchanged"] == 0
    assert rep["sources"][0]["reason"] == "no_mirror_configured"


def test_a_missing_database_file_is_cannot_check(tmp_path):
    rep = check_doctrine([entry(100)], tmp_path / "absent.sqlite3")
    assert only(rep)["state"] == "cannot_check" and rep["mirror"]["available"] is False
    assert "database not found" in rep["mirror"]["reason"]


def test_an_unreadable_database_file_is_cannot_check(tmp_path):
    bad = tmp_path / "garbage.sqlite3"
    bad.write_bytes(b"this is not a sqlite database at all" * 40)
    rep = check_doctrine([entry(100)], bad)
    assert only(rep)["state"] == "cannot_check" and rep["mirror"]["available"] is False
    assert rep["mirror"]["reason"].startswith("mirror_unavailable")


def test_a_reader_that_raises_is_cannot_check_not_a_crash(store):
    class Broken:
        namespaces = {}

        def staleness(self):
            return {"status": "fresh", "age_hours": 1.0, "reasons": []}

        def get_page(self, *a, **k):
            raise RuntimeError("database is locked")

    r = only(check_doctrine([entry(100)], Broken()))
    assert r["state"] == "cannot_check" and "database is locked" in r["reason"]


def test_a_reader_whose_freshness_is_unreadable_is_cannot_check():
    class NoFresh:
        namespaces = {}

        def staleness(self):
            raise RuntimeError("boom")

        def get_page(self, *a, **k):
            raise AssertionError("must not be consulted")

    rep = check_doctrine([entry(100)], NoFresh())
    assert only(rep)["state"] == "cannot_check" and rep["mirror"]["available"] is False


def test_a_never_pulled_mirror_does_not_say_unchanged(tmp_path, wall):
    s = Store.open(tmp_path / "empty.sqlite3", clock=wall)  # no last_full_pull_utc
    baseline(s, make_rev(revid=100))
    r = only(check_doctrine([entry(100)], s))
    assert r["state"] == "cannot_check" and r["reason"] == "mirror_very_stale"
    s.close()


def test_a_very_stale_mirror_does_not_vouch_for_unchanged_but_still_reports_changes(store, wall):
    baseline(store, make_rev(revid=100, text="a"))
    baseline_two = make_rev(page_id=2, title="Still", revid=200, text="b")
    baseline(store, baseline_two)
    hold(store, make_rev(revid=101, text="a2"))
    wall.advance(days=8)  # past the hold and past very_stale
    store.promote_due()
    rep = check_doctrine([entry(100), entry(200, eid="still", title="Still")], store)
    by = {r["entry_id"]: r for r in rep["sources"]}
    assert by["well-rule"]["state"] == "changed"  # a positive finding survives
    assert by["still"]["state"] == "cannot_check" and by["still"]["reason"] == "mirror_very_stale"
    assert rep["mirror"]["freshness"]["status"] == "very_stale"


def test_a_cited_revision_the_mirror_has_not_served_yet_is_cannot_check(store):
    baseline(store, make_rev(revid=100))
    r = only(check_doctrine([entry(150)], store))
    assert r["state"] == "cannot_check" and r["reason"] == "cited_revision_not_yet_served"


# ---- uncited, and doctrine's other shapes ------------------------------------------------


def test_an_entry_with_no_revid_is_listed_as_uncited_never_unchanged(store):
    baseline(store, make_rev(revid=100))
    old = {"id": "old", "scope": "universal", "status": "prior", "topics": ["water"], "statement": "s",
           "sources": [{"kind": "wiki", "ref": "Well", "describes": "unknown", "read": "unrecorded"}]}
    rep = check_doctrine([old, entry(100)], store)
    assert rep["uncited"] == [{"entry_id": "old", "source_index": 0, "ref": "Well", "read": "unrecorded"}]
    assert [r["entry_id"] for r in rep["sources"]] == ["well-rule"]
    assert rep["summary"]["unchanged"] == 1 and "old" not in rep["flags_by_entry"]


def test_non_wiki_and_malformed_entries_are_ignored(store):
    rep = check_doctrine(
        [{"id": "u", "sources": [{"kind": "user", "ref": "own play"}]}, "junk", None, {"id": "n"}], store
    )
    assert rep["sources"] == [] and rep["uncited"] == []


def test_page_title_and_page_ns_override_the_ref(store):
    baseline(store, make_rev(title="Well", revid=100))
    e = entry(100, title="Well (see also)", page_title="Well", page_ns=0)
    assert only(check_doctrine([e], store))["state"] == "unchanged"


# ---- the flag structure S7 consumes ---------------------------------------------------------


def test_flags_by_entry_and_wiki_flags_for_entry(store, wall):
    baseline(store, make_rev(revid=100, text="old"))
    hold(store, make_rev(revid=101, text="new"))
    wall.advance(days=7)
    store.promote_due()
    e = entry(100)
    rep = check_doctrine([e], store)
    (flag,) = rep["flags_by_entry"]["well-rule"]
    assert set(flag) == set(wiki_check._FLAG_KEYS)
    assert flag["state"] == "changed" and flag["cited_revid"] == 100 and flag["served_revid"] == 101
    assert rep["needing_reread"] == ["well-rule"]
    assert wiki_flags_for_entry(e, store) == [flag]
    assert wiki_flags_for_entry(entry(101), store) == []


def test_verified_entries_get_a_lower_severity(store, wall):
    baseline(store, make_rev(revid=100, text="old"))
    hold(store, make_rev(revid=101, text="new"))
    wall.advance(days=7)
    store.promote_due()
    rep = check_doctrine([entry(100, status="verified")], store)
    assert only(rep)["severity"] == "note" and rep["needing_reread"] == []


def test_cited_page_ids(store):
    baseline(store, make_rev(revid=100))
    ids = cited_page_ids([entry(100), entry(5, eid="x", title="Nope")], store)
    assert ids == {1}


# ---- read-only ---------------------------------------------------------------------------------


def test_the_check_by_path_is_read_only_and_leaves_the_file_unchanged(tmp_path, wall):
    path = tmp_path / "m.sqlite3"
    s = Store.open(path, clock=wall)
    s.set_meta("last_full_pull_utc", iso(T0))
    baseline(s, make_rev(revid=100))
    hold(s, make_rev(revid=101, text="held"))
    s.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    rep = check_doctrine([entry(100)], path)
    assert only(rep)["state"] == "held_newer"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_the_report_is_json_serialisable(store):
    import json

    baseline(store, make_rev(revid=100))
    json.dumps(check_doctrine([entry(100)], store))


def test_cli_exit_codes(tmp_path, wall, capsys):
    path = tmp_path / "m.sqlite3"
    s = Store.open(path, clock=wall)
    s.set_meta("last_full_pull_utc", iso(T0))
    baseline(s, make_rev(revid=100))
    s.close()
    doc = tmp_path / "d.yaml"
    import yaml

    doc.write_text(yaml.safe_dump([entry(100)]), encoding="utf-8")
    assert wiki_check.main(["--db", str(path), "--doctrine", str(doc)]) == 0
    assert wiki_check.main(["--db", str(tmp_path / "gone.sqlite3"), "--doctrine", str(doc)]) == 1
    assert "UNAVAILABLE" in capsys.readouterr().out
