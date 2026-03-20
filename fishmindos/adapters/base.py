"""
适配器基类和接口定义
提供统一的API访问接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class MapInfo:
    """地图信息"""
    id: int
    name: str
    description: str = ""
    
    
@dataclass
class WaypointInfo:
    """路点信息"""
    id: int
    name: str
    map_id: int
    x: float
    y: float
    z: float = 0.0
    yaw: float = 0.0
    type: str = "normal"


@dataclass
class TaskInfo:
    """任务信息"""
    id: int
    name: str
    description: str = ""
    status: str = "idle"
    program: dict = None


@dataclass
class RobotStatus:
    """机器人状态"""
    nav_running: bool = False
    charging: bool = False
    battery_soc: Optional[float] = None
    current_pose: dict = None


class RobotAdapter(ABC):
    """
    机器人适配器基类
    所有具体适配器需要实现这些接口
    """
    
    @property
    @abstractmethod
    def vendor_name(self) -> str:
        """厂商名称"""
        pass
    
    @abstractmethod
    def connect(self) -> Dict[str, Any]:
        """连接到机器人，返回结构化健康检查结果"""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
        pass
    
    # ========== 地图操作 ==========
    @abstractmethod
    def list_maps(self) -> List[MapInfo]:
        """获取地图列表"""
        pass
    
    @abstractmethod
    def get_map(self, map_id: int) -> Optional[MapInfo]:
        """获取地图详情"""
        pass
    
    # ========== 路点操作 ==========
    @abstractmethod
    def list_waypoints(self, map_id: int) -> List[WaypointInfo]:
        """获取路点列表"""
        pass
    
    @abstractmethod
    def get_waypoint(self, waypoint_id: int) -> Optional[WaypointInfo]:
        """获取路点详情"""
        pass
    
    # ========== 导航操作 ==========
    @abstractmethod
    def start_navigation(self, map_id: int) -> bool:
        """启动导航"""
        pass
    
    @abstractmethod
    def stop_navigation(self) -> bool:
        """停止导航"""
        pass
    
    @abstractmethod
    def goto_waypoint(self, waypoint_id: int) -> bool:
        """前往路点"""
        pass
    
    @abstractmethod
    def goto_point(self, x: float, y: float, yaw: float = 0.0) -> bool:
        """前往坐标点"""
        pass
    
    @abstractmethod
    def get_navigation_status(self) -> dict:
        """获取导航状态"""
        pass
    
    # ========== 任务操作 ==========
    @abstractmethod
    def list_tasks(self) -> List[TaskInfo]:
        """获取任务列表"""
        pass
    
    @abstractmethod
    def run_task(self, task_id: int) -> bool:
        """运行任务"""
        pass
    
    @abstractmethod
    def cancel_task(self) -> bool:
        """取消当前任务"""
        pass
    
    # ========== 回调管理 ==========
    def set_callback_url(self, url: str, enable: bool = True) -> bool:
        """
        设置导航事件回调URL
        
        Args:
            url: 回调接收地址
            enable: 是否启用
            
        Returns:
            是否设置成功
        """
        # 默认实现，子类可覆盖
        print(f"[Adapter] 回调URL设置: {url} (enabled={enable})")
        self._callback_url = url if enable else None
        return True
    
    def send_callback(self, event_type: str, data: Dict[str, Any]) -> bool:
        """
        发送回调事件
        
        Args:
            event_type: 事件类型 (nav_start, arrival, dock_complete 等)
            data: 事件数据
            
        Returns:
            是否发送成功
        """
        import json
        import urllib.request
        
        url = getattr(self, '_callback_url', None)
        if not url:
            return False
        
        try:
            payload = {
                "event": event_type,
                "timestamp": __import__('time').time(),
                "data": data
            }
            
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={"Content-Type": "application/json"},
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except Exception as e:
            print(f"[Adapter] 回调发送失败: {e}")
            return False

    def handle_callback_event(self, event: Dict[str, Any]) -> None:
        """Handle callback events pushed from the embedded receiver."""
        return

    def get_callback_state(self) -> Dict[str, Any]:
        """Return the latest callback-driven runtime state."""
        return {}


class AdapterError(Exception):
    """适配器错误"""
    pass
