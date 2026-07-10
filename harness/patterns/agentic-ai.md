# Agentic-AI Patterns

The reusable catalogue of agentic design patterns — generic engineering doctrine, not a project's design. The spec-writer picks the minimal set a project actually needs and records the concrete composition in [`spec/agent.md`](../../spec/agent.md), citing the patterns chosen here. Prefer the simplest pattern that works: do not reach for multi-agent when a single tool-use loop suffices.

---

### 1. Prompt Chaining
**What** — Decompose a task into a fixed sequence of LLM steps, each consuming the prior step's output.
**When** — Choose when the task has clear, ordered sub-steps; avoid when steps are independent (parallelize) or branch by input (route).
**Example** — Draft outline → expand each section → copy-edit the assembled document.

### 2. Routing
**What** — A classifier or router directs each input to the right specialized handler or prompt.
**When** — Choose when inputs fall into distinct categories needing different handling; avoid when one prompt handles all cases well.
**Example** — Triage a support ticket to the billing, technical, or account-management sub-agent.

### 3. Parallelization
**What** — Run independent subtasks concurrently (sectioning), or sample the same task multiple times and aggregate (voting).
**When** — Choose to cut latency on independent work or raise reliability via consensus; avoid when steps depend on each other.
**Example** — Score a document against five rubric criteria at once, then merge the scores.

### 4. Reflection
**What** — The agent critiques and revises its own output before finalizing (self-review / critic loop).
**When** — Choose for quality-sensitive output where a second pass measurably helps; avoid on simple tasks — it adds a full extra round-trip.
**Example** — Generate code, run a self-review pass for bugs and edge cases, then emit the fixed version.

### 5. Tool Use (Function Calling)
**What** — The LLM calls external tools, APIs, or functions to act in the world and fetch live data.
**When** — Choose whenever the task needs real data, side effects, or computation the model can't do reliably; avoid when the answer is fully in-context.
**Example** — Call a weather API and a calendar API to propose meeting times around clear-sky windows.

### 6. Planning
**What** — The agent generates an explicit multi-step plan before acting, then executes the steps.
**When** — Choose for complex, multi-step goals where order and dependencies matter; avoid for single-shot tasks where planning is overhead.
**Example** — "Migrate this service to v2" → produce a numbered plan, then carry out each step.

### 7. Multi-Agent Collaboration
**What** — Multiple specialized agents with distinct roles coordinate to complete a task.
**When** — Choose when roles genuinely differ and separation improves quality or isolation; avoid when one agent with tools would do — it multiplies cost and latency.
**Example** — Researcher gathers sources, writer drafts, editor critiques, in a shared workflow.

### 8. Memory Management
**What** — Maintain short-term (context window) and long-term (vector store / database) memory across turns and sessions.
**When** — Choose when the agent must recall prior context or personalize; avoid persistent memory for stateless, single-shot tasks.
**Example** — A coding assistant recalls the user's stack preferences from earlier sessions.

### 9. Learning and Adaptation
**What** — The agent improves over time from feedback, examples, or observed outcomes.
**When** — Choose when behaviour should evolve with usage and you can capture a feedback signal; avoid when fixed behaviour is required or auditable determinism matters.
**Example** — Re-rank suggestions based on which past recommendations the user accepted.

### 10. Model Context Protocol (MCP)
**What** — A standardized protocol for exposing tools, data, and context to models and agents.
**When** — Choose to integrate external tools/data through a common interface and reuse servers across agents; avoid the overhead for one bespoke in-process tool.
**Example** — Connect the agent to a GitHub MCP server to read issues and open pull requests.

### 11. Goal Setting and Monitoring
**What** — Define explicit goals and success metrics, then track progress against them during execution.
**When** — Choose for long-running or autonomous tasks needing a stopping condition; avoid when success is a single obvious end-state.
**Example** — "Reach 90% test coverage" — the agent measures coverage after each change and continues until met.

### 12. Exception Handling and Recovery
**What** — Detect failures (tool errors, malformed output) and retry, fall back, or degrade gracefully.
**When** — Choose for any agent touching unreliable tools or external systems — i.e. nearly all production agents; rarely omit.
**Example** — On an API timeout, retry with back-off, then fall back to a cached result.

