/** Filters feature — sidebar panel with date accordion, roll type filter, and tag chips.

Filters are applied client-side (the backend GET /clips supports date/roll_type/tag
query params; the frontend composes them and re-fetches via `onFilterChange`).

Usage:
  <Filters onFilterChange={(filters) => setAppliedFilters(filters)} />
*/

import { useEffect, useState } from 'react'

import { api } from '@/api/client'

/** Extract the YYYY-MM-DD date for a clip (embedded capture time preferred). */
function clipDate(c: { capture_time?: string | null; created_at?: string }): string | null {
  const raw = c.capture_time || c.created_at
  if (!raw) return null
  const d = new Date(raw)
  return isNaN(d.getTime()) ? null : d.toISOString().slice(0, 10)
}

// ── Filter state interface (mirrors ClipFilter) ────────────────

export interface FiltersState {
  date: string | null
  roll_type: 'a' | 'b' | null
  tag: string | null
}

const DEFAULT_FILTERS: FiltersState = { date: null, roll_type: null, tag: null }

// ── Main Filters component ──────────────────────────────────────

export interface FiltersProps {
  /** Called whenever any filter changes; receives the full filters object. */
  onFilterChange: (filters: FiltersState) => void
}

export function Filters({ onFilterChange }: FiltersProps) {
  const [filters, setFilters] = useState<FiltersState>(DEFAULT_FILTERS)

  // Unique tag names and dates derived from the clip list (fetched on mount).
  const [allTags, setAllTags] = useState<string[]>([])
  const [allDates, setAllDates] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    api.listClips()
      .then((clips) => {
        if (cancelled) return
        const tagNames = new Set<string>()
        const dates = new Set<string>()
        for (const c of clips) {
          c.tags?.forEach((t) => tagNames.add(t.name))
          const d = clipDate(c)
          if (d) dates.add(d)
        }
        setAllTags([...tagNames].sort())
        setAllDates([...dates].sort().reverse()) // newest first
      })
      .catch(() => { setAllTags([]); setAllDates([]) })

    return () => { cancelled = true }
  }, [])

  const updateFilter = <K extends keyof FiltersState>(key: K, value: FiltersState[K]) => {
    const next = { ...filters, [key]: value }
    setFilters(next)
    onFilterChange(next)
  }

  const clearAll = () => {
    setFilters(DEFAULT_FILTERS)
    onFilterChange({ ...DEFAULT_FILTERS })
  }

  const hasActiveFilters = filters.date !== null || filters.roll_type !== null || filters.tag !== null

  return (
    <div className="flex h-full w-64 shrink-0 flex-col gap-5 overflow-y-auto border-r border-[--border] bg-[--surface-1] p-4">
      <h2 className="text-sm font-semibold tracking-tight text-[--text-primary]">Filters</h2>

      {/* ── Roll type filter ─────────────────────────────── */}
      <div>
        <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-[--text-muted]">
          Type
        </label>
        <div className="flex gap-1.5">
          {([['all', 'All'], ['a', 'A-roll'], ['b', 'B-roll']] as const).map(([value, label]) => {
            const isActive = value === 'all' ? filters.roll_type === null : filters.roll_type === value
            return (
              <button
                key={value}
                onClick={() => updateFilter('roll_type', value === 'all' ? null : (value as 'a' | 'b'))}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-[--primary] text-white'
                    : 'text-[--text-secondary] hover:bg-[--surface-2]'
                }`}
              >
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {/* ── Date filter (accordion) ─────────────────────── */}
      <div>
        <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-[--text-muted]">
          Date
        </label>
        <select
          value={filters.date ?? ''}
          onChange={(e) => updateFilter('date', e.target.value || null)}
          className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-xs text-[--text-primary] outline-none transition-colors focus:border-[--primary]"
        >
          <option value="">All dates</option>
          {allDates.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>

      {/* ── Tag filter (chips) ─────────────────────────── */}
      <div>
        <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-[--text-muted]">
          Tags
        </label>
        {allTags.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {allTags.map((tag) => (
              <button
                key={tag}
                onClick={() => updateFilter('tag', filters.tag === tag ? null : tag)}
                className={`rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors ${
                  filters.tag === tag
                    ? 'border-[--primary] bg-[--primary-soft] text-[--primary]'
                    : 'border-[--border] bg-[--surface-2] text-[--text-secondary] hover:border-[--border-strong]'
                }`}
              >
                {tag}
              </button>
            ))}
          </div>
        ) : (
          <p className="text-xs text-[--text-muted]">No tags yet</p>
        )}
      </div>

      {/* ── Clear all button ───────────────────────────── */}
      {hasActiveFilters && (
        <button
          onClick={clearAll}
          className="mt-auto text-xs font-medium text-[--text-muted] underline hover:text-[--primary]"
        >
          Clear all filters
        </button>
      )}
    </div>
  )
}
