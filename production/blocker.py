"""The AND-OR blocker walk: `docs/PRODUCTION-MODEL.md` §1 question 1, §9
rung 1, `handoffs/2026-09-18-blocker-walk.md`.

A pure function over a snapshot plus the stored graph (`schema.py`'s seven
tables, or hand-built rows of the same shape). **No live calls in here at
all**: the caller reads DFHack, deducts, and hands in a `stock` dict; this
module only walks the already-assembled facts. Same boundary the days-of-
cover calculator uses, same reason (spec §9's "Interface" note).

## The walk, in one paragraph

A goal is a `(target, is_class)` pair: a **node** id for a concrete item or
building, or a **class** name. `production_flow.node_id` mixes the two by
design (spec §4's own comment, confirmed in `production/extract.py`'s
`_reagent_class`): a reagent row always names a *class*, a product row
always names a *node*. This module holds that distinction as a parameter
rather than guessing from string shape, because guessing is exactly the
naive-query trap the handoff warns about.

A target needs `quantity` units. If the snapshot already has that much
**available** (never total -- spec §7's four deductions happen before this
module ever sees the number), the target is satisfied. If not, every
process that lists the target as a product is a candidate route (the OR).
A candidate route needs *all* of its reagents, plus its workshop node
(spec §7: "buildings are nodes", checked with the exact same machinery as
any other reagent -- no special case). That is the AND. The first route
with every requirement satisfied wins; if none do, the walk reports the
first node with zero available stock and no completable process of its
own, named, with the quantity short, and the path taken to reach it.

## What is NOT modelled here, on purpose

- **Multi-run quantity propagation.** If a process yields 5 units per run
  and the goal needs 12, this walk does not compute "3 runs, so 3x each
  reagent". It asks only "is one run of this process completable" per
  spec §9's own scope ("Blocking... never a coordinate", not a quantity
  forecast) and per the min-cost-flow question being explicitly a later,
  separate piece (spec §2). The `quantity_short` on a *blocker* is exact
  (it is a stock subtraction); a *satisfied* target's route is not scaled.
- **Per-class routing preference.** When a class reagent (e.g. "chain or
  rope") is satisfied by summed stock across its members, this module does
  not report *which* member covers it. That is a display concern for the
  caller, not a blocking fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from . import schema

# ---- available stock, never total (spec sec7) -----------------------------
#
# Four deductions, all exact reads on the live side; this function is the
# pure netting step the caller runs *before* building the snapshot this
# module walks. The fifth case (item moved to a trade depot) is
# unverified per spec sec7/docs sec17 -- this function recognises no
# `on_depot`-shaped flag, so an item carrying one is neither deducted nor
# claimed to be handled; callers must keep such items out of the pool
# rather than pass them through here.

DEDUCTION_FLAGS = ("in_job", "owned", "forbid", "trader")


def available_quantity(items: Iterable[Mapping]) -> int:
    """Net count of `items`, each a dict that may carry the boolean flags
    `in_job` (`item.flags.in_job`), `owned` (`item.flags.owned` plus a
    `UNIT_HOLDER` ref), `forbid` (`item.flags.forbid`, **not**
    `forbidden`), and `trader` (`flags.trader`). An item counts toward the
    total unless at least one of those four reads true. Pure arithmetic
    over data the caller already read live; this function makes no DFHack
    call itself."""
    count = 0
    for item in items:
        if any(item.get(flag) for flag in DEDUCTION_FLAGS):
            continue
        count += 1
    return count


# ---- status combination -----------------------------------------------------
#
# spec sec3/interface: "a status on every figure used, so a blocker derived
# from a prior cannot be mistaken for one derived from raws." A result's
# status is the weakest of every status it touched: a node's own
# `production_node.status`, a stock entry's status, or a nested target's
# status. Rank order below is "how much to trust this", low to high;
# `_weakest` takes the minimum.

_STATUS_RANK = {
    schema.UNAVAILABLE: 0,
    schema.PRIOR: 1,
    schema.MEASURED: 2,
    schema.VERIFIED_RAWS: 3,
}


def _weakest(statuses: Iterable[str]) -> str:
    statuses = list(statuses)
    if not statuses:
        return schema.UNAVAILABLE
    return min(statuses, key=lambda s: _STATUS_RANK.get(s, 0))


# ---- the graph index ---------------------------------------------------------


@dataclass(frozen=True)
class ProductionGraph:
    """An indexed read-only view over `production_node` / `production_class`
    / `production_process` / `production_flow` rows (the same dict shapes
    `extract.py` emits and `store.write_all` accepts), built once and
    walked many times. Holds no live handle and no coordinate."""

    nodes_by_id: dict
    classes_by_node: dict          # node_id -> set(class)
    members_by_class: dict         # class -> set(node_id)
    processes_by_id: dict          # process_id -> process row
    flows_by_process: dict         # process_id -> list(flow row)
    producers_by_node: dict        # node_id -> list(process_id), product flows
    producers_by_class: dict       # class -> list(process_id), product flows whose node_id is a class member


def build_graph(
    nodes: list[dict], classes: list[dict], processes: list[dict], flows: list[dict],
) -> ProductionGraph:
    nodes_by_id = {n["id"]: n for n in nodes}

    classes_by_node: dict[str, set] = {}
    members_by_class: dict[str, set] = {}
    for c in classes:
        classes_by_node.setdefault(c["node_id"], set()).add(c["class"])
        members_by_class.setdefault(c["class"], set()).add(c["node_id"])

    processes_by_id = {p["id"]: p for p in processes}

    flows_by_process: dict[str, list] = {}
    producers_by_node: dict[str, list] = {}
    producers_by_class: dict[str, list] = {}
    for f in flows:
        flows_by_process.setdefault(f["process_id"], []).append(f)
        if f["direction"] == schema.PRODUCT and f.get("node_id") is not None:
            node_id = f["node_id"]
            plist = producers_by_node.setdefault(node_id, [])
            if f["process_id"] not in plist:
                plist.append(f["process_id"])
            for cls in classes_by_node.get(node_id, ()):
                clist = producers_by_class.setdefault(cls, [])
                if f["process_id"] not in clist:
                    clist.append(f["process_id"])

    return ProductionGraph(
        nodes_by_id=nodes_by_id, classes_by_node=classes_by_node,
        members_by_class=members_by_class, processes_by_id=processes_by_id,
        flows_by_process=flows_by_process, producers_by_node=producers_by_node,
        producers_by_class=producers_by_class,
    )


# ---- result shapes -----------------------------------------------------------


@dataclass(frozen=True)
class Blocker:
    """The named blocker: a leaf target with zero available stock and no
    completable process of its own. Never a coordinate -- `target` is
    always a node id or class name, the same closed vocabulary the schema
    already uses."""

    target: str
    is_class: bool
    quantity_needed: int
    quantity_available: int
    quantity_short: int
    status: str
    path: tuple[str, ...]


@dataclass(frozen=True)
class BranchOutcome:
    """One OR branch considered at some point in the walk: a process that
    could have produced the target one level up, and whether it was
    actually completable. `blocker` is set exactly when `completable` is
    False, and is the *deepest* blocker under that branch, not the branch's
    own target -- so a reader sees why the branch died, not just that it
    did."""

    process_id: str
    completable: bool
    blocker: "Blocker | None"


@dataclass(frozen=True)
class WalkResult:
    goal: str
    is_class: bool
    blocked: bool
    blocker: "Blocker | None"
    path: tuple[str, ...]
    route: "tuple[str, ...] | None"     # process id used to satisfy the goal; () if satisfied from stock directly; None if blocked
    branches: tuple[BranchOutcome, ...]  # every OR branch this call itself evaluated (not nested ones)
    status: str


class GraphTraversalError(Exception):
    """Raised instead of recursing forever or overflowing the stack. A
    depth guard and a visited-set guard are both cheaper than trusting the
    data (handoff, 'Cases worth testing'), so both are active; either can
    fire first depending on the graph's shape."""


