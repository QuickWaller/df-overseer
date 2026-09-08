# df-overseer

Turning Dwarf Fortress from a game you sit down to play into a fortress that
runs, survives, and tells its own story without you.

A language model plays the fort. It is never shown the map.

## Status

**Design, plus infrastructure that is scripted and proven, but not currently
running.** The Proxmox provisioning and the DF Classic plus DFHack install are
both scripted here and were verified end to end against a real VM. That VM and
its template were deleted on 2026-09-01 when the hypervisor underneath them was
rebuilt, so the honest claim today is that the whole stack is reconstitutible
from this repo, not that it is up.

No game-side code exists yet: no perception layer, no agent, no toolkit.
Everything in `docs/` and `research/` is a design artifact. Claims marked
*verified* were checked against a DFHack install, a live API, or a primary
source. The rest are proposals, and are labelled as such on purpose.

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
| [`evals/`](evals/) | The perception eval harness, which needs no running game |
| [`ledger/`](ledger/) | Structured record of fort outcomes |
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
