/** Filters feature — sidebar panel with date accordion, roll type filter, and tag chips.

Filters are applied client-side (the backend GET /clips supports date/roll_type/tag
query params; the frontend composes them and re-fetches via `onFilterChange`).

Usage:
  <Filters onFilterChange={(filters) => setAppliedFilters(filters)} />
*/

import { useEffect, useState } from 'react'

import { api } from '@/api/client'
import { Search } from '@/features/search'
import { useI18n } from '@/i18n'

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
  roll_type: 'a' | 'b' | 'photo' | null
  tag: string | null
}

const DEFAULT_FILTERS: FiltersState = { date: null, roll_type: null, tag: null }

// ── Main Filters component ──────────────────────────────────────

export interface FiltersProps {
  /** Called whenever any filter changes; receives the full filters object. */
  onFilterChange: (filters: FiltersState) => void
  /** Called with the current search query (the search box lives in the sidebar). */
  onSearch?: (query: string) => void
}

export function Filters({ onFilterChange, onSearch }: FiltersProps) {
  const { t } = useI18n()
  const [filters, setFilters] = useState<FiltersState>(DEFAULT_FILTERS)
  const [collapsed, setCollapsed] = useState(false)

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

  // Collapsed: a thin rail with an expand button (keeps the gallery roomy).
  if (collapsed) {
    return (
      <div className="flex h-full w-11 shrink-0 flex-col items-center border-r border-[--border] bg-[--surface-1] py-4">
        <button
          onClick={() => setCollapsed(false)}
          title={t('filters.expand')}
          aria-label={t('filters.expand')}
          className="relative rounded p-2 text-[--text-secondary] hover:bg-[--surface-2] hover:text-[--text-primary]"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24">
            <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 6h16.5M6.75 12h10.5m-7.5 6h4.5" />
          </svg>
          {hasActiveFilters && (
            <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-[--primary]" />
          )}
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-full w-64 shrink-0 flex-col gap-5 overflow-y-auto border-r border-[--border] bg-[--surface-1] p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-tight text-[--text-primary]">{t('filters.title')}</h2>
        <button
          onClick={() => setCollapsed(true)}
          title={t('filters.collapse')}
          aria-label={t('filters.collapse')}
          className="rounded p-1 text-[--text-muted] hover:bg-[--surface-2] hover:text-[--text-primary]"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24">
            <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
        </button>
      </div>

      {/* ── Search box ───────────────────────────────────── */}
      {onSearch && <Search onSearch={onSearch} />}

      {/* ── Roll type filter ─────────────────────────────── */}
      <div>
        <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-[--text-muted]">
          {t('filters.type')}
        </label>
        <div className="flex gap-1.5">
          {([['all', t('filters.all')], ['a', 'A-roll'], ['b', 'B-roll'], ['photo', t('filters.photo')]] as const).map(([value, label]) => {
            const isActive = value === 'all' ? filters.roll_type === null : filters.roll_type === value
            return (
              <button
                key={value}
                onClick={() => updateFilter('roll_type', value === 'all' ? null : (value as 'a' | 'b' | 'photo'))}
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
