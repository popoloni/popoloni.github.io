# Addy Osmani — 50 annotated practitioner articles

## Canonical O-series research context, corrected edition (10 October 2026)

These are publicly indexed essays published from 10 October 2024 through 10 October 2026. O001–O050 are stable practitioner IDs, distinct from the book's W001–W193 original research catalogue.
Research links are editorial comparisons, never claims of direct Osmani citation, experimental validation, or causal replication.

The exact publisher-page heading for O003 is **Agentic Skill Decay**; the browser/SEO headline differs (**Mastery Still Comes From Doing the Reps**). The O ID is unchanged.

### O001 — The Code Nobody Reads

**Reference.** Osmani, Addy (2026-09-28). *The Code Nobody Reads*. Elevate (Substack). https://addyo.substack.com/p/the-code-nobody-reads

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Verification & review; Engineering structure.

**In short.** When human line-by-line reading no longer scales, independently justified checks and accountable approval must replace its assurance role.

**Summary.** Osmani revises his earlier advice to inspect every generated line: routine low-risk changes may receive automated first-pass review, while high-blast-radius changes retain deeper scrutiny. He argues that review also transmitted knowledge and that engineering teams must retain both understanding and authority to refuse a release.

**Main findings / practitioner recommendations.** Use explicit risk tiers and an evidence dossier rather than assuming every line is read; Keep independent tests and a named human acceptance authority; Protect mentoring, explainability and reviewer capacity.

**Book placement.** C08, §8.8. Role: CORE_CITED.

**Research comparisons (editorial only).** W093 | W100 | W111.

**Limitation.** The page includes a Teleport-sponsored passage, alongside quoted vendor/self-reported statistics. Its risk-calibrated review argument is practitioner commentary, not a controlled intervention; validate independent primary metrics before reusing any numbers.

### O002 — Brownfield Agentic Engineering

**Reference.** Osmani, Addy (2026-09-14). *Brownfield Agentic Engineering*. Elevate (Substack). https://addyo.substack.com/p/brownfield-agentic-engineering

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** System knowledge & memory; Engineering structure.

**In short.** Reliable agents in mature codebases need recovered tacit constraints and regression evidence before modifying code.

**Summary.** The essay stresses that a repository rarely captures the full behavior of a legacy service: contracts, migrations, user journeys and institutional knowledge remain external. Small reversible changes, context gathering and reproducible tests are offered as controls against locally successful but architecturally wrong agent patches.

**Main findings / practitioner recommendations.** Inventory external invariants and dependencies before delegation; Make brownfield changes incremental and reversible; Verify old behavior alongside new acceptance criteria.

**Book placement.** C09, §9.1. Role: CORE_CITED.

**Research comparisons (editorial only).** W154 | W155 | W171.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O003 — Agentic Skill Decay

**Reference.** Osmani, Addy (2026-08-31). *Agentic Skill Decay*. Elevate (Substack). https://addyo.substack.com/p/agentic-skill-decay

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Skills & learning; System knowledge & memory.

**In short.** Developers must deliberately practice reasoning, debugging and code comprehension when agents perform most implementation work.

**Summary.** Osmani describes how automatic completion can remove the repetitions that once built expertise. He proposes predicting failures before asking an agent, explaining diffs, reconstructing decisions and periodically solving problems manually so proficiency does not disappear behind apparent task completion.

**Main findings / practitioner recommendations.** Preserve manual practice and counterfactual reasoning exercises; Measure retained comprehension rather than prompt throughput; Avoid confusing agent task success with human competence.

**Book placement.** C10, §10.8. Role: CORE_CITED.

**Research comparisons (editorial only).** W117 | W118 | W121.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O004 — Audit your Agent files

**Reference.** Osmani, Addy (2026-08-27). *Audit your Agent files*. Elevate (Substack). https://addyo.substack.com/p/audit-your-agent-files

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** System knowledge & memory; Code quality & security.

**In short.** Agent configuration and memory are perishable operational assets that should be periodically revalidated.

**Summary.** Instructions in AGENTS.md, CLAUDE.md, skills and durable memory can become outdated as tools and repositories change. Osmani recommends auditing usefulness, trimming redundant directives, testing outcomes and separating genuinely persistent facts from temporary guidance.

**Main findings / practitioner recommendations.** Record an owner and expiry policy for agent instructions; Test whether each instruction changes verified behavior; Audit tool privileges and memory freshness independently.

**Book placement.** C09, §9.6. Role: CORE_CITED.

**Research comparisons (editorial only).** W053 | W157 | W159.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O005 — Human judgment doesn't leave the software factory. It relocates.

**Reference.** Osmani, Addy (2026-08-21). *Human judgment doesn't leave the software factory. It relocates.*. Elevate (Substack). https://addyo.substack.com/p/human-judgment-doesnt-leave-the-software

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; Verification & review.

**In short.** Agentic factories relocate human responsibility toward intent, quality criteria and authorization rather than eliminating it.

**Summary.** The article compares human-supervised and largely unattended factories and asks who defines product intent, architectural trade-offs and unacceptable regressions. It advocates persistent checks, managed risk boundaries and explicit ownership even when many implementation steps run without a person present.

**Main findings / practitioner recommendations.** Put human judgment at the intention and acceptance boundaries; Automate early regression and security checks; Escalate design ambiguity and irreversible operations to authorized owners.

**Book placement.** C11, §11.6. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W147 | W149 | W093.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O006 — Practical Loop Engineering

**Reference.** Osmani, Addy (2026-08-14). *Practical Loop Engineering*. Elevate (Substack). https://addyo.substack.com/p/practical-loop-engineering

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; What agents can do.

**In short.** Effective autonomous loops begin with bounded goals, observable checks and explicit stopping rules.

**Summary.** Drawing on concurrent agent use, Osmani separates tasks safe for fully bounded delegation from tasks that require close review. He describes iterative act-test-revise operation while emphasizing constraints, definition of done and final human judgment where risk is material.

