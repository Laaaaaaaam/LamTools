# LamTools CLI 使用指南

本文按当前源码整理，区分 Core 维护命令与 Writer/Artist 成员命令。所有示例默认在仓库根目录 `E:\LamTools` 执行；如果已把仓库根目录加入 PATH，可省略 `.\`。

## 编码与运行前提

- `writer.cmd`、`artist.cmd` 会先切换到 UTF-8 代码页。
- PowerShell 中传递中文长任务时，优先直接作为参数传入；不要用管道或 here-string 传任务正文，避免编码污染。
- 后端未启动时，先用 `.\lamtools.cmd dev <member> backend` 启动对应后端。

## Core 维护命令

### 启动开发服务

主入口：

```powershell
.\lamtools.cmd dev all
.\lamtools.cmd dev core frontend
.\lamtools.cmd dev writer all
.\lamtools.cmd dev writer backend
.\lamtools.cmd dev writer frontend
.\lamtools.cmd dev artist all
.\lamtools.cmd dev artist backend
.\lamtools.cmd dev artist frontend
.\lamtools.cmd dev writer all --open
```

兼容入口：

```powershell
.\scripts\dev.ps1 all
.\scripts\dev.ps1 core frontend
.\scripts\dev.ps1 writer all
.\scripts\dev.ps1 writer backend
.\scripts\dev.ps1 writer frontend
.\scripts\dev.ps1 artist all
.\scripts\dev.ps1 artist backend
.\scripts\dev.ps1 artist frontend
```

端口来自 `scripts/ports.json`：

| 组件 | 后端 | 前端 dev |
|---|---:|---:|
| core | 无常驻后端 | 5173 |
| writer | 6173 | 6174 |
| artist | 6171 | 5174 |

### 构建

```powershell
.\lamtools.cmd build all
.\lamtools.cmd build core
.\lamtools.cmd build writer
.\lamtools.cmd build artist

.\scripts\build.ps1 all
.\scripts\build.ps1 core
.\scripts\build.ps1 writer
.\scripts\build.ps1 artist
```

### 测试

```powershell
.\lamtools.cmd test all
.\lamtools.cmd test core
.\lamtools.cmd test writer
.\lamtools.cmd test artist

.\scripts\test.ps1 all
.\scripts\test.ps1 core
.\scripts\test.ps1 writer
.\scripts\test.ps1 artist
```

### 打开与诊断

```powershell
.\lamtools.cmd open writer
.\lamtools.cmd open artist
.\lamtools.cmd doctor all
.\lamtools.cmd doctor writer --json
.\lamtools.cmd members list
```

`open` 读取 `scripts/ports.json`，不要求用户记端口；`doctor` 检查 Python/Node/npm、成员目录、根 CLI、Writer 默认数据库目录、后端健康和前端 dev server。

### 创建新成员

```powershell
.\lamtools.cmd scaffold member editor --name LamEditor --display-name LamEditor --capability code --capability git
.\lamtools.cmd scaffold member editor --name LamEditor --dry-run

.\scripts\scaffold-member.ps1 -Id editor -Name LamEditor -DisplayName LamEditor -Capabilities code,git
.\scripts\scaffold-member.ps1 -Id editor -Name LamEditor -DryRun
```

脚手架会生成 `members/<id>/` 和根目录 `<id>.cmd`。它不会完整接入 `dev/build/test` 脚本，生成后仍要按脚本输出补齐成员注册和维护入口。

## Writer CLI

### 常用任务命令

```powershell
writer run <任务描述...>
writer run <任务描述...> --work-root E:\Project
writer run <任务描述...> --title "会话标题"
writer run <任务描述...> --model-id <model-id>
writer resume <session-id> <继续描述...>
writer watch <session-id>
writer cancel <session-id>
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--base-url` | 后端地址，默认 `http://127.0.0.1:6173`。 |
| `--title` | 新会话标题，仅 `run` 使用。 |
| `--work-root` / `--project` | 任务工作目录。 |
| `--mode` | 运行模式，默认 `EXECUTE`。 |
| `--model-id` | 单次运行覆盖模型，仅 `run` 使用。 |
| `--raw` | 输出原始事件。 |
| `--verbose` | 显示更细的运行事件。 |
| `--heartbeat-interval` | 等待心跳间隔秒数。 |
| `--interactive-decisions` | 决策点要求用户交互。 |
| `--no-interactive-decisions` | 不在 CLI 中交互等待决策。 |

### 会话命令

推荐使用根入口统一形态：

```powershell
writer session list
writer session list -n 50
writer session new
writer session new "会话标题"
writer session show <session-id>
writer session messages <session-id>
writer session status <session-id>
writer session result <session-id>
writer session rename <session-id> "新标题"
writer session delete <session-id>
```

底层 Writer CLI 也接受 `writer list/new/messages/status/result`，但对用户文档不再主推两套写法。

### 健康检查

```powershell
writer health
```

### 开发者命令

维护标注（2026-06-30）：旧 `writer quick`、`writer chat`、`writer agent ...`、`writer tool ...`、`writer debug decision-point`、`writer message send`、`writer step send` 已删除；Writer CLI 只保留 app-server 主线和会话读取入口。

## Artist CLI

### 常用任务命令

```powershell
artist run <生图或修改指令...>
artist <生图或修改指令...>
artist resume <session-id> <继续指令...>
artist session <session-id> <继续指令...>
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--session-id` | 复用已有会话；省略则新建。 |
| `--title` | 新会话标题，默认 `Artist CLI`。 |
| `--image-count` | 请求图片数量。 |
| `--image-size` | 图片尺寸，默认 `1024x1024`。 |
| `--negative-prompt` | 负面提示词。 |
| `--refine-mode` | 强制精修模式。 |
| `--selected-image-url` | 精修目标图 URL。 |
| `--reference-image` | 参考图 URL，可重复。 |
| `--image-provider-id` | 单次覆盖图片模型 provider。 |
| `--vlm-provider-id` | 单次覆盖 VLM provider。 |
| `--vlm-base-url` / `--vlm-model-id` / `--vlm-api-key` | 临时 VLM 连接参数。 |
| `--compact` | 精简输出。 |
| `--mock image|all` | Mock 图片或全部模型调用。 |

### 直接生图

```powershell
artist image <prompt...>
artist image <prompt...> --image-count 3 --image-size 1024x1024
```

### 会话管理

```powershell
artist session list
artist session ls
artist session new
artist session <session-id>
artist session <session-id> <prompt...>
artist session copy <session-id>
artist session rename <session-id> "新标题"
```

`artist session <session-id>` 不带 prompt 时进入交互模式，输入 `/exit` 或 `/quit` 退出。

### 健康检查

```powershell
artist health
```

### 当前注意事项

- Artist 根入口提供子命令式 help；任务入口统一为 `artist run <prompt...>`。
- Artist 的 Provider/模型管理当前主要在 GUI 中完成，CLI 没有对等 CRUD 命令。

## 推荐命令形态

面向日常使用，优先记住以下入口：

```powershell
writer run <任务...>
writer resume <session-id> <继续...>
writer session list
writer health

artist run <指令...>
artist resume <session-id> <继续...>
artist session list
artist health
```
