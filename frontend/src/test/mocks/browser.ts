/** MSW browser worker — starts the service worker for all frontend tests.

Import this file at the top of any test that needs HTTP mocking:
  import '../test/mocks/browser'

MSW is configured via handlers in `handlers.ts`.
*/

import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

// This worker will start the service worker for tests.
export const worker = setupWorker(...handlers)
