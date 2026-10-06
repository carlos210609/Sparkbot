#!/usr/bin/env python3
"""SparkBot Command Center — conversational autonomous agent launcher."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sparkbot.ai import AIClient
from sparkbot.agent import SparkAgent
from sparkbot.agent_mesh import AgentMesh
from sparkbot.cognitive import CognitiveEngine\nfrom sparkbot.kernel import SparkKernel\nfrom sparkbot.mission_control import MissionStore, MissionRunner
from sparkbot.db import fetch_all, init_db

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
PORT = int(os.getenv("SPARKBOT_PORT", "8000"))
HOST = os.getenv("SPARKBOT_HOST", "0.0.0.0")

ai = AIClient()
legacy_agent = SparkAgent()
cognitive = CognitiveEngine()
mesh = AgentMesh()
init_db()\n\ndef run_background(request, emit):\n    emit("observe", "Kernel inspected the mission.", security=kernel.security.inspect(request))\n    result = cognitive.run(request, mode="DRY_RUN")\n    for event in result.get("events", []):\n        emit(event.get("type", "event"), event.get("message", "progress"), **{k:v for k,v in event.items() if k not in {"type","message"}})\n    return result\n\nmission_runner = MissionRunner(mission_store, run_background)

SYSTEM = """You are SparkBot, a high-end autonomous operations intelligence.
Speak naturally, clearly and use the user's language. Behave like a strong ChatGPT-style
assistant: understand the goal, reason about trade-offs, ask only necessary questions,
plan work, execute authorized operations, verify results and report progress.
Never claim an external action happened unless a real tool actually performed and verified it.
You have specialist agents, operational skills, memory and a safety/permission layer.
When execution is blocked or only simulated, say so explicitly. Do not fabricate APIs,
accounts, traffic, followers, revenue, research results or tool actions.
"""

def chat(messages: list[dict]) -> dict:
    clean = [{"role": "system", "content": SYSTEM}] + [
        m for m in messages
        if isinstance(m, dict) and m.get("role") in {"user", "assistant", "system"}
        and isinstance(m.get("content", ""), str)
    ]
    user = next((m.get("content", "") for m in reversed(clean) if m.get("role") == "user"), "")
    if not user:
        response = ai.chat(clean)
        return {"reply": response.content, "provider": response.provider, "model": response.model,
                "latency_ms": response.latency_ms, "ai_fallback": response.fallback,
                "mission": None, "events": [], "kernel": kernel.inspect("")}

    mission = cognitive.run(user, mode="DRY_RUN")
    events = mission["events"]
    # Keep the model context compact while preserving the complete mission in the API response.
    compact = {
        "mission_id": mission["mission_id"],
        "status": mission["status"],
        "mode": mission["mode"],
        "verified": mission["verified"],
        "selected_agents": [
            {"id": a["id"], "name": a["name"], "role": a["role"], "domain": a["domain"]}
            for a in mission["agents"]
        ],
        "selected_skills": [
            {"id": s["id"], "name": s["name"], "category": s["category"]}
            for s in mission["skills"]
        ],
        "critique": mission["critique"],
        "results": [
            {"skill_id": r["skill_id"], "status": r["status"], "verified": r["verified"], "error": r["error"]}
            for r in mission["results"]
        ],
    }
    context_message = {
        "role": "system",
        "content": "Live mission state (do not invent beyond it): " + json.dumps(compact, ensure_ascii=False),
    }
    response = ai.chat(clean + [context_message])
    return {
        "reply": response.content,
        "provider": response.provider,
        "model": response.model,
        "latency_ms": response.latency_ms,
        "ai_fallback": response.fallback,
        "mission": mission,
        "events": events,
    }

class H(BaseHTTPRequestHandler):
    def send(self, data, code=200, ctype="application/json"):
        body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, (dict, list)) else data
        self.send_response(int(code))
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            return self.send({"status": "ok", "service": "sparkbot", "chat": True, "agents": 700, "skills": 1500})
        if path == "/api/ai/status":
            return self.send(ai.status())
        if path == "/api/skills":
            return self.send({"count": len(cognitive.registry.all())})
        if path == "/api/agents":
            return self.send(mesh.stats() | {"agents": [a.to_dict() for a in mesh.all()]})
        if path == "/api/missions":\n            return self.send({"missions": [mission_store.get(mid) for mid in list(mission_store._missions.keys())[-50:]]})\n        if path.startswith("/api/missions/") and path.endswith("/events"):\n            mission_id = path.split("/")[-2]\n            return self.send({"events": mission_store.events(mission_id)})\n        if path == "/api/snapshot":
            snap = legacy_agent.snapshot()
            return self.send({
                "goals": snap["goals"], "tasks": snap["tasks"], "activity": snap["activity"],
                "browser_events": fetch_all("SELECT * FROM browser_events ORDER BY id DESC LIMIT 100"),
                "missions": fetch_all("SELECT * FROM missions ORDER BY created_at DESC LIMIT 20"),
                "mission_events": fetch_all("SELECT * FROM mission_events ORDER BY id DESC LIMIT 50"),
                "ai": ai.status(), "skills": len(cognitive.registry.all()), "agents": mesh.stats(),
            })
        if path.startswith("/api/missions/"):
            mission_id = path.rsplit("/", 1)[-1]
            return self.send({
                "mission": fetch_all("SELECT * FROM missions WHERE id = ?", (mission_id,)),
                "events": fetch_all("SELECT * FROM mission_events WHERE mission_id = ? ORDER BY id", (mission_id,)),
            })
        if path in ("/", "/index.html"):
            return self.send((STATIC / "index.html").read_bytes(), 200, "text/html")
        if path.startswith("/static/"):
            file_path = (ROOT / path.lstrip("/")).resolve()
            static_root = STATIC.resolve()
            if file_path.is_file() and str(file_path).startswith(str(static_root)):
                ctype = "text/css" if file_path.suffix == ".css" else "application/javascript"
                return self.send(file_path.read_bytes(), 200, ctype)
        return self.send({"error": "not found"}, 404)

    def do_POST(self):
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        except Exception:
            return self.send({"error": "invalid JSON"}, 400)
        path = self.path.split("?", 1)[0]
        if path == "/api/chat":
            messages = data.get("messages", [])
            if not isinstance(messages, list):
                return self.send({"error": "messages must be a list"}, 400)
            return self.send(chat(messages))
        if path == "/api/mission":
            request = data.get("request", "")
            if not isinstance(request, str) or not request.strip():
                return self.send({"error": "request is required"}, 400)
            if bool(data.get("background", False)):\n                mid = mission_runner.submit(request)\n                return self.send({"mission_id": mid, "status": "QUEUED"})\n            return self.send(cognitive.run(request, mode=str(data.get("mode", "DRY_RUN"))))
        if path == "/api/browser/events":
            action = data.get("action")
            if not isinstance(action, str) or not action.strip():
                return self.send({"error": "action is required"}, 400)
            from sparkbot.browser_monitor import BrowserMonitor
            return self.send(BrowserMonitor().record(
                action, url=str(data.get("url", "")), target=str(data.get("target", "")),
                status=str(data.get("status", "observed")),
                details=data.get("details") if isinstance(data.get("details"), dict) else {},
            ))
        return self.send({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        print("[SparkBot]", fmt % args)

if __name__ == "__main__":
    print(f"SparkBot Command Center: http://127.0.0.1:{PORT}")
    print(f"Agents: {mesh.stats()['total']} | Skills: {len(cognitive.registry.all())}")
    print("NVIDIA:", "ready" if ai.status()["configured"] else "configure NVIDIA_API_KEY")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
