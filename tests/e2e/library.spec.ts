import { expect, test } from '@playwright/test'

// The Design Records rail replaced the old Library tab + preset editor in the
// Phase 4.1 redesign. This spec needs NO LLM run: it asserts the rail's shell
// (new-design action, Projects "coming" stub, and either the designed empty
// state or real record items with status chips) against whatever the scratch
// session holds. The full completed-design → record-item → replay path is
// covered live in design-journey.spec.ts.

test.describe('Design Records rail shell (no LLM run required)', () => {
  test('rail renders the new-design action, Projects stub, and empty-or-records state', async ({ page }) => {
    await page.goto('/app/')

    const rail = page.getByTestId('design-records-rail')
    await expect(rail).toBeVisible({ timeout: 15_000 })

    // The [+ New design] entry point is always present.
    await expect(page.getByTestId('new-design')).toBeVisible()

    // The Projects grouping is a clearly-labelled "coming" stub, never a bug.
    await expect(page.getByTestId('projects-stub')).toContainText(/coming/i)

    // Either the designed empty state OR real record items (with status chips).
    const empty = page.getByTestId('records-empty')
    const records = page.getByTestId('record-item')
    const recordCount = await records.count()
    if (recordCount === 0) {
      await expect(empty).toBeVisible()
      await expect(empty).toContainText(/run your first design/i)
    } else {
      await expect(records.first()).toBeVisible()
      await expect(records.first().getByTestId('status-chip')).toBeVisible()
    }

    // Nothing on the rail reads as an unfinished bug.
    await expect(page.locator('text=/Coming in Phase/i')).toHaveCount(0)
  })
})
