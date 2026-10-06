from __future__ import annotations

def test_engine_routes_and_dry_runs():
    from sparkbot.engine import ExecutionContext, SkillExecutor, SkillRouter
    from sparkbot.skills import SkillRegistry

    registry = SkillRegistry()
    router = SkillRouter(registry)
    selected = router.route("instagram growth", limit=5)
    assert selected

    result = SkillExecutor(registry).execute(
        selected[0].id,
        ExecutionContext(mode="DRY_RUN"),
        {"request": "instagram growth"},
    )
    assert result.status == "COMPLETED"
    assert result.verified is True
    assert result.output["simulation"] is True


def test_production_without_adapter_does_not_claim_success():
    from sparkbot.engine import ExecutionContext, SkillExecutor
    from sparkbot.skills import SkillRegistry

    result = SkillExecutor(SkillRegistry()).execute(
        "001.01",
        ExecutionContext(mode="PRODUCTION"),
        {},
    )
    assert result.status == "FAILED"
    assert result.verified is False


def test_runtime_manifest_only_advertises_real_capabilities():
    from sparkbot.runtime import manifest

    runtime = manifest(browser_available=False)
    tools = {tool["id"]: tool for tool in runtime["tools"]}
    assert tools["WEB_FETCH"]["available"] is True
    assert tools["BROWSER"]["available"] is False
    assert tools["FILES"]["available"] is False
    assert tools["EXTERNAL_ACCOUNT"]["available"] is False


def test_browser_agent_fails_gracefully_without_playwright():
    from sparkbot.browser_agent import BrowserAgent

    status = BrowserAgent().status()
    assert "installed" in status
    assert "started" in status
