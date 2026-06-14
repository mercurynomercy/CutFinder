/** Button component with variant variants (primary / secondary / ghost / danger).

Built with class-variance-authority for type-safe variant composition.
*/

import { cva, type VariantProps } from 'class-variance-authority'
import * as React from 'react'

import { cn } from '@/lib/cn'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium ' +
    'transition-colors focus-visible:outline-none focus-visible:ring-2 ' +
    'focus-visible:ring-offset-2 focus-visible:ring-[--primary] disabled:pointer-events-none',
  {
    variants: {
      variant: {
        primary: 'bg-[--primary] text-[--primary-fg] hover:bg-[--primary-hover]',
        secondary: 'bg-[--surface-2] text-[--text-primary] hover:bg-[--surface-3]',
        ghost: 'hover:bg-[--surface-2] text-[--text-secondary]',
        danger: 'bg-[--error] text-white hover:bg-red-600',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        md: 'h-9 px-4 py-2',
        lg: 'h-10 px-6 text-base',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  ),
)
Button.displayName = 'Button'

export { Button, buttonVariants }
