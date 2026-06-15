/** MSW node server — used by Vitest (jsdom) for HTTP mocking.
 *
 * jsdom has no service worker, so tests use `setupServer` (Node) rather than
 * the browser worker in `browser.ts` (which is for Playwright e2e).
 */
import { setupServer } from 'msw/node'

import { handlers } from './handlers'

export const server = setupServer(...handlers)
