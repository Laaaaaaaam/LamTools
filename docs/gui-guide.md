# LamTools GUI 使用指南

本文按当前源码整理 GUI 入口，区分 Core demo、Writer GUI、Artist GUI。GUI 指用户可见页面或桌面窗口；后端已有但未在页面暴露的 HTTP 能力不算 GUI 入口。

## Core GUI

Core 没有独立产品工作台，只有 UI 组件 demo。

```powershell
.\lamtools.cmd dev core frontend --open
```

打开：

```text
http://127.0.0.1:5173
```

用途：验证 `@lamtools/ui` 的 WorkspaceShell、SessionSidebar、ChatThread、ComposerBar、RuntimePanel。不要把它当成 Writer/Artist 的业务入口。

## Writer GUI

### 浏览器开发入口

```powershell
.\lamtools.cmd dev writer all --open
```

打开：

```text
http://127.0.0.1:6174
```

后端默认地址：

```text
http://127.0.0.1:6173
```

### 桌面入口

在 `members/writer/frontend` 下可用：

```powershell
npm run desktop:dev
npm run desktop:build
npm run desktop:unpacked
npm run tauri:dev
npm run tauri:build
npm run tauri:portable
```

Electron 与 Tauri 都会启动本地 Writer 后端，并通过桌面 bridge 把动态 `apiBase` 传给前端。

### 主界面 `/`

| 区域 | 可用操作 |
|---|---|
| 左侧项目/会话 | 查看项目分组、选择会话、新建会话、重命名会话、新建项目、删除项目、打开项目 `AGENTS.md` 编辑弹窗。 |
| 中央对话 | 查看用户消息、模型输出、工具/过程、决策卡片。 |
| 输入区 | 输入任务并发送；运行中无文本时按钮变为 stop；可在输入区选择执行模型。 |
| 队列区 | 运行中继续输入会排队；可编辑、删除、作为引导发送。 |
| 右侧改动审查 | 刷新改动、查看文件列表和 diff、撤销全部改动、撤销单文件。 |
| 右侧验收 | 通过并提交、要求调整、稍后处理。 |
| 右侧隔离结果 | 查看 Agent 分支 diff、合并、放弃。 |
| 右侧上下文与调用 | 查看最近运行的上下文、调用、费用或工具统计。 |
| 右侧检查点 | 保存检查点、回退到检查点。 |

### 设置页 `/settings`

| 分区 | 可用操作 |
|---|---|
| 模型与 API | Provider/Model 增删改、从当前环境导入、配置 adapter profile、模型上下文/输出/thinking 参数。 |
| Writer 行为 | 配置默认质量模式等 Writer 默认行为。 |
| 项目默认值 | 配置默认 work root。 |
| 工具与 Agent | 设置主模型路由、启用/禁用 Agent、配置项目子 Agent、设置命令权限、启用/禁用工具。 |
| 界面 | 调整密度、内容宽度、主题颜色、是否显示 Git 图和运行信息。 |

### 当前没有稳定 GUI 入口的 Writer 能力

- 旧 `writer agent ...`、`writer tool ...`、debug/message/step 注入入口已在 2026-06-30 删除；不再作为 GUI 或 CLI 开发者入口保留。
- Attachment API wrapper 和后端路由存在，但当前主界面没有稳定上传/预览入口。
- `/api/writer/novel/**` 是产品子能力或预留 HTTP 能力，不在当前主工作台暴露。

## Artist GUI

### 浏览器开发入口

```powershell
.\lamtools.cmd dev artist all --open
```

打开：

```text
http://127.0.0.1:5174
```

后端默认地址：

```text
http://127.0.0.1:6171
```

### 桌面入口

Artist 桌面使用 pywebview/PyInstaller。打包入口在 `members/artist`：

```powershell
py -3.14 build.py
```

桌面外壳会在本机选择可用端口、启动后端、打开 pywebview 窗口，并提供托盘操作。

### 主界面 `/`

| 区域 | 可用操作 |
|---|---|
| 左侧分组/会话 | 查看会话、新建会话、重命名会话、新建分组、删除分组；分组保存在浏览器 localStorage。 |
| 中央对话 | 查看 Artist 对话结果和图片输出。 |
| 输入区 | 输入生图或修改指令并发送。 |
| 右侧运行状态 | 查看当前会话、消息数、Provider 数量、累计费用。 |
| 设置入口 | 点击设置进入 `/settings`。 |

### 设置页 `/settings`

| 分区 | 可用操作 |
|---|---|
| 模型默认值 | 设置提示词优化、图像生成、任务规划等默认模型。 |
| API 管理 | 按供应商和模型管理 API：新增、编辑、删除、测试连接。 |
| 生成参数 | 配置默认图片数量、尺寸、并发等参数。 |
| 下载设置 | 设置下载目录；留空使用默认目录。 |
| 界面 | 调整密度、内容宽度、主题颜色、运行状态/最近图片显示。 |
| 数据迁移 | 从旧数据目录导入；清除缓存当前只清 localStorage。 |

### 当前没有稳定 GUI 入口的 Artist 能力

- `artist image ...` 是 CLI 的 direct image 入口，GUI 主输入统一走 Artist turn。
- `copy/session copy` 当前仍是 CLI 能力；GUI 侧边栏已支持会话重命名。
- Billing 明细/导出、reference 图片 CRUD、dashboard stats、long-task 控制、lineage drawer 相关代码存在，但当前主路由没有完整可见入口。
- `/api/sessions/{id}/generate` 是后端存在的旧/旁路接口；当前 GUI 使用 `/api/sessions/{id}/artist-turn`。

## 使用建议

- 普通任务优先用成员 GUI 主界面：Writer 写作/代码任务走 Writer `/`，Artist 生图任务走 Artist `/`。
- 配置模型和 Provider 优先用 GUI 设置页。
- 批量、自动化、诊断任务优先用 CLI。
- 不要把 `/api/core/*/messages` 当成“启动任务”入口；它只是 Core 形状的消息写入/读取接口。
