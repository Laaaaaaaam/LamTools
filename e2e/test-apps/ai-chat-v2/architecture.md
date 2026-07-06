# AI 对话软件 - 架构设计

## 文件结构
```
/
├── chat.html      # 前端界面（单文件，含 HTML/CSS/JS）
└── server.py      # 后端服务（Flask）
```

## 前端架构 (chat.html)

### HTML 结构
```
┌─────────────────────────────────────────┐
│  ┌──────────┐  ┌──────────────────────┐ │
│  │ 侧边栏    │  │  主聊天区            │ │
│  │          │  │  ┌────────────────┐  │ │
│  │ 新对话    │  │  │  消息列表      │  │ │
│  │ ─────── │  │  │  (用户/AI消息)  │  │ │
│  │ 历史对话1 │  │  │                │  │ │
│  │ 历史对话2 │  │  └────────────────┘  │ │
│  │ 历史对话3 │  │  ┌────────────────┐  │ │
│  │          │  │  │  输入区         │  │ │
│  │          │  │  │  [文本输入][发送]│  │ │
│  │          │  │  └────────────────┘  │ │
│  └──────────┘  └──────────────────────┘ │
└─────────────────────────────────────────┘
```

### CSS 设计
- 深色主题为主（类似 ChatGPT）
- 侧边栏：深灰色背景 (#202123)
- 主聊天区：深色背景 (#343541)
- 用户消息：浅色背景
- AI 消息：透明/深色背景
- 消息气泡圆角、阴影
- 输入框固定在底部
- 滚动条自定义样式

### JavaScript 逻辑

#### 核心功能模块
1. **消息管理** - 发送、接收、渲染消息
2. **SSE 连接** - 使用 EventSource 接收流式回复
3. **对话管理** - 多对话切换、本地存储
4. **UI 控制** - 滚动、加载状态、错误处理

#### 关键函数
- `sendMessage()` - 发送用户消息
- `startSSE(messageId)` - 建立 SSE 连接
- `renderMessage(msg)` - 渲染单条消息
- `renderMarkdown(text)` - 渲染 Markdown
- `scrollToBottom()` - 自动滚动
- `newConversation()` - 新建对话
- `switchConversation(id)` - 切换对话
- `saveConversations()` - 保存到 localStorage
- `loadConversations()` - 从 localStorage 加载

#### 数据流
1. 用户输入 → 点击发送/回车
2. POST `/chat` → 后端返回 message_id
3. 创建 EventSource → GET `/stream/<message_id>`
4. 接收 SSE 事件 → 逐块更新 AI 消息内容
5. 收到 `done` 事件 → 关闭连接

## 后端架构 (server.py)

### 依赖
- Flask
- flask-cors (可选)

### 路由设计

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 返回 chat.html |
| POST | `/chat` | 接收用户消息，返回 message_id |
| GET | `/stream/<message_id>` | SSE 流式返回 AI 回复 |
| GET | `/history` | 获取对话历史 |
| POST | `/clear` | 清空所有对话 |

### 数据模型
```python
{
    "conversations": {
        "conv_id_1": {
            "id": "conv_id_1",
            "title": "对话标题",
            "messages": [
                {"role": "user", "content": "...", "id": "msg_xxx"},
                {"role": "assistant", "content": "...", "id": "msg_yyy"}
            ],
            "created_at": timestamp
        }
    },
    "current_conv_id": "conv_id_1"
}
```

### SSE 实现
- 使用 Flask Response 和生成器
- 设置 Content-Type: text/event-stream
- 每 0.05-0.1 秒发送一个数据块
- 数据格式：`data: {"content": "..."}\n\n`
- 结束标记：`event: done\ndata: {}\n\n`

### AI 回复模式

#### 模拟模式
从预定义回复列表中随机选取，逐字模拟流式输出。

#### OpenAI 模式
调用 OpenAI API 的 streaming 接口，逐 chunk 转发。

### 对话历史管理
- 使用 Python dict 内存存储
- 每个对话包含消息列表
- 支持多对话并行
