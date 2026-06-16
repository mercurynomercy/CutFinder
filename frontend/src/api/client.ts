/** Fetch-based REST client for the CutFinder backend API.

All endpoints are typed with TypeScript interfaces matching Pydantic schemas on
the server side.  The client uses plain `fetch` (no axios dependency) and
automatically serialises request bodies to JSON.

Base URL defaults to `http://localhost:5080` (Vite dev proxy target) but can
be overridden via the `API_BASE_URL` environment variable at build time.

Usage:
  import { api } from '@/api/client'
  const clips = await api.listClips({ roll_type: 'a', tag: 'sunset' })
*/

// ── Environment config ────────────────────────────────────────────

const BASE =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:5080'

// ── Types (mirrors Pydantic models on the server) ───────────────

export interface ClipCandidate {
  source_path: string
}

export interface JobStatus {
  id: number
  status: string          // 'pending' | 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
  total: number
  done: number
  failed: number
  started_at: string | null
  finished_at?: string | null
  kind?: 'scan' | 'reanalyze'
}

export interface JobsQueueResponse {
  jobs: JobStatus[]
  paused: boolean
}

export interface ClipSummary {
  id: number
  source_path: string
  roll_type: 'a' | 'b' // or string if not yet classified
  duration_s: number | null
  thumbnail_path: string | null
  // Optional: always sent by the list endpoint, but omitted in some views/fixtures.
  library_path?: string | null
  summary?: string | null
  description?: string | null
  status?: string          // 'pending' | 'processing' | 'done' | 'failed'
  created_at?: string      // used for client-side date filtering
  capture_time?: string | null  // embedded EXIF capture time (ISO); primary date source
  date_source?: string     // 'embedded' | 'file'
  tags?: TagItem[]         // present on detail / mock data; absent from the list endpoint
}

export interface ClipDetail extends ClipSummary {
  roll_source: string          // 'auto' | 'manual'
  width: number | null
  height: number | null
  fps: number | null
  codec: string | null
  error: string | null
  capture_time: string | null
  date_source: string          // 'embedded' | 'file'
  tags: TagItem[]
  transcript?: TranscriptData
}

export interface TagItem {
  name: string
  source: 'auto' | 'manual'
}

export interface TranscriptData {
  full_text: string
  segments: TranscriptSegment[]
}

export interface TranscriptSegment {
  start_s: number
  end_s: number
  text: string
}

export interface SettingsPrefs {
  source_folders: string[]
  library_path: string | null
  text_model: string
  vision_model: string
  whisper_model: string
  extensions: string[]
  broll_frame_count: number
  vad_threshold: number
  output_language: 'zh' | 'en'
}

export interface SettingsResponse {
  env: Record<string, string>
  prefs: SettingsPrefs
}

export interface LibraryStatus {
  library_path: string | null
}

export interface UpdateSettingsBody {
  source_folders?: string[]
  library_path?: string | null
  text_model?: string
  vision_model?: string
  whisper_model?: string
  extensions?: string[]
  broll_frame_count?: number
  vad_threshold?: number
  output_language?: 'zh' | 'en'
  // Machine-global keys (persisted to ~/.cutfinder/config.json, shared across
  // libraries). Omit OMLX_API_KEY to leave the stored secret unchanged.
  OMLX_BASE_URL?: string
  OMLX_API_KEY?: string
  WHISPER_MODEL_PATH?: string
}

export interface ClipFilter {
  date?: string | null
  roll_type?: string | null
  tag?: string | null
}

export interface ClipEditBody {
  summary?: string | null
  description?: string | null
}

export interface TagListBody {
  tags: Array<{ name: string; source?: 'auto' | 'manual' }>
}

// ── ApiError class ───────────────────────────────────────────────

export class ApiError extends Error {
  constructor(readonly status: number, readonly detail: string) {
    super(`API error ${status}: ${detail}`)
  }

  static async fromResponse(response: Response): Promise<ApiError> {
    const body = await response.json().catch(() => ({})) as Record<string, unknown>
    const detail = Array.isArray(body.detail)
      ? body.detail.map((e: unknown) => (typeof e === 'object' && e !== null ? JSON.stringify(e) : String(e))).join('; ')
      : typeof body.detail === 'string'
        ? body.detail
        : response.statusText
    return new ApiError(response.status, detail)
  }
}

// ── Helpers ──────────────────────────────────────────────────────

async function _fetch<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })

  if (!response.ok) {
    throw await ApiError.fromResponse(response)
  }

  return response.json() as Promise<T>
}

