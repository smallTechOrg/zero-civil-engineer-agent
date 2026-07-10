import { expect, test, type Page } from '@playwright/test'

// The Library tab and presets editor need NO LLM run: this spec is
// independent of the journey spec and asserts against whatever the scratch
// database holds — a populated table when earlier specs ran, the designed
// empty state otherwise. The presets editor must work in both cases.

async function openLibrary(page: Page) {
  await page.goto('/app/')
  // A fresh browser context has no stored session, so the first-visit hero
  // shows — it carries a direct link into the library. If a session exists,
  // the tab strip is already rendered.
  const heroLink = page.getByTestId('hero-library-link')
  const libraryTab = page.getByTestId('tab-library')
  await expect(heroLink.or(libraryTab).first()).toBeVisible({ timeout: 15_000 })
  if (await heroLink.isVisible()) {
    await heroLink.click()
  } else {
    await libraryTab.click()
  }
  await expect(page.getByTestId('library-panel')).toBeVisible({ timeout: 15_000 })
}

test.describe('design library + presets editor (no LLM run required)', () => {
  test('library renders the run table or its designed empty state', async ({ page }) => {
    await openLibrary(page)

    // Wait for the listing fetch to settle (skeleton gone, no error panel).
    await expect(page.getByTestId('library-loading')).toHaveCount(0, { timeout: 15_000 })
    await expect(page.getByTestId('library-error')).toHaveCount(0)

    const rows = page.getByTestId('library-row')
    const rowCount = await rows.count()
    if (rowCount === 0) {
      const empty = page.getByTestId('library-empty')
      await expect(empty).toBeVisible()
      await expect(empty).toContainText('Every design you run is stored here — run your first design')
    } else {
      // Table semantics + the spec'd columns on a real row.
      await expect(page.getByTestId('library-table')).toBeVisible()
      await expect(page.getByRole('columnheader', { name: 'Verdict' })).toBeVisible()
      await expect(rows.first().getByTestId('library-verdict')).toBeVisible()
      await expect(page.getByTestId('library-range')).toContainText(/of \d+/)
    }

    // The session filter is always present, with the all-sessions option.
    await expect(page.getByTestId('library-session-filter')).toBeVisible()
    await expect(page.getByTestId('library-session-filter').locator('option').first()).toHaveText('All sessions')

    // Nothing on the page reads as unfinished.
    await expect(page.locator('text=/Coming in Phase/i')).toHaveCount(0)
  })

  test('presets editor: invalid cover shows the API 422 inline; valid edit persists across reload', async ({
    page,
  }) => {
    await openLibrary(page)

    const editor = page.getByTestId('preset-editor')
    await expect(editor).toBeVisible({ timeout: 15_000 })

    const cover = page.getByTestId('preset-field-clear_cover_mm')
    await expect(cover).toBeVisible()

    // --- Invalid: cover 200 mm is outside the 40–75 range → inline 422 ------
    await cover.fill('200')
    await page.getByTestId('preset-save').click()
    const saveError = page.getByTestId('preset-save-error')
    await expect(saveError).toBeVisible({ timeout: 15_000 })
    // The API names the valid range in its message (spec/capabilities/design-library.md).
    await expect(saveError).toContainText('40')
    await expect(saveError).toContainText('75')
    await expect(page.getByTestId('preset-save-success')).toHaveCount(0)

    // --- Valid: cover 40 mm saves with an inline success note ---------------
    await cover.fill('40')
    await page.getByTestId('preset-save').click()
    await expect(page.getByTestId('preset-save-success')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByTestId('preset-save-error')).toHaveCount(0)

    // --- The edit persisted: a full reload shows 40 --------------------------
    await openLibrary(page)
    await expect(page.getByTestId('preset-field-clear_cover_mm')).toHaveValue('40', { timeout: 15_000 })
  })
})
