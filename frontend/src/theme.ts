/** Light (default) / dark theme switching, persisted to localStorage. */
export type Theme = 'light' | 'dark'

const KEY = 'cutfinder-theme'

/** Stored preference, defaulting to light when unset/invalid. */
export function getStoredTheme(): Theme {
  return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light'
}

/** Apply a theme to <html> and persist it. */
export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme)
  localStorage.setItem(KEY, theme)
}
