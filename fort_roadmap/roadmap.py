"""The fort roadmap, V1: seed loading, the validator, stage computation, the
plan's comply-or-explain check and the one-line summaries.

`fort_roadmap/seed-v1.yaml` is the data; this module has no I/O beyond
reading that file and one small stage-state file, and no DFHack access:
callers pass in what the world says (`alive`, the `nobles.list` read).

## What is refused and what is flagged

The validator **refuses** only what a public, generic file must never hold or
what cannot be read as a roadmap at all: a coordinate, a fort name, a landmark
or anchor, a malformed stage list. Everything else is a **flag** (a bad
signal, a target over the plan cap, a missing rationale or source, a stock
number, a confidence other than `prior`), matching the Planner's accept and
flag rule (register 2026-10-07).

## Stages

A fort's stage is the last stage, in order, whose `enter_when` has ever held,
kept as a high-water mark so a dip from 21 to 19 alive never steps it back
down (red team finding 5; decision 12). `alive` is the only trigger. A stage
that names a `game_check` (the game's own `HAS_MET_POP_REQ`, read through
`nobles.list`) is cross-checked against `alive` and any disagreement is
reported; the stage is never moved by the game's flag, nor guessed.

## The plan's side

Plan version 1 is the current stage's targets (`plan_targets`). A plan target
may carry `roadmap_ref: <entry id>`; `check_refs` computes the deviation from
that stage entry (`up`, `down` or `shape`) and flags one with no
`deviation_reason` (an information flag: the target still runs). A revision
that only adopts a newly entered stage's targets is exempt from the season
interval (`adopts_stage`).

Callers outside this package (the plan tools, `dfqueue/plan.py`) import it;
it imports `dfqueue.plan` only inside functions, so there is no import cycle.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence

import yaml

SEED_PATH = Path(__file__).resolve().parent / "seed-v1.yaml"

#: Fields of a seed target that belong to the roadmap, not the plan.
ROADMAP_ONLY_FIELDS = ("confidence", "rationale", "sources")
#: The plan-target fields a seed target may supply (a subset of
#: `dfqueue.plan.TARGET_FIELDS`; `roadmap_ref` is added on conversion).
PLAN_FIELDS = (
    "id", "signal", "per", "want", "reorder", "reorder_gap", "owner",
    "district", "max_in_flight", "note",
)
ALLOWED_CONFIDENCE = ("prior",)
#: Names this public file must not carry. Lower case, substring match.
FORBIDDEN_NAMES = ("uniboslan", "ragwind", "artobcatten", "df-colony")
#: Target keys that anchor a plan to a place.
FORBIDDEN_TARGET_KEYS = ("landmark", "anchor", "site", "coordinates", "x", "y", "z")
#: Signal families that carry stock numbers (doctrine owns those).
STOCK_FAMILIES = ("stocks", "order")

_cache: dict = {}


def seed(path: Optional[Path] = None) -> dict:
    """The seed file, re-read when its content changes."""
    p = Path(path or SEED_PATH)
    blob = p.read_bytes()
    digest = (str(p), hashlib.sha256(blob).hexdigest())
    hit = _cache.get(str(p))
    if hit is not None and hit[0] == digest:
        return hit[1]
    data = yaml.safe_load(blob.decode("utf-8")) or {}
    _cache[str(p)] = (digest, data)
    return data


# ---- the validator -------------------------------------------------------------------


def _flag(code: str, message: str, stage=None, target=None) -> dict:
    return {"code": code, "stage": stage, "id": target, "message": message}


def _threshold(stage: Mapping) -> Optional[int]:
    """The alive count a stage is entered at: 0 for `always`, else
    `alive_gte`; `None` when the condition is malformed."""
    cond = stage.get("enter_when")
    if not isinstance(cond, Mapping):
        return None
    if cond.get("always") is True and len(cond) == 1:
        return 0
    n = cond.get("alive_gte")
    if len(cond) == 1 and isinstance(n, int) and not isinstance(n, bool) and n > 0:
        return n
    return None


def validate(data: Any) -> dict:
    """`{refusals, flags}` for a roadmap document. A non-empty `refusals`
    means the document must not be used; `flags` are repairs wanted (each
    `{code, stage, id, message}`). Total: never raises on a bad document."""
    from dfqueue import plan, schema
    from doctrine import validate as doctrine_validate
    from learning import live_signals

    refusals: List[str] = []
    flags: List[dict] = []
    if not isinstance(data, Mapping):
        return {"refusals": ["the roadmap must be a mapping"], "flags": []}
    if data.get("kind") != "fort_roadmap":
        refusals.append("kind: expected 'fort_roadmap'")

    body = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    coord = schema._find_coordinate(body)
    if coord:
        refusals.append(f"contains a raw-coordinate pattern ({coord!r}); a roadmap is generic, never a position")
    low = body.lower()
    for name in FORBIDDEN_NAMES:
        if name in low:
            refusals.append(f"names {name!r}; a roadmap is generic and carries no fort or host name")

    gv = data.get("game_version")
    if not isinstance(gv, str) or not gv.strip():
        flags.append(_flag("game_version_missing", "game_version: expected the DF version the numbers are tuned for, a string"))

    stages = data.get("stages")
    if not isinstance(stages, list) or not stages:
        refusals.append("stages: expected a non-empty list")
        return {"refusals": refusals, "flags": flags}

    pol = plan.policy()
    seen_stage: set = set()
    last_threshold = -1
    for si, st in enumerate(stages):
        if not isinstance(st, Mapping):
            refusals.append(f"stages[{si}]: expected a mapping")
            continue
        sid = st.get("id")
        if not isinstance(sid, str) or not sid.strip():
            refusals.append(f"stages[{si}].id: expected a non-empty string")
            sid = f"#{si}"
        elif sid in seen_stage:
            refusals.append(f"stages[{si}].id: {sid!r} is used by more than one stage")
        seen_stage.add(sid)
        th = _threshold(st)
        if th is None:
            refusals.append(f"stage {sid}: enter_when must be {{always: true}} or {{alive_gte: N}} (N a whole number above 0)")
        else:
            if si == 0 and th != 0:
                refusals.append(f"stage {sid}: the first stage must be entered always")
            if si > 0 and th <= last_threshold:
                refusals.append(f"stage {sid}: alive_gte must be above the previous stage's ({last_threshold})")
            last_threshold = max(last_threshold, th)
        if not isinstance(st.get("summary"), str) or not st["summary"].strip():
            flags.append(_flag("summary_missing", "summary: expected one line", sid))
        gc = st.get("game_check")
        if gc is not None:
            rp = gc.get("requires_population") if isinstance(gc, Mapping) else None
            if not (isinstance(gc, Mapping) and len(gc) == 1 and isinstance(rp, int) and not isinstance(rp, bool) and rp > 0):
                flags.append(_flag("bad_game_check", "game_check: expected {requires_population: N}", sid))
        targets = st.get("targets")
        if not isinstance(targets, list):
            refusals.append(f"stage {sid}: targets must be a list")
            continue
        if len(targets) > pol["caps"]["targets"]:
            flags.append(_flag("over_cap", f"{len(targets)} targets; the plan holds at most {pol['caps']['targets']}", sid))
        seen_ids: set = set()
        ctx = plan.PlanContext()
        for ti, t in enumerate(targets):
            if not isinstance(t, Mapping):
                refusals.append(f"stage {sid}.targets[{ti}]: expected a mapping")
                continue
            tid = t.get("id") if isinstance(t.get("id"), str) and t.get("id") else f"#{ti}"
            for k in FORBIDDEN_TARGET_KEYS:
                if k in t:
                    refusals.append(f"stage {sid}, target {tid}: {k!r} anchors a target to a place; a roadmap is generic")
            sig = t.get("signal")
            if isinstance(sig, str):
                try:
                    parsed = live_signals.parse(sig)
                except live_signals.SignalError:
                    parsed = None
                if parsed is not None and (parsed.landmark is not None or parsed.exit_to is not None):
                    refusals.append(f"stage {sid}, target {tid}: signal {sig!r} names a landmark; a roadmap is generic")
                if sig.split(".", 1)[0] in STOCK_FAMILIES:
                    flags.append(_flag(
                        "stock_number",
                        f"signal {sig!r} is a stock figure; doctrine owns stock numbers, not the roadmap",
                        sid, tid,
                    ))
            if tid in seen_ids:
                flags.append(_flag("duplicate_id", f"id {tid!r} appears twice in the stage", sid, tid))
            seen_ids.add(tid)
            for k in t:
                if k not in PLAN_FIELDS and k not in ROADMAP_ONLY_FIELDS:
                    flags.append(_flag("unknown_field", f"{k}: not a roadmap target field", sid, tid))
            for pf in plan.check_target(plan_form(t, ref=False), ti, ctx, pol):
                flags.append(_flag(pf["code"], pf["message"], sid, tid))
            if t.get("confidence") not in ALLOWED_CONFIDENCE:
                flags.append(_flag("bad_confidence", f"confidence: expected one of {list(ALLOWED_CONFIDENCE)}", sid, tid))
            if not isinstance(t.get("rationale"), str) or not t["rationale"].strip():
                flags.append(_flag("rationale_missing", "rationale: expected why this number", sid, tid))
            srcs = t.get("sources")
            if not isinstance(srcs, list) or not srcs:
                flags.append(_flag("sources_missing", "sources: expected at least one, in doctrine's provenance format", sid, tid))
            else:
                for i, s in enumerate(srcs):
                    for msg in doctrine_validate._validate_source(f"{sid}.{tid}", i, s):
                        flags.append(_flag("bad_source", msg, sid, tid))
                    if isinstance(s, Mapping) and s.get("kind") == "wiki" and "revid" not in s:
                        flags.append(_flag("uncited_revision", f"sources[{i}]: a wiki source without a revid cannot be drift-checked", sid, tid))
    return {"refusals": refusals, "flags": flags}


# ---- stages ----------------------------------------------------------------------------


def stages(data: Optional[Mapping] = None) -> List[dict]:
    return list((data or seed()).get("stages") or [])


def stage_ids(data: Optional[Mapping] = None) -> List[str]:
    return [s["id"] for s in stages(data)]


def stage_entry(sid: str, data: Optional[Mapping] = None) -> Optional[dict]:
    for s in stages(data):
        if s.get("id") == sid:
            return s
    return None


def _valid_alive(alive: Any) -> bool:
    return isinstance(alive, (int, float)) and not isinstance(alive, bool) and alive >= 0


def stage_index_by_alive(alive: Any, data: Optional[Mapping] = None) -> Optional[int]:
    """The last stage whose condition holds at `alive` now, `None` when
    `alive` is unknown (never read as zero)."""
    if not _valid_alive(alive):
        return None
    best = 0
    for i, s in enumerate(stages(data)):
        th = _threshold(s)
        if th is not None and alive >= th:
            best = i
    return best


def compute_stage(alive: Any, stored: Optional[str], data: Optional[Mapping] = None) -> dict:
    """The fort's stage: the later of the stored high-water stage and the
    stage `alive` reaches now. `entered` is true when this call advanced the
    mark (the caller persists it); `held` when a dip is being ignored."""
    ids = stage_ids(data)
    stored_idx = ids.index(stored) if stored in ids else -1
    by_alive = stage_index_by_alive(alive, data)
    idx = max(stored_idx, by_alive if by_alive is not None else -1, 0)
    return {
        "stage": ids[idx], "index": idx, "alive": alive if _valid_alive(alive) else None,
        "alive_known": by_alive is not None,
        "by_alive": ids[by_alive] if by_alive is not None else None,
        "entered": idx > stored_idx,
        "first_seen": stored_idx < 0,
        "held": by_alive is not None and by_alive < idx,
    }


def next_stage(idx: int, alive: Any, data: Optional[Mapping] = None) -> Optional[dict]:
    st = stages(data)
    if idx + 1 >= len(st):
        return None
    nxt = st[idx + 1]
    return {"stage": nxt["id"], "alive_gte": _threshold(nxt), "alive": alive if _valid_alive(alive) else None}


def cross_check(alive: Any, nobles: Any, data: Optional[Mapping] = None) -> List[dict]:
    """For each stage naming a `game_check`, compare `alive` with the game's
    own population flag (`nobles.list`: the positions needing that
    population, their `population_requirement_met`). `state` is `agree`,
    `disagree`, `unreadable` (the read or `alive` is missing) or
    `no_position` (no position asks for that population). Reported, never
    acted on."""
    out: List[dict] = []
    for s in stages(data):
        gc = s.get("game_check")
        if not isinstance(gc, Mapping):
            continue
        n = gc.get("requires_population")
        row: dict = {"stage": s["id"], "requires_population": n, "alive": alive if _valid_alive(alive) else None}
        positions = nobles.get("positions") if isinstance(nobles, Mapping) else None
        if not isinstance(positions, list) or not _valid_alive(alive):
            row["state"] = "unreadable"
            out.append(row)
            continue
        rows = [p for p in positions if isinstance(p, Mapping) and p.get("requires_population") == n]
        if not rows:
            row["state"] = "no_position"
            out.append(row)
            continue
        met = any(p.get("population_requirement_met") is True for p in rows)
        reached = alive >= n
        row.update({"game_flag_met": met, "alive_reached": reached, "state": "agree" if met == reached else "disagree"})
        out.append(row)
    return out


class StageStore:
    """The stored high-water stage, one small JSON file beside the fort's
    database. A missing file is a fresh fort; an unreadable one reads as
    missing (the mark is rebuilt from `alive`, the only risk being a dip
    that is then not held), which `load` reports so the caller can say so."""

    def __init__(self, path: "Path | str"):
        self.path = Path(path)

    @classmethod
    def beside(cls, db_path: "Path | str") -> "StageStore":
        p = Path(db_path)
        return cls(p.with_name(p.stem + ".roadmap-stage.json"))

    def load(self) -> "tuple[Optional[str], bool]":
        """`(stage or None, unreadable)`."""
        if not self.path.is_file():
            return None, False
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            stage = raw.get("stage") if isinstance(raw, dict) else None
            return (stage if isinstance(stage, str) else None), not isinstance(stage, str)
        except (OSError, ValueError):
            return None, True

    def save(self, stage: str, alive: Any = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"stage": stage, "alive_when_entered": alive if _valid_alive(alive) else None}, fh)
            Path(tmp).replace(self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def _want_text(want: Any) -> str:
    if isinstance(want, Mapping):
        parts = []
        if "per_alive" in want:
            parts.append(f"{_n(want['per_alive'])}/alive")
        if "plus" in want:
            parts.append(f"+{_n(want['plus'])}")
        if "min" in want:
            parts.append(f"min {_n(want['min'])}")
        if "max" in want:
            parts.append(f"max {_n(want['max'])}")
        return " ".join(parts)
    return _n(want)


def _n(v: Any) -> str:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return "?"
    return str(int(v)) if float(v) == int(v) else f"{float(v):g}"


def status_line(block: Mapping) -> str:
    """The one compact line for the Overseer's briefing: the stage, alive and
    when the next stage comes, the top targets, and any disagreement."""
    nxt = block.get("next")
    bits = [f"ROADMAP stage {block.get('stage')}"]
    alive = block.get("alive")
    tail = f"alive {_n(alive)}" if alive is not None else "alive unknown"
    if isinstance(nxt, Mapping):
        tail += f", {nxt.get('stage')} at {nxt.get('alive_gte')}"
    bits.append(f"({tail})")
    from dfqueue import plan

    # block targets carry the flat want form; the line reads the mapping
    tgts = [f"{t.get('id')} {_want_text(plan.canonical_want(t).get('want'))}" for t in (block.get("targets") or [])[:3]]
    if tgts:
        bits.append(": " + "; ".join(tgts))
    line = " ".join(bits).replace(" :", ":")
    bad = [c for c in block.get("cross_check") or [] if c.get("state") == "disagree"]
    for c in bad:
        line += (
            f". The game's own flag for population {c.get('requires_population')} "
            f"({'met' if c.get('game_flag_met') else 'not met'}) disagrees with alive {_n(c.get('alive'))}"
        )
    return line + "."


def resolve(
    alive: Any, nobles: Any, store: Optional[StageStore], data: Optional[Mapping] = None,
    persist: bool = True,
) -> dict:
    """The fort's roadmap block: stage (high-water, persisted when it
    advances), the next stage, the cross-check, the stage's targets with
    their rationale, and the one-line summary. Total over bad inputs."""
    from dfqueue import plan

    data = data or seed()
    stored, unreadable = store.load() if store is not None else (None, False)
    cs = compute_stage(alive, stored, data)
    if persist and store is not None and cs["entered"] and cs["alive_known"]:
        try:
            store.save(cs["stage"], alive)
        except OSError:
            cs["persist_failed"] = True
    # An advance that could not be recorded still reports the stage.
    st = stage_entry(cs["stage"], data) or {}
    block = {
        "version": data.get("version"), "game_version": data.get("game_version"),
        "stage": cs["stage"], "summary": st.get("summary"), "alive": cs["alive"],
        "entered": cs["entered"], "held": cs["held"], "alive_known": cs["alive_known"],
        "next": next_stage(cs["index"], alive, data),
        "cross_check": cross_check(alive, nobles, data),
        # `want` in the flat form plan.write takes (`want`, `per`, `want_plus`,
        # `want_min`, `want_max`), so a target copied from here files verbatim.
        "targets": [
            {
                "id": t.get("id"), "signal": t.get("signal"),
                **plan.flat_want({k: t[k] for k in ("want", "per") if t.get(k) is not None}),
                "reorder_gap": t.get("reorder_gap"), "reorder": t.get("reorder"),
                "confidence": t.get("confidence"), "rationale": (t.get("rationale") or "").strip(),
            }
            for t in st.get("targets") or []
        ],
    }
    if unreadable:
        block["stage_file_unreadable"] = True
    block["line"] = status_line(block)
    return block


# ---- the plan's side -------------------------------------------------------------------


def plan_form(target: Mapping, ref: bool = True) -> dict:
    """A seed target as a plan target: the plan fields only, plus
    `roadmap_ref: <entry id>` when `ref`."""
    out = {k: json.loads(json.dumps(target[k])) for k in PLAN_FIELDS if k in target}
    if ref and isinstance(target.get("id"), str):
        out["roadmap_ref"] = target["id"]
    return out


def plan_targets(stage_id: Optional[str] = None, data: Optional[Mapping] = None) -> List[dict]:
    """The plan targets for a stage (the first stage when none is named): the
    base of a fort's plan version 1."""
    data = data or seed()
    st = stage_entry(stage_id, data) if stage_id else (stages(data) or [None])[0]
    return [plan_form(t) for t in (st or {}).get("targets") or []]


