#!/usr/bin/env python3
"""SparkBot Command Center — conversational autonomous agent launcher."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request

from sparkbot.ai import AIClient
from sparkbot.agent import SparkAgent
from sparkbot.agent_mesh import AgentMesh
from sparkbot.cognitive import CognitiveEngine
from sparkbot.db import fetch_all, init_db
from sparkbot.kernel import SparkKernel
from sparkbot.mission_control import MissionRunner, MissionStore
from sparkbot.runtime import manifest as runtime_manifest
from sparkbot.browser_monitor import BrowserMonitor
from sparkbot.browser_agent import BrowserAgent

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
PORT = int(os.getenv("SPARKBOT_PORT", "8000"))
HOST = os.getenv("SPARKBOT_HOST", "0.0.0.0")

ai = AIClient()
legacy_agent = SparkAgent()
cognitive = CognitiveEngine()
kernel = SparkKernel()
mesh = AgentMesh()
mission_store = MissionStore()
browser = BrowserAgent()
init_db()


WEB_TOOL = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": "Fetch a public HTTP/HTTPS web page for research or verification. Use this when current public internet information is needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Public http or https URL to retrieve."},
                "max_chars": {"type": "integer", "minimum": 1000, "maximum": 12000, "description": "Maximum text returned."},
            },
            "required": ["url"],
        },
    },
}


BROWSER_TOOLS = [
    {"type": "function", "function": {
        "name": "browser_navigate", "description": "Open a public web page in SparkBot's real browser session.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "browser_click", "description": "Click a visible page element with a selector.",
        "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    {"type": "function", "function": {
        "name": "browser_fill", "description": "Fill a visible form field. Never bypass CAPTCHA or authentication.",
        "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "value": {"type": "string"}}, "required": ["selector", "value"]}}},
    {"type": "function", "function": {
        "name": "browser_text", "description": "Read visible text from the current browser page.",
        "parameters": {"type": "object", "properties": {"max_chars": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "browser_screenshot", "description": "Capture the current browser page for verification.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]

def _public_web_fetch(url: str, max_chars: int = 8000) -> dict:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return {"ok": False, "error": "Only public HTTP/HTTPS URLs are allowed."}
    host = parsed.hostname
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return {"ok": False, "error": "Private or local network targets are blocked."}
    except OSError as exc:
        return {"ok": False, "error": f"DNS resolution failed: {exc}"}
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SparkBot/1.0 (public-web-research)", "Accept": "text/html,text/plain,application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(1_000_000)
            charset = response.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
            if "html" in (response.headers.get("Content-Type") or "").lower():
                import re
                text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
                text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
            return {"ok": True, "url": response.geturl(), "content_type": response.headers.get("Content-Type", ""), "text": text[:max(1000, min(int(max_chars), 12000))]}
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return {"ok": False, "error": f"Web fetch failed: {type(exc).__name__}: {exc}"}


def execute_tool(name: str, args: dict) -> dict:
    if name == "web_fetch":
        return _public_web_fetch(str(args.get("url", "")), int(args.get("max_chars", 8000)))
    if name == "browser_navigate":
        return browser.navigate(str(args.get("url", "")))
    if name == "browser_click":
        return browser.click(str(args.get("selector", "")))
    if name == "browser_fill":
        return browser.fill(str(args.get("selector", "")), str(args.get("value", "")))
    if name == "browser_text":
        return browser.text(int(args.get("max_chars", 12000)))
    if name == "browser_screenshot":
        return browser.screenshot()
    return {"ok": False, "error": f"Unknown tool: {name}"}



def run_background(request, emit, mission_id=None):
    emit("observe", "Kernel inspected the mission.", security=kernel.security.inspect(request))
    result = cognitive.run(request, mode="DRY_RUN", mission_id=mission_id)
    for event in result.get("events", []):
        emit(
            event.get("type", "event"),
            event.get("message", "progress"),
            **{k: v for k, v in event.items() if k not in {"type", "message"}},
        )
    return result


mission_runner = MissionRunner(mission_store, run_background)

SYSTEM = """You are SparkBot: an autonomous operations agent, not a passive chatbot.

