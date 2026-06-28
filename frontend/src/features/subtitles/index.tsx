/** Subtitle export feature — full-screen page.
 *
 * The user picks a finished/edited video and an output folder (native macOS
 * dialogs), chooses subtitle formats (iTT / SRT), and exports. The backend
 * transcribes the video's audio and writes subtitle files into the chosen
 * folder. Progress is polled via GET /api/jobs/{id}; produced files are listed
 * with a "Reveal in Finder" action.
 *
 * The subtitle language follows the AI output language set in Settings — this
 * page does NOT pick the language (the backend resolves it).
 *
 * Usage:
 *   <SubtitlesPage onClose={() => setShowSubtitles(false)} />
 */

import { useEffect, useState } from 'react'

import { api } from '@/api/client'
import { Button } from '@/components/Button'
import { useI18n } from '@/i18n'

const basename = (p: string) => p.split('/').pop() || p

// Format a seconds count as m:ss for the elapsed timer.
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

// Percent at which the backend switches from vocal separation to transcription.
// Mirrors `_SEPARATION_WEIGHT` (0.4) in the backend mlx_whisper.py adapter.
const SEPARATION_WEIGHT_PCT = 40

// Poll a job until it reaches a terminal state; returns the final status.
// `onProgress` receives the live done/total percentage (clamped 0..100) on each poll.
async function waitForJob(
  jobId: number,
  onProgress: (pct: number) => void,
  timeoutMs = 30 * 60_000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1500))
    try {
      const job = await api.getJob(jobId)
      const pct = job.total > 0 ? (job.done / job.total) * 100 : 0
      onProgress(Math.max(0, Math.min(100, pct)))
      if (['done', 'failed', 'cancelled'].includes(job.status)) return job.status
    } catch {
      // transient error — keep polling
    }
  }
  return 'failed'
}

type Phase = 'idle' | 'running' | 'done' | 'error'

export interface SubtitlesPageProps {
  /** Called when the user closes the page. */
  onClose: () => void
}

