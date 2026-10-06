from sparkbot.browser_monitor import BrowserMonitor
from sparkbot.db import init_db


def test_browser_monitor_records_event(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARKBOT_DB_PATH", str(tmp_path / "sparkbot.db"))
    init_db()
    event = BrowserMonitor().record("navigate", url="https://example.com", status="completed")
    assert event["action"] == "navigate"
    assert event["url"] == "https://example.com"
    assert BrowserMonitor().recent(10)[0]["event_id"] == event["event_id"]