IDENTITY:
You operate as the reasoning layer of a real agent runtime. Your job is to understand a
goal, inspect available capabilities, choose specialist agents and skills, execute
authorized tool actions, verify evidence, learn from outcomes, and report actual state.

AGENT LOOP:
OBSERVE -> UNDERSTAND -> PLAN -> SELECT AGENTS/SKILLS -> CHECK PERMISSIONS -> EXECUTE ->
VERIFY -> MEASURE -> LEARN -> REPORT -> NEXT ACTION.

TOOL AWARENESS:
The runtime may expose WEB_FETCH, BROWSER, FILES, AI and INTERNAL capabilities. WEB_FETCH
means public web retrieval. BROWSER means interactive browser automation only when its
availability is true. A listed capability is not proof that an action happened.

EXTERNAL ACTIONS:
You may propose and, when the runtime actually supports it, execute legitimate
user-authorized web/browser work. Account creation or modification uses the user's real
authorization/data and the approval gate. Never create fake accounts, bypass
authentication/CAPTCHA, evade platform limits, spam, or impersonate people.

TRUTHFULNESS:
Never claim you opened, clicked, created, posted, researched or changed something unless
a real tool returned evidence. If a capability is unavailable, say exactly which runtime
component is missing and continue with the best useful plan.

You have 700 specialist agent profiles, 1,500 operational skill slots, mission control,
memory, verification, telemetry and a safety layer. Use them as an orchestration system.
"""


def chat(messages: list[dict]) -> dict:
    capabilities = runtime_manifest(browser_available=browser.status()["started"])
    runtime_context = json.dumps(capabilities, ensure_ascii=False)
    clean = [{"role": "system", "content": SYSTEM + "\n\nRUNTIME CAPABILITIES:\n" + runtime_context}] + [
        m for m in messages
        if isinstance(m, dict)
        and m.get("role") in {"user", "assistant", "system"}
        and isinstance(m.get("content", ""), str)
    ]
    user = next(
        (m.get("content", "") for m in reversed(clean) if m.get("role") == "user"),
        "",
    )

    if not user:
        response = ai.chat(clean, tools=[WEB_TOOL, *BROWSER_TOOLS], tool_executor=execute_tool)
        return {
            "reply": response.content,
            "provider": response.provider,
            "model": response.model,
            "latency_ms": response.latency_ms,
            "ai_fallback": response.fallback,
            "mission": None,
            "events": [],
            "kernel": kernel.inspect(""),
        }

    mission = cognitive.run(user, mode="DRY_RUN")
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
            {
                "skill_id": r["skill_id"],
                "status": r["status"],
                "verified": r["verified"],
                "error": r["error"],
            }
            for r in mission["results"]
        ],
    }
    context_message = {
        "role": "system",
        "content": "Live mission state (do not invent beyond it): "
        + json.dumps(compact, ensure_ascii=False),
    }
    response = ai.chat(clean + [context_message], tools=[WEB_TOOL, *BROWSER_TOOLS], tool_executor=execute_tool)
    return {
        "reply": response.content,
        "provider": response.provider,
        "model": response.model,
        "latency_ms": response.latency_ms,
        "ai_fallback": response.fallback,
        "mission": mission,
        "events": mission["events"],
        "kernel": kernel.inspect(user),
    }


class H(BaseHTTPRequestHandler):
    def send(self, data, code=200, ctype="application/json"):
        body = (
            json.dumps(data, ensure_ascii=False).encode()
            if isinstance(data, (dict, list))
            else data
        )
        self.send_response(int(code))
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _query_param(self, name: str) -> str:
        from urllib.parse import parse_qs, urlsplit
        values = parse_qs(urlsplit(self.path).query).get(name, [])
        return values[0].strip() if values else ""

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/health":
            return self.send({
                "status": "ok",
                "service": "sparkbot",
                "chat": True,
                "agents": mesh.stats(),
                "skills": len(cognitive.registry.all()),
            })

        if path == "/api/ai/status":
            return self.send(ai.status())

        if path == "/api/runtime":
            return self.send(runtime_manifest(browser_available=False))

        if path == "/api/skills":
            skills = cognitive.registry.all()
            query = self._query_param("q")
            category = self._query_param("category")
            limit_raw = self._query_param("limit") or "1500"
            try:
                limit = min(max(int(limit_raw), 1), 1500)
            except ValueError:
                limit = 1500
            if query:
                skills = cognitive.registry.search(query, limit=limit)
            if category:
                skills = [s for s in skills if s.category.lower() == category.lower()]
            return self.send({
                "count": len(skills),
                "skills": [s.to_dict() for s in skills[:limit]],
            })

        if path.startswith("/api/skills/"):
            skill_id = path.rsplit("/", 1)[-1]
            skill = cognitive.registry.get(skill_id)
            if not skill:
                return self.send({"error": "skill not found"}, 404)
            return self.send({"skill": skill.to_dict()})

        if path == "/api/agents":
            return self.send(mesh.stats() | {"agents": [a.to_dict() for a in mesh.all()]})

        if path == "/api/browser":
            events = browser.monitor.recent(200)
            return self.send({"events": events, "count": len(events), "status": browser.status()})

        if path == "/api/browser/status":
            return self.send(browser.status())

        if path == "/api/browser/start":
            return self.send(browser.start())

        if path == "/api/browser/stop":
            return self.send(browser.stop())

        if path == "/api/activity":
            raw = self._query_param("limit") or "100"
            try:
                limit = min(max(int(raw), 1), 500)
            except ValueError:
                limit = 100
            return self.send({
                "activity": fetch_all(
                    "SELECT * FROM activity_logs ORDER BY id DESC LIMIT ?",
                    (limit,),
                ),
            })

        if path == "/api/missions":
            ids = list(mission_store._missions.keys())[-50:]
            return self.send({"missions": [mission_store.get(mid) for mid in ids]})

        if path.startswith("/api/missions/") and path.endswith("/events"):
            mission_id = path.split("/")[-2]
            return self.send({"events": mission_store.events(mission_id)})

        if path == "/api/snapshot":
            snap = legacy_agent.snapshot()
            return self.send({
                "goals": snap["goals"],
                "tasks": snap["tasks"],
                "activity": snap["activity"],
                "browser_events": fetch_all(
                    "SELECT * FROM browser_events ORDER BY id DESC LIMIT 100"
                ),
                "missions": fetch_all(
                    "SELECT * FROM missions ORDER BY created_at DESC LIMIT 20"
                ),
                "mission_events": fetch_all(
                    "SELECT * FROM mission_events ORDER BY id DESC LIMIT 50"
                ),
                "ai": ai.status(),
                "skills": len(cognitive.registry.all()),
                "agents": mesh.stats(),
            })

        if path.startswith("/api/missions/"):
            mission_id = path.rsplit("/", 1)[-1]
            return self.send({
                "mission": fetch_all(
                    "SELECT * FROM missions WHERE id = ?", (mission_id,)
                ),
                "events": fetch_all(
                    "SELECT * FROM mission_events WHERE mission_id = ? ORDER BY id",
                    (mission_id,),
                ),
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
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length) or b"{}")
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
            if bool(data.get("background", False)):
                mission_id = mission_runner.submit(request)
                return self.send({"mission_id": mission_id, "status": "QUEUED"})
            return self.send(
                cognitive.run(request, mode=str(data.get("mode", "DRY_RUN")))
            )

        if path == "/api/browser/events":
            action = data.get("action")
            if not isinstance(action, str) or not action.strip():
                return self.send({"error": "action is required"}, 400)
            from sparkbot.browser_monitor import BrowserMonitor

            return self.send(
                BrowserMonitor().record(
                    action,
                    url=str(data.get("url", "")),
                    target=str(data.get("target", "")),
                    status=str(data.get("status", "observed")),
                    details=data.get("details")
                    if isinstance(data.get("details"), dict)
                    else {},
                )
            )

        return self.send({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        print("[SparkBot]", fmt % args)


if __name__ == "__main__":
    print(f"SparkBot Command Center: http://127.0.0.1:{PORT}")
    print(f"Agents: {mesh.stats()['total']} | Skills: {len(cognitive.registry.all())}")
    print("NVIDIA:", "ready" if ai.status()["configured"] else "configure NVIDIA_API_KEY")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