**Main findings / practitioner recommendations.** State an independent success predicate before granting retries; Limit cost, duration, permissions and edit scope; Escalate on ambiguity or verification exhaustion.

**Book placement.** C03, §3.6. Role: CORE_CITED.

**Research comparisons (editorial only).** W095 | W191 | W152.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O007 — Agentic Code Quality

**Reference.** Osmani, Addy (2026-08-08). *Agentic Code Quality*. Elevate (Substack). https://addyo.substack.com/p/agentic-code-quality

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Code quality & security; Verification & review.

**In short.** Quality assurance for generated code increasingly depends on repeatable harness checks, not only manual inspection or agent opinion.

**Summary.** Osmani notes the scalability limit of inspecting high-volume agent diffs and the instability of repeated model-review judgments. He favors consistent repository rules, static checks, tests and explicit quality gates surrounding generation, while keeping focused human scrutiny for risky changes.

**Main findings / practitioner recommendations.** Move quality requirements into repeatable repository checks and agent harness gates; Track defects, architectural fit and post-merge maintenance—not merely model review approval; Retain risk-sensitive human review because multiple models can share error modes.

**Book placement.** C05, §5.1. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W054 | W055 | W079.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O008 — Software Factories, Light and Dark

**Reference.** Osmani, Addy (2026-07-22). *Software Factories, Light and Dark*. Elevate (Substack). https://addyo.substack.com/p/software-factories-light-and-dark

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; Economics.

**In short.** A software factory is many governed loops; its level of human involvement changes both risk and total operating cost.

**Summary.** The essay contrasts "light" factories that retain human interpretation with "dark" factories that minimize review, exposing the trade-off between throughput and lost comprehension. Osmani argues that harness capability and measurable verification should determine safe autonomy, not the attraction of unattended execution.

**Main findings / practitioner recommendations.** Separate an autonomous loop from the governance system supervising many loops; Measure cost of failures and rework, not just generation speed; Choose review intensity by reversibility and blast radius.

**Book placement.** C11, §11.9. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W027 | W147 | W152.

**Limitation.** A conceptual taxonomy and projections, not a controlled comparison of factory operating models.

### O009 — Own the Outer Loop

**Reference.** Osmani, Addy (2026-07-09). *Own the Outer Loop*. Elevate (Substack). https://addyo.substack.com/p/own-the-outer-loop

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; Verification & review.

**In short.** Engineers can delegate the inner execution loop while retaining ownership of quality criteria, verdicts and consequences.

**Summary.** Osmani distinguishes producing code and testing artifacts from accepting the evidence those checks produce. He locates professional accountability in the surrounding outer loop: intent, checks, risk appetite, provenance, approval and action if a released change fails.

**Main findings / practitioner recommendations.** Define quality signals before execution; Separate the checker from the final acceptance authority; Require a named owner with authority to stop or roll back.

**Book placement.** C11, §11.6. Role: CORE_CITED.

**Research comparisons (editorial only).** W095 | W100 | W111.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O010 — Agentic Autonomy Levels

**Reference.** Osmani, Addy (2026-07-03). *Agentic Autonomy Levels*. Elevate (Substack). https://addyo.substack.com/p/agentic-autonomy-levels

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** What agents can do; Engineering structure.

**In short.** Osmani separates autonomy into agency and orchestration axes, describing six operating levels from suggestions to management-by-exception.

**Summary.** Osmani argues that a one-dimensional autonomy ladder hides the difference between what one agent may do and the ability to coordinate many agents. He proposes two axes—agency and orchestration—and six practical levels: assist, supervised action, scoped task delegation, goal-driven autonomy, parallel delegation, and managed-by-exception orchestration. Risk, reversibility, independent checks and escalation limit the appropriate level for any task.

**Main findings / practitioner recommendations.** Grade individual-agent initiative separately from multi-agent orchestration; Use the six levels as a contextual operational taxonomy, not a validated maturity index; Set an explicit risk and verification ceiling for delegated work.

**Book placement.** C03, §3.3. Role: CORE_CITED.

**Research comparisons (editorial only).** W191 | W152 | W095.

**Limitation.** Practitioner interpretation; not primary experimental evidence. Framework or market hypothesis is an authored practitioner proposal, not an empirically validated scale or intervention.

### O011 — Agentic Code Review

**Reference.** Osmani, Addy (2026-06-16). *Agentic Code Review*. Elevate (Substack). https://addyo.substack.com/p/agentic-code-review

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Verification & review; Skills & learning.

**In short.** AI-generated code moves the bottleneck from writing to justified acceptance, making review strategy a core engineering skill.

**Summary.** Osmani contrasts solo experiments and long-lived team repositories, arguing that risk, context, integration and shared learning demand different review methods. Review must consider correctness evidence, comprehension and how design decisions survive the handoff.

**Main findings / practitioner recommendations.** Allocate human attention by risk rather than diff size; Audit automated reviewer false positives and misses; Preserve review as a team knowledge-transfer mechanism.

**Book placement.** C08, §8.8. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W069 | W093 | W098.

**Limitation.** Practitioner interpretation; not primary experimental evidence. Any externally quoted benchmark, productivity or vendor telemetry requires independent verification of original method and population.

### O012 — Loop Engineering

**Reference.** Osmani, Addy (2026-06-08). *Loop Engineering*. Elevate (Substack). https://addyo.substack.com/p/loop-engineering

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; What agents can do.

**In short.** Osmani identifies five interoperable loop-building primitives—scheduling, worktrees, skills, connectors and subagents—plus durable external memory.

**Summary.** Loop engineering means configuring a system that discovers work, dispatches agents, checks outputs, records progress and repeats rather than manually prompting each step. Osmani identifies five recurring primitives: automations/scheduling, isolated Git worktrees, reusable skills, plugins and connectors, and specialized subagents. A separate persistent memory or task board is the sixth requirement for continuity. He also warns about verification, comprehension debt and unpredictable token costs.

**Main findings / practitioner recommendations.** Schedule discovery and triage but bound side effects; Isolate parallel work in worktrees; share intentions via tested skills/connectors and durable state; Separate the maker from the checker, measure token usage, and escalate when independent checks fail.

