"""The live snapshot assembler: DFHack tool output in, `blocker.find_blocker`
/ `cover.compute_cover_report` input out. `handoffs/2026-09-19-snapshot-
assembler.md`.

`blocker.py` and `cover.py` are pure functions over a snapshot **the caller
assembles** (both modules' own docstrings, "no live calls in here at all").
This module is that caller's translation layer -- **still no live call
inside it either**: every function here takes tool-shaped Python data
(already read, already `json.decode`d) and returns the dict/list shapes
those two modules are documented to accept. Nothing here reaches DFHack,
same boundary rule, one level up.

## The gap, established from the tool source, not assumed

`blocker.available_quantity()` (and `cover.split_stock()`, which imports the
same constant) need all **four** deduction flags: `blocker.DEDUCTION_FLAGS`
= `("in_job", "owned", "forbid", "trader")` (spec §7's table). Grepping
every `df-overseer-*.lua` file in `scripts/dfhack/` for
`in_job|forbid|flags.owned|UNIT_HOLDER` turns up exactly one file:
`df-overseer-stocks.lua`, and there only in a header comment recording that
`flags.owned` was *checked and found unrelated* (item-level personal
ownership, not fort-vs-caravan) -- never read into any tool's return value.

The three tools that report fort-owned counts today all share one
predicate, and it is the same three-or-four-term test in each case:

- `df-overseer-stocks.lua` `is_fort_owned(item)`: `not flags.trader and not
  flags.garbage_collect and not flags.removed and not is_on_hidden_tile(item)`
  (lines 190-194).
- `df-overseer-well.lua` `is_fort_owned_item(item)`: byte-for-byte the same
  test, duplicated on purpose (its own header, "stocks.lua is not a touched
  surface this stream"), lines 200-204.
- `df-overseer-workshop.lua`'s `count_fort_owned` duplicates the identical
  test again (`building_material_report`, `BOULDER`/`WOOD`/`BLOCKS`
  fort-owned counts, and the `BARREL` count next to it) per its own
  `TOOLS.yaml` entry ("duplicated rather than reqscript'd, stocks.lua not a
  touched surface").

So **`trader` is the only one of the four deduction flags any shipped tool
nets today**, plus two extra exclusions no module here asks for
(`garbage_collect`, `removed`) and a project-specific hidden-tile guard.
`in_job`, `owned` and `forbid` are read by **none** of them. And what these
three tools return is not even item-level to begin with: `count_fort_owned`
folds straight to an integer (`n = n + 1` per passing item, well.lua lines
206-218), so there is no item list downstream of it for this module to net
further even if it wanted to -- the information is gone before the JSON is
printed. `df-overseer-stocks.lua`'s buckets are the same shape: `units`/
`item_count`/`rotten_units`/`unreachable_units` sums, never a per-item
record.

**The flags are readable in principle** -- `in_job`/`forbid`/ownership were
read live and by hand this project (`df-overseer-orders.lua`'s own header,
"3 fort-owned (ids 81, 149, 150), empty, unforbidden, unclaimed, no
holder", tick 227160) -- but that was an ad hoc `dfhack-run lua` probe in a
chat session, not a return value any committed tool exposes. Closing this
gap needs a tool change (a new command, or an extension of an existing one,
that returns per-item `in_job`/`owned`/`forbid` alongside what is already
read) -- out of scope here: **this stream may not edit the Lua tools.**

## Two input shapes, two honesty levels

1. **`fort_owned_counts_to_stock`** -- today's actual tool shape: a dict of
   `DF_TYPE -> fort_owned_count` (`well.lua`'s `requirements().fort_owned`,
   `workshop.lua`'s `building_material_report().fort_owned`). Netted for
   `trader`/`garbage_collect`/`removed`/hidden-tile only. **Cannot** be
   netted further for `in_job`/`owned`/`forbid` because the count is already
   collapsed to an integer before this module ever sees it. Every entry
   this function produces carries `status=schema.UNAVAILABLE` and an
   explicit `unnetted_flags` marker -- never `schema.MEASURED`, because
   claiming a full-netting status here is exactly the "assume the flag is
   absent-therefore-false" error the handoff warns against, and it is the
   same failure the fort already lived through once (three empty buckets
   present in a stockpile, `in_job`/reachability unread, and water still
   undelivered -- `df-overseer-orders.lua`'s own header narrative, tick
   214135). The numeric `available` is still carried through (it is the
   best information there is, and `blocker._available`/`_weakest` are
   built to use the number while downgrading the status, not to reject an
   unavailable-status figure outright) -- but no caller of this module can
   mistake the result for a netted one, because the status says so.

2. **`stock_from_items`** / **`items_for_cover`** -- the shape both modules'
   own docstrings actually ask for: item dicts carrying `in_job`, `owned`,
   `forbid`, `trader` (`blocker.DEDUCTION_FLAGS`) and, for `cover.py`,
   `rotten` plus `node_id`. No shipped tool returns this today (see above);
   these functions exist for the day one does, and are exercised in
   `test_snapshot.py` against hand-built tool-shaped fixtures so the
   translation itself is proven correct now rather than only once a live
   tool exists. A full netting here is `schema.MEASURED`, matching
   `available_quantity`'s and `split_stock`'s own status expectations.

## Vocabulary mapping

Node ids belong to whatever graph is loaded (`extract.py`'s domain, a
parallel stream, not this one) -- this module holds no hardcoded DF-type ->
node-id table of its own. Every function that needs one takes a
caller-supplied `node_id_map: Mapping[str, str]`. A DF-reported key with no
entry in that map raises `UnknownNodeError` rather than being silently
dropped (handoff: "A material the graph does not know about must surface,
never vanish").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from . import schema
from .blocker import DEDUCTION_FLAGS, available_quantity

# ---- errors -----------------------------------------------------------------


class UnknownNodeError(KeyError):
    """Raised when a DF-reported type/class has no entry in the caller's
    `node_id_map`. Never caught internally and silently skipped -- a
    material the graph does not know about must surface as a hard failure,
    not vanish from a total."""


class StockConflictError(ValueError):
    """Raised by `merge_stock` when two input stocks disagree about the
    same node id (a different `available` or `status`). Silently picking
    one source over the other is exactly the kind of miss this module's
    rules forbid reporting quietly."""


def _resolve_node_id(df_key: str, node_id_map: Mapping[str, str]) -> str:
    try:
        return node_id_map[df_key]
    except KeyError:
        raise UnknownNodeError(
            f"{df_key!r} has no node_id mapping in the supplied node_id_map "
            "-- the production graph does not (yet) know this DF type. "
            "Add it to the map, or extend the graph, rather than dropping "
            "this reading."
        ) from None


# ---- path 1: today's actual tool shape ---------------------------------------
#
# well.lua `requirements().fort_owned`, workshop.lua
# `building_material_report().fort_owned`: DF_TYPE -> integer, already netted
# for trader/garbage_collect/removed/hidden-tile (is_fort_owned /
# is_fort_owned_item, identical test, duplicated across both files -- see
# module docstring) and NOT for in_job/owned/forbid, because neither tool
# emits an item list this module could net further.

UNNETTABLE_TODAY = ("in_job", "owned", "forbid")


def _unnetted_reason(source: str, df_key: str, count: int) -> str:
    return (
        f"{source} ({df_key}): {count} fort-owned by trader/garbage_collect/"
        "removed/hidden-tile only (is_fort_owned / is_fort_owned_item; see "
        "production/snapshot.py module docstring). in_job, owned and forbid "
        "are not netted -- no shipped tool exposes them per item -- so this "
        "count may overcount true availability. Needs a tool change; see "
        "handoffs/2026-09-19-snapshot-assembler.md write-up."
    )


def fort_owned_counts_to_stock(
    fort_owned: Mapping[str, int],
    node_id_map: Mapping[str, str],
    *,
    source: str,
) -> dict[str, dict]:
    """`fort_owned`: DF type -> fort-owned integer count, the exact shape
    `well.lua`'s and `workshop.lua`'s `fort_owned` blocks already return.
    `source` names the tool this reading came from (e.g. `"df-overseer-well
    requirements"`), folded into each entry's `reason` for a reader tracing
    a figure back to its origin. Every entry is `status=schema.UNAVAILABLE`
    with `unnetted_flags=UNNETTABLE_TODAY` -- see module docstring, "Two
    input shapes, two honesty levels". Raises `UnknownNodeError` for any
    `df_key` the caller's `node_id_map` does not cover."""
    stock: dict[str, dict] = {}
    for df_key, count in fort_owned.items():
        node_id = _resolve_node_id(df_key, node_id_map)
        stock[node_id] = {
            "available": count,
            "status": schema.UNAVAILABLE,
            "unnetted_flags": UNNETTABLE_TODAY,
            "reason": _unnetted_reason(source, df_key, count),
        }
    return stock


