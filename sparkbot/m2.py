"""M2 durable, resumable orchestration state machine with checkpoints and idempotency."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .db import execute, fetch_one, init_db


class RunState(str, Enum):
    RECEIVED = "RECEIVED"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    DECOMPOSING = "DECOMPOSING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    REPLANNING = "REPLANNING"
    SYNTHESIZING = "SYNTHESIZING"
    SELF_EVALUATING = "SELF_EVALUATING"
    DELIVERING = "DELIVERING"
    LEARNING = "LEARNING"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    WAITING_USER = "WAITING_USER"
    WAITING_TOOL = "WAITING_TOOL"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    SECURITY_BLOCKED = "SECURITY_BLOCKED"


TERMINAL = {
    RunState.COMPLETED,
    RunState.CANCELLED,
    RunState.SECURITY_BLOCKED,
}


ALLOWED: dict[RunState, set[RunState]] = {
    RunState.RECEIVED: {RunState.UNDERSTANDING, RunState.FAILED, RunState.CANCELLED},
    RunState.UNDERSTANDING: {RunState.PLANNING, RunState.WAITING_USER, RunState.FAILED},
    RunState.PLANNING: {RunState.DECOMPOSING, RunState.REPLANNING, RunState.FAILED},
    RunState.DECOMPOSING: {RunState.EXECUTING, RunState.FAILED},
    RunState.EXECUTING: {RunState.VERIFYING, RunState.WAITING_TOOL, RunState.FAILED, RunState.PAUSED},
    RunState.VERIFYING: {
        RunState.EXECUTING,
        RunState.REPLANNING,
        RunState.SYNTHESIZING,
        RunState.FAILED,
        RunState.PAUSED,
    },
    RunState.REPLANNING: {RunState.PLANNING, RunState.FAILED, RunState.BUDGET_EXCEEDED},
    RunState.SYNTHESIZING: {RunState.SELF_EVALUATING, RunState.FAILED, RunState.PAUSED},
    RunState.SELF_EVALUATING: {RunState.DELIVERING, RunState.REPLANNING, RunState.FAILED, RunState.PAUSED},
    RunState.DELIVERING: {RunState.LEARNING, RunState.FAILED, RunState.PAUSED},
    RunState.LEARNING: {RunState.COMPLETED, RunState.FAILED, RunState.PAUSED},
    RunState.PAUSED: {
        RunState.RECEIVED,
        RunState.PLANNING,
        RunState.EXECUTING,
        RunState.CANCELLED,
    },
    RunState.FAILED: {
        RunState.RECEIVED,
        RunState.REPLANNING,
        RunState.CANCELLED,
    },
    RunState.WAITING_USER: {RunState.RECEIVED, RunState.CANCELLED},
    RunState.WAITING_TOOL: {RunState.RECEIVED, RunState.EXECUTING, RunState.CANCELLED},
    RunState.BUDGET_EXCEEDED: {RunState.REPLANNING, RunState.CANCELLED},
}


@dataclass(frozen=True)
class DurableTask:
    id: str
    prompt: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DurableToolResult:
    ok: bool
    output: Any = None
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


Planner = Callable[[DurableTask], list[str]]
Tool = Callable[[str, DurableTask, str], DurableToolResult]
Verifier = Callable[[str, DurableToolResult], tuple[bool, str]]


def default_verifier(_step: str, result: DurableToolResult) -> tuple[bool, str]:
    if not result.ok:
        return False, result.error or "tool failed"
    if result.evidence.get("verified") is not True:
        return False, "missing independent verification evidence"
    return True, "verified"


class DurableRunStore:
    def __init__(self) -> None:
        init_db()

    def create(self, task_id: str, run_id: str | None = None) -> str:
        rid = run_id or uuid.uuid4().hex
        execute(
            "INSERT INTO orchestration_runs(id,task_id,status,state_payload) VALUES (?,?,?,?)",
            (rid, task_id, RunState.RECEIVED.value, "{}"),
        )
        return rid

    def get(self, run_id: str) -> dict[str, Any] | None:
        return fetch_one("SELECT * FROM orchestration_runs WHERE id=?", (run_id,))

    def checkpoint(self, run_id: str, state: RunState, payload: dict[str, Any]) -> int:
        latest = fetch_one(
            "SELECT COALESCE(MAX(checkpoint_index), -1) AS idx "
            "FROM orchestration_checkpoints WHERE run_id=?",
            (run_id,),
        )
        index = int(latest["idx"]) + 1 if latest else 0
        body = json.dumps(payload, ensure_ascii=False, default=str)
        execute(
            "INSERT INTO orchestration_checkpoints(run_id,state,checkpoint_index,payload) "
            "VALUES (?,?,?,?)",
            (run_id, state.value, index, body),
        )
        execute(
            "UPDATE orchestration_runs SET status=?, state_payload=?, updated_at=CURRENT_TIMESTAMP "
            "WHERE id=?",
            (state.value, body, run_id),
        )
        return index

    def latest(self, run_id: str) -> dict[str, Any] | None:
        return fetch_one(
            "SELECT * FROM orchestration_checkpoints WHERE run_id=? "
            "ORDER BY checkpoint_index DESC LIMIT 1",
            (run_id,),
        )

    def effect_get(self, run_id: str, idempotency_key: str) -> DurableToolResult | None:
        row = fetch_one(
            "SELECT output FROM orchestration_effects WHERE run_id=? AND idempotency_key=?",
            (run_id, idempotency_key),
        )
        if not row:
            return None
        data = json.loads(row["output"])
        return DurableToolResult(**data)

    def effect_put(self, run_id: str, idempotency_key: str, result: DurableToolResult) -> None:
        payload = json.dumps(
            {
                "ok": result.ok,
                "output": result.output,
                "evidence": result.evidence,
                "error": result.error,
            },
            ensure_ascii=False,
            default=str,
        )
        execute(
            "INSERT OR IGNORE INTO orchestration_effects(run_id,idempotency_key,output) "
            "VALUES (?,?,?)",
            (run_id, idempotency_key, payload),
        )


class DurableOrchestrator:
    """Resumable state machine; every transition is checkpointed."""

    def __init__(
        self,
        planner: Planner,
        tool: Tool,
        verifier: Verifier = default_verifier,
        store: DurableRunStore | None = None,
    ) -> None:
        self.planner = planner
        self.tool = tool
        self.verifier = verifier
        self.store = store or DurableRunStore()

    def _transition(self, run_id: str, current: RunState, target: RunState, payload: dict[str, Any]) -> None:
        if target not in ALLOWED.get(current, set()):
            raise RuntimeError(f"invalid transition: {current.value} -> {target.value}")
        self.store.checkpoint(run_id, target, payload)

    def _state(self, run_id: str) -> tuple[RunState, dict[str, Any]]:
        checkpoint = self.store.latest(run_id)
        if not checkpoint:
            run = self.store.get(run_id)
            if not run:
                raise KeyError(run_id)
            return RunState(run["status"]), json.loads(run["state_payload"] or "{}")
        return RunState(checkpoint["state"]), json.loads(checkpoint["payload"])

    def run(
        self,
        task: DurableTask,
        run_id: str | None = None,
        max_tool_steps: int = 20,
        max_replans: int = 3,
    ) -> dict[str, Any]:
        if max_tool_steps < 1:
            raise ValueError("max_tool_steps must be positive")
        if run_id:
            existing = self.store.get(run_id)
            if not existing:
                raise KeyError(run_id)
            if existing["task_id"] != task.id:
                raise ValueError("run_id belongs to a different task")
            rid = run_id
        else:
            rid = self.store.create(task.id)
        state, payload = self._state(rid)
        payload = {**payload, "max_replans": max(0, max_replans)}
        if state in TERMINAL:
            return {"run_id": rid, "status": state.value, **payload}

        if max_tool_steps < 1:
            raise ValueError("max_tool_steps must be positive")

        if state in {RunState.FAILED}:
            self.store.checkpoint(rid, RunState.RECEIVED, {"task": task.prompt, "task_id": task.id})
            state = RunState.RECEIVED
            payload = {"task": task.prompt, "task_id": task.id}

        if state == RunState.PAUSED:
            resume_state = RunState(payload.get("resume_state", RunState.RECEIVED.value))
            payload = dict(payload.get("resume_payload", payload))
            state = resume_state

        if state == RunState.RECEIVED:
            self._transition(rid, state, RunState.UNDERSTANDING, payload)
            state = RunState.UNDERSTANDING
            payload = {**payload, "intent": task.prompt}

        if state == RunState.UNDERSTANDING:
            self._transition(rid, state, RunState.PLANNING, payload)
            state = RunState.PLANNING
            try:
                payload = {**payload, "steps": self.planner(task), "next_step": 0, "outputs": []}
            except Exception as exc:
                payload = {**payload, "error": f"{type(exc).__name__}: {exc}"}
                self._transition(rid, state, RunState.FAILED, payload)
                return {"run_id": rid, "status": RunState.FAILED.value, **payload}

        if state == RunState.BUDGET_EXCEEDED:
            replans = int(payload.get("replans", 0))
            if replans >= int(payload.get("max_replans", 3)):
                return {"run_id": rid, "status": RunState.BUDGET_EXCEEDED.value, **payload}
            self._transition(rid, state, RunState.REPLANNING, payload)
            state = RunState.REPLANNING

        if state == RunState.REPLANNING:
            self._transition(rid, state, RunState.PLANNING, payload)
            state = RunState.PLANNING
            try:
                payload = {
                    **payload,
                    "steps": self.planner(task),
                    "next_step": int(payload.get("next_step", 0)),
                    "outputs": list(payload.get("outputs", [])),
                    "replans": int(payload.get("replans", 0)) + 1,
                }
            except Exception as exc:
                payload = {**payload, "error": f"{type(exc).__name__}: {exc}"}
                self._transition(rid, state, RunState.FAILED, payload)
                return {"run_id": rid, "status": RunState.FAILED.value, **payload}

        steps = list(payload.get("steps", []))
        if not steps:
            self._transition(rid, state, RunState.FAILED, {**payload, "error": "empty plan"})
            return {"run_id": rid, "status": RunState.FAILED.value, "error": "empty plan"}

        if state == RunState.PLANNING:
            self._transition(rid, state, RunState.DECOMPOSING, payload)
            state = RunState.DECOMPOSING
        if state == RunState.DECOMPOSING:
            self._transition(rid, state, RunState.EXECUTING, payload)
            state = RunState.EXECUTING
        if state in {RunState.VERIFYING, RunState.WAITING_TOOL}:
            self._transition(rid, state, RunState.EXECUTING, payload)
            state = RunState.EXECUTING

        outputs = list(payload.get("outputs", []))
        start_index = int(payload.get("next_step", 0))
        for index in range(start_index, len(steps)):
            if index >= max_tool_steps:
                data = {**payload, "next_step": index, "outputs": outputs, "error": "tool step budget exceeded"}
                self._transition(rid, RunState.EXECUTING, RunState.BUDGET_EXCEEDED, data)
                return {"run_id": rid, "status": RunState.BUDGET_EXCEEDED.value, **data}

            key = f"{task.id}:{index}:{steps[index]}"
            current_payload = {
                **payload,
                "steps": steps,
                "next_step": index,
                "outputs": outputs,
                "idempotency_key": key,
            }
            self.store.checkpoint(rid, RunState.EXECUTING, current_payload)
            cached = self.store.effect_get(rid, key)
            if cached is None:
                try:
                    cached = self.tool(steps[index], task, key)
                except Exception as exc:
                    wait_payload = {**current_payload, "error": f"{type(exc).__name__}: {exc}"}
                    self._transition(rid, RunState.EXECUTING, RunState.WAITING_TOOL, wait_payload)
                    return {"run_id": rid, "status": RunState.WAITING_TOOL.value, **wait_payload}
                self.store.effect_put(rid, key, cached)

            verify_payload = {**current_payload, "tool_ok": cached.ok, "tool_error": cached.error}
            self._transition(rid, RunState.EXECUTING, RunState.VERIFYING, verify_payload)
            verified, reason = self.verifier(steps[index], cached)
            if not verified:
                data = {**verify_payload, "verification_error": reason}
                self._transition(rid, RunState.VERIFYING, RunState.FAILED, data)
                return {"run_id": rid, "status": RunState.FAILED.value, **data}
            outputs.append(cached.output)
            payload = {**current_payload, "outputs": outputs, "next_step": index + 1}

        self._transition(rid, RunState.VERIFYING if steps else RunState.EXECUTING, RunState.SYNTHESIZING, payload)
        payload = {**payload, "result": outputs}
        self._transition(rid, RunState.SYNTHESIZING, RunState.SELF_EVALUATING, payload)
        payload = {**payload, "self_evaluation": {"verified_outputs": len(outputs)}}
        self._transition(rid, RunState.SELF_EVALUATING, RunState.DELIVERING, payload)
        self._transition(rid, RunState.DELIVERING, RunState.LEARNING, payload)
        self._transition(rid, RunState.LEARNING, RunState.COMPLETED, payload)
        return {"run_id": rid, "status": RunState.COMPLETED.value, **payload}

    def pause(self, run_id: str) -> dict[str, Any]:
        state, payload = self._state(run_id)
        if state in TERMINAL or state == RunState.PAUSED:
            return {"run_id": run_id, "status": state.value, **payload}
        paused = {
            "resume_state": state.value,
            "resume_payload": payload,
            "paused": True,
        }
        self.store.checkpoint(run_id, RunState.PAUSED, paused)
        return {"run_id": run_id, "status": RunState.PAUSED.value, **paused}

    def cancel(self, run_id: str) -> dict[str, Any]:
        state, payload = self._state(run_id)
        if state in TERMINAL:
            return {"run_id": run_id, "status": state.value, **payload}
        self.store.checkpoint(
            run_id, RunState.CANCELLED, {**payload, "cancelled_from": state.value}
        )
        return {"run_id": run_id, "status": RunState.CANCELLED.value, **payload}

    def resume(
        self,
        task: DurableTask,
        run_id: str,
        max_tool_steps: int = 20,
        max_replans: int = 3,
    ) -> dict[str, Any]:
        return self.run(
            task,
            run_id=run_id,
            max_tool_steps=max_tool_steps,
            max_replans=max_replans,
        )
