"""Spark Kernel: shared cognition, memory, tools, security, experiments and learning."""
from __future__ import annotations
import json, re, time, uuid
from dataclasses import dataclass, field
from typing import Any, Callable
from .db import execute, fetch_all

@dataclass
class Evidence:
    claim: str
    source: str
    confidence: float = 0.5
    timestamp: float = field(default_factory=time.time)

@dataclass
class MemoryItem:
    kind: str
    key: str
    value: str
    importance: float = 0.5

class MemorySystem:
    def remember(self, kind: str, key: str, value: Any, importance: float=0.5):
        execute("INSERT INTO memories(kind,key,value,importance) VALUES (?,?,?,?)",
                (kind,key,json.dumps(value,ensure_ascii=False) if not isinstance(value,str) else value,float(importance)))
    def recall(self, query: str, limit: int=10) -> list[dict[str,Any]]:
        terms=[x for x in re.findall(r"\w+",query.lower()) if len(x)>2]
        rows=fetch_all("SELECT * FROM memories ORDER BY importance DESC, updated_at DESC LIMIT 500")
        scored=[]
        for row in rows:
            text=f"{row['key']} {row['value']}".lower()
            score=sum(1 for t in terms if t in text)
            if score: scored.append((score,row))
        scored.sort(key=lambda x:(-x[0],-float(x[1]['importance'])))
        return [r for _,r in scored[:limit]]

class WorldModel:
    def __init__(self): self.state: dict[str,Any] = {"entities":{}, "relations":[], "facts":[]}
    def upsert(self, entity: str, data: dict[str,Any]):
        self.state["entities"].setdefault(entity,{}).update(data)
    def relate(self, subject: str, relation: str, object_: str):
        edge={"subject":subject,"relation":relation,"object":object_}
        if edge not in self.state["relations"]: self.state["relations"].append(edge)
    def snapshot(self): return self.state

class EvidenceEngine:
    def add(self, claim: str, source: str, confidence: float=0.5):
        return Evidence(claim,source,max(0,min(1,confidence)))
    def consensus(self, evidence: list[Evidence]) -> dict[str,Any]:
        if not evidence: return {"confidence":0,"evidence":[]}
        return {"confidence":sum(e.confidence for e in evidence)/len(evidence),
                "evidence":[e.__dict__ for e in evidence]}

class ToolRouter:
    def __init__(self): self.tools: dict[str,dict[str,Any]]={}
    def register(self,name: str,handler: Callable[...,Any],risk: str="low",permissions: tuple[str,...]=("READ",)):
        self.tools[name]={"handler":handler,"risk":risk,"permissions":permissions}
    def choose(self, request: str, limit: int=5):
        terms=set(re.findall(r"\w+",request.lower()))
        scored=[]
        for name,tool in self.tools.items():
            score=sum(1 for t in terms if t in name.lower())
            if score: scored.append((score,name))
        scored.sort(key=lambda x:-x[0])
        return [self.tools[n] | {"name":n} for _,n in scored[:limit]]

class SecurityBrain:
    HIGH_RISK=re.compile(r"(?i)\b(password|senha|token|api[_ -]?key|secret|credential|credencial|money|dinheiro|pay|pagar|delete|deletar|publish|publicar)\b")
    def inspect(self, request: str, domain: str="") -> dict[str,Any]:
        high=bool(self.HIGH_RISK.search(request))
        return {"allow":True,"risk":"high" if high else "low","requires_approval":high,
                "reason":"Sensitive external side effects require explicit approval." if high else "No elevated risk detected."}

class ExperimentEngine:
    def create(self, hypothesis: str, variants: list[str]) -> dict[str,Any]:
        return {"id":uuid.uuid4().hex,"hypothesis":hypothesis,"variants":variants,"status":"READY","metrics":{}}
    def record(self, experiment_id: str, variant: str, metric: str, value: float) -> dict[str,Any]:
        return {"experiment_id":experiment_id,"variant":variant,"metric":metric,"value":value}

class OpportunityEngine:
    def score(self, opportunity: dict[str,Any]) -> float:
        impact=float(opportunity.get("impact",0)); confidence=float(opportunity.get("confidence",0))
        effort=max(float(opportunity.get("effort",1)),0.1); risk=float(opportunity.get("risk",0))
        return max(0,min(100,100*(impact*confidence)/(effort*(1+risk))))
    def rank(self, opportunities: list[dict[str,Any]]) -> list[dict[str,Any]]:
        out=[dict(x,score=self.score(x)) for x in opportunities]
        return sorted(out,key=lambda x:x["score"],reverse=True)

class AgentCouncil:
    def deliberate(self, agents: list[dict[str,Any]], request: str) -> dict[str,Any]:
        roles=[a.get("role") for a in agents]
        missing=[r for r in ("researcher","strategist","critic","verifier") if r not in roles]
        return {"participants":len(agents),"roles":roles,"missing_roles":missing,
                "consensus_ready":not missing,"decision":"proceed" if not missing else "recruit_more"}

class BenchmarkEngine:
    def evaluate(self, agent_id: str, success: bool, latency_ms: float, verified: bool) -> dict[str,Any]:
        return {"agent_id":agent_id,"success":success,"verified":verified,"latency_ms":latency_ms,
                "score":(1 if success else 0)*0.5+(1 if verified else 0)*0.4+max(0,1-min(latency_ms/10000,1))*0.1}

class SparkKernel:
    def __init__(self):
        self.memory=MemorySystem(); self.world=WorldModel(); self.evidence=EvidenceEngine()
        self.tools=ToolRouter(); self.security=SecurityBrain(); self.experiments=ExperimentEngine()
        self.opportunities=OpportunityEngine(); self.council=AgentCouncil(); self.benchmarks=BenchmarkEngine()
    def inspect(self, request: str) -> dict[str,Any]:
        security=self.security.inspect(request)
        memories=self.memory.recall(request,5)
        return {"security":security,"memories":memories,"world":self.world.snapshot(),
                "available_tools":list(self.tools.tools)}
