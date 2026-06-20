/** Jobs queue feature — full-screen "任务队列" page.

Lists all scan/reanalyze jobs with status, lets the user delete a job, retry a
failed job's failed items, and globally pause/resume processing.  Polls
GET /api/jobs every 2s (same idiom as the ProgressBar in features/jobs).

Usage:
  <JobsQueuePage onClose={() => setShowJobs(false)} />
*/

import { useCallback, useEffect, useState } from 'react'

import type { JobStatus } from '@/api/client'
import { api } from '@/api/client'
import { Button } from '@/components/Button'
import { useI18n, type I18n } from '@/i18n'

// ── Label / badge maps ────────────────────────────────────────────

function kindLabel(t: I18n['t'], kind?: string): string {
  if (kind === 'scan') return t('jobs.kindScan')
  if (kind === 'reanalyze') return t('jobs.kindReanalyze')
  return kind || '—'
}

function statusLabel(t: I18n['t'], status: string): string {
  switch (status) {
    case 'queued':
    case 'pending':
      return t('jobs.statusQueued')
    case 'running':
      return t('jobs.statusRunning')
    case 'paused':
      return t('jobs.statusPaused')
    case 'done':
      return t('jobs.statusDone')
    case 'failed':
      return t('jobs.statusFailed')
    case 'cancelled':
      return t('jobs.statusCancelled')
    default:
      return status
  }
}

const STATUS_BADGE: Record<string, string> = {
  queued: 'bg-[--surface-3] text-[--text-secondary]',
  pending: 'bg-[--surface-3] text-[--text-secondary]',
  running: 'bg-[--primary]/15 text-[--primary]',
  paused: 'bg-[--warning]/15 text-[--warning]',
  done: 'bg-[--success]/15 text-[--success]',
  failed: 'bg-[--error]/15 text-[--error]',
  cancelled: 'bg-[--surface-3] text-[--text-muted]',
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (isNaN(d.getTime())) return value
  return d.toLocaleString()
}

// ── Single job row ────────────────────────────────────────────────

function JobRow({ job, paused, onChanged }: { job: JobStatus; paused: boolean; onChanged: () => void }) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)

  // A queued job can't progress while the whole worker is paused — say so
  // explicitly instead of leaving it as an indefinite "queued".
  const isPausedQueued = paused && (job.status === 'queued' || job.status === 'pending')
  const statusText = isPausedQueued ? t('jobs.statusPaused') : statusLabel(t, job.status)
  const statusBadge = isPausedQueued
    ? 'bg-[--warning]/15 text-[--warning]'
    : (STATUS_BADGE[job.status] ?? 'bg-[--surface-3] text-[--text-secondary]')

  const handleDelete = async () => {
    setBusy(true)
    try {
      await api.deleteJob(job.id)
      onChanged()
    } catch {
      // ignore — refresh keeps the list consistent
    } finally {
      setBusy(false)
    }
  }

  const handleRetry = async () => {
    setBusy(true)
    try {
      await api.retryJob(job.id)
      onChanged()
    } catch {
      // ignore (e.g. 400 when there are no failed items)
    } finally {
      setBusy(false)
    }
  }

  const handleResume = async () => {
    setBusy(true)
    try {
      await api.resumeJob(job.id)
      onChanged()
    } catch {
      // ignore — refresh keeps the list consistent
    } finally {
      setBusy(false)
    }
  }

  // A restart-interrupted scan/keyframes job can be resumed (both are idempotent
  // — they re-derive only the remaining work). Reanalyze can't (its target clip
  // isn't recoverable after the in-memory queue is lost).
  const canResume = job.status === 'paused' && job.kind !== 'reanalyze'
  const pct = job.total > 0 ? Math.min(100, Math.round((job.done / job.total) * 100)) : 0

  return (
    <tr className="border-b border-[--border]">
      <td className="px-4 py-3 text-sm tabular-nums text-[--text-muted]">
        #{job.id}
      </td>
      <td className="px-4 py-3 text-sm text-[--text-primary]">
        {kindLabel(t, job.kind)}
      </td>
      <td className="px-4 py-3">
        <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${statusBadge}`}>
          {statusText}
        </span>
      </td>
      <td className="px-4 py-3 text-sm text-[--text-secondary]">
        {job.total === 0 && job.status === 'done' ? (
          <span className="text-[--text-muted]">{t('jobs.noNewFiles')}</span>
        ) : (
          <div className="w-32">
            <div className="flex items-baseline justify-between tabular-nums">
              <span>{job.done}/{job.total}</span>
              {job.failed > 0 && (
                <span className="text-[--error]">{t('jobs.failedN', { n: job.failed })}</span>
              )}
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-[--surface-3]">
              <div
                className={`h-full rounded-full transition-all duration-500 ease-out ${
                  job.status === 'done' ? 'bg-[--success]'
                    : job.status === 'failed' ? 'bg-[--error]'
                    : job.status === 'paused' ? 'bg-[--warning]'
                    : 'bg-[--primary]'
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-[--text-muted]">{formatTime(job.started_at)}</td>
      <td className="px-4 py-3 text-right">
        <div className="flex justify-end gap-2">
          {canResume && (
            <Button size="sm" variant="secondary" onClick={handleResume} disabled={busy}>
              {t('jobs.resume')}
            </Button>
          )}
          {job.failed > 0 && (
            <Button size="sm" variant="secondary" onClick={handleRetry} disabled={busy}>
              {t('jobs.retryFailed')}
            </Button>
          )}
          <Button size="sm" variant="danger" onClick={handleDelete} disabled={busy}>
            {t('jobs.delete')}
          </Button>
        </div>
      </td>
    </tr>
  )
}

