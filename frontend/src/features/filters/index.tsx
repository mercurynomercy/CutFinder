/** Filters feature — sidebar panel with date accordion, roll type filter, and tag chips.

Filters are applied client-side (the backend GET /clips supports date/roll_type/tag
query params; the frontend composes them and re-fetches via `onFilterChange`).

Usage:
  <Filters onFilterChange={(filters) => setAppliedFilters(filters)} />
*/

import { useEffect, useState } from 'react'

import { api } from '@/api/client'
import { localDateKey } from '@/lib/date'
import { useI18n } from '@/i18n'

/** Extract the local YYYY-MM-DD shooting date for a clip (embedded capture time preferred). */
function clipDate(c: { capture_time?: string | null; created_at?: string }): string | null {
  return localDateKey(c.capture_time || c.created_at)
}

// ── Filter state interface (mirrors ClipFilter) ────────────────

export interface FiltersState {
  date: string | null
  roll_type: 'a' | 'b' | 'photo' | null
  tag: string | null
}

const DEFAULT_FILTERS: FiltersState = { date: null, roll_type: null, tag: null }

// ── Main Filters component ──────────────────────────────────────

export interface FiltersProps {
  /** Called whenever any filter changes; receives the full filters object. */
  onFilterChange: (filters: FiltersState) => void
  /** Controlled collapsed state. Omit to let Filters manage its own (uncontrolled). */
  collapsed?: boolean
  /** Called to toggle collapse when controlled (required alongside `collapsed`). */
  onToggleCollapsed?: () => void
}

