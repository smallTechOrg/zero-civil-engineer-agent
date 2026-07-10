---
name: zero-shot-build
description: Turn a zero-shot idea into a perfectly-working, thoroughly-tested, spec-driven agent. One intake round (which also collects the API keys into .env), then the agent-builder builds one phase at a time — autonomous within a phase, with a human testing gate between phases. Also used to add a new capability to an existing agent.
argument-hint: [your idea]
disable-model-invocation: true
allowed-tools: Bash(git*) Bash(gh*)
---

You run the human channel — intake, then the testing gate at every phase boundary — and hand the building off to the **agent-builder** orchestrator. The idea is in `$ARGUMENTS`. **If `$ARGUMENTS` is empty, ask the user in plain text to describe their idea / the problem they want to solve, and WAIT for their free-text reply before doing anything else.** Do NOT load `AskUserQuestion` to solicit, suggest, or pick the idea — the idea must come from the user as their own text. Only once you have the idea do you move to Stage 1 intake. Goal: **one prompt → a perfectly-working, thoroughly-tested agent, one user-testable phase at a time.**

**Autonomy model:** autonomous *within* a phase; a **human testing gate between phases**. Intake is the only interactive SETUP step; after it, agent-builder builds a phase end-to-end without pausing, then returns a test-handoff. You present the handoff, handhold the user through testing, and only proceed to the next phase on the user's go. agent-builder pauses mid-phase only on a hard blocker (e.g. a required key still missing from `.env`).

## Stage 1 — Intake (the only interactive setup step)

Intake has **two fixed sections and a variable middle**:

1. **Product rounds (variable, minimum 5)** — all product questions, progressively deeper. You keep going until you have resolved every dimension that would force a design decision in Phase 1. Five rounds is the floor; complex ideas may need 6, 7, or more. Each round covers a different dimension and must not repeat covered ground.
2. **Technical round (fixed, always last)** — one round of build-blockers only (LLM provider, stack, access method).

All rounds use `AskUserQuestion`; the API key prompt is the only additional manual step.

**How to decide when to stop product rounds:** After each round, ask: *"Is there any dimension — interaction model, state/memory, features, constraints, edge cases, observability, integrations — that, if left unresolved, would force spec-writer to guess?* If yes: write another product round on that dimension. If no: move to the technical round. Err on the side of one more round rather than handing off an ambiguous brief.

**The golden rule: Phase 1 is the smallest user-testable quick win.** Richer intake sharpens *which* slice to build first — it does not license a bigger Phase 1. More rounds ≠ bigger scope; it means better-scoped scope.

**Precondition: you already have the user's idea as their own free text** (from `$ARGUMENTS` or the plain-text prompt above). Never use `AskUserQuestion` to generate or propose the idea itself.

**The cardinal rule across ALL five rounds: every question and every option must be specific to THIS idea.** After Round 1 you know the idea category — use it. For a data analyst agent, Round 2 options should be things like "persistent sessions with conversation history" and "multi-file joins across uploaded datasets" — not generic buckets like "stateful" or "multi-entity". A user must instantly recognise every option as being about their thing. Generic options are a failure.

---

### Round 1 — What is the idea? (4 questions)

1. Acknowledge the idea in one sentence.
2. Load the question tool: `ToolSearch` with query `select:AskUserQuestion`.
3. Ask **4 questions** via `AskUserQuestion`, all `multiSelect: true`. Plain, friendly language — no technical jargon. Pure product questions.

   Four themes — adapt wording and all options to the idea:
   - **What it works on** *(4 idea-specific options)* — the data, content, or domain it processes. Be concrete: not "documents" but "CSV exports from our CRM", "raw survey responses", "GitHub PR diffs".
   - **What it produces** *(4 idea-specific options)* — the output or action it delivers. Be concrete: not "a result" but "an interactive chart I can explore", "a ranked list with reasons", "a cleaned file ready to re-upload".
   - **Usage pattern** *(4 options)* — who uses it, how often, in what context. E.g. "Just me, a few times a day", "My whole team on-demand", "Runs automatically on a trigger", "Our customers use it directly".
   - **Non-negotiables** *(4 options)* — always offer at least: "My data can't leave my machine / this server", "Keep costs very low", "Must connect to [something they mentioned]", "None — just build it well".

