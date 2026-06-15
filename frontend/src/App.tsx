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
    if (appliedFilters.date && clip.created_at) {
      const clipDate = new Date(clip.created_at).toISOString().slice(0, 10)
      if (appliedFilters.date! !== '' && !clipDate.startsWith(appliedFilters.date!) && appliedFilters.date!.length > 4) return false
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
              <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01" />
            </svg>
          </button>
          <button
            onClick={() => setShowSettings(true)}
            className="rounded-md p-1.5 text-[--text-secondary] hover:bg-[--surface-3] transition-colors"
            aria-label="Settings"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth={1.5} />
              <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20.82 7.774l-.75-1.3c-.406-.702-1.308-.956-2.01-.547l-.825.477c-1.396.808-3.125.402-3.76-.98V4c0-.828-.672-1.5-1.5-1.5h-1.5c-.828 0-1.5.672-1.5 1.5v.43c0 1.867-2.096 2.954-3.717 2.08L3.6 5.924c-.701-.41-1.603-.155-2.01.547l-.75 1.3c-.406.702-.152 1.604.55 2.01l.738.427c1.62.935 1.62 3.045 0 3.98l-.738.426c-.701.405-.956 1.308-.55 2.01l.75 1.3c.406.702 1.308.956 2.01.547l.825-.477c1.62-.87 3.717.213 3.717 2.08V20c0 .828.672 1.5 1.5 1.5h1.5c.829 0 1.5-.672 1.5-1.5v-.43c0-1.867 2.1-2.954 3.72-2.08l.825.477c.701.406 1.603.152 2.01-.55l.75-1.3c.406-.702.152-1.604-.55-2.01l-.738-.427c-1.62-.935-1.62-3.045 0-3.98l.738-.426c.701-.405.956-1.308.55-2.01z" />
            </svg>
          </button>
        </div>
      </header>

      {/* Main layout: sidebar + gallery */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar: filters + gallery */}
        <div className="flex w-full overflow-hidden">
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
