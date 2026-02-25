from __future__ import annotations

import os

from tenants.registry import TenantRegistry
from tools.tenant_knowledge_tools import TenantKnowledgeTools


class FlairKnowledgeTools(TenantKnowledgeTools):
    def __init__(self, snapshot_path: str | None = None) -> None:
        super().__init__(
            tenant_slug="flair",
            snapshot_path=snapshot_path
            or os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data",
                "flair_public_support_snapshot_2026-02-25.json",
            ),
            tenant_profile=TenantRegistry().try_load("flair"),
        )