### 13. Human-in-the-Loop
**What** — Insert human approval or correction at high-stakes or low-confidence decision points.
**When** — Choose for irreversible, costly, or sensitive actions, and below a confidence threshold; avoid where it would bottleneck high-volume routine work.
**Example** — Pause for human sign-off before sending a refund over $500.

### 14. Knowledge Retrieval (RAG)
**What** — Retrieve relevant external knowledge and ground the LLM's response in it.
**When** — Choose when answers depend on a corpus larger than the context window or on fresh/proprietary facts; avoid when knowledge is small enough to keep in-prompt.
**Example** — Answer policy questions by retrieving the matching sections of the employee handbook.

### 15. Inter-Agent Communication (A2A)
**What** — Agents exchange messages and results through a defined protocol or shared channel.
**When** — Choose when multiple agents (often across boundaries) must coordinate via structured messages; avoid for in-process agents that can share state directly.
**Example** — A scheduling agent negotiates a slot with a separate calendar agent over a message protocol.

### 16. Resource-Aware Optimization
**What** — Manage cost, latency, and token budgets via model tiering, caching, and truncation.
**When** — Choose at scale or under tight latency/cost limits; avoid premature tuning before a real budget pressure appears.
**Example** — Route easy queries to a small model and escalate only hard ones to the large model.

### 17. Reasoning Techniques
**What** — Structured reasoning strategies: chain-of-thought, ReAct, tree/graph-of-thought, self-consistency.
**When** — Choose for problems where explicit intermediate reasoning improves accuracy; avoid on simple lookups where it only burns tokens.
**Example** — Use ReAct (reason → act → observe) so the agent interleaves thinking with tool calls.

### 18. Guardrails / Safety Patterns
**What** — Input/output validation, content filtering, constraint enforcement, and jailbreak defense.
**When** — Choose whenever inputs are untrusted or outputs are user-facing or acted upon — effectively always in production.
**Example** — Validate the model's JSON against a schema and reject responses containing disallowed content.

### 19. Evaluation and Monitoring
**What** — Offline evals plus production observability — traces, metrics, and LLM-as-judge scoring.
**When** — Choose for any agent you intend to ship and iterate on; skip only for throwaway prototypes.
**Example** — Run a regression eval set on each prompt change and trace live runs for latency and failures.

### 20. Prioritization
**What** — The agent ranks or orders competing tasks, goals, or tool calls by importance and urgency.
**When** — Choose when more work exists than can be done at once and ordering matters; avoid when there is a single task or a fixed order.
**Example** — A task agent works the highest-impact, soonest-due item from its backlog first.

### 21. Exploration and Discovery
**What** — The agent explores an open-ended space through search and experimentation rather than a fixed path.
**When** — Choose when the solution space is unknown and must be discovered; avoid when the procedure is known — just execute it.
**Example** — A research agent branches across queries and sources to map an unfamiliar topic.

### 22. LLM-Generated Code Execution
**What** — For dynamic questions over structured data, the LLM writes executable code and the system runs it with the data in scope.
**When** — Any capability where users ask arbitrary, open-ended questions about data. **Anti-pattern:** a hardcoded op-list the LLM maps questions onto — fails silently when inputs don't match or the list lacks a primitive. Always generate executable code, never a rigid op-list interpreter.

---

## Choosing patterns

**The default architecture is a ReAct loop.** Unless the task is a single deterministic transform with no branching, the baseline for "an agent" is a **ReAct loop** (#17 + #5): **reason → act via a tool → observe → repeat until done** — wrapped with guardrails (#18) and observability (#19) always on. That is the floor, not a single-shot `prompt → answer`. A linear prompt chain (#1) is a step *down* from this floor — pick it only when there are genuinely no tools and no branching.

- **Start at ReAct, not below it.** A tool-use loop with good prompts and structured logging is the smallest *real* agent. Wire it in Phase 1 and measure.
- **Reach up only on a concrete need.** Planning (#6), reflection (#4), multi-agent (#7), and heavy reasoning add latency and cost — upgrade them in Phase 4, never up front.
- **Reach down only when there are no tools.** If the task is a fixed transform with no actions to take, a prompt chain (#1) or a single call is correct — don't bolt a loop onto a one-shot.
- **Compose deliberately.** Patterns stack (e.g. planning + tool use + reflection); keep the set minimal and the data flow between them explicit.

The chosen composition for **this** project — which patterns, wired how — is documented in [`spec/agent.md`](../../spec/agent.md).
