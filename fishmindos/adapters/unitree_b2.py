"""
Unitree B2 适配器
通过 unitree_sdk2py DDS 接口接入宇树科技 B2 四足机器人
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from fishmindos.adapters.base import (
    AdapterError,
    MapInfo,
    RobotAdapter,
    RobotStatus,
    TaskInfo,
    WaypointInfo,
)
from fishmindos.config import UnitreeB2Config

# 回充点的候选名称（匹配任何一个即跳转充电桩）
_DOCK_NAMES = {"回充点", "dock", "充电", "charge", "充电桩"}


class UnitreeB2Adapter(RobotAdapter):
    """
    Unitree B2 四足机器人适配器

    通讯方式: DDS (unitree_sdk2py Python bindings)
    地图/路点: 本地 JSON 文件管理
    导航: SportClient.MoveToPos(dx, dy, dyaw)
    到达检测: 轮询 SportModeState 速度
    状态更新: 后台线程每 500ms 读取一次
    TTS: pyttsx3 或 gTTS（板载 PC 扬声器）
    """

    def __init__(
        self,
        robot_ip: str = "192.168.123.161",
        network_interface: str = "eth0",
        enable_lease: bool = True,
        waypoints_file: str = "waypoints.json",
        maps_file: str = "maps.json",
        **kwargs,
    ):
        self.config = UnitreeB2Config(
            robot_ip=robot_ip,
            network_interface=network_interface,
            enable_lease=enable_lease,
            waypoints_file=waypoints_file,
            maps_file=maps_file,
        )

        # SDK 客户端（延迟初始化，避免无 SDK 时报错）
        self._sport_client = None
        self._state_subscriber = None

        # 内部状态
        self._connected = False
        self._current_pose: Dict[str, float] = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self._velocity: Dict[str, float] = {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}
        self._battery_soc: float = 100.0
        self._nav_running: bool = False
        self._charging: bool = False
        self._current_map_id: Optional[int] = None

        # 本地地图/路点数据（从 JSON 文件加载）
        self._maps: List[MapInfo] = []
        self._waypoints: Dict[int, List[WaypointInfo]] = {}  # map_id -> waypoints

        # 回调兼容层
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
        self._callback_lock = threading.Lock()

        # 后台状态轮询线程
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_stop = threading.Event()

        print(f"[UnitreeB2] 适配器初始化: {robot_ip} (interface={network_interface})")

    # ------------------------------------------------------------------
    # 基本属性
    # ------------------------------------------------------------------

    @property
    def vendor_name(self) -> str:
        return "Unitree B2 Navigator"

    # ------------------------------------------------------------------
    # 私有工具方法
    # ------------------------------------------------------------------

    def _load_waypoints_file(self) -> None:
        """从 JSON 文件加载路点数据"""
        path = self.config.waypoints_file
        if not os.path.exists(path):
            print(f"[UnitreeB2] 路点文件不存在: {path}")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw: Dict[str, List[Dict]] = json.load(f)
            for map_id_str, wps in raw.items():
                map_id = int(map_id_str)
                self._waypoints[map_id] = [
                    WaypointInfo(
                        id=wp["id"],
                        name=wp["name"],
                        map_id=map_id,
                        x=wp.get("x", 0.0),
                        y=wp.get("y", 0.0),
                        z=wp.get("z", 0.0),
                        yaw=wp.get("yaw", 0.0),
                    )
                    for wp in wps
                ]
            print(
                f"[UnitreeB2] 已加载路点文件: {path} "
                f"({sum(len(v) for v in self._waypoints.values())} 个路点)"
            )
        except Exception as e:
            print(f"[UnitreeB2] 路点文件加载失败: {e}")

    def _load_maps_file(self) -> None:
        """从 JSON 文件加载地图数据"""
        path = self.config.maps_file
        if not os.path.exists(path):
            print(f"[UnitreeB2] 地图文件不存在: {path}")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw: List[Dict] = json.load(f)
            self._maps = [
                MapInfo(
                    id=m["id"],
                    name=m["name"],
                    description=m.get("description", ""),
                )
                for m in raw
            ]
            if self._maps:
                self._current_map_id = self._maps[0].id
            print(f"[UnitreeB2] 已加载地图文件: {path} ({len(self._maps)} 张地图)")
        except Exception as e:
            print(f"[UnitreeB2] 地图文件加载失败: {e}")

    def _init_sdk(self) -> bool:
        """初始化 Unitree SDK（若未安装则跳过）"""
        try:
            from unitree_sdk2py.core.channel import ChannelFactory  # type: ignore
            from unitree_sdk2py.go2.sport.sport_client import SportClient  # type: ignore

            ChannelFactory.Instance().Init(0, self.config.network_interface)
            self._sport_client = SportClient()
            self._sport_client.SetTimeout(10.0)
            self._sport_client.Init()
            print("[UnitreeB2] SDK 初始化成功")
            return True
        except ImportError:
            print("[UnitreeB2] unitree_sdk2py 未安装，将以模拟模式运行")
            return False
        except Exception as e:
            print(f"[UnitreeB2] SDK 初始化失败: {e}")
            return False

    def _start_state_polling(self) -> None:
        """启动后台状态轮询线程（每 500ms 读取一次机器人状态）"""
        self._poll_stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_state_loop, daemon=True, name="b2-state-poll"
        )
        self._poll_thread.start()

    def _poll_state_loop(self) -> None:
        """后台线程：轮询机器人运动状态"""
        while not self._poll_stop.is_set():
            try:
                self._fetch_robot_state()
            except Exception:
                pass
            self._poll_stop.wait(0.5)

    def _fetch_robot_state(self) -> None:
        """通过 DDS 读取 SportModeState（速度、位姿等）"""
        if self._sport_client is None:
            return
        try:
            from unitree_sdk2py.go2.sport.sport_client import SportClient  # type: ignore

            # 尝试读取最新状态消息
            state = getattr(self._sport_client, "_state", None)
            if state is None:
                return

            # 提取速度（用于到达检测）
            vx = getattr(state, "velocity", [0.0, 0.0, 0.0])
            if isinstance(vx, (list, tuple)) and len(vx) >= 3:
                self._velocity = {"vx": vx[0], "vy": vx[1], "vyaw": vx[2]}

            # 提取位置
            pos = getattr(state, "position", None)
            # 偏航角来自 imu_state 或 heading，不是 pos.z（pos.z 是垂直高度）
            imu = getattr(state, "imu_state", None)
            yaw = 0.0
            if imu is not None:
                # rpy: [roll, pitch, yaw]
                rpy = getattr(imu, "rpy", None)
                if isinstance(rpy, (list, tuple)) and len(rpy) >= 3:
                    yaw = float(rpy[2])
            elif hasattr(state, "heading"):
                yaw = float(state.heading)
            if pos and hasattr(pos, "x"):
                self._current_pose = {
                    "x": float(pos.x),
                    "y": float(pos.y),
                    "yaw": yaw,
                }

            # 更新回调状态
            with self._callback_lock:
                self._callback_state["current_pose"] = self._current_pose.copy()

        except Exception:
            pass

    def _is_stopped(self) -> bool:
        """判断机器人速度是否接近零（到达判定）"""
        v = self._velocity
        return abs(v.get("vx", 0.0)) < 0.05 and abs(v.get("vy", 0.0)) < 0.05

    def _find_waypoint_by_id(self, waypoint_id: int) -> Optional[WaypointInfo]:
        """跨地图查找路点"""
        for wps in self._waypoints.values():
            for wp in wps:
                if wp.id == waypoint_id:
                    return wp
        return None

    def _find_waypoint_by_name(self, name: str) -> Optional[WaypointInfo]:
        """按名称查找路点（支持模糊匹配）"""
        name_lower = name.lower()
        for wps in self._waypoints.values():
            for wp in wps:
                if wp.name == name or wp.name.lower() == name_lower:
                    return wp
        return None

    def _emit_callback_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """更新内部回调状态（模拟回调推送）"""
        now = time.time()
        with self._callback_lock:
            self._callback_state["event_count"] += 1
            self._callback_state["last_event"] = event_type
            self._callback_state["last_event_at"] = now
            self._callback_state["last_event_payload"] = data
            for k, v in data.items():
                if k in self._callback_state:
                    self._callback_state[k] = v
        self.send_callback(event_type, data)

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    def connect(self) -> Dict[str, Any]:
        """
        连接机器人并执行健康检查。

        返回与 FishBotAdapter 相同的结构体：
        {
            "success": bool,
            "nav_server": {"connected": bool, "error": str|None},
            "nav_app":    {"connected": bool, "error": str|None},
            "rosbridge":  {"connected": bool, "error": str|None},
            "overall_status": str  # "healthy" | "degraded" | "offline"
        }
        """
        results: Dict[str, Any] = {
            "success": False,
            "nav_server": {"connected": False, "error": None},
            "nav_app": {"connected": False, "error": None},
            "rosbridge": {"connected": False, "error": None},
            "overall_status": "offline",
        }

        # 加载本地地图/路点文件
        self._load_maps_file()
        self._load_waypoints_file()

        # 初始化 SDK（用 nav_server 槽位记录结果）
        sdk_ok = self._init_sdk()
        if sdk_ok:
            results["nav_server"]["connected"] = True
            results["nav_app"]["connected"] = True
            results["rosbridge"]["connected"] = True
            results["overall_status"] = "healthy"
            results["success"] = True
            self._connected = True
            self._start_state_polling()
        else:
            # SDK 不可用时，若本地文件加载成功则以离线模式运行
            files_ok = bool(self._maps or self._waypoints)
            results["nav_server"]["connected"] = files_ok
            results["nav_server"]["error"] = None if files_ok else "unitree_sdk2py 未安装"
            results["nav_app"]["connected"] = False
            results["nav_app"]["error"] = "unitree_sdk2py 未安装（DDS 不可用）"
            results["rosbridge"]["connected"] = False
            results["rosbridge"]["error"] = "unitree_sdk2py 未安装（DDS 不可用）"

            if files_ok:
                results["overall_status"] = "degraded"
                results["success"] = True
                self._connected = True
                print("[UnitreeB2] 离线模式：SDK 不可用，仅本地文件可用")
            else:
                results["overall_status"] = "offline"
                self._connected = False

        return results

    def disconnect(self) -> None:
        """断开连接，停止后台线程"""
        self._poll_stop.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)
        self._connected = False
        print("[UnitreeB2] 已断开连接")

    # ------------------------------------------------------------------
    # 地图操作
    # ------------------------------------------------------------------

    def list_maps(self) -> List[MapInfo]:
        """返回本地地图列表"""
        return list(self._maps)

    def get_map(self, map_id: int) -> Optional[MapInfo]:
        """按 ID 查找地图"""
        for m in self._maps:
            if m.id == map_id:
                return m
        return None

    # ------------------------------------------------------------------
    # 路点操作
    # ------------------------------------------------------------------

    def list_waypoints(self, map_id: int) -> List[WaypointInfo]:
        """返回指定地图的路点列表"""
        return list(self._waypoints.get(map_id, []))

    def get_waypoint(self, waypoint_id: int) -> Optional[WaypointInfo]:
        """按 ID 查找路点"""
        return self._find_waypoint_by_id(waypoint_id)

    # ------------------------------------------------------------------
    # 导航操作
    # ------------------------------------------------------------------

    def start_navigation(self, map_id: int) -> bool:
        """切换当前地图（B2 导航无独立启动流程）"""
        if self.get_map(map_id) is not None:
            self._current_map_id = map_id
            self._nav_running = True
            print(f"[UnitreeB2] 切换地图: {map_id}")
            return True
        print(f"[UnitreeB2] 地图不存在: {map_id}")
        return False

    def stop_navigation(self) -> bool:
        """发送停止指令"""
        self._nav_running = False
        if self._sport_client is not None:
            try:
                self._sport_client.StopMove()
                print("[UnitreeB2] 导航已停止")
                return True
            except Exception as e:
                print(f"[UnitreeB2] 停止导航失败: {e}")
                return False
        return True

    def goto_waypoint(self, waypoint_id: int) -> bool:
        """前往路点（按 ID）"""
        wp = self._find_waypoint_by_id(waypoint_id)
        if wp is None:
            print(f"[UnitreeB2] 路点不存在: {waypoint_id}")
            return False
        return self._navigate_to_waypoint(wp)

    def goto_point(self, x: float, y: float, yaw: float = 0.0) -> bool:
        """前往绝对坐标"""
        return self._move_to_pos(x, y, yaw)

    def get_navigation_status(self) -> Dict[str, Any]:
        """返回当前导航状态"""
        return {
            "nav_running": self._nav_running,
            "current_pose": self._current_pose.copy(),
            "current_map_id": self._current_map_id,
            "charging": self._charging,
            "battery_soc": self._battery_soc,
        }

    # ------------------------------------------------------------------
    # 导航内部实现
    # ------------------------------------------------------------------

    def _navigate_to_waypoint(self, wp: WaypointInfo, timeout: int = 60) -> bool:
        """查找路点坐标后调用 MoveToPos，轮询速度判断是否到达"""
        print(f"[UnitreeB2] 前往路点: {wp.name} ({wp.x}, {wp.y}, yaw={wp.yaw})")

        # 更新目标状态
        with self._callback_lock:
            self._callback_state["target_waypoint_id"] = wp.id
            self._callback_state["target_waypoint_name"] = wp.name
            self._callback_state["target_updated_at"] = time.time()

        self._emit_callback_event(
            "nav_start",
            {"target_waypoint_id": wp.id, "target_waypoint_name": wp.name},
        )

        success = self._move_to_pos(wp.x, wp.y, wp.yaw, timeout=timeout)

        if success:
            self._emit_callback_event(
                "arrival",
                {
                    "arrived_waypoint_id": wp.id,
                    "target_waypoint_name": wp.name,
                    "arrived_at": time.time(),
                },
            )
        return success

    def _move_to_pos(
        self, x: float, y: float, yaw: float = 0.0, timeout: int = 60
    ) -> bool:
        """
        调用 SportClient.MoveToPos(dx, dy, dyaw) 并等待到达。
        当 SDK 不可用时，模拟移动（立即返回成功）。
        """
        if self._sport_client is not None:
            try:
                code, _ = self._sport_client.MoveToPos(x, y, yaw)
                if code != 0:
                    print(f"[UnitreeB2] MoveToPos 返回错误码: {code}")
                    return False

                # 等待速度归零（到达判定）
                deadline = time.time() + timeout
                time.sleep(1.0)  # 等待机器人开始运动
                while time.time() < deadline:
                    if self._is_stopped():
                        self._nav_running = False
                        print(f"[UnitreeB2] 已到达目标位置 ({x}, {y})")
                        return True
                    time.sleep(0.5)

                print(f"[UnitreeB2] 导航超时: ({x}, {y})")
                return False

            except Exception as e:
                print(f"[UnitreeB2] MoveToPos 调用失败: {e}")
                return False
        else:
            # SDK 不可用：模拟移动
            print(f"[UnitreeB2] [模拟] 移动到 ({x}, {y}, yaw={yaw})")
            self._current_pose = {"x": x, "y": y, "yaw": yaw}
            with self._callback_lock:
                self._callback_state["current_pose"] = self._current_pose.copy()
            return True

    # ------------------------------------------------------------------
    # 回充
    # ------------------------------------------------------------------

    def goto_dock(self) -> bool:
        """前往回充点（名称匹配 _DOCK_NAMES）"""
        # 在所有地图中查找充电桩路点
        for wps in self._waypoints.values():
            for wp in wps:
                if wp.name in _DOCK_NAMES or wp.name.lower() in {
                    n.lower() for n in _DOCK_NAMES
                }:
                    print(f"[UnitreeB2] 前往回充点: {wp.name}")
                    ok = self._navigate_to_waypoint(wp)
                    if ok:
                        self._charging = True
                        self._emit_callback_event(
                            "dock_complete",
                            {"dock_complete_at": time.time(), "charging": True},
                        )
                    return ok
        print("[UnitreeB2] 未找到回充点路点（需命名为 '回充点'/'dock'/'充电'/'charge'）")
        return False

    # ------------------------------------------------------------------
    # 灯光控制
    # ------------------------------------------------------------------

    def set_light(self, code: int) -> bool:
        """
        映射 FishMindOS 灯光代码到 B2 LED API（初版 stub）。

        code: 11=红, 13=绿, 0=关
        """
        color_map = {11: "红色", 13: "绿色", 0: "关闭"}
        color = color_map.get(code, f"自定义({code})")
        print(f"[UnitreeB2] 设置 LED: {color}")

        if self._sport_client is not None:
            try:
                # B2 LED API（如已支持）
                if hasattr(self._sport_client, "SetBodyLight"):
                    self._sport_client.SetBodyLight(code)
                return True
            except Exception as e:
                print(f"[UnitreeB2] LED 设置失败: {e}")
                return False
        return True

    # ------------------------------------------------------------------
    # TTS / 语音
    # ------------------------------------------------------------------

    def play_audio(self, text: str) -> bool:
        """
        使用板载 PC 扬声器播报语音。
        优先使用 pyttsx3，回退到 gTTS + playsound。
        """
        print(f"[UnitreeB2] 播报: {text}")
        try:
            import pyttsx3  # type: ignore

            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
            return True
        except ImportError:
            pass
        except Exception as e:
            print(f"[UnitreeB2] pyttsx3 播报失败: {e}")

        try:
            import tempfile

            from gtts import gTTS  # type: ignore

            tts = gTTS(text=text, lang="zh")
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name
            tts.save(tmp_path)
            subprocess.run(["mpg123", "-q", tmp_path], check=False)
            os.unlink(tmp_path)
            return True
        except ImportError:
            print("[UnitreeB2] pyttsx3 和 gTTS 均未安装，跳过语音播报")
        except Exception as e:
            print(f"[UnitreeB2] gTTS 播报失败: {e}")

        return False

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def get_status(self) -> RobotStatus:
        """返回机器人完整状态"""
        return RobotStatus(
            nav_running=self._nav_running,
            charging=self._charging,
            battery_soc=self._battery_soc,
            current_pose=self._current_pose.copy(),
        )

    def get_current_pose(self) -> Dict[str, float]:
        """获取当前位姿"""
        return self._current_pose.copy()

    def get_battery(self) -> Dict[str, Any]:
        """获取电池状态"""
        return {"soc": self._battery_soc, "charging": self._charging}

    # ------------------------------------------------------------------
    # 任务管理（B2 不原生支持，返回空/False）
    # ------------------------------------------------------------------

    def list_tasks(self) -> List[TaskInfo]:
        """B2 不原生支持任务，返回空列表"""
        return []

    def run_task(self, task_id: int) -> bool:
        """B2 不原生支持任务"""
        print(f"[UnitreeB2] 任务不支持 (task_id={task_id})")
        return False

    def cancel_task(self) -> bool:
        """取消当前运动（停止导航）"""
        return self.stop_navigation()

    # ------------------------------------------------------------------
    # 回调兼容层
    # ------------------------------------------------------------------

    def get_callback_state(self) -> Dict[str, Any]:
        """返回最新的回调驱动状态（与 FishBotAdapter 兼容）"""
        with self._callback_lock:
            return dict(self._callback_state)

    def handle_callback_event(self, event: Dict[str, Any]) -> None:
        """处理从嵌入式接收器推送来的回调事件"""
        event_type = event.get("event", "")
        data = event.get("data", {})
        with self._callback_lock:
            self._callback_state["event_count"] += 1
            self._callback_state["last_event"] = event_type
            self._callback_state["last_event_at"] = time.time()
            for k, v in data.items():
                if k in self._callback_state:
                    self._callback_state[k] = v


# ------------------------------------------------------------------
# 工厂函数
# ------------------------------------------------------------------


def create_unitree_b2_adapter(
    robot_ip: str = "192.168.123.161",
    network_interface: str = "eth0",
    waypoints_file: str = "waypoints.json",
    maps_file: str = "maps.json",
    **kwargs,
) -> UnitreeB2Adapter:
    """
    工厂函数：创建 Unitree B2 适配器

    用法::

        adapter = create_unitree_b2_adapter(robot_ip="192.168.123.161")
        if adapter.connect()["success"]:
            adapter.goto_waypoint(1)

    Args:
        robot_ip: B2 机器人 IP 地址
        network_interface: DDS 网络接口名称 (如 "eth0")
        waypoints_file: 本地路点 JSON 文件路径
        maps_file: 本地地图 JSON 文件路径
        **kwargs: 其他传递给 UnitreeB2Adapter 的参数

    Returns:
        UnitreeB2Adapter 实例
    """
    return UnitreeB2Adapter(
        robot_ip=robot_ip,
        network_interface=network_interface,
        waypoints_file=waypoints_file,
        maps_file=maps_file,
        **kwargs,
    )
