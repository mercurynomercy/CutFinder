/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Surface tokens from design system
        canvas: 'var(--bg-canvas)',
        surface1: 'var(--surface-1)',
        surface2: 'var(--surface-2)',
        surface3: 'var(--surface-3)',
        border: 'var(--border)',
        'border-strong': 'var(--border-strong)',
      },
      textColor: {
        primary: 'var(--text-primary)',
        secondary: 'var(--text-secondary)',
        muted: 'var(--text-muted)',
      },
      borderColor: {
        border: 'var(--border)',
        'border-strong': 'var(--border-strong)',
      },
      backgroundColor: {
        primary: 'var(--primary)',
        'primary-hover': 'var(--primary-hover)',
        'primary-press': 'var(--primary-press)',
        'primary-soft': 'var(--primary-soft)',
        'roll-a': 'var(--roll-a)',
        'roll-a-soft': 'var(--roll-a-soft)',
        'roll-b': 'var(--roll-b)',
        'roll-b-soft': 'var(--roll-b-soft)',
      },
      fontFamily: {
        sans: ['Inter', 'var(--font-sans)'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
