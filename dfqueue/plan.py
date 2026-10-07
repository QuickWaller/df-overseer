"""The fort plan, as pure logic: section composition, flags, the diff, the
season interval and the shortfall arithmetic.

`research/2026-10-07-planner-design.md` 2 (revision 2) and `handoffs/
2026-10-07-planner-p1a.md`. The plan is **intent, never action**: it names
targets (later districts, industries, flows) by kind and signal, never a tile,
a site or a step. The `fort_plan` record kind is in `dfqueue/schema.py`; the
stateful parts (the active version, the base check, the ruling citation, the
`plan_change` rate limit, in-flight work) are in `dfqueue/store.py`; the tools
are in `dfmcp/plan_tools.py`. This module has no I/O beyond reading its own
policy and default plan files, and no DFHack or queue access: callers pass in
what the world says.

## Accept and flag, never refuse for content

The user's call (register 2026-10-07, Planner open question 1, option b): the
server **accepts and flags** plan mistakes (a kind typo, an unknown landmark,
an oversized section, a malformed signal, a bad threshold). Flags come back in
`plan.write`'s reply and are stored on the record; a flagged entry is **inert**
(never measured, never woken on) until fixed. What is refused is only what
cannot be stored at all: a payload that is not the schema shape, a section
that has no home in the record yet, a section that is not a list of objects,
and coordinates. Both live elsewhere (`schema._validate_fort_plan_fields`,
`compose` below).

A version that changes **only entries the active version flagged** is exempt
from the season interval (`fix_only`), so a typo never costs a season.

## Season

`season_index = tick // season_ticks` (policy, 100,800), stamped on every
version (F-3, F-11). One version per season index, except version 1, a
fix-only version, and a version citing an accepted `plan_change` ruling. An
active version from a *later* season than now (a test-harness reload, which
`docs/ARMOK-RULINGS.md` allows) counts as elapsed.

## The arithmetic (design 2.6), never rounded before comparing

```
position = on_hand + in_flight
per alive: compare against want * alive
open (reorder_gap)  = want*alive - position >= reorder_gap
open (reorder)      = position < reorder * alive
```
A target whose signal cannot be read, or whose want needs an alive count that
is missing, is `unresolved`, never a shortfall.

A `want` is a number (optionally with `per: alive`, want * alive) or a mapping
`{per_alive, plus, min, max}`: wanted level = clamp(per_alive * alive + plus,
min, max). `reorder_gap` is always units short of the computed wanted level;
with the mapping form `reorder` is an absolute level (no per-citizen scale),
since the wanted level is not a constant multiple of alive.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import yaml

from learning import live_signals

from . import schema, templates

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = Path(__file__).resolve().parent / "plan_policy.yaml"
DEFAULT_PLAN_PATH = REPO_ROOT / "plans" / "default-v1.yaml"

_cache: dict = {}


def _read_cached(path: Path, key: str) -> Any:
    blob = Path(path).read_bytes()
    digest = (str(path), hashlib.sha256(blob).hexdigest())
    hit = _cache.get(key)
    if hit is not None and hit[0] == digest:
        return hit[1]
    data = yaml.safe_load(blob.decode("utf-8")) or {}
    _cache[key] = (digest, data)
    return data


def policy() -> dict:
    """`dfqueue/plan_policy.yaml`, re-read when its content changes (a test
    may point `POLICY_PATH` at a temp file)."""
    return _read_cached(POLICY_PATH, "policy")


def default_plan() -> dict:
    """`plans/default-v1.yaml`: the base version 1 is composed from."""
    return _read_cached(DEFAULT_PLAN_PATH, "default")


# ---- season ---------------------------------------------------------------------


def season_index(tick: int, pol: Optional[Mapping] = None) -> int:
    pol = pol or policy()
    return int(tick) // int(pol["season_ticks"])


def next_season_tick(tick: int, pol: Optional[Mapping] = None) -> int:
    pol = pol or policy()
    return (season_index(tick, pol) + 1) * int(pol["season_ticks"])


# ---- composition ------------------------------------------------------------------


class PlanShapeError(Exception):
    """The payload cannot be stored as a plan (a refusal, never a flag). The
    message lists every problem."""


def compose(active: Optional[Mapping], set_sections: Any) -> dict:
    """The full `targets` (and later sections) of the new version: the active
    version's sections (or `plans/default-v1.yaml` for version 1) with each
    section in `set_sections` replacing its whole list. Raises
    `PlanShapeError` listing every problem; content mistakes are not problems
    here (they are flagged by `check_sections`)."""
    pol = policy()
    errors: list[str] = []
    if set_sections is None:
        set_sections = {}
    if not isinstance(set_sections, dict):
        raise PlanShapeError("set: expected an object mapping a section name to its full list")
    open_sections = list(pol["open_sections"])
    for name, items in set_sections.items():
        if name not in pol["sections"]:
            errors.append(
                f"set.{name}: not a plan section (sections: {sorted(pol['sections'])})"
            )
            continue
        if name not in open_sections:
            errors.append(
                f"set.{name}: arrives at stage {pol['sections'][name]}; this server stores "
                f"only {open_sections} so far"
            )
            continue
        if not isinstance(items, list):
            errors.append(f"set.{name}: expected a list (the section's whole new list)")
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"set.{name}.{i}: expected an object")
    if errors:
        raise PlanShapeError("; ".join(errors))
    base = dict(active) if active is not None else dict(default_plan())
    out: dict = {}
    for name in open_sections:
        items = set_sections[name] if name in set_sections else base.get(name, [])
        out[name] = json.loads(json.dumps(items))  # a deep copy; never alias the base
    return out


# ---- the diff -----------------------------------------------------------------------


def _keys(items: list) -> list[str]:
    """A stable key per entry: its `id`, a duplicate or missing id made
    unique by position."""
    seen: dict[str, int] = {}
    keys = []
    for i, item in enumerate(items):
        base = item.get("id") if isinstance(item, dict) and isinstance(item.get("id"), str) else f"#{i}"
        n = seen.get(base, 0)
        seen[base] = n + 1
        keys.append(base if n == 0 else f"{base}#{n + 1}")
    return keys


def diff_changes(old: Mapping, new: Mapping) -> list[dict]:
    """What a new version changes against the previous sections (or, for
    version 1, against the default): `{section, id, op, fields?}`, `op` one of
    `added`, `removed`, `changed`, `reordered`. Computed by the server, never
    typed by the Planner (F-20)."""
    out: list[dict] = []
    for section in policy()["open_sections"]:
        o_items, n_items = list(old.get(section) or []), list(new.get(section) or [])
        o_keys, n_keys = _keys(o_items), _keys(n_items)
        o_map, n_map = dict(zip(o_keys, o_items)), dict(zip(n_keys, n_items))
        for k in n_keys:
            if k not in o_map:
                out.append({"section": section, "id": k, "op": "added"})
            elif o_map[k] != n_map[k]:
                a, b = o_map[k], n_map[k]
                fields = sorted(
                    f for f in set(a if isinstance(a, dict) else {}) | set(b if isinstance(b, dict) else {})
                    if (a.get(f) if isinstance(a, dict) else None) != (b.get(f) if isinstance(b, dict) else None)
                )
                out.append({"section": section, "id": k, "op": "changed", "fields": fields})
        for k in o_keys:
            if k not in n_map:
                out.append({"section": section, "id": k, "op": "removed"})
        kept_old = [k for k in o_keys if k in n_map]
        kept_new = [k for k in n_keys if k in o_map]
        if kept_old != kept_new:
            out.append({"section": section, "id": None, "op": "reordered"})
    return out


# ---- flags -------------------------------------------------------------------------

#: Flags that are information, not a fault: the entry still works.
INFO_CODES = frozenset({"kinds_unchecked", "unreadable_citation"})

TARGET_FIELDS = (
    "id", "signal", "per", "want", "reorder", "reorder_gap", "owner",
    "district", "max_in_flight", "note",
)


class PlanContext:
    """What the world says, passed in by the caller: the zone kind tokens
    (`zone.list-kinds`) and the landmark names (`landmarks.list`), each `None`
    when that read could not be made (then the matching check is skipped and
    one `kinds_unchecked` info flag says so)."""

    def __init__(
        self, zone_kinds: Optional[Iterable[str]] = None, landmarks: Optional[Iterable[str]] = None,
        roster_roles: Optional[Iterable[str]] = None,
    ):
        self.zone_kinds = set(zone_kinds) if zone_kinds is not None else None
        self.landmarks = set(landmarks) if landmarks is not None else None
        self.roster_roles = set(roster_roles) if roster_roles is not None else None


def _flag(section: str, eid, code: str, message: str, **extra) -> dict:
    f = {
        "section": section, "id": eid, "code": code, "message": message,
        "inert": code not in INFO_CODES,
    }
    f.update(extra)
    return f


flag = _flag  # public: the tool layer raises the flags only it can know (an unreadable citation)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _nearest(token: str, choices: Iterable[str]) -> Optional[str]:
    close = difflib.get_close_matches(token, sorted(choices), n=1, cutoff=0.5)
    return close[0] if close else None


def check_signal(signal: Any, ctx: PlanContext, section: str, eid) -> list[dict]:
    """Flags for one signal string: unparseable, not an integer signal where
    one is needed is the caller's, an unknown zone kind (the nearest token
    named), an unknown landmark."""
    out: list[dict] = []
    try:
        parsed = live_signals.parse(signal)
    except live_signals.SignalError as exc:
        return [_flag(section, eid, "bad_signal", str(exc))]
    if parsed.zone_kind is not None and ctx.zone_kinds is not None and parsed.zone_kind not in ctx.zone_kinds:
        near = _nearest(parsed.zone_kind, ctx.zone_kinds)
        msg = f"zone kind {parsed.zone_kind!r} is not a kind the game has (zone.list-kinds)"
        if near:
            msg += f"; did you mean {near!r}?"
        out.append(_flag(section, eid, "unknown_kind", msg, **({"nearest": near} if near else {})))
    if ctx.landmarks is not None:
        for name in (parsed.landmark, parsed.exit_to):
            if name is not None and name not in ctx.landmarks:
                near = _nearest(name, ctx.landmarks)
                msg = f"landmark {name!r} does not exist now (landmarks.list)"
                if near:
                    msg += f"; did you mean {near!r}?"
                out.append(_flag(section, eid, "unknown_landmark", msg, **({"nearest": near} if near else {})))
    return out


WANT_KEYS = ("per_alive", "plus", "min", "max")


def _finite_num(v) -> bool:
    return _is_num(v) and math.isfinite(v)


def want_mapping_problems(want: Mapping) -> list[str]:
    """Repair text for every fault in a mapping-form `want` (empty when it is
    sound): unknown keys, non-finite or negative numbers, neither of
    per_alive/plus, min above max."""
    probs: list[str] = []
    for k in want:
        if k not in WANT_KEYS:
            probs.append(f"{k}: not a want key (keys: {list(WANT_KEYS)})")
    for k in WANT_KEYS:
        if k not in want:
            continue
        v = want[k]
        if not _finite_num(v):
            probs.append(f"{k}: expected a finite number, got {v!r}")
        elif v < 0 and k != "plus":
            probs.append(f"{k}: expected a number of 0 or more (only plus may be negative), got {v!r}")
    if "per_alive" not in want and "plus" not in want:
        probs.append("give at least one of per_alive or plus")
    if _finite_num(want.get("min")) and _finite_num(want.get("max")) and want["min"] > want["max"]:
        probs.append(f"min {want['min']!r} is above max {want['max']!r}")
    return probs


def want_uses_alive(target: Mapping) -> bool:
    """Whether the target's wanted level needs the alive count."""
    w = target.get("want")
    if isinstance(w, Mapping):
        return "per_alive" in w
    return target.get("per") == "alive"


