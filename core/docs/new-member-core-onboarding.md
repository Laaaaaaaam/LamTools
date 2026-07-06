# 新成员 Core 接入指南

> 面向 LamEditor、LamMate、LamButler 等新成员的最小接入清单。

## 1. Core 当前范围

**后端 SDK** (`lamtools_core`)：
- 协议层：LLM、Tool、Event、Prompt、MEM、Guardrail、Runtime
- 内核层：Core Loop Kernel（共享主循环骨架）
- HTTP 层：`/api/core` 通用路由（session、event、provider、usage）
- 应用层：`create_app` 工厂、`MemberManifest` 成员声明

**前端 UI Core** (`ui/src`)：
- 布局：WorkspaceShell（三栏骨架）
- 会话：SessionSidebar（支持分组）
- 对话：ChatThread（消息流）
- 输入：ComposerBar（具名工具插槽）
- 运行时：RuntimePanel（步骤组）
- 设置：SettingsShell（动态段）

## 2. 后端接入

### 2.1 声明成员身份

```python
from lamtools_core.member import MemberManifest

manifest = MemberManifest(
    id="lameditor",                    # 成员唯一标识
    name="LamEditor",                  # 机器名
    version="0.1.0",                  # 语义版本
    display_name="LamEditor",          # 显示名（可选，默认用 name）
    capabilities=["code", "git"],     # 能力标签
    default_routes={"/api/editor": "Editor API"},  # 路由描述
    config={"default_model": "gpt-4"},           # 成员配置
    hooks={"startup": my_startup_hook},          # 生命周期钩子
)
```

### 2.2 创建应用

```python
from lamtools_core.app import create_app
from lamtools_core.member import MemberManifest

app = create_app(
    members=[manifest],               # 注册成员
    member_routers={"lameditor": my_router},  # 挂载产品路由到 /api/lameditor
    title="LamEditor",
    version="0.1.0",
    enable_core_routes=True,          # 启用 /api/core 路由
)
```

### 2.3 `/api/core` 路由边界

Core 提供的路由（`enable_core_routes=True` 时自动挂载）：

| 路由 | 用途 | 产品是否扩展 |
|------|------|-------------|
| `GET /api/core/sessions` | 会话列表 | 否 |
| `POST /api/core/sessions` | 创建会话 | 否 |
| `GET /api/core/sessions/{id}` | 获取会话 | 否 |
| `PATCH /api/core/sessions/{id}` | 更新会话 | 否 |
| `GET /api/core/sessions/{id}/messages` | 消息列表 | 否 |
| `POST /api/core/sessions/{id}/messages` | 添加消息 | 否 |
| `GET /api/core/sessions/{id}/events` | 运行事件 | 否 |
| `POST /api/core/sessions/{id}/events` | 添加事件 | 否 |
| `GET /api/core/providers` | Provider 列表 | 否 |
| `POST /api/core/providers` | 注册 Provider | 否 |
| `GET /api/core/providers/default` | 默认 Provider | 否 |
| `GET /api/core/usage` | 用量记录 | 否 |
| `POST /api/core/usage` | 记录用量 | 否 |
| `GET /api/core/usage/total` | 用量汇总 | 否 |

**必须留产品侧**：
- 产品业务路由（如 `/api/editor/files`、`/api/editor/run`）
- 产品业务逻辑（代码分析、Git 操作、测试执行）
- 产品专用工具（file_read、file_write、run_command）
- 产品 persona 和 system prompt
- 产品验收逻辑（测试通过判断、代码质量检查）

### 2.4 Core Loop Kernel 接入（可选）

如果产品需要共享主循环骨架：

```python
from lamtools_core.kernel import CoreLoopKernel, RuntimeKit, LoopPolicy

class MyRuntimeKit(RuntimeKit):
    name = "lameditor"
    
    async def build_context(self, state, turn): ...
    async def parse_model_output(self, output, context): ...
    async def execute_tool(self, call, context): ...
    async def verify(self, state, turn, tool_results): ...
    async def decide_next(self, state, decision, verification): ...
    async def writeback(self, state, result): ...

kernel = CoreLoopKernel(kit=my_kit, policy=LoopPolicy())
result = await kernel.run(initial_state)
```