def merge_stock(*stocks: Mapping[str, Mapping]) -> dict[str, dict]:
    """Combine several stock dicts (e.g. one from `well.lua`'s reading, one
    from `workshop.lua`'s) into one `blocker.find_blocker`-ready mapping.
    Two sources reporting the *same* node id must agree on both `available`
    and `status`, or this raises `StockConflictError` -- picking one
    silently would hide a real disagreement (a stale read, a race, two
    tools disagreeing about the same item type) behind a single number."""
    merged: dict[str, dict] = {}
    for stock in stocks:
        for node_id, entry in stock.items():
            if node_id in merged:
                prior = merged[node_id]
                if prior.get("available") != entry.get("available") or prior.get("status") != entry.get("status"):
                    raise StockConflictError(
                        f"conflicting stock entries for {node_id!r}: "
                        f"{prior!r} vs {entry!r}"
                    )
                continue
            merged[node_id] = dict(entry)
    return merged


# ---- path 2: the shape blocker.py / cover.py actually document --------------
#
# Item dicts carrying blocker.DEDUCTION_FLAGS (`in_job`, `owned`, `forbid`,
# `trader`) plus `node_id` and (for cover.py) `rotten`. No shipped tool
# returns this today (see module docstring); these functions exist so the
# translation is proven correct in advance of one, against hand-built
# tool-shaped fixtures in test_snapshot.py.


