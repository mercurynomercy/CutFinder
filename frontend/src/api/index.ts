/** Barrel exports for the API client and SSE hooks. */

export { api, ApiError } from './client'
export type {
  ClipCandidate, JobStatus, ClipSummary, ClipDetail, TagItem,
  TranscriptData, TranscriptSegment, SettingsPrefs, SettingsResponse,
  UpdateSettingsBody, ClipFilter, ClipEditBody, TagListBody,
} from './client'

export { useJobEvents, useSSE } from './sse'
export type { JobEvent } from './sse'
