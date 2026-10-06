import os
from pathlib import Path
os.environ["SPARKBOT_DB_PATH"] = str(Path(__file__).parent / "test.db")
os.environ["SPARKBOT_ALLOW_INSECURE_LOCAL"] = "true"
from fastapi.testclient import TestClient
from sparkbot.app import app
client = TestClient(app)
def test_health():
 r=client.get("/health"); assert r.status_code==200; assert r.json()["status"]=="ok"
def test_command_creates_plan():
 r=client.post("/api/commands",json={"command":"Quero aumentar os leads do meu SaaS"})
 assert r.status_code==200; body=r.json(); assert body["intent"]=="SALES_GROWTH"; assert body["goal_id"]>0; assert len(body["tasks"])>=3
def test_task_status_update():
 task=client.post("/api/tasks",json={"title":"Test task"}).json()
 r=client.patch(f"/api/tasks/{task['id']}",json={"status":"COMPLETED"}); assert r.status_code==200; assert r.json()["status"]=="COMPLETED"
