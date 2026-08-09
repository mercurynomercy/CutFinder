/** Settings feature — configuration page for source/library folders, model selectors,
extension whitelist, B-roll frame count, and VAD threshold with validation.

Fetches current settings from GET /api/settings on mount and saves via PUT /api/settings
on form submission.  All fields have basic validation (required, min/max, type checks).

Usage:
  <SettingsPage onSave={(prefs) => handleSave(prefs)} />
*/

import { useCallback, useEffect, useState } from 'react'

import type { UpdateSettingsBody } from '@/api/client'
import { api } from '@/api/client'
import { Button, ConfirmDialog } from '@/components'
import { useI18n } from '@/i18n'

// ── Validation helpers ────────────────────────────────────────────

interface FieldError {
  field: string
  messageKey: 'settings.validationInt' | 'settings.validationNum'
}

function validatePrefs(prefs: UpdateSettingsBody): FieldError[] {
  const errors: FieldError[] = []

  if (prefs.broll_frame_count !== undefined) {
    const v = prefs.broll_frame_count as number
    if (!Number.isInteger(v) || v < 1) {
      errors.push({ field: 'broll_frame_count', messageKey: 'settings.validationInt' })
    }
  }

  if (prefs.vad_threshold !== undefined) {
    const v = prefs.vad_threshold as number
    if (typeof v !== 'number' || isNaN(v) || v <= 0 || v > 1) {
      errors.push({ field: 'vad_threshold', messageKey: 'settings.validationNum' })
    }
  }

  return errors
}

// ── Folder picker (native macOS dialog via backend osascript) ───
// A browser <input webkitdirectory> only exposes the folder *name*
// (webkitRelativePath), never an absolute path — useless for a local tool
// that resolves real filesystem paths. So we ask the backend to open a native
// macOS chooser (POST /api/pick-folder) which returns the absolute path.

interface FolderPickerButtonProps {
  label: string
  icon?: React.ReactNode | null
  onChange: (folderPath: string) => void
}

function FolderPickerButton({ label, icon = null, onChange }: FolderPickerButtonProps) {
  const [picking, setPicking] = useState(false)

  const handlePick = async () => {
    setPicking(true)
    try {
      const { path } = await api.pickFolder()
      if (path) onChange(path) // null = user cancelled the dialog
    } catch {
      // backend unreachable / non-macOS — silently ignore
    } finally {
      setPicking(false)
    }
  }

  return (
    <button
      type="button"
      onClick={handlePick}
      disabled={picking}
      aria-label={label}
      className="inline-flex items-center justify-center rounded-md border border-[--border] bg-[--surface-2] px-2 py-1 text-[--text-secondary] transition-colors hover:bg-[--surface-3]"
    >
      {icon}
    </button>
  )
}

// ── Extension tag (for the whitelist) ────────────────────────────

function ExtensionTag({ value, onRemove }: { value: string; onRemove: () => void }) {
  const { t } = useI18n()
  return (
    <span className="inline-flex items-center gap-1 rounded border border-[--border] bg-[--surface-2] px-2 py-0.5 text-xs font-mono">
      {value}
      <button onClick={onRemove} className="flex size-3.5 items-center justify-center rounded text-[--text-muted] transition-colors hover:bg-[--surface-3] hover:text-[--text-primary]" aria-label={t('settings.remove', { name: value })}>
        ×
      </button>
    </span>
  )
}

// ── Toggle switch ────────────────────────────────────────────────

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex-1">
        <div className="text-sm font-medium text-[--text-primary]">{label}</div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className="relative shrink-0 overflow-hidden rounded-full transition-colors duration-200 will-change-[background-color] hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[--primary-soft]"
        style={{ width: '40px', height: '22px', backgroundColor: checked ? 'var(--primary)' : 'var(--border)' }}
      >
        <span
          className="block size-4 rounded-full bg-white shadow transition-transform duration-200"
          style={{ transform: checked ? 'translateX(18px)' : 'translateX(0)', marginTop: '3px', marginLeft: '3px' }}
        />
      </button>
    </div>
  )
}

