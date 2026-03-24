from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fishmindos.world.models import SemanticLocation, SemanticMap, SemanticWorld


class WorldStore:
    """Load and save semantic world data from JSON."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def ensure_exists(self) -> Path:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.default_payload(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        return self.path

    def load(self) -> SemanticWorld:
        self.ensure_exists()
        raw = self.path.read_text(encoding="utf-8").strip()
        data = json.loads(raw or "{}")
        if not isinstance(data, dict):
            data = {}
        return self._from_dict(data)

    def save(self, world: SemanticWorld) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "name": world.name,
            "description": world.description,
            "default_map_name": world.default_map_name,
            "default_map_id": world.default_map_id,
            "maps": [
                {
                    "name": item.name,
                    "map_id": item.map_id,
                    "aliases": item.aliases,
                    "description": item.description,
                }
                for item in world.maps
            ],
            "locations": [
                {
                    "name": item.name,
                    "map_name": item.map_name,
                    "map_id": item.map_id,
                    "waypoint_name": item.waypoint_name,
                    "waypoint_id": item.waypoint_id,
                    "location_type": item.location_type,
                    "description": item.description,
                    "category": item.category,
                    "aliases": item.aliases,
                    "task_hints": item.task_hints,
                    "relations": item.relations,
                    "tags": item.tags,
                    "metadata": item.metadata,
                }
                for item in world.locations
            ],
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def default_payload() -> Dict[str, Any]:
        return {
            "name": "default",
            "description": "",
            "default_map_name": None,
            "default_map_id": None,
            "maps": [],
            "locations": [],
        }

    def _from_dict(self, data: Dict[str, Any]) -> SemanticWorld:
        maps = []
        for item in data.get("maps", []) or []:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            maps.append(
                SemanticMap(
                    name=item["name"],
                    map_id=item.get("map_id"),
                    aliases=list(item.get("aliases", []) or []),
                    description=item.get("description", "") or "",
                )
            )

        locations = []
        for item in data.get("locations", []) or []:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            locations.append(
                SemanticLocation(
                    name=item["name"],
                    map_name=item.get("map_name"),
                    map_id=item.get("map_id"),
                    waypoint_name=item.get("waypoint_name"),
                    waypoint_id=item.get("waypoint_id"),
                    location_type=item.get("location_type", "waypoint") or "waypoint",
                    description=item.get("description", "") or "",
                    category=item.get("category", "") or "",
                    aliases=list(item.get("aliases", []) or []),
                    task_hints=list(item.get("task_hints", []) or []),
                    relations=[
                        relation
                        for relation in list(item.get("relations", []) or [])
                        if isinstance(relation, dict) and relation.get("type") and relation.get("target")
                    ],
                    tags=list(item.get("tags", []) or []),
                    metadata=dict(item.get("metadata", {}) or {}),
                )
            )

        return SemanticWorld(
            name=data.get("name") or "default",
            description=data.get("description", "") or "",
            default_map_name=data.get("default_map_name"),
            default_map_id=data.get("default_map_id"),
            maps=maps,
            locations=locations,
        )