**Book placement.** C03, §3.6. Role: CORE_CITED.

**Research comparisons (editorial only).** W075 | W095 | W191.

**Limitation.** A practitioner engineering pattern; the article does not establish comparative loop reliability by controlled experiment. Framework or market hypothesis is an authored practitioner proposal, not an empirically validated scale or intervention.

### O013 — Long-running Agents

**Reference.** Osmani, Addy (2026-04-30). *Long-running Agents*. Elevate (Substack). https://addyo.substack.com/p/long-running-agents

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** System knowledge & memory; What agents can do.

**In short.** Agents operating across sessions require durable task state, resumability, recovery and verifiable progress.

**Summary.** The article examines context-window exhaustion, repeated mistakes and premature "done" claims in workflows lasting days. It recommends structured progress artifacts, checkpoints, clean workspaces and independent acceptance tests to support handoffs between agent sessions.

**Main findings / practitioner recommendations.** Persist decisions and current state outside the transient model context; Make retries idempotent and restartable; Verify continuity and completion against external artifacts.

**Book placement.** C09, §9.6. Role: CORE_CITED.

**Research comparisons (editorial only).** W157 | W159 | W191.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O014 — The Agent Stack Bet

**Reference.** Osmani, Addy (2026-04-18). *The Agent Stack Bet*. Elevate (Substack). https://addyo.substack.com/p/the-agent-stack-bet

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Code quality & security; Engineering structure.

**In short.** Production agents need identity, authorization, observability and recovery controls beyond an impressive base model.

**Summary.** Osmani describes fragile production plumbing: broad service-account permissions, schema drift, opaque state and broken recovery. The remedy is an explicit agent stack with task-scoped access, traceability, policy enforcement and durable error handling.

**Main findings / practitioner recommendations.** Bind every action to scoped identity and human ownership; Restrict tool permissions and monitor effects; Design recoverable operations and audit trails for runtime failures.

**Book placement.** C06, §6.8. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W053 | W060 | W152.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O015 — Is the IDE dead?

**Reference.** Osmani, Addy (2026-03-20). *Is the IDE dead?*. Elevate (Substack). https://addyo.substack.com/p/death-of-the-ide

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; What agents can do.

**In short.** Asynchronous agent orchestration may become the primary developer control surface, while editors remain tools for targeted inspection.

**Summary.** Osmani discusses workbench and control-plane interfaces for coordinating cloud and local coding agents. The claim is about a shift in where engineers plan, inspect and approve work, not proof that code editors will disappear.

**Main findings / practitioner recommendations.** Teach delegation and inspection as separate activities; Compare orchestration tools on observable state and control; Treat claims about the IDE dying as forecasts.

**Book placement.** C01, §1.3. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W002 | W014 | W027.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O016 — 14 More lessons from 14 years at Google

**Reference.** Osmani, Addy (2026-02-12). *14 More lessons from 14 years at Google*. Elevate (Substack). https://addyo.substack.com/p/14-more-lessons-from-14-years-at

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; Skills & learning.

**In short.** Long-lived engineering teams depend on trust, clear decision-making, effective communication and organizational stewardship.

**Summary.** A second retrospective about long-term team effectiveness stresses the structures around projects: communication, ownership, priorities, collaboration and shared decisions. These lessons provide organizational context rather than new research on AI agents.

**Main findings / practitioner recommendations.** Make decision rights and handoffs visible; Value team reliability above heroic individual throughput; Use as background principles, not an AI impact study.

**Book placement.** C11, §11.2. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W161 | W171 | W178.

**Limitation.** Personal career retrospective; no original AI-specific field experiment. CONTEXTUAL ONLY: this article does not evaluate AI-assisted development, agent behavior, or causal AI outcomes.

### O017 — The 80% Problem in Agentic Coding

**Reference.** Osmani, Addy (2026-01-28). *The 80% Problem in Agentic Coding*. Elevate (Substack). https://addyo.substack.com/p/the-80-problem-in-agentic-coding

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Skills & learning; System knowledge & memory.

**In short.** When agents implement most code, developers can accumulate comprehension debt even while shipping more changes.

**Summary.** Extending his earlier "70% problem", Osmani frames agent-heavy development as an inversion between authorship and understanding. Speed moves the bottleneck toward explaining decisions, tracing behavior and maintaining the code after the generation session ends.

**Main findings / practitioner recommendations.** Require explain-back, behavioral traces and repair exercises; Measure whether an engineer can modify agent-written code later; Treat the 80% phrase as illustration, not a measured universal ratio.

**Book placement.** C10, §10.8. Role: CORE_CITED.

**Research comparisons (editorial only).** W154 | W117 | W122.

**Limitation.** The 80% figure expresses an illustrative workflow shift; it is not a population-level experimental estimate.

### O018 — How to write a good spec for AI agents

**Reference.** Osmani, Addy (2026-01-19). *How to write a good spec for AI agents*. Elevate (Substack). https://addyo.substack.com/p/how-to-write-a-good-spec-for-ai-agents

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; System knowledge & memory.

**In short.** A useful agent specification is compact, testable and iterative rather than a giant prompt resembling an unvalidated requirements dump.

**Summary.** Osmani provides guidance on the degree of detail in requirements, decomposition into small tasks, read-only planning and successive execution. Intent, constraints, expected behavior and testing guidance become checkpoints throughout development.

**Main findings / practitioner recommendations.** Specify desired behavior and forbidden regressions separately from implementation detail; Plan before writes, then build in small independently checked increments; Update specification when evidence reveals an ambiguity.

**Book placement.** C04, §4.1. Role: CORE_CITED.

**Research comparisons (editorial only).** W148 | W151 | W077.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O019 — Code Review in the Age of AI

**Reference.** Osmani, Addy (2026-01-05). *Code Review in the Age of AI*. Elevate (Substack). https://addyo.substack.com/p/code-review-in-the-age-of-ai

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Verification & review; Engineering structure.

**In short.** The rise in generated changes makes code review an explicit burden-of-proof and accountability process.

