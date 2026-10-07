from sparkbot.evolution import (
    AgentCoordinator, Blackboard, ComputerUseGuard, ContextEngine, EvalCase,
    EvaluationEngine, MemoryIndex, MemoryRecord, ModelCandidate, ModelRouter,
    PlanCandidate, PlanSearch, PolicyEngine, RateLimiter, ResponseCache,
    ToolRegistry, ToolSpec, VerificationEngine, readiness,
)


def test_m3_memory_and_context():
    memory = MemoryIndex()
    memory.put(MemoryRecord("semantic", "nvidia", "default provider", 0.9))
    assert memory.search("nvidia")[0].key == "nvidia"
    assert ContextEngine().assemble("system", "task", memory.search("nvidia"))


def test_m4_router_and_cache():
    candidates = [
        ModelCandidate("x", "slow", 2, 500, 16000, True),
        ModelCandidate("nvidia", "fast", 1, 300, 16000, True),
    ]
    assert ModelRouter().choose(candidates, needs_tools=True).model == "fast"
    cache = ResponseCache(); key = cache.key([{"role": "user", "content": "hi"}], "fast")
    cache.put(key, "ok"); assert cache.get(key) == "ok"


def test_m5_typed_tools():
    registry = ToolRegistry()
    registry.register(ToolSpec("echo", "echo"), lambda value: value)
    assert registry.invoke("echo", value="ok") == "ok"


def test_m6_verification_requires_evidence():
    verifier = VerificationEngine()
    assert not verifier.verify("ok").passed
    assert verifier.verify("ok", {"deterministic": True}).passed


def test_m7_search_and_stagnation():
    search = PlanSearch()
    assert search.rank([PlanCandidate(("a",), 1), PlanCandidate(("a","b"), .5)])[0].score == 1
    assert search.stagnating(["x", "x", "x"])


def test_m8_security_checkpoint():
    assert ComputerUseGuard().inspect("fill", "password").manual_checkpoint
    assert not ComputerUseGuard().inspect("click", "Home").manual_checkpoint


def test_m9_blackboard():
    board = Blackboard("t1"); board.publish("researcher", "proposal", "x")
    board.evidence.append({"source": "test"})
    assert AgentCoordinator().consensus(board)["ready"]


def test_m10_policy():
    spec = ToolSpec("publish", "publish", ("PUBLISH",), "critical")
    assert not PolicyEngine().decide(spec, {"PUBLISH"}).allowed
    assert PolicyEngine().decide(ToolSpec("read", "read"), {"READ"}).allowed


def test_m11_eval():
    report = EvaluationEngine().report([EvalCase("1", True, True, .9), EvalCase("2", True, False, .2)])
    assert report["accuracy"] == .5
    assert 0 <= report["brier"] <= 1


def test_m12_learning():
    from sparkbot.evolution import OutcomeLearner
    learner=OutcomeLearner(); learner.record("a", True); learner.record("a", False); learner.record("b", True)
    assert learner.rank()[0][0] == "b"


def test_m13_trace():
    from sparkbot.evolution import Trace
    trace=Trace("r1"); trace.add("PLAN", "planned")
    assert trace.export()[0]["stage"] == "PLAN"


def test_m14_rate_limit():
    limiter=RateLimiter(2)
    assert limiter.allow("u"); assert limiter.allow("u"); assert not limiter.allow("u")


def test_m15_readiness():
    assert readiness(database=True, evals=True).ready
    assert not readiness(database=True, evals=False).ready