**Kit 负责业务，Kernel 负责流程**：
- Kernel：循环控制、事件发射、状态管理、repair 注入
- Kit：上下文构建、输出解析、工具执行、验收判断、写回

## 3. 前端接入

### 3.1 安装依赖

```bash
# 在产品 frontend 目录
npm install ../../../core/ui  # 或发布后的包名
```

配置路径别名（tsconfig.json + vite.config.ts）：

```jsonc
// tsconfig.app.json
{
  "compilerOptions": {
    "paths": {
      "@lamtools/ui": ["../../../core/ui/src/index.ts"]
    }
  },
  "include": [
    "src/**/*.ts", "src/**/*.vue",
    "../../../core/ui/src/**/*.ts", "../../../core/ui/src/**/*.vue"
  ]
}
```

```typescript
// vite.config.ts
resolve: {
  alias: {
    '@lamtools/ui': fileURLToPath(new URL('../../../core/ui/src/index.ts', import.meta.url)),
  },
}
```

### 3.2 实现 ProductAdapter 和 sessionGroups

```typescript
import type { ProductAdapter, CoreSessionGroup } from '@lamtools/ui';

const adapter: ProductAdapter = {
  id: 'lameditor',
  displayName: 'LamEditor',
  version: '0.1.0',
  supportedFeatures: ['chat', 'runtime-events', 'code'],
};

const sessionGroups = computed<CoreSessionGroup[]>(() => [
  { id: 'editor-sessions', label: 'Editor sessions', description: 'All Editor sessions' },
]);
```

### 3.3 使用 Core Mapper Helper

```typescript
// api/core.ts
import { createSessionMapper, createMessageMapper, type CoreSessionRawLike, type CoreMessageRawLike } from '@lamtools/ui';

const sessionMapper = createSessionMapper('editor-sessions');
const messageMapper = createMessageMapper();

// session endpoint
export async function listCoreSessions() {
  const raw = await request<CoreSessionRawLike[]>('/api/core/sessions');
  return raw.map(sessionMapper.toCore);
}

// message endpoint
export async function getCoreMessages(sessionId: string) {
  const raw = await request<CoreMessageRawLike[]>(`/api/core/sessions/${sessionId}/messages`);
  return raw.map(messageMapper.toCore);
}
```

event mapper 留产品侧（因为各产品 event schema 不同）。

### 3.4 使用 Core Controller

```typescript
// CoreWorkbenchView.vue
import { useCoreWorkbenchController } from '@lamtools/ui';
import type { CoreWorkbenchApi } from '@lamtools/ui';

const api: CoreWorkbenchApi = {
  listSessions: listCoreSessions,
  createSession: createCoreSession,
  getMessages: getCoreMessages,
  createMessage: createCoreMessage,
  getEvents: getCoreEvents,
  listProviders: listCoreProviders,
};

const {
  sessions, activeSessionId, messages, events,
  composerText, loading, providerCount, stepGroups,
  selectSession, newSession, sendMessage, loadInitialData,
} = useCoreWorkbenchController({
  api,
  onMountedExtra: async (ctx) => {
    // 产品特有初始化（如 usage 获取），可选
  },
});

onMounted(() => {
  loadInitialData();
});
```

### 3.5 填充 WorkspaceShell Slots

```vue
<template>
  <WorkspaceShell>
    <!-- 左侧边栏头 -->
    <template #sidebar-header>
      <div class="product-logo">LamEditor</div>
    </template>
    
    <!-- 左侧边栏主体 -->
    <template #sidebar>
      <SessionSidebar
        :sessions="sessions"
        :active-id="activeSessionId"
        :groups="adapter.sessionGroups"
        @select="onSelectSession"
      >
        <template #group-icon="{ group }">
          <Icon :name="group.id" />
        </template>
      </SessionSidebar>
    </template>
    
    <!-- 中央对话 -->
    <template #chat>
      <ChatThread :messages="messages">
        <template #message-product="{ message }">
          <!-- 产品特有消息渲染（如代码块带语法高亮） -->
        </template>
      </ChatThread>
      
      <ComposerBar
        v-model="inputText"
        @submit="onSubmit"
      >
        <template #toolbar-model>
          <ModelSelector :models="models" v-model="selectedModel" />
        </template>
        <template #toolbar-quality>
          <QualitySelector v-model="quality" />
        </template>
        <template #toolbar-custom>
          <!-- 产品特有工具按钮 -->
        </template>
      </ComposerBar>
    </template>
    
    <!-- 右侧面板 -->
    <template #drawer-right>
      <RuntimePanel :events="events" :step-groups="stepGroups">
        <template #step-detail="{ group, step }">
          <!-- 产品特有步骤详情（如代码 diff 预览） -->
        </template>
      </RuntimePanel>
    </template>
  </WorkspaceShell>
</template>
```