**Summary.** The essay argues that tests, reproducible manual checks and a stated risk assessment should accompany every proposal. Teams should preserve contextual knowledge and ownership rather than confusing a model-generated diff with evidence that the resulting change is safe.

**Main findings / practitioner recommendations.** Attach objective verification artifacts to pull requests; Review intent, integration risk and sensitive paths; Never treat a passing self-generated test as independent approval.

**Book placement.** C08, §8.9. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W065 | W069 | W093.

**Limitation.** Practitioner interpretation; not primary experimental evidence. Any externally quoted benchmark, productivity or vendor telemetry requires independent verification of original method and population.

### O020 — How Good Is AI at Coding React (Really)?

**Reference.** Osmani, Addy (2025-12-29). *How Good Is AI at Coding React (Really)?*. Elevate (Substack). https://addyo.substack.com/p/how-good-is-ai-at-coding-react-really

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** What agents can do; Verification & review.

**In short.** React-related AI success is highly task-dependent, with integration and usability much harder to establish than component scaffolding.

**Summary.** Using third-party web and coding benchmarks, Osmani contrasts relatively tractable isolated UI tasks with weaker multi-step integration. He recommends context-rich specifications, UI standards, accessibility checks and browser-level evaluation instead of equating code generation with product quality.

**Main findings / practitioner recommendations.** Benchmark scores have task- and version-specific denominators; Use browser tests and accessibility review for end-to-end UI changes; Treat reported percentages as third-party snapshot results, not the author’s experimental measurement.

**Book placement.** C03, §3.4. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W191 | W193 | W111.

**Limitation.** Numerical benchmark claims are a synthesis of separate benchmarks with different tasks, versions and measurement methods; not directly comparable. Any externally quoted benchmark, productivity or vendor telemetry requires independent verification of original method and population.

### O021 — My LLM coding workflow going into 2026

**Reference.** Osmani, Addy (2025-12-18). *My LLM coding workflow going into 2026*. Elevate (Substack). https://addyo.substack.com/p/my-llm-coding-workflow-going-into

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; Verification & review.

**In short.** Planning, scoped delegation and continuous checking outperform an unmanaged prompt-to-merge workflow as an engineering practice.

**Summary.** Osmani describes his own evolving approach to working with coding assistants: articulate a plan, provide repository context, implement bounded steps, execute tests and remain accountable for reviews and integration.

**Main findings / practitioner recommendations.** Start from a task brief and acceptance criteria; Review after each small increment; Distinguish personal workflow preference from measured performance gains.

**Book placement.** C04, §4.6. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W151 | W095 | W083.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O022 — 21 Lessons from 14 Years at Google

**Reference.** Osmani, Addy (2025-12-04). *21 Lessons from 14 Years at Google*. Elevate (Substack). https://addyo.substack.com/p/21-lessons-from-14-years-at-google

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; Skills & learning.

**In short.** Durable engineering effectiveness depends on solving user problems, judgment and collaboration beyond producing code.

**Summary.** Osmani shares lessons from his work at Google about user empathy, simplifying problems, team alignment and career growth. The lessons supply an organizational foundation for AI-assisted engineering without presenting direct evidence about coding agents.

**Main findings / practitioner recommendations.** Optimize for user outcomes instead of code volume; Preserve communication, shared understanding and professional judgment; Keep this as general engineering context.

**Book placement.** C11, §11.2. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W161 | W175 | W184.

**Limitation.** Career reflection; not original AI outcome research. CONTEXTUAL ONLY: this article does not evaluate AI-assisted development, agent behavior, or causal AI outcomes.

### O023 — Treat AI-Generated code as a draft

**Reference.** Osmani, Addy (2025-11-25). *Treat AI-Generated code as a draft*. Elevate (Substack). https://addyo.substack.com/p/treat-ai-generated-code-as-a-draft

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Verification & review; System knowledge & memory.

**In short.** AI-generated code should be treated as an untrusted draft and not merged without responsible understanding and verification.

**Summary.** This earlier essay stresses reading AI code closely so that humans connect implementation back to intent, testing and maintenance. Its strong line-by-line reading prescription is explicitly revised in the September 2026 "The Code Nobody Reads" essay, which advocates risk-tiered independent checking.

**Main findings / practitioner recommendations.** Verify AI output against requirements before acceptance; Record decision ownership; Document the change in the author’s proposed review policy over time.

**Book placement.** C08, §8.8. Role: CORE_CITED.

**Research comparisons (editorial only).** W067 | W069 | W154.

**Limitation.** Prescriptive practice subsequently qualified by the same author in September 2026.

### O024 — Critical Thinking during the age of AI

**Reference.** Osmani, Addy (2025-11-21). *Critical Thinking during the age of AI*. Elevate (Substack). https://addyo.substack.com/p/critical-thinking-during-the-age

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Skills & learning; Engineering structure.

**In short.** Critical questions about purpose, assumptions, context and evidence remain necessary when AI supplies plausible solutions.

**Summary.** Osmani organizes an engineering reasoning checklist around who, what, where, when, why and how. The article emphasizes problem definition, root-cause analysis and skepticism toward well-phrased AI output.

**Main findings / practitioner recommendations.** Ask what result is needed before asking for code; Require evidence for assumptions and fixes; Train developers to challenge generated explanations.

**Book placement.** C10, §10.5. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W117 | W118.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O025 — Conductors to Orchestrators: The Future of Agentic Coding

**Reference.** Osmani, Addy (2025-11-01). *Conductors to Orchestrators: The Future of Agentic Coding*. Elevate (Substack). https://addyo.substack.com/p/conductors-to-orchestrators-the-future

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; Jobs & roles.

**In short.** Developers are moving from guiding one agent toward coordinating multiple asynchronously executing agents.

**Summary.** The essay distinguishes a single-agent "conductor" role from an "orchestrator" that allocates work among parallel agents with isolated workspaces. It forecasts changes in the engineer’s day-to-day role while acknowledging tool maturity and coordination costs.

