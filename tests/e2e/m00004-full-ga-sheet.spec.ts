import { expect, test, type Page } from '@playwright/test'

// M-00004 Standard Box Culvert (RDSO) — Phase 2: the FULL RDSO/M-00004 GA sheet.
// This spec asserts, on a STYLED render, that after submitting the params-direct
// form (span 4 / height 4 / fill 2 / surcharge 0) the "Full GA Sheet" panel:
//   (1) renders the six named per-diagram drawings' SVGs inline;
//   (2) exposes a per-diagram DXF download link that resolves (200);
//   (3) offers the composed `m00004_ga_sheet.pdf` inline (application/pdf);
//   (4) offers the `m00004_bundle.zip` download affordance;
//   (5) STEP-part downloads are present (assembly/box/curtain/return + fused);
//   (6) everything carries a visible PROVISIONAL marking;
//   (7) the run's resolved grade is M35 — the form left concrete grade on Auto
//       (derive) + exposure Severe, so the backend DERIVES M35 (guards FIX f-1).
//
// The full backend wiring (per-diagram DXF/SVG, STEP parts, compose + zip) lands
// in the sibling Phase-2 slices; this spec is written to the FIXED artefact
// filenames/kinds (spec/capabilities/m00004-box-culvert.md § "New artefact kinds")
// so it passes once the whole stack is integrated at the phase gate. It runs on
// E2E_PORT=8004 (playwright.config default). Intake is params-direct (zero LLM
// understand/extract) and the review-memo narration is non-fatal.

const M00004_TYPE_ID = 'm00004_box_culvert'

// The six named engineering drawings (subset of the ten) — data-testid keys.
const NAMED_DRAWINGS = [
  'elevation',
  'cross_section',
  'plan',
  'curtain_wall',
  'typical_details',
  'return_wall',
] as const

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

