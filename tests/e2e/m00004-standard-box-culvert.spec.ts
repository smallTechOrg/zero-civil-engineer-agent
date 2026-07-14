import { expect, test, type Page } from '@playwright/test'

// M-00004 Standard Box Culvert (RDSO) — the ninth registered component, a
// params-direct (standard-driven) type. This spec asserts, on a STYLED render:
//   (1) picking the M-00004 card reveals the typed parameter form (the NL prompt
//       box is replaced);
//   (2) submitting span 4 / height 4 / fill 2 / surcharge 0 streams a real GA SVG,
//       the type-summary shows the selected config (F2_4x4) + a PROVISIONAL marking,
//       and the M-00004 PDF artefact resolves to a non-empty application/pdf.
// Because intake is params-direct (zero LLM understand/extract calls) and the
// review-memo narration is non-fatal, this run completes without a live LLM.
// The existing culvert / retaining-wall / breadth specs are left intact.

const M00004_TYPE_ID = 'm00004_box_culvert'

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

async function pickM00004(page: Page) {
  const picker = page.getByTestId('component-picker')
  await expect(picker).toBeVisible({ timeout: 30_000 })
  const card = picker.locator(`[data-testid="component-card"][data-type-id="${M00004_TYPE_ID}"]`)
  await expect(card, 'the M-00004 card must appear in the gallery once registered').toBeVisible({ timeout: 30_000 })
  await expect(card).toHaveAttribute('data-status', 'available')
  await card.click()
  await expect(card).toHaveAttribute('data-active', 'true')
}

test.describe('M-00004 Standard Box Culvert — picker → parameter form → outputs', () => {
  test('picking the M-00004 card reveals the typed parameter form (NL prompt box replaced)', async ({ page }) => {
    const cssStatuses = trackCss(page)
    await page.goto('/app/')
    await assertStyledRender(page, cssStatuses)

    // Before selection the NL prompt box is shown, not the form.
    await expect(page.getByTestId('component-picker')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('m00004-form')).toHaveCount(0)

    await pickM00004(page)

    // The typed parameter form replaces the NL prompt box.
    const form = page.getByTestId('m00004-form')
    await expect(form).toBeVisible()
    await expect(page.getByTestId('prompt-input'), 'the NL prompt box is hidden for a params-direct component').toHaveCount(0)

    // Every documented field is present with the right defaults.
    for (const key of [
      'clear_span_m',
      'clear_height_m',
      'cushion_m',
      'surcharge_kn_m2',
      'formation_width_m',
      'side_slope_h_per_v',
      'concrete_grade',
      'steel_grade',
    ]) {
      await expect(page.getByTestId(`m00004-${key}`), `field ${key} present`).toBeVisible()
    }
    await expect(page.getByTestId('m00004-surcharge_kn_m2')).toHaveValue('0')
    await expect(page.getByTestId('m00004-formation_width_m')).toHaveValue('6.85')
    await expect(page.getByTestId('m00004-side_slope_h_per_v')).toHaveValue('2')
    await expect(page.getByTestId('m00004-concrete_grade')).toHaveValue('M30')
    await expect(page.getByTestId('m00004-steel_grade')).toHaveValue('Fe500')

    // Client-side validation blocks an empty required field without a run.
    await page.getByTestId('m00004-submit').click()
    await expect(page.getByTestId('m00004-clear_span_m-error')).toBeVisible()

    // Nothing on the page reads as an unfinished stub.
    await expect(page.locator('text=/Coming in Phase/i')).toHaveCount(0)
  })

  test('submit 4×4 m, fill 2 m → real GA SVG + selected config + PROVISIONAL + reachable PDF', async ({
    page,
    request,
  }) => {
    test.setTimeout(300_000)
    const cssStatuses = trackCss(page)
    await page.goto('/app/')
    await assertStyledRender(page, cssStatuses)

    await pickM00004(page)

    // Enter the canonical box: span 4 / height 4 / fill 2 / surcharge 0.
    await page.getByTestId('m00004-clear_span_m').fill('4')
    await page.getByTestId('m00004-clear_height_m').fill('4')
    await page.getByTestId('m00004-cushion_m').fill('2')
    await page.getByTestId('m00004-surcharge_kn_m2').fill('0')

    await page.getByTestId('m00004-submit').click()
    await expect(page.getByTestId('m00004-submit')).toBeDisabled({ timeout: 2_000 })

    // Params-direct: Understand + Extract go straight to done (no LLM intake),
    // then the run streams through Analyse → Check → Draw → Review.
    await expect(step(page, 'Understand')).toHaveAttribute('data-status', /active|done/, { timeout: 60_000 })
    await expect(step(page, 'Draw')).toHaveAttribute('data-status', 'done', { timeout: 240_000 })

    // A real inline GA SVG with genuine geometry streams into the Drawing tab.
    await page.getByTestId('tab-drawing').click()
    const svg = page.locator('[data-testid="drawing-svg"] svg')
    await expect(svg).toBeVisible({ timeout: 60_000 })
    expect(await page.locator('[data-testid="drawing-svg"] svg *').count()).toBeGreaterThan(10)

    // The "Open M-00004 sheet (PDF)" affordance is present on the Drawing toolbar.
    await expect(page.getByTestId('open-m00004-pdf')).toBeVisible({ timeout: 60_000 })

    // The type-summary shows the selected standard config + the PROVISIONAL marking.
    await page.getByTestId('tab-summary').click()
    const panel = page.getByTestId('type-summary-panel')
    await expect(panel).toBeVisible({ timeout: 30_000 })
    await expect(panel, 'the selected config id F2_4x4 is shown').toContainText('F2_4x4')
    await expect(page.getByTestId('type-summary-provisional')).toBeVisible()
    await expect(panel).toContainText(/PROVISIONAL/i)

    // The run finishes and the form re-opens.
    await expect(page.getByTestId('m00004-submit')).toBeEnabled({ timeout: 240_000 })

    // The snapshot names the M-00004 component and carries the m00004_standard summary + the PDF artefact.
    const runId = await page.getByTestId('step-tracker').getAttribute('data-run-id')
    expect(runId, 'tracker must expose the run id').toBeTruthy()
    const snapRes = await request.get(`/api/designs/${runId}`)
    expect(snapRes.status()).toBe(200)
    const snap = (await snapRes.json()).data
    expect(String(snap.component_type ?? '')).toBe(M00004_TYPE_ID)
    expect(snap.type_summary, 'snapshot carries a type_summary').toBeTruthy()
    expect(String(snap.type_summary.config_id ?? ''), 'config F2_4x4 selected for 4×4/2 m').toBe('F2_4x4')
    expect(
      (snap.artefacts ?? []).some((a: { kind: string }) => a.kind === 'm00004_sheet'),
      'the run emitted the m00004_sheet PDF artefact',
    ).toBe(true)

    // The M-00004 PDF resolves inline to a non-empty application/pdf.
    const pdfRes = await request.get(`/api/designs/${runId}/artifacts/m00004_sheet.pdf`)
    expect(pdfRes.status(), 'the PDF artefact is reachable').toBe(200)
    expect(pdfRes.headers()['content-type'] ?? '', 'served as application/pdf').toContain('application/pdf')
    const pdfBody = await pdfRes.body()
    expect(pdfBody.length, 'the PDF is non-empty').toBeGreaterThan(1000)
    expect(pdfBody.subarray(0, 5).toString('latin1'), 'a valid PDF header').toBe('%PDF-')

    await expect(page.locator('text=/Coming in Phase/i')).toHaveCount(0)
  })
})
