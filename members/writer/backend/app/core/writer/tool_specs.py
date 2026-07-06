"""Writer tool specifications: schema, permission, failure modes, recovery.

This module provides a declarative specification for each Writer tool,
consolidating information from permission.py and core_kernel_adapter.py.
The specs are used for:
- Tool permission lookup (reuses core PermissionTier constants)
- Failure classification (reuses WriterKit's failure patterns)
- Recovery instruction generation (reuses WriterKit's recovery logic)
- Tool observation classification (reuses WriterKit's classification)

WriterKit uses these specs for dispatch and validation; this module also
serves for documentation, testing, and future spec-driven execution.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lamtools_core.agent import SUB_AGENT_TOOL_NAME, SUB_AGENT_TOOL_SPEC
from lamtools_core.tool.permission import AUTO_ALLOW, ASK_USER, HARD_BLOCK, PermissionTier


TOOL_CATEGORY_BY_NAME: dict[str, str] = {
    "read_file": "file_read",
    "list_dir": "file_read",
    "search_files": "file_read",
    "search_content": "file_read",
    "inspect_project": "file_read",
    "write_file": "file_write",
    "edit_file": "file_write",
    "run_command": "command",
    "run_tests": "command",
    "git_status": "git",
    "git_diff": "git",
    "web_search": "web",
    "web_fetch": "web",
    "browser_check": "browser",
    "recall_session": "memory",
    "load_skill": "skill",
    SUB_AGENT_TOOL_NAME: "agent",
    "delegate_to_member": "agent",
    "mcp_tool": "mcp",
    "decision_point": "control",
    "request_commit_review": "control",
    "write_checklist": "control",
    "update_checklist": "control",
    "verify_design": "control",
    "chat_only": "control",
    "ask_clarification": "control",
    "self_critique": "control",
}

MODEL_VISIBLE_CATEGORIES = frozenset({
    "file_read",
    "file_write",
    "command",
    "git",
    "web",
    "browser",
    "memory",
    "skill",
    "agent",
    "control",
})

INTERNAL_ONLY_TOOLS = frozenset({
    "ask_clarification",
    "chat_only",
    "mcp_tool",
    "self_critique",
})

DEFAULT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {"type": "string", "enum": ["ok", "failed", "skipped", "blocked"]},
        "content": {"type": "string"},
        "error": {"type": "string"},
        "metadata": {"type": "object"},
        "artifacts": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["status", "content", "error", "metadata", "artifacts"],
}


def _default_display(category: str) -> dict[str, Any]:
    card_by_category = {
        "file_read": "file",
        "file_write": "diff",
        "command": "command",
        "git": "diff",
        "web": "web",
        "browser": "browser",
        "memory": "memory",
        "skill": "skill",
        "agent": "agent",
        "mcp": "tool",
        "control": "process",
    }
    return {
        "card": card_by_category.get(category, "tool"),
        "default_collapsed": category in {"control", "memory", "skill"},
    }


def _schema_type_includes(schema: dict[str, Any], value: str) -> bool:
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        return schema_type == value
    if isinstance(schema_type, list):
        return value in schema_type
    return False


def _allow_null(schema: dict[str, Any]) -> None:
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        if schema_type != "null":
            schema["type"] = [schema_type, "null"]
    elif isinstance(schema_type, list):
        if "null" not in schema_type:
            schema["type"] = [*schema_type, "null"]
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and None not in enum_values:
        enum_values.append(None)


def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return an OpenAI strict-compatible schema from a Writer tool schema."""
    normalized = deepcopy(schema)

    def visit(node: dict[str, Any]) -> None:
        if _schema_type_includes(node, "object") or "properties" in node:
            properties = node.get("properties")
            if isinstance(properties, dict):
                originally_required = set(node.get("required") or [])
                for key, child in properties.items():
                    if isinstance(child, dict):
                        if key not in originally_required:
                            _allow_null(child)
                        visit(child)
                node["required"] = list(properties.keys())
            node["additionalProperties"] = False

        items = node.get("items")
        if isinstance(items, dict):
            visit(items)

    visit(normalized)
    return normalized


