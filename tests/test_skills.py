from sparkbot.skills import SkillRegistry
from sparkbot.engine import ExecutionContext, SkillExecutor, SkillRouter

def test_registry_has_exact_slot_count():
    r=SkillRegistry()
    assert len(r.all()) == 1500
    assert len({s.id for s in r.all()}) == 1500

def test_router_returns_enabled_skills():
    r=SkillRouter(SkillRegistry())
    assert r.route("Instagram growth")

def test_dry_run_never_claims_external_execution():
    e=SkillExecutor(SkillRegistry())
    result=e.execute("018.01", ExecutionContext(mode="DRY_RUN"))
    assert result.status == "COMPLETED"
    assert result.verified is True
    assert result.output["simulation"] is True

def test_production_high_risk_requires_approval():
    r=SkillRegistry(); s=r.get("001.01")
    from dataclasses import replace
    from sparkbot.skills.models import SkillRisk, Permission
    r.replace(replace(s,risk_level=SkillRisk.HIGH,permissions=[Permission.WRITE]))
    e=SkillExecutor(r)
    result=e.execute(s.id,ExecutionContext(mode="PRODUCTION",permissions={Permission.WRITE}))
    assert result.status == "BLOCKED"
