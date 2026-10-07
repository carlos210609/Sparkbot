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
import re

from sparkbot.ai import AIClient
from sparkbot.agent import SparkAgent
from sparkbot.agent_mesh import AgentMesh
from sparkbot.cognitive import CognitiveEngine
from sparkbot.db import execute, fetch_all, fetch_one, init_db
from sparkbot.kernel import SparkKernel
from sparkbot.mission_control import MissionRunner, MissionStore
from sparkbot.runtime import manifest as runtime_manifest
from sparkbot.policy import validate_request
from sparkbot.browser_agent import BrowserAgent
from sparkbot.social import SocialController, catalog as social_catalog

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
PORT = int(os.getenv("SPARKBOT_PORT", "8000"))
HOST = os.getenv("SPARKBOT_HOST", "127.0.0.1")

ai = AIClient()
legacy_agent = SparkAgent()
cognitive = CognitiveEngine()
kernel = SparkKernel()
mesh = AgentMesh()
mission_store = MissionStore()
browser = BrowserAgent()
social = SocialController(browser)
init_db()


WEB_TOOLS = [
    {"type": "function", "function": {
        "name": "web_search", "description": "Search the public web for current information and return source URLs.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "web_fetch", "description": "Fetch a public HTTP/HTTPS web page for research or verification.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "max_chars": {"type": "integer", "minimum": 1000, "maximum": 12000}}, "required": ["url"]}}},
]


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
    {"type": "function", "function": {
        "name": "browser_elements", "description": "Inspect interactive elements on the current page before choosing a selector.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 150}}, "required": []}}},
    {"type": "function", "function": {
        "name": "browser_upload", "description": "Upload a local media file through a visible file input.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "social_catalog", "description": "List supported social and content platforms.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "social_open", "description": "Open the official home or signup page for a supported platform. Security verification remains human.",
        "parameters": {"type": "object", "properties": {"platform": {"type": "string"}, "purpose": {"type": "string", "enum": ["home","signup"]}}, "required": ["platform"]}}},
    {"type": "function", "function": {
        "name": "social_prepare_post", "description": "Prepare a social post draft without publishing it.",
        "parameters": {"type": "object", "properties": {"platform": {"type": "string"}, "caption": {"type": "string"}, "media_path": {"type": "string"}}, "required": ["platform"]}}},
    {"type": "function", "function": {
        "name": "social_publish", "description": "Stage a real social publication for explicit human approval.",
        "parameters": {"type": "object", "properties": {"platform": {"type": "string"}, "caption": {"type": "string"}, "media_path": {"type": "string"}}, "required": ["platform","caption"]}}},

]

def _create_approval(action: str, args: dict, reason: str) -> str:
    import uuid
    approval_id = uuid.uuid4().hex
    value = json.dumps({"action": action, "args": args, "reason": reason, "status": "PENDING"}, ensure_ascii=False)
    execute("INSERT INTO memories(kind,key,value,importance) VALUES (?,?,?,?)",
            ("approval", approval_id, value, 1.0))
    return approval_id

def _learn(subject: str, action: str, result: dict) -> None:
    success = bool(result.get("ok"))
    verified = bool(result.get("verified"))
    score = 0.55 * int(success) + 0.35 * int(verified)
    kernel.memory.remember("learning", f"{subject}:{action}",
                           {"success": success, "verified": verified, "score": score},
                           score)

def _public_web_search(query: str, limit: int = 8) -> dict:
    query = str(query).strip()
    if not query:
        return {"ok": False, "error": "query is required"}
    limit = max(1, min(int(limit), 10))
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    request = urllib.request.Request(url, headers={"User-Agent": "SparkBot/1.0", "Accept": "text/html"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(1_500_000)
            charset = response.headers.get_content_charset() or "utf-8"
            html = raw.decode(charset, errors="replace")
        results = []
        for match in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.I | re.S):
            href = re.sub(r"&amp;", "&", match.group(1))
            title = re.sub(r"<[^>]+>", " ", match.group(2))
            title = re.sub(r"\s+", " ", title).strip()
            if href.startswith("//"): href = "https:" + href
            if href.startswith("http"): results.append({"title": title, "url": href})
            if len(results) >= limit: break
        return {"ok": True, "query": query, "results": results, "count": len(results)}
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return {"ok": False, "error": f"Web search failed: {type(exc).__name__}: {exc}"}


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


def browser_autonomy_enabled() -> bool:
    return os.getenv("SPARKBOT_BROWSER_AUTONOMY", "1").strip().lower() in {"1", "true", "yes", "on"}

def execute_tool(name: str, args: dict) -> dict:
    if name == "web_search":
        return _public_web_search(str(args.get("query", "")), int(args.get("limit", 8)))
    if name == "web_fetch":
        return _public_web_fetch(str(args.get("url", "")), int(args.get("max_chars", 8000)))
    if name == "browser_navigate":
        result = browser.navigate(str(args.get("url", ""))); _learn("browser","navigate",result); return result
    if name == "browser_click":
        # Browser autonomy is a persistent user-granted capability. Do not create
        # per-click conversational approval loops. Security checkpoints such as
        # CAPTCHA/OTP/2FA remain enforced by BrowserAgent.
        result = browser.click(
            str(args.get("selector", "")),
            confirmed=browser_autonomy_enabled(),
        )
        _learn("browser","click",result)
        return result
    if name == "browser_fill":
        result = browser.fill(str(args.get("selector", "")), str(args.get("value", "")), confirmed=browser_autonomy_enabled())
        _learn("browser","fill",result); return result
    if name == "browser_text":
        result = browser.text(int(args.get("max_chars", 12000))); _learn("browser","text",result); return result
    if name == "browser_screenshot":
        result = browser.screenshot(); _learn("browser","screenshot",result); return result
    if name == "browser_elements":
        result = browser.elements(int(args.get("limit", 80))); _learn("browser","elements",result); return result
    if name == "browser_upload":
        result = browser.upload(str(args.get("path", ""))); _learn("browser","upload",result); return result
    if name == "social_catalog":
        return {"ok": True, "platforms": social_catalog()}
    if name == "social_open":
        result = social.open(str(args.get("platform","")), str(args.get("purpose","home"))); _learn("social","open",result); return result
    if name == "social_prepare_post":
        result = social.prepare_post(str(args.get("platform","")), str(args.get("caption","")), str(args.get("media_path",""))); _learn("social","draft",result); return result
    if name == "social_publish":
        payload = {"platform":str(args.get("platform","")), "caption":str(args.get("caption","")), "media_path":str(args.get("media_path",""))}
        aid = _create_approval("social_publish", payload, "External publication requires explicit approval.")
        return {"ok": False, "approval_required": True, "approval_id": aid,
                "message": "Publication staged. Approve it from the approval center."}
    return {"ok": False, "error": f"Unknown tool: {name}"}



kernel.tools.register("web_search", execute_tool, risk="low", permissions=("READ",))
kernel.tools.register("web_fetch", execute_tool, risk="low", permissions=("READ",))
kernel.tools.register("browser_navigate", execute_tool, risk="medium", permissions=("READ",))
kernel.tools.register("browser_click", execute_tool, risk="medium", permissions=("WRITE",))
kernel.tools.register("browser_fill", execute_tool, risk="high", permissions=("WRITE",))
kernel.tools.register("browser_text", execute_tool, risk="low", permissions=("READ",))
kernel.tools.register("browser_screenshot", execute_tool, risk="low", permissions=("READ",))
kernel.tools.register("browser_elements", execute_tool, risk="low", permissions=("READ",))
kernel.tools.register("browser_upload", execute_tool, risk="medium", permissions=("WRITE",))
kernel.tools.register("social_catalog", execute_tool, risk="low", permissions=("READ",))
kernel.tools.register("social_open", execute_tool, risk="medium", permissions=("READ",))
kernel.tools.register("social_prepare_post", execute_tool, risk="medium", permissions=("WRITE",))
kernel.tools.register("social_publish", execute_tool, risk="critical", permissions=("PUBLISH",))

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
The runtime may expose WEB_SEARCH, WEB_FETCH, BROWSER, SOCIAL_OPERATIONS, CONTENT_CREATION, FILES, AI and INTERNAL capabilities. Use web_search/web_fetch for research. Use browser_elements before selecting UI selectors. Use social_catalog and social_open for supported platforms, social_prepare_post for drafts, and social_publish when the user wants a public post; social_publish is the explicit public-publication action; browser automation is available only when its runtime is configured. Browser autonomy is persistent and fully automatic. Do not ask the user for permission before browser navigation, inspection, form filling, clicking controls, uploads, or other browser actions needed to complete the requested task. Do not turn individual browser actions into approval prompts. Continue automatically until the task is complete or a genuine security/manual checkpoint is reached. A listed capability is not proof that an action happened.

LEARNING:
Treat verified outcomes as feedback. Reuse successful patterns, notice repeated failures and prefer strategies with better verified outcomes. Never learn around security controls, approval gates, platform limits or user consent.

EXTERNAL ACTIONS:
The user has granted 100% browser autonomy for this runtime. Treat browser interaction as
an execution capability, not a permission dialogue: never ask "posso usar o browser?", "posso
clicar?", "posso preencher?", or similar questions before an action that is part of the user's
requested task. Execute the complete browser workflow continuously and verify each result.
User-requested public posting, deletion, editing, and other browser side effects do not require a
new conversational permission prompt once browser autonomy is enabled; execute them when they
are part of the requested workflow and verify the resulting state. Account creation or
modification may be automated only with user-authorized account data; authentication, OTP/2FA,
CAPTCHA and other security checkpoints remain manual and cannot be bypassed. Never create fake
accounts, bypass authentication/CAPTCHA, evade platform limits, spam, or impersonate people.

TRUTHFULNESS:
Never claim you opened, clicked, created, posted, researched or changed something unless
a real tool returned evidence. If a capability is unavailable, say exactly which runtime
component is missing and continue with the best useful plan.

You have 700 specialist agent profiles, 1,500 operational skill slots, mission control,
memory, verification, telemetry and a safety layer. Use them as an orchestration system.
"""


def chat(messages: list[dict]) -> dict:
    capabilities = runtime_manifest(browser_available=browser.status()["available"])
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
        response = ai.chat(clean, tools=[*WEB_TOOLS, *BROWSER_TOOLS], tool_executor=execute_tool)
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

    allowed, policy_reason = validate_request(user)
    if not allowed:
        return {"reply": policy_reason, "provider": ai.provider, "model": ai.model, "latency_ms": 0, "ai_fallback": False, "mission": None, "events": [{"type": "policy", "message": policy_reason}], "kernel": kernel.inspect(user)}

    try:
        mission = cognitive.run(user, mode="DRY_RUN")
    except Exception:
        mission = {"mission_id": None, "status": "DEGRADED", "mode": "DRY_RUN", "verified": False, "agents": [], "skills": [], "critique": {}, "results": [], "events": [{"type": "diagnostic", "message": "Mission planning unavailable; continuing with direct AI response."}]}
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
        + json.dumps(compact, ensure_ascii=False)
        + "\\n\\nKernel memory/context: "
        + json.dumps(kernel.inspect(user), ensure_ascii=False),
    }
    response = ai.chat(clean + [context_message], tools=[*WEB_TOOLS, *BROWSER_TOOLS], tool_executor=execute_tool)
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

        if path == "/api/diagnostics":
            checks = {}
            try:
                checks["database"] = {"ok": bool(fetch_all("SELECT 1 AS ok"))}
            except Exception as exc:
                checks["database"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            checks["nvidia"] = {"ok": ai.status()["configured"], "provider": ai.provider, "model": ai.model}
            checks["skills"] = {"ok": len(cognitive.registry.all()) == 1500, "count": len(cognitive.registry.all())}
            checks["agents"] = {"ok": mesh.stats()["total"] == 700, **mesh.stats()}
            checks["browser"] = browser.status()
            checks["runtime_tools"] = kernel.inspect("")["available_tools"]
            from sparkbot.m16_m150 import MilestoneRegistry
            milestone_count = len(MilestoneRegistry().all())
            checks["milestones"] = {"ok": milestone_count == 135, "m16_m150": milestone_count}
            failed = [name for name, value in checks.items() if isinstance(value, dict) and value.get("ok") is False]
            return self.send({"status": "FAILED" if failed else "READY", "failed": failed, "checks": checks})

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
            return self.send(runtime_manifest(browser_available=browser.status()["available"]))
        
        if path == "/api/milestones":
            from sparkbot.m16_m150 import MilestoneRegistry
            rows = MilestoneRegistry().all()
            return self.send({
                "count": len(rows),
                "milestones": [item.__dict__ for item in rows],
            })

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

        if path == "/api/social":
            return self.send({"platforms": social_catalog()})

        if path == "/api/approvals":
            rows = fetch_all("SELECT * FROM memories WHERE kind='approval' ORDER BY id DESC LIMIT 100")
            for row in rows:
                try: row["value"] = json.loads(row["value"])
                except Exception: pass
            return self.send({"approvals": rows})

        if path == "/api/learning":
            rows = fetch_all("SELECT * FROM memories WHERE kind='learning' ORDER BY id DESC LIMIT 200")
            for row in rows:
                try: row["value"] = json.loads(row["value"])
                except Exception: pass
            return self.send({"events": rows})

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
            return self.send({"missions": mission_store.all(50)})

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

        if path == "/api/browser/navigate":
            return self.send(browser.navigate(str(data.get("url", ""))))

        if path == "/api/browser/click":
            return self.send(browser.click(str(data.get("selector", ""))))

        if path == "/api/browser/fill":
            return self.send(browser.fill(str(data.get("selector", "")), str(data.get("value", ""))))

        if path == "/api/browser/text":
            return self.send(browser.text(int(data.get("max_chars", 12000))))

        if path == "/api/browser/screenshot":
            return self.send(browser.screenshot())

        if path == "/api/browser/elements":
            return self.send(browser.elements(int(data.get("limit", 80))))

        if path == "/api/browser/upload":
            return self.send(browser.upload(str(data.get("path", ""))))

        if path == "/api/social/open":
            return self.send(social.open(str(data.get("platform","")), str(data.get("purpose","home"))))

        if path == "/api/social/prepare-post":
            return self.send(social.prepare_post(str(data.get("platform","")), str(data.get("caption","")), str(data.get("media_path",""))))

        if path == "/api/approvals/approve":
            approval_id = str(data.get("id",""))
            row = fetch_one("SELECT * FROM memories WHERE kind='approval' AND key=?", (approval_id,))
            if not row: return self.send({"error":"approval not found"},404)
            approval = json.loads(row["value"])
            if approval.get("status") != "PENDING": return self.send({"approval":approval})
            action, args = approval.get("action"), approval.get("args") or {}
            if action == "social_publish":
                result = social.execute_post(args.get("platform",""), args.get("caption",""), args.get("media_path",""), publish=True)
            elif action == "browser_click":
                result = browser.click(args.get("selector",""), confirmed=True)
            else:
                result = {"ok":False,"error":"unsupported approval action"}
            approval["status"] = "EXECUTED" if result.get("ok") else "FAILED"
            execute("UPDATE memories SET value=?,updated_at=CURRENT_TIMESTAMP WHERE kind='approval' AND key=?",
                    (json.dumps(approval,ensure_ascii=False),approval_id))
            _learn("approval",action,result)
            return self.send({"approval":approval,"result":result})

        if path == "/api/approvals/reject":
            approval_id = str(data.get("id",""))
            row = fetch_one("SELECT * FROM memories WHERE kind='approval' AND key=?", (approval_id,))
            if not row: return self.send({"error":"approval not found"},404)
            approval=json.loads(row["value"]); approval["status"]="REJECTED"
            execute("UPDATE memories SET value=?,updated_at=CURRENT_TIMESTAMP WHERE kind='approval' AND key=?",
                    (json.dumps(approval,ensure_ascii=False),approval_id))
            return self.send({"approval":approval})

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
