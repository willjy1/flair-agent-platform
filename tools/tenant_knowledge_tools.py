from __future__ import annotations

import json
import os
import re
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
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        if os.path.isdir(data_dir):
            prefix = f"{tenant_slug}_public_support_snapshot_"
            matches = sorted(
                [name for name in os.listdir(data_dir) if name.startswith(prefix) and name.endswith(".json")]
            )
            if matches:
                return os.path.join(data_dir, matches[-1])
        return os.path.join(data_dir, f"{tenant_slug}_public_support_snapshot_2026-02-25.json")

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
            "knowledge_consistency": self.consistency_report(),
        }

    def consistency_report(self) -> dict:
        entries = list(self.snapshot.get("entries", []) or [])
        if not entries:
            return {
                "snapshot_date": self.snapshot.get("snapshot_date"),
                "ok": True,
                "potential_conflicts": [],
                "checks_run": ["phone_numbers", "support_hours"],
            }

        contact_entries = [
            e for e in entries
            if str(e.get("topic", "")).lower() in {"contact", "official_channels", "accessibility", "support", "customer_service", "help"}
            or any(t in {"contact", "support", "accessibility"} for t in [str(x).lower() for x in (e.get("tags") or [])])
        ]
        if not contact_entries:
            contact_entries = entries

        phone_groups: Dict[str, Dict[str, List[dict]]] = {"general": defaultdict(list), "accessibility": defaultdict(list)}
        hour_groups: Dict[str, List[dict]] = defaultdict(list)
        for entry in contact_entries:
            text = " ".join(
                [
                    str(entry.get("id") or ""),
                    str(entry.get("topic") or ""),
                    str(entry.get("text") or ""),
                ]
            )
            normalized_text = text.lower()
            group = "accessibility" if any(k in normalized_text for k in ["accessib", "wheelchair", "special assistance"]) else "general"
            for number in self._extract_phone_numbers(text):
                phone_groups[group][number].append(entry)
            for hours in self._extract_support_hours_phrases(text):
                hour_groups[hours].append(entry)

        conflicts: List[dict] = []
        for group, numbers in phone_groups.items():
            if len(numbers) > 1:
                # Multiple numbers can be valid; flag only when multiple general support numbers appear.
                if group == "general":
                    conflicts.append(
                        {
                            "type": "phone_number_variants",
                            "severity": "medium",
                            "contact_type": group,
                            "values": sorted(numbers.keys()),
                            "sources": self._dedupe_sources([e for vals in numbers.values() for e in vals])[:8],
                            "summary": "Multiple general support phone numbers appear across public support sources.",
                        }
                    )

        if len(hour_groups) > 1:
            conflicts.append(
                {
                    "type": "support_hours_variants",
                    "severity": "medium",
                    "values": sorted(hour_groups.keys()),
                    "sources": self._dedupe_sources([e for vals in hour_groups.values() for e in vals])[:10],
                    "summary": "Support-hour wording differs across public support sources and may confuse customers.",
                }
            )

        return {
            "snapshot_date": self.snapshot.get("snapshot_date"),
            "ok": len(conflicts) == 0,
            "checks_run": ["phone_numbers", "support_hours"],
            "potential_conflicts": conflicts,
        }

    def _extract_phone_numbers(self, text: str) -> List[str]:
        out: List[str] = []
        for match in re.finditer(r"(?:\+?1[\s\-\.]?)?(?:\(?\d{3}\)?[\s\-\.]?)\d{3}[\s\-\.]?\d{4}", text):
            raw = match.group(0)
            digits = "".join(ch for ch in raw if ch.isdigit())
            if len(digits) == 10:
                norm = f"1-{digits[:3]}-{digits[3:6]}-{digits[6:]}"
            elif len(digits) == 11 and digits.startswith("1"):
                norm = f"1-{digits[1:4]}-{digits[4:7]}-{digits[7:]}"
            else:
                continue
            if norm not in out:
                out.append(norm)
        return out

    def _extract_support_hours_phrases(self, text: str) -> List[str]:
        lower = str(text or "").lower()
        phrases: List[str] = []
        # Common patterns: "24/7", "7am to 9pm", "Mon-Fri 8am-6pm", "Monday to Friday"
        if "24/7" in lower or "24 hours" in lower:
            phrases.append("24/7")
        for pattern in [
            r"(mon(?:day)?\s*[-to]+\s*fri(?:day)?[^.;\n]{0,45}(?:am|pm))",
            r"(mon(?:day)?\s*[-to]+\s*sun(?:day)?[^.;\n]{0,55}(?:am|pm))",
            r"(\b\d{1,2}\s*(?::\d{2})?\s*(?:am|pm)\s*(?:to|-)\s*\d{1,2}\s*(?::\d{2})?\s*(?:am|pm)\b)",
            r"(\b\d{1,2}\s*(?:am|pm)\s*-\s*\d{1,2}\s*(?:am|pm)\b)",
        ]:
            for m in re.finditer(pattern, lower):
                phrase = re.sub(r"\s+", " ", m.group(1).strip())
                if phrase and phrase not in phrases:
                    phrases.append(phrase)
        return phrases

    def _dedupe_sources(self, entries: List[dict]) -> List[dict]:
        seen = set()
        out: List[dict] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            url = str(entry.get("source_url") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(
                {
                    "source_url": url,
                    "topic": entry.get("topic"),
                    "id": entry.get("id"),
                    "source_type": entry.get("source_type"),
                }
            )
        return out
