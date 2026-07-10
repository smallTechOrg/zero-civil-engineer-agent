# Spec-Driven Development

This project follows a strict spec-first discipline. This file explains what that means in practice.

## The Rule

**The spec is always written before the code.**

No exceptions. If you find yourself writing code for something that isn't in the spec, stop and spec it first.

## Why

When code is written without a spec:
- Different parts of the system make inconsistent assumptions about behavior
- Testing becomes guesswork ("does this do what I think it does?")
- AI coding sessions produce inconsistent results because each session re-derives requirements
- Scope creep happens silently

When spec comes first:
- Every AI session reads the same requirements
- Tests can be derived mechanically from the spec
- "Does this match the spec?" is a concrete, answerable question
- Drift audits (see the `qa-auditor` sub-agent, driven by `/zero-shot-sync`) can catch divergence automatically

## What Goes in the Spec

**Product spec (`spec/`):**
- What the agent does (behavior, not implementation)
- Who uses it and why
- What data it handles
- What APIs and integrations it uses
- What the UI looks like (if any)

**Chosen stack (in `spec/architecture.md`):**
- The project's language/framework/LLM/database lives in the `## Stack` section — app-specific, captured at intake.

**Engineering harness (`harness/`):**
- `harness/patterns/tech-stack.md` — generic stack rules; `harness/patterns/code.md` — generic code conventions; `harness/patterns/agentic-ai.md` — agentic-pattern catalogue
- How to handle errors, secrets, and testing
- What the implementation phases are
- Repeatable workflows for AI sessions

**Does NOT go in the spec:**
- Specific line-by-line implementation (that's the code)
- Temporary workarounds
- Debug notes or session-specific context (those belong in commit messages / the PR, not the spec)

## What to Do When Requirements Change

1. Update the spec first (the spec-writer self-reviews its changes)
2. Then update the code
3. Run `/zero-shot-sync` (the qa-auditor) to confirm code matches the updated spec

Never update the code first and "update the spec later" — later never comes.

## Spec vs. Implementation Conflicts

If the spec says X and the code does Y:
- The code is wrong
- Fix the code to match the spec
- Exception: if the spec is wrong, update the spec and get it reviewed first, then fix the code

## Adding a New Capability

Run `/zero-shot-build` on the existing spec — it drives the spec-writer to add the capability, then plans, builds, and verifies it. Do not add capabilities by writing code and then describing what you built.