**Main findings / practitioner recommendations.** Isolate concurrent branches and agent responsibilities; Assign merge and conflict-resolution ownership; Treat role changes as a scenario to evaluate, not an established labor-market effect.

**Book placement.** C11, §11.2. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W002 | W027 | W152.

**Limitation.** Role forecasts and workflow examples, not validated hiring or productivity outcomes.

### O026 — Gemini CLI Tips & Tricks

**Reference.** Osmani, Addy (2025-10-21). *Gemini CLI Tips & Tricks*. Elevate (Substack). https://addyo.substack.com/p/gemini-cli-tips-and-tricks

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** What agents can do; System knowledge & memory.

**In short.** Command-line agent effectiveness depends on tool configuration, project context and deliberate execution controls.

**Summary.** A hands-on guide to Gemini CLI installation, task prompting, tool use and operational shortcuts. Its practical examples illustrate the capabilities and risks of agent access to shells, repositories and developer data.

**Main findings / practitioner recommendations.** Teach observable tool permissions and commands; Keep version-specific instructions separate from timeless engineering principles; Do not infer model superiority from a tips guide.

**Book placement.** C03, §3.2. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W191.

**Limitation.** Vendor-tool feature guide; installation flags and quotas may have changed since publication.

### O027 — How modern browsers work

**Reference.** Osmani, Addy (2025-09-13). *How modern browsers work*. Elevate (Substack). https://addyo.substack.com/p/how-modern-browsers-work

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure.

**In short.** Modern browsers coordinate networking, parsing, JavaScript execution, rendering, process isolation and security boundaries.

**Summary.** A broad walkthrough of modern browser internals, including navigation, parsing, JavaScript, GPU rendering, multiprocessing and sandboxing. It is not about AI-assisted engineering; its connection to the graph is contextual architecture literacy.

**Main findings / practitioner recommendations.** Use browser internals as a brownfield-comprehension teaching example; Distinguish runtime behavior from source-file appearance; Exclude it from AI-specific evidence claims.

**Book placement.** C05, §5.5. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** No defensible direct analogue assigned.

**Limitation.** General browser engineering explainer; no claims of AI development outcomes. CONTEXTUAL ONLY: this article does not evaluate AI-assisted development, agent behavior, or causal AI outcomes.

### O028 — Vibe coding is not the same as AI-Assisted engineering.

**Reference.** Osmani, Addy (2025-08-30). *Vibe coding is not the same as AI-Assisted engineering.*. Elevate (Substack). https://addyo.substack.com/p/vibe-coding-is-not-the-same-as-ai

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; Code quality & security.

**In short.** Fast conversational prototyping and accountable AI-assisted engineering are distinct development regimes.

**Summary.** Osmani distinguishes exploratory prompting from production practices with design documents, test-driven changes, review and ownership. He argues that treating either workflow as universally appropriate obscures the requirements of maintenance-intensive software.

**Main findings / practitioner recommendations.** Choose rigor appropriate to the target environment; Require explicit acceptance contracts for production work; Teach the transition from prototype to maintainable system.

**Book placement.** C04, §4.1. Role: CORE_CITED.

**Research comparisons (editorial only).** W045 | W050 | W151.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O029 — The reality of AI-Assisted software engineering productivity

**Reference.** Osmani, Addy (2025-08-16). *The reality of AI-Assisted software engineering productivity*. Elevate (Substack). https://addyo.substack.com/p/the-reality-of-ai-assisted-software

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Productivity; Economics.

**In short.** Perceived personal acceleration with coding AI does not necessarily translate into net team or release-level productivity.

**Summary.** The article synthesizes surveys and selected field studies showing variation by task, developer and codebase. It cautions against treating high adoption, code generation or self-reported speed as direct evidence of deployment throughput or organizational value.

**Main findings / practitioner recommendations.** Use task-adjusted and quality-adjusted metrics; Report study context before citing a percentage; Separate survey sentiment, experiments and shipped-value outcomes.

**Book placement.** C02, §2.5. Role: CORE_CITED.

**Research comparisons (editorial only).** W003 | W023 | W010.

**Limitation.** The percentages reported by Osmani come from diverse third-party surveys and experiments; no single pooled causal estimate is supplied. Any externally quoted benchmark, productivity or vendor telemetry requires independent verification of original method and population.

### O030 — Coding for the Future Agentic World

**Reference.** Osmani, Addy (2025-07-29). *Coding for the Future Agentic World*. Elevate (Substack). https://addyo.substack.com/p/coding-for-the-future-agentic-world

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** What agents can do; Engineering structure.

**In short.** CLI agents and background task runners extend software generation into tool-using, multi-step workflows, but require more oversight.

**Summary.** Osmani surveys emerging agentic tools and contrasts autocomplete, interactive assistants and agents that edit files, run commands, debug and propose pull requests. He argues that more capable execution increases the value of planning, context and final approval.

**Main findings / practitioner recommendations.** Teach capabilities with bounded task examples; Evaluate tool use and integration separately from model fluency; Retain explicit sandbox and final release authority.

**Book placement.** C03, §3.1. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W002 | W191.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O031 — Context Engineering: Bringing Engineering Discipline to Prompts

**Reference.** Osmani, Addy (2025-07-13). *Context Engineering: Bringing Engineering Discipline to Prompts*. Elevate (Substack). https://addyo.substack.com/p/context-engineering-bringing-engineering

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** System knowledge & memory; Engineering structure.

**In short.** Reliable prompts are assembled from selected system context, tools and constraints rather than crafted by wording alone.

**Summary.** The essay develops context engineering as information architecture: relevant files, architectural records, error logs, schemas, examples and acceptance constraints. It emphasizes curating high-signal context so a coding agent can act within repository realities.

**Main findings / practitioner recommendations.** Treat context as a versioned engineering input; Prefer relevant artifacts over exhaustive dumps; Verify provenance and freshness of retrieved context.

**Book placement.** C09, §9.6. Role: CORE_CITED.

**Research comparisons (editorial only).** W155 | W159 | W184.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O032 — The AI-Native Software Engineer

