/** Lightweight UI internationalization (English / Chinese).
 *
 * This is the *interface* language — completely separate from the AI output
 * language (which is a backend pref controlling summaries/tags). It is stored
 * per-device in localStorage and defaults to English.
 *
 * Usage:
 *   const { t, lang, setLang } = useI18n()
 *   <h1>{t('app.settings')}</h1>
 *   <span>{t('gallery.clipsCount', { n: 5 })}</span>
 *
 * Components rendered outside <LanguageProvider> (e.g. isolated unit tests)
 * fall back to English via the default context value.
 */

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type Lang = 'en' | 'zh'

const STORAGE_KEY = 'cutfinder:ui-lang'

// ── Dictionary ────────────────────────────────────────────────────
// `en` defines the key set; `zh` must mirror it. `{name}` placeholders are
// filled by the `vars` argument to `t`.

const en = {
  // App header
  'app.searchPlaceholder': 'Search clips…',
  'app.clearSearch': 'Clear search',
  'app.scan': 'Scan',
  'app.taskQueue': 'Task queue',
  'app.settings': 'Settings',
  'app.logs': 'Backend logs',
  'app.keyframes': 'Keyframes',
  'app.subtitles': 'Subtitle export',
  'app.themeToLight': 'Switch to light mode',
  'app.themeToDark': 'Switch to dark mode',
  'app.menu': 'Menu',
  'app.roughcut': 'Rough cut',

  // Rough-cut director (chat → shot list)
  'roughcut.title': 'Rough cut',
  'roughcut.desc': 'Chat with the director to build a shot list from your cataloged footage.',
  'roughcut.newSession': 'New conversation',
  'roughcut.noSessions': 'No conversations yet',
  'roughcut.deleteSession': 'Delete conversation',
  'roughcut.deleteConfirm': 'Delete this conversation and its shot list?',
  'roughcut.untitled': 'Untitled',
  'roughcut.you': 'You',
  'roughcut.assistant': 'Director',
  'roughcut.placeholder': 'e.g. Make a 15–20 min vlog from 4/25–5/11 footage, 16:9, narrative + upbeat rhythm',
  'roughcut.send': 'Send',
  'roughcut.thinking': 'Director is working…',
  'roughcut.progressTitle': 'Generation log ({n})',
  'roughcut.partialGenerating': 'Some dates are ready — still generating the rest…',
  'roughcut.emptyConvo': 'Describe the cut you want — date range, length, style, rhythm.',
  'roughcut.planTitle': 'Shot list',
  'roughcut.noPlan': 'No shot list yet. Send a request to generate one.',
  'roughcut.copyMarkdown': 'Copy as Markdown',
  'roughcut.copied': 'Copied',
  'roughcut.close': 'Close',
  'roughcut.selectSession': 'Select or start a conversation.',
  'roughcut.collapseList': 'Collapse list',
  'roughcut.expandList': 'Expand list',
  'roughcut.fullscreen': 'Fullscreen',
  'roughcut.exitFullscreen': 'Exit fullscreen',
  'roughcut.promptSettings': 'Rough-cut settings',
  'roughcut.settingsTitle': 'Rough-cut settings',
  'roughcut.genOptions': 'Generation options',
  'roughcut.promptSection': 'Director prompt',
  'roughcut.directorMode': 'Generation mode',
  'roughcut.directorModeDesc': 'Agent: a scoped tool loop per shooting date (deeper, falls back to fast when it doesn’t converge). Fast: one structured pass per date (quicker, coarser).',
  'roughcut.modeAgent': 'Agent (deeper)',
  'roughcut.modeStaged': 'Fast (one pass per date)',
  'roughcut.maxRounds': 'Max tool rounds (agent)',
  'roughcut.maxRoundsDesc': 'How many tool-call rounds a day’s agent may take before it’s forced to finalize (or falls back to fast). Higher = more room to deep-dive, slower. Only applies in Agent mode.',
  'roughcut.critic': 'Critic review pass',
  'roughcut.criticDesc': 'After the shot list is assembled, run one extra review pass (rhythm / narrative / A-B balance) and re-do the dates it flags. Costs one more model call.',
  'roughcut.visionBudget': 'Vision look-ups per generation',
  'roughcut.visionBudgetDesc': 'Max live B-roll vision checks per shot list (0 = unlimited). Each one makes OMLX swap models, slow on weaker Macs.',
  'roughcut.durationFootageHint': '(limited footage in range — fitted as close as possible)',
  'roughcut.leanBudget': 'Per-day catalog size (agent, tokens)',
  'roughcut.leanBudgetDesc': 'How much of a day’s clip catalog the agent sees (one short line per clip; transcripts fetched on demand), counted as real tokens via OMLX. Higher = no clips dropped on busy days; the text model takes a huge context, so the cap is just to bound local prefill cost.',
  'roughcut.stagedBudget': 'Per-day catalog size (fast, tokens)',
  'roughcut.stagedBudgetDesc': 'Fast mode inlines transcripts (it has no tools), so it fills faster than agent mode. Counted as real tokens via OMLX. Higher = fuller transcripts reach the model, at more local prefill cost.',
  'roughcut.promptTitle': 'Director prompt',
  'roughcut.promptHelp': 'Edit the director system prompt. Placeholders {aspect}, {target}, {style} are filled per request.',
  'roughcut.promptCustom': 'Custom prompt in use',
  'roughcut.promptDefault': 'Using built-in default',
  'roughcut.save': 'Save',
  'roughcut.saved': 'Saved',
  'roughcut.reset': 'Reset to default',
  'roughcut.cancel': 'Cancel',

  // Subtitle export page
  'subtitles.title': 'Subtitle export',
  'subtitles.desc': 'Pick a finished video and an output folder, then export subtitles transcribed from its audio.',
  'subtitles.chooseVideo': 'Choose video',
  'subtitles.chooseFolder': 'Choose output folder',
  'subtitles.video': 'Video',
  'subtitles.folder': 'Output folder',
  'subtitles.noVideo': 'No video selected',
  'subtitles.noFolder': 'No folder selected',
  'subtitles.formats': 'Formats',
  'subtitles.itt': 'iTT',
  'subtitles.srt': 'SRT',
  'subtitles.languageNote': 'Subtitle language follows the AI output language set in Settings.',
  'subtitles.export': 'Export',
  'subtitles.exporting': 'Exporting…',
  'subtitles.done': 'Subtitles exported',
  'subtitles.failed': 'Export failed — check logs for details.',
  'subtitles.reveal': 'Reveal in Finder',
  'subtitles.close': 'Close',
  'subtitles.progressTitle': 'Transcribing audio…',
  'subtitles.phaseSeparating': 'Separating vocals…',
  'subtitles.phaseTranscribing': 'Transcribing…',
  'subtitles.phaseDownloadingModel': 'Downloading speech model…',
  'subtitles.progressHint': 'This can take a few minutes for a long video — please keep this open.',
  'subtitles.downloadingModelHint': 'First use downloads the speech model (several GB). This runs once; transcription starts automatically when it finishes.',
  'subtitles.elapsed': 'Elapsed {time}',

  // Backend logs modal
  'logs.title': 'Backend logs',
  'logs.empty': 'No logs yet',
  'logs.autoscroll': 'Auto-scroll',
  'logs.clear': 'Clear',
  'logs.close': 'Close',
  'logs.paused': 'Paused',
  'logs.live': 'Live',

  // Gallery toolbar + empty state
  'gallery.clipsCount': '{n} clips',
  'gallery.sort': 'Sort',
  'gallery.sortDateNewest': 'Date (newest)',
  'gallery.sortDateOldest': 'Date (oldest)',
  'gallery.emptyTitle': 'No clips yet',
  'gallery.emptyDesc': 'Add source folders and run a scan to see your footage here.',
  'gallery.unknownDate': 'Unknown date',
  'gallery.openFolder': 'Open in Finder',
  'gallery.collapse': 'Collapse',
  'gallery.expand': 'Expand',
  'gallery.collapseAll': 'Collapse all',
  'gallery.expandAll': 'Expand all',

  // Thumbnail card
  'card.reanalyze': 'Re-analyze',
  'card.photo': 'Photo',
  'card.reanalyzing': 'Re-analyzing…',
  'card.openVideo': 'Open video',
  'card.partial': 'Partial',
  'card.partialTitle': 'AI analysis incomplete — re-analyze',

  // Filters
  'filters.title': 'Filters',
  'filters.expand': 'Expand filters',
  'filters.collapse': 'Collapse filters',
  'filters.type': 'Type',
  'filters.all': 'All',
  'filters.photo': 'Photo',
  'filters.date': 'Date',
  'filters.allDates': 'All dates',
  'filters.tags': 'Tags',
  'filters.searchTags': 'Search tags…',
  'filters.noTags': 'No tags yet',
  'filters.noMatchingTags': 'No matching tags',
  'filters.showAll': 'Show all {n}',
  'filters.showLess': 'Show less',
  'filters.clearAll': 'Clear all filters',

  // Detail panel
  'detail.fileDestination': 'File destination',
  'detail.captureDate': 'Capture date',
  'detail.captureDateFromFile': 'Capture date (from file time)',
  'detail.summaryARoll': 'Summary (A-roll)',
  'detail.descriptionBRoll': 'Description (B-roll)',
  'detail.photo': 'Photo',
  'detail.photoDescription': 'Description',
  'detail.transcript': 'Transcript',
  'detail.sourceFile': 'Source file',
  'detail.metadata': 'Metadata',
  'detail.duration': 'Duration',
  'detail.resolution': 'Resolution',
  'detail.frameRate': 'Frame rate',
  'detail.codec': 'Codec',
  'detail.loadingClip': 'Loading clip…',
  'detail.openVideo': 'Open video',
  'detail.reanalyze': 'Re-analyze',
  'detail.reanalyzing': 'Re-analyzing…',
  'detail.closePanel': 'Close panel',
  'detail.addTag': 'Add tag…',
  'detail.add': 'Add',
  'detail.save': 'Save',
  'detail.saving': 'Saving…',
  'detail.removeTag': 'Remove tag {name}',
  'detail.minutes': 'min',
  'detail.fps': 'fps',
  'detail.suggestedCuts': 'Suggested cuts',
  'detail.suggestKeyframes': 'Suggest keyframes',
  'detail.suggesting': 'Suggesting…',
  'detail.noKeyframes': 'No suggestions yet — click "Suggest keyframes".',

  // Thumbnail card badge
  'card.hasKeyframes': 'Has cut suggestions',

  // Common
  'common.close': 'Close',

  // Scan confirm (App)
  'scan.title': 'Scan',
  'scan.pausedConfirm':
    'The task queue is paused, so new scanned tasks will not start automatically.\n\nClick "OK" to resume processing and start scanning; click "Cancel" to abort this scan.',

  // Jobs queue page
  'jobs.title': 'Task queue',
  'jobs.pause': 'Pause',
  'jobs.resume': 'Resume',
  'jobs.resumeProcessing': 'Resume processing',
  'jobs.close': 'Close',
  'jobs.pausedBanner': 'Queue paused — queued tasks will not be processed. Click "Resume" to continue.',
  'jobs.empty': 'No tasks',
  'jobs.colId': 'ID',
  'jobs.colType': 'Type',
  'jobs.colStatus': 'Status',
  'jobs.colProgress': 'Progress',
  'jobs.colStartTime': 'Start time',
  'jobs.colActions': 'Actions',
  'jobs.retryFailed': 'Retry failed',
  'jobs.delete': 'Delete',
  'jobs.noNewFiles': 'No new files',
  'jobs.failedN': '{n} failed',
  'jobs.kindScan': 'Scan',
  'jobs.kindReanalyze': 'Re-analyze',
  'jobs.kindKeyframes': 'Keyframes',
  'jobs.kindSubtitle': 'Subtitles',
  'jobs.kindCutplan': 'Rough cut',
  'jobs.statusQueued': 'Queued',
  'jobs.statusRunning': 'Running',
  'jobs.statusDone': 'Done',
  'jobs.statusFailed': 'Failed',
  'jobs.statusCancelled': 'Cancelled',
  'jobs.statusPaused': 'Paused',

  // Scan progress + toasts
  'jobs.scanning': 'Scanning…',
  'jobs.suggestingKeyframes': 'Suggesting keyframes…',
  'jobs.reanalyzing': 'Re-analyzing…',
  'jobs.speechModelDownloadHint': 'First clip with speech will download the transcription model (a few minutes) — this happens once.',
  'jobs.toastStarted': 'Scan started — processing clips',
  'jobs.toastCompleted': 'Scan completed — {n} clips processed',
  'jobs.toastFailed': 'Scan failed — check logs for details',

  // Settings
  'settings.title': 'Settings',
  'settings.backToGallery': 'Back to gallery',
  'settings.loading': 'Loading settings…',
  'settings.failedLoad': 'Failed to load settings: {message}',
  'settings.setupTitle': 'Set up your library',
  'settings.setupDesc':
    'No library is configured yet. Enter an absolute path where CutFinder should store organized copies, thumbnails, and its catalog.',
  'settings.setLibrary': 'Set library',
  'settings.setting': 'Setting…',
  'settings.newLibraryPlaceholder': '/Users/you/Movies/CutFinder Library',

  'settings.sourceFolders': 'Source folders',
  'settings.sourceFoldersDesc':
    'These folders hold your original footage (read-only — never modified or moved). Scans only read files from these folders.',
  'settings.addFolder': 'Add folder',
  'settings.libraryPath': 'Library path',
  'settings.libraryPathDesc':
    'Organized copies, thumbnails, and the catalog database are stored here. Switching to another folder uses that library instead (each library is independent; the current one is not modified).',
  'settings.choose': 'Choose…',
  'settings.selecting': 'Selecting…',

  'settings.omlxConnection': 'OMLX connection',
  'settings.omlxConnectionDesc':
    'Address and key for the local OMLX inference service (machine-wide, stored in ~/.cutfinder/config.json — no .env needed). Values saved here take precedence over .env / environment variables.',
  'settings.baseUrl': 'Base URL',
  'settings.apiKey': 'API key',
  'settings.apiKeyConfigured': 'Configured — leave blank to keep, enter a new value to override',
  'settings.apiKeyNotConfigured': 'Not configured',
  'settings.apiKeyPlaceholder': '••••••••（leave blank to keep）',
  'settings.textModel': 'Text model',
  'settings.textModelDesc':
    'For A-roll summary + tag generation (via OMLX, text-only model). Defaults to Qwen3.6-35B-A3B if blank.',
  'settings.visionModel': 'Vision model',
  'settings.visionModelDesc':
    'For B-roll visual tags + description generation (via OMLX, multimodal model). Defaults to Qwen3-VL-8B if blank.',

  'settings.whisperTitle': 'Speech engine (speech-to-text)',
  'settings.whisperDesc': 'How A-roll speech is transcribed — used everywhere: catalog analysis, keyframes, and subtitle export. Runs locally, not via OMLX.',
  'settings.whisperModel': 'Whisper model',
  'settings.whisperModelDesc': 'HuggingFace model id. Downloaded into the project models/ folder on first use and loaded offline afterwards.',
  'settings.speechEngine': 'Engine',
  'settings.speechEngineDesc': 'Whisper, or Qwen3-ASR + ForcedAligner (more accurate for Chinese / zh-en mixed audio, with real word-level subtitle timing).',
  'settings.engineWhisper': 'Whisper (large-v3)',
  'settings.engineQwen': 'Qwen3-ASR + ForcedAligner',
  'settings.qwenAsrModel': 'Qwen ASR model',
  'settings.qwenAlignerModel': 'Qwen ForcedAligner model',
  'settings.qwenMaxChunk': 'Max chunk seconds',
  'settings.qwenMaxChunkDesc': 'Audio is split at silences (VAD) into chunks no longer than this before transcription + alignment. Larger = fewer cue breaks and faster. Max 300s: the ForcedAligner can only assign timestamps within ~400s per chunk, so longer chunks would lose timing.',

  'settings.processingOptions': 'Processing options',
  'settings.supportedExtensions': 'Supported extensions',
  'settings.supportedExtensionsDesc': 'Only files with these extensions are processed during scans',
  'settings.photoExtensions': 'Photo extensions',
  'settings.photoExtensionsDesc': 'Files with these extensions are cataloged as photos',
  'settings.brollFrameCount': 'B-roll frame count',
  'settings.brollFrameCountDesc':
    'Number of frames extracted for B-roll visual analysis — more is more accurate but slower',
  'settings.vadThreshold': 'VAD threshold (0–1)',
  'settings.vadThresholdDesc':
    'Speech-detection sensitivity — higher is stricter (only segments with clear speech are marked A-roll)',
  'settings.vocalSeparation': 'Separate vocals before A-roll transcription (strip BGM, slower)',
  'settings.vocalSeparationDesc':
    'Uses Demucs to remove background music before Whisper. Only affects clips scanned after you enable it. Subtitle export always separates.',
  'settings.aiOutputLanguage': 'AI output language',
  'settings.aiOutputLanguageDesc': 'Language of AI-generated summaries, tags, and other text output',
  'settings.keyframeCount': 'Keyframe suggestions per clip',
  'settings.keyframeCountDesc': 'Max ranked cut/frame suggestions generated per clip (1–10)',
  'settings.keyframeAuto': 'Auto-suggest keyframes after scan',
  'settings.keyframeAutoDesc': 'When a scan finishes, queue keyframe suggestion for the new clips',
  'settings.roughcutTitle': 'Rough-cut director',
  'settings.langZh': '中文',
  'settings.langEn': 'English',
  'settings.uiLanguage': 'Interface language',
  'settings.uiLanguageDesc': 'Language of the app interface (independent of the AI output language)',
  'settings.save': 'Save settings',
  'settings.saving': 'Saving…',
  'settings.remove': 'Remove {name}',
  'settings.validationInt': 'Must be an integer >= 1',
  'settings.validationNum': 'Must be a number between 0 and 1',
  'settings.switchLibraryConfirm':
    'Switch library to:\n{path}\n\nThe app will use that folder\'s catalog database, thumbnails, and settings (each library is independent). The current library is not modified. Continue?',
  'settings.cleanupDeleted': 'Clean up deleted files',
  'settings.cleanupNone': 'Nothing to clean up — every catalog entry still has its file.',
  'settings.cleanupUnreachable': 'The library folder is unreachable (e.g. an external drive is unmounted). Skipped to avoid wiping the catalog.',
  'settings.cleanupConfirm': '{n} catalog entr(ies) point to files that no longer exist. Delete these entries (and their thumbnails/keyframes)? Source files are not affected.',
  'settings.cleanupDone': 'Removed {n} entr(ies).',
  'confirm.confirm': 'OK',
  'confirm.cancel': 'Cancel',
} as const

