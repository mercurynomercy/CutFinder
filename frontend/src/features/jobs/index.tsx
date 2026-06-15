/** Jobs feature — top progress bar + per-clip task list with status icons, plus toast notifications.

Listens to SSE events via `useJobEvents` hook and displays:
- A 2px progress bar at the top of the screen (indeterminate when unknown, determinate otherwise)
- A collapsible task list showing each clip's processing status
- Toast notifications for job start/completion/failure events

Usage:
  <JobsPanel activeJobId={currentScanJobId} />
*/

import { useCallback, useEffect, useState } from 'react'

import type { JobEvent, JobStatus } from '@/api/client'
import { api, ApiError } from '@/api/client'
import { useJobEvents } from '@/api/sse'

// ── Toast notification types ───────────────────────────────────────

interface ToastItem {
  id: number
  type: 'info' | 'success' | 'error'
  message: string
}

let toastIdCounter = 0

function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  // Memoized so consumers can safely list addToast in effect deps without
  // triggering an infinite render loop.
  const addToast = useCallback((type: ToastItem['type'], message: string) => {
    const id = ++toastIdCounter
    setToasts((prev) => [...prev, { id, type, message }])

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 5000)

    return id
  }, [])

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return { toasts, addToast, removeToast } as const
}

// ── Progress bar (2px thin) ───────────────────────

interface ProgressBarProps {
  /** Current job id, or null if no active job */
  jobId: number | null
}

function ProgressBar({ jobId }: ProgressBarProps) {
  const [job, setJob] = useState<JobStatus | null>(null)

  // Use SSE events to show real-time progress (clip being processed, step info)
  const { events } = useJobEvents(jobId)

  // Poll job status every 2 seconds (fallback for total/done/failed counters)
  useEffect(() => {
    if (!jobId) return

    let cancelled = false

    const fetchStatus = () => {
      if (cancelled) return
      api.getJob(jobId).then(setJob).catch(() => {}) // silently fail, SSE will catch real changes
    }

    fetchStatus()
    const interval = setInterval(fetchStatus, 2000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [jobId])

  // Derive "currently processing" text from SSE events (last clip_started event)
  const currentClip = (() => {
    if (!events.length) return null
    // Find the latest clip_started event (not overridden by a later one)
    let last: JobEvent | null = null
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].type === 'clip_started' && events[i].path) {
        last = events[i]
        break
      }
    }
    return last?.path ?? null
  })()

  const progress = job && job.total > 0 ? Math.round((job.done / job.total) * 100) : undefined
  const isIndeterminate = progress === undefined

  // Determine display text priority: SSE step > polling counter > status
  const lastClipDone = [...events].reverse().find((e: JobEvent) => e.type === 'clip_done')
  const lastJobCompleted = events.find((e: JobEvent) => e.type === 'job_completed')

  if (lastJobCompleted || !events.length && (!job || !['pending', 'running'].includes(job.status))) return null
  if (events.length === 0 && (!job || !['pending', 'running'].includes(job.status))) return null

  const displayText = lastClipDone
    ? `Done: ${lastClipDone.path}`
    : currentClip
      ? currentClip.length > 50 ? `Processing: ${currentClip.slice(-48)}…` : `Processing: ${currentClip}`
      : job?.status ?? ''

  return (
    <div className="h-0.5 w-full bg-[--surface-2]">
      <div
        className={`h-full transition-all duration-500 ease-out ${isIndeterminate ? 'animate-[shimmer_2s_infinite]' : ''}`}
        style={{
          width: isIndeterminate ? undefined : `${progress}%`,
        }}
      >
        {!isIndeterminate && (
          <div className="h-full w-full bg-[--primary] transition-all" />
        )}
      </div>

      {isIndeterminate && (
        <style>{`
          @keyframes shimmer {
            0% { transform: translateX(-100%) }
            50%, 100% { transform: translateX(100%) }
          }
        `}</style>
      )}

      {/* Status text */}
      <div className="absolute right-4 top-0 flex items-center gap-2 pt-[6px] text-xs tabular-numbers">
        <span className="max-w-48 truncate text-[--text-muted]">{displayText}</span>
        {job && job.done > 0 && <span className="text-[--primary]">{job.done}/{job.total}</span>}
      </div>
    </div>
  )
}

