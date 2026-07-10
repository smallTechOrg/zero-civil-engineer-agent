# AI Agent Rules

**These rules apply to every Claude Code session in this repo.**

Read this file completely before doing anything else.

---

## ⚠ Non-Negotiable Rules

These rules are never optional, never skipped, and must survive context compression. If your context window is compressed and you can only remember a few rules, these are the ones.

1. **README must always be accurate.** Every command in the README must work exactly as written, from the directory stated. Before ending any session or marking any phase complete: run the README commands yourself — if any fail, fix the README first. A README that lies is worse than no README.

2. **Never claim a test passed if you didn't run it.** "It should work" is not a passing test. Run `pytest` (or equivalent). Show the output. If you can't run it, say so — do not fabricate results.

3. **All commands in docs use the package manager prefix.** For Python + uv projects: every `alembic`, `pytest`, `python` command in the README and docs must be prefixed with `uv run`. Bare commands (e.g. `alembic upgrade head`) fail unless the venv is manually activated — which users won't do.

4. **Working directory must be explicit.** Any README or doc section with shell commands must state the exact working directory at the top of the code block. "Run from project root" is not enough — give the exact relative path from the repo root.

5. **No SQLite substitute for PostgreSQL tests.** If the production database is PostgreSQL, tests run against PostgreSQL. Tests that only pass on SQLite do not count as passing.

6. **Golden-path UI smoke test is mandatory before Phase 2 passes.** If the project has any UI or HTTP surface, Phase 2 must include an automated test that walks the full primary user journey end-to-end against the **real LLM/API** (keys from `.env`) via `TestClient` (or equivalent) and asserts **response content**, not just status codes. A build that returns 200 but renders a broken-looking page is a failing build. Edge-case and end-to-end coverage of the journey are required, not optional.

7. **Tests and evals run against the real LLM/API using keys loaded from `.env`.** There is no offline-passing requirement; real-key execution is the default and required path for every gate, against the production DB driver (never SQLite if production is PostgreSQL). A stub provider MAY exist as an optional local fallback when a key is genuinely absent, but it is never the gate. The quality bar is perfect, zero errors — edge-case, end-to-end, and UI tests are required, not optional. The gate must exercise the **hard, idiomatic inputs the capability promises** and push the **real LLM's hard outputs through every guard** on the user's path — not just one easy happy-path example (see `harness/patterns/test-driven.md` → "Gate Tests Must Cover the Capability's Hard Cases").

8. **Every commit must be pushed immediately.** `git commit -m "..." && git push origin <branch>` is one indivisible action — a commit that isn't pushed doesn't exist. See `harness/rules/git.md`.

9. **`main` is boilerplate-only. Never commit application code to `main`.** App code lives on a feature branch cut from the current HEAD and is PR'd back into that branch — it never reaches `main` (only harness/boilerplate does, via a reviewed PR). See `harness/rules/git.md`.

10. **A PR must exist before the first feature-branch commit.** Open it right after the first push, **based on the branch you cut from** (`gh pr create --base "$base" --head feature/<slug>-v0.1`, where `$base` is the HEAD captured before `checkout -b`); every later push updates it. See `harness/rules/git.md`.

---

### Optional stub fallback (non-normative)

The real provider is the default and what every gate tests. A stub provider MAY exist purely as a local fallback for when a key is genuinely absent:

- It should auto-select real when a key is present (`provider=auto` → real when key set), never requiring the user to flip a flag *in addition* to setting the key.
- If an active stub is ever used, signal it visibly in the UI so demo output is never mistaken for real output.
- If implemented, its per-node outputs should be distinct (branch on injected node tags, never on prose keywords) and shaped like real output, so the fallback is not misleading.

None of this is gated — the Phase 2 gate runs against real keys.

---

## 1. Session Start Checklist

Complete all steps in order before writing any code:

- [ ] Read `spec/roadmap.md` — know what you're building
- [ ] Check if the spec is complete (no `<!-- FILL IN -->` markers in product spec files)
  - If incomplete: tell the user to run `/zero-shot-build`; do not write application code
- [ ] If spec is complete: read the full spec manifest in `CLAUDE.md`
- [ ] Run `git status` — working tree must be clean before starting
- [ ] **Branch from the current HEAD**: `base=$(git rev-parse --abbrev-ref HEAD)` then `git checkout -b feature/<slug>-v0.1` — branch from wherever you are so the build dogfoods THIS harness version; never `git checkout main` first (see `harness/rules/git.md`)
- [ ] **Create the project directory** `<agent-slug>/` if it doesn't exist — never write agent code into the boilerplate root
- [ ] Confirm `.env` exists and contains the required API keys/secrets (requested at intake) — tests and the build run against the real LLM/API using these keys
- [ ] Confirm which phase you are implementing (see `harness/patterns/phases.md`)

