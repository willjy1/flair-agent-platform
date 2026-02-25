from __future__ import annotations

from typing import Dict

from agents.orchestrator import OrchestratorAgent
from tenants.registry import TenantRegistry
from tools.flair_knowledge_tools import FlairKnowledgeTools
from tools.tenant_knowledge_tools import TenantKnowledgeTools


class TenantOrchestratorPool:
    def __init__(self, tenant_registry: TenantRegistry | None = None) -> None:
        self.registry = tenant_registry or TenantRegistry()
        self._cache: Dict[str, OrchestratorAgent] = {}

    def get(self, tenant_slug: str = "flair") -> OrchestratorAgent:
        slug = (tenant_slug or "flair").strip().lower()
        if slug in self._cache:
            return self._cache[slug]

        profile = self.registry.try_load(slug)
        if slug == "flair":
            knowledge = FlairKnowledgeTools()
        else:
            knowledge = TenantKnowledgeTools(tenant_slug=slug, tenant_profile=profile, tenant_registry=self.registry)
        orchestrator = OrchestratorAgent(flair_knowledge_tools=knowledge, tenant_slug=slug, tenant_profile=profile)
        self._cache[slug] = orchestrator
        return orchestrator