_SHAPE_KEYS = ("signal", "per", "owner", "max_in_flight", "district")


def _want_form(want: Any):
    return tuple(sorted(want)) if isinstance(want, Mapping) else "scalar"


def deviation(target: Mapping, entry: Mapping, alive: Any = None) -> Optional[str]:
    """How a plan target differs from its roadmap entry: `None` when it
    matches, `up` or `down` when the wanted level at `alive` moved with the
    same shape, otherwise `shape` (a different signal, owner, want form, key
    set, reorder rule or any other parameter)."""
    from dfqueue import plan

    # Compare the want in one form: the flat siblings are folded and a scalar
    # per-alive want equals its `{per_alive}` mapping (so a verbatim copy of an
    # entry sent through the flat form shows no deviation).
    target, entry = plan.comparable_want(target), plan.comparable_want(entry)
    keys = _SHAPE_KEYS + ("want", "reorder", "reorder_gap")
    if all(target.get(k) == entry.get(k) for k in keys):
        return None
    if any(target.get(k) != entry.get(k) for k in _SHAPE_KEYS):
        return "shape"
    if ("reorder" in target) != ("reorder" in entry) or ("reorder_gap" in target) != ("reorder_gap" in entry):
        return "shape"
    if _want_form(target.get("want")) != _want_form(entry.get("want")):
        return "shape"
    ref_alive = float(alive) if _valid_alive(alive) and alive > 0 else 1.0
    try:
        a, b = plan.want_units(target, ref_alive), plan.want_units(entry, ref_alive)
    except (KeyError, TypeError, ValueError):
        return "shape"
    if a > b:
        return "up"
    if a < b:
        return "down"
    return "shape"


