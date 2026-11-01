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
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
  await page.screenshot({ path: `test-results/home-${info.project.name}.png`, fullPage: true })
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Friends & positions', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/$/)
  await expect(page.getByRole('heading', { name: 'Connect your account' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
})

test('disconnected visitors never request or see any account data', async ({ page }) => {
  const reads = await marketData(page)
  await page.goto('/app/')
  await expect(page.getByRole('heading', { name: 'Connect your account' })).toBeVisible()
  await expect(page.locator('.real-position, .group-accounts, .group-fills')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: /Recent fills|The group's accounts|My positions/ })).toHaveCount(0)
  expect(reads).toEqual([])
  expect(await page.evaluate(() => window.__walletRequests)).toEqual([])
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
    await route.fulfill({ json: [{ universe: [{ name: 'XMR' }, { name: 'xyz:UNITREE' }, { name: 'xyz:ANT' }, { name: 'xyz:NVDA' }] }, [{ markPx: '200' }, { markPx: '17.50' }, { markPx: '42' }, { markPx: '205' }]] })
  })
  await page.route('**/lab/chat', route => {
    const body = route.request().postDataJSON()
    expect(body.days).toBe(180)
    expect(body.message).toContain('hold 1 day')
    expect(body.message).toContain('over the last 180 days using hourly candles')
    return route.fulfill({ json: { kind: 'error', reply: 'History is incomplete. No backtest was run.' } })
  })
  await page.goto('/')
  await expect(page.getByRole('tab')).toHaveCount(4)
  await expect(page.getByText('Long XMR', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /Trade it in Telegram/ })).toHaveAttribute('href', 'https://t.me/ProtossTradingDemoBot')
  await page.getByRole('button', { name: 'Run it now' }).click()
  await expect(page.getByRole('status')).toContainText('History is incomplete. No backtest was run.')
  await page.getByRole('tab', { name: /Robots take over/ }).click()
  await expect(page.getByText('Long xyz:UNITREE', { exact: true })).toBeVisible()
  await expect(page.getByText('$17.50', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: /Anthropic bubble/ }).click()
  await expect(page.getByText('Short xyz:ANT', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: /Dwarkesh/ }).click()
  await expect(page.getByText('Long xyz:NVDA', { exact: true })).toBeVisible()
  await expect(page.getByText('reads his podcast feed every 10 minutes', { exact: false })).toBeVisible()
  expect(reads.every(body => body.type === 'metaAndAssetCtxs')).toBeTruthy()
})


test('historical research shows the ordinary-day baseline', async ({ page }) => {
  await page.route('https://api.hyperliquid.xyz/info', route => route.fulfill({ json: [{ universe: [{ name: 'XMR' }] }, [{ markPx: '200' }]] }))
  await page.route('**/lab/chat', route => route.fulfill({ json: {
    kind: 'backtest', reply: 'Tested the requested 180-day window.', spec: { type: 'event_buy', event_set: 'major_hacks', market: 'XMR', hold_days: 1 },
    result: { notes: ['baseline: compare the event reaction with the same hold after any day.', 'Internal detail'] }
  } }))
  await page.goto('/')
  await page.getByRole('button', { name: 'Run it now' }).click()
  await expect(page.getByRole('status')).toContainText('180-day window')
  await expect(page.getByRole('status')).toContainText('baseline: compare')
  await expect(page.getByRole('status')).not.toContainText('Internal detail')
})


test('a live answer that is not the idea is not shown as its result', async ({ page }) => {
  await page.route('https://api.hyperliquid.xyz/info', route => route.fulfill({ json: [{ universe: [{ name: 'xyz:ANT' }] }, [{ markPx: '42' }]] }))
  await page.route('**/lab/chat', route => route.fulfill({ json: { kind: 'clarify', reply: 'Which idea should I test?' } }))
  await page.goto('/')
  await page.getByRole('tab', { name: /Anthropic bubble/ }).click()
  await page.getByRole('button', { name: 'Run it now' }).click()
  await expect(page.getByRole('status')).toContainText("The live Lab can't run this idea yet")
  await expect(page.getByRole('status')).not.toContainText('Which idea should I test?')
})
