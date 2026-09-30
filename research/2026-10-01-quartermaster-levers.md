# Quartermaster levers: manager orders, labor, priority, from DFHack source

Date: 2026-10-01. Researcher (Sonnet), read-only: no code, no live access.
Brief: `handoffs/2026-10-01-quartermaster-levers-research.md`.

Sources for this document are DFHack tag `53.16-r1` on GitHub (raw source,
fetched this session), `df-structures` (the structures submodule DFHack
pins for that tag), and the DF wiki. Every claim below is marked
**verified-from-source (file:line)** or **unverified**. Where the wiki and
source disagree, the source wins and the disagreement is named.

## Plan for this document

1. Manager orders: `workorder.lua`'s create path, `manager_order` struct and
   `item_conditions`, order sequence, validated/active states. Propose
   `orders.create`'s extended, generic argument shape.
2. Labor in v50: autolabor plugin status, `labormanager`, v50 work details,
   how per-labor min/max are set. Propose `labor.quota`'s shape.
3. Priority: designation priority 1-7 on tile occupancy, quickfort priority
   syntax, DFHack `prioritize`'s actual mechanism (do_now, job type scope,
   persistence).
4. Per lever: armok status, and the live test that would confirm it.

Committing this plan now, then after each question lands.

## 1. Manager orders

(pending)

## 2. Labor in v50

(pending)

## 3. Priority

(pending)

## 4. Armok status and live test plan

(pending)

## Not verified

(pending)
