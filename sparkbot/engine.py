from __future__ import annotations

"""Core skill routing, permissions, execution and verification."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .skills import Permission, Skill, SkillRegistry, SkillRisk


@dataclass
class ExecutionContext:
    actor: str = "sparkbot"
    mode: str = "DRY_RUN"
    permissions: set[Permission] = field(default_factory=lambda: {Permission.READ})
    data: dict[str, Any] = field(default_factory=dict)
    human_approved: bool = False

    def __post_init__(self) -> None:
        self.mode = str(self.mode).upper()
        if self.mode not in {"SIMULATION", "DRY_RUN", "PRODUCTION"}:
            raise ValueError(f"invalid execution mode: {self.mode}")


@dataclass
class ExecutionResult:
    execution_id: str
    skill_id: str
    status: str
    verified: bool
    output: dict[str, Any]
    error: str | None
    duration_ms: float
    verification: dict[str, Any] = field(default_factory=dict)


class PermissionEngine:
    def check(self, skill: Skill, ctx: ExecutionContext) -> tuple[bool, str]:
        missing = [p.value for p in skill.permissions if p not in ctx.permissions]
        if missing:
            return False, f"missing permissions: {', '.join(missing)}"
        if (
            ctx.mode == "PRODUCTION"
            and skill.risk_level in {SkillRisk.HIGH, SkillRisk.CRITICAL}
            and not (ctx.human_approved or ctx.data.get("human_approved", False))
        ):
            return False, "human approval required for high/critical production action"
        return True, "allowed"


class VerificationEngine:
    def verify(self, skill: Skill, output: dict[str, Any], mode: str) -> tuple[bool, str]:
        if not isinstance(output, dict):
            return False, "handler output must be an object"
        if mode in {"SIMULATION", "DRY_RUN"}:
            return True, "simulation contract verified; no external side effect claimed"
        if output.get("verified") is True:
            return True, "handler explicitly verified the result"
        if skill.verification_method == "output_exists" and output:
            return True, "non-empty handler output returned"
        return False, "production handler did not provide verifiable evidence"


class SkillRouter:
    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def route(self, request: str, limit: int = 5) -> list[Skill]:
        selected = self.registry.search(request, limit)
        if selected:
            return selected
        fallback_ids = ("001.01", "007.01", "003.01", "011.01", "089.01")
        return [self.registry.get(i) for i in fallback_ids if self.registry.get(i)][:limit]


class SkillExecutor:
    def __init__(self, registry: SkillRegistry):
        self.registry = registry
        self.permissions = PermissionEngine()
        self.verifier = VerificationEngine()
        self.handlers: dict[str, Callable[..., dict[str, Any]]] = {}

    def register_handler(self, skill_id: str, handler: Callable[..., dict[str, Any]]) -> None:
        if self.registry.get(skill_id) is None:
            raise KeyError(skill_id)
        self.handlers[skill_id] = handler

    def execute(
        self,
        skill_id: str,
        ctx: ExecutionContext,
        payload: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        skill = self.registry.get(skill_id)
        start = time.perf_counter()
        eid = uuid.uuid4().hex
        if skill is None:
            return ExecutionResult(eid, skill_id, "FAILED", False, {}, "skill_not_found", 0.0)
        if not skill.enabled:
            return ExecutionResult(eid, skill_id, "BLOCKED", False, {}, "skill_disabled", 0.0)

        ok, reason = self.permissions.check(skill, ctx)
        if not ok:
            return ExecutionResult(
                eid, skill_id, "BLOCKED", False, {}, reason,
                (time.perf_counter() - start) * 1000,
            )

        try:
            payload = payload or {}
            if ctx.mode in {"SIMULATION", "DRY_RUN"}:
                output = {
                    "verified": True,
                    "simulation": True,
                    "skill_id": skill.id,
                    "input": payload,
                    "message": "Simulated only; no external side effect was performed.",
                }
            elif skill.id in self.handlers:
                output = self.handlers[skill.id](skill, ctx, payload)
            elif skill.handler is not None:
                output = skill.handler(payload, ctx.data)
            else:
                output = {
                    "verified": False,
                    "simulation": False,
                    "skill_id": skill.id,
                    "message": "No production adapter is registered for this skill.",
                }

            verified, verification_reason = self.verifier.verify(skill, output, ctx.mode)
            return ExecutionResult(
                eid,
                skill.id,
                "COMPLETED" if verified else "FAILED",
                verified,
                output,
                None if verified else verification_reason,
                (time.perf_counter() - start) * 1000,
                {"verified": verified, "reason": verification_reason, "mode": ctx.mode},
            )
        except Exception as exc:
            return ExecutionResult(
                eid, skill.id, "FAILED", False, {},
                f"{type(exc).__name__}: {exc}",
                (time.perf_counter() - start) * 1000,
                {"verified": False, "reason": "handler exception", "mode": ctx.mode},
            )
