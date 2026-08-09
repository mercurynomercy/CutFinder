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
  // Minimum on-screen seconds per cue (0 = keep transcribed timing). Holds short
  // cues long enough to read, without overlapping the next. Defaults to 2s.
  const [minCueS, setMinCueS] = useState(2)
  const [phase, setPhase] = useState<Phase>('idle')
  const [files, setFiles] = useState<string[]>([])
  const [jobId, setJobId] = useState<number | null>(null)
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

  const formats = [itt ? 'itt' : null, srt ? 'srt' : null].filter(Boolean) as string[]
  const canExport = Boolean(videoPath) && Boolean(outDir) && formats.length > 0 && phase !== 'running'

  const handlePickVideo = async () => {
    if (videoPath) {
      setVideoPath(null)
      return
    }
    try {
      const { path } = await api.pickFile()
      if (path) setVideoPath(path)
    } catch {
      // backend unreachable / non-macOS — silently ignore
    }
  }

  const handlePickFolder = async () => {
    if (outDir) {
      setOutDir(null)
      return
    }
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
        min_cue_s: minCueS,
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

  // Build the readiness status text for the footer.
  const statusText = canExport
    ? `Ready — will export ${formats.join(' + ')} format`
    : ''

  return (
    <div className="flex h-screen w-full flex-col bg-[--bg-canvas] text-[--text-primary]">
      {/* ── Top Bar ─────────────────────────────── */}
      <header className="flex h-12 shrink-0 items-center border-b border-[--border] bg-[--surface-1] px-4">
        <h1 className="text-lg font-semibold tracking-tight">{t('subtitles.title')}</h1>
        <span className="flex-1" />
        <button
          onClick={onClose}
          className="rounded-md p-1.5 text-[--text-secondary] hover:bg-[--surface-3] transition-colors"
          aria-label={t('subtitles.close')}
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 16 16">
            <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 4l8 8M12 4l-8 8" />
          </svg>
        </button>
      </header>

      {/* ── Content ─────────────────────────────── */}
      <div className="flex-1 overflow-auto px-6 py-6">
        <div className="mx-auto w-full max-w-[640px] flex flex-col gap-5">
          <p className="text-sm text-[--text-secondary] leading-relaxed">{t('subtitles.desc')}</p>

          {/* ── Video Selection Card ──────────────── */}
          <div className="rounded-lg border border-[--border] bg-[--surface-1] p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-[--text-primary]">{t('subtitles.video')}</span>
            </div>
            {videoPath ? (
              <div className="flex flex-col gap-1">
                <span className="text-sm font-medium text-[--text-primary]">{basename(videoPath)}</span>
                <span className="font-mono text-xs text-[--text-muted]">{videoPath}</span>
              </div>
            ) : (
              <span className="text-xs text-[--text-muted] italic">{t('subtitles.noVideo')}</span>
            )}
            <button
              type="button"
              onClick={handlePickVideo}
              className={`h-8 px-3 flex items-center justify-center text-sm font-medium rounded-md transition-colors ${
                videoPath
                  ? 'bg-[--success] text-white'
                  : 'bg-[--primary] text-[--primary-fg] hover:bg-[--primary-hover]'
              }`}
            >
              {videoPath ? '更换视频' : t('subtitles.chooseVideo')}
            </button>
          </div>

          {/* ── Output Folder Card ────────────────── */}
          <div className="rounded-lg border border-[--border] bg-[--surface-1] p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-[--text-primary]">{t('subtitles.folder')}</span>
            </div>
            {outDir ? (
              <span className="text-sm font-medium text-[--text-primary]">{outDir}</span>
            ) : (
              <span className="text-xs text-[--text-muted] italic">{t('subtitles.noFolder')}</span>
            )}
            <button
              type="button"
              onClick={handlePickFolder}
              className={`h-8 px-3 flex items-center justify-center text-sm font-medium rounded-md transition-colors ${
                outDir
                  ? 'bg-[--success] text-white'
                  : 'bg-[--primary] text-[--primary-fg] hover:bg-[--primary-hover]'
              }`}
            >
              {outDir ? '更换文件夹' : t('subtitles.chooseFolder')}
            </button>
          </div>

          {/* ── Format Options Card ──────────────── */}
          <div className="rounded-lg border border-[--border] bg-[--surface-1] p-4 flex flex-col gap-2.5">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-[--text-primary]">{t('subtitles.formats')}</span>
            </div>
            <div className="flex flex-col gap-2.5">
              {/* iTT checkbox */}
              <label className="flex items-center gap-2 cursor-pointer">
                <span className="relative w-[18px] h-[18px] flex-shrink-0">
                  <input
                    type="checkbox"
                    checked={itt}
                    onChange={(e) => setItt(e.target.checked)}
                    className="absolute opacity-0 w-full h-full cursor-pointer z-1 m-0"
                  />
                  <span
                    className={`w-[18px] h-[18px] rounded-[4px] flex items-center justify-center transition-all duration-150 ${
                      itt ? 'bg-[--primary] border-[--primary]' : 'border border-[--border] bg-[--surface-2]'
                    }`}
                  >
                    <svg className="w-3 h-3 text-[--primary-fg]" style={{ opacity: itt ? 1 : 0, transition: 'opacity 150ms' }} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path d="M2.5 6.5L4.5 8.5L9.5 3.5" />
                    </svg>
                  </span>
                </span>
                <span className="text-sm font-medium text-[--text-primary]">{t('subtitles.itt')}</span>
              </label>
              {/* SRT checkbox */}
              <label className="flex items-center gap-2 cursor-pointer">
                <span className="relative w-[18px] h-[18px] flex-shrink-0">
                  <input
                    type="checkbox"
                    checked={srt}
                    onChange={(e) => setSrt(e.target.checked)}
                    className="absolute opacity-0 w-full h-full cursor-pointer z-1 m-0"
                  />
                  <span
                    className={`w-[18px] h-[18px] rounded-[4px] flex items-center justify-center transition-all duration-150 ${
                      srt ? 'bg-[--primary] border-[--primary]' : 'border border-[--border] bg-[--surface-2]'
                    }`}
                  >
                    <svg className="w-3 h-3 text-[--primary-fg]" style={{ opacity: srt ? 1 : 0, transition: 'opacity 150ms' }} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path d="M2.5 6.5L4.5 8.5L9.5 3.5" />
                    </svg>
                  </span>
                </span>
                <span className="text-sm font-medium text-[--text-primary]">{t('subtitles.srt')}</span>
              </label>
            </div>
            <p className="text-xs text-[--text-muted] leading-relaxed -mt-0.5">{t('subtitles.languageNote')}</p>

            {/* Minimum on-screen seconds per cue */}
            <div className="flex items-center gap-2 pt-1 border-t border-[--border]">
              <span className="text-xs font-medium text-[--text-secondary] whitespace-nowrap">{t('subtitles.minDuration')}</span>
              <input
                type="number"
                min={0}
                max={30}
                step={0.5}
                value={minCueS}
                onChange={(e) => setMinCueS(parseFloat(e.target.value) || 0)}
                className="w-[72px] h-8 text-center font-mono text-sm bg-[--surface-2] border border-[--border] rounded-md text-[--text-primary] outline-none transition-colors focus:border-[--primary] focus:shadow-[0_0_0_2px_var(--primary-soft)]"
              />
              <span className="text-xs text-[--text-muted]">s</span>
            </div>
            <p className="text-xs text-[--text-muted] leading-relaxed">{t('subtitles.minDurationDesc')}</p>
          </div>

          {/* ── Model download notice (shown in content while model loads) ─ */}
          {phase === 'running' && modelDownloading && (
            <p className="text-xs text-[--text-muted]">
              {t('subtitles.downloadingModelHint')}
            </p>
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

      {/* ── Footer ──────────────────────────────── */}
      <footer className="shrink-0 border-t border-[--border] bg-[--surface-1] px-6 py-3 flex flex-col gap-2">
        {/* Progress bar — visible during export */}
        <div className={`flex flex-col gap-1 ${phase === 'running' ? '' : 'hidden'}`}>
          <div className="h-[4px] w-full overflow-hidden rounded-[2px] bg-[--surface-3]">
            <div className="h-full rounded-[2px] bg-[--primary] transition-all duration-300 ease-out" style={{ width: `${progress}%` }} />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-[--text-muted]">
              {t(
                modelDownloading
                  ? 'subtitles.phaseDownloadingModel'
                  : progress < SEPARATION_WEIGHT_PCT
                    ? 'subtitles.phaseSeparating'
                    : 'subtitles.phaseTranscribing',
              )}
            </span>
            <span className="font-mono text-xs text-[--text-muted]">{Math.round(progress)}%</span>
          </div>
        </div>
        {/* Status + buttons row — always present, invisible during export */}
        <div className={`flex items-center justify-between ${phase === 'running' ? 'invisible' : ''}`}>
          <span className="text-xs text-[--text-muted]">
            {statusText}
          </span>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose}>
              {t('subtitles.close')}
            </Button>
            <button
              onClick={handleExport}
              disabled={!canExport}
              className="h-9 px-5 flex items-center justify-center text-sm font-medium rounded-md bg-[--primary] text-[--primary-fg] hover:bg-[--primary-hover] transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:pointer-events-none"
            >
              {t('subtitles.export')}
            </button>
          </div>
        </div>
      </footer>
    </div>
  )
}
