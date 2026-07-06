from __future__ import annotations

import pytest

from app.core.writer.agent_runtime import (
    AgentCall,
    AgentRegistry,
    AgentRuntime,
    AgentSpec,
    default_agent_registry,
    delete_project_sub_agent_definition,
    load_sub_agent_definitions,
    SubAgentDefinition,
    write_project_sub_agent_definition,
)


class SimpleLLMResponse:
    def __init__(
        self,
        content: str = "",
        tool_calls: list[dict] | None = None,
        finish_reason: str = "stop",
        thinking: str = "",
    ):
        self.content = content
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason
        self.thinking = thinking


class ScriptedLLM:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls = 0

    async def chat_full(self, messages, tools=None, **kwargs):
        _ = messages, tools, kwargs
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, SimpleLLMResponse):
            return response
        return SimpleLLMResponse(response)


class RecordingLLM(ScriptedLLM):
    def __init__(self, responses: list[str]):
        super().__init__(responses)
        self.messages = []
        self.tools = []

    async def chat_full(self, messages, tools=None, **kwargs):
        self.messages.append(messages)
        self.tools.append(tools or [])
        return await super().chat_full(messages, tools, **kwargs)


class RecordingSubAgentKernelRunner:
    def __init__(
        self,
        *,
        content: str = "子任务完成",
        tool_records: list[dict] | None = None,
        reasoning_blocks: list[dict] | None = None,
    ):
        self.content = content
        self.tool_records = tool_records or []
        self.reasoning_blocks = reasoning_blocks or []
        self.calls = []

    async def __call__(self, definition, call, prompt, available_tools, workspace):
        self.calls.append({
            "definition": definition,
            "call": call,
            "prompt": prompt,
            "available_tools": available_tools,
            "workspace": workspace,
        })
        return (
            {
                "content": self.content,
            },
            self.tool_records,
            self.reasoning_blocks,
            {"runner": "test_kernel", "parse_status": "unstructured_text"},
        )


def test_default_registry_exposes_initial_agent_set():
    registry = default_agent_registry()

    assert registry.names() == ["sub"]
    assert registry.resolve("architecture") is None
    assert registry.resolve("architecture_agent") is None
    assert registry.resolve("design") is None
    assert registry.resolve("design_agent") is None
    assert registry.resolve("architect") is None
    assert registry.resolve("sub") is not None


@pytest.mark.asyncio
async def test_unknown_agent_returns_structured_tool_error():
    runtime = AgentRuntime(
        llm_client=ScriptedLLM([]),
        design_mode_selector=lambda task: "low",
    )

    result = await runtime.run("agent-runtime-test", AgentCall(name="unknown", task="查资料"))

    assert result.metadata["error"] == "unknown_agent"
    assert result.output.startswith("Unknown agent:")
    assert result.metadata["available_agents"] == ["sub"]


@pytest.mark.asyncio
async def test_agent_depth_limit_is_enforced():
    registry = AgentRegistry()
    registry.register(AgentSpec(name="custom", description="custom", max_depth=0))
    runtime = AgentRuntime(
        llm_client=ScriptedLLM([]),
        design_mode_selector=lambda task: "low",
        registry=registry,
    )

    result = await runtime.run("agent-runtime-test", AgentCall(name="custom", task="x", depth=1))

    assert result.metadata["error"] == "agent_depth_exceeded"
    assert "exceeds max_depth=0" in result.output


@pytest.mark.asyncio
async def test_agent_tool_allowlist_rejects_out_of_scope_tool():
    calls = []

    async def tool_runner(name, params):
        calls.append((name, params))
        return "{}"

    runtime = AgentRuntime(
        llm_client=ScriptedLLM([]),
        design_mode_selector=lambda task: "low",
        tool_runner=tool_runner,
    )
    runtime._agent_stack.append("sub")
    try:
        result = await runtime._tool("run_tests", {"command": "pytest"})
    finally:
        runtime._agent_stack.pop()

    assert result.startswith("AGENT TOOL REJECTED:")
    assert "agent=sub" in result
    assert calls == []


