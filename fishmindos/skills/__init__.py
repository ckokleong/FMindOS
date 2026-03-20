"""
FishMindOS Skills - 技能系统
"""

from fishmindos.skills.base import Skill, MacroSkill, SkillRegistry, SkillExecutor
from fishmindos.skills.loader import (
    SkillMetadata,
    SkillDiscoverer,
    SkillLoader,
    SkillManager,
    create_skill_manager,
)
from fishmindos.skills.builtin.navigation import (
    StartNavigationSkill,
    StopNavigationSkill,
    GoToWaypointSkill,
    GoToLocationSkill,
    GetNavigationStatusSkill,
    ListMapsSkill,
    ListWaypointsSkill,
)
from fishmindos.skills.builtin.motion import (
    MotionStandSkill,
    MotionLieDownSkill,
    MotionApplyPresetSkill,
)
from fishmindos.skills.builtin.audio import (
    PlayAudioSkill,
    TTSSkill,
)
from fishmindos.skills.builtin.lights import (
    SetLightSkill,
    TurnOnLightSkill,
    TurnOffLightSkill,
)
from fishmindos.skills.builtin.system import (
    GetBatterySkill,
    GetStatusSkill,
    GetChargingStatusSkill,
    GetPoseSkill,
    WaitEventSkill,
)
from fishmindos.skills.builtin.callback import (
    SetCallbackSkill,
    GetCallbackStatusSkill,
    StartCallbackServerSkill,
)
from fishmindos.skills.builtin.items import (
    ItemPickupSkill,
    ItemDropoffSkill,
    ItemCheckSkill,
    ItemPlaceSkill,
    reset_inventory,
    get_cargo,
)

__all__ = [
    # 基础类
    "Skill",
    "MacroSkill",
    "SkillRegistry",
    "SkillExecutor",
    # 加载器
    "SkillMetadata",
    "SkillDiscoverer",
    "SkillLoader",
    "SkillManager",
    "create_skill_manager",
    # 导航技能
    "StartNavigationSkill",
    "StopNavigationSkill",
    "GoToWaypointSkill",
    "GoToLocationSkill",
    "GetNavigationStatusSkill",
    "ListMapsSkill",
    "ListWaypointsSkill",
    # 动作技能
    "MotionStandSkill",
    "MotionLieDownSkill",
    "MotionApplyPresetSkill",
    # 音频技能
    "PlayAudioSkill",
    "TTSSkill",
    # 灯光技能
    "SetLightSkill",
    "TurnOnLightSkill",
    "TurnOffLightSkill",
    # 系统技能
    "GetBatterySkill",
    "GetStatusSkill",
    "GetChargingStatusSkill",
    "GetPoseSkill",
    "WaitEventSkill",
    "SetCallbackSkill",
    "GetCallbackStatusSkill",
    "StartCallbackServerSkill",
    # 物品管理技能
    "ItemPickupSkill",
    "ItemDropoffSkill",
    "ItemCheckSkill",
    "ItemPlaceSkill",
    "reset_inventory",
    "get_cargo",
]


def create_default_registry() -> SkillRegistry:
    """创建默认技能注册表并注册所有内置技能"""
    registry = SkillRegistry()
    
    # 导航技能
    registry.register(StartNavigationSkill())
    registry.register(StopNavigationSkill())
    registry.register(GoToWaypointSkill())
    registry.register(GoToLocationSkill())
    registry.register(GetNavigationStatusSkill())
    registry.register(ListMapsSkill())
    registry.register(ListWaypointsSkill())
    
    # 动作技能
    registry.register(MotionStandSkill())
    registry.register(MotionLieDownSkill())
    registry.register(MotionApplyPresetSkill())
    
    # 音频技能
    registry.register(PlayAudioSkill())
    registry.register(TTSSkill())
    
    # 灯光技能
    registry.register(SetLightSkill())
    registry.register(TurnOnLightSkill())
    registry.register(TurnOffLightSkill())
    
    # 系统技能
    registry.register(GetBatterySkill())
    registry.register(GetStatusSkill())
    registry.register(GetChargingStatusSkill())
    registry.register(GetPoseSkill())
    registry.register(WaitEventSkill())
    registry.register(SetCallbackSkill())
    registry.register(GetCallbackStatusSkill())
    registry.register(StartCallbackServerSkill())
    
    # 物品管理技能
    registry.register(ItemPickupSkill())
    registry.register(ItemDropoffSkill())
    registry.register(ItemCheckSkill())
    registry.register(ItemPlaceSkill())
    
    return registry
