import { test, expect } from '@playwright/test';

test.describe('Artist smoke @smoke', () => {
  async function expectNoConsoleProblems(page: import('@playwright/test').Page, visit: () => Promise<void>) {
    const problems: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' || msg.type() === 'warning') {
        problems.push(`${msg.type()}: ${msg.text()}`);
      }
    });
    page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`));
    await visit();
    await page.waitForTimeout(500);
    expect(problems).toEqual([]);
  }

  test('page shell loads', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const body = page.locator('body');
    await expect(body).toBeVisible({ timeout: 10000 });
  });

  test('sidebar drawer exists', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const drawer = page.locator('.drawer-left');
    await expect(drawer).toBeAttached({ timeout: 10000 });
  });

  test('lamartist brand visible in sidebar', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const brand = page.locator('.drawer-left .drawer-head strong');
    await expect(brand).toHaveText('lamartist', { timeout: 10000 });
  });

  test('composer textarea exists', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const composer = page.locator('.floating-composer textarea');
    await expect(composer).toBeAttached({ timeout: 10000 });
  });

  test('main content area exists', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const main = page.locator('.writer-main');
    await expect(main).toBeAttached({ timeout: 10000 });
  });

  test('runtime panel values are readable', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('body')).not.toContainText('[object Object]');
  });

  test('composer gives clear input feedback', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const composer = page.locator('.floating-composer textarea');
    await expect(composer).toHaveAttribute('placeholder', /输入/);
    await expect(page.getByRole('button', { name: '发送' })).toBeDisabled();
    await composer.fill('体验测试任务');
    await expect(page.getByRole('button', { name: '发送' })).toBeEnabled();
  });

  test('mobile viewport has no horizontal overflow', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test('settings page is stable and readable', async ({ page }) => {
    await expectNoConsoleProblems(page, async () => {
      await page.goto('/settings');
      await page.waitForLoadState('domcontentloaded');
    });
    await expect(page.getByRole('heading', { name: '模型与 API' })).toBeVisible();
    await expect(page.locator('body')).not.toContainText('[object Object]');
    await expect(page.getByRole('button', { name: /返回主界面/ })).toBeVisible();
  });
});
