/** Tests for the Search feature — debounced search input with clear button. */

import { describe, it, expect } from 'vitest'
// eslint-disable-next-line import/no-relative-packages
import * as searchModule from '../index'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

describe('Search', () => {
  it('renders an empty input field with placeholder text', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    expect(await screen.findByPlaceholderText(/Search clips/i)).toBeInTheDocument()
  })

  it('shows clear button when input has content', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement

    // Initially, clear button should not be visible
    expect(screen.queryByLabelText('Clear search')).not.toBeInTheDocument()

    // Type some text — clear button should appear
    await userEvent.type(input, 'x')

    const clearBtn = await screen.findByLabelText('Clear search') as HTMLButtonElement | null
    expect(clearBtn).toBeTruthy()
  })

  it('has magnifying glass icon SVG in the input wrapper', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    await screen.findByPlaceholderText(/Search clips/i)
    const svg = document.querySelector('svg') as SVGElement | null
    expect(svg).toBeTruthy()
  })

  it('renders with relative class for icon positioning', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    const wrapper = document.querySelector('div[class*="relative"]') as HTMLElement | null
    expect(wrapper).toBeTruthy()
  })

  it('renders input with bg-[--surface-2] background', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('bg-[--surface-2]')
  })

  it('renders input with rounded-md class', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('rounded-md')
  })

  it('renders input with pl-10 padding-left for icon', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('pl-10')
  })

  it('renders input with text-sm font size', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('text-sm')
  })

  it('renders input with w-full width', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('w-full')
  })

  it('renders input with border-border class', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('border-[--border]')
  })

  it('renders input with focus-visible:border-[--primary]', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('focus:border-[--primary]')
  })

  it('renders input with transition-colors class', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('transition-colors')
  })

  it('renders input with py-2 padding', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('py-2')
  })

  it('renders input with text-[--text-primary] class', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('text-[--text-primary]')
  })

  it('renders input with placeholder:text-[--text-muted]', async () => {
    render(<searchModule.Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('placeholder:text-[--text-muted]')
  })

})
