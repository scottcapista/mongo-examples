import { test, expect } from '@playwright/test'

test('admin dataset records render JSON tree, not Empty', async ({ page }) => {
  await page.goto('/')

  await page.getByRole('button', { name: 'Admin' }).click()
  await expect(page.getByRole('heading', { name: 'Datasets' })).toBeVisible()

  const datasetCard = page.getByRole('button', { name: /filerouter\.calendarEvents/i }).first()
  await expect(datasetCard).toBeVisible()
  await datasetCard.click()

  await expect(page.getByRole('heading', { name: 'filerouter.calendarEvents' })).toBeVisible()
  await expect(page.locator('.record-card').first()).toBeVisible()

  const firstRecord = page.locator('.record-card').first()
  await expect(firstRecord.getByRole('button', { name: 'tree' })).toBeVisible()
  await expect(firstRecord.getByText('Empty', { exact: true })).toHaveCount(0)
  await expect(firstRecord.locator('.json-tree')).toContainText('title')
})
