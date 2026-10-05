# Procedures, turn briefings and bounded turns for a woken LLM worker

Date: 2026-10-05 (section 7, DeepSeek, added after the brief was widened)
Scope: literature and practice review plus a read of this repo's own live evidence. Nothing here was built or tested; recommendations are proposals.
Status: research spec. Confidence is flagged per claim: **[H]** read directly in a primary or official source this session, or measured from repo files; **[M]** from a reputable secondary summary or a single source; **[L]** inferred, or from a source of doubtful quality.

Read first for context: `research/2026-09-12-multi-agent-architecture-prior-art.md` (not repeated here: single decider with advisors, ICS span of control, mission command in one paragraph, MAST failure taxonomy, EMS standing orders). Live evidence: `evals/live/2026-10-05-pause-safety/README.md` and `runs-public.json`.

## 0. The problem, domain-neutral

A delegated worker, woken periodically to act on a shared world, shows three faults:

1. It does not reliably follow a written procedure it demonstrably knows.
2. It spends most of a turn re-deriving facts and re-stating its inputs, and drifts into a neighbour's work.
3. It notices a problem outside its brief and defers it with no owner.

Fields that already own this: human factors and safety engineering (forcing functions, poka-yoke, checklists), clinical and process-industry handover, military orders doctrine, incident and alarm management, and workflow engines. All of them were designed for human workers. The LLM literature is thinner and younger, and much of it is vendor guidance rather than controlled study. Where that matters it is said.

## 1. Answer up front

**A.** Enforce by the server only the things the server can observe and that corrupt shared state or are irreversible; make the wrong path impossible rather than forbidden where you can (poka-yoke beats interlock beats warning). Use required output shapes where a downstream consumer needs a fixed form. Keep prose guidance for judgment, priority and style, and give its reason. A written rule that the server silently contradicts by accepting the violating call is not a rule; the live case is exactly that. A decision rule is in section 3.

**B.** Brief with a short, fixed-order, mostly-structured block: state of the world in numbers, why you were woken, what is already decided and by whom, what is yours to do, what is explicitly not yours, then the open items with owners. Put the facts first and the ask last, keep it bounded, and link to detail rather than inlining it. The strongest measured result in the handoff literature (I-PASS, section 4) is for a structured bundle that includes a receiver read-back, not for the mnemonic alone. The repo's `conductor/briefing.py` already does the facts half well; the gap is the pending proposals' content, the lane statement and the open-items ledger.

**C.** Bound a turn by explicit scope plus a measured budget, announced to the worker, plus a place to put out-of-lane work that is cheaper than doing it. The evidence for LLM step budgets is real but narrow (one 2025 study, web-search agents). Mission command supplies the intent-not-method shape; separation of duties supplies the lane.

**D.** Incident and alarm practice converges on one rule: an item that cannot name an owner and a next action is not an alert, it is noise. For this repo the finding is mechanical: the Overseer's allowlist has no tool whose effect is "hand this noticed problem to someone", so deferral is the only available move.

## 2. What the live evidence actually shows (repo, confirmed)

Read from `evals/live/2026-10-05-pause-safety/runs-public.json` (run-0004, Overseer, `queue_pending`, 645 s) and the code. **[H]** unless noted.

