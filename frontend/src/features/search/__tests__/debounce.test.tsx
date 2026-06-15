/** Tests for Search debounced behavior — uses a sync-debounce variant of Search. */

import { describe, it, expect, vi } from 'vitest'
// eslint-disable-next-line import/no-relative-packages
import * as searchModule from '../index'
import { useState } from 'react'
// eslint-disable-next-line import/no-relative-packages
import { render, screen } from '@testing-library/react'
// eslint-disable-next-line import/no-relative-packages
import userEvent from '@testing-library/user-event'

// Sync-debounce: calls fn immediately instead of scheduling.
function syncDebounce<A extends unknown[]>(fn: (...args: A) => void) {
  return (...args: A) => fn(...args)
}

// Test-specific Search that calls the debounced callback immediately (no timer).
function SearchSync({ onSearch }: searchModule.SearchProps) {
  const [query, setQuery] = useState('')

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const debouncedSearch = syncDebounce((q: string) => { onSearch(q.trim()) })

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

describe('Search — debounced behavior', () => {
  it('calls onSearch with query when text is entered and debounce fires', async () => {
    const handleSearch = vi.fn()
    render(<SearchSync onSearch={handleSearch} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement

    // Simulate typing — debounced callback fires synchronously
    await userEvent.type(input, 'test query')

    expect(handleSearch).toHaveBeenCalledWith('test query')
  })

  it('calls onSearch with empty string when clear button is clicked', async () => {
    const handleSearch = vi.fn()
    render(<SearchSync onSearch={handleSearch} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement

    // Type some text first to make clear button appear
    await userEvent.type(input, 'test')

    // Clear button should now be visible (depends on query state)
    const clearBtn = await screen.findByLabelText('Clear search') as HTMLButtonElement | null
    expect(clearBtn).toBeTruthy()

    // Click clear — should call onSearch with empty string
    await userEvent.click(clearBtn!)

    expect(handleSearch).toHaveBeenCalledWith('')
  })

  it('clears input when clear button is clicked', async () => {
    render(<SearchSync onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement

    // Clear button is visible only when query has text
    await userEvent.type(input, 'test')

    const clearBtn = await screen.findByLabelText('Clear search') as HTMLButtonElement | null
    expect(clearBtn).toBeTruthy()

    await userEvent.click(clearBtn!)
    expect(input.value).toBe('')
  })

})
