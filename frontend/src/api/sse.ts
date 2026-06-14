/** SSE (Server-Sent Events) subscription hook for real-time progress updates.

Listens to `GET /api/jobs/{id}/events` and yields events as they arrive.
Cleans up the fetch connection on unmount or when the job completes/fails.

Usage:
  const events = useJobEvents(jobId)
  // events is { loading, error, data: JobEvent[] }

Job event structure (from backend):
  { type: 'progress' | 'job_started' | 'clip_done' | 'job_completed' | ...
    job_id: number, done?: number, total?: number }
*/

import { useEffect, useRef, useState } from 'react'

export interface JobEvent extends Record<string, unknown> {
  type?: string
  job_id: number
  done?: number
  total?: number
}

interface UseJobEventsReturn {
  loading: boolean
  error: Error | null
  events: JobEvent[]
}

const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5080'

/**
 * React hook that subscribes to SSE events for a specific job.
 * Returns loading state, error (if any), and the accumulated event list.
 */
export function useJobEvents(jobId: number | null): UseJobEventsReturn {
  const [events, setEvents] = useState<JobEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // Keep a ref to the AbortController so we can cancel on cleanup
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (jobId === null || jobId === undefined) return

    // Cancel any previous subscription
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setEvents([])
    setError(null)

    const url = `${BASE}/api/jobs/${jobId}/events`
    let active = true

    fetch(url, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`SSE connection failed: ${response.status}`)
        const reader = response.body?.getReader()
        if (!reader) throw new Error('No readable stream in SSE response')

        const decoder = new TextDecoder()
        let buffer = ''

        while (active) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          // SSE events are delimited by double newlines; split and parse each event line
          const lines = buffer.split(/\n\n/)
          // Keep the last (possibly incomplete) chunk in buffer
          buffer = lines.pop() || ''

          for (const block of lines) {
            const dataLine = block.split('\n').find((l) => l.startsWith('data: '))
            if (dataLine) {
              try {
                const event = JSON.parse(dataLine.slice(6)) as JobEvent
                setEvents((prev) => [...prev, event])
              } catch {
                // Silently skip unparseable events (keep stream alive)
              }
            }
          }
        }

        setLoading(false)
      })
      .catch((err: unknown) => {
        if (!active || (err instanceof DOMException && err.name === 'AbortError')) return
        setError(err instanceof Error ? err : new Error(String(err)))
        setLoading(false)
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [jobId])

  return { loading, error, events }
}

/**
 * Generic SSE subscription hook — subscribes to any URL and yields raw events.
 */
export function useSSE(url: string | null): UseJobEventsReturn {
  const [events, setEvents] = useState<JobEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!url) return

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setEvents([])
    setError(null)

    let active = true

    fetch(url, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`SSE connection failed: ${response.status}`)
        const reader = response.body?.getReader()
        if (!reader) throw new Error('No readable stream')

        const decoder = new TextDecoder()
        let buffer = ''

        while (active) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split(/\n\n/)
          buffer = lines.pop() || ''

          for (const block of lines) {
            const dataLine = block.split('\n').find((l) => l.startsWith('data: '))
            if (dataLine) {
              try {
                const event = JSON.parse(dataLine.slice(6)) as JobEvent
                setEvents((prev) => [...prev, event])
              } catch { /* skip */ }
            }
          }
        }

        setLoading(false)
      })
      .catch((err: unknown) => {
        if (!active || (err instanceof DOMException && err.name === 'AbortError')) return
        setError(err instanceof Error ? err : new Error(String(err)))
        setLoading(false)
      })

    return () => { active = false; controller.abort() }
  }, [url])

  return { loading, error, events }
}
