/** Tests for the Filters feature — behavior-focused (interactions + callbacks). */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { Filters } from '../index'
import { server } from '@/test/mocks/server'

/** Override GET /api/clips with one clip carrying many auto tags. */
function mockManyTags(count: number) {
  const tags = Array.from({ length: count }, (_, i) => ({
    name: `tag${String(i).padStart(3, '0')}`,
    source: 'auto' as const,
  }))
  server.use(
    http.get('http://localhost:5080/api/clips', () =>
      HttpResponse.json([
        { id: 1, source_path: '/a.mp4', roll_type: 'a', duration_s: 1, thumbnail_path: null, status: 'done', tags },
      ]),
    ),
  )
}

/** Override GET /api/clips with clips spread across two months. */
function mockDatedClips() {
  server.use(
    http.get('http://localhost:5080/api/clips', () =>
      HttpResponse.json([
        { id: 1, source_path: '/a.mp4', roll_type: 'a', duration_s: 1, thumbnail_path: null, status: 'done', tags: [], capture_time: '2016-08-31T00:00:00Z' },
        { id: 2, source_path: '/b.mp4', roll_type: 'a', duration_s: 1, thumbnail_path: null, status: 'done', tags: [], capture_time: '2016-08-31T00:00:00Z' },
        { id: 3, source_path: '/c.mp4', roll_type: 'a', duration_s: 1, thumbnail_path: null, status: 'done', tags: [], capture_time: '2016-07-01T00:00:00Z' },
      ]),
    ),
  )
}

describe('Filters', () => {
  it('renders the heading and roll-type buttons', () => {
    render(<Filters onFilterChange={() => {}} />)
    expect(screen.getByText('Filters')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'A-roll' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'B-roll' })).toBeInTheDocument()
  })

  it('emits roll_type="a" when A-roll is clicked', async () => {
    const onChange = vi.fn()
    render(<Filters onFilterChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: 'A-roll' }))
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ roll_type: 'a' }))
  })

  it('clears roll_type when All is clicked', async () => {
    const onChange = vi.fn()
    render(<Filters onFilterChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: 'A-roll' }))
    await userEvent.click(screen.getByRole('button', { name: 'All' }))
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ roll_type: null }))
  })

  it('shows a placeholder when there are no tags', () => {
    render(<Filters onFilterChange={() => {}} />)
    expect(screen.getByText('No tags yet')).toBeInTheDocument()
  })

  it('caps a long tag list and reveals the rest via "Show all"', async () => {
    mockManyTags(40)
    render(<Filters onFilterChange={() => {}} />)

    // First 24 (frequency/alpha order) shown; tag030 is initially hidden.
    await screen.findByRole('button', { name: 'tag000' })
    expect(screen.queryByRole('button', { name: 'tag030' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Show all 40' }))
    expect(screen.getByRole('button', { name: 'tag030' })).toBeInTheDocument()
  })

  it('filters tags by the search box', async () => {
    mockManyTags(40)
    render(<Filters onFilterChange={() => {}} />)

    const search = await screen.findByPlaceholderText('Search tags…')
    await userEvent.type(search, 'tag039')

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'tag039' })).toBeInTheDocument(),
    )
    expect(screen.queryByRole('button', { name: 'tag000' })).not.toBeInTheDocument()
  })

  it('reveals "Clear all filters" after a filter is active and resets on click', async () => {
    const onChange = vi.fn()
    render(<Filters onFilterChange={onChange} />)
    expect(screen.queryByText('Clear all filters')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'B-roll' }))
    await userEvent.click(await screen.findByText('Clear all filters'))

    expect(onChange).toHaveBeenLastCalledWith({ date: null, roll_type: null, tag: null })
  })

  it('renders an icon inside each type-filter button', () => {
    render(<Filters onFilterChange={() => {}} />)
    for (const name of ['All', 'A-roll', 'B-roll', 'Photo']) {
      const btn = screen.getByRole('button', { name })
      expect(btn.querySelector('svg')).toBeTruthy()
    }
  })

  it('does not render its own search box (search lives in the top bar now)', () => {
    render(<Filters onFilterChange={() => {}} />)
    expect(screen.queryByPlaceholderText('Search clips…')).not.toBeInTheDocument()
  })

  it('renders nothing visible and calls onToggleCollapsed when controlled collapsed=true', () => {
    const onToggle = vi.fn()
    render(<Filters onFilterChange={() => {}} collapsed onToggleCollapsed={onToggle} />)
    expect(screen.queryByText('Filters')).not.toBeInTheDocument()
  })

  it('calls onToggleCollapsed (not internal state) when the collapse button is clicked in controlled mode', async () => {
    const onToggle = vi.fn()
    render(<Filters onFilterChange={() => {}} collapsed={false} onToggleCollapsed={onToggle} />)
    await userEvent.click(screen.getByLabelText('Collapse filters'))
    expect(onToggle).toHaveBeenCalledTimes(1)
    // Still rendered — collapse is controlled by the parent, not internal state.
    expect(screen.getByText('Filters')).toBeInTheDocument()
  })

  it('groups dates by month with a per-month count, collapsed by default', async () => {
    mockDatedClips()
    render(<Filters onFilterChange={() => {}} />)
    expect(await screen.findByRole('button', { name: /2016-08/ })).toHaveTextContent('2')
    expect(screen.queryByRole('button', { name: '2016-08-31' })).not.toBeInTheDocument()
  })

  it('expands a month to reveal its days, and selecting a day filters by exact date', async () => {
    mockDatedClips()
    const onChange = vi.fn()
    render(<Filters onFilterChange={onChange} />)
    await userEvent.click(await screen.findByRole('button', { name: /2016-08/ }))
    const dayBtn = await screen.findByRole('button', { name: '2016-08-31' })
    await userEvent.click(dayBtn)
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ date: '2016-08-31' }))
  })

  it('shows the "no dates" message when there are no clips', () => {
    render(<Filters onFilterChange={() => {}} />)
    expect(screen.getByText('No dates yet')).toBeInTheDocument()
  })

  it('reflects a controlled `filters` prop (e.g. after a remount) by highlighting the matching roll-type button', () => {
    render(
      <Filters
        onFilterChange={() => {}}
        filters={{ date: null, roll_type: 'a', tag: null }}
      />,
    )
    expect(screen.getByRole('button', { name: 'A-roll' })).toHaveClass('bg-[--primary]')
    expect(screen.getByRole('button', { name: 'All' })).not.toHaveClass('bg-[--primary]')
    // "Clear all filters" should also show, since the controlled value is non-default.
    expect(screen.getByText('Clear all filters')).toBeInTheDocument()
  })
})
