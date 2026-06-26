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

// Dev: talk to the Vite dev server (which proxies /api → backend). Production
// build (packaged .app): same-origin, since one server serves UI + API.
const BASE =
  import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.PROD ? '' : 'http://localhost:5080')

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
  kind?: 'scan' | 'reanalyze' | 'keyframes' | 'subtitle'
}

export interface JobsQueueResponse {
  jobs: JobStatus[]
  paused: boolean
}

export interface ClipSummary {
  id: number
  source_path: string
  roll_type: 'a' | 'b' | 'photo' // or string if not yet classified
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
  has_keyframes?: boolean  // true if the clip has keyframe suggestions
  tags?: TagItem[]         // present on detail / mock data; absent from the list endpoint
}

export interface CutSuggestion {
  rank: number
  start_s: number
  end_s: number
  reason: string
  source: 'text' | 'vision'
  has_frame: boolean
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
  keyframes?: CutSuggestion[]
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
  transcription_engine: 'whisper' | 'qwen'
  qwen_asr_model: string
  qwen_aligner_model: string
  qwen_max_chunk_s: number
  extensions: string[]
  photo_extensions: string[]
  broll_frame_count: number
  vad_threshold: number
  vocal_separation: boolean
  output_language: 'zh' | 'en'
  // UI interface language — per-device (one value for the whole machine). Drives
  // which default director prompt is shown and used, as well as progress messages.
  ui_language?: 'zh' | 'en'
  keyframe_count: number
  keyframe_auto: boolean
  cut_director_mode?: 'agent' | 'staged'
  cut_max_tool_rounds: number
  cut_vision_budget: number
  cut_default_aspect_ratio: string
  cut_critic_enabled?: boolean
  cut_lean_token_budget?: number
  cut_staged_token_budget?: number
  // Machine-global keys are merged into this one view (no separate "env" group);
  // the OMLX secret comes back masked. Optional so test fixtures can omit them.
  OMLX_BASE_URL?: string
  OMLX_API_KEY?: string
  TEXT_MODEL?: string
  VISION_MODEL?: string
}

export interface SettingsResponse {
  prefs: SettingsPrefs
}

export interface LibraryStatus {
  library_path: string | null
}

export interface LogEntry {
  seq: number
  time: number        // epoch seconds
  level: string       // 'INFO' | 'WARNING' | 'ERROR' | ...
  name: string        // logger name
  message: string
}

export interface LogsResponse {
  logs: LogEntry[]
  last_seq: number
}

export interface UpdateSettingsBody {
  source_folders?: string[]
  library_path?: string | null
  text_model?: string
  vision_model?: string
  whisper_model?: string
  transcription_engine?: 'whisper' | 'qwen'
  qwen_asr_model?: string
  qwen_aligner_model?: string
  qwen_max_chunk_s?: number
  extensions?: string[]
  photo_extensions?: string[]
  broll_frame_count?: number
  vad_threshold?: number
  vocal_separation?: boolean
  output_language?: 'zh' | 'en'
  ui_language?: 'zh' | 'en'
  keyframe_count?: number
  keyframe_auto?: boolean
  cut_director_mode?: 'agent' | 'staged'
  cut_max_tool_rounds?: number
  cut_vision_budget?: number
  cut_default_aspect_ratio?: string
  cut_critic_enabled?: boolean
  cut_lean_token_budget?: number
  cut_staged_token_budget?: number
  // Machine-global keys (persisted to ~/.cutfinder/config.json, shared across
  // libraries). Omit OMLX_API_KEY to leave the stored secret unchanged.
  OMLX_BASE_URL?: string
  OMLX_API_KEY?: string
  TEXT_MODEL?: string
  VISION_MODEL?: string
}

export interface ClipFilter {
  date?: string | null
  roll_type?: string | null
  tag?: string | null
}

// ── Rough-cut director agent (§3.15) ────────────────────────────

export interface CutSession {
  id: number
  title: string
  status: string // 'idle' | 'running' | 'error'
  progress?: string // live status while a turn runs (e.g. "第 2/6 天 · 查看片段 #123")
  created_at: string | null
  updated_at: string | null
}

export interface CutMessage {
  role: 'user' | 'assistant'
  content: string
  created_at: string | null
}

export interface CutShot {
  clip_id: number
  roll: string
  in_s: number
  out_s: number
  content: string
  rationale: string
  chapter: string
  clip_label: string
  clip_date: string
  thumb_ref: string | null
}

export interface CutPromptResponse {
  prompt: string
  default: string
  is_default: boolean
}

export interface CutPlan {
  shots: CutShot[]
  chapters: string[]
  total_s: number
  target_min_s: number | null
  target_max_s: number | null
  within_target: boolean
  note: string
  markdown: string
}

export interface CutSessionDetail {
  session: CutSession
  messages: CutMessage[]
  plan: CutPlan | null
}

export interface RoughCutRequestBody {
  date_from?: string | null
  date_to?: string | null
  target_min_s?: number | null
  target_max_s?: number | null
  aspect_ratio?: string | null
  style_notes?: string | null
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