def want_units(target: Mapping, alive: Optional[float]) -> float:
    """The computed wanted level in absolute units (the caller has checked
    alive when `want_uses_alive`). Scalar form: want, times alive under
    `per: alive`. Mapping form: clamp(per_alive * alive + plus, min, max)."""
    w = target["want"]
    if not isinstance(w, Mapping):
        return float(w) * (float(alive) if target.get("per") == "alive" else 1.0)
    level = float(w.get("per_alive", 0.0)) * (float(alive) if "per_alive" in w else 0.0) + float(w.get("plus", 0.0))
    if "min" in w:
        level = max(level, float(w["min"]))
    if "max" in w:
        level = min(level, float(w["max"]))
    return level


def check_target(entry: Mapping, index: int, ctx: PlanContext, pol: Mapping) -> list[dict]:
    eid = entry.get("id") if isinstance(entry.get("id"), str) and entry.get("id") else f"#{index}"
    out: list[dict] = []
    if not (isinstance(entry.get("id"), str) and entry.get("id")):
        out.append(_flag("targets", eid, "bad_field", "id: expected a non-empty string"))
    for k in entry:
        if k not in TARGET_FIELDS:
            out.append(_flag("targets", eid, "unknown_field", f"{k}: not a target field (fields: {list(TARGET_FIELDS)})"))
    signal = entry.get("signal")
    if "signal" not in entry:
        out.append(_flag("targets", eid, "bad_signal", "signal: required"))
    else:
        sig_flags = check_signal(signal, ctx, "targets", eid)
        out.extend(sig_flags)
        if not any(f["code"] == "bad_signal" for f in sig_flags):
            if live_signals.parse(signal).value_type != live_signals.INTEGER:
                out.append(_flag(
                    "targets", eid, "bad_signal_type",
                    f"signal {signal!r} is not a number; a target measures an integer count",
                ))
    per = entry.get("per")
    if per is not None and per not in pol["target"]["per"]:
        out.append(_flag("targets", eid, "bad_field", f"per: expected one of {pol['target']['per']} or absent, got {per!r}"))
    want = entry.get("want")
    mapping_form = isinstance(want, Mapping)
    if mapping_form:
        probs = want_mapping_problems(want)
        for pr in probs:
            out.append(_flag("targets", eid, "bad_threshold", f"want: {pr}"))
        if per is not None:
            out.append(_flag("targets", eid, "bad_field", "per: not used with a mapping want; put per_alive inside want, or drop per"))
        want = want.get("max") if not probs and _finite_num(want.get("max")) else None
    elif not _is_num(want) or want <= 0 or not math.isfinite(want):
        out.append(_flag(
            "targets", eid, "bad_threshold",
            f"want: expected a number above 0 or a mapping {{per_alive, plus, min, max}}, got {want!r}",
        ))
        want = None
    has_ratio, has_gap = "reorder" in entry, "reorder_gap" in entry
    if has_ratio == has_gap:
        out.append(_flag("targets", eid, "bad_threshold", "give exactly one of reorder (a level) or reorder_gap (units short)"))
    elif has_ratio:
        r = entry["reorder"]
        if not _is_num(r) or r <= 0 or (want is not None and r > want):
            out.append(_flag("targets", eid, "bad_threshold", f"reorder: expected a number above 0 and no more than want{' (an absolute level with a mapping want; at most its max)' if mapping_form else ''}, got {r!r}"))
    else:
        g = entry["reorder_gap"]
        if not _is_num(g) or g <= 0:
            out.append(_flag("targets", eid, "bad_threshold", f"reorder_gap: expected a number above 0, got {g!r}"))
    owner = entry.get("owner")
    if not isinstance(owner, str) or not owner:
        out.append(_flag("targets", eid, "owner_unknown", "owner: required, the role that serves this target"))
    else:
        roles = ctx.roster_roles
        vocab = schema.TYPE_VOCAB_BY_ROLE.get(owner, ())
        if (roles is not None and owner not in roles) or not vocab:
            out.append(_flag("targets", eid, "owner_unknown", f"owner {owner!r} is not a role that proposes work"))
        elif isinstance(signal, str):
            family = signal.split(".", 1)[0]
            serving = (pol.get("family_serving_types") or {}).get(family)
            if serving is not None and not set(serving) & set(vocab):
                out.append(_flag(
                    "targets", eid, "owner_cannot_serve",
                    f"owner {owner!r} proposes {list(vocab)}, none of which serves a {family} signal ({serving})",
                ))
    mif = entry.get("max_in_flight")
    if mif is not None and (isinstance(mif, bool) or not isinstance(mif, int) or not 1 <= mif <= pol["target"]["max_in_flight_max"]):
        out.append(_flag("targets", eid, "bad_field", f"max_in_flight: expected an integer 1 to {pol['target']['max_in_flight_max']}"))
    for name in ("note", "district"):
        v = entry.get(name)
        if v is None:
            continue
        if not isinstance(v, str):
            out.append(_flag("targets", eid, "bad_field", f"{name}: expected a string"))
        elif len(v) > pol["field_max"]:
            out.append(_flag("targets", eid, "text_too_long", f"{name}: {len(v)} characters; at most {pol['field_max']}"))
    return out


