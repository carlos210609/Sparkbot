from __future__ import annotations
from typing import Iterable
from .models import Skill, SkillRisk
from .catalog import CATALOG

class SkillRegistry:
    def __init__(self, skills: Iterable[Skill] | None = None):
        self._skills = {s.id: s for s in (skills or build_catalog())}
        self._validate()
    def _validate(self) -> None:
        if len(self._skills) != 1500:
            raise ValueError(f"Skill registry must contain exactly 1500 skills; found {len(self._skills)}")
        expected = {f"{d:03d}.{s:02d}" for d in range(1,101) for s in range(1,16)}
        if set(self._skills) != expected:
            raise ValueError("Skill IDs must cover exactly 001.01 through 100.15")
        for s in self._skills.values():
            if s.risk_level in {SkillRisk.HIGH, SkillRisk.CRITICAL} and not s.permissions:
                raise ValueError(f"High-risk skill {s.id} has no declared permissions")
            if s.version.count(".") != 2:
                raise ValueError(f"Invalid semver for {s.id}")
    def get(self, skill_id: str) -> Skill | None: return self._skills.get(skill_id)
    def all(self) -> list[Skill]: return list(self._skills.values())
    def search(self, query: str, limit: int = 10) -> list[Skill]:
        q = query.lower().strip()
        terms = set(q.split())
        scored=[]
        for s in self._skills.values():
            hay=f"{s.name} {s.description} {s.category}".lower()
            score=sum(3 for t in terms if t in s.name.lower()) + sum(1 for t in terms if t in hay)
            if score and s.enabled: scored.append((score,s))
        scored.sort(key=lambda x:(-x[0], x[1].id))
        return [s for _,s in scored[:limit]]
    def replace(self, skill: Skill) -> None:
        if skill.id not in self._skills: raise KeyError(skill.id)
        self._skills[skill.id]=skill
        self._validate()

def build_catalog() -> list[Skill]:
    return [Skill(id=i, name=name, description=f"Operational capability: {name}.", category=cat,
                   outputs=["verified_result"], success_conditions=["verification_passed"],
                   failure_conditions=["execution_error","verification_failed"])
            for i,cat,name in CATALOG]
