/** Rough-cut director page (§3.15).
 *
 * Left: collapsible conversation list (new / delete) + chat thread + input.
 * Right: live shot list preview (chapters + thumbnails), expandable to full screen.
 *
 * On open it restores the last active conversation; if its turn is still running
 * in the backend it shows the "thinking" indicator and resumes polling.
 *
 * Usage: <CutplanPage onClose={() => ...} />
 */

import { useEffect, useRef, useState } from 'react'

import type { CutMessage, CutPlan, CutSession } from '@/api/client'
import { api } from '@/api/client'
import { useI18n } from '@/i18n'
import { ConfirmDialog } from '@/components'

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

export interface CutplanPageProps {
  onClose: () => void
}

export function CutplanPage({ onClose }: CutplanPageProps) {
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
  const [copied, setCopied] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [listCollapsed, setListCollapsed] = useState(false)
  const [planFullscreen, setPlanFullscreen] = useState(false)
  const [promptOpen, setPromptOpen] = useState(false)
  const [promptText, setPromptText] = useState('')
  const [promptDefault, setPromptDefault] = useState('')
  const [promptIsDefault, setPromptIsDefault] = useState(true)
  const [promptSaved, setPromptSaved] = useState(false)

  const threadRef = useRef<HTMLDivElement>(null)
  // Tracks the currently-open session so resume polling can bail if the user
  // switches away mid-poll. Set explicitly (not on render) so async guards see
  // the new value immediately.
  const activeRef = useRef<number | null>(null)

  // Append a new step to the trajectory, skipping blanks and adjacent repeats.
  const pushProgress = (p: string) =>
    setProgressLog((prev) => (!p || prev[prev.length - 1] === p ? prev : [...prev, p]))
  const lastProgress = progressLog[progressLog.length - 1] ?? ''

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

  // Poll a still-running session until it goes idle/error, live-updating the
  // partial plan + the director's current step on every tick (so completed
  // dates and "查看片段 #N" status show while the rest still generates).
  const resumePoll = async (id: number) => {
    const deadline = Date.now() + 10 * 60_000
    while (Date.now() < deadline) {
      if (activeRef.current !== id) return // user switched away
      try {
        const detail = await api.getCutSession(id)
        if (activeRef.current !== id) return
        if (detail.plan) setPlan(detail.plan)          // show completed dates early
        pushProgress(detail.session.progress ?? '')     // live "正在查看…" trajectory
        if (detail.session.status !== 'running') {
          setMessages(detail.messages)
          setPlan(detail.plan)
          setProgressLog([])
          setBusy(false)
          return
        }
      } catch {
        /* transient — keep polling */
      }
      await new Promise((r) => setTimeout(r, 1500))
    }
    if (activeRef.current === id) {
      setBusy(false)
      setProgressLog([])
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
    try {
      const detail = await api.getCutSession(id)
      if (activeRef.current !== id) return
      setMessages(detail.messages)
      setPlan(detail.plan)
      if (detail.session.status === 'running') {
        pushProgress(detail.session.progress ?? '')
        setBusy(true)
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
    try {
      // The route marks the session 'running' synchronously, so we can poll the
      // session directly — resumePoll live-updates the partial plan + progress
      // and finalizes when it goes idle/error.
      await api.sendCutMessage(sessionId, text)
      await resumePoll(sessionId)
      await loadSessions() // refresh titles / updated_at ordering
    } catch (err) {
      console.error('Rough-cut turn failed:', err)
    } finally {
      setBusy(false)
      setProgressLog([])
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

  const openPrompt = async () => {
    setPromptOpen(true)
    try {
      const r = await api.getCutPrompt()
      setPromptText(r.prompt)
      setPromptDefault(r.default)
      setPromptIsDefault(r.is_default)
    } catch (err) {
      console.error('Load director prompt failed:', err)
    }
  }

  const savePrompt = async () => {
    try {
      const r = await api.setCutPrompt(promptText)
      setPromptText(r.prompt)
      setPromptIsDefault(r.is_default)
      setPromptSaved(true)
      setTimeout(() => setPromptSaved(false), 1500)
    } catch (err) {
      console.error('Save director prompt failed:', err)
    }
  }

  const resetPrompt = async () => {
    try {
      const r = await api.resetCutPrompt()
      setPromptText(r.prompt)
      setPromptIsDefault(r.is_default)
    } catch (err) {
      console.error('Reset director prompt failed:', err)
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

  return (
    <div className="flex h-screen w-full flex-col bg-[--bg-canvas] text-[--text-primary]">
      {/* Header */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-[--border] bg-[--surface-1] px-6">
        <h1 className="text-sm font-semibold">{t('roughcut.title')}</h1>
        <button
          onClick={onClose}
          className="rounded-md border border-[--border] px-3 py-1.5 text-sm text-[--text-secondary] hover:bg-[--surface-3]"
        >
          {t('roughcut.close')}
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* Sessions sidebar (collapsible) */}
        {listCollapsed ? (
          <aside className="flex w-10 shrink-0 flex-col items-center border-r border-[--border] bg-[--surface-1] py-2">
            <button
              onClick={() => setListCollapsed(false)}
              aria-label={t('roughcut.expandList')}
              title={t('roughcut.expandList')}
              className="rounded-md p-1.5 text-[--text-secondary] hover:bg-[--surface-3]"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </aside>
        ) : (
          <aside className="flex w-56 shrink-0 flex-col border-r border-[--border] bg-[--surface-1]">
            <div className="flex items-center gap-1 p-2">
              <button
                onClick={newSession}
                className="flex-1 rounded-md bg-[--primary] px-3 py-2 text-sm font-medium text-white hover:bg-[--primary]/90"
              >
                + {t('roughcut.newSession')}
              </button>
              <button
                onClick={() => setListCollapsed(true)}
                aria-label={t('roughcut.collapseList')}
                title={t('roughcut.collapseList')}
                className="rounded-md p-1.5 text-[--text-secondary] hover:bg-[--surface-3]"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15 5l-7 7 7 7" />
                </svg>
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
              {sessions.length === 0 ? (
                <p className="px-2 py-4 text-xs text-[--text-muted]">{t('roughcut.noSessions')}</p>
              ) : (
                sessions.map((s) => (
                  <div
                    key={s.id}
                    className={`group flex items-center justify-between rounded-md px-2 py-1.5 text-sm ${
                      s.id === activeId ? 'bg-[--surface-3] text-[--text-primary]' : 'text-[--text-secondary] hover:bg-[--surface-2]'
                    }`}
                  >
                    <button className="min-w-0 flex-1 truncate text-left" onClick={() => openSession(s.id)}>
                      {s.title || t('roughcut.untitled')}
                    </button>
                    <button
                      onClick={() => setConfirmDeleteId(s.id)}
                      aria-label={t('roughcut.deleteSession')}
                      title={t('roughcut.deleteSession')}
                      className="ml-1 hidden rounded p-1 text-[--text-muted] hover:text-[--error] group-hover:block"
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

        {/* Conversation column */}
        <section className="flex min-w-0 flex-1 flex-col border-r border-[--border]">
          <div ref={threadRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {messages.length === 0 && !busy ? (
              <p className="text-sm text-[--text-muted]">{t('roughcut.emptyConvo')}</p>
            ) : (
              messages.map((m, i) => (
                <div key={i} className={m.role === 'user' ? 'text-right' : 'text-left'}>
                  <div
                    className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-left text-sm ${
                      m.role === 'user'
                        ? 'bg-[--primary] text-white'
                        : 'bg-[--surface-2] text-[--text-primary]'
                    }`}
                  >
                    {m.content}
                  </div>
                </div>
              ))
            )}
            {busy && (
              <div className="text-left">
                <div className="inline-flex max-w-[90%] flex-col gap-1 rounded-lg bg-[--surface-2] px-3 py-2 text-sm text-[--text-secondary]">
                  {progressLog.length === 0 ? (
                    <div className="inline-flex items-center gap-2">
                      <ThinkingDots />
                      <span>{t('roughcut.thinking')}</span>
                    </div>
                  ) : (
                    progressLog.slice(-5).map((p, i, arr) => (
                      <div
                        key={`${i}-${p}`}
                        className={`inline-flex items-center gap-2 ${i < arr.length - 1 ? 'text-xs text-[--text-muted]' : ''}`}
                      >
                        {i === arr.length - 1 ? <ThinkingDots /> : <span aria-hidden="true">·</span>}
                        <span>{p}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
          <div className="shrink-0 border-t border-[--border] p-3">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault()
                  send()
                }
              }}
              rows={3}
              placeholder={t('roughcut.placeholder')}
              className="w-full resize-none rounded-md border border-[--border] bg-[--surface-2] px-3 py-2 text-sm outline-none focus:border-[--primary]"
            />
            <div className="mt-2 flex items-center justify-between">
              <button
                onClick={openPrompt}
                aria-label={t('roughcut.promptSettings')}
                title={t('roughcut.promptSettings')}
                className="inline-flex items-center gap-1.5 rounded-md border border-[--border] px-2.5 py-1.5 text-xs text-[--text-secondary] hover:bg-[--surface-3]"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0ZM3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-9.75 0h9.75" />
                </svg>
                {t('roughcut.promptSettings')}
              </button>
              <button
                onClick={send}
                disabled={busy || !input.trim()}
                className="inline-flex items-center gap-2 rounded-md bg-[--primary] px-4 py-1.5 text-sm font-medium text-white hover:bg-[--primary]/90 disabled:opacity-50"
              >
                {busy && <ThinkingDots />}
                {t('roughcut.send')}
              </button>
            </div>
          </div>
        </section>

        {/* Shot list preview */}
        <section className="flex w-[46%] min-w-0 shrink-0 flex-col bg-[--surface-1]">
          <div className="flex h-11 shrink-0 items-center justify-between border-b border-[--border] px-4">
            <span className="text-xs font-medium text-[--text-secondary]">{t('roughcut.planTitle')}</span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPlanFullscreen(true)}
                aria-label={t('roughcut.fullscreen')}
                title={t('roughcut.fullscreen')}
                className="rounded border border-[--border] p-1 text-[--text-secondary] hover:bg-[--surface-3]"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
                </svg>
              </button>
              {plan && (
                <button
                  onClick={copyMarkdown}
                  className="rounded border border-[--border] px-2 py-1 text-xs text-[--text-secondary] hover:bg-[--surface-3]"
                >
                  {copied ? t('roughcut.copied') : t('roughcut.copyMarkdown')}
                </button>
              )}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
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
        </section>
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

      {/* Director prompt settings modal */}
      {promptOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-lg border border-[--border] bg-[--surface-1] shadow-xl">
            <div className="flex items-center justify-between border-b border-[--border] px-5 py-3">
              <span className="text-sm font-semibold">{t('roughcut.promptTitle')}</span>
              <span className={`text-xs ${promptIsDefault ? 'text-[--text-muted]' : 'text-[--primary]'}`}>
                {promptIsDefault ? t('roughcut.promptDefault') : t('roughcut.promptCustom')}
              </span>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-5">
              <p className="mb-2 text-xs text-[--text-muted]">{t('roughcut.promptHelp')}</p>
              <textarea
                value={promptText}
                onChange={(e) => setPromptText(e.target.value)}
                rows={16}
                spellCheck={false}
                className="w-full resize-y rounded-md border border-[--border] bg-[--surface-2] px-3 py-2 font-mono text-xs leading-relaxed outline-none focus:border-[--primary]"
              />
            </div>
            <div className="flex items-center justify-between border-t border-[--border] px-5 py-3">
              <button
                onClick={resetPrompt}
                disabled={promptIsDefault && promptText === promptDefault}
                className="rounded-md border border-[--border] px-3 py-1.5 text-sm text-[--text-secondary] hover:bg-[--surface-3] disabled:opacity-40"
              >
                {t('roughcut.reset')}
              </button>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPromptOpen(false)}
                  className="rounded-md border border-[--border] px-3 py-1.5 text-sm text-[--text-secondary] hover:bg-[--surface-3]"
                >
                  {t('roughcut.cancel')}
                </button>
                <button
                  onClick={savePrompt}
                  className="rounded-md bg-[--primary] px-4 py-1.5 text-sm font-medium text-white hover:bg-[--primary]/90"
                >
                  {promptSaved ? t('roughcut.saved') : t('roughcut.save')}
                </button>
              </div>
            </div>
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
  const chapters = plan.chapters.length ? plan.chapters : ['']
  let index = 0
  return (
    <div className="space-y-5" data-testid="shot-list">
      {chapters.map((chapter) => {
        const shots = plan.shots.filter((s) => (s.chapter || '') === (chapter || ''))
        if (!shots.length) return null
        return (
          <div key={chapter || '__none'}>
            <h3 className="mb-2 text-sm font-semibold text-[--text-primary]">{chapter || '未分章'}</h3>
            <div className="space-y-2">
              {shots.map((s) => {
                index += 1
                return (
                  <div key={index} className="flex gap-2 rounded-md border border-[--border] bg-[--surface-2] p-2">
                    <span className="w-5 shrink-0 text-right text-xs text-[--text-muted]">{index}</span>
                    {s.thumb_ref ? (
                      <img src={s.thumb_ref} alt="" className="h-12 w-20 shrink-0 rounded object-cover" />
                    ) : (
                      <div className="h-12 w-20 shrink-0 rounded bg-[--surface-3]" />
                    )}
                    <div className="min-w-0 flex-1 text-xs">
                      <div className="flex items-center gap-2 text-[--text-secondary]">
                        <span className="font-mono">{fmtTimecode(s.in_s)}–{fmtTimecode(s.out_s)}</span>
                        <span className="rounded bg-[--surface-3] px-1">{s.roll === 'a' ? 'A' : 'B'}</span>
                        {s.clip_date && <span className="font-mono text-[--text-muted]">{s.clip_date}</span>}
                        <span className="truncate text-[--text-muted]">{s.clip_label}</span>
                      </div>
                      {s.content && <p className="mt-0.5 truncate text-[--text-primary]">{s.content}</p>}
                      {s.rationale && <p className="text-[--text-muted]">{s.rationale}</p>}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
      <div className={`text-sm font-medium ${plan.within_target ? 'text-[--text-secondary]' : 'text-[--error]'}`}>
        {`总时长：${fmtDuration(plan.total_s)}`}
        {plan.target_min_s != null && plan.target_max_s != null &&
          `（目标 ${fmtDuration(plan.target_min_s)}–${fmtDuration(plan.target_max_s)} ${plan.within_target ? '✓' : '⚠️'}）`}
      </div>
    </div>
  )
}

export default CutplanPage
