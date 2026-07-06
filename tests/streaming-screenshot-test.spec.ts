import { test, expect } from '@playwright/test'

test('流式输出截图测试 - 个人博客网站', async ({ page }) => {
  // 设置更长的超时时间
  test.setTimeout(180000) // 180 秒

  // 直接访问带有 session 参数的 URL，跳过项目创建
  await page.goto('http://localhost:6174/?session=a553786d8cd1419da0ce734db087dfce')
  await page.waitForLoadState('networkidle')

  // 等待页面加载完成
  await page.waitForTimeout(3000)

  // 截图：初始状态（已有会话）
  await page.screenshot({ path: 'test-output/screenshot-00-initial.png', fullPage: true })
  console.log('截图 0: 初始状态')

  // 输入任务
  const taskInput = page.locator('textarea[placeholder="输入任务描述..."]')
  await taskInput.click()
  await taskInput.fill('写一个个人博客网站')
  await page.waitForTimeout(1000)

  // 截图：任务已输入
  await page.screenshot({ path: 'test-output/screenshot-01-task-entered.png', fullPage: true })
  console.log('截图 1: 任务已输入')

  // 提交任务
  await taskInput.press('Enter')
  await page.waitForTimeout(5000)

  // 截图：任务开始执行
  await page.screenshot({ path: 'test-output/screenshot-02-task-started.png', fullPage: true })
  console.log('截图 2: 任务开始执行')

  // 每 10 秒截图一次，持续 50 秒
  for (let i = 3; i <= 7; i++) {
    await page.waitForTimeout(10000)
    await page.screenshot({ path: `test-output/screenshot-${i.toString().padStart(2, '0')}-running.png`, fullPage: true })
    console.log(`截图 ${i}: 运行中 (${(i-2) * 10}秒)`)
  }

  // 最终截图
  await page.waitForTimeout(5000)
  await page.screenshot({ path: 'test-output/screenshot-08-final.png', fullPage: true })
  console.log('截图 8: 最终状态')

  console.log('截图测试完成！')
})
