from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SoulPreference:
    key: str
    value: str
    confidence: int = 1
    source: str = "learned"
    notes: str = ""


@dataclass
class SoulRule:
    name: str
    rule: str
    confidence: int = 1
    source: str = "learned"
    examples: List[str] = field(default_factory=list)


@dataclass
class SoulMemory:
    summary: str
    user_input: str = ""
    learned_at: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class SoulState:
    version: int = 1
    name: str = "default"
    description: str = "FishMindOS 的长期学习与个性化偏好存储。"
    preferences: Dict[str, SoulPreference] = field(default_factory=dict)
    rules: Dict[str, SoulRule] = field(default_factory=dict)
    memories: List[SoulMemory] = field(default_factory=list)
