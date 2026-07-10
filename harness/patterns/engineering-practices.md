# Engineering Best Practices

Rules that apply to every implementation phase, regardless of stack or project type.

---

## Design

**Single responsibility.** Every function, class, and module does one thing. If you need "and" to describe it, split it.

**Dependency inversion.** Code depends on abstractions (interfaces, protocols), not on concrete implementations. This makes stubs, testing, and future swaps cheap.

**No premature abstraction.** Three similar lines is better than a premature helper. Extract only when you have three real uses — not hypothetical ones.

**Immutable data by default.** Prefer returning new values over mutating in place. Makes behaviour easier to reason about and test.

---

## Testing

**Tests are part of the phase — not an afterthought.** Write the test alongside the code, not after. A function that is written before its test is harder to test by design.

**Testing pyramid.** Unit tests form the base (fast, many, isolated). Integration tests sit above them (slower, fewer, test the real DB and the real LLM/API boundary with keys from `.env`). End-to-end / smoke tests at the top (fewest, run on a real process against the real provider). Edge-case, error-path, and UI tests are required, not optional — the quality bar is perfect, zero errors, within a ~20-30 min build budget.

**Test behaviour, not implementation.** Tests assert what the function returns or what side-effects occur — not which internal calls were made. Tests that mirror the implementation break on refactors that don't change behaviour.

**Never mock what you can stub.** Prefer thin stub implementations (e.g. an in-memory queue) over framework mocks. Stubs compose, mocks create test-coupling. Stubbing is reserved for pure-unit isolation: the LLM/external provider is **not** stubbed in integration and e2e tests — those hit the real provider with keys from `.env`.

**One assertion per concept.** When a test fails you want to know exactly what broke. Multiple unrelated assertions per test obscure failures.

**Unit tests must be deterministic.** No random data, no wall-clock-dependent assertions. If you need "random" data, seed it; if you need time, inject it. Integration and e2e tests *do* make real LLM/API calls — keep them stable by asserting on structural properties (status, shape, key fields), not exact prose, so real calls don't make them flaky.

---

## Code quality

**Name things from the caller's perspective.** A function named `process_items` tells you nothing. `validate_inventory_thresholds` tells you exactly what to expect.

**Short functions.** If a function doesn't fit on one screen, it has too many responsibilities. The rule of thumb: if you need a comment to break it into sections, split it into functions instead.

**No magic numbers or strings.** Every hard-coded literal that has domain meaning must be a named constant.

**Fail fast.** Validate inputs at the boundary (API, CLI, message queue). Never let invalid data propagate deep into the system — it produces misleading errors far from the source.

**Return early.** Prefer guard clauses at the top over deeply nested conditionals. Each guard clause reduces the cognitive load of the path below it.

---

## Error handling

**Handle errors at the level that has context to recover.** A low-level DB function should not catch and swallow errors — it should let them propagate to the layer that knows whether to retry, degrade, or abort.

**Distinguish recoverable from unrecoverable.** Retryable errors (network timeout, transient lock) must be retried with back-off. Unrecoverable errors (bad config, missing required env var) must fail hard at startup with a clear message.

**Log at the right level.** DEBUG for internal state you'd want during a debugging session. INFO for normal operation milestones (request received, job started). WARNING for recoverable anomalies. ERROR for failures that require attention. Never log sensitive data (tokens, passwords, PII).

**Errors must include context.** `"Database error"` is useless. `"Failed to insert order id=42: unique constraint orders_pkey"` is actionable. Include the inputs that caused the failure.

---

## Security

**Never trust input.** Validate everything that crosses a trust boundary: HTTP requests, CLI arguments, file uploads, database values, environment variables.

**Principle of least privilege.** Each component, service account, and API token should have only the permissions it needs — nothing more.

**Secrets are never in code.** No API keys, passwords, or tokens in source files, even in test fixtures. The real key lives in `.env` (the single manual user step, filled at intake), gitignored and loaded programmatically for tests/evals via `python-dotenv` / the config loader — never hardcoded, echoed, or committed. Confirm a key by presence (bool) only. See `harness/rules/secret-hygiene.md`.

**Parameterised queries only.** Never construct SQL (or any query language) from user-supplied strings. Use the ORM or parameterised query interface without exception.

**Dependency hygiene.** Pin dependency versions. Review new dependencies before adding them. Prefer libraries with active maintenance and small attack surface.

---

## Observability

**Structured logging.** Emit JSON logs (or a structured format your logging pipeline can parse). Include `timestamp`, `level`, `trace_id`/`request_id`, and `message` on every line. Free-text logs are hard to aggregate and alert on.

**Trace IDs propagate.** Any operation that spans multiple services or agent nodes must carry a trace ID from entry to exit. Log it at every step.

**Every external call is instrumented.** Latency and error rate for each DB query, LLM call, and HTTP request should be observable. You will debug production issues from these numbers.

**Metrics are not logs.** Counters, histograms, and gauges belong in a metrics system (Prometheus, StatsD, OpenTelemetry). Logs are for events; metrics are for rates and distributions.

---

## Git and code review

See `harness/rules/git.md` for the full git rules. The quality principles that belong here:

**Commits are logical units.** Each commit should be a self-contained, reviewable change. "Fix bug and refactor and add feature" is three commits.

**Commit messages explain the why.** The diff shows the what. The message answers: why was this change needed, and what is the outcome?

**No commented-out code in commits.** If code is not needed, delete it. Git history preserves it.

**PR description is not optional.** Every PR needs: what changed, why, and how to verify. Screenshots or test output for UI/behavioural changes.

**Review the diff before committing.** `git diff --staged` before every commit. You are responsible for what you push.
