/** App shell — header (title + search + scan button), sidebar filters, gallery grid,
full-screen clip detail view, and bottom status bar for active jobs.

Usage: <App /> — no props needed; state is managed internally.
*/

import { useEffect, useMemo, useRef, useState } from 'react'

import type { ClipSummary } from '@/api/client'
import { api } from '@/api/client'
import { Filters, type FiltersState as FilterState } from '@/features/filters'
import { Search } from '@/features/search'
import { Gallery, groupKeys } from '@/features/gallery'
import { DetailPanel, type DetailPanelProps as DetailPanelPropsType } from '@/features/detail'
import { JobsPanel, type JobsPanelProps } from '@/features/jobs'
import { JobsQueuePage } from '@/features/jobs-queue'
import { SettingsPage } from '@/features/settings'
import { SubtitlesPage } from '@/features/subtitles'
import { CutplanPage } from '@/features/cutplan'
import { LauncherPage, type LauncherScreen } from '@/features/launcher'
import { LogsPage } from '@/features/logs'
import { ConfirmDialog } from '@/components'
import { localDateKey } from '@/lib/date'
import { useI18n } from '@/i18n'
import { applyTheme, getStoredTheme, type Theme } from '@/theme'

// Poll a job until it reaches a terminal state (or the timeout elapses).
async function waitForJob(jobId: number, timeoutMs = 30 * 60_000): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1500))
    try {
      const job = await api.getJob(jobId)
      if (['done', 'failed', 'cancelled'].includes(job.status)) return
    } catch {
      // transient error — keep polling
    }
  }
}

// ── App state ────────────────────────────────────────