def translate_items(
    raw_items: Iterable[Mapping],
    node_id_map: Mapping[str, str] | None = None,
    *,
    type_key: str = "df_type",
) -> list[dict]:
    """Normalises a list of tool-reported item dicts into the flat shape
    `blocker.available_quantity` / `cover.split_stock` are documented to
    accept: `node_id`, `in_job`, `owned`, `forbid`, `trader`, `rotten`.

    Each `raw_items` entry is read defensively, not assumed to already
    match the target shape: a flag may be given at the top level (`{"df_type":
    "BUCKET", "in_job": True, ...}`) or nested under `"flags"` (mirroring
    `item.flags.in_job`-style DFHack struct access, `{"df_type": "BUCKET",
    "flags": {"in_job": True}}`) -- either is accepted, and a top-level key
    wins if somehow both are present. A missing flag reads as `False`
    (matching `blocker.available_quantity`'s and `cover.split_stock`'s own
    `item.get(flag)` convention -- absence is a normal, expected shape for
    an item that simply is not claimed/owned/forbidden/trader-held, not a
    read failure). `node_id_map` is optional: pass it when `raw_items` key
    their type under `type_key` (default `"df_type"`) and need translating
    to a node id; omit it when `raw_items` already carry a `node_id` field
    directly. Unknown types raise `UnknownNodeError`, never silently drop
    the item."""
    out: list[dict] = []
    for raw in raw_items:
        flags_nested = raw.get("flags") or {}
        if node_id_map is not None:
            node_id = _resolve_node_id(raw[type_key], node_id_map)
        else:
            node_id = raw["node_id"]
        item = {"node_id": node_id}
        for flag in (*DEDUCTION_FLAGS, "rotten"):
            item[flag] = raw.get(flag, flags_nested.get(flag, False))
        out.append(item)
    return out


def stock_from_items(
    raw_items: Iterable[Mapping],
    node_id_map: Mapping[str, str] | None = None,
    *,
    type_key: str = "df_type",
) -> dict[str, dict]:
    """Builds a `blocker.find_blocker`-ready stock mapping from item-level
    tool output (see `translate_items`), fully netted via
    `blocker.available_quantity` over all four deduction flags. Grouped by
    the resolved `node_id`; every entry is `status=schema.MEASURED` because,
    unlike `fort_owned_counts_to_stock`, this path has actually seen and
    deducted all four flags on every item."""
    items = translate_items(raw_items, node_id_map, type_key=type_key)
    by_node: dict[str, list[dict]] = {}
    for item in items:
        by_node.setdefault(item["node_id"], []).append(item)
    return {
        node_id: {"available": available_quantity(node_items), "status": schema.MEASURED}
        for node_id, node_items in by_node.items()
    }


def items_for_cover(
    raw_items: Iterable[Mapping],
    node_id_map: Mapping[str, str] | None = None,
    *,
    type_key: str = "df_type",
) -> list[dict]:
    """`cover.split_stock` / `cover.compute_cover_report` take a flat item
    iterable directly (no per-node grouping) -- this is `translate_items`
    under the name the cover-report call site actually wants, so a reader
    of `snapshot.py`'s public surface does not have to know the two
    functions are the same shape by coincidence."""
    return translate_items(raw_items, node_id_map, type_key=type_key)