export function Filters({ onFilterChange, collapsed: collapsedProp, onToggleCollapsed }: FiltersProps) {
  const { t } = useI18n()
  const [filters, setFilters] = useState<FiltersState>(DEFAULT_FILTERS)
  const [internalCollapsed, setInternalCollapsed] = useState(false)
  const collapsed = collapsedProp ?? internalCollapsed
  const toggleCollapsed = onToggleCollapsed ?? (() => setInternalCollapsed((v) => !v))

  // Unique tag names (sorted by frequency) and dates, derived from the clip
  // list (fetched on mount).
  const [allTags, setAllTags] = useState<string[]>([])
  const [allDates, setAllDates] = useState<string[]>([])

  // Tag list controls (the list can grow into the hundreds).
  const [tagQuery, setTagQuery] = useState('')
  const [showAllTags, setShowAllTags] = useState(false)

  useEffect(() => {
    let cancelled = false
    api.listClips()
      .then((clips) => {
        if (cancelled) return
        const tagCounts = new Map<string, number>()
        const dates = new Set<string>()
        for (const c of clips) {
          c.tags?.forEach((t) => tagCounts.set(t.name, (tagCounts.get(t.name) ?? 0) + 1))
          const d = clipDate(c)
          if (d) dates.add(d)
        }
        // Most-used tags first, then alphabetical — surfaces the useful ones.
        const sorted = [...tagCounts.keys()].sort(
          (a, b) => (tagCounts.get(b)! - tagCounts.get(a)!) || a.localeCompare(b),
        )
        setAllTags(sorted)
        setAllDates([...dates].sort().reverse()) // newest first
      })
      .catch(() => { setAllTags([]); setAllDates([]) })

    return () => { cancelled = true }
  }, [])

  // Visible tags: filter by search, then cap the count unless expanded. The
  // selected tag is always kept visible so it can be toggled off.
  const TAG_LIMIT = 24
  const query = tagQuery.trim().toLowerCase()
  const matchedTags = query ? allTags.filter((t) => t.toLowerCase().includes(query)) : allTags
  const capped = showAllTags || query ? matchedTags : matchedTags.slice(0, TAG_LIMIT)
  const visibleTags =
    filters.tag && !capped.includes(filters.tag) && matchedTags.includes(filters.tag)
      ? [filters.tag, ...capped]
      : capped
  const hiddenCount = matchedTags.length - capped.length

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

  if (collapsed) return null

  return (
    <div className="flex h-full w-60 shrink-0 flex-col gap-5 overflow-y-auto border-r border-[--border] bg-[--surface-1] p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-tight text-[--text-primary]">{t('filters.title')}</h2>
        <button
          onClick={toggleCollapsed}
          title={t('filters.collapse')}
          aria-label={t('filters.collapse')}
          className="rounded p-1 text-[--text-muted] hover:bg-[--surface-2] hover:text-[--text-primary]"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24">
            <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
        </button>
      </div>

      {/* ── Roll type filter ─────────────────────────────── */}
      <div>
        <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-[--text-muted]">
          {t('filters.type')}
        </label>
        <div className="flex gap-1.5">
          {([
            ['all', t('filters.all'), (
              <svg key="i" className="h-3 w-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <rect x="1.5" y="1.5" width="4" height="4" rx="0.5" /><rect x="6.5" y="1.5" width="4" height="4" rx="0.5" />
                <rect x="1.5" y="6.5" width="4" height="4" rx="0.5" /><rect x="6.5" y="6.5" width="4" height="4" rx="0.5" />
              </svg>
            )],
            ['a', 'A-roll', (
              <svg key="i" className="h-3 w-3" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
                <path d="M6 1a1.5 1.5 0 0 0-1.5 1.5v2.5L3 6v3a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V6L7.5 5V2.5A1.5 1.5 0 0 0 6 1Z" />
              </svg>
            )],
            ['b', 'B-roll', (
              <svg key="i" className="h-3 w-3" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
                <rect x="1.5" y="2" width="9" height="8" rx="1" />
              </svg>
            )],
            ['photo', t('filters.photo'), (
              <svg key="i" className="h-3 w-3" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
                <rect x="1.5" y="2" width="9" height="8" rx="1" /><circle cx="4" cy="5" r="1" />
                <path d="M1.5 9l3-3 2 2 2-2 2.5 2.5" />
              </svg>
            )],
          ] as const).map(([value, label, icon]) => {
            const isActive = value === 'all' ? filters.roll_type === null : filters.roll_type === value
            return (
              <button
                key={value}
                onClick={() => updateFilter('roll_type', value === 'all' ? null : (value as 'a' | 'b' | 'photo'))}
                className={`flex flex-1 items-center justify-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  isActive ? 'bg-[--primary] text-white' : 'text-[--text-secondary] hover:bg-[--surface-2]'
                }`}
              >
                {icon}
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {/* ── Date filter (accordion) ─────────────────────── */}
      <div>
        <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-[--text-muted]">
          {t('filters.date')}
        </label>
        <select
          value={filters.date ?? ''}
          onChange={(e) => updateFilter('date', e.target.value || null)}
          className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-xs text-[--text-primary] outline-none transition-colors focus:border-[--primary]"
        >
          <option value="">{t('filters.allDates')}</option>
          {allDates.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>

      {/* ── Tag filter (searchable, capped chips) ───────── */}
      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <label className="text-xs font-medium uppercase tracking-wider text-[--text-muted]">
            {t('filters.tags')}
          </label>
          {allTags.length > 0 && (
            <span className="text-[10px] text-[--text-muted]">{allTags.length}</span>
          )}
        </div>

        {allTags.length === 0 ? (
          <p className="text-xs text-[--text-muted]">{t('filters.noTags')}</p>
        ) : (
          <>
            {/* Search — only worth showing once the list is long. */}
            {allTags.length > TAG_LIMIT && (
              <input
                type="text"
                value={tagQuery}
                onChange={(e) => setTagQuery(e.target.value)}
                placeholder={t('filters.searchTags')}
                className="mb-2 w-full rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-xs text-[--text-primary] placeholder:text-[--text-muted] outline-none transition-colors focus:border-[--primary]"
              />
            )}

            {visibleTags.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {visibleTags.map((tag) => (
                  <button
                    key={tag}
                    onClick={() => updateFilter('tag', filters.tag === tag ? null : tag)}
                    className={`max-w-full truncate rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors ${
                      filters.tag === tag
                        ? 'border-[--primary] bg-[--primary-soft] text-[--primary]'
                        : 'border-[--border] bg-[--surface-2] text-[--text-secondary] hover:border-[--border-strong]'
                    }`}
                    title={tag}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-[--text-muted]">{t('filters.noMatchingTags')}</p>
            )}

            {/* Show more / less — hidden while searching (search already trims). */}
            {!query && (hiddenCount > 0 || showAllTags) && matchedTags.length > TAG_LIMIT && (
              <button
                onClick={() => setShowAllTags((v) => !v)}
                className="mt-2 text-xs font-medium text-[--text-muted] hover:text-[--primary]"
              >
                {showAllTags ? t('filters.showLess') : t('filters.showAll', { n: matchedTags.length })}
              </button>
            )}
          </>
        )}
      </div>

      {/* ── Clear all button ───────────────────────────── */}
      {hasActiveFilters && (
        <button
          onClick={clearAll}
          className="mt-auto text-xs font-medium text-[--text-muted] underline hover:text-[--primary]"
        >
          {t('filters.clearAll')}
        </button>
      )}
    </div>
  )
}
