"""
FishMindOS Adapters - 适配器层
提供统一的机器人API接口
"""

from fishmindos.adapters.base import (
    RobotAdapter,
    MapInfo,
    WaypointInfo,
    TaskInfo,
    RobotStatus,
    AdapterError,
)
from fishmindos.adapters.unitree_go2 import UnitreeGo2Adapter, create_go2_adapter

__all__ = [
    "RobotAdapter",
    "MapInfo",
    "WaypointInfo",
    "TaskInfo",
    "RobotStatus",
    "AdapterError",
    "UnitreeGo2Adapter",
    "create_go2_adapter",
]