export function SubtitlesPage({ onClose }: SubtitlesPageProps) {
  const { t } = useI18n()
  const [videoPath, setVideoPath] = useState<string | null>(null)
  const [outDir, setOutDir] = useState<string | null>(null)
  const [itt, setItt] = useState(true)
  const [srt, setSrt] = useState(true)
  const [phase, setPhase] = useState<Phase>('idle')
  const [files, setFiles] = useState<string[]>([])
  const [jobId, setJobId] = useState<number | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [progress, setProgress] = useState(0)
  // True when the speech model wasn't on disk at export time: the first export
  // blocks on a multi-GB download before transcription can start, so we surface
  // a notice (the stall would otherwise look like a frozen progress bar).
  const [modelDownloading, setModelDownloading] = useState(false)

  // Re-attach to a subtitle job still running in the backend after a page
  // refresh: the worker keeps transcribing even though the UI lost its job id,
  // so resume the progress bar instead of showing an idle form.
  useEffect(() => {
    let cancelled = false
    api.listJobs()
      .then(async ({ jobs }) => {
        const active = jobs.find(
          (j) => j.kind === 'subtitle' && ['queued', 'running'].includes(j.status),
        )
        if (!active || cancelled) return
        setJobId(active.id)
        setPhase('running')
        const status = await waitForJob(active.id, setProgress)
        if (cancelled) return
        if (status !== 'done') { setPhase('error'); return }
        const result = await api.getSubtitleResult(active.id)
        if (cancelled) return
        setFiles(result.files)
        setPhase('done')
      })
      .catch(() => {}) // backend unreachable / no jobs — nothing to restore
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Tick an elapsed timer while a job is running so the user sees it's working
  // (Whisper transcription of a long video can take minutes with no sub-step).
  useEffect(() => {
    if (phase !== 'running') return
    setElapsed(0)
    const id = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [phase])

  const formats = [itt ? 'itt' : null, srt ? 'srt' : null].filter(Boolean) as string[]
  const canExport = Boolean(videoPath) && Boolean(outDir) && formats.length > 0 && phase !== 'running'

  const handlePickVideo = async () => {
    try {
      const { path } = await api.pickFile()
      if (path) setVideoPath(path)
    } catch {
      // backend unreachable / non-macOS — silently ignore
    }
  }

  const handlePickFolder = async () => {
    try {
      const { path } = await api.pickFolder()
      if (path) setOutDir(path)
    } catch {
      // backend unreachable / non-macOS — silently ignore
    }
  }

  const handleExport = async () => {
    if (!videoPath || !outDir || formats.length === 0) return
    setPhase('running')
    setFiles([])
    setProgress(0)
    // Check up front whether the speech model still needs downloading, so the
    // notice is visible during the (silent, networked) first-use stall.
    try {
      const { ready } = await api.getSubtitleModelReady()
      setModelDownloading(!ready)
    } catch {
      setModelDownloading(false)
    }
    try {
      const { job_id } = await api.exportSubtitles({
        video_path: videoPath,
        out_dir: outDir,
        formats,
      })
      setJobId(job_id)
      const status = await waitForJob(job_id, (pct) => {
        setProgress(pct)
        // Once real transcription progress appears past the model-load stall,
        // the download has finished — drop the notice.
        if (pct > SEPARATION_WEIGHT_PCT) setModelDownloading(false)
      })
      if (status !== 'done') {
        setPhase('error')
        return
      }
      const result = await api.getSubtitleResult(job_id)
      setFiles(result.files)
      setPhase('done')
    } catch {
      setPhase('error')
    }
  }

  const handleReveal = async () => {
    if (jobId === null) return
    try {
      await api.revealSubtitle(jobId)
    } catch {
      // ignore
    }
  }

  return (
    <div className="flex h-screen w-full flex-col bg-[--bg-canvas] text-[--text-primary]">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-[--border] bg-[--surface-1] px-6">
        <h1 className="text-lg font-semibold tracking-tight">{t('subtitles.title')}</h1>
        <button
          onClick={onClose}
          className="rounded-md p-1.5 text-[--text-secondary] hover:bg-[--surface-3] transition-colors"
          aria-label={t('subtitles.close')}
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24">
            <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="mx-auto w-full max-w-2xl space-y-6">
          <p className="text-sm text-[--text-secondary]">{t('subtitles.desc')}</p>

          {/* ── Video ─────────────────────────────── */}
          <fieldset className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
            <legend className="text-sm font-medium text-[--text-primary]">{t('subtitles.video')}</legend>
            {videoPath ? (
              <div className="mt-2">
                <div className="truncate text-sm font-medium text-[--text-primary]">{basename(videoPath)}</div>
                <div className="truncate text-xs text-[--text-muted]">{videoPath}</div>
              </div>
            ) : (
              <p className="mt-2 text-sm text-[--text-muted]">{t('subtitles.noVideo')}</p>
            )}
            <button
              type="button"
              onClick={handlePickVideo}
              className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-[--surface-2] px-3 py-1.5 text-xs font-medium text-[--text-secondary] hover:bg-[--surface-3]"
            >
              {t('subtitles.chooseVideo')}
            </button>
          </fieldset>

          {/* ── Output folder ─────────────────────── */}
          <fieldset className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
            <legend className="text-sm font-medium text-[--text-primary]">{t('subtitles.folder')}</legend>
            {outDir ? (
              <div className="mt-2 truncate text-sm text-[--text-primary]">{outDir}</div>
            ) : (
              <p className="mt-2 text-sm text-[--text-muted]">{t('subtitles.noFolder')}</p>
            )}
            <button
              type="button"
              onClick={handlePickFolder}
              className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-[--surface-2] px-3 py-1.5 text-xs font-medium text-[--text-secondary] hover:bg-[--surface-3]"
            >
              {t('subtitles.chooseFolder')}
            </button>
          </fieldset>

          {/* ── Formats ───────────────────────────── */}
          <fieldset className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
            <legend className="text-sm font-medium text-[--text-primary]">{t('subtitles.formats')}</legend>
            <div className="mt-3 flex gap-6">
              <label className="flex items-center gap-2 text-sm text-[--text-secondary]">
                <input
                  type="checkbox" checked={itt}
                  onChange={(e) => setItt(e.target.checked)}
                  className="h-4 w-4 rounded border-[--border] bg-[--surface-2]"
                />
                {t('subtitles.itt')}
              </label>
              <label className="flex items-center gap-2 text-sm text-[--text-secondary]">
                <input
                  type="checkbox" checked={srt}
                  onChange={(e) => setSrt(e.target.checked)}
                  className="h-4 w-4 rounded border-[--border] bg-[--surface-2]"
                />
                {t('subtitles.srt')}
              </label>
            </div>
            <p className="mt-3 text-xs text-[--text-muted]">{t('subtitles.languageNote')}</p>
          </fieldset>

          {/* ── Export ────────────────────────────── */}
          <div className="flex items-center gap-3">
            <Button onClick={handleExport} disabled={!canExport}>
              {phase === 'running' ? t('subtitles.exporting') : t('subtitles.export')}
            </Button>
          </div>

          {/* ── Progress (determinate, two phases: separation → transcription) ─ */}
          {phase === 'running' && (
            <div className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 text-sm font-medium text-[--text-primary]">
                  <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-[--primary] border-t-transparent" />
                  {t(
                    modelDownloading
                      ? 'subtitles.phaseDownloadingModel'
                      : progress < SEPARATION_WEIGHT_PCT
                        ? 'subtitles.phaseSeparating'
                        : 'subtitles.phaseTranscribing',
                  )}
                </span>
                <span className="number-tabular text-xs text-[--text-muted]">
                  {t('subtitles.elapsed', { time: mmss(elapsed) })}
                </span>
              </div>
              <div className="mt-3 flex items-center gap-3">
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[--surface-3]">
                  <div className="h-full rounded-full bg-[--primary] transition-all duration-500 ease-out" style={{ width: `${progress}%` }} />
                </div>
                <span className="tabular-nums text-xs text-[--text-secondary]">{Math.round(progress)}%</span>
              </div>
              <p className="mt-2 text-xs text-[--text-muted]">
                {t(modelDownloading ? 'subtitles.downloadingModelHint' : 'subtitles.progressHint')}
              </p>
            </div>
          )}

          {/* ── Result ────────────────────────────── */}
          {phase === 'error' && (
            <p className="text-sm text-[--error]">{t('subtitles.failed')}</p>
          )}
          {phase === 'done' && (
            <div className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <span className="text-sm font-medium text-[--success]">{t('subtitles.done')}</span>
                <Button size="sm" variant="secondary" onClick={handleReveal}>
                  {t('subtitles.reveal')}
                </Button>
              </div>
              <ul className="space-y-1">
                {files.map((f) => (
                  <li key={f} className="truncate font-mono text-xs text-[--text-secondary]">{basename(f)}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
