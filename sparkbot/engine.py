from __future__ import annotations
import time, uuid
from dataclasses import dataclass, field
from .skills import SkillRegistry, Skill
from .skills.models import Permission, SkillRisk

@dataclass
class ExecutionContext:
    actor: str = "system"; mode: str = "DRY_RUN"; permissions: set[Permission] = field(default_factory=lambda:{Permission.READ})
    data: dict = field(default_factory=dict)

@dataclass
class ExecutionResult:
    execution_id: str; skill_id: str; status: str; verified: bool; output: dict; error: str | None; duration_ms: float

class PermissionEngine:
    def check(self, skill: Skill, ctx: ExecutionContext) -> tuple[bool,str]:
        missing=[p.value for p in skill.permissions if p not in ctx.permissions]
        if missing: return False, f"missing permissions: {', '.join(missing)}"
        if skill.risk_level in {SkillRisk.HIGH,SkillRisk.CRITICAL} and ctx.mode == "PRODUCTION" and not ctx.data.get("human_approved",False):
            return False, "human approval required for high/critical production action"
        return True, ""

class VerificationEngine:
    def verify(self, skill: Skill, output: dict) -> tuple[bool,str]:
        if not isinstance(output,dict): return False,"handler output must be an object"
        method=skill.verification_method
        if method=="output_exists": return bool(output), "output exists" if output else "empty output"
        if method=="explicit_verified": return output.get("verified") is True, "explicit verification flag required"
        return bool(output.get("verified", output)), "verification result unavailable"

class SkillRouter:
    def __init__(self, registry: SkillRegistry): self.registry=registry
    def route(self, request: str, limit: int=5) -> list[Skill]: return self.registry.search(request, limit)

class SkillExecutor:
    def __init__(self, registry: SkillRegistry):
        self.registry=registry; self.permissions=PermissionEngine(); self.verifier=VerificationEngine()
    def execute(self, skill_id: str, ctx: ExecutionContext, payload: dict | None=None) -> ExecutionResult:
        skill=self.registry.get(skill_id); eid=str(uuid.uuid4()); start=time.perf_counter()
        if not skill: return ExecutionResult(eid,skill_id,"FAILED",False,{},"skill_not_found",0)
        ok,reason=self.permissions.check(skill,ctx)
        if not ok: return ExecutionResult(eid,skill_id,"BLOCKED",False,{},reason,(time.perf_counter()-start)*1000)
        if ctx.mode not in {"SIMULATION","DRY_RUN","PRODUCTION"}: return ExecutionResult(eid,skill_id,"FAILED",False,{},"invalid_mode",0)
        try:
            if ctx.mode != "PRODUCTION" or skill.handler is None:
                output={"verified":True,"simulation":True,"skill_id":skill.id,"input":payload or {}}
            else: output=skill.handler(payload or {},ctx.data)
            verified,reason=self.verifier.verify(skill,output)
            return ExecutionResult(eid,skill.id,"COMPLETED" if verified else "FAILED",verified,output,None if verified else reason,(time.perf_counter()-start)*1000)
        except Exception as exc:
            return ExecutionResult(eid,skill.id,"FAILED",False,{},f"{type(exc).__name__}: {exc}",(time.perf_counter()-start)*1000)
