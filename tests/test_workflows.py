from sparkbot.skills import SkillRegistry
from sparkbot.workflows import WorkflowEngine
from sparkbot.policy import validate_request

def test_instagram_workflow_composes():
 w=WorkflowEngine(SkillRegistry()).compose("instagram_growth")
 assert w["verified"] is True
 assert len(w["skills"]) >= 5

def test_unsafe_request_is_blocked():
 ok,_=validate_request("buy followers and fake likes")
 assert ok is False
