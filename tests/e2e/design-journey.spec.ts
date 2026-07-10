import { expect, test, type Page } from '@playwright/test'

const CANONICAL_PROMPT =
  'single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, BG single line, 25t loading'

const step = (page: Page, name: string) => page.locator(`[data-testid="step-${name}"]`)

test.describe('primary design journey (real backend + Gemini)', () => {
  test('canonical prompt: styled render, live tracker, calc sheet, drawing, proof-check, 3D model, chips, library, cost badge', async ({
    page,
    request,
  }) => {
    test.setTimeout(300_000)

    // --- 1. Styled render ---------------------------------------------------
    const cssStatuses: number[] = []
    page.on('response', response => {
      if (response.url().includes('/_next/static/css/') || response.url().endsWith('.css')) {
        cssStatuses.push(response.status())
      }
    })

    await page.goto('/app/')
    await expect(page.getByRole('banner')).toContainText('IR Box Culvert Design & Proof-Check Agent')

    expect(cssStatuses.length, 'at least one stylesheet must be requested').toBeGreaterThan(0)
    expect(cssStatuses, 'stylesheet must load with 200').toContain(200)

    const headerBg = await page.evaluate(() => getComputedStyle(document.querySelector('header')!).backgroundColor)
    expect(headerBg, 'header must be styled, not browser-default transparent').not.toBe('rgba(0, 0, 0, 0)')
    expect(headerBg, 'header must be styled, not plain white').not.toBe('rgb(255, 255, 255)')

    // --- 2. Submit the canonical prompt; tracker advances in order ----------
    await page.getByTestId('prompt-input').fill(CANONICAL_PROMPT)
    await page.getByTestId('prompt-submit').click()
    // Feedback within ~100 ms: the disable is synchronous with the click handler.
    await expect(page.getByTestId('prompt-submit')).toBeDisabled({ timeout: 500 })

    await expect(step(page, 'Understand')).toHaveAttribute('data-status', /active|done/, { timeout: 60_000 })
    await expect(step(page, 'Extract')).toHaveAttribute('data-status', /active|done/, { timeout: 90_000 })
    await expect(step(page, 'Analyse')).toHaveAttribute('data-status', /active|done/, { timeout: 120_000 })

    // --- 3. Calc Sheet streams in BEFORE the review completes ---------------
    // The calc_sheet artefact fires at the end of Check; Review (FE re-solve +
    // memo) runs after. Seeing sheet content while Review is not yet done is
    // the DOM-level proxy for the artefact-before-review-done SSE ordering.
    await page.getByTestId('tab-calc-sheet').click()
    await expect(page.getByTestId('calc-assumptions')).toBeVisible({ timeout: 180_000 })
    expect(
      await step(page, 'Review').getAttribute('data-status'),
      'calc sheet must arrive before the Review step completes',
    ).not.toBe('done')

    // Assumptions block + all four sections.
    const sectionCount = await page.getByTestId('calc-section').count()
    expect(sectionCount, 'the sheet must contain the four sections').toBeGreaterThanOrEqual(4)

    // Every loading line carries its citation; the ACS correction-slip level
    // must be visible on the loading lines.
    const loadingSection = page.locator('[data-testid="calc-section"][data-section-id="loading"]')
    await expect(loadingSection).toBeVisible()
    await expect(
      loadingSection.locator('[data-testid="calc-citation"]').filter({ hasText: 'ACS' }).first(),
    ).toBeVisible()

    // Drill-down: expanding a trail row reveals the formula + substituted inputs.
    await page.getByTestId('calc-row-expand').first().click()
    const trail = page.getByTestId('calc-trail').first()
    await expect(trail).toBeVisible()
    const formulaText = (await trail.getByTestId('calc-trail-formula').first().textContent()) ?? ''
    expect(formulaText.trim().length, 'the trail must show a real formula').toBeGreaterThan(0)
    await expect(trail.getByTestId('calc-trail-inputs').first()).toBeVisible()
    const inputCount = await trail.locator('[data-testid="calc-trail-input"]').count()
    expect(inputCount, 'the trail must show substituted inputs').toBeGreaterThan(0)

    // --- 4. Check and Review are REAL steps now (done, never skipped) -------
    await expect(step(page, 'Check')).toHaveAttribute('data-status', 'done', { timeout: 180_000 })
    await expect(step(page, 'Review')).toHaveAttribute('data-status', 'done', { timeout: 180_000 })

    // Regression (F1): whatever order later step events arrive in, the live
    // tracker must keep Draw done — never downgrade a done/failed step.
    await expect(step(page, 'Draw')).toHaveAttribute('data-status', 'done', { timeout: 180_000 })

    // --- 5. Real inline SVG drawing with pan/zoom-ready DOM -----------------
    await page.getByTestId('tab-drawing').click()
    const svg = page.locator('[data-testid="drawing-svg"] svg')
    await expect(svg).toBeVisible({ timeout: 180_000 })
    const svgChildCount = await page.locator('[data-testid="drawing-svg"] svg *').count()
    expect(svgChildCount, 'GA drawing SVG must contain real geometry').toBeGreaterThan(10)

    // Run must finish (button re-enables as Refine) before final artefact checks.
    await expect(page.getByTestId('prompt-submit')).toHaveText('Refine', { timeout: 180_000 })
    await expect(page.getByTestId('prompt-submit')).toBeEnabled()

    // --- 6. Proof-Check tab: verdict banner, 12-row matrix, BMD/SFD ---------
    await page.getByTestId('tab-proof-check').click()
    const banner = page.getByTestId('verdict-banner')
    await expect(banner).toBeVisible({ timeout: 30_000 })
    await expect(banner).toHaveAttribute('data-verdict', 'recommended_for_approval')
    await expect(banner).toContainText('Recommended for approval')

    await expect(page.getByTestId('memo')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('compliance-row')).toHaveCount(12, { timeout: 30_000 })

    await expect(page.locator('[data-testid="bmd-svg"] svg')).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('[data-testid="sfd-svg"] svg')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('fe-agreement')).toContainText(/agrees within [\d.]+%/)

    // --- 7. Genuine DXF download ---------------------------------------------
    const runId = await page.getByTestId('step-tracker').getAttribute('data-run-id')
    expect(runId, 'tracker must expose the run id').toBeTruthy()

    const dxfResponse = await request.get(`/api/designs/${runId}/artifacts/ga.dxf`)
    expect(dxfResponse.status()).toBe(200)
    expect(dxfResponse.headers()['content-disposition'] ?? '').toContain('attachment')
    const dxfBody = await dxfResponse.body()
    expect(dxfBody.length, 'DXF must be a non-trivial file').toBeGreaterThan(5 * 1024)

    // --- 8. 3D Model tab: interactive viewer loads + genuine STEP download --
    await page.getByTestId('tab-3d-model').click()
    const viewer = page.getByTestId('model3d-viewer')
    await expect(viewer).toBeVisible({ timeout: 30_000 })
    // Headless WebGL runs on SwiftShader — GLB parse + first render is slow.
    await expect(viewer).toHaveAttribute('data-model-loaded', 'true', { timeout: 120_000 })
    await expect(page.getByTestId('model3d-caption')).toContainText(
      'Generated from the same BoxGeometry as the drawing and calc sheet',
    )
    await expect(page.getByTestId('download-step')).toBeEnabled()

    const stepResponse = await request.get(`/api/designs/${runId}/artifacts/model.step`)
    expect(stepResponse.status()).toBe(200)
    expect(stepResponse.headers()['content-disposition'] ?? '').toContain('attachment')
    const stepBody = await stepResponse.body()
    expect(stepBody.length, 'STEP must be a non-trivial solid').toBeGreaterThan(5 * 1024)

    // --- 9. Suggestion chips: render after completion; a click fills the box -
    const chips = page.getByTestId('suggestion-chip')
    await expect(chips.first()).toBeVisible({ timeout: 30_000 })
    const chipCount = await chips.count()
    expect(chipCount, 'a completed run suggests 1–3 refinements').toBeGreaterThanOrEqual(1)
    expect(chipCount).toBeLessThanOrEqual(3)
    const chipText = ((await chips.first().textContent()) ?? '').trim()
    expect(chipText.length, 'a chip must carry real suggestion text').toBeGreaterThan(0)
    await chips.first().click()
    // Fill-only, never auto-submit: the text lands in the focused prompt box.
    await expect(page.getByTestId('prompt-input')).toHaveValue(chipText)
    await expect(page.getByTestId('prompt-input')).toBeFocused()
    await expect(page.getByTestId('prompt-submit')).toHaveText('Refine')

    // --- 10. Library tab: populated table; a row click replays the run ------
    await page.getByTestId('tab-library').click()
    const rows = page.getByTestId('library-row')
    await expect(rows.first()).toBeVisible({ timeout: 30_000 })
    await expect(rows.first().getByTestId('library-verdict')).toBeVisible()
    await expect(page.getByTestId('library-range')).toContainText(/of \d+/)

    const rowRunId = await rows.first().getAttribute('data-run-id')
    expect(rowRunId, 'library rows must carry their run id').toBeTruthy()
    await rows.first().click()
    // The replay repaints the tracker with the selected run…
    await expect(page.getByTestId('step-tracker')).toHaveAttribute('data-run-id', rowRunId!, { timeout: 15_000 })
    // …and the Drawing tab (auto-selected on replay) re-renders the stored SVG.
    await expect(page.locator('[data-testid="drawing-svg"] svg')).toBeVisible({ timeout: 30_000 })

    // --- 11. Page-wide stub sweep: nothing reads as unfinished anymore ------
    await expect(page.locator('text=/Coming in Phase/i')).toHaveCount(0)

    // --- 12. Token/cost badge shows a real, non-zero token count ------------
    const badgeText = (await page.getByTestId('token-cost-badge').textContent()) ?? ''
    expect(badgeText).toMatch(/tok · \$[\d.]+ run · \$[\d.]+ session/)
    const tokenMatch = badgeText.match(/^([\d.]+)(k?) tok/)
    expect(tokenMatch, `badge must lead with a token count, got: ${badgeText}`).toBeTruthy()
    const tokenCount = parseFloat(tokenMatch![1]) * (tokenMatch![2] === 'k' ? 1000 : 1)
    expect(tokenCount, 'a real Gemini run must report non-zero tokens').toBeGreaterThan(0)
  })
})
