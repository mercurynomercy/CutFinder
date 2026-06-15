/** Search feature — search bar with magnifying glass icon and clear button.

Provides a debounced full-text search input that calls `onSearch` with the
query string. An empty query (clear) resets to an empty string.

Usage:
  <Search onSearch={(query) => setSearchQuery(query)} />
*/

import { useEffect, useState } from 'react'

// ── Search bar component ────────────────────────────────────────

export interface SearchProps {
  /** Called with the current query string (may be empty). */
  onSearch: (query: string) => void
}

/** Debounce helper — returns a function that only calls `fn` after `ms` ms
 *  of inactivity. */
export function useDebounce<T extends (...args: unknown[]) => void>(fn: T, ms: number): T {
  const [timer, setTimer] = useState<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const cb = fn as (...args: unknown[]) => void // type widening for setTimeout compatibility
    return () => { if (timer) clearTimeout(timer) }
  }, [])

  // eslint-disable-next-line func-names
  const debounced = function (...args: Parameters<T>) {
    if (timer) clearTimeout(timer)
    setTimer(setTimeout(() => fn(...args), ms))
  } as T

  return debounced
}

export function Search({ onSearch }: SearchProps) {
  const [query, setQuery] = useState('')

  // Debounced search — fires 300ms after the user stops typing
  const debouncedSearch = useDebounce((q: string) => {
    onSearch(q.trim())
  }, 300)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setQuery(value)
    debouncedSearch(value.trim())
  }

  const handleClear = () => {
    setQuery('')
    onSearch('')
  }

  return (
    <div className="relative flex w-full max-w-md">
      {/* Magnifying glass icon */}
      <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[--text-muted]" fill="none" viewBox="0 0 24 24">
        <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
      </svg>

      <input
        type="text"
        value={query}
        onChange={handleChange}
        placeholder="Search clips…"
        className="w-full rounded-md border border-[--border] bg-[--surface-2] pl-10 pr-9 py-2 text-sm text-[--text-primary] placeholder:text-[--text-muted] outline-none transition-colors focus:border-[--primary]"
      />

      {/* Clear button (only visible when there's text) */}
      {query && (
        <button
          onClick={handleClear}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-[--text-muted] hover:text-[--text-primary]"
          aria-label="Clear search"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24">
            <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  )
}
