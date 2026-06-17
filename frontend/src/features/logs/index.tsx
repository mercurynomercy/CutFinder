/** Backend log viewer — a modal that tails the server's in-memory log buffer.
 *
 * Polls GET /api/logs while open (incrementally, via `after=<last_seq>`) so the
 * user can watch backend activity without tailing the terminal.
 *
 * Usage:
 *   <LogModal open={showLogs} onClose={() => setShowLogs(false)} />
 */

import { useEffect, useRef, useState } from 'react'

import type { LogEntry } from '@/api/client'
import { api } from '@/api/client'
import { useI18n } from '@/i18n'

const MAX_LINES = 2000

function levelColor(level: string): string {
  switch (level) {
    case 'ERROR':
    case 'CRITICAL':
      return 'text-[--error]'
    case 'WARNING':
      return 'text-[--warning]'
    case 'DEBUG':
      return 'text-[--text-muted]'
    default:
      return 'text-[--text-secondary]'
  }
}

function formatTime(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleTimeString(undefined, { hour12: false })
}

export interface LogModalProps {
  open: boolean
  onClose: () => void
}

export function LogModal({ open, onClose }: LogModalProps) {
  const { t } = useI18n()
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [live, setLive] = useState(true)
  const afterRef = useRef(0)
  const bodyRef = useRef<HTMLDivElement>(null)

  // Reset the buffer each time the modal opens (fetch starts from the top).
  useEffect(() => {
    if (open) {
      afterRef.current = 0
      setLogs([])
      setLive(true)
    }
  }, [open])

  // Poll for new lines while open + live (an immediate tick, then every 1.5s).
  useEffect(() => {
    if (!open || !live) return
    let cancelled = false

    const tick = async () => {
      try {
        const res = await api.getLogs(afterRef.current)
        if (cancelled || res.logs.length === 0) return
        afterRef.current = res.last_seq
        setLogs((prev) => {
          const merged = prev.concat(res.logs)
          return merged.length > MAX_LINES ? merged.slice(-MAX_LINES) : merged
        })
      } catch {
        // transient error — keep polling
      }
    }

    void tick()
    const id = setInterval(tick, 1500)
    return () => { cancelled = true; clearInterval(id) }
  }, [open, live])

  // Keep the view pinned to the newest line while live.
  useEffect(() => {
    if (live && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [logs, live])

  // Esc closes.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center p-6" role="dialog" aria-modal onClick={onClose}>
      <div className="absolute inset-0 bg-black/60" />

      <div
        className="relative flex max-h-[80vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-[--border] bg-[--surface-1] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-[--border] px-4 py-3">
          <h2 className="text-sm font-semibold text-[--text-primary]">{t('logs.title')}</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setLive((v) => !v)}
              className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                live ? 'bg-[--primary]/15 text-[--primary]' : 'bg-[--surface-2] text-[--text-secondary] hover:text-[--text-primary]'
              }`}
            >
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${live ? 'animate-pulse bg-[--primary]' : 'bg-[--text-muted]'}`} />
              {live ? t('logs.live') : t('logs.paused')}
            </button>
            <button
              onClick={() => { afterRef.current = 0; setLogs([]) }}
              className="rounded-md bg-[--surface-2] px-2.5 py-1 text-xs font-medium text-[--text-secondary] transition-colors hover:text-[--text-primary]"
            >
              {t('logs.clear')}
            </button>
            <button
              onClick={onClose}
              className="rounded-md p-1 text-[--text-muted] hover:text-[--text-primary]"
              aria-label={t('logs.close')}
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Body */}
        <div ref={bodyRef} className="min-h-0 flex-1 overflow-auto bg-[--bg-canvas] px-4 py-3 font-mono text-xs leading-relaxed">
          {logs.length === 0 ? (
            <p className="text-[--text-muted]">{t('logs.empty')}</p>
          ) : (
            logs.map((entry) => (
              <div key={entry.seq} className="flex gap-2 whitespace-pre-wrap break-all">
                <span className="shrink-0 tabular-nums text-[--text-muted]">{formatTime(entry.time)}</span>
                <span className={`shrink-0 ${levelColor(entry.level)}`}>{entry.level}</span>
                <span className="break-all text-[--text-primary]">{entry.message}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
