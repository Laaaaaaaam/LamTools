import { test, expect } from '@playwright/test'

test('Mock 流式输出截图测试', async ({ page }) => {
  test.setTimeout(120000)

  // 访问 mock HTML 页面
  await page.goto('http://localhost:8765/mock-streaming.html')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(2000)

  // 截图：初始状态
  await page.screenshot({ path: 'test-output/mock-00-initial.png', fullPage: true })
  console.log('截图 0: 初始状态')

  // 点击开始按钮
  await page.click('#btn-start')
  await page.waitForTimeout(2000)

  // 截图：开始流式输出
  await page.screenshot({ path: 'test-output/mock-01-started.png', fullPage: true })
  console.log('截图 1: 开始流式输出')

  // 每 3 秒截图一次，持续 30 秒
  for (let i = 2; i <= 10; i++) {
    await page.waitForTimeout(3000)
    await page.screenshot({ path: `test-output/mock-${i.toString().padStart(2, '0')}-streaming.png`, fullPage: true })
    console.log(`截图 ${i}: 流式输出中 (${(i-1) * 3}秒)`)
  }

  // 最终截图
  await page.waitForTimeout(5000)
  await page.screenshot({ path: 'test-output/mock-11-final.png', fullPage: true })
  console.log('截图 11: 最终状态')

  console.log('Mock 流式输出测试完成！')
})
