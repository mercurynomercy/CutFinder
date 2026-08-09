/** Rough-cut settings page — full-screen layout per OpenDesign spec.
 *
 * Replaces the modal that lived inside CutplanPage. Presents the same
 * generation options and director prompt editor in a centered card.
 *
 * Usage:
 *   <RoughCutSettingsPage
 *     onClose={() => setShowCutplanSettings(false)}
 *     theme={theme}
 *     onToggleTheme={toggleTheme}
 *   />
 */

import { useEffect, useState } from 'react'

import { api } from '@/api/client'
import { useI18n } from '@/i18n'
import type { Theme } from '@/theme'

export interface RoughCutSettingsPageProps {
  onClose: () => void
  theme: Theme
  onToggleTheme: () => void
}

export function RoughCutSettingsPage({ onClose, theme, onToggleTheme }: RoughCutSettingsPageProps) {
  const { t } = useI18n()

  // Generation options
  const [directorMode, setDirectorMode] = useState<'agent' | 'staged'>('agent')
  const [maxToolRounds, setMaxToolRounds] = useState(24)
  const [criticEnabled, setCriticEnabled] = useState(false)
  const [visionBudget, setVisionBudget] = useState(6)
  const [leanTokenBudget, setLeanTokenBudget] = useState(50000)
  const [stagedTokenBudget, setStagedTokenBudget] = useState(40000)

  // Director prompt
  const [promptText, setPromptText] = useState('')
  const [promptIsDefault, setPromptIsDefault] = useState(true)
  const [promptSaved, setPromptSaved] = useState(false)

  // Load current values on mount
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const r = await api.getCutPrompt()
        if (!cancelled) {
          setPromptText(r.prompt)
          setPromptIsDefault(r.is_default)
        }
      } catch (err) {
        console.error('Load director prompt failed:', err)
      }
      try {
        const data = await api.getSettings()
        if (!cancelled) {
          setDirectorMode(data.prefs.cut_director_mode ?? 'agent')
          setMaxToolRounds(data.prefs.cut_max_tool_rounds ?? 24)
          setCriticEnabled(data.prefs.cut_critic_enabled ?? false)
          setVisionBudget(data.prefs.cut_vision_budget ?? 6)
          setLeanTokenBudget(data.prefs.cut_lean_token_budget ?? 50000)
          setStagedTokenBudget(data.prefs.cut_staged_token_budget ?? 40000)
        }
      } catch {
        /* no library bound / unreachable — keep defaults */
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSave = async () => {
    try {
      const r = await api.setCutPrompt(promptText)
      setPromptText(r.prompt)
      setPromptIsDefault(r.is_default)
      await api.putSettings({
        cut_director_mode: directorMode,
        cut_max_tool_rounds: maxToolRounds,
        cut_critic_enabled: criticEnabled,
        cut_vision_budget: visionBudget,
        cut_lean_token_budget: leanTokenBudget,
        cut_staged_token_budget: stagedTokenBudget,
      })
      setPromptSaved(true)
      setTimeout(() => setPromptSaved(false), 1500)
    } catch (err) {
      console.error('Save rough-cut settings failed:', err)
    }
  }

  const handleReset = async () => {
    try {
      const r = await api.resetCutPrompt()
      setPromptText(r.prompt)
      setPromptIsDefault(r.is_default)
    } catch (err) {
      console.error('Reset director prompt failed:', err)
    }
  }

  return (
    <div className="flex h-screen w-full flex-col bg-[--bg-canvas] text-[--text-primary]">
      {/* ── Top Bar ─────────────────────────────── */}
      <header className="flex h-12 shrink-0 items-center border-b border-[--border] bg-[--surface-1] px-4">
        <h1 className="text-lg font-semibold tracking-tight">{t('roughcut.settingsTitle')}</h1>
        <span className="flex-1" />
        <button
          onClick={onToggleTheme}
          className="rounded-md p-1.5 text-[--text-secondary] hover:bg-[--surface-3] transition-colors"
          aria-label={theme === 'dark' ? t('app.themeToLight') : t('app.themeToDark')}
        >
          {theme === 'dark' ? (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
              <circle cx="8" cy="8" r="3" />
              <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.1 3.1l1.4 1.4M11.5 11.5l1.4 1.4M12.9 3.1l-1.4 1.4M4.5 11.5l-1.4 1.4" />
            </svg>
          ) : (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
              <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7Z" />
            </svg>
          )}
        </button>
        <button
          onClick={onClose}
          className="rounded-md p-1.5 text-[--text-secondary] hover:bg-[--surface-3] transition-colors"
          aria-label={t('roughcut.close')}
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4l8 8M12 4l-8 8" />
          </svg>
        </button>
      </header>

      {/* ── Main Content ────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-[640px] rounded-lg border border-[--border] bg-[--surface-1] overflow-hidden">
          {/* Card header */}
          <div className="flex items-center justify-between border-b border-[--border] px-6 py-4">
            <span className="text-sm font-semibold">{t('roughcut.settingsTitle')}</span>
            <span className={`text-xs ${promptIsDefault ? 'text-[--text-muted]' : 'text-[--primary]'}`}>
              {promptIsDefault ? t('roughcut.promptDefault') : t('roughcut.promptCustom')}
            </span>
          </div>

          {/* Card body */}
          <div className="px-6 py-6">
            {/* ── Generation Options ──────────────── */}
            <div className="mb-6">
              <div className="mb-3 text-sm font-semibold text-[--text-secondary] tracking-wide">{t('roughcut.genOptions')}</div>

              {/* Generation mode */}
              <div className="mb-5">
                <label className="block text-sm font-medium text-[--text-primary] mb-1.5" htmlFor="gen-mode">
                  {t('roughcut.directorMode')}
                </label>
                <select
                  id="gen-mode"
                  value={directorMode}
                  onChange={(e) => setDirectorMode(e.target.value as 'agent' | 'staged')}
                  className="w-full h-9 px-3 bg-[--surface-2] border border-[--border] rounded-md text-sm text-[--text-primary] outline-none cursor-pointer transition-colors focus:border-[--primary] focus:shadow-[0_0_0_2px_var(--primary-soft)] hover:border-[--border-strong] appearance-none"
                  style={{
                    backgroundImage: `url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1L5 5L9 1' stroke='%236B7280' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")`,
                    backgroundRepeat: 'no-repeat',
                    backgroundPosition: 'right 12px center',
                    paddingRight: '32px',
                  }}
                >
                  <option value="agent">{t('roughcut.modeAgent')}</option>
                  <option value="staged">{t('roughcut.modeStaged')}</option>
                </select>
                <div className="text-xs text-[--text-secondary] mt-1 leading-relaxed">
                  {t('roughcut.directorModeDesc')}
                </div>
              </div>

              {/* Max tool rounds (agent only) */}
              {directorMode === 'agent' && (
                <>
                  <div className="mb-5">
                    <label className="block text-sm font-medium text-[--text-primary] mb-1.5">
                      {t('roughcut.maxRounds')}
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={200}
                      value={maxToolRounds}
                      onChange={(e) => setMaxToolRounds(parseInt(e.target.value, 10) || 1)}
                      className="w-[120px] h-9 text-center font-mono text-sm bg-[--surface-2] border border-[--border] rounded-md text-[--text-primary] outline-none transition-colors focus:border-[--primary] focus:shadow-[0_0_0_2px_var(--primary-soft)]"
                    />
                    <div className="text-xs text-[--text-secondary] mt-1 leading-relaxed">
                      {t('roughcut.maxRoundsDesc')}
                    </div>
                  </div>

                  {/* Per-day catalog size (agent) */}
                  <div className="mb-5">
                    <label className="block text-sm font-medium text-[--text-primary] mb-1.5">
                      {t('roughcut.leanBudget')}
                    </label>
                    <input
                      type="number"
                      min={1000}
                      max={200000}
                      step={1000}
                      value={leanTokenBudget}
                      onChange={(e) => setLeanTokenBudget(parseInt(e.target.value, 10) || 1000)}
                      className="w-[120px] h-9 text-center font-mono text-sm bg-[--surface-2] border border-[--border] rounded-md text-[--text-primary] outline-none transition-colors focus:border-[--primary] focus:shadow-[0_0_0_2px_var(--primary-soft)]"
                    />
                    <div className="text-xs text-[--text-secondary] mt-1 leading-relaxed">
                      {t('roughcut.leanBudgetDesc')}
                    </div>
                  </div>
                </>
              )}

              {/* Critic review pass */}
              <div className="mb-5">
                <label className="flex items-start gap-2.5 cursor-pointer select-none">
                  <span className="relative w-[18px] h-[18px] flex-shrink-0 mt-0.5">
                    <input
                      type="checkbox"
                      checked={criticEnabled}
                      onChange={(e) => setCriticEnabled(e.target.checked)}
                      className="absolute opacity-0 w-full h-full cursor-pointer z-1 m-0"
                    />
                    <span
                      className={`w-[18px] h-[18px] rounded-[4px] flex items-center justify-center transition-all duration-150 border ${
                        criticEnabled
                          ? 'bg-[--primary] border-[--primary]'
                          : 'border-[--border-strong] bg-transparent'
                      }`}
                    >
                      <svg
                        className="w-3 h-3 text-[--primary-fg]"
                        style={{ opacity: criticEnabled ? 1 : 0, transition: 'opacity 150ms' }}
                        viewBox="0 0 12 12"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <path d="M2.5 6.5L5 8.5L9.5 3.5" />
                      </svg>
                    </span>
                  </span>
                  <div>
                    <div className="text-sm font-medium text-[--text-primary]">{t('roughcut.critic')}</div>
                    <div className="text-xs text-[--text-secondary] leading-relaxed mt-0.5">
                      {t('roughcut.criticDesc')}
                    </div>
                  </div>
                </label>
              </div>

              {/* Vision look-ups */}
              <div className="mb-5">
                <label className="block text-sm font-medium text-[--text-primary] mb-1.5">
                  {t('roughcut.visionBudget')}
                </label>
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={visionBudget}
                  onChange={(e) => setVisionBudget(parseInt(e.target.value, 10) || 0)}
                  className="w-[120px] h-9 text-center font-mono text-sm bg-[--surface-2] border border-[--border] rounded-md text-[--text-primary] outline-none transition-colors focus:border-[--primary] focus:shadow-[0_0_0_2px_var(--primary-soft)]"
                />
                <div className="text-xs text-[--text-secondary] mt-1 leading-relaxed">
                  {t('roughcut.visionBudgetDesc')}
                </div>
              </div>

              {/* Per-day catalog size (fast) */}
              <div>
                <label className="block text-sm font-medium text-[--text-primary] mb-1.5">
                  {t('roughcut.stagedBudget')}
                </label>
                <input
                  type="number"
                  min={1000}
                  max={200000}
                  step={1000}
                  value={stagedTokenBudget}
                  onChange={(e) => setStagedTokenBudget(parseInt(e.target.value, 10) || 1000)}
                  className="w-[120px] h-9 text-center font-mono text-sm bg-[--surface-2] border border-[--border] rounded-md text-[--text-primary] outline-none transition-colors focus:border-[--primary] focus:shadow-[0_0_0_2px_var(--primary-soft)]"
                />
                <div className="text-xs text-[--text-secondary] mt-1 leading-relaxed">
                  {t('roughcut.stagedBudgetDesc')}
                </div>
              </div>
            </div>

            {/* Divider */}
            <div className="border-t border-[--border] my-6" />

            {/* ── Director Prompt ─────────────────── */}
            <div>
              <div className="mb-2 text-sm font-semibold text-[--text-secondary] tracking-wide">
                {t('roughcut.promptSection')}
              </div>
              <div className="text-xs text-[--text-secondary] mb-1.5">
                {t('roughcut.promptHelp')}
              </div>
              <textarea
                value={promptText}
                onChange={(e) => setPromptText(e.target.value)}
                rows={12}
                spellCheck={false}
                className="w-full min-h-[180px] p-3 bg-[--surface-2] border border-[--border] rounded-md text-xs text-[--text-primary] outline-none resize-y leading-relaxed transition-colors focus:border-[--primary] focus:shadow-[0_0_0_2px_var(--primary-soft)]"
              />
            </div>
          </div>

          {/* Card footer */}
          <div className="flex items-center justify-between border-t border-[--border] px-6 py-4 bg-[--surface-1]">
            <button
              onClick={handleReset}
              className="h-9 px-4 text-sm font-medium rounded-md border border-[--border] bg-[--surface-2] text-[--text-secondary] hover:bg-[--surface-3] transition-colors"
            >
              {t('roughcut.reset')}
            </button>
            <div className="flex gap-2">
              <button
                onClick={onClose}
                className="h-9 px-4 text-sm font-medium rounded-md border border-[--border] bg-[--surface-2] text-[--text-secondary] hover:bg-[--surface-3] transition-colors"
              >
                {t('roughcut.cancel')}
              </button>
              <button
                onClick={handleSave}
                className="h-9 px-5 text-sm font-semibold rounded-md bg-[--primary] text-[--primary-fg] hover:bg-[--primary-hover] transition-colors"
              >
                {promptSaved ? t('roughcut.saved') : t('roughcut.save')}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