1. **The project step was skipped despite a loud charter rule.** The pre-fix charter (`git show ede52d4^:agents/overseer/role.md`) said "Every accepted proposal gets a project before anything is executed ... A one-action job is a one-step project, never skipped." The rule sat inside one dense bullet. The surviving reasoning says: "should I record via queue.project ... or just queue.executed?", "Since I didn't create a project for the bedroom ruling, I'll just record a plain executed entry", then invents an exception: "the Overseer creates a project (queue.project) for accepted rulings that need multi-step plans, OR just records execution for simple ones", and "I could create a project. But honestly, I've already done the dig work, so I'll just record it." It had earlier "recorded execution directly" for the brew. So: the worker knew the rule, reconstructed an exception, and nothing in the system corrected it.
2. **The server contradicted the charter by accepting the call.** Before `171e7ac` the queue accepted `queue.executed` for an accepted ruling with no project (the handoff states the live queue had zero project records ever). Each accepted-without-project call was positive feedback that the step was optional. **[M]**: this is inference about the mechanism; the transcript shows the worker's belief, not why it formed it. It is consistent with the Ontario checklist result (section 3.1): a mandated step with no consequence for skipping it.
3. **Self-recognised drift did not stop the drift.** At about char 6,900 of the surviving 12,025 the worker writes "I think I'm overreaching by trying to fully execute the architect's room-siting proposal. Let me reconsider my role." It then went on to apply two more bedroom digs. Recognition without a stop mechanism. The README counts six previews and two applies. Note the transcript is capped and the middle is cut (`THINKING_MAX_CHARS = 12000`, `conductor/runner.py`), so this is a lower bound on what happened.
4. **Re-derivation is visible.** The worker's opening is a three-line restatement of the three proposals, then a plan to "check the current drink stock", "check the manager orders", "check gotcha-0002" (lookups the facts block in `briefing.py` now covers for stock and orders). In the surviving text the three proposal ids are mentioned 14 times and "Let me" 26 times, "Actually" 12 times (my count; repeated restating, consistent with the README's "about four times"). The briefing at that time carried queue ids only (`briefing["queue"]["ids"]`), not proposal content, so the worker had to read and then restate each proposal.
5. **The deferral is real and ownerless.** The report ends with "Noted for next cycle" and "worth a look next wake" about two suspended constructions that are "the root cause of zero finished beds". No Overseer tool turns that into an owned item (`agents/overseer/tools.yaml` queue tools: `rule`, `project`, `project_status`, `pending`, `executed`, `escalate`, `ask`, `amend`, `abandon`; no propose, no note). The stuck-job wake targets the Quartermaster only (`conductor/policy.yaml`, `stuck_job: wakes: [quartermaster]`), so the Overseer saw the digest but is not the wake's owner. Whether the Quartermaster acted on the Bed is unknown (README).
6. **Model caveat.** `agents/overseer/model.yaml` runs the Overseer on a DeepSeek model (user's call, 2026-10-01), with a Claude fallback. Anthropic's published prompting guidance below is written for Claude; its direction is plausible for any instruction-tuned model but is **not** verified on this model. **[M]**
7. **Turn length vs cap.** `duration_s` 645 against a 600 s default role cap (`conductor/cycle.py role_timeout_seconds`, `conductor/runner.py`, 60 s outer grace). The report reads complete, so it probably finished rather than being killed, but I could not tell from the files whether the inner deadline was involved.

## 3. Question A: enforce, structure, or guide

### 3.1 What the human-factors literature says

- **Forcing functions (Norman).** Interlock (X must happen before Y), lock-in (cannot terminate before finishing), lock-out (cannot enter a hazardous state). Shingo's poka-yoke splits into **control** (the process cannot continue until fixed) and **warning** (it alerts and relies on the operator). Source: summaries of *The Design of Everyday Things* and Shingo, e.g. https://architectures.danlockton.co.uk/everyday-things-persuasive-technology/ and https://en.wikipedia.org/wiki/Poka-yoke. **[M]**, secondary sources, but the taxonomy is standard.
  Mapping: "project before executed" is an interlock. A charter paragraph is, in Shingo's terms, at best a warning.
- **Checklists work, but the evidence is split.** Haynes et al. 2009 (WHO surgical checklist, eight hospitals): 30-day mortality 1.5% to 0.8%, complications 11% to 7%. Urbach et al. 2014 (Ontario, mandated across 101 hospitals): death 0.71% to 0.65%, complications 3.86% to 3.82%, neither significant. Commentary attributes the gap to compliance and buy-in (UK observational compliance 55% pre-op and 9% post-op; a Dutch study full compliance in 39% of operations). Sources: https://mdedge.com/content/surgical-checklists-failed-improve-outcomes ; https://www.longwoods.com/content/23781. **[M]** (reported via news and secondary summaries, not the NEJM text; the compliance explanation is commentary, not a proven cause). Lesson for us: **a mandated step that is only mandated, with no one or nothing verifying it happened, converts to box-ticking or silence.** That is the Overseer case.
- **Checklist types.** Gawande's popularisation of READ-DO (do each step as read) versus DO-CONFIRM (act from memory, then verify) comes from aviation, and Boorman's point that checklists written in offices fail in cockpits. https://athena-newsletter.beehiiv.com/p/atul-gawande-s-surgeon-checklist **[M]** (secondary). Degani and Wiener 1993, "Human factors of flight-deck checklists: the normal checklist" (NASA CR 177549), ties misuse to design and to production pressure and culture: https://ntrs.nasa.gov/citations/19920000775 **[M]**, abstract only, full paper not read. Lesson: a checklist is for a small number of critical items, kept short, designed with the people who use it, and it needs a verification point (the confirm).
- **Alarm management (EEMUA 191 / ISA 18.2).** Every alarm needs a defined operator response, time to respond, consequence and corrective action, or it should not exist. https://www.exida.com/Alarm-Management/Detail/Alarm-Rationalization **[M]**. This is the closest human-factors cousin of "enforce only what has a defined response".

### 3.2 What workflow and agent practice says

- **Workflows versus agents (Anthropic, "Building effective agents").** "Workflows are systems where LLMs and tools are orchestrated through predefined code paths"; agents "dynamically direct their own processes and tool usage". Prompt chaining allows "programmatic checks (see 'gate' ...) on any intermediate steps". "Stopping conditions (such as a maximum number of iterations)". "Poka-yoke your tools. Change the arguments so that it is harder to make mistakes." https://www.anthropic.com/engineering/building-effective-agents **[H]**.
- **Tool design.** Error messages should "clearly communicate specific and actionable improvements, rather than opaque error codes"; consolidate frequently chained multi-step operations into one tool; parameter names unambiguous. https://www.anthropic.com/engineering/writing-tools-for-agents **[H]**. Implication: a refusal is itself a prompt; its text is the guidance that is read at the exact decision moment, which is when the charter is weakest.
- **Deterministic control versus relying on the model.** Claude Code's hooks documentation states the design principle outright: hooks "give you deterministic control: certain actions always happen rather than relying on the LLM to choose to run them", and separately offers model-judged hooks "for decisions that require judgment rather than deterministic rules". https://code.claude.com/docs/en/hooks-guide **[H]**. This is the same split as our enforce-versus-guide question, from a vendor that ships both.
- **MetaGPT SOPs.** Encodes standard operating procedures into prompt sequences with an assembly-line division of labour and verification of intermediate results, to counter "cascading hallucinations caused by naively chaining LLMs". https://arxiv.org/abs/2308.00352 **[H]** for the abstract claim; **I did not read the paper's ablation**, so I cannot say how much of the benefit came from the SOP versus the structured intermediate outputs. Note MetaGPT's SOPs are enforced by the pipeline (each role consumes the previous role's structured document), not left to a role to remember.
- **Policy-following is measurably unreliable.** tau-bench (retail and airline customer-service agents with tool APIs and a policy document) reports that GPT-4o succeeds on well under half of tasks and reliability collapses with repetition, pass^8 below 25% in retail. https://arxiv.org/abs/2406.12045 **[M]** (via search summary of the abstract). Anthropic's "think" tool post reports airline pass^1 0.370 to 0.570 with a think tool plus an optimised prompt, retail 0.783 to 0.812 with the tool alone, and says the tool helps for sequential, policy-heavy tasks and not for single calls or tasks with few constraints. https://www.anthropic.com/engineering/claude-think-tool **[H]**. Lesson: prompting a policy yields a probability of compliance, not a guarantee, and even the best-case gains reported are partial. A procedure that must hold every time cannot rely on it.
- **Instruction density.** IFScale (500 keyword-inclusion instructions in a report-writing task, 20 models): best frontier models reach 68% at the maximum density, with three decay shapes (threshold, linear, exponential) and a bias toward earlier instructions. https://arxiv.org/abs/2507.11538 **[M]** (abstract-level). It is a synthetic keyword task, so the 68% is not a prediction for our charters; the transferable claim is only that adherence falls as the number of simultaneous instructions rises. Our Overseer charter is 129 lines and the allowlist 783 lines. **[L]** for any quantitative inference to our case.
- **Prompt emphasis can backfire.** Anthropic's current guidance says recent Claude models "may now overtrigger" on aggressive language and to replace "CRITICAL: You MUST use this tool when..." with plain wording, and that giving "context or motivation behind your instructions" helps. https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices **[H]** for the quoted sentences; Claude-specific, see 2.6. Taken with the live evidence (a bold "never skipped" did not hold), shouting is not the lever.
- **Context position.** "Lost in the middle": performance is highest when relevant information is at the beginning or end of context and degrades in the middle. https://arxiv.org/abs/2307.03172 **[H]** (abstract). Anthropic reports "queries at the end can improve response quality by up to 30 percent in tests" for long multi-document inputs (same best-practices page, **[H]** for the sentence, internal tests so **[M]** on the number). A required step buried in the middle of a long bullet in a long charter is in the weakest position.

### 3.3 A decision rule for each new rule

Apply in order; stop at the first yes.

1. **Irreversible, outward-facing or safety-relevant?** (unpause, delete, anything widening access, anything a human cannot undo.) Hard refusal, plus an alert path. Do not rely on any prose. This matches the repo's existing "a charter rule is not a boundary" stance (`docs/AGENT-ARCHITECTURE.md` principle 8).
2. **Can the server see compliance from data it already holds, and is a false refusal cheap?** Cheap means the refusal text can say exactly what to do next and the worker can then comply in one call. If yes, **refuse** (interlock). Write the refusal as the instruction ("call `queue.project` with `from_ruling` first, one step per action, then call `queue.executed` naming `step_id`").
3. **Is the correct sequence always the same?** Then prefer to **remove the choice**: collapse the steps into one tool or have the server derive the step (poka-yoke control). Trade-off for the project case: auto-creating a default project on `queue.executed` would guarantee a record but would produce low-quality display fields (`public_title`, `public_rationale`, step labels, `urgency`); the refusal keeps the author in the loop. Choose by whether a mediocre auto-record is acceptable.
4. **Does a downstream consumer need a fixed shape?** (the Board draws the job graph; the grader needs a prediction window.) **Required output shape**, validated at write time, rejected with a precise reason. The existing proposal validation is this.
5. **Does the server not see compliance (a judgment, a priority, a style, "do not re-derive")?** **Written guidance**, short, with its reason, in the briefing or the charter's top lines, not the middle. Add a **detector** (log the violation, show it in the eval/run record) so the guidance is measured, not assumed.
6. **Promotion ladder.** Any guidance rule whose violation the log can detect and which is violated twice in real runs is promoted to step 2 or 4. Any hard rule that produces refusal loops (the worker retries the same refused call, or satisfies the check with a hollow record) is demoted to a shape check with a content check, or redesigned. This is the EEMUA idea applied to rules: a rule must earn its place by having a defined response, and be pruned if the response is rote.

Two cautions, both from the evidence: (a) **a gate can be satisfied emptily** (a one-step project with a blank rationale satisfies "has a project" and defeats its purpose; the Ontario checklists were "completed" and changed nothing). A gate needs a minimal content check on the things its consumer actually reads. (b) **Every added hard rule adds a refusal to a model that reads refusals as prompts**; keep the set small enough that each refusal message is distinctive.

### 3.4 Applied to the Overseer's current rules (my classification, for the orchestrator to accept or change)

| Rule | Class | Why |
|---|---|---|
| Project before `queue.executed` | Server refusal (done, `171e7ac`) plus content check on display fields | Step 2 and 4 of the rule; consumer is the Board |
| `step_id` required once a project has steps | Server refusal (done) | Server-visible |
| Do not resume the fort | Server refusal (already) | Step 1 |
| `queue.escalate` is the only escalation | Server-observed (already, conductor reads tool calls) | Step 2 |
| Do not re-derive an advisor's findings; arbitrate | Guidance plus briefing content (section 4) plus a detector | Judgment; not server-visible, but the briefing can remove the need |
| Stay out of the Architect's siting | Allowlist (structural) plus a detector | See 5.2: this is where the allowlist, not the charter, is the boundary |
| WIP limit | Guidance with a number, plus a server count of open projects as a briefing fact | Number is observable, enforcement judgment-laden |
| Public display fields set | Required shape | Step 4 |

## 4. Question B: briefing at the start of a turn

### 4.1 Handoff literature

- **I-PASS.** Mnemonic: illness severity, patient summary, action list, situation awareness and contingency, synthesis by receiver. Starmer et al., NEJM 2014, nine paediatric residency programs, before-after: medical errors 24.5 to 18.8 per 100 admissions (23% relative), preventable adverse events 4.7 to 3.3 per 100 (30% relative), no adverse effect on workflow. https://psnet.ahrq.gov/issue/changes-medical-errors-after-implementation-handoff-program ; https://www.massdevice.com/handoff-tool-cuts-harmful-medical-errors-30-percent/ **[M]** (AHRQ PSNet and trade press, not the NEJM text). **Caveats that matter:** not randomised; the intervention was a bundle (mnemonic, training, faculty development, observation, sustainability), so the effect cannot be attributed to the format. One summary quotes the 23% as the preventable adverse event figure and another as medical errors; the rates above are from the more detailed summary, and the discrepancy was not resolved against the primary text.
  Transferable parts: a **severity flag first**; an **action list with owners**; **contingency** ("if X, then Y"); and **synthesis by receiver**, i.e. the receiver restates and the sender corrects. The LLM analogue of receiver synthesis is cheap: require the worker's first output to be a short restatement, then have a code check compare it with the briefing; or at least make the first tool call an acknowledgement. I have **no evidence** that this helps an LLM; it is an analogy. **[L]**
- **SBAR** (situation, background, assessment, recommendation). A systematic review (BMJ Open 2018, https://bmjopen.bmj.com/content/8/8/e022202) found moderate evidence of safety gains, with 8 of 26 measured outcomes significantly improved, others improved without tests, 6 unchanged, and "a lack of high-quality research". **[M]**. Treat SBAR as a plausible default, not a proven one. It is designed for a sender who has an assessment and wants an action; our briefing sender is code, so "assessment" and "recommendation" are things only advisors produce.
- **Shift handover in high-hazard industry.** HSE guidance: handover has three parts, preparation by the outgoing person, a two-way exchange both verbal and written, and a cross-check by the incoming person as they "assume responsibility"; content should be based on "an analysis of the information needs of incoming staff"; poor handover figures in Piper Alpha, Texas City and Buncefield. https://www.hse.gov.uk/humanfactors/topics/shift-handover.htm ; https://www.energyinst.org/technical/publications/topics/human-and-organisational-factors/human-factors-briefing-note-no.-10-communications **[H]** for the HSE page, **[M]** for the accident attributions (stated by the Energy Institute note, not independently checked). Lesson: define the receiver's **information needs** explicitly and audit handovers. We can audit mechanically: log which briefing fields the worker re-fetched by tool call.
- **Military orders.** Mission orders state purpose and end state (commander's intent) and key tasks; subordinates choose method. BLUF comes from Army Regulation 25-50: main point first, active voice. https://www.army.mil/article/215297/mission_command_requires_sharp_commanders_intent ; https://en.wikipedia.org/wiki/BLUF_(communication) **[M]**. The five-paragraph order (situation, mission, execution, support, command and signal) was not read this session; I know of it from general background only and make no claim about its details. **[L]**
- **Incident handover.** Google's SRE workbook: the incident commander "assumes all roles that have not been delegated yet", handoff is explicit, and a live document collects "working theories, eliminated causes". https://sre.google/workbook/incident-response/ **[H]**. The live-document idea is our ledger of what is already decided, so the next worker does not re-derive it.

### 4.2 Context engineering for LLM agents

From Anthropic, "Effective context engineering for AI agents" **[H]**: aim for "the smallest set of high-signal tokens that maximize the likelihood of some desired outcome"; "the minimal set of information that fully outlines your expected behavior"; context rot ("as the number of tokens in the context window increases, the model's ability to accurately recall information from that context decreases"); keep "lightweight identifiers" and load detail just-in-time with tools; structured note-taking outside the window; examples as the "pictures" worth a thousand words; system prompts at "the right altitude", neither brittle if-else nor vague. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
Multi-agent research postmortem **[H]**: each subagent needs "an objective, an output format, guidance on the tools and sources to use, and clear task boundaries", and vague short instructions produced duplicated work. https://www.anthropic.com/engineering/multi-agent-research-system. Note that is a **delegation brief**, which is what the conductor's briefing is.

### 4.3 Synthesis: format, length, order, omissions

Format and order (proposed, mostly synthesis, **[L]** as a whole, built from the cited parts):

1. **Header, one line:** role, game tick, why you were woken (reason and detail), and a severity word (I-PASS illness severity; the repo already has `wake_reason`, `clock`, vitals).
2. **Facts block, numbers and short lines** (stocks, orders not progressing, availability, vitals, stuck jobs). Already built (`build_facts`, `stock_facts`, `order_facts`). Keep capped, keep out coordinates and anything map-like (design commitment 1).
3. **Inputs you must act on, with their content, not ids.** For the Overseer: each pending proposal in a fixed 3 to 5 line shape (who, what, one-line rationale, prediction, plus a computed "overlaps proposal-N" flag). Today only ids are briefed (`briefing["queue"]["ids"]`). This is the single biggest re-derivation sink in the evidence (section 2, point 4). Tension to resolve explicitly: `briefing.py`'s own rule is "Tier 0 figures only", from `docs/AGENT-ARCHITECTURE.md` section 5; proposal summaries are bounded text, not figures, so this needs a decision, not a quiet change.
4. **Already decided (do not redo):** recent rulings and open projects with their status, one line each, so a worker does not re-rule or re-derive.
5. **Your lane, in three lines:** what you own this wake, what you do not (name the role that does), the stop condition ("when each pending proposal has a ruling and its execution record, stop and report").
6. **Open items with owners** (D, section 6): carried-over noticed problems, each with owner and next action.
7. **Then the ask**, last (position effect; queries at the end).

Length: no study I found gives a number for an LLM turn briefing. The nearest evidence is qualitative (context rot, high-signal tokens). Start from the existing cap discipline (every list capped, count always shown) and measure by section 5.4's re-fetch signal rather than guessing a size. **[L]**

What to leave out: anything the worker can fetch by a tool when needed (give an identifier); history older than the last decided items; the reasons the system was designed as it was (those belong in the charter, once); anything that restates the charter. Do not inline detail "just in case"; that is context rot.

Receiver synthesis: if the briefing is long enough to need a read-back, it is probably too long. Prefer to shorten.

## 5. Question C: bounded and in-lane turns

### 5.1 Mission command and separation of duties

Mission command: state intent and end state, bound by what is forbidden, leave method to the subordinate (https://www.army.mil/article/215297/mission_command_requires_sharp_commanders_intent **[M]**). The prior-art report already covers ICS's one supervisor and span of control; not repeated. Two points not there:

- **Intent plus stop condition beats a task list.** The Overseer's wake reason is `queue_pending`; the natural end state is "every pending proposal ruled and every accepted one projected and executed". It then drifted into siting rooms because nothing in the brief said the sited room is the Architect's output, and siting a room "looks like" execution of an accepted proposal. This is a legitimate ambiguity in the design, not just model misbehaviour: proposal-0013 itself was to "site five bedrooms" and the Overseer holds `blueprint.apply`. **[H]** that the Overseer's allowlist includes the actions; whether execution of the Architect's own siting proposal by the Overseer is intended is a design question the charter currently answers only implicitly (the Overseer is "the only component that mutates the fortress"). So the drift may be correct under the charter. The worker itself judged it "overreaching", which suggests the charter and the intended division disagree. Flag for the orchestrator: decide whether execution of a siting proposal is the Overseer's or the Architect's, then write it in both charters.
- **Separation of duties is only real as a tool boundary.** Anthropic's own multi-agent guidance gives subagents explicit "task boundaries"; our repo's principle 8 says the allowlist is the boundary. If the Overseer should not site rooms, it should not hold a tool that does so freely; if it must execute them, the per-turn cost of doing so should be bounded by the proposal (execute exactly the proposed site, no previews beyond N).

### 5.2 Time-boxing and budgets, and what is known about LLMs

- **Human time-boxing.** I found no controlled evidence worth citing that time-boxing improves quality; the practice is widespread (sprints, ICS operational periods) but the sources I reached were practice guidance. "Nobody has evidence" is the honest finding. **[L]**
- **LLM budgets.** "Budget-Aware Tool-Use Enables Effective Agent Scaling" (Nov 2025, web-search agents) finds that simply granting a larger tool-call budget fails to improve performance because agents lack budget awareness and hit a ceiling; a "budget tracker" that shows remaining budget continuously helps, as does a framework that decides whether to dig deeper or pivot given remaining resources. https://arxiv.org/abs/2511.17006 **[M]** (abstract-level; narrow domain; it is a single study and I did not read the effect sizes).
- **Effort scaling in the prompt.** Anthropic's research system embeds explicit effort rules in the lead's prompt ("Simple fact-finding requires just 1 agent with 3-10 tool calls ... complex research might use more than 10 subagents") to "prevent overinvestment in simple queries". https://www.anthropic.com/engineering/multi-agent-research-system **[H]**. This is the same idea as telling the Overseer "a queue of three proposals is about N tool calls".
- **Stopping and scope instructions (Claude).** The Sonnet 5.5 prompting page recommends a stop condition ("When the work the user asked for is done and checked, stop and report. Don't add features ... If you think one would help, mention it at the end instead of doing it") and reports on one test at max effort that a similar "stop and report" instruction cut session cost by about a third with no quality change. https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5 **[H]** for the text and the figure; **single-vendor self-report on coding tasks, and a different model from the Overseer's**. It also warns that harness-injected text after every tool result can be misread as prompt injection, and that countdowns "after every tool result" can trigger this, while occasional one-turn reminders rarely do. **[H]** Implication: if we add a budget display, put it in the briefing and a rare reminder, not in every tool result. For a non-Claude model this is untested.
- **What our own harness already has.** A wall-clock deadline per role (600 s default, `conductor/cycle.py`, `conductor/runner.py`) is a hard stop but a blunt one: it ends the turn wherever it is, mid-plan, which for a write-ahead-log design is exactly the state to avoid. There is no tool-call budget and no budget shown to the worker (**[H]**, grep of `conductor/` for budget-related code found only the daily USD ceiling in `model.yaml`, which that file says is enforced by triage gating, not by the host).

### 5.3 A cheaper outlet than doing it

Drift is partly a cost comparison: noticing a problem and doing it myself is, for the worker, cheaper than getting it to the right owner. Section 6 covers the outlet. The structural counterpart is the one the HSE handover guidance names: define each role's information needs so it does not go looking.

### 5.4 Instrumentation (so the next study has data)

A detector set derived from the cited failure modes, all computable from the existing run record and tool-call log, none requiring new model behaviour: (a) calls to read tools whose answer is already in the briefing facts (re-derivation); (b) action tools called outside the proposal being executed (drift); (c) number of `blueprint.preview` or equivalent calls per applied site; (d) turn duration and tool-call count per wake reason; (e) any noted-for-later item in the final report with no owner record. These are the "log the violation" half of section 3.3 step 5.

## 6. Question D: a noticed problem gets an owner

- **Pages must be actionable.** Google SRE: "Every page should be actionable", "If a page merely merits a robotic response, it shouldn't be a page", and non-urgent email alerts tend toward spam, "rarely read or acted on". https://sre.google/sre-book/monitoring-distributed-systems/ **[H]**. The email-alert point is the analogue of "worth a look next wake": a channel with no owner and no response obligation decays.
- **Alarm rationalisation.** Each alarm has a documented cause, consequence, corrective action and time to respond (EEMUA 191 / ISA 18.2, https://www.exida.com/Alarm-Management/Detail/Alarm-Rationalization **[M]**). An observation without a defined response is a candidate for deletion, not for a note.
- **Incident ownership.** One accountable person; roles not delegated default to the commander (SRE workbook, **[H]**). Action items after incidents need one accountable owner, a priority, tracking and a verifiable end state; the claims about owner, deadline and tracking fields come from an industry blog summary of the workbook (https://oneuptime.com/blog/post/2026-07-31-assign-postmortem-owners-without-blame/view), **[L]**, third-hand; the underlying principle, one named owner, is also in the SRE material above.
- **Diffusion of responsibility** (already in the prior-art report) is the mechanism: an observation visible to several parties and owned by none is acted on by none.

Mapping, **[L]** (design synthesis): a "noticed problem" should be an object, not prose. Minimal fields: what, evidence (tool call or id), proposed owner role, a next action, and an expiry after which it escalates. The default owner is the commander analogue, here the Overseer for cross-role issues or the role whose domain it is, with the default being "you own it until you hand it to someone" (the SRE rule that undelegated roles default to the IC). The worker's alternatives become: act (if in lane), hand off (create the object with an owner), or drop (state why). "Defer with no owner" is not offered. Today's tools offer no such object for the Overseer (point 5, section 2); the Architect and Quartermaster have `queue.propose`, which is close to it, and `queue.ask`, which routes to the Consultant only.

## 7. The model actually in use: DeepSeek V4 Pro (added after the brief)

The four fort roles run `deepseek/deepseek-v4-pro` via openclaw (`agents/*/model.yaml`), Claude only as fallback. The captured thinking in `runs-public.json` is DeepSeek reasoning. This section re-weights sections 3 to 6 and adds what the DeepSeek documentation says.

### 7.1 Transfer of the evidence already cited

- **Model-agnostic, so stronger for us:** the human-factors results (forcing functions, checklists, alarm rationalisation, handover), the structure of the live evidence in section 2 (the worker skipped a step the server accepted skipping), the position effect (Lost in the Middle tested several models), the instruction-density finding (IFScale tested 20 models from seven providers), and tau-bench's finding that policy-following is unreliable across repeated trials (tested on non-Claude models). Server refusals do not depend on the model at all. **[M]**
- **Claude-specific, weaker for us:** the "dial back CRITICAL/MUST" advice, the Sonnet 5.5 stop-and-report prompt and its one-third cost figure, the turn-scoped reminder and injection-misread behaviour, and effort-level advice. Treat as hypotheses to test on DeepSeek, not findings. **[H]** that they are Claude-specific, since the pages say so.
- **tau-bench caveat found while checking:** an agentic-benchmark critique (arXiv 2507.02825, via search summary) reports tau-bench counts an empty response as success on impossible tasks, with a trivial agent scoring 38%. Read the tau-bench numbers in section 3.2 as direction only. **[M]**

### 7.2 DeepSeek-specific evidence on adherence and tool calls

- Third-party summaries put V4 Pro's instruction-following score at 62.4/100 and say V4-Pro (max) trails Opus 4.7 and GPT-5.5 by 3 to 15 points on overlapping benchmarks, with the largest gaps on agentic workloads (search summaries of aggregator pages such as https://www.remio.ai/post/deepseek-v4-pro-delivers-mixed-benchmark-results). **[L]**: aggregator sites of unknown rigour, underlying benchmark not opened, and they concern text tasks, not our tool-heavy turns. No source I reached measured DeepSeek on procedure compliance in a tool loop, on restating inputs, or on repetition in long agentic turns. "Nobody has measured this" is my finding, with the caveat that my search was a handful of queries.
- **Tool-call arguments.** DeepSeek's docs say strict mode is Beta: it needs the beta base URL, `strict: true` on each function, every object property `required` and `additionalProperties: false`, and a limited schema type set (object, string, number, integer, boolean, array, enum, anyOf). https://api-docs.deepseek.com/guides/tool_calls **[H]** (via fetch tool). A search summary of the docs says the model "does not always generate valid JSON, and may hallucinate parameters not defined by your function schema", so arguments must be validated; I did not see that sentence in my own fetch of the page, so **[M]**. Nothing found measures nested-JSON failure rates. Implication: calls with nested arguments (`queue.project` steps and `requires` edges) should be validated server side with repair-oriented errors (R1). Whether openclaw can use strict mode is **not verified**; strict mode's "all properties required" rule would also conflict with our optional fields.
- Because we cannot assume strong argument discipline, server-side validation with specific refusal text is likely a stronger lever here than for a stronger model. **[L]**, reasoning not measurement.

### 7.3 Reasoning mode on long agentic turns

- DeepSeek docs: thinking is on by default, default effort `high`; `reasoning_effort` takes low, high or max (medium maps to high, xhigh to max); tool use works in thinking mode (since V3.2); with tools, the `reasoning_content` of all previous turns must be passed back and is concatenated into the context; temperature, presence and frequency penalties have no effect in thinking mode. https://api-docs.deepseek.com/guides/thinking_mode **[H]** (via fetch tool).
- Implications. (a) **Effort is a documented control**, and the penalties that might curb repetition do nothing in thinking mode, so repetition has to be handled by input shape and turn bounds, not sampling. (b) **Reasoning accumulates in context across tool rounds**, so every re-derivation costs output tokens and enlarges later inputs; a long restating turn compounds. Consistent with the 11-minute turn, but I have no per-step token data. **[L]** (c) The repo sets no effort anywhere (grep of the repo found no `reasoning_effort` config); whether openclaw passes one is **not verified**, so roles probably run at the default `high`. A per-role effort (low for routine ruling, high for hard arbitration) is untested but cheap to try if openclaw exposes it. **[L]**
- The restating and "Actually, let me reconsider" loops are visible in run-0004 (26 "Let me", 12 "Actually" in 12k surviving characters); I found no published DeepSeek-specific study of it.

### 7.4 Context caching and briefing layout

- DeepSeek caches by **prefix**: a later request hits only if it "fully matches a cache prefix unit"; units are created at the end of user input and model output and at fixed token intervals for long inputs; "best-effort", no guaranteed hit rate; hits are reported as `prompt_cache_hit_tokens` and `prompt_cache_miss_tokens` in usage. https://api-docs.deepseek.com/guides/kv_cache **[H]** (fetch tool). The docs say nothing about ordering, so the layout advice below is inference from prefix matching.
- Price (pricing page via fetch tool): V4-Pro input cache hit $0.022 to $0.044 per million tokens, cache miss $0.66 to $1.32, output $1.98 to $3.96; the ranges look like peak versus off-peak (off-peak half; peak 01:00 to 04:00 and 06:00 to 10:00 UTC, Monday to Friday); 1M context, 384K max output. https://api-docs.deepseek.com/quick_start/pricing **[M]**: I did not resolve which end of each range is which; prices change. On these numbers a hit is about 30 times cheaper than a miss and output costs roughly 90 times a cached input token, so **cost is dominated by output (reasoning) tokens, not briefing size**. That weakens any cost case for squeezing the briefing; the case for brevity is attention and re-derivation.
- **Layout (inference, [L]).** Order stable to volatile: charter and tool definitions first, then slow-changing doctrine and rules, then the per-wake briefing, then the ask. Anything that changes every wake (tick, wake reason, facts, timestamps) goes after the stable part or it breaks the shared prefix; no timestamp or tick in the first lines of the system prompt. This agrees with putting the ask last (section 4.3). Wakes are minutes apart and the docs give no cache lifetime, so whether a prefix survives from one wake to the next is **not verified**; measure it from `prompt_cache_hit_tokens` if openclaw surfaces usage (it may not).
- Within a turn, all reasoning is replayed as input each round, so later rounds are mostly cheap cached reads plus expensive new output. Cost grows with reasoning rounds, which supports bounding rounds (section 5.2) over trimming input.
- The 1M context means context size is not the binding limit; attention quality (position effect, context rot, **not measured for DeepSeek**) and output tokens are.

### 7.5 What this changes in the recommendations

- R1 (server refusals) rises in priority: it is model-agnostic and the weak evidence says this model is not a strong agentic instruction follower. Add schema-level validation with repair text for nested arguments.
- R3 (charters): test emphatic versus plain wording on DeepSeek directly instead of adopting Claude advice; order charters stable-first for the cache.
- R2 (briefing): fixed order, volatile fields after stable ones, and do not justify trimming by cost.
- R5 (turn bounds): try a per-role `reasoning_effort` and a cap on tool rounds; output tokens are both the cost and the drift.
- **R7 (new): measure on this model before tuning.** Log per-run cache-hit tokens, output (reasoning) tokens and rounds if openclaw exposes them; replay one wake snapshot at effort low and high and compare decisions. This replaces borrowed Claude evidence with our own. Whether openclaw exposes any of this is **not verified**.

## 8. Recommendations, mapped to this repo's parts

Ordered by value for effort. All are proposals; none built.

**R1. dfmcp server refusals: finish the interlock with a content check, and write the other sequence rules as refusals.** (Section 3.3 steps 2 to 4.)
- Keep the refusal on `queue.executed` without a project (`dfmcp/queue_tools.py`, `dfqueue/store.py`, done). Add a **minimal content check at `queue.project`** for the fields the Board reads (non-empty `public_title`, `public_rationale` of at least a sentence that is not a copy of the proposal's, a `label` on every step), refused with a message that names the missing field. This addresses the hollow-gate risk (section 3.3 caution a).
- Audit the other "always" sentences in `agents/overseer/role.md` and `agents/*/role.md` against the decision rule; each one the server can observe becomes a refusal with a repair message, each one it cannot becomes guidance plus a detector. Candidates seen in the Overseer charter: `queue.executed` must name every tool call made; `queue.escalate` is the only escalation (already mechanical).
- Make refusal text the second place the rule is stated (write for the model, per Anthropic's tool guidance).
- Watch for the refusal-loop failure: log repeated identical refused calls per run.

**R2. conductor/briefing.py: brief with content, lane and ledger, in fixed order.** (Section 4.3.)
- Add a `pending` block for the Overseer with a bounded per-proposal summary (who, what, one line why, prediction) and a computed overlap flag between pending proposals. Resolve the "Tier 0 figures only" rule explicitly: either extend it to "bounded short text" in `docs/AGENT-LOOP.md` item 6 or put these summaries in a second block with its own cap.
- Add a `decided` block (last few rulings and open projects, one line each) so decided work is not redone.
- Add a `lane` block, three lines: owns, does not own (names the other role), stop condition. Generate it from the role's charter data so it is not a second copy to keep in sync.
- Add an `open_items` block (R4).
- Keep ordering facts first, ask last.
- Measure before tuning size: count briefing-fact re-fetches per run (section 5.4).

**R3. agents/*/role.md charters: shorten, reorder, state reasons, remove duplicated rules.** (Section 3.2 position and density evidence; Claude guidance **[M]** for this model.)
- Put the three things that cannot be skipped in the first lines, as a short numbered sequence with the reason for each. The Execution bullet was already rewritten this way in `ede52d4`; the rest of the 129-line charter has the same dense-bullet shape.
- Where a rule is now a server refusal, replace its prose with one line pointing at the order of operations, so the charter does not teach a rule the server already holds (and cannot drift from it).
- Add an explicit stop condition and an explicit "not mine" list per role, including the siting decision flagged in section 5.1 (needs an orchestrator decision first).
- Test wording changes on the actual model (DeepSeek), not only on Claude; the vendor guidance cited is Claude-specific.

**R4. agents/*/tools.yaml allowlists plus one new server tool: give "I noticed X" a home that has an owner.** (Section 6.)
- A `queue.flag` (name illustrative) available to every role: fields what, evidence, owner role, next action, expiry. The server requires an owner and a next action and refuses without them. Open flags appear in the owner's `open_items` briefing block until closed. This directly replaces "worth a look next wake" and routes through the existing sole-writer design (the Overseer rules on flags the way it rules on proposals, or the owner role picks it up).
- If a new tool is too much, the cheapest approximation is to let the Overseer `queue.ask` the owning advisor (it can already), and make the detector in section 5.4(e) flag any final report that contains "next wake" or "next cycle" without a corresponding ask or flag. This is weaker, since it only catches after the fact.
- On boundaries: if the Overseer should not site rooms, remove or constrain the tool (for example, `blueprint.apply` only for a site recorded in an accepted ruling's own project steps), rather than rely on the charter. This is a judgment call, flagged in section 5.1.

**R5. Conductor wake signals: make ownership visible in the wake, and bound the turn.** (Sections 5.2, 6.)
- `stuck_job` currently wakes the Quartermaster only (`conductor/policy.yaml`), and the live run showed the Overseer seeing the digest without being its owner, then deferring. Either name the owner explicitly in the wake detail ("owner: quartermaster; next action: order a Bed or release the construction") or let the conductor open a flag (R4) with the owner pre-filled when `stuck_job` fires and no owner has acted by the renotify interval (`stuck_job_renotify_ticks`).
- Add a per-wake-reason turn expectation to the briefing (expected tool-call range, section 5.2 effort scaling) and a **soft** budget shown once in the briefing and as at most one mid-turn reminder, rather than only the 600 s wall-clock cap. Measure first (section 5.4(d)) to set the numbers; do not copy figures from the research-system example.
- Consider ending the turn on the stop condition by code: when every pending proposal has a ruling and every accepted one has an executed record, the conductor can detect completion from the tool-call log. Today that is not used to cut the turn short; it is a detector, not a kill. **[L]**

**R6. Verify before building: one cheap experiment that separates the hypotheses.** The evidence cannot tell whether the worker skipped the project because the server accepted it (feedback), because the charter text was buried, or because of this model's habits. After the server refusal is deployed, one real wake that accepts a proposal will show whether the worker complies after the refusal text, which tests the "refusal is a prompt" claim directly on this model. Record the count of refused-then-complied versus refused-then-hollow in the run record.

## 9. What I could not verify

- **No live run exists after the server refusal** and none of the briefing changes are built, so every recommendation is untested against this fort or this model.
- **The Overseer model is not Claude.** Anthropic prompting guidance is Claude-specific; section 7 covers DeepSeek, but its adherence and repetition evidence is thin aggregator-level material, its cache and price facts come from a summarising fetch tool, and I did not inspect openclaw to see which DeepSeek controls (effort, strict mode, usage fields) it exposes.
- **I-PASS and surgical-checklist numbers** come from AHRQ PSNet, trade press and a news summary of the NEJM papers; I did not read the NEJM text. One of the two I-PASS summaries attached the 23% figure to a different measure than the other; the rates given are from the more detailed summary. The compliance explanation for the Ontario null result is commentary, not a finding.
- **SBAR's** quality-of-evidence statement is from one search summary of a 2018 review; I did not read the review.
- **Degani and Wiener (1993)**: abstract-level only. Gawande's read-do/do-confirm: secondary summary only. The five-paragraph order and the BLUF history: secondary only; the five-paragraph order not read at all.
- **tau-bench** numbers are from search summaries of the paper's abstract; **IFScale** and **BATS** are abstract-level; I did not read their tables. The BATS result is for web-search agents, not for world-mutating tool use. I found **no study of turn or step budgets for agents acting on a shared mutable world**, and none comparing hard tool-gating against prompt rules for procedure compliance. "Nobody has measured this" is my finding, with the caveat that my search was a handful of queries, not a systematic review.
- **Time-boxing evidence for humans:** not found beyond practice guidance.
- **Whether the surviving transcript is representative.** The capture is 12,025 characters with the middle cut; the counts in section 2 are of the surviving text only.
- **Whether `stuck_job` led the Quartermaster to act on the Bed** is unknown (README).
- **Claude Code hooks and Anthropic pages** were fetched through a summarising fetch tool for most quoted phrases; short quotes were returned verbatim by the tool but I did not pin copies. No line-number citations are made from any long web source. Repo file claims were read directly.
- I did not search for the multi-agent literature on **role drift** beyond what the 2026-09-12 report already covers (MAST's "disobey role specification" and "task derailment" classes).

## 10. Sources

DeepSeek: https://api-docs.deepseek.com/guides/kv_cache ; https://api-docs.deepseek.com/quick_start/pricing ; https://api-docs.deepseek.com/guides/thinking_mode ; https://api-docs.deepseek.com/guides/tool_calls ; https://arxiv.org/abs/2507.02825 (agentic benchmark flaws) ; https://www.remio.ai/post/deepseek-v4-pro-delivers-mixed-benchmark-results

Repo (read directly): `evals/live/2026-10-05-pause-safety/README.md` and `runs-public.json`; `conductor/briefing.py`, `conductor/runner.py`, `conductor/cycle.py`, `conductor/policy.yaml`; `agents/overseer/role.md`, `tools.yaml`, `model.yaml`; `handoffs/2026-10-05-project-before-executed.md`; commit `ede52d4` (diff of the charter's old Execution bullet).

External:
- Anthropic, Building effective agents: https://www.anthropic.com/engineering/building-effective-agents
- Anthropic, Effective context engineering for AI agents: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic, Writing effective tools for agents: https://www.anthropic.com/engineering/writing-tools-for-agents
- Anthropic, How we built our multi-agent research system: https://www.anthropic.com/engineering/multi-agent-research-system
- Anthropic, The think tool: https://www.anthropic.com/engineering/claude-think-tool
- Anthropic, Claude prompting best practices: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- Anthropic, Prompting Claude Sonnet 5.5: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5
- Claude Code hooks guide: https://code.claude.com/docs/en/hooks-guide
- MetaGPT: https://arxiv.org/abs/2308.00352
- tau-bench: https://arxiv.org/abs/2406.12045
- IFScale: https://arxiv.org/abs/2507.11538
- Budget-Aware Tool-Use (BATS): https://arxiv.org/abs/2511.17006
- Lost in the Middle: https://arxiv.org/abs/2307.03172
- I-PASS: https://psnet.ahrq.gov/issue/changes-medical-errors-after-implementation-handoff-program ; https://www.massdevice.com/handoff-tool-cuts-harmful-medical-errors-30-percent/
- SBAR review: https://bmjopen.bmj.com/content/8/8/e022202
- Surgical checklists: https://mdedge.com/content/surgical-checklists-failed-improve-outcomes ; https://www.longwoods.com/content/23781
- Degani and Wiener: https://ntrs.nasa.gov/citations/19920000775
- Gawande summaries: https://athena-newsletter.beehiiv.com/p/atul-gawande-s-surgeon-checklist
- Forcing functions and poka-yoke: https://architectures.danlockton.co.uk/everyday-things-persuasive-technology/ ; https://en.wikipedia.org/wiki/Poka-yoke
- HSE shift handover: https://www.hse.gov.uk/humanfactors/topics/shift-handover.htm ; Energy Institute human factors briefing note 10: https://www.energyinst.org/technical/publications/topics/human-and-organisational-factors/human-factors-briefing-note-no.-10-communications
- Army mission command and BLUF: https://www.army.mil/article/215297/mission_command_requires_sharp_commanders_intent ; https://en.wikipedia.org/wiki/BLUF_(communication)
- Google SRE book, monitoring: https://sre.google/sre-book/monitoring-distributed-systems/
- Google SRE workbook, incident response: https://sre.google/workbook/incident-response/
- Alarm rationalisation: https://www.exida.com/Alarm-Management/Detail/Alarm-Rationalization
- Postmortem action-item ownership (third-hand): https://oneuptime.com/blog/post/2026-07-31-assign-postmortem-owners-without-blame/view
