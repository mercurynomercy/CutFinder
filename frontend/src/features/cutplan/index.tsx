/** Rough-cut director page (§3.15).
 *
 * Three-column layout: sidebar (conversation list) | chat panel | shot list.
 * Top bar with generation status pill, theme toggle, and close.
 *
 * On open it restores the last active conversation; if its turn is still running
 * in the backend it shows the "thinking" indicator and resumes polling.
 *
 * Usage: <CutplanPage onClose={() => ...} onOpenSettings={() => ...} theme={...} onToggleTheme={() => ...} />
 */

import { Fragment, useEffect, useRef, useState } from 'react'

import type { CutMessage, CutPlan, CutSession } from '@/api/client'
import { api } from '@/api/client'
import { useI18n } from '@/i18n'
import { ConfirmDialog } from '@/components'
import type { Theme } from '@/theme'

const ACTIVE_KEY = 'cutfinder:cut-active-session'

function fmtTimecode(s: number): string {
  const ms = Math.max(0, Math.round(s * 1000))
  const h = Math.floor(ms / 3_600_000)
  const m = Math.floor((ms % 3_600_000) / 60_000)
  const sec = Math.floor((ms % 60_000) / 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(h)}:${pad(m)}:${pad(sec)}`
}

function fmtDuration(s: number): string {
  const total = Math.round(Math.max(0, s))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const sec = total % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`
}

