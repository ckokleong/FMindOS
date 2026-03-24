from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict

from fishmindos.soul.models import SoulMemory, SoulPreference, SoulRule, SoulState


class SoulStore:
    """Load and save long-term Soul state."""

    def __init__(self, path: str | Path, max_memories: int = 200):
        self.path = Path(path)
        self.max_memories = max_memories

    def ensure_exists(self) -> Path:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.default_payload(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        return self.path

    def load(self) -> SoulState:
        self.ensure_exists()
        raw = self.path.read_text(encoding="utf-8").strip()
        data = json.loads(raw or "{}")
        if not isinstance(data, dict):
            data = {}
        return self._from_dict(data)

    def save(self, state: SoulState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": state.version,
            "name": state.name,
            "description": state.description,
            "preferences": {key: asdict(value) for key, value in state.preferences.items()},
            "rules": {key: asdict(value) for key, value in state.rules.items()},
            "memories": [asdict(memory) for memory in state.memories[-self.max_memories:]],
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def default_payload() -> Dict[str, object]:
        return {
            "version": 1,
            "name": "default",
            "description": "FishMindOS 的长期学习与个性化偏好存储。",
            "preferences": {},
            "rules": {},
            "memories": [],
        }

    def _from_dict(self, data: Dict[str, object]) -> SoulState:
        preferences = {}
        for key, item in dict(data.get("preferences", {}) or {}).items():
            if isinstance(item, dict):
                preferences[key] = SoulPreference(
                    key=item.get("key") or key,
                    value=str(item.get("value", "")),
                    confidence=int(item.get("confidence", 1) or 1),
                    source=str(item.get("source", "learned")),
                    notes=str(item.get("notes", "")),
                )

        rules = {}
        for key, item in dict(data.get("rules", {}) or {}).items():
            if isinstance(item, dict):
                rules[key] = SoulRule(
                    name=item.get("name") or key,
                    rule=str(item.get("rule", "")),
                    confidence=int(item.get("confidence", 1) or 1),
                    source=str(item.get("source", "learned")),
                    examples=list(item.get("examples", []) or []),
                )

        memories = []
        for item in list(data.get("memories", []) or []):
            if not isinstance(item, dict):
                continue
            memories.append(
                SoulMemory(
                    summary=str(item.get("summary", "")),
                    user_input=str(item.get("user_input", "")),
                    learned_at=str(item.get("learned_at", "")),
                    tags=list(item.get("tags", []) or []),
                )
            )

        return SoulState(
            version=int(data.get("version", 1) or 1),
            name=str(data.get("name", "default")),
            description=str(data.get("description", "FishMindOS 的长期学习与个性化偏好存储。")),
            preferences=preferences,
            rules=rules,
            memories=memories[-self.max_memories:],
        )
