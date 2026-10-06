#!/usr/bin/env python3
import json,os,sqlite3,time,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).parent.resolve(); STATIC=ROOT/"static"; DB=Path(os.getenv("SPARKBOT_DB_PATH",str(ROOT/"data/sparkbot.db")))
KEY=os.getenv("NVIDIA_API_KEY",""); BASE=os.getenv("SPARKBOT_AI_BASE_URL","https://integrate.api.nvidia.com/v1").rstrip("/"); MODEL=os.getenv("SPARKBOT_NVIDIA_MODEL","auto")
PREFERRED=("deepseek-ai/deepseek-v3.2","qwen/qwen3.5-397b-a17b","meta/llama-3.3-70b-instruct","meta/llama-3.1-70b-instruct","meta/llama-3.1-8b-instruct")
def db():
 DB.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.executescript("CREATE TABLE IF NOT EXISTS browser_events(id INTEGER PRIMARY KEY,event_id TEXT UNIQUE,action TEXT,url TEXT,target TEXT,status TEXT,details TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS activity_logs(id INTEGER PRIMARY KEY,event_type TEXT,message TEXT,metadata TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);"); return c
def event(action,url="",target="",status="observed",details=None):
 e={"event_id":str(uuid.uuid4()),"action":action,"url":url,"target":target,"status":status,"details":details or {},"timestamp":time.time()}
 with db() as c:c.execute("INSERT INTO browser_events(event_id,action,url,target,status,details) VALUES(?,?,?,?,?,?)",(e["event_id"],action,url,target,status,json.dumps(e["details"])));c.execute("INSERT INTO activity_logs(event_type,message,metadata) VALUES(?,?,?)",("BROWSER_ACTION",action,json.dumps(e)))
 return e
def models():
 if not KEY:return []
 try:return [x["id"] for x in json.loads(urlopen(Request(BASE+"/models",headers={"Authorization":"Bearer "+KEY}),timeout=15).read()).get("data",[]) if isinstance(x,dict) and x.get("id")]
 except Exception:return []
def model():
 if MODEL!="auto":return MODEL
 a=models()
 return next((x for x in PREFERRED if x in a),a[0] if a else PREFERRED[-1])
def chat(messages):
 if not KEY:return {"ok":False,"error":"NVIDIA_API_KEY is not configured"}
 m=model(); body=json.dumps({"model":m,"messages":messages,"temperature":.2,"max_tokens":1024}).encode()
 try:
  d=json.loads(urlopen(Request(BASE+"/chat/completions",data=body,headers={"Authorization":"Bearer "+KEY,"Content-Type":"application/json"},method="POST"),timeout=45).read())
  return {"ok":True,"provider":"nvidia","model":m,"content":d["choices"][0]["message"]["content"]}
 except Exception as e:return {"ok":False,"provider":"nvidia","model":m,"error":f"{type(e).__name__}: {e}"}
def status():return {"provider":"nvidia","configured":bool(KEY),"model":MODEL,"selected_model":model() if KEY else MODEL,"standalone":True,"dependencies":"standard-library-only"}
class H(BaseHTTPRequestHandler):
 def out(self,x,code=200,typ="application/json"):
  b=json.dumps(x,ensure_ascii=False).encode() if typ=="application/json" else x;self.send_response(code);self.send_header("Content-Type",typ+"; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  p=self.path.split("?")[0]
  if p=="/health":return self.out({"status":"ok","service":"sparkbot","standalone":True})
  if p=="/api/ai/status":return self.out(status())
  if p=="/api/browser/events":
   with db() as c:r=[dict(x) for x in c.execute("SELECT * FROM browser_events ORDER BY id DESC LIMIT 100")]
   return self.out({"events":r})
  if p=="/api/snapshot":
   with db() as c:a=[dict(x) for x in c.execute("SELECT * FROM activity_logs ORDER BY id DESC LIMIT 50")]
   return self.out({"goals":[],"tasks":[],"activity":a,"browser_events":self.get_events(),"ai":status()})
  f=STATIC/"index.html" if p in ("/","/index.html") else (ROOT/p.lstrip("/") if p.startswith("/static/") else None)
  if f and f.is_file():return self.out(f.read_bytes(),typ="text/html" if f.suffix==".html" else "text/css")
  return self.out({"error":"not found"},404)
 def get_events(self):
  with db() as c:return [dict(x) for x in c.execute("SELECT * FROM browser_events ORDER BY id DESC LIMIT 100")]
 def do_POST(self):
  try:d=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))) or b"{}")
  except Exception:return self.out({"error":"invalid JSON"},400)
  p=self.path.split("?")[0]
  if p=="/api/ai/chat":return self.out(chat(d.get("messages",[])))
  if p=="/api/browser/events":
   if not isinstance(d.get("action"),str) or not d["action"].strip():return self.out({"error":"action is required"},400)
   return self.out(event(d["action"],str(d.get("url","")),str(d.get("target","")),str(d.get("status","observed")),d.get("details")))
  if p=="/api/commands":
   c=str(d.get("command","")).strip()
   if not c:return self.out({"error":"command is required"},400)
   event("agent_command",target=c,details={"source":"dashboard"});return self.out({"intent":"command_received","command":c})
  return self.out({"error":"not found"},404)
 def log_message(self,*a):pass
if __name__=="__main__":
 db().close();port=int(os.getenv("SPARKBOT_PORT","8000"));print(f"SparkBot: http://127.0.0.1:{port}");print("NVIDIA:","configured" if KEY else "NVIDIA_API_KEY not configured");ThreadingHTTPServer((os.getenv("SPARKBOT_HOST","0.0.0.0"),port),H).serve_forever()
