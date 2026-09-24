## (1) What a ghost is likely to do, and how urgent it is

The single fact that decides everything is **which type of ghost** this is. Your DFHack install's own `gui/unit-info-viewer.lua` hard-codes the list (indexed by `unit.ghost_info.type`), so this is **[verified]** against your exact build:

| # | Type | [verified] the game's own description |
|---|---|---|
| 0 | **Murderous ghost** | (no flavour text — it's the killer type) |
| 1 | Sadistic ghost | — |
| 2 | Secretive ghost | — |
| 3 | Energetic poltergeist | — |
| 4 | Angry ghost | — |
| 5 | **Violent ghost** | — |
| 6 | Moaning spirit | "will generally trouble one unfortunate at a time" |
| 7 | Howling spirit | "ceaseless noise is making sleep difficult" |
| 8 | Troublesome poltergeist | — |
| 9 | Restless haunt | "troubling past acquaintances and relatives" |
| 10 | Forlorn haunt | "seeking known locations or drifting around the place of death" |

**What each does, in practice:**
- **Murderous / Sadistic / Violent / Angry (0, 1, 5, 4)** — the dangerous band. Murderous ghosts kill dwarves; sadistic and violent ghosts also attack; angry ghosts are hostile. **[recall]** — your build's strings name them but don't literally spell out the combat behaviour, so treat the *exact* lethality as recall. These are the ones that turn this from a nuisance into an emergency.
- **Secretive (2) and the two poltergeists (3, 8)** — misplace, hide, throw, or steal items. Mischief + bad thoughts, no deaths. **[recall]**
- **Moaning (6), Howling (7), Restless (9), Forlorn (10)** — bad thoughts only: sleep disruption, fright, one dwarf troubled at a time, drifting to old haunts. **[verified]** — these descriptions are your build's own text.

**Persistence:** a ghost stays until it's laid to rest; it does not time out. **[standard practice]**

**Urgency:** If it's in the 0/1/4/5 band, act *now* — dwarves can die. If it's a poltergeist/haunt/moaning type, it's slow stress damage: you have in-game weeks, but don't ignore it, because accumulated bad thoughts snowball into tantrums. Right now "nobody hurt, vitals unchanged" is **not** reassuring by itself — it just means the ghost hasn't picked a target yet. You can't judge urgency until you know the type, which is exactly why the first step below is identification.

## (2) Every way to lay it to rest, ranked for *your* constraints

1. **Memorial slab — engrave one at your existing Stoneworker's Workshop. [top pick]**
   Cost: one stone + a mason labor + build time. Reliability: **highest** — works whether or not the body exists, is reachable, or was destroyed. **[verified]** your build's item text calls a slab "a memorial stone, used to calm a restless ghost when engraved with [a name]"; the workshop job is literally `df.job_type.ConstructSlab`. This is a *direct workshop order* (`q` on the workshop), which **bypasses your broken manager** — the manager only gates `j`-`m` work orders. And you already have the Stoneworker's Workshop built **[verified — live landmarks list]**, so no new construction is needed.

2. **Coffin burial.**
   Cost: build a coffin (stone coffin at that same Stoneworker's Workshop, or wood at a carpenter's — you have **no** carpenter's workshop), then build it as a tomb, assign it, and wait for the body to be hauled. Reliability: **lower** — it only works if the body still exists *and* is reachable, and you don't know either. Your live building list shows **no coffin, tomb, or cemetery exists** **[verified]**, so nothing has ever been buried. This is strictly worse than the slab under your constraints.

3. **DFHack `autoslab`.**
   It auto-queues slab-engraving work orders for ghosts **[verified, from the tool docs]**. But it works *through the manager work-order system*, which you've said is not dispatching — so it would queue an order that never fires. **[recall/inference]** Treat as unreliable here; do the slab manually instead.

4. **Diagnostics (not fixes):** `cursecheck` and `gui/unit-info-viewer` (see below).

**Not real options, and one trap:**
- You **cannot** kill a ghost with military or combat in fort mode — it's non-corporeal. **[recall]**
- The DFHack `ghostly` tool only toggles *an adventurer's* ghost status; it's useless in fort mode. **[verified, from tool docs]**
- Once at rest, do **not** deconstruct its coffin/slab — a re-raised ghost comes back as a *Murderous* ghost. **[prior — v0.34 wiki; flag as old-namespace]**
- The **kea is a red herring for the fix**: it steals small/light items, not a heavy stone boulder or a built slab. **[recall]** It can't block the slab; at most, don't leave small valuables scattered on the surface.

## (3) What I'd need to know before committing, and how to find out

1. **The ghost's type — the one thing that gates everything.**
   Find out: in the DFHack console, run `cursecheck detail` (whole-map scan, no need to actually see the sprite), then `gui/unit-info-viewer` on that unit to read the exact `ghost_type` string. `cursecheck nick` will label the curse type so it's visible in-game.
   ⚠️ **I cannot read this for you from my side** — my toolset doesn't expose the units vector, so this is a step *you* run. It's one command.

2. **Does the body still exist, and where?**
   `gui/unit-info-viewer` will show "is missing." if the game has marked the corpse missing **[verified — that string is in the script]**. If missing/destroyed (magma, fire, bridge, fell off the map), burial is off the table and the slab is the *only* path. This decides between option 1 and option 2.

3. **Do I have a mason + a free stone?**
   The Stoneworker's Workshop exists **[verified]**, but I don't know if any dwarf currently has Masonry enabled, or whether a loose stone boulder is in a stockpile. You've been mining (the shale Throne is right there), so stone is very likely available. Check `u` (unit/labor) and the stone stockpile.

4. **Is the manager the *only* thing broken?**
   The slab job is a direct workshop order and should sidestep the manager — but confirm the workshop actually has a mason assigned and reachable stone before relying on it.

## (4) The single thing I'd do first

Run **`cursecheck detail`** in the DFHack console. It's one command, read-only, no dependencies, and it resolves the urgency question that everything else hangs on. In the same breath — because the fix is identical either way and costs almost nothing — order a slab directly at the Stoneworker's Workshop (`q` → slab engraving; the `sort` plugin adds a "show only citizens who need a slab" filter **[verified]** so you can't miss the gem setter). Engrave it, place it, done.

That order (identify first, slab in parallel) gets you: knowledge of whether you're in a kill-emergency, *and* the correct fix already in motion, with no manager and no new workshop required.

**What I don't know and won't pretend to:** the ghost's type and location (I can't see the units vector); whether the body exists or where; whether a mason labor is currently enabled and a stone is free; and the exact v53 keybindings for the slab menu (I'm giving the mechanic, not the hotkeys). The "murderous/sadistic/violent/angry ghosts actually attack" claim is recall — your build names the types but doesn't spell out the combat behaviour.