// ── Per-clip task list item with status icons ───────────────

interface TaskItemProps {
  event: JobEvent
}

function statusIcon(type?: string) {
  switch (type) {
    case 'clip_done':
      return <svg className="h-3.5 w-3.5 text-[--success]" fill="none" viewBox="0 0 24 24">
        <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4.5 12.75l6 6 9-13.5" />
      </svg>
    case 'job_failed':
    case 'clip_error':
      return <svg className="h-3.5 w-3.5 text-[--error]" fill="none" viewBox="0 0 24 24">
        <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
      </svg>
    default:
      return <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-[--text-muted] border-t-transparent" />
  }
}

function TaskItem({ event }: TaskItemProps) {
  const clipId = (event.clip_id ?? '') as number | string // could be int or str
  const path = (event.path ?? event.source_path ?? `Clip #${clipId}`) as string

  return (
    <div className="flex items-center gap-3 py-1 text-xs">
      {statusIcon(event.type)}
      <span className="flex-1 truncate text-[--text-secondary]">{path}</span>
    </div>
  )
}

// ── Main Jobs Panel component (progress bar + task list) ────────

export interface JobsPanelProps {
  /** The active scan/reanalyze job id, or null if none running */
  activeJobId: number | null
}

export function JobsPanel({ activeJobId }: JobsPanelProps) {
  const [taskList, setTaskList] = useState<JobEvent[]>([])
  const { toasts, addToast } = useToast()

  // Subscribe to SSE events for the active job (task list + toast notifications)
  const { events } = useJobEvents(activeJobId)

  // Update task list and show toasts for notable events
  useEffect(() => {
    if (events.length === 0) return

    setTaskList((prev) => {
      // Merge events — avoid duplicates by type + clip_id
      const merged = [...prev]
      for (const event of events) {
        // Update progress on job_started / progress events
        if (event.type === 'job_started' || event.type === 'progress') {
          // progress events update the bar, not task list
        } else if (event.type === 'clip_done' || event.type === 'job_completed') {
          merged.push(event)
        } else if (event.type?.includes('error') || event.type === 'job_failed') {
          merged.push(event)
        } else if (event.type !== undefined && !merged.some((e: JobEvent) => e.clip_id === event.clip_id && e.type === event.type)) {
          merged.push(event)
        } else if (event.type !== undefined && !merged.some((e: JobEvent) => e.clip_id === event.clip_id)) {
          merged.push(event)
        }
      }

      return merged.slice(-20) // keep last 20 events for the task list
    })

    // Show toast for the most recent significant event.
    const lastEvent = events[events.length - 1] as JobEvent | undefined
    if (lastEvent?.type === 'job_started') {
      addToast('info', `Scan started — processing clips`)
    } else if (lastEvent?.type === 'job_completed') {
      addToast('success', `Scan completed — ${lastEvent.done} clips processed`)
    } else if (lastEvent?.type === 'job_failed') {
      addToast('error', `Scan failed — check logs for details`)
    }
  }, [events, addToast])

  // If no active job and no events to show, render nothing
  if (!activeJobId && taskList.length === 0) return null

  // If active job but no events yet, show just the progress bar
  if (events.length === 0) return <ProgressBar jobId={activeJobId} />

  // Show progress bar (via SSE + polling) and task list
  return (
    <div className="relative">
      {/* Progress bar from SSE + polling */}
      {activeJobId && <ProgressBar jobId={activeJobId} />}

      {/* Task list (collapsible) */}
      {taskList.length > 0 && (
        <div className="max-h-48 overflow-y-auto border-b border-[--border] bg-[--surface-1]/95 px-4 py-2">
          {taskList.map((event, i) => (
            <TaskItem key={`${(event.clip_id ?? '')}-${i}`} event={event} />
          ))}
        </div>
      )}

      {/* Toast notifications (absolute positioned, top-right) */}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
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
    </div>
  )
}
