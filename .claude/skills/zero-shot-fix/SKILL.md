---
name: zero-shot-fix
description: Diagnose and fix a problem in an existing agent — a bug description, a runtime error/stack trace, failing tests, or spec/code drift — then verify the fix. Calls the worker agents directly; runs autonomously to a verified result.
argument-hint: [bug description / error / "tests" / "drift"]
disable-model-invocation: true
allowed-tools: Bash(git*) Bash(uv run*)
---

You orchestrate a targeted fix by calling worker agents directly — no full agent-builder needed. The target is in `$ARGUMENTS`. **If `$ARGUMENTS` is empty, ask the user in plain text to describe what's broken — the bug, error, failing test, or drift — and WAIT for their free-text reply before doing anything else.** Do NOT load `AskUserQuestion` to solicit, suggest, or pick the problem — the problem statement must come from the user as their own text. Only once you have it do you proceed to Step 1. Run autonomously: diagnose+classify → fix → verify, looping until the failure signal is gone. Pause only on a hard blocker or explicit request.

**qa-auditor runs FIRST** — it diagnoses, captures the failing signal, and CLASSIFIES the root cause (SPEC vs CODE, and which surface). Its verdict ROUTES the fix and names which generator. Fixing happens in the **code-generator** and/or **code-generator** (picked by surface); judging happens in read-only **qa-auditor**; you (the skill) own the commit + push.

## Step 1 — Diagnose + classify (qa-auditor first)

**Skip if already diagnosed:** if the caller has passed a qa-auditor verdict with exact `file:line` and SPEC/CODE classification, use that as the baseline and go straight to Step 2 — do not re-invoke qa-auditor.

Otherwise, invoke **qa-auditor** with the target. It:
- captures the current red state — the failing test output, the reproduced error, or the specific drift divergence + file — as your before/after baseline;
- CLASSIFIES the root cause as **SPEC** (spec wrong/missing) vs **CODE** (code diverges from spec), and names **which surface** (frontend / backend) and file(s);
- returns a routed verdict. It stays read-only and never spawns agents.

State the classification in one line. If qa-auditor can't reproduce the reported problem, say so and ask for repro steps rather than guessing.

Done-when, by signal:

| Signal in `$ARGUMENTS` | Done when |
|---|---|
| **Failing tests** | the gate test is green |
| **Bug description** | the wrong behavior no longer occurs and a regression test covers it |
| **Runtime error / stack trace** | the error no longer reproduces when the app runs |
| **Spec/code drift** | qa-auditor (drift mode) reports CLEAN (see also `/zero-shot-sync`) |

## Step 2 — Fix (routed by the verdict)

- **SPEC root cause** → invoke **spec-writer** to rewrite the spec section, then invoke the responsible generator(s) to redo the code toward the corrected spec.
- **CODE root cause** → invoke the responsible generator(s) directly — **code-generator** for `src/` (api, db, graph, llm, tools, prompts, observability), **code-generator** for the frontend/UI surface. Both can run concurrently if the fix spans both surfaces (disjoint paths).

Give the generator the precise target, the responsible files, and the spec sections defining correct behavior. It fixes toward spec intent and adds/updates a regression test (for an LLM/API bug, the regression test uses real keys from `.env`). It must not mute a test or delete an assertion to go green; if spec and test genuinely conflict, it stops and reports (likely a spec bug → re-run Step 1 as SPEC, or suggest `/zero-shot-sync`).

## Step 3 — Verify (qa-auditor always; scope tiered by fix size)

**qa-auditor verifies every fix** — independence is the point: the agent that judges the fix is never the one that wrote it. What changes by tier is the **scope of what qa-auditor runs**, not whether it runs.

### Scoped gate (express) — use when ALL hold
- Root cause is **CODE**, not SPEC
- `git diff --name-only HEAD` shows **≤ 3 files changed**
- No DB migration added (`migrations/` untouched)
- No API contract changed (`spec/api.md` untouched)

Invoke **qa-auditor in scoped gate mode**: verify only the changed surface — run the targeted tests covering the changed files + the new regression test + one real-key smoke call on the exact behavior that was broken (and a frontend `pnpm build` only if a frontend file changed). It does NOT run the full suite or full E2E. It still reviews the diff with fresh eyes and returns VERIFIED/BLOCKED. Typical cost: ~1–2 min vs. the full gate's 10+.

### Full gate — use when: SPEC root cause / migration added / API contract changed / > 3 files changed / scoped gate came back BLOCKED

Invoke **qa-auditor** in full gate mode (real-key tests from `.env`, full suite + E2E) against the Step 1 signal. Still BLOCKED → re-route per the verdict (re-invoke the responsible generator with the new detail); loop until VERIFIED. For a drift fix, also confirm qa-auditor (drift mode) reports CLEAN.

## Step 4 — Ship + report

Commit + push the fix yourself (atomic `git commit … && git push`, staging only the changed files, per `harness/rules/git.md`). Summarize: classification (SPEC/CODE + surface), root cause (1–2 sentences), files changed, the regression test added, the verified before→after, and the pushed SHA.
