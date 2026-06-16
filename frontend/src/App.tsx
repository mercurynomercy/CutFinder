/** App shell — header (title + search + scan button), sidebar filters, gallery grid,
detail drawer, and top progress bar for active jobs.

Usage: <App /> — no props needed; state is managed internally.
*/

import { useEffect, useRef, useState } from 'react'

import type { ClipSummary } from '@/api/client'
import { api } from '@/api/client'
import { Search } from '@/features/search'
import { Filters, type FiltersState as FilterState } from '@/features/filters'
import { Gallery } from '@/features/gallery'
import { DetailPanel, type DetailPanelProps as DetailPanelPropsType } from '@/features/detail'
import { JobsPanel, type JobsPanelProps } from '@/features/jobs'
import { JobsQueuePage } from '@/features/jobs-queue'
import { SettingsPage } from '@/features/settings'

// ── App state ────────────────────────────────────────

export default function App() {
  const [clips, setClips] = useState<ClipSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [showSettings, setShowSettings] = useState(false)
  const [showJobs, setShowJobs] = useState(false)
  const [selectedClipId, setSelectedClipId] = useState<DetailPanelPropsType['clipId']>(null)
  const [activeJobId, setActiveJobId] = useState<JobsPanelProps['activeJobId']>(null)
  const [appliedFilters, setAppliedFilters] = useState<Partial<FilterState>>({})

  const clipsRef = useRef(clips)
  clipsRef.current = clips

  // Fetch clips on mount
  useEffect(() => {
    let cancelled = false
    api.listClips()
      .then((data) => { if (!cancelled) setClips(data) })
      .catch(() => {}) // silently fail; empty gallery shows helpful message
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
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

  // Filter clips client-side (date, roll_type, tag)
  const filteredClips = clips.filter((clip) => {
    if (appliedFilters.roll_type && clip.roll_type !== appliedFilters.roll_type) return false
    if (appliedFilters.tag && !clip.tags?.some((t) => t.name === appliedFilters.tag)) return false
    if (appliedFilters.date) {
      const raw = clip.capture_time || clip.created_at
      if (!raw) return false
      const d = new Date(raw)
      const clipDate = isNaN(d.getTime()) ? '' : d.toISOString().slice(0, 10)
      if (clipDate !== appliedFilters.date) return false
    }
    return true
  })

  const handleScan = async () => {
    console.log('[App] Scan button clicked')
    try {
      // Trigger scan — SSE will stream progress events; poll for job id
      console.log('[App] Calling POST /api/scan...')
      const response = await fetch('/api/scan', { method: 'POST' })
      if (response.ok) {
        const data = await response.json()
        console.log('[App] POST /api/scan returned:', data)
        setActiveJobId(data.job_id as number)
        // Jump to the task queue so the user can see scan progress immediately.
        setShowJobs(true)
      }
    } catch (err) {
      console.error('Scan failed:', err)
    }
  }

  const handleSearch = (_query: string) => {
    // Full-text search via API — placeholder for v1 (client-side only for now)
  }

  const handleFilterChange = (filters: FilterState) => {
    setAppliedFilters({ date: filters.date, roll_type: filters.roll_type, tag: filters.tag })
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

  // If loading, show empty gallery with skeleton (handled by Gallery itself)
  if (loading && clips.length === 0) {
    return <Gallery clips={[]} selectedClipId={selectedClipId} onSelect={setSelectedClipId} />
  }

  // Settings view (full-screen, replaces main layout)
  if (showSettings) {
    return <SettingsPage onSave={() => { setShowSettings(false); refreshClips() }} />
  }

  // Jobs queue view (full-screen, replaces main layout)
  if (showJobs) {
    return <JobsQueuePage onClose={() => setShowJobs(false)} />
  }

  return (
    <div className="flex h-screen w-full flex-col bg-[--bg-canvas] text-[--text-primary]">
      {/* Top progress bar (absolute, sticky) */}
      <JobsPanel activeJobId={activeJobId} />

      {/* Header bar */}
      <header className="h-14 shrink-0 border-b border-[--border] bg-[--surface-1] px-6 flex items-center justify-between">
        <h1 className="text-lg font-semibold tracking-tight">CutFinder</h1>
        <div className="flex items-center gap-3">
          <Search onSearch={handleSearch} />
          <button
            onClick={handleScan}
            className="rounded-md bg-[--primary] px-4 py-1.5 text-sm font-medium text-white shadow hover:bg-[--primary]/90 transition-colors"
          >
            Scan
          </button>
          <button
            onClick={() => setShowJobs(true)}
            className="rounded-md p-1.5 text-[--text-secondary] hover:bg-[--surface-3] transition-colors"
            aria-label="任务队列"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24">
              <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 6.878V6a2.25 2.25 0 012.25-2.25h7.5A2.25 2.25 0 0118 6v.878m-12 0c.235-.083.487-.128.75-.128h10.5c.263 0 .515.045.75.128m-12 0A2.25 2.25 0 004.5 9v.878m13.5-3A2.25 2.25 0 0119.5 9v.878m0 0a2.246 2.246 0 00-.75-.128H5.25c-.263 0-.515.045-.75.128m15 0A2.25 2.25 0 0121 12v6a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 18v-6c0-.98.626-1.813 1.5-2.122" />
            </svg>
          </button>
          <button
            onClick={() => setShowSettings(true)}
            className="rounded-md p-1.5 text-[--text-secondary] hover:bg-[--surface-3] transition-colors"
            aria-label="Settings"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24">
              <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.49l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
              <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </div>
      </header>

      {/* Main layout: sidebar + gallery */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Sidebar: filters + gallery */}
        <div className="flex min-h-0 w-full overflow-hidden">
          {/* Filters sidebar (fixed width) */}
          <Filters onFilterChange={handleFilterChange} />

          {/* Gallery grid (flex-1, scrollable) */}
          <Gallery
            clips={filteredClips}
            selectedClipId={selectedClipId}
            onSelect={(clipId) => setSelectedClipId(clipId)}
          />
        </div>

        {/* Detail panel (slide-in drawer, right side) */}
        <DetailPanel clipId={selectedClipId} onClose={() => setSelectedClipId(null)} />
      </div>
    </div>
  )
}
