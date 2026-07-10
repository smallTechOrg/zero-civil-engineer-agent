import { expect, test } from '@playwright/test'

// Each test gets a fresh browser context (empty localStorage), so each starts
// its own session — no cross-test 409 RUN_ACTIVE interference (workers: 1).

test.describe('guard rails (real backend + Gemini)', () => {
  test('out-of-scope request renders a graceful scope statement, not an error', async ({ page }) => {
    await page.goto('/app/')

    await page.getByTestId('prompt-input').fill('design a suspension bridge')
    await page.getByTestId('prompt-submit').click()
    await expect(page.getByTestId('prompt-submit')).toBeDisabled({ timeout: 500 })

    // The scope statement arrives as an informational agent reply in the turn
    // history once the run ends `out_of_scope`.
    await expect(page.getByTestId('scope-statement')).toBeVisible({ timeout: 180_000 })
    await expect(page.getByTestId('turn-item').first()).toContainText('Out of scope')

    // Informational, never error styling or a failed tracker.
    await expect(page.getByTestId('error-banner')).toHaveCount(0)
    await expect(page.locator('[data-testid^="step-"][data-status="failed"]')).toHaveCount(0)

    // The prompt re-opens for the next request.
    await expect(page.getByTestId('prompt-submit')).toBeEnabled({ timeout: 30_000 })
  })

  test('missing critical parameter asks exactly one pointed question and switches to Answer', async ({ page }) => {
    await page.goto('/app/')

    await page.getByTestId('prompt-input').fill('box culvert 3 m height, 2 m cushion')
    await page.getByTestId('prompt-submit').click()
    await expect(page.getByTestId('prompt-submit')).toBeDisabled({ timeout: 500 })

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
    await expect(page.getByTestId('turn-item').first()).toContainText('Needs input')
  })
})