// Animated three-dot "thinking" indicator (uses currentColor so it inherits).
function ThinkingDots() {
  return (
    <span className="inline-flex items-center gap-1" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-current"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  )
}

// Mini spinner for active step
function MiniSpinner() {
  return (
    <span className="inline-block h-3 w-3 animate-spin rounded-full border-[1.5px] border-[--border] border-t-[--primary]" />
  )
}

export interface CutplanPageProps {
  onClose: () => void
  onOpenSettings: () => void
  theme: Theme
  onToggleTheme: () => void
}

export function CutplanPage({ onClose, onOpenSettings, theme, onToggleTheme }: CutplanPageProps) {
  const { t } = useI18n()
  const [sessions, setSessions] = useState<CutSession[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<CutMessage[]>([])
  const [plan, setPlan] = useState<CutPlan | null>(null)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  // Rolling trajectory of the director's recent steps (so the user can see what
  // it's thinking through, not just the latest line). Polling only gets the
  // latest string each tick; we append distinct ones to build the history.
  const [progressLog, setProgressLog] = useState<string[]>([])
  // Whether the progress trajectory is expanded. Open while a turn runs; collapses
  // once it finishes so the finished log sits quietly between the request and reply.
  const [progressOpen, setProgressOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [listCollapsed, setListCollapsed] = useState(false)
  const [planFullscreen, setPlanFullscreen] = useState(false)
  // Elapsed time tracking for generation
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [generationStarted, setGenerationStarted] = useState(false)
  // Real day-based progress from the backend (day_index/day_total), e.g. "day 2 of 5".
  const [dayIndex, setDayIndex] = useState<number | null>(null)
  const [dayTotal, setDayTotal] = useState<number | null>(null)

  const threadRef = useRef<HTMLDivElement>(null)
  const progressRef = useRef<HTMLDivElement>(null)
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Tracks the currently-open session so resume polling can bail if the user
  // switches away mid-poll. Set explicitly (not on render) so async guards see
  // the new value immediately.
  const activeRef = useRef<number | null>(null)

  // Append a new step to the trajectory, skipping blanks and adjacent repeats.
  const pushProgress = (p: string) =>
    setProgressLog((prev) => (!p || prev[prev.length - 1] === p ? prev : [...prev, p]))
  const lastProgress = progressLog[progressLog.length - 1] ?? ''
  const currentStepIndex = progressLog.length
  const dayPct = dayIndex != null && dayTotal ? Math.round((dayIndex / dayTotal) * 100) : null

  const persistActive = (id: number | null) => {
    try {
      if (id == null) localStorage.removeItem(ACTIVE_KEY)
      else localStorage.setItem(ACTIVE_KEY, String(id))
    } catch {
      /* ignore */
    }
  }

  const loadSessions = async (): Promise<CutSession[]> => {
    try {
      const { sessions } = await api.listCutSessions()
      setSessions(sessions)
      return sessions
    } catch {
      return []
    }
  }

  // Start elapsed time timer
  const startElapsedTimer = () => {
    setElapsedSeconds(0)
    setGenerationStarted(true)
    if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current)
    elapsedTimerRef.current = setInterval(() => {
      setElapsedSeconds((s) => s + 1)
    }, 1000)
  }

  // Stop elapsed time timer
  const stopElapsedTimer = () => {
    if (elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current)
      elapsedTimerRef.current = null
    }
    setGenerationStarted(false)
  }

  const fmtElapsed = (s: number): string => {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return m > 0 ? `${m}m${String(sec).padStart(2, '0')}s` : `${sec}s`
  }

  // Poll a still-running session until it goes idle/error, live-updating the
  // partial plan + the director's current step on every tick (so completed
  // dates and "查看片段 #N" status show while the rest still generates).
  const resumePoll = async (id: number) => {
    // Generous backstop: a multi-day 15–20 min vlog in agent mode can run a long
    // time. The real exit is status going non-running; this only stops us polling
    // a hung/dead backend forever.
    const deadline = Date.now() + 60 * 60_000
    while (Date.now() < deadline) {
      if (activeRef.current !== id) return // user switched away
      try {
        const detail = await api.getCutSession(id)
        if (activeRef.current !== id) return
        if (detail.plan) setPlan(detail.plan)          // show completed dates early
        pushProgress(detail.session.progress ?? '')     // live "正在查看…" trajectory
        setDayIndex(detail.session.day_index ?? null)
        setDayTotal(detail.session.day_total ?? null)
        if (detail.session.status !== 'running') {
          setMessages(detail.messages)                  // restore the assistant reply
          setPlan(detail.plan)
          setBusy(false)
          setProgressOpen(false)                        // collapse the finished log
          setDayIndex(null); setDayTotal(null)
          stopElapsedTimer()
          return                                        // keep progressLog for review
        }
      } catch {
        /* transient — keep polling */
      }
      await new Promise((r) => setTimeout(r, 1500))
    }
    // Deadline reached: do one final sync so a turn that finished right at the
    // boundary still shows its reply instead of silently vanishing.
    if (activeRef.current === id) {
      try {
        const detail = await api.getCutSession(id)
        if (activeRef.current === id) {
          setMessages(detail.messages)
          if (detail.plan) setPlan(detail.plan)
        }
      } catch {
        /* ignore */
      }
      setBusy(false)
      setProgressOpen(false)
      stopElapsedTimer()
    }
  }

  // Open a session: load its messages + plan, and if its turn is still running
  // in the backend, show the thinking state and resume polling until it ends.
  const openSession = async (id: number) => {
    activeRef.current = id // sync now so the guard below doesn't wait for a render
    setActiveId(id)
    persistActive(id)
    setPlan(null)
    setMessages([])
    setBusy(false)
    setProgressLog([])
    setDayIndex(null); setDayTotal(null)
    stopElapsedTimer()
    try {
      const detail = await api.getCutSession(id)
      if (activeRef.current !== id) return
      setMessages(detail.messages)
      setPlan(detail.plan)
      if (detail.session.status === 'running') {
        pushProgress(detail.session.progress ?? '')
        setBusy(true)
        setProgressOpen(true)
        void resumePoll(id)
      }
    } catch {
      setMessages([])
      setPlan(null)
    }
  }

  // On mount: restore the last active conversation (or the most recent one).
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const list = await loadSessions()
      if (cancelled || list.length === 0) return
      let savedId: number | null = null
      try {
        const raw = localStorage.getItem(ACTIVE_KEY)
        savedId = raw ? Number(raw) : null
      } catch {
        /* ignore */
      }
      const target = list.find((s) => s.id === savedId) ?? list[0]
      if (target) await openSession(target.id)
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight
  }, [messages, busy])

  // Tail the progress log to its latest line while a turn runs; once it stops the
  // user is free to scroll up through the full trajectory.
  useEffect(() => {
    if (busy && progressOpen && progressRef.current) {
      progressRef.current.scrollTop = progressRef.current.scrollHeight
    }
  }, [progressLog, busy, progressOpen])

  // Update the tab title with day progress while generating, so it's visible
  // even when the user has switched away from this tab.
  useEffect(() => {
    const base = document.title.replace(/^\(\d+\/\d+\)\s*/, '')
    if (busy && dayIndex != null && dayTotal != null) {
      document.title = `(${dayIndex}/${dayTotal}) ${base}`
    } else {
      document.title = base
    }
    return () => {
      document.title = document.title.replace(/^\(\d+\/\d+\)\s*/, '')
    }
  }, [busy, dayIndex, dayTotal])

  const newSession = async () => {
    const s = await api.createCutSession('')
    await loadSessions()
    await openSession(s.id)
  }

  const send = async () => {
    const text = input.trim()
    if (!text || busy) return

    let sessionId = activeId
    if (sessionId == null) {
      const s = await api.createCutSession(text.slice(0, 24))
      sessionId = s.id
      activeRef.current = sessionId
      setActiveId(sessionId)
      persistActive(sessionId)
      await loadSessions()
    }

    // Optimistically show the user's message.
    setMessages((prev) => [...prev, { role: 'user', content: text, created_at: null }])
    setInput('')
    setBusy(true)
    setProgressLog([])
    setDayIndex(null); setDayTotal(null)
    setProgressOpen(true)
    startElapsedTimer()
    try {
      // The route marks the session 'running' synchronously, so we can poll the
      // session directly — resumePoll live-updates the partial plan + progress
      // and finalizes when it goes idle/error.
      await api.sendCutMessage(sessionId, text)
      await resumePoll(sessionId)
      await loadSessions() // refresh title / updated_at ordering
    } catch (err) {
      console.error('Rough-cut turn failed:', err)
    } finally {
      setBusy(false)
      // Keep progressLog so the finished run's trajectory stays visible; it's
      // cleared when the next turn starts (above) or another session is opened.
    }
  }

  const doDelete = async (id: number) => {
    setConfirmDeleteId(null)
    try {
      await api.deleteCutSession(id)
    } catch (err) {
      console.error('Delete conversation failed:', err)
    }
    const remaining = await loadSessions()
    if (activeId === id) {
      setActiveId(null)
      persistActive(null)
      setMessages([])
      setPlan(null)
      if (remaining.length) await openSession(remaining[0].id)
    }
  }

  const copyMarkdown = async () => {
    if (!plan?.markdown) return
    try {
      await navigator.clipboard.writeText(plan.markdown)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable */
    }
  }

  const cancelGeneration = () => {
    // The backend has no turn-cancel endpoint, so the turn keeps running there.
    // Detach from it the same way switching sessions does — activeRef is the
    // guard resumePoll checks before every tick, so this stops the next poll
    // from repopulating progressLog/plan out from under the cleared panel.
    activeRef.current = null
    setBusy(false)
    setProgressLog([])
    setDayIndex(null); setDayTotal(null)
    stopElapsedTimer()
  }

  // The progress trajectory belongs to the latest turn: while it runs it trails
  // the last (user) message; once the assistant reply lands it sits *between* the
  // request and that reply (anchored just before the trailing assistant message),
  // collapsed by default.
  const showProgress = busy || progressLog.length > 0
  const lastIsAssistant = messages.length > 0 && messages[messages.length - 1].role === 'assistant'
  const progressAnchor = !busy && lastIsAssistant ? messages.length - 1 : messages.length

  // Generation process panel node
  const progressNode = (
    <div className="text-left">
      <div className="inline-flex max-w-full flex-col gap-1 rounded-lg border border-[--border] bg-[--surface-1] px-3 py-2 text-sm text-[--text-secondary] shadow-[var(--shadow-2)]">
        {/* Header — clickable to toggle steps */}
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => setProgressOpen((v) => !v)}
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-[--text-secondary] hover:text-[--text-primary]"
          >
            {busy && <span className="h-1.5 w-1.5 rounded-full bg-[--primary] animate-pulse" />}
            <span>{t('roughcut.generatingSteps', { n: progressLog.length })}</span>
          </button>
          {busy && (
            <button
              type="button"
              onClick={cancelGeneration}
              className="h-5 rounded px-2 text-[10px] font-medium text-[--text-muted] hover:bg-[--surface-3] hover:text-[--error]"
            >
              {t('roughcut.cancel')}
            </button>
          )}
        </div>

        {/* Current step line — always visible */}
        <div className="flex items-baseline gap-2 border-t border-[--border] pt-2">
          <span className="flex-1 min-w-0 truncate text-xs text-[--text-secondary]">
            {busy && progressLog.length > 0 ? lastProgress : (busy ? t('roughcut.thinking') : '完成')}
          </span>
          {generationStarted && (
            <span className="font-mono text-[10px] text-[--text-muted] shrink-0">
              {fmtElapsed(elapsedSeconds)}
            </span>
          )}
        </div>

        {/* Steps list — collapsible */}
        {progressOpen && (
          <div ref={progressRef} className="mt-1 flex max-h-48 flex-col gap-1 overflow-y-auto">
            {progressLog.length === 0 && busy ? (
              <div className="flex items-center gap-2 text-xs text-[--text-muted]">
                <ThinkingDots />
                <span>{t('roughcut.thinking')}</span>
              </div>
            ) : (
              progressLog.map((p, i) => {
                const isLast = i === progressLog.length - 1
                const isDone = !busy || !isLast
                return (
                  <div
                    key={`${i}-${p}`}
                    className={`flex items-start gap-2 text-xs leading-relaxed py-1 ${
                      isDone ? 'text-[--text-muted]' : 'text-[--text-secondary]'
                    }`}
                  >
                    <span className="w-4 shrink-0 flex items-center justify-center mt-0.5">
                      {isDone ? (
                        <span className="text-[--success]">
                          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M2.5 6.5L4.5 8.5L9.5 3.5" />
                          </svg>
                        </span>
                      ) : busy ? (
                        <MiniSpinner />
                      ) : (
                        <span className="text-[--text-muted]">·</span>
                      )}
                    </span>
                    <span>{p}</span>
                  </div>
                )
              })
            )}
          </div>
        )}

        {/* Progress bar footer — indeterminate: the director doesn't report a
            known step total, so this shows activity rather than a fake percent */}
        {busy && (
          <div className="flex items-center gap-2 pt-1">
            <div className="h-[3px] flex-1 overflow-hidden rounded-full bg-[--surface-3]">
              <div className="h-full w-1/3 animate-[cf-slide_1.4s_ease-in-out_infinite] rounded-full bg-[--primary]" />
            </div>
            <span className="font-mono text-[10px] text-[--text-muted]">
              {currentStepIndex}
            </span>
            <style>{`@keyframes cf-slide{0%{transform:translateX(-120%)}100%{transform:translateX(420%)}}`}</style>
          </div>
        )}
      </div>
    </div>
  )

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-[--bg-canvas] text-[--text-primary]">
      {/* ── Top Bar ── */}
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-[--border] bg-[--surface-1] px-4 z-50">
        <h1 className="text-base font-semibold tracking-tight">{t('roughcut.title')}</h1>

        {/* Generation status pill */}
        {busy && (
          <div className="flex h-[26px] items-center gap-1.5 rounded-full bg-[--primary-soft] px-2.5 pl-1 animate-[status-fade-in_200ms_ease]" role="status" aria-live="polite">
            <span className="h-[15px] w-[15px] shrink-0" aria-hidden="true">
              <svg viewBox="0 0 16 16" className="h-full w-full" style={{ transform: 'rotate(-90deg)' }}>
                <circle cx="8" cy="8" r="7" fill="none" stroke="var(--primary-soft)" strokeWidth="2.5" />
                <circle
                  cx="8" cy="8" r="7" fill="none" stroke="var(--primary)" strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeDasharray="44"
                  strokeDashoffset={dayPct != null ? 44 * (1 - dayPct / 100) : 11}
                  className={dayPct == null ? 'animate-spin' : undefined}
                  style={dayPct != null ? { transition: 'stroke-dashoffset 400ms ease' } : undefined}
                />
              </svg>
            </span>
            <span className="text-[10px] font-semibold text-[--primary] font-variant-numeric-tabular-nums whitespace-nowrap">
              {dayIndex != null && dayTotal != null
                ? t('roughcut.generatingDay', { idx: String(dayIndex), n: String(dayTotal) })
                : t('roughcut.generating', { n: String(currentStepIndex) })}
            </span>
          </div>
        )}

        <span className="flex-1" />

        <div className="flex items-center gap-1">
          {/* Theme toggle */}
          <button
            type="button"
            onClick={onToggleTheme}
            className="flex h-8 w-8 items-center justify-center rounded text-[--text-secondary] hover:bg-[--surface-3] hover:text-[--text-primary]"
            aria-label={theme === 'dark' ? t('app.themeToLight') : t('app.themeToDark')}
          >
            {theme === 'dark' ? (
              <svg className="h-5 w-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <circle cx="8" cy="8" r="3" />
                <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.1 3.1l1.4 1.4M11.5 11.5l1.4 1.4M12.9 3.1l-1.4 1.4M4.5 11.5l-1.4 1.4" />
              </svg>
            ) : (
              <svg className="h-5 w-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7Z" />
              </svg>
            )}
          </button>

          {/* Close button */}
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded text-[--text-secondary] hover:bg-[--surface-3] hover:text-[--text-primary]"
            aria-label={t('roughcut.close')}
          >
            <svg className="h-5 w-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M4 4l8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>
      </header>

      {/* ── Main 3-Column ── */}
      <div className="flex flex-1 overflow-hidden">
        {/* ── Column 1: Sidebar ── */}
        {listCollapsed ? (
          <aside className="flex w-10 shrink-0 flex-col items-center bg-[--surface-1] border-r border-[--border] py-2">
            <button
              onClick={() => setListCollapsed(false)}
              aria-label={t('roughcut.expandList')}
              title={t('roughcut.expandList')}
              className="rounded-md p-1.5 text-[--text-muted] hover:bg-[--surface-3]"
            >
              <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M10 4L6 8l4 4" />
              </svg>
            </button>
          </aside>
        ) : (
          <aside className="flex w-[220px] shrink-0 flex-col bg-[--surface-1] border-r border-[--border]">
            <div className="flex items-center p-3">
              <button
                onClick={newSession}
                className="flex flex-1 h-[30px] items-center justify-center gap-1 text-sm font-medium bg-[--primary] text-[--primary-fg] rounded-md hover:bg-[--primary-hover]"
              >
                <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                  <path d="M6 2v8M2 6h8" />
                </svg>
                {t('roughcut.newSession')}
              </button>
              <button
                onClick={() => setListCollapsed(true)}
                aria-label={t('roughcut.collapseList')}
                title={t('roughcut.collapseList')}
                className="flex h-7 w-7 items-center justify-center rounded text-[--text-muted] hover:bg-[--surface-3] ml-2"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <path d="M10 4L6 8l4 4" />
                </svg>
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-2">
              {sessions.length === 0 ? (
                <p className="px-2 py-4 text-xs text-[--text-muted]">{t('roughcut.noSessions')}</p>
              ) : (
                sessions.map((s) => (
                  <div key={s.id} className="group relative">
                    <div
                      className={`flex items-center rounded-md px-2.5 py-2 text-sm cursor-pointer transition-colors ${
                        s.id === activeId
                          ? 'bg-[--primary-soft] text-[--primary] font-medium'
                          : 'text-[--text-secondary] hover:bg-[--surface-3] hover:text-[--text-primary]'
                      }`}
                      onClick={() => openSession(s.id)}
                    >
                      <span className="truncate">{s.title || <span className="italic text-[--text-muted]">{t('roughcut.untitled')}</span>}</span>
                    </div>
                    <button
                      onClick={() => setConfirmDeleteId(s.id)}
                      aria-label={t('roughcut.deleteSession')}
                      title={t('roughcut.deleteSession')}
                      className="absolute right-1 top-1/2 -translate-y-1/2 rounded p-1 text-[--text-muted] hover:text-[--error] opacity-0 group-hover:opacity-100"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                        <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M6 7h12M9 7V5h6v2m-7 0 .8 12a1 1 0 0 0 1 1h4.4a1 1 0 0 0 1-1L16 7" />
                      </svg>
                    </button>
                  </div>
                ))
              )}
            </div>
          </aside>
        )}

        {/* ── Column 2: Chat ── */}
        <div className="flex w-[420px] shrink-0 flex-col bg-[--bg-canvas] border-r border-[--border]">
          <div ref={threadRef} className="min-h-0 flex-1 overflow-y-auto p-4">
            {messages.length === 0 && !showProgress ? (
              <p className="text-sm text-[--text-muted]">{t('roughcut.emptyConvo')}</p>
            ) : (
              <>
                {messages.map((m, i) => (
                  <Fragment key={i}>
                    {showProgress && i === progressAnchor && progressNode}
                    <div className={m.role === 'user' ? 'text-right' : 'text-left'}>
                      <div
                        className={`inline-block max-w-[90%] break-words rounded-lg px-4 py-2.5 text-sm leading-relaxed ${
                          m.role === 'user'
                            ? 'bg-[--primary] text-[--primary-fg] rounded-br-sm'
                            : 'bg-[--surface-1] border border-[--border] rounded-bl-sm'
                        }`}
                      >
                        {m.content}
                      </div>
                    </div>
                  </Fragment>
                ))}
                {showProgress && progressAnchor >= messages.length && progressNode}
              </>
            )}
          </div>

          {/* Chat Input */}
          <div className="shrink-0 border-t border-[--border] bg-[--surface-1] p-3">
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <textarea
                  ref={(el) => {
                    if (el) {
                      el.style.height = 'auto'
                      el.style.height = Math.min(el.scrollHeight, 120) + 'px'
                    }
                  }}
                  value={input}
                  onChange={(e) => {
                    setInput(e.target.value)
                    // Auto-resize
                    if (e.target) {
                      e.target.style.height = 'auto'
                      e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault()
                      send()
                    }
                  }}
                  rows={1}
                  placeholder={t('roughcut.placeholder')}
                  className="w-full min-h-[36px] max-h-[120px] resize-none rounded-md border border-[--border] bg-[--surface-2] px-3 py-2 text-sm text-[--text-primary] outline-none placeholder:text-[--text-muted] focus:border-[--primary] focus:shadow-[0_0_0_2px_var(--primary-soft)] transition-[border-color,box-shadow]"
                />
                <div className="mt-1.5 flex gap-1">
                  <button
                    onClick={onOpenSettings}
                    aria-label={t('roughcut.promptSettings')}
                    title={t('roughcut.promptSettings')}
                    className="flex h-[26px] items-center gap-1 rounded-md border border-[--border] bg-[--surface-2] px-2 text-[10px] font-medium text-[--text-secondary] hover:bg-[--surface-3]"
                  >
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.49l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
                      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    {t('roughcut.promptSettings')}
                  </button>
                </div>
              </div>
              <button
                onClick={send}
                disabled={busy || !input.trim()}
                className="flex h-9 shrink-0 items-center justify-center rounded-md bg-[--primary] px-4 text-sm font-semibold text-[--primary-fg] hover:bg-[--primary-hover] disabled:opacity-40 disabled:cursor-not-allowed transition-[background,opacity]"
              >
                {t('roughcut.send')}
              </button>
            </div>
          </div>
        </div>

        {/* ── Column 3: Shot Panel ── */}
        <div className="flex flex-1 flex-col overflow-hidden bg-[--bg-canvas]">
          <div className="relative flex h-11 shrink-0 items-center justify-between border-b border-[--border] bg-[--surface-1] px-5">
            <span className="text-sm font-semibold">{t('roughcut.planTitle')}</span>
            <div className="flex items-center gap-1">
              {plan && (
                <button
                  onClick={copyMarkdown}
                  className="flex h-7 items-center gap-1 rounded-md border border-[--border] bg-[--surface-2] px-2 text-[10px] font-medium text-[--text-secondary] hover:bg-[--surface-3]"
                >
                  <svg className="h-3 w-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                    <rect x="5" y="5" width="9" height="9" rx="1.5" />
                    <path d="M11 5V3.5A1.5 1.5 0 0 0 9.5 2h-6A1.5 1.5 0 0 0 2 3.5v6A1.5 1.5 0 0 0 3.5 11H5" />
                  </svg>
                  {copied ? t('roughcut.copied') : t('roughcut.copyMarkdown')}
                </button>
              )}
              <button
                onClick={() => setPlanFullscreen(true)}
                aria-label={t('roughcut.fullscreen')}
                title={t('roughcut.fullscreen')}
                className="flex h-7 items-center justify-center rounded-md border border-[--border] bg-[--surface-2] p-1 text-[--text-secondary] hover:bg-[--surface-3]"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                  <path d="M10 2h4v4M14 2L8 8M2 6v8a1 1 0 0 0 1 1h8" />
                </svg>
              </button>
            </div>
            {/* Progress bar on header bottom edge */}
            <div className={`absolute left-0 right-0 bottom-0 h-0.5 overflow-hidden bg-[--surface-3] transition-opacity ${busy ? 'opacity-100' : 'opacity-0'}`}>
              <div
                className="h-full bg-[--primary] transition-[width] duration-500"
                style={{ width: busy ? '60%' : '0%' }}
              />
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-5">
            {!plan ? (
              <p className="text-sm text-[--text-muted]">{t('roughcut.noPlan')}</p>
            ) : (
              <>
                {busy && (
                  <div className="mb-3 flex items-center gap-2 rounded-md bg-[--surface-2] px-3 py-2 text-xs text-[--text-secondary]">
                    <ThinkingDots />
                    <span>{lastProgress || t('roughcut.partialGenerating')}</span>
                  </div>
                )}
                <ShotList plan={plan} />
              </>
            )}
          </div>
        </div>
      </div>

      {/* Fullscreen shot list overlay */}
      {planFullscreen && (
        <div className="fixed inset-0 z-50 flex flex-col bg-[--bg-canvas]">
          <div className="flex h-12 shrink-0 items-center justify-between border-b border-[--border] bg-[--surface-1] px-6">
            <span className="text-sm font-semibold">{t('roughcut.planTitle')}</span>
            <div className="flex items-center gap-2">
              {plan && (
                <button
                  onClick={copyMarkdown}
                  className="rounded border border-[--border] px-2 py-1 text-xs text-[--text-secondary] hover:bg-[--surface-3]"
                >
                  {copied ? t('roughcut.copied') : t('roughcut.copyMarkdown')}
                </button>
              )}
              <button
                onClick={() => setPlanFullscreen(false)}
                className="rounded-md border border-[--border] px-3 py-1.5 text-sm text-[--text-secondary] hover:bg-[--surface-3]"
              >
                {t('roughcut.exitFullscreen')}
              </button>
            </div>
          </div>
          <div className="mx-auto min-h-0 w-full max-w-5xl flex-1 overflow-y-auto p-6">
            {plan ? <ShotList plan={plan} /> : <p className="text-sm text-[--text-muted]">{t('roughcut.noPlan')}</p>}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmDeleteId !== null}
        title={t('roughcut.deleteSession')}
        message={t('roughcut.deleteConfirm')}
        onConfirm={() => confirmDeleteId !== null && doDelete(confirmDeleteId)}
        onCancel={() => setConfirmDeleteId(null)}
      />
    </div>
  )
}

