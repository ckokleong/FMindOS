"""
YourRobot 适配器示例
用于接入其他品牌机器人的完整实现
"""

import json
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from fishmindos.adapters.base import (
    RobotAdapter, MapInfo, WaypointInfo, TaskInfo, RobotStatus, AdapterError
)


class YourRobotAPIError(Exception):
    """YourRobot API错误"""
    pass


@dataclass
class YourRobotConfig:
    """YourRobot 配置"""
    host: str = "192.168.1.100"
    port: int = 8080
    api_key: str = ""
    protocol: str = "http"  # http 或 https
    timeout: int = 30
    
    @property
    def base_url(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}"


class YourRobotAdapter(RobotAdapter):
    """
    YourRobot 适配器 - 示例实现
    
    适配其他品牌机器人的标准接口
    支持: HTTP REST API + WebSocket 实时控制
    """
    
    def __init__(self, 
                 host: str = "192.168.1.100",
                 port: int = 8080,
                 api_key: str = "",
                 **kwargs):
        """
        初始化适配器
        
        Args:
            host: 机器人IP地址
            port: API端口
            api_key: API认证密钥
            **kwargs: 其他配置参数
        """
        self.config = YourRobotConfig(
            host=host,
            port=port,
            api_key=api_key
        )
        
        # 内部状态
        self._connected = False
        self._current_map_id: Optional[int] = None
        self._current_pose = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self._battery = 100.0
        self._nav_running = False
        
        # WebSocket 客户端（如果需要实时控制）
        self.ws_client = None
        
        print(f"[YourRobot] 适配器初始化: {self.config.base_url}")
    
    @property
    def vendor_name(self) -> str:
        return "YourRobot Navigator"
    
    # ========== HTTP 请求封装 ==========
    
    def _request(self, 
                 method: str, 
                 endpoint: str, 
                 data: Dict = None, 
                 params: Dict = None) -> Dict:
        """
        发送HTTP请求
        
        Args:
            method: HTTP方法 (GET/POST/PUT/DELETE)
            endpoint: API端点
            data: 请求体数据
            params: URL参数
            
        Returns:
            API响应数据
            
        Raises:
            YourRobotAPIError: 请求失败
        """
        url = f"{self.config.base_url}{endpoint}"
        
        if params:
            import urllib.parse
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
            "Accept": "application/json"
        }
        
        body = json.dumps(data).encode('utf-8') if data else None
        
        req = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method
        )
        
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                # 检查业务错误码
                if result.get("code", 0) != 0:
                    error_msg = result.get("msg", "未知错误")
                    raise YourRobotAPIError(f"API错误: {error_msg} (code:{result.get('code')})")
                
                return result
                
        except urllib.error.HTTPError as e:
            raise YourRobotAPIError(f"HTTP {e.code}: {e.reason}")
        except Exception as e:
            raise YourRobotAPIError(f"请求失败: {e}")
    
    # ========== 连接管理 ==========
    
    def connect(self) -> Dict[str, Any]:
        """
        连接到机器人并执行健康检查
        
        Returns:
            {
                "success": bool,
                "status": str,
                "details": Dict
            }
        """
        results = {
            "success": False,
            "status": "offline",
            "details": {}
        }
        
        try:
            # 测试连接 - 获取机器人状态
            response = self._request("GET", "/api/robot/status")
            
            if response.get("code", -1) == 0:
                self._connected = True
                results["success"] = True
                results["status"] = "online"
                results["details"] = response.get("data", {})
                print(f"[YourRobot] 连接成功: {self.config.base_url}")
            else:
                results["status"] = "error"
                results["details"]["error"] = response.get("msg", "未知错误")
                
        except Exception as e:
            results["status"] = "offline"
            results["details"]["error"] = str(e)
            print(f"[YourRobot] 连接失败: {e}")
        
        return results
    
    def disconnect(self) -> None:
        """断开连接"""
        self._connected = False
        if self.ws_client:
            # 关闭WebSocket连接
            pass
        print("[YourRobot] 断开连接")
    
    # ========== 地图操作 ==========
    
    def list_maps(self) -> List[MapInfo]:
        """获取地图列表"""
        try:
            result = self._request("GET", "/api/maps/list")
            maps_data = result.get("data", {}).get("maps", [])
            
            return [
                MapInfo(
                    id=m["id"],
                    name=m["name"],
                    description=m.get("description", "")
                )
                for m in maps_data
            ]
        except Exception as e:
            print(f"[YourRobot] 获取地图列表失败: {e}")
            return []
    
    def get_map(self, map_id: int) -> Optional[MapInfo]:
        """获取地图详情"""
        try:
            result = self._request("GET", f"/api/maps/{map_id}")
            data = result.get("data", {})
            
            return MapInfo(
                id=data["id"],
                name=data["name"],
                description=data.get("description", "")
            )
        except Exception as e:
            print(f"[YourRobot] 获取地图详情失败: {e}")
            return None
    
    def start_navigation(self, map_id: int) -> bool:
        """启动导航（加载地图）"""
        try:
            result = self._request(
                "POST", 
                "/api/navigation/start",
                data={"map_id": map_id}
            )
            
            if result.get("code", -1) == 0:
                self._current_map_id = map_id
                self._nav_running = True
                print(f"[YourRobot] 导航已启动，地图ID: {map_id}")
                return True
            return False
            
        except Exception as e:
            print(f"[YourRobot] 启动导航失败: {e}")
            return False
    
    def stop_navigation(self) -> bool:
        """停止导航"""
        try:
            result = self._request("POST", "/api/navigation/stop")
            self._nav_running = False
            return result.get("code", -1) == 0
        except Exception as e:
            print(f"[YourRobot] 停止导航失败: {e}")
            return False
    
    def pause_navigation(self) -> bool:
        """暂停导航"""
        try:
            result = self._request("POST", "/api/navigation/pause")
            return result.get("code", -1) == 0
        except Exception as e:
            print(f"[YourRobot] 暂停导航失败: {e}")
            return False
    
    def resume_navigation(self) -> bool:
        """恢复导航"""
        try:
            result = self._request("POST", "/api/navigation/resume")
            return result.get("code", -1) == 0
        except Exception as e:
            print(f"[YourRobot] 恢复导航失败: {e}")
            return False
    
    def get_navigation_status(self) -> Dict[str, Any]:
        """获取导航状态"""
        try:
            result = self._request("GET", "/api/navigation/status")
            return result.get("data", {})
        except Exception as e:
            return {"nav_running": False, "error": str(e)}
    
    # ========== 路点操作 ==========
    
    def list_waypoints(self, map_id: int) -> List[WaypointInfo]:
        """获取路点列表"""
        try:
            result = self._request(
                "GET", 
                f"/api/maps/{map_id}/waypoints"
            )
            
            waypoints = result.get("data", {}).get("waypoints", [])
            
            return [
                WaypointInfo(
                    id=wp["id"],
                    name=wp["name"],
                    map_id=map_id,
                    x=wp.get("x", 0.0),
                    y=wp.get("y", 0.0),
                    z=wp.get("z", 0.0),
                    yaw=wp.get("yaw", 0.0)
                )
                for wp in waypoints
            ]
        except Exception as e:
            print(f"[YourRobot] 获取路点列表失败: {e}")
            return []
    
    def get_waypoint(self, waypoint_id: int) -> Optional[WaypointInfo]:
        """获取路点详情"""
        try:
            result = self._request("GET", f"/api/waypoints/{waypoint_id}")
            data = result.get("data", {})
            
            return WaypointInfo(
                id=data["id"],
                name=data["name"],
                map_id=data.get("map_id", 0),
                x=data.get("x", 0.0),
                y=data.get("y", 0.0),
                yaw=data.get("yaw", 0.0)
            )
        except Exception as e:
            print(f"[YourRobot] 获取路点详情失败: {e}")
            return None
    
    def goto_waypoint(self, waypoint_id: int) -> bool:
        """前往指定路点"""
        try:
            result = self._request(
                "POST",
                "/api/navigation/goto/waypoint",
                data={"waypoint_id": waypoint_id}
            )
            return result.get("code", -1) == 0
        except Exception as e:
            print(f"[YourRobot] 前往路点失败: {e}")
            return False
    
    def goto_location(self, location: str, location_type: str = "waypoint") -> bool:
        """前往指定位置（通过名称）"""
        try:
            # YourRobot 可能支持通过名称导航
            result = self._request(
                "POST",
                "/api/navigation/goto/location",
                data={
                    "location": location,
                    "type": location_type
                }
            )
            return result.get("code", -1) == 0
        except Exception as e:
            print(f"[YourRobot] 前往位置失败: {e}")
            return False
    
    def goto_point(self, x: float, y: float, yaw: float = None) -> bool:
        """前往指定坐标"""
        try:
            data = {"x": x, "y": y}
            if yaw is not None:
                data["yaw"] = yaw
            
            result = self._request(
                "POST",
                "/api/navigation/goto/point",
                data=data
            )
            return result.get("code", -1) == 0
        except Exception as e:
            print(f"[YourRobot] 前往坐标失败: {e}")
            return False
    
    def goto_dock(self, map_id: int = None) -> bool:
        """前往回充点"""
        try:
            data = {}
            if map_id:
                data["map_id"] = map_id
            
            result = self._request(
                "POST",
                "/api/navigation/goto/dock",
                data=data
            )
            return result.get("code", -1) == 0
        except Exception as e:
            print(f"[YourRobot] 前往回充点失败: {e}")
            return False
    
    # ========== 等待事件 ==========
    
    def wait_nav_started(self, timeout: int = 60) -> bool:
        """等待导航启动"""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = self.get_navigation_status()
            if status.get("nav_running"):
                return True
            time.sleep(0.5)
        
        return False
    
    def wait_arrival(self, waypoint_id: int = None, timeout: int = 300) -> bool:
        """等待到达路点"""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = self.get_navigation_status()
            if not status.get("nav_running"):
                # 导航停止，可能已到达
                return True
            time.sleep(0.5)
        
        return False
    
    def wait_dock_complete(self, timeout: int = 300) -> bool:
        """等待回充完成"""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = self.get_status()
            if status.charging:
                return True
            time.sleep(1.0)
        
        return False
    
    # ========== 运动控制 ==========
    
    def motion_stand(self) -> bool:
        """站立"""
        try:
            result = self._request("POST", "/api/robot/stand")
            print("[YourRobot] 机器狗已站立")
            return result.get("code", -1) == 0
        except Exception as e:
            print(f"[YourRobot] 站立失败: {e}")
            return False
    
    def motion_lie_down(self) -> bool:
        """趴下"""
        try:
            result = self._request("POST", "/api/robot/lie_down")
            print("[YourRobot] 机器狗已趴下")
            return result.get("code", -1) == 0
        except Exception as e:
            print(f"[YourRobot] 趴下失败: {e}")
            return False
    
    # ========== 灯光控制 ==========
    
    def set_light(self, code: int) -> bool:
        """设置灯光"""
        try:
            result = self._request(
                "POST",
                "/api/robot/light",
                data={"code": code}
            )
            colors = {11: "红灯", 13: "绿灯", 0: "关灯"}
            print(f"[YourRobot] 灯光已设置为: {colors.get(code, '自定义')}")
            return result.get("code", -1) == 0
        except Exception as e:
            print(f"[YourRobot] 设置灯光失败: {e}")
            return False
    
    # ========== 音频控制 ==========
    
    def play_audio(self, text: str) -> bool:
        """播放语音"""
        try:
            result = self._request(
                "POST",
                "/api/robot/tts",
                data={"text": text}
            )
            print(f"[YourRobot] 播报: {text}")
            return result.get("code", -1) == 0
        except Exception as e:
            print(f"[YourRobot] 语音播报失败: {e}")
            return False
    
    # ========== 状态查询 ==========
    
    def get_status(self) -> RobotStatus:
        """获取完整状态"""
        try:
            result = self._request("GET", "/api/robot/status")
            data = result.get("data", {})
            
            self._battery = data.get("battery", 100.0)
            self._nav_running = data.get("nav_running", False)
            
            pose = data.get("pose", {})
            self._current_pose = {
                "x": pose.get("x", 0.0),
                "y": pose.get("y", 0.0),
                "yaw": pose.get("yaw", 0.0)
            }
            
            return RobotStatus(
                nav_running=self._nav_running,
                charging=data.get("charging", False),
                battery_soc=self._battery,
                current_pose=self._current_pose
            )
        except Exception as e:
            print(f"[YourRobot] 获取状态失败: {e}")
            return RobotStatus()
    
    def get_current_pose(self) -> Dict[str, float]:
        """获取当前位置"""
        return self._current_pose.copy()
    
    def get_battery(self) -> Dict[str, Any]:
        """获取电池状态"""
        try:
            result = self._request("GET", "/api/robot/battery")
            return result.get("data", {"soc": 100.0, "charging": False})
        except Exception as e:
            return {"soc": 100.0, "charging": False, "error": str(e)}
    
    # ========== 任务管理 ==========
    
    def list_tasks(self) -> List[TaskInfo]:
        """获取任务列表"""
        try:
            result = self._request("GET", "/api/tasks/list")
            tasks = result.get("data", {}).get("tasks", [])
            
            return [
                TaskInfo(
                    id=t["id"],
                    name=t["name"],
                    description=t.get("description", ""),
                    status=t.get("status", "idle")
                )
                for t in tasks
            ]
        except Exception as e:
            return []
    
    def create_task(self, name: str, description: str = "", program: Dict = None) -> TaskInfo:
        """创建任务"""
        try:
            result = self._request(
                "POST",
                "/api/tasks/create",
                data={
                    "name": name,
                    "description": description,
                    "program": program or {}
                }
            )
            
            data = result.get("data", {})
            return TaskInfo(
                id=data["id"],
                name=data["name"],
                description=data.get("description", "")
            )
        except Exception as e:
            raise AdapterError(f"创建任务失败: {e}")
    
    def run_task(self, task_id: int) -> bool:
        """运行任务"""
        try:
            result = self._request("POST", f"/api/tasks/{task_id}/run")
            return result.get("code", -1) == 0
        except Exception as e:
            return False
    
    def cancel_task(self) -> bool:
        """取消当前任务"""
        try:
            result = self._request("POST", "/api/tasks/cancel")
            return result.get("code", -1) == 0
        except Exception as e:
            return False


# ========== 工厂函数 ==========

def create_your_robot_adapter(
    host: str = "192.168.1.100",
    port: int = 8080,
    api_key: str = "",
    **kwargs
) -> YourRobotAdapter:
    """
    工厂函数：创建 YourRobot 适配器
    
    用法:
        adapter = create_your_robot_adapter(
            host="192.168.1.100",
            port=8080,
            api_key="your-api-key"
        )
        
        if adapter.connect()["success"]:
            print("连接成功")
            adapter.goto_location("会议室")
    
    Args:
        host: 机器人IP地址
        port: API端口
        api_key: API认证密钥
        **kwargs: 其他参数
        
    Returns:
        YourRobotAdapter 实例
    """
    return YourRobotAdapter(
        host=host,
        port=port,
        api_key=api_key,
        **kwargs
    )
