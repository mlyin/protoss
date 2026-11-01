import { test, expect } from '@playwright/test'
const api = process.env.E2E_API_URL || 'http://127.0.0.1:8011'
const exchangeRequests = new WeakMap()

test.beforeEach(async ({ page }) => {
  // Any wallet or exchange execution attempt is a test failure, including accidental auto-connect.
  await page.addInitScript(() => { window.__walletRequests = []; window.ethereum = { request: args => { window.__walletRequests.push(args.method); throw new Error('Wallet requests forbidden in these tests') } } })
  exchangeRequests.set(page, [])
  await page.route('**/exchange', route => { exchangeRequests.get(page).push(route.request().url()); return route.abort() })
})

test.afterEach(async ({ page }) => {
  expect(exchangeRequests.get(page)).toEqual([])
  expect(await page.evaluate(() => window.__walletRequests || [])).toEqual([])
})

test('homepage leads to the four ideas, Telegram and the real accounts', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Your friends. Your own trade.' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Open Telegram' }).first()).toHaveAttribute('href', 'https://t.me/ProtossTradingDemoBot')
  for (const said of ["Let's buy XMR every time a major company gets hacked", 'I think robots are going to take over the world', 'The Anthropic bubble is going to pop', 'Dwarkesh is always right. Trade every new episode']) {
    await expect(page.getByRole('heading', { name: `“${said}”` })).toBeVisible()
  }
  await expect(page.getByText(/practice/i)).toHaveCount(0)
  await page.getByRole('link', { name: 'See the accounts' }).click()
  await expect(page).toHaveURL(/\/app\/#\/accounts$/)
  await expect(page.getByRole('heading', { name: 'Accounts', exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Home', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Your friends. Your own trade.' })).toBeVisible()
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
  await page.getByRole('textbox', { name: 'Your what-if' }).fill('I think robots are going to take over the world')
  const response = page.waitForResponse(r => r.url() === `${api}/lab/chat` && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Run', exact: true }).click()
  const r = await response
  expect(r.ok()).toBeTruthy()
  const data = await r.json()
  expect(['backtest', 'error', 'clarify']).toContain(data.kind)
  // A data-quality refusal is valid evidence, not a fabricated backtest.
  await expect(page.locator('.msg.ai').last()).toContainText(data.reply)
})


test('fee approval stays explicit', async ({ page }) => {
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

test('accounts come from Hyperliquid, and a failure shows an error instead of invented balances', async ({ page }) => {
  await page.goto('/app/#/accounts')
  await expect(page.getByRole('heading', { name: 'lando' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'second' })).toBeVisible()
  await expect(page.getByText('Equity').first()).toBeVisible()
  await page.route('https://api.hyperliquid.xyz/**', route => route.abort())
  await page.reload()
  await expect(page.getByRole('alert')).toContainText('Could not reach Hyperliquid')
  await expect(page.getByRole('heading', { name: 'lando' })).toHaveCount(0)
})