// ── Section wrapper ──────────────────────────────────────────────

function Section({ title, desc, children }: { title: string; desc: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
      <h2 className="text-sm font-medium text-[--text-primary]">{title}</h2>
      <p className="mt-1 text-xs leading-relaxed text-[--text-secondary]">{desc}</p>
      {children}
    </div>
  )
}

// ── Main Settings component ──────────────────────────────────────

export interface SettingsPageProps {
  /** Called when settings are successfully saved. */
  onSave?: () => void
  /** Called to trigger keyframe suggestion for every clip missing one. */
  onSuggestAllKeyframes?: () => void
  /** Called to open the library-cleanup confirmation flow. */
  onCleanupLibrary?: () => void
  /** Called to open the backend logs modal. */
  onShowLogs?: () => void
}

export function SettingsPage({ onSave, onSuggestAllKeyframes, onCleanupLibrary, onShowLogs }: SettingsPageProps) {
  const { t, lang, setLang } = useI18n()
  const [prefs, setPrefs] = useState<UpdateSettingsBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [fieldErrors, setFieldErrors] = useState<FieldError[]>([])

  // Form inputs
  const [extensions, setExtensions] = useState('')
  const [photoExtensions, setPhotoExtensions] = useState('')

  // Machine-global env settings (OMLX endpoint/key, model names). These live
  // in ~/.cutfinder/config.json — no .env needed. The API key is write-only:
  // GET returns a mask, and we only send it when the user types a new value.
  const [omlxBaseUrl, setOmlxBaseUrl] = useState('')
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [textModelGlobal, setTextModelGlobal] = useState('')
  const [visionModelGlobal, setVisionModelGlobal] = useState('')
  const [apiKeyConfigured, setApiKeyConfigured] = useState(false)
  const [omlxTest, setOmlxTest] = useState<
    { state: 'idle' | 'testing' } |
    { state: 'ok'; models: string[]; missing: string[] } |
    { state: 'err'; error: string }
  >({ state: 'idle' })

  // Library binding (when no library is bound, the user sets one here first).
  const [libraryPath, setLibraryPath] = useState<string | null | undefined>(undefined)
  const [newLibraryPath, setNewLibraryPath] = useState('')

  // Confirmation dialog for library switch (WKWebView has no window.confirm).
  const [confirmSwitch, setConfirmSwitch] = useState(false)
  const [switchPath, setSwitchPath] = useState('')

  // Cancel library switch: close dialog without changing anything.
  const handleCancelSwitch = () => { setConfirmSwitch(false); setSwitchPath('') }

  // Confirm library switch: actually perform the switch (extracted from handleSwitchLibrary).
  const handleConfirmSwitch = async () => {
    setConfirmSwitch(false)
    if (!switchPath || switchPath === libraryPath) return
    setSaving(true)
    setError(null)
    try {
      await api.setLibrary(switchPath)
      await load()
    } catch (err: unknown) {
      setError(err instanceof Error ? err : new Error(String(err)))
    } finally {
      setSaving(false)
    }
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const lib = await api.getLibrary()
      setLibraryPath(lib.library_path)
      if (lib.library_path) {
        const data = await api.getSettings()
        // Machine-global keys (OMLX endpoint/key, model names) are merged into
        // the one prefs view now — there is no separate "env" grouping.
        setPrefs(data.prefs)
        setTextModelGlobal(data.prefs.TEXT_MODEL || '')
        setVisionModelGlobal(data.prefs.VISION_MODEL || '')
        setOmlxBaseUrl(data.prefs.OMLX_BASE_URL || '')
        setApiKeyConfigured(Boolean(data.prefs.OMLX_API_KEY))
        setApiKeyInput('')
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err : new Error(String(err)))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const handleSetLibrary = async () => {
    const path = newLibraryPath.trim()
    if (!path) return
    setSaving(true)
    setError(null)
    try {
      await api.setLibrary(path)
      setNewLibraryPath('')
      await load()
    } catch (err: unknown) {
      setError(err instanceof Error ? err : new Error(String(err)))
    } finally {
      setSaving(false)
    }
  }

  // Switch the active library at runtime. Unlike other prefs (saved via
  // PUT /settings into the *current* library), the library binding lives in
  // ~/.cutfinder/active_library and must be changed via POST /api/library —
  // otherwise the app keeps using the old library no matter what's picked.
  // Show confirmation dialog instead of window.confirm (WKWebView has no JS dialogs).
  const handleSwitchLibrary = async (path: string) => {
    const p = path.trim()
    if (!p || p === libraryPath) return
    setSwitchPath(p)
    setConfirmSwitch(true)
  }

  const updateField = <K extends keyof UpdateSettingsBody>(key: K, value: UpdateSettingsBody[K]) => {
    setPrefs((prev) => (prev ? { ...prev, [key]: value } : prev))
    // Clear field error for this key if present
    setFieldErrors((prev) => prev.filter((e) => e.field !== key))
  }

  const handleAddExtension = () => {
    const ext = extensions.trim().replace(/^\.*/, '.') // ensure leading dot
    if (!ext || !prefs) return

    const current = prefs.extensions || []
    if (current.includes(ext)) { setExtensions(''); return }

    updateField('extensions', [...current, ext])
    setExtensions('')
  }

  const handleRemoveExtension = (ext: string) => {
    if (!prefs) return
    updateField('extensions', (prefs.extensions ?? []).filter((e: string) => e !== ext))
  }

  const handleAddPhotoExtension = () => {
    const ext = photoExtensions.trim().replace(/^\.*/, '.') // ensure leading dot
    if (!ext || !prefs) return

    const current = prefs.photo_extensions || []
    if (current.includes(ext)) { setPhotoExtensions(''); return }

    updateField('photo_extensions', [...current, ext])
    setPhotoExtensions('')
  }

  const handleRemovePhotoExtension = (ext: string) => {
    if (!prefs) return
    updateField('photo_extensions', (prefs.photo_extensions ?? []).filter((e: string) => e !== ext))
  }

  const handleRemoveSourceFolder = (folder: string) => {
    if (!prefs || !prefs.source_folders?.includes(folder)) return
    updateField('source_folders', prefs.source_folders.filter((f: string) => f !== folder))
  }

  const handleSave = async () => {
    if (!prefs) return

    const errors = validatePrefs(prefs)
    setFieldErrors(errors)
    if (errors.length > 0) return

    setSaving(true)
    try {
      // library_path is the active-library binding, not a normal pref — it's
      // changed via setLibrary (POST /api/library). Stripping it here keeps the
      // saved pref from diverging from the real binding.
      const body: UpdateSettingsBody = { ...prefs }
      delete body.library_path
      // Persist the current UI language as a machine-global pref so the backend can
      // pick it up (bilingual director prompt + progress messages).
      body.ui_language = lang as 'zh' | 'en'
      // Machine-global keys: always send the (non-secret) endpoint and model names; only send
      // the API key when the user typed a new one, so the stored secret is
      // never overwritten by the mask.
      body.OMLX_BASE_URL = omlxBaseUrl.trim()
      if (textModelGlobal) body.TEXT_MODEL = textModelGlobal
      else delete body.TEXT_MODEL  // clear: fall back to default
      if (visionModelGlobal) body.VISION_MODEL = visionModelGlobal
      if (apiKeyInput.trim()) body.OMLX_API_KEY = apiKeyInput.trim()
      await api.putSettings(body)
      if (apiKeyInput.trim()) {
        setApiKeyConfigured(true)
        setApiKeyInput('')
      }
      onSave?.()
    } catch (err: unknown) {
      setError(err instanceof Error ? err : new Error(String(err)))
    } finally {
      setSaving(false)
    }
  }

  // Probe the OMLX endpoint/key/models with the form's current (unsaved) values,
  // so "已配置" is verifiable before hitting Save.
  const handleTestConnection = async () => {
    setOmlxTest({ state: 'testing' })
    try {
      const body: Record<string, string> = {
        OMLX_BASE_URL: omlxBaseUrl,
        TEXT_MODEL: textModelGlobal,
        VISION_MODEL: visionModelGlobal,
      }
      if (apiKeyInput.trim()) body.OMLX_API_KEY = apiKeyInput.trim()
      const res = await api.testOmlxConnection(body)
      if (res.ok) setOmlxTest({ state: 'ok', models: res.models ?? [], missing: res.missing ?? [] })
      else setOmlxTest({ state: 'err', error: res.error ?? t('settings.testFailed') })
    } catch (err: unknown) {
      setOmlxTest({ state: 'err', error: err instanceof Error ? err.message : String(err) })
    }
  }

  if (loading) return <div className="p-6 text-[--text-muted]">{t('settings.loading')}</div>

  // No library bound yet — prompt the user to set one (binds at runtime).
  if (libraryPath === null) {
    return (
      <div className="p-6">
        <h2 className="mb-2 text-lg font-medium text-[--text-primary]">{t('settings.setupTitle')}</h2>
        <p className="mb-4 max-w-prose text-sm text-[--text-secondary]">
          {t('settings.setupDesc')}
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={newLibraryPath}
            onChange={(e) => setNewLibraryPath(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void handleSetLibrary() }}
            placeholder={t('settings.newLibraryPlaceholder')}
            className="flex-1 rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm outline-none focus:border-[--primary]"
          />
          <FolderPickerButton label={t('settings.choose')} icon={null} onChange={(folder) => setNewLibraryPath(folder)} />
          <Button onClick={handleSetLibrary} disabled={saving || !newLibraryPath.trim()}>
            {saving ? t('settings.setting') : t('settings.setLibrary')}
          </Button>
        </div>
        {error && <p className="mt-2 text-xs text-[--error]">{error.message}</p>}
      </div>
    )
  }

  if (error) return <div className="p-6 text-[--error]">{t('settings.failedLoad', { message: error.message })}</div>
  if (!prefs) return null

  // Prepend dot to extensions for display, ensure they start with a dot
  const extDisplay = (prefs.extensions || []).map((e: string) => e.startsWith('.') ? e : `.${e}`)
  const photoExtDisplay = (prefs.photo_extensions || []).map((e: string) => e.startsWith('.') ? e : `.${e}`)

  return (
    <div className="flex flex-1 overflow-auto">
      <div className="mx-auto w-full max-w-5xl p-6 pb-24">
        <h1 className="mb-8 text-2xl font-semibold tracking-tight text-[--text-primary]">{t('settings.title')}</h1>

        {/* Responsive two-column grid — single column on narrow screens */}
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">

          {/* ── Column 1 ───────────────────────────────────── */}
          <div className="space-y-5">

            {/* ── Interface language ─────────────────────── */}
            <Section title={t('settings.uiLanguage')} desc={t('settings.uiLanguageDesc')}>
              <div className="mt-3">
                <select
                  value={lang}
                  onChange={(e) => setLang(e.target.value as 'zh' | 'en')}
                  aria-label={t('settings.uiLanguage')}
                  className="w-full max-w-xs rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm outline-none focus:border-[--primary]"
                >
                  <option value="zh">{t('settings.langZh')}</option>
                  <option value="en">{t('settings.langEn')}</option>
                </select>
              </div>
            </Section>

            {/* ── Source folders ─────────────────────── */}
            <Section title={t('settings.sourceFolders')} desc={t('settings.sourceFoldersDesc')}>
              <div className="mt-3 space-y-2">
                {(prefs.source_folders || []).map((folder: string, i: number) => (
                  <div key={i} className="flex items-center gap-1.5">
                    <input
                      type="text"
                      value={folder}
                      readOnly
                      className="flex-1 rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-sm outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => handleRemoveSourceFolder(folder)}
                      className="flex size-4 items-center justify-center rounded text-[--text-muted] transition-colors hover:bg-[--surface-3] hover:text-[--text-primary]"
                      aria-label={t('settings.remove', { name: folder })}
                    >
                      <svg className="size-3.5" fill="none" viewBox="0 0 16 16">
                        <path stroke="currentColor" strokeWidth={1.5} d="M4 4l8 8M12 4l-8 8" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
              <div className="mt-2 flex items-center gap-1.5">
                <FolderPickerButton
                  label={t('settings.addFolder')}
                  icon={
                    <svg className="size-3.5" fill="none" viewBox="0 0 12 12">
                      <path stroke="currentColor" strokeWidth={1.5} d="M6 2v8M2 6h8" />
                    </svg>
                  }
                  onChange={(folder) => {
                    if (!prefs || (prefs.source_folders ?? []).includes(folder)) return
                    updateField('source_folders', [...(prefs.source_folders || []), folder])
                  }}
                />
                <span className="text-sm text-[--text-secondary]">{t('settings.addFolder')}</span>
              </div>
            </Section>

            {/* ── Library path ─────────────────────── */}
            <Section title={t('settings.libraryPath')} desc={t('settings.libraryPathDesc')}>
              <div className="mt-3 flex items-center gap-1.5">
                <input
                  type="text"
                  value={libraryPath || ''}
                  readOnly
                  className="flex-1 rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-sm outline-none"
                />
                <FolderPickerButton
                  label={t('settings.choose')}
                  icon={
                    <svg className="size-4" fill="none" viewBox="0 0 16 16">
                      <path stroke="currentColor" strokeWidth={1.5} d="M1.5 4.5v7a1.5 1.5 0 0 0 1.5 1.5h10a1.5 1.5 0 0 0 1.5-1.5v-5a1.5 1.5 0 0 0-1.5-1.5h-5.5L7 3.5H3A1.5 1.5 0 0 0 1.5 5v-.5z" />
                    </svg>
                  }
                  onChange={(folder) => void handleSwitchLibrary(folder)}
                />
                <span className="text-sm text-[--text-secondary]">{t('settings.choose')}</span>
              </div>
            </Section>

            {/* ── OMLX connection (machine-global) ─────── */}
            <Section title={t('settings.omlxConnection')} desc={t('settings.omlxConnectionDesc')}>
              {/* Connection status indicator */}
              {omlxTest.state === 'ok' && (
                <div className="mt-3 flex items-center gap-1.5 text-sm" style={{ color: 'var(--success)' }}>
                  <span className="size-2 rounded-full" style={{ background: 'var(--success)' }} />
                  {omlxTest.missing.length === 0
                    ? t('settings.testOk', { n: omlxTest.models.length })
                    : t('settings.testMissing', { models: omlxTest.missing.join(', ') })}
                </div>
              )}
              {omlxTest.state === 'err' && (
                <p className="mt-2 text-xs text-[--error]">{omlxTest.error}</p>
              )}
              {omlxTest.state !== 'idle' && (
                <button
                  type="button"
                  onClick={handleTestConnection}
                  disabled={omlxTest.state === 'testing'}
                  className="mt-2 rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm hover:border-[--primary] disabled:opacity-60"
                >
                  {omlxTest.state === 'testing' ? t('settings.testing') : t('settings.testConnection')}
                </button>
              )}
              {omlxTest.state === 'idle' && (
                <button
                  type="button"
                  onClick={handleTestConnection}
                  className="mt-2 rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm hover:border-[--primary]"
                >
                  {t('settings.testConnection')}
                </button>
              )}

              <div className="mt-3">
                <label className="mb-1 block text-sm font-medium text-[--text-primary]">{t('settings.baseUrl')}</label>
                <input
                  type="text" value={omlxBaseUrl}
                  onChange={(e) => setOmlxBaseUrl(e.target.value)}
                  placeholder="http://localhost:8000/v1"
                  className="w-full rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-xs font-mono outline-none focus:border-[--primary] focus:shadow-[0_0_0_2px_var(--primary-soft)]"
                />
              </div>

              <div className="mt-3">
                <label className="mb-1 block text-sm font-medium text-[--text-primary]">{t('settings.apiKey')}</label>
                <p className="mb-1 text-xs text-[--text-secondary]">
                  {apiKeyConfigured ? t('settings.apiKeyConfigured') : t('settings.apiKeyNotConfigured')}
                </p>
                <input
                  type="password" value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  placeholder={apiKeyConfigured ? t('settings.apiKeyPlaceholder') : 'omlx-…'}
                  autoComplete="new-password"
                  className="w-full rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-xs font-mono outline-none focus:border-[--primary] focus:shadow-[0_0_0_2px_var(--primary-soft)]"
                />
              </div>

              <div className="mt-3">
                <label className="mb-1 block text-sm font-medium text-[--text-primary]">{t('settings.textModel')}</label>
                <p className="mb-1 text-xs text-[--text-secondary]">{t('settings.textModelDesc')}</p>
                <input
                  type="text" value={textModelGlobal}
                  onChange={(e) => setTextModelGlobal(e.target.value)}
                  placeholder="Qwen3.6-35B-A3B"
                  className="w-full rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-xs font-mono outline-none focus:border-[--primary] focus:shadow-[0_0_0_2px_var(--primary-soft)]"
                />
              </div>

              <div className="mt-3">
                <label className="mb-1 block text-sm font-medium text-[--text-primary]">{t('settings.visionModel')}</label>
                <p className="mb-1 text-xs text-[--text-secondary]">{t('settings.visionModelDesc')}</p>
                <input
                  type="text" value={visionModelGlobal}
                  onChange={(e) => setVisionModelGlobal(e.target.value)}
                  placeholder="Qwen3-VL-8B"
                  className="w-full rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-xs font-mono outline-none focus:border-[--primary] focus:shadow-[0_0_0_2px_var(--primary-soft)]"
                />
              </div>
            </Section>

            {/* ── Speech engine ─────────────────────── */}
            <Section title={t('settings.whisperTitle')} desc={t('settings.whisperDesc')}>
              <div className="mt-3">
                <label className="mb-1 block text-sm font-medium text-[--text-primary]">{t('settings.speechEngine')}</label>
                <p className="mb-1 text-xs text-[--text-secondary]">{t('settings.speechEngineDesc')}</p>
                <select
                  value={prefs.transcription_engine ?? 'whisper'}
                  onChange={(e) => updateField('transcription_engine', e.target.value as 'whisper' | 'qwen')}
                  aria-label={t('settings.speechEngine')}
                  className="w-full rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-sm outline-none focus:border-[--primary]"
                >
                  <option value="whisper">{t('settings.engineWhisper')}</option>
                  <option value="qwen">{t('settings.engineQwen')}</option>
                </select>
              </div>

              {(prefs.transcription_engine ?? 'whisper') === 'whisper' ? (
                <div className="mt-3">
                  <label className="mb-1 block text-sm font-medium text-[--text-primary]">{t('settings.whisperModel')}</label>
                  <input
                    type="text" value={prefs.whisper_model}
                    onChange={(e) => updateField('whisper_model', e.target.value)}
                    className="w-full rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-xs font-mono outline-none focus:border-[--primary]"
                  />
                </div>
              ) : (
                <>
                  <div className="mt-3">
                    <label className="mb-1 block text-sm font-medium text-[--text-primary]">{t('settings.qwenAsrModel')}</label>
                    <input
                      type="text" value={prefs.qwen_asr_model ?? ''}
                      onChange={(e) => updateField('qwen_asr_model', e.target.value)}
                      className="w-full rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-xs font-mono outline-none focus:border-[--primary]"
                    />
                  </div>
                  <div className="mt-3">
                    <label className="mb-1 block text-sm font-medium text-[--text-primary]">{t('settings.qwenAlignerModel')}</label>
                    <input
                      type="text" value={prefs.qwen_aligner_model ?? ''}
                      onChange={(e) => updateField('qwen_aligner_model', e.target.value)}
                      className="w-full rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-xs font-mono outline-none focus:border-[--primary]"
                    />
                  </div>
                  <div className="mt-3">
                    <label className="mb-1 block text-sm font-medium text-[--text-primary]">{t('settings.qwenMaxChunk')}</label>
                    <p className="mb-1 text-xs text-[--text-secondary]">{t('settings.qwenMaxChunkDesc')}</p>
                    <input
                      type="number" min={5} max={300} step={5} value={prefs.qwen_max_chunk_s ?? 60}
                      onChange={(e) => updateField('qwen_max_chunk_s', parseFloat(e.target.value))}
                      className="w-24 rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-sm outline-none focus:border-[--primary]"
                    />
                  </div>
                </>
              )}
            </Section>

          </div>

          {/* ── Column 2 ───────────────────────────────────── */}
          <div className="space-y-5">

            {/* ── Processing options (extensions only) ─── */}
            <Section title={t('settings.processingOptions')} desc={t('settings.supportedExtensionsDesc')}>
              {/* Video extensions */}
              <div className="mt-3">
                <label className="mb-1 block text-sm font-medium text-[--text-primary]">{t('settings.supportedExtensions')}</label>
                <div className="mb-2 flex flex-wrap gap-1">
                  {extDisplay.map((ext, i) => (
                    <ExtensionTag key={i} value={ext} onRemove={() => handleRemoveExtension(ext)} />
                  ))}
                </div>
                <div className="flex gap-1.5">
                  <input
                    type="text" value={extensions} onChange={(e) => setExtensions(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleAddExtension() }}
                    placeholder=".webm"
                    className="flex-1 rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-xs font-mono outline-none focus:border-[--primary]"
                  />
                  <button type="button" onClick={handleAddExtension} className="flex size-8 items-center justify-center rounded-md border border-[--border] bg-[--surface-2] text-[--text-secondary] transition-colors hover:bg-[--surface-3]">
                    +
                  </button>
                </div>
              </div>

              {/* Photo extensions */}
              <div className="mt-4">
                <label className="mb-1 block text-sm font-medium text-[--text-primary]">{t('settings.photoExtensions')}</label>
                <p className="mb-1 text-xs text-[--text-secondary]">{t('settings.photoExtensionsDesc')}</p>
                <div className="mb-2 flex flex-wrap gap-1">
                  {photoExtDisplay.map((ext, i) => (
                    <ExtensionTag key={i} value={ext} onRemove={() => handleRemovePhotoExtension(ext)} />
                  ))}
                </div>
                <div className="flex gap-1.5">
                  <input
                    type="text" value={photoExtensions} onChange={(e) => setPhotoExtensions(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleAddPhotoExtension() }}
                    placeholder=".webp"
                    className="flex-1 rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-xs font-mono outline-none focus:border-[--primary]"
                  />
                  <button type="button" onClick={handleAddPhotoExtension} className="flex size-8 items-center justify-center rounded-md border border-[--border] bg-[--surface-2] text-[--text-secondary] transition-colors hover:bg-[--surface-3]">
                    +
                  </button>
                </div>
              </div>
            </Section>

            {/* ── B-roll frame count ─────────────── */}
            <Section title={t('settings.brollFrameCount')} desc={t('settings.brollFrameCountDesc')}>
              <div className="mt-3">
                <input
                  type="number" min={1} max={20} step={1} value={prefs.broll_frame_count}
                  onChange={(e) => updateField('broll_frame_count', parseInt(e.target.value, 10))}
                  className="w-24 rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-sm outline-none focus:border-[--primary]"
                />
              </div>
            </Section>

            {/* ── VAD threshold ─────────────── */}
            <Section title={t('settings.vadThreshold')} desc={t('settings.vadThresholdDesc')}>
              <div className="mt-3">
                <input
                  type="number" min={0} max={1} step={0.01} value={prefs.vad_threshold}
                  onChange={(e) => updateField('vad_threshold', parseFloat(e.target.value))}
                  className="w-24 rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-sm outline-none focus:border-[--primary]"
                />
              </div>
            </Section>

            {/* ── Vocal separation toggle ─────────────── */}
            <Section title={t('settings.vocalSeparation')} desc={t('settings.vocalSeparationDesc')}>
              <div className="mt-3 pt-2.5">
                <Toggle
                  checked={prefs.vocal_separation ?? false}
                  onChange={(v) => updateField('vocal_separation', v)}
                  label={t('settings.vocalSeparation')}
                />
              </div>
            </Section>

            {/* ── AI output language ─────────────── */}
            <Section title={t('settings.aiOutputLanguage')} desc={t('settings.aiOutputLanguageDesc')}>
              <div className="mt-3">
                <select
                  value={prefs.output_language}
                  onChange={(e) => updateField('output_language', e.target.value as 'zh' | 'en')}
                  aria-label={t('settings.aiOutputLanguage')}
                  className="w-full rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1.5 text-sm outline-none focus:border-[--primary]"
                >
                  <option value="zh">{t('settings.langZh')}</option>
                  <option value="en">{t('settings.langEn')}</option>
                </select>
              </div>
            </Section>

            {/* ── Keyframe suggestions per clip ─────── */}
            <Section title={t('settings.keyframeCount')} desc={t('settings.keyframeCountDesc')}>
              <div className="mt-3">
                <input
                  type="number" min={1} max={10} step={1} value={prefs.keyframe_count ?? 3}
                  onChange={(e) => updateField('keyframe_count', parseInt(e.target.value, 10))}
                  className="w-24 rounded-md border border-[--border] bg-[--surface-2] px-2.5 py-1 text-sm outline-none focus:border-[--primary]"
                />
              </div>
            </Section>

            {/* ── Auto-suggest keyframes ─────────────── */}
            <Section title={t('settings.keyframeAuto')} desc={t('settings.keyframeAutoDesc')}>
              <div className="mt-3 pt-2.5">
                <Toggle
                  checked={prefs.keyframe_auto ?? false}
                  onChange={(v) => updateField('keyframe_auto', v)}
                  label={t('settings.keyframeAuto')}
                />
              </div>
            </Section>

            {/* ── System tools ─────────────── */}
            <Section title={t('settings.maintenanceTitle')} desc={t('settings.maintenanceDesc')}>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" onClick={() => onSuggestAllKeyframes?.()} className="inline-flex items-center gap-1 rounded-md border border-[--border] bg-[--surface-2] px-3 py-1 text-sm text-[--text-secondary] transition-colors hover:bg-[--surface-3]">
                  {t('settings.suggestAllKeyframes')}
                </button>
                <button type="button" onClick={() => onCleanupLibrary?.()} className="inline-flex items-center gap-1 rounded-md border border-[--border] bg-[--surface-2] px-3 py-1 text-sm text-[--text-secondary] transition-colors hover:bg-[--surface-3]">
                  {t('settings.cleanupDeleted')}
                </button>
                <button type="button" onClick={() => onShowLogs?.()} className="inline-flex items-center gap-1 rounded-md border border-[--border] bg-[--surface-2] px-3 py-1 text-sm text-[--text-secondary] transition-colors hover:bg-[--surface-3]">
                  <svg className="size-3.5" fill="none" viewBox="0 0 16 16">
                    <path stroke="currentColor" strokeWidth={1.5} d="M3 3h10v10H3z" />
                    <path stroke="currentColor" strokeWidth={1.5} d="M5 6h6M5 8h6M5 10h3" />
                  </svg>
                  {t('app.logs')}
                </button>
              </div>
            </Section>

          </div>

        </div>

        {/* Field errors */}
        {fieldErrors.map((err) => (
          <p key={err.field} className="mt-2 text-xs text-[--error]">{t(err.messageKey)}</p>
        ))}

        {/* Library switch confirmation dialog */}
        <ConfirmDialog
          open={confirmSwitch}
          title={t('settings.setLibrary')}
          message={t('settings.switchLibraryConfirm', { path: switchPath })}
          onConfirm={handleConfirmSwitch}
          onCancel={handleCancelSwitch}
        />
      </div>

      {/* ── Fixed save bar ───────────────────────────────────── */}
      <div className="fixed bottom-0 left-0 right-0 border-t border-[--border] bg-[--surface-1]">
        <div className="mx-auto flex max-w-5xl justify-end px-6 py-3">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? t('settings.saving') : t('settings.save')}
          </Button>
        </div>
      </div>
    </div>
  )
}
