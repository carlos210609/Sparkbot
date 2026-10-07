from evals.runner.result import EvaluationResult
from evals.runner.runner import BenchmarkRunner
from evals.runner.scenario import Scenario
from sparkbot.m1 import M1Orchestrator, Plan, Task, ToolResult, scenario_from_task


def planner(task: Task) -> Plan:
    return Plan(task.id, ("deterministic_echo",))


def tool(step: str, task: Task) -> ToolResult:
    return ToolResult(ok=True, output={"answer": task.prompt}, evidence={"verified": True, "method": "deterministic"})


def execute(scenario: Scenario) -> EvaluationResult:
    task=Task(scenario.id, scenario.prompt)
    result, trace=M1Orchestrator(planner, tool).run(task)
    return scenario_from_task(task, result, trace)


def main() -> None:
    scenarios=[Scenario("m1-001", "smoke", "Return this exact text.")]
    results=BenchmarkRunner(execute).run(scenarios)
    assert results[0].passed and results[0].verified
    print(results[0].to_dict())


if __name__ == "__main__":
    main()
