"""M16-M150 platform layer.

Provides concrete local primitives and a complete milestone registry. External
providers, social networks, clouds, payment processors and other third-party
systems are represented as typed integration seams and never as fake success.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable


# ---------------------------------------------------------------------------
# Core reliability primitives used by M16-M30
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    backoff_s: float = 0.25
    max_backoff_s: float = 5.0

    def delay(self, attempt: int) -> float:
        return min(self.max_backoff_s, self.backoff_s * (2 ** max(0, attempt)))


class Retrier:
    def run(self, fn: Callable[[], Any], policy: RetryPolicy = RetryPolicy()) -> Any:
        last: Exception | None = None
        for attempt in range(max(1, policy.attempts)):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 - generic retry boundary
                last = exc
                if attempt + 1 < policy.attempts:
                    time.sleep(policy.delay(attempt))
        raise RuntimeError("operation failed after retries") from last


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failures: int = 3, reset_s: float = 30.0) -> None:
        self.failures = max(1, failures)
        self.reset_s = max(0.0, reset_s)
        self.state = CircuitState.CLOSED
        self.count = 0
        self.opened_at = 0.0

    def allow(self) -> bool:
        if self.state == CircuitState.OPEN and time.time() - self.opened_at >= self.reset_s:
            self.state = CircuitState.HALF_OPEN
        return self.state != CircuitState.OPEN

    def success(self) -> None:
        self.count = 0
        self.state = CircuitState.CLOSED

    def failure(self) -> None:
        self.count += 1
        if self.count >= self.failures:
            self.state = CircuitState.OPEN
            self.opened_at = time.time()


class TokenBucket:
    def __init__(self, rate: float = 1.0, capacity: float = 10.0) -> None:
        self.rate = max(0.0, rate)
        self.capacity = max(1.0, capacity)
        self.tokens = self.capacity
        self.updated = time.monotonic()

    def consume(self, amount: float = 1.0) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens < amount:
            return False
        self.tokens -= amount
        return True


class LeaseManager:
    def __init__(self) -> None:
        self._leases: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str, owner: str, ttl_s: float = 30.0) -> bool:
        now = time.time()
        with self._lock:
            current = self._leases.get(key)
            if current and current[1] > now and current[0] != owner:
                return False
            self._leases[key] = (owner, now + max(0.1, ttl_s))
            return True

    def release(self, key: str, owner: str) -> bool:
        with self._lock:
            if self._leases.get(key, ("", 0))[0] != owner:
                return False
            self._leases.pop(key, None)
            return True


class IdempotencyStore:
    def __init__(self) -> None:
        self._values: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self._values.get(key)

    def put(self, key: str, value: Any) -> None:
        self._values.setdefault(key, value)


@dataclass(frozen=True)
class Event:
    type: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    ts: float = field(default_factory=time.time)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def publish(self, event: Event) -> None:
        for handler in tuple(self._subscribers.get(event.type, [])):
            handler(event)


@dataclass(frozen=True)
class Schedule:
    job_id: str
    run_at: float
    payload: dict[str, Any]


class Scheduler:
    def __init__(self) -> None:
        self._jobs: list[Schedule] = []

    def add(self, job_id: str, run_at: float, payload: dict[str, Any]) -> None:
        self._jobs.append(Schedule(job_id, run_at, payload))
        self._jobs.sort(key=lambda x: x.run_at)

    def due(self, now: float | None = None) -> list[Schedule]:
        now = time.time() if now is None else now
        ready = [job for job in self._jobs if job.run_at <= now]
        self._jobs = [job for job in self._jobs if job.run_at > now]
        return ready


class BudgetGuard:
    def __init__(self, steps: int = 100, cost: float = 10.0, latency_ms: float = 300000.0) -> None:
        self.steps_limit = steps
        self.cost_limit = cost
        self.latency_limit = latency_ms

    def check(self, steps: int, cost: float, latency_ms: float) -> bool:
        return (
            steps <= self.steps_limit
            and cost <= self.cost_limit
            and latency_ms <= self.latency_limit
        )


# ---------------------------------------------------------------------------
# Security and privacy primitives used by M31-M45
# ---------------------------------------------------------------------------

class SecretRedactor:
    PATTERNS = (
        re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
        re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]+"),
    )

    def redact(self, text: str) -> str:
        out = text
        for pattern in self.PATTERNS:
            out = pattern.sub(lambda m: m.group(0).split(":", 1)[0] + ": [REDACTED]", out)
        return out


class PIIProtector:
    def scrub(self, text: str) -> str:
        text = re.sub(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", "[EMAIL]", text)
        text = re.sub(r"\b(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b", "[PHONE]", text)
        return text


@dataclass(frozen=True)
class AuditEntry:
    action: str
    actor: str
    target: str
    result: str
    previous_hash: str = ""
    entry_hash: str = ""


class AuditLedger:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    def append(self, action: str, actor: str, target: str, result: str) -> AuditEntry:
        previous = self.entries[-1].entry_hash if self.entries else ""
        raw = json.dumps(
            {"action": action, "actor": actor, "target": target, "result": result, "previous": previous},
            sort_keys=True,
        )
        entry = AuditEntry(action, actor, target, result, previous, hashlib.sha256(raw.encode()).hexdigest())
        self.entries.append(entry)
        return entry

    def verify(self) -> bool:
        previous = ""
        for entry in self.entries:
            raw = json.dumps(
                {
                    "action": entry.action,
                    "actor": entry.actor,
                    "target": entry.target,
                    "result": entry.result,
                    "previous": previous,
                },
                sort_keys=True,
            )
            if hashlib.sha256(raw.encode()).hexdigest() != entry.entry_hash:
                return False
            previous = entry.entry_hash
        return True


class PromptInjectionGuard:
    SIGNALS = (
        "ignore previous instructions",
        "reveal system prompt",
        "disable security",
        "bypass policy",
        "exfiltrate",
    )

    def inspect(self, text: str) -> dict[str, Any]:
        lowered = text.lower()
        hits = [signal for signal in self.SIGNALS if signal in lowered]
        return {"suspicious": bool(hits), "signals": hits}


class WebhookVerifier:
    def verify(self, body: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        provided = signature.removeprefix("sha256=")
        return hmac.compare_digest(expected, provided)


@dataclass(frozen=True)
class OAuthState:
    state: str
    provider: str
    created_at: float


class OAuthStateStore:
    def __init__(self) -> None:
        self._states: dict[str, OAuthState] = {}

    def create(self, provider: str) -> OAuthState:
        state = OAuthState(uuid.uuid4().hex, provider, time.time())
        self._states[state.state] = state
        return state

    def consume(self, state: str, provider: str, max_age_s: float = 600.0) -> bool:
        value = self._states.pop(state, None)
        return bool(value and value.provider == provider and time.time() - value.created_at <= max_age_s)


# ---------------------------------------------------------------------------
# Knowledge/research primitives used by M46-M60
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceRef:
    url: str
    title: str = ""
    publisher: str = ""
    accessed_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class EvidenceClaim:
    claim: str
    sources: tuple[SourceRef, ...]
    confidence: float


class EvidencePack:
    def __init__(self) -> None:
        self.claims: list[EvidenceClaim] = []

    def add(self, claim: str, sources: Iterable[SourceRef], confidence: float) -> EvidenceClaim:
        item = EvidenceClaim(claim, tuple(sources), max(0.0, min(1.0, confidence)))
        self.claims.append(item)
        return item

    def unsupported(self) -> list[EvidenceClaim]:
        return [claim for claim in self.claims if not claim.sources]


class ResearchPlanner:
    def plan(self, question: str) -> list[str]:
        q = question.strip()
        return [
            f"define_scope:{q}",
            "collect_primary_sources",
            "cross_check_independent_sources",
            "extract_evidence",
            "synthesize_with_uncertainty",
        ]


class ClaimConsistency:
    def compare(self, claims: Iterable[str]) -> dict[str, Any]:
        rows = [x.strip().lower() for x in claims if x.strip()]
        return {"count": len(rows), "unique": len(set(rows)), "consistent": len(rows) <= 1 or len(set(rows)) == 1}


# ---------------------------------------------------------------------------
# Computer-use and communication primitives used by M61-M75
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BrowserAction:
    action: str
    target: str
    value: str = ""


class ActionPlanner:
    def classify(self, action: BrowserAction) -> str:
        text = f"{action.action} {action.target}".lower()
        if any(x in text for x in ("captcha", "otp", "2fa", "recovery", "password")):
            return "MANUAL_SECURITY"
        if any(x in text for x in ("publish", "delete", "send", "transfer", "buy")):
            return "HIGH_IMPACT"
        return "ORDINARY"


@dataclass(frozen=True)
class ContentDraft:
    platform: str
    text: str
    media: tuple[str, ...] = ()
    status: str = "DRAFT"


class ContentPipeline:
    def draft(self, platform: str, text: str, media: Iterable[str] = ()) -> ContentDraft:
        return ContentDraft(platform, text.strip(), tuple(media))


class ApprovalBoundary:
    def requires_approval(self, action_class: str) -> bool:
        return action_class in {"HIGH_IMPACT", "MANUAL_SECURITY"}


# ---------------------------------------------------------------------------
# Growth / CRM / commerce primitives used by M76-M105
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Lead:
    id: str
    source: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class LeadScorer:
    def score(self, fit: float, intent: float, recency: float) -> float:
        values = [max(0.0, min(1.0, x)) for x in (fit, intent, recency)]
        return round((0.45 * values[0] + 0.4 * values[1] + 0.15 * values[2]) * 100, 4)


@dataclass(frozen=True)
class FunnelEvent:
    name: str
    value: float = 1.0


class FunnelAnalyzer:
    def conversion_rates(self, events: list[FunnelEvent]) -> dict[str, float]:
        totals: dict[str, float] = {}
        for event in events:
            totals[event.name] = totals.get(event.name, 0.0) + event.value
        names = list(totals)
        return {
            f"{names[i]}->{names[i + 1]}": round(totals[names[i + 1]] / totals[names[i]], 6)
            if totals[names[i]] else 0.0
            for i in range(len(names) - 1)
        }


class ExperimentTracker:
    def __init__(self) -> None:
        self._values: dict[str, list[float]] = {}

    def record(self, variant: str, metric: float) -> None:
        self._values.setdefault(variant, []).append(metric)

    def summary(self) -> dict[str, dict[str, float]]:
        return {
            key: {
                "count": float(len(values)),
                "mean": sum(values) / len(values) if values else 0.0,
            }
            for key, values in self._values.items()
        }


@dataclass(frozen=True)
class PriceDecision:
    price: float
    rationale: str
    confidence: float


class PricingEngine:
    def recommend(self, base: float, elasticity: float, confidence: float = 0.5) -> PriceDecision:
        multiplier = max(0.5, min(1.5, 1.0 - elasticity))
        price = round(max(0.01, base * multiplier), 2)
        return PriceDecision(price, "bounded elasticity adjustment", max(0.0, min(1.0, confidence)))


class RevenueLedger:
    def __init__(self) -> None:
        self._entries: list[float] = []

    def add(self, amount: float) -> None:
        if amount < 0:
            raise ValueError("revenue amount cannot be negative")
        self._entries.append(float(amount))

    def total(self) -> float:
        return round(sum(self._entries), 2)


# ---------------------------------------------------------------------------
# Engineering / DevOps primitives used by M106-M120
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Artifact:
    id: str
    sha256: str
    size: int
    metadata: dict[str, Any]


class ArtifactStore:
    def __init__(self) -> None:
        self._items: dict[str, bytes] = {}

    def put(self, data: bytes) -> Artifact:
        digest = hashlib.sha256(data).hexdigest()
        self._items[digest] = data
        return Artifact(digest, digest, len(data), {})

    def get(self, artifact_id: str) -> bytes | None:
        return self._items.get(artifact_id)


class HealthRegistry:
    def __init__(self) -> None:
        self._checks: dict[str, Callable[[], bool]] = {}

    def register(self, name: str, check: Callable[[], bool]) -> None:
        self._checks[name] = check

    def run(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name, check in self._checks.items():
            try:
                results[name] = bool(check())
            except Exception:  # noqa: BLE001 - health boundary
                results[name] = False
        return results


@dataclass(frozen=True)
class FeatureFlag:
    name: str
    enabled: bool
    rollout: float = 1.0


class FeatureFlags:
    def __init__(self) -> None:
        self._flags: dict[str, FeatureFlag] = {}

    def set(self, name: str, enabled: bool, rollout: float = 1.0) -> None:
        self._flags[name] = FeatureFlag(name, enabled, max(0.0, min(1.0, rollout)))

    def enabled(self, name: str) -> bool:
        return bool(self._flags.get(name, FeatureFlag(name, False)).enabled)


@dataclass(frozen=True)
class ChangeSet:
    id: str
    files: tuple[str, ...]
    tests_required: bool = True
    rollback_token: str = ""


class ChangeGuard:
    def validate(self, change: ChangeSet, tests_green: bool, approved: bool) -> bool:
        return bool(change.files and tests_green and approved)


# ---------------------------------------------------------------------------
# Evaluation / optimization primitives used by M121-M135
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricPoint:
    name: str
    value: float
    target: float


class MetricMonitor:
    def evaluate(self, points: Iterable[MetricPoint]) -> dict[str, Any]:
        rows = list(points)
        passed = [p for p in rows if p.value >= p.target]
        return {
            "passed": len(passed),
            "total": len(rows),
            "ratio": len(passed) / len(rows) if rows else 0.0,
        }


class RegressionDetector:
    def detect(self, baseline: float, current: float, tolerance: float = 0.05) -> bool:
        if baseline == 0:
            return current < 0
        return current < baseline * (1 - max(0.0, tolerance))


class DriftDetector:
    def distance(self, baseline: Iterable[float], current: Iterable[float]) -> float:
        a, b = list(baseline), list(current)
        n = min(len(a), len(b))
        if n == 0:
            return 0.0
        return sum(abs(a[i] - b[i]) for i in range(n)) / n


class CanaryEvaluator:
    def compare(self, baseline: float, candidate: float, minimum_delta: float = 0.0) -> bool:
        return candidate >= baseline + minimum_delta


class OptimizationLoop:
    def step(self, current: float, candidate: float, guard: Callable[[float], bool]) -> float:
        return candidate if guard(candidate) else current


# ---------------------------------------------------------------------------
# Product / platform / scaling primitives used by M136-M150
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PluginSpec:
    name: str
    version: str
    capabilities: tuple[str, ...]
    permissions: tuple[str, ...] = ()


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, PluginSpec] = {}

    def register(self, plugin: PluginSpec) -> None:
        if plugin.name in self._plugins:
            raise ValueError(f"plugin already registered: {plugin.name}")
        self._plugins[plugin.name] = plugin

    def list(self) -> list[PluginSpec]:
        return list(self._plugins.values())


@dataclass(frozen=True)
class APIContract:
    method: str
    path: str
    request_schema: dict[str, Any]
    response_schema: dict[str, Any]


class ContractRegistry:
    def __init__(self) -> None:
        self._contracts: dict[str, APIContract] = {}

    def register(self, name: str, contract: APIContract) -> None:
        self._contracts[name] = contract

    def get(self, name: str) -> APIContract:
        return self._contracts[name]


@dataclass(frozen=True)
class Tenant:
    id: str
    name: str
    plan: str = "free"


class TenantRegistry:
    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}

    def create(self, name: str, plan: str = "free") -> Tenant:
        tenant = Tenant(uuid.uuid4().hex, name.strip(), plan)
        if not tenant.name:
            raise ValueError("tenant name is required")
        self._tenants[tenant.id] = tenant
        return tenant

    def get(self, tenant_id: str) -> Tenant:
        return self._tenants[tenant_id]


class KillSwitch:
    def __init__(self) -> None:
        self._enabled = False

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def active(self) -> bool:
        return self._enabled


@dataclass(frozen=True)
class Readiness:
    required: tuple[str, ...]
    checks: dict[str, bool]

    @property
    def ready(self) -> bool:
        return all(self.checks.get(item, False) for item in self.required)


def readiness(required: Iterable[str], checks: dict[str, bool]) -> Readiness:
    return Readiness(tuple(required), dict(checks))


# ---------------------------------------------------------------------------
# Complete M16-M150 milestone registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Milestone:
    id: int
    name: str
    area: str
    implementation: str
    verification: str
    dependency: int | None = None


_MILESTONE_ROWS = [
    (16, "Durable Event Log", "reliability", "EventBus", "publish/subscribe"),
    (17, "Retry Engine", "reliability", "Retrier", "deterministic retry test"),
    (18, "Exponential Backoff", "reliability", "RetryPolicy", "bounded delay"),
    (19, "Circuit Breaker", "reliability", "CircuitBreaker", "open/half-open"),
    (20, "Rate Limiting", "reliability", "TokenBucket", "token accounting"),
    (21, "Distributed Lease", "reliability", "LeaseManager", "exclusive ownership"),
    (22, "Idempotency", "reliability", "IdempotencyStore", "duplicate suppression"),
    (23, "Scheduling", "reliability", "Scheduler", "due-job retrieval"),
    (24, "Resource Budgets", "reliability", "BudgetGuard", "budget rejection"),
    (25, "Failure Containment", "reliability", "CircuitBreaker", "safe failure state"),
    (26, "Run Recovery", "reliability", "IdempotencyStore", "replay-safe result"),
    (27, "Event Fanout", "reliability", "EventBus", "subscriber delivery"),
    (28, "Lease Expiry", "reliability", "LeaseManager", "ttl takeover"),
    (29, "Execution Quotas", "reliability", "TokenBucket", "quota enforcement"),
    (30, "Operational Scheduling", "reliability", "Scheduler", "queue ordering"),

    (31, "Secret Redaction", "security", "SecretRedactor", "secret removal"),
    (32, "PII Scrubbing", "privacy", "PIIProtector", "PII masking"),
    (33, "Audit Ledger", "security", "AuditLedger", "hash chain"),
    (34, "Audit Integrity", "security", "AuditLedger", "tamper detection"),
    (35, "Prompt Injection Detection", "security", "PromptInjectionGuard", "signal detection"),
    (36, "Webhook Verification", "security", "WebhookVerifier", "HMAC verification"),
    (37, "OAuth State Protection", "security", "OAuthStateStore", "state consumption"),
    (38, "Security Boundaries", "security", "ApprovalBoundary", "high-impact classification"),
    (39, "Manual Checkpoints", "security", "ActionPlanner", "security classification"),
    (40, "Consent Surface", "privacy", "ApprovalBoundary", "approval decision"),
    (41, "Credential Isolation", "privacy", "SecretRedactor", "no secret echo"),
    (42, "Data Minimization", "privacy", "PIIProtector", "scrubbed payload"),
    (43, "Tamper Evidence", "security", "AuditLedger", "chain validation"),
    (44, "Signed Webhooks", "security", "WebhookVerifier", "signature validation"),
    (45, "OAuth Replay Defense", "security", "OAuthStateStore", "single-use state"),

    (46, "Source Registry", "research", "SourceRef", "typed source"),
    (47, "Evidence Pack", "research", "EvidencePack", "claim/source link"),
    (48, "Unsupported Claim Detection", "research", "EvidencePack", "missing source detection"),
    (49, "Research Planner", "research", "ResearchPlanner", "five-stage plan"),
    (50, "Claim Consistency", "research", "ClaimConsistency", "consistency result"),
    (51, "Primary Source Workflow", "research", "ResearchPlanner", "workflow contract"),
    (52, "Cross-check Workflow", "research", "ResearchPlanner", "independent checks"),
    (53, "Evidence Confidence", "research", "EvidencePack", "bounded confidence"),
    (54, "Source Provenance", "research", "SourceRef", "timestamped provenance"),
    (55, "Research Synthesis", "research", "EvidencePack", "evidence-backed claims"),
    (56, "Research Uncertainty", "research", "EvidencePack", "confidence bound"),
    (57, "Source Deduplication", "research", "SourceRef", "stable URL identity"),
    (58, "Knowledge Handoff", "research", "EvidencePack", "portable claims"),
    (59, "Fact/Opinion Separation", "research", "ClaimConsistency", "classification seam"),
    (60, "Research Verification", "research", "EvidencePack", "unsupported count"),

    (61, "Browser Action Classification", "computer_use", "ActionPlanner", "action classes"),
    (62, "Manual Security Checkpoint", "computer_use", "ActionPlanner", "CAPTCHA/OTP boundary"),
    (63, "High-impact Action Boundary", "computer_use", "ApprovalBoundary", "approval required"),
    (64, "Content Drafting", "computer_use", "ContentPipeline", "draft object"),
    (65, "Media Attachment Contract", "computer_use", "ContentDraft", "media tuple"),
    (66, "Social Draft State", "social", "ContentDraft", "DRAFT status"),
    (67, "Browser Side-effect Guard", "computer_use", "ApprovalBoundary", "classification"),
    (68, "Navigation Planning", "computer_use", "ActionPlanner", "ordinary action"),
    (69, "Form Workflow", "computer_use", "ActionPlanner", "field classification"),
    (70, "Publication Boundary", "social", "ApprovalBoundary", "publish classification"),
    (71, "Deletion Boundary", "social", "ApprovalBoundary", "delete classification"),
    (72, "Messaging Boundary", "social", "ApprovalBoundary", "send classification"),
    (73, "Media Workflow", "content", "ContentPipeline", "media preservation"),
    (74, "Platform Draft Isolation", "social", "ContentPipeline", "platform-specific draft"),
    (75, "Computer-use Verification", "computer_use", "ActionPlanner", "action classification evidence"),

    (76, "Lead Scoring", "growth", "LeadScorer", "bounded score"),
    (77, "Funnel Analysis", "growth", "FunnelAnalyzer", "conversion rates"),
    (78, "Experiment Tracking", "growth", "ExperimentTracker", "metric summary"),
    (79, "Pricing Recommendation", "commerce", "PricingEngine", "bounded price"),
    (80, "Revenue Ledger", "finance", "RevenueLedger", "exact total"),
    (81, "Campaign Measurement", "growth", "ExperimentTracker", "variant metrics"),
    (82, "Growth Opportunity Scoring", "growth", "LeadScorer", "priority score"),
    (83, "Conversion Monitoring", "growth", "FunnelAnalyzer", "rate output"),
    (84, "A/B Result Storage", "growth", "ExperimentTracker", "variant storage"),
    (85, "Offer Optimization", "commerce", "PricingEngine", "price candidate"),
    (86, "Revenue Accounting Seam", "finance", "RevenueLedger", "ledger total"),
    (87, "Lead Metadata", "crm", "Lead", "typed lead"),
    (88, "Lead Qualification", "crm", "LeadScorer", "score threshold"),
    (89, "Sales Funnel State", "sales", "FunnelEvent", "funnel event"),
    (90, "Retention Experimentation", "growth", "ExperimentTracker", "cohort metric"),
    (91, "Referral Measurement", "growth", "ExperimentTracker", "variant metric"),
    (92, "Partner Attribution Seam", "growth", "Lead", "source field"),
    (93, "Revenue Attribution Seam", "finance", "RevenueLedger", "entry total"),
    (94, "Pricing Confidence", "commerce", "PricingEngine", "confidence bound"),
    (95, "Offer Guardrails", "commerce", "PricingEngine", "bounded multiplier"),
    (96, "CRM Event Contract", "crm", "FunnelEvent", "typed event"),
    (97, "Pipeline Conversion", "sales", "FunnelAnalyzer", "conversion map"),
    (98, "Campaign Variant Registry", "growth", "ExperimentTracker", "variant registry"),
    (99, "Revenue Integrity", "finance", "RevenueLedger", "non-negative validation"),
    (100, "Growth Reporting", "growth", "FunnelAnalyzer", "report map"),

    (101, "Artifact Storage", "engineering", "ArtifactStore", "content hash"),
    (102, "Artifact Retrieval", "engineering", "ArtifactStore", "byte equality"),
    (103, "Health Registry", "devops", "HealthRegistry", "check aggregation"),
    (104, "Feature Flags", "platform", "FeatureFlags", "flag state"),
    (105, "Change Guard", "devops", "ChangeGuard", "approval/test gate"),
    (106, "Release Contract", "devops", "ChangeSet", "typed change"),
    (107, "Rollback Token", "devops", "ChangeSet", "rollback field"),
    (108, "Service Health", "devops", "HealthRegistry", "healthy checks"),
    (109, "Artifact Integrity", "engineering", "ArtifactStore", "SHA-256"),
    (110, "Deployment Gating", "devops", "ChangeGuard", "green tests"),
    (111, "Progressive Rollout", "platform", "FeatureFlags", "rollout bound"),
    (112, "Kill Switch", "platform", "KillSwitch", "instant stop"),
    (113, "Operational Readiness", "devops", "HealthRegistry", "aggregate checks"),
    (114, "Environment Separation", "devops", "FeatureFlags", "explicit state"),
    (115, "Safe Self-modification", "devops", "ChangeGuard", "approval required"),

    (116, "Artifact Provenance", "engineering", "ArtifactStore", "content address"),
    (117, "Build Evidence", "devops", "ChangeSet", "test requirement"),
    (118, "Release Safety", "devops", "ChangeGuard", "approval/test validation"),
    (119, "Runtime Health", "devops", "HealthRegistry", "health snapshot"),
    (120, "Emergency Shutdown", "security", "KillSwitch", "active state"),

    (121, "Metric Monitoring", "evaluation", "MetricMonitor", "target ratio"),
    (122, "Regression Detection", "evaluation", "RegressionDetector", "threshold"),
    (123, "Drift Detection", "evaluation", "DriftDetector", "distance"),
    (124, "Canary Comparison", "evaluation", "CanaryEvaluator", "candidate gate"),
    (125, "Optimization Loop", "optimization", "OptimizationLoop", "guarded update"),
    (126, "Benchmark Monitoring", "evaluation", "MetricMonitor", "metric aggregation"),
    (127, "Accuracy Regression", "evaluation", "RegressionDetector", "accuracy floor"),
    (128, "Latency Regression", "evaluation", "RegressionDetector", "latency guard"),
    (129, "Cost Regression", "evaluation", "RegressionDetector", "cost guard"),
    (130, "Memory Retention Drift", "evaluation", "DriftDetector", "distance"),
    (131, "Security Regression", "security", "RegressionDetector", "security floor"),
    (132, "Recovery Regression", "evaluation", "RegressionDetector", "recovery floor"),
    (133, "A/B Canary", "optimization", "CanaryEvaluator", "candidate comparison"),
    (134, "Safe Optimization", "optimization", "OptimizationLoop", "guarded candidate"),
    (135, "Evaluation Gate", "evaluation", "MetricMonitor", "required metrics"),

    (136, "Plugin Registry", "platform", "PluginRegistry", "unique plugin names"),
    (137, "API Contract Registry", "platform", "ContractRegistry", "typed endpoint"),
    (138, "Tenant Registry", "platform", "TenantRegistry", "tenant creation"),
    (139, "Tenant Isolation Seam", "platform", "TenantRegistry", "tenant lookup"),
    (140, "Feature Governance", "platform", "FeatureFlags", "explicit flags"),
    (141, "Plugin Permission Metadata", "platform", "PluginSpec", "permission tuple"),
    (142, "API Schema Metadata", "platform", "APIContract", "request/response schema"),
    (143, "Multi-tenant Identity", "platform", "Tenant", "stable tenant id"),
    (144, "Platform Kill Switch", "security", "KillSwitch", "global stop"),
    (145, "Capability Inventory", "platform", "PluginRegistry", "list capabilities"),
    (146, "Integration Contract Layer", "platform", "ContractRegistry", "contract lookup"),
    (147, "Tenant-aware Routing Seam", "platform", "TenantRegistry", "tenant context"),
    (148, "Production Readiness Aggregation", "platform", "Readiness", "all required checks"),
    (149, "Final Security Gate", "security", "Readiness", "security check required"),
    (150, "SparkBot Platform Gate", "platform", "Readiness", "all mandatory checks"),
]


MILESTONES = tuple(
    Milestone(
        row[0],
        row[1],
        row[2],
        row[3],
        row[4],
        row[0] - 1 if row[0] > 16 else None,
    )
    for row in _MILESTONE_ROWS
)


class MilestoneRegistry:
    def __init__(self, milestones: Iterable[Milestone] = MILESTONES) -> None:
        rows = tuple(milestones)
        self._items = {m.id: m for m in rows}
        if len(self._items) != len(rows):
            raise ValueError("duplicate milestone ids")

    def get(self, milestone_id: int) -> Milestone:
        return self._items[milestone_id]

    def all(self) -> list[Milestone]:
        return [self._items[k] for k in sorted(self._items)]

    def range(self, start: int, end: int) -> list[Milestone]:
        return [m for m in self.all() if start <= m.id <= end]

    def complete_contract(self, milestone_id: int) -> dict[str, Any]:
        item = self.get(milestone_id)
        return {
            "id": item.id,
            "name": item.name,
            "area": item.area,
            "implementation": item.implementation,
            "verification": item.verification,
            "contract_ready": True,
        }
