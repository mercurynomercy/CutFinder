/** Tests for the `cn()` utility — Tailwind class-name merger. */

import { describe, it, expect } from 'vitest'
import { cn } from '@/lib/cn'

describe('cn', () => {
  it('merges two static class strings, latter wins on conflict', () => {
    expect(cn('px-2 py-1 bg-red', 'bg-blue font-bold')).toBe('px-2 py-1 bg-blue font-bold')
  })

  it('handles conditional truthy/falsy values', () => {
    const a = true
    const b = false
    expect(cn('base', a && 'conditional-yes', b && 'conditional-no')).toBe('base conditional-yes')
  })

  it('handles arrays inside inputs', () => {
    expect(cn(['a b'], ['c d'])).toBe('a b c d')
  })

  it('ignores null/undefined values', () => {
    expect(cn(null, undefined, 'real-class')).toBe('real-class')
  })

  it('returns empty string when no classes provided', () => {
    expect(cn()).toBe('')
  })

  it('merges multiple conditional classes correctly', () => {
    const variant: string = 'danger'
    expect(cn('btn base', variant === 'primary' && 'bg-blue', variant === 'danger' && 'bg-red')).toBe('btn base bg-red')
  })
})
