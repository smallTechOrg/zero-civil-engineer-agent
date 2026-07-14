import { expect, test } from '@playwright/test'

// Each test gets a fresh browser context (empty localStorage), so each starts
// its own session — no cross-test 409 RUN_ACTIVE interference (workers: 1).
//
// DEFERRED offline: the Gemini project is over its monthly spend cap, so every
// live LLM call returns 429 RESOURCE_EXHAUSTED. Both guard-rail tests submit a
// prompt, so they are marked `test.fixme` and skipped by the offline gate;
// re-enable (drop the `test.fixme`) once billing resets — the assertions are
// ready to run as-is.

test.describe('guard rails (real backend + Gemini)', () => {
  test('out-of-scope request renders a graceful scope statement, not an error', async ({ page }) => {
    test.fixme(
      true,
      'DEFERRED: Gemini project over monthly spend cap — live LLM calls 429 RESOURCE_EXHAUSTED; re-enable when billing resets',
    )
    await page.goto('/app/')

    await page.getByTestId('prompt-input').fill('design a suspension bridge')
    await page.getByTestId('prompt-submit').click()
    await expect(page.getByTestId('prompt-submit')).toBeDisabled({ timeout: 500 })

    // The scope statement arrives as an informational agent reply in the run
    // status line once the run ends `out_of_scope`.
    await expect(page.getByTestId('status-line')).toBeVisible({ timeout: 180_000 })
    await expect(page.getByTestId('status-line')).toContainText(/scope/i)
    // The design record for this turn is present in the Design Records rail.
    await expect(page.getByTestId('record-item').first()).toBeVisible()

    // Informational, never error styling or a failed tracker.
    await expect(page.getByTestId('error-banner')).toHaveCount(0)
    await expect(page.locator('[data-testid^="step-"][data-status="failed"]')).toHaveCount(0)

    // The prompt re-opens for the next request.
    await expect(page.getByTestId('prompt-submit')).toBeEnabled({ timeout: 30_000 })
  })

  test('missing critical parameter asks exactly one pointed question and switches to Answer', async ({ page }) => {
    test.fixme(
      true,
      'DEFERRED: Gemini project over monthly spend cap — live LLM calls 429 RESOURCE_EXHAUSTED; re-enable when billing resets',
    )
    await page.goto('/app/')

    await page.getByTestId('prompt-input').fill('box culvert 3 m height, 2 m cushion')
    await page.getByTestId('prompt-submit').click()
    await expect(page.getByTestId('prompt-submit')).toBeDisabled({ timeout: 500 })

    // The clarification prompt lives in the Define stage in the new IA.
    await expect(page.getByTestId('stage-rail')).toBeVisible({ timeout: 180_000 })
    await page.getByTestId('stage-tab-define').click()

    // Exactly ONE amber clarification card, naming the missing clear span.
    const card = page.getByTestId('clarification-card')
    await expect(card).toHaveCount(1, { timeout: 180_000 })
    await expect(card).toBeVisible()
    await expect(card).toContainText('One question:')
    await expect(card).toContainText(/span/i)

    // The submit button switches to answering mode and re-enables.
    await expect(page.getByTestId('prompt-submit')).toHaveText('Answer', { timeout: 30_000 })
    await expect(page.getByTestId('prompt-submit')).toBeEnabled()

    // Never rendered as a failure.
    await expect(page.getByTestId('error-banner')).toHaveCount(0)
    // The design record for this turn is present in the Design Records rail.
    await expect(page.getByTestId('record-item').first()).toBeVisible()
  })
})
