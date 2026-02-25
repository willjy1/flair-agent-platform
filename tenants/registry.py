from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class TenantProfile:
    slug: str
    display_name: str
    vertical: str
    category: str
    locale: str = "en-CA"
    support_experience_name: str = "Support"
    customer_capabilities: List[str] = field(default_factory=list)
    channels: List[str] = field(default_factory=list)
    support_commitments: List[str] = field(default_factory=list)
    self_service_options: Dict[str, List[dict]] = field(default_factory=dict)
    citations_by_intent_topics: Dict[str, List[str]] = field(default_factory=dict)
    official_channel_topics: List[str] = field(default_factory=lambda: ["contact"])
    hidden_from_customer_marketing: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TenantProfile":
        return cls(
            slug=str(data["slug"]),
            display_name=str(data["display_name"]),
            vertical=str(data.get("vertical", "travel")),
            category=str(data.get("category", "generic")),
            locale=str(data.get("locale", "en-CA")),
            support_experience_name=str(data.get("support_experience_name", "Support")),
            customer_capabilities=list(data.get("customer_capabilities", [])),
            channels=list(data.get("channels", [])),
            support_commitments=list(data.get("support_commitments", [])),
            self_service_options=dict(data.get("self_service_options", {})),
            citations_by_intent_topics={str(k): list(v) for k, v in dict(data.get("citations_by_intent_topics", {})).items()},
            official_channel_topics=list(data.get("official_channel_topics", ["contact"])),
            hidden_from_customer_marketing=bool(data.get("hidden_from_customer_marketing", True)),
            metadata=dict(data.get("metadata", {})),
        )


class TenantRegistry:
    def __init__(self, profiles_dir: str | Path | None = None) -> None:
        self.profiles_dir = Path(profiles_dir or (Path(__file__).resolve().parent / "profiles"))
        self._cache: Dict[str, TenantProfile] = {}

    def list_profiles(self) -> List[TenantProfile]:
        profiles: List[TenantProfile] = []
        if not self.profiles_dir.exists():
            return profiles
        for path in sorted(self.profiles_dir.glob("*.json")):
            try:
                profiles.append(self.load(path.stem))
            except Exception:
                continue
        return profiles

    def load(self, slug: str = "flair") -> TenantProfile:
        slug = slug.strip().lower()
        if slug in self._cache:
            return self._cache[slug]
        path = self.profiles_dir / f"{slug}.json"
        if not path.exists():
            raise FileNotFoundError(f"tenant profile not found: {slug}")
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        profile = TenantProfile.from_dict(data)
        self._cache[slug] = profile
        return profile

    def try_load(self, slug: str = "flair") -> TenantProfile | None:
        try:
            return self.load(slug)
        except Exception:
            return None

