"""
FishMindOS Mock - 真实 LLM + Mock Adapter
用于测试 LLM 决策能力，不控制真机器人
"""

import sys
from pathlib import Path

# 确保可以导入 fishmindos
sys.path.insert(0, str(Path(__file__).parent))

# 替换 adapters 模块中的 Go2 Adapter
import fishmindos.adapters as adapters_module
from fishmindos.adapters.base import RobotAdapter, MapInfo, WaypointInfo, TaskInfo, RobotStatus

class MockGo2Adapter(RobotAdapter):
    """
    Mock Adapter - 模拟所有 API 调用，不连接真机器人
    与真实 UnitreeGo2Adapter 接口完全一致
    """
    
    def __init__(self, 
                 robot_ip: str = "192.168.123.161", robot_port: int = 8081,
                 nav_server_host: str = "192.168.123.161", nav_server_port: int = 8081,
                 nav_app_host: str = "192.168.123.161", nav_app_port: int = 8081,
                 **kwargs):
        
        self.nav_server_base = f"http://{nav_server_host}:{nav_server_port}"
        self.nav_app_base = f"http://{nav_app_host}:{nav_app_port}"
        self._connected = False
        self._current_map_id = 51
        
        # Mock 数据
        self._mock_maps = [
            {"id": 51, "name": "26层", "description": "26楼办公区"},
            {"id": 52, "name": "3层", "description": "3楼大厅"},
            {"id": 1, "name": "1层", "description": "1楼公共区域"},
            {"id": 99, "name": "last", "description": "上次地图"},
        ]
        
        self._mock_waypoints = {
            51: [
                {"id": 101, "name": "大厅", "x": 10.0, "y": 20.0},
                {"id": 102, "name": "会议室", "x": 30.0, "y": 40.0},
                {"id": 103, "name": "厕所", "x": 25.0, "y": 35.0},
                {"id": 104, "name": "回充点", "x": 5.0, "y": 5.0},
            ],
            52: [
                {"id": 201, "name": "前台", "x": 15.0, "y": 25.0},
                {"id": 202, "name": "厕所", "x": 20.0, "y": 30.0},
                {"id": 203, "name": "回充点", "x": 5.0, "y": 5.0},
            ],
            1: [
                {"id": 301, "name": "入口", "x": 0.0, "y": 0.0},
                {"id": 302, "name": "前台", "x": 10.0, "y": 10.0},
                {"id": 303, "name": "休息区", "x": 20.0, "y": 20.0},
                {"id": 304, "name": "厕所", "x": 15.0, "y": 15.0},
                {"id": 305, "name": "回充点", "x": 5.0, "y": 5.0},
            ],
            99: [
                {"id": 901, "name": "默认位置", "x": 0.0, "y": 0.0},
                {"id": 902, "name": "回充点", "x": 5.0, "y": 5.0},
            ]
        }
        
        self._nav_running = False
        self._current_pose = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self._battery = 85.0
        
        print(f"[MOCK] Adapter 初始化: {robot_ip}:{robot_port}")
    
    @property
    def vendor_name(self) -> str:
        return "Unitree Go2 (MOCK)"
    
    def connect(self) -> dict:
        """健康检查"""
        print("[MOCK] 健康检查通过")
        self._connected = True
        return {
            "success": True,
            "sdk": {"connected": True, "error": None},
            "nav_server": {"connected": True, "error": None},
            "nav_app": {"connected": True, "error": None},
            "overall_status": "healthy"
        }
    
    def disconnect(self) -> None:
        self._connected = False
        print("[MOCK] 断开连接")
    
    # ========== 地图操作 ==========
    def list_maps(self):
        print("[MOCK] list_maps()")
        return [MapInfo(**m) for m in self._mock_maps]
    
    def start_navigation(self, map_id: int = None) -> bool:
        if map_id is None:
            map_id = self._current_map_id or (self._mock_maps[0]["id"] if self._mock_maps else 1)
        print(f"[MOCK] start_navigation(map_id={map_id})")
        self._current_map_id = map_id
        self._nav_running = True
        return True
    
    def stop_navigation(self) -> bool:
        print("[MOCK] stop_navigation()")
        self._nav_running = False
        return True
    
    def get_navigation_status(self) -> dict:
        return {
            "nav_running": self._nav_running,
            "current_map_id": self._current_map_id
        }
    
    # ========== 路点操作 ==========
    def list_waypoints(self, map_id: int):
        print(f"[MOCK] list_waypoints(map_id={map_id})")
        waypoints = self._mock_waypoints.get(map_id, [])
        return [WaypointInfo(id=wp["id"], name=wp["name"], map_id=map_id, 
                           x=wp["x"], y=wp["y"]) for wp in waypoints]
    
    def goto_waypoint(self, waypoint_id: int) -> bool:
        print(f"[MOCK] goto_waypoint(waypoint_id={waypoint_id})")
        return True
    
    def goto_location(self, location: str, location_type: str = "waypoint") -> bool:
        print(f"[MOCK] goto_location(location='{location}', type='{location_type}')")
        return True
    
    def goto_dock(self, map_id: int = None) -> bool:
        print(f"[MOCK] goto_dock(map_id={map_id})")
        return True
    
    # ========== 运动控制 ==========
    def motion_stand(self) -> bool:
        print("[MOCK] motion_stand()")
        return True
    
    def motion_lie_down(self) -> bool:
        print("[MOCK] motion_lie_down()")
        return True
    
    # ========== 灯光控制 ==========
    def set_light(self, code: int) -> bool:
        colors = {11: "红灯", 13: "绿灯", 0: "关灯"}
        print(f"[MOCK] set_light(code={code}) - {colors.get(code, '未知')}")
        return True
    
    # ========== 音频控制 ==========
    def play_audio(self, text: str) -> bool:
        print(f"[MOCK] play_audio('{text}')")
        return True
    
    # ========== 等待事件 ==========
    def wait_nav_started(self, timeout: int = 60) -> bool:
        print(f"[MOCK] wait_nav_started(timeout={timeout})")
        return True
    
    def wait_arrival(self, waypoint_id: int, timeout: int = 300) -> bool:
        print(f"[MOCK] wait_arrival(waypoint_id={waypoint_id})")
        return True
    
    def wait_dock_complete(self, timeout: int = 300) -> bool:
        print(f"[MOCK] wait_dock_complete(timeout={timeout})")
        return True
    
    # ========== 状态查询 ==========
    def get_status(self):
        return RobotStatus(
            nav_running=self._nav_running,
            charging=False,
            battery_soc=self._battery,
            current_pose=self._current_pose
        )
    
    def get_current_pose(self) -> dict:
        return self._current_pose.copy()
    
    # ========== 其他必需方法（快速实现）==========
    def get_map(self, map_id: int):
        for m in self._mock_maps:
            if m["id"] == map_id:
                return MapInfo(**m)
        return None
    
    def get_waypoint(self, waypoint_id: int):
        for map_waypoints in self._mock_waypoints.values():
            for wp in map_waypoints:
                if wp["id"] == waypoint_id:
                    return WaypointInfo(id=wp["id"], name=wp["name"], map_id=1, x=wp["x"], y=wp["y"])
        return None
    
    def create_task(self, name: str, description: str = "", program: dict = None):
        print(f"[MOCK] create_task('{name}')")
        return TaskInfo(id=1, name=name, description=description)
    
    def delete_task(self, task_id: int) -> bool:
        print(f"[MOCK] delete_task({task_id})")
        return True
    
    def start_task(self, task_id: int) -> bool:
        print(f"[MOCK] start_task({task_id})")
        return True
    
    def stop_task(self, task_id: int) -> bool:
        print(f"[MOCK] stop_task({task_id})")
        return True
    
    def get_task_status(self, task_id: int):
        print(f"[MOCK] get_task_status({task_id})")
        return TaskInfo(id=task_id, name="mock_task", status="running")
    
    def goto_point(self, x: float, y: float, yaw: float = None) -> bool:
        print(f"[MOCK] goto_point(x={x}, y={y}, yaw={yaw})")
        return True
    
    def list_tasks(self):
        print("[MOCK] list_tasks()")
        return []
    
    def pause_navigation(self) -> bool:
        print("[MOCK] pause_navigation()")
        return True
    
    def resume_navigation(self) -> bool:
        print("[MOCK] resume_navigation()")
        return True
    
    def get_battery_status(self):
        print("[MOCK] get_battery_status()")
        return {"soc": 85.0, "charging": False}
    
    def run_task(self, task_id: int) -> bool:
        print(f"[MOCK] run_task({task_id})")
        return True
    
    def cancel_task(self) -> bool:
        print("[MOCK] cancel_task()")
        return True
    
    def get_battery(self):
        print("[MOCK] get_battery()")
        return {"soc": 85.0, "charging": False}

    def get_mock_world(self):
        """返回用于规划测试的静态场景信息。"""
        map_lookup = {m["id"]: m["name"] for m in self._mock_maps}
        return {
            "current_map": map_lookup.get(self._current_map_id, "26层"),
            "map_aliases": {
                "楼下": "1层",
                "楼上": "26层",
            },
            "waypoints": {
                map_lookup.get(map_id, str(map_id)): [wp["name"] for wp in waypoints]
                for map_id, waypoints in self._mock_waypoints.items()
            }
        }


