"""Spark cognitive mission engine: recruitment, planning, critique, execution and verification."""
from __future__ import annotations
import json, time, uuid
from typing import Any
from .agent_mesh import AgentMesh, AgentProfile
from .db import execute
from .engine import ExecutionContext, SkillExecutor, SkillRouter
from .skills import SkillRegistry, Permission

class CognitiveEngine:
    def __init__(self, registry: SkillRegistry | None = None):
        self.registry = registry or SkillRegistry()
        self.router = SkillRouter(self.registry)
        self.executor = SkillExecutor(self.registry)
        self.agents = AgentMesh()

    def recruit(self, request: str, limit: int = 14) -> list[AgentProfile]:
        selected = self.agents.search(request, limit)
        if not selected:
            selected = [self.agents.get(x) for x in (
                "A001-RESEARCHER","A001-STRATEGIST","A001-PLANNER",
                "A001-CRITIC","A001-VERIFIER")]
        return [a for a in selected if a is not None]

    def critique(self, request: str, agents: list[AgentProfile], skills: list[dict[str, Any]]) -> dict[str, Any]:
        risk_words=("pagar","comprar","excluir","deletar","publicar","enviar","senha","credencial","dinheiro")
        high_risk=any(w in request.lower() for w in risk_words)
        return {"approved_for_planning":True,"requires_approval":high_risk,
                "concerns":["External side effects require explicit permissions/approval."] if high_risk else [],
                "agent_count":len(agents),"skill_count":len(skills),"confidence":0.92 if skills else 0.55}

    def run(self, request: str, *, mode: str="DRY_RUN", max_skills: int=8, mission_id: str | None = None) -> dict[str, Any]:
        started=time.perf_counter(); mission_id=mission_id or uuid.uuid4().hex
        skills=self.router.route(request, limit=max_skills); skill_dicts=[s.to_dict() for s in skills]
        agents=self.recruit(request); critique=self.critique(request,agents,skill_dicts)
        execute_mode="DRY_RUN" if critique["requires_approval"] else mode
        ctx=ExecutionContext(actor="spark-cognitive-core",mode=execute_mode,permissions={Permission.READ},data={"mission_id":mission_id})
        results=[]; events=[{"type":"observe","message":"Mission received and context normalized."},{"type":"recruit","message":f"{len(agents)} specialist agents recruited."},{"type":"plan","message":f"{len(skills)} relevant skills selected."},{"type":"critique","message":"Plan passed the safety/verification gate."}]
        for skill in skills:
            result=self.executor.execute(skill.id,ctx,{"request":request,"mission_id":mission_id})
            results.append({"execution_id":result.execution_id,"skill_id":result.skill_id,"status":result.status,"verified":result.verified,"output":result.output,"error":result.error,"duration_ms":result.duration_ms})
            events.append({"type":"execution","skill_id":result.skill_id,"status":result.status,"verified":result.verified})
        verified=bool(results) and all(r["verified"] for r in results)
        status="COMPLETED" if verified else ("PLANNED" if not results else "PARTIAL")
        duration_ms=(time.perf_counter()-started)*1000
        execute(
            "UPDATE missions SET request=?, goal=?, status=?, confidence=?, selected_agents=?, selected_skills=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (request, "Autonomous mission", status, float(critique["confidence"]), len(agents), len(skills), mission_id),
        )
        if not __import__("sparkbot.db", fromlist=["fetch_one"]).fetch_one("SELECT id FROM missions WHERE id=?", (mission_id,)):
            execute(
                "INSERT INTO missions(id,request,goal,status,confidence,selected_agents,selected_skills) VALUES (?,?,?,?,?,?,?)",
                (mission_id, request, "Autonomous mission", status, float(critique["confidence"]), len(agents), len(skills)),
            )
        for e in events:
            execute("INSERT INTO mission_events(mission_id,event_type,message,metadata) VALUES (?,?,?,?)",
                    (mission_id,e["type"],e["message"],json.dumps(e,ensure_ascii=False)))
        return {"mission_id":mission_id,"status":status,"mode":execute_mode,"request":request,
                "agents":[a.to_dict() for a in agents],"skills":skill_dicts,"critique":critique,
                "results":results,"events":events,"verified":verified,"duration_ms":duration_ms}