def check_refs(targets: Sequence[Any], stage_id: str, alive: Any = None, data: Optional[Mapping] = None) -> dict:
    """The comply-or-explain check over a plan's targets against the fort's
    current stage. `{deviations, flags, missing}`: a deviation is
    `{id, ref, kind, reason}`; one with no `deviation_reason` also raises an
    information flag (`unexplained_deviation`) and the target still runs; a
    `roadmap_ref` naming no entry of the stage raises `roadmap_ref_unknown`;
    `missing` lists stage entries no target refers to (reported, not
    flagged: the plan's `reason` is where that is explained)."""
    from dfqueue import plan

    data = data or seed()
    entries = {e["id"]: e for e in plan_targets(stage_id, data)}
    deviations: List[dict] = []
    flags: List[dict] = []
    referenced: set = set()
    for i, t in enumerate(targets or []):
        if not isinstance(t, Mapping) or "roadmap_ref" not in t:
            continue
        tid = t.get("id") if isinstance(t.get("id"), str) and t.get("id") else f"#{i}"
        ref = t.get("roadmap_ref")
        entry = entries.get(ref) if isinstance(ref, str) else None
        if entry is None:
            flags.append(plan.flag(
                "targets", tid, "roadmap_ref_unknown",
                f"roadmap_ref {ref!r} is not an entry of the {stage_id} stage ({sorted(entries)})",
            ))
            continue
        referenced.add(ref)
        kind = deviation(t, entry, alive)
        if kind is None:
            continue
        reason = t.get("deviation_reason")
        reason = reason.strip() if isinstance(reason, str) and reason.strip() else None
        deviations.append({"id": tid, "ref": ref, "kind": kind, "reason": reason})
        if reason is None:
            flags.append(plan.flag(
                "targets", tid, "unexplained_deviation",
                f"differs from the {stage_id} roadmap entry {ref!r} ({kind}); say why in deviation_reason "
                "(the target still runs)",
            ))
    return {"deviations": deviations, "flags": flags, "missing": sorted(set(entries) - referenced)}