MODEL_TOOL_ORDER: tuple[str, ...] = ('read_file', 'write_file', 'edit_file', 'search_content', 'search_files', 'recall_session', 'load_skill', 'web_search', 'run_command', 'git_status', 'git_diff', 'list_dir', 'web_fetch', 'run_tests', 'inspect_project', 'browser_check', 'request_commit_review', 'decision_point', 'write_checklist', 'update_checklist', 'verify_design', 'delegate_to_member', SUB_AGENT_TOOL_NAME)

WRITER_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read file content within work_root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to work_root"},
            },
            "required": ["path"],
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [
            {"type": "path_outside_root", "message": "Blocked: path is outside work_root"},
            {"type": "file_not_found", "message": "File not found"},
            {"type": "read_error", "message": "Error reading file"},
        ],
        "recovery": "Check path exists, use list_dir to find correct path",
    },
    {
        "name": "write_file",
        "description": (
            "Write content to a file. Use ONLY for creating new files or when the user explicitly asks for a full "
            "rewrite. For modifying existing files, prefer edit_file with the smallest possible change."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to work_root"},
                "content": {"type": "string", "description": "File content to write"},
            },
            "required": ["path", "content"],
        },
        "permission": ASK_USER,
        "failure_modes": [
            {"type": "path_outside_root", "message": "Blocked: path is outside work_root"},
            {"type": "sensitive_pattern", "message": "Blocked: path contains sensitive pattern"},
            {"type": "write_rejected", "message": "WRITE REJECTED: {reason}"},
        ],
        "recovery": "Check path bounds, avoid sensitive patterns, ensure content is valid",
    },
    {
        "name": "edit_file",
        "description": (
            "PREFERRED way to modify existing files. Replace an exact text segment with new text. Always use this "
            "instead of write_file for changes to existing files; it produces smaller, more reviewable diffs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to work_root"},
                "old_text": {"type": "string", "description": "Text to find and replace"},
                "new_text": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_text", "new_text"],
        },
        "permission": ASK_USER,
        "failure_modes": [
            {"type": "old_string_empty", "message": "old_string is empty"},
            {"type": "old_string_not_found", "message": "old_string not found in file"},
            {"type": "path_outside_root", "message": "Blocked: path is outside work_root"},
            {"type": "sensitive_pattern", "message": "Blocked: path contains sensitive pattern"},
            {"type": "edit_rejected", "message": "EDIT REJECTED: {reason}"},
        ],
        "recovery": "Read file first to get exact content, use precise old_string match",
    },
    {
        "name": "search_content",
        "description": "Search file contents with a literal text pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Literal text pattern"},
                "path": {"type": "string", "description": "File or directory search path"},
            },
            "required": ["pattern"],
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "Use an exact substring from the file or narrow the search path",
    },
    {
        "name": "search_files",
        "description": "Find files by glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern"},
                "path": {"type": "string", "description": "Search path"},
            },
            "required": ["pattern"],
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "list_dir",
        "description": "List directory contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"},
            },
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "run_command",
        "description": (
            "Execute a shell command inside work_root. Foreground commands return exit code, stdout, stderr, and "
            "timeout status. Use background=true only when the process should remain running; provide readiness_url "
            "when success depends on a local server becoming reachable. For local preview servers, do not retry the "
            "same port after port_in_use, wrong_server, or probe_unreachable; choose a free port or fix the served "
            "directory/readiness URL first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "timeout": {"type": "integer", "description": "Timeout in seconds"},
                "background": {
                    "type": "boolean",
                    "description": "Start a long-running process in the background instead of waiting for exit.",
                },
                "readiness_url": {
                    "type": "string",
                    "description": "Optional HTTP URL to probe when background=true before reporting the command ok.",
                },
                "readiness_text": {
                    "type": "string",
                    "description": "Optional text that must appear in the readiness_url response body.",
                },
            },
            "required": ["command"],
        },
        "permission": ASK_USER,
        "failure_modes": [
            {"type": "command_rejected", "message": "Command rejected: {reason}"},
            {"type": "command_failed", "message": "Command failed with exit code {code}"},
            {"type": "command_timeout", "message": "Command timed out after {timeout}s"},
            {"type": "incompatible_shell", "message": "Incompatible shell command on Windows"},
            {"type": "port_in_use", "message": "Requested local port is already listening"},
            {"type": "wrong_server", "message": "HTTP probe reached a server that is not serving the current work_root"},
            {"type": "probe_unreachable", "message": "Background process did not become reachable at the probe URL"},
            {"type": "probe_http_error", "message": "Readiness URL returned a non-success HTTP status"},
            {"type": "readiness_text_missing", "message": "Readiness response did not contain readiness_text"},
        ],
        "recovery": (
            "Fix command syntax, check platform compatibility, or increase timeout. For local preview servers, use "
            "recommended_action from tool metadata; for port_in_use choose a free port instead of retrying the same command."
        ),
    },
    {
        "name": "run_tests",
        "description": (
            "Detect and run test commands. A nonzero test exit is usually product feedback: inspect the failing "
            "assertion, make the smallest production-code edit with edit_file/write_file, then rerun tests. "
            "Only keep changing commands when the output clearly shows an environment or invocation problem."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Test command (auto-detected if empty)"},
                "timeout": {"type": "integer", "description": "Timeout in seconds"},
            },
        },
        "permission": ASK_USER,
        "failure_modes": [
            {"type": "no_test_command", "message": "No test command detected"},
            {"type": "test_failed", "message": "Tests failed"},
            {"type": "command_timeout", "message": "Test command timed out"},
        ],
        "recovery": (
            "If assertions fail, fix production code before rerunning equivalent tests. If the command itself is "
            "invalid, pass an explicit command, create a test script, or use alternative verification."
        ),
    },
    {
        "name": "web_search",
        "description": "Search the web via SearXNG or DuckDuckGo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results"},
                "domains": {"type": "array", "items": {"type": "string"}, "description": "Domain filter"},
            },
            "required": ["query"],
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [
            {"type": "search_failed", "message": "Web search failed"},
        ],
        "recovery": "Retry with simpler query, try different search terms",
    },
    {
        "name": "web_fetch",
        "description": "Fetch content from a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
            },
            "required": ["url"],
        },
        "permission": ASK_USER,
        "failure_modes": [
            {"type": "fetch_failed", "message": "Failed to fetch URL"},
            {"type": "invalid_url", "message": "Invalid URL"},
        ],
        "recovery": "Check URL validity, try alternative URL",
    },
    {
        "name": "git_status",
        "description": "Run git status in work_root.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "git_diff",
        "description": "Run git diff in work_root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Optional path filter"},
            },
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "recall_session",
        "description": (
            "Retrieve same-session indexed details by output_id, exact path, tag, or query. Use this when a previous "
            "tool output was summarized in the prompt and you need the full record."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "output_id": {
                    "type": "string",
                    "description": "Exact session output id, e.g. out-0002-0001-abcd1234",
                },
                "event_id": {
                    "type": "string",
                    "description": "Exact Git event id from the session memory index, e.g. git-a1b2c3d4e5",
                },
                "git_ref": {
                    "type": "string",
                    "description": "Exact Git commit, branch, or ref to inspect from the current repository",
                },
                "include_diff": {
                    "type": "boolean",
                    "description": "When true, return Git patch detail for git_ref/event_id/path.",
                },
                "path": {"type": "string", "description": "Exact file path to recall related session records"},
                "tag": {
                    "type": "string",
                    "description": "Exact tag such as error, tool:run_command, status:error, git:checkpoint",
                },
                "symbol": {
                    "type": "string",
                    "description": "Exact code symbol such as a class, function, interface, or exported name",
                },
                "heading": {
                    "type": "string",
                    "description": "Exact Markdown heading text from an indexed design or plan document",
                },
                "step_id": {
                    "type": "string",
                    "description": "Exact current plan step id associated with the record",
                },
                "query": {"type": "string", "description": "Keyword query over indexed summaries and refs"},
                "kind": {
                    "type": "string",
                    "enum": ["", "knowledge", "tool_output", "git"],
                    "description": "Optional record kind filter",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of index matches when output_id is not provided",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum detail chars to return for output_id lookup",
                },
            },
            "required": ["query"],
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "inspect_project",
        "description": "Inspect project structure and stack.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Project path"},
                "max_files": {"type": "integer", "description": "Max files to inspect"},
            },
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "browser_check",
        "description": "Fetch URL and check content/accessibility.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to check"},
                "expect": {"type": "string", "description": "Expected content pattern"},
            },
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [
            {"type": "file_protocol_blocked", "message": "Access to file: protocol is blocked"},
            {"type": "fetch_failed", "message": "Failed to fetch URL"},
        ],
        "recovery": "Use local static server with http://127.0.0.1:<port>/ instead of file://",
    },
    {
        "name": "decision_point",
        "description": "Declare a blocking user decision point with options. Runtime records it and asks the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Decision title"},
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Stable option id"},
                            "label": {"type": "string", "description": "Short user-facing option label"},
                            "description": {"type": "string", "description": "One-sentence option impact"},
                        },
                        "required": ["id", "label"],
                    },
                    "description": "Decision options with id, label, and description",
                },
                "context": {"type": "string", "description": "Short context for why the decision is needed"},
                "blocking": {"type": "boolean", "description": "Whether execution should wait for user input"},
            },
            "required": ["title", "options"],
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [
            {"type": "decision_rejected", "message": "DECISION REJECTED: {reason}"},
        ],
        "recovery": "Rephrase question, provide clearer options",
    },
    {
        "name": "request_commit_review",
        "description": "Ask the user to review the current completed work before creating a formal commit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short user-facing review title"},
                "summary": {"type": "string", "description": "Brief business-language summary"},
                "how_to_review": {"type": "string", "description": "Short practical review instruction"},
                "self_check": {"type": "string", "description": "What Writer already checked"},
                "commit_message": {"type": "string", "description": "Suggested commit message"},
            },
            "required": ["title", "summary", "how_to_review"],
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [
            {"type": "missing_review_summary", "message": "Review request needs a clear summary"},
        ],
        "recovery": "State what changed and how the user can verify it",
    },
    deepcopy(SUB_AGENT_TOOL_SPEC),
    {
        "name": "delegate_to_member",
        "description": "Delegate a sub-task to another LamTools family member.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_member": {
                    "type": "string",
                    "description": "Which member to delegate to: butler, sage, or artist",
                    "enum": ["butler", "sage", "artist"],
                },
                "task_description": {"type": "string", "description": "What task to delegate"},
                "context": {"type": "string", "description": "Brief context for the delegated member"},
            },
            "required": ["target_member", "task_description"],
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "load_skill",
        "description": "Load a specialized skill module.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name"},
            },
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "mcp_tool",
        "description": "Call an MCP-registered tool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "MCP tool name"},
                "arguments": {"type": "object", "description": "Tool arguments"},
            },
        },
        "permission": ASK_USER,
        "failure_modes": [
            {"type": "mcp_error", "message": "MCP TOOL ERROR: {reason}"},
            {"type": "tool_not_found", "message": "MCP tool not found"},
        ],
        "recovery": "Check tool name and arguments, verify MCP server status",
    },
    {
        "name": "chat_only",
        "description": "Chat-only mode, no tool execution.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "ask_clarification",
        "description": "Ask user for clarification.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Clarification question"},
            },
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "self_critique",
        "description": "Self-critique current work.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "write_checklist",
        "description": "Create the active structured checklist for the task. Use short numbered steps; each step becomes a Markdown checkbox in the UI.",
        "input_schema": {
            "type": "object",
            "properties": {
                "design_summary": {
                    "type": "string",
                    "description": "One short business-language sentence describing the goal.",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files or deliverables expected to change.",
                },
                "steps": {
                    "type": "array",
                    "description": "Ordered checklist items. Use 3-7 concrete steps for normal engineering tasks.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Stable id like s1, s2, s3."},
                            "description": {"type": "string", "description": "User-readable action item."},
                            "deliverables": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Concrete outputs for this step.",
                            },
                        },
                        "required": ["id", "description"],
                    },
                },
            },
            "required": ["design_summary", "steps"],
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "update_checklist",
        "description": "Update the active structured checklist. Mark a step complete immediately after verifying its deliverable; do not rewrite the whole checklist for ordinary progress.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add_step", "update_step", "split_step", "block_step", "complete_step", "replace_plan"],
                },
                "step_id": {"type": "string"},
                "description": {"type": "string"},
                "deliverables": {"type": "array", "items": {"type": "string"}},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "blocked", "skipped", "replaced"],
                    "description": "New status for update_step.",
                },
                "steps": {"type": "array", "items": {"type": "object"}},
                "files": {"type": "array", "items": {"type": "string"}},
                "design_summary": {"type": "string"},
                "reason": {"type": "string", "description": "Short reason visible in the run log."},
            },
            "required": ["action", "reason"],
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "verify_design",
        "description": "Verify design constraints.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
]


