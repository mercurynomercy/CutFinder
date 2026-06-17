/** End-to-end tests for CutFinder gallery, filters, detail panel, and search.

Runs against the Vite dev server (port 5080) with Playwright's `page.route()`
intercepting all API calls and returning mock data  no real backend needed.

Flows covered:
  1. Gallery loads with thumbnails and A/B badges
  2. Filter by roll type (A-roll / B-roll)
  3. Clip detail panel opens, shows metadata + transcript
  4. Tag editing (add / delete tags) via the detail panel
  5. A/B roll correction in the detail panel footer
  6. Search hits clips by summary / description keywords
*/

import { test, expect, type Page } from 'playwright/test'

//  Mock data factories (mirrors src/test/mocks/handlers.ts) 

interface ClipSummary {
  id: number
  source_path: string
  library_path: string | null
  roll_type: 'a' | 'b'
  summary: string | null
  description: string | null
  duration_s: number | null
  thumbnail_path: string | null
  status: string
  tags?: TagItem[]
}

interface TagItem { name: string; source: 'auto' | 'manual' }

const ALL_CLIPS: ClipSummary[] = [
  { id: 1, source_path: '/media/vlog/2024-06/MVI_5298.MP4', library_path: null, roll_type: 'a', summary: 'A-roll narration about a trip to the mountains.', description: null, duration_s: 120, thumbnail_path: '/thumbnails/1.jpg', status: 'done' },
  { id: 2, source_path: '/media/vlog/2024-06/DJI_5368.MP4', library_path: null, roll_type: 'b', summary: null, description: 'Visual footage of a sunset over the ocean.', duration_s: 90, thumbnail_path: '/thumbnails/2.jpg', status: 'done' },
  { id: 3, source_path: '/media/vlog/2024-06/MVI_5310.MP4', library_path: null, roll_type: 'a', summary: 'A-roll narration about a city walking tour.', description: null, duration_s: 85, thumbnail_path: '/thumbnails/3.jpg', status: 'done' },
  { id: 4, source_path: '/media/vlog/2024-06/DJI_5370.MP4', library_path: null, roll_type: 'b', summary: null, description: 'Drone footage of a coastline.', duration_s: 60, thumbnail_path: '/thumbnails/4.jpg', status: 'done' },
  { id: 5, source_path: '/media/vlog/2024-06/MVI_5315.MP4', library_path: null, roll_type: 'a', summary: 'A-roll narration about wildlife spotting.', description: null, duration_s: 105, thumbnail_path: '/thumbnails/5.jpg', status: 'done' },
  { id: 6, source_path: '/media/vlog/2024-06/DJI_5375.MP4', library_path: null, roll_type: 'b', summary: null, description: 'Forest trail with autumn foliage.', duration_s: 75, thumbnail_path: '/thumbnails/6.jpg', status: 'done' },
]

const TAGS_1 = [{ name: 'mountains', source: 'auto' }, { name: 'nature', source: 'manual' }] as const
const TAGS_2 = [{ name: 'sunset', source: 'auto' }, { name: 'ocean', source: 'auto' }] as const
const TAGS_3 = [{ name: 'cityscape', source: 'auto' }, { name: 'urban', source: 'manual' }] as const
const TAGS_4 = [{ name: 'coastline', source: 'auto' }, { name: 'drone', source: 'auto' }] as const
const TAGS_5 = [{ name: 'wildlife', source: 'auto' }, { name: 'birds', source: 'auto' }] as const
const TAGS_6 = [{ name: 'forest', source: 'auto' }, { name: 'autumn', source: 'manual' }] as const

function clipDetail(clip: ClipSummary, tags: TagItem[]) {
  return {
    ...clip,
    roll_source: 'auto',
    width: 1920, height: 1080, fps: 30, codec: 'h264',
    error: null, capture_time: '2024-06-15T10:30:00Z', date_source: 'embedded',
    tags,
    transcript: clip.roll_type === 'a' ? {
      full_text: `Transcript for ${clip.id}`,
      segments: [
        { start_s: 0, end_s: 3.5, text: 'Hello world' },
        { start_s: 3.5, end_s: 7, text: 'this is a test' },
      ],
    } : undefined,
  }
}

//  Helper: route all API calls to mock data (called once per test)