**Reference.** Osmani, Addy (2025-07-01). *The AI-Native Software Engineer*. Elevate (Substack). https://addyo.substack.com/p/the-ai-native-software-engineer

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Skills & learning; Engineering structure.

**In short.** An AI-native engineer integrates assistance into ordinary work while retaining domain expertise and continuous learning.

**Summary.** Osmani presents a practical skills playbook for pairing with coding assistants, delegating repetitive work and learning better tool use. The article is intentionally aspirational about possible productivity multiples rather than a controlled performance study.

**Main findings / practitioner recommendations.** Teach effective delegation alongside manual competence; Create deliberate skill-updating routines; Do not present advertised 2x–10x multipliers as validated general results.

**Book placement.** C10, §10.9. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W116 | W118 | W122.

**Limitation.** Prospective productivity multipliers are hypothetical and should not be cited as empirical measurements.

### O033 — The "Trust, But Verify" Pattern For AI-Assisted Engineering

**Reference.** Osmani, Addy (2025-06-09). *The "Trust, But Verify" Pattern For AI-Assisted Engineering*. Elevate (Substack). https://addyo.substack.com/p/the-trust-but-verify-pattern-for

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Verification & review; Engineering structure.

**In short.** Verification becomes the bottleneck when generation is cheap; every AI-produced change needs a justified check.

**Summary.** Osmani frames the assistant as a capable but fallible collaborator whose output must be tested and reviewed before adoption. The post translates automation-bias concerns into reviewer practices, guardrails and accountable sign-off.

**Main findings / practitioner recommendations.** Check against independent requirements and regression oracles; Record the outcome of manual and automated review; Teach why plausible code is not proof of correctness.

**Book placement.** C07, §7.2. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W067 | W077 | W093.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O034 — The Prompt Engineering Playbook for Programmers

**Reference.** Osmani, Addy (2025-05-27). *The Prompt Engineering Playbook for Programmers*. Elevate (Substack). https://addyo.substack.com/p/the-prompt-engineering-playbook-for

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; System knowledge & memory.

**In short.** Effective developer prompts state a bounded problem, relevant context, constraints and the expected verification method.

**Summary.** Through contrasting examples, Osmani demonstrates how explicit role, environment, scope, format and feedback loops can improve coding-assistant usefulness. The book can reuse the patterns as task-envelope teaching devices rather than treat prompt form as a substitute for formal specifications.

**Main findings / practitioner recommendations.** Provide concrete files and constraints with each request; Make successful output observable; Iterate with feedback instead of claiming prompt wording ensures reliability.

**Book placement.** C04, §4.3. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W151 | W077 | W148.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O035 — AI Won't Kill Junior Devs - But Your Hiring Strategy Might

**Reference.** Osmani, Addy (2025-05-10). *AI Won't Kill Junior Devs - But Your Hiring Strategy Might*. Elevate (Substack). https://addyo.substack.com/p/ai-wont-kill-junior-devs-but-your

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Jobs & roles; Skills & learning.

**In short.** Removing junior engineering positions can damage apprenticeship and the future pool of experienced maintainers.

**Summary.** Osmani argues that early-career roles must evolve toward debugging, system comprehension, collaboration and verification as assistants automate routine output. This is a workforce-development argument, not a causal demonstration that AI has or has not changed entry-level hiring.

**Main findings / practitioner recommendations.** Protect supervised learning opportunities for junior developers; Evaluate apprenticeship capacity alongside coding throughput; Compare hiring claims with primary labor-market studies.

**Book placement.** C12, §12.7. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W112 | W125 | W131.

**Limitation.** A prescriptive career and hiring essay; no original causal analysis of employment trends.

### O036 — Avoiding Skill Atrophy in the Age of AI

**Reference.** Osmani, Addy (2025-04-25). *Avoiding Skill Atrophy in the Age of AI*. Elevate (Substack). https://addyo.substack.com/p/avoiding-skill-atrophy-in-the-age

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Skills & learning; System knowledge & memory.

**In short.** Using AI to avoid every difficult step risks eroding the reasoning skills needed to supervise future AI output.

**Summary.** Osmani draws an analogy with other forms of cognitive offloading and recommends intentional debugging, independent implementation, explanation and review. The essay identifies a plausible risk, while the size and persistence of skill loss require empirical evaluation.

**Main findings / practitioner recommendations.** Maintain opportunities for unaided practice; Use delayed comprehension and transfer tests; Keep the analogy separate from evidence of measured developer skill decay.

**Book placement.** C10, §10.4. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W117 | W118 | W121.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O037 — Vibe Coding is not an excuse for low-quality work

**Reference.** Osmani, Addy (2025-04-18). *Vibe Coding is not an excuse for low-quality work*. Elevate (Substack). https://addyo.substack.com/p/vibe-coding-is-not-an-excuse-for

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Code quality & security; Engineering structure.

**In short.** Rapid AI prototyping does not exempt production changes from ordinary software quality obligations.

**Summary.** Osmani warns that easy generation can conceal bugs, weak design and unmaintainable dependencies. He urges standard review, architectural judgment, tests and security checks even when non-specialists can produce working prototypes.

**Main findings / practitioner recommendations.** Evaluate generated artifacts against system standards; Require a maintenance plan for promoted prototypes; Measure longer-run defects and complexity, not demo velocity.

**Book placement.** C05, §5.8. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W039 | W050 | W059.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O038 — What are AI Agents? why do they matter?

**Reference.** Osmani, Addy (2025-04-11). *What are AI Agents? why do they matter?*. Elevate (Substack). https://addyo.substack.com/p/what-are-ai-agents-why-do-they-matter

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** What agents can do; Engineering structure.

**In short.** An agent differs from one-shot model completion by using tools and feedback to pursue a goal over multiple steps.

**Summary.** The post offers an introductory description of agent perception, planning, tool use, action and iteration. It is useful for defining system boundaries and distinguishing model capability from the reliability of a surrounding task workflow.

