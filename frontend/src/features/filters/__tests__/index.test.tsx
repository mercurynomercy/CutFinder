/** Tests for the Filters feature — behavior-focused (interactions + callbacks). */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Filters } from '../index'

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

  it('reveals "Clear all filters" after a filter is active and resets on click', async () => {
    const onChange = vi.fn()
    render(<Filters onFilterChange={onChange} />)
    expect(screen.queryByText('Clear all filters')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'B-roll' }))
    await userEvent.click(await screen.findByText('Clear all filters'))

    expect(onChange).toHaveBeenLastCalledWith({ date: null, roll_type: null, tag: null })
  })
})
