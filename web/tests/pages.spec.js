import { test, expect } from '@playwright/test'
const owner = '0x' + '1'.repeat(40)
const other = '0x' + '2'.repeat(40)
const attempts = new WeakMap()

// Test fixtures stay in the test bundle. The published app never receives sample accounts or positions.
test.beforeEach(async ({ page }) => {
  attempts.set(page, [])
  await page.route('**/exchange', route => { attempts.get(page).push(route.request().url()); return route.abort() })
  await page.addInitScript(({ owner }) => {
    window.__walletRequests = []
    window.__accountListeners = {}
    window.ethereum = {
      request: async args => {
        window.__walletRequests.push(args.method)
        if (args.method !== 'eth_requestAccounts') throw new Error('Signing and trading are forbidden')
        return [owner]
      },
      on: (event, handler) => { window.__accountListeners[event] = handler },
      removeListener: (event, handler) => { if (window.__accountListeners[event] === handler) delete window.__accountListeners[event] },
    }
  }, { owner })
})
test.afterEach(async ({ page }) => {
  expect(attempts.get(page)).toEqual([])
  expect((await page.evaluate(() => window.__walletRequests || [])).every(method => method === 'eth_requestAccounts')).toBeTruthy()
})

async function marketData(page, { empty = false, fail = '', delay = 0 } = {}) {
  const reads = []
  await page.route('https://api.hyperliquid.xyz/info', async route => {
    const body = route.request().postDataJSON()
    reads.push(body)
    if (body.type === 'metaAndAssetCtxs') return route.fulfill({ json: [{ universe: [{ name: 'XMR' }] }, [{ markPx: '200' }]] })
    if (body.type === 'perpDexs') return route.fulfill({ json: [null, { name: 'xyz' }] })
    if (body.type !== 'clearinghouseState') throw new Error('Unexpected data access')
    if (delay && body.user === other) await new Promise(r => setTimeout(r, delay))
    if (fail === 'all' || (fail && fail === body.dex)) return route.fulfill({ status: 503, json: {} })
    const positions = empty || body.user === other ? [] : [{ position: { coin: body.dex ? 'xyz:ANT' : 'BTC', szi: body.dex ? '-0.25' : '0.01', entryPx: '100', positionValue: '25', unrealizedPnl: '-2.50' } }]
    await route.fulfill({ json: { assetPositions: positions } })
  })
  return reads
}

