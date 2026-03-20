"""
灯光控制技能
"""

from typing import Any, Dict
from fishmindos.core.models import SkillContext, SkillResult
from fishmindos.skills.base import Skill


# 灯光代码定义
LIGHT_CODES = {
    11: "红灯常亮",
    12: "黄灯常亮", 
    13: "绿灯常亮",
    21: "红灯慢闪",
    22: "黄灯慢闪",
    23: "绿灯慢闪",
    31: "红灯快闪",
    32: "黄灯快闪",
    33: "绿灯快闪",
    0: "关灯"  # 修改为 0 而不是 60
}


class SetLightSkill(Skill):
    """设置灯光技能"""
    name = "light_set"
    description = "设置机器狗灯光（颜色、闪烁模式）"
    category = "system"
    
    parameters = {
        "type": "object",
        "properties": {
            "color": {
                "type": "string",
                "enum": ["red", "yellow", "green"],
                "description": "灯光颜色: red-红, yellow-黄, green-绿"
            },
            "mode": {
                "type": "string",
                "enum": ["solid", "slow", "fast", "off"],
                "description": "灯光模式: solid-常亮, slow-慢闪, fast-快闪, off-关闭"
            },
            "code": {
                "type": "integer",
                "description": "灯光代码(可选): 11=红灯常亮, 12=黄灯常亮, 13=绿灯常亮, 21=红灯慢闪, 22=黄灯慢闪, 23=绿灯慢闪, 31=红灯快闪, 32=黄灯快闪, 33=绿灯快闪, 0=关灯"
            }
        },
        "required": []
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        code = params.get("code")
        color = params.get("color", "red")
        mode = params.get("mode", "solid")
        
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        # 如果提供了code直接使用，否则根据color和mode计算
        if code is None:
            code = self._resolve_code(color, mode)
        
        success = self.adapter.set_light(code)
        
        if success:
            desc = LIGHT_CODES.get(code, f"代码 {code}")
            return SkillResult(True, f"灯光已设置为: {desc}", {"code": code})
        return SkillResult(False, "设置灯光失败")
    
    def _resolve_code(self, color: str, mode: str) -> int:
        """根据颜色和模式解析灯光代码"""
        color_map = {
            "red": 1,
            "yellow": 2,
            "green": 3
        }
        
        mode_map = {
            "solid": 0,
            "slow": 1,
            "fast": 2,
            "off": 6  # 修改为 6，使得 (6+1)*10+0 = 0 不对，需要直接返回 0
        }
        
        c = color_map.get(color, 1)
        m = mode_map.get(mode, 0)
        
        if m == 6:  # off - 直接返回 0
            return 0
        
        return (m + 1) * 10 + c


class TurnOnLightSkill(Skill):
    """开灯技能"""
    name = "light_on"
    description = "打开机器狗灯光，可以指定颜色"
    category = "system"
    
    parameters = {
        "type": "object",
        "properties": {
            "color": {
                "type": "string",
                "enum": ["red", "green", "yellow"],
                "description": "灯光颜色: red-红灯, green-绿灯(绿色), yellow-黄灯"
            }
        },
        "required": []
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        color = params.get("color", "red")
        
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        # 颜色到代码的映射
        color_map = {
            "red": 11,      # 红灯常亮
            "green": 13,    # 绿灯常亮  
            "yellow": 12    # 黄灯常亮
        }
        
        code = color_map.get(color, 11)
        success = self.adapter.set_light(code)
        
        color_names = {"red": "红灯", "green": "绿灯", "yellow": "黄灯"}
        color_name = color_names.get(color, color)
        
        if success:
            return SkillResult(True, f"{color_name}已打开", {"color": color, "code": code})
        return SkillResult(False, f"开{color_name}失败")


class TurnOffLightSkill(Skill):
    """关灯技能"""
    name = "light_off"
    description = "关闭机器狗灯光"
    category = "system"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        # 使用 0 关灯
        success = self.adapter.set_light(0)
        
        if success:
            return SkillResult(True, "灯光已关闭")
        return SkillResult(False, "关灯失败")
