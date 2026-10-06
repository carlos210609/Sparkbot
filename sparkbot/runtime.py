from __future__ import annotations

"""Operational capability manifest exposed to SparkBot's reasoning layer.

This module is deliberately honest: a capability being described here does not
mean an external action has already happened. The execution layer must report
real evidence before SparkBot claims completion.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCapability:
    id: str
    name: str
    description: str
    available: bool
    permissions: tuple[str, ...]
    risk: str
    requires_approval: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "available": self.available,
            "permissions": list(self.permissions),
            "risk": self.risk,
            "requires_approval": self.requires_approval,
        }


def manifest(*, browser_available: bool = False) -> dict[str, Any]:
    tools = [
        ToolCapability(
            "WEB_SEARCH", "Web search",
            "Search public web sources and return source URLs for follow-up retrieval.",
            True, ("READ",), "low",
        ),
        ToolCapability(
            "WEB_FETCH", "Web fetch",
            "Retrieve public HTTP/HTTPS resources for research and verification.",
            True, ("READ",), "low",
        ),
        ToolCapability(
            "BROWSER", "Browser",
            "Navigate and interact with a real browser session when a browser runtime is configured.",
            browser_available, ("READ", "WRITE", "COMMUNICATE"),
            "medium", True,
        ),
        ToolCapability(
            "FILES", "File intelligence",
            "Inspect and transform files made available to the agent.",
            False, ("READ", "WRITE"), "low",
        ),
        ToolCapability(
            "AI", "AI reasoning",
            "Reason, plan, critique, synthesize and communicate using the configured AI provider.",
            True, ("READ",), "low",
        ),
        ToolCapability(
            "INTERNAL", "Spark runtime",
            "Run SparkBot's local planning, skills, memory, verification and telemetry.",
            True, ("READ", "WRITE"), "low",
        ),
        ToolCapability(
            "EXTERNAL_ACCOUNT", "External account actions",
            "Create or modify user-authorized external accounts through supported browser integrations.",
            browser_available, ("ACCOUNT", "WRITE"), "high", True,
        ),
    ]
    return {
        "agent_identity": "SparkBot autonomous operations agent",
        "operating_principle": (
            "Reason -> select capability -> check permission -> execute -> verify -> report evidence."
        ),
        "internet_access": {
            "public_web": True,
            "browser_automation": browser_available,
            "statement": (
                "Public web search and retrieval are available through the web tools; "
                "interactive browser control is available only when a browser runtime is configured."
            ),
        },
        "tools": [tool.to_dict() for tool in tools],
        "safety": {
            "never_fabricate_execution": True,
            "never_bypass_authentication_or_captcha": True,
            "respect_platform_limits_and_opt_outs": True,
            "approval_required_for_high_risk_external_actions": True,
        },
    }
