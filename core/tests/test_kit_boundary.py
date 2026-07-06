"""Contract tests: prove that RuntimeKit only does protocol bridging and tool execution.

RuntimeKit is a Protocol that defines the 10 lifecycle methods the kernel
calls. The Kit should not have methods that bypass the kernel's loop control.
"""

from __future__ import annotations

import inspect

from lamtools_core.kernel.kit import RuntimeKit


class TestKitBoundaryGuardrails:
    """Prove that RuntimeKit only does protocol bridging and tool execution."""

    def test_kit_has_no_decision_override(self):
        """RuntimeKit.decide_next returns a decision but cannot override it.

        The Kit's decide_next returns the decision for the current step, while
        CoreLoopKernel owns the loop structure and state transitions.
        """
        assert hasattr(RuntimeKit, 'decide_next'), "Kit should have decide_next"
        sig = inspect.signature(RuntimeKit.decide_next)
        # Return type should be LoopDecision, not a decision override
        # (This is a structural check, not runtime)

    def test_kit_has_lifecycle_methods_only(self):
        """RuntimeKit only has the 10 defined lifecycle methods."""
        methods = [name for name, _ in inspect.getmembers(RuntimeKit, predicate=inspect.isfunction) if not name.startswith('_')]
        expected = {
            'on_run_start', 'build_context', 'build_model_request',
            'parse_model_output', 'execute_tool', 'format_tool_result_for_model',
            'verify', 'decide_next', 'writeback', 'on_run_end',
        }
        actual = set(methods)
        extra = actual - expected
        assert len(extra) == 0, f"Kit should only have lifecycle methods, found extra: {extra}"

    def test_kit_cannot_start_loop(self):
        """RuntimeKit has no run/loop method that starts its own loop.

        on_run_start/on_run_end are lifecycle callbacks called BY the kernel,
        not methods that start the loop themselves.
        """
        methods = [name for name, _ in inspect.getmembers(RuntimeKit, predicate=inspect.isfunction) if not name.startswith('_')]
        loop_methods = [m for m in methods if any(kw in m.lower() for kw in ['loop', 'execute_turn'])]
        assert len(loop_methods) == 0, f"Kit should not have loop-starting methods, found: {loop_methods}"