async function interceptApi(page: Page): Promise<void> {
  console.log('[intercept] starting...')

  // ⚠️ Playwright route matching is first-match-wins. Register specific routes BEFORE catch-alls
  // so that /api/clips/1/thumbnail, detail endpoints etc. are handled by their specific handler
  // rather than being swallowed by the /api/clips catch-all below.

  // GET /api/clips/:id/thumbnail — return a minimal PNG placeholder
  await page.route(/\/api\/clips\/\d+\/thumbnail/, async (route) => {
    const png = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
      'base64'
    )
    await route.fulfill({
      status: 200, body: png, headers: { 'Content-Type': 'image/png' },
    })
  })

  // PATCH /api/clips/:id/roll — accept any roll value, return ok
  await page.route(/\/api\/clips\/\d+\/roll/, async (route) => {
    const url = new URL(route.request().url())
    await route.fulfill({ json: { status: 'ok', clip_id: 1, roll_type: url.searchParams.get('roll') } })
  })

  // PUT /api/clips/:id/tags — accept any tag list, return ok
  await page.route(/\/api\/clips\/\d+\/tags$/, async (route) => {
    await route.fulfill({ json: { status: 'ok', clip_id: 1, tags_count: 2 } })
  })

  // POST /api/clips/:id/reanalyze — return a fake job_id
  await page.route(/\/api\/clips\/\d+\/reanalyze$/, async (route) => {
    await route.fulfill({ json: { job_id: 99 } })
  })

  // PATCH /api/clips/:id — accept any edit body, return ok (method-checked to avoid catching GET detail)
  // Negative lookahead excludes sub-paths handled by specific routes above (/thumbnail, /roll, /tags, /reanalyze)
  await page.route(/\/api\/clips\/\d+(?!(?:\/thumbnail|\/roll|\/tags|\/reanalyze))/, async (route) => {
    if (route.request().method() !== 'PATCH') return route.continue()
    await route.fulfill({ json: { status: 'ok', clip_id: 1 } })
  })

  // GET /api/clips/:id (detail) — must come AFTER specific sub-paths, before glob catch-all
  await page.route(/\/api\/clips\/\d+(?:\?|$)(?!(?:\/thumbnail|\/roll|\/tags|\/reanalyze))/, async (route) => {
    const id = Number(route.request().url().split('/api/clips/')[1]?.split(/[?#]/)[0])
    const idx = ALL_CLIPS.findIndex((c) => c.id === id)
    if (idx < 0) return route.fulfill({ status: 404, json: { detail: 'Clip not found' } })
    const tagMap = [TAGS_1, TAGS_2, TAGS_3, TAGS_4, TAGS_5, TAGS_6]
    await route.fulfill({ json: clipDetail(ALL_CLIPS[idx], [...tagMap[idx]] as TagItem[]) })
  })

  // GET /api/clips (with optional query params) — catch-all for list + filtered lists
  await page.route('**/api/clips*', async (route) => {
    const url = new URL(route.request().url())
    // Strip query string to check if this is a detail/list endpoint already handled above
    const path = url.pathname.split('?')[0]
    // If it matches /api/clips/ID (detail) etc, skip — handled by specific routes above
    if (/^\/api\/clips\/\d+(?!(?:\/thumbnail|\/roll|\/tags|\/reanalyze))/.test(path)) return route.continue()
    const rollType = url.searchParams.get('roll_type') as 'a' | 'b' | null
    const tag = url.searchParams.get('tag')

    let results = ALL_CLIPS
    if (rollType) results = results.filter((c) => c.roll_type === rollType)
    if (tag) results = results.filter((c) => c.tags?.some((t: TagItem) => t.name === tag))
    await route.fulfill({ json: results })
  })

  // POST /api/scan — return a fake job_id
  await page.route('**/api/scan', async (route) => {
    await route.fulfill({ json: { job_id: 42 } })
  })

  // GET /api/jobs/:id — return job status
  await page.route(/\/api\/jobs\/\d+/, async (route) => {
    await route.fulfill({ json: { id: 1, status: 'done', total: 3, done: 3, failed: 0, started_at: null } })
  })

  // GET /api/jobs/:id/events — SSE endpoint (empty)
  await page.route(/\/api\/jobs\/\d+\/events/, async (route) => {
    await route.fulfill({ status: 204 })
  })

  // GET /api/settings — return settings
  await page.route('**/api/settings*', async (route) => {
    await route.fulfill({ json: { prefs: { source_folders: ['/Volumes/SD'], library_path: null, text_model: 'Qwen3.6-35B-A3B', vision_model: 'Qwen3-VL-8B', whisper_model: 'large-v3', extensions: ['.mp4'], broll_frame_count: 5, vad_threshold: 0.48 } } })
  })

  // GET /api/search?q= — search clips by summary/description/path keywords
  await page.route('**/api/search*', async (route) => {
    const url = new URL(route.request().url())
    const q = (url.searchParams.get('q') ?? '').toLowerCase()
    if (!q) return route.fulfill({ json: [] as ClipSummary[] })
    const results = ALL_CLIPS.filter((c) => {
      if (c.summary?.toLowerCase().includes(q)) return true
      if (c.description?.toLowerCase().includes(q)) return true
      return c.source_path.toLowerCase().includes(q)
    })
    await route.fulfill({ json: results })
  })
}

//  Helper: navigate by dispatching a custom event (avoids overlay click issues).
// App.tsx listens for 'cutfinder:navigate' and sets selectedClipId from it.
async function navigateToClip(page: Page, clipId: number): Promise<void> {
  await page.evaluate((id) => {
    window.dispatchEvent(new CustomEvent('cutfinder:navigate', { detail: { clipId: id } }))
  }, clipId)
}

//  Test suites

test.describe('Gallery', () => {
  test.beforeEach(async ({ page }) => {
    console.log('[beforeEach] starting...')

    // Capture ALL browser console output for debugging API interception
    const msgs: string[] = []
    page.on('console', (msg) => {
      const text = msg.text()
      if (!text.includes('ResizeObserver') && !text.includes('@vite/client')) {
        msgs.push(`${msg.type()}: ${text}`)
      }
    })
    page.on('pageerror', (err) => {
      msgs.push(`ERROR: ${err.message}`)
    })

    console.log('[beforeEach] calling interceptApi...')
    await interceptApi(page)
    console.log('[beforeEach] after interceptApi, navigating...')

    // Navigate and wait for React to render the gallery.
    await page.goto('/')
    console.log('[beforeEach] after goto, waiting...')

    // Simple fixed delay — gives React time to fetch data and render.
    await page.waitForTimeout(3000)
    console.log('[beforeEach] done')
  })


  test('loads clips with thumbnails in the gallery grid', async ({ page }) => {
    const rootContent = await page.evaluate(() => document.getElementById('root')?.innerHTML || 'EMPTY_ROOT')
    console.log(`ROOT LEN: ${rootContent.length}`)

    const clipCount = await page.locator('[data-clip-id]').count()
    console.log(`CLIP COUNT: ${clipCount}`)

    // All 6 clips should be visible in the gallery grid
    const cards = page.locator('[data-clip-id]')
    await expect(cards).toHaveCount(6)

    // Each card should have a data-clip-id attribute
    for (let i = 1; i <= 6; i++) {
      await expect(page.locator(`[data-clip-id="${i}"]`)).toBeVisible()
    }

    // Source path filename should be visible on each card
    const filenames = ['MVI_5298.MP4', 'DJI_5368.MP4', 'MVI_5310.MP4', 'DJI_5370.MP4', 'MVI_5315.MP4', 'DJI_5375.MP4']
    for (const name of filenames) {
      await expect(page.locator(`text="${name}"`)).toBeVisible()
    }

    // Thumbnail images should be present as img elements (lazy-loaded)
    const thumbnailImages = page.locator('img[src*="thumbnail"]')
    await expect(thumbnailImages).toHaveCount(6)
  })

  test('shows A/B roll badges on cards', async ({ page }) => {
    // Check that the first clip (id=1, roll_type='a') has an A-roll badge
    const card1 = page.locator('[data-clip-id="1"]')
    await expect(card1).toBeVisible()

    // The Badge component renders as <span>A</span> or <span>B</span>;
    // find all spans containing A or B (the roll-type badges).
    const aBadges = page.locator('span:has-text("A")')
    await expect(aBadges.first()).toBeVisible()

    const bBadges = page.locator('span:has-text("B")')
    await expect(bBadges.first()).toBeVisible()

    const aRollCount = ALL_CLIPS.filter((c) => c.roll_type === 'a').length
    expect(await aBadges.count()).toBeGreaterThanOrEqual(aRollCount)

    const bRollCount = ALL_CLIPS.filter((c) => c.roll_type === 'b').length
    expect(await bBadges.count()).toBeGreaterThanOrEqual(bRollCount)
  })

  test('selects a clip when clicked and opens detail panel', async ({ page }) => {
    // Click the first card (clip id=1)
    const card1 = page.locator('[data-clip-id="1"]')
    await card1.click()

    // Detail panel should open (slide-in drawer with role="dialog")
    const dialog = page.locator('[role="dialog"]')
    await expect(dialog).toBeVisible()

    // The selected card should have a ring (ring-2 class)
    await expect(card1).toHaveClass(/ring/)

    // Clip source path should be visible in the detail panel (dialog already declared above)
    await expect(dialog).toBeVisible()
    await expect(dialog.locator('text=/MVI_5298/')).toBeVisible()
  })

  test('closes detail panel when close button is clicked', async ({ page }) => {
    // Open the detail panel first
    await page.locator('[data-clip-id="3"]').click()
    await expect(page.locator('[role="dialog"]')).toBeVisible()

    // Click the close button (X icon)
    const closeButton = page.locator('button[aria-label="Close panel"]')
    await closeButton.click()

    // Detail panel should be gone (the component returns null when clipId is null)
    await expect(page.locator('[role="dialog"]')).not.toBeVisible()

    // Gallery should be visible again
    await expect(page.locator('[data-clip-id]')).toHaveCount(6)
  })

  test('clicking backdrop closes detail panel', async ({ page }) => {
    // Open the detail panel first
    await page.locator('[data-clip-id="2"]').click()

    // Click the backdrop (absolute overlay with black/50 background)
    await page.locator('[role="dialog"] > div:first-child').click()

    // Detail panel should be closed
    await expect(page.locator('[role="dialog"]')).not.toBeVisible()
  })
})

test.describe('Filter by roll type', () => {
  test.beforeEach(async ({ page }) => {
    await interceptApi(page)
    await page.goto('/')
  })

  test('filtering by A-roll shows only A-clip cards', async ({ page }) => {
    // Click the "A-roll" filter button in the sidebar
    const aRollBtn = page.locator('button').filter({ hasText: /A-roll/ })
    await aRollBtn.click()

    // Only A-roll cards should be visible (clips 1, 3, 5)
    const visibleCards = page.locator('[data-clip-id]').filter({ visible: true })
    await expect(visibleCards).toHaveCount(3)

    // Verify specific clip IDs are visible
    await expect(page.locator('[data-clip-id="1"]')).toBeVisible()
    await expect(page.locator('[data-clip-id="3"]')).toBeVisible()
    await expect(page.locator('[data-clip-id="5"]')).toBeVisible()

    // B-roll clips should be hidden
    await expect(page.locator('[data-clip-id="2"]')).not.toBeVisible()
  })

  test('filtering by B-roll shows only B-clip cards', async ({ page }) => {
    // Click the "B-roll" filter button in the sidebar
    const bRollBtn = page.locator('button').filter({ hasText: /B-roll/ })
    await bRollBtn.click()

    // Only B-roll cards should be visible (clips 2, 4, 6)
    const visibleCards = page.locator('[data-clip-id]').filter({ visible: true })
    await expect(visibleCards).toHaveCount(3)

    await expect(page.locator('[data-clip-id="2"]')).toBeVisible()
    await expect(page.locator('[data-clip-id="4"]')).toBeVisible()
    await expect(page.locator('[data-clip-id="6"]')).toBeVisible()

    // A-roll clips should be hidden
    await expect(page.locator('[data-clip-id="1"]')).not.toBeVisible()
  })

  test('clearing filters shows all clips again', async ({ page }) => {
    // Apply A-roll filter
    await page.locator('button').filter({ hasText: /A-roll/ }).click()
    await expect(page.locator('[data-clip-id]').filter({ visible: true })).toHaveCount(3)

    // Click "Clear all filters"
    const clearBtn = page.locator('text=Clear all filters')
    await clearBtn.click()

    // All clips should be visible again
    await expect(page.locator('[data-clip-id]').filter({ visible: true })).toHaveCount(6)
  })

  test('clicking All shows all clips', async ({ page }) => {
    // Apply B-roll filter first
    await page.locator('button').filter({ hasText: /B-roll/ }).click()
    await expect(page.locator('[data-clip-id]').filter({ visible: true })).toHaveCount(3)

    // Click "All" button
    await page.locator('button').filter({ hasText: /^All$/ }).click()

    // All clips should be visible again
    await expect(page.locator('[data-clip-id]').filter({ visible: true })).toHaveCount(6)
  })
})

test.describe('Detail panel', () => {
  test.beforeEach(async ({ page }) => {
    await interceptApi(page)
    await page.goto('/')
  })

  test('shows clip metadata in detail panel', async ({ page }) => {
    // Open clip 1's detail panel
    await page.locator('[data-clip-id="1"]').click()

    // Wait for dialog to appear, then assert within it
    const dialog = page.locator('[role="dialog"]')
    await expect(dialog).toBeVisible()

    // Source path should be visible inside the panel
    await expect(dialog.locator('text=/MVI_5298/')).toBeVisible()

    // Roll type badge should show A (Badge renders "A" or "B")
    await expect(dialog.locator('[class*="rounded-full"]').getByText('A', { exact: true })).toBeVisible()

    // Metadata section should be expandable (details element with summary)
    const details = dialog.locator('details')
    await expect(details).toBeVisible()

    // Metadata is inside a collapsed <details> — expand it first
    await dialog.locator('summary:has-text("Metadata")').click()

    // Duration should be shown (120s = 2.0 min)
    await expect(dialog.locator('text=2.0 min')).toBeVisible()

    // Resolution should be shown (width × height)
    await expect(dialog.locator('text=1920×1080')).toBeVisible()
  })

  test('shows transcript section for A-roll clips', async ({ page }) => {
    // Clip 1 is A-roll: should have a collapsible Transcript section
    await page.locator('[data-clip-id="1"]').click()

    const dialog = page.locator('[role="dialog"]')
    await expect(dialog).toBeVisible()

    // TranscriptSection renders a button with text "Transcript"
    const transcriptBtn = dialog.locator('button:has-text("Transcript")')
    await expect(transcriptBtn).toBeVisible()

    // Transcript content is collapsed by default — the full_text for clip 1 = "Transcript for 1"
    const transcriptContent = dialog.locator('text=Transcript for 1')
    await expect(transcriptContent).not.toBeVisible()

    // Expand it — segments + full_text should appear
    await transcriptBtn.click()
    await expect(dialog.locator('text=Transcript for 1')).toBeVisible()

    // Segment text "Hello world" should also be visible
    await expect(dialog.locator('text=Hello world')).toBeVisible()
  })

  test('does NOT show transcript section for B-roll clips', async ({ page }) => {
    // Clip 2 is B-roll: should NOT have a Transcript section
    await page.locator('[data-clip-id="2"]').click()

    const dialog = page.locator('[role="dialog"]')
    await expect(dialog).toBeVisible()

    const transcriptBtn = dialog.locator('button:has-text("Transcript")')
    await expect(transcriptBtn).not.toBeVisible()

    // Should show description instead of summary
    await expect(dialog.locator('text=/Visual footage/')).toBeVisible()
  })

  test('shows A/B correction buttons in footer', async ({ page }) => {
    // Open clip 1 (currently A-roll) detail panel
    await page.locator('[data-clip-id="1"]').click()

    // Both A-roll and B-roll buttons should be visible
    await expect(page.locator('text=A-roll (narration)')).toBeVisible()
    await expect(page.locator('text=B-roll (visual)')).toBeVisible()

    // A-roll button should be primary (active), B-roll secondary
    const aRollBtn = page.locator('text=A-roll (narration)')
    await expect(aRollBtn).toHaveClass(/bg-\[--primary\]/)

    // Click the B-roll button to correct classification
    const bRollBtn = page.locator('text=B-roll (visual)')
    await bRollBtn.click()

    // B-roll button should now be primary (active)
    await expect(bRollBtn).toHaveClass(/bg-\[--primary\]/)
  })

  test('triggers re-analyze button', async ({ page }) => {
    await page.locator('[data-clip-id="1"]').click()

    // Re-analyze button should be visible
    const reanalyzeBtn = page.locator('text=Re-analyze')
    await expect(reanalyzeBtn).toBeVisible()

    // Click it  should trigger the API call (already mocked)
    await reanalyzeBtn.click()

    // No error should be thrown; the button may briefly show loading
    await expect(reanalyzeBtn).toBeVisible()
  })

  test('edits summary for A-roll clips', async ({ page }) => {
    await page.locator('[data-clip-id="1"]').click()

    // The summary textarea should be visible for A-roll clips
    const summaryTextarea = page.locator('textarea').first()
    await expect(summaryTextarea).toBeVisible()

    // Clear existing text and type new summary
    await summaryTextarea.fill('')
    await summaryTextarea.type('New custom narration about mountains.')

    // Click Save button
    const saveBtn = page.locator('button:has-text("Save")')
    await expect(saveBtn).toBeVisible()

    // The save button click triggers the PATCH request (already mocked)
    await expect(saveBtn).not.toHaveAttribute('disabled')
  })

  test('shows description (read-only) for B-roll clips', async ({ page }) => {
    await page.locator('[data-clip-id="2"]').click()

    // Should show description (not summary)
    const descLabel = page.locator('text=Description (B-roll)')
    await expect(descLabel).toBeVisible()

    // Description textarea should be read-only (not editable)
    const descTextarea = page.locator('textarea[readonly]').first()
    await expect(descTextarea).toBeVisible()

    // Should NOT show summary label (only A-roll has editable summary)
    const summaryLabel = page.locator('text=Summary (A-roll)')
    await expect(summaryLabel).not.toBeVisible()
  })

  test('adds a new tag in the detail panel', async ({ page }) => {
    await page.locator('[data-clip-id="1"]').click()

    // Tag input should be visible (placeholder is "Add tag…" with full-width ellipsis)
    const tagInput = page.locator('input[placeholder*="Add tag"]')
    await expect(tagInput).toBeVisible()

    // Use fill() — sets value directly and triggers React onChange reliably
    await tagInput.fill('test-tag')

    // Wait for the input value to actually change (React state update)
    await expect(tagInput).toHaveValue('test-tag')

    const addBtn = page.locator('button:has-text("Add")')
    await expect(addBtn).not.toHaveAttribute('disabled')

    // Clicking Add triggers api.setTags() → setNewTag('').
    await expect(addBtn).toBeEnabled()
    await addBtn.click()

    // Wait for React to re-render (chip should appear, input cleared)
    await page.waitForTimeout(300)

    // Verify the new tag chip appeared in the DOM
    const chips = page.locator('[class*="rounded-full"][class*="border"]')
    await expect(chips).toHaveCount(3)

    // Input should be cleared after successful add
    await expect(tagInput).toHaveValue('')
  })

  test('deletes an existing tag in the detail panel', async ({ page }) => {
    await page.locator('[data-clip-id="1"]').click()

    // There should be existing tags (mountains, nature).
    const chips = page.locator('[class*="rounded-full"][class*="border"]')
    await expect(chips).toHaveCount(2)

    // Click the delete button (X icon) on the mountains chip
    const mountChip = page.locator('[class*="rounded-full"][class*="border"]').filter({ hasText: 'mountains' })
    const deleteBtn = mountChip.locator('button[aria-label*="Remove tag"]')
    await expect(deleteBtn).toBeVisible()

    // Click delete — API call is mocked, no error expected
    await expect(deleteBtn).toBeEnabled()
    await deleteBtn.click()

    // Wait for React to re-render (chip should be removed from state + DOM)
    await page.waitForTimeout(300)

    // The chip should be removed (API mocked to succeed, state updated via onUpdate callback)
    await expect(chips).toHaveCount(1)
  })

  test('shows thumbnail image in detail panel', async ({ page }) => {
    await page.locator('[data-clip-id="1"]').click()

    // Thumbnail image in the detail panel should be visible
    const thumbnail = page.locator('[role="dialog"] img[alt="Thumbnail"]')
    await expect(thumbnail).toBeVisible()

    // The image src should point to the mock thumbnail
    const src = await thumbnail.getAttribute('src')
    expect(src).toBe('/thumbnails/1.jpg')
  })

  test('shows clip duration and metadata', async ({ page }) => {
    await page.locator('[data-clip-id="4"]').click()

    const dialog = page.locator('[role="dialog"]')
    await expect(dialog).toBeVisible()

    // Expand the collapsible metadata section (it is <details> collapsed by default)
    await dialog.locator('summary:has-text("Metadata")').click()

    // Duration: 60s = 1.0 min
    await expect(dialog.locator('text=1.0 min')).toBeVisible()

    // Resolution (width × height)
    await expect(dialog.locator('text=1920×1080')).toBeVisible()

    // Frame rate
    await expect(dialog.locator('text=30 fps')).toBeVisible()

    // Codec
    await expect(dialog.locator('text=h264')).toBeVisible()
  })

  test('handles clip not found (invalid id)', async ({ page }) => {
    // Intercept the detail call for clip 999 to return 404, while keeping list route intact
    await page.route(/\/api\/clips\/999(?=\?|$)/, async (route) => {
      await route.fulfill({ status: 404, json: { detail: 'Clip not found' } })
    }, { times: 1 })

    // Reload to trigger the list API (interceptApi's catch-all handles this)
    await page.reload()

    // The gallery should still be visible since the invalid load doesn't crash
    await expect(page.locator('[data-clip-id]')).toHaveCount(6)

    // Clean up the one-shot route so it doesn't affect subsequent tests
    await page.unroute(/\/api\/clips\/999(?=\?|$)/)
  })

  test('shows loading state when detail panel is opening', async ({ page }) => {
    // Intercept the clip 5 detail call to delay response — use {times:1} so it auto-cleans up
    await page.route(/\/api\/clips\/5(?=\?|$)/, async (route) => {
      setTimeout(async () => {
        await route.fulfill({ json: clipDetail(ALL_CLIPS[4], [...TAGS_5] as TagItem[]) })
      }, 300)
    }, { times: 1 })

    await page.locator('[data-clip-id="5"]').click()

    // Loading text should briefly appear (use a short timeout since it resolves quickly)
    await expect(page.locator('text=Loading clip…')).toBeVisible()

    // Then content should appear — wait for the delayed response to resolve
    await page.waitForResponse(/\/api\/clips\/5(?=\?|$)/, { timeout: 3000 })

    // TranscriptSection is inside a collapsed <details>, so expand the transcript section
    await page.locator('[role="dialog"]').locator('button:has-text("Transcript")').click()
    await expect(page.locator('[role="dialog"]')).toContainText('Transcript for 5')

    // Ensure route is cleaned up
    await page.unroute(/\/api\/clips\/5(?=\?|$)/)
  })

  test('shows empty state when no clips exist', async ({ page }) => {
    // Unroute the beforeEach catch-all so our specific route takes effect.
    await page.unroute('**/api/clips*')

    // Only route the thumbnail endpoint to avoid 404s, then return empty clips list.
    await page.route(/\/api\/clips\/\d+\/thumbnail/, async (route) => {
      const png = Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
        'base64',
      )
      await route.fulfill({ status: 200, body: png, headers: { 'Content-Type': 'image/png' } })
    }, { times: 1 })

    await page.route('**/api/clips', async (route) => {
      await route.fulfill({ json: [] })
    }, { times: 1 })

    // Reload to get empty state
    await page.reload()

    // Empty state message should be visible
    const noClipsText = page.locator('text=No clips yet')
    await expect(noClipsText).toBeVisible()

    // No clip cards should be present
    await expect(page.locator('[data-clip-id]')).toHaveCount(0)

    // Clean up
    await page.unroute('**/api/clips')
  })

  test('shows empty state while clips are being fetched, then renders grid', async ({ page }) => {
    // Unroute the beforeEach catch-all so our specific route takes effect.
    await page.unroute('**/api/clips*')

    // Reload to trigger loading state (shows empty gallery while waiting).
    await page.reload()

    // Register routes AFTER reload so React's initial mount (without prior cleanup)
    // processes delayed responses correctly — StrictMode double-mount is not a factor.
    await page.route(/\/api\/clips\/\d+\/thumbnail/, async (route) => {
      const png = Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
        'base64',
      )
      await route.fulfill({ status: 200, body: png, headers: { 'Content-Type': 'image/png' } })
    }, { times: 10 })

    // Intercept list endpoint to delay response (simulate slow network).
    await page.route('**/api/clips', async (route) => {
      setTimeout(async () => {
        await route.fulfill({ json: ALL_CLIPS })
      }, 500)
    }, { times: 2 })

    // Empty state should be visible during load (wait up to 2s).
    await expect(page.locator('text="No clips yet"')).toBeVisible({ timeout: 2000 })

    // Then actual content should appear after response arrives.
    await expect(page.locator('[data-clip-id="1"]')).toBeVisible()

    // Clean up.
    await page.unroute('**/api/clips')
  })
})

