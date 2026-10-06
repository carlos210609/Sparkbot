def test_social_catalog_has_core_platforms():
    from sparkbot.social import catalog
    ids = {item["id"] for item in catalog()}
    assert {"instagram","tiktok","youtube","linkedin","facebook","x","threads","pinterest","reddit","canva"} <= ids

def test_learning_records_and_recommends(tmp_path, monkeypatch):
    db = tmp_path / "learn.db"
    monkeypatch.setenv("SPARKBOT_DB_PATH", str(db))
    from sparkbot.db import init_db
    from sparkbot.learning import LearningEngine
    init_db()
    learner = LearningEngine()
    learner.record(subject="instagram", action="draft", success=True, verified=True, latency_ms=10)
    learner.record(subject="instagram", action="publish", success=False, verified=False, latency_ms=100)
    rows = learner.recommend("instagram")
    assert rows and rows[0]["action"] == "draft"

def test_approval_store_roundtrip(tmp_path, monkeypatch):
    db = tmp_path / "approval.db"
    monkeypatch.setenv("SPARKBOT_DB_PATH", str(db))
    from sparkbot.db import init_db
    from sparkbot.approvals import ApprovalStore
    init_db()
    store = ApprovalStore()
    aid = store.create("social_publish", {"platform":"instagram"}, "external publication")
    assert store.get(aid)["status"] == "PENDING"
    store.approve(aid)
    assert store.get(aid)["status"] == "APPROVED"
