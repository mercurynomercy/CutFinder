/** Date helpers for grouping/filtering clips by shooting day.

`capture_time` is stored as a UTC instant by the backend. The shooting day a
user cares about is the *local* calendar date of that instant — the same date
the detail panel shows via `toLocaleDateString` and the same date the backend
files the copy under. Slicing the raw ISO string (UTC) instead mis-groups
clips shot after local midnight into the previous day.

Usage:
  localDateKey('2026-05-09T22:24:16Z') // → '2026-05-10' in a UTC+8 locale
*/

/** Return the local-time `YYYY-MM-DD` for an ISO instant, or null if absent/invalid. */
export function localDateKey(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
