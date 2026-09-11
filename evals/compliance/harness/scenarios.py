"""Task prompts the model answers while holding the doctrine.

Deliberately generic and outside the Dwarf Fortress domain: the point of this
harness is raw instruction-following capacity against rule count, not domain
knowledge, and a DF-flavoured task would confound the two (a rule like
"never use the word 'often'" is harder to hold onto while also reasoning about
siege mechanics than while explaining the water cycle). Keep prompts open-ended
enough that every rule in the pool is satisfiable regardless of which task is
asked — none of them, for instance, demands a number, an exclamation, or a
first-person account.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    id: str
    prompt: str


SCENARIOS: list[Scenario] = [
    Scenario("hash_table", "Explain how a hash table works, for someone who has never programmed before."),
    Scenario("interview_prep", "Give advice on how to prepare for a technical job interview."),
    Scenario("sleep", "Summarize why sleep matters for health."),
    Scenario("water_cycle", "Describe the water cycle."),
    Scenario("focus_habits", "Recommend habits for staying focused while working."),
    Scenario("weather_climate", "Explain the difference between weather and climate."),
    Scenario("bicycle_gears", "Describe how a bicycle's gears change how hard it is to pedal."),
    Scenario("compound_interest", "Explain how compound interest works."),
    Scenario("good_password", "Explain what makes a password strong."),
    Scenario("exercise_mind", "Explain why regular exercise benefits mental health."),
]

BY_ID = {s.id: s for s in SCENARIOS}
