#!/usr/bin/env python3
"""SparkBot conversational standalone launcher. Python standard library only."""
from __future__ import annotations
import json, os, sqlite3, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from sparkbot.ai import AIClient
from sparkbot.agent import SparkAgent
from sparkbot.orchestrator import Orchestrator
from sparkbot.engine import ExecutionContext
from sparkbot.skills.models import Permission
from sparkbot.db import init_db, fetch_all

ROOT=Path(__file__).resolve().parent
STATIC=ROOT/"static"
PORT=int(os.getenv("SPARKBOT_PORT","8000"))
HOST=os.getenv("SPARKBOT_HOST","0.0.0.0")
ai=AIClient()
agent=SparkAgent()
orchestrator=Orchestrator()
init_db()

SYSTEM="""You are SparkBot, an autonomous marketing, sales and growth operations agent.
Speak naturally like a strong ChatGPT-style assistant, in the user's language.
You may plan, reason, explain, research through connected tools when available, and execute
authorized operations. Never claim an external action happened unless a tool actually did it.
When a request can be handled internally, do it. For risky external actions, explain the
approval needed. Keep the user updated with concise progress and final verification.
"""

def chat(messages):
    clean=[{"role":"system","content":SYSTEM}]+[m for m in messages if isinstance(m,dict) and m.get("role") in {"user","assistant","system"}]
    user=next((m.get("content","") for m in reversed(clean) if m.get("role")=="user"),"")
    plan=orchestrator.plan(user) if user else {"skills":[],"count":0}
    agent_result=agent.run_command(user) if user else {}
    events=[]
    if user:
        events.append({"type":"thinking","text":"Entendi a missão e estou selecionando as capacidades mais relevantes."})
        events.append({"type":"plan","text":f"Encontrei {plan['count']} capacidades candidatas."})
        ctx=ExecutionContext(actor="chat",mode="DRY_RUN",permissions={Permission.READ},data={})
        results=[]
        for skill in plan["skills"][:5]:
            r=orchestrator.executor.execute(skill["id"],ctx,{"request":user})
            results.append(r.__dict__)
            events.append({"type":"execution","skill_id":skill["id"],"skill":skill["name"],"status":r.status,"verified":r.verified})
        events.append({"type":"verification","text":"As etapas internas foram verificadas em DRY_RUN; nenhuma ação externa foi inventada."})
    else: results=[]
    context_message={"role":"system","content":"Execution context: "+json.dumps({"plan":plan,"agent_result":agent_result,"results":results},ensure_ascii=False)}
    response=ai.chat(clean+[context_message])
    return {"reply":response.content,"provider":response.provider,"model":response.model,"latency_ms":response.latency_ms,"ai_fallback":response.fallback,"plan":plan,"agent_result":agent_result,"results":results,"events":events}

class H(BaseHTTPRequestHandler):
    def send(self,data,code=200,ctype="application/json"):
        b=json.dumps(data,ensure_ascii=False).encode() if isinstance(data,(dict,list)) else data
        self.send_response(code); self.send_header("Content-Type",ctype+"; charset=utf-8"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        p=self.path.split("?",1)[0]
        if p=="/health": return self.send({"status":"ok","service":"sparkbot","standalone":True,"chat":True})
        if p=="/api/ai/status": return self.send(ai.status())
        if p=="/api/skills": return self.send({"count":len(orchestrator.registry.all())})
        if p=="/api/snapshot":
            return self.send({"goals":agent.snapshot()["goals"],"tasks":agent.snapshot()["tasks"],"activity":agent.snapshot()["activity"],"browser_events":fetch_all("SELECT * FROM browser_events ORDER BY id DESC LIMIT 100"),"ai":ai.status(),"skills":len(orchestrator.registry.all())})
        if p in ("/","/index.html"):
            return self.send((STATIC/"index.html").read_bytes(),"200","text/html")
        if p.startswith("/static/"):
            f=(ROOT/p.lstrip("/")).resolve()
            if f.is_file() and str(f).startswith(str(STATIC.resolve())): return self.send(f.read_bytes(),200,"text/css" if f.suffix==".css" else "application/javascript")
        return self.send({"error":"not found"},404)
    def do_POST(self):
        try:data=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))) or b"{}")
        except Exception:return self.send({"error":"invalid JSON"},400)
        p=self.path.split("?",1)[0]
        if p=="/api/chat":
            messages=data.get("messages",[])
            if not isinstance(messages,list):return self.send({"error":"messages must be a list"},400)
            return self.send(chat(messages))
        if p=="/api/browser/events":
            action=data.get("action")
            if not isinstance(action,str) or not action.strip():return self.send({"error":"action is required"},400)
            from sparkbot.browser_monitor import BrowserMonitor
            return self.send(BrowserMonitor().record(action,url=str(data.get("url","")),target=str(data.get("target","")),status=str(data.get("status","observed")),details=data.get("details") if isinstance(data.get("details"),dict) else {}))
        return self.send({"error":"not found"},404)
    def log_message(self,fmt,*args): print("[SparkBot]",fmt%args)

if __name__=="__main__":
    print(f"SparkBot Command Center: http://127.0.0.1:{PORT}")
    print("NVIDIA:", "ready" if ai.status()["configured"] else "configure NVIDIA_API_KEY")
    ThreadingHTTPServer((HOST,PORT),H).serve_forever()
