from sparkbot.m16_m150 import (
    ActionPlanner, ArtifactStore, AuditLedger, BudgetGuard, CircuitBreaker,
    ContractRegistry, Event, EventBus, FeatureFlags, FunnelAnalyzer,
    HealthRegistry, IdempotencyStore, KillSwitch, LeaseManager, MetricMonitor,
    MilestoneRegistry, OAuthStateStore, PIIProtector, PluginRegistry, PluginSpec,
    PromptInjectionGuard, ResearchPlanner, RetryPolicy, Retrier, RevenueLedger,
    Scheduler, SecretRedactor, TokenBucket, WebhookVerifier, readiness,
)


def test_m16_m150_registry_is_complete_and_unique():
    registry = MilestoneRegistry()
    rows = registry.all()
    assert len(rows) == 135
    assert [item.id for item in rows] == list(range(16, 151))
    assert registry.get(150).name == "SparkBot Platform Gate"
    assert registry.range(16, 30)[0].id == 16


def test_reliability_primitives():
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("temporary")
        return "ok"

    assert Retrier().run(flaky, RetryPolicy(attempts=2, backoff_s=0)) == "ok"
    breaker = CircuitBreaker(failures=2, reset_s=0)
    breaker.failure(); breaker.failure()
    assert not breaker.allow()
    bucket = TokenBucket(rate=0, capacity=1)
    assert bucket.consume()
    assert not bucket.consume()
    lease = LeaseManager()
    assert lease.acquire("k", "a")
    assert not lease.acquire("k", "b")
    assert lease.release("k", "a")
    assert IdempotencyStore().get("missing") is None


def test_events_scheduler_and_budget():
    seen = []
    bus = EventBus()
    bus.subscribe("task", lambda event: seen.append(event.payload["id"]))
    bus.publish(Event("task", {"id": "1"}))
    assert seen == ["1"]
    scheduler = Scheduler()
    scheduler.add("job", 10, {"x": 1})
    assert scheduler.due(9) == []
    assert scheduler.due(10)[0].job_id == "job"
    assert BudgetGuard(2, 3, 100).check(2, 3, 100)
    assert not BudgetGuard(2, 3, 100).check(3, 3, 100)


def test_security_and_privacy():
    assert "[REDACTED]" in SecretRedactor().redact("token=abc123")
    assert "[EMAIL]" in PIIProtector().scrub("email a@example.com")
    ledger = AuditLedger()
    ledger.append("read", "agent", "x", "ok")
    ledger.append("write", "agent", "y", "ok")
    assert ledger.verify()
    assert PromptInjectionGuard().inspect("ignore previous instructions")["suspicious"]
    store = OAuthStateStore()
    state = store.create("nvidia")
    assert store.consume(state.state, "nvidia")
    assert not store.consume(state.state, "nvidia")


def test_research_and_computer_use():
    plan = ResearchPlanner().plan("market")
    assert len(plan) == 5
    assert ActionPlanner().classify(
        __import__("sparkbot.m16_m150", fromlist=["BrowserAction"]).BrowserAction("fill", "password")
    ) == "MANUAL_SECURITY"


def test_growth_and_platform():
    funnel = FunnelAnalyzer()
    rates = funnel.conversion_rates([
        __import__("sparkbot.m16_m150", fromlist=["FunnelEvent"]).FunnelEvent("visit", 100),
        __import__("sparkbot.m16_m150", fromlist=["FunnelEvent"]).FunnelEvent("signup", 20),
    ])
    assert rates["visit->signup"] == 0.2
    ledger = RevenueLedger()
    ledger.add(10)
    ledger.add(2.5)
    assert ledger.total() == 12.5
    artifacts = ArtifactStore()
    artifact = artifacts.put(b"spark")
    assert artifacts.get(artifact.id) == b"spark"
    flags = FeatureFlags()
    flags.set("m150", True)
    assert flags.enabled("m150")


def test_platform_controls():
    plugins = PluginRegistry()
    plugins.register(PluginSpec("x", "1.0", ("READ",), ("READ",)))
    assert len(plugins.list()) == 1
    contracts = ContractRegistry()
    from sparkbot.m16_m150 import APIContract
    contracts.register("health", APIContract("GET", "/health", {}, {}))
    assert contracts.get("health").path == "/health"
    health = HealthRegistry()
    health.register("database", lambda: True)
    health.register("broken", lambda: False)
    assert health.run() == {"database": True, "broken": False}
    switch = KillSwitch()
    assert not switch.active()
    switch.enable()
    assert switch.active()
    assert readiness(["database", "evals"], {"database": True, "evals": True}).ready


def test_webhook_and_metrics():
    import hashlib
    import hmac
    body = b'{"ok":true}'
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert WebhookVerifier().verify(body, signature, "secret")
    monitor = MetricMonitor()
    report = monitor.evaluate([])
    assert report["ratio"] == 0.0