def adopts_stage(
    active: Optional[Mapping], changes: Sequence[Mapping], sections: Mapping, stage_id: Optional[str],
    data: Optional[Mapping] = None,
) -> bool:
    """Whether a revision only adopts the newly entered stage's targets, so
    the season interval does not apply. True when: the active version was
    filed for another stage (or before stages existed), every change is an
    entry added or changed to exactly the stage's plan entry, or an entry
    removed (any entry of a version that predates the roadmap, otherwise
    only one that carried a `roadmap_ref`), and a reorder keeps the stage
    entries in the stage's own order."""
    from dfqueue import plan

    if not stage_id or active is None or not changes:
        return False
    if active.get("roadmap_stage") == stage_id:
        return False
    data = data or seed()
    entries = plan_targets(stage_id, data)
    if not entries:
        return False
    by_id = {e["id"]: e for e in entries}
    legacy = active.get("roadmap_stage") is None   # absent or null: filed before stages existed
    new_items = list(sections.get("targets") or [])
    old_items = list(active.get("targets") or [])
    new_map = dict(zip(plan._keys(new_items), new_items))
    old_map = dict(zip(plan._keys(old_items), old_items))
    for c in changes:
        if c.get("section") != "targets":
            return False
        op, key = c.get("op"), c.get("id")
        if op in ("added", "changed"):
            item = new_map.get(key)
            if not isinstance(item, Mapping) or by_id.get(item.get("id")) != item:
                return False
        elif op == "removed":
            old = old_map.get(key)
            if not legacy and not (isinstance(old, Mapping) and "roadmap_ref" in old):
                return False
        elif op == "reordered":
            order = [t.get("id") for t in new_items if isinstance(t, Mapping) and t.get("id") in by_id]
            if order != [e["id"] for e in entries if e["id"] in order]:
                return False
        else:
            return False
    return True