def _enrich_tool_specs() -> None:
    """Attach cross-cutting contract fields to every Writer tool spec."""
    for spec in WRITER_TOOL_SPECS:
        name = str(spec["name"])
        category = TOOL_CATEGORY_BY_NAME.get(name)
        if category is None:
            raise RuntimeError(f"Writer tool spec missing category: {name}")
        spec["input_schema"] = _strict_schema(spec["input_schema"])
        spec.setdefault("category", category)
        spec.setdefault("internal_only", name in INTERNAL_ONLY_TOOLS)
        spec.setdefault("output_schema", dict(DEFAULT_OUTPUT_SCHEMA))
        spec.setdefault("display", _default_display(category))


_enrich_tool_specs()


WRITER_TOOL_PERMISSIONS: dict[str, PermissionTier] = {
    spec["name"]: spec["permission"]
    for spec in WRITER_TOOL_SPECS
}


def writer_model_tools() -> list[dict[str, Any]]:
    """Generate OpenAI-compatible function tools from Writer tool specs."""
    specs_by_name = {str(spec["name"]): spec for spec in WRITER_TOOL_SPECS}
    tools: list[dict[str, Any]] = []

    for name in MODEL_TOOL_ORDER:
        spec = specs_by_name.get(name)
        if not spec:
            continue
        if spec.get("internal_only"):
            continue
        if spec.get("category") not in MODEL_VISIBLE_CATEGORIES:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(spec["description"]),
                    "strict": True,
                    "parameters": deepcopy(spec["input_schema"]),
                },
            }
        )

    return tools


WRITER_TOOLS: list[dict[str, Any]] = writer_model_tools()


def writer_tool_spec(name: str) -> dict[str, Any] | None:
    """Look up a tool spec by name. Returns None if not found."""
    for spec in WRITER_TOOL_SPECS:
        if spec["name"] == name:
            return spec
    return None


__all__ = [
    "DEFAULT_OUTPUT_SCHEMA",
    "INTERNAL_ONLY_TOOLS",
    "MODEL_VISIBLE_CATEGORIES",
    "TOOL_CATEGORY_BY_NAME",
    "WRITER_TOOLS",
    "WRITER_TOOL_SPECS",
    "WRITER_TOOL_PERMISSIONS",
    "writer_model_tools",
    "writer_tool_spec",
]
