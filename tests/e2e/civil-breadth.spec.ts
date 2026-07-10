import { expect, test, type Page } from '@playwright/test'

// Expansion Phase 2 — Civil Breadth live journeys, one per new civil component
// (plate girder / slab-T-beam / pier & abutment). Each drives the SAME journey
// the retaining wall proves in component-expansion.spec.ts: pick (or describe) →
// step tracker → real GA SVG → type-aware Stability/Capacity summary →
// proof-check verdict, on a STYLED render against the real backend + Gemini.
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

/** Pick a civil card explicitly, submit the prompt, and prove the full journey. */
async function runCivilJourney(
  page: Page,
  opts: {
    typeId: string
    prompt: string
    chipMatch: RegExp
    /** type_summary field(s) that must render as pass/fail rows for this type. */
    summaryTestIds: string[]
  },
) {
  const cssStatuses = trackCss(page)
  await page.goto('/app/')
  await assertStyledRender(page, cssStatuses)

  // Explicit pick of the civil component from the (now-available) gallery.
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

  // Real inline GA SVG with genuine geometry.
  await page.getByTestId('tab-drawing').click()
  const svg = page.locator('[data-testid="drawing-svg"] svg')
  await expect(svg).toBeVisible({ timeout: 60_000 })
  expect(await page.locator('[data-testid="drawing-svg"] svg *').count()).toBeGreaterThan(10)

  // Run finishes; the prompt re-opens as Refine.
  await expect(page.getByTestId('prompt-submit')).toHaveText('Refine', { timeout: 240_000 })

  // Type-aware Stability / Capacity summary (tab 0): each declared metric row
  // resolves to a real green/red pass verdict.
  await page.getByTestId('tab-summary').click()
  const panel = page.getByTestId('type-summary-panel')
  await expect(panel).toBeVisible({ timeout: 30_000 })
  for (const testid of opts.summaryTestIds) {
    const row = page.getByTestId(testid)
    await expect(row, `${testid} renders`).toBeVisible()
    const pass = await row.getAttribute('data-pass')
    expect(pass, `${testid} resolves to a pass/fail`).toMatch(/^(true|false)$/)
  }

  // Proof-check verdict block renders.
  await page.getByTestId('tab-proof-check').click()
  await expect(page.getByTestId('verdict-banner')).toBeVisible({ timeout: 30_000 })

  await expect(page.locator('text=/Coming in Phase/i')).toHaveCount(0)
}

test.describe('Expansion Phase 2 — civil breadth live journeys (deferred)', () => {
  test('steel plate girder: pick → GA SVG → stress summary → proof-check verdict', async ({ page }) => {
    test.fixme(
      true,
      'DEFERRED: Gemini project over monthly spend cap — live LLM calls 429 RESOURCE_EXHAUSTED; re-enable when billing resets',
    )
    test.setTimeout(300_000)
    await runCivilJourney(page, {
      typeId: 'plate_girder',
      prompt: 'design a welded steel plate girder for a 24 m railway bridge span, BG single line, 25t loading',
      chipMatch: /girder/i,
      // stress_summary → bending / shear / deflection comparison rows.
      summaryTestIds: ['type-summary-bending', 'type-summary-shear_stress', 'type-summary-deflection'],
    })
  })

  test('RCC slab / T-beam: pick → GA SVG → flexure summary → proof-check verdict', async ({ page }) => {
    test.fixme(
      true,
      'DEFERRED: Gemini project over monthly spend cap — live LLM calls 429 RESOURCE_EXHAUSTED; re-enable when billing resets',
    )
    test.setTimeout(300_000)
    await runCivilJourney(page, {
      typeId: 'slab_tbeam',
      prompt: 'design an RCC T-beam superstructure for a 12 m railway span, 25t loading',
      chipMatch: /t-beam|slab/i,
      // flexure_summary → required-vs-provided depth + shear comparison rows.
      summaryTestIds: ['type-summary-flexure_depth', 'type-summary-slab_shear'],
    })
  })

  test('pier & abutment: pick → GA SVG → stability summary → proof-check verdict', async ({ page }) => {
    test.fixme(
      true,
      'DEFERRED: Gemini project over monthly spend cap — live LLM calls 429 RESOURCE_EXHAUSTED; re-enable when billing resets',
    )
    test.setTimeout(300_000)
    await runCivilJourney(page, {
      typeId: 'pier_abutment',
      prompt: 'design a bridge pier for a 20 m railway span, SBC 300 kN/m², two-span continuous',
      chipMatch: /pier|abutment/i,
      // stability → FoS overturning / sliding + bearing-vs-SBC comparison.
      summaryTestIds: ['type-summary-fos_overturning', 'type-summary-fos_sliding', 'type-summary-bearing'],
    })
  })
})
