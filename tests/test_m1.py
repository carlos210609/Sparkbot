from sparkbot.m1 import M1Orchestrator, Plan, Task, ToolResult


def test_m1_requires_verification_evidence():
    orch=M1Orchestrator(lambda t: Plan(t.id, ("x",)), lambda s, t: ToolResult(True, "done", evidence={"verified": False}))
    result, trace=orch.run(Task("t1", "do it"))
    assert not result.success
    assert result.error == "missing independent verification evidence"
    assert trace[-1]["stage"] == "VERIFIED"


def test_m1_completes_verified_tool():
    orch=M1Orchestrator(lambda t: Plan(t.id, ("x",)), lambda s, t: ToolResult(True, "done", evidence={"verified": True}))
    result, trace=orch.run(Task("t2", "do it"))
    assert result.success
    assert result.output == "done"
    assert [x["stage"] for x in trace] == ["RECEIVED", "PLANNED", "TOOL", "VERIFIED"]
