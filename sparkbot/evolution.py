"""M3-M15 production architecture primitives.

These modules are deliberately provider/tool agnostic. They provide real local
contracts and deterministic behavior; integrations only report success when
they have evidence.
"""
from __future__ import annotations

import hashlib, json, math, time, uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


# M3 — Memory + context
@dataclass(frozen=True)
class MemoryRecord:
    kind: str
    key: str
    value: Any
    importance: float = 0.5
    source: str = "runtime"

class MemoryIndex:
    def __init__(self) -> None:
        self._items: list[MemoryRecord] = []
    def put(self, record: MemoryRecord) -> None:
        self._items = [x for x in self._items if not (x.kind == record.kind and x.key == record.key)]
        self._items.append(record)
    def search(self, query: str, limit: int = 10) -> list[MemoryRecord]:
        terms = {x for x in query.lower().split() if len(x) > 2}
        ranked = []
        for item in self._items:
            text = f"{item.key} {item.value}".lower()
            score = sum(term in text for term in terms) + item.importance
            if score:
                ranked.append((score, item))
        return [x for _, x in sorted(ranked, key=lambda p: p[0], reverse=True)[:limit]]

@dataclass(frozen=True)
class ContextItem:
    role: str
    content: str
    priority: float = 0.5
    trusted: bool = True

class ContextEngine:
    def assemble(self, system: str, task: str, memories: Iterable[MemoryRecord] = (), budget: int = 12000) -> list[ContextItem]:
        items = [ContextItem("system", system, 1.0), ContextItem("user", task, 1.0)]
        for m in memories:
            items.append(ContextItem("memory", f"[{m.source}] {m.key}: {m.value}", m.importance, m.source == "runtime"))
        items.sort(key=lambda x: x.priority, reverse=True)
        out, used = [], 0
        for item in items:
            if used + len(item.content) > budget:
                continue
            out.append(item); used += len(item.content)
        return out


# M4 — Provider routing/cache
@dataclass(frozen=True)
class ModelCandidate:
    provider: str
    model: str
    cost: float = 0.0
    latency_ms: float = 0.0
    context: int = 0
    tools: bool = False

class ModelRouter:
    def choose(self, candidates: Iterable[ModelCandidate], *, needs_tools=False, context_tokens=0) -> ModelCandidate:
        eligible = [c for c in candidates if c.context >= context_tokens and (not needs_tools or c.tools)]
        if not eligible:
            raise RuntimeError("no eligible model")
        return min(eligible, key=lambda c: (c.cost, c.latency_ms))


@dataclass
class ResponseCache:
    values: dict[str, Any] = field(default_factory=dict)
    def key(self, messages: list[dict[str, Any]], model: str) -> str:
        raw = json.dumps({"messages": messages, "model": model}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()
    def get(self, key: str) -> Any:
        return self.values.get(key)
    def put(self, key: str, value: Any) -> None:
        self.values[key] = value


# M5 — typed tools
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    permissions: tuple[str, ...] = ("READ",)
    risk: str = "low"
    cost: float = 0.0
    timeout_s: float = 30.0
    idempotent: bool = True

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolSpec, Callable[..., Any]]] = {}
    def register(self, spec: ToolSpec, handler: Callable[..., Any]) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = (spec, handler)
    def spec(self, name: str) -> ToolSpec:
        return self._tools[name][0]
    def invoke(self, name: str, **kwargs: Any) -> Any:
        return self._tools[name][1](**kwargs)
    def list(self) -> list[ToolSpec]:
        return [x[0] for x in self._tools.values()]


# M6 — layered verification
@dataclass(frozen=True)
class Verification:
    passed: bool
    level: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)

class VerificationEngine:
    def verify(self, result: Any, evidence: dict[str, Any] | None = None) -> Verification:
        evidence = evidence or {}
        if evidence.get("deterministic") is True:
            return Verification(True, "deterministic", "deterministic check passed", evidence)
        if evidence.get("executed") is True and evidence.get("observed") is True:
            return Verification(True, "execution", "independent execution evidence observed", evidence)
        if evidence.get("verified") is True:
            return Verification(True, "explicit", "explicit verification evidence supplied", evidence)
        return Verification(False, "none", "no sufficient verification evidence", evidence)


# M7 — adaptive planning/search
@dataclass(frozen=True)
class PlanCandidate:
    steps: tuple[str, ...]
    score: float

class PlanSearch:
    def rank(self, candidates: Iterable[PlanCandidate]) -> list[PlanCandidate]:
        return sorted(candidates, key=lambda x: (-x.score, len(x.steps)))

    def stagnating(self, histories: list[str], window: int = 3) -> bool:
        return len(histories) >= window and len(set(histories[-window:])) == 1


