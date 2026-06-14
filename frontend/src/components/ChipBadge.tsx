/** Chip and Badge components for roll type display + source indicators.

- **Badge**: Small pill showing A-roll (amber) or B-roll (teal).
- **Chip**: Tag-style pill with optional auto/manual dot indicator.
*/

import * as React from 'react'

import { cn } from '@/lib/cn'

// ── Badge (A/B roll type) ────────────────────────────────────────

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** `'a'` or `'b'` — determines color */
  type: 'a' | 'b'
}

export function Badge({ className, type, children, ...props }: BadgeProps) {
  const isA = type === 'a'
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
        isA ? 'bg-[--roll-a-soft] text-[--roll-a]' : 'bg-[--roll-b-soft] text-[--roll-b]',
        className,
      )}
      {...props}
    >
      {isA ? 'A' : 'B'}
      {children && <span className="ml-1">{children}</span>}
    </span>
  )
}

// ── Chip (tag-style with source dot) ─────────────────────────────

export interface ChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Source label shown as a dot before the tag name */
  source?: 'auto' | 'manual'
}

export function Chip({ className, source = 'auto', children, ...props }: ChipProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border border-[--border] bg-[--surface-2]',
        'px-2.5 py-0.5 text-xs font-medium text-[--text-secondary] transition-colors',
        'hover:border-[--border-strong]',
        className,
      )}
      {...props}
    >
      {/* Source dot */}
      <span
        className={cn(
          'inline-block h-1.5 w-1.5 rounded-full',
          source === 'auto' ? 'bg-[--text-muted]' : 'bg-[--primary]',
        )}
      />
      {children}
    </span>
  )
}
