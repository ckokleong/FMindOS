"""
FishMindOS - 机器狗智能控制系统

重构后的架构:
- core: 核心框架和模型
- skills: 技能系统
- adapters: 适配器层
- brain: LLM大脑层
"""

from fishmindos.skills import (
    create_default_registry,
    SkillRegistry,
    SkillExecutor,
    SkillManager,
    create_skill_manager,
)
from fishmindos.adapters import (
    create_go2_adapter,
    UnitreeGo2Adapter,
)

__all__ = [
    # 技能系统
    "create_default_registry",
    "SkillRegistry", 
    "SkillExecutor",
    "SkillManager",
    "create_skill_manager",
    # 适配器
    "create_go2_adapter",
    "UnitreeGo2Adapter",
]

__version__ = "2.0.0"
