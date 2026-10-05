"""The pause alert and "waiting on a human" on the site's live strip
(handoffs/2026-10-05-safe-to-resume.md): the publisher side (`dfqueue/live.py`
`build_pause`, `read_conductor_dir`, `build_live`) and the strip's rendering
through node on the real `web/stream/app.js` (the node half skips without node)."""
import json
from datetime import datetime, timezone

import pytest

from dfqueue import live
from dfqueue.tests.test_site_js_threads import _run

T0 = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc).timestamp()


def _iso(offset):
    return datetime.fromtimestamp(T0 + offset, timezone.utc).isoformat()


def _conductor(block, *, updated=-5):
    return {"running": None, "last_runs": {}, "pause": {"block": block, "updated_at": _iso(updated)}}


ALERT = {"still_paused": True, "waiting_on_human": False,
         "alert": {"reason": "the Overseer gave no verdict on an unexplained pause; staying paused", "since": T0 - 300}}
WAIT = {"still_paused": True, "waiting_on_human": True, "alert": None}


def test_an_alert_reaches_the_live_block_with_reason_and_since():
    out = live.build_live([], T0, public=True, conductor=_conductor(ALERT))
    assert out["pause"]["waiting_on_human"] is False
    assert out["pause"]["alert"] == {"reason": ALERT["alert"]["reason"], "since": _iso(-300)[:19] + "+00:00"}


def test_waiting_on_a_human_reaches_the_live_block_and_a_running_fort_carries_nothing():
    out = live.build_live([], T0, public=True, conductor=_conductor(WAIT))
    assert out["pause"] == {"alert": None, "waiting_on_human": True}
    resumed = {**ALERT, "still_paused": False}
    assert "pause" not in live.build_live([], T0, public=True, conductor=_conductor(resumed))
    quiet = {"still_paused": True, "waiting_on_human": False, "alert": None}
    assert "pause" not in live.build_live([], T0, public=True, conductor=_conductor(quiet))


def test_a_stale_status_file_never_leaves_an_alert_up():
    stale = _conductor(ALERT, updated=-(live.PAUSE_BLOCK_MAX_AGE_S + 5))
    assert "pause" not in live.build_live([], T0, public=True, conductor=stale)
    assert "pause" not in live.build_live([], T0, public=True, conductor={"running": None, "last_runs": {}})


def test_the_public_reason_goes_through_the_feed_safety_net():
    bad = {**ALERT, "alert": {"reason": "see http://10.0.0.5/secret for why", "since": T0}}
    pub = live.build_live([], T0, public=True, conductor=_conductor(bad))
    assert pub["pause"]["alert"]["reason"] == live.PAUSE_REASON_GENERIC
    assert "10.0.0.5" not in json.dumps(pub)
    long = {**ALERT, "alert": {"reason": "word " * 100, "since": T0}}
    out = live.build_live([], T0, public=True, conductor=_conductor(long))
    assert len(out["pause"]["alert"]["reason"]) <= live.PAUSE_REASON_MAX


def test_read_conductor_dir_carries_the_pause_block(tmp_path):
    (tmp_path / "status.json").write_text(json.dumps({
        "state": "running", "updated_at": _iso(0), "pause_watch": ALERT}), encoding="utf-8")
    got = live.read_conductor_dir(tmp_path)
    assert got["pause"]["block"]["alert"]["reason"].startswith("the Overseer gave no verdict")
    assert live.build_live([], T0 + 1, public=True, conductor=got)["pause"]["alert"]


def test_pause_does_not_make_the_hash_volatile_and_changes_it_when_it_changes():
    a = live.build_live([], T0, public=True, conductor=_conductor(ALERT))
    b = live.build_live([], T0 + 30, public=True, conductor=_conductor(ALERT, updated=-5))
    assert live.live_hash_payload(a) == live.live_hash_payload(b)
    c = live.build_live([], T0, public=True, conductor=_conductor(WAIT))
    assert live.live_hash_payload(a) != live.live_hash_payload(c)


# ---- the strip, on the real app.js ---------------------------------------------

STRIP = r"""
  const strip = new Node("div"); strip.hidden = true;
  const page = Object.create(StreamPage.prototype);
  page.liveStripEl = strip; page.mode = "public"; page.statusFetchedAt = Date.now();
  page.status = { live: DATA };
  page._renderLiveStrip();
  const seen = []; const walk = (n) => { if (n.className) seen.push(n.className); if (n.textContent) seen.push(n.textContent); n.children.forEach(walk); }; walk(strip);
  return { hidden: strip.hidden, seen };
"""


def test_the_strip_shows_an_alert_in_the_alert_shade_with_age_and_reason():
    pause = {"alert": {"reason": "the Overseer gave no verdict", "since": datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - 600, timezone.utc).isoformat()}, "waiting_on_human": False}
    res = _run(STRIP, {"available": True, "running": False, "awake": [], "last_runs": {}, "pause": pause})
    assert res["hidden"] is False
    assert "ls-seg ls-pause ls-alert" in res["seen"]
    assert "Paused, needs attention" in res["seen"] and "the Overseer gave no verdict" in res["seen"]
    assert any(s.startswith("10m") or s.startswith("10 m") or "10" in s for s in res["seen"] if s not in ("Paused, needs attention",)), res["seen"]


def test_the_strip_shows_waiting_in_the_hold_shade_and_stays_one_segment():
    res = _run(STRIP, {"available": True, "running": False, "awake": [], "last_runs": {},
                       "pause": {"alert": None, "waiting_on_human": True}})
    assert res["hidden"] is False
    assert "ls-seg ls-pause ls-wait" in res["seen"] and "Paused, waiting for a person" in res["seen"]
    assert "ls-alert" not in " ".join(res["seen"])


def test_no_pause_means_the_strip_is_unchanged_and_hidden_when_idle():
    res = _run(STRIP, {"available": True, "running": False, "awake": [], "last_runs": {}})
    assert res["hidden"] is True
    res2 = _run(STRIP, {"available": True, "running": False, "awake": [], "last_runs": {},
                        "pause": {"alert": None, "waiting_on_human": False}})
    assert res2["hidden"] is True


def test_an_alert_sits_before_an_awake_role_on_the_same_one_line_strip():
    awake = [{"role": "overseer", "elapsed_s": 30, "last_tool": "queue.pending", "wake_reason": "unexplained_pause"}]
    res = _run(STRIP, {"available": True, "running": True, "awake": awake, "last_runs": {},
                       "pause": {"alert": {"reason": "held", "since": None}, "waiting_on_human": False}})
    assert res["seen"].index("ls-seg ls-pause ls-alert") < res["seen"].index("queue.pending")


def test_an_idle_alert_replaces_the_last_run_line_and_a_crowded_one_keeps_only_a_short_heading():
    last = {"overseer": {"duration_s": 40, "ended_at": "2026-10-05T11:00:00+00:00", "wake_reason": "routine_review"}}
    alert = {"alert": {"reason": "held for a human", "since": None}, "waiting_on_human": False}
    idle = _run(STRIP, {"available": True, "running": False, "awake": [], "last_runs": last, "pause": alert})
    assert "Last run" not in idle["seen"] and "Paused, needs attention" in idle["seen"]
    assert "held for a human" in idle["seen"]
    awake = [{"role": "overseer", "elapsed_s": 30, "last_tool": "queue.pending", "wake_reason": None}]
    crowded = _run(STRIP, {"available": True, "running": True, "awake": awake, "last_runs": {}, "pause": alert})
    assert "Paused" in crowded["seen"] and "Paused, needs attention" not in crowded["seen"]
    assert "held for a human" not in crowded["seen"]
