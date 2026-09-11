# df-overseer

Turning Dwarf Fortress from a game you sit down to play into a fortress that
runs, survives, and tells its own story without you.

A language model plays the fort. It is never shown the map.

## Status

**Infrastructure unchanged and still solid; a real fort is founded and
running; and a bounded piece of it has now played itself, twice, end to
end.** The Proxmox provisioning and the DF Classic plus DFHack install are
both scripted here and were verified end to end against a real VM,
`df-colony-01`, rebuilt from scratch on 2026-09-08 after an earlier VM and
template (built 2026-08-27) were deleted on 2026-09-01 in a hypervisor
rebuild. **Uniboslan, "Ragwind,"** is the one fort (a first fort,
Artobcatten, was founded and then unrecoverably lost as a side effect of
founding Uniboslan, `decisions/DECISIONS.md` 2026-09-10); it has survived a
real VM outage since.

Game-side code now exists, and much of it has run for real, not just been
written. A spatial-perception layer (connectivity, landmarks, `get_overview`,
`get_diff_since`, `find_open_area`, `find_chokepoints`, `get_stuck_jobs`,
build order items 2-8 in `docs/PURPOSE.md`) is built and live-verified
against Uniboslan, on its own branch and worktree,
`perception-layer-experiments`. It stays unmerged deliberately, on the
user's own repeated call to keep working with it rather than merge yet, not
because it is unfinished or blocked. On `main`: a labor-management slice
(`get_unit_status`/`set_labor`, with `autolabor` enabled and confirmed
actually assigning jobs) and a second, authenticated personal-control VNC
channel for the user, alongside the existing public view-only feed.

The headline result: **two independently-verified, fully closed,
coordinate-free decision-to-mutation loops**, the first real end-to-end
evidence for the commitment below rather than eval-harness evidence alone.
A bounded, tools-only autonomous-play experiment used `find_open_area` to
pick a ranked, named construction candidate, then a fused resolve-and-act
primitive (`build_open_area`/`build`) turned that pick into a real, verified
fort mutation, a second stockpile, without the raw coordinate ever being
visible to whatever made the decision. The same pattern was repeated for
diggable terrain (`find_diggable_area`/`dig_diggable_area`): a dwarf claimed
a real dig job and all 41 designated tiles were fully dug. Full trail:
`decisions/DECISIONS.md`'s 2026-09-10 and 2026-09-11 entries, `Working.md`'s
current handover.

Claims marked *verified* were checked against a DFHack install, a live API,
or a primary source. Everything in `docs/` and `research/` beyond what is
cited above as verified is still a design artifact or a proposal, and is
labelled as such on purpose.

## The commitment that shapes everything

**The model is never shown a rendered map.** Not ASCII, not a tile grid, not a
screenshot. Every spatial fact is computed in code and asserted to the model in
text: what connects to what, what is reachable, where the chokepoints are.

This is a hard commitment rather than a preference, and it is the reason the
project is interesting. Vision-language models are poor at reading a tile map
and good at reasoning over structured claims, so the work moves to building a
perception layer worth reasoning about. The evidence behind the call is in
[`research/2026-08-25-spatial-perception.md`](research/2026-08-25-spatial-perception.md).

## Three layers

**A toolkit.** Automations that hold a fortress together against the item,
corpse and population accumulation that normally kills long runs. Useful on its
own, played by hand, and the substrate for everything above it.

**A perception and action interface.** The game as structured state and typed
actions, so a model can make the decisions a player would.

**An observation layer.** An ambient display of the fortress going about its
business, and a written chronicle of what it did and why. The chronicle is the
point. A fort that survives a month unattended and cannot say what happened is
only half the result.

[`docs/PURPOSE.md`](docs/PURPOSE.md) is the full design, including the build
order and the open questions.

## Layout

| | |
|---|---|
| [`ROADMAP.md`](ROADMAP.md) | What is next, in Now / Next / Later, plus explicit non-goals |
| [`Working.md`](Working.md) | What is in motion right now, and the traps a fresh session would otherwise hit |
| [`decisions/`](decisions/DECISIONS.md) | Every decision worth remembering, with its date, status and reason |
| [`docs/`](docs/) | Design artifacts: purpose, memory architecture |
| [`research/`](research/) | Dated, cited research specs. Read the relevant one before designing in its area |
| [`scripts/`](scripts/) | Proxmox provisioning and the DF + DFHack install, both driven over the API and SSH |
| [`evals/`](evals/) | Eval harnesses that need no running game: perception (`evals/perception/`) and doctrine-compliance at scale (`evals/compliance/`) |
| [`learning/ledger/`](learning/ledger/) | Structured record of fort outcomes |
| [`learning/predictions/`](learning/predictions/) | Mechanical prediction log: pre-registered decisions checked against ledger state, never against the model's own account |
| [`memory/`](memory/) | Repo context not derivable from the code |

## Running it

You need a Proxmox host, a pool-scoped API token, and an SSH keypair. Copy
[`infra/local.example.env`](infra/local.example.env) to `.env` in the repo root
and fill it in, then:

```
python scripts/provision_vm.py status          # read-only, allocates nothing
python scripts/provision_vm.py fetch-image
python scripts/provision_vm.py build-template
python scripts/provision_vm.py clone
python scripts/install_df.py install
```

`install_df.py` takes `--dry-run`, which prints the exact script it would run
inside the guest and connects to nothing, so it can be reviewed before it is
trusted. See [`infra/README.md`](infra/README.md) for the access model.

**This repo is public and holds no infrastructure specifics.** Hosts,
addresses, tokens and IDs live in gitignored `infra/local.*` files with
committed `.example` counterparts. Committed files use placeholders.

## How this repo is managed

Written with Claude Code against a structured memory system, following the
pattern published as
[`claude-code-managed-repo-template`](https://github.com/QuickWaller/claude-code-managed-repo-template).
[`CLAUDE.md`](CLAUDE.md) is the entry point and the working agreement.

Two conventions do most of the work. **Research before designing from
scratch:** state the problem in domain-neutral terms, find which other fields
already own it, and read those first. **Verify the verification:** before
reporting an all-clear, confirm the check could actually have gone red. A
search that finds nothing and a search that cannot see produce the same output,
and this repo has caught several of the latter.

## License

MIT. See [`LICENSE`](LICENSE).
