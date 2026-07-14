import { expect, test, type Page } from '@playwright/test'

// Expansion Phase 3 — Mechanical Domain live journeys, one per new mechanical
// component (structural steel member / rolling-stock member / machine element).
// Each drives the SAME journey the civil components prove: pick the card →
// step tracker → real GA SVG (weld-symbol drawing) → type-aware Stress/Strength/
// FoS summary → proof-check verdict, on a STYLED render against the real backend
// + Gemini. Proves the abstraction is not civil-specific — same interface + same
// IR-protocol review spine, differing only in codes (IS 800 / RDSO / machine
// design) and drawing conventions.
//
// DEFERRED: the Gemini project is over its monthly spend cap, so every live LLM
// call returns 429 RESOURCE_EXHAUSTED. These specs SUBMIT a prompt, so they are
// marked `test.fixme` and skipped by the offline binding gate. Re-enable them
// (drop the `test.fixme`) once billing resets — the assertions below document
// the intended behaviour and are ready to run as-is.

const step = (page: Page, name: string) => page.locator(`[data-testid="step-${name}"]`)

function trackCss(page: Page): number[] {
  const cssStatuses: number[] = []
  page.on('response', response => {
    if (response.url().includes('/_next/static/css/') || response.url().endsWith('.css')) {
      cssStatuses.push(response.status())
    }
  })
  return cssStatuses
}

async function assertStyledRender(page: Page, cssStatuses: number[]) {
  await expect(page.getByRole('banner')).toBeVisible()
  expect(cssStatuses.length, 'at least one stylesheet must be requested').toBeGreaterThan(0)
  expect(cssStatuses, 'stylesheet must load with 200').toContain(200)
  const headerBg = await page.evaluate(() => getComputedStyle(document.querySelector('header')!).backgroundColor)
  expect(headerBg, 'header must be styled, not transparent').not.toBe('rgba(0, 0, 0, 0)')
  expect(headerBg, 'header must be styled, not plain white').not.toBe('rgb(255, 255, 255)')
}

/** Pick a mechanical card explicitly, submit the prompt, and prove the full journey. */
async function runMechanicalJourney(
  page: Page,
  opts: {
    typeId: string
    prompt: string
    /** type_summary field(s) that must render as pass/fail rows for this type. */
    summaryTestIds: string[]
  },
) {
  const cssStatuses = trackCss(page)
  await page.goto('/app/')
  await assertStyledRender(page, cssStatuses)

  // Explicit pick of the mechanical component from the (now-available) gallery.
  const card = page.locator(`[data-testid="component-card"][data-type-id="${opts.typeId}"]`)
  await expect(card).toBeVisible({ timeout: 30_000 })
  await expect(card).toHaveAttribute('data-status', 'available')
  await card.click()
  await expect(card).toHaveAttribute('data-active', 'true')

  await page.getByTestId('prompt-input').fill(opts.prompt)
  await page.getByTestId('prompt-submit').click()
  await expect(page.getByTestId('prompt-submit')).toBeDisabled({ timeout: 500 })

  // Step tracker advances through the deterministic pipeline.
  await expect(step(page, 'Understand')).toHaveAttribute('data-status', /active|done/, { timeout: 60_000 })
  await expect(step(page, 'Draw')).toHaveAttribute('data-status', 'done', { timeout: 240_000 })

  // Real inline GA SVG (mechanical drawing with weld symbols) — Design → Drawing.
  await page.getByTestId('stage-tab-design').click()
  await page.getByTestId('design-panel-drawing').click()
  const svg = page.locator('[data-testid="drawing-svg"] svg')
  await expect(svg).toBeVisible({ timeout: 60_000 })
  expect(await page.locator('[data-testid="drawing-svg"] svg *').count()).toBeGreaterThan(10)

  // Run finishes; the prompt re-opens as Refine.
  await expect(page.getByTestId('prompt-submit')).toHaveText('Refine', { timeout: 240_000 })

  // Type-aware Stress / Strength / FoS summary now lives in the Overview stage:
  // each declared metric row resolves to a real green/red pass verdict.
  await page.getByTestId('stage-tab-overview').click()
  const panel = page.getByTestId('type-summary-panel')
  await expect(panel).toBeVisible({ timeout: 30_000 })
  for (const testid of opts.summaryTestIds) {
    const row = page.getByTestId(testid)
    await expect(row, `${testid} renders`).toBeVisible()
    const pass = await row.getAttribute('data-pass')
    expect(pass, `${testid} resolves to a pass/fail`).toMatch(/^(true|false)$/)
  }

  // Proof-check verdict block renders in the Review stage.
  await page.getByTestId('stage-tab-review').click()
  await expect(page.getByTestId('verdict-banner')).toBeVisible({ timeout: 30_000 })

  await expect(page.locator('text=/Coming in Phase/i')).toHaveCount(0)
}

test.describe('Expansion Phase 3 — mechanical breadth live journeys (deferred)', () => {
  test('structural steel member: pick → weld-symbol GA SVG → utilisation summary → proof-check verdict', async ({
    page,
  }) => {
    test.fixme(
      true,
      'DEFERRED: Gemini project over monthly spend cap — live LLM calls 429 RESOURCE_EXHAUSTED; re-enable when billing resets',
    )
    test.setTimeout(300_000)
    await runMechanicalJourney(page, {
      typeId: 'structural_steel_member',
      prompt: 'design a welded steel bracket, IS 800, 20 kN tip load, 6 m gantry post',
      // utilisation_summary → bending / shear / axial / weld comparison rows.
      summaryTestIds: [
        'type-summary-bending',
        'type-summary-shear_stress',
        'type-summary-axial',
        'type-summary-weld',
      ],
    })
  })

  test('rolling-stock member: pick → GA SVG → strength summary → proof-check verdict', async ({ page }) => {
    test.fixme(
      true,
      'DEFERRED: Gemini project over monthly spend cap — live LLM calls 429 RESOURCE_EXHAUSTED; re-enable when billing resets',
    )
    test.setTimeout(300_000)
    await runMechanicalJourney(page, {
      typeId: 'rolling_stock_member',
      prompt: 'design a wagon underframe sole-bar member to RDSO specs, 2.4 m',
      // strength_summary → bending + shear comparison rows (governing_load_case
      // renders as a labelled fallback value).
      summaryTestIds: ['type-summary-bending', 'type-summary-shear_stress'],
    })
  })

  test('machine element: pick → detail GA SVG → factor-of-safety summary → proof-check verdict', async ({ page }) => {
    test.fixme(
      true,
      'DEFERRED: Gemini project over monthly spend cap — live LLM calls 429 RESOURCE_EXHAUSTED; re-enable when billing resets',
    )
    test.setTimeout(300_000)
    await runMechanicalJourney(page, {
      typeId: 'machine_element',
      prompt: 'design a transmission shaft for 20 kW at 1000 rpm',
      // fos_summary → max-stress-vs-permissible + factor-of-safety-vs-required rows.
      summaryTestIds: ['type-summary-machine_stress', 'type-summary-machine_fos'],
    })
  })
})
