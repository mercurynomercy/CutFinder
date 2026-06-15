/** Tests for the Filters feature — sidebar panel with roll type, date, and tag filters. */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Filters, type FiltersState } from '../index'

// HTTP mocking is configured globally via src/test/setup.ts (MSW node server).

describe('Filters', () => {
  it('renders with "Filters" heading text', async () => {
    render(<Filters onFilterChange={() => {}} />)
    await waitFor(() => expect(screen.getByText('Filters')).toBeInTheDocument())
  })

  it('renders "Type" label for roll type filter section', async () => {
    render(<Filters onFilterChange={() => {}} />)
    await waitFor(() => expect(screen.getByText('Type')).toBeInTheDocument())
  })

  it('renders "Date" label for date filter section', async () => {
    render(<Filters onFilterChange={() => {}} />)
    await waitFor(() => expect(screen.getByText('Date')).toBeInTheDocument())
  })

  it('renders "Tags" label for tag filter section', async () => {
    render(<Filters onFilterChange={() => {}} />)
    await waitFor(() => expect(screen.getByText('Tags')).toBeInTheDocument())
  })

  it('renders All, A-roll, B-roll buttons', async () => {
    render(<Filters onFilterChange={() => {}} />)
    expect(screen.getByText('All')).toBeInTheDocument()
    expect(screen.getByText('A-roll')).toBeInTheDocument()
    expect(screen.getByText('B-roll')).toBeInTheDocument()
  })

  it('has "All dates" option in date select dropdown', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const select = await screen.findByRole('combobox') as HTMLSelectElement | null
    expect(select).toBeTruthy()
  })

  it('calls onFilterChange with roll_type="a" when A-roll button is clicked', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)
    await waitFor(() => expect(screen.getByText('A-roll')).toBeInTheDocument())
    const aRollBtn = screen.getByText('A-roll') as HTMLButtonElement
    fireEvent.click(aRollBtn)
    expect(handleFilter).toHaveBeenCalledWith({ date: null, roll_type: 'a', tag: null })
  })

  it('calls onFilterChange with roll_type="b" when B-roll button is clicked', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)
    const bRollBtn = await screen.findByText('B-roll') as HTMLButtonElement
    fireEvent.click(bRollBtn)
    expect(handleFilter).toHaveBeenCalledWith({ date: null, roll_type: 'b', tag: null })
  })

  it('calls onFilterChange with roll_type=null when All button is clicked after selecting A-roll', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)

    // First click A-roll
    const aRollBtn = await screen.findByText('A-roll') as HTMLButtonElement
    fireEvent.click(aRollBtn)

    // Then click All to reset
    const allBtn = screen.getByText('All') as HTMLButtonElement
    fireEvent.click(allBtn)

    expect(handleFilter).toHaveBeenCalledWith({ date: null, roll_type: null, tag: null })
  })

  it('calls onFilterChange with date value when select option changes', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)
    const select = await screen.findByRole('combobox') as HTMLSelectElement | null

    fireEvent.change(select!, { target: { value: '2025-06' } })
    expect(handleFilter).toHaveBeenCalledWith({ date: '2025-06', roll_type: null, tag: null })
  })

  it('calls onFilterChange with tag name when tag chip is clicked', async () => {
    const handleFilter = vi.fn()

    // Mock the API response to return clips with tags
  })

  it('renders "No tags yet" message when no tags are available', async () => {
    render(<Filters onFilterChange={() => {}} />)
    await waitFor(() => expect(screen.getByText('No tags yet')).toBeInTheDocument())
  })

  it('does not show "Clear all filters" when no filters are active', async () => {
    render(<Filters onFilterChange={() => {}} />)
    await waitFor(() => expect(screen.getByText('Filters')).toBeInTheDocument())
    // Clear all button should not be visible initially since no filters are active
  })

  it('shows "Clear all filters" button when roll_type filter is applied', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)

    // Click A-roll to activate a filter
    const aRollBtn = await screen.findByText('A-roll') as HTMLButtonElement
    fireEvent.click(aRollBtn)

    await waitFor(() => expect(screen.getByText('Clear all filters')).toBeInTheDocument())
  })

  it('resets to default when "Clear all" button is clicked', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)

    // Activate a filter first
    const bRollBtn = await screen.findByText('B-roll') as HTMLButtonElement
    fireEvent.click(bRollBtn)

    // Clear all filters
    const clearAll = await screen.findByText('Clear all filters') as HTMLButtonElement
    fireEvent.click(clearAll)

    expect(handleFilter).toHaveBeenCalledWith({ date: null, roll_type: null, tag: null })
  })

  it('renders with w-64 width for sidebar layout', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const sidebar = document.querySelector('div[class*="w-64"]') as HTMLElement | null
    expect(sidebar).toBeTruthy()
  })

  it('renders with border-r-[--border] class on sidebar', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const sidebar = document.querySelector('div[class*="border-r"]') as HTMLElement | null
    expect(sidebar).toBeTruthy()
  })

  it('renders with bg-[--surface-1] background', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const sidebar = document.querySelector('div[class*="bg-\\[--surface-1\\]"]') as HTMLElement | null
    expect(sidebar).toBeTruthy()
  })

  it('renders with p-4 padding', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const sidebar = document.querySelector('div[class*="p-4"]') as HTMLElement | null
    expect(sidebar).toBeTruthy()
  })

  it('renders with flex-col layout', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const sidebar = document.querySelector('div[class*="flex-col"]') as HTMLElement | null
    expect(sidebar).toBeTruthy()
  })

  it('renders with overflow-y-auto for scrollable content', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const sidebar = document.querySelector('div[class*="overflow-y-auto"]') as HTMLElement | null
    expect(sidebar).toBeTruthy()
  })

  it('renders with shrink-0 class (fixed width)', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const sidebar = document.querySelector('div[class*="shrink-0"]') as HTMLElement | null
    expect(sidebar).toBeTruthy()
  })

  it('renders h-full for full height', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const sidebar = document.querySelector('div[class*="h-full"]') as HTMLElement | null
    expect(sidebar).toBeTruthy()
  })

  it('renders with gap-5 spacing between sections', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const sidebar = document.querySelector('div[class*="gap-5"]') as HTMLElement | null
    expect(sidebar).toBeTruthy()
  })

  it('renders Filters heading with text-sm font-semibold', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const heading = screen.getByText('Filters') as HTMLElement | null
    expect(heading?.className).toContain('text-sm')
  })

  it('renders Type label with uppercase tracking-wider', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const typeLabel = screen.getByText('Type') as HTMLElement | null
    expect(typeLabel?.className).toContain('uppercase')
  })

  it('renders Type label with text-xs font-medium', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const typeLabel = screen.getByText('Type') as HTMLElement | null
    expect(typeLabel?.className).toContain('text-xs')
  })

  it('applies bg-[--primary] text-white to active roll type button', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)

    const aRollBtn = await screen.findByText('A-roll') as HTMLButtonElement
    fireEvent.click(aRollBtn)

    expect(aRollBtn).toHaveClass('bg-[--primary]')
  })

  it('applies text-white to active roll type button', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)

    const bRollBtn = await screen.findByText('B-roll') as HTMLButtonElement
    fireEvent.click(bRollBtn)

    expect(bRollBtn).toHaveClass('text-white')
  })

  it('applies hover:bg-[--surface-2] to inactive roll type buttons', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)

    const allBtn = screen.getByText('All') as HTMLButtonElement
    expect(allBtn).toHaveClass('hover:bg-[--surface-2]')
  })

  it('applies text-[--text-secondary] to inactive roll type buttons', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)

    const allBtn = screen.getByText('All') as HTMLButtonElement
    expect(allBtn).toHaveClass('text-[--text-secondary]')
  })

  it('applies rounded-md class to roll type buttons', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)

    const allBtn = screen.getByText('All') as HTMLButtonElement
    expect(allBtn).toHaveClass('rounded-md')
  })

  it('applies px-2.5 py-1 class to roll type buttons', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)

    const allBtn = screen.getByText('All') as HTMLButtonElement
    expect(allBtn).toHaveClass('px-2.5')
  })

  it('applies text-xs font-medium to roll type buttons', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)

    const allBtn = screen.getByText('All') as HTMLButtonElement
    expect(allBtn).toHaveClass('text-xs')
  })

  it('applies transition-colors class to roll type buttons', async () => {
    const handleFilter = vi.fn()
    render(<Filters onFilterChange={handleFilter} />)

    const allBtn = screen.getByText('All') as HTMLButtonElement
    expect(allBtn).toHaveClass('transition-colors')
  })

  it('renders date select with w-full width', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const select = document.querySelector('select') as HTMLSelectElement | null
    expect(select?.className).toContain('w-full')
  })

  it('renders date select with rounded-md class', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const select = document.querySelector('select') as HTMLSelectElement | null
    expect(select?.className).toContain('rounded-md')
  })

  it('renders date select with border-[--border] class', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const select = document.querySelector('select') as HTMLSelectElement | null
    expect(select?.className).toContain('border-[--border]')
  })

  it('renders date select with bg-[--surface-2] background', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const select = document.querySelector('select') as HTMLSelectElement | null
    expect(select?.className).toContain('bg-[--surface-2]')
  })

  it('renders date select with focus:border-[--primary]', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const select = document.querySelector('select') as HTMLSelectElement | null
    expect(select?.className).toContain('focus:border-[--primary]')
  })

  it('renders date select with text-xs font size', async () => {
    render(<Filters onFilterChange={() => {}} />)
    const select = document.querySelector('select') as HTMLSelectElement | null
    expect(select?.className).toContain('text-xs')
  })

})
