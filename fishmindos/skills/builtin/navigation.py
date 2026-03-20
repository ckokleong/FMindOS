"""
导航相关技能
"""

import re
from typing import Any, Dict
from fishmindos.core.models import SkillContext, SkillResult
from fishmindos.skills.base import Skill, MacroSkill


class StartNavigationSkill(Skill):
    """启动导航技能"""
    name = "nav_start"
    description = "在指定地图上启动导航系统"
    category = "navigation"
    
    parameters = {
        "type": "object",
        "properties": {
            "map_name": {
                "type": "string",
                "description": "地图名称"
            },
            "map_id": {
                "type": "integer",
                "description": "地图ID"
            }
        },
        "required": []
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        map_name = params.get("map_name")
        map_id = params.get("map_id")
        
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        # 先获取所有地图列表
        all_maps = self.adapter.list_maps()
        
        # 如果没有提供任何参数，优先复用当前上下文中的地图
        if not map_name and map_id is None:
            current_map = context.get("current_map")
            if isinstance(current_map, dict):
                map_id = current_map.get("id")
                map_name = current_map.get("name")

        if not map_name and map_id is None:
            available_maps = [m.name for m in all_maps[:10]] if all_maps else []
            available_str = ", ".join(available_maps) if available_maps else "无"
            return SkillResult(
                False,
                f"未指定地图。请先提供 map_name，或先确认当前地图。可用地图：{available_str}",
                {"available_maps": available_maps}
            )
        
        # 如果提供了地图名，先查找地图ID
        if map_name and not map_id:
            # 方法1：完全匹配
            for m in all_maps:
                if m.name == map_name:
                    map_id = m.id
                    break
            
            # 方法2：包含匹配（"26层"包含在"26层大厅"中）
            if not map_id:
                for m in all_maps:
                    if map_name in m.name:
                        map_id = m.id
                        break
            
            # 方法3：反向包含（"26层大厅"包含在"26层"中）
            if not map_id:
                for m in all_maps:
                    if m.name in map_name:
                        map_id = m.id
                        break
            
            # 方法4：提取数字匹配（如"26层"->匹配包含26的地图）
            if not map_id:
                # 提取用户输入中的所有数字
                input_numbers = re.findall(r'\d+', map_name)
                if input_numbers:
                    for m in all_maps:
                        map_numbers = re.findall(r'\d+', m.name)
                        # 检查是否有共同数字
                        if any(num in map_numbers for num in input_numbers):
                            map_id = m.id
                            map_name = m.name  # 使用实际地图名
                            break
            
            # 方法5：模糊匹配（忽略空格和特殊字符）
            if not map_id:
                clean_input = re.sub(r'[^\w\d]', '', map_name)
                for m in all_maps:
                    clean_map = re.sub(r'[^\w\d]', '', m.name)
                    if clean_input in clean_map or clean_map in clean_input:
                        map_id = m.id
                        map_name = m.name
                        break
        
        if not map_id:
            # 返回可用地图列表帮助用户选择
            available_maps = [m.name for m in all_maps[:10]] if all_maps else []
            available_str = ", ".join(available_maps) if available_maps else "无"
            return SkillResult(
                False, 
                f"未找到地图 '{map_name}'。可用地图：{available_str}",
                {"available_maps": available_maps, "requested": map_name}
            )
        
        success = self.adapter.start_navigation(map_id)
        if success:
            # 保存当前地图到上下文
            actual_map_name = map_name or str(map_id)
            context.set("current_map", {"id": map_id, "name": actual_map_name})
            return SkillResult(True, f"已在地图 {actual_map_name} 上启动导航", {"map_id": map_id, "map_name": actual_map_name})
        else:
            return SkillResult(False, "启动导航失败")


class StopNavigationSkill(Skill):
    """停止导航技能"""
    name = "nav_stop"
    description = "停止当前导航"
    category = "navigation"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        success = self.adapter.stop_navigation()
        if success:
            return SkillResult(True, "已停止导航")
        else:
            return SkillResult(False, "停止导航失败")


class GoToWaypointSkill(Skill):
    """前往路点技能"""
    name = "nav_goto_waypoint"
    description = "导航到指定路点"
    category = "navigation"
    
    parameters = {
        "type": "object",
        "properties": {
            "waypoint_name": {
                "type": "string",
                "description": "路点名称"
            },
            "waypoint_id": {
                "type": "integer",
                "description": "路点ID"
            }
        },
        "required": []
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        waypoint_name = params.get("waypoint_name")
        waypoint_id = params.get("waypoint_id")
        
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        # 如果提供了路点名，先查找路点ID
        if waypoint_name and not waypoint_id:
            current_map = context.get("current_map")
            if current_map:
                map_id = current_map.get("id")
                waypoints = self.adapter.list_waypoints(map_id)
                for wp in waypoints:
                    if wp.name == waypoint_name or waypoint_name in wp.name:
                        waypoint_id = wp.id
                        break
        
        if not waypoint_id:
            return SkillResult(False, "请指定有效的路点名称或ID")
        
        success = self.adapter.goto_waypoint(waypoint_id)
        if success:
            waypoint = self.adapter.get_waypoint(waypoint_id)
            context.set("last_waypoint", {"id": waypoint_id, "name": waypoint.name if waypoint else ""})
            return SkillResult(True, f"正在前往路点", {"waypoint_id": waypoint_id})
        else:
            return SkillResult(False, "前往路点失败")


class GoToLocationSkill(Skill):
    """前往位置技能（宏技能）"""
    name = "nav_goto_location"
    description = "前往指定位置（支持路点、坐标、回充点等）。如果找不到路点，会返回可用路点列表"
    category = "navigation"
    
    parameters = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "位置名称（如路点名、回充点等）"
            },
            "location_type": {
                "type": "string",
                "enum": ["waypoint", "dock", "coordinate"],
                "description": "位置类型"
            }
        },
        "required": ["location"]
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        location = params.get("location")
        location_type = params.get("location_type", "waypoint")
        
        # 检查参数
        if not location:
            return SkillResult(False, "请提供目标位置（location参数）")
        
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        # 检查是否是回充点（通过关键词或 location_type）
        dock_keywords = ["回充点", "充电点", "回充站", "充电桩", "回桩"]
        is_dock = location_type == "dock" or any(kw in location for kw in dock_keywords)
        
        if is_dock:
            return self._goto_dock(context)
        
        if location_type == "waypoint":
            # 查找路点
            current_map = context.get("current_map")
            if not current_map:
                return SkillResult(False, "未加载地图，请先调用 nav_start 加载地图")
            
            map_id = current_map.get("id")
            waypoints = self.adapter.list_waypoints(map_id)
            
            # 精确匹配
            for wp in waypoints:
                if wp.name == location:
                    success = self.adapter.goto_waypoint(wp.id)
                    if success:
                        return SkillResult(True, f"正在前往 {wp.name}", {"waypoint_id": wp.id, "waypoint_name": wp.name})
            
            # 模糊匹配
            for wp in waypoints:
                if location in wp.name or wp.name in location:
                    success = self.adapter.goto_waypoint(wp.id)
                    if success:
                        return SkillResult(True, f"正在前往 {wp.name}", {"waypoint_id": wp.id, "waypoint_name": wp.name})
            
            # 没找到，返回可用路点列表
            available = [wp.name for wp in waypoints[:10]]
            return SkillResult(
                False, 
                f"未找到路点 '{location}'。该地图可用路点: {', '.join(available)}",
                {"available_waypoints": available, "requested": location}
            )
        
        return SkillResult(False, f"未找到位置: {location}")
    
    def _goto_dock(self, context: SkillContext) -> SkillResult:
        """前往回充点"""
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        try:
            # 获取当前地图ID
            current_map = context.get("current_map")
            map_id = current_map.get("id") if current_map else None
            
            # 调用适配器的 goto_dock，传入 map_id
            success = self.adapter.goto_dock(map_id=map_id)
            if success:
                return SkillResult(True, "正在前往回充点", {
                    "location": "回充点",
                    "location_type": "dock",
                })
            else:
                return SkillResult(False, "前往回充点失败，请检查回充点是否可用")
        except Exception as e:
            return SkillResult(False, f"前往回充点异常: {str(e)}")

    def _ensure_current_map(self, context: SkillContext) -> Dict[str, Any]:
        """从上下文或适配器状态恢复当前地图。"""
        current_map = context.get("current_map")
        if isinstance(current_map, dict) and current_map.get("id") is not None:
            return current_map

        if not self.adapter:
            return {}

        map_info = None
        if hasattr(self.adapter, "resolve_current_map"):
            map_info = self.adapter.resolve_current_map()
        else:
            try:
                nav_status = self.adapter.get_navigation_status()
                map_id = nav_status.get("current_map_id") or nav_status.get("map_id")
                if map_id is not None and hasattr(self.adapter, "get_map"):
                    map_info = self.adapter.get_map(map_id)
            except Exception:
                map_info = None

        if not map_info:
            return {}

        resolved = {"id": map_info.id, "name": map_info.name}
        context.set("current_map", resolved)
        return resolved

    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        location = params.get("location")
        location_type = params.get("location_type", "waypoint")

        if not location:
            return SkillResult(False, "请提供目标位置（location 参数）")

        if not self.adapter:
            return SkillResult(False, "适配器未设置")

        dock_keywords = ["回充点", "充电点", "回充站", "充电桩", "回桩"]
        is_dock = location_type == "dock" or any(kw in location for kw in dock_keywords)

        if is_dock:
            return self._goto_dock(context)

        if location_type == "waypoint":
            current_map = self._ensure_current_map(context)
            if not current_map:
                return SkillResult(False, "未加载地图，请先调用 nav_start 加载地图")

            map_id = current_map.get("id")
            waypoints = self.adapter.list_waypoints(map_id)

            for wp in waypoints:
                if wp.name == location:
                    success = self.adapter.goto_waypoint(wp.id)
                    if success:
                        context.set("pending_arrival", {"waypoint_id": wp.id, "name": wp.name})
                        context.set("last_waypoint", {"waypoint_id": wp.id, "name": wp.name})
                        return SkillResult(True, f"正在前往 {wp.name}", {
                            "waypoint_id": wp.id,
                            "waypoint_name": wp.name,
                            "location": wp.name,
                            "map_id": map_id
                        })

            for wp in waypoints:
                if location in wp.name or wp.name in location:
                    success = self.adapter.goto_waypoint(wp.id)
                    if success:
                        context.set("pending_arrival", {"waypoint_id": wp.id, "name": wp.name})
                        context.set("last_waypoint", {"waypoint_id": wp.id, "name": wp.name})
                        return SkillResult(True, f"正在前往 {wp.name}", {
                            "waypoint_id": wp.id,
                            "waypoint_name": wp.name,
                            "location": wp.name,
                            "map_id": map_id
                        })

            available = [wp.name for wp in waypoints[:10]]
            return SkillResult(
                False,
                f"未找到路点 '{location}'。该地图可用路点: {', '.join(available)}",
                {"available_waypoints": available, "requested": location, "map_id": map_id}
            )

        return SkillResult(False, f"未找到位置 {location}")

    def _goto_dock(self, context: SkillContext) -> SkillResult:
        if not self.adapter:
            return SkillResult(False, "适配器未设置")

        try:
            current_map = self._ensure_current_map(context)
            map_id = current_map.get("id") if current_map else None
            success = self.adapter.goto_dock(map_id=map_id)
            if success:
                return SkillResult(True, "正在前往回充点", {
                    "location": "回充点",
                    "location_type": "dock",
                    "map_id": map_id
                })
            return SkillResult(False, "前往回充点失败，请检查回充点是否可用")
        except Exception as e:
            return SkillResult(False, f"前往回充点异常: {str(e)}")