---

### Round 2 — How users interact (4 questions)

4. Read Round 1 answers carefully. You now know the idea category (data analysis, email triage, code review, etc.). Write ALL questions and ALL options for this round as if you are a product designer who has used tools exactly like this.
5. Load `AskUserQuestion`. Ask **4 questions**, all `multiSelect: true`. Cover these four interaction-model dimensions — all options must be specific to the idea:

   - **Session model** — how long does one "conversation" last? E.g. for a data analyst agent: "I upload a file, ask one question, done", "I upload once and ask many questions in a session", "I return to the same dataset across multiple days", "It runs automatically and I review results".
   - **Memory & state** — what should carry across turns or sessions? E.g. for a data analyst agent: "The conversation history (what I asked before)", "The uploaded datasets stay loaded", "Derived/cleaned datasets I created during the session", "A global context I can annotate (column descriptions, business rules)", "Nothing — fresh start every time".
   - **Multi-item handling** — does it work with one thing at a time or many? E.g. for a data analyst agent: "One file at a time", "Multiple files I can join or compare", "A folder of related files treated as one dataset", "It picks the right file automatically from my library".
   - **When things go wrong** — what should it do when it can't answer confidently? E.g. for a data analyst agent: "Ask me a clarifying question before running", "Give me its best guess and flag the uncertainty", "Show me what it tried and where it got stuck", "Retry with a different approach automatically".

   **Skip any question if Round 1 already answered it.** Do not ask for information you already have.

---

### Round 3 — Feature depth (4 questions)

6. Read Rounds 1–2. You now know what the agent processes and how users interact with it. This round uncovers what makes the agent genuinely powerful vs. a toy. Write ALL options as idea-specific concrete features — not abstract categories.
7. Load `AskUserQuestion`. Ask **4 questions**, all `multiSelect: true`. Cover these four feature-depth dimensions:

   - **Analysis / reasoning depth** — how hard should it work on each request? E.g. for a data analyst agent: "Fast answer — one LLM call, no iteration", "Multi-step reasoning — tries code, sees result, tries again", "Iterative until it finds the right answer (up to N steps)", "Plans a full analysis strategy before executing".
   - **Output richness** — what forms should results take? E.g. for a data analyst agent: "Plain text answer with key numbers", "Interactive charts I can zoom and filter", "A summary table alongside the prose", "An exportable file (CSV, cleaned dataset, report)".
   - **Proactive intelligence** — should it do anything without being asked? E.g. for a data analyst agent: "No — only answers what I ask", "Suggests 2–3 follow-up questions after each answer", "Flags anomalies or data-quality issues it notices while answering", "Auto-profiles a new dataset when I upload it".
   - **Integration surface** — what else does it connect to or produce for? E.g. for a data analyst agent: "Standalone — no integrations needed", "Saves derived/cleaned datasets back to my library", "Exports to Slack / email / dashboard", "Embeds in our existing data tool".

   **Skip any question if already answered.** Do not repeat covered ground.

---

### Round 4 — Constraints & scale (3 questions)

8. Read Rounds 1–3. This round surfaces hard constraints that would invalidate a design decision if missed. Write ALL options as specific, concrete limits — not vague categories.
9. Load `AskUserQuestion`. Ask **3 questions**, all `multiSelect: true`:

   - **Data scale & performance** — how much data and how fast? E.g. for a data analyst agent: "Small files, a few MB, latency doesn't matter", "Up to 100 MB CSVs, answer in under 30s", "Millions of rows — needs sampling or streaming", "Multiple users querying concurrently".
   - **Privacy & data residency** — where can data go? Options: "Everything must stay on my machine / our server (no cloud LLM API calls)", "LLM API calls are OK but raw data rows must never leave", "Cloud storage and APIs are fine", "We have compliance requirements (SOC 2, GDPR, HIPAA)".
   - **Reliability bar** — what's the quality/trust bar? Options: "Experimental / prototype — imperfect answers OK", "Production-ready — I'll act on the answers", "Needs an audit trail of what the agent did and why", "Needs access control — different users see different data".

---

### Round 5 — Observability, trust & transparency (3–4 questions)