# M8 — browser/computer-use policy seam
class ComputerUseGuard:
    SECURITY_CHECKPOINTS = ("captcha", "otp", "2fa", "password", "recovery code")
    def inspect(self, action: str, target: str = "") -> dict[str, Any]:
        text = f"{action} {target}".lower()
        manual = any(x in text for x in self.SECURITY_CHECKPOINTS)
        return {"allowed": not manual, "manual_checkpoint": manual,
                "reason": "security checkpoint requires user interaction" if manual else "allowed"}


# M9 — multi-agent blackboard
@dataclass
class Blackboard:
    task_id: str
    facts: dict[str, Any] = field(default_factory=dict)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    def publish(self, agent: str, kind: str, value: Any) -> None:
        self.proposals.append({"agent": agent, "kind": kind, "value": value, "ts": time.time()})

class AgentCoordinator:
    def consensus(self, board: Blackboard) -> dict[str, Any]:
        if not board.proposals:
            return {"ready": False, "reason": "no proposals"}
        return {"ready": bool(board.evidence), "proposals": len(board.proposals), "evidence": len(board.evidence)}


# M10 — security/permissions
@dataclass(frozen=True)
class SecurityDecision:
    allowed: bool
    risk: str
    permissions: tuple[str, ...]
    reason: str

class PolicyEngine:
    RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    def decide(self, spec: ToolSpec, granted: set[str], *, dry_run: bool = False) -> SecurityDecision:
        missing = [p for p in spec.permissions if p not in granted]
        if missing:
            return SecurityDecision(False, spec.risk, tuple(missing), "missing permissions")
        if dry_run:
            return SecurityDecision(True, spec.risk, spec.permissions, "dry-run")
        if spec.risk == "critical":
            return SecurityDecision(False, spec.risk, spec.permissions, "critical action requires explicit policy approval")
        return SecurityDecision(True, spec.risk, spec.permissions, "allowed")


# M11 — evals/calibration
@dataclass(frozen=True)
class EvalCase:
    id: str
    expected: Any
    actual: Any
    confidence: float

class EvaluationEngine:
    def accuracy(self, cases: Iterable[EvalCase]) -> float:
        rows=list(cases)
        return sum(x.actual == x.expected for x in rows) / len(rows) if rows else 0.0
    def brier(self, cases: Iterable[EvalCase]) -> float:
        rows=list(cases)
        if not rows: return 0.0
        return sum((x.confidence - float(x.actual == x.expected)) ** 2 for x in rows) / len(rows)
    def report(self, cases: Iterable[EvalCase]) -> dict[str, float]:
        rows=list(cases)
        return {"accuracy": self.accuracy(rows), "brier": self.brier(rows), "count": float(len(rows))}


# M12 — outcome learning
@dataclass
class StrategyStat:
    attempts: int = 0
    successes: int = 0
    reward: float = 0.0

class OutcomeLearner:
    def __init__(self) -> None:
        self.stats: dict[str, StrategyStat] = {}
    def record(self, strategy: str, success: bool, reward: float = 0.0) -> None:
        s=self.stats.setdefault(strategy, StrategyStat())
        s.attempts += 1; s.successes += int(success); s.reward += reward
    def rank(self) -> list[tuple[str, float]]:
        return sorted(
            ((k, (v.successes / v.attempts if v.attempts else 0.0) + v.reward * 0.001) for k,v in self.stats.items()),
            key=lambda x: x[1], reverse=True,
        )


# M13 — observability
@dataclass(frozen=True)
class TraceEvent:
    run_id: str
    stage: str
    message: str
    ts: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

class Trace:
    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or uuid.uuid4().hex
        self.events: list[TraceEvent] = []
    def add(self, stage: str, message: str, **metadata: Any) -> TraceEvent:
        event=TraceEvent(self.run_id, stage, message, metadata=metadata)
        self.events.append(event); return event
    def export(self) -> list[dict[str, Any]]:
        return [e.__dict__ for e in self.events]


# M14 — gateway/session API contracts
@dataclass(frozen=True)
class Session:
    id: str
    user_id: str
    created_at: float = field(default_factory=time.time)

class RateLimiter:
    def __init__(self, limit: int = 60) -> None:
        self.limit=limit; self._counts: dict[str, int] = {}
    def allow(self, key: str) -> bool:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key] <= self.limit
    def reset(self, key: str) -> None:
        self._counts.pop(key, None)


# M15 — production readiness gates
@dataclass(frozen=True)
class ReadinessReport:
    checks: dict[str, bool]
    @property
    def ready(self) -> bool:
        return bool(self.checks) and all(self.checks.values())

def readiness(**checks: bool) -> ReadinessReport:
    return ReadinessReport(dict(checks))
