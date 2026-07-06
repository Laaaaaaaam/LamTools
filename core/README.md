# LamTools Core SDK

第一版：通用协议、类型、基础接口。不包含业务实现。

## 模块

| 模块 | 说明 |
|---|---|
| `llm` | LLM 请求/响应/流式事件/工具调用协议、客户端协议、system 合并/usage 归一化 |
| `tool` | 工具定义/调用/结果/权限协议、ToolRegistry |
| `event` | 统一事件 envelope、EventSink/EventLog 协议、InMemoryEventLog |
| `prompt` | Prompt 片段/组装协议、BasePromptAssembler |
| `mem` | 记忆 entry/query/hit 协议、store/recall/budget 协议 |
| `guardrail` | 检查/判定/策略/管线协议 |
| `runtime` | 运行状态/步骤/循环状态/完成验证协议 |
| `kernel` | Core Loop Kernel：共享主循环骨架、RuntimeKit 协议、LoopPolicy、LoopDecision |

## 当前范围

- **后端 SDK**（`src/lamtools_core`）：协议层 + Core Loop Kernel + HTTP 路由 + 应用工厂
- **前端 UI Core**（`ui/src`）：WorkspaceShell、SessionSidebar、ChatThread、ComposerBar、RuntimePanel、SettingsShell

## 新成员接入

新成员（LamEditor/LamMate/LamButler 等）接入 Core 的最小清单见 [docs/new-member-core-onboarding.md](docs/new-member-core-onboarding.md)。

## 非目标

- 不包含 Artist / Writer 业务代码、persona、专用工具
- 不包含具体 guardrail 规则或 completion verifier 实现
- 不包含 MEM store 实现

## 运行测试

```
py -3.14 -m pytest
```

## Python 版本

>=3.14
