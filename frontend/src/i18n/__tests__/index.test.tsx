/** Tests for the UI i18n layer — default language, switching, persistence. */

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { LanguageProvider, useI18n } from '../index'

function Probe() {
  const { t, lang, setLang } = useI18n()
  return (
    <div>
      <span data-testid="lang">{lang}</span>
      <span data-testid="scan">{t('app.scan')}</span>
      <span data-testid="count">{t('gallery.clipsCount', { n: 3 })}</span>
      <button onClick={() => setLang('zh')}>to-zh</button>
      <button onClick={() => setLang('en')}>to-en</button>
    </div>
  )
}

describe('i18n', () => {
  beforeEach(() => localStorage.clear())

  it('defaults to English and interpolates vars', () => {
    render(<LanguageProvider><Probe /></LanguageProvider>)
    expect(screen.getByTestId('lang')).toHaveTextContent('en')
    expect(screen.getByTestId('scan')).toHaveTextContent('Scan')
    expect(screen.getByTestId('count')).toHaveTextContent('3 clips')
  })

  it('switches to Chinese and persists the choice', async () => {
    render(<LanguageProvider><Probe /></LanguageProvider>)
    await userEvent.click(screen.getByRole('button', { name: 'to-zh' }))

    expect(screen.getByTestId('scan')).toHaveTextContent('扫描')
    expect(screen.getByTestId('count')).toHaveTextContent('3 个片段')
    expect(localStorage.getItem('cutfinder:ui-lang')).toBe('zh')
  })

  it('reads the persisted language on mount', () => {
    localStorage.setItem('cutfinder:ui-lang', 'zh')
    render(<LanguageProvider><Probe /></LanguageProvider>)
    expect(screen.getByTestId('lang')).toHaveTextContent('zh')
    expect(screen.getByTestId('scan')).toHaveTextContent('扫描')
  })

  it('falls back to English when used without a provider', () => {
    render(<Probe />)
    expect(screen.getByTestId('scan')).toHaveTextContent('Scan')
  })
})
