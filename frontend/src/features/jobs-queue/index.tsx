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

// ── Label / badge maps ────────────────────────────────────────────

const KIND_LABELS: Record<string, string> = {
  scan: '扫描',
  reanalyze: '重新分析',
}

const STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  pending: '排队中',
  running: '进行中',
  done: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

const STATUS_BADGE: Record<string, string> = {
  queued: 'bg-[--surface-3] text-[--text-secondary]',
  pending: 'bg-[--surface-3] text-[--text-secondary]',
  running: 'bg-[--primary]/15 text-[--primary]',
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

function JobRow({ job, onChanged }: { job: JobStatus; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)

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

  return (
    <tr className="border-b border-[--border]">
      <td className="px-4 py-3 text-sm tabular-nums text-[--text-muted]">
        #{job.id}
      </td>
      <td className="px-4 py-3 text-sm text-[--text-primary]">
        {KIND_LABELS[job.kind ?? ''] ?? job.kind ?? '—'}
      </td>
      <td className="px-4 py-3">
        <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[job.status] ?? 'bg-[--surface-3] text-[--text-secondary]'}`}>
          {STATUS_LABELS[job.status] ?? job.status}
        </span>
      </td>
      <td className="px-4 py-3 text-sm tabular-nums text-[--text-secondary]">
        {job.done}/{job.total}
        {job.failed > 0 && (
          <span className="ml-2 text-[--error]">失败 {job.failed}</span>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-[--text-muted]">{formatTime(job.started_at)}</td>
      <td className="px-4 py-3 text-right">
        <div className="flex justify-end gap-2">
          {job.failed > 0 && (
            <Button size="sm" variant="secondary" onClick={handleRetry} disabled={busy}>
              重试失败项
            </Button>
          )}
          <Button size="sm" variant="danger" onClick={handleDelete} disabled={busy}>
            删除
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
        <h1 className="text-lg font-semibold tracking-tight">任务队列</h1>
        <div className="flex items-center gap-3">
          <Button variant="secondary" size="sm" onClick={handleTogglePause}>
            {paused ? '恢复' : '暂停'}
          </Button>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-[--text-secondary] hover:bg-[--surface-3] transition-colors"
            aria-label="关闭"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24">
              <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-6">
        {jobs.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-[--text-muted]">
            暂无任务
          </div>
        ) : (
          <table className="w-full border-collapse overflow-hidden rounded-lg border border-[--border] bg-[--surface-1]">
            <thead>
              <tr className="border-b border-[--border] text-left text-xs font-medium text-[--text-secondary]">
                <th className="px-4 py-2 w-16">ID</th>
                <th className="px-4 py-2">类型</th>
                <th className="px-4 py-2">状态</th>
                <th className="px-4 py-2">进度</th>
                <th className="px-4 py-2">开始时间</th>
                <th className="px-4 py-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <JobRow key={job.id} job={job} onChanged={refresh} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