def check_sections(sections: Mapping, ctx: PlanContext, pol: Optional[Mapping] = None) -> list[dict]:
    """Every flag for the composed sections: per entry checks, duplicate ids,
    item caps (entries beyond a cap are flagged inert, never dropped)."""
    pol = pol or policy()
    flags: list[dict] = []
    items = list(sections.get("targets") or [])
    cap = pol["caps"]["targets"]
    seen: set = set()
    for i, entry in enumerate(items):
        flags.extend(check_target(entry, i, ctx, pol))
        eid = entry.get("id")
        if isinstance(eid, str) and eid:
            if eid in seen:
                flags.append(_flag("targets", eid, "duplicate_id", f"id {eid!r} is used by more than one target"))
            seen.add(eid)
        if i >= cap:
            flags.append(_flag(
                "targets", eid if isinstance(eid, str) and eid else f"#{i}", "over_cap",
                f"target {i + 1} is over the cap of {cap}; it is inert until the list is trimmed",
            ))
    if ctx.zone_kinds is None:
        flags.append(_flag(
            "plan", None, "kinds_unchecked",
            "zone kind tokens could not be read this time (zone.list-kinds), so kinds were not checked",
        ))
    return flags


def check_text_fields(reason: Any, public_rationale: Any, relies_on: Any, ctx: PlanContext, pol: Optional[Mapping] = None) -> list[dict]:
    """Flags for the plan-level fields: over-long reason or public rationale,
    too many `relies_on` entries, a malformed or unparseable cited signal."""
    pol = pol or policy()
    out: list[dict] = []
    if isinstance(reason, str) and len(reason) > pol["field_max"]:
        out.append(_flag("plan", None, "text_too_long", f"reason: {len(reason)} characters; at most {pol['field_max']}"))
    if isinstance(public_rationale, str) and len(public_rationale) > pol["public_rationale_max"]:
        out.append(_flag("plan", None, "text_too_long", f"public_rationale: {len(public_rationale)} characters; at most {pol['public_rationale_max']}"))
    if isinstance(relies_on, list):
        if len(relies_on) > pol["caps"]["relies_on"]:
            out.append(_flag("relies_on", None, "over_cap", f"relies_on: {len(relies_on)} entries; at most {pol['caps']['relies_on']}"))
        for i, ref in enumerate(relies_on):
            if not isinstance(ref, dict):
                continue
            if "signal" in ref:
                if set(ref) - {"signal"}:
                    out.append(_flag("relies_on", f"#{i}", "bad_field", "a signal citation carries only `signal`"))
                out.extend(check_signal(ref.get("signal"), ctx, "relies_on", f"#{i}"))
            elif not (isinstance(ref.get("tool"), str) and isinstance(ref.get("field"), str)):
                out.append(_flag("relies_on", f"#{i}", "bad_field", "cite either {signal} or {tool, args?, field}"))
    return out