## 2. Build Flow

The goal is: **one prompt → a perfectly-working, thoroughly-tested agent, delivered one user-testable phase at a time.** Intake is the only interactive setup step. After it, the build is autonomous *within* a phase, with a **human testing gate between phases** — the user tests each phase before the next one starts.

```
INTAKE (capture scope, stack, trigger, constraints; ask additional clarifying
        questions up front if anything is ambiguous; request the user fill .env
        with the required API keys/secrets)
        ↓
BUILD PHASE N (spec + architecture + agent + roadmap on the first phase, then
       implement the phase; gated by passing real-key tests) → publish the
       phase test-handoff
        ↓
HUMAN TESTING GATE (the user tests the phase; on Yes → next phase, on issue →
       qa-auditor diagnoses → the right generator fixes → re-gate → re-present)
        ↓
BUILD PHASE N+1 … (repeat at every phase boundary)
```

**TIGHT SCOPE FOR QUICK WINS / FIRST-TIME-RIGHT:** Phase 1 is the *smallest* user-testable win and must work the first time the user tests it — zero rough edges on the tested path. The frontend builds in parallel and may include clearly-labelled non-functional stubs so the user sees the vision; a stub must never be mistaken for a bug. The user must never have to debug what we hand them.

**Rules that never change:**
- Stack decisions (database, language, hosting) belong to the user — captured at intake, never chosen autonomously.
- Filling `.env` is the only manual user step, requested at intake.
- Each build phase must pass its gate against the real LLM/API before the next phase starts.
- The human tests each phase before the next one starts — that is the gate between phases.
- spec-writer self-reviews its spec (architecture + agent-graph + roadmap), frontend and backend generators build independent slices in parallel, and qa-auditor independently gates each phase.

```
[Phase implemented] → [real-key gate passes] → [committed] → [human tests] → [next phase]
```

---

## 3. Spec-First Rule

**No code change without a spec backing it.**

If you are asked to implement something not in the spec:
1. Stop
2. Tell the user what spec gap you found
3. Propose adding it to the spec first
4. Wait for approval before writing code

See `harness/patterns/spec-driven.md` for full details.

## 4. Phase Discipline

**Never start phase N+1 while phase N is incomplete or failing.**

Each phase ends when:
- All code for that phase is written and committed
- All tests for that phase pass
- The qa-auditor sub-agent has returned VERIFIED (or you have run the gate checklist manually)
- **README is updated** to reflect what this phase added — any new setup steps, commands, endpoints, or environment variables must be accurate and runnable before the gate is declared passed (Rule 1 applies at every phase boundary, not just at session close)

See `harness/patterns/phases.md` for the phase definitions and gates.

## 5. Git Discipline

See `harness/rules/git.md` for the full rules. Summary:

- Commit every logical unit of work — never let the working tree stay dirty for more than one logical change
- **Push immediately after every commit** — `git commit -m "..." && git push origin <branch>` is one indivisible action
- Commit message format: `phase-N: [what you did]`
- Never commit secrets; never force-push without user confirmation
- **Never `git add -A` / `git add .`** — stage specific files only

**Before every reply to the user:**
1. Run `git status`
2. If dirty: commit and push
3. Confirm the working tree is clean **and** the branch is pushed before replying

## 6. Test Before Claiming Done

A phase is not done until all tests pass against the real LLM/API. "It looks right" is not a test. The quality bar is perfect, zero errors — not fast and minimal.

- Write tests for each capability as you implement it, including edge cases
- Cover end-to-end and UI journeys (real keys) for any UI/HTTP surface
- Run the full suite against keys from `.env` before marking a phase complete
- If tests fail, fix them before moving on

## 7. Error Resilience

Every external call (API, database, LLM) must have:
- Error handling that doesn't crash the agent
- Logged failures (to file or stdout at minimum)
- Graceful degradation (the agent continues if a non-critical step fails)

Surface a clear, actionable error when an API key is missing or invalid (point the user at `.env`) — never silently fall back in a way that hides a real failure during tests.

## 8. No Gold-Plating

Build what the spec says, nothing more.

- No extra features "while you're in there"
- No refactoring outside the current phase scope
- No premature abstractions
- If you spot a future improvement, note it and keep moving

## 9. When Stuck

If requirements are unclear:
1. Stop
2. State your specific questions to the user
3. Ask the user — do not guess

If the spec is ambiguous:
1. State the ambiguity
2. Propose an interpretation
3. Wait for confirmation before implementing

## 10. Closing a Session

Before ending a session:
- [ ] Working tree is clean (all changes committed and pushed)
- [ ] Tests pass
- [ ] `README.md` updated if project layout, setup steps, or commands changed
