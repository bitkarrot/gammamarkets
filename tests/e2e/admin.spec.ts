import {expect, test} from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

/* Merchant-facing journey: the admin shell on the host Vue/Quasar app.
 * Authenticates with the seeded account's cookie_access_token — the
 * same credential the host sets after a real login. */

const seed = JSON.parse(
  fs.readFileSync(path.join(__dirname, '.seed.json'), 'utf8')
)

test.describe.configure({mode: 'serial'})

test.beforeEach(async ({context}) => {
  await context.addCookies([
    {
      name: 'cookie_access_token',
      value: seed.access_token,
      url: seed.base_url
    }
  ])
})

test('admin shell mounts with all four surfaces', async ({page}) => {
  await page.goto('/gammamarkets/')
  await expect(page.locator('#gm-admin-root')).toBeVisible()
  for (const nav of ['orders', 'catalog', 'publications', 'settings']) {
    await expect(page.locator(`[data-gm-nav="${nav}"]`)).toBeVisible()
  }
  // Existing merchant → workspace (not the first-run setup card)
  await expect(
    page.locator('[data-gm-surface="orders"]')
  ).toBeVisible({timeout: 20_000})
})

test('orders workspace lists the seeded order + detail pane', async ({
  page
}) => {
  // Create a fresh order first — accumulated rows settle/expire over
  // time, so no prior state can be relied on for the legal-action check.
  const checkout = await page.request.post(
    '/gammamarkets/api/v1/public/checkout',
    {
      headers: {
        'Idempotency-Key': crypto.randomUUID() + crypto.randomUUID(),
        Origin: seed.base_url
      },
      data: {
        merchant_pubkey: seed.pubkey,
        items: [{d_tag: seed.digital.d_tag, quantity: 1}]
      }
    }
  )
  expect(checkout.status()).toBe(201)

  await page.goto('/gammamarkets/')
  await expect(
    page.locator('[placeholder="Search order or buyer"]')
  ).toBeVisible({timeout: 20_000})

  const row = page
    .locator('.gm-order-row')
    .filter({hasText: 'Awaiting payment'})
    .first()
  await expect(row).toBeVisible({timeout: 20_000})
  await expect(page.locator('[data-gm="orders-summary"]')).toContainText(
    'active orders'
  )

  await row.click()
  // Linear Split detail pane: state pill + legal actions + timeline
  await expect(
    page.getByText('Technical delivery details')
  ).toBeVisible({timeout: 15_000})
  // awaiting_payment → Cancel is the only legal state action
  await expect(
    page.getByRole('button', {name: 'Cancel', exact: true})
  ).toBeVisible()
})

test('catalog surface lists products with editor CTAs', async ({page}) => {
  await page.goto('/gammamarkets/')
  await page.locator('[data-gm-nav="catalog"]').click()
  await expect(
    page.getByRole('button', {name: 'New product'})
  ).toBeVisible({timeout: 15_000})
  // Scope to the catalog surface — hidden surfaces keep their DOM
  // (v-show) and the orders list contains the same product titles.
  const catalog = page.locator('[data-gm-surface="catalog"]')
  await expect(
    catalog.getByText('e2e digital tour').first()
  ).toBeVisible()
  await expect(catalog.getByText('e2e poster').first()).toBeVisible()
})

test('publications surface shows relay health + evidence copy', async ({
  page
}) => {
  await page.goto('/gammamarkets/')
  await page.locator('[data-gm-nav="publications"]').click()
  await expect(
    page.getByText(
      'Relay ACKs are delivery evidence — they never mean payment settled.'
    )
  ).toBeVisible({timeout: 15_000})
  // Starter relay seeded at merchant creation (scoped — the settings
  // surface renders the same relay URL in hidden DOM)
  await expect(
    page
      .locator('[data-gm-surface="publications"]')
      .getByText('wss://relay.nostr.net')
      .first()
  ).toBeVisible()
})

test('settings surface: identity, relays, notifications, appearance', async ({
  page
}) => {
  await page.goto('/gammamarkets/')
  await page.locator('[data-gm-nav="settings"]').click()
  const settings = page.locator('[data-gm-surface="settings"]')
  await expect(settings.getByText('Relays').first()).toBeVisible({
    timeout: 15_000
  })
  await expect(
    settings.getByText('wss://relay.nostr.net').first()
  ).toBeVisible()
  await expect(
    page.getByRole('button', {name: 'Save relay configuration'})
  ).toBeVisible()

  await page.getByRole('tab', {name: 'Notifications'}).click()
  await expect(
    page.getByText('Notification addresses', {exact: true})
  ).toBeVisible()

  await page.getByRole('tab', {name: 'Appearance'}).click()
  await expect(
    page.getByText(/warm|preset/i).first()
  ).toBeVisible()
})

test('unauthenticated admin visit redirects or denies', async ({
  browser
}) => {
  const anon = await browser.newContext()
  const page = await anon.newPage()
  const resp = await page.goto('/gammamarkets/')
  // check_user_exists rejects anonymous — the shell must not render
  expect([302, 307, 401, 403]).toContain(resp?.status())
  await anon.close()
})
