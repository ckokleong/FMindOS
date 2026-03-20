"""
动作控制技能
"""

from typing import Any, Dict
from fishmindos.core.models import SkillContext, SkillResult
from fishmindos.skills.base import Skill


class MotionStandSkill(Skill):
    """站立技能"""
    name = "motion_stand"
    description = "让机器狗站立"
    category = "motion"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        success = self.adapter.motion_stand()
        if success:
            return SkillResult(True, "已站立")
        return SkillResult(False, "站立命令执行失败")


class MotionLieDownSkill(Skill):
    """趴下技能"""
    name = "motion_lie_down"
    description = "让机器狗趴下"
    category = "motion"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        success = self.adapter.motion_lie_down()
        if success:
            return SkillResult(True, "已趴下")
        return SkillResult(False, "趴下命令执行失败")


class MotionApplyPresetSkill(Skill):
    """应用动作预设"""
    name = "motion_apply_preset"
    description = "应用预设动作（站立/趴下）"
    category = "motion"
    
    parameters = {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["stand", "lie_down"],
                "description": "动作预设名称: stand-站立, lie_down-趴下"
            }
        },
        "required": ["preset"]
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        preset = params.get("preset")
        
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        if preset == "stand":
            success = self.adapter.motion_stand()
            message = "已站立" if success else "站立失败"
        elif preset == "lie_down":
            success = self.adapter.motion_lie_down()
            message = "已趴下" if success else "趴下失败"
        else:
            return SkillResult(False, f"未知的动作预设: {preset}")
        
        return SkillResult(success, message)