// ── Public API client (immutable object) ────────────────────────

export const api = {
  /** POST /api/scan — enqueue clips for processing. */
  scan(candidates: ClipCandidate[]): Promise<{ job_id: number }> {
    return _fetch('/api/scan', { method: 'POST', body: JSON.stringify(candidates) })
  },

  /** GET /api/clips — list clips with optional filters. */
  listClips(filters?: ClipFilter): Promise<ClipSummary[]> {
    const qs = new URLSearchParams()
    if (filters?.date) qs.set('date', filters.date)
    if (filters?.roll_type) qs.set('roll_type', filters.roll_type)
    if (filters?.tag) qs.set('tag', filters.tag)
    const query = qs.toString() ? `?${qs.toString()}` : ''
    return _fetch<ClipSummary[]>(`/api/clips${query}`)
  },

  /** GET /api/clips/{id} — clip detail with tags & transcript. */
  getClip(id: number): Promise<ClipDetail> {
    return _fetch(`/api/clips/${id}`)
  },

  /** PATCH /api/clips/{id}/roll — correct A/B classification. */
  correctRoll(id: number, roll: 'a' | 'b'): Promise<{ status: string; clip_id: number }> {
    return _fetch(`/api/clips/${id}/roll?roll=${roll}`, { method: 'PATCH' })
  },

  /** PATCH /api/clips/{id} — edit summary/description. */
  updateClip(id: number, body: ClipEditBody): Promise<{ status: string; clip_id: number }> {
    return _fetch(`/api/clips/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
  },

  /** PUT /api/clips/{id}/tags — replace all tags. */
  setTags(id: number, body: TagListBody): Promise<{ status: string; clip_id: number }> {
    return _fetch(`/api/clips/${id}/tags`, { method: 'PUT', body: JSON.stringify(body) })
  },

  /** POST /api/clips/{id}/reanalyze — trigger re-analysis. */
  reanalyzeClip(id: number): Promise<{ job_id: number }> {
    return _fetch(`/api/clips/${id}/reanalyze`, { method: 'POST' })
  },

  /** GET /api/search?q= — full-text search. */
  search(q: string): Promise<ClipSummary[]> {
    return _fetch(`/api/search?q=${encodeURIComponent(q)}`)
  },

  /** GET /api/jobs/{id} — job status. */
  getJob(id: number): Promise<JobStatus> {
    return _fetch(`/api/jobs/${id}`)
  },

  /** GET /api/jobs — list all jobs + global pause state. */
  listJobs(): Promise<JobsQueueResponse> {
    return _fetch('/api/jobs')
  },

  /** DELETE /api/jobs/{id} — delete a job (cancels first if running/queued). */
  deleteJob(id: number): Promise<{ status: string; job_id: number }> {
    return _fetch(`/api/jobs/${id}`, { method: 'DELETE' })
  },

  /** POST /api/jobs/{id}/retry — re-enqueue a job's failed items. */
  retryJob(id: number): Promise<{ job_id: number }> {
    return _fetch(`/api/jobs/${id}/retry`, { method: 'POST' })
  },

  /** POST /api/jobs/pause — globally pause processing. */
  pauseJobs(): Promise<{ paused: boolean }> {
    return _fetch('/api/jobs/pause', { method: 'POST' })
  },

  /** POST /api/jobs/resume — globally resume processing. */
  resumeJobs(): Promise<{ paused: boolean }> {
    return _fetch('/api/jobs/resume', { method: 'POST' })
  },

  /** GET /api/settings — current config. */
  getSettings(): Promise<SettingsResponse> {
    return _fetch('/api/settings')
  },

  /** PUT /api/settings — update prefs. */
  putSettings(body: UpdateSettingsBody): Promise<{ status: string }> {
    return _fetch('/api/settings', { method: 'PUT', body: JSON.stringify(body) })
  },

  /** GET /api/library — the active library path (or null). */
  getLibrary(): Promise<LibraryStatus> {
    return _fetch('/api/library')
  },

  /** POST /api/library — bind a library path at runtime. */
  setLibrary(path: string): Promise<{ status: string; library_path: string }> {
    return _fetch('/api/library', { method: 'POST', body: JSON.stringify({ path }) })
  },

  /** POST /api/pick-folder — open a native macOS folder chooser; path is null if cancelled. */
  pickFolder(): Promise<{ path: string | null }> {
    return _fetch('/api/pick-folder', { method: 'POST' })
  },
} as const
