import { expect, test, type Page } from '@playwright/test'

// Expansion Phase 1 E2E: the multi-component picker, auto-detect surfacing, and
// the type-aware Stability summary — all on a STYLED render (real CSS, not just
// HTTP 200), against the real backend + Gemini. The canonical culvert journey is
// re-checked here as a regression that the expansion never broke it.

const CULVERT_PROMPT =
  'single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, BG single line, 25t loading'
const RETAINING_WALL_PROMPT =
  'design a 5 m high RCC cantilever retaining wall, SBC 200 kN/m², BG single-line track surcharge, backfill φ 30°'

const step = (page: Page, name: string) => page.locator(`[data-testid="step-${name}"]`)

// Asserts the page rendered with real stylesheets, not a naked DOM.
async function assertStyledRender(page: Page, cssStatuses: number[]) {
  await expect(page.getByRole('banner')).toBeVisible()
  expect(cssStatuses.length, 'at least one stylesheet must be requested').toBeGreaterThan(0)
  expect(cssStatuses, 'stylesheet must load with 200').toContain(200)
  const headerBg = await page.evaluate(() => getComputedStyle(document.querySelector('header')!).backgroundColor)
  expect(headerBg, 'header must be styled, not transparent').not.toBe('rgba(0, 0, 0, 0)')
  expect(headerBg, 'header must be styled, not plain white').not.toBe('rgb(255, 255, 255)')
}

function trackCss(page: Page): number[] {
  const cssStatuses: number[] = []
  page.on('response', response => {
    if (response.url().includes('/_next/static/css/') || response.url().endsWith('.css')) {
      cssStatuses.push(response.status())
    }
  })
  return cssStatuses
}

