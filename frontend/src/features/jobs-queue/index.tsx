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
  if (kind === 'keyframes') return t('jobs.kindKeyframes')
  if (kind === 'subtitle') return t('jobs.kindSubtitle')
  if (kind === 'cutplan') return t('jobs.kindCutplan')
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

// Kind badge colors — match OpenDesign: scan=primary, keyframe=warning, cut=teal
const KIND_BADGE: Record<string, string> = {
  scan: 'bg-[--primary-soft] text-[--primary]',
  reanalyze: 'bg-[--primary-soft] text-[--primary]',
  keyframes: 'bg-[--warning]/15 text-[--warning]',
  subtitle: 'bg-[--primary-soft] text-[--primary]',
  cutplan: 'bg-teal-500/15 text-teal-600',
}

const STATUS_COLOR: Record<string, string> = {
  queued: 'text-[--text-muted]',
  pending: 'text-[--text-muted]',
  running: 'text-[--primary]',
  paused: 'text-[--warning]',
  done: 'text-[--success]',
  failed: 'text-[--error]',
  cancelled: 'text-[--text-muted]',
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
  const statusColor = isPausedQueued
    ? 'text-[--warning]'
    : (STATUS_COLOR[job.status] ?? 'text-[--text-secondary]')
  const kindBadge = KIND_BADGE[job.kind ?? ''] ?? 'bg-[--surface-3] text-[--text-secondary]'

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

  // Progress bar fill color
  const progressFillClass =
    job.status === 'done' ? 'bg-[--success]'
      : job.status === 'failed' ? 'bg-[--error]'
        : job.status === 'paused' ? 'bg-[--warning]'
          : 'bg-[--primary]'

  return (
    <tr className="border-b border-[--border] hover:bg-[--surface-2] transition-colors">
      <td className="px-4 py-3">
        <span className="font-mono text-sm text-[--text-secondary] font-medium">#{job.id}</span>
      </td>
      <td className="px-4 py-3">
        <span className={`inline-flex items-center h-[22px] px-2 text-xs font-semibold rounded-[4px] whitespace-nowrap ${kindBadge}`}>
          {kindLabel(t, job.kind)}
        </span>
      </td>
      <td className="px-4 py-3">
        <span className={`text-sm font-medium whitespace-nowrap ${statusColor}`}>
          {statusText}
        </span>
      </td>
      <td className="px-4 py-3 min-w-[140px]">
        {job.total === 0 && job.status === 'done' ? (
          <span className="text-[--text-muted]">{t('jobs.noNewFiles')}</span>
        ) : (
          <div className="flex flex-col gap-1">
            <div className="h-[4px] overflow-hidden rounded-[2px] bg-[--surface-3]">
              <div
                className={`h-full rounded-[2px] transition-all duration-300 ease-out ${progressFillClass}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="flex items-baseline justify-between tabular-nums">
              <span className="font-mono text-xs text-[--text-muted]">{job.done}/{job.total}</span>
              {job.failed > 0 && (
                <span className="text-xs text-[--error]">{t('jobs.failedN', { n: job.failed })}</span>
              )}
            </div>
            {job.status === 'failed' && job.error && (
              <p
                className="mt-0.5 max-w-[200px] truncate text-xs text-[--error]"
                title={job.error}
              >
                {t('jobs.errorLabel')}: {job.error}
              </p>
            )}
          </div>
        )}
      </td>
      <td className="px-4 py-3">
        <span className="font-mono text-xs text-[--text-secondary] whitespace-nowrap">
          {formatTime(job.started_at)}
        </span>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          {canResume && (
            <button
              onClick={handleResume}
              disabled={busy}
              className="h-6 px-2.5 text-xs font-medium rounded-md border border-[--border] text-[--text-secondary] hover:bg-[--surface-2] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {t('jobs.resume')}
            </button>
          )}
          {job.failed > 0 && (
            <button
              onClick={handleRetry}
              disabled={busy}
              className="h-6 px-2.5 text-xs font-medium rounded-md border border-[--border] text-[--text-secondary] hover:bg-[--surface-2] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {t('jobs.retryFailed')}
            </button>
          )}
          <button
            onClick={handleDelete}
            disabled={busy}
            className="h-6 px-2.5 text-xs font-medium rounded-md border border-[--error] text-[--error] hover:bg-[--error] hover:text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {t('jobs.delete')}
          </button>
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