DEFAULT_MAX_DEPTH = 64


# ---- the walk itself ----------------------------------------------------------


def _node_status(target: str, is_class: bool, graph: ProductionGraph) -> str:
    if is_class:
        members = graph.members_by_class.get(target, ())
        statuses = [graph.nodes_by_id[m]["status"] for m in members if m in graph.nodes_by_id]
        return _weakest(statuses) if statuses else schema.UNAVAILABLE
    node = graph.nodes_by_id.get(target)
    return node["status"] if node else schema.UNAVAILABLE


def _available(
    target: str, is_class: bool, graph: ProductionGraph, stock: Mapping[str, Mapping],
) -> tuple[int, str]:
    if is_class:
        members = graph.members_by_class.get(target, ())
        total = 0
        statuses = [_node_status(target, True, graph)]
        for m in members:
            entry = stock.get(m)
            if entry is not None:
                total += entry.get("available", 0)
                statuses.append(entry.get("status", schema.MEASURED))
        return total, _weakest(statuses)

    entry = stock.get(target)
    node_status = _node_status(target, False, graph)
    if entry is None:
        return 0, node_status
    return entry.get("available", 0), _weakest([node_status, entry.get("status", schema.MEASURED)])


def _producers(target: str, is_class: bool, graph: ProductionGraph) -> list[str]:
    if is_class:
        return list(graph.producers_by_class.get(target, ()))
    return list(graph.producers_by_node.get(target, ()))


