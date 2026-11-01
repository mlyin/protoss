import { test, expect } from '@playwright/test'

const wallet = '0x' + '1'.repeat(40)
const connection = {
  display_name: 'Test owner', group: 'Test group', challenge: 'Test ownership message. No trading permission.',
  wallet: null, mode: 'sim',
}
const trade = {
  participant: 'Test owner', market: 'xyz:ANT', budget: 20, status: 'draft', wallet,
  challenge: 'Test ownership message', quote: null, receipt: null,
}

test.beforeEach(async ({ page }) => {
  await page.route('**/exchange', route => { throw new Error(`Unexpected exchange submission: ${route.request().method()}`) })
  await page.addInitScript(({ wallet }) => {
    window.__walletCalls = []
    window.ethereum = { request: async ({ method }) => {
      window.__walletCalls.push(method)
      if (method === 'eth_requestAccounts' || method === 'eth_accounts') return [wallet]
      if (method === 'personal_sign') return '0x' + '1'.repeat(130) // mock, never a real signature
      throw new Error('Trade signing is forbidden in these tests')
    } }
  }, { wallet })
})

test('legacy private connection links survive canonicalization and reload', async ({ page }, info) => {
  const requests = []
  await page.route('**/telegram/connect', route => {
    requests.push(route.request())
    return route.fulfill({ json: connection })
  })
  await page.goto('/#/telegram/connect?token=test-private-token')
  await expect(page).toHaveURL(/\/app\/#\/telegram\/connect\?token=test-private-token$/)
  await expect(page.getByRole('heading', { name: 'Your chat. Your wallet.' })).toBeVisible()
  await page.reload()
  await expect(page.getByText('Test owner', { exact: true })).toBeVisible()
  expect(requests.length).toBeGreaterThanOrEqual(2)
  for (const request of requests) {
    expect(request.url()).not.toContain('test-private-token')
    expect(request.headers().authorization).toBe('Bearer test-private-token')
  }
  expect(await page.evaluate(() => window.__walletCalls)).toEqual([])
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('test-private-token')
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
  await page.screenshot({ path: `test-results/connection-${info.project.name}.png`, fullPage: true })
})

test('wallet ownership only starts after a click and saves through the private API', async ({ page }) => {
  const posts = []
  await page.route('**/telegram/connect', route => {
    if (route.request().method() === 'POST') {
      posts.push(route.request().postDataJSON())
      return route.fulfill({ json: { wallet, ownership_verified: true } })
    }
    return route.fulfill({ json: connection })
  })
  await page.goto('/app/#/telegram/connect?token=first')
  await expect(page.getByRole('button', { name: 'Connect wallet and prove ownership' })).toBeVisible()
  expect(await page.evaluate(() => window.__walletCalls)).toEqual([])
  await page.getByRole('button', { name: 'Connect wallet and prove ownership' }).click()
  await expect(page.getByRole('heading', { name: 'Wallet ownership verified' })).toBeVisible()
  expect(posts).toEqual([{ wallet, signature: '0x' + '1'.repeat(130) }])
  expect(await page.evaluate(() => window.__walletCalls)).toEqual(['eth_requestAccounts', 'personal_sign', 'eth_accounts'])
})

test('changing private links clears previous owner state', async ({ page }) => {
  await page.route('**/telegram/connect', route => route.fulfill({ json: {
    ...connection, display_name: route.request().headers().authorization === 'Bearer first' ? 'First owner' : 'Second owner',
  } }))
  await page.goto('/app/#/telegram/connect?token=first')
  await expect(page.getByText('First owner', { exact: true })).toBeVisible()
  await page.evaluate(() => { location.hash = '#/telegram/connect?token=second' })
  await expect(page.getByText('Second owner', { exact: true })).toBeVisible()
  await expect(page.getByText('First owner', { exact: true })).toHaveCount(0)
})

test('missing and expired private links explain how to recover', async ({ page }) => {
  const reads = []
  await page.route('**/telegram/connect', route => {
    reads.push(route.request().url())
    return route.fulfill({ status: 410, json: { detail: 'connection link expired; request /join again in Telegram' } })
  })
  await page.goto('/app/#/telegram/connect')
  await expect(page.getByRole('alert')).toContainText('Open your private connection link')
  expect(reads).toEqual([])
  await page.goto('/app/#/telegram/connect?token=expired')
  await expect(page.getByRole('alert')).toContainText('request /join again')
  await expect(page.getByRole('button', { name: 'Connect wallet and prove ownership' })).toHaveCount(0)
})

test('private trade review is reachable without automatic wallet or exchange actions', async ({ page }, info) => {
  await page.route('**/live/review', route => route.fulfill({ json: trade }))
  await page.goto('/#/trade?token=review-token')
  await expect(page).toHaveURL(/\/app\/#\/trade\?token=review-token$/)
  await expect(page.getByText('Buy xyz:ANT', { exact: true })).toBeVisible()
  await expect(page.getByText('Each trade requires your wallet approval')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Get current quote' })).toBeVisible()
  expect(await page.evaluate(() => window.__walletCalls)).toEqual([])
  await expect(page.getByRole('button', { name: /Approve buy/ })).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
  await page.screenshot({ path: `test-results/review-${info.project.name}.png`, fullPage: true })
})

test('a previously prepared trade cannot be resubmitted after reload', async ({ page }) => {
  const prepared = { ...trade, status: 'prepared', quote: {
    ask: 40, size: '0.49', limit_price: '40.20', max_position_usd: 19.698,
    expires_after: Date.now() + 60000, account: { mode: 'standard' },
  } }
  await page.route('**/live/review', route => route.fulfill({ json: prepared }))
  await page.route('**/live/verify', route => route.fulfill({ json: { status: 'prepared', receipt: null } }))
  await page.goto('/app/#/trade?token=prepared')
  await expect(page.getByRole('button', { name: 'Check exchange result' })).toBeVisible()
  await expect(page.getByRole('checkbox')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Approve/ })).toHaveCount(0)
  expect(await page.evaluate(() => window.__walletCalls)).toEqual([])
})

test('leaving while trade preparation is pending never opens a wallet dialog', async ({ page }) => {
  const quote = { nonce: 123, ask: 40, size: '0.49', limit_price: '40.20', max_position_usd: 19.698,
    expires_after: Date.now() + 60000, account: { mode: 'standard' } }
  await page.route('**/live/review', route => route.fulfill({ json: trade }))
  await page.route('**/live/quote', route => route.fulfill({ json: quote }))
  let release, finish
  const pending = new Promise(resolve => { release = resolve })
  const finished = new Promise(resolve => { finish = resolve })
  await page.route('**/live/prepare', async route => {
    await pending
    await route.fulfill({ json: quote })
    finish()
  })
  await page.goto('/app/#/trade?token=old-request')
  await page.getByRole('button', { name: 'Get current quote' }).click()
  await page.getByRole('checkbox').check()
  const prepare = page.waitForRequest('**/live/prepare')
  await page.getByRole('button', { name: '1. Approve 1× setting in wallet' }).click()
  await prepare
  // In-app hash change unmounts the review without destroying this browser document.
  await page.evaluate(() => { location.hash = '#/telegram/connect' })
  await expect(page.getByRole('heading', { name: 'Your chat. Your wallet.' })).toBeVisible()
  const response = page.waitForResponse('**/live/prepare')
  release()
  await finished
  await (await response).finished()
  await expect(page.getByRole('alert')).toContainText('Open your private connection link')
  expect(await page.evaluate(() => window.__walletCalls)).toEqual([])
})

test('public Pages links use the configured API and ignore an injected backend URL', async ({ page, baseURL }) => {
  await page.route('https://protoss.trade/**', async route => {
    const url = new URL(route.request().url())
    const response = await route.fetch({ url: baseURL + url.pathname + url.search })
    await route.fulfill({ response })
  })
  const requests = []
  await page.route('https://api.protoss.trade/telegram/connect', route => {
    requests.push(route.request())
    return route.fulfill({ json: connection })
  })
  await page.route('https://untrusted.example/**', () => { throw new Error('Private token sent to untrusted origin') })
  await page.goto('https://protoss.trade/app/#/telegram/connect?token=pages-token&api=https://untrusted.example')
  await expect(page.getByText('Test owner', { exact: true })).toBeVisible()
  expect(requests).toHaveLength(1)
  expect(requests[0].headers().authorization).toBe('Bearer pages-token')
  expect(requests[0].headers().referer).toBeUndefined()
})
