"""Tests for scripts/build_wiki_snapshot.py, the offline builder of the
snapshot `dfmcp.knowledge_tools.knowledge.wiki_lookup` reads.

No real network call happens anywhere in this file (`build_snapshot`'s own
`fetch` parameter is the seam, matching `tests/test_provision_vm_capture.py`'s
convention of testing scripts/*.py's pure functions directly). This stream
was explicitly told not to download the whole wiki
(`handoffs/2026-09-22-loop-consultant-retrieval.md`); these tests instead
prove the builder's own logic -- section splitting, markup stripping, the
version-namespace heuristic, and the end-to-end JSON shape
`dfmcp.knowledge_tools` expects -- against small, hand-written wikitext
fixtures.
"""

import json
import os
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import build_wiki_snapshot as bws  # noqa: E402


_WELL_WIKITEXT = """A '''well''' lets dwarves drink from an underground water source.

== Requirements ==
A well needs [[Blocks|blocks]], a bucket, a chain, and a mechanism.
It must be built on a tile directly above revealed water.

== Construction ==
Build the well from the {{template|arg}} Furniture menu.
See also [[Water]] for water mechanics.

== See also ==
* [[Cistern]]
* [[Water source]]
"""

_STUB_WIKITEXT = "Just one short paragraph, no headers at all."


def _fake_fetch(pages):
    def fetch(title, api_url):
        if title not in pages:
            raise bws.SnapshotBuildError(f"{title!r}: not found (fixture)")
        return pages[title]
    return fetch


_FIXED_NOW = lambda: datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)  # noqa: E731


# --------------------------------------------------------------------------
# split_sections
# --------------------------------------------------------------------------


def test_split_sections_splits_on_headers_of_any_depth():
    sections = bws.split_sections(_WELL_WIKITEXT)
    headings = [s["heading"] for s in sections]
    assert headings == ["Introduction", "Requirements", "Construction", "See also"]


def test_split_sections_strips_wikilinks_to_display_text():
    sections = bws.split_sections(_WELL_WIKITEXT)
    requirements = next(s for s in sections if s["heading"] == "Requirements")
    assert "blocks" in requirements["text"]
    assert "[[" not in requirements["text"]
    assert "]]" not in requirements["text"]


def test_split_sections_drops_templates():
    sections = bws.split_sections(_WELL_WIKITEXT)
    construction = next(s for s in sections if s["heading"] == "Construction")
    assert "{{" not in construction["text"]
    assert "template" not in construction["text"]


def test_split_sections_with_no_headers_is_one_introduction_section():
    sections = bws.split_sections(_STUB_WIKITEXT)
    assert len(sections) == 1
    assert sections[0]["heading"] == "Introduction"
    assert "short paragraph" in sections[0]["text"]


def test_split_sections_caps_section_length():
    long_body = "== Big ==\n" + ("x" * 10000)
    sections = bws.split_sections(long_body)
    big = next(s for s in sections if s["heading"] == "Big")
    assert len(big["text"]) == bws._MAX_SECTION_CHARS


def test_split_sections_empty_wikitext_yields_no_sections():
    assert bws.split_sections("") == []
    assert bws.split_sections("   \n\n  ") == []


# --------------------------------------------------------------------------
# version_namespace_of
# --------------------------------------------------------------------------


def test_version_namespace_of_plain_title_is_current():
    assert bws.version_namespace_of("Well") == "current"


def test_version_namespace_of_prefixed_title_is_the_prefix():
    assert bws.version_namespace_of("DF2014:Well") == "DF2014"


def test_version_namespace_of_multiple_colons_uses_first_segment():
    assert bws.version_namespace_of("DF2014:Well:Sub") == "DF2014"


# --------------------------------------------------------------------------
# page_url
# --------------------------------------------------------------------------


def test_page_url_replaces_spaces_and_quotes():
    url = bws.page_url("Plump helmet")
    assert url == "https://dwarffortresswiki.org/index.php/Plump_helmet"


# --------------------------------------------------------------------------
# build_snapshot: end-to-end shape, no network
# --------------------------------------------------------------------------


def test_build_snapshot_shape_matches_what_knowledge_tools_expects():
    fetch = _fake_fetch({"Well": _WELL_WIKITEXT, "DF2014:Well": _STUB_WIKITEXT})
    snapshot = bws.build_snapshot(["Well", "DF2014:Well"], fetch=fetch, now=_FIXED_NOW)

    assert snapshot["source_api"] == bws.DEFAULT_API_URL
    assert snapshot["generated_utc"] == "2026-09-22T12:00:00+00:00"
    assert set(snapshot["pages"]) == {"Well", "DF2014:Well"}

    well = snapshot["pages"]["Well"]
    assert well["version_namespace"] == "current"
    assert well["url"] == "https://dwarffortresswiki.org/index.php/Well"
    assert well["fetched_utc"] == "2026-09-22T12:00:00+00:00"
    assert len(well["sections"]) == 4

    old_well = snapshot["pages"]["DF2014:Well"]
    assert old_well["version_namespace"] == "DF2014"


def test_build_snapshot_raises_naming_the_failed_title():
    fetch = _fake_fetch({"Well": _WELL_WIKITEXT})
    try:
        bws.build_snapshot(["Well", "Nonexistent Page"], fetch=fetch, now=_FIXED_NOW)
        assert False, "expected SnapshotBuildError"
    except bws.SnapshotBuildError as exc:
        assert "Nonexistent Page" in str(exc)


def test_build_snapshot_output_is_json_serialisable_and_round_trips(tmp_path):
    fetch = _fake_fetch({"Well": _WELL_WIKITEXT})
    snapshot = bws.build_snapshot(["Well"], fetch=fetch, now=_FIXED_NOW)
    out = tmp_path / "snap.json"
    out.write_text(json.dumps(snapshot), encoding="utf-8")
    reloaded = json.loads(out.read_text(encoding="utf-8"))
    assert reloaded == snapshot


# --------------------------------------------------------------------------
# CLI, exercised with a fake fetch injected at the build_snapshot layer
# (main() itself always uses real_fetch_wikitext, so this test monkeypatches
# the module-level name real_fetch_wikitext rather than calling main() with
# a live network dependency)
# --------------------------------------------------------------------------


def test_main_writes_a_snapshot_file(tmp_path, monkeypatch):
    monkeypatch.setattr(bws, "real_fetch_wikitext", lambda title, api_url: _WELL_WIKITEXT)
    out_path = tmp_path / "out" / "snap.json"
    rc = bws.main(["Well", "--out", str(out_path)])
    assert rc == 0
    assert out_path.is_file()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert "Well" in data["pages"]


def test_main_returns_nonzero_and_writes_nothing_on_a_failed_fetch(tmp_path, monkeypatch, capsys):
    def boom(title, api_url):
        raise bws.SnapshotBuildError(f"{title!r}: simulated failure")
    monkeypatch.setattr(bws, "real_fetch_wikitext", boom)
    out_path = tmp_path / "snap.json"
    rc = bws.main(["Well", "--out", str(out_path)])
    assert rc == 1
    assert not out_path.exists()
    captured = capsys.readouterr()
    assert "simulated failure" in captured.err
