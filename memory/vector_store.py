from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class PolicyChunk:
    text: str
    metadata: Dict[str, str]


class PolicyVectorStore:
    def __init__(self) -> None:
        self._chunks: List[PolicyChunk] = []

    def ingest(self, documents: List[Dict[str, str]]) -> int:
        count = 0
        for doc in documents:
            text = doc.get("text", "").strip()
            if not text:
                continue
            self._chunks.append(PolicyChunk(text=text, metadata={k: str(v) for k, v in doc.items() if k != "text"}))
            count += 1
        return count

    def query(self, query: str, top_k: int = 5) -> List[Dict[str, str]]:
        q_terms = {t for t in query.lower().split() if t}
        scored: List[tuple[int, PolicyChunk]] = []
        for chunk in self._chunks:
            terms = set(chunk.text.lower().split())
            score = len(q_terms & terms)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"text": c.text, **c.metadata} for _, c in scored[:top_k]]
