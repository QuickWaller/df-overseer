# The stream page: chat, projects, operator view, and the data behind them

Date: 2026-10-01. Researcher (Opus), design only, from
`handoffs/2026-10-01-stream-page-design.md`. Nothing here is built. Every
claim about existing code is marked **verified** (read in this repo at
`9fa7fde`) or **proposed**; departures from what the user agreed are marked
**DEPARTURE** so they can be accepted or struck one by one.

## Plan (committed first, in case this run is cancelled)

1. Short answer.
2. What exists today (verified): records, links, stamps, the conductor's
   events, the call log, vitals, the relay, the portfolio site.
3. Q1, the data: sources, the public and operator projections, the schema
   additions ("about", "reply to", project public fields, conductor events).
4. Q2, the pipeline: publisher, push or poll, snapshot plus incremental,
   history, ordering, restarts, kill switch, cost at a year.
5. Q3, where the page lives and how the operator view is gated.
6. Q4, the UI: the mockup critiqued, threading, a project's life, mobile,
   the season archive, the ten-second test, ambient mode.
7. Q5, safety.
8. Q6, the slice plan.
9. Departures from the brief, collected.
10. Decisions for the user.
11. What could not be verified.
