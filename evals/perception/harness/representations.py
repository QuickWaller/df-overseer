"""Representations: fixture -> the text the model actually sees.

Every representation here is linear text. None of them renders a map, in any
form — that is design commitment #1 (docs/PURPOSE.md) and it is not a variable
this harness sweeps over. What it does sweep over is *which linear encoding*
carries spatial facts best, which is the part the design guessed at.

Each representation declares what classes of fact it can express:

  topology            which landmarks connect directly to which
  connected_geometry  bearing / distance / z-delta between DIRECTLY connected
                      landmarks
  global_geometry     the same, between an ARBITRARY pair
  facts               population, resources, units, alerts, event log

The question generator tags each question with what it needs, and the runner
skips combinations a representation cannot express, rather than scoring a
representation on questions its encoding never contained the answer to. Which
questions get skipped is itself a finding: it names the zoom tools the agent
must be given, because no amount of prompting will recover a fact the briefing
never carried.
"""

from __future__ import annotations

import json

from .fixture import Fixture

# Byte-identical output across runs is a hard requirement, not tidiness: the
# whole prefix-caching design (research spec section 7) depends on the stable
# part of the briefing serializing the same way every turn.
_JSON = dict(sort_keys=True, indent=2, ensure_ascii=False, separators=(",", ": "))


def _tier0(fx: Fixture) -> dict:
    return {
        "fortress": fx.fortress,
        "embark_biome": fx.embark_biome,
        "representation": None,  # filled per-representation
    }


def _tier2(fx: Fixture) -> dict:
    return {
        "in_game_date": fx.in_game_date,
        "alerts": fx.alerts,
        "citizens_of_note": sorted(
            (
                {
                    "name": u["name"],
                    "profession": u.get("profession", "unknown"),
                    "last_seen_at": u.get("at"),
                }
                for u in fx.units
            ),
            key=lambda u: u["name"],
        ),
        "recent_events": fx.events,
    }


def _exits_for(fx: Fixture, name: str) -> list[dict]:
    out = []
    for other in fx.neighbours(name):
        conn = fx.connection(name, other)
        assert conn is not None
        out.append(
            {
                "to": other,
                "direction": fx.bearing(name, other),
                "distance_tiles": fx.straight_line_tiles(name, other),
                "walk_tiles": conn.walk_tiles,
                "z_delta": fx.z_delta(name, other),
                "via": conn.via,
            }
        )
    return sorted(out, key=lambda e: e["to"])


# --------------------------------------------------------------------------
# exits_v1 — the representation the design actually proposes
# --------------------------------------------------------------------------


def exits_v1(fx: Fixture) -> str:
    t0 = _tier0(fx)
    t0["representation"] = "exits_v1"
    briefing = {
        "tier0": t0,
        "tier1": {
            "population": fx.population,
            "landmarks": [
                {"name": l.name, "kind": l.kind, "exits": _exits_for(fx, l.name)}
                for l in sorted(fx.landmarks, key=lambda l: l.name)
            ],
            "resource_summary": fx.resources,
        },
        "tier2": _tier2(fx),
    }
    return json.dumps(briefing, **_JSON)


exits_v1.provides = {"topology", "connected_geometry", "facts"}
exits_v1.blurb = (
    "Named landmarks with an exit list each: direction, distance, z-delta, and "
    "the route type. No coordinates. This is the representation docs/PURPOSE.md "
    "commits to."
)


# --------------------------------------------------------------------------
# coords_v1 — control arm: raw coordinates, still linear text
# --------------------------------------------------------------------------


def coords_v1(fx: Fixture) -> str:
    t0 = _tier0(fx)
    t0["representation"] = "coords_v1"
    t0["axes"] = "x increases east, y increases south, z increases upward"
    briefing = {
        "tier0": t0,
        "tier1": {
            "population": fx.population,
            "landmarks": [
                {"name": l.name, "kind": l.kind, "x": l.pos[0], "y": l.pos[1], "z": l.pos[2]}
                for l in sorted(fx.landmarks, key=lambda l: l.name)
            ],
            "connections": sorted(
                (
                    {
                        "between": sorted([c.a, c.b]),
                        "via": c.via,
                        "walk_tiles": c.walk_tiles,
                    }
                    for c in fx.connections
                ),
                key=lambda c: c["between"],
            ),
            "resource_summary": fx.resources,
        },
        "tier2": _tier2(fx),
    }
    return json.dumps(briefing, **_JSON)


coords_v1.provides = {"topology", "connected_geometry", "global_geometry", "facts"}
coords_v1.blurb = (
    "A coordinate table plus a flat connection list — the representation the "
    "design rejected on the way to exits_v1. Strictly more informative, so it "
    "is the fair control: if it wins on the shared questions, the landmark "
    "idiom is not paying for itself."
)


# --------------------------------------------------------------------------
# prose_v1 — same facts as exits_v1, as English
# --------------------------------------------------------------------------


def _prose_exit(e: dict) -> str:
    z = (
        "on the same level"
        if e["z_delta"] == 0
        else f"{abs(e['z_delta'])} level{'s' if abs(e['z_delta']) != 1 else ''} "
        + ("up" if e["z_delta"] > 0 else "down")
    )
    return (
        f"{e['to']} lies {e['distance_tiles']} tiles to the {e['direction']}, "
        f"{z}, reached by {e['via']} ({e['walk_tiles']} tiles of walking)"
    )


def prose_v1(fx: Fixture) -> str:
    lines = [
        f"FORTRESS {fx.fortress}, {fx.embark_biome}. It is {fx.in_game_date}. "
        f"Population {fx.population}.",
        "",
        "LAYOUT",
    ]
    for l in sorted(fx.landmarks, key=lambda l: l.name):
        exits = _exits_for(fx, l.name)
        if exits:
            body = "; ".join(_prose_exit(e) for e in exits) + "."
        else:
            body = "It connects directly to nothing."
        lines.append(f"- {l.name} ({l.kind}). From here: {body}")

    lines += ["", "RESOURCES"]
    for key in sorted(fx.resources):
        value = fx.resources[key]
        rendered = ", ".join(value) if isinstance(value, list) else str(value)
        lines.append(f"- {key}: {rendered}")

    lines += ["", "CITIZENS OF NOTE"]
    for u in sorted(fx.units, key=lambda u: u["name"]):
        lines.append(
            f"- {u['name']}, {u.get('profession', 'unknown')}, "
            f"last seen at {u.get('at', 'an unrecorded place')}."
        )

    lines += ["", "ALERTS"]
    if fx.alerts:
        for a in fx.alerts:
            lines.append(f"- [{a.get('type', 'alert')}] {a.get('detail', '')}")
    else:
        lines.append("- None.")

    lines += ["", "RECENT EVENTS"]
    if fx.events:
        for e in fx.events:
            lines.append(f"- {e.get('type', 'event')}: {e.get('detail', '')}")
    else:
        lines.append("- None.")

    return "\n".join(lines)


prose_v1.provides = {"topology", "connected_geometry", "facts"}
prose_v1.blurb = (
    "Exactly the facts exits_v1 carries, written as English sentences. Isolates "
    "the encoding from the content: if prose and exits_v1 score the same, the "
    "JSON structure is buying nothing but tokens."
)


REPRESENTATIONS = {
    "exits_v1": exits_v1,
    "coords_v1": coords_v1,
    "prose_v1": prose_v1,
}