**Main findings / practitioner recommendations.** Model agents as bounded goal-directed processes; Separate tool authority from language-model output; Require observable success and failure states.

**Book placement.** C03, §3.1. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W191 | W002 | W152.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O039 — Vibe Coding: Revolution or Reckless Abandon?

**Reference.** Osmani, Addy (2025-04-03). *Vibe Coding: Revolution or Reckless Abandon?*. Elevate (Substack). https://addyo.substack.com/p/vibe-coding-revolution-or-reckless

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Code quality & security; Skills & learning.

**In short.** Vibe coding can democratize prototypes while amplifying unnoticed security and maintainability risks.

**Summary.** Osmani discusses enthusiastic prompting with minimal code inspection and contrasts its accessibility with risks from incorrect assumptions, latent defects and insufficient operator understanding. The essay calls for professional checks as project consequence increases.

**Main findings / practitioner recommendations.** Separate creative prototyping from production acceptance; Add security and regression checks early; Train users to recognize the limits of superficial functional demos.

**Book placement.** C05, §5.1. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W045 | W046 | W050.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O040 — MCP: What It Is and Why It Matters

**Reference.** Osmani, Addy (2025-03-27). *MCP: What It Is and Why It Matters*. Elevate (Substack). https://addyo.substack.com/p/mcp-what-it-is-and-why-it-matters

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** What agents can do; Code quality & security.

**In short.** The Model Context Protocol standardizes agent access to external resources and tools, increasing integration reach and the importance of permission controls.

**Summary.** An accessible explanation of MCP clients, servers and tool interoperability, including opportunities for richer context. For the book it illustrates the distinction between a convenient integration protocol and the authorization, sandbox and trust decisions the protocol cannot solve alone.

**Main findings / practitioner recommendations.** Teach interface contracts separately from access policy; Review external tool descriptions as untrusted input; Constrain secrets, scopes and side-effecting calls.

**Book placement.** C06, §6.7. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W053 | W060.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O041 — Leading Effective Engineering Teams in the Age of GenAI

**Reference.** Osmani, Addy (2025-03-19). *Leading Effective Engineering Teams in the Age of GenAI*. Elevate (Substack). https://addyo.substack.com/p/leading-effective-engineering-teams-c9b

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; Skills & learning.

**In short.** Engineering leaders should define outcome quality, train teams and make human verification a normal part of AI adoption.

**Summary.** Osmani translates AI tool introduction into management duties: agree on what "better" means, avoid dependency on apparent speed, establish review expectations and support developer upskilling. It functions as organizational guidance rather than measured intervention.

**Main findings / practitioner recommendations.** Publish an explicit AI contribution policy; Allocate capacity for capability development and review; Evaluate delivery quality and learning, not generated-line counts.

**Book placement.** C11, §11.3. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W147 | W149 | W150.

**Limitation.** Practitioner interpretation; not primary experimental evidence.

### O042 — Beyond the 70%: Maximizing the human 30% of AI-assisted coding

**Reference.** Osmani, Addy (2025-03-13). *Beyond the 70%: Maximizing the human 30% of AI-assisted coding*. Elevate (Substack). https://addyo.substack.com/p/beyond-the-70-maximizing-the-human

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Skills & learning; Productivity.

**In short.** The difficult last-mile work in AI-assisted development remains architecture, requirements, integration and verification.

**Summary.** Expanding his 2024 "70% problem" framing, Osmani discusses the durable value of engineers who can interpret behavior, handle edge cases and maintain systems. The percentages are rhetorical heuristics for relative task difficulty, not tested ratios of project completion.

**Main findings / practitioner recommendations.** Distinguish generated scaffold from production-ready change; Teach system-level debugging and design; Avoid quoting 70/30 as a measured software engineering constant.

**Book placement.** C10, §10.9. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W117 | W154 | W010.

**Limitation.** The 70/30 split is a practitioner metaphor and is not independently measured in this essay.

### O043 — Applied "Software Engineering at Google"

**Reference.** Osmani, Addy (2025-03-06). *Applied "Software Engineering at Google"*. Elevate (Substack). https://addyo.substack.com/p/applied-software-engineering-at-google

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure; Verification & review.

**In short.** Testing, review, documentation and sustainable ownership are established software-engineering practices that remain useful with AI-generated code.

**Summary.** Osmani adapts lessons from the public Software Engineering at Google book, including tests that make change safer, code review and organizational learning. It supplies historical engineering principles, not direct evidence that an AI technique is effective.

**Main findings / practitioner recommendations.** Reuse established tests-and-change reasoning; Distinguish well-founded engineering precedent from measured agent performance; Use as contextual support for governance.

**Book placement.** C07, §7.4. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W064 | W161 | W173.

**Limitation.** Expository synthesis of an existing software engineering book, not original AI research. CONTEXTUAL ONLY: this article does not evaluate AI-assisted development, agent behavior, or causal AI outcomes.

### O044 — Speech-to-Code: Vibe Coding with Voice

**Reference.** Osmani, Addy (2025-02-28). *Speech-to-Code: Vibe Coding with Voice*. Elevate (Substack). https://addyo.substack.com/p/speech-to-code-vibe-coding-with-voice

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** What agents can do; Productivity.

**In short.** Voice input changes how developers express tasks to coding assistants but does not remove the need to verify resulting software.

**Summary.** Osmani demonstrates dictating instructions into an AI coding workflow using speech tools and describes personal ergonomic and velocity benefits. The improvement is experiential; no controlled comparison of input methods or final code quality is provided.

**Main findings / practitioner recommendations.** Teach modality-independent task specification; Evaluate accessibility and ergonomics separately from correctness; Do not extrapolate a personal speedup to all teams.

**Book placement.** C01, §1.2. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W002.

**Limitation.** First-person tool demonstration without measured comparative productivity.

### O045 — Personal Software: The Unbundling of the Programmer?

**Reference.** Osmani, Addy (2025-02-09). *Personal Software: The Unbundling of the Programmer?*. Elevate (Substack). https://addyo.substack.com/p/personal-software-the-unbundling

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Economics; Jobs & roles.

