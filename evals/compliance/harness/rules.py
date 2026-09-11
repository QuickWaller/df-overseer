"""The synthetic doctrine pool: independently verifiable rules, mechanically graded.

Replicates the "Prompt Design at Scale" methodology (arXiv:2607.19257) against
this project's own model and doctrine format, per
`research/2026-08-25-learning-architecture.md` §4/§7 item 1: load synthetic
doctrine at increasing rule counts, measure where compliance degrades. Every
rule here governs the *form* of a free-text response only (wording, structure,
punctuation) so that it can be checked by code against the raw response text,
never by asking a model to grade another model's compliance — that would be
grading exactly the kind of self-assessment the register already treats as
unreliable (`decisions/DECISIONS.md`, 2026-08-25: "All learning grading is
mechanical").

**Nesting, not independent sampling.** `rule_set(n)` returns the first `n`
rules of one fixed shuffled order (`NESTED`), so `rule_set(20)` is always a
strict subset of `rule_set(40)`. This is deliberate: it isolates "what changed
when doctrine grew from N to 2N" to the rules that were actually added, rather
than confounding rule count with which rules happened to be sampled.

**No two rules in the pool may contradict each other.** A pool containing both
"always end with a question mark" and "never use a question mark" would make
perfect compliance impossible regardless of model quality, which would corrupt
every downstream measurement. Categories that are inherently mutually
exclusive (a required prefix, a required suffix, an exact sentence count...)
therefore contribute exactly **one** concrete rule each to the pool, never
several competing variants. `harness/selftest.py` proves the full pool is
jointly satisfiable by constructing one response that passes every rule in the
largest configured set — not just asserting it by design.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, Callable

Check = Callable[[str], bool]


@dataclass(frozen=True)
class Rule:
    id: str
    category: str
    text: str  # shown to the model, verbatim, inside the doctrine block
    param: Any  # category-specific data selftest.py needs to reconstruct a pass/fail example
    check: Check  # mechanical grader: True iff a response OBEYED this rule


def _word(pattern_word: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(pattern_word)}\b", text, re.IGNORECASE) is not None


# Disjoint by construction: hedges/connectives (banned) vs. concrete nouns
# (required) are different parts of speech, so no word needs manual dedup
# against the other list. Neither list overlaps the plain, punctuation-free
# words used by the prefix/suffix/filler machinery in selftest.py.
_BANNED_WORD_BANK = [
    "very", "just", "actually", "clearly", "obviously", "basically", "simply",
    "really", "quite", "perhaps", "maybe", "definitely", "certainly", "totally",
    "literally", "essentially", "fundamentally", "arguably", "admittedly",
    "frankly", "honestly", "ultimately", "ideally", "ironically",
    "interestingly", "surprisingly", "notably", "importantly", "significantly",
    "considerably", "substantially", "remarkably", "undoubtedly",
    "unquestionably", "indeed", "truly", "genuinely", "absolutely",
    "completely", "entirely", "wholly", "utterly", "virtually", "practically",
    "effectively", "largely", "mostly", "primarily", "mainly", "chiefly",
    "particularly", "specifically", "especially", "generally", "typically",
    "usually", "normally", "ordinarily", "occasionally", "frequently",
    "rarely", "seldom", "sometimes", "often", "always", "never", "moreover",
    "furthermore", "additionally", "however", "nevertheless", "nonetheless",
    "regardless", "therefore", "thus", "hence", "consequently",
    "accordingly", "meanwhile", "otherwise", "likewise", "similarly",
    "naturally", "evidently",
]

_REQUIRED_WORD_BANK = [
    "process", "result", "outcome", "method", "approach", "system", "factor",
    "structure", "pattern", "balance", "sequence", "measure", "signal",
    "source", "target", "range", "scope", "trend", "summary", "insight",
    "overview", "framework", "principle", "concept", "element", "component",
    "aspect", "feature", "function", "mechanism", "condition", "criterion",
    "standard", "guideline", "benchmark", "baseline", "threshold", "variable",
    "parameter", "attribute", "property", "quality", "quantity", "instance",
    "category", "context", "purpose", "detail", "example", "practice", "step",
    "level", "point", "value", "model", "stage", "cause", "record", "input",
    "output",
]

assert not set(_BANNED_WORD_BANK) & set(_REQUIRED_WORD_BANK)

# Substring/char groups, never a bare apostrophe (that would entangle this
# category with no_contractions below and make the two non-independent).
_BANNED_CHAR_GROUPS = [
    ("em_dash", ["—"], "an em dash (—)"),
    ("semicolon", [";"], "a semicolon (;)"),
    ("exclamation", ["!"], "an exclamation mark (!)"),
    ("colon", [":"], "a colon (:)"),
    ("ellipsis", ["...", "…"], "an ellipsis (... or …)"),
    ("parentheses", ["(", ")"], "parentheses ( or )"),
    ("quotation_marks", ["\"", "“", "”", "‘", "’"],
     "any quotation marks"),
]

_MIN_WORD_COUNTS = [10, 15, 20, 25, 30]
# The floor here must comfortably exceed len(_REQUIRED_WORD_BANK) plus a few
# tokens of prefix/suffix overhead (60 + ~4), since at high doctrine sizes
# nearly every required-word rule is simultaneously active and mandatory —
# selftest.py's joint-satisfiability check is what caught this the first time
# a floor of 60 was tried and proved unsatisfiable.
_MAX_WORD_COUNTS = [80, 100, 120, 150, 200]

_PREFIX_PHRASE = "response"
_SUFFIX_PHRASE = "end of response"
_SENTENCE_COUNT = 3


def _build_pool() -> list[Rule]:
    pool: list[Rule] = []

    for w in _BANNED_WORD_BANK:
        pool.append(Rule(
            id=f"banned_word_{w}", category="banned_word",
            text=f'Never use the word "{w}" anywhere in your response.',
            param=w, check=lambda t, w=w: not _word(w, t),
        ))

    for w in _REQUIRED_WORD_BANK:
        pool.append(Rule(
            id=f"required_word_{w}", category="required_word",
            text=f'Your response must include the word "{w}" at least once.',
            param=w, check=lambda t, w=w: _word(w, t),
        ))

    for name, chars, human in _BANNED_CHAR_GROUPS:
        pool.append(Rule(
            id=f"banned_char_{name}", category="banned_char",
            text=f"Never use {human} anywhere in your response.",
            param=(name, chars),
            check=lambda t, chars=chars: not any(c in t for c in chars),
        ))

    for n in _MIN_WORD_COUNTS:
        pool.append(Rule(
            id=f"min_word_count_{n}", category="min_word_count",
            text=f"Your response must be at least {n} words long.",
            param=n, check=lambda t, n=n: len(t.split()) >= n,
        ))

    for n in _MAX_WORD_COUNTS:
        pool.append(Rule(
            id=f"max_word_count_{n}", category="max_word_count",
            text=f"Your response must be no more than {n} words long.",
            param=n, check=lambda t, n=n: len(t.split()) <= n,
        ))

    pool.append(Rule(
        id="prefix", category="prefix",
        text=f'Begin your response with the word "{_PREFIX_PHRASE}" as the '
             f"very first word (case-insensitive).",
        param=_PREFIX_PHRASE,
        check=lambda t: t.strip().lower().startswith(_PREFIX_PHRASE),
    ))

    def _suffix_check(t: str) -> bool:
        stripped = t.strip().rstrip(".!?").rstrip()
        return stripped.lower().endswith(_SUFFIX_PHRASE)

    pool.append(Rule(
        id="suffix", category="suffix",
        text=f'End your response with the exact phrase "{_SUFFIX_PHRASE}" '
             f"(case-insensitive; trailing punctuation is ignored).",
        param=_SUFFIX_PHRASE, check=_suffix_check,
    ))

    def _sentence_count_check(t: str) -> bool:
        # Approximate on purpose: counts terminal punctuation runs, not a full
        # sentence parser. Good enough to grade a model that is actually trying;
        # documented here so a report reader knows the ceiling of this check.
        return len(re.findall(r"[.!?]+(?:\s|$)", t.strip() + " ")) == _SENTENCE_COUNT

    pool.append(Rule(
        id="exact_sentence_count", category="exact_sentence_count",
        text=f"Write your entire response as exactly {_SENTENCE_COUNT} "
             f"sentences, no more and no fewer.",
        param=_SENTENCE_COUNT, check=_sentence_count_check,
    ))

    pool.append(Rule(
        id="single_paragraph", category="single_paragraph",
        text="Write your response as a single continuous paragraph, with no "
             "line breaks.",
        param=None, check=lambda t: "\n" not in t.strip(),
    ))

    pool.append(Rule(
        id="all_lowercase", category="all_lowercase",
        text="Write your entire response in lowercase; do not use any "
             "uppercase letters.",
        param=None, check=lambda t: t == t.lower(),
    ))

    pool.append(Rule(
        id="no_contractions", category="no_contractions",
        text="Never use contractions (e.g. don't, it's, can't); always use "
             "the full form (do not, it is, cannot).",
        param=None,
        check=lambda t: re.search(r"\b\w+'(t|re|ll|ve|d|s|m)\b", t, re.IGNORECASE) is None,
    ))

    pool.append(Rule(
        id="no_digits", category="no_digits",
        text="Never include any numeral digits (0-9) anywhere in your "
             "response; spell out any numbers as words.",
        param=None, check=lambda t: not any(c.isdigit() for c in t),
    ))

    pool.append(Rule(
        id="no_first_person", category="no_first_person",
        text="Never use first-person pronouns (I, me, my, mine, myself) "
             "anywhere in your response.",
        param=None,
        check=lambda t: (
            re.search(r"\bI\b", t) is None
            and re.search(r"\b(me|my|mine|myself)\b", t, re.IGNORECASE) is None
        ),
    ))

    pool.append(Rule(
        id="ends_with_question", category="ends_with_question",
        text="End your response with a question mark.",
        param=None, check=lambda t: t.strip().endswith("?"),
    ))

    ids = [r.id for r in pool]
    assert len(ids) == len(set(ids)), "duplicate rule id in the pool"
    return pool


_UNSHUFFLED = _build_pool()

# One fixed shuffle, seeded for reproducibility across runs and across the
# selftest. This is the order rule_set(n) slices — it is what makes nesting
# hold: rule_set(20) is always rule_set(40)'s first 20 elements.
NESTED: list[Rule] = list(_UNSHUFFLED)
random.Random(20260911).shuffle(NESTED)

BY_ID: dict[str, Rule] = {r.id: r for r in NESTED}
MAX_RULES = len(NESTED)

SINGLETON_CATEGORIES = [
    "prefix", "suffix", "exact_sentence_count", "single_paragraph",
    "all_lowercase", "no_contractions", "no_digits", "no_first_person",
    "ends_with_question",
]


def rule_set(n: int) -> list[Rule]:
    if n > MAX_RULES:
        raise ValueError(f"only {MAX_RULES} rules exist in the pool, asked for {n}")
    return NESTED[:n]
