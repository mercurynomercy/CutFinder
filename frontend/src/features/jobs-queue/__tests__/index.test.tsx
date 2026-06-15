/** Tests for the JobsQueuePage feature — job list, delete, retry, pause/resume.
 *
 * Behavior-focused (rendered text + network effects). Each test installs its
 * own stateful MSW handlers via server.use() for determinism.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { server } from '@/test/mocks/server'
import type { JobStatus } from '@/api/client'
import { JobsQueuePage } from '../index'

const API = 'http://localhost:5080/api'

function job(overrides: Partial<JobStatus> = {}): JobStatus {
  return {
    id: 1,
    status: 'done',
    total: 3,
    done: 3,
    failed: 0,
    started_at: '2024-06-15T10:30:00Z',
    finished_at: null,
    kind: 'scan',
    ...overrides,
  }
}

/** Install a stateful /api/jobs queue backed by a local array. */
function installQueue(initial: JobStatus[], opts: { paused?: boolean } = {}) {
  let jobs = [...initial]
  let paused = opts.paused ?? false
  const retry = vi.fn()
  const del = vi.fn()

  server.use(
    http.get(`${API}/jobs`, () => HttpResponse.json({ jobs, paused })),
    http.delete(`${API}/jobs/:id`, ({ params }) => {
      const id = Number(params.id)
      del(id)
      jobs = jobs.filter((j) => j.id !== id)
      return HttpResponse.json({ status: 'ok', job_id: id })
    }),
    http.post(`${API}/jobs/:id/retry`, ({ params }) => {
      const id = Number(params.id)
      const j = jobs.find((x) => x.id === id)
      if (!j || j.failed === 0) {
        return HttpResponse.json({ detail: 'No failed items' }, { status: 400 })
      }
      retry(id)
      return HttpResponse.json({ job_id: id })
    }),
    http.post(`${API}/jobs/pause`, () => { paused = true; return HttpResponse.json({ paused: true }) }),
    http.post(`${API}/jobs/resume`, () => { paused = false; return HttpResponse.json({ paused: false }) }),
  )

  return { retry, del }
}

describe('JobsQueuePage', () => {
  it('renders jobs with Chinese status labels', async () => {
    installQueue([
      job({ id: 1, kind: 'scan', status: 'running', total: 10, done: 4 }),
      job({ id: 2, kind: 'reanalyze', status: 'failed', total: 5, done: 3, failed: 2 }),
    ])

    render(<JobsQueuePage onClose={() => {}} />)

    expect(await screen.findByText('进行中')).toBeInTheDocument()
    expect(screen.getByText('失败')).toBeInTheDocument()
    expect(screen.getByText('扫描')).toBeInTheDocument()
    expect(screen.getByText('重新分析')).toBeInTheDocument()
  })

  it('renders the empty state when there are no jobs', async () => {
    installQueue([])
    render(<JobsQueuePage onClose={() => {}} />)
    expect(await screen.findByText('暂无任务')).toBeInTheDocument()
  })

  it('deletes a job and removes its row', async () => {
    const { del } = installQueue([
      job({ id: 1, kind: 'scan', status: 'done' }),
      job({ id: 2, kind: 'reanalyze', status: 'done' }),
    ])

    render(<JobsQueuePage onClose={() => {}} />)
    expect(await screen.findByText('重新分析')).toBeInTheDocument()

    const deleteButtons = screen.getAllByRole('button', { name: '删除' })
    await userEvent.click(deleteButtons[1])

    await waitFor(() => expect(del).toHaveBeenCalledWith(2))
    await waitFor(() => expect(screen.queryByText('重新分析')).not.toBeInTheDocument())
  })

  it('only shows 重试失败项 for jobs with failed>0 and calls retryJob', async () => {
    const { retry } = installQueue([
      job({ id: 1, kind: 'scan', status: 'done', failed: 0 }),
      job({ id: 2, kind: 'reanalyze', status: 'failed', total: 5, done: 3, failed: 2 }),
    ])

    render(<JobsQueuePage onClose={() => {}} />)
    await screen.findByText('重新分析')

    const retryButtons = screen.getAllByRole('button', { name: '重试失败项' })
    expect(retryButtons).toHaveLength(1)

    await userEvent.click(retryButtons[0])
    await waitFor(() => expect(retry).toHaveBeenCalledWith(2))
  })

  it('pauses then resumes, toggling the button label', async () => {
    installQueue([job({ id: 1, status: 'running' })], { paused: false })

    render(<JobsQueuePage onClose={() => {}} />)

    const pauseBtn = await screen.findByRole('button', { name: '暂停' })
    await userEvent.click(pauseBtn)

    expect(await screen.findByRole('button', { name: '恢复' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '恢复' }))
    expect(await screen.findByRole('button', { name: '暂停' })).toBeInTheDocument()
  })
})
