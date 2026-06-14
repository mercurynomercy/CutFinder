/** App shell — header (title + search + scan button), sidebar filters, gallery grid,
detail drawer, and top progress bar for active jobs.

Usage: <App /> — no props needed; state is managed internally.
*/

import { useEffect, useState } from 'react'

import type { ClipSummary, JobEvent } from '@/api/client'
import { api } from '@/api/client'
import { useJobEvents, useSSE } from '@/api/sse'
import { Search } from '@/features/search'
import { Filters, type FiltersState as FilterState } from '@/features/filters'
import { Gallery, type GalleryProps } from '@/features/gallery'
import { DetailPanel, type DetailPanelProps as DetailPanelPropsType } from '@/features/detail'
import { JobsPanel, type JobsPanelProps } from '@/features/jobs'

// ── App state ────────────────────────────────────────

export default function App() {
  const [clips, setClips] = useState<ClipSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedClipId, setSelectedClipId] = useState<DetailPanelPropsType['clipId']>(null)
  const [activeJobId, setActiveJobId] = useState<JobsPanelProps['activeJobId']>(null)
  const [appliedFilters, setAppliedFilters] = useState<Partial<FilterState>>({})

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
    try {
      // Trigger scan — SSE will stream progress events; poll for job id
      const response = await fetch('/api/scan', { method: 'POST' })
      if (response.ok) {
        const data = await response.json()
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

  // If loading, show empty gallery with skeleton (handled by Gallery itself)
  if (loading && clips.length === 0) {
    return <Gallery clips={[]} selectedClipId={selectedClipId} onSelect={setSelectedClipId} />
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
