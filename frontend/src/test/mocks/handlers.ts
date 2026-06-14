/** MSW request handlers for the CutFinder API.

Each handler returns realistic mock data matching the TypeScript types in `api/client.ts`.
All URLs match the actual FastAPI routes defined in `backend/cutfinder/api/routes.py`.
*/

import { http, HttpResponse } from 'msw'
import type { ClipSummary, ClipDetail, TagItem, SettingsPrefs, JobStatus } from '@/api/client'

// ── Mock data factories ────────────────────────────────

function makeTag(name: string, source: 'auto' | 'manual' = 'auto'): TagItem {
  return { name, source }
}

function makeClipSummary(overrides: Partial<ClipSummary> = {}): ClipSummary {
  return {
    id: overrides.id ?? Math.floor(Math.random() * 100),
    source_path: overrides.source_path ?? `/media/vlog/2024-06/${String(overrides.id).padStart(3, '0')}.mp4`,
    library_path: overrides.library_path ?? null,
    roll_type: (overrides.roll_type as 'a' | 'b') ?? ((Math.random() > 0.5 ? 'a' : 'b') as 'a' | 'b'),
    summary: overrides.summary ?? null,
    description: overrides.description ?? null,
    duration_s: overrides.duration_s ?? 30 + Math.floor(Math.random() * 120),
    thumbnail_path: overrides.thumbnail_path ?? `/thumbnails/${overrides.id}.jpg`,
    status: (overrides.status as string) ?? 'done',
  }
}

function makeClipDetail(overrides: Partial<ClipDetail> = {}): ClipDetail {
  return {
    ...makeClipSummary(overrides),
    roll_source: overrides.roll_source ?? 'auto',
    width: overrides.width ?? 1920,
    height: overrides.height ?? 1080,
    fps: overrides.fps ?? 30,
    codec: 'h264',
    error: null,
    capture_time: overrides.capture_time ?? '2024-06-15T10:30:00Z',
    date_source: 'embedded' as const,
    tags: overrides.tags ?? [
      { name: 'mountains', source: 'auto' },
    ],
    transcript: overrides.transcript ?? {
      full_text: 'Today we visited the beautiful mountains near our town.',
      segments: [
        { start_s: 0, end_s: 3.5, text: 'Today we visited' },
        { start_s: 3.5, end_s: 7, text: 'the beautiful mountains near our town.' },
      ],
    },
  }
}

function makeSettingsPrefs(overrides: Partial<SettingsPrefs> = {}): SettingsPrefs {
  return {
    source_folders: overrides.source_folders ?? ['/Volumes/SD_Card_1', '/Volumes/DJI_Drone'],
    library_path: overrides.library_path ?? '/Users/jan/Media/CutFinder_Library',
    text_model: overrides.text_model ?? 'Qwen3.6-35B-A3B',
    vision_model: overrides.vision_model ?? 'Qwen3-VL-8B',
    whisper_model: overrides.whisper_model ?? 'large-v3',
    extensions: overrides.extensions ?? ['.mp4', '.mov'],
    broll_frame_count: overrides.broll_frame_count ?? 5,
    vad_threshold: overrides.vad_threshold ?? 0.48,
  }
}

function makeJobStatus(overrides: Partial<JobStatus> = {}): JobStatus {
  return {
    id: overrides.id ?? 1,
    status: (overrides.status as string) ?? 'done',
    total: overrides.total ?? 3,
    done: (overrides.done as number) ?? 3,
    failed: overrides.failed ?? 0,
    started_at: overrides.started_at ?? '2024-06-15T10:30:00Z',
  }
}

// ── Pre-built clip lists (consistent across handlers) ────

const ALL_CLIPS: ClipSummary[] = [
  makeClipSummary({ id: 1, source_path: '/media/vlog/2024-06/MVI_5298.MP4', roll_type: 'a' as const, summary: 'A-roll narration about a trip to the mountains.', tags: [makeTag('mountains', 'auto'), makeTag('nature', 'manual')] }),
  makeClipSummary({ id: 2, source_path: '/media/vlog/2024-06/DJI_5368.MP4', roll_type: 'b' as const, description: 'Visual footage of a sunset over the ocean.', tags: [makeTag('sunset', 'auto'), makeTag('ocean', 'auto')] }),
  makeClipSummary({ id: 3, source_path: '/media/vlog/2024-06/MVI_5310.MP4', roll_type: 'a' as const, summary: 'A-roll narration about a city walking tour.', tags: [makeTag('cityscape', 'auto'), makeTag('urban', 'manual')] }),
  makeClipSummary({ id: 4, source_path: '/media/vlog/2024-06/DJI_5370.MP4', roll_type: 'b' as const, description: 'Drone footage of a coastline.', tags: [makeTag('coastline', 'auto'), makeTag('drone', 'auto')] }),
  makeClipSummary({ id: 5, source_path: '/media/vlog/2024-06/MVI_5315.MP4', roll_type: 'a' as const, summary: 'A-roll narration about wildlife spotting.', tags: [makeTag('wildlife', 'auto'), makeTag('birds', 'auto')] }),
  makeClipSummary({ id: 6, source_path: '/media/vlog/2024-06/DJI_5375.MP4', roll_type: 'b' as const, description: 'Forest trail with autumn foliage.', tags: [makeTag('forest', 'auto'), makeTag('autumn', 'manual')] }),
]