test.describe('Expansion Phase 1 — component picker + auto-detect + type summary', () => {
  test('picker shows all 8 available components, none coming-soon, on a styled render', async ({ page }) => {
    const cssStatuses = trackCss(page)
    await page.goto('/app/')
    await assertStyledRender(page, cssStatuses)

    // The gallery is fed by GET /api/components and grouped by domain.
    const picker = page.getByTestId('component-picker')
    await expect(picker).toBeVisible({ timeout: 30_000 })

    // "Let the agent decide" (auto-detect) is offered and pressed by default.
    const auto = page.getByTestId('component-auto')
    await expect(auto).toBeVisible()
    await expect(auto).toHaveAttribute('aria-pressed', 'true')

    // Expansion Phase 3 flips the three mechanical types to available, so the whole
    // roadmap is delivered: EIGHT selectable components (5 civil + 3 mechanical).
    const available = picker.locator('[data-testid="component-card"][data-status="available"]')
    await expect(available.first()).toBeVisible()
    expect(
      await available.count(),
      'eight available components once the mechanical domain lands',
    ).toBe(8)

    // Both domains are represented — the five civil types and the three mechanical.
    await expect(picker).toContainText(/culvert/i)
    await expect(picker).toContainText(/retaining wall/i)
    await expect(picker).toContainText(/plate girder/i)
    await expect(picker).toContainText(/slab \/ t-beam/i)
    await expect(picker).toContainText(/pier & abutment/i)
    await expect(picker).toContainText(/structural steel/i)
    await expect(picker).toContainText(/rolling-stock/i)
    await expect(picker).toContainText(/machine element/i)

    // Each mechanical type is a real, selectable available card.
    const mechanical = ['structural_steel_member', 'rolling_stock_member', 'machine_element'] as const
    for (const typeId of mechanical) {
      const card = picker.locator(`[data-testid="component-card"][data-type-id="${typeId}"]`)
      await expect(card, `${typeId} card is present`).toBeVisible()
      await expect(card, `${typeId} is available, not greyed`).toHaveAttribute('data-status', 'available')
    }

    // The whole roadmap is delivered: ZERO greyed "Coming soon" cards, no badge.
    const comingSoon = picker.locator('[data-testid="component-card"][data-status="coming_soon"]')
    expect(await comingSoon.count(), 'no component remains greyed "Coming soon"').toBe(0)
    await expect(page.getByTestId('coming-soon-badge')).toHaveCount(0)

    // Selecting each mechanical card sets it active + shows the type-aware prompt hint.
    for (const typeId of mechanical) {
      const card = picker.locator(`[data-testid="component-card"][data-type-id="${typeId}"]`)
      await card.click()
      await expect(card, `${typeId} becomes the active component`).toHaveAttribute('data-active', 'true')
      await expect(page.getByTestId('prompt-hint')).toBeVisible()
    }

    // Nothing on the page reads as an unfinished stub.
    await expect(page.locator('text=/Coming in Phase/i')).toHaveCount(0)
  })

  test('regression: canonical culvert prompt still completes with a real GA SVG', async ({ page }) => {
    test.fixme(
      true,
      'DEFERRED: Gemini project over monthly spend cap — live LLM calls 429 RESOURCE_EXHAUSTED; re-enable when billing resets',
    )
    test.setTimeout(300_000)
    const cssStatuses = trackCss(page)
    await page.goto('/app/')
    await assertStyledRender(page, cssStatuses)

    // Leave the picker on auto-detect; run the canonical culvert prompt.
    await expect(page.getByTestId('component-auto')).toHaveAttribute('aria-pressed', 'true', { timeout: 30_000 })
    await page.getByTestId('prompt-input').fill(CULVERT_PROMPT)
    await page.getByTestId('prompt-submit').click()
    await expect(page.getByTestId('prompt-submit')).toBeDisabled({ timeout: 500 })

    await expect(step(page, 'Understand')).toHaveAttribute('data-status', /active|done/, { timeout: 60_000 })
    await expect(step(page, 'Draw')).toHaveAttribute('data-status', 'done', { timeout: 240_000 })

    // Real inline GA SVG with genuine geometry.
    await page.getByTestId('tab-drawing').click()
    const svg = page.locator('[data-testid="drawing-svg"] svg')
    await expect(svg).toBeVisible({ timeout: 60_000 })
    expect(await page.locator('[data-testid="drawing-svg"] svg *').count()).toBeGreaterThan(10)

    // Run finishes; the prompt re-opens as Refine.
    await expect(page.getByTestId('prompt-submit')).toHaveText('Refine', { timeout: 240_000 })
  })

  test('retaining-wall prompt auto-routes → GA SVG + stability summary + proof-check verdict', async ({
    page,
    request,
  }) => {
    test.fixme(
      true,
      'DEFERRED: Gemini project over monthly spend cap — live LLM calls 429 RESOURCE_EXHAUSTED; re-enable when billing resets',
    )
    test.setTimeout(300_000)
    const cssStatuses = trackCss(page)
    await page.goto('/app/')
    await assertStyledRender(page, cssStatuses)

    // Auto-detect path: no explicit pick, the agent classifies the request.
    await expect(page.getByTestId('component-auto')).toHaveAttribute('aria-pressed', 'true', { timeout: 30_000 })
    await page.getByTestId('prompt-input').fill(RETAINING_WALL_PROMPT)
    await page.getByTestId('prompt-submit').click()
    await expect(page.getByTestId('prompt-submit')).toBeDisabled({ timeout: 500 })

    await expect(step(page, 'Understand')).toHaveAttribute('data-status', /active|done/, { timeout: 60_000 })

    // Auto-detect surfacing: the classified type appears as a chip with a switch.
    const chip = page.getByTestId('detected-type-chip')
    await expect(chip).toBeVisible({ timeout: 120_000 })
    await expect(chip).toContainText(/wall/i)
    await expect(page.getByTestId('detected-type-switch')).toBeVisible()

    // A real GA SVG streams into the Drawing tab.
    await expect(step(page, 'Draw')).toHaveAttribute('data-status', 'done', { timeout: 240_000 })
    await page.getByTestId('tab-drawing').click()
    const svg = page.locator('[data-testid="drawing-svg"] svg')
    await expect(svg).toBeVisible({ timeout: 60_000 })
    expect(await page.locator('[data-testid="drawing-svg"] svg *').count(), 'RW GA SVG must carry geometry').toBeGreaterThan(
      10,
    )

    // Run finishes.
    await expect(page.getByTestId('prompt-submit')).toHaveText('Refine', { timeout: 240_000 })

    // Type-aware Stability summary (tab 0): FoS overturning, FoS sliding, bearing.
    await page.getByTestId('tab-summary').click()
    const panel = page.getByTestId('type-summary-panel')
    await expect(panel).toBeVisible({ timeout: 30_000 })

    const fosOver = page.getByTestId('type-summary-fos_overturning')
    const fosSlide = page.getByTestId('type-summary-fos_sliding')
    const bearing = page.getByTestId('type-summary-bearing')
    await expect(fosOver).toBeVisible()
    await expect(fosSlide).toBeVisible()
    await expect(bearing).toBeVisible()

    // Each metric carries a real green/red pass verdict.
    for (const row of [fosOver, fosSlide, bearing]) {
      const pass = await row.getAttribute('data-pass')
      expect(pass, 'each stability metric must resolve to a pass/fail').toMatch(/^(true|false)$/)
    }
    await expect(fosOver).toContainText('2.0') // required minimum shown
    await expect(fosSlide).toContainText('1.5')
    await expect(bearing).toContainText(/kN\/m²/)

    // Proof-check verdict block renders.
    await page.getByTestId('tab-proof-check').click()
    await expect(page.getByTestId('verdict-banner')).toBeVisible({ timeout: 30_000 })

    // The snapshot carries component_type + the retaining-wall type_summary shape.
    const runId = await page.getByTestId('step-tracker').getAttribute('data-run-id')
    expect(runId, 'tracker must expose the run id').toBeTruthy()
    const snapRes = await request.get(`/api/designs/${runId}`)
    expect(snapRes.status()).toBe(200)
    const snap = (await snapRes.json()).data
    expect(String(snap.component_type ?? ''), 'snapshot names the retaining-wall component').toMatch(/wall/i)
    expect(snap.type_summary, 'snapshot carries a type_summary').toBeTruthy()
    for (const key of ['fos_overturning', 'fos_sliding', 'max_bearing_pressure_kn_m2', 'sbc_kn_m2', 'bearing_ok']) {
      expect(snap.type_summary, `type_summary.${key} present`).toHaveProperty(key)
    }

    await expect(page.locator('text=/Coming in Phase/i')).toHaveCount(0)
  })
})