test.describe('M-00004 Standard Box Culvert — full RDSO/M-00004 GA sheet', () => {
  test('submit 4×4 m, fill 2 m → six drawings + DXF + composed PDF + zip + STEP parts', async ({
    page,
    request,
  }) => {
    test.setTimeout(360_000)
    const cssStatuses = trackCss(page)
    await page.goto('/app/')
    await assertStyledRender(page, cssStatuses)

    await pickM00004(page)

    // Fill the canonical box: span 4 / height 4 / fill 2 / surcharge 0.
    await page.getByTestId('m00004-clear_span_m').fill('4')
    await page.getByTestId('m00004-clear_height_m').fill('4')
    await page.getByTestId('m00004-cushion_m').fill('2')
    await page.getByTestId('m00004-surcharge_kn_m2').fill('0')

    // Capture the run id from the submit response (robust, testid-independent).
    const submitResponse = page.waitForResponse(
      r => r.request().method() === 'POST' && /\/api\/sessions\/[^/]+\/designs$/.test(r.url()),
      { timeout: 60_000 },
    )
    await page.getByTestId('m00004-submit').click()
    const resp = await submitResponse
    expect(resp.status(), 'the params-direct submit is accepted').toBe(200)
    const runId = (await resp.json())?.data?.run_id as string
    expect(runId, 'the submit response carries a run_id').toBeTruthy()

    // The redesigned shell UNMOUNTS the param form on submit (Define → Overview),
    // so the old "submit re-enabled" sync no longer exists. Sync instead on the
    // run reaching a terminal state via the snapshot — an LLM-INDEPENDENT signal:
    // this run is params-direct and its only LLM call is the non-fatal review-memo
    // narration, so it completes even if Gemini returns 429 (quota). We must NOT
    // sync on anything that a successful LLM call would gate.
    await expect
      .poll(
        async () => {
          const r = await request.get(`/api/designs/${runId}`)
          if (r.status() !== 200) return 'pending'
          return String((await r.json())?.data?.status ?? 'pending')
        },
        { timeout: 300_000, intervals: [2_000] },
      )
      .toBe('completed')

    // Navigate to the Design stage → the M-00004-only "Full GA Sheet" panel. The
    // Design panel becoming available (the sheet tab + its artefacts below) is the
    // real post-run signal in the redesigned flow.
    await page.getByTestId('stage-tab-design').click()
    const sheetTab = page.getByTestId('design-panel-sheet')
    await expect(sheetTab, 'the Full GA Sheet panel is exposed for M-00004').toBeVisible({ timeout: 30_000 })
    await sheetTab.click()

    const panel = page.getByTestId('m00004-sheet-panel')
    await expect(panel).toBeVisible({ timeout: 30_000 })

    // (6) Everything carries a PROVISIONAL marking.
    await expect(page.getByTestId('m00004-sheet-provisional')).toContainText(/PROVISIONAL/i)

    // (1) The six named drawings render their SVGs inline.
    for (const key of NAMED_DRAWINGS) {
      const svgHost = page.getByTestId(`m00004-diagram-svg-${key}`)
      await expect(svgHost, `drawing ${key} SVG renders inline`).toBeVisible({ timeout: 120_000 })
      expect(
        await page.locator(`[data-testid="m00004-diagram-svg-${key}"] svg *`).count(),
        `drawing ${key} has real geometry`,
      ).toBeGreaterThan(1)
    }

    // (2) At least one per-diagram DXF download link resolves (200 + DXF body).
    const dxfLink = page.getByTestId('m00004-diagram-dxf-cross_section')
    await expect(dxfLink).toBeVisible()
    const dxfHref = await dxfLink.getAttribute('href')
    expect(dxfHref, 'the cross-section DXF link has an href').toBeTruthy()
    const dxfRes = await request.get(dxfHref!)
    expect(dxfRes.status(), 'the per-diagram DXF resolves').toBe(200)
    expect((await dxfRes.body()).length, 'the DXF is non-empty').toBeGreaterThan(100)

    // (3) The composed GA sheet is offered inline and resolves to application/pdf.
    const gaSheetLink = page.getByTestId('open-m00004-ga-sheet')
    await expect(gaSheetLink).toBeVisible({ timeout: 60_000 })
    const gaHref = await gaSheetLink.getAttribute('href')
    expect(gaHref, 'the composed GA sheet link points at the artefact').toContain('m00004_ga_sheet.pdf')
    const gaRes = await request.get(gaHref!)
    expect(gaRes.status(), 'the composed GA sheet resolves').toBe(200)
    expect(gaRes.headers()['content-type'] ?? '', 'served inline as application/pdf').toContain('application/pdf')
    const gaBody = await gaRes.body()
    expect(gaBody.subarray(0, 5).toString('latin1'), 'a valid PDF header').toBe('%PDF-')

    // (4) The bundle .zip download affordance exists and points at the artefact.
    const bundleLink = page.getByTestId('download-m00004-bundle')
    await expect(bundleLink).toBeVisible()
    expect(await bundleLink.getAttribute('href'), 'the bundle link points at the zip').toContain('m00004_bundle.zip')

    // (5) STEP-part downloads are present (at least the full assembly).
    await expect(page.getByTestId('m00004-step-assembly_step')).toBeVisible({ timeout: 60_000 })

    // Cross-check against the snapshot: the run emitted the Phase-2 kinds.
    const snapRes = await request.get(`/api/designs/${runId}`)
    expect(snapRes.status()).toBe(200)
    const snap = (await snapRes.json()).data
    expect(String(snap.component_type ?? '')).toBe(M00004_TYPE_ID)

    // Guards FIX f-1: the form left concrete grade on Auto (derive) + exposure
    // Severe, so the backend must DERIVE M35 (not the old hard-coded M30). This is
    // the one grade rendered everywhere (notes/type_summary/title block).
    expect(
      String(snap.type_summary?.concrete_grade_resolved ?? ''),
      'Auto (derive) + Severe exposure resolves to M35',
    ).toBe('M35')

    const kinds: string[] = (snap.artefacts ?? []).map((a: { kind: string }) => a.kind)
    for (const kind of [
      'elevation_svg',
      'cross_section_svg',
      'plan_svg',
      'm00004_ga_sheet',
      'm00004_bundle',
      'assembly_step',
    ]) {
      expect(kinds, `snapshot carries the ${kind} artefact`).toContain(kind)
    }

    // Nothing on the surface reads as an unfinished stub.
    await expect(page.locator('text=/Coming in Phase/i')).toHaveCount(0)
  })
})
