import pytest

from sparkbot.m2 import (
    DurableOrchestrator,
    DurableRunStore,
    DurableTask,
    DurableToolResult,
    RunState,
)


def test_m2_persists_checkpoints_and_completes(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARKBOT_DB_PATH", str(tmp_path / "sparkbot.db"))
    calls = []

    def planner(task):
        return ["step-a", "step-b"]

    def tool(step, task, key):
        calls.append(key)
        return DurableToolResult(True, {"step": step}, {"verified": True})

    store = DurableRunStore()
    result = DurableOrchestrator(planner, tool, store=store).run(
        DurableTask("task-1", "do two things")
    )

    assert result["status"] == RunState.COMPLETED.value
    assert len(calls) == 2
    assert store.latest(result["run_id"])["state"] == RunState.COMPLETED.value


def test_m2_resumes_waiting_tool_without_repeating_verified_effect(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARKBOT_DB_PATH", str(tmp_path / "sparkbot.db"))
    calls = {"count": 0}

    def planner(task):
        return ["only-step"]

    def tool(step, task, key):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary tool outage")
        return DurableToolResult(True, "ok", {"verified": True})

    store = DurableRunStore()
    orchestrator = DurableOrchestrator(planner, tool, store=store)
    task = DurableTask("task-2", "recover")

    first = orchestrator.run(task)
    assert first["status"] == RunState.WAITING_TOOL.value

    second = orchestrator.run(task, run_id=first["run_id"])
    assert second["status"] == RunState.COMPLETED.value
    assert calls["count"] == 2

    effects = store.effect_get(first["run_id"], "task-2:0:only-step")
    assert effects is not None
    assert effects.evidence["verified"] is True


def test_m2_budget_can_resume_with_new_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARKBOT_DB_PATH", str(tmp_path / "sparkbot.db"))
    calls = []

    def planner(task):
        return ["a", "b"]

    def tool(step, task, key):
        calls.append(step)
        return DurableToolResult(True, step, {"verified": True})

    store = DurableRunStore()
    orchestrator = DurableOrchestrator(planner, tool, store=store)
    task = DurableTask("task-3", "budget")

    first = orchestrator.run(task, max_tool_steps=1)
    assert first["status"] == RunState.BUDGET_EXCEEDED.value

    second = orchestrator.run(task, run_id=first["run_id"], max_tool_steps=5)
    assert second["status"] == RunState.COMPLETED.value
    assert calls == ["a", "b"]


def test_m2_verification_blocks_unverified_results(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARKBOT_DB_PATH", str(tmp_path / "sparkbot.db"))

    def planner(task):
        return ["unsafe-result"]

    def tool(step, task, key):
        return DurableToolResult(True, "claimed", {"verified": False})

    store = DurableRunStore()
    result = DurableOrchestrator(planner, tool, store=store).run(
        DurableTask("task-4", "verify")
    )

    assert result["status"] == RunState.FAILED.value
    assert result["verification_error"] == "missing independent verification evidence"


def test_m2_pause_resume_preserves_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARKBOT_DB_PATH", str(tmp_path / "sparkbot.db"))
    calls = []

    def planner(task):
        return ["a", "b"]

    def tool(step, task, key):
        calls.append(step)
        return DurableToolResult(True, step, {"verified": True})

    store = DurableRunStore()
    orchestrator = DurableOrchestrator(planner, tool, store=store)
    task = DurableTask("task-pause", "pause")

    first = orchestrator.run(task, max_tool_steps=1)
    assert first["status"] == RunState.BUDGET_EXCEEDED.value

    paused = orchestrator.pause(first["run_id"])
    assert paused["status"] == RunState.PAUSED.value

    resumed = orchestrator.resume(task, paused["run_id"], max_tool_steps=5)
    assert resumed["status"] == RunState.COMPLETED.value
    assert calls == ["a", "b"]


def test_m2_cancel_is_terminal(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARKBOT_DB_PATH", str(tmp_path / "sparkbot.db"))

    def planner(task):
        return ["a"]

    def tool(step, task, key):
        return DurableToolResult(True, "ok", {"verified": True})

    store = DurableRunStore()
    orchestrator = DurableOrchestrator(planner, tool, store=store)
    task = DurableTask("task-cancel", "cancel")

    created = store.create(task.id)
    cancelled = orchestrator.cancel(created)
    assert cancelled["status"] == RunState.CANCELLED.value

    resumed = orchestrator.run(task, run_id=created)
    assert resumed["status"] == RunState.CANCELLED.value
