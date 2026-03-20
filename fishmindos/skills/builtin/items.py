"""
物品管理技能
支持取货、送货、物品追踪
"""

from typing import Any, Dict, List
from fishmindos.core.models import SkillContext, SkillResult
from fishmindos.skills.base import Skill


# 全局物品库存（模拟）
_ITEM_INVENTORY: Dict[str, Dict[str, Any]] = {}
_ROBOT_CARGO: Dict[str, Any] = {}  # 机器人当前携带的物品


class ItemPickupSkill(Skill):
    """取物品技能"""
    name = "item_pickup"
    description = "在指定位置取物品"
    category = "manipulation"
    
    parameters = {
        "type": "object",
        "properties": {
            "item_name": {
                "type": "string",
                "description": "物品名称"
            },
            "location": {
                "type": "string",
                "description": "取货地点"
            },
            "quantity": {
                "type": "integer",
                "default": 1,
                "description": "数量"
            }
        },
        "required": ["item_name"]
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        item_name = params.get("item_name", "物品")
        location = params.get("location", "当前位置")
        quantity = params.get("quantity", 1)
        
        # 模拟取货过程
        global _ROBOT_CARGO
        
        # 检查是否已有物品
        if _ROBOT_CARGO:
            return SkillResult(
                False, 
                f"我已经携带了 {_ROBOT_CARGO.get('name')}，请先放下当前物品"
            )
        
        # 模拟取货
        _ROBOT_CARGO = {
            "name": item_name,
            "quantity": quantity,
            "pickup_location": location,
            "pickup_time": __import__("datetime").datetime.now().isoformat()
        }
        
        context.set("carrying_item", _ROBOT_CARGO)
        
        return SkillResult(
            True,
            f"已在{location}取到{item_name} x{quantity}",
            {"item": _ROBOT_CARGO}
        )


class ItemDropoffSkill(Skill):
    """放物品技能"""
    name = "item_dropoff"
    description = "在指定位置放下物品"
    category = "manipulation"
    
    parameters = {
        "type": "object",
        "properties": {
            "item_name": {
                "type": "string",
                "description": "物品名称（可选，默认放下当前携带的物品）"
            },
            "location": {
                "type": "string",
                "description": "送货地点"
            }
        },
        "required": []
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        item_name = params.get("item_name")
        location = params.get("location", "当前位置")
        
        global _ROBOT_CARGO
        
        # 检查是否携带物品
        if not _ROBOT_CARGO:
            return SkillResult(False, "我没有携带任何物品")
        
        # 如果指定了物品名，检查是否匹配
        if item_name and _ROBOT_CARGO.get("name") != item_name:
            return SkillResult(
                False, 
                f"我携带的是 {_ROBOT_CARGO.get('name')}，不是 {item_name}"
            )
        
        # 记录送货信息
        delivered_item = _ROBOT_CARGO.copy()
        delivered_item["dropoff_location"] = location
        delivered_item["dropoff_time"] = __import__("datetime").datetime.now().isoformat()
        
        # 清空携带物品
        item_display_name = _ROBOT_CARGO.get("name", "物品")
        _ROBOT_CARGO = {}
        context.set("carrying_item", None)
        
        return SkillResult(
            True,
            f"已在{location}放下{item_display_name}",
            {"delivered_item": delivered_item}
        )


class ItemCheckSkill(Skill):
    """检查物品技能"""
    name = "item_check"
    description = "检查当前携带的物品"
    category = "manipulation"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        global _ROBOT_CARGO
        
        if not _ROBOT_CARGO:
            return SkillResult(True, "我目前没有携带任何物品", {"carrying": None})
        
        item_name = _ROBOT_CARGO.get("name", "未知物品")
        quantity = _ROBOT_CARGO.get("quantity", 1)
        pickup_location = _ROBOT_CARGO.get("pickup_location", "未知地点")
        
        message = f"我当前携带: {item_name} x{quantity} (从{pickup_location}取的)"
        
        return SkillResult(
            True,
            message,
            {"carrying": _ROBOT_CARGO}
        )


class ItemPlaceSkill(Skill):
    """放置物品到指定位置技能（模拟）"""
    name = "item_place"
    description = "将物品放置到指定位置（如桌上、柜子里）"
    category = "manipulation"
    
    parameters = {
        "type": "object",
        "properties": {
            "position": {
                "type": "string",
                "description": "放置位置，如: 桌上、柜子里、门口",
                "enum": ["桌上", "柜子里", "门口", "地面", "架子上"]
            }
        },
        "required": ["position"]
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        position = params.get("position", "地面")
        
        global _ROBOT_CARGO
        
        if not _ROBOT_CARGO:
            return SkillResult(False, "我没有携带任何物品可以放置")
        
        item_name = _ROBOT_CARGO.get("name", "物品")
        
        # 模拟放置过程
        _ROBOT_CARGO["placed_at"] = position
        context.set("carrying_item", _ROBOT_CARGO)
        
        return SkillResult(
            True,
            f"已将{item_name}放置在{position}",
            {"item": _ROBOT_CARGO, "position": position}
        )


def reset_inventory():
    """重置库存（用于测试）"""
    global _ITEM_INVENTORY, _ROBOT_CARGO
    _ITEM_INVENTORY.clear()
    _ROBOT_CARGO = {}


def get_cargo() -> Dict[str, Any]:
    """获取当前携带的物品"""
    return _ROBOT_CARGO.copy()