function ShotList({ plan }: { plan: CutPlan }) {
  const { t } = useI18n()

  // Group shots by date (clip_date)
  const dateGroups: Record<string, typeof plan.shots> = {}
  plan.shots.forEach((shot) => {
    const date = shot.clip_date || '__unknown__'
    if (!dateGroups[date]) dateGroups[date] = []
    dateGroups[date].push(shot)
  })

  // Sort dates chronologically
  const sortedDates = Object.keys(dateGroups).sort()

  let index = 0
  return (
    <div className="space-y-5" data-testid="shot-list">
      {sortedDates.map((date) => {
        const shots = dateGroups[date]
        if (!shots.length) return null
        return (
          <div key={date}>
            <h3 className="mb-2 border-b border-[--border] pb-2 text-sm font-semibold text-[--text-secondary]">
              {date}
            </h3>
            <div className="space-y-2">
              {shots.map((s) => {
                index += 1
                return (
                  <div
                    key={`${date}-${index}`}
                    className="flex gap-3 rounded-md border border-[--border] bg-[--surface-1] p-3 transition-shadow hover:shadow-[var(--shadow-1)]"
                  >
                    {/* Left: number + type dot */}
                    <div className="flex flex-col items-center gap-1 shrink-0">
                      <span className="font-mono text-[10px] text-[--text-muted]">{index}</span>
                      <span
                        className={`flex h-5 w-5 items-center justify-center rounded text-[10px] font-bold text-white ${
                          s.roll === 'a' ? 'bg-[--roll-a]' : s.roll === 'b' ? 'bg-[--roll-b]' : s.roll === 'photo' ? 'bg-[--roll-photo]' : 'bg-gray-400'
                        }`}
                      >
                        {s.roll === 'a' ? 'A' : s.roll === 'b' ? 'B' : s.roll === 'photo' ? t('card.photo') : s.roll?.[0]?.toUpperCase()}
                      </span>
                    </div>

                    {/* Thumbnail */}
                    <button
                      type="button"
                      onClick={() => {
                        if (s.clip_path) api.openPath(s.clip_path).catch((err) => console.error('Failed to open path:', err))
                      }}
                      className={`flex flex-col items-center gap-0.5 shrink-0 ${s.clip_path ? 'cursor-pointer' : ''}`}
                    >
                      <div className="h-[68px] w-[120px] overflow-hidden rounded bg-[--surface-2]">
                        {s.thumb_ref ? (
                          <img src={s.thumb_ref} alt="" className="h-full w-full object-cover" />
                        ) : (
                          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-[--surface-2] to-[--surface-3]">
                            <svg className="h-5 w-5 text-[--text-muted] opacity-30" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1" aria-hidden="true">
                              <rect x="2" y="2" width="12" height="12" rx="2" />
                              <circle cx="6.5" cy="6" r="1.2" />
                              <path d="M2 11l3.5-3L8 10.5 10.5 8.5 14 11" />
                            </svg>
                          </div>
                        )}
                      </div>
                      <span className="max-w-[120px] truncate text-center font-mono text-[10px] text-[--text-muted]">
                        {s.clip_label || ''}
                      </span>
                    </button>

                    {/* Info */}
                    <div className="min-w-0 flex-1">
                      <span className="font-mono text-[10px] font-medium text-[--text-secondary]">
                        {fmtTimecode(s.in_s)} – {fmtTimecode(s.out_s)}
                      </span>
                      {s.content && (
                        <p className="text-sm font-semibold leading-relaxed mt-1">
                          <span className={`text-[10px] font-medium mr-1 ${
                            s.roll === 'a' ? 'text-[--roll-a]' : s.roll === 'b' ? 'text-[--roll-b]' : ''
                          }`}>
                            [{s.roll === 'a' ? 'A-roll' : s.roll === 'b' ? 'B-roll' : s.roll === 'photo' ? t('card.photo') : s.roll}]
                          </span>
                          {s.content}
                        </p>
                      )}
                      {s.rationale && (
                        <p className="text-[10px] leading-relaxed text-[--text-secondary] mt-1">
                          {s.rationale}
                        </p>
                      )}
                      {s.clip_path && (
                        <p className="font-mono text-[10px] text-[--text-muted] mt-1">
                          File: {s.clip_label || s.clip_path.split('/').pop()}
                        </p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}

      {/* Duration summary */}
      <div className={`text-sm font-medium ${plan.within_target ? 'text-[--text-secondary]' : 'text-[--error]'}`}>
        {`总时长：${fmtDuration(plan.total_s)}`}
        {plan.target_min_s != null && plan.target_max_s != null &&
          `（目标 ${fmtDuration(plan.target_min_s)}–${fmtDuration(plan.target_max_s)} ${plan.within_target ? '✓' : '⚠️'}）`}
        {plan.target_min_s != null && plan.target_max_s != null && !plan.within_target &&
          ` ${t('roughcut.durationFootageHint')}`}
      </div>
    </div>
  )
}

export default CutplanPage
