"""Built-in navigation skills."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from fishmindos.core.models import SkillContext, SkillResult
from fishmindos.skills.base import Skill


DOCK_KEYWORDS = ("回充", "充电", "回桩", "dock")


def _get_world_resolver(context: SkillContext):
    resolver = context.get("world") or getattr(context, "world_model", None)
    if resolver and hasattr(resolver, "resolve_location"):
        return resolver
    return None


def _set_current_map(context: SkillContext, map_id: Optional[int], map_name: Optional[str]) -> None:
    if map_id is None and not map_name:
        return
    context.set("current_map", {"id": map_id, "name": map_name or str(map_id)})


def _ensure_current_map(adapter, context: SkillContext) -> Dict[str, Any]:
    current_map = context.get("current_map")
    if isinstance(current_map, dict) and (current_map.get("id") is not None or current_map.get("name")):
        return current_map

    if not adapter:
        return {}

    map_info = None
    if hasattr(adapter, "resolve_current_map"):
        try:
            map_info = adapter.resolve_current_map()
        except Exception:
            map_info = None

    if map_info is None:
        try:
            nav_status = adapter.get_navigation_status()
            map_id = nav_status.get("current_map_id") or nav_status.get("map_id")
            if map_id is not None and hasattr(adapter, "get_map"):
                map_info = adapter.get_map(map_id)
        except Exception:
            map_info = None

    if not map_info:
        return {}

    resolved = {"id": map_info.id, "name": map_info.name}
    context.set("current_map", resolved)
    return resolved


def _match_map_from_adapter(all_maps, map_name: str):
    for item in all_maps:
        if item.name == map_name:
            return item

    for item in all_maps:
        if map_name in item.name or item.name in map_name:
            return item

    input_numbers = re.findall(r"\d+", map_name or "")
    if input_numbers:
        for item in all_maps:
            map_numbers = re.findall(r"\d+", item.name)
            if any(num in map_numbers for num in input_numbers):
                return item

    clean_input = re.sub(r"[^\w\d\u4e00-\u9fff]", "", map_name or "")
    if clean_input:
        for item in all_maps:
            clean_map = re.sub(r"[^\w\d\u4e00-\u9fff]", "", item.name)
            if clean_input in clean_map or clean_map in clean_input:
                return item

    return None


def _resolve_world_default_map(adapter, context: SkillContext) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    resolver = _get_world_resolver(context)
    if not resolver or not hasattr(resolver, "get_default_map"):
        return None, None, None

    resolved_default = resolver.get_default_map()
    if not resolved_default:
        return None, None, None

    map_id = resolved_default.map_id
    map_name = resolved_default.name

    if map_id is None and map_name and adapter:
        try:
            matched = _match_map_from_adapter(adapter.list_maps(), map_name)
        except Exception:
            matched = None
        if matched:
            map_id = matched.id
            map_name = matched.name

    return map_id, map_name, getattr(resolved_default, "source", "world_default")


def _format_known_locations(resolver, limit: int = 12) -> str:
    if resolver is None or not hasattr(resolver, "list_known_locations"):
        return ""
    names = [name for name in resolver.list_known_locations() if name]
    if not names:
        return ""
    shown = names[:limit]
    suffix = " 等" if len(names) > limit else ""
    return ", ".join(shown) + suffix


class StartNavigationSkill(Skill):
    """Start navigation on a map."""

    name = "nav_start"
    description = "在指定地图上启动导航。启用 world 时，不传参数会默认启动当前 world 绑定地图。"
    category = "navigation"

    parameters = {
        "type": "object",
        "properties": {
            "map_name": {"type": "string", "description": "地图名称"},
            "map_id": {"type": "integer", "description": "地图 ID"},
        },
        "required": [],
    }

    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        map_name = params.get("map_name")
        map_id = params.get("map_id")

        if not self.adapter:
            return SkillResult(False, "适配器未设置")

        try:
            all_maps = self.adapter.list_maps()
        except Exception:
            all_maps = []

        resolver = _get_world_resolver(context)
        world_default_used = False

        if map_name is None and map_id is None:
            default_map_id, default_map_name, _ = _resolve_world_default_map(self.adapter, context)
            if default_map_id is not None or default_map_name:
                map_id = default_map_id
                map_name = default_map_name
                world_default_used = True

        if map_name is None and map_id is None:
            current_map = context.get("current_map")
            if isinstance(current_map, dict):
                map_id = current_map.get("id")
                map_name = current_map.get("name")

        if map_name and map_id is None and resolver and hasattr(resolver, "resolve_map"):
            resolved_map = resolver.resolve_map(map_name)
            if resolved_map:
                map_id = resolved_map.map_id
                map_name = resolved_map.name

        if map_id is not None and not map_name and hasattr(self.adapter, "get_map"):
            try:
                map_info = self.adapter.get_map(map_id)
            except Exception:
                map_info = None
            if map_info:
                map_name = map_info.name

        if map_name and map_id is None:
            matched = _match_map_from_adapter(all_maps, map_name)
            if matched:
                map_id = matched.id
                map_name = matched.name

        if map_name is None and map_id is None:
            if resolver and not getattr(resolver, "adapter_fallback", False):
                world_name = getattr(getattr(resolver, "world", None), "name", "default")
                return SkillResult(
                    False,
                    f"当前 world '{world_name}' 尚未绑定默认地图，请先导入一张地图到 world 或显式传入 map_name。",
                )

            available_maps = [item.name for item in all_maps[:10]]
            available_text = ", ".join(available_maps) if available_maps else "无"
            return SkillResult(
                False,
                f"未指定地图。请传入 map_name，或先确认当前地图。可用地图: {available_text}",
                {"available_maps": available_maps},
            )

        if map_id is None:
            if resolver and not getattr(resolver, "adapter_fallback", False):
                world_name = getattr(getattr(resolver, "world", None), "name", "default")
                return SkillResult(
                    False,
                    f"当前 world '{world_name}' 中未找到地图 '{map_name}'。",
                    {"requested": map_name},
                )

            available_maps = [item.name for item in all_maps[:10]]
            available_text = ", ".join(available_maps) if available_maps else "无"
            return SkillResult(
                False,
                f"未找到地图 '{map_name}'。可用地图: {available_text}",
                {"available_maps": available_maps, "requested": map_name},
            )

        success = self.adapter.start_navigation(map_id)
        if not success:
            return SkillResult(False, "启动导航失败")

        # 【核心修改 1】强制等待底层导航服务彻底启动就绪
        is_ready = self.adapter.wait_nav_started(timeout=30)
        if not is_ready:
            return SkillResult(False, "启动导航超时，底层导航服务未就绪")

        actual_map_name = map_name or str(map_id)
        _set_current_map(context, map_id, actual_map_name)

        message = f"已在地图 {actual_map_name} 上启动导航"
        if world_default_used:
            message = f"已按当前 world 默认地图启动导航: {actual_map_name}"
        return SkillResult(
            True,
            message,
            {"map_id": map_id, "map_name": actual_map_name, "world_default_used": world_default_used},
        )


class StopNavigationSkill(Skill):
    """Stop navigation."""

    name = "nav_stop"
    description = "停止当前导航"
    category = "navigation"

    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        return SkillResult(True, "已停止导航") if self.adapter.stop_navigation() else SkillResult(False, "停止导航失败")


class GoToWaypointSkill(Skill):
    """Navigate to a waypoint on the current map."""

    name = "nav_goto_waypoint"
    description = "导航到指定路点"
    category = "navigation"

    parameters = {
        "type": "object",
        "properties": {
            "waypoint_name": {"type": "string", "description": "路点名称"},
            "waypoint_id": {"type": "integer", "description": "路点 ID"},
        },
        "required": [],
    }

    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        waypoint_name = params.get("waypoint_name")
        waypoint_id = params.get("waypoint_id")

        if not self.adapter:
            return SkillResult(False, "适配器未设置")

        if waypoint_name and waypoint_id is None:
            current_map = _ensure_current_map(self.adapter, context)
            map_id = current_map.get("id") if current_map else None
            if map_id is not None:
                for wp in self.adapter.list_waypoints(map_id):
                    if wp.name == waypoint_name or waypoint_name in wp.name or wp.name in waypoint_name:
                        waypoint_id = wp.id
                        waypoint_name = wp.name
                        break

        if waypoint_id is None:
            return SkillResult(False, "请指定有效的路点名称或 ID")

        success = self.adapter.goto_waypoint(waypoint_id)
        if not success:
            return SkillResult(False, "前往路点失败")

        pending = {"waypoint_id": waypoint_id, "name": waypoint_name or ""}
        context.set("pending_arrival", pending)
        context.set("last_waypoint", pending)
        return SkillResult(True, "正在前往路点", {"waypoint_id": waypoint_id, "waypoint_name": waypoint_name})


class GoToLocationSkill(Skill):
    """Navigate using semantic locations."""

    name = "nav_goto_location"
    description = "前往指定位置。启用 world 时会优先按当前 world 解析地点，并按 world 绑定地图自动切图。"
    category = "navigation"

    parameters = {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "位置名称"},
            "location_type": {
                "type": "string",
                "enum": ["waypoint", "dock", "coordinate"],
                "description": "位置类型",
            },
        },
        "required": ["location"],
    }

    def _start_navigation_if_needed(
        self,
        context: SkillContext,
        target_map_id: Optional[int],
        target_map_name: Optional[str],
    ) -> tuple[bool, bool]:
        if not self.adapter:
            return False, False

        if target_map_id is None and target_map_name:
            try:
                matched = _match_map_from_adapter(self.adapter.list_maps(), target_map_name)
            except Exception:
                matched = None
            if matched:
                target_map_id = matched.id
                target_map_name = matched.name

        if target_map_id is None:
            current_map = _ensure_current_map(self.adapter, context)
            if current_map:
                _set_current_map(context, current_map.get("id"), current_map.get("name"))
                return True, False
            return True, False

        current_map = _ensure_current_map(self.adapter, context)
        current_map_id = current_map.get("id") if current_map else None

        if current_map_id == target_map_id:
            _set_current_map(context, target_map_id, target_map_name)
            return True, False

        resolver = _get_world_resolver(context)
        if resolver and not getattr(resolver, "auto_switch_map", True) and current_map_id is not None:
            return False, False

        success = self.adapter.start_navigation(target_map_id)
        if success:
            # 【核心修改 2】自动切图时，也必须等待新地图的导航服务就绪
            is_ready = self.adapter.wait_nav_started(timeout=30)
            if not is_ready:
                # 如果没就绪，返回失败，阻止后续发出移动指令
                return False, False
                
            _set_current_map(context, target_map_id, target_map_name)
            return True, True
        return False, False

    def _navigate_to_waypoint(
        self,
        context: SkillContext,
        waypoint_id: int,
        waypoint_name: str,
        map_id: Optional[int],
        map_name: Optional[str],
        auto_switched: bool = False,
        resolved_from: str = "map",
    ) -> SkillResult:
        success = self.adapter.goto_waypoint(waypoint_id)
        if not success:
            return SkillResult(False, f"前往 {waypoint_name} 失败")

        pending = {"waypoint_id": waypoint_id, "name": waypoint_name}
        context.set("pending_arrival", pending)
        context.set("last_waypoint", pending)
        _set_current_map(context, map_id, map_name)

        detail = f"正在前往 {waypoint_name}"
        if auto_switched and map_name:
            detail = f"已自动切换到地图 {map_name}，正在前往 {waypoint_name}"

        return SkillResult(
            True,
            detail,
            {
                "waypoint_id": waypoint_id,
                "waypoint_name": waypoint_name,
                "location": waypoint_name,
                "map_id": map_id,
                "map_name": map_name,
                "resolved_from": resolved_from,
                "auto_started_navigation": auto_switched,
            },
        )

    def _resolve_location(self, location: str, context: SkillContext):
        resolver = _get_world_resolver(context)
        if resolver is None:
            return None

        current_map = _ensure_current_map(self.adapter, context)
        current_map_id = current_map.get("id") if current_map else None
        current_map_name = current_map.get("name") if current_map else None
        return resolver.resolve_location(location, current_map_id=current_map_id, current_map_name=current_map_name)

    def _goto_resolved_location(self, resolved, context: SkillContext) -> SkillResult:
        target_map_id = getattr(resolved, "map_id", None)
        target_map_name = getattr(resolved, "map_name", None)
        location_type = getattr(resolved, "location_type", "waypoint")

        if location_type == "dock":
            return self._goto_dock(context, resolved)

        ok, auto_switched = self._start_navigation_if_needed(context, target_map_id, target_map_name)
        if not ok:
            target_label = target_map_name or str(target_map_id)
            return SkillResult(False, f"当前禁止自动切图，请先切换到地图 {target_label}")

        waypoint_id = getattr(resolved, "waypoint_id", None)
        waypoint_name = getattr(resolved, "waypoint_name", None) or getattr(resolved, "name", None)

        if waypoint_id is None and target_map_id is not None and waypoint_name:
            for wp in self.adapter.list_waypoints(target_map_id):
                if wp.name == waypoint_name or waypoint_name in wp.name or wp.name in waypoint_name:
                    waypoint_id = wp.id
                    waypoint_name = wp.name
                    break

        if waypoint_id is None or not waypoint_name:
            return SkillResult(False, f"已命中语义地点 '{getattr(resolved, 'name', '目标点')}'，但未找到可用路点")

        return self._navigate_to_waypoint(
            context,
            waypoint_id=waypoint_id,
            waypoint_name=waypoint_name,
            map_id=target_map_id,
            map_name=target_map_name,
            auto_switched=auto_switched,
            resolved_from=getattr(resolved, "source", "world"),
        )

    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        location = params.get("location")
        location_type = params.get("location_type", "waypoint")

        if not location:
            return SkillResult(False, "请提供目标位置 (location)")
        if not self.adapter:
            return SkillResult(False, "适配器未设置")

        resolver = _get_world_resolver(context)
        resolved = self._resolve_location(location, context)
        is_dock = location_type == "dock" or any(keyword in location for keyword in DOCK_KEYWORDS)

        if resolved is not None:
            if getattr(resolved, "location_type", "waypoint") == "dock" or is_dock:
                return self._goto_dock(context, resolved)
            return self._goto_resolved_location(resolved, context)

        if resolver and not getattr(resolver, "adapter_fallback", False):
            known_locations = _format_known_locations(resolver)
            world_name = getattr(getattr(resolver, "world", None), "name", "default")
            if is_dock:
                default_map = resolver.get_default_map() if hasattr(resolver, "get_default_map") else None
                if default_map and (default_map.map_id is not None or default_map.name):
                    return self._goto_dock(context, default_map)
            detail = f"当前 world '{world_name}' 中未找到位置 '{location}'"
            if known_locations:
                detail += f"。当前 world 可用地点: {known_locations}"
            return SkillResult(False, detail, {"requested": location, "world": world_name})

        if is_dock:
            return self._goto_dock(context)

        current_map = _ensure_current_map(self.adapter, context)
        if not current_map:
            return SkillResult(False, "未加载地图，请先调用 nav_start 加载地图")

        map_id = current_map.get("id")
        waypoints = self.adapter.list_waypoints(map_id)

        for wp in waypoints:
            if wp.name == location:
                return self._navigate_to_waypoint(
                    context,
                    waypoint_id=wp.id,
                    waypoint_name=wp.name,
                    map_id=map_id,
                    map_name=current_map.get("name"),
                )

        for wp in waypoints:
            if location in wp.name or wp.name in location:
                return self._navigate_to_waypoint(
                    context,
                    waypoint_id=wp.id,
                    waypoint_name=wp.name,
                    map_id=map_id,
                    map_name=current_map.get("name"),
                )

        available = [wp.name for wp in waypoints[:10]]
        return SkillResult(
            False,
            f"未找到位置 '{location}'。该地图可用路点: {', '.join(available)}",
            {"available_waypoints": available, "requested": location, "map_id": map_id},
        )

    def _goto_dock(self, context: SkillContext, resolved=None) -> SkillResult:
        if not self.adapter:
            return SkillResult(False, "适配器未设置")

        target_map_id = getattr(resolved, "map_id", None) if resolved is not None else None
        target_map_name = getattr(resolved, "map_name", None) if resolved is not None else None

        ok, auto_switched = self._start_navigation_if_needed(context, target_map_id, target_map_name)
        if not ok:
            target_label = target_map_name or str(target_map_id)
            return SkillResult(False, f"当前禁止自动切图，请先切换到地图 {target_label}")

        current_map = _ensure_current_map(self.adapter, context)
        map_id = target_map_id if target_map_id is not None else (current_map.get("id") if current_map else None)
        success = self.adapter.goto_dock(map_id=map_id)
        if not success:
            return SkillResult(False, "前往回充点失败，请检查回充点是否可用")

        detail = "正在前往回充点"
        if auto_switched and target_map_name:
            detail = f"已自动切换到地图 {target_map_name}，正在前往回充点"

        return SkillResult(
            True,
            detail,
            {
                "location": "回充点",
                "location_type": "dock",
                "map_id": map_id,
                "map_name": target_map_name or (current_map.get("name") if current_map else None),
                "resolved_from": getattr(resolved, "source", "direct") if resolved is not None else "direct",
                "auto_started_navigation": auto_switched,
            },
        )


class GetNavigationStatusSkill(Skill):
    """Get navigation status."""

    name = "nav_get_status"
    description = "获取当前导航状态"
    category = "navigation"

    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        if not self.adapter:
            return SkillResult(False, "适配器未设置")

        status = self.adapter.get_navigation_status()
        nav_running = status.get("nav_running", False)
        if nav_running:
            return SkillResult(True, "正在导航中", status)
        return SkillResult(True, "当前未在导航", status)


class ListMapsSkill(Skill):
    """List maps."""

    name = "nav_list_maps"
    description = "获取所有可用地图列表"
    category = "navigation"

    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        if not self.adapter:
            return SkillResult(False, "适配器未设置")

        maps = self.adapter.list_maps()
        map_list = [{"id": item.id, "name": item.name} for item in maps]
        if map_list:
            names = [item["name"] for item in map_list[:5]]
            suffix = " 等" if len(map_list) > 5 else ""
            message = f"找到 {len(map_list)} 张地图: {', '.join(names)}{suffix}"
        else:
            message = "没有找到地图"

        return SkillResult(True, message, {"maps": map_list})


class ListWaypointsSkill(Skill):
    """List waypoints for a map."""

    name = "nav_list_waypoints"
    description = "获取指定地图的所有路点"
    category = "navigation"

    parameters = {
        "type": "object",
        "properties": {
            "map_name": {"type": "string", "description": "地图名称"},
        },
        "required": [],
    }

    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        map_name = params.get("map_name")

        if not self.adapter:
            return SkillResult(False, "适配器未设置")

        map_id = None
        resolver = _get_world_resolver(context)

        if map_name and resolver and hasattr(resolver, "resolve_map"):
            resolved_map = resolver.resolve_map(map_name)
            if resolved_map:
                map_id = resolved_map.map_id
                map_name = resolved_map.name

        if map_id is None and map_name:
            maps = self.adapter.list_maps()
            matched = _match_map_from_adapter(maps, map_name)
            if matched:
                map_id = matched.id
                map_name = matched.name

        if map_id is None:
            default_map_id, default_map_name, _ = _resolve_world_default_map(self.adapter, context)
            if default_map_id is not None or default_map_name:
                map_id = default_map_id
                map_name = default_map_name

        if map_id is None:
            current_map = _ensure_current_map(self.adapter, context)
            if current_map:
                map_id = current_map.get("id")
                map_name = current_map.get("name")

        if map_id is None:
            return SkillResult(False, "请指定地图名称，或先为当前 world 绑定默认地图")

        waypoints = self.adapter.list_waypoints(map_id)
        wp_list = [{"id": wp.id, "name": wp.name, "x": wp.x, "y": wp.y} for wp in waypoints]
        if wp_list:
            names = [wp["name"] for wp in wp_list[:5]]
            suffix = " 等" if len(wp_list) > 5 else ""
            message = f"找到 {len(wp_list)} 个路点: {', '.join(names)}{suffix}"
        else:
            message = "没有找到路点"

        context.set("last_waypoint_list", wp_list)
        return SkillResult(True, message, {"waypoints": wp_list, "map_id": map_id, "map_name": map_name})