**In short.** Lower creation costs may expand demand for one-off and personal applications, an economic hypothesis distinct from measured productivity or employment effects.

**Summary.** Osmani explores a world in which individuals and domain specialists build small personalized applications too narrow to justify traditional development contracts. The claim is about enabling software that previously would not be built at all. It is a forward-looking long-tail demand scenario, not a measured labor substitution, return-on-investment or full lifecycle cost study.

**Main findings / practitioner recommendations.** Separate prototype creation cost from lifecycle cost; Evaluate new demand and substitution scenarios independently; Mark market forecasts as hypotheses.

**Book placement.** C12, §12.8. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W145.

**Limitation.** Forward-looking economic scenario; no primary adoption or welfare evaluation. Framework or market hypothesis is an authored practitioner proposal, not an empirically validated scale or intervention.

### O046 — Why I use Cline for AI Engineering

**Reference.** Osmani, Addy (2025-01-30). *Why I use Cline for AI Engineering*. Elevate (Substack). https://addyo.substack.com/p/why-i-use-cline-for-ai-engineering

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** What agents can do; System knowledge & memory.

**In short.** Cline illustrates how a tool-using coding assistant differs from a conventional completion engine through its context and environment access.

**Summary.** Osmani offers a first-person comparison of coding assistants, favoring Cline for file, terminal, browser and debugging workflows while acknowledging trade-offs. The post was updated in July 2025; its feature and product assessments are time-specific.

**Main findings / practitioner recommendations.** Classify assistant capabilities by observable tools and permissions; Evaluate cost and context visibility on representative tasks; Treat personal vendor preferences as dated, not benchmark evidence.

**Book placement.** C03, §3.2. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W002 | W191.

**Limitation.** Subjective tool review, updated 2025-07-21; product comparisons are not controlled benchmarks.

### O047 — AI-Driven Prototyping: v0, Bolt, and Lovable Compared

**Reference.** Osmani, Addy (2025-01-11). *AI-Driven Prototyping: v0, Bolt, and Lovable Compared*. Elevate (Substack). https://addyo.substack.com/p/ai-driven-prototyping-v0-bolt-and

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** What agents can do; Engineering structure.

**In short.** AI prototyping services reduce time from concept to demonstrable app but vary in architecture, control and production suitability.

**Summary.** The essay compares v0, Bolt and Lovable for common proof-of-concept workflows, noting different strengths in UI scaffolding and fuller application assembly. It distinguishes product exploration from subsequent testing, maintainability and integration work.

**Main findings / practitioner recommendations.** Choose tools by intended artifact and handoff needs; Budget refactoring and testing after a prototype; Do not treat a point-in-time vendor comparison as a reproducible benchmark.

**Book placement.** C03, §3.3. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W002 | W191.

**Limitation.** Practitioner tool comparison; tool features have evolved since early 2025.

### O048 — Future-proofing your Software Engineering career

**Reference.** Osmani, Addy (2024-12-23). *Future-proofing your Software Engineering career*. Elevate (Substack). https://addyo.substack.com/p/future-proofing-your-software-engineering

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Skills & learning; Jobs & roles.

**In short.** Career resilience in AI-assisted software engineering rests on adaptable domain expertise, systems judgment and learning.

**Summary.** Osmani surveys the tasks models can automate and emphasizes software architecture, evaluation, product understanding and the ability to learn new techniques. Predictions about changing roles are presented as guidance, not labor-market identification.

**Main findings / practitioner recommendations.** Build a transferable engineering-skills portfolio; Practice validating and integrating AI work; Separate career advice from measured employment effects.

**Book placement.** C10, §10.9. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** W118 | W122 | W135.

**Limitation.** Career advice and forecasts, not original labor-market empirical research.

### O049 — The 70% problem: Hard truths about AI-assisted coding

**Reference.** Osmani, Addy (2024-12-04). *The 70% problem: Hard truths about AI-assisted coding*. Elevate (Substack). https://addyo.substack.com/p/the-70-problem-hard-truths-about

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Productivity; Code quality & security.

**In short.** Getting a prototype mostly implemented with AI is far easier than completing the remaining integrations and engineering assurances.

**Summary.** Osmani contrasts fast "zero-to-MVP" generation with difficult iteration, debugging and production readiness in realistic codebases. His memorable 70% phrasing is descriptive and experiential, not a controlled measurement of task success.

**Main findings / practitioner recommendations.** Measure end-to-end shipping and rework instead of scaffolding speed; Identify integration and maintenance as separate work; Preserve the heuristic character of the percentage.

**Book placement.** C02, §2.5. Role: CORE_CITED.

**Research comparisons (editorial only).** W004 | W010 | W055.

**Limitation.** The 70% estimate is an anecdotal framing, not a validated quantitative benchmark.

### O050 — User-centric engineering.

**Reference.** Osmani, Addy (2024-11-15). *User-centric engineering.*. Elevate (Substack). https://addyo.substack.com/p/user-centric-engineering

**Source type.** Practitioner analysis and technical commentary; not a peer-reviewed experimental study.

**Thematic stream(s).** Engineering structure.

**In short.** Customer needs and observable outcomes—not lines of code—should determine whether an engineering change succeeds.

**Summary.** Osmani argues that engineering decisions should start with user needs and observable benefit rather than technical elegance. He offers questions to ask before development, during iterative implementation and after launch, supported by practices such as support-ticket analysis, behavioral observation, interviews and product feedback. The article does not evaluate AI coding systems.

**Main findings / practitioner recommendations.** Start with a concrete user problem and a user-observable success criterion; Validate design trade-offs through user interviews, usage data, and support feedback; Use only as background product engineering context, not as evidence of AI productivity.

**Book placement.** C01, §1.1. Role: GRAPH_ONLY_OR_BACKGROUND.

**Research comparisons (editorial only).** No defensible direct analogue assigned.

**Limitation.** General user-experience and product principles, no original AI evaluation. CONTEXTUAL ONLY: this article does not evaluate AI-assisted development, agent behavior, or causal AI outcomes.

