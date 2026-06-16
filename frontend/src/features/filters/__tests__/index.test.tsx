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
})