type Key = keyof typeof en

const zh: Record<Key, string> = {
  'app.searchPlaceholder': '搜索片段…',
  'app.clearSearch': '清除搜索',
  'app.scan': '扫描',
  'app.taskQueue': '任务队列',
  'app.settings': '设置',
  'app.logs': '后端日志',
  'app.keyframes': '关键帧',
  'app.subtitles': '字幕导出',
  'app.themeToLight': '切换到浅色模式',
  'app.themeToDark': '切换到深色模式',
  'app.menu': '菜单',
  'app.roughcut': '初剪',

  'roughcut.title': '初剪',
  'roughcut.desc': '和导演 Agent 对话，从已编目的素材库生成分镜表。',
  'roughcut.newSession': '新建对话',
  'roughcut.noSessions': '暂无对话',
  'roughcut.deleteSession': '删除对话',
  'roughcut.deleteConfirm': '删除这个对话及其分镜表？',
  'roughcut.untitled': '未命名',
  'roughcut.you': '你',
  'roughcut.assistant': '导演',
  'roughcut.placeholder': '例如：用 4/25–5/11 的素材剪一条 15–20 分钟、叙事/轻快/有节奏的 vlog，16:9',
  'roughcut.send': '发送',
  'roughcut.thinking': '导演正在生成…',
  'roughcut.progressTitle': '生成过程（{n} 步）',
  'roughcut.partialGenerating': '部分日期已生成，其余仍在继续…',
  'roughcut.emptyConvo': '描述你想要的初剪——日期范围、时长、风格、节奏。',
  'roughcut.planTitle': '分镜表',
  'roughcut.noPlan': '还没有分镜表，发送需求来生成。',
  'roughcut.copyMarkdown': '复制为 Markdown',
  'roughcut.copied': '已复制',
  'roughcut.close': '关闭',
  'roughcut.selectSession': '选择或新建一个对话。',
  'roughcut.collapseList': '收起列表',
  'roughcut.expandList': '展开列表',
  'roughcut.fullscreen': '全屏',
  'roughcut.exitFullscreen': '退出全屏',
  'roughcut.promptSettings': '初剪设置',
  'roughcut.settingsTitle': '初剪设置',
  'roughcut.genOptions': '生成选项',
  'roughcut.promptSection': '导演 Prompt',
  'roughcut.directorMode': '生成模式',
  'roughcut.directorModeDesc': 'Agent：每个拍摄日期跑一个 scoped 工具环（更精细，收不了口时自动回落到快速模式）。快速：每天一次结构化补全（更快、更糙）。',
  'roughcut.modeAgent': 'Agent（更精细）',
  'roughcut.modeStaged': '快速（每天一次）',
  'roughcut.maxRounds': '最大工具轮数（Agent）',
  'roughcut.maxRoundsDesc': '单天 agent 在强制收口（或回落快速模式）前最多可用的工具调用轮数。越大越有余地深挖、但更慢。仅 Agent 模式生效。',
  'roughcut.critic': '审片复检',
  'roughcut.criticDesc': '分镜表拼好后，额外跑一轮审片：检查主观质量（节奏、叙事连贯、A/B-roll 配比），并对点名的日期重做一遍。会多一次模型调用。',
  'roughcut.visionBudget': '视觉确认次数',
  'roughcut.visionBudgetDesc': '每份分镜表里现场看 B-roll 画面的最大次数（0 = 不限）。每次都会让 OMLX 换模型，弱机会变慢。',
  'roughcut.durationFootageHint': '（该范围内素材有限，已尽量贴近）',
  'roughcut.leanBudget': '单日素材目录上限（Agent，token）',
  'roughcut.leanBudgetDesc': 'Agent 模式下这一天能看到的素材目录大小（每片段一行摘要，台词按需用工具取），按真实 token 计（经 OMLX 数）。越大越不会在素材多的日子丢片段；文本模型可吃超大上下文，这个上限只是为了约束本地推理开销。',
  'roughcut.stagedBudget': '单日素材目录上限（快速，token）',
  'roughcut.stagedBudgetDesc': '快速模式会把台词内联进目录（它没有工具可取），所以比 Agent 模式填得更快；按真实 token 计（经 OMLX 数）。越大送进模型的台词越完整，本地推理开销也越高。',
  'roughcut.promptTitle': '导演 Prompt',
  'roughcut.promptHelp': '编辑导演的 system prompt。占位符 {aspect}、{target}、{style} 会在每次请求时自动替换。',
  'roughcut.promptCustom': '正在使用自定义 prompt',
  'roughcut.promptDefault': '正在使用自带默认 prompt',
  'roughcut.save': '保存',
  'roughcut.saved': '已保存',
  'roughcut.reset': '恢复默认',
  'roughcut.cancel': '取消',

  'subtitles.title': '字幕导出',
  'subtitles.desc': '选择一个剪辑好的视频和输出文件夹，导出根据音频转写生成的字幕。',
  'subtitles.chooseVideo': '选择视频',
  'subtitles.chooseFolder': '选择输出文件夹',
  'subtitles.video': '视频',
  'subtitles.folder': '输出文件夹',
  'subtitles.noVideo': '尚未选择视频',
  'subtitles.noFolder': '尚未选择文件夹',
  'subtitles.formats': '格式',
  'subtitles.itt': 'iTT',
  'subtitles.srt': 'SRT',
  'subtitles.languageNote': '字幕语言跟随设置中的 AI 输出语言。',
  'subtitles.export': '导出',
  'subtitles.exporting': '导出中…',
  'subtitles.done': '字幕已导出',
  'subtitles.failed': '导出失败 — 请查看日志了解详情。',
  'subtitles.reveal': '在 Finder 中显示',
  'subtitles.close': '关闭',
  'subtitles.progressTitle': '正在转写音频…',
  'subtitles.phaseSeparating': '分离人声中…',
  'subtitles.phaseTranscribing': '转写中…',
  'subtitles.phaseDownloadingModel': '正在下载语音模型…',
  'subtitles.progressHint': '视频较长时可能需要几分钟，请保持此页面打开。',
  'subtitles.downloadingModelHint': '首次使用需下载语音模型（数 GB），仅需一次；下载完成后会自动开始转写。',
  'subtitles.elapsed': '已用时 {time}',

  'logs.title': '后端日志',
  'logs.empty': '暂无日志',
  'logs.autoscroll': '自动滚动',
  'logs.clear': '清空',
  'logs.close': '关闭',
  'logs.paused': '已暂停',
  'logs.live': '实时',

  'gallery.clipsCount': '{n} 个片段',
  'gallery.sort': '排序',
  'gallery.sortDateNewest': '日期（最新）',
  'gallery.sortDateOldest': '日期（最旧）',
  'gallery.emptyTitle': '暂无片段',
  'gallery.emptyDesc': '添加素材文件夹并扫描，素材会显示在这里。',
  'gallery.unknownDate': '未知日期',
  'gallery.openFolder': '在 Finder 中打开',
  'gallery.collapse': '收起',
  'gallery.expand': '展开',
  'gallery.collapseAll': '全部收起',
  'gallery.expandAll': '全部展开',

  'card.reanalyze': '重新分析',
  'card.photo': '照片',
  'card.reanalyzing': '重新分析中…',
  'card.openVideo': '打开视频',
  'card.partial': '部分',
  'card.partialTitle': 'AI 分析未完成，可重新分析',

  'filters.title': '筛选',
  'filters.expand': '展开筛选',
  'filters.collapse': '收起筛选',
  'filters.type': '类型',
  'filters.all': '全部',
  'filters.photo': '照片',
  'filters.date': '日期',
  'filters.allDates': '全部日期',
  'filters.tags': '标签',
  'filters.searchTags': '搜索标签…',
  'filters.noTags': '暂无标签',
  'filters.noMatchingTags': '没有匹配的标签',
  'filters.showAll': '显示全部 {n}',
  'filters.showLess': '收起',
  'filters.clearAll': '清除所有筛选',

  'detail.fileDestination': '文件位置',
  'detail.captureDate': '拍摄日期',
  'detail.captureDateFromFile': '拍摄日期（来自文件时间）',
  'detail.summaryARoll': '摘要（A-roll）',
  'detail.descriptionBRoll': '描述（B-roll）',
  'detail.photo': '照片',
  'detail.photoDescription': '描述',
  'detail.transcript': '转写文本',
  'detail.sourceFile': '源文件',
  'detail.metadata': '元数据',
  'detail.duration': '时长',
  'detail.resolution': '分辨率',
  'detail.frameRate': '帧率',
  'detail.codec': '编码',
  'detail.loadingClip': '加载中…',
  'detail.openVideo': '打开视频',
  'detail.reanalyze': '重新分析',
  'detail.reanalyzing': '重新分析中…',
  'detail.closePanel': '关闭面板',
  'detail.addTag': '添加标签…',
  'detail.add': '添加',
  'detail.save': '保存',
  'detail.saving': '保存中…',
  'detail.removeTag': '移除标签 {name}',
  'detail.minutes': '分钟',
  'detail.fps': 'fps',
  'detail.suggestedCuts': '剪辑建议',
  'detail.suggestKeyframes': '推荐关键帧',
  'detail.suggesting': '分析中…',
  'detail.noKeyframes': '暂无建议 —— 点「推荐关键帧」生成。',

  'card.hasKeyframes': '已有剪辑建议',

  'common.close': '关闭',

  'scan.title': '扫描',
  'scan.pausedConfirm':
    '任务队列已暂停，扫描出的新任务不会自动开始处理。\n\n点击「确定」恢复处理并开始扫描；点击「取消」放弃本次扫描。',

  'jobs.title': '任务队列',
  'jobs.pause': '暂停',
  'jobs.resume': '恢复',
  'jobs.resumeProcessing': '恢复处理',
  'jobs.close': '关闭',
  'jobs.pausedBanner': '队列已暂停 — 排队中的任务不会被处理。点击「恢复」继续。',
  'jobs.empty': '暂无任务',
  'jobs.colId': 'ID',
  'jobs.colType': '类型',
  'jobs.colStatus': '状态',
  'jobs.colProgress': '进度',
  'jobs.colStartTime': '开始时间',
  'jobs.colActions': '操作',
  'jobs.retryFailed': '重试失败项',
  'jobs.delete': '删除',
  'jobs.noNewFiles': '无新文件',
  'jobs.failedN': '失败 {n}',
  'jobs.kindScan': '扫描',
  'jobs.kindReanalyze': '重新分析',
  'jobs.kindKeyframes': '关键帧',
  'jobs.kindSubtitle': '字幕',
  'jobs.kindCutplan': '初剪',
  'jobs.statusQueued': '排队中',
  'jobs.statusRunning': '进行中',
  'jobs.statusDone': '已完成',
  'jobs.statusFailed': '失败',
  'jobs.statusCancelled': '已取消',
  'jobs.statusPaused': '已暂停',

  'jobs.scanning': '扫描中…',
  'jobs.suggestingKeyframes': '生成关键帧中…',
  'jobs.reanalyzing': '重新分析中…',
  'jobs.speechModelDownloadHint': '首次遇到有人声的片段会下载语音识别模型（几分钟），仅首次需要。',
  'jobs.toastStarted': '扫描开始 — 正在处理片段',
  'jobs.toastCompleted': '扫描完成 — 已处理 {n} 个片段',
  'jobs.toastFailed': '扫描失败 — 请查看日志了解详情',

  'settings.title': '设置',
  'settings.backToGallery': '返回图库',
  'settings.loading': '加载设置中…',
  'settings.failedLoad': '加载设置失败：{message}',
  'settings.setupTitle': '设置素材库',
  'settings.setupDesc':
    '还没有配置素材库。请输入一个绝对路径，CutFinder 会在这里存放整理后的副本、缩略图和目录数据库。',
  'settings.setLibrary': '设置素材库',
  'settings.setting': '设置中…',
  'settings.newLibraryPlaceholder': '/Users/你/Movies/CutFinder Library',

  'settings.sourceFolders': '素材文件夹',
  'settings.sourceFoldersDesc':
    '这些文件夹是你的原始视频素材（只读，不会被修改或移动）。扫描时 CutFinder 只会读取这些文件夹里的文件。',
  'settings.addFolder': '添加文件夹',
  'settings.libraryPath': '素材库路径',
  'settings.libraryPathDesc':
    '组织后的素材副本、缩略图和目录数据库会存储在这里。切换到其他目录会改用那个库（每个库各自独立，当前库不会被修改）。',
  'settings.choose': '选择…',
  'settings.selecting': '选择中…',

  'settings.omlxConnection': 'OMLX 连接',
  'settings.omlxConnectionDesc':
    '本地 OMLX 推理服务的地址和密钥（全机共用，存储在 ~/.cutfinder/config.json，无需 .env 文件）。这里保存的值优先生效，会覆盖 .env / 环境变量。',
  'settings.baseUrl': 'Base URL',
  'settings.apiKey': 'API 密钥',
  'settings.apiKeyConfigured': '已配置 — 留空则保持不变，输入新值则覆盖',
  'settings.apiKeyNotConfigured': '尚未配置',
  'settings.apiKeyPlaceholder': '••••••••（留空不修改）',
  'settings.textModel': '文本模型',
  'settings.textModelDesc':
    '用于 A-roll 的中文摘要 + 标签生成（通过 OMLX，纯文本模型）。留空则用默认 Qwen3.6-35B-A3B。',
  'settings.visionModel': '视觉模型',
  'settings.visionModelDesc':
    '用于 B-roll 的视觉标签 + 描述生成（通过 OMLX，多模态模型）。留空则用默认 Qwen3-VL-8B。',

  'settings.whisperTitle': '语音引擎（语音转写）',
  'settings.whisperDesc': 'A-roll 语音转文字的方式——全程通用：编目分析、关键帧、字幕导出都用它。本地运行，不经过 OMLX。',
  'settings.whisperModel': 'Whisper model',
  'settings.whisperModelDesc': 'HuggingFace 模型 id。首次使用时下载到项目的 models/ 目录，之后离线加载。',
  'settings.speechEngine': '引擎',
  'settings.speechEngineDesc': 'Whisper，或 Qwen3-ASR + ForcedAligner（中文 / 中英混合更准确，字幕带真实的逐词时间轴）。',
  'settings.engineWhisper': 'Whisper（large-v3）',
  'settings.engineQwen': 'Qwen3-ASR + ForcedAligner',
  'settings.qwenAsrModel': 'Qwen ASR 模型',
  'settings.qwenAlignerModel': 'Qwen ForcedAligner 模型',
  'settings.qwenMaxChunk': '分段最大秒数',
  'settings.qwenMaxChunkDesc': '转写+对齐前，音频会按静音（VAD）切成不超过该长度的片段。越大切分越少、速度越快。最大 300 秒：对齐器单段只能标注约 400 秒以内的时间戳，超过会丢失时间轴。',

  'settings.processingOptions': '处理选项',
  'settings.supportedExtensions': '支持的扩展名',
  'settings.supportedExtensionsDesc': '扫描时只处理这些后缀的视频文件',
  'settings.photoExtensions': '照片扩展名',
  'settings.photoExtensionsDesc': '这些后缀的文件会作为照片入库',
  'settings.brollFrameCount': 'B-roll 帧数',
  'settings.brollFrameCountDesc': 'B-roll 视觉分析时提取的视频帧数，越多越准确但处理更慢',
  'settings.vadThreshold': 'VAD 阈值 (0–1)',
  'settings.vadThresholdDesc': '语音检测灵敏度阈值，越高越严格（只标记有明显人声的片段为 A-roll）',
  'settings.vocalSeparation': 'A-roll 转写前分离人声（去 BGM，较慢）',
  'settings.vocalSeparationDesc': '转写前用 Demucs 去掉背景音乐。仅影响开启后新扫描的素材；字幕导出始终分离。',
  'settings.aiOutputLanguage': 'AI 输出语言',
  'settings.aiOutputLanguageDesc': 'AI 生成的摘要、标签等文字输出的语言',
  'settings.keyframeCount': '每段关键帧建议数',
  'settings.keyframeCountDesc': '每段素材生成的剪辑/帧建议上限（1–10）',
  'settings.keyframeAuto': '扫描后自动推荐关键帧',
  'settings.keyframeAutoDesc': '扫描完成后，自动为新片段排队生成关键帧建议',
  'settings.roughcutTitle': '初剪导演 Agent',
  'settings.langZh': '中文',
  'settings.langEn': 'English',
  'settings.uiLanguage': '界面语言',
  'settings.uiLanguageDesc': '应用界面的语言（与 AI 输出语言相互独立）',
  'settings.save': '保存设置',
  'settings.saving': '保存中…',
  'settings.remove': '移除 {name}',
  'settings.validationInt': '必须是 ≥1 的整数',
  'settings.validationNum': '必须是 0 到 1 之间的数字',
  'settings.switchLibraryConfirm':
    '切换素材库到:\n{path}\n\n应用将改用这个目录的目录数据库、缩略图和设置（每个库各自独立）。当前库不会被修改。是否继续？',
  'settings.cleanupDeleted': '清理已删除的文件',
  'settings.cleanupNone': '无需清理 — 每条目录记录的文件都还在。',
  'settings.cleanupUnreachable': '素材库目录不可达（例如外接盘未挂载）。已跳过，以免误删整个目录。',
  'settings.cleanupConfirm': '有 {n} 条目录记录指向的文件已不存在。删除这些记录（及其缩略图/关键帧）？原始文件不受影响。',
  'settings.cleanupDone': '已清理 {n} 条记录。',
  'confirm.confirm': '确定',
  'confirm.cancel': '取消',
}

