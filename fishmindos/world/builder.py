from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from fishmindos.world.models import SemanticLocation, SemanticMap, SemanticWorld
from fishmindos.world.store import WorldStore


DOCK_KEYWORDS = ("回充", "充电", "回桩", "dock")


class WorldBuilder:
    """Build or update a semantic world from a single navigation map."""

    def __init__(self, adapter):
        self.adapter = adapter

    def import_map_to_world(
        self,
        world_path: str | Path,
        map_name: Optional[str] = None,
        map_id: Optional[int] = None,
        world_name: Optional[str] = None,
        replace_map_locations: bool = True,
        set_default: bool = True,
    ) -> SemanticWorld:
        store = WorldStore(world_path)
        world = store.load()
        map_info = self._resolve_map(map_name=map_name, map_id=map_id)
        waypoints = self.adapter.list_waypoints(map_info.id)
        existing_locations = self._index_locations(world.locations, map_info.id, map_info.name)

        if world_name:
            world.name = world_name
        elif not world.name:
            world.name = map_info.name

        if replace_map_locations:
            world.locations = [
                item
                for item in world.locations
                if not (
                    item.map_id == map_info.id
                    or (item.map_name and item.map_name == map_info.name)
                )
            ]

        existing_map = next((item for item in world.maps if item.map_id == map_info.id or item.name == map_info.name), None)
        if existing_map is None:
            world.maps.append(SemanticMap(name=map_info.name, map_id=map_info.id))
        else:
            existing_map.name = map_info.name
            existing_map.map_id = map_info.id

        if set_default:
            world.default_map_id = map_info.id
            world.default_map_name = map_info.name

        for waypoint in waypoints:
            location_type = "dock" if self._is_dock_name(waypoint.name) else "waypoint"
            existing = existing_locations.get(self._location_key(map_info.id, map_info.name, waypoint.id, waypoint.name))
            suggested = self._suggest_semantics(waypoint.name, location_type)
            metadata = dict(existing.metadata) if existing else {}
            metadata.update(
                {
                    "x": waypoint.x,
                    "y": waypoint.y,
                    "z": waypoint.z,
                    "yaw": waypoint.yaw,
                    "source": "imported_from_nav_map",
                }
            )
            world.locations.append(
                SemanticLocation(
                    name=waypoint.name,
                    map_name=map_info.name,
                    map_id=map_info.id,
                    waypoint_name=waypoint.name,
                    waypoint_id=waypoint.id,
                    location_type=location_type,
                    description=existing.description if existing and existing.description else suggested["description"],
                    category=existing.category if existing and existing.category else suggested["category"],
                    aliases=list(existing.aliases) if existing and existing.aliases else suggested["aliases"],
                    task_hints=list(existing.task_hints) if existing and existing.task_hints else suggested["task_hints"],
                    relations=list(existing.relations) if existing and existing.relations else suggested["relations"],
                    tags=list(existing.tags) if existing and existing.tags else suggested["tags"],
                    metadata=metadata,
                )
            )

        store.save(world)
        return world

    def _resolve_map(self, map_name: Optional[str], map_id: Optional[int]):
        maps = self.adapter.list_maps()
        if map_id is not None:
            for item in maps:
                if item.id == map_id:
                    return item
        if map_name:
            for item in maps:
                if item.name == map_name:
                    return item
            for item in maps:
                if map_name in item.name or item.name in map_name:
                    return item
        raise ValueError(f"Map not found: map_name={map_name}, map_id={map_id}")

    def _is_dock_name(self, name: str) -> bool:
        lowered = (name or "").lower()
        return any(keyword in lowered or keyword in (name or "") for keyword in DOCK_KEYWORDS)

    def _index_locations(
        self,
        locations,
        map_id: Optional[int],
        map_name: Optional[str],
    ) -> Dict[str, SemanticLocation]:
        indexed: Dict[str, SemanticLocation] = {}
        for item in locations:
            if item.map_id == map_id or (item.map_name and item.map_name == map_name):
                indexed[self._location_key(map_id, map_name, item.waypoint_id, item.waypoint_name or item.name)] = item
        return indexed

    def _location_key(
        self,
        map_id: Optional[int],
        map_name: Optional[str],
        waypoint_id: Optional[int],
        waypoint_name: Optional[str],
    ) -> str:
        return f"{map_id or map_name}:{waypoint_id or waypoint_name}"

    def _suggest_semantics(self, waypoint_name: str, location_type: str) -> Dict[str, object]:
        name = waypoint_name or ""

        if location_type == "dock":
            return {
                "description": "机器人任务结束后返回充电的位置，用于等待回充完成，不作为普通送物终点。",
                "category": "charging",
                "aliases": ["充电点", "回充", "回桩"],
                "task_hints": ["返回充电", "任务结束后回充", "等待回充完成"],
                "relations": [],
                "tags": ["dock", "charging"],
            }

        if name == "大厅":
            return {
                "description": "26层主要公共区域，适合接待、会合、送物到达后播报。",
                "category": "reception",
                "aliases": ["大堂", "门厅", "前厅"],
                "task_hints": ["接待", "会合", "送物", "播报"],
                "relations": [{"type": "after_task_return", "target": "回充点"}],
                "tags": ["public_area"],
            }

        if name == "楼上":
            return {
                "description": "26层里通向上层或楼层切换的过渡点，常用于跨楼层任务衔接。",
                "category": "transition",
                "aliases": ["上楼", "去楼上"],
                "task_hints": ["楼层切换", "跨楼层任务", "前往上层"],
                "relations": [{"type": "transition_to", "target": "其他楼层"}],
                "tags": ["transition"],
            }

        if name.lower() == "deepsleep":
            return {
                "description": "机器人低功耗待机或安静停留位置，适合待命、休眠，不适合作为送物终点。",
                "category": "rest",
                "aliases": ["休眠点", "待机点"],
                "task_hints": ["待命", "休眠", "安静停留"],
                "relations": [{"type": "after_task_return", "target": "回充点"}],
                "tags": ["rest"],
            }

        if name.startswith("巡检点"):
            short_name = name.split("_", 1)[0]
            return {
                "description": "26层巡检路线中的检查点，适合巡逻、巡检、路径经过，不是常规接待点。",
                "category": "patrol",
                "aliases": [short_name],
                "task_hints": ["巡检", "巡逻", "路径经过"],
                "relations": [{"type": "same_route", "target": "巡检路线"}],
                "tags": ["patrol"],
            }

        return {
            "description": "",
            "category": "general",
            "aliases": [],
            "task_hints": [],
            "relations": [],
            "tags": [location_type] if location_type else [],
        }
