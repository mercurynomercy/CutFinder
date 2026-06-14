/** Tests for the Search feature — debounced search input with clear button. */

import { describe, it, expect } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Search } from '../index'

describe('Search', () => {
  it('renders an empty input field with placeholder text', async () => {
    render(<Search onSearch={() => {}} />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Search clips/i)).toBeInTheDocument()
    })
  })

  it('calls onSearch with query when text is entered and debounce fires', async () => {
    const handleSearch = vi.fn()
    render(<Search onSearch={handleSearch} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement

    // Simulate typing — debounce is 300ms, so we advance timers
    await act(async () => {
      userEvent.type(input, 'test query')
      // Advance past the 300ms debounce window
    })

    expect(handleSearch).toHaveBeenCalledWith('test query')
  })

  it('calls onSearch with empty string when clear button is clicked', async () => {
    const handleSearch = vi.fn()
    render(<Search onSearch={handleSearch} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement

    // Type some text first to make clear button appear
    await act(async () => { userEvent.type(input, 'test'); })

    // Clear button should now be visible
    const clearBtn = await screen.findByLabelText('Clear search') as HTMLButtonElement | null
    expect(clearBtn).toBeTruthy()

    // Click clear — should call onSearch with empty string
    await act(async () => { userEvent.click(clearBtn!); })

    expect(handleSearch).toHaveBeenCalledWith('')
  })

  it('shows clear button when input has content', async () => {
    render(<Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement

    // Initially, clear button should not be visible
    await waitFor(() => { expect(screen.queryByLabelText('Clear search')).not.toBeInTheDocument(); })

    // Type some text — clear button should appear
    await act(async () => { userEvent.type(input, 'x'); })

    const clearBtn = await screen.findByLabelText('Clear search') as HTMLButtonElement | null
    expect(clearBtn).toBeTruthy()
  })

  it('clears input when clear button is clicked', async () => {
    render(<Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement

    // Clear button is visible only when query has text
    await act(async () => { userEvent.type(input, 'test'); })

    const clearBtn = await screen.findByLabelText('Clear search') as HTMLButtonElement | null
    expect(clearBtn).toBeTruthy()

    await act(async () => { userEvent.click(clearBtn!); })
    expect(input.value).toBe('')
  })

  it('has magnifying glass icon SVG in the input wrapper', async () => {
    render(<Search onSearch={() => {}} />)
    await screen.findByPlaceholderText(/Search clips/i)
    const svg = document.querySelector('svg') as SVGElement | null
    expect(svg).toBeTruthy()
  })

  it('renders with relative class for icon positioning', async () => {
    render(<Search onSearch={() => {}} />)
    const wrapper = document.querySelector('div[class*="relative"]') as HTMLElement | null
    expect(wrapper).toBeTruthy()
  })

  it('renders input with bg-[--surface-2] background', async () => {
    render(<Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('bg-[--surface-2]')
  })

  it('renders input with rounded-md class', async () => {
    render(<Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('rounded-md')
  })

  it('renders input with pl-10 padding-left for icon', async () => {
    render(<Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('pl-10')
  })

  it('renders input with text-sm font size', async () => {
    render(<Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('text-sm')
  })

  it('renders input with w-full width', async () => {
    render(<Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('w-full')
  })

  it('renders input with border-border class', async () => {
    render(<Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('border-[--border]')
  })

  it('renders input with focus-visible:border-[--primary]', async () => {
    render(<Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('focus:border-[--primary]')
  })

  it('renders input with transition-colors class', async () => {
    render(<Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('transition-colors')
  })

  it('renders input with py-2 padding', async () => {
    render(<Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('py-2')
  })

  it('renders input with text-[--text-primary] class', async () => {
    render(<Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('text-[--text-primary]')
  })

  it('renders input with placeholder:text-[--text-muted]', async () => {
    render(<Search onSearch={() => {}} />)
    const input = await screen.findByPlaceholderText(/Search clips/i) as HTMLInputElement
    expect(input).toHaveClass('placeholder:text-[--text-muted]')
  })

})
