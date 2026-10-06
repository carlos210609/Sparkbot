"""Operational learning facade backed by SparkBot persistent memory."""
from __future__ import annotations
from .kernel import MemorySystem

class LearningEngine:
    def __init__(self):
        self.memory = MemorySystem()
    def record(self, subject, action, success, verified, latency_ms=0.0, context=None):
        self.memory.remember("learning", f"{subject}:{action}",
                             {"success":bool(success),"verified":bool(verified),
                              "latency_ms":float(latency_ms),"context":context or {}},
                             0.9 if verified else 0.5)
    def recommend(self, subject, limit=5):
        return self.memory.recall(subject, limit=limit)
    def snapshot(self, limit=100):
        return self.memory.recall("learning", limit=limit)
    def summary(self):
        rows=self.snapshot(500)
        return {"events":len(rows)}
