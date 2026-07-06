import { test, expect } from '@playwright/test'

/**
 * Mock 流式输出测试
 * 通过注入 mock SSE 数据来验证前端流式显示效果
 */
test('Mock 流式输出截图测试', async ({ page }) => {
  test.setTimeout(120000) // 120 秒

  // 访问前端
  await page.goto('http://localhost:6174/')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(2000)

  // 截图：初始状态
  await page.screenshot({ path: 'test-output/mock-00-initial.png', fullPage: true })
  console.log('截图 0: 初始状态')

  // 注入 mock SSE 数据模拟流式输出
  await page.evaluate(() => {
    // Mock SSE 事件流
    const mockEvents = [
      { type: 'status', data: { status: 'thinking', text: '正在思考...' } },
      { type: 'text_delta', data: { content: '我来帮你创建一个个人博客网站。' } },
      { type: 'text_delta', data: { content: '首先，我会规划项目结构。' } },
      { type: 'tool_call', data: { name: 'create_file', args: { path: 'index.html' } } },
      { type: 'tool_result', data: { name: 'create_file', result: '文件已创建' } },
      { type: 'text_delta', data: { content: '\n\n接下来创建样式文件。' } },
      { type: 'tool_call', data: { name: 'create_file', args: { path: 'style.css' } } },
      { type: 'tool_result', data: { name: 'create_file', result: '文件已创建' } },
      { type: 'text_delta', data: { content: '\n\n现在添加 JavaScript 交互逻辑。' } },
      { type: 'tool_call', data: { name: 'create_file', args: { path: 'app.js' } } },
      { type: 'tool_result', data: { name: 'create_file', result: '文件已创建' } },
      { type: 'text_delta', data: { content: '\n\n博客网站已创建完成！包含首页、样式和交互功能。' } },
      { type: 'status', data: { status: 'completed', text: '任务完成' } },
    ]

    // 模拟 SSE 流式输出
    let index = 0
    const interval = setInterval(() => {
      if (index >= mockEvents.length) {
        clearInterval(interval)
        return
      }

      const event = mockEvents[index]
      // 触发全局事件，让前端监听
      window.dispatchEvent(new CustomEvent('mock-sse-event', { detail: event }))
      index++
    }, 2000) // 每 2 秒发送一个事件
  })

  // 等待并截图
  for (let i = 1; i <= 8; i++) {
    await page.waitForTimeout(5000)
    await page.screenshot({ path: `test-output/mock-${i.toString().padStart(2, '0')}-streaming.png`, fullPage: true })
    console.log(`截图 ${i}: 流式输出中`)
  }

  // 最终截图
  await page.waitForTimeout(3000)
  await page.screenshot({ path: 'test-output/mock-09-final.png', fullPage: true })
  console.log('截图 9: 最终状态')

  console.log('Mock 流式输出测试完成！')
})