10. Read Rounds 1–4. This round covers what users need to see in order to trust and debug the agent — often skipped but critical for agents that users depend on.
11. Load `AskUserQuestion`. Ask **3–4 questions**, all `multiSelect: true`:

    - **Reasoning visibility** — should users see how the agent reached its answer? E.g. for a data analyst agent: "No — just show me the answer", "Show me the code it ran (collapsible)", "Show me each step — what it tried, what failed, what worked", "Show me the full reasoning chain".
    - **Usage & cost awareness** — should users know what the agent is spending? E.g. for a data analyst agent: "No — hide this", "Show tokens used per query", "Show estimated cost per query", "Show a running daily total".
    - **Agent health & progress** — should users see the agent working? E.g. for a data analyst agent: "Just a spinner is fine", "Show a step counter (Step 3 of 6)", "Show a progress bar + elapsed timer", "Stream partial answers as they arrive".
    - **Logging & audit** — how much should be recorded server-side? E.g.: "Nothing persistent", "Log each query and answer to a file", "Store full run history in the database with timestamps", "Full audit trail: who asked what, what code ran, what result was stored".

---

### Additional product rounds (as many as needed)

After Round 5, check: *"Is there any dimension that would force spec-writer to guess?"* If yes, write another product round on that exact dimension. Common dimensions that spill over:

- **Edge cases & error handling** — what happens when input is malformed, the LLM is wrong, an integration fails, or the user asks something outside scope?
- **Collaboration & sharing** — single user, shared team workspace, or multi-tenant with isolation?
- **Output lifecycle** — are results ephemeral (session-only) or persistent (saved, versioned, exportable)?
- **Onboarding & defaults** — first-run experience, example data, guided tours, sensible defaults vs. full configuration?
- **Specific feature trade-offs** — any remaining capability choice (e.g. "auto-profile on upload or on demand?", "clarification gate before every query or only on ambiguity?") that would produce a meaningfully different Phase 1.

Keep going until the brief you'll write in the synthesis step would let spec-writer fill every capability file without a single guess.

---

### Technical round — What do we need to build it? (3–4 questions, always last)

Read all prior rounds. Now ask the **technical build questions** — only genuine blockers, 3–4 total:
- **LLM provider** *(single-select)* — offer: **Anthropic (API key)**, **Gemini (API key)**, **OpenRouter (any model)**, **Other / self-hosted**. This drives which key the user sets.
- **Stack preference** — language, database? ("No preference" → Python + SQLite defaults for local/prototype tools, PostgreSQL for production-grade, documented as assumptions.)
- **How will they access it?** — Web UI in a browser, CLI in the terminal, REST API, scheduled/automated job. Drives whether to build a frontend.
- **One follow-up** from prior rounds only if something would force a mid-build pause — skip if everything is clear.

**API key** (the only manual user step). Read `.env` and check whether the key for the chosen provider is already set (non-empty): `AGENT_ANTHROPIC_API_KEY`, `AGENT_GEMINI_API_KEY`, or `AGENT_OPENROUTER_API_KEY` (for **Other**, ask which env var + base URL). If present and non-empty, skip silently. Only if missing or empty, tell the user to set it in `.env` (from `.env.example`) and wait for confirmation. Never echo, print, paste, or commit a secret value.

**Synthesis brief**: write a **2–3 paragraph brief** covering: what the agent does and who uses it; the core interaction model (session shape, memory/state, multi-item handling); the key capabilities and features (analysis depth, output forms, proactive behaviours, edge-case handling, integrations, observability); the hard constraints (scale, privacy, reliability bar); and the technical stack and access model. Name the one core path for Phase 1 explicitly — the single most important thing a user does that proves the idea. ("Just build it" → narrow MVP, Python + SQLite defaults, documented as assumptions.)

## Stage 2 — Design + scaffold + build Phase 1 (delegate)

Invoke the **agent-builder** sub-agent once with the brief and the populated `.env`. Tell it to run, in order, and return the **Phase-1 test-handoff**:

- **DESIGN** — spec-writer writes the full spec: vision/capabilities, `spec/architecture.md` (incl. the `## Stack` section), `spec/agent.md` (if a framework is chosen), and the phased plan in `spec/roadmap.md` under "## Phases of Development" (per phase: Goal · independent slices · key surfaces/files · the exact runnable Gate command · how the user tests it).
- **SCAFFOLD** — branch `feature/<slug>-v0.1`, project dirs, `.env.example`, first commit + push, open the PR.
- **BUILD PHASE 1** — fan out generators per independent slice in parallel, gate each slice with qa-auditor, then return the Phase-1 test-handoff and STOP.

Relay only the hard blockers it escalates (e.g. a required key still missing from `.env`).

## Stage 3 — Human testing gate (you own the human channel)

Phase 1 is the smallest working win: real on the one core path, with clearly-labelled non-functional stubs for everything coming later. **Spoon-feed the user: the ONLY things they should ever do by hand are (a) put secrets in `.env` and (b) interact with the running app (click / chat). They must never run a terminal command to test.** You own the gate, the server lifecycle, and re-invocation:

1. **Launch the server** (you own this — agent-builder does NOT start it; sub-agent background processes are cleaned up on return). The handoff includes the project root path + run command. In order from the project root:
   a. If the phase has a frontend slice: `cd frontend && pnpm build && cd ..`
   b. If the phase has migrations: `uv run alembic upgrade head`
   c. `uv run python -m src` with `run_in_background: true`
   d. Health-check with retry: `for i in {1..10}; do curl -sf http://localhost:8001/health && break || sleep 2; done` — wait for the server before presenting the gate. If it never responds → route immediately to qa-auditor (boot failure), do not present the URL.
2. Load the question tool: `ToolSearch` with query `select:AskUserQuestion` (before asking).
3. Present the handoff as **phase release notes**: the live URL, what was built this phase, what to click / type / look at, the expected result, which parts are clearly-labelled stubs vs real (a stub must never read as a bug), and what the next phase adds. No run commands in the handoff — the app is already serving.
4. Ask via `AskUserQuestion` (two questions in one call):
   - *"Is the app loading at [URL]?"* → **"Yes, I can see it"** / **"No — error or blank page"**
   - *"Your verdict?"* (multiSelect) → **"It works well"** / **"Output isn't right"** / **"UI feels off"** / **"Something is broken"**
5. Route on their answers:
   - App didn't load → qa-auditor (boot failure), fix, re-present.
   - Any negative verdict → capture what they saw, then delegate to **zero-shot-fix** — pass the user's description, the phase context, the live URL, and any qa-auditor diagnosis already in context (file:line + SPEC/CODE classification) so it can skip re-diagnosis. It owns diagnose → fix → verify → commit + push autonomously, using the **scoped gate** for small CODE fixes (qa-auditor verifies only the changed surface + a real-key smoke call — not the full suite/E2E). When it returns VERIFIED, rebuild + restart the running app and **re-present** the gate. Loop until satisfied.
   - Positive only → **"Ready for Phase 2?"** → **"Yes, let's go"** / **"One more thing first"**. "One more thing" → route as negative above. "Yes" → Stage 4.

## Stage 4 — Per remaining phase (build → gate, repeat)

For EVERY remaining phase boundary:

1. Invoke **agent-builder** again — **one phase per invocation** — passing the user's feedback from the prior gate. It wires the relevant stubs into real functionality, fanning out generators per independent slice in parallel and gating each with qa-auditor, then returns that phase's test-handoff and STOPS.
2. Run the **Stage 3 human testing gate** again for this phase.

Repeat until no phases remain.

## Stage 5 — Ship + report

1. **qa-auditor** — final whole-tree drift audit (CLEAN). Route any divergence per Stage 3 and re-verify.
2. **agent-builder** — ensure the final state is pushed and the PR body is current.
3. Summarize for the user: what was built, the **live URL it's running at** (keep it serving), what's deferred, and the PR link. Run commands belong in the README for the record — not as something the user must execute to test.

## Adding a capability to an existing agent

If the spec is already filled in and the user is adding a capability: skip the scope intake; confirm the existing `.env` already holds the needed keys and ask only if the new capability requires a new provider/key. Tell agent-builder to run **spec-writer** (it owns architecture + roadmap now: add the capability to the spec and append an incremental phase to `spec/roadmap.md`, self-reviewed) → fan out the **frontend/backend generators** per slice → gate with qa-auditor. Then run the **human testing gate** on the new phase, same as any other.
