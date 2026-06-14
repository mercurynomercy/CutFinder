import '@testing-library/jest-dom/vitest'

// Global Vitest + RTL setup for the CutFinder frontend.
import { afterAll, beforeAll } from 'vitest'

// MSW's setupWorker only works in a real browser environment.
// For jsdom tests that don't need HTTP mocking, skip MSW setup entirely.
const isBrowserEnvironment = typeof window !== 'undefined' && !!window.navigator?.serviceWorker

if (isBrowserEnvironment) {
  const { worker } = await import('./mocks/browser')

  // Establish API mocking before all tests.
  beforeAll(() => worker.listen({ onUnhandledRequest: 'bypass' }))

  // Reset any request handlers that are added during tests.
  afterAll(() => worker.resetHandlers())
}