@pytest.mark.asyncio
async def test_sub_agent_runs_delegated_role_with_core_prompt():
    runner = RecordingSubAgentKernelRunner(content="先补测试再交付")
    runtime = AgentRuntime(
        llm_client=RecordingLLM([]),
        design_mode_selector=lambda task: "low",
        sub_agent_kernel_runner=runner,
    )

    result = await runtime.run(
        "agent-runtime-test",
        AgentCall(
            name="sub",
            task="审查项目",
            mode="low",
            options={"agent": "default", "role": "review", "expected_output": "阻塞问题和下一步"},
        ),
    )

    assert result.output == "先补测试再交付"
    assert result.metadata["agent_name"] == "default"
    assert result.metadata["runtime_agent"] == "sub"
    assert result.metadata["agent"] == "default"
    assert "final_answer" not in result.metadata
    assert "临时 SubAgent" in runner.calls[0]["prompt"]
    assert "最终必须输出 JSON" not in runner.calls[0]["prompt"]
    assert "read_file" in runner.calls[0]["available_tools"]
    assert "sub_agent" not in runner.calls[0]["available_tools"]


@pytest.mark.asyncio
async def test_sub_agent_returns_plain_body_without_duplicate_summary_fields():
    runner = RecordingSubAgentKernelRunner(content="## 结论\n已经读完 README，可以继续。")
    runtime = AgentRuntime(
        llm_client=RecordingLLM([]),
        design_mode_selector=lambda task: "low",
        sub_agent_kernel_runner=runner,
    )

    result = await runtime.run(
        "agent-runtime-test",
        AgentCall(name="sub", task="审查 README", mode="low", options={"agent": "reviewer"}),
    )

    assert result.output == "## 结论\n已经读完 README，可以继续。"
    assert result.metadata["diagnostics"]["parse_status"] == "unstructured_text"
    assert "summary" not in result.metadata
    assert "handoff" not in result.metadata
    assert "final_answer" not in result.metadata
    assert "confidence" not in result.metadata
    assert "fallback_reason" not in result.metadata


@pytest.mark.asyncio
async def test_sub_agent_fallback_records_missing_kernel_runner():
    runtime = AgentRuntime(
        llm_client=RecordingLLM([]),
        design_mode_selector=lambda task: "low",
    )

    result = await runtime.run(
        "agent-runtime-test",
        AgentCall(name="sub", task="审查", mode="low", options={"agent": "reviewer"}),
    )

    assert result.output.startswith("子代理 reviewer 执行失败。")
    assert "任务：审查" in result.output
    assert "core kernel loop" in result.output
    assert result.metadata["fallback_reason"] == "exception"
    assert result.metadata["diagnostics"]["exception_type"] == "RuntimeError"
    assert "core kernel loop" in result.metadata["diagnostics"]["exception"]


@pytest.mark.asyncio
async def test_sub_agent_fallback_records_exception_reason():
    async def failing_runner(*args, **kwargs):
        _ = args, kwargs
        raise RuntimeError("model unavailable")

    runtime = AgentRuntime(
        llm_client=RecordingLLM([]),
        design_mode_selector=lambda task: "low",
        sub_agent_kernel_runner=failing_runner,
    )

    result = await runtime.run(
        "agent-runtime-test",
        AgentCall(name="sub", task="审查", mode="low", options={"agent": "reviewer"}),
    )

    assert result.output.startswith("子代理 reviewer 执行失败。")
    assert "任务：审查" in result.output
    assert "model unavailable" in result.output
    assert result.metadata["fallback_reason"] == "exception"
    assert result.metadata["diagnostics"]["exception_type"] == "RuntimeError"
    assert "model unavailable" in result.metadata["diagnostics"]["exception"]


@pytest.mark.asyncio
async def test_sub_agent_empty_kernel_result_exposes_diagnostic_reason_to_writer():
    async def empty_runner(*args, **kwargs):
        _ = args, kwargs
        return (
            {},
            [],
            [],
            {
                "runner": "core_kernel",
                "decision": "failed",
                "tool_call_count": 0,
                "event_count": 3,
                "error": "Model call failed after 10 attempts: LLM API error 401: invalid api key",
            },
        )

    runtime = AgentRuntime(
        llm_client=RecordingLLM([]),
        design_mode_selector=lambda task: "low",
        sub_agent_kernel_runner=empty_runner,
    )

    result = await runtime.run(
        "agent-runtime-test",
        AgentCall(name="sub", task="检查 README", mode="low", options={"agent": "explorer"}),
    )

    assert result.output.startswith("子代理 explorer 执行失败。")
    assert "任务：检查 README" in result.output
    assert "LLM API error 401" in result.output
    assert "工具调用数：0" in result.output
    assert "summary" not in result.metadata
    assert "handoff" not in result.metadata


