import '@testing-library/jest-dom/vitest'

// Global Vitest + RTL setup for the CutFinder frontend.
import { afterAll, afterEach, beforeAll } from 'vitest'

import { server } from './mocks/server'

// Establish API mocking (MSW node server) for all tests. jsdom has no service
// worker, so we use setupServer (node) rather than the browser worker.
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