### 3.6 组件 Slot 契约速查

| 组件 | Slot | 用途 |
|------|------|------|
| WorkspaceShell | `sidebar-header` | 左侧边栏顶部（产品 logo/标题） |
| WorkspaceShell | `sidebar` | 左侧边栏主体（SessionSidebar） |
| WorkspaceShell | `sidebar-footer` | 左侧边栏底部 |
| WorkspaceShell | `chat-header` | 中央顶部 |
| WorkspaceShell | `chat` | 中央主体（ChatThread + ComposerBar） |
| WorkspaceShell | `composer-extra` | 编辑器下方扩展区 |
| WorkspaceShell | `drawer-right` | 右侧面板（RuntimePanel） |
| WorkspaceShell | `panel` | 右侧面板（旧版兼容，优先用 drawer-right） |
| SessionSidebar | `group-icon` | 分组图标 |
| SessionSidebar | `empty` | 空会话提示 |
| ChatThread | `message-product` | 整条消息覆盖渲染 |
| ChatThread | `content-product` | 消息内容覆盖（保留气泡外壳） |
| ChatThread | `message-renderer` | 消息渲染（旧版兼容） |
| ChatThread | `empty` | 空消息提示 |
| ComposerBar | `toolbar-model` | 模型选择器 |
| ComposerBar | `toolbar-quality` | 质量控制 |
| ComposerBar | `toolbar-custom` | 产品特有工具 |
| ComposerBar | `extension` | 扩展区（旧版兼容） |
| RuntimePanel | `step-detail` | 步骤详情 |
| RuntimePanel | `action` | 事件动作 |
| RuntimePanel | `artifact` | 产物展示 |
| SettingsShell | `section` | 动态段内容 |
| SettingsShell | `general` | 通用段（旧版兼容） |
| SettingsShell | `members` | 成员段（旧版兼容） |

### 3.7 CoreApiMapper 思路

当产品 API 返回的数据结构与 Core 类型不完全匹配时：

```typescript
import type { CoreApiMapper, CoreSessionListItem } from '@lamtools/ui';

// 产品 API 返回的原始类型
interface ProductSession {
  uuid: string;
  title: string;
  created_at: string;
  updated_at: string;
  project_id: string;
}

// 映射器
const sessionMapper: CoreApiMapper<ProductSession, CoreSessionListItem> = {
  toCore(raw) {
    return {
      id: raw.uuid,
      title: raw.title,
      createdAt: raw.created_at,
      updatedAt: raw.updated_at,
      groupId: raw.project_id,
    };
  },
  toRaw(core) {
    return {
      uuid: core.id,
      title: core.title,
      created_at: core.createdAt,
      updated_at: core.updatedAt,
      project_id: core.groupId ?? '',
    };
  },
};
```

**何时需要**：
- 产品 API 字段命名风格不同（snake_case vs camelCase）
- 产品 API 有额外字段需要过滤
- 产品 API 缺少可选字段需要补默认值

**何时不需要**：
- 产品直接使用 Core mapper helper（`createSessionMapper`/`createMessageMapper`），类型已对齐
- 产品前端直接构造 Core 类型对象

### 3.8 使用 Core 全局 CSS

Core 提供的 `ltw-*` CSS 类（在 `@lamtools/ui/styles` 中自动导出）：

