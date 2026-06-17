/** Jobs feature — ambient scan progress (thin top bar + floating card) and toasts.

Listens to SSE events via `useJobEvents` and polls job status. Shows:
- A thin progress bar fixed to the very top of the viewport.
- A compact floating progress card (bottom-right) with count + current clip.
- Toast notifications for job start/completion/failure.

Usage:
  <JobsPanel activeJobId={currentScanJobId} />
*/

import { useCallback, useEffect, useState } from 'react'

import type { JobStatus } from '@/api/client'
import { api } from '@/api/client'
import { useJobEvents, type JobEvent } from '@/api/sse'
import { useI18n } from '@/i18n'

// ── Toast notifications ─────────────────────────────────────────────

interface ToastItem {
  id: number
  type: 'info' | 'success' | 'error'
  message: string
}

let toastIdCounter = 0

function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const addToast = useCallback((type: ToastItem['type'], message: string) => {
    const id = ++toastIdCounter
    setToasts((prev) => [...prev, { id, type, message }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 5000)
    return id
  }, [])

  return { toasts, addToast } as const
}

// ── Scan progress (thin top bar + floating card) ────────────────────

interface ScanProgressProps {
  jobId: number | null
  events: JobEvent[]
}

function ScanProgress({ jobId, events }: ScanProgressProps) {
  const { t } = useI18n()
  const [job, setJob] = useState<JobStatus | null>(null)

  // Poll job status for the determinate counter (SSE drives the live filename).
  useEffect(() => {
    if (!jobId) { setJob(null); return }
    setJob(null)  // drop the previous job's status so it can't leak across jobs
    let cancelled = false
    const tick = () => {
      if (cancelled) return
      api.getJob(jobId).then((j) => { if (!cancelled) setJob(j) }).catch(() => {})
    }
    tick()
    const interval = setInterval(tick, 1500)
    return () => { cancelled = true; clearInterval(interval) }
  }, [jobId])

  // The scan is finished once a terminal SSE event arrives OR the polled job
  // status is terminal. The status check is essential: SSE only delivers events
  // emitted after we subscribe, so a job that completes before/around mount
  // never yields a terminal SSE event — without the status fallback the card
  // would linger forever.
  const finishedBySse = events.some((e) => e.type === 'job_completed' || e.type === 'job_failed')
  const finishedByStatus = job != null && ['done', 'failed', 'cancelled'].includes(job.status)
  const finished = finishedBySse || finishedByStatus

  if (!jobId || finished) return null

  // Most recent clip path from SSE (clip_started / clip_done).
  let currentPath: string | null = null
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i]
    if ((e.type === 'clip_started' || e.type === 'clip_done') && e.path) {
      currentPath = e.path as string
      break
    }
  }

  const total = job?.total ?? 0
  const done = job?.done ?? 0
  const pct = total > 0 ? Math.round((done / total) * 100) : null

  return (
    <>
      {/* Thin progress bar pinned to the very top of the viewport */}
      <div className="fixed inset-x-0 top-0 z-[60] h-0.5 bg-[--surface-2]">
        {pct === null ? (
          <div className="h-full w-1/3 animate-[cf-slide_1.4s_ease-in-out_infinite] bg-[--primary]" />
        ) : (
          <div className="h-full bg-[--primary] transition-all duration-500 ease-out" style={{ width: `${pct}%` }} />
        )}
        <style>{`@keyframes cf-slide{0%{transform:translateX(-120%)}100%{transform:translateX(420%)}}`}</style>
      </div>

      {/* Floating progress card */}
      <div className="fixed bottom-4 right-4 z-[90] w-72 rounded-xl border border-[--border] bg-[--surface-1] p-3 shadow-xl">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-medium text-[--text-primary]">
            <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-[--primary] border-t-transparent" />
            {t('jobs.scanning')}
          </div>
          {pct !== null && (
            <span className="text-xs tabular-nums text-[--text-secondary]">{done}/{total}</span>
          )}
        </div>

        {/* Inner determinate/indeterminate bar */}
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[--surface-3]">
          {pct === null ? (
            <div className="h-full w-1/3 animate-[cf-slide_1.4s_ease-in-out_infinite] rounded-full bg-[--primary]" />
          ) : (
            <div className="h-full rounded-full bg-[--primary] transition-all duration-500 ease-out" style={{ width: `${pct}%` }} />
          )}
        </div>

        {/* Current clip */}
        {currentPath && (
          <p className="mt-2 truncate text-xs text-[--text-muted]" title={currentPath}>{currentPath}</p>
        )}
      </div>
    </>
  )
}

// ── Main Jobs Panel ─────────────────────────────────────────────────

export interface JobsPanelProps {
  /** The active scan/reanalyze job id, or null if none running */
  activeJobId: number | null
}

export function JobsPanel({ activeJobId }: JobsPanelProps) {
  const { t } = useI18n()
  const { toasts, addToast } = useToast()
  const { events } = useJobEvents(activeJobId)

  // Toast on notable events.
  useEffect(() => {
    if (events.length === 0) return
    const last = events[events.length - 1] as JobEvent | undefined
    if (last?.type === 'job_started') {
      addToast('info', t('jobs.toastStarted'))
    } else if (last?.type === 'job_completed') {
      addToast('success', t('jobs.toastCompleted', { n: last.done as number }))
    } else if (last?.type === 'job_failed') {
      addToast('error', t('jobs.toastFailed'))
    }
  }, [events, addToast, t])

  if (!activeJobId && toasts.length === 0) return null

  return (
    <>
      <ScanProgress jobId={activeJobId} events={events} />

      {/* Toast notifications (bottom-right, above the progress card) */}
      <div className="fixed bottom-24 right-4 z-[100] flex flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`flex items-center gap-2 rounded-lg border px-4 py-3 text-sm shadow-xl ${
              toast.type === 'success' ? 'border-[--success]/30 bg-[--surface-1] text-[--text-primary]' :
              toast.type === 'error' ? 'border-[--error]/30 bg-[--surface-1] text-[--text-primary]' :
              'border-[--primary]/30 bg-[--surface-1] text-[--text-primary]'
            }`}
          >
            {toast.type === 'success' && (
              <svg className="h-4 w-4 shrink-0 text-[--success]" fill="none" viewBox="0 0 24 24">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            )}
            {toast.type === 'error' && (
              <svg className="h-4 w-4 shrink-0 text-[--error]" fill="none" viewBox="0 0 24 24">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
              </svg>
            )}
            <span className="flex-1">{toast.message}</span>
          </div>
        ))}
      </div>
    </>
  )
}