class GetNavigationStatusSkill(Skill):
    """获取导航状态技能"""
    name = "nav_get_status"
    description = "获取当前导航状态"
    category = "navigation"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        status = self.adapter.get_navigation_status()
        nav_running = status.get("nav_running", False)
        
        if nav_running:
            return SkillResult(True, "正在导航中", status)
        else:
            return SkillResult(True, "当前未在导航", status)


class ListMapsSkill(Skill):
    """列出地图技能"""
    name = "nav_list_maps"
    description = "获取所有可用地图列表"
    category = "navigation"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        maps = self.adapter.list_maps()
        map_list = [{"id": m.id, "name": m.name} for m in maps]
        
        if map_list:
            names = [m["name"] for m in map_list[:5]]
            suffix = " 等" if len(map_list) > 5 else ""
            message = f"找到 {len(map_list)} 张地图: {', '.join(names)}{suffix}"
        else:
            message = "没有找到地图"
        
        return SkillResult(True, message, {"maps": map_list})


class ListWaypointsSkill(Skill):
    """列出路点技能"""
    name = "nav_list_waypoints"
    description = "获取指定地图的所有路点"
    category = "navigation"
    
    parameters = {
        "type": "object",
        "properties": {
            "map_name": {
                "type": "string",
                "description": "地图名称"
            }
        },
        "required": []
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        map_name = params.get("map_name")
        
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        # 获取地图ID
        map_id = None
        if map_name:
            maps = self.adapter.list_maps()
            for m in maps:
                if m.name == map_name or map_name in m.name:
                    map_id = m.id
                    break
        
        if not map_id:
            current_map = context.get("current_map")
            if current_map:
                map_id = current_map.get("id")
        
        if not map_id:
            return SkillResult(False, "请指定地图名称或先加载地图")
        
        waypoints = self.adapter.list_waypoints(map_id)
        wp_list = [{"id": wp.id, "name": wp.name, "x": wp.x, "y": wp.y} for wp in waypoints]
        
        if wp_list:
            names = [wp["name"] for wp in wp_list[:5]]
            suffix = " 等" if len(wp_list) > 5 else ""
            message = f"找到 {len(wp_list)} 个路点: {', '.join(names)}{suffix}"
        else:
            message = "没有找到路点"
        
        context.set("last_waypoint_list", wp_list)
        return SkillResult(True, message, {"waypoints": wp_list, "map_id": map_id})