def inert_keys(flags: Iterable[Mapping]) -> set:
    """`(section, id)` of every entry with an inert flag."""
    return {(f["section"], f.get("id")) for f in flags if f.get("inert") and f.get("id") is not None}


# ---- guardrails ------------------------------------------------------------------------


def fix_only(changes: list, active_flags: Iterable[Mapping]) -> bool:
    """A version that only changes or removes entries the active version
    flagged inert is a correction, exempt from the season interval. No added
    entry, no reorder, nothing unflagged."""
    if not changes:
        return False
    inert = inert_keys(active_flags)
    for c in changes:
        if c["op"] not in ("changed", "removed"):
            return False
        if (c["section"], c["id"]) not in inert:
            return False
    return True


def guardrail(
    active: Optional[Mapping], tick: int, changes: list, ruling_id: Optional[str] = None,
    pol: Optional[Mapping] = None,
) -> dict:
    """The season interval (design 2.4 item 1): `{ok, reason, refusal?}`.
    `reason` names why a version was allowed: `first`, `new_season`,
    `reload`, `fix_only` or `ruled`. The ruling's own validity is the
    store's check; here a cited `ruling_id` only makes the interval exempt."""
    pol = pol or policy()
    if active is None:
        return {"ok": True, "reason": "first"}
    if ruling_id:
        return {"ok": True, "reason": "ruled"}
    cur = season_index(tick, pol)
    have = active.get("season_index")
    if not isinstance(have, int) or have < cur:
        return {"ok": True, "reason": "new_season"}
    if have > cur:
        return {"ok": True, "reason": "reload"}
    if fix_only(changes, active.get("flags") or []):
        return {"ok": True, "reason": "fix_only"}
    return {
        "ok": False, "reason": "interval",
        "refusal": (
            f"season {cur} already has plan version {active.get('version')} (one version per season). "
            f"The next season opens at tick {next_season_tick(tick, pol)}. To revise sooner: file only "
            "corrections to entries that version flagged (those are exempt), or file a plan_change "
            "proposal, wait for the Overseer to accept it, and file again with its ruling id as ruling_id."
        ),
    }


