from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional

from fishmindos.world.models import ResolvedLocation, ResolvedMap, SemanticLocation, SemanticWorld
from fishmindos.world.store import WorldStore


class WorldResolver:
    """Resolve semantic places to concrete map and waypoint targets."""

    DOCK_KEYWORDS = ("回充", "充电", "回桩", "dock")

    def __init__(
        self,
        world: SemanticWorld,
        adapter=None,
        soul=None,
        auto_switch_map: bool = True,
        prefer_current_map: bool = True,
        adapter_fallback: bool = False,
    ):
        self.world = world
        self.adapter = adapter
        self.soul = soul
        self.auto_switch_map = auto_switch_map
        self.prefer_current_map = prefer_current_map
        self.adapter_fallback = adapter_fallback

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        adapter=None,
        soul=None,
        auto_switch_map: bool = True,
        prefer_current_map: bool = True,
        adapter_fallback: bool = False,
    ) -> "WorldResolver":
        store = WorldStore(path)
        world = store.load()
        return cls(
            world=world,
            adapter=adapter,
            soul=soul,
            auto_switch_map=auto_switch_map,
            prefer_current_map=prefer_current_map,
            adapter_fallback=adapter_fallback,
        )

    def set_soul(self, soul) -> None:
        self.soul = soul

    def describe(self) -> str:
        return (
            f"name={self.world.name}, "
            f"default_map={self.world.default_map_name or self.world.default_map_id or 'None'}, "
            f"locations={len(self.world.locations)}"
        )

    def describe_for_prompt(self, limit: int = 20) -> str:
        summary = [
            f"当前 world: {self.world.name}",
            f"world 绑定地图: {self.world.default_map_name or self.world.default_map_id or '未设置'}",
        ]
        if self.world.description:
            summary.append(f"world 描述: {self.world.description}")

        location_lines = []
        for item in self._prompt_locations(limit):
            details = []
            details.append(f"类型:{item.location_type}")
            if item.category:
                details.append(f"类别:{item.category}")
            if item.description:
                details.append(item.description)
            merged_aliases = self._merge_aliases(item.name, item.aliases)
            if merged_aliases:
                details.append(f"别名:{'/'.join(merged_aliases[:4])}")
            if item.task_hints:
                details.append(f"用途:{'/'.join(item.task_hints[:3])}")
            if item.relations:
                relation_text = "/".join(
                    f"{relation.get('type')}->{relation.get('target')}"
                    for relation in item.relations[:2]
                    if relation.get("type") and relation.get("target")
                )
                if relation_text:
                    details.append(f"关系:{relation_text}")
            label = item.name
            if details:
                label += f"（{'；'.join(details)}）"
            location_lines.append(label)

        if location_lines:
            summary.append(f"当前 world 可用地点: {'，'.join(location_lines)}")
        return "\n".join(summary)

    def list_known_locations(self) -> List[str]:
        return [item.name for item in self.world.locations]

    def resolve_return_target(
        self,
        reference_location: Optional[str] = None,
        current_map_id: Optional[int] = None,
        current_map_name: Optional[str] = None,
    ) -> Optional[ResolvedLocation]:
        if reference_location:
            reference = self.resolve_location(
                reference_location,
                current_map_id=current_map_id,
                current_map_name=current_map_name,
            )
            if reference:
                related = self._resolve_return_relation_target(
                    reference.relations,
                    current_map_id=reference.map_id or current_map_id,
                    current_map_name=reference.map_name or current_map_name,
                )
                if related:
                    return related

        return self._resolve_default_dock(current_map_id=current_map_id, current_map_name=current_map_name)

    def resolve_map(self, query: str) -> Optional[ResolvedMap]:
        normalized_query = self._normalize(query)
        if not normalized_query:
            return None

        candidates: List[ResolvedMap] = []
        for item in self.world.maps:
            score = self._score_match(normalized_query, self._iter_names(item.name, item.aliases))
            if score <= 0:
                continue
            candidates.append(
                ResolvedMap(
                    query=query,
                    name=item.name,
                    map_id=item.map_id,
                    source="world",
                    score=score + 20,
                    aliases=list(item.aliases),
                )
            )

        if self.adapter_fallback:
            for map_info in self._list_adapter_maps():
                score = self._score_match(normalized_query, [map_info.name])
                if score <= 0:
                    continue
                candidates.append(
                    ResolvedMap(
                        query=query,
                        name=map_info.name,
                        map_id=map_info.id,
                        source="adapter",
                        score=score,
                        aliases=[],
                    )
                )

        if not candidates:
            return None

        candidates.sort(key=lambda item: (-item.score, item.name))
        return candidates[0]

    def resolve_location(
        self,
        query: str,
        current_map_id: Optional[int] = None,
        current_map_name: Optional[str] = None,
    ) -> Optional[ResolvedLocation]:
        normalized_query = self._normalize(query)
        if not normalized_query:
            return None

        candidates: List[ResolvedLocation] = []
        current_map_name_norm = self._normalize(current_map_name or "")
        default_map_name_norm = self._normalize(self.world.default_map_name or "")
        alias_target = self._resolve_soul_alias_target(query)
        alias_target_norm = self._normalize(alias_target or "")

        for item in self.world.locations:
            names = self._iter_names(item.name, item.aliases)
            score = self._score_match(normalized_query, names)
            source = "world"
            if alias_target_norm:
                alias_score = self._score_match(alias_target_norm, names)
                if alias_score > 0:
                    score = max(score, min(alias_score + 15, 115))
                    source = "soul_alias"
                elif self._normalize(item.name) == alias_target_norm:
                    score = max(score, 95)
                    source = "soul_alias"
            if score <= 0:
                continue
            map_id, map_name = self._resolve_location_map(item)
            if current_map_id is not None and map_id == current_map_id:
                score += 25
            elif current_map_name_norm and self._normalize(map_name or "") == current_map_name_norm:
                score += 20
            elif default_map_name_norm and self._normalize(map_name or "") == default_map_name_norm:
                score += 10
            candidates.append(
                ResolvedLocation(
                    query=query,
                    name=item.name,
                    map_name=map_name,
                    map_id=map_id,
                    waypoint_name=item.waypoint_name or item.name,
                    waypoint_id=item.waypoint_id,
                    location_type=item.location_type or "waypoint",
                    description=item.description,
                    category=item.category,
                    task_hints=list(item.task_hints),
                    relations=list(item.relations),
                    source=source,
                    score=score + 30,
                    metadata=dict(item.metadata),
                )
            )

        dock_requested = self._looks_like_dock(normalized_query)
        if dock_requested:
            map_id, map_name = self._default_target_map(current_map_id, current_map_name)
            candidates.append(
                ResolvedLocation(
                    query=query,
                    name="回充点",
                    map_name=map_name,
                    map_id=map_id,
                    waypoint_name="回充点",
                    waypoint_id=None,
                    location_type="dock",
                    description="机器人默认回充/充电位置",
                    category="charging",
                    task_hints=["返回充电", "等待回充完成"],
                    relations=[],
                    source="dock_keyword",
                    score=150 if (map_id is not None or map_name) else 60,
                    metadata={},
                )
            )

        if self.adapter_fallback:
            for map_info in self._ordered_adapter_maps(current_map_id, current_map_name):
                try:
                    waypoints = self.adapter.list_waypoints(map_info.id) if self.adapter else []
                except Exception:
                    waypoints = []
                for waypoint in waypoints:
                    score = self._score_match(normalized_query, [waypoint.name])
                    if alias_target_norm:
                        alias_score = self._score_match(alias_target_norm, [waypoint.name])
                        if alias_score > 0:
                            score = max(score, min(alias_score + 15, 110))
                    if score <= 0:
                        continue
                    location_type = "dock" if self._looks_like_dock(self._normalize(waypoint.name)) else "waypoint"
                    if current_map_id is not None and map_info.id == current_map_id:
                        score += 25
                    elif default_map_name_norm and self._normalize(map_info.name) == default_map_name_norm:
                        score += 10
                    candidates.append(
                        ResolvedLocation(
                            query=query,
                            name=waypoint.name,
                            map_name=map_info.name,
                            map_id=map_info.id,
                            waypoint_name=waypoint.name,
                            waypoint_id=waypoint.id,
                            location_type=location_type,
                            description="",
                            category="",
                            task_hints=[],
                            relations=[],
                            source="adapter",
                            score=score,
                            metadata={
                                "x": waypoint.x,
                                "y": waypoint.y,
                                "z": waypoint.z,
                                "yaw": waypoint.yaw,
                            },
                        )
                    )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: (
                -item.score,
                0 if item.map_id == current_map_id and current_map_id is not None else 1,
                0 if item.source == "world" else 1,
                item.map_name or "",
                item.name,
            )
        )
        return candidates[0]

    def get_default_map(self) -> Optional[ResolvedMap]:
        if self.world.default_map_id is not None or self.world.default_map_name:
            return ResolvedMap(
                query=self.world.default_map_name or str(self.world.default_map_id),
                name=self.world.default_map_name or str(self.world.default_map_id),
                map_id=self.world.default_map_id,
                source="world_default",
                score=999,
                aliases=[],
            )
        return None

    def _resolve_location_map(self, item: SemanticLocation) -> tuple[Optional[int], Optional[str]]:
        if item.map_id is not None:
            map_name = item.map_name
            if not map_name and self.adapter and hasattr(self.adapter, "get_map"):
                try:
                    map_info = self.adapter.get_map(item.map_id)
                    if map_info:
                        map_name = map_info.name
                except Exception:
                    map_name = None
            return item.map_id, map_name

        if item.map_name:
            resolved = self.resolve_map(item.map_name)
            if resolved:
                return resolved.map_id, resolved.name
            return None, item.map_name

        return self._default_target_map(None, None)

    def _default_target_map(
        self,
        current_map_id: Optional[int],
        current_map_name: Optional[str],
    ) -> tuple[Optional[int], Optional[str]]:
        if current_map_id is not None or current_map_name:
            return current_map_id, current_map_name
        if self.world.default_map_id is not None or self.world.default_map_name:
            return self.world.default_map_id, self.world.default_map_name
        return None, None

    def _resolve_return_relation_target(
        self,
        relations: Iterable[dict],
        current_map_id: Optional[int],
        current_map_name: Optional[str],
    ) -> Optional[ResolvedLocation]:
        for relation in relations or []:
            relation_type = (relation.get("type") or "").strip()
            target = (relation.get("target") or "").strip()
            if relation_type not in {"after_task_return", "default_after_task", "return_to"} or not target:
                continue
            resolved = self.resolve_location(
                target,
                current_map_id=current_map_id,
                current_map_name=current_map_name,
            )
            if resolved:
                return resolved
            if self._looks_like_dock(self._normalize(target)):
                map_id, map_name = self._default_target_map(current_map_id, current_map_name)
                return ResolvedLocation(
                    query=target,
                    name="回充点",
                    map_name=map_name,
                    map_id=map_id,
                    waypoint_name="回充点",
                    waypoint_id=None,
                    location_type="dock",
                    description="机器人默认回充/充电位置",
                    category="charging",
                    task_hints=["返回充电", "等待回充完成"],
                    relations=[],
                    source="world_relation",
                    score=160,
                    metadata={},
                )
        return None

    def _resolve_default_dock(
        self,
        current_map_id: Optional[int],
        current_map_name: Optional[str],
    ) -> Optional[ResolvedLocation]:
        docks = [item for item in self.world.locations if (item.location_type or "waypoint") == "dock"]
        if not docks:
            return None

        current_map_name_norm = self._normalize(current_map_name or "")
        default_map_name_norm = self._normalize(self.world.default_map_name or "")

        def priority(item: SemanticLocation) -> tuple[int, int, str]:
            map_id, map_name = self._resolve_location_map(item)
            if current_map_id is not None and map_id == current_map_id:
                return (0, 0, item.name)
            if current_map_name_norm and self._normalize(map_name or "") == current_map_name_norm:
                return (0, 1, item.name)
            if default_map_name_norm and self._normalize(map_name or "") == default_map_name_norm:
                return (1, 0, item.name)
            return (2, 0, item.name)

        chosen = sorted(docks, key=priority)[0]
        map_id, map_name = self._resolve_location_map(chosen)
        return ResolvedLocation(
            query=chosen.name,
            name=chosen.name,
            map_name=map_name,
            map_id=map_id,
            waypoint_name=chosen.waypoint_name or chosen.name,
            waypoint_id=chosen.waypoint_id,
            location_type=chosen.location_type or "dock",
            description=chosen.description,
            category=chosen.category,
            task_hints=list(chosen.task_hints),
            relations=list(chosen.relations),
            source="world_default_return",
            score=170,
            metadata=dict(chosen.metadata),
        )

    def _ordered_adapter_maps(
        self,
        current_map_id: Optional[int],
        current_map_name: Optional[str],
    ):
        maps = self._list_adapter_maps()
        if not maps:
            return []

        current_map_name_norm = self._normalize(current_map_name or "")
        default_map_name_norm = self._normalize(self.world.default_map_name or "")

        def priority(map_info) -> tuple[int, str]:
            if current_map_id is not None and map_info.id == current_map_id:
                return (0, map_info.name)
            if current_map_name_norm and self._normalize(map_info.name) == current_map_name_norm:
                return (0, map_info.name)
            if default_map_name_norm and self._normalize(map_info.name) == default_map_name_norm:
                return (1, map_info.name)
            return (2, map_info.name)

        return sorted(maps, key=priority)

    def _list_adapter_maps(self):
        if not self.adapter:
            return []
        try:
            return self.adapter.list_maps()
        except Exception:
            return []

    def _iter_names(self, primary: str, aliases: Iterable[str]) -> List[str]:
        names = [primary]
        names.extend(self._merge_aliases(primary, aliases))
        return [name for name in names if name]

    def _merge_aliases(self, primary: str, aliases: Iterable[str]) -> List[str]:
        merged: List[str] = []
        seen = set()
        primary_norm = self._normalize(primary)
        for name in list(aliases) + self._get_soul_aliases_for_target(primary):
            normalized = self._normalize(name)
            if not normalized or normalized == primary_norm or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(name)
        return merged

    def _prompt_locations(self, limit: int) -> List[SemanticLocation]:
        def richness(item: SemanticLocation) -> tuple[int, int, int, int, str]:
            semantic_score = sum(
                1
                for field in (
                    item.description,
                    item.category,
                    item.aliases,
                    item.task_hints,
                    item.relations,
                )
                if field
            )
            dock_bonus = 1 if item.location_type == "dock" else 0
            return (-semantic_score, -dock_bonus, 0 if item.name in {"大厅", "回充点", "楼上"} else 1, 0, item.name)

        locations = list(self.world.locations)
        locations.sort(key=richness)
        return locations[:limit]

    def _score_match(self, normalized_query: str, names: Iterable[str]) -> int:
        best = 0
        for raw_name in names:
            normalized_name = self._normalize(raw_name)
            if not normalized_name:
                continue
            if normalized_name == normalized_query:
                best = max(best, 100)
            elif normalized_query in normalized_name:
                best = max(best, 80)
            elif normalized_name in normalized_query:
                best = max(best, 70)
        return best

    def _looks_like_dock(self, normalized_text: str) -> bool:
        return any(keyword in normalized_text for keyword in self.DOCK_KEYWORDS)

    def _normalize(self, text: str) -> str:
        text = (text or "").strip().lower()
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)

    def _resolve_soul_alias_target(self, query: str) -> Optional[str]:
        if not self.soul or not hasattr(self.soul, "resolve_location_alias"):
            return None
        try:
            return self.soul.resolve_location_alias(query)
        except Exception:
            return None

    def _get_soul_aliases_for_target(self, target: str) -> List[str]:
        if not self.soul or not hasattr(self.soul, "get_location_aliases_for_target"):
            return []
        try:
            return list(self.soul.get_location_aliases_for_target(target) or [])
        except Exception:
            return []
