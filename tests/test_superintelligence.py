from __future__ import annotations

def test_agent_mesh_has_exactly_700_agents():
    from sparkbot.agent_mesh import AgentMesh
    mesh = AgentMesh()
    stats = mesh.stats()
    assert stats["total"] == 700
    assert stats["enabled"] == 700
    assert stats["domains"] == 100
    assert stats["roles"] == 7

def test_skill_registry_has_exactly_1500_skills():
    from sparkbot.skills import SkillRegistry
    registry = SkillRegistry()
    assert len(registry.all()) == 1500
    assert registry.get("001.01") is not None
    assert registry.get("100.15") is not None

def test_cognitive_engine_can_plan_and_verify_in_dry_run(tmp_path, monkeypatch):
    db_file = tmp_path / "sparkbot.db"
    monkeypatch.setenv("SPARKBOT_DB_PATH", str(db_file))
    # DB path is resolved at import time, so this test focuses on the pure mission contract.
    from sparkbot.cognitive import CognitiveEngine
    result = CognitiveEngine().run("crie uma estratégia de crescimento", mode="DRY_RUN")
    assert result["mission_id"]
    assert result["mode"] == "DRY_RUN"
    assert result["agents"]
    assert result["skills"]
    assert result["results"]
    assert all(item["verified"] for item in result["results"])
