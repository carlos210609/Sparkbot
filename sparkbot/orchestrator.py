from __future__ import annotations
from .engine import ExecutionContext, SkillExecutor, SkillRouter
from .skills import SkillRegistry

class Orchestrator:
    def __init__(self):
        self.registry=SkillRegistry(); self.router=SkillRouter(self.registry); self.executor=SkillExecutor(self.registry)
    def plan(self, request:str) -> dict:
        skills=self.router.route(request,limit=10)
        return {"request":request,"skills":[s.to_dict() for s in skills],"count":len(skills)}
    def run(self, request:str, ctx:ExecutionContext|None=None) -> dict:
        ctx=ctx or ExecutionContext()
        selected=self.router.route(request,limit=10)
        results=[]
        for skill in selected:
            results.append(self.executor.execute(skill.id,ctx,{"request":request}).__dict__)
        return {"request":request,"mode":ctx.mode,"results":results,"verified":all(r["verified"] for r in results) if results else False}
