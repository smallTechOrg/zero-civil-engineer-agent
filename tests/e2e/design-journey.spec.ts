import { expect, test, type Page } from '@playwright/test'

// Redesign Phase 1 (Phase 4.1) primary journey against the real backend + Gemini
// on the new lifecycle IA (dark studio shell + Design Records rail + Stage Rail).
// Asserts the roadmap Phase-4.1 Gate's five items end-to-end on the canonical
// box-culvert prompt.

const CANONICAL_PROMPT =
  'single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, BG single line, 25t loading'
const REFINE_PROMPT = 'increase the fill to 4 m'

const step = (page: Page, name: string) => page.locator(`[data-testid="step-${name}"]`)

test.describe('Phase 4.1 redesigned design journey (real backend + Gemini)', () => {
  test('platform title, prompt-first entry, full lifecycle run, no tab-yank, lifecycle stubs', async ({
    page,
    request,
  }) => {
    test.setTimeout(300_000)

    // --- Styled dark render -------------------------------------------------
    const cssStatuses: number[] = []
    page.on('response', response => {
      if (response.url().includes('/_next/static/css/') || response.url().endsWith('.css')) {
        cssStatuses.push(response.status())
      }
    })

    await page.goto('/app/')

    // (1) Top bar reads the platform title — never the old "Box Culvert" wordmark.
    const banner = page.getByRole('banner')
    await expect(banner).toContainText('IR Engineering Design & Proof-Check Platform')
    await expect(banner).not.toContainText(/Box Culvert/i)

    expect(cssStatuses.length, 'at least one stylesheet must be requested').toBeGreaterThan(0)
    expect(cssStatuses, 'stylesheet must load with 200').toContain(200)
    const headerBg = await page.evaluate(() => getComputedStyle(document.querySelector('header')!).backgroundColor)
    expect(headerBg, 'header must be styled, not transparent').not.toBe('rgba(0, 0, 0, 0)')
    expect(headerBg, 'header must be styled, not plain white').not.toBe('rgb(255, 255, 255)')

    // (2) Prompt-first new-design entry: hero prompt + Civil/Mechanical gallery
    //     + "let the agent decide".
    await expect(page.getByTestId('prompt-input')).toBeVisible()
    await expect(page.getByTestId('hero-starter')).toBeVisible()
    const picker = page.getByTestId('component-picker')
    await expect(picker).toBeVisible({ timeout: 30_000 })
    await expect(picker).toContainText(/culvert/i)
    await expect(picker).toContainText(/machine element/i)
    const auto = page.getByTestId('component-auto')
    await expect(auto).toBeVisible()
    await expect(auto).toContainText(/let the agent decide/i)

    // The left Design Records rail + its Projects "coming" stub are present.
    await expect(page.getByTestId('design-records-rail')).toBeVisible()
    await expect(page.getByTestId('projects-stub')).toContainText(/coming/i)

    // --- (3) Submit the canonical prompt; the Stage Rail advances ------------
    await page.getByTestId('prompt-input').fill(CANONICAL_PROMPT)
    await page.getByTestId('prompt-submit').click()
    await expect(page.getByTestId('prompt-submit')).toBeDisabled({ timeout: 1000 })

    // The Stage Rail is now mounted and Define lights up as the run streams.
    await expect(page.getByTestId('stage-rail')).toBeVisible({ timeout: 30_000 })
    await expect(step(page, 'Understand')).toHaveAttribute('data-status', /active|done/, { timeout: 60_000 })
    await expect(step(page, 'Draw')).toHaveAttribute('data-status', 'done', { timeout: 240_000 })
    // The run is fully finished once Review completes (the prompt/Refine button
    // lives only in the Define stage, so completion is read from the tracker).
    await expect(step(page, 'Review')).toHaveAttribute('data-status', 'done', { timeout: 240_000 })

    // Overview opens automatically: verdict banner + key numbers + cost.
    await expect(page.getByTestId('stage-tab-overview')).toHaveAttribute('data-active', 'true')
    const overviewBanner = page.getByTestId('overview-verdict-banner')
    await expect(overviewBanner).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('overview-panel')).toContainText(/\$\d/) // cost figure

    // Design → Drawing: a real GA SVG with genuine geometry + a DXF that responds.
    await page.getByTestId('stage-tab-design').click()
    await page.getByTestId('design-panel-drawing').click()
    const svg = page.locator('[data-testid="drawing-svg"] svg')
    await expect(svg).toBeVisible({ timeout: 60_000 })
    expect(await page.locator('[data-testid="drawing-svg"] svg *').count()).toBeGreaterThan(10)

    const runId = await page.getByTestId('step-tracker').getAttribute('data-run-id')
    expect(runId, 'tracker must expose the run id').toBeTruthy()
    const dxfResponse = await request.get(`/api/designs/${runId}/artifacts/ga.dxf`)
    expect(dxfResponse.status()).toBe(200)
    expect((await dxfResponse.body()).length, 'DXF must be a non-trivial file').toBeGreaterThan(2 * 1024)

    // Review: verdict banner + compliance matrix.
    await page.getByTestId('stage-tab-review').click()
    await expect(page.getByTestId('verdict-banner')).toBeVisible({ timeout: 30_000 })
    expect(await page.getByTestId('compliance-row').count(), 'the proof-check matrix has rows').toBeGreaterThan(0)

    // --- (5) Simulate/Test/Approve stages + Projects render as ⊘ stubs ------
    for (const stub of ['simulate', 'test', 'approve'] as const) {
      await page.getByTestId(`stage-tab-${stub}`).click()
      const panel = page.getByTestId(`stage-stub-${stub}`)
      await expect(panel).toBeVisible()
      await expect(page.getByTestId(`stage-stub-badge-${stub}`)).toContainText(/coming/i)
    }
    // Projects entry (left rail) is a clearly-labelled coming stub, not an error.
    await expect(page.getByTestId('projects-stub')).toContainText(/coming/i)
    await expect(page.getByTestId('error-banner')).toHaveCount(0)

    // --- Records rail replay: a completed design becomes a replayable record -
    await expect(page.getByTestId('record-item').first()).toBeVisible()
    await expect(page.getByTestId('record-item').first().getByTestId('status-chip')).toBeVisible()
    await page.getByTestId('new-design').click()
    await expect(page.getByTestId('hero-starter')).toBeVisible() // back on the entry
    await page.getByTestId('record-item').first().click()
    await expect(page.getByTestId('overview-verdict-banner')).toBeVisible({ timeout: 30_000 })

    // --- (4) NO-TAB-YANK: refine while on Calc Sheet keeps Calc Sheet active -
    await page.getByTestId('stage-tab-design').click()
    await page.getByTestId('design-panel-calc').click()
    await expect(page.getByTestId('design-panel-calc')).toHaveAttribute('aria-selected', 'true')

    // Trigger a refine run from the Define stage (the only prompt surface once a
    // design is open). The active Design panel must NOT be yanked back to Drawing.
    await page.getByTestId('stage-tab-define').click()
    await page.getByTestId('prompt-input').fill(REFINE_PROMPT)
    await page.getByTestId('prompt-submit').click()
    await expect(page.getByTestId('prompt-submit')).toBeDisabled({ timeout: 1000 })

    await page.getByTestId('stage-tab-design').click()
    await expect(page.getByTestId('design-panel-calc')).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByTestId('design-panel-drawing')).toHaveAttribute('aria-selected', 'false')
  })
})
