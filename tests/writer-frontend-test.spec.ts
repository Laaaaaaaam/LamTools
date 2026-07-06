import { test, expect } from '@playwright/test'

test('Writer 前端流式输出截图测试', async ({ page }) => {
  test.setTimeout(120000)

  // 访问真实的 Writer 前端
  await page.goto('http://localhost:6174/')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(2000)

  // 截图：初始状态
  await page.screenshot({ path: 'test-output/writer-00-initial.png', fullPage: true })
  console.log('截图 0: 初始状态')

  // 等待页面完全加载
  await page.waitForTimeout(3000)

  // 截图：加载完成
  await page.screenshot({ path: 'test-output/writer-01-loaded.png', fullPage: true })
  console.log('截图 1: 页面加载完成')

  // 尝试找到并点击"新建会话"按钮
  const newSessionBtn = await page.locator('button:has-text("新建会话"), button:has-text("New Session"), button:has-text("+")').first()
  if (await newSessionBtn.isVisible()) {
    await newSessionBtn.click()
    await page.waitForTimeout(2000)
    await page.screenshot({ path: 'test-output/writer-02-new-session.png', fullPage: true })
    console.log('截图 2: 新建会话')
  }

  // 尝试找到输入框并输入任务
  const inputBox = await page.locator('textarea, input[type="text"]').first()
  if (await inputBox.isVisible()) {
    await inputBox.fill('写一个个人博客网站')
    await page.waitForTimeout(1000)
    await page.screenshot({ path: 'test-output/writer-03-input-filled.png', fullPage: true })
    console.log('截图 3: 输入任务')

    // 尝试发送任务
    const sendBtn = await page.locator('button:has-text("发送"), button:has-text("Send"), button[type="submit"]').first()
    if (await sendBtn.isVisible()) {
      await sendBtn.click()
      console.log('任务已发送，开始截图流式输出过程...')

      // 每 3 秒截图一次，持续 30 秒
      for (let i = 4; i <= 13; i++) {
        await page.waitForTimeout(3000)
        await page.screenshot({ path: `test-output/writer-${i.toString().padStart(2, '0')}-streaming.png`, fullPage: true })
        console.log(`截图 ${i}: 流式输出中 (${(i-3) * 3}秒)`)
      }
    }
  }

  // 最终截图
  await page.waitForTimeout(5000)
  await page.screenshot({ path: 'test-output/writer-14-final.png', fullPage: true })
  console.log('截图 14: 最终状态')

  console.log('Writer 前端测试完成！')
})
