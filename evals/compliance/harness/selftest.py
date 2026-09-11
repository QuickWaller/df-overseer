"""Checks on the harness itself. Run before trusting any result it produces.

    python -m evals.compliance.harness.selftest

Mirrors the perception eval's selftest philosophy
(`evals/perception/harness/selftest.py`): every check here recomputes ground
truth independently of the code path it is checking, rather than re-running
the same function and comparing it to itself.
"""

from __future__ import annotations

import sys
from collections import defaultdict

from .formats import FORMATS
from .rules import BY_ID, MAX_RULES, NESTED, SINGLETON_CATEGORIES, Rule, rule_set
from .scenarios import SCENARIOS


def _synthetic_pass_fail(rule: Rule) -> tuple[str, str] | None:
    """A hand-independent (pass_text, fail_text) pair for one rule's category.

    Returns None for categories where a single generic pair cannot be built
    context-free (there are none currently, but this keeps the door open
    without silently skipping a category that needed one).
    """
    if rule.category == "banned_word":
        return ("This reply steers away from it.",
                f"This response uses the word {rule.param} directly.")
    if rule.category == "required_word":
        return (f"This response mentions {rule.param} directly.",
                "This reply steers away from that term.")
    if rule.category == "banned_char":
        _, chars = rule.param
        return ("This response has no forbidden punctuation in it.",
                f"This response has a forbidden mark{chars[0]} right here.")
    if rule.category == "min_word_count":
        return ("word " * rule.param, "short")
    if rule.category == "max_word_count":
        return ("word", "word " * (rule.param + 20))
    if rule.category == "prefix":
        return (f"{rule.param} starts this text.", "Something else starts this text.")
    if rule.category == "suffix":
        return (f"Text ends with {rule.param}.", "Text ends with something else.")
    if rule.category == "exact_sentence_count":
        return ("One. Two. Three.", "Just one sentence.")
    if rule.category == "single_paragraph":
        return ("One line only.", "First line.\nSecond line.")
    if rule.category == "all_lowercase":
        return ("all lowercase here.", "Not All Lowercase Here.")
    if rule.category == "no_contractions":
        return ("Do not use short forms.", "Don't use short forms.")
    if rule.category == "no_digits":
        return ("no numerals here at all.", "there are 3 numerals here.")
    if rule.category == "no_first_person":
        return ("The team finished the task.", "I finished the task myself.")
    if rule.category == "ends_with_question":
        return ("Is this a question?", "This is not a question.")
    return None


def _check_pool(check) -> None:
    ids = [r.id for r in NESTED]
    check(len(ids) == len(set(ids)), "duplicate rule id in the pool")
    check(MAX_RULES >= 160, f"pool has only {MAX_RULES} rules, need >= 160 to match the paper's range")

    by_cat: dict[str, list[Rule]] = defaultdict(list)
    for r in NESTED:
        by_cat[r.category].append(r)

    for cat in SINGLETON_CATEGORIES:
        check(len(by_cat.get(cat, [])) == 1, f"singleton category {cat!r} has {len(by_cat.get(cat, []))} rules, expected 1")

    for r in NESTED:
        pair = _synthetic_pass_fail(r)
        check(pair is not None, f"{r.id}: no synthetic pass/fail example for category {r.category!r}")
        if pair is None:
            continue
        pass_text, fail_text = pair
        check(r.check(pass_text), f"{r.id}: rejects its own synthetic pass example {pass_text!r}")
        check(not r.check(fail_text), f"{r.id}: accepts its own synthetic fail example {fail_text!r}")


def _check_nesting(check) -> None:
    for small, large in zip([10, 20, 40, 80, 120], [20, 40, 80, 120, 160]):
        if large > MAX_RULES:
            continue
        a = [r.id for r in rule_set(small)]
        b = [r.id for r in rule_set(large)]
        check(a == b[: len(a)], f"rule_set({small}) is not a prefix of rule_set({large})")