test('homepage contains the real account entry and no practice navigation', async ({ page }, info) => {
  const reads = await marketData(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Your friends. Your own trade.' })).toBeVisible()
  await expect(page.getByRole('tab')).toHaveCount(4)
  await expect(page.getByRole('link', { name: 'Practice app', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Activity', exact: true })).toHaveCount(0)
  expect(reads.every(r => r.type === 'metaAndAssetCtxs')).toBeTruthy()
  expect(await page.evaluate(() => window.__walletRequests)).toEqual([])
  await page.screenshot({ path: `test-results/home-${info.project.name}.png`, fullPage: true })
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Friends & positions', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/$/)
  await expect(page.getByRole('heading', { name: 'Connect your account' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
})

test('connection reads actual venue responses and never calls the exchange', async ({ page }, info) => {
  const reads = await marketData(page)
  await page.goto('/app/')
  await page.getByRole('button', { name: 'Connect wallet', exact: true }).click()
  await expect(page.getByText('BTC', { exact: true })).toBeVisible()
  await expect(page.getByText('xyz:ANT', { exact: true })).toBeVisible()
  expect(reads).toEqual([{ type: 'perpDexs' }, { type: 'clearinghouseState', user: owner, dex: '' }, { type: 'clearinghouseState', user: owner, dex: 'xyz' }])
  await expect(page.getByText('Long', { exact: true })).toBeVisible()
  await expect(page.getByText('Short', { exact: true })).toBeVisible()
  await expect(page.getByText('No friends added yet.')).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
  await page.screenshot({ path: `test-results/account-${info.project.name}.png`, fullPage: true })
})

test('empty exchange responses render an honest empty state', async ({ page }) => {
  await marketData(page, { empty: true })
  await page.goto('/app/')
  await page.getByRole('button', { name: 'Connect wallet', exact: true }).click()
  await expect(page.getByText('No open positions.', { exact: true })).toBeVisible()
  await expect(page.locator('.real-position')).toHaveCount(0)
})

test('missing markets do not masquerade as a flat account', async ({ page }) => {
  await marketData(page, { empty: true, fail: 'all' })
  await page.goto('/app/')
  await page.getByRole('button', { name: 'Connect wallet', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Positions below may be incomplete')
  await expect(page.getByText('No open positions.', { exact: true })).toHaveCount(0)
})

test('wallet change and disconnect immediately clear the previous positions', async ({ page }) => {
  await marketData(page, { delay: 800 })
  await page.goto('/app/')
  await page.getByRole('button', { name: 'Connect wallet', exact: true }).click()
  await expect(page.getByText('BTC', { exact: true })).toBeVisible()
  await page.evaluate(other => window.__accountListeners.accountsChanged([other]), other)
  await expect(page.getByText('BTC', { exact: true })).toHaveCount(0)
  await expect(page.getByText('No open positions.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Disconnect', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Connect your account' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'My positions', exact: true })).toHaveCount(0)
})

test('friends are explicitly added contacts scoped to the connected wallet', async ({ page }) => {
  await marketData(page, { empty: true })
  await page.goto('/app/')
  await page.getByRole('button', { name: 'Connect wallet', exact: true }).click()
  await page.getByRole('button', { name: 'Add friend', exact: true }).click()
  await page.getByLabel('Name', { exact: true }).fill('Test friend')
  await page.getByLabel('Telegram username', { exact: true }).fill('test_friend')
  await page.getByRole('button', { name: 'Save friend', exact: true }).click()
  await expect(page.getByRole('link', { name: 'Test friend @test_friend' })).toHaveAttribute('href', 'https://t.me/test_friend')
  await page.evaluate(other => window.__accountListeners.accountsChanged([other]), other)
  await expect(page.getByRole('link', { name: 'Test friend @test_friend' })).toHaveCount(0)
  await page.evaluate(owner => window.__accountListeners.accountsChanged([owner]), owner)
  await expect(page.getByRole('link', { name: 'Test friend @test_friend' })).toBeVisible()
  await page.getByRole('button', { name: 'Remove Test friend' }).click()
  await expect(page.getByText('No friends added yet.')).toBeVisible()
})

test('retired demo and activity links enter the real account screen', async ({ page }) => {
  for (const path of ['/app/#/huddle/demo', '/app/#/feed', '/#/lab', '/app/lab']) {
    await page.goto('/')
    await page.goto(path)
    await expect(page).toHaveURL(/\/app\/$/)
    await expect(page.getByRole('heading', { name: 'Connect your account' })).toBeVisible()
  }
})

test('missing wallet is explained without invented account data', async ({ page }) => {
  await page.addInitScript(() => { delete window.ethereum })
  await page.goto('/app/')
  await page.getByRole('button', { name: 'Connect wallet', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Open this site in your wallet browser')
  await expect(page.locator('.real-position')).toHaveCount(0)
})


test('four idea previews use exchange quotes and honest event status', async ({ page }) => {
  const reads = []
  await page.route('https://api.hyperliquid.xyz/info', async route => {
    const body = route.request().postDataJSON(); reads.push(body)
    expect(body.type).toBe('metaAndAssetCtxs')
    await route.fulfill({ json: [{ universe: [{ name: 'XMR' }, { name: 'xyz:UNITREE' }, { name: 'xyz:ANT' }] }, [{ markPx: '200' }, { markPx: '17.50' }, { markPx: '42' }]] })
  })
  await page.route('**/lab/chat', route => route.fulfill({ json: { kind: 'error', reply: 'History is incomplete. No backtest was run.' } }))
  await page.goto('/')
  await expect(page.getByRole('tab')).toHaveCount(4)
  await expect(page.getByText('Long XMR', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Test the historical rule' }).click()
  await expect(page.getByRole('status')).toContainText('History is incomplete. No backtest was run.')
  await page.getByRole('tab', { name: /Robots take over/ }).click()
  await expect(page.getByText('Long xyz:UNITREE', { exact: true })).toBeVisible()
  await expect(page.getByText('$17.50', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: /Anthropic bubble/ }).click()
  await expect(page.getByText('Short xyz:ANT', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: /Dwarkesh/ }).click()
  await expect(page.getByText('Episode monitoring is not connected.', { exact: false })).toBeVisible()
  await expect(page.getByRole('link', { name: /Read an episode/ })).toHaveAttribute('href', 'https://www.dwarkesh.com/podcast')
  expect(reads.every(body => body.type === 'metaAndAssetCtxs')).toBeTruthy()
})