const dict: Record<Lang, Record<Key, string>> = { en, zh }

type Vars = Record<string, string | number>

function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template
  return template.replace(/\{(\w+)\}/g, (_, k: string) => (k in vars ? String(vars[k]) : `{${k}}`))
}

export interface I18n {
  lang: Lang
  setLang: (lang: Lang) => void
  t: (key: Key, vars?: Vars) => string
}

function translate(lang: Lang, key: Key, vars?: Vars): string {
  return interpolate(dict[lang][key] ?? dict.en[key] ?? key, vars)
}

// Default value: English passthrough, so components used outside the provider
// (isolated unit tests) render English without crashing.
const I18nContext = createContext<I18n>({
  lang: 'en',
  setLang: () => {},
  t: (key, vars) => translate('en', key, vars),
})

function readInitialLang(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'en' || stored === 'zh') return stored
  } catch {
    /* localStorage unavailable — fall through to default */
  }
  return 'en'
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readInitialLang)

  const value = useMemo<I18n>(
    () => ({
      lang,
      setLang: (next: Lang) => {
        setLangState(next)
        try {
          localStorage.setItem(STORAGE_KEY, next)
        } catch {
          /* ignore persistence errors */
        }
      },
      t: (key, vars) => translate(lang, key, vars),
    }),
    [lang],
  )

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18n {
  return useContext(I18nContext)
}
