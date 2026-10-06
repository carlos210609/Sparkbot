import os
import tempfile

DB_PATH = tempfile.NamedTemporaryFile(prefix="sparkbot-test-", suffix=".db", delete=False).name
os.environ["SPARKBOT_DB_PATH"] = DB_PATH
os.environ["SPARKBOT_ALLOW_INSECURE_LOCAL"] = "true"

from fastapi.testclient import TestClient
from sparkbot.app import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_command_creates_plan():
    response = client.post("/api/commands", json={"command": "Quero aumentar os leads do meu SaaS"})
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "SALES_GROWTH"
    assert body["goal_id"] > 0
    assert len(body["tasks"]) >= 3

def test_task_status_update():
    task = client.post("/api/tasks", json={"title": "Test task"}).json()
    response = client.patch(f"/api/tasks/{task['id']}", json={"status": "COMPLETED"})
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"
