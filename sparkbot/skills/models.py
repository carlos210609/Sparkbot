from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

class SkillRisk(str, Enum):
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"
class Permission(str, Enum):
    READ="READ"; WRITE="WRITE"; PUBLISH="PUBLISH"; COMMUNICATE="COMMUNICATE"; FINANCIAL="FINANCIAL"; ACCOUNT="ACCOUNT"; ADMIN="ADMIN"

@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    category: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    permissions: list[Permission] = field(default_factory=list)
    risk_level: SkillRisk = SkillRisk.LOW
    prerequisites: list[str] = field(default_factory=list)
    success_conditions: list[str] = field(default_factory=list)
    failure_conditions: list[str] = field(default_factory=list)
    verification_method: str = "output_exists"
    cost_estimate: float = 0.0
    latency_estimate: float = 0.0
    version: str = "1.0.0"
    enabled: bool = True
    telemetry: dict[str, Any] = field(default_factory=dict)
    handler: Callable[..., Any] | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "handler"}
        d["permissions"] = [p.value for p in self.permissions]
        d["risk_level"] = self.risk_level.value
        return d