def _requirements(process_id: str, graph: ProductionGraph) -> list[dict]:
    """The AND set for one process: its workshop node (spec sec7, checked
    with no special case) plus every reagent flow. A reagent's `node_id` is
    always read as a *class* (spec sec4's node_id comment; extract.py's
    `_reagent_class` never emits a bare node id for a reagent); a product's
    is always a concrete node -- this module trusts that distinction rather
    than inferring it, which is the naive-query trap the handoff names."""
    reqs: list[dict] = []
    process = graph.processes_by_id.get(process_id, {})
    workshop = process.get("workshop_node")
    if workshop:
        reqs.append({"target": workshop, "is_class": False, "quantity": 1})
    for f in graph.flows_by_process.get(process_id, ()):
        if f["direction"] != schema.REAGENT:
            continue
        node_id = f.get("node_id")
        if node_id is None:
            # An unresolved reagent (spec sec6 pass 2: a parametric flow
            # pass 2 never joined). Nothing names what would satisfy it, so
            # it can never read as completable -- treated as a class with
            # no members, which _available reports as 0 available,
            # UNAVAILABLE, and _producers reports as no producers, which is
            # the same failure mode this row's own data honestly supports.
            reqs.append({"target": f"{process_id}:UNRESOLVED_REAGENT", "is_class": True, "quantity": 1})
            continue
        qty = f.get("quantity") or 1
        reqs.append({"target": node_id, "is_class": True, "quantity": qty})
    return reqs


def _walk(
    target: str, is_class: bool, quantity: int, graph: ProductionGraph,
    stock: Mapping[str, Mapping], path: tuple[str, ...], visiting: frozenset,
    depth: int, max_depth: int,
) -> WalkResult:
    if depth > max_depth:
        raise GraphTraversalError(
            f"depth guard tripped at {depth} walking to {target!r} "
            f"(path so far: {' -> '.join(path)}); either a genuinely deep "
            f"chain exceeds max_depth or a cycle escaped the visited-set guard"
        )
    key = (target, is_class)
    if key in visiting:
        raise GraphTraversalError(
            f"cycle detected: {' -> '.join(path)} -> {target} revisits a node "
            f"already on the path"
        )
    visiting = visiting | {key}
    path = path + (target,)

    available, avail_status = _available(target, is_class, graph, stock)
    if available >= quantity:
        return WalkResult(
            goal=target, is_class=is_class, blocked=False, blocker=None,
            path=path, route=(), branches=(), status=avail_status,
        )

    producers = _producers(target, is_class, graph)
    if not producers:
        blocker = Blocker(
            target=target, is_class=is_class, quantity_needed=quantity,
            quantity_available=available, quantity_short=quantity - available,
            status=avail_status, path=path,
        )
        return WalkResult(
            goal=target, is_class=is_class, blocked=True, blocker=blocker,
            path=path, route=None, branches=(), status=avail_status,
        )

    branch_outcomes: list[BranchOutcome] = []
    for process_id in producers:
        reqs = _requirements(process_id, graph)
        process_blocker: Blocker | None = None
        sub_statuses = [avail_status]
        for req in reqs:
            sub = _walk(
                req["target"], req["is_class"], req["quantity"], graph, stock,
                path + (process_id,), visiting, depth + 1, max_depth,
            )
            sub_statuses.append(sub.status)
            if sub.blocked:
                process_blocker = sub.blocker
                break  # AND short-circuits: one failing reagent kills this route
        if process_blocker is None:
            # This route is fully completable -- report it live rather than
            # continuing to enumerate remaining producers (handoff: "the
            # live route", not an exhaustive branch survey).
            return WalkResult(
                goal=target, is_class=is_class, blocked=False, blocker=None,
                path=path, route=(process_id,), branches=tuple(branch_outcomes),
                status=_weakest(sub_statuses),
            )
        branch_outcomes.append(
            BranchOutcome(process_id=process_id, completable=False, blocker=process_blocker)
        )

    # Every producer dead. Report the first branch's own deepest blocker as
    # *the* named blocker (it is already the true leaf, not "target"
    # itself, by construction above), while keeping every branch's reason
    # visible in `branches`.
    chosen = branch_outcomes[0].blocker
    assert chosen is not None
    return WalkResult(
        goal=target, is_class=is_class, blocked=True, blocker=chosen,
        path=chosen.path, route=None, branches=tuple(branch_outcomes),
        status=_weakest([b.blocker.status for b in branch_outcomes if b.blocker is not None]),
    )


def find_blocker(
    goal: str,
    graph: ProductionGraph,
    stock: Mapping[str, Mapping],
    *,
    is_class: bool = False,
    quantity: int = 1,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> WalkResult:
    """Entry point. `goal` is a node id (`is_class=False`, the normal case
    -- a building or item goal) or a class name (`is_class=True`). `stock`
    maps node id -> `{"available": int, "status": str}`, already netted by
    `available_quantity` (or equivalent) on the caller's side -- never a
    live call from in here."""
    return _walk(goal, is_class, quantity, graph, stock, path=(), visiting=frozenset(), depth=0, max_depth=max_depth)