# 替换真实的 create_go2_adapter
original_create_go2_adapter = adapters_module.create_go2_adapter

def mock_create_go2_adapter(**kwargs):
    """工厂函数：创建 Mock Adapter"""
    return MockGo2Adapter(**kwargs)

# Monkey patch
adapters_module.create_go2_adapter = mock_create_go2_adapter
adapters_module.UnitreeGo2Adapter = MockGo2Adapter


# 现在导入真实的 FishMindOS
from fishmindos.__main__ import FishMindOS


def main():
    """主入口"""
    print("=" * 70)
    print(" FishMindOS Mock - 真实 LLM + Mock Adapter (Unitree Go2)")
    print(" 测试 LLM 决策能力，不控制真机器人")
    print("=" * 70)
    print()
    print("观察重点:")
    print("  1. [PLAN] 工具序列是否正确")
    print("  2. 是否会多余调用 nav_start")
    print("  3. '完成后亮绿灯' 是否生成 system_wait + light_set")
    print("  4. 网络抖动时是否优雅处理")
    print()
    print("=" * 70)
    print()
    
    # 使用真实的 FishMindOS
    app = FishMindOS()
    
    if app.initialize():
        if app.brain:
            app.brain.session_context["current_map"] = {"id": 51, "name": "26层"}
            app.brain.session_context["current_location"] = "入口"
            app.brain.session_context["planning_only"] = True
            if hasattr(app.adapter, "get_mock_world"):
                app.brain.session_context["mock_world"] = app.adapter.get_mock_world()
            print("[MOCK] 默认上下文: 地图=26层, 位置=入口")
            print("[MOCK] 模式: 规划优先（禁用 nav_list_maps/nav_list_waypoints）")
        print("\n输入指令开始测试（输入 'exit' 退出）:\n")
        app.run()
    else:
        print("\n初始化失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
