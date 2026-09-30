# Handoff: design the stream page (chat, projects, operator view) and its data

Date: 2026-10-01. **Researcher, Opus, design only. You have real freedom
here** (the user's words: "give it a bit of freedom"): the mockup and the
decisions below are the brief, not a spec. Improve on them, argue with them,
propose what we have not thought of; mark clearly what departs from what the
user agreed so they can choose.

## What the user wants

A page beside the live video where people can watch the fort run itself:
what the agents are saying to each other, what projects are under way and why,
and how the season goal is going. The user has seen a clickable mockup and
likes it: `research/2026-10-01-stream-page-mockup.dc.html`
(sample data only; read it, its `renderVals()` holds the sample story). Its
shape: live view left; status strip and season goal under it; right column
with Chat (every queue record as a message from its role, role filters, jump
to latest) and Projects (outline under the season goal, status, progress,
hold reasons, workforce line); a project drawer with steps, the live DF job
under the current step, and that project's own conversation; a Public /
Operator switch where operator shows raw detail.

## Decisions already made (register, 2026-09-14, 2026-09-25, 2026-10-01 rows)

- Public fields are an **allowlist**, never redaction (`dfqueue/render.py`
  `public_view`, `docs/AGENT-ARCHITECTURE.md` §8); kill switch; no delay.
- **Operator view** shows everything, behind the user's existing Cloudflare
  Access login; it is how "everything is visible to the user" is met, and is
  part of v1.
- One conversation; per-project chat is a filtered view. Every message says
  what it is about (a chip: project, step, season goal, or fort-wide) and
  what it replies to. Some records lack that link today (asks, user
  messages, goals): design the **"about" and "reply to" references** the
  queue needs.
- Projects need a **public projection** (title, status, progress, hold
  reason) that the allowlist does not have yet.
- The user's Telegram messages to the Overseer, and its replies, show in the
  chat as the user's own speaker. Telegram is not a mirror.
- Coming later, the page must take without redesign: season goals and their
  review, the executor, commissions, the Overseer's changes to its own
  wake-ups, escalations and system alarms.
- The live view already exists and works (`research/2026-09-09-reverse-vnc-relay.md`,
  `ROADMAP.md` "Live human viewing"): outbound-only from VM 103 through a
  relay and a Cloudflare Tunnel. Nothing may open an inbound port on VM 103.

## Questions to answer (and any better ones you find)

1. The data: exactly which records and events feed the page (queue records,
   the conductor's wakes and holds, `dfmcp` call log for operator detail,
   fort vitals), the public and operator projections, and the schema
   additions ("about", "reply to", project public fields, conductor events
   as records or not).
2. The pipeline: a publisher on VM 103 (or VM 106, where the conductor is),
   outbound only; push versus poll; snapshot plus incremental; how a new
   viewer loads history; ordering, gaps, restarts, the kill switch; cost at a
   year of history.
3. Where the page lives (the user's portfolio site, which already links the
   viewer, versus beside the viewer on the relay) and how the operator view
   is gated; what the static-site constraint allows.
4. The UI: what the mockup gets right or wrong; threading and reply lines;
   how a project's life (draft, amendments, holds, result) reads; mobile; the
   season archive as a chronicle; what a first-time viewer understands in ten
   seconds.
5. Safety: nothing private or infrastructural reaches the public projection
   (no hostnames, addresses, tokens, file paths, raw tool arguments);
   rationale text is model-written, so what if it contains something it
   should not.
6. A build plan in small slices, smallest valuable first, each marked with
   what it needs from the user.

## Read first

`docs/PURPOSE.md`, `docs/AGENT-ARCHITECTURE.md` (§4, §8), `dfqueue/schema.py`,
`dfqueue/render.py`, `dfqueue/store.py` (project status), `conductor/`
(cycle, triage, status), `research/2026-09-08-live-viewing.md`,
`research/2026-09-09-reverse-vnc-relay.md`, `ROADMAP.md` (the 2026-09-25
"make the tools and agents visible" item), the register's 2026-10-01 rows.

## Deliver

`research/2026-10-01-stream-page-design.md`: short answer up front,
verified versus proposed marked, departures from the brief called out, the
slice plan. Fill in this handoff's Result (about 250 words plus the
decisions the user must make).

## Rules

- Design only: no code, no live access, no changes outside the research
  document and this handoff.
- First step `git merge --ff-only main`; commit the plan early, then after
  each section (agents here get cancelled mid-run).
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- This repo is public: never write a hostname, address, subnet or token.
  Name hosts by their repo IDs (VM 103, VM 106, the relay).
- Never design anything that shows a model a rendered map (the video is for
  humans only).
- No em dashes in prose. No attribution lines in any commit.
- Stop and report on any permission refusal.

## Touched surfaces

`research/2026-10-01-stream-page-design.md` and this handoff only.

## Result

(fill in)
