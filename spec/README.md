# Spec — Single Source of Truth

This directory is the authoritative specification for this project. All code must match this spec. When spec and code disagree, spec wins — fix the code.

## Status

Check `spec/roadmap.md` to see if the spec has been filled in. If it still contains `<!-- FILL IN -->` markers, the spec-writer sub-agent needs to complete it before any application code is written.

## Structure

`spec/` is **the product** — what the agent does, in terms a user can read and edit. Generic engineering doctrine (how to build anything) lives in `harness/`.

```
spec/                 ← The product (you read & edit this)
  roadmap.md       ← Purpose, goals, success criteria, future phases
  architecture.md  ← System design, layers, data flow, and the chosen ## Stack
  agent.md         ← This agent's graph (state, nodes, edges) — if a framework is used
  data.md          ← Data schema
  api.md           ← API surface (REST/GraphQL/CLI/etc.)
  ui.md            ← UI requirements (if any)
  capabilities/    ← One file per discrete capability

harness/              ← How to build it (generic engineering doctrine)
  rules/           ← Mandatory rules (ai-agents, git, secret-hygiene)
  patterns/        ← phases, project-layout, test-driven, ui-ux, engineering-practices,
                     spec-driven, tech-stack (generic stack rules), code (conventions),
                     agentic-ai (pattern catalogue)
```

## Governance Rules

1. **Spec first** — no code change without a spec backing it
2. **One fact, one place** — never duplicate facts across spec files; cross-reference with links
3. **Capabilities are atomic** — each file in `capabilities/` describes exactly one discrete thing the agent can do
4. **No implementation details in product spec** — `spec/` describes WHAT, `harness/` describes HOW
5. **Update spec before code** — if requirements change, update the spec first, then update the code

## Who Updates the Spec

- **New project:** the `/zero-shot-build` skill drives the spec-writer sub-agent, which drafts and self-reviews the spec
- **New capability:** run `/zero-shot-build` on an existing spec — it adds the capability via the spec-writer
- **Drift between spec and code:** run `/zero-shot-sync` to reconcile (spec wins)
