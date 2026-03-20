"""
FishBot适配器 - 接入实际API
集成HTTP API和WebSocket (Rosbridge)
"""

from typing import Any, Dict, List, Optional
import json
import threading
import time
import urllib.request
import urllib.error
from urllib.parse import urlencode

from fishmindos.adapters.base import RobotAdapter, MapInfo, WaypointInfo, TaskInfo, RobotStatus
from fishmindos.adapters.ws_client import RosbridgeClient


class FishBotAPIError(Exception):
    """API错误"""
    pass


class FishBotAdapter(RobotAdapter):
    """
    FishBot适配器
    接入nav_app (9002) 和 nav_server (9001) 的实际API
    同时通过Rosbridge WebSocket控制灯光等实时功能
    """
    
    def __init__(self, nav_server_host: str = "127.0.0.1", nav_server_port: int = 9001,
                 nav_app_host: str = "127.0.0.1", nav_app_port: int = 9002,
                 rosbridge_host: str = "127.0.0.1", rosbridge_port: int = 9090,
                 rosbridge_path: str = "/api/rt"):
        self.nav_server_base = f"http://{nav_server_host}:{nav_server_port}"
        self.nav_app_base = f"http://{nav_app_host}:{nav_app_port}"
        self._connected = False
        self._current_map_id: Optional[int] = None
        self._callback_enabled = False
        self._callback_condition = threading.Condition()
        self._callback_state: Dict[str, Any] = {
            "event_count": 0,
            "last_event": None,
            "last_event_at": None,
            "last_event_payload": None,
            "nav_running": None,
            "nav_started_at": None,
            "current_map_id": None,
            "current_pose": None,
            "target_pose": None,
            "target_waypoint_id": None,
            "target_waypoint_name": None,
            "target_updated_at": None,
            "arrived_waypoint_id": None,
            "arrived_at": None,
            "dock_complete_at": None,
            "charging": None,
        }
        
        # WebSocket客户端（用于灯光控制等）
        self.ws_client: Optional[RosbridgeClient] = None
        self.rosbridge_host = rosbridge_host
        self.rosbridge_port = rosbridge_port
        self.rosbridge_path = rosbridge_path
    
    @property
    def vendor_name(self) -> str:
        return "FishBot Navigator"
    
    def _request(self, method: str, endpoint: str, base_url: str = None, 
                 data: Dict = None, params: Dict = None) -> Dict:
        """发送HTTP请求"""
        base = base_url or self.nav_server_base
        url = f"{base}{endpoint}"
        
        if params:
            url += "?" + urlencode(params)
        
        headers = {"Content-Type": "application/json"}
        
        if data:
            body = json.dumps(data).encode('utf-8')
        else:
            body = None
        
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result
        except urllib.error.HTTPError as e:
            raise FishBotAPIError(f"HTTP {e.code}: {e.reason}")
        except Exception as e:
            raise FishBotAPIError(f"请求失败: {e}")
    
    def connect(self) -> Dict[str, Any]:
        """
        健康检查 - 分段检查各个组件
        
        Returns:
            {
                "success": bool,  # 整体是否成功
                "nav_server": {"connected": bool, "error": str|None},
                "nav_app": {"connected": bool, "error": str|None}, 
                "rosbridge": {"connected": bool, "error": str|None},
                "overall_status": str  # "healthy" | "degraded" | "offline"
            }
        """
        results = {
            "success": False,
            "nav_server": {"connected": False, "error": None},
            "nav_app": {"connected": False, "error": None},
            "rosbridge": {"connected": False, "error": None},
            "overall_status": "offline"
        }
        
        # 1. 检查 nav_server
        try:
            result = self._request("GET", "/api/nav/maps/list")
            # 检查业务错误码
            if result.get("code", 0) != 0:
                error_msg = result.get("msg", "未知错误")
                results["nav_server"]["error"] = f"服务错误: {error_msg} (code:{result.get('code')})"
            else:
                results["nav_server"]["connected"] = True
        except Exception as e:
            results["nav_server"]["error"] = str(e)
        
        # 2. 检查 nav_app (与 nav_server 共享端口，使用相同的检查方式)
        # nav_app 和 nav_server 实际是同一个服务
        try:
            # 如果 nav_server_base 和 nav_app_base 相同，复用 nav_server 的结果
            if self.nav_server_base == self.nav_app_base:
                results["nav_app"] = results["nav_server"].copy()
            else:
                # 不同端口时，尝试获取地图列表
                self._request("GET", "/api/nav/maps/list", base_url=self.nav_app_base)
                results["nav_app"]["connected"] = True
        except Exception as e:
            results["nav_app"]["error"] = str(e)
        
        # 3. 检查 rosbridge (WebSocket)
        try:
            self.ws_client = RosbridgeClient(
                self.rosbridge_host, self.rosbridge_port, self.rosbridge_path
            )
            if self.ws_client.connect():
                results["rosbridge"]["connected"] = True
            else:
                results["rosbridge"]["error"] = "WebSocket连接失败"
        except Exception as e:
            results["rosbridge"]["error"] = str(e)
        
        # 计算整体状态
        connected_count = sum([
            results["nav_server"]["connected"],
            results["nav_app"]["connected"],
            results["rosbridge"]["connected"]
        ])
        
        if connected_count == 3:
            results["overall_status"] = "healthy"
            results["success"] = True
            self._connected = True
        elif connected_count >= 1:
            results["overall_status"] = "degraded"
            results["success"] = True  # 部分可用也算成功
            self._connected = True
        else:
            results["overall_status"] = "offline"
            self._connected = False
        
        return results

    def set_callback_url(self, url: str, enable: bool = True) -> bool:
        """Persist callback enablement so waits can prefer callback-driven state."""
        self._callback_enabled = bool(enable and url)
        return super().set_callback_url(url, enable)

    @staticmethod
    def _clone_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: FishBotAdapter._clone_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [FishBotAdapter._clone_value(item) for item in value]
        return value

    @staticmethod
    def _coerce_int(value: Any) -> Any:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return value

    @staticmethod
    def _normalize_pose(value: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(value, dict):
            return None

        source = value
        if isinstance(value.get("point"), dict):
            source = dict(value["point"])
            for extra_key in ("yaw", "roll", "pitch", "time", "timestamp"):
                if extra_key in value and extra_key not in source:
                    source[extra_key] = value[extra_key]

        pose: Dict[str, Any] = {}
        aliases = {
            "x": "x",
            "y": "y",
            "z": "z",
            "yaw": "yaw",
            "theta": "yaw",
            "roll": "roll",
            "pitch": "pitch",
            "time": "time",
            "timestamp": "timestamp",
        }
        for src_key, dst_key in aliases.items():
            if src_key in source:
                pose[dst_key] = source[src_key]

        if "x" in pose and "y" in pose:
            return pose
        return None

    def _extract_prefixed_pose(self, payload: Dict[str, Any], prefix: str) -> Optional[Dict[str, Any]]:
        pose: Dict[str, Any] = {}
        found = False
        for src_key, dst_key in {
            f"{prefix}_x": "x",
            f"{prefix}_y": "y",
            f"{prefix}_z": "z",
            f"{prefix}_yaw": "yaw",
            f"{prefix}_theta": "yaw",
            f"{prefix}_roll": "roll",
            f"{prefix}_pitch": "pitch",
            f"{prefix}_time": "time",
            f"{prefix}_timestamp": "timestamp",
        }.items():
            if src_key in payload:
                pose[dst_key] = payload[src_key]
                found = True
        if found and "x" in pose and "y" in pose:
            return pose
        return None

    def _extract_current_pose(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for key in ("current_pose", "robot_pose", "self_pose", "current_position", "pose", "position"):
            pose = self._normalize_pose(payload.get(key))
            if pose:
                return pose
        for prefix in ("robot", "self", "current", "pose", "position"):
            pose = self._extract_prefixed_pose(payload, prefix)
            if pose:
                return pose
        return None

    def _extract_target_pose(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for key in ("target_pose", "target_position", "goal_pose", "goal_position", "target_point", "goal", "target"):
            pose = self._normalize_pose(payload.get(key))
            if pose:
                return pose
        for prefix in ("target", "goal"):
            pose = self._extract_prefixed_pose(payload, prefix)
            if pose:
                return pose
        return None

    @staticmethod
    def _event_name(payload: Dict[str, Any]) -> str:
        raw = payload.get("event") or payload.get("type") or payload.get("name") or ""
        return str(raw).strip().lower()

    @staticmethod
    def _extract_payload(event: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(event)
        nested = payload.get("data")
        if isinstance(nested, dict):
            merged = dict(nested)
            for key, value in payload.items():
                if key != "data" and key not in merged:
                    merged[key] = value
            return merged
        return payload

    @staticmethod
    def _matches_event(event_name: str, keywords: List[str]) -> bool:
        if not event_name:
            return False
        return any(keyword in event_name for keyword in keywords)

    def _is_arrival_event(self, event_name: str, payload: Dict[str, Any]) -> bool:
        if payload.get("arrived") is True:
            return True
        return self._matches_event(event_name, ["arriv", "reached", "reach", "waypoint_arrived", "到达"])

    def _is_dock_complete_event(self, event_name: str, payload: Dict[str, Any]) -> bool:
        if payload.get("dock_complete") is True or payload.get("charging") is True and self._matches_event(event_name, ["dock", "charg"]):
            return True
        return self._matches_event(event_name, ["dock_complete", "docking_complete", "charge_complete", "charging_complete", "docked", "充电完成", "回充完成"])

    def _is_nav_started_event(self, event_name: str, payload: Dict[str, Any]) -> bool:
        if payload.get("started") is True:
            return True
        return self._matches_event(event_name, ["nav_start", "nav_started", "navigation_started", "start_navigation", "开始导航"])

    def _is_nav_stop_event(self, event_name: str) -> bool:
        return self._matches_event(event_name, ["nav_stop", "navigation_stopped", "cancel", "abort", "stop"])

    def _update_callback_state(self, **updates: Any) -> None:
        with self._callback_condition:
            self._callback_state.update(updates)
            self._callback_condition.notify_all()

    def handle_callback_event(self, event: Dict[str, Any]) -> None:
        """Merge nav callback events into adapter runtime state."""
        if not isinstance(event, dict):
            return

        payload = self._extract_payload(event)
        event_name = self._event_name(payload)
        timestamp = payload.get("timestamp") or time.time()
        map_id = self._coerce_int(payload.get("current_map_id") or payload.get("map_id"))
        waypoint_id = self._coerce_int(
            payload.get("waypoint_id")
            or payload.get("target_waypoint_id")
            or payload.get("goal_waypoint_id")
        )
        waypoint_name = (
            payload.get("waypoint_name")
            or payload.get("target_waypoint_name")
            or payload.get("goal_name")
            or payload.get("location")
        )
        current_pose = self._extract_current_pose(payload)
        target_pose = self._extract_target_pose(payload)
        nav_running = payload.get("nav_running", payload.get("running"))
        charging = payload.get("charging")

        with self._callback_condition:
            self._callback_state["event_count"] = int(self._callback_state.get("event_count", 0) or 0) + 1
            self._callback_state["last_event"] = event_name or "unknown"
            self._callback_state["last_event_at"] = timestamp
            self._callback_state["last_event_payload"] = self._clone_value(payload)

            if map_id is not None:
                self._callback_state["current_map_id"] = map_id
                self._current_map_id = map_id

            if current_pose:
                self._callback_state["current_pose"] = current_pose

            if target_pose:
                self._callback_state["target_pose"] = target_pose

            if nav_running is not None:
                self._callback_state["nav_running"] = bool(nav_running)

            if charging is not None:
                self._callback_state["charging"] = bool(charging)

            if self._is_nav_started_event(event_name, payload):
                self._callback_state["nav_started_at"] = timestamp
                self._callback_state["nav_running"] = True
                self._callback_state["dock_complete_at"] = None

            if waypoint_id is not None and not self._is_arrival_event(event_name, payload):
                self._callback_state["target_waypoint_id"] = waypoint_id
                self._callback_state["target_updated_at"] = timestamp
                self._callback_state["nav_running"] = True

            if waypoint_name and not self._is_arrival_event(event_name, payload):
                self._callback_state["target_waypoint_name"] = waypoint_name

            if (current_pose or target_pose) and not (
                self._is_arrival_event(event_name, payload)
                or self._is_dock_complete_event(event_name, payload)
                or self._is_nav_stop_event(event_name)
            ):
                self._callback_state["nav_running"] = True

            if self._is_arrival_event(event_name, payload):
                if waypoint_id is None:
                    waypoint_id = self._callback_state.get("target_waypoint_id")
                self._callback_state["arrived_waypoint_id"] = waypoint_id
                self._callback_state["arrived_at"] = timestamp
                self._callback_state["nav_running"] = False

            if self._is_dock_complete_event(event_name, payload):
                self._callback_state["dock_complete_at"] = timestamp
                self._callback_state["nav_running"] = False
                self._callback_state["charging"] = True

            if self._is_nav_stop_event(event_name):
                self._callback_state["nav_running"] = False

            self._callback_condition.notify_all()

    def get_callback_state(self) -> Dict[str, Any]:
        with self._callback_condition:
            return self._clone_value(self._callback_state)

    def _wait_for_callback(self, predicate, timeout: int) -> bool:
        if not self._callback_enabled:
            return False

        with self._callback_condition:
            if not self._callback_state.get("event_count"):
                return False

        deadline = time.time() + timeout
        with self._callback_condition:
            while True:
                if predicate(self._callback_state):
                    return True
                remaining = deadline - time.time()
                if remaining <= 0:
                    return False
                self._callback_condition.wait(timeout=min(1.0, remaining))
    
    def disconnect(self) -> None:
        """断开连接"""
        self._connected = False
        if self.ws_client:
            self.ws_client.disconnect()
    
    # ========== 地图操作 ==========
    def list_maps(self) -> List[MapInfo]:
        """获取地图列表"""
        try:
            result = self._request("GET", "/api/nav/maps/list")
            data = result.get("data", {})
            maps = data.get("maps", []) if isinstance(data, dict) else data
            
            return [
                MapInfo(
                    id=int(m.get("id", 0)),
                    name=str(m.get("name", "")),
                    description=str(m.get("description", ""))
                )
                for m in maps if isinstance(m, dict)
            ]
        except Exception as e:
            print(f"获取地图列表失败: {e}")
            return []
    
    def get_map(self, map_id: int) -> Optional[MapInfo]:
        """获取地图详情"""
        try:
            result = self._request("GET", f"/api/nav/maps/{map_id}")
            data = result.get("data", {})
            if isinstance(data, dict):
                return MapInfo(
                    id=int(data.get("id", 0)),
                    name=str(data.get("name", "")),
                    description=str(data.get("description", ""))
                )
            return None
        except Exception:
            return None
    
    # ========== 路点操作 ==========
    def list_waypoints(self, map_id: int) -> List[WaypointInfo]:
        """获取路点列表"""
        try:
            result = self._request("GET", f"/api/nav/maps/{map_id}/waypoints")
            data = result.get("data", [])
            
            return [
                WaypointInfo(
                    id=int(wp.get("id", 0)),
                    name=str(wp.get("name", "")),
                    map_id=map_id,
                    x=float(wp.get("point", {}).get("x", 0)),
                    y=float(wp.get("point", {}).get("y", 0)),
                    z=float(wp.get("point", {}).get("z", 0)),
                    yaw=float(wp.get("point", {}).get("yaw", 0)),
                    type=str(wp.get("type", "normal"))
                )
                for wp in data if isinstance(wp, dict)
            ]
        except Exception as e:
            print(f"获取路点列表失败: {e}")
            return []
    
    def get_waypoint(self, waypoint_id: int) -> Optional[WaypointInfo]:
        """获取路点详情（通过遍历所有地图）"""
        maps = self.list_maps()
        for m in maps:
            waypoints = self.list_waypoints(m.id)
            for wp in waypoints:
                if wp.id == waypoint_id:
                    return wp
        return None
    
    # ========== 导航操作 ==========
    def start_navigation(self, map_id: int) -> bool:
        """启动导航"""
        try:
            result = self._request(
                "POST", 
                "/api/nav/nav/start",
                data={"map_id": map_id}
            )
            success = result.get("code", -1) == 200
            if success:
                self._current_map_id = map_id
                self._update_callback_state(
                    current_map_id=map_id,
                    nav_running=True,
                    nav_started_at=time.time(),
                    target_waypoint_id=None,
                    target_waypoint_name=None,
                    target_pose=None,
                    target_updated_at=None,
                    arrived_waypoint_id=None,
                    arrived_at=None,
                    dock_complete_at=None,
                )
                # 发送回调
                self.send_callback("nav_start", {"map_id": map_id})
            return success
        except Exception as e:
            print(f"启动导航失败: {e}")
            return False
    
    def stop_navigation(self) -> bool:
        """停止导航"""
        try:
            result = self._request("POST", "/api/nav/nav/stop")
            return result.get("code", -1) == 200
        except Exception as e:
            print(f"停止导航失败: {e}")
            return False
    
    def goto_waypoint(self, waypoint_id: int) -> bool:
        """导航到路点"""
        try:
            result = self._request(
                "POST",
                "/api/nav/nav/goto_waypoint",
                data={"waypoint_id": waypoint_id}
            )
            success = result.get("code", -1) == 200
            if success:
                waypoint = self.get_waypoint(waypoint_id)
                self._update_callback_state(
                    nav_running=True,
                    target_waypoint_id=waypoint_id,
                    target_waypoint_name=waypoint.name if waypoint else None,
                    target_pose={
                        "x": waypoint.x,
                        "y": waypoint.y,
                        "z": waypoint.z,
                        "yaw": waypoint.yaw,
                    } if waypoint else None,
                    target_updated_at=time.time(),
                    arrived_waypoint_id=None,
                    arrived_at=None,
                    dock_complete_at=None,
                )
            return success
        except Exception as e:
            print(f"导航到路点失败: {e}")
            return False
    
    def goto_point(self, x: float, y: float, yaw: float = 0.0) -> bool:
        """导航到坐标点"""
        try:
            result = self._request(
                "POST",
                "/api/nav/nav/goto_point",
                data={
                    "x": x,
                    "y": y,
                    "z": 0.0,
                    "yaw": yaw,
                    "speed": 0.5
                }
            )
            return result.get("code", -1) == 200
        except Exception as e:
            print(f"导航到坐标点失败: {e}")
            return False
    
    def get_navigation_status(self) -> Dict[str, Any]:
        """获取导航状态"""
        try:
            result = self._request("GET", "/api/nav/nav/state")
            data = result.get("data", {})
            if isinstance(data, dict):
                # API返回的是 "running" 而不是 "nav_running"
                return {
                    "nav_running": data.get("running", False),
                    "current_pose": data.get("current_pose"),
                    "map_id": data.get("map_id")
                }
            return {"nav_running": False}
        except Exception:
            return {"nav_running": False}
    
    # ========== 任务操作 ==========
    def list_tasks(self) -> List[TaskInfo]:
        """获取任务列表"""
        try:
            result = self._request(
                "GET", 
                "/api/nav/tasks",
                base_url=self.nav_app_base
            )
            data = result.get("data", {})
            tasks = data.get("tasks", []) if isinstance(data, dict) else data
            
            return [
                TaskInfo(
                    id=int(t.get("id", 0)),
                    name=str(t.get("name", "")),
                    description=str(t.get("description", "")),
                    status=str(t.get("status", "idle"))
                )
                for t in tasks if isinstance(t, dict)
            ]
        except Exception:
            return []
    
    def run_task(self, task_id: int) -> bool:
        """运行任务"""
        try:
            result = self._request(
                "POST",
                f"/api/nav/tasks/{task_id}/run",
                base_url=self.nav_app_base
            )
            return result.get("code", -1) == 0
        except Exception:
            return False
    
    def cancel_task(self) -> bool:
        """取消当前任务"""
        try:
            result = self._request(
                "POST",
                "/api/nav/tasks/cancel_all",
                base_url=self.nav_app_base
            )
            return result.get("code", -1) == 0
        except Exception:
            return False
    
    # ========== 状态操作 ==========
    def get_status(self) -> RobotStatus:
        """获取机器人状态"""
        status = RobotStatus()
        
        # 导航状态
        try:
            nav_data = self.get_navigation_status()
            status.nav_running = nav_data.get("nav_running", False)
            status.current_pose = nav_data.get("current_pose")
        except:
            pass
        
        # 电量状态
        try:
            result = self._request("GET", "/api/nav/status/health")
            data = result.get("data", {})
            if isinstance(data, dict):
                status.battery_soc = data.get("battery_level")
                status.charging = data.get("charging", False)
        except:
            pass

        callback_state = self.get_callback_state()
        if callback_state.get("nav_running") is not None:
            status.nav_running = bool(callback_state.get("nav_running"))
        if isinstance(callback_state.get("current_pose"), dict):
            status.current_pose = callback_state.get("current_pose")
        if callback_state.get("charging") is not None:
            status.charging = bool(callback_state.get("charging"))
        
        return status
    
    def get_battery(self) -> Dict[str, Any]:
        """获取电量信息 - 优先通过WebSocket ROS topic获取"""
        # 尝试通过WebSocket获取电量（如果已连接）
        if self.ws_client and self.ws_client.connected:
            try:
                # 订阅电池SOC topic
                import time
                battery_data = {"soc": None, "charging": False}
                
                def on_battery(msg):
                    battery_data["soc"] = msg.get("data")
                
                def on_charging(msg):
                    battery_data["charging"] = msg.get("data", False)
                
                # 订阅topic
                self.ws_client.on_topic("/bms_soc", on_battery)
                self.ws_client.on_topic("/bms_state", on_charging)
                self.ws_client.subscribe("/bms_soc", "std_msgs/msg/Float32")
                self.ws_client.subscribe("/bms_state", "std_msgs/msg/Bool")
                
                # 等待一秒接收数据
                time.sleep(1)
                
                if battery_data["soc"] is not None:
                    print(f"[Battery] Got from WebSocket: SOC={battery_data['soc']}%")
                    return battery_data
            except Exception as e:
                print(f"[Battery] WebSocket failed: {e}")
        
        # 尝试HTTP API（如果存在）
        try:
            result = self._request("GET", "/api/nav/status/health")
            print(f"[DEBUG] Battery API response: {result}")
            data = result.get("data", {})
            if isinstance(data, dict) and data.get("battery_level") is not None:
                return {
                    "soc": data.get("battery_level"),
                    "charging": data.get("charging", False)
                }
        except Exception as e:
            print(f"[DEBUG] Battery API error: {e}")
        
        # 无法获取电量
        print("[Battery] Cannot get battery info - API not available")
        return {"soc": None, "charging": False, "error": "Battery API not available"}
    
    # ========== 动作操作 ==========
    def motion_stand(self) -> bool:
        """站立 - 通过/cmd_vel发送z轴正值"""
        try:
            if self.ws_client and self.ws_client.connected:
                # 发送站立命令 (z轴速度 > 0)，通过设置合适的速度组合
                # 实际上，通常站立是通过设置z轴linear.z为正
                success = self.ws_client.publish(
                    "/cmd_vel",
                    {
                        "linear": {"x": 0.0, "y": 0.0, "z": 1.0},
                        "angular": {"x": 0.0, "y": 0.0, "z": 0.0}
                    },
                    msg_type="geometry_msgs/msg/Twist"
                )
                if success:
                    print("[Motion] Stand command sent via WebSocket (z=1.0)")
                    return True
            
            print("[Motion] Stand: WebSocket not available")
            return False
        except Exception as e:
            print(f"[Motion] Stand failed: {e}")
            return False
    
    def motion_lie_down(self) -> bool:
        """趴下 - 通过/cmd_vel发送z轴负值"""
        try:
            if self.ws_client and self.ws_client.connected:
                # 发送趴下命令 (z轴速度 < 0)
                success = self.ws_client.publish(
                    "/cmd_vel",
                    {
                        "linear": {"x": 0.0, "y": 0.0, "z": -1.0},
                        "angular": {"x": 0.0, "y": 0.0, "z": 0.0}
                    },
                    msg_type="geometry_msgs/msg/Twist"
                )
                if success:
                    print("[Motion] Lie down command sent via WebSocket (z=-1.0)")
                    return True
            
            print("[Motion] Lie down: WebSocket not available")
            return False
        except Exception as e:
            print(f"[Motion] Lie down failed: {e}")
            return False
    
    def set_light(self, code: int) -> bool:
        """设置灯光 - 通过WebSocket (Rosbridge)"""
        try:
            # 优先使用WebSocket
            if self.ws_client and self.ws_client.connected:
                success = self.ws_client.control_light(code)
                if success:
                    return True
            
            # 回退到HTTP API
            result = self._request(
                "POST",
                "/api/nav/light/set",
                base_url=self.nav_app_base,
                data={"code": code}
            )
            return result.get("code", -1) == 0
        except Exception:
            return False
    
    def play_audio(self, text: str) -> bool:
        """播放语音 - 通过nav_app的TTS API"""
        try:
            result = self._request(
                "POST",
                "/api/nav/tts/play",
                base_url=self.nav_app_base,
                data={"text": text}
            )
            return result.get("code", -1) == 0
        except Exception:
            return False
    
    # ========== 等待事件 ==========
    def wait_nav_started(self, timeout: int = 60) -> bool:
        """等待导航启动"""
        if self._wait_for_callback(lambda state: bool(state.get("nav_started_at")), timeout):
            return True
        try:
            result = self._request(
                "POST",
                "/api/nav/events/wait_nav_started",
                data={"timeout": timeout}
            )
            data = result.get("data", {})
            success = data.get("started", False) if isinstance(data, dict) else False
            if success:
                self._update_callback_state(nav_started_at=time.time(), nav_running=True)
            return success
        except Exception:
            return self._wait_for_callback(lambda state: bool(state.get("nav_started_at")), timeout)

    def wait_arrival(self, waypoint_id: int, timeout: int = 300) -> bool:
        """等待到达路点"""
        if self._wait_for_callback(
            lambda state: state.get("arrived_waypoint_id") == waypoint_id and bool(state.get("arrived_at")),
            timeout,
        ):
            return True
        try:
            result = self._request(
                "POST",
                "/api/nav/events/wait_arrival",
                data={"waypoint_id": waypoint_id, "timeout": timeout}
            )
            data = result.get("data", {})
            success = data.get("arrived", False) if isinstance(data, dict) else False
            if success:
                self._update_callback_state(
                    nav_running=False,
                    arrived_waypoint_id=waypoint_id,
                    arrived_at=time.time(),
                )
            return success
        except Exception:
            return self._wait_for_callback(
                lambda state: state.get("arrived_waypoint_id") == waypoint_id and bool(state.get("arrived_at")),
                timeout,
            )

    def wait_dock_complete(self, timeout: int = 300) -> bool:
        """等待回充完成"""
        if self._wait_for_callback(lambda state: bool(state.get("dock_complete_at")), timeout):
            return True
        try:
            result = self._request(
                "POST",
                "/api/nav/events/wait_dock_complete",
                data={"timeout": timeout}
            )
            data = result.get("data", {})
            success = data.get("result", False) if isinstance(data, dict) else False
            if success:
                self._update_callback_state(
                    nav_running=False,
                    charging=True,
                    dock_complete_at=time.time(),
                )
            return success
        except Exception:
            return self._wait_for_callback(lambda state: bool(state.get("dock_complete_at")), timeout)
    
    def goto_dock(self, map_id: int = None) -> bool:
        """前往回充点
        
        Args:
            map_id: 地图ID，如果提供则先查找该地图下的回充点路点
        """
        try:
            # 策略1: 如果提供了 map_id，先在该地图下查找回充点路点
            if map_id:
                try:
                    waypoints = self.list_waypoints(map_id)
                    dock_waypoint = None
                    for wp in waypoints:
                        if "回充" in wp.name or "dock" in wp.name.lower() or "充电" in wp.name:
                            dock_waypoint = wp
                            break
                    
                    if dock_waypoint:
                        return self.goto_waypoint(dock_waypoint.id)
                except Exception as e:
                    print(f"查找回充点路点失败: {e}")
            
            # 策略2: 使用当前地图
            if self._current_map_id:
                try:
                    waypoints = self.list_waypoints(self._current_map_id)
                    dock_waypoint = None
                    for wp in waypoints:
                        if "回充" in wp.name or "dock" in wp.name.lower() or "充电" in wp.name:
                            dock_waypoint = wp
                            break
                    
                    if dock_waypoint:
                        return self.goto_waypoint(dock_waypoint.id)
                except Exception as e:
                    print(f"使用当前地图查找回充点失败: {e}")
            
            # 策略3: 直接调用回充API（不依赖路点）
            result = self._request(
                "POST",
                "/api/nav/dock/goto",
                base_url=self.nav_app_base
            )
            return result.get("code", -1) == 0
        except Exception as e:
            print(f"前往回充点失败: {e}")
            return False

    def get_navigation_status(self) -> Dict[str, Any]:
        """优先按文档定义读取导航状态，并兼容旧接口。"""
        status = {"nav_running": False}

        for endpoint in ("/api/nav/events/state", "/api/nav/nav/state"):
            try:
                result = self._request("GET", endpoint)
                data = result.get("data", {})
                if not isinstance(data, dict):
                    continue

                map_id = data.get("current_map_id")
                if map_id is None:
                    map_id = data.get("map_id")

                if map_id is not None:
                    try:
                        self._current_map_id = int(map_id)
                    except (TypeError, ValueError):
                        self._current_map_id = map_id

                status.update({
                    "nav_running": data.get("nav_running", data.get("running", False)),
                    "mapping_active": data.get("mapping_active", False),
                    "current_map_id": map_id,
                    "map_id": map_id,
                    "timestamp": data.get("timestamp"),
                })
                break
            except Exception:
                continue

        try:
            pose_result = self._request("GET", "/api/nav/status/current_pose")
            pose_data = pose_result.get("data", {})
            if isinstance(pose_data, dict):
                status["current_pose"] = pose_data
        except Exception:
            pass

        callback_state = self.get_callback_state()
        if callback_state.get("current_map_id") is not None:
            status["current_map_id"] = callback_state.get("current_map_id")
            status["map_id"] = callback_state.get("current_map_id")
        if callback_state.get("nav_running") is not None:
            status["nav_running"] = bool(callback_state.get("nav_running"))
        if isinstance(callback_state.get("current_pose"), dict):
            status["current_pose"] = callback_state.get("current_pose")
        if isinstance(callback_state.get("target_pose"), dict):
            status["target_pose"] = callback_state.get("target_pose")
        if callback_state.get("target_waypoint_id") is not None:
            status["target_waypoint_id"] = callback_state.get("target_waypoint_id")
        if callback_state.get("target_waypoint_name"):
            status["target_waypoint_name"] = callback_state.get("target_waypoint_name")
        if callback_state.get("last_event"):
            status["last_event"] = callback_state.get("last_event")
            status["callback_event_count"] = callback_state.get("event_count", 0)
            status["callback_timestamp"] = callback_state.get("last_event_at")

        return status

    def resolve_current_map(self) -> Optional[MapInfo]:
        """尽量从当前导航状态恢复当前地图。"""
        map_id = self._current_map_id
        if map_id is None:
            nav_status = self.get_navigation_status()
            map_id = nav_status.get("current_map_id") or nav_status.get("map_id")

        if map_id is None:
            return None

        try:
            map_id = int(map_id)
        except (TypeError, ValueError):
            return None

        current_map = self.get_map(map_id)
        if current_map:
            return current_map

        for map_info in self.list_maps():
            if map_info.id == map_id:
                return map_info
        return None

    def goto_dock(self, map_id: int = None) -> bool:
        """优先使用 dock_to_waypoint 触发标准回充/对接流程。"""
        search_map_ids = []
        if map_id is not None:
            search_map_ids.append(map_id)
        if self._current_map_id is not None and self._current_map_id not in search_map_ids:
            search_map_ids.append(self._current_map_id)

        for candidate_map_id in search_map_ids:
            try:
                waypoints = self.list_waypoints(candidate_map_id)
                dock_waypoint = None
                for wp in waypoints:
                    name = (wp.name or "").lower()
                    if "回充" in wp.name or "充电" in wp.name or "dock" in name:
                        dock_waypoint = wp
                        break

                if dock_waypoint:
                    result = self._request(
                        "POST",
                        "/api/nav/nav/dock_to_waypoint",
                        data={"waypoint_id": dock_waypoint.id}
                    )
                    success = result.get("code", -1) == 200
                    if success:
                        self._update_callback_state(
                            nav_running=True,
                            target_waypoint_id=dock_waypoint.id,
                            target_waypoint_name=dock_waypoint.name,
                            target_pose={
                                "x": dock_waypoint.x,
                                "y": dock_waypoint.y,
                                "z": dock_waypoint.z,
                                "yaw": dock_waypoint.yaw,
                            },
                            target_updated_at=time.time(),
                            dock_complete_at=None,
                            arrived_waypoint_id=None,
                            arrived_at=None,
                        )
                    return success
            except Exception as e:
                print(f"Dock to waypoint failed on map {candidate_map_id}: {e}")

        try:
            result = self._request(
                "POST",
                "/api/nav/dock/goto",
                base_url=self.nav_app_base
            )
            success = result.get("code", -1) in (0, 200)
            if success:
                self._update_callback_state(
                    nav_running=True,
                    target_waypoint_id=None,
                    target_waypoint_name="回充点",
                    target_pose=None,
                    target_updated_at=time.time(),
                    dock_complete_at=None,
                    arrived_waypoint_id=None,
                    arrived_at=None,
                )
            return success
        except Exception as e:
            print(f"Goto dock failed: {e}")
            return False


def create_fishbot_adapter(nav_server_host: str = "127.0.0.1", 
                          nav_server_port: int = 9001,
                          nav_app_host: str = "127.0.0.1",
                          nav_app_port: int = 9002,
                          rosbridge_host: str = "127.0.0.1",
                          rosbridge_port: int = 9090,
                          rosbridge_path: str = "/api/rt") -> FishBotAdapter:
    """工厂函数：创建FishBot适配器"""
    return FishBotAdapter(
        nav_server_host, nav_server_port, 
        nav_app_host, nav_app_port,
        rosbridge_host, rosbridge_port, rosbridge_path
    )
