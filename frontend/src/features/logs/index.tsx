/** Backend log viewer — full page that tails the server's in-memory log buffer.
 *
 * Polls GET /api/logs while visible (incrementally, via `after=<last_seq>`) so the
 * user can watch backend activity without tailing the terminal.
 *
 * Usage:
 *   <LogsPage onClose={() => setShowLogs(false)} />
 */

import { useEffect, useRef, useState } from 'react'

import type { LogEntry } from '@/api/client'
import { api } from '@/api/client'
import { useI18n } from '@/i18n'

const MAX_LINES = 2000

type FilterLevel = 'all' | 'info' | 'warn' | 'error' | 'scan'

function levelColor(level: string): string {
  switch (level) {
    case 'ERROR':
    case 'CRITICAL':
      return 'bg-[--error]/10 text-[--error]'
    case 'WARNING':
      return 'bg-[--warning]/10 text-[--warning]'
    case 'SCAN':
      return 'bg-[--success]/10 text-[--success]'
    case 'DEBUG':
      return 'bg-[--primary]/10 text-[--primary]'
    default:
      return 'bg-[--primary]/10 text-[--primary]'
  }
}

function formatTime(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleTimeString(undefined, { hour12: false })
}

function mapLogLevel(level: string): FilterLevel {
  const upper = level.toUpperCase()
  if (upper === 'WARNING' || upper === 'WARN') return 'warn'
  if (upper === 'ERROR' || upper === 'CRITICAL') return 'error'
  if (upper === 'SCAN') return 'scan'
  return 'info'
}

export interface LogsPageProps {
  onClose: () => void
  theme?: 'light' | 'dark'
  onToggleTheme?: () => void
}

export function LogsPage({ onClose, theme, onToggleTheme }: LogsPageProps) {
  const { t } = useI18n()
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [live, setLive] = useState(true)
  const [filter, setFilter] = useState<FilterLevel>('all')
  const afterRef = useRef(0)
  const bodyRef = useRef<HTMLDivElement>(null)

  // Reset the buffer each time the page mounts.
  useEffect(() => {
    afterRef.current = 0
    setLogs([])
    setLive(true)
  }, [])

  // Poll for new lines while visible + live (immediate tick, then every 1.5s).
  useEffect(() => {
    if (!live) return
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
  }, [live])

  // Keep the view pinned to the newest line while live.
  useEffect(() => {
    if (live && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [logs, live])

  // Esc closes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const filteredLogs = filter === 'all'
    ? logs
    : logs.filter((e) => mapLogLevel(e.level) === filter)

  const filters: Array<{ key: FilterLevel; label: string }> = [
    { key: 'all', label: t('logs.all') },
    { key: 'info', label: 'INFO' },
    { key: 'warn', label: 'WARN' },
    { key: 'error', label: 'ERROR' },
    { key: 'scan', label: t('logs.scan') },
  ]

  return (
    <div className="flex h-screen w-full flex-col">
      {/* ── Top Bar ─────────────────────────────────────────── */}
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-[--border] bg-[--surface-1] px-4">
        <button
          onClick={onClose}
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm font-medium text-[--text-secondary] transition-colors hover:bg-[--surface-3] hover:text-[--text-primary]"
        >
          <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
            <path d="M10 4L6 8l4 4" />
          </svg>
          {t('logs.back')}
        </button>
        <span className="text-lg font-semibold tracking-tight text-[--text-primary]">{t('logs.title')}</span>
        <span className="flex-1" />
        <button
          onClick={onToggleTheme}
          aria-label={theme === 'dark' ? t('app.themeToLight') : t('app.themeToDark')}
          className="flex h-8 w-8 items-center justify-center rounded-md text-[--text-secondary] transition-colors hover:bg-[--surface-3] hover:text-[--text-primary]"
        >
          {theme === 'dark' ? (
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
              <circle cx="8" cy="8" r="3" />
              <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.1 3.1l1.4 1.4M11.5 11.5l1.4 1.4M12.9 3.1l-1.4 1.4M4.5 11.5l-1.4 1.4" />
            </svg>
          ) : (
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
              <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7Z" />
            </svg>
          )}
        </button>
      </header>

      {/* ── Page Content ────────────────────────────────────── */}
      <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-4 overflow-auto p-6">

        {/* Toolbar */}
        <div className="flex shrink-0 items-center gap-2">
          {filters.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`h-8 rounded-md px-2.5 text-xs font-medium transition-colors ${
                filter === f.key
                  ? 'bg-[--primary] text-[--primary-fg]'
                  : 'border border-[--border] bg-[--surface-2] text-[--text-secondary] hover:bg-[--surface-3]'
              }`}
            >
              {f.label}
            </button>
          ))}
          <span className="flex-1" />
          <button
            onClick={() => { afterRef.current = 0; setLogs([]) }}
            className="h-8 rounded-md border border-[--border] bg-[--surface-2] px-2.5 text-xs font-medium text-[--text-muted] transition-colors hover:bg-[--surface-3] hover:text-[--text-secondary]"
          >
            {t('logs.clear')}
          </button>
        </div>

        {/* Live indicator */}
        <button
          onClick={() => setLive((v) => !v)}
          className="self-start rounded-md px-2.5 py-1 text-xs font-medium transition-colors"
          style={{ backgroundColor: live ? 'var(--primary)' : 'var(--surface-2)', color: live ? 'var(--primary-fg)' : 'var(--text-secondary)' }}
        >
          <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${live ? 'animate-pulse bg-[--primary-fg]' : 'bg-[--text-muted]'}`} />
          {live ? t('logs.live') : t('logs.paused')}
        </button>

        {/* Log Container */}
        <div className="flex-1 overflow-hidden rounded-lg border border-[--border] bg-[--surface-1]">
          <div ref={bodyRef} className="h-full overflow-auto">
            {filteredLogs.length === 0 ? (
              <div className="flex items-center justify-center py-12 text-sm text-[--text-muted]">
                {logs.length === 0 ? t('logs.empty') : t('logs.noMatch')}
              </div>
            ) : (
              filteredLogs.map((entry) => (
                <div key={entry.seq} className="flex gap-3 border-b border-[--border] px-4 py-2 font-mono text-xs leading-relaxed last:border-b-0">
                  <span className="shrink-0 text-[--text-muted]">{formatTime(entry.time)}</span>
                  <span className={`shrink-0 inline-flex items-center justify-center min-w-[48px] h-[18px] rounded px-1 text-xs font-semibold ${levelColor(entry.level)}`}>
                    {entry.level.toUpperCase()}
                  </span>
                  <span className="break-all text-[--text-secondary]">{entry.message}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
