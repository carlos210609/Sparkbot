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
    RunState.EXECUTING: {RunState.VERIFYING, RunState.WAITING_TOOL, RunState.FAILED},
    RunState.VERIFYING: {
        RunState.EXECUTING,
        RunState.REPLANNING,
        RunState.SYNTHESIZING,
        RunState.FAILED,
    },
    RunState.REPLANNING: {RunState.PLANNING, RunState.FAILED, RunState.BUDGET_EXCEEDED},
    RunState.SYNTHESIZING: {RunState.SELF_EVALUATING, RunState.FAILED},
    RunState.SELF_EVALUATING: {RunState.DELIVERING, RunState.REPLANNING, RunState.FAILED},
    RunState.DELIVERING: {RunState.LEARNING, RunState.FAILED},
    RunState.LEARNING: {RunState.COMPLETED, RunState.FAILED},
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
    RunState.WAITING_TOOL: {RunState.RECEIVED, RunState.CANCELLED},
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

    def run(self, task: DurableTask, run_id: str | None = None, max_tool_steps: int = 20) -> dict[str, Any]:
        rid = run_id or self.store.create(task.id)
        state, payload = self._state(rid)
        if state in TERMINAL:
            return {"run_id": rid, "status": state.value, **payload}

        if state in {RunState.RECEIVED, RunState.FAILED, RunState.PAUSED}:
            self.store.checkpoint(rid, RunState.RECEIVED, {"task": task.prompt, "task_id": task.id})
            state = RunState.RECEIVED
            payload = {"task": task.prompt, "task_id": task.id}

        self._transition(rid, state, RunState.UNDERSTANDING, payload)
        payload = {**payload, "intent": task.prompt}
        self._transition(rid, RunState.UNDERSTANDING, RunState.PLANNING, payload)
        steps = self.planner(task)
        if not steps:
            self._transition(rid, RunState.PLANNING, RunState.FAILED, {**payload, "error": "empty plan"})
            return {"run_id": rid, "status": RunState.FAILED.value, "error": "empty plan"}

        payload = {**payload, "steps": steps, "next_step": 0, "outputs": []}
        self._transition(rid, RunState.PLANNING, RunState.DECOMPOSING, payload)
        self._transition(rid, RunState.DECOMPOSING, RunState.EXECUTING, payload)

        outputs = list(payload.get("outputs", []))
        for index in range(int(payload.get("next_step", 0)), len(steps)):
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
                cached = self.tool(steps[index], task, key)
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
            self._transition(rid, RunState.VERIFYING, RunState.EXECUTING, payload)

        self._transition(rid, RunState.EXECUTING, RunState.SYNTHESIZING, payload)
        payload = {**payload, "result": outputs}
        self._transition(rid, RunState.SYNTHESIZING, RunState.SELF_EVALUATING, payload)
        payload = {**payload, "self_evaluation": {"verified_outputs": len(outputs)}}
        self._transition(rid, RunState.SELF_EVALUATING, RunState.DELIVERING, payload)
        self._transition(rid, RunState.DELIVERING, RunState.LEARNING, payload)
        self._transition(rid, RunState.LEARNING, RunState.COMPLETED, payload)
        return {"run_id": rid, "status": RunState.COMPLETED.value, **payload}

    def pause(self, run_id: str) -> dict[str, Any]:
        state, payload = self._state(run_id)
        if state in TERMINAL:
            return {"run_id": run_id, "status": state.value, **payload}
        self.store.checkpoint(run_id, RunState.PAUSED, payload)
        return {"run_id": run_id, "status": RunState.PAUSED.value, **payload}
