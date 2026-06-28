/** Tests for `localDateKey()` — local-time grouping key for clips. */

import { describe, it, expect } from 'vitest'
import { localDateKey } from '@/lib/date'

describe('localDateKey', () => {
  it('returns null for empty/invalid input', () => {
    expect(localDateKey(null)).toBeNull()
    expect(localDateKey(undefined)).toBeNull()
    expect(localDateKey('')).toBeNull()
    expect(localDateKey('not-a-date')).toBeNull()
  })

  it('matches the detail-panel localized date regardless of timezone (regression)', () => {
    // The grouping key must agree with what the detail panel shows via
    // toLocaleDateString — otherwise a clip shot after local midnight is
    // grouped under the previous (UTC) day. This holds in any test-runner tz.
    const iso = '2026-05-09T22:24:16Z'
    const key = localDateKey(iso)
    expect(key).not.toBeNull()
    const localized = new Date(iso).toLocaleDateString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
    })
    expect((key as string).replace(/-/g, '/')).toBe(localized)
  })
})
