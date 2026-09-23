import {expect, test} from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

/* Buyer-facing journey (A2 checkout card + A3 order status):
 * product page → checkout → invoice → fragment-token status page →
 * FakeWallet settlement → confirmed. Serial: later tests reuse the
 * status URL minted by the checkout test. */

const seed = JSON.parse(
  fs.readFileSync(path.join(__dirname, '.seed.json'), 'utf8')
)

test.describe.configure({mode: 'serial'})

let statusUrl = ''

test('product page embeds the adaptive checkout card', async ({page}) => {
  const resp = await page.goto(seed.digital_url)
  expect(resp?.status()).toBe(200)
  // §5.4 protective headers on the public document
  const csp = resp?.headers()['content-security-policy'] ?? ''
  expect(csp).toContain("default-src 'self'")
  expect(resp?.headers()['cache-control']).toContain('no-store')

  await expect(page.locator('#gm-checkout-card')).toBeVisible()
  // Persistent Items/Shipping/Total summary — SAT prices seeded
  await expect(page.locator('[data-sum="items"]')).toContainText('2,500')
  await expect(page.locator('[data-sum="total"]')).toContainText('2,500')
  await expect(page.locator('.privacy')).toContainText(
    'never placed in the URL'
  )
  // Editorial preset: all section bodies visible, stepper hidden
  await expect(page.locator('#gm-checkout-card')).toHaveAttribute(
    'data-mode',
    'editorial'
  )
  await expect(page.locator('#gm-email')).toBeVisible()
  await expect(
    page.getByText('Send transactional updates. No marketing.')
  ).toBeVisible()
})

test('digital checkout creates a Lightning invoice', async ({page}) => {
  await page.goto(seed.digital_url)
  await page.locator('#gm-qty').fill('1')
  await page.locator('button[type=submit]').click()

  const panel = page.locator('#gm-invoice-panel')
  await expect(panel).toHaveAttribute(
    'data-invoice-state',
    'awaiting_payment',
    {timeout: 20_000}
  )
  // Same-origin QR + full BOLT11 + countdown + verbatim security copy
  const bolt11 = await panel.locator('textarea.bolt11').inputValue()
  expect(bolt11.toLowerCase()).toMatch(/^ln/)
  await expect(panel.locator('.invoice-qr svg')).toBeVisible()
  await expect(panel.locator('.invoice-countdown')).toContainText(
    'Expires in'
  )
  await expect(panel).toContainText(
    'Invoice is correlated to this order only'
  )
  // The token never lands in the page URL or emitted links
  expect(page.url()).not.toContain('#')
  statusUrl = await page.evaluate(() =>
    (window as unknown as {GM: {statusUrl(): string}}).GM.statusUrl()
  )
  expect(statusUrl).toContain('/gammamarkets/order#')
})

test('order status page: fragment stripped, polls, settles', async ({
  page,
  request
}) => {
  const token = new URL(statusUrl).hash.slice(1)
  expect(token.length).toBeGreaterThan(10)

  await page.goto(statusUrl)
  await expect(page.locator('#gm-order-state')).toContainText(
    'Waiting for payment'
  )
  // Fragment stripped immediately — token is memory-only
  expect(new URL(page.url()).hash).toBe('')
  await expect(page.locator('#gm-order-invoice')).toBeVisible()

  // Settle via the harness route (FakeWallet pay + listener path)
  const settled = await request.post(`${seed.base_url}/_e2e/settle`, {
    params: {token}
  })
  expect((await settled.json()).ok).toBe(true)

  // 5s poll picks up the confirmed state
  await expect(page.locator('#gm-order-state')).toContainText(
    'Payment confirmed',
    {timeout: 20_000}
  )
  // Invoice panel collapses once paid (bolt11 leaves the DOM)
  await expect(page.locator('#gm-order-invoice')).toBeHidden()
})

test('invalid order token shows identical dead-link copy', async ({
  page
}) => {
  await page.goto(
    `${seed.base_url}/gammamarkets/order#not-a-real-token-e2e-000`
  )
  await expect(page.locator('#gm-order-state')).toContainText(
    'This order link is no longer valid.'
  )
})

test('physical product requires destination + shipping', async ({
  page
}) => {
  await page.goto(seed.physical_url)
  await expect(page.locator('#gm-line1')).toBeVisible()
  await expect(page.locator('#gm-shipping')).toBeVisible()

  // Submit without a destination → inline contract copy, no request
  await page.locator('button[type=submit]').click()
  await expect(
    page.locator('[data-error-for="country"]')
  ).toContainText('Choose a shipping option for this destination.')

  await page.locator('#gm-country').selectOption('US')
  await page.locator('#gm-line1').fill('1 Main St')
  await page.locator('#gm-city').fill('Springfield')
  await page.locator('#gm-region').fill('US-IL')
  await page.locator('#gm-postal').fill('62701')
  await page.locator('#gm-shipping').selectOption({index: 1})

  // Persistent summary reflects item + shipping (7,500 + 500 SAT)
  await expect(page.locator('[data-sum="shipping"]')).toContainText('500')
  await expect(page.locator('[data-sum="total"]')).toContainText('8,000')

  await page.locator('button[type=submit]').click()
  const panel = page.locator('#gm-invoice-panel')
  await expect(panel).toHaveAttribute(
    'data-invoice-state',
    'awaiting_payment',
    {timeout: 20_000}
  )
})

test('compact layout is forced at <=560px', async ({page}) => {
  await page.setViewportSize({width: 375, height: 800})
  await page.goto(seed.digital_url)
  await expect(page.locator('#gm-checkout-card')).toHaveAttribute(
    'data-mode',
    'compact'
  )
  // Compact: collapsed sections behind disclosure heads
  const heads = page.locator('.co-section-head')
  await expect(heads.first()).toBeVisible()
})
