/** Placeholder e2e test — will be replaced with real flows (gallery → filter → detail). */

import { test, expect } from '@playwright/test'

test('shows placeholder text on load', async ({ page }) => {
  await page.goto('/')
  // The scaffold renders a "Loading..." placeholder until the gallery is implemented.
  await expect(page.locator('p:text-is("Loading…")')).toBeVisible()
})