@pytest.mark.asyncio
async def test_reviewer_sub_agent_uses_review_tool_allowlist():
    runner = RecordingSubAgentKernelRunner(
        content="README 可继续复核",
        tool_records=[{
            "id": "read-1",
            "name": "read_file",
            "arguments": {"path": "README.md"},
            "status": "completed",
            "output": "README 内容",
        }],
    )
    runtime = AgentRuntime(
        llm_client=RecordingLLM([]),
        design_mode_selector=lambda task: "low",
        sub_agent_kernel_runner=runner,
    )

    result = await runtime.run(
        "agent-runtime-test",
        AgentCall(
            name="sub",
            task="审查 README",
            mode="low",
                options={"agent": "reviewer", "expected_output": "发现问题"},
            ),
        )

    assert result.metadata["agent"] == "reviewer"
    assert "referenced_tools" not in result.metadata
    assert result.metadata["tool_calls"][0]["status"] == "completed"
    assert "read_file" in runner.calls[0]["available_tools"]
    assert "write_file" not in runner.calls[0]["available_tools"]


@pytest.mark.asyncio
async def test_sub_agent_records_reasoning_blocks():
    runner = RecordingSubAgentKernelRunner(
        content="可以继续",
        reasoning_blocks=[{
            "id": "sub-reasoning-0",
            "content": "先看任务边界，再给结论。",
            "status": "completed",
        }],
    )
    runtime = AgentRuntime(
        llm_client=RecordingLLM([]),
        design_mode_selector=lambda task: "low",
        sub_agent_kernel_runner=runner,
    )

    result = await runtime.run(
        "agent-runtime-test",
        AgentCall(name="sub", task="审查", mode="low", options={"agent": "reviewer"}),
    )

    assert result.metadata["reasoning_blocks"] == [{
        "id": "sub-reasoning-0",
        "content": "先看任务边界，再给结论。",
        "status": "completed",
    }]


@pytest.mark.asyncio
async def test_explorer_sub_agent_does_not_receive_write_tools():
    runner = RecordingSubAgentKernelRunner(content="不执行写入")
    runtime = AgentRuntime(
        llm_client=RecordingLLM([]),
        design_mode_selector=lambda task: "low",
        sub_agent_kernel_runner=runner,
    )

    result = await runtime.run(
        "agent-runtime-test",
        AgentCall(name="sub", task="复核", mode="low", options={"agent": "explorer"}),
    )

    assert result.metadata["agent"] == "explorer"
    assert "write_file" not in runner.calls[0]["available_tools"]


@pytest.mark.asyncio
async def test_worker_sub_agent_can_write_but_not_call_agents():
    runner = RecordingSubAgentKernelRunner(
        content="检查 todo.txt",
        tool_records=[{
            "id": "write-1",
            "name": "write_file",
            "arguments": {"path": "todo.txt", "content": "done"},
            "status": "completed",
            "output": "created",
        }],
    )
    runtime = AgentRuntime(
        llm_client=RecordingLLM([]),
        design_mode_selector=lambda task: "low",
        sub_agent_kernel_runner=runner,
    )

    result = await runtime.run(
        "agent-runtime-test",
        AgentCall(name="sub", task="小范围实现", mode="low", options={"agent": "worker", "write_scope": ["todo.txt"]}),
    )

    assert result.metadata["agent"] == "worker"
    assert result.metadata["tool_calls"][0]["status"] == "completed"
    assert "write_file" in runner.calls[0]["available_tools"]
    assert "sub_agent" not in runner.calls[0]["available_tools"]
    assert result.metadata["can_call_agents"] is False


@pytest.mark.asyncio
async def test_write_capable_sub_agent_requires_write_scope():
    llm = RecordingLLM([
        '{"role":"implementation","task":"实现","summary":"不应调用","findings":[],"risks":[],"required_next_actions":[],"handoff":"不应调用","confidence":"low"}',
    ])
    runtime = AgentRuntime(
        llm_client=llm,
        design_mode_selector=lambda task: "low",
    )

    result = await runtime.run(
        "agent-runtime-test",
        AgentCall(name="sub", task="实现", mode="low", options={"agent": "worker"}),
    )

    assert llm.calls == 0
    assert result.metadata["status"] == "blocked"
    assert result.metadata["error"] == "missing_write_scope"
    assert "write_scope" in result.output


@pytest.mark.asyncio
async def test_write_scope_rejects_out_of_scope_mutation():
    runner = RecordingSubAgentKernelRunner(content="只允许修改 todo.txt")
    runtime = AgentRuntime(
        llm_client=RecordingLLM([]),
        design_mode_selector=lambda task: "low",
        sub_agent_kernel_runner=runner,
    )

    result = await runtime.run(
        "agent-runtime-test",
        AgentCall(name="sub", task="实现", mode="low", options={"agent": "worker", "write_scope": ["todo.txt"]}),
    )

    assert result.metadata["write_scope"] == ["todo.txt"]
    assert runner.calls[0]["workspace"] == {}


