# Handoff: conventions for running n8n at scale (naming, tagging, layout)

Date: 2026-09-25. **Researcher. No VM, no install on any project machine.**

Read `research/2026-09-25-n8n-fit.md` and `research/2026-09-25-n8n-testing-vc-nodes.md`
first. The user wants to stand up an n8n instance for df-overseer, starting with
the wiki refresh and seeding workflows (`wikimirror/`), and to grow it later
(possibly consultant tool workflows behind per-role MCP triggers). Before
building, settle the conventions so the first workflows do not need renaming.

## Questions

1. **Tagging.** How do experienced n8n teams use workflow tags at scale? What
   dimensions are worth tagging (owning role, component such as `wikimirror`,
   environment, read-only vs mutating, trigger kind, lifecycle)? Tag limits,
   uniqueness rules and the import tag-collision crash already noted in the
   research: how to avoid them, and how tags survive export to git.
2. **Naming.** Workflow, node and credential naming conventions that scale
   past a few dozen workflows; naming for sub-workflows used as tools.
3. **Layout and reuse.** Folders/projects, one-workflow-per-tool vs shared
   sub-workflows, error-workflow conventions, how to keep control flow in
   nodes (user rule) while staying reviewable in git.
4. **Audit and observability.** How to make every run attributable (role,
   component, correlation id) and queryable, given the repo's design
   requirement that agent messages carry sender, recipient, type and a
   one-line rationale. Execution-data retention settings worth setting.
5. **Environments and secrets.** Dev vs live separation, credential
   handling for a public repo (nothing specific committed).

## Method

Primary sources first (n8n docs, source at the stable tag, official template
and community conventions), cross-checked against how mature teams describe
their setups. Mark each recommendation as documented, observed or
opinion. Follow the repo's "research before designing" rule: name the
domain-neutral problem (naming and taxonomy for a workflow estate) and see
what adjacent fields (CI pipelines, Airflow/Prefect DAG naming, IaC module
conventions) already settled.

## Produce

`research/2026-09-25-n8n-conventions.md`: a short recommended convention set
(a table the user can accept or edit), the reasoning behind each row, and a
"could not verify" section. Keep it decision-ready: the user has little
bandwidth for design right now, so give one recommended default per question.

## Rules

- `git merge --ff-only main` first; this brief is committed on main.
- You own only that research file and this doc's Result section. Do not edit
  `Working.md`, `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`.
- Do not read the user's other n8n project. Public repo: no infrastructure
  specifics, no other-project or company names.
- No em dashes in prose. **No attribution lines in any commit message.**
- Commit after each milestone. Stop and report on any permission refusal.

## Result

Cancelled 2026-09-25 before any output. The user chose to leave the wiki mirror stale for now and work on something else. Not started; safe to re-dispatch unchanged.
