# AI Chat App - 智能对话应用

一个基于 Next.js 14 构建的现代化 AI 对话应用，拥有精美的深色主题界面和流畅的交互体验。

## ✨ 功能特性

- 🎨 **精美暗黑主题** - 专为长时间使用设计的深色界面，带有发光效果
- 💬 **多轮对话** - 支持多轮连续对话，上下文关联
- 📝 **Markdown 渲染** - 完整支持 Markdown 语法，包括代码高亮
- 🔄 **流式输出** - 模拟 AI 逐字生成的流式效果
- 📂 **对话管理** - 创建、切换、删除多个对话
- 🤖 **多模型选择** - 支持 GPT-4 / GPT-3.5 / Claude 3 / 本地模型切换
- 💾 **本地存储** - 对话记录自动保存到 localStorage
- 📱 **响应式设计** - 适配桌面和移动设备
- 🎯 **快捷建议** - 提供预设问题快速开始对话
- ⌨️ **键盘快捷键** - Enter 发送，Shift+Enter 换行

## 🚀 快速开始

### 安装依赖

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

访问 [http://localhost:3000](http://localhost:3000) 查看应用。

### 构建生产版本

```bash
npm run build
npm start
```

## 📁 项目结构

```
src/
├── app/
│   ├── globals.css      # 全局样式和CSS变量
│   ├── layout.tsx       # 根布局
│   └── page.tsx         # 主页面（状态管理核心）
├── components/
│   ├── ChatHeader.tsx   # 对话头部信息栏
│   ├── ChatInput.tsx    # 消息输入框
│   ├── MessageBubble.tsx# 消息气泡（支持Markdown渲染）
│   ├── Sidebar.tsx      # 侧边栏（对话列表+模型选择）
│   ├── TypingIndicator.tsx # AI输入中动画
│   └── WelcomeScreen.tsx   # 欢迎页面
└── lib/
    ├── types.ts         # TypeScript 类型定义
    └── utils.ts         # 工具函数和模拟AI响应
```

## 🔧 自定义配置

### 接入真实 AI API

在 `src/lib/utils.ts` 中，将 `streamAIResponse` 函数替换为真实的 API 调用：

```typescript
export async function* streamAIResponse(messages: Message[]): AsyncGenerator<string> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    yield decoder.decode(value);
  }
}
```

### 修改主题颜色

编辑 `src/app/globals.css` 中的 CSS 变量：

```css
:root {
  --accent: #6c5ce7;        /* 主色调 */
  --accent-light: #a29bfe;  /* 浅主色调 */
  --bg-primary: #0a0a0f;    /* 主背景色 */
  /* ... */
}
```

## 🛠 技术栈

- **框架**: Next.js 14 (App Router)
- **语言**: TypeScript
- **样式**: Tailwind CSS + CSS Variables
- **图标**: Lucide React
- **Markdown**: react-markdown + react-syntax-highlighter
- **存储**: localStorage

## 📄 License

MIT