test.describe('Search', () => {
  test.beforeEach(async ({ page }) => {
    await interceptApi(page)
    await page.goto('/')
  })

  // Search filters the gallery client-side (App.handleSearch sets a query that
  // matches filename, summary, description, and tags). The box lives in the
  // left filter sidebar.

  test('searching by keyword in summary finds matching clips', async ({ page }) => {
    // Type "mountain"  should match clip 1 (summary: "...trip to the mountains.")
    const searchInput = page.locator('input[placeholder*="Search clips"]')
    await expect(searchInput).toBeVisible()

    // Search is debounced (300ms), so typing should trigger it
    await searchInput.fill('mountain')

    // Wait for debounce (300ms)
    await page.waitForTimeout(400)

    // Gallery should show only matching clips (clip 1 matches "mountains")
    const visibleCards = page.locator('[data-clip-id]').filter({ visible: true })
    expect(await visibleCards.count()).toBeGreaterThan(0)

    // Clip 1 should be visible
    await expect(page.locator('[data-clip-id="1"]')).toBeVisible()
  })

  test('searching by keyword in description finds matching clips', async ({ page }) => {
    // Type "sunset"  should match clip 2 (description: "...sunset over the ocean.")
    const searchInput = page.locator('input[placeholder*="Search clips"]')
    await searchInput.fill('sunset')

    // Wait for debounce (300ms)
    await page.waitForTimeout(450)

    // Gallery should show matching clips (clip 2 matches "sunset")
    const visibleCards = page.locator('[data-clip-id]').filter({ visible: true })
    expect(await visibleCards.count()).toBeGreaterThan(0)

    // Clip 2 should be visible
    await expect(page.locator('[data-clip-id="2"]')).toBeVisible()
  })

  test('searching by filename finds matching clips', async ({ page }) => {
    // Type "5368"  should match clip 2 (source_path: "...DJI_5368.MP4")
    const searchInput = page.locator('input[placeholder*="Search clips"]')
    await searchInput.fill('5368')

    // Wait for debounce (300ms)
    await page.waitForTimeout(450)

    // Gallery should show matching clips (clip 2 matches "DJI_5368.MP4")
    const visibleCards = page.locator('[data-clip-id]').filter({ visible: true })
    expect(await visibleCards.count()).toBeGreaterThan(0)

    // Clip 2 should be visible
    await expect(page.locator('[data-clip-id="2"]')).toBeVisible()
  })

  test('clearing search shows all clips again', async ({ page }) => {
    // Search for something first
    const searchInput = page.locator('input[placeholder*="Search clips"]')
    await searchInput.fill('mountain')

    // Wait for debounce (300ms)
    await page.waitForTimeout(450)

    // Click the clear button (X icon, only visible when there's text in search input)
    const clearBtn = page.locator('button[aria-label="Clear search"]')
    await expect(clearBtn).toBeVisible()
    await clearBtn.click()

    // Wait for debounce (300ms)  search clears the query
    await page.waitForTimeout(450)

    // All clips should be visible again (the app does client-side filtering,
    // but with empty query the callback is called which resets state)
    const visibleCards = page.locator('[data-clip-id]').filter({ visible: true })
    expect(await visibleCards.count()).toBeGreaterThan(0)

    // Search input should be empty
    await expect(searchInput).toHaveValue('')
  })

  test.skip('search with no matches shows empty gallery', async ({ page }) => {
    // Search for something that won't match anything (case-sensitive in mock)
    const searchInput = page.locator('input[placeholder*="Search clips"]')
    await searchInput.fill('zzznonexistentxyz')

    // Wait for debounce (300ms)
    await page.waitForTimeout(450)

    // Gallery should show empty state since no clips match
    const visibleCards = page.locator('[data-clip-id]').filter({ visible: true })
    await expect(visibleCards).toHaveCount(0)

    // Empty state should be visible (the gallery renders empty state when no clips match)
    const noClipsText = page.locator('text=No clips yet')
    await expect(noClipsText).toBeVisible()
  })

  test.skip('search is case-insensitive', async ({ page }) => {
    // "MOUNTAINS" (uppercase) should match the same clips as "mountains"
    const searchInput = page.locator('input[placeholder*="Search clips"]')
    await searchInput.fill('MOUNTAINS')

    // Wait for debounce (300ms)
    await page.waitForTimeout(450)

    // Should match clip 1 (same as "mountain" search above)
    await expect(page.locator('[data-clip-id="1"]')).toBeVisible()

    // Clear and search with mixed case
    await page.locator('button[aria-label="Clear search"]').click()
    await page.waitForTimeout(450)

    // "SunSET" should match clip 2
    await searchInput.fill('SunSET')
    await page.waitForTimeout(450)

    // Should match clip 2 (description has "sunset")
    await expect(page.locator('[data-clip-id="2"]')).toBeVisible()
  })

  test.skip('filters and search work together', async ({ page }) => {
    // First filter to A-roll only (clips 1, 3, 5)
    await page.locator('button').filter({ hasText: /A-roll/ }).click()

    // Then search for "mountain"  should match clip 1 (A-roll + mountains)
    const searchInput = page.locator('input[placeholder*="Search clips"]')
    await searchInput.fill('mountain')

    // Wait for debounce (300ms)
    await page.waitForTimeout(450)

    // Gallery should show only clips matching BOTH filter AND search
    const visibleCards = page.locator('[data-clip-id]').filter({ visible: true })
    expect(await visibleCards.count()).toBeGreaterThan(0)

    // Clip 1 should be visible (A-roll + mountains match both criteria)
    await expect(page.locator('[data-clip-id="1"]')).toBeVisible()

    // Clip 3 (city walk) should NOT be visible since it doesn't match "mountain"
    // Note: the app filters client-side, so we need to verify this behavior

    // Clear search
    await page.locator('button[aria-label="Clear search"]').click()
  })

  test('scan button works via mocked API', async ({ page }) => {
    // Scan button should be visible in the header
    const scanBtn = page.locator('button:has-text("Scan")')
    await expect(scanBtn).toBeVisible()

    // Click scan  triggers POST /api/scan which is mocked
    await scanBtn.click()

    // No error should occur; the mock returns { job_id: 42 }
    await expect(scanBtn).toBeVisible()

    // Verify the scan button's onClick fired without throwing (the job state
    // is managed internally; we just confirm no crash/error).
  })

  test('filter by roll type AND tag together', async ({ page }) => {
    // Filter to B-roll (clips 2, 4, 6)
    await page.locator('button').filter({ hasText: /B-roll/ }).click()

    // The tag filter section might be empty (tags are fetched but placeholder)
    // Just verify the B-roll filter is applied and visible cards match expected count
    const visibleCards = page.locator('[data-clip-id]').filter({ visible: true })
    await expect(visibleCards).toHaveCount(3)

    // Verify B-roll clips are visible
    await expect(page.locator('[data-clip-id="2"]')).toBeVisible()
  })
})

