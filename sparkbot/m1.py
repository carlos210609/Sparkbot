"""M1 task orchestration flow: Task -> Plan -> Tool -> Verify -> Result -> Trace -> Eval."""
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable

from evals.runner.result import EvaluationResult
from evals.runner.scenario import Scenario


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    task_id: str
    steps: tuple[str, ...]


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: Any = None
    error: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerifiedResult:
    success: bool
    output: Any = None
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class M1Orchestrator:
    """Small deterministic orchestration seam ready to connect to existing SparkBot tools."""

    def __init__(self, planner: Callable[[Task], Plan], tool: Callable[[str, Task], ToolResult]):
        self.planner = planner
        self.tool = tool

    def run(self, task: Task) -> tuple[VerifiedResult, list[dict[str, Any]]]:
        trace: list[dict[str, Any]] = []
        started = perf_counter()
        trace.append({"stage": "RECEIVED", "task_id": task.id})
        plan = self.planner(task)
        trace.append({"stage": "PLANNED", "steps": list(plan.steps)})
        if not plan.steps:
            return VerifiedResult(False, error="empty plan"), trace
        last: ToolResult | None = None
        for step in plan.steps:
            last = self.tool(step, task)
            trace.append({"stage": "TOOL", "step": step, "ok": last.ok, "evidence": last.evidence})
            if not last.ok:
                trace.append({"stage": "FAILED", "error": last.error})
                return VerifiedResult(False, error=last.error), trace
        assert last is not None
        verified = bool(last.ok and last.evidence.get("verified") is True)
        result = VerifiedResult(verified, last.output if verified else None, last.evidence,
                               None if verified else "missing independent verification evidence")
        trace.append({"stage": "VERIFIED", "success": result.success,
                      "latency_ms": (perf_counter() - started) * 1000})
        return result, trace


def scenario_from_task(task: Task, result: VerifiedResult, trace: list[dict[str, Any]]) -> EvaluationResult:
    return EvaluationResult(
        scenario_id=task.id,
        passed=result.success,
        steps=sum(1 for item in trace if item["stage"] == "TOOL"),
        latency_ms=float(next((item.get("latency_ms", 0) for item in reversed(trace) if "latency_ms" in item), 0)),
        verified=bool(result.evidence.get("verified") is True),
        hallucinated_result=bool(result.output is not None and not result.success),
        metadata={"trace_stages": [item["stage"] for item in trace]},
    )
