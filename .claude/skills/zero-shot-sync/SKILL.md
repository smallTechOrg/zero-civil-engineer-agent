---
name: zero-shot-sync
description: Reconcile spec and code so they match. Audits the whole tree for drift, brings code in line with the spec (spec wins), and verifies. Calls worker agents directly; runs autonomously to a CLEAN audit.
argument-hint: [optional path or capability to scope to]
disable-model-invocation: true
allowed-tools: Bash(git*) Bash(uv run*)
---

You orchestrate a spec↔code sync by calling worker agents directly. **Spec is the source of truth — when spec and code disagree, fix the code** (harness/patterns/spec-driven.md). Optional scope in `$ARGUMENTS`; otherwise the whole project. Run autonomously to a CLEAN audit; pause only on a hard blocker or if a divergence reveals the *spec* is wrong (surface it — don't silently rewrite the spec to match code).

**qa-auditor runs FIRST** — read-only, it finds and classifies every divergence and its direction; its verdict routes each fix to the responsible **code-generator** and/or **code-generator** by surface. You (the skill) own the commit + push.

## Step 1 — Audit (qa-auditor first, drift mode)

Invoke **qa-auditor** in drift mode (whole-tree). For each divergence it returns: severity, the **direction** (code-wrong vs spec-wrong), and **which surface** (frontend / backend) + file(s). CLEAN → report and stop. It stays read-only and never spawns agents.

## Step 2 — Triage by direction

Per divergence, act on qa-auditor's direction:
- **Code wrong, spec right** (common, default) → fix the code, routed to the surface qa-auditor named.
- **Spec wrong, code right** → do **not** auto-edit the spec to match code. Surface to the user with the specific mismatch and a proposed spec change; wait. (Silently editing the spec defeats spec-driven development.)
- **Undocumented behavior** → remove from code, or if intended, surface as a spec addition for confirmation.

Handle High severity first, then Medium; Low only if in scope.

## Step 3 — Reconcile code (routed by surface, parallel where independent)

Group the "code wrong" divergences **by surface**, then invoke the responsible generator per group:
- **code-generator** — divergences in `src/` (api, db, graph, llm, tools, prompts, observability).
- **code-generator** — divergences in the frontend/UI surface.

Independent groups (disjoint paths) run **concurrently**. Give each generator the spec section + the offending file(s); it edits code to match the spec and adds/updates a test asserting the spec'd behavior. Group divergences that touch the same files into one invocation.

## Step 4 — Verify (qa-auditor, gate mode)

Invoke **qa-auditor** in gate mode to confirm the reconciliation didn't break anything (tests green against real keys from `.env`, plus smoke + UI tests if there's a UI). BLOCKED → re-invoke the responsible generator with the detail; loop.

## Step 5 — Re-audit

Invoke **qa-auditor** (drift mode) again. Repeat 2–4 until CLEAN (modulo spec-is-wrong items surfaced for user decision).

## Step 6 — Ship + report

Commit + push yourself (atomic `git commit … && git push`, staging only the changed files, per `harness/rules/git.md`). Summarize: divergences by severity and surface, which were fixed in code (files + regression tests), which were surfaced as possible spec bugs awaiting decision, and the final audit status.