export default function App() {
  const { t } = useI18n()
  const [clips, setClips] = useState<ClipSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [showSettings, setShowSettings] = useState(false)
  const [showJobs, setShowJobs] = useState(false)
  const [showSubtitles, setShowSubtitles] = useState(false)
  const [showCutplan, setShowCutplan] = useState(false)
  const [showLauncher, setShowLauncher] = useState(true)
  const [showLogs, setShowLogs] = useState(false)
  const [selectedClipId, setSelectedClipId] = useState<DetailPanelPropsType['clipId']>(null)
  const [activeJobId, setActiveJobId] = useState<JobsPanelProps['activeJobId']>(null)
  const [appliedFilters, setAppliedFilters] = useState<FilterState>({ date: null, roll_type: null, tag: null })
  const [reanalyzingIds, setReanalyzingIds] = useState<Set<number>>(new Set())
  const [sortBy, setSortBy] = useState<'date-newest' | 'date-oldest'>('date-newest')
  const [collapsedDates, setCollapsedDates] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [theme, setTheme] = useState<Theme>(getStoredTheme)
  const [filtersCollapsed, setFiltersCollapsed] = useState(false)

  // Confirmation dialog for pause→resume scan (WKWebView has no window.confirm).
  const [confirmPause, setConfirmPause] = useState(false)

  // True while a scan is in flight — disables the Scan button so it can't be
  // clicked again and enqueue a second concurrent scan job.
  const [scanning, setScanning] = useState(false)

  // Library cleanup (remove catalog entries whose copy was deleted) — triggered
  // from the Settings page.
  const [confirmCleanup, setConfirmCleanup] = useState(false)
  const [orphanIds, setOrphanIds] = useState<number[]>([])

  // Raise an ambient toast (reuses JobsPanel's toast UI via a window event).
  const showToast = (type: 'info' | 'success' | 'error', message: string) =>
    window.dispatchEvent(new CustomEvent('cutfinder:toast', { detail: { type, message } }))

  // Cancel pause-resume dialog.
  const handleCancelResume = () => { setConfirmPause(false) }

  // Confirm: resume jobs, then start the scan.
  const handleConfirmResume = async () => {
    setConfirmPause(false)
    await api.resumeJobs()
    await doScan()
  }

  // Check for catalog entries whose library copy was deleted; show a notice or
  // open the confirm dialog. Library unreachable → skip (never wipe the catalog).
  const handleCleanupLibrary = async () => {
    try {
      const { library_reachable, orphans } = await api.listOrphans()
      if (!library_reachable) { showToast('info', t('settings.cleanupUnreachable')); return }
      if (orphans.length === 0) { showToast('info', t('settings.cleanupNone')); return }
      setOrphanIds(orphans.map((o) => o.id))
      setConfirmCleanup(true)
    } catch (err) {
      console.error('Failed to check library for deleted files:', err)
    }
  }

  const handleConfirmCleanup = async () => {
    setConfirmCleanup(false)
    try {
      const { deleted } = await api.deleteOrphans(orphanIds)
      showToast('success', t('settings.cleanupDone', { n: deleted }))
      await refreshClips()
    } catch (err) {
      console.error('Failed to clean up deleted files:', err)
    } finally {
      setOrphanIds([])
    }
  }

  // Light / dark toggle — persists and updates <html data-theme>.
  const toggleTheme = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    applyTheme(next)
    setTheme(next)
  }

  // Launcher navigation — enter a specific screen from the launcher cards.
  const handleNavigate = (screen: LauncherScreen) => {
    setShowLauncher(false)
    if (screen === 'settings') setShowSettings(true)
    else if (screen === 'jobs') setShowJobs(true)
    else if (screen === 'cutplan') setShowCutplan(true)
    else if (screen === 'subtitles') setShowSubtitles(true)
  }

  // Logo click — back out of any full-screen view to the launcher.
  const handleBackToLauncher = () => {
    setShowSettings(false)
    setShowJobs(false)
    setShowSubtitles(false)
    setShowCutplan(false)
    setShowLauncher(true)
  }

  // Synchronous re-entry guard for scans — covers a rapid double-click landing
  // before React re-renders the disabled button.
  const scanningRef = useRef(false)

  // Fetch clips on mount
  useEffect(() => {
    let cancelled = false
    api.listClips()
      .then((data) => { if (!cancelled) setClips(data) })
      .catch(() => {}) // silently fail; empty gallery shows helpful message
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  // Re-attach to a job still running in the backend after a page refresh. The
  // worker keeps processing, but the UI lost its in-memory job id so the top
  // progress bar vanished. Adopt the active job so the bar reappears (JobsPanel
  // polls + re-subscribes SSE on its own), then refresh the gallery when it
  // ends. Subtitle jobs are restored by the subtitles page itself.
  useEffect(() => {
    let cancelled = false
    api.listJobs()
      .then(async ({ jobs }) => {
        const active = jobs.find(
          (j) => ['queued', 'running'].includes(j.status) && j.kind !== 'subtitle',
        )
        if (!active || cancelled) return
        setActiveJobId(active.id)
        await waitForJob(active.id)
        if (!cancelled) await refreshClips()
      })
      .catch(() => {}) // no job queue / backend unreachable — nothing to restore
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Expose a custom event for e2e tests to navigate without clicking (avoids overlay issues).
  // Usage: window.dispatchEvent(new CustomEvent('cutfinder:navigate', { detail: { clipId: 2 } }))
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { clipId: number } | undefined
      if (detail?.clipId !== undefined) setSelectedClipId(detail.clipId)
    }
    window.addEventListener('cutfinder:navigate', handler)
    return () => window.removeEventListener('cutfinder:navigate', handler)
  }, [])

  // Filter clips client-side (search query + date, roll_type, tag), then sort.
  // Memoised so it only recomputes when the inputs change, not on every render.
  const sortedClips = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    const matchesQuery = (clip: ClipSummary) => {
      if (!query) return true
      const name = (clip.library_path || clip.source_path || '').split('/').pop()?.toLowerCase() || ''
      if (name.includes(query)) return true
      if (clip.summary?.toLowerCase().includes(query)) return true
      if (clip.description?.toLowerCase().includes(query)) return true
      return Boolean(clip.tags?.some((t) => t.name.toLowerCase().includes(query)))
    }

    const filteredClips = clips.filter((clip) => {
      if (!matchesQuery(clip)) return false
      if (appliedFilters.roll_type && clip.roll_type !== appliedFilters.roll_type) return false
      if (appliedFilters.tag && !clip.tags?.some((t) => t.name === appliedFilters.tag)) return false
      if (appliedFilters.date) {
        const clipDate = localDateKey(clip.capture_time || clip.created_at)
        if (clipDate !== appliedFilters.date) return false
      }
      return true
    })

    // Sort the filtered clips (default: by shooting date, newest first).
    return [...filteredClips].sort((a, b) => {
      // 'date' — embedded capture time preferred
      const da = a.capture_time || a.created_at || ''
      const db = b.capture_time || b.created_at || ''
      return sortBy === 'date-newest' ? db.localeCompare(da) : da.localeCompare(db)
    })
  }, [clips, appliedFilters, searchQuery, sortBy])

  // Whether every date group is currently collapsed — drives the toggle-all label.
  const dateGroupKeys = groupKeys(sortedClips)
  const allDatesCollapsed = dateGroupKeys.length > 0 && dateGroupKeys.every((k) => collapsedDates.has(k))
  const toggleAllDates = () => setCollapsedDates(allDatesCollapsed ? new Set() : new Set(dateGroupKeys))

  // Called from the Scan button. Checks pause state first; if paused, shows a dialog.
  const handleScan = async () => {
    console.log('[App] Scan button clicked')
    try {
      const { paused } = await api.listJobs()
      if (paused) { setConfirmPause(true); return }
    } catch { /* couldn't check pause state — proceed anyway */ }
    await doScan()
  }

  // Core scan logic: trigger /api/scan, poll until done. Does NOT check pause state.
  const doScan = async () => {
    if (scanningRef.current) return  // a scan is already in flight — ignore
    scanningRef.current = true
    setScanning(true)
    console.log('[App] Scan button clicked')
    try {
      // Trigger scan — SSE will stream progress events; poll for job id
      console.log('[App] Calling POST /api/scan...')
      const response = await fetch('/api/scan', { method: 'POST' })
      if (response.ok) {
        const data = await response.json()
        console.log('[App] POST /api/scan returned:', data)
        const jobId = data.job_id as number
        setActiveJobId(jobId)
        // Jump to the task queue so the user can see scan progress immediately.
        setShowJobs(true)

        // Wait for the scan job to finish, then refresh clips so new ones
        // appear immediately (no manual refresh needed).
        const deadline = Date.now() + 30 * 60_000 // 30 min timeout
        while (Date.now() < deadline) {
          await new Promise((resolve) => setTimeout(resolve, 1500))
          try {
            const job = await api.getJob(jobId)
            if (['done', 'failed', 'cancelled'].includes(job.status)) break
          } catch {
            // transient error — keep polling
          }
        }
        await refreshClips()

        // A scan auto-queues a keyframes job (when enabled). Adopt it as the
        // active job so its progress bar keeps showing after the scan ends.
        try {
          const { jobs } = await api.listJobs()
          const kf = jobs.find((j) => j.kind === 'keyframes' && ['queued', 'running'].includes(j.status))
          if (kf) {
            setActiveJobId(kf.id)
            await waitForJob(kf.id)
            await refreshClips()
          }
        } catch {
          // best effort — no auto keyframes follow-up
        }
      }
    } catch (err) {
      console.error('Scan failed:', err)
    } finally {
      scanningRef.current = false
      setScanning(false)
    }
  }

  const handleSearch = (query: string) => {
    setSearchQuery(query)
  }

  const handleFilterChange = (filters: FilterState) => {
    setAppliedFilters({ date: filters.date, roll_type: filters.roll_type, tag: filters.tag })
  }

  // Re-analyze a clip directly from its card: trigger the job, poll until it
  // finishes, then refresh so the card's summary/tags/marker update in place.
  const handleReanalyzeClip = async (clipId: number) => {
    if (reanalyzingIds.has(clipId)) return
    setReanalyzingIds((prev) => new Set(prev).add(clipId))
    try {
      const { job_id } = await api.reanalyzeClip(clipId)
      const deadline = Date.now() + 5 * 60_000
      while (Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 1500))
        try {
          const job = await api.getJob(job_id)
          if (['done', 'failed', 'cancelled'].includes(job.status)) break
        } catch {
          // transient error — keep polling
        }
      }
      await refreshClips()
    } catch (err) {
      console.error('Failed to re-analyze clip:', err)
    } finally {
      setReanalyzingIds((prev) => {
        const next = new Set(prev)
        next.delete(clipId)
        return next
      })
    }
  }

  // One-click: generate keyframe suggestions for all clips that lack them.
  const handleSuggestAllKeyframes = async () => {
    try {
      const { job_id, count } = await api.suggestAllKeyframes()
      if (count === 0) return  // nothing to do — every clip already has suggestions
      setActiveJobId(job_id)
      setShowJobs(true)
      await waitForJob(job_id)
      await refreshClips()
    } catch (err) {
      console.error('Failed to suggest keyframes:', err)
    }
  }

  // Open a file in its default app, or reveal a folder in Finder (macOS `open`).
  const handleOpenPath = async (path: string) => {
    try {
      await api.openPath(path)
    } catch (err) {
      console.error('Failed to open path:', err)
    }
  }

  const refreshClips = async () => {
    try {
      const data = await api.listClips()
      setClips(data)
    } catch {
      // silently fail; empty gallery shows helpful message
    } finally {
      setLoading(false)
    }
  }

  // Launcher (主目录) — CutFinder's entry screen; shown before anything else.
  if (showLauncher) {
    return <LauncherPage theme={theme} onToggleTheme={toggleTheme} onNavigate={handleNavigate} />
  }

  // If loading, show empty gallery with skeleton (handled by Gallery itself)
  if (loading && clips.length === 0 && !showSettings && !showJobs && !showSubtitles && !showCutplan && selectedClipId === null) {
    return <Gallery clips={[]} selectedClipId={selectedClipId} onSelect={setSelectedClipId} />
  }

  // Backend log viewer (full-screen, replaces main layout)
  if (showLogs) {
    return (
      <LogsPage
        onClose={() => setShowLogs(false)}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
    )
  }

  // Settings view (full-screen, replaces main layout)
  if (showSettings) {
    return (
      <>
        <SettingsPage
          onSave={() => { setShowSettings(false); refreshClips() }}
          onSuggestAllKeyframes={handleSuggestAllKeyframes}
          onCleanupLibrary={handleCleanupLibrary}
          onShowLogs={() => setShowLogs(true)}
          onClose={handleBackToLauncher}
          theme={theme}
          onToggleTheme={toggleTheme}
        />

        {/* Ambient toast host — cleanup/keyframe actions raise toasts via this. */}
        <JobsPanel activeJobId={activeJobId} />

        {/* Library cleanup: confirm deletion of orphaned catalog entries */}
        <ConfirmDialog
          open={confirmCleanup}
          title={t('settings.cleanupDeleted')}
          message={t('settings.cleanupConfirm', { n: orphanIds.length })}
          onConfirm={handleConfirmCleanup}
          onCancel={() => { setConfirmCleanup(false); setOrphanIds([]) }}
        />
      </>
    )
  }

  // Jobs queue view (full-screen, replaces main layout)
  if (showJobs) {
    return <JobsQueuePage onClose={() => setShowJobs(false)} />
  }

  // Subtitle export view (full-screen, replaces main layout)
  if (showSubtitles) {
    return <SubtitlesPage onClose={() => setShowSubtitles(false)} />
  }

  // Rough-cut director view (full-screen, replaces main layout)
  if (showCutplan) {
    return <CutplanPage onClose={() => setShowCutplan(false)} />
  }

  // Clip detail view (full-screen, replaces main layout)
  if (selectedClipId !== null) {
    return (
      <>
        <DetailPanel
          clipId={selectedClipId}
          onClose={() => setSelectedClipId(null)}
          onOpenPath={handleOpenPath}
        />

        {/* Ambient toast host — keeps job progress/toasts visible while viewing a clip. */}
        <JobsPanel activeJobId={activeJobId} />
      </>
    )
  }

  return (
    <div className="flex h-screen w-full flex-col bg-[--bg-canvas] text-[--text-primary]">
      {/* Bottom status bar (fixed) for active jobs, plus the ambient toast host */}
      <JobsPanel activeJobId={activeJobId} />

      {/* Header bar */}
      <header className="h-14 shrink-0 border-b border-[--border] bg-[--surface-1] px-6 flex items-center gap-4">
        <button onClick={handleBackToLauncher} className="flex shrink-0 items-center">
          <img src="/logo.svg" alt="CutFinder" className="h-11 w-auto select-none" />
        </button>
        <span className="sr-only">CutFinder</span>

        <div className="min-w-0 flex-1">
          <Search onSearch={handleSearch} query={searchQuery} />
        </div>

        <nav className="flex shrink-0 items-center gap-1">
          <button
            onClick={() => setShowJobs(true)}
            className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm text-[--text-secondary] hover:bg-[--surface-3] hover:text-[--text-primary] transition-colors"
          >
            <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 6.878V6a2.25 2.25 0 012.25-2.25h7.5A2.25 2.25 0 0118 6v.878m-12 0c.235-.083.487-.128.75-.128h10.5c.263 0 .515.045.75.128m-12 0A2.25 2.25 0 004.5 9v.878m13.5-3A2.25 2.25 0 0119.5 9v.878m0 0a2.246 2.246 0 00-.75-.128H5.25c-.263 0-.515.045-.75.128m15 0A2.25 2.25 0 0121 12v6a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 18v-6c0-.98.626-1.813 1.5-2.122" />
            </svg>
            {t('app.taskQueue')}
          </button>
          <button
            onClick={() => setShowCutplan(true)}
            className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm text-[--text-secondary] hover:bg-[--surface-3] hover:text-[--text-primary] transition-colors"
          >
            <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="6" cy="6" r="3" />
              <circle cx="6" cy="18" r="3" />
              <path d="M20 4 8.12 15.88" />
              <path d="m14.8 14.8 5.2 5.2" />
              <path d="M8.12 8.12 12 12" />
            </svg>
            {t('app.roughcut')}
          </button>

          <div className="mx-1 h-6 w-px bg-[--border]" />

          <button
            onClick={() => setShowSettings(true)}
            aria-label={t('app.settings')}
            title={t('app.settings')}
            className="rounded-md p-1.5 text-[--text-secondary] hover:bg-[--surface-3] hover:text-[--text-primary] transition-colors"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.49l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
              <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>

          <button
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? t('app.themeToLight') : t('app.themeToDark')}
            title={theme === 'dark' ? t('app.themeToLight') : t('app.themeToDark')}
            className="rounded-md p-1.5 text-[--text-secondary] hover:bg-[--surface-3] hover:text-[--text-primary] transition-colors"
          >
            {theme === 'dark' ? (
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
              </svg>
            ) : (
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" />
              </svg>
            )}
          </button>
        </nav>

        <button
          onClick={handleScan}
          disabled={scanning}
          className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md bg-[--primary] px-4 py-1.5 text-sm font-medium text-white shadow hover:bg-[--primary]/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-[--primary]"
        >
          <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M3.75 7.5V6A2.25 2.25 0 016 3.75h1.5m9 0H18A2.25 2.25 0 0120.25 6v1.5m0 9V18A2.25 2.25 0 0118 20.25h-1.5m-9 0H6A2.25 2.25 0 013.75 18v-1.5M3 12h18" />
          </svg>
          {t('app.scan')}
        </button>
      </header>

      {/* Main layout: sidebar + gallery */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Sidebar: filters + gallery */}
        <div className="flex min-h-0 w-full overflow-hidden">
          {/* Filters sidebar (fixed width) — search box lives in the top bar */}
          <Filters
            onFilterChange={handleFilterChange}
            filters={appliedFilters}
            collapsed={filtersCollapsed}
            onToggleCollapsed={() => setFiltersCollapsed((v) => !v)}
          />

          {/* Gallery column: sort toolbar + scrollable grid */}
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <div className="flex h-11 shrink-0 items-center justify-between border-b border-[--border] px-4">
              <div className="flex items-center gap-2">
                {filtersCollapsed && (
                  <button
                    onClick={() => setFiltersCollapsed(false)}
                    title={t('filters.expand')}
                    aria-label={t('filters.expand')}
                    className="rounded p-1 text-[--text-muted] hover:bg-[--surface-2] hover:text-[--text-primary]"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 6h16.5M6.75 12h10.5m-7.5 6h4.5" />
                    </svg>
                  </button>
                )}
                <span className="text-xs text-[--text-muted]">{t('gallery.clipsCount', { n: sortedClips.length })}</span>
              </div>
              <div className="flex items-center gap-3">

                <button
                  onClick={toggleAllDates}
                  className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-[--text-muted] transition-colors hover:bg-[--surface-2] hover:text-[--text-primary]"
                >
                  <svg
                    className={`h-3 w-3 transition-transform ${allDatesCollapsed ? '-rotate-90' : ''}`}
                    fill="none" viewBox="0 0 24 24" aria-hidden="true"
                  >
                    <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                  </svg>
                  {allDatesCollapsed ? t('gallery.expandAll') : t('gallery.collapseAll')}
                </button>
                <label className="flex items-center gap-2 text-xs text-[--text-muted]">
                  {t('gallery.sort')}
                  <select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value as 'date-newest' | 'date-oldest')}
                    className="rounded-md border border-[--border] bg-[--surface-2] px-2 py-1 text-xs text-[--text-primary] outline-none transition-colors focus:border-[--primary]"
                  >
                    <option value="date-newest">{t('gallery.sortDateNewest')}</option>
                    <option value="date-oldest">{t('gallery.sortDateOldest')}</option>
                  </select>
                </label>
              </div>
            </div>
            <Gallery
              clips={sortedClips}
              selectedClipId={selectedClipId}
              onSelect={(clipId) => setSelectedClipId(clipId)}
              onReanalyze={handleReanalyzeClip}
              reanalyzingIds={reanalyzingIds}
              onOpenPath={handleOpenPath}
              collapsedDates={collapsedDates}
              onToggleDate={(key) =>
                setCollapsedDates((prev) => {
                  const next = new Set(prev)
                  next.has(key) ? next.delete(key) : next.add(key)
                  return next
                })
              }
            />
          </div>
        </div>
      </div>

      {/* Pause→resume scan confirmation dialog */}
      <ConfirmDialog
        open={confirmPause}
        title={t('scan.title')}
        message={t('scan.pausedConfirm')}
        onConfirm={handleConfirmResume}
        onCancel={handleCancelResume}
      />
    </div>
  )
}
