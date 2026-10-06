"""SparkBot's 700-agent specialist mesh.

The mesh is deterministic: 100 operational domains x 7 cognitive/operational roles
= exactly 700 registered agents. Agents are lightweight specialist profiles routed to
the same execution and policy core; they are not 700 uncontrolled model processes.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class AgentProfile:
    id: str
    name: str
    domain: str
    role: str
    focus: str
    description: str
    tools: tuple[str, ...] = ("internal", "web", "files", "ai")
    permissions: tuple[str, ...] = ("READ",)
    risk_level: str = "low"
    enabled: bool = True
    system_prompt: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "domain": self.domain,
            "role": self.role, "focus": self.focus, "description": self.description,
            "tools": list(self.tools), "permissions": list(self.permissions),
            "risk_level": self.risk_level, "enabled": self.enabled,
            "system_prompt": self.system_prompt, "metrics": dict(self.metrics),
        }

DOMAINS = [
  "Core Intelligence",
  "Reasoning",
  "Planning",
  "Decision Making",
  "Memory",
  "Knowledge",
  "Research",
  "Web Intelligence",
  "Browser Operations",
  "Task Execution",
  "Self Correction",
  "Meta Intelligence",
  "Marketing Strategy",
  "Branding",
  "Customer Research",
  "Market Analysis",
  "Competitive Intelligence",
  "Instagram",
  "Reels",
  "Stories",
  "Social Content",
  "TikTok",
  "YouTube",
  "X Microblogging",
  "LinkedIn",
  "Facebook",
  "Threads",
  "Pinterest",
  "Reddit",
  "Community",
  "Content Strategy",
  "Copywriting",
  "Storytelling",
  "SEO",
  "Local SEO",
  "Paid Advertising",
  "Meta Ads",
  "Google Ads",
  "Email Marketing",
  "CRM",
  "Sales",
  "Lead Generation",
  "Outbound",
  "Sales Enablement",
  "Customer Success",
  "Retention",
  "Referral",
  "Influencer Marketing",
  "Affiliate Marketing",
  "Partnerships",
  "Growth",
  "CRO",
  "Funnels",
  "Product Marketing",
  "Pricing",
  "Ecommerce",
  "Marketplaces",
  "Content Distribution",
  "Viral Content",
  "Analytics",
  "Data Science",
  "Experimentation",
  "Forecasting",
  "Revenue",
  "Finance",
  "Project Management",
  "Automation",
  "API",
  "Integrations",
  "CRM Communication",
  "Customer Support",
  "Conversational AI",
  "Multilingual",
  "Creative Direction",
  "Video",
  "Design",
  "Website",
  "Software Engineering",
  "Git",
  "DevOps",
  "Security",
  "Privacy",
  "Compliance",
  "Account Management",
  "Credentials",
  "Observability",
  "Notifications",
  "Scheduling",
  "Reporting",
  "Executive Intelligence",
  "Opportunity Detection",
  "Trend Intelligence",
  "Reputation",
  "Crisis Management",
  "Productivity",
  "Knowledge Work",
  "File Intelligence",
  "Learning",
  "Self Optimization",
  "Autonomous Super Agent"
]
ROLES = [
  [
    "researcher",
    "Researcher",
    "research, evidence gathering, source comparison"
  ],
  [
    "strategist",
    "Strategist",
    "strategy, prioritization, trade-offs"
  ],
  [
    "planner",
    "Planner",
    "decomposition, dependencies, sequencing"
  ],
  [
    "executor",
    "Executor",
    "operational task execution within permissions"
  ],
  [
    "analyst",
    "Analyst",
    "measurement, diagnosis, metrics, pattern detection"
  ],
  [
    "critic",
    "Critic",
    "challenge assumptions, identify risks, propose corrections"
  ],
  [
    "verifier",
    "Verifier",
    "evidence-based verification and completion checks"
  ]
]

AGENTS: tuple[AgentProfile, ...] = tuple(
    AgentProfile(
        id=f"A{d+1:03d}-{role.upper()}",
        name=f"{domain} {role_name}",
        domain=domain,
        role=role,
        focus=focus,
        description=f"Specialist agent for {domain} focused on {focus}.",
        risk_level="medium" if role == "executor" else "low",
        system_prompt=(
            f"You are the {role_name} specialist for {domain}. {focus}. "
            "Work only within granted permissions. State uncertainty, never fabricate "
            "execution, and return verifiable outputs."
        ),
    )
    for d, domain in enumerate(DOMAINS)
    for role, role_name, focus in ROLES
)

if len(AGENTS) != 700:
    raise RuntimeError(f"Agent mesh integrity failure: expected 700, found {len(AGENTS)}")

class AgentMesh:
    def __init__(self, agents: tuple[AgentProfile, ...] = AGENTS):
        self._agents = {a.id: a for a in agents}

    def all(self) -> list[AgentProfile]:
        return list(self._agents.values())

    def get(self, agent_id: str) -> AgentProfile | None:
        return self._agents.get(agent_id)

    def search(self, query: str, limit: int = 12) -> list[AgentProfile]:
        terms = {t for t in query.lower().replace("-", " ").split() if len(t) > 1}
        scored: list[tuple[int, AgentProfile]] = []
        for agent in self._agents.values():
            hay = f"{agent.name} {agent.domain} {agent.role} {agent.focus}".lower()
            score = sum(4 for t in terms if t in agent.domain.lower())
            score += sum(3 for t in terms if t in agent.name.lower())
            score += sum(1 for t in terms if t in hay)
            if score and agent.enabled:
                scored.append((score, agent))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        return [agent for _, agent in scored[:limit]]

    def by_domain(self, domain: str) -> list[AgentProfile]:
        return [a for a in self._agents.values() if a.domain.lower() == domain.lower()]

    def stats(self) -> dict[str, Any]:
        return {
            "total": len(self._agents),
            "enabled": sum(a.enabled for a in self._agents.values()),
            "domains": len({a.domain for a in self._agents.values()}),
            "roles": len({a.role for a in self._agents.values()}),
        }