def test_project_sub_agent_definition_overrides_builtin(tmp_path):
    project = tmp_path / "project"
    agent_dir = project / ".claude" / "agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "explorer.md").write_text(
        "\n".join([
            "---",
            "name: explorer",
            "description: Project explorer",
            "tools:",
            "  - read_file",
            "model: fast-model",
            "maxTurns: 2",
            "---",
            "Only inspect the requested files.",
        ]),
        encoding="utf-8",
    )

    definitions = {item.name: item for item in load_sub_agent_definitions(project)}

    assert definitions["explorer"].source == "project"
    assert definitions["explorer"].description == "Project explorer"
    assert definitions["explorer"].tools == ("read_file",)
    assert definitions["explorer"].model == "fast-model"
    assert definitions["explorer"].max_tool_rounds == 2


def test_project_sub_agent_definition_write_and_delete_roundtrip(tmp_path):
    project = tmp_path / "project"

    saved = write_project_sub_agent_definition(
        project,
        SubAgentDefinition(
            name="project-worker",
            description="Project worker",
            role="implementation",
            developer_instructions="Only handle project work.",
            tools=("read_file", "write_file"),
            model="fast-model",
            max_tool_rounds=2,
            aliases=("pw",),
            source="project",
        ),
    )

    assert saved.source == "project"
    definitions = {item.name: item for item in load_sub_agent_definitions(project)}
    assert definitions["project-worker"].developer_instructions == "Only handle project work."
    assert definitions["project-worker"].tools == ("read_file", "write_file")
    assert definitions["project-worker"].aliases == ("pw",)

    assert delete_project_sub_agent_definition(project, "project-worker")
    assert "project-worker" not in {item.name for item in load_sub_agent_definitions(project)}


@pytest.mark.asyncio
async def test_runtime_uses_project_sub_agent_definition_tools(tmp_path):
    project = tmp_path / "project"
    agent_dir = project / ".lamtools" / "agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "worker.md").write_text(
        "\n".join([
            "---",
            "name: worker",
            "description: Read-only project worker",
            "tools: [read_file]",
            "---",
            "Do not write files.",
        ]),
        encoding="utf-8",
    )
    runner = RecordingSubAgentKernelRunner(content="交回主 Writer")
    runtime = AgentRuntime(
        llm_client=RecordingLLM([]),
        design_mode_selector=lambda task: "low",
        work_root=project,
        sub_agent_kernel_runner=runner,
    )

    result = await runtime.run(
        "agent-runtime-test",
        AgentCall(name="sub", task="实现", mode="low", options={"agent": "worker"}),
    )

    assert result.metadata["subagent_description"] == "Read-only project worker"
    assert result.metadata["tools"] == ["read_file"]
    assert runner.calls[0]["available_tools"] == frozenset({"read_file"})


@pytest.mark.asyncio
async def test_runtime_still_reads_legacy_writer_project_sub_agent_definitions(tmp_path):
    project = tmp_path / "project"
    agent_dir = project / ".writer" / "agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "worker.md").write_text(
        "\n".join([
            "---",
            "name: worker",
            "description: Legacy project worker",
            "tools: [read_file]",
            "---",
            "Do not write files.",
        ]),
        encoding="utf-8",
    )

    definitions = {item.name: item for item in load_sub_agent_definitions(project)}

    assert definitions["worker"].source == "project"
    assert definitions["worker"].description == "Legacy project worker"


@pytest.mark.asyncio
async def test_sub_agent_workspace_is_passed_to_tool_runner(tmp_path):
    workspace = tmp_path / "agent-worktree"
    workspace.mkdir()
    runner = RecordingSubAgentKernelRunner(content="完成")

    async def workspace_factory(definition, call):
        return {"work_root": str(workspace), "branch": f"writer/agent/{definition.name}/test"}

    runtime = AgentRuntime(
        llm_client=RecordingLLM([]),
        design_mode_selector=lambda task: "low",
        sub_agent_workspace_factory=workspace_factory,
        sub_agent_kernel_runner=runner,
    )

    await runtime.run(
        "agent-runtime-test",
        AgentCall(name="sub", task="实现", mode="low", options={"agent": "worker", "write_scope": ["x.txt"]}),
    )

    assert runner.calls[0]["workspace"]["work_root"] == str(workspace)