# ---- shortfall arithmetic ---------------------------------------------------------------


def target_position(
    target: Mapping, on_hand: Optional[float], in_flight: float, alive: Optional[float],
) -> dict:
    """One target's position and state. Never rounds before comparing.
    `state` is `unresolved` when the signal or the alive count cannot be
    read, `open` below the reorder level (or `reorder_gap` units short),
    `quiet` otherwise; `below_want` says whether the want itself is met."""
    per_alive = want_uses_alive(target)
    mapping_form = isinstance(target.get("want"), Mapping)
    out: dict = {"on_hand": on_hand, "in_flight": in_flight}
    if on_hand is None:
        return {**out, "state": "unresolved", "why": "signal could not be read"}
    if per_alive and (alive is None or isinstance(alive, bool) or alive <= 0):
        return {**out, "state": "unresolved", "why": "no alive count to divide by"}
    # A scalar `reorder` is per citizen under `per: alive`; with a mapping
    # want it is an absolute level.
    scale = float(alive) if (per_alive and not mapping_form) else 1.0
    position = on_hand + in_flight
    wanted = want_units(target, alive)
    short = wanted - position
    out.update({"position": position, "want_units": wanted, "short_units": max(0.0, short)})
    if "reorder_gap" in target:
        is_open = short >= float(target["reorder_gap"])
    else:
        is_open = position < float(target["reorder"]) * scale
    out["below_want"] = position < wanted
    out["state"] = "open" if is_open else "quiet"
    return out


