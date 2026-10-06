from __future__ import annotations
import os, secrets
from pathlib import Path
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .agent import SparkAgent
from .db import execute, fetch_all, fetch_one, init_db
from .models import CommandRequest, GoalCreate, TaskCreate, TaskStatusUpdate, SkillRouteRequest, SkillExecuteRequest
from .orchestrator import Orchestrator
from .engine import ExecutionContext
from .skills.models import Permission
load_dotenv(); init_db()
app=FastAPI(title="SparkBot",version="0.2.0"); agent=SparkAgent(); orchestrator=Orchestrator()
static_dir=Path(__file__).resolve().parent.parent/"static"; app.mount("/static",StaticFiles(directory=static_dir),name="static")
API_KEY=os.getenv("SPARKBOT_API_KEY",""); ALLOW_INSECURE_LOCAL=os.getenv("SPARKBOT_ALLOW_INSECURE_LOCAL","false").lower()=="true"
def require_auth(authorization:str|None=Header(default=None))->str:
 if not API_KEY:
  if ALLOW_INSECURE_LOCAL:return "local-dev"
  raise HTTPException(503,"SPARKBOT_API_KEY is not configured")
 if not authorization or not secrets.compare_digest(authorization,f"Bearer {API_KEY}"):raise HTTPException(401,"Unauthorized")
 return "api-key"
@app.get("/")
def index():return FileResponse(static_dir/"index.html")
@app.get("/health")
def health():return {"status":"ok","service":"sparkbot","version":"0.2.0","skills":len(orchestrator.registry.all())}
@app.get("/api/snapshot")
def snapshot(_:str=Depends(require_auth)):return agent.snapshot()
@app.get("/api/skills")
def skills(_:str=Depends(require_auth)):return {"count":len(orchestrator.registry.all()),"skills":[s.to_dict() for s in orchestrator.registry.all()]}
@app.post("/api/skills/route")
def route(payload:SkillRouteRequest,_:str=Depends(require_auth)):return orchestrator.plan(payload.request)
@app.post("/api/skills/execute")
def execute_skill(payload:SkillExecuteRequest,actor:str=Depends(require_auth)):
 try:perms={Permission(x) for x in payload.permissions}
 except ValueError as e:raise HTTPException(400,f"invalid permission: {e}")
 ctx=ExecutionContext(actor=actor,mode=payload.mode,permissions=perms,data={"human_approved":payload.human_approved})
 result=orchestrator.executor.execute(payload.skill_id,ctx,payload.payload)
 execute("INSERT INTO activity_logs(event_type,message,metadata) VALUES (?,?,?)",("SKILL_EXECUTION",f"{payload.skill_id}:{result.status}",str(result.__dict__)))
 return result.__dict__
@app.post("/api/commands")
def command(payload:CommandRequest,actor:str=Depends(require_auth)):
 result=agent.run_command(payload.command); result["skill_plan"]=orchestrator.plan(payload.command); execute("INSERT INTO audit_logs(action,actor,target,result) VALUES (?,?,?,?)",("command",actor,"agent","plan_created")); return result
@app.post("/api/goals")
def create_goal(payload:GoalCreate,actor:str=Depends(require_auth)):
 goal_id=execute("INSERT INTO goals(title,description,kpi) VALUES (?,?,?)",(payload.title,payload.description,payload.kpi)); execute("INSERT INTO audit_logs(action,actor,target,result) VALUES (?,?,?,?)",("create_goal",actor,str(goal_id),"created")); return fetch_one("SELECT * FROM goals WHERE id=?",(goal_id,))
@app.get("/api/goals")
def goals(_:str=Depends(require_auth)):return fetch_all("SELECT * FROM goals ORDER BY id DESC")
@app.post("/api/tasks")
def create_task(payload:TaskCreate,actor:str=Depends(require_auth)):
 task_id=execute("INSERT INTO tasks(goal_id,title,description,priority,tool,expected_output) VALUES (?,?,?,?,?,?)",(payload.goal_id,payload.title,payload.description,payload.priority,payload.tool,payload.expected_output)); execute("INSERT INTO audit_logs(action,actor,target,result) VALUES (?,?,?,?)",("create_task",actor,str(task_id),"created")); return fetch_one("SELECT * FROM tasks WHERE id=?",(task_id,))
@app.patch("/api/tasks/{task_id}")
def update_task(task_id:int,payload:TaskStatusUpdate,actor:str=Depends(require_auth)):
 task=fetch_one("SELECT * FROM tasks WHERE id=?",(task_id,))
 if not task:raise HTTPException(404,"Task not found")
 execute("UPDATE tasks SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(payload.status,task_id)); execute("INSERT INTO audit_logs(action,actor,target,result) VALUES (?,?,?,?)",("update_task",actor,str(task_id),payload.status)); return fetch_one("SELECT * FROM tasks WHERE id=?",(task_id,))
@app.get("/api/audit")
def audit(_:str=Depends(require_auth)):return fetch_all("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100")