  /** PATCH /api/clips/{id}/roll — correct A/B classification (relocates the copy). */
  correctRoll(id: number, roll: 'a' | 'b'): Promise<{ status: string; clip_id: number; library_path?: string | null }> {
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

  /** POST /api/clips/{id}/keyframes — generate keyframe (cut/frame) suggestions. */
  suggestKeyframes(id: number): Promise<{ job_id: number }> {
    return _fetch(`/api/clips/${id}/keyframes`, { method: 'POST' })
  },

  /** POST /api/keyframes — generate keyframes for all clips that lack them. */
  suggestAllKeyframes(): Promise<{ job_id: number; count: number }> {
    return _fetch('/api/keyframes', { method: 'POST' })
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

  /** POST /api/jobs/{id}/resume — resume a restart-interrupted scan job. */
  resumeJob(id: number): Promise<{ job_id: number }> {
    return _fetch(`/api/jobs/${id}/resume`, { method: 'POST' })
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

  /** GET /api/library/orphans — catalog entries whose library copy was deleted. */
  listOrphans(): Promise<{
    library_reachable: boolean
    orphans: Array<{ id: number; source_path: string; library_path: string | null; roll_type: string }>
  }> {
    return _fetch('/api/library/orphans')
  },

  /** POST /api/library/orphans/delete — delete the given clip ids + derived files. */
  deleteOrphans(clipIds: number[]): Promise<{ deleted: number }> {
    return _fetch('/api/library/orphans/delete', { method: 'POST', body: JSON.stringify({ clip_ids: clipIds }) })
  },

  /** POST /api/pick-folder — open a native macOS folder chooser; path is null if cancelled. */
  pickFolder(): Promise<{ path: string | null }> {
    return _fetch('/api/pick-folder', { method: 'POST' })
  },

  /** POST /api/pick-file — open a native macOS file chooser; path is null if cancelled. */
  pickFile(): Promise<{ path: string | null }> {
    return _fetch('/api/pick-file', { method: 'POST' })
  },

  /** POST /api/subtitles/export — transcribe a video and write subtitle files. */
  exportSubtitles(body: {
    video_path: string
    out_dir: string
    formats: string[]
    language?: string
  }): Promise<{ job_id: number }> {
    return _fetch('/api/subtitles/export', { method: 'POST', body: JSON.stringify(body) })
  },

  /** GET /api/subtitles/{jobId} — subtitle export result (files populate once done). */
  getSubtitleResult(jobId: number): Promise<{ job_id: number; status: string; files: string[] }> {
    return _fetch(`/api/subtitles/${jobId}`)
  },

  /** POST /api/subtitles/{jobId}/reveal — reveal the output folder in Finder. */
  revealSubtitle(jobId: number): Promise<{ status: string }> {
    return _fetch(`/api/subtitles/${jobId}/reveal`, { method: 'POST' })
  },

  /** POST /api/open — reveal a folder in Finder or open a file in its default app. */
  openPath(path: string): Promise<{ status: string; path: string }> {
    return _fetch('/api/open', { method: 'POST', body: JSON.stringify({ path }) })
  },

  // ── Rough-cut director agent (§3.15) ──────────────────────────

  /** GET /api/cut/sessions — list rough-cut conversations. */
  listCutSessions(): Promise<{ sessions: CutSession[] }> {
    return _fetch('/api/cut/sessions')
  },

  /** POST /api/cut/sessions — create a new conversation. */
  createCutSession(title = ''): Promise<CutSession> {
    return _fetch('/api/cut/sessions', { method: 'POST', body: JSON.stringify({ title }) })
  },

  /** GET /api/cut/sessions/{id} — messages + latest plan. */
  getCutSession(id: number): Promise<CutSessionDetail> {
    return _fetch(`/api/cut/sessions/${id}`)
  },

  /** DELETE /api/cut/sessions/{id} — delete a conversation. */
  deleteCutSession(id: number): Promise<{ status: string; session_id: number }> {
    return _fetch(`/api/cut/sessions/${id}`, { method: 'DELETE' })
  },

  /** POST /api/cut/sessions/{id}/messages — send a message; runs a director turn. */
  sendCutMessage(
    id: number,
    text: string,
    request?: RoughCutRequestBody,
  ): Promise<{ job_id: number; session_id: number }> {
    return _fetch(`/api/cut/sessions/${id}/messages`, {
      method: 'POST',
      body: JSON.stringify({ text, request }),
    })
  },

  /** GET /api/cut/sessions/{id}/plan — latest plan (with rendered markdown). */
  getCutPlan(id: number): Promise<{ plan: CutPlan | null }> {
    return _fetch(`/api/cut/sessions/${id}/plan`)
  },

  /** GET /api/cut/prompt — current director prompt (+ built-in default). */
  getCutPrompt(): Promise<CutPromptResponse> {
    return _fetch('/api/cut/prompt')
  },

  /** PUT /api/cut/prompt — save a custom director prompt. */
  setCutPrompt(prompt: string): Promise<CutPromptResponse> {
    return _fetch('/api/cut/prompt', { method: 'PUT', body: JSON.stringify({ prompt }) })
  },

  /** DELETE /api/cut/prompt — reset to the built-in default. */
  resetCutPrompt(): Promise<CutPromptResponse> {
    return _fetch('/api/cut/prompt', { method: 'DELETE' })
  },

  /** GET /api/logs — recent backend log lines (poll with `after` for new ones). */
  getLogs(after = 0, limit = 500): Promise<LogsResponse> {
    return _fetch(`/api/logs?after=${after}&limit=${limit}`)
  },
} as const