def derived_inputs(
    requires: Iterable[str], count: float, available: Mapping[str, Optional[float]], pol: Optional[Mapping] = None,
) -> list[dict]:
    """The inputs a target's serving template needs for `count` in-flight
    sites: `[{item, needed, available, owner, short}]`, `available` None when
    unread. One unit of each required item per site (a `requires` entry is
    one item). The owner is policy data (`item_owner`)."""
    pol = pol or policy()
    out = []
    for item in requires:
        have = available.get(item)
        out.append({
            "item": item, "needed": count, "available": have,
            "owner": (pol.get("item_owner") or {}).get(item, pol["default_item_owner"]),
            "short": None if have is None else max(0.0, count - have),
        })
    return out


def item_type(item: str, pol: Optional[Mapping] = None) -> str:
    """The `stocks.availability` TYPE key for a `requires` item."""
    pol = pol or policy()
    return (pol.get("item_types") or {}).get(item, item.upper())


def input_owner_roles(target: Mapping, template_dir=None, pol: Optional[Mapping] = None) -> set:
    """The owners of a target's derived inputs (a role that may also serve
    the target, design F-1): empty when no template serves its signal."""
    pol = pol or policy()
    tpl = templates.serving(target.get("signal"), template_dir) if isinstance(target.get("signal"), str) else None
    if tpl is None:
        return set()
    return {
        (pol.get("item_owner") or {}).get(item, pol["default_item_owner"]) for item in tpl["requires"]
    }


def may_serve(target: Mapping, role: str, template_dir=None) -> bool:
    """`serves` is accepted from the target's owner or the owner of one of
    its derived inputs (design 2.5, F-1)."""
    return role == target.get("owner") or role in input_owner_roles(target, template_dir)


# ---- role slices -----------------------------------------------------------------------


def slice_for_role(plan_targets: list, role: str, template_dir=None) -> list:
    """The target lines a role is shown: all of them for the Planner, the
    overseer and the conductor (they see the whole plan); for any other role,
    only the targets it owns or whose derived inputs it owns (design 2.5)."""
    if role in (schema.PLAN_ROLE, schema.sole_writer(), schema.OBSERVATION_ROLE):
        return list(plan_targets)
    out = []
    for t in plan_targets:
        if isinstance(t, dict) and may_serve(t, role, template_dir):
            out.append(t)
    return out


def version_line(record: Mapping) -> dict:
    """One history line for `plan.read`."""
    return {
        "version": record.get("version"), "id": record.get("id"),
        "season_index": record.get("season_index"), "tick": record.get("cycle"),
        "reason": record.get("reason"), "ruling_id": record.get("ruling_id"),
        "changes": len(record.get("changes") or []), "flags": len(record.get("flags") or []),
    }
