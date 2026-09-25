# Handoff: read-only vitals check of Uniboslan

Date: 2026-09-25. **Executor, Sonnet. READ-ONLY on the live fort. No files written except this doc's Result.**

Goal: report the fort's true current state. Find how to reach it from
`memory/`, `docs/RUNBOOK-*`, `CLAUDE.md` and `Working.md` (dfmcp tools such as
overview/stocks/landmarks, or the documented SSH route to VM 103). Read secrets
only by the single key you need, never the whole file.

## Read every vital sign, not just one
Paused or running state, population (alive/dead, any new deaths since the last
known 22 alive / 1 dead), hunger and thirst, food and drink stock, seeds,
stuck jobs, tripwire/vitals tools if available, and anything alarming. State
what you checked and how, and what you could NOT check.

## Hard limits
Do not unpause, save, reload, place, dig, order or change anything in the game.
Do not restart or modify any service or VM. If the only way in is a write,
stop and report. Do not run the conductor.

## Rules
- Report in under 250 words: verdict, the numbers, anything that changed
  versus `CLAUDE.md`/`Working.md`, and any doc/state disagreement.
- Do NOT write `Working.md`, `decisions/`, `memory/`. Commit nothing.
- Stop and report on any permission refusal; do not route around it via
  another agent.

## Result

(pending)
