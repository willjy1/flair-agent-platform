from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Dict, List

from tenants.registry import TenantProfile, TenantRegistry


class TenantKnowledgeTools:
    def __init__(
        self,
        tenant_slug: str = "flair",
        snapshot_path: str | None = None,
        tenant_profile: TenantProfile | None = None,
        tenant_registry: TenantRegistry | None = None,
    ) -> None:
        self.tenant_slug = tenant_slug
        self.tenant_registry = tenant_registry or TenantRegistry()
        self.tenant_profile = tenant_profile or self.tenant_registry.try_load(tenant_slug) or self._fallback_profile(tenant_slug)
        self.snapshot_path = snapshot_path or self._default_snapshot_path(tenant_slug)
        self.snapshot = self._load_snapshot()

    def _default_snapshot_path(self, tenant_slug: str) -> str:
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            f"{tenant_slug}_public_support_snapshot_2026-02-25.json",
        )

    def _fallback_profile(self, slug: str) -> TenantProfile:
        return TenantProfile(
            slug=slug,
            display_name=f"{slug.title()} Support Agents",
            vertical="travel",
            category="generic",
            customer_capabilities=["customer support triage", "status updates", "changes and refund guidance", "human handoff"],
            channels=["web chat", "voice", "sms", "email"],
            support_commitments=["Keep context across channels.", "Show next steps clearly."],
        )

    def _load_snapshot(self) -> dict:
        if not os.path.exists(self.snapshot_path):
            return {"snapshot_date": None, "entries": [], "comparison_baseline": {}}
        with open(self.snapshot_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def query(self, query: str, top_k: int = 5) -> List[dict]:
        q_terms = {t.strip(".,:;!?()[]{}").lower() for t in query.split() if t.strip()}
        results: List[tuple[int, dict]] = []
        for entry in self.snapshot.get("entries", []):
            text = str(entry.get("text", ""))
            tags = [str(t).lower() for t in entry.get("tags", [])]
            haystack_terms = {t.strip(".,:;!?()[]{}").lower() for t in text.split() if t.strip()}
            score = len(q_terms & haystack_terms) + sum(2 for t in q_terms if t in tags)
            if score > 0:
                results.append((score, entry))
        results.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in results[:top_k]]

    def citations_for_intent(self, intent: str) -> List[dict]:
        intent = intent.upper()
        topic_map = self.tenant_profile.citations_by_intent_topics or {}
        topics = set(topic_map.get(intent, ["contact"]))
        selected: List[dict] = []
        for entry in self.snapshot.get("entries", []):
            if entry.get("topic") in topics:
                selected.append(entry)
        return selected[:4]

    def official_channel_summary(self) -> dict:
        topics = set(self.tenant_profile.official_channel_topics or ["contact"])
        entries = [e for e in self.snapshot.get("entries", []) if e.get("topic") in topics]
        return {
            "snapshot_date": self.snapshot.get("snapshot_date"),
            "tenant": self.tenant_profile.display_name,
            "entries": entries,
        }

    def self_service_options_for_intent(self, intent: str) -> List[dict]:
        return list((self.tenant_profile.self_service_options or {}).get(intent.upper(), []))

    def _source_index(self) -> List[dict]:
        seen = set()
        out = []
        for entry in self.snapshot.get("entries", []):
            url = entry.get("source_url")
            if url and url not in seen:
                seen.add(url)
                out.append({"url": url, "source_type": entry.get("source_type")})
        return out

    def grouped_entries(self) -> Dict[str, List[dict]]:
        grouped: Dict[str, List[dict]] = defaultdict(list)
        for entry in self.snapshot.get("entries", []):
            grouped[str(entry.get("topic", "other"))].append(entry)
        return dict(grouped)

    def benchmark_vs_platform(self, platform_capabilities: Dict[str, bool]) -> dict:
        baseline = self.snapshot.get("comparison_baseline", {})
        current_strengths = list(
            baseline.get("current_strengths")
            or baseline.get("current_flair_strengths")
            or []
        )
        current_gaps = list(
            baseline.get("current_gaps_observed_or_likely")
            or baseline.get("current_flair_gaps_observed_or_likely")
            or []
        )
        capability_groups = {
            "omnichannel_orchestration": ["web_chat", "sms", "social", "voice", "email"],
            "agentic_resolution": ["booking_changes", "refunds", "disruption_status", "appr_compensation", "baggage", "accessibility", "human_handoff"],
            "operations_visibility": ["analytics_dashboard", "audit_trail", "escalation_queue", "proactive_disruption_monitor"],
            "safety_compliance": ["sentiment_escalation", "appr_rules", "fraud_channel_guidance", "official_channel_citations"],
        }
        scores = {}
        for group, keys in capability_groups.items():
            have = sum(1 for k in keys if platform_capabilities.get(k, False))
            scores[group] = {"implemented": have, "total": len(keys), "percent": round((have / len(keys)) * 100) if keys else 0}
        return {
            "snapshot_date": self.snapshot.get("snapshot_date"),
            "tenant": self.tenant_profile.display_name,
            "current_strengths": current_strengths,
            "current_gaps_observed_or_likely": current_gaps,
            "platform_capability_scores": scores,
            "sources": self._source_index(),
        }