| 类名 | 用途 |
|------|------|
| `.ltw-sidebar-header` | 侧边栏头部容器 |
| `.ltw-sidebar-title` | 侧边栏标题 |
| `.ltw-sidebar-subtitle` | 侧边栏副标题 |
| `.ltw-new-session-btn` | 新建会话按钮 |
| `.ltw-empty-state` | 空状态占位 |
| `.ltw-toolbar-status` | 工具栏状态文字 |

产品独有 CSS 保留在产品 scoped style 中（如 Artist 的 `.core-drawer-info`）。

### 3.9 SettingsShell 动态段

```vue
<SettingsShell :sections="sections">
  <template #section="{ section }">
    <component :is="sectionComponents[section.id]" />
  </template>
</SettingsShell>

<script setup lang="ts">
import type { SettingsSectionDef } from '@lamtools/ui';

const sections: SettingsSectionDef[] = [
  { id: 'general', label: '通用', order: 0 },
  { id: 'editor', label: '代码设置', order: 1 },
  { id: 'git', label: 'Git 设置', order: 2 },
];
</script>
```

## 4. 产品侧必须填充的内容

### 4.1 后端必须实现

| 内容 | 原因 | 示例 |
|------|------|------|
| MemberManifest | 声明产品身份 | `id="lameditor"` |
| 产品路由 | 业务 API | `/api/editor/files` |
| RuntimeKit（如用 Kernel） | 业务逻辑注入 | `execute_tool` 实现文件读写 |
| 业务工具 | 产品专用能力 | `file_read`、`run_test` |
| 验收逻辑 | 完成判断 | 测试通过、代码质量检查 |
| Persona/System Prompt | 产品人格 | "你是代码助手..." |

### 4.2 前端必须填充

| 内容 | 原因 | 示例 |
|------|------|------|
| ProductAdapter | 产品身份声明 | `id: 'lameditor'` |
| WorkspaceShell slots | 布局填充 | sidebar-header、drawer-right |
| SessionSidebar groups | 会话分组 | 项目分组、时间分组 |
| ComposerBar toolbar-* | 工具栏 | 模型选择、质量控制 |
| RuntimePanel step-detail | 步骤详情 | 代码 diff、终端输出 |
| SettingsShell sections | 设置段 | 代码风格、Git 配置 |
| 产品特有 UI | 业务展示 | 文件树、终端、Git 图 |

### 4.3 不能抽到 Core 的内容

| 类型 | 原因 | 示例 |
|------|------|------|
| 产品 persona | 业务身份 | Artist 人格、Writer 人格 |
| 产品工具 | 业务能力 | 生图工具、文件工具 |
| 产品数据模型 | 业务领域 | 图片谱系、任务计划 |
| 产品 UI 组件 | 业务展示 | 图片编辑器、Diff 查看器 |
| 产品验收规则 | 业务判断 | 图像质量判断、测试通过判断 |
| 产品配置 | 业务参数 | 默认模型、输出格式 |

**判断标准**：如果只有单一产品使用，或两个产品的实现完全不同，则留产品侧。

## 5. Writer/Artist 验证结论

**已完成验证**：
- Writer /core：使用 Core mapper/helper/controller，构建通过
- Artist /core：使用 Core mapper/helper/controller，构建通过
- 两者均调用真实 `/api/core` API，无 mock

**差异仅在**：
- Slot 填充内容（Writer 填文档相关，Artist 填图片相关）
- API 请求层（Writer 用 fetch + API_BASE，Artist 用 axios client）
- Event mapper（Writer 用 category/name schema，Artist 用 fallback 逻辑）
- 业务状态（Artist 有 usageTotal/usageCurrency/usageLabel、drawer info）
- 业务 UI（Writer 有 Git/Diff，Artist 有图片编辑）

**骨架完全相同**：
- 同一套 WorkspaceShell + SessionSidebar + ChatThread + ComposerBar + RuntimePanel
- 同一套 Core 类型（ProductAdapter、CoreSessionGroup、CoreRuntimeStepGroup）
- 同一套 Core helpers（createSessionMapper、createMessageMapper、createLoadingStepGroup）
- 同一套 Core controller（useCoreWorkbenchController）
- 同一套 Core CSS（ltw-sidebar-header/title/subtitle、ltw-new-session-btn、ltw-empty-state、ltw-toolbar-status）
- 同一套 `/api/core` 路由

