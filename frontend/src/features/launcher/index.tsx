/** Launcher feature — CutFinder's entry screen with cards to each top-level view.

Usage:
  <LauncherPage theme={theme} onToggleTheme={toggleTheme} onNavigate={(screen) => ...} />
*/

import { useI18n } from '@/i18n'
import type { Theme } from '@/theme'

export type LauncherScreen = 'gallery' | 'settings' | 'jobs' | 'cutplan' | 'subtitles'

export interface LauncherPageProps {
  theme: Theme
  onToggleTheme: () => void
  onNavigate: (screen: LauncherScreen) => void
}

export function LauncherPage({ theme, onToggleTheme, onNavigate }: LauncherPageProps) {
  const { t } = useI18n()

  return (
    <div className="flex min-h-screen w-full flex-col items-center justify-center bg-[--bg-canvas] p-6 text-[--text-primary]">
      <button
        onClick={onToggleTheme}
        aria-label={theme === 'dark' ? t('app.themeToLight') : t('app.themeToDark')}
        className="fixed right-4 top-4 flex h-9 w-9 items-center justify-center rounded-md border border-[--border] bg-[--surface-1] text-[--text-secondary] transition-colors hover:bg-[--surface-3] hover:text-[--text-primary]"
      >
        {theme === 'dark' ? (
          <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
            <circle cx="8" cy="8" r="3" />
            <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.1 3.1l1.4 1.4M11.5 11.5l1.4 1.4M12.9 3.1l-1.4 1.4M4.5 11.5l-1.4 1.4" />
          </svg>
        ) : (
          <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
            <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7Z" />
          </svg>
        )}
      </button>

      <div className="w-full max-w-[640px] text-center">
        <div className="mb-2 flex items-center justify-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-[10px] bg-[--primary]">
            <svg className="h-6 w-6" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <rect x="2" y="2" width="16" height="16" rx="4" fill="white" opacity="0.2" />
              <path d="M7 7.5L13 10L7 12.5V7.5Z" fill="white" />
            </svg>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">{t('launcher.title')}</h1>
        </div>
        <p className="mb-10 text-[15px] text-[--text-secondary]">{t('launcher.subtitle')}</p>

        <div className="grid grid-cols-2 gap-4 max-[500px]:grid-cols-1">
          <button
            onClick={() => onNavigate('gallery')}
            className="flex flex-col items-start gap-2 rounded-[14px] border border-[--border] bg-[--surface-1] p-5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
          >
            <div className="mb-1 flex h-9 w-9 items-center justify-center rounded-md bg-[--primary-soft] text-[--primary]">
              <svg className="h-5 w-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <rect x="2" y="2" width="5" height="5" rx="1" /><rect x="9" y="2" width="5" height="5" rx="1" />
                <rect x="2" y="9" width="5" height="5" rx="1" /><rect x="9" y="9" width="5" height="5" rx="1" />
              </svg>
            </div>
            <span className="text-base font-semibold">{t('launcher.cardGallery')}</span>
            <span className="flex-1 text-sm text-[--text-secondary]">{t('launcher.cardGalleryDesc')}</span>
            <span className="inline-flex items-center gap-1 text-sm font-medium text-[--primary]">{t('launcher.open')} →</span>
          </button>

          <button
            onClick={() => onNavigate('settings')}
            className="flex flex-col items-start gap-2 rounded-[14px] border border-[--border] bg-[--surface-1] p-5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
          >
            <div className="mb-1 flex h-9 w-9 items-center justify-center rounded-md bg-[--surface-3] text-[--text-secondary]">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.49l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <span className="text-base font-semibold">{t('launcher.cardSettings')}</span>
            <span className="flex-1 text-sm text-[--text-secondary]">{t('launcher.cardSettingsDesc')}</span>
            <span className="inline-flex items-center gap-1 text-sm font-medium text-[--primary]">{t('launcher.open')} →</span>
          </button>

          <button
            onClick={() => onNavigate('jobs')}
            className="flex flex-col items-start gap-2 rounded-[14px] border border-[--border] bg-[--surface-1] p-5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
          >
            <div className="mb-1 flex h-9 w-9 items-center justify-center rounded-md bg-[--success-soft] text-[--success]">
              <svg className="h-5 w-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <rect x="2" y="3" width="12" height="10" rx="2" /><path d="M2 6h12" />
              </svg>
            </div>
            <span className="text-base font-semibold">{t('launcher.cardTasks')}</span>
            <span className="flex-1 text-sm text-[--text-secondary]">{t('launcher.cardTasksDesc')}</span>
            <span className="inline-flex items-center gap-1 text-sm font-medium text-[--primary]">{t('launcher.open')} →</span>
          </button>

          <button
            onClick={() => onNavigate('cutplan')}
            className="flex flex-col items-start gap-2 rounded-[14px] border border-[--border] bg-[--surface-1] p-5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
          >
            <div className="mb-1 flex h-9 w-9 items-center justify-center rounded-md bg-[--roll-b-soft] text-[--roll-b]">
              <svg className="h-5 w-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <path d="M3 4h10M3 8h10M3 12h6" />
              </svg>
            </div>
            <span className="text-base font-semibold">{t('launcher.cardCut')}</span>
            <span className="flex-1 text-sm text-[--text-secondary]">{t('launcher.cardCutDesc')}</span>
            <span className="inline-flex items-center gap-1 text-sm font-medium text-[--primary]">{t('launcher.open')} →</span>
          </button>

          <button
            onClick={() => onNavigate('subtitles')}
            className="flex flex-col items-start gap-2 rounded-[14px] border border-[--border] bg-[--surface-1] p-5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
          >
            <div className="mb-1 flex h-9 w-9 items-center justify-center rounded-md bg-[--roll-photo-soft] text-[--roll-photo]">
              <svg className="h-5 w-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <rect x="2" y="3" width="12" height="10" rx="2" /><path d="M5 6.5h1.5M9 6.5h2M5 9h6M5 11h4" />
              </svg>
            </div>
            <span className="text-base font-semibold">{t('launcher.cardSubtitles')}</span>
            <span className="flex-1 text-sm text-[--text-secondary]">{t('launcher.cardSubtitlesDesc')}</span>
            <span className="inline-flex items-center gap-1 text-sm font-medium text-[--primary]">{t('launcher.open')} →</span>
          </button>
        </div>
      </div>
    </div>
  )
}
