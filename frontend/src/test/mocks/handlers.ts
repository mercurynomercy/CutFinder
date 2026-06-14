/** MSW request handlers for the CutFinder API.

Each handler returns realistic mock data matching the TypeScript types in `api/client.ts`.
*/

import { http, HttpResponse } from 'msw'
import type { ClipSummary, ClipDetail, SettingsPrefs, JobStatus } from '@/api/client'

// ── Mock data factories ────────────────────────────────

function makeClipSummary(overrides: Partial<ClipSummary> = {}): ClipSummary {
  return {
    id: overrides.id ?? Math.floor(Math.random() * 100),
    source_path: overrides.source_path ?? `/media/vlog/2024-06/${overrides.id}.mp4`,
    roll_type: overrides.roll_type ?? (Math.random() > 0.5 ? 'a' : 'b'),
    thumbnail_path: overrides.thumbnail_path ?? `/thumbnails/${overrides.id}.jpg`,
    duration_s: overrides.duration_s ?? 30 + Math.floor(Math.random() * 120),
    tags: overrides.tags ?? [],
    created_at: overrides.created_at ?? '2024-06-15T10:30:00Z',
    ...overrides,
  }
}

function makeClipDetail(overrides: Partial<ClipDetail> = {}): ClipDetail {
  return {
    ...makeClipSummary(overrides),
    summary: overrides.summary ?? 'A roll narration about a trip to the mountains.',
    description: overrides.description ?? null,
    tags: overrides.tags ?? [
      { name: 'mountains', source: 'auto' },
      { name: 'nature', source: 'manual' },
    ],
    transcript: overrides.transcript ?? {
      full_text: 'Today we visited the beautiful mountains near our town.',
      segments: [
        { start_s: 0, end_s: 3.5, text: 'Today we visited' },
        { start_s: 3.5, end_s: 7, text: 'the beautiful mountains near our town.' },
      ],
    },
    width: overrides.width ?? 1920,
    height: overrides.height ?? 1080,
    fps: overrides.fps ?? 30,
    codec: overrides.codec ?? 'h264',
    ...overrides,
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
    ...overrides,
  }
}

function makeJobStatus(overrides: Partial<JobStatus> = {}): JobStatus {
  return {
    job_id: overrides.job_id ?? 1,
    status: 'running',
    total: overrides.total ?? 10,
    done: (overrides.done as number) ?? 3,
    ...overrides,
  }
}

// ── Handlers ───────────────────────────────────────────

export const handlers = [
  // GET /api/clips — list clips
  http.get('http://localhost:5080/api/clips', () => {
    const clips = [
      makeClipSummary({ id: 1, source_path: '/media/vlog/2024-06/a-roll_01.mp4', roll_type: 'a' }),
      makeClipSummary({ id: 2, source_path: '/media/vlog/2024-06/b-roll_01.mp4', roll_type: 'b' }),
      makeClipSummary({ id: 3, source_path: '/media/vlog/2024-06/a-roll_02.mp4', roll_type: 'a' }),
    ]
    return HttpResponse.json(clips)
  }),

  // GET /api/clips/:id — get clip detail
  http.get('http://localhost:5080/api/clips/:id', ({ params }) => {
    const id = Number(params.id)
    if (isNaN(id)) return HttpResponse.json({ detail: 'Invalid clip id' }, { status: 400 })
    return HttpResponse.json(makeClipDetail({ id }))
  }),

  // POST /api/clips/:id/correct-roll — correct roll type
  http.post('http://localhost:5080/api/clips/:id/correct-roll', async ({ request, params }) => {
    const body = await request.json() as { roll_type: string }
    return HttpResponse.json({ ok: true, clip_id: Number(params.id), roll_type: body.roll_type })
  }),

  // PATCH /api/clips/:id — update clip (summary)
  http.patch('http://localhost:5080/api/clips/:id', async ({ request, params }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({ ok: true, clip_id: Number(params.id), ...body })
  }),

  // POST /api/tags — set tags for a clip (using id from params)
  http.post('http://localhost:5080/api/tags/:id', async ({ request, params }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({ ok: true, clip_id: Number(params.id), tags: body.tags ?? [] })
  }),

  // POST /api/clips/:id/reanalyze — trigger re-analyze (returns job id)
  http.post('http://localhost:5080/api/clips/:id/reanalyze', ({ params }) => {
    return HttpResponse.json({ ok: true, job_id: Math.floor(Math.random() * 100) })
  }),

  // POST /api/scan — trigger scan (returns job id)
  http.post('http://localhost:5080/api/scan', () => {
    return HttpResponse.json({ ok: true, job_id: 42 })
  }),

  // GET /api/jobs/:id — get job status
  http.get('http://localhost:5080/api/jobs/:id', ({ params }) => {
    const id = Number(params.id)
    if (isNaN(id)) return HttpResponse.json({ detail: 'Invalid job id' }, { status: 400 })
    return HttpResponse.json(makeJobStatus({ job_id: id }))
  }),

  // GET /api/settings — get current settings
  http.get('http://localhost:5080/api/settings', () => {
    return HttpResponse.json({ prefs: makeSettingsPrefs() })
  }),

  // PUT /api/settings — update settings
  http.put('http://localhost:5080/api/settings', async ({ request }) => {
    const prefs = await request.json() as Record<string, unknown>
    return HttpResponse.json({ ok: true, prefs })
  }),

  // GET /api/search — search clips (returns same format as list)
  http.get('http://localhost:5080/api/search', ({ request }) => {
    const url = new URL(request.url)
    const q = url.searchParams.get('q') ?? ''
    // Return clips whose source_path contains the query (case-insensitive)
    const allClips = [1, 2, 3].map((id) => makeClipSummary({ id }))
    const results = q ? allClips.filter((c) => c.source_path.toLowerCase().includes(q.toLowerCase())) : []
    return HttpResponse.json(results)
  }),

  // SSE events endpoint — returns empty (tests mock this with custom fetch or msw)
  http.get('http://localhost:5080/api/jobs/:id/events', () => {
    // SSE is hard to mock with MSW; tests will use custom fetch mocks or the hook directly
    return HttpResponse.json([])
  }),
]