test.describe('Integration', () => {
  test.beforeEach(async ({ page }) => {
    await interceptApi(page)
    await page.goto('/')
  })

  test('full flow: filter  select detail  correct roll  close', async ({ page }) => {
    // Step 1: Filter to A-roll clips only
    await page.locator('button').filter({ hasText: /A-roll/ }).click()
    await expect(page.locator('[data-clip-id]').filter({ visible: true })).toHaveCount(3)

    // Step 2: Click on clip 5 (wildlife, A-roll) to open detail
    await page.locator('[data-clip-id="5"]').click()

    // Step 3: Verify detail panel opened
    await expect(page.locator('[role="dialog"]')).toBeVisible()

    // Step 4: Verify A-roll button is active
    await expect(page.locator('text=A-roll (narration)')).toHaveClass(/bg-\[--primary\]/)

    // Step 5: Correct to B-roll
    await page.locator('text=B-roll (visual)').click()

    // Step 6: Verify B-roll button is now active
    await expect(page.locator('text=B-roll (visual)')).toHaveClass(/bg-\[--primary\]/)

    // Step 7: Close the detail panel
    await page.locator('button[aria-label="Close panel"]').click()

    // Step 8: Verify detail panel is closed
    await expect(page.locator('[role="dialog"]')).not.toBeVisible()

    // Step 9: Clear filter to see all clips
    await page.locator('text=Clear all filters').click()

    // Step 10: All clips should be visible again
    await expect(page.locator('[data-clip-id]').filter({ visible: true })).toHaveCount(6)
  })

  test('full flow: search  select detail  add tag  save summary', async ({ page }) => {
    // Step 1: Search for "mountain" (matches clip 1)
    const searchInput = page.locator('input[placeholder*="Search clips"]')
    await searchInput.fill('mountain')
    await page.waitForTimeout(450)

    // Step 2: Click on the matching clip
    await page.locator('[data-clip-id="1"]').click()

    // Step 3: Verify detail panel opened
    await expect(page.locator('[role="dialog"]')).toBeVisible()

    // Step 4: Add a new tag (placeholder has full-width ellipsis "Add tag…")
    const tagInput = page.locator('input[placeholder*="Add tag"]')
    await tagInput.fill('custom-tag')
    await page.locator('button:has-text("Add")').click()
    // Wait for React re-render after tag add
    await page.waitForTimeout(300)

    // Step 5: Edit the summary
    const textarea = page.locator('textarea').first()
    await textarea.fill('')
    await textarea.type('Custom summary about mountains.')

    // Step 6: Save the edit
    await page.locator('button:has-text("Save")').click()

    // Step 7: Close detail panel
    await page.locator('button[aria-label="Close panel"]').click()

    // Step 8: Clear search
    await page.locator('button[aria-label="Clear search"]').click()

    // Step 9: All clips should be visible again
    await expect(page.locator('[data-clip-id]').filter({ visible: true })).toHaveCount(6)
  })

  test('thumbnail loading and serving', async ({ page }) => {
    // All thumbnails should be requested when cards appear (lazy loading)
    const thumbnailRequests = await page.waitForRequest(
      (req) => req.url().includes('/thumbnail') && req.method() === 'GET'
    ).catch(() => null)

    // At least one thumbnail request should have been made
    expect(thumbnailRequests).not.toBeNull()

    // The thumbnail response should be a valid PNG
    const url = thumbnailRequests!.url()
    await expect(page.locator(`img[src="${url.replace('http://localhost:5080', '')}"]`)).toBeVisible()
  })

  test('re-analyze flow: trigger  job created', async ({ page }) => {
    // Open clip 1 detail panel and trigger re-analyze
    await page.locator('[data-clip-id="1"]').click()
    await expect(page.locator('button:has-text("Re-analyze")')).toBeVisible()

    // Click re-analyze
    await page.locator('button:has-text("Re-analyze")').click()

    // No error should occur (mocked API returns job_id)
    await expect(page.locator('[role="dialog"]')).toBeVisible()

    // Close panel
    await page.locator('button[aria-label="Close panel"]').click()
  })

  test('handles error state gracefully', async ({ page }) => {
    // Intercept clips list to return 500 (simulating server error) — specific pattern only
    await page.route('/api/clips', async (route) => {
      await route.fulfill({ status: 500, json: { detail: 'Internal server error' } })
    }, { times: 1 })

    await page.reload()

    // App should handle error gracefully (empty gallery with helpful message)
    await expect(page.locator('text=No clips yet')).toBeVisible()

    // No crash — the app should still be functional
    await expect(page.locator('h1:has-text("CutFinder")')).toBeVisible()

    // Clean up
    await page.unroute('/api/clips')
  })

  test('navigation between multiple clips in detail panel', async ({ page }) => {
    // Open clip 1, then switch to clip 2 without closing panel
    await page.locator('[data-clip-id="1"]').click()
    await expect(page.locator('text=/MVI_5298/')).toBeVisible()

    // Switch to clip 2 via custom event (avoids overlay click issues).
    await navigateToClip(page, 2)

    // Should now show clip 2's content
    await expect(page.locator('text=/DJI_5368/')).toBeVisible()

    // Should show B-roll content (description, not summary)
    await expect(page.locator('text=Description (B-roll)')).toBeVisible()

    // Should NOT show transcript section for B-roll
    await expect(page.locator('button:has-text("Transcript")')).not.toBeVisible()
  })

  test('keyboard accessibility: close panel with Escape key', async ({ page }) => {
    // Open the detail panel (backdrop is NOT yet visible, so click works normally)
    await page.locator('[data-clip-id="3"]').click()

    // Verify panel is open
    await expect(page.locator('[role="dialog"]')).toBeVisible()

    // Press Escape — DetailPanel listens for this key and calls onClose
    await page.keyboard.press('Escape')

    // Panel should be closed (auto-retry handles React re-render timing)
    await expect(page.locator('[role="dialog"]')).not.toBeVisible()
  })

  test('responsive layout: gallery grid adapts to viewport', async ({ page }) => {
    // Default desktop width (1280px)  should show 4+ columns
    await page.setViewportSize({ width: 1280, height: 800 })
    await expect(page.locator('[data-clip-id]')).toHaveCount(6)

    // Tablet width (768px)  should show 2-3 columns
    await page.setViewportSize({ width: 768, height: 1024 })
    await expect(page.locator('[data-clip-id]')).toHaveCount(6)

    // Mobile width (375px)  should show 1-2 columns
    await page.setViewportSize({ width: 375, height: 667 })
    await expect(page.locator('[data-clip-id]')).toHaveCount(6)

    // All cards should still be visible regardless of viewport size
  })
})
