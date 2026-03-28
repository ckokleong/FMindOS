"""
Unitree Go2 适配器
接入宇树Go2四足机器狗的实际API
支持通过 unitree_sdk2py (CycloneDDS) 和 HTTP API 进行控制
"""

from typing import Any, Dict, List, Optional
import json
import threading
import time
import urllib.request
import urllib.error
from urllib.parse import urlencode

from fishmindos.adapters.base import RobotAdapter, MapInfo, WaypointInfo, TaskInfo, RobotStatus


class UnitreeGo2APIError(Exception):
    """Unitree Go2 API错误"""
    pass


class UnitreeGo2Adapter(RobotAdapter):
    """
    Unitree Go2 适配器
    接入宇树Go2四足机器人的控制API

    支持两种通信方式:
    1. unitree_sdk2py (CycloneDDS) - 用于运动控制、状态订阅等实时操作
    2. HTTP API - 用于导航管理、地图操作等高级功能

    Go2 默认网络配置:
    - 机器人IP: 192.168.123.161
    - 通信端口: 8081 (HTTP API)
    """

    def __init__(self, robot_ip: str = "192.168.123.161",
                 robot_port: int = 8081,
                 nav_server_host: str = "192.168.123.161",
                 nav_server_port: int = 8081,
                 nav_app_host: str = "192.168.123.161",
                 nav_app_port: int = 8081):
        self.robot_ip = robot_ip
        self.robot_port = robot_port
        self.robot_base = f"http://{robot_ip}:{robot_port}"
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

        # Go2 SDK clients (optional, requires unitree_sdk2py)
        self._sport_client = None
        self._robot_state_client = None
        self._sdk_available = False
        self._battery_soc = None
        self._charging = False
        self._current_pose = {"x": 0.0, "y": 0.0, "yaw": 0.0}

        # Try to initialize SDK
        self._init_sdk()

    def _init_sdk(self):
        """Try to initialize unitree_sdk2py SDK"""
        try:
            from unitree_sdk2py.core.channel import ChannelFactoryInitialize
            from unitree_sdk2py.go2.sport.sport_client import SportClient
            from unitree_sdk2py.go2.robot_state.robot_state_client import RobotStateClient

            ChannelFactoryInitialize(0, self.robot_ip)

            self._sport_client = SportClient()
            self._sport_client.SetTimeout(5.0)
            self._sport_client.Init()

            self._robot_state_client = RobotStateClient()
            self._robot_state_client.SetTimeout(5.0)
            self._robot_state_client.Init()

            self._sdk_available = True
            print(f"[Go2] SDK initialized: {self.robot_ip}")
        except ImportError:
            print("[Go2] unitree_sdk2py not installed, using HTTP API only")
            self._sdk_available = False
        except Exception as e:
            print(f"[Go2] SDK init failed: {e}, using HTTP API only")
            self._sdk_available = False

    @property
    def vendor_name(self) -> str:
        return "Unitree Go2"

    def _request(self, method: str, endpoint: str, base_url: str = None,
                 data: Dict = None, params: Dict = None) -> Dict:
        """Send HTTP request"""
        base = base_url or self.robot_base
        url = f"{base}{endpoint}"

        if params:
            url += "?" + urlencode(params)

        headers = {"Content-Type": "application/json"}

        body = json.dumps(data).encode('utf-8') if data else None

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result
        except urllib.error.HTTPError as e:
            raise UnitreeGo2APIError(f"HTTP {e.code}: {e.reason}")
        except Exception as e:
            raise UnitreeGo2APIError(f"Request failed: {e}")

    def connect(self) -> Dict[str, Any]:
        """
        Health check - check each component

        Returns:
            {
                "success": bool,
                "sdk": {"connected": bool, "error": str|None},
                "nav_server": {"connected": bool, "error": str|None},
                "nav_app": {"connected": bool, "error": str|None},
                "overall_status": str  # "healthy" | "degraded" | "offline"
            }
        """
        results = {
            "success": False,
            "sdk": {"connected": False, "error": None},
            "nav_server": {"connected": False, "error": None},
            "nav_app": {"connected": False, "error": None},
            "overall_status": "offline"
        }

        # 1. Check SDK connection
        if self._sdk_available:
            try:
                results["sdk"]["connected"] = True
            except Exception as e:
                results["sdk"]["error"] = str(e)
        else:
            results["sdk"]["error"] = "SDK not available"

        # 2. Check nav_server (HTTP API)
        try:
            result = self._request("GET", "/api/nav/maps/list", base_url=self.nav_server_base)
            if isinstance(result, dict) and result.get("code", 0) != 0:
                error_msg = result.get("msg", "unknown error")
                results["nav_server"]["error"] = f"Service error: {error_msg}"
            else:
                results["nav_server"]["connected"] = True
        except Exception as e:
            results["nav_server"]["error"] = str(e)

        # 3. Check nav_app
        try:
            if self.nav_server_base == self.nav_app_base:
                results["nav_app"] = results["nav_server"].copy()
            else:
                self._request("GET", "/api/nav/maps/list", base_url=self.nav_app_base)
                results["nav_app"]["connected"] = True
        except Exception as e:
            results["nav_app"]["error"] = str(e)

        # Calculate overall status
        connected_count = sum([
            results["sdk"]["connected"],
            results["nav_server"]["connected"],
            results["nav_app"]["connected"]
        ])

        if connected_count >= 2:
            results["overall_status"] = "healthy"
            results["success"] = True
            self._connected = True
        elif connected_count >= 1:
            results["overall_status"] = "degraded"
            results["success"] = True
            self._connected = True
        else:
            results["overall_status"] = "offline"
            self._connected = False

        return results

    def set_callback_url(self, url: str, enable: bool = True) -> bool:
        self._callback_enabled = bool(enable and url)
        return super().set_callback_url(url, enable)

    @staticmethod
    def _clone_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: UnitreeGo2Adapter._clone_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [UnitreeGo2Adapter._clone_value(item) for item in value]
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
            "x": "x", "y": "y", "z": "z",
            "yaw": "yaw", "theta": "yaw",
            "roll": "roll", "pitch": "pitch",
            "time": "time", "timestamp": "timestamp",
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
            f"{prefix}_x": "x", f"{prefix}_y": "y", f"{prefix}_z": "z",
            f"{prefix}_yaw": "yaw", f"{prefix}_theta": "yaw",
            f"{prefix}_roll": "roll", f"{prefix}_pitch": "pitch",
            f"{prefix}_time": "time", f"{prefix}_timestamp": "timestamp",
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
        if payload.get("dock_complete") is True or (payload.get("charging") is True and self._matches_event(event_name, ["dock", "charg"])):
            return True
        return self._matches_event(event_name, [
            "dock_complete", "docking_complete", "charge_complete",
            "charging_complete", "docked", "充电完成", "回充完成"
        ])

    def _is_nav_started_event(self, event_name: str, payload: Dict[str, Any]) -> bool:
        if payload.get("started") is True:
            return True
        return self._matches_event(event_name, [
            "nav_start", "nav_started", "navigation_started",
            "start_navigation", "开始导航"
        ])

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
        """Disconnect"""
        self._connected = False
        print("[Go2] Disconnected")

    # ========== Map operations ==========
    def list_maps(self) -> List[MapInfo]:
        try:
            result = self._request("GET", "/api/nav/maps/list", base_url=self.nav_server_base)
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
            print(f"[Go2] Failed to list maps: {e}")
            return []

    def get_map(self, map_id: int) -> Optional[MapInfo]:
        try:
            result = self._request("GET", f"/api/nav/maps/{map_id}", base_url=self.nav_server_base)
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

    # ========== Waypoint operations ==========
    def list_waypoints(self, map_id: int) -> List[WaypointInfo]:
        try:
            result = self._request("GET", f"/api/nav/maps/{map_id}/waypoints", base_url=self.nav_server_base)
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
            print(f"[Go2] Failed to list waypoints: {e}")
            return []

    def get_waypoint(self, waypoint_id: int) -> Optional[WaypointInfo]:
        maps = self.list_maps()
        for m in maps:
            waypoints = self.list_waypoints(m.id)
            for wp in waypoints:
                if wp.id == waypoint_id:
                    return wp
        return None

    # ========== Navigation operations ==========
    def start_navigation(self, map_id: int) -> bool:
        try:
            result = self._request(
                "POST", "/api/nav/nav/start",
                base_url=self.nav_server_base,
                data={"map_id": map_id}
            )
            success = result.get("code", -1) in (0, 200)
            if success:
                self._current_map_id = map_id
                self._update_callback_state(
                    current_map_id=map_id, nav_running=True,
                    nav_started_at=time.time(),
                    target_waypoint_id=None, target_waypoint_name=None,
                    target_pose=None, target_updated_at=None,
                    arrived_waypoint_id=None, arrived_at=None,
                    dock_complete_at=None,
                )
                self.send_callback("nav_start", {"map_id": map_id})
            return success
        except Exception as e:
            print(f"[Go2] Failed to start navigation: {e}")
            return False

    def stop_navigation(self) -> bool:
        try:
            result = self._request("POST", "/api/nav/nav/stop", base_url=self.nav_server_base)
            return result.get("code", -1) in (0, 200)
        except Exception as e:
            print(f"[Go2] Failed to stop navigation: {e}")
            return False

    def goto_waypoint(self, waypoint_id: int) -> bool:
        try:
            result = self._request(
                "POST", "/api/nav/nav/goto_waypoint",
                base_url=self.nav_server_base,
                data={"waypoint_id": waypoint_id}
            )
            success = result.get("code", -1) in (0, 200)
            if success:
                waypoint = self.get_waypoint(waypoint_id)
                self._update_callback_state(
                    nav_running=True,
                    target_waypoint_id=waypoint_id,
                    target_waypoint_name=waypoint.name if waypoint else None,
                    target_pose={
                        "x": waypoint.x, "y": waypoint.y,
                        "z": waypoint.z, "yaw": waypoint.yaw,
                    } if waypoint else None,
                    target_updated_at=time.time(),
                    arrived_waypoint_id=None, arrived_at=None,
                    dock_complete_at=None,
                )
            return success
        except Exception as e:
            print(f"[Go2] Failed to goto waypoint: {e}")
            return False

    def goto_point(self, x: float, y: float, yaw: float = 0.0) -> bool:
        try:
            result = self._request(
                "POST", "/api/nav/nav/goto_point",
                base_url=self.nav_server_base,
                data={"x": x, "y": y, "z": 0.0, "yaw": yaw, "speed": 0.5}
            )
            return result.get("code", -1) in (0, 200)
        except Exception as e:
            print(f"[Go2] Failed to goto point: {e}")
            return False

    def get_navigation_status(self) -> Dict[str, Any]:
        status = {"nav_running": False}
        for endpoint in ("/api/nav/events/state", "/api/nav/nav/state"):
            try:
                result = self._request("GET", endpoint, base_url=self.nav_server_base)
                data = result.get("data", {})
                if not isinstance(data, dict):
                    continue
                map_id = data.get("current_map_id") or data.get("map_id")
                if map_id is not None:
                    try:
                        self._current_map_id = int(map_id)
                    except (TypeError, ValueError):
                        self._current_map_id = map_id
                status.update({
                    "nav_running": data.get("nav_running", data.get("running", False)),
                    "mapping_active": data.get("mapping_active", False),
                    "current_map_id": map_id, "map_id": map_id,
                    "timestamp": data.get("timestamp"),
                })
                break
            except Exception:
                continue

        try:
            pose_result = self._request("GET", "/api/nav/status/current_pose", base_url=self.nav_server_base)
            pose_data = pose_result.get("data", {})
            if isinstance(pose_data, dict):
                status["current_pose"] = pose_data
        except Exception:
            pass

        callback_state = self.get_callback_state()
        if callback_state.get("current_map_id") is not None:
            status["current_map_id"] = callback_state["current_map_id"]
            status["map_id"] = callback_state["current_map_id"]
        if callback_state.get("nav_running") is not None:
            status["nav_running"] = bool(callback_state["nav_running"])
        if isinstance(callback_state.get("current_pose"), dict):
            status["current_pose"] = callback_state["current_pose"]
        if isinstance(callback_state.get("target_pose"), dict):
            status["target_pose"] = callback_state["target_pose"]
        if callback_state.get("target_waypoint_id") is not None:
            status["target_waypoint_id"] = callback_state["target_waypoint_id"]
        if callback_state.get("target_waypoint_name"):
            status["target_waypoint_name"] = callback_state["target_waypoint_name"]
        if callback_state.get("last_event"):
            status["last_event"] = callback_state["last_event"]
            status["callback_event_count"] = callback_state.get("event_count", 0)
            status["callback_timestamp"] = callback_state.get("last_event_at")
        return status

    # ========== Task operations ==========
    def list_tasks(self) -> List[TaskInfo]:
        try:
            result = self._request("GET", "/api/nav/tasks", base_url=self.nav_app_base)
            data = result.get("data", {})
            tasks = data.get("tasks", []) if isinstance(data, dict) else data
            return [
                TaskInfo(
                    id=int(t.get("id", 0)), name=str(t.get("name", "")),
                    description=str(t.get("description", "")),
                    status=str(t.get("status", "idle"))
                )
                for t in tasks if isinstance(t, dict)
            ]
        except Exception:
            return []

    def run_task(self, task_id: int) -> bool:
        try:
            result = self._request("POST", f"/api/nav/tasks/{task_id}/run", base_url=self.nav_app_base)
            return result.get("code", -1) in (0, 200)
        except Exception:
            return False

    def cancel_task(self) -> bool:
        try:
            result = self._request("POST", "/api/nav/tasks/cancel_all", base_url=self.nav_app_base)
            return result.get("code", -1) in (0, 200)
        except Exception:
            return False

    # ========== Status operations ==========
    def get_status(self) -> RobotStatus:
        status = RobotStatus()
        try:
            nav_data = self.get_navigation_status()
            status.nav_running = nav_data.get("nav_running", False)
            status.current_pose = nav_data.get("current_pose")
        except Exception:
            pass

        # Try SDK for battery
        if self._sdk_available:
            try:
                battery_info = self._get_battery_from_sdk()
                if battery_info.get("soc") is not None:
                    status.battery_soc = battery_info["soc"]
                    status.charging = battery_info.get("charging", False)
            except Exception:
                pass

        # Fallback to HTTP for battery
        if status.battery_soc is None:
            try:
                result = self._request("GET", "/api/nav/status/health", base_url=self.nav_server_base)
                data = result.get("data", {})
                if isinstance(data, dict):
                    status.battery_soc = data.get("battery_level")
                    status.charging = data.get("charging", False)
            except Exception:
                pass

        callback_state = self.get_callback_state()
        if callback_state.get("nav_running") is not None:
            status.nav_running = bool(callback_state["nav_running"])
        if isinstance(callback_state.get("current_pose"), dict):
            status.current_pose = callback_state["current_pose"]
        if callback_state.get("charging") is not None:
            status.charging = bool(callback_state["charging"])
        return status

    def _get_battery_from_sdk(self) -> Dict[str, Any]:
        if not self._sdk_available or not self._robot_state_client:
            return {"soc": None, "charging": False}
        try:
            code, state = self._robot_state_client.ServiceState(
                "sport_mode", ["battery_percentage", "battery_charging"]
            )
            if code == 0 and state:
                return {
                    "soc": state.get("battery_percentage"),
                    "charging": state.get("battery_charging", False)
                }
        except Exception:
            pass
        return {"soc": None, "charging": False}

    def get_battery(self) -> Dict[str, Any]:
        if self._sdk_available:
            battery = self._get_battery_from_sdk()
            if battery.get("soc") is not None:
                return battery
        try:
            result = self._request("GET", "/api/nav/status/health", base_url=self.nav_server_base)
            data = result.get("data", {})
            if isinstance(data, dict) and data.get("battery_level") is not None:
                return {"soc": data["battery_level"], "charging": data.get("charging", False)}
        except Exception:
            pass
        return {"soc": None, "charging": False, "error": "Battery API not available"}

    def get_current_pose(self) -> Dict[str, float]:
        return self._current_pose.copy()

    # ========== Motion operations ==========
    def motion_stand(self) -> bool:
        """Stand up - via Go2 Sport API"""
        try:
            if self._sdk_available and self._sport_client:
                code = self._sport_client.StandUp()
                if code == 0:
                    print("[Go2] StandUp command sent via SDK")
                    return True
            # Fallback to HTTP API
            try:
                result = self._request("POST", "/api/sport/stand_up", data={})
                if result.get("code", -1) in (0, 200):
                    print("[Go2] StandUp command sent via HTTP")
                    return True
            except Exception:
                pass
            print("[Go2] Stand: No available interface")
            return False
        except Exception as e:
            print(f"[Go2] Stand failed: {e}")
            return False

    def motion_lie_down(self) -> bool:
        """Lie down - via Go2 Sport API"""
        try:
            if self._sdk_available and self._sport_client:
                code = self._sport_client.StandDown()
                if code == 0:
                    print("[Go2] StandDown command sent via SDK")
                    return True
            # Fallback to HTTP API
            try:
                result = self._request("POST", "/api/sport/stand_down", data={})
                if result.get("code", -1) in (0, 200):
                    print("[Go2] StandDown command sent via HTTP")
                    return True
            except Exception:
                pass
            print("[Go2] Lie down: No available interface")
            return False
        except Exception as e:
            print(f"[Go2] Lie down failed: {e}")
            return False

    def set_light(self, code: int) -> bool:
        try:
            result = self._request("POST", "/api/robot/light", data={"code": code})
            return result.get("code", -1) in (0, 200)
        except Exception:
            try:
                result = self._request("POST", "/api/nav/light/set", base_url=self.nav_app_base, data={"code": code})
                return result.get("code", -1) in (0, 200)
            except Exception:
                return False

    def play_audio(self, text: str) -> bool:
        try:
            result = self._request("POST", "/api/nav/tts/play", base_url=self.nav_app_base, data={"text": text})
            return result.get("code", -1) in (0, 200)
        except Exception:
            try:
                result = self._request("POST", "/api/robot/tts", data={"text": text})
                return result.get("code", -1) in (0, 200)
            except Exception:
                return False

    # ========== Wait for events ==========
    def wait_nav_started(self, timeout: int = 60) -> bool:
        if self._wait_for_callback(lambda state: bool(state.get("nav_started_at")), timeout):
            return True
        try:
            result = self._request(
                "POST", "/api/nav/events/wait_nav_started",
                base_url=self.nav_server_base, data={"timeout": timeout}
            )
            data = result.get("data", {})
            success = data.get("started", False) if isinstance(data, dict) else False
            if success:
                self._update_callback_state(nav_started_at=time.time(), nav_running=True)
            return success
        except Exception:
            return self._wait_for_callback(lambda state: bool(state.get("nav_started_at")), timeout)

    def wait_arrival(self, waypoint_id: int, timeout: int = 300) -> bool:
        if self._wait_for_callback(
            lambda state: state.get("arrived_waypoint_id") == waypoint_id and bool(state.get("arrived_at")),
            timeout,
        ):
            return True
        try:
            result = self._request(
                "POST", "/api/nav/events/wait_arrival",
                base_url=self.nav_server_base,
                data={"waypoint_id": waypoint_id, "timeout": timeout}
            )
            data = result.get("data", {})
            success = data.get("arrived", False) if isinstance(data, dict) else False
            if success:
                self._update_callback_state(
                    nav_running=False, arrived_waypoint_id=waypoint_id, arrived_at=time.time(),
                )
            return success
        except Exception:
            return self._wait_for_callback(
                lambda state: state.get("arrived_waypoint_id") == waypoint_id and bool(state.get("arrived_at")),
                timeout,
            )

    def wait_dock_complete(self, timeout: int = 300) -> bool:
        if self._wait_for_callback(lambda state: bool(state.get("dock_complete_at")), timeout):
            return True
        try:
            result = self._request(
                "POST", "/api/nav/events/wait_dock_complete",
                base_url=self.nav_server_base, data={"timeout": timeout}
            )
            data = result.get("data", {})
            success = data.get("result", False) if isinstance(data, dict) else False
            if success:
                self._update_callback_state(nav_running=False, charging=True, dock_complete_at=time.time())
            return success
        except Exception:
            return self._wait_for_callback(lambda state: bool(state.get("dock_complete_at")), timeout)

    def goto_dock(self, map_id: int = None) -> bool:
        """Go to charging dock"""
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
                        "POST", "/api/nav/nav/dock_to_waypoint",
                        base_url=self.nav_server_base,
                        data={"waypoint_id": dock_waypoint.id}
                    )
                    success = result.get("code", -1) in (0, 200)
                    if success:
                        self._update_callback_state(
                            nav_running=True,
                            target_waypoint_id=dock_waypoint.id,
                            target_waypoint_name=dock_waypoint.name,
                            target_pose={
                                "x": dock_waypoint.x, "y": dock_waypoint.y,
                                "z": dock_waypoint.z, "yaw": dock_waypoint.yaw,
                            },
                            target_updated_at=time.time(),
                            dock_complete_at=None,
                            arrived_waypoint_id=None, arrived_at=None,
                        )
                    return success
            except Exception as e:
                print(f"[Go2] Dock to waypoint failed on map {candidate_map_id}: {e}")

        try:
            result = self._request("POST", "/api/nav/dock/goto", base_url=self.nav_app_base)
            success = result.get("code", -1) in (0, 200)
            if success:
                self._update_callback_state(
                    nav_running=True, target_waypoint_id=None,
                    target_waypoint_name="回充点", target_pose=None,
                    target_updated_at=time.time(), dock_complete_at=None,
                    arrived_waypoint_id=None, arrived_at=None,
                )
            return success
        except Exception as e:
            print(f"[Go2] Goto dock failed: {e}")
            return False

    def resolve_current_map(self) -> Optional[MapInfo]:
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


def create_go2_adapter(
    robot_ip: str = "192.168.123.161",
    robot_port: int = 8081,
    nav_server_host: str = "192.168.123.161",
    nav_server_port: int = 8081,
    nav_app_host: str = "192.168.123.161",
    nav_app_port: int = 8081,
    **kwargs
) -> UnitreeGo2Adapter:
    """Factory function: create Unitree Go2 adapter"""
    return UnitreeGo2Adapter(
        robot_ip=robot_ip,
        robot_port=robot_port,
        nav_server_host=nav_server_host,
        nav_server_port=nav_server_port,
        nav_app_host=nav_app_host,
        nav_app_port=nav_app_port,
    )
