import { expect, test } from '@playwright/test'

// The demo money-shot: a deliberately under-designed run is caught by the
// automatic proof-check, then a user-triggered revision recovers the verdict.
// Two real Gemini runs back-to-back (each < 90 s), hence the generous budget.

const UNDERDESIGN_PROMPT =
  'single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, BG single line, 25t loading, top slab only 200 mm'
const REVISION_PROMPT = 'increase the top slab to 450 mm'

test.describe('under-designed slab caught by the proof-check (real backend + Gemini)', () => {
  test('thin top slab → warning + FAIL rows + red verdict naming the slab; revision → green verdict', async ({
    page,
  }) => {
    test.setTimeout(420_000)

    await page.goto('/app/')

    // --- Run 1: the deliberate under-design ----------------------------------
    await page.getByTestId('prompt-input').fill(UNDERDESIGN_PROMPT)
    await page.getByTestId('prompt-submit').click()
    await expect(page.getByTestId('prompt-submit')).toBeDisabled({ timeout: 500 })

    // The unusual override is flagged (amber warning), never silently accepted
    // and never treated as an error.
    await expect(page.getByTestId('warning-banner').first()).toBeVisible({ timeout: 120_000 })
    await expect(page.getByTestId('error-banner')).toHaveCount(0)

    // The run completes despite the failing design (transparent, not fatal).
    await expect(page.getByTestId('prompt-submit')).toHaveText('Refine', { timeout: 180_000 })
    await expect(page.getByTestId('prompt-submit')).toBeEnabled()

    // FAIL rows are unmistakable in the calc sheet.
    await page.getByTestId('tab-calc-sheet').click()
    await expect(page.getByTestId('calc-assumptions')).toBeVisible({ timeout: 30_000 })
    const failRows = page.locator('[data-testid="calc-row"][data-status="FAIL"]')
    expect(await failRows.count(), 'the under-designed run must show FAIL calc lines').toBeGreaterThan(0)
    await expect(failRows.first()).toContainText('FAIL')

    // Red verdict banner; the memo/matrix names the failing member.
    await page.getByTestId('tab-proof-check').click()
    const banner = page.getByTestId('verdict-banner')
    await expect(banner).toBeVisible({ timeout: 30_000 })
    await expect(banner).toHaveAttribute('data-verdict', 'return_for_revision')
    await expect(banner).toContainText('Return for revision')
    await expect(page.locator('#panel-proof-check')).toContainText(/top slab/i, { timeout: 30_000 })

    // Major non-conformities render distinctly from minor/observation rows.
    expect(
      await page.locator('[data-testid="compliance-row"][data-severity="NON_CONFORMITY_MAJOR"]').count(),
      'flexure/shear items must report a MAJOR non-conformity',
    ).toBeGreaterThan(0)

    // --- Run 2: the user-triggered revision recovers the verdict -------------
    await page.getByTestId('prompt-input').fill(REVISION_PROMPT)
    await page.getByTestId('prompt-submit').click()
    await expect(page.getByTestId('prompt-submit')).toBeDisabled({ timeout: 500 })

    await expect(page.getByTestId('prompt-submit')).toBeEnabled({ timeout: 180_000 })
    await expect(page.getByTestId('prompt-submit')).toHaveText('Refine')

    await page.getByTestId('tab-proof-check').click()
    const revisedBanner = page.getByTestId('verdict-banner')
    await expect(revisedBanner).toBeVisible({ timeout: 30_000 })
    await expect(revisedBanner).toHaveAttribute('data-verdict', 'recommended_for_approval')
    await expect(revisedBanner).toContainText('Recommended for approval')
  })
})
