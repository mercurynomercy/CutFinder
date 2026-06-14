/** Tailwind CSS class-name merger using clsx + tailwind-merge.

Combines static and dynamic className strings, merging Tailwind conflicts
so later classes always win (e.g. variant overrides).

Usage:
  cn('px-4 py-2', 'bg-red-500', isActive && 'bg-blue-500')
  → "px-4 py-2 bg-blue-500"
*/

import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: unknown[]): string {
  return twMerge(clsx(inputs))
}
