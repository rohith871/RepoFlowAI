from __future__ import annotations

from typing import Any

import httpx


class OllamaProvider:
    def __init__(self, base_url: str, model: str, timeout_seconds: float = 8.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def available(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=1.5)
            return response.is_success
        except httpx.HTTPError:
            return False

    def explain(self, question: str, context: list[dict[str, Any]]) -> dict[str, Any] | None:
        prompt = {
            "question": question,
            "instruction": "Answer only from the supplied evidence. Return JSON with answer, claims, assumptions, unresolved_questions. Every claim must include evidence_ids.",
            "evidence": context,
        }
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "stream": False, "format": "json", "messages": [{"role": "user", "content": str(prompt)}]},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload.get("message", {}).get("content")
            if not isinstance(content, str):
                return None
            import json
            result = json.loads(content)
            if not isinstance(result, dict) or not isinstance(result.get("answer"), str):
                return None
            return result
        except (httpx.HTTPError, ValueError, TypeError):
            return None
