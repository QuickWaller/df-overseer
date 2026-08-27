"""Fort ledger schema: field definitions, controlled vocabularies, validation.

One ledger row per fortress, written when the fort ends. This is a **trial
registry**: `decisions/DECISIONS.md` (2026-08-25) moved it to the earliest
build item because "nothing else in the learning design is checkable without
it, and its schema determines what can ever be learned."

Four rules produced every field below. The first three are from
`research/2026-08-25-learning-architecture.md` section 3.2; the fourth is this
repo's own and the research does not state it.

1.  **Attribution is at the feature level, never the decision level.** With
    ~20 forts you cannot honestly say a decision in year 4 killed a fort; you
    can compare coarse recorded features across forts. So features are closed
    vocabularies. Free text does not stratify, and a field that cannot
    stratify can never become a lesson.

2.  **Covariates at the time of the event, not only at embark.** "This fort
    had two entrances and died" is worth almost nothing without the year, the
    population, and the size of the thing that killed it. `threat_log` carries
    those; `embark` carries the fixed confounds ("embarked beside a goblin
    fortress" is the strawman's own example of what goes unadjusted-for).

3.  **Plural, ranked contributing factors, never one `cause_of_death`
    string.** A fort dies of a chain; flattening the chain to one label
    destroys exactly the structure that process-tracing needs.

4.  **Every field declares how it gets populated** (`source`). A field with no
    mechanical path is a field that will be empty or wishful in six months.
    Only `MECHANICAL` and `DERIVED` fields may be read by any grading code.
    `docs/MEMORY-ARCHITECTURE.md`'s "never grade the agent's account of its own
    learning" is enforced here, in the schema, rather than left to discipline.

## Orthogonality

Design features are deliberately split into narrow orthogonal axes rather than
one `entrance_design` blob. The register's build item 8 (the
one-variable-at-a-time experiment selector) is meaningless if a single field
bundles three independent choices: you cannot "vary one variable" when the
variable is a portmanteau. `entrance_count`, `entrance_seal` and
`entrance_traps` are three fields for this reason, not for tidiness.

## The `unrecorded` sentinel

Every vocabulary includes `unrecorded`, and stratification **excludes** it
rather than pooling it into a bucket. This is the mechanical enforcement of
section 3.2's central warning: an unrecorded feature can never become a lesson,
and the ledger should say so out loud instead of quietly treating "we didn't
look" as if it were a measurement.

## Status

**Proposed, not verified.** No field's mechanical path has been checked against
a running DFHack instance; see `MECHANICAL_PATH_VERIFIED` below. The
vocabularies are informed by the game but were not validated against the DFHack
API surface, because no game side of this project exists yet.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = 1

# No field's `MECHANICAL` claim has been confirmed against a live DFHack
# instance: there is no perception layer yet to confirm it with. Flip this
# only when a real extraction script has populated a real row, and record the
# check in decisions/DECISIONS.md.
MECHANICAL_PATH_VERIFIED = False

# ---- how a field gets populated -------------------------------------------

MECHANICAL = "mechanical"  # read from game state by code; no judgement involved
DERIVED = "derived"        # computed from other ledger fields
AGENT = "agent"            # the overseer asserted it. NEVER read by grading.
HUMAN = "human"            # a person wrote it

#: Sources that grading and hypothesis-evidence code are permitted to read.
GRADEABLE_SOURCES = frozenset({MECHANICAL, DERIVED})

# ---- the sentinel ---------------------------------------------------------

UNRECORDED = "unrecorded"

# ---- controlled vocabularies ----------------------------------------------

AQUIFER = ("none", "light", "heavy", UNRECORDED)

ENTRANCE_SEAL = ("none", "door", "hatch", "drawbridge", "mixed", UNRECORDED)
ENTRANCE_TRAPS = ("none", "cage", "weapon", "both", UNRECORDED)
CAVERNS_SEALED = ("never_breached", "sealed", "partial", "open", UNRECORDED)
MILITARY_POSTURE = (
    "none", "traps_only", "part_time_militia", "standing_squad",
    "multiple_squads", UNRECORDED,
)
SURFACE_FOOTPRINT = (
    "none", "minimal", "workshops_above", "full_surface_fort", UNRECORDED,
)
WATER_SOURCE = (
    "brook", "river", "well_from_cistern", "well_from_aquifer",
    "murky_pools", "none", UNRECORDED,
)
FOOD_STRATEGY = (
    "underground_farm", "surface_farm", "fishing", "foraging",
    "trade_dependent", "mixed", "none", UNRECORDED,
)
PRIMARY_INDUSTRY = (
    "none", "crafts_for_trade", "stonework", "weapons_armour", "textiles",
    "brewing", "mixed", UNRECORDED,
)
BURIAL_PROVISION = ("none", "coffins_only", "tomb_complex", UNRECORDED)
DEFENSE_DEPTH = ("none", "single_layer", "layered", UNRECORDED)

#: How the fort ended. `run_ended_technical` and the `agent_error` factor exist
#: on purpose: a ledger that cannot record "FPS collapsed and we stopped" or
#: "the overseer walled its own dwarves in" will produce a flattering, wrong
#: picture of how this project actually went.
FORT_STATUS = (
    "alive",
    "dead_all",                 # every dwarf dead
    "dead_abandoned",           # abandoned under threat, fort effectively lost
    "abandoned_deliberate",     # walked away by choice, fort intact
    "retired",                  # retired to be revisited
    "reclaimed",                # this row covers a reclaim of an earlier site
    "run_ended_technical",      # FPS collapse, crash, infrastructure failure
    UNRECORDED,
)

THREAT_KIND = (
    "goblin_siege", "goblin_ambush", "goblin_snatcher", "kobold_thief",
    "human_siege", "elf_siege", "undead_siege", "megabeast",
    "forgotten_beast", "titan", "demon", "werebeast", "cavern_ambush",
    "cavern_creature", "none", UNRECORDED,
)

THREAT_OUTCOME = (
    "repelled_no_losses", "repelled_with_losses", "survived_besieged",
    "fort_lost", "ignored_departed", UNRECORDED,
)

#: What contributed to the end. Ranked and plural; see rule 3.
CONTRIBUTING_FACTOR = (
    # violence
    "siege_overrun", "ambush_losses", "megabeast_rampage",
    "forgotten_beast_rampage", "undead_overrun", "werebeast_outbreak",
    "cavern_breach_invasion",
    # sustenance
    "starvation", "dehydration", "food_production_failure",
    # morale
    "tantrum_spiral", "unhappiness_cascade", "insanity_deaths",
    "loyalty_cascade",
    # environment / engineering
    "flood_water", "flood_magma", "cave_in", "aquifer_breach", "miasma",
    "trapped_by_own_construction",
    # logistics
    "stranded_pathing", "resource_exhaustion", "economic_collapse",
    "hauling_gridlock",
    # us, not the game
    "agent_error", "human_intervention",
    # infrastructure
    "fps_collapse", "crash_or_corruption",
    UNRECORDED,
)

MILESTONE_KIND = (
    "first_migrant_wave", "trade_depot_built", "first_death",
    "first_squad_formed", "caverns_breached", "caverns_sealed",
    "aquifer_pierced", "magma_reached", "well_completed", "first_artifact",
    "first_siege", "first_noble_demand", "monarch_arrived",
    "tantrum_spiral_start", "population_peak", UNRECORDED,
)

#: Van Evera's process-tracing typology. The rubric is applied at *write* time
#: by a fixed rule, not by the model's sense of how convincing it felt.
#:
#:   straw_in_the_wind  — consistent with the hypothesis, discriminates weakly.
#:                        "Fort had two entrances and died", no breach data.
#:   hoop               — the hypothesis must pass this to stay alive; passing
#:                        does not confirm it. Failing it is near-fatal.
#:   smoking_gun        — passing strongly confirms; failing is weak evidence
#:                        against. "The breach was at the second entrance and
#:                        nowhere else."
#:   doubly_decisive    — passing confirms and failing refutes. Rare; be
#:                        suspicious of any claim to have found one.
DIAGNOSTICITY = ("straw_in_the_wind", "hoop", "smoking_gun", "doubly_decisive")

OBSERVATION_RELATION = ("corroborates", "contradicts")


# ---- field spec -----------------------------------------------------------


@dataclass(frozen=True)
class Field:
    """One ledger field, and the reason it exists.

    `why` is not decoration. Section 3.2's point is that schema design *is*
    learning design, so a field nobody can justify is a field that should be
    removed rather than filled in badly.
    """

    name: str
    type: str
    source: str
    why: str
    required: bool = True
    vocab: tuple[str, ...] | None = None
    nullable: bool = False


# Fixed at embark. These are the confounds every cross-fort comparison has to
# condition on; without them, Bradford Hill "consistency" cannot be checked.
EMBARK_FIELDS: tuple[Field, ...] = (
    Field("start_year", "integer", MECHANICAL,
          "Anchors the fort in world time; threat rate rises with world age."),
    Field("biome", "string", MECHANICAL,
          "Free text by necessity: DF's biome names are many and compound. "
          "Stratify on the derived flags below, not on this."),
    Field("surroundings", "string", MECHANICAL,
          "Savagery/evil of the embark tile. Drives threat kind and rate; the "
          "single largest environmental confound."),
    Field("embark_tiles", "integer", MECHANICAL,
          "Embark area. Bears on FPS ceiling and on how much surface to hold."),
    Field("aquifer", "vocab", MECHANICAL,
          "Light vs heavy is a different game, not a different difficulty.",
          vocab=AQUIFER),
    Field("has_flux", "boolean", MECHANICAL,
          "Gates steel, which gates a real military. A military-doctrine "
          "comparison that ignores flux availability is comparing nothing."),
    Field("has_shallow_metal", "boolean", MECHANICAL,
          "Gates early weapons and traps."),
    Field("has_deep_metal", "boolean", MECHANICAL,
          "Gates late military capability."),
    Field("soil_depth", "integer", MECHANICAL,
          "Determines whether underground farming is available immediately.",
          nullable=True),
    Field("trees", "string", MECHANICAL,
          "Wood availability gates beds, barrels, and charcoal."),
    Field("nearest_hostile_civ_distance", "integer", MECHANICAL,
          "THE confound named in the design docs: a fort that died beside a "
          "goblin fortress did not necessarily die of its entrance design.",
          nullable=True),
    Field("neighbour_civs", "string_list", MECHANICAL,
          "Which civs can reach us at all. Determines the threat menu."),
    Field("starting_dwarves", "integer", MECHANICAL,
          "Normally 7; recorded because it is an experiment axis."),
    Field("world_age", "integer", MECHANICAL,
          "Older worlds have stronger, more numerous hostile civs.",
          nullable=True),
)

# The design choices whose effects we are trying to learn. Closed vocabularies,
# orthogonal axes; see the module docstring.
DESIGN_FIELDS: tuple[Field, ...] = (
    Field("entrance_count", "integer", MECHANICAL,
          "Split from seal and traps so each can be varied alone."),
    Field("entrance_seal", "vocab", MECHANICAL,
          "What actually closes the entrance, if anything.",
          vocab=ENTRANCE_SEAL),
    Field("entrance_traps", "vocab", MECHANICAL,
          "Trap type at the entrance, independent of whether it seals.",
          vocab=ENTRANCE_TRAPS),
    Field("caverns_sealed", "vocab", MECHANICAL,
          "`never_breached` and `sealed` are different states with different "
          "risk profiles and must not collapse into one 'safe' bucket.",
          vocab=CAVERNS_SEALED),
    Field("caverns_sealed_year", "integer", MECHANICAL,
          "The doc's example doctrine is 'seal the caverns before year 3', a "
          "claim about timing, untestable without the year.",
          nullable=True),
    Field("military_posture", "vocab", MECHANICAL,
          "Ordinal-ish ladder from none to multiple squads.",
          vocab=MILITARY_POSTURE),
    Field("military_first_squad_year", "integer", MECHANICAL,
          "Timing again: 'raise a militia early' is a timing claim.",
          nullable=True),
    Field("surface_footprint", "vocab", MECHANICAL,
          "How much above ground there is to defend.",
          vocab=SURFACE_FOOTPRINT),
    Field("water_source", "vocab", MECHANICAL,
          "Wells vs surface water changes siege survivability.",
          vocab=WATER_SOURCE),
    Field("food_strategy", "vocab", MECHANICAL,
          "Surface farming and fishing both fail under siege; underground "
          "farming does not. A siege-survival comparison needs this.",
          vocab=FOOD_STRATEGY),
    Field("primary_industry", "vocab", MECHANICAL,
          "What the fort spent its labour on.", vocab=PRIMARY_INDUSTRY),
    Field("burial_provision", "vocab", MECHANICAL,
          "Unburied corpses drive the unhappiness cascade; this is the "
          "candidate cause for tantrum-spiral hypotheses.",
          vocab=BURIAL_PROVISION),
    Field("defense_depth", "vocab", MECHANICAL,
          "Whether there is anything behind the first line.",
          vocab=DEFENSE_DEPTH),
    Field("max_depth_z", "integer", MECHANICAL,
          "How deep the fort went. Bears on cavern and magma exposure.",
          nullable=True),
    Field("peak_dwarf_count", "integer", MECHANICAL,
          "Population is both an outcome and a covariate: a fort of 20 and a "
          "fort of 200 do not face the same siege."),
)

MILESTONE_FIELDS: tuple[Field, ...] = (
    Field("year", "integer", MECHANICAL, "When it happened."),
    Field("kind", "vocab", MECHANICAL, "Closed set so milestones stratify.",
          vocab=MILESTONE_KIND),
    Field("detail", "string", AGENT, "Prose colour. Never read by grading.",
          required=False, nullable=True),
)

# Rule 2: covariates *at the time of the event*. This record is the reason the
# ledger can distinguish "died to a siege" from "died to a siege at year 3 with
# 14 dwarves and no military".
THREAT_FIELDS: tuple[Field, ...] = (
    Field("year", "integer", MECHANICAL, "Event time."),
    Field("kind", "vocab", MECHANICAL, "What arrived.", vocab=THREAT_KIND),
    Field("attacker_count", "integer", MECHANICAL,
          "Siege size is the dominant covariate for siege survival.",
          nullable=True),
    Field("population_at_time", "integer", MECHANICAL,
          "Not peak population, not final population: population *then*."),
    Field("military_strength_at_time", "integer", MECHANICAL,
          "Count of dwarves in active squads at the time of the event."),
    Field("outcome", "vocab", MECHANICAL, "How it resolved.",
          vocab=THREAT_OUTCOME),
    Field("dwarf_deaths", "integer", MECHANICAL, "Losses from this event."),
    Field("breach_location", "string", MECHANICAL,
          "Landmark name where the defence was penetrated, if it was. This is "
          "the field that turns a straw-in-the-wind observation into a "
          "smoking-gun one; see DIAGNOSTICITY.",
          required=False, nullable=True),
)

CONTRIBUTING_FACTOR_FIELDS: tuple[Field, ...] = (
    Field("rank", "integer", HUMAN,
          "1 = largest contributor. Ranked, not weighted: weights at N~20 "
          "would be false precision."),
    Field("factor", "vocab", HUMAN, "Closed set so causes stratify.",
          vocab=CONTRIBUTING_FACTOR),
    Field("evidence", "string", HUMAN,
          "What in the record supports this being a contributor."),
)

OUTCOME_FIELDS: tuple[Field, ...] = (
    Field("status", "vocab", MECHANICAL, "How the fort ended.",
          vocab=FORT_STATUS),
    Field("end_year", "integer", MECHANICAL, "In-game year at the end.",
          nullable=True),
    Field("duration_years", "integer", DERIVED,
          "end_year - start_year. The headline survival metric.",
          nullable=True),
    Field("population_at_end", "integer", MECHANICAL, "Survivors.",
          nullable=True),
    Field("total_deaths", "integer", MECHANICAL, "Cumulative dwarf deaths."),
    Field("contributing_factors", "record_list:contributing_factor", HUMAN,
          "Plural and ranked, per rule 3. An empty list is legitimate for a fort "
          "that is still alive; it is NOT legitimate for a fort that ended."),
    Field("wealth_at_end", "integer", MECHANICAL,
          "Created wealth drives siege scaling, so it is a covariate as well "
          "as a score.", nullable=True),
)

# The evidence link. One record per hypothesis this fort bears on.
OBSERVATION_FIELDS: tuple[Field, ...] = (
    Field("hypothesis_id", "string", HUMAN,
          "Which hypothesis this observation bears on."),
    Field("relation", "vocab", HUMAN, "Direction of the evidence.",
          vocab=OBSERVATION_RELATION),
    Field("diagnosticity", "vocab", HUMAN,
          "Van Evera class, assigned by the fixed rubric in DIAGNOSTICITY, "
          "not by how convincing the narrative felt.",
          vocab=DIAGNOSTICITY),
    Field("rationale", "string", HUMAN,
          "Why this class and not a weaker one. The audit trail for the "
          "single field most vulnerable to motivated reasoning."),
    Field("supporting_fields", "string_list", HUMAN,
          "Dotted paths to the ledger fields this rests on, e.g. "
          "'threat_log.0.breach_location'. Makes the claim checkable against "
          "the mechanical record instead of taken on trust.",
          required=False),
)

# Null unless this fort was a deliberate one-variable-at-a-time trial.
EXPERIMENT_FIELDS: tuple[Field, ...] = (
    Field("variable", "string", HUMAN,
          "The single design field varied, as a dotted path e.g. "
          "'design.entrance_seal'. One field; that is the whole discipline."),
    Field("value", "string", HUMAN, "What it was set to here."),
    Field("control_fort_id", "string", HUMAN,
          "The fort this is being compared against.", nullable=True),
    Field("hypothesis_id", "string", HUMAN, "What it was meant to resolve."),
    Field("same_world_as_control", "boolean", DERIVED,
          "Re-embarking in the same world holds the largest confound constant "
          "(register, 2026-08-25). False is allowed but weakens the trial a "
          "lot, and the comparison should say so."),
)

RECORD_FIELDS: dict[str, tuple[Field, ...]] = {
    "embark": EMBARK_FIELDS,
    "design": DESIGN_FIELDS,
    "milestone": MILESTONE_FIELDS,
    "threat": THREAT_FIELDS,
    "contributing_factor": CONTRIBUTING_FACTOR_FIELDS,
    "outcome": OUTCOME_FIELDS,
    "observation": OBSERVATION_FIELDS,
    "experiment": EXPERIMENT_FIELDS,
}

# The three identity levels are load-bearing for the hierarchical model: fort
# nested in site nested in world is exactly the grouping structure partial
# pooling needs (research section 3.3). Without world_id there is no
# world-level random effect and the model collapses back into the flat counter
# it was chosen to replace.
FORT_FIELDS: tuple[Field, ...] = (
    Field("schema_version", "integer", DERIVED,
          "Rows written under an older schema must be identifiable. Section "
          "3.2 warns that retrofitting covariates defeats the purpose, so this "
          "makes the gap visible rather than silent."),
    Field("fort_id", "string", HUMAN, "Unique. Convention: name-yNNN."),
    Field("world_id", "string", MECHANICAL,
          "Grouping variable for the world-level effect."),
    Field("site_id", "string", MECHANICAL,
          "Embark site. Two forts at one site share site-scoped facts."),
    Field("fortress_name", "string", MECHANICAL, "Display name."),
    Field("written_at", "string", DERIVED, "Real-world ISO date of writing."),
    Field("embark", "object:embark", MECHANICAL, "Fixed embark covariates."),
    Field("design", "object:design", MECHANICAL, "The design features."),
    Field("milestones", "record_list:milestone", MECHANICAL, "Dated events."),
    Field("threat_log", "record_list:threat", MECHANICAL,
          "Threats with event-time covariates, per rule 2."),
    Field("outcome", "object:outcome", MECHANICAL, "How it ended."),
    Field("observations", "record_list:observation", HUMAN,
          "Diagnosticity-tagged evidence links."),
    Field("experiment", "object:experiment", HUMAN,
          "Set only for deliberate trials.", required=False, nullable=True),
    Field("epitaph_ref", "string", HUMAN,
          "Path to the prose epitaph. The ledger row is the data; the epitaph "
          "is the story. They are deliberately separate.",
          required=False, nullable=True),
    Field("notes", "string", AGENT,
          "Free text. Never read by grading; source is AGENT for that reason.",
          required=False, nullable=True),
)


# ---- validation -----------------------------------------------------------


def _type_ok(value, field: Field) -> str | None:
    """Return an error string, or None if the value fits the field."""
    t = field.type
    if t == "string":
        if not isinstance(value, str) or not value:
            return "expected a non-empty string"
    elif t == "integer":
        # bool is an int subclass in Python; an accidental True here would
        # sail through and silently corrupt a stratification.
        if isinstance(value, bool) or not isinstance(value, int):
            return "expected an integer"
    elif t == "boolean":
        if not isinstance(value, bool):
            return "expected a boolean"
    elif t == "vocab":
        if value not in (field.vocab or ()):
            return f"{value!r} is not in the vocabulary for this field"
    elif t == "string_list":
        if not isinstance(value, list) or any(
            not isinstance(v, str) for v in value
        ):
            return "expected a list of strings"
    elif t.startswith("object:") or t.startswith("record_list:"):
        return None  # handled by the caller, which recurses
    else:
        return f"unknown field type {t!r} in the schema itself"
    return None


def _validate_record(fields: tuple[Field, ...], obj, path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(obj, dict):
        return [f"{path}: expected an object"]

    known = {f.name for f in fields}
    for key in obj:
        if key not in known:
            errors.append(f"{path}.{key}: not a field in the schema")

    for field in fields:
        here = f"{path}.{field.name}"
        if field.name not in obj:
            if field.required:
                errors.append(f"{here}: required field is missing")
            continue

        value = obj[field.name]
        if value is None:
            if not field.nullable:
                errors.append(f"{here}: null is not allowed for this field")
            continue

        if field.type.startswith("object:"):
            sub = field.type.split(":", 1)[1]
            errors.extend(_validate_record(RECORD_FIELDS[sub], value, here))
        elif field.type.startswith("record_list:"):
            sub = field.type.split(":", 1)[1]
            if not isinstance(value, list):
                errors.append(f"{here}: expected a list")
                continue
            for i, item in enumerate(value):
                errors.extend(
                    _validate_record(RECORD_FIELDS[sub], item, f"{here}.{i}")
                )
        else:
            problem = _type_ok(value, field)
            if problem:
                errors.append(f"{here}: {problem}")

    return errors


def validate(row) -> list[str]:
    """Validate one ledger row. Returns a list of errors; empty means valid.

    Beyond field types, four cross-field rules are checked here, because each
    encodes a design commitment that a per-field check cannot express.
    """
    errors = _validate_record(FORT_FIELDS, row, "row")
    if errors:
        return errors

    if row["schema_version"] != SCHEMA_VERSION:
        errors.append(
            f"row.schema_version: row is version {row['schema_version']}, "
            f"this code is version {SCHEMA_VERSION}"
        )

    outcome = row["outcome"]
    ended = outcome["status"] not in ("alive", UNRECORDED)

    # Rule 3, enforced: a fort that ended with no contributing factors is
    # exactly the single-cause flattening the schema exists to prevent.
    if ended and not outcome["contributing_factors"]:
        errors.append(
            "row.outcome.contributing_factors: a fort that ended must record "
            "at least one contributing factor"
        )

    ranks = [f["rank"] for f in outcome["contributing_factors"]]
    if sorted(ranks) != list(range(1, len(ranks) + 1)):
        errors.append(
            "row.outcome.contributing_factors: ranks must be 1..n with no "
            f"gaps or ties, got {sorted(ranks)}"
        )

    # duration_years is DERIVED, so it must actually agree with its inputs
    # rather than being asserted independently.
    end_year, duration = outcome["end_year"], outcome["duration_years"]
    if end_year is not None and duration is not None:
        expected = end_year - row["embark"]["start_year"]
        if duration != expected:
            errors.append(
                f"row.outcome.duration_years: {duration} disagrees with "
                f"end_year - start_year ({expected})"
            )

    # The whole point of the experiment block is one variable.
    experiment = row.get("experiment")
    if experiment and "," in experiment["variable"]:
        errors.append(
            "row.experiment.variable: one field only; a comma means this was "
            "not a one-variable-at-a-time trial"
        )

    return errors


def blank_row(fort_id: str, world_id: str, site_id: str, fortress_name: str,
              written_at: str) -> dict:
    """A row with every vocabulary field set to `unrecorded`.

    Deliberately *not* valid: numeric and boolean fields are left absent so
    that `validate` names them. A template that passes validation is a template
    that invites shipping placeholder data, and this ledger is meant to end up
    in a public report.
    """
    def fill(fields: tuple[Field, ...]) -> dict:
        out: dict = {}
        for f in fields:
            if f.type == "vocab":
                out[f.name] = UNRECORDED
            elif f.type == "string_list" or f.type.startswith("record_list:"):
                out[f.name] = []
            elif f.nullable:
                out[f.name] = None
        return out

    return {
        "schema_version": SCHEMA_VERSION,
        "fort_id": fort_id,
        "world_id": world_id,
        "site_id": site_id,
        "fortress_name": fortress_name,
        "written_at": written_at,
        "embark": fill(EMBARK_FIELDS),
        "design": fill(DESIGN_FIELDS),
        "milestones": [],
        "threat_log": [],
        "outcome": fill(OUTCOME_FIELDS),
        "observations": [],
        "experiment": None,
        "epitaph_ref": None,
        "notes": None,
    }