def _build_compliant_text(rules: list[Rule]) -> str:
    """Construct one response that should pass every rule in `rules`.

    Not a proof by assertion — this is exercised through the actual `.check`
    callables below, so it only demonstrates the pool is jointly satisfiable
    if every check genuinely returns True on the text built here.
    """
    by_cat: dict[str, list[Rule]] = defaultdict(list)
    for r in rules:
        by_cat[r.category].append(r)

    banned_words = {r.param.lower() for r in by_cat.get("banned_word", [])}
    required_words = [r.param for r in by_cat.get("required_word", [])]

    filler_candidates = ["team", "today", "steadily", "together", "onward", "quietly"]
    filler = [w for w in filler_candidates if w.lower() not in banned_words]
    assert filler, "every filler candidate collided with a banned word"

    tokens: list[str] = list(required_words)

    prefix_rules = by_cat.get("prefix", [])
    suffix_rules = by_cat.get("suffix", [])
    if prefix_rules:
        tokens = [prefix_rules[0].param] + tokens
    if suffix_rules:
        tokens = tokens + suffix_rules[0].param.split()

    max_min = max([r.param for r in by_cat.get("min_word_count", [])], default=0)
    min_max = min([r.param for r in by_cat.get("max_word_count", [])], default=10**9)

    i = 0
    while len(tokens) < max_min:
        tokens.append(filler[i % len(filler)])
        i += 1
    assert len(tokens) <= min_max, (
        f"required words + prefix/suffix already need {len(tokens)} words, "
        f"which exceeds the tightest max_word_count ({min_max})"
    )

    n_sentences = by_cat.get("exact_sentence_count", [])
    n = n_sentences[0].param if n_sentences else 1
    k, m = divmod(len(tokens), n)
    chunks, start = [], 0
    for idx in range(n):
        size = k + (1 if idx < m else 0)
        chunks.append(tokens[start:start + size] or ["and"])
        start += size

    ends_with_q = bool(by_cat.get("ends_with_question"))
    sentences = []
    for idx, chunk in enumerate(chunks):
        end = "?" if (ends_with_q and idx == n - 1) else "."
        sentences.append(" ".join(chunk) + end)
    text = " ".join(sentences)

    if by_cat.get("all_lowercase"):
        text = text.lower()
    return text


def _check_joint_satisfiability(check) -> None:
    rules = rule_set(MAX_RULES)
    try:
        text = _build_compliant_text(rules)
    except AssertionError as exc:
        check(False, f"could not even construct a candidate compliant response: {exc}")
        return
    failed = [r.id for r in rules if not r.check(text)]
    check(
        not failed,
        f"the full {MAX_RULES}-rule pool has no jointly satisfiable response "
        f"(constructed text fails: {failed}) — text was: {text!r}",
    )


def _check_formats(check) -> None:
    rules = rule_set(40)
    for name, fn in FORMATS.items():
        a, b = fn(rules), fn(rules)
        check(a == b, f"format {name!r} is not deterministic")
        check(bool(a.strip()), f"format {name!r} produced an empty doctrine block")
        for r in rules:
            check(r.text in a, f"format {name!r} dropped rule {r.id!r}")


class _StubResponse:
    def __init__(self, text: str):
        self.stop_reason = "end_turn"
        self.stop_details = None
        self.content = [type("Block", (), {"type": "text", "text": text})()]
        self.usage = type(
            "Usage", (), {"input_tokens": 1, "output_tokens": 1, "cache_read_input_tokens": 0}
        )()


class _StubClient:
    def __init__(self, text: str):
        self.text = text
        self.last: dict = {}
        self.messages = type("M", (), {"create": self._create})()

    def _create(self, **kwargs):
        self.last = kwargs
        return _StubResponse(self.text)


def _check_request_path(check) -> None:
    from .run import SYSTEM_PREAMBLE, Cell, ask
    from .scenarios import SCENARIOS

    rules = rule_set(5)
    cell = Cell(5, "markdown", SCENARIOS[0], rules, 0)
    compliant = _build_compliant_text(rules)

    client = _StubClient(compliant)
    row = ask(client, "anthropic", "claude-opus-5", "medium", cell, 4000)
    sent = client.last

    check(row.get("perfect") is True, f"a jointly-compliant response graded as non-perfect: {row}")
    check(not row.get("error"), f"unexpected error: {row.get('error')}")
    check(sent.get("model") == "claude-opus-5", "model not passed through")
    system = sent.get("system") or []
    check(
        isinstance(system, list) and len(system) == 2
        and all(isinstance(b, dict) and "cache_control" in b for b in system),
        "system prompt is not two cache-marked blocks",
    )
    if isinstance(system, list) and len(system) == 2:
        check(system[0].get("text") == SYSTEM_PREAMBLE, "stable preamble must be the first block for cache stability")

    bad = ask(_StubClient(""), "anthropic", "claude-opus-5", "medium", cell, 4000)
    check(bool(bad.get("error")) and not bad.get("perfect"), "an empty response was not recorded as an error")

    noncompliant = ask(_StubClient("i think it's very simply this."), "anthropic", "claude-opus-5", "medium", cell, 4000)
    check(not noncompliant.get("perfect"), "an obviously non-compliant response graded as perfect")
    check(noncompliant.get("failed_rule_ids"), "a non-compliant response reported no failed rules")


def run() -> list[str]:
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    _check_pool(check)
    _check_nesting(check)
    _check_joint_satisfiability(check)
    _check_formats(check)
    check(len(SCENARIOS) >= 5, "expected at least five scenarios")
    check(len({s.id for s in SCENARIOS}) == len(SCENARIOS), "duplicate scenario id")

    try:
        _check_request_path(check)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"request path check raised: {type(exc).__name__}: {exc}")

    return failures


def main() -> int:
    failures = run()
    if failures:
        print(f"{len(failures)} SELFTEST FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"selftest OK ({MAX_RULES} rules in the pool)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