// ── Handlers (aligned with backend routes in routes.py) ────

export const handlers = [
  // GET /api/clips — list clips with optional query params (date, roll_type, tag)
  http.get('http://localhost:5080/api/clips', ({ request }) => {
    const url = new URL(request.url)
    const rollType = url.searchParams.get('roll_type') as 'a' | 'b' | null
    const tag = url.searchParams.get('tag')

    let results = ALL_CLIPS
    if (rollType) {
      results = results.filter((c) => c.roll_type === rollType)
    }
    if (tag) {
      results = results.filter((c) => c.tags?.some((t) => t.name === tag))
    }
    return HttpResponse.json(results)
  }),

  // GET /api/clips/:id — get clip detail with tags & transcript
  http.get('http://localhost:5080/api/clips/:id', ({ params }) => {
    const id = Number(params.id)
    if (isNaN(id)) return HttpResponse.json({ detail: 'Invalid clip id' }, { status: 400 })
    const clip = ALL_CLIPS.find((c) => c.id === id)
    if (!clip) {
      return HttpResponse.json({ detail: 'Clip not found' }, { status: 404 })
    }
    return HttpResponse.json(makeClipDetail({ id: clip.id, roll_type: clip.roll_type as 'a' | 'b', tags: clip.tags }))
  }),

  // PATCH /api/clips/{clip_id}/roll?roll=a|b — correct A/B classification
  http.patch('http://localhost:5080/api/clips/:id/roll', ({ params, request }) => {
    const url = new URL(request.url)
    const roll = url.searchParams.get('roll') as 'a' | 'b'
    if (roll !== 'a' && roll !== 'b') {
      return HttpResponse.json({ detail: 'roll must be a or b' }, { status: 422 })
    }
    return HttpResponse.json({ status: 'ok', clip_id: Number(params.id), roll_type: roll })
  }),

  // PATCH /api/clips/:id — update clip (summary/description)
  http.patch('http://localhost:5080/api/clips/:id', async ({ request, params }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({ status: 'ok', clip_id: Number(params.id) })
  }),

  // PUT /api/clips/:id/tags — replace all tags on a clip
  http.put('http://localhost:5080/api/clips/:id/tags', async ({ request, params }) => {
    const body = await request.json() as Record<string, unknown>
    const tags: Array<{ name: string }> = body.tags ?? []
    return HttpResponse.json({ status: 'ok', clip_id: Number(params.id), tags_count: tags.length })
  }),

  // POST /api/clips/:id/reanalyze — trigger re-analysis (returns job id)
  http.post('http://localhost:5080/api/clips/:id/reanalyze', ({ params }) => {
    return HttpResponse.json({ job_id: Math.floor(Math.random() * 100) })
  }),

  // POST /api/scan — enqueue clips for processing (returns job id)
  http.post('http://localhost:5080/api/scan', () => {
    return HttpResponse.json({ job_id: 42 })
  }),

  // GET /api/jobs/:id — get job status (aligned with JobStatus schema)
  http.get('http://localhost:5080/api/jobs/:id', ({ params }) => {
    const id = Number(params.id)
    if (isNaN(id)) return HttpResponse.json({ detail: 'Invalid job id' }, { status: 400 })
    return HttpResponse.json(makeJobStatus({ id }))
  }),

  // GET /api/settings — get current settings
  http.get('http://localhost:5080/api/settings', () => {
    return HttpResponse.json({ prefs: makeSettingsPrefs() })
  }),

  // PUT /api/settings — update settings
  http.put('http://localhost:5080/api/settings', async ({ request }) => {
    const prefs = await request.json() as Record<string, unknown>
    return HttpResponse.json({ status: 'ok', prefs })
  }),

  // GET /api/search?q= — search clips by full-text match on summary/description
  http.get('http://localhost:5080/api/search', ({ request }) => {
    const url = new URL(request.url)
    const q = (url.searchParams.get('q') ?? '').toLowerCase()
    if (!q) return HttpResponse.json([] as ClipSummary[])
    const results = ALL_CLIPS.filter((c) => {
      if (c.summary?.toLowerCase().includes(q)) return true
      if (c.description?.toLowerCase().includes(q)) return true
      const path = c.source_path.toLowerCase()
      if (path.includes(q)) return true
      return false
    })
    return HttpResponse.json(results)
  }),

  // GET /api/jobs/:id/events — SSE endpoint (returns empty for MSW mock)
  http.get('http://localhost:5080/api/jobs/:id/events', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  // GET /api/clips/:id/thumbnail — serve thumbnail image (returns a placeholder PNG)
  http.get('http://localhost:5080/api/clips/:id/thumbnail', ({ params }) => {
    const id = Number(params.id)
    if (isNaN(id)) return HttpResponse.json({ detail: 'Invalid clip id' }, { status: 400 })
    const clip = ALL_CLIPS.find((c) => c.id === id)
    if (!clip || !clip.thumbnail_path) {
      return HttpResponse.json({ detail: 'No thumbnail available' }, { status: 404 })
    }
    // Return a minimal valid PNG (1x1 pixel, red) as placeholder thumbnail content
    const pngBytes = new Uint8Array([
      0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
      0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
      0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
      0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
      0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
      0x54, 0x08, 0xD7, 0xC1, 0xC4, 0x20, 0x0C, 0xD3,
      0xF1, 0xCD, 0x52, 0x9E, 0xA7, 0xEC, 0xFA, 0x61,
      0xE8, 0xFD, 0xFF, 0xFE, 0x3F, 0xE8, 0xFC, 0xC1,
      0x7F, 0xF5, 0xFF, 0xFC, 0xDF, 0x1F, 0xC6, 0xE8,
      0xFD, 0x9F, 0xD7, 0xBB, 0xF3, 0xAF, 0xC6, 0xD4,
      0x13, 0xB7, 0xE5, 0xF9, 0x1E, 0xA6, 0xE3, 0xD5,
      0x8E, 0xDB, 0x2A, 0xA5, 0xD6, 0xF4, 0x28, 0xBB,
      0xE3, 0xB5, 0x41, 0xAD, 0xF9, 0xDC, 0xB6, 0x51,
      0xEB, 0xD8, 0xC7, 0x53, 0xE4, 0xBB, 0xDD, 0xF2,
      0xAD, 0x45, 0xE8, 0xF1, 0xB7, 0x3B, 0xD8, 0xA6,
      0xE1, 0x73, 0xF9, 0xBB, 0xB6, 0xC5, 0xA1, 0x84,
      0xF3, 0xB5, 0xD2, 0x6B, 0xBC, 0xF3, 0xAB, 0xDC,
      0x5F, 0xDE, 0xF4, 0xEB, 0xBB, 0x9E, 0xE1, 0xF5,
      0xD4, 0x6C, 0xC8, 0xA9, 0xD7, 0xF2, 0x6B, 0xAB,
      0xE3, 0xF5, 0xD4, 0x7B, 0xBD, 0xE3, 0xAF, 0xC6,
      0xD4, 0x13, 0xB7, 0xE5, 0xF9, 0x1E, 0xA6, 0xE3,
      0xD5, 0x8E, 0xDB, 0x2A, 0xA5, 0xD6, 0xF4, 0x28,
      0xBB, 0xE3, 0xB5, 0x41, 0xAD, 0xF9, 0xDC, 0xB6,
      0x51, 0xEB, 0xD8, 0xC7, 0x53, 0xE4, 0xBB, 0xDD,
      0xF2, 0xAD, 0x45, 0xE8, 0xF1, 0xB7, 0x3B, 0xD8,
      0xA6, 0xE1, 0x73, 0xF9, 0xBB, 0xB6, 0xC5, 0xA1,
      0x84, 0xF3, 0xB5, 0xD2, 0x6B, 0xBC, 0xF3, 0xAB,
      0xDC, 0x5F, 0xDE, 0xF4, 0xEB, 0xBB, 0x9E, 0xE1,
      0xF5, 0xD4, 0x6C, 0xC8, 0xA9, 0xD7, 0xF2, 0x6B,
      0xAB, 0xE3, 0xF5, 0xD4, 0x7B, 0xBD, 0xE3, 0xAF,
      0xC6, 0xD4, 0x13, 0xB7, 0xE5, 0xF9, 0x1E,
      // IEND chunk
      0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0xAE,
    ])
    return new HttpResponse(pngBytes, {
      headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=86400' },
    })
  }),
]