// ── Main page ─────────────────────────────────────────────────────

export interface JobsQueuePageProps {
  /** Called when the user closes the page. */
  onClose: () => void
}

export function JobsQueuePage({ onClose }: JobsQueuePageProps) {
  const { t } = useI18n()
  const [jobs, setJobs] = useState<JobStatus[]>([])
  const [paused, setPaused] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const data = await api.listJobs()
      setJobs(data.jobs)
      setPaused(data.paused)
    } catch {
      // silently fail; empty/last state remains
    }
  }, [])

  // Poll on mount and every 2s.
  useEffect(() => {
    let cancelled = false
    const tick = () => { if (!cancelled) void refresh() }
    tick()
    const interval = setInterval(tick, 2000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [refresh])

  const handleTogglePause = async () => {
    try {
      const res = paused ? await api.resumeJobs() : await api.pauseJobs()
      setPaused(res.paused)
      void refresh()
    } catch {
      // ignore
    }
  }

  return (
    <div className="flex h-screen w-full flex-col bg-[--bg-canvas] text-[--text-primary]">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-[--border] bg-[--surface-1] px-6">
        <h1 className="text-lg font-semibold tracking-tight">{t('jobs.title')}</h1>
        <div className="flex items-center gap-3">
          <Button variant="secondary" size="sm" onClick={handleTogglePause}>
            {paused ? t('jobs.resume') : t('jobs.pause')}
          </Button>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-[--text-secondary] hover:bg-[--surface-3] transition-colors"
            aria-label={t('jobs.close')}
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24">
              <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-6">
        {paused && (
          <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-[--warning]/30 bg-[--warning]/10 px-4 py-3">
            <div className="flex items-center gap-2 text-sm text-[--warning]">
              <svg className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.75 5.25v13.5m-7.5-13.5v13.5" />
              </svg>
              <span>{t('jobs.pausedBanner')}</span>
            </div>
            <Button size="sm" variant="secondary" onClick={handleTogglePause}>
              {t('jobs.resumeProcessing')}
            </Button>
          </div>
        )}
        {jobs.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-[--text-muted]">
            {t('jobs.empty')}
          </div>
        ) : (
          <table className="w-full border-collapse overflow-hidden rounded-lg border border-[--border] bg-[--surface-1]">
            <thead>
              <tr className="border-b border-[--border] text-left text-xs font-medium text-[--text-secondary]">
                <th className="px-4 py-2 w-16">{t('jobs.colId')}</th>
                <th className="px-4 py-2">{t('jobs.colType')}</th>
                <th className="px-4 py-2">{t('jobs.colStatus')}</th>
                <th className="px-4 py-2">{t('jobs.colProgress')}</th>
                <th className="px-4 py-2">{t('jobs.colStartTime')}</th>
                <th className="px-4 py-2 text-right">{t('jobs.colActions')}</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <JobRow key={job.id} job={job} paused={paused} onChanged={refresh} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
