"""Tests for lamtools_core.guardrail module."""

from lamtools_core.guardrail import (
    BaseGuardrailPipeline,
    GuardrailAction,
    GuardrailCheck,
    GuardrailDecision,
    GuardrailPipeline,
    GuardrailPolicy,
    GuardrailProtocol,
    GuardrailResult,
    GuardrailSubject,
    GuardrailSubjectKind,
)


class StaticPolicy:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def check(self, subject):
        self.calls += 1
        return self.result


class TestGuardrailTypes:
    def test_guardrail_check(self):
        check = GuardrailCheck(
            name="boundary_check",
            subject_kind="tool_call",
            subject_name="mutating_operation",
            payload={"path": "x"},
            context={"session_id": "s1"},
        )
        d = check.to_dict()
        assert d["name"] == "boundary_check"
        assert d["subject_kind"] == "tool_call"
        assert d["payload"] == {"path": "x"}
        assert d["context"] == {"session_id": "s1"}

    def test_guardrail_result_allow(self):
        r = GuardrailResult(action="allow")
        assert r.allowed is True
        assert r.action == "allow"

    def test_guardrail_result_block(self):
        r = GuardrailResult(action="block", reason="policy violation", severity="error", metadata={"rule": "x"})
        assert r.allowed is False
        d = r.to_dict()
        assert d["action"] == "block"
        assert d["severity"] == "error"
        assert d["metadata"] == {"rule": "x"}

    def test_guardrail_result_warn(self):
        r = GuardrailResult(action="warn", reason="suspicious", severity="warning")
        assert r.action == "warn"
        assert not r.allowed

    def test_guardrail_result_repair(self):
        r = GuardrailResult(action="repair", repair_suggestion="Adjust the request")
        assert r.action == "repair"
        d = r.to_dict()
        assert d["action"] == "repair"
        assert d["repair_suggestion"] == "Adjust the request"

    def test_guardrail_result_ask_user(self):
        r = GuardrailResult(action="ask_user", requires_user_input=True)
        assert r.action == "ask_user"
        assert r.requires_user_input is True

    def test_guardrail_subject(self):
        s = GuardrailSubject(kind="tool_call", name="mutating_operation", payload={"target": "x"})
        assert s.kind == "tool_call"
        assert s.name == "mutating_operation"
        assert s.to_dict()["payload"] == {"target": "x"}

    def test_guardrail_decision(self):
        d = GuardrailDecision(allowed=False, reason="blocked", retryable=True, metadata={"source": "policy"})
        assert not d.allowed
        assert d.retryable
        assert d.to_dict()["metadata"] == {"source": "policy"}

    def test_all_actions(self):
        actions: list[GuardrailAction] = ["allow", "block", "warn", "repair", "ask_user"]
        for action in actions:
            r = GuardrailResult(action=action)
            assert r.action == action

    def test_all_subject_kinds(self):
        kinds: list[GuardrailSubjectKind] = [
            "tool_call", "tool_result", "llm_request", "llm_response", "event", "state",
        ]
        for kind in kinds:
            s = GuardrailSubject(kind=kind)
            assert s.kind == kind

    def test_protocols_are_runtime_checkable(self):
        assert isinstance("not_a_policy", GuardrailPolicy) is False
        assert isinstance("not_a_pipeline", GuardrailPipeline) is False
        assert isinstance("not_a_protocol", GuardrailProtocol) is False


class TestBaseGuardrailPipeline:
    async def test_empty_pipeline_allows(self):
        result = await BaseGuardrailPipeline().check(GuardrailSubject(kind="state"))
        assert result.action == "allow"

    async def test_pipeline_merges_warn_and_repair(self):
        pipeline = BaseGuardrailPipeline([
            StaticPolicy(GuardrailResult(action="warn", reason="soft issue", severity="warning")),
            StaticPolicy(GuardrailResult(
                action="repair",
                reason="needs repair",
                severity="error",
                repair_suggestion="adjust input",
                metadata={"rule": "repair"},
            )),
        ])

        result = await pipeline.check(GuardrailSubject(kind="tool_call"))

        assert result.action == "repair"
        assert result.severity == "error"
        assert result.reason == "soft issue; needs repair"
        assert result.repair_suggestion == "adjust input"
        assert result.metadata == {"rule": "repair"}

    async def test_pipeline_converts_decision_and_stops_on_block(self):
        blocking = StaticPolicy(GuardrailDecision(allowed=False, reason="blocked", severity="critical"))
        later = StaticPolicy(GuardrailResult(action="warn", reason="should not run"))
        pipeline = BaseGuardrailPipeline([blocking, later])

        result = await pipeline.check(GuardrailSubject(kind="llm_request"))

        assert result.action == "block"
        assert result.severity == "critical"
        assert result.reason == "blocked"
        assert later.calls == 0