## 6. 推荐目录形态

**迁移目标**（非当前事实）：

```
LamTools/
├── core/                    # Core SDK + UI Core
│   ├── src/lamtools_core/   # 后端 SDK
│   └── ui/                  # 前端 UI Core
├── members/
│   ├── writer/              # Writer 产品
│   ├── Artist/              # Artist 产品
│   ├── editor/               # 新成员
│   ├── mate/                # 新成员
│   └── butler/              # 新成员
└── shared/                  # 共享资源（可选）
```

**当前仓库**：
- `E:\LamTools\core`：Core SDK + UI Core
- `E:\LamTools\members\writer`：Writer 产品
- `E:\LamTools\members\Artist`：Artist 产品

**新成员起步**：
1. 运行 `.\scripts\scaffold-member.ps1 -Id editor -Name LamEditor -DisplayName LamEditor -Capabilities code,git` 生成骨架（先用 `-DryRun` 预览）
2. 依赖 `lamtools-core` 包（已由模板配置）
3. 依赖 `@lamtools/ui` 包（已由模板配置路径别名）
4. 实现 MemberManifest + RuntimeKit（模板已含 MemberManifest 最小声明）
5. 填充 UI slots（模板已含 WorkbenchView 最小骨架）
6. 添加业务工具和业务 UI
7. 手动将新成员加入 `dev.ps1`、`build.ps1`、`test.ps1` 的组件列表

## 7. 验收命令

**Core 仓库**：
```bash
# 后端测试
py -3.14 -m pytest

# UI 构建
cd ui && npm run build
```

**产品仓库**：
```bash
# 前端构建
cd frontend && npm run build

# 后端测试（如有）
py -3.14 -m pytest

# /core 路由测试（如有）
py -3.14 -m pytest tests/test_core_routes.py
```

**验收标准**：
- Core UI 构建通过
- 产品前端构建通过
- 产品后端测试通过
- `/core` 路由调用真实 API（无 mock）
- 主 WorkbenchView 不变（仅 `/core` 预览路由使用新骨架）

## 8. 反例警示

**不要复制整套 Workbench**：
[avoid] 复制 Writer 的整个 WorkbenchView.vue
[required] 只填充 WorkspaceShell 的 slots

**不要在 Core 放产品业务**：
[avoid] 在 Core 添加 `image_generation` 工具
[avoid] 在 Core 添加 `git_commit` 工具
[avoid] 在 Core 添加 `persona_writer` 字段
[required] 这些都留产品侧的 RuntimeKit

**不要 mock /core**：
[avoid] 在 `/core` 路由返回假数据
[required] 调用真实 `/api/core` API

**不要过早抽象**：
[avoid] 只有一个产品使用就抽到 Core
[required] 等两个产品都有类似实现再抽

**不要削弱类型检查**：
[avoid] 使用 `any` 类型
- [avoid] 省略 slot prop 类型
- [required] 所有接口有完整类型定义

## 9. 快速检查清单

接入前确认：
- [ ] 已阅读 `docs/core-sdk-full-extraction-plan.md` 了解整体架构
- [ ] 已阅读 `docs/core-loop-kernel-design.md` 了解 Kernel 边界

后端接入：
- [ ] 已创建 MemberManifest
- [ ] 已调用 create_app 并注册成员
- [ ] 已决定是否使用 Core Loop Kernel
- [ ] 产品路由挂载到 `/api/{member_id}`
- [ ] 业务工具留在产品侧

前端接入：
- [ ] 已配置 @lamtools/ui 路径别名（tsconfig + vite.config）
- [ ] 已实现 ProductAdapter
- [ ] 已定义 sessionGroups（使用产品 groupId）
- [ ] 已使用 createSessionMapper / createMessageMapper
- [ ] 已保留产品侧 event mapper
- [ ] 已使用 useCoreWorkbenchController
- [ ] 已填充 WorkspaceShell 必要 slots
- [ ] 已使用 Core ltw-* CSS 类
- [ ] 产品特有 UI 和业务状态留在产品侧

验收：
- [ ] Core UI 构建通过
- [ ] 产品前端构建通过
- [ ] 产品后端测试通过
- [ ] `/core` 路由无 mock
