# Rule: Secret Hygiene

**Scope:** everywhere, always. This is the rule most likely to cause real-world harm if violated.

## What is a secret

Anything that authenticates, authorizes, or can be used to impersonate.

For code purposes, treat any field whose name matches `*_token`, `*_secret`,
`*_password`, `*_key`, or `*_credential` as a secret.

## Where secrets live

| Location | Secrets allowed? |
|---|---|
| `.env` | ✅ Yes (primary store) |
| OS environment variables | ✅ Yes |
| Source code | ❌ Never, including tests |
| Git history | ❌ Never |
| Commit messages, PR descriptions, logs | ❌ Never |

Tests and evals read keys from `.env` / the process environment at runtime — never hardcode a key in a test or fixture.

## Rules for code

### Never log a secret

```python
# BAD
log.info("api_call", token=access_token)

# GOOD
log.info("api_call", token_present=bool(access_token))
```

### Never include secrets in exception messages

```python
# BAD
raise ValueError(f"Auth failed with token {token}")

# GOOD
raise ValueError("Auth failed. Check your API key in .env.")
```

### Never `print()` or `repr()` a config object that may contain secrets

Config models use pydantic. Secret fields must use pydantic's `SecretStr` type.
`SecretStr.get_secret_value()` is the only way to extract the raw value, and it
should be called only at the boundary where the secret is actually used.

## Rules for `.gitignore`

The repo's `.gitignore` is the enforcement point. If you introduce a new
secret-bearing file location, **add it to `.gitignore` before creating the file**.

## Rules for commits

Before every commit involving new or changed files:

1. Scan the diff for strings that look like tokens (length > 20, mix of alphanumerics, common prefixes like `sk-`, `gsk_`, `ghp_`).
2. If anything matches, **stop**. Do not include in the commit. Rotate the secret if it was real.
3. `git diff --cached` is your friend.

## Rules for AI agents

- **Load keys programmatically, never echo them.** The build and tests load keys from `.env` programmatically (e.g. via the config loader / process env) — that is expected. Do not echo or paste raw `.env` values into responses or logs. When you must confirm a key, confirm by presence only (a bool), never by value.
- **Never echo, print, or paste a secret value** into your response.
- **Never commit a file that contains a secret** even if the user asks. Push back, rotate, continue.
- **When intake requests API keys, instruct the user to put them in `.env`** (gitignored) — never accept secrets pasted into chat or committed to source.

## If a secret leaks

1. Rotate the secret immediately at the provider.
2. Update the relevant `.env` with the new value.
3. Purge from git history if committed: `git filter-repo` or `bfg`. Force-push with operator approval.
4. Note the incident in the commit message without repeating the leaked value.
