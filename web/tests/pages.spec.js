import { test, expect } from '@playwright/test'
const api = process.env.E2E_API_URL || 'http://127.0.0.1:8011'
const exchangeRequests = new WeakMap()

test.beforeEach(async ({ page }) => {
  // Any wallet or exchange execution attempt is a test failure, including accidental auto-connect.
  await page.addInitScript(() => { window.__walletRequests = []; window.ethereum = { request: args => { window.__walletRequests.push(args.method); throw new Error('Wallet requests forbidden in practice tests') } } })
  exchangeRequests.set(page, [])
  await page.route('**/exchange', route => { exchangeRequests.get(page).push(route.request().url()); return route.abort() })
})

test.afterEach(async ({ page }) => {
  expect(exchangeRequests.get(page)).toEqual([])
  expect(await page.evaluate(() => window.__walletRequests || [])).toEqual([])
})

test('homepage to actual practice workspace, refresh and navigation', async ({ page }, info) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Your friends. Your own trade.' })).toBeVisible()
  await page.getByRole('link', { name: 'Try the practice app' }).click()
  await expect(page).toHaveURL(/\/app\/$/)
  await expect(page.getByRole('heading', { name: 'Practice workspace' })).toBeVisible()
  await expect(page.getByText('Practice mode', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Practice groups' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
  await page.screenshot({ path: `test-results/practice-${info.project.name}.png`, fullPage: true })
  await page.getByRole('link', { name: 'Home', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Your friends. Your own trade.' })).toBeVisible()
  await page.screenshot({ path: `test-results/home-${info.project.name}.png`, fullPage: true })
  expect(errors).toEqual([])
})

test('legacy and deep links open the research screen', async ({ page }) => {
  await page.goto('/#/lab?idea=buy%20BTC')
  await expect(page).toHaveURL(/\/app\/#\/lab/)
  await expect(page.getByRole('heading', { name: 'Test your idea' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Your what-if' })).toHaveValue('buy BTC')
  await page.goto('/app/lab')
  await expect(page).toHaveURL(/\/app\/#\/lab/)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Test your idea' })).toBeVisible()
})

test('research reaches the actual backend and renders the result', async ({ page }) => {
  await page.goto('/app/#/lab')
  await page.getByRole('textbox', { name: 'Your what-if' }).fill('what if I bought BTC every day for 30 days')
  const response = page.waitForResponse(r => r.url() === `${api}/lab/chat` && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Run', exact: true }).click()
  const r = await response
  expect(r.ok()).toBeTruthy()
  const data = await r.json()
  expect(['backtest', 'error', 'clarify']).toContain(data.kind)
  // A data-quality refusal is valid evidence, not a fabricated backtest.
  await expect(page.locator('.msg.ai').last()).toContainText(data.reply)
})

test('practice funding never requests a wallet or sends payment', async ({ page }) => {
  const writes = []
  page.on('request', r => { if (r.method() === 'POST') writes.push(r.url()) })
  await page.goto('/app/#/join')
  await page.getByRole('button', { name: 'Preview checkout', exact: true }).click()
  await page.getByRole('button', { name: 'Simulate funds arriving' }).click()
  await page.getByRole('button', { name: 'Confirm paper contribution' }).click()
  await expect(page.getByRole('heading', { name: 'Preview complete' })).toBeVisible()
  expect(writes).toEqual([])
})

test('existing group chat loads and fee approval stays explicit', async ({ page }) => {
  await page.goto('/app/#/huddle/demo')
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Copy invite link' })).toBeVisible()
  await page.goto('/app/#/approve')
  await expect(page.getByRole('button', { name: /connect/i })).toBeVisible()
})

test('API allows Pages origin, rejects foreign origin and unauthenticated access', async ({ request }) => {
  const health = await request.get(`${api}/health`, { headers: { Origin: 'https://protoss.trade' } })
  expect(health.headers()['access-control-allow-origin']).toBe('https://protoss.trade')
  expect(['paper', 'sim']).toContain((await health.json()).mode)
  const foreign = await request.fetch(`${api}/health`, { method: 'OPTIONS', headers: { Origin: 'https://untrusted.example', 'Access-Control-Request-Method': 'POST' } })
  expect(foreign.status()).toBe(400)
  const protectedData = await request.get(`${api}/v1/orders`)
  expect([401, 403]).toContain(protectedData.status())
})

test('API failure shows an error instead of invented balances', async ({ page }) => {
  await page.route('**/leaderboard?*', route => route.abort())
  await page.goto('/app/')
  await expect(page.getByText(/Practice activity is temporarily unavailable/i).first()).toBeVisible()
})
