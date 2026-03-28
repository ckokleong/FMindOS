"""
FishMindOS Mock - 架构一致的调试版本
与真实系统完全相同的架构，只是 Adapter 使用 Mock 实现
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

# 确保可以导入 fishmindos
sys.path.insert(0, str(Path(__file__).parent))

from fishmindos.config import get_config, FishMindConfig
from fishmindos.skills import create_default_registry, SkillRegistry
from fishmindos.skills.loader import create_skill_manager
from fishmindos.brain.llm_brain import LLMBrain
from fishmindos.interaction import InteractionManager


class MockGo2Adapter:
    """
    Mock Go2 Adapter - 模拟所有 API 调用
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
        self._current_map_id: Optional[int] = 51
        
        # 模拟数据
        self._mock_maps = [
            {"id": 51, "name": "26层", "description": "26楼办公区"},
            {"id": 52, "name": "3层", "description": "3楼大厅"},
            {"id": 1, "name": "1层", "description": "1楼公共区域"},
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
                {"id": 399, "name": "回充点", "x": 5.0, "y": 5.0},
            ]
        }
        
        self._nav_running = False
        self._current_pose = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        
        print(f"[MOCK] Go2Adapter 初始化")
        print(f"[MOCK] robot: {robot_ip}:{robot_port}")
        print(f"[MOCK] nav_server: {nav_server_host}:{nav_server_port}")
    
    @property
    def vendor_name(self) -> str:
        return "Unitree Go2 (MOCK)"
    
    def connect(self) -> Dict[str, Any]:
        """健康检查 - 模拟"""
        print("[MOCK] 执行健康检查...")
        
        results = {
            "success": True,
            "sdk": {"connected": True, "error": None},
            "nav_server": {"connected": True, "error": None},
            "nav_app": {"connected": True, "error": None},
            "overall_status": "healthy"
        }
        self._connected = True
        return results
    
    def disconnect(self) -> None:
        self._connected = False
        print("[MOCK] 断开连接")
    
    # ========== 地图操作 ==========
    def list_maps(self) -> List[Any]:
        """获取地图列表"""
        from fishmindos.adapters.base import MapInfo
        print("[MOCK] list_maps()")
        
        return [MapInfo(
            id=m["id"],
            name=m["name"],
            description=m.get("description", "")
        ) for m in self._mock_maps]
    
    def start_navigation(self, map_id: int = None) -> bool:
        """启动导航 - 支持默认地图"""
        if map_id is None:
            map_id = self._current_map_id or (self._mock_maps[0]["id"] if self._mock_maps else 1)
            print(f"[MOCK] start_navigation(map_id={map_id}) [复用当前地图]")
        else:
            print(f"[MOCK] start_navigation(map_id={map_id})")
        self._current_map_id = map_id
        self._nav_running = True
        return True
    
    def stop_navigation(self) -> bool:
        """停止导航"""
        print("[MOCK] stop_navigation()")
        self._nav_running = False
        return True
    
    def get_navigation_status(self) -> Dict[str, Any]:
        """获取导航状态"""
        return {
            "nav_running": self._nav_running,
            "current_map_id": self._current_map_id
        }
    
    # ========== 路点操作 ==========
    def list_waypoints(self, map_id: int) -> List[Any]:
        """获取路点列表"""
        from fishmindos.adapters.base import WaypointInfo
        print(f"[MOCK] list_waypoints(map_id={map_id})")
        
        # 为所有地图添加默认路点
        default_waypoints = [
            {"id": 1, "name": "入口", "x": 0.0, "y": 0.0},
            {"id": 2, "name": "出口", "x": 10.0, "y": 10.0},
            {"id": 99, "name": "回充点", "x": 5.0, "y": 5.0},
        ]
        
        waypoints = self._mock_waypoints.get(map_id, default_waypoints)
        return [WaypointInfo(
            id=wp["id"],
            name=wp["name"],
            map_id=map_id,
            x=wp["x"],
            y=wp["y"]
        ) for wp in waypoints]
    
    def goto_waypoint(self, waypoint_id: int) -> bool:
        """前往路点"""
        print(f"[MOCK] goto_waypoint(waypoint_id={waypoint_id})")
        return True
    
    def goto_location(self, location: str, location_type: str = "waypoint") -> bool:
        """前往指定位置"""
        print(f"[MOCK] goto_location(location='{location}', type='{location_type}')")
        return True
    
    def goto_dock(self, map_id: int = None) -> bool:
        """前往回充点"""
        print(f"[MOCK] goto_dock(map_id={map_id})")
        return True
    
    # ========== 运动控制 ==========
    def motion_stand(self) -> bool:
        """站立"""
        print("[MOCK] motion_stand() - 机器狗已站立")
        return True
    
    def motion_lie_down(self) -> bool:
        """趴下"""
        print("[MOCK] motion_lie_down() - 机器狗已趴下")
        return True
    
    # ========== 灯光控制 ==========
    def set_light(self, code: int) -> bool:
        """设置灯光"""
        colors = {11: "红灯", 13: "绿灯", 0: "关灯"}
        color_name = colors.get(code, f"代码{code}")
        print(f"[MOCK] set_light(code={code}) - {color_name}")
        return True
    
    # ========== 音频控制 ==========
    def play_audio(self, text: str) -> bool:
        """播放语音"""
        print(f"[MOCK] play_audio('{text}')")
        return True
    
    # ========== 等待事件 ==========
    def wait_nav_started(self, timeout: int = 60) -> bool:
        print(f"[MOCK] wait_nav_started(timeout={timeout})")
        return True
    
    def wait_arrival(self, waypoint_id: int, timeout: int = 300) -> bool:
        print(f"[MOCK] wait_arrival(waypoint_id={waypoint_id}, timeout={timeout})")
        return True
    
    def wait_dock_complete(self, timeout: int = 300) -> bool:
        print(f"[MOCK] wait_dock_complete(timeout={timeout})")
        return True
    
    # ========== 状态查询 ==========
    def get_status(self) -> Any:
        """获取完整状态"""
        from fishmindos.adapters.base import RobotStatus
        
        return RobotStatus(
            nav_running=self._nav_running,
            charging=False,
            battery_soc=85.0,
            current_pose=self._current_pose
        )
    
    def get_current_pose(self) -> Dict[str, float]:
        return self._current_pose.copy()

    def get_mock_world(self) -> Dict[str, Any]:
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


def create_mock_go2_adapter(
    robot_ip: str = "192.168.123.161", robot_port: int = 8081,
    nav_server_host: str = "192.168.123.161", nav_server_port: int = 8081,
    nav_app_host: str = "192.168.123.161", nav_app_port: int = 8081,
    **kwargs
) -> MockGo2Adapter:
    """工厂函数：创建 Mock Adapter"""
    return MockGo2Adapter(
        robot_ip=robot_ip, robot_port=robot_port,
        nav_server_host=nav_server_host, nav_server_port=nav_server_port,
        nav_app_host=nav_app_host, nav_app_port=nav_app_port,
    )


class MockFishMindOS:
    """
    Mock FishMindOS - 与真实系统完全相同的架构
    只替换 Adapter 为 Mock 实现
    """
    
    def __init__(self):
        self.registry: Optional[SkillRegistry] = None
        self.skill_manager = None
        self.adapter = None
        self.brain: Optional[LLMBrain] = None
        self.interaction: Optional[InteractionManager] = None
        
    def initialize(self) -> bool:
        """初始化系统 - 与 __main__.py 相同逻辑"""
        try:
            config = get_config()
            
            print("=" * 60)
            print(" FishMindOS Mock - 架构调试模式")
            print("=" * 60)
            print()
            
            # 1. 初始化技能系统
            print("1. Initializing skill system...")
            self.registry = create_default_registry()
            print(f"   Built-in skills: {len(self.registry.list_all())}")
            
            # 2. 加载自定义技能
            self.skill_manager = create_skill_manager(self.registry)
            config_paths = config.skills.search_paths if hasattr(config.skills, 'search_paths') else []
            paths = list(dict.fromkeys(config_paths))
            loaded = self.skill_manager.initialize(
                search_paths=paths,
                enable_hot_reload=config.skills.hot_reload
            )
            print(f"   Custom skills: {loaded}")
            
            # 3. 连接 Mock 机器人
            print("2. Connecting to robot (MOCK)...")
            self.adapter = create_mock_go2_adapter(
                robot_ip=config.nav_server.host,
                robot_port=config.nav_server.port,
                nav_server_host=config.nav_server.host,
                nav_server_port=config.nav_server.port,
                nav_app_host=config.nav_app.host,
                nav_app_port=config.nav_app.port,
            )
            
            health = self.adapter.connect()
            print(f"   {self.adapter.vendor_name}")
            print(f"   Status: {health['overall_status']}")
            
            if health['success']:
                self.registry.set_adapter_for_all(self.adapter)
                self.skill_manager.loader.set_adapter(self.adapter)
            
            # 4. 初始化大脑
            print("3. Initializing brain...")
            from fishmindos.brain.llm_providers import create_llm_provider
            
            llm_provider = None
            try:
                llm_provider = create_llm_provider(config.llm)
                print(f"   LLM: {config.llm.provider} ({config.llm.model})")
            except Exception as e:
                print(f"   LLM init failed: {e}")
                print("   Using rule engine")
            
            self.brain = LLMBrain(self.registry, self.adapter, llm_provider)
            self.brain.session_context["current_map"] = {"id": 51, "name": "26层"}
            self.brain.session_context["current_location"] = "入口"
            self.brain.session_context["planning_only"] = True
            self.brain.session_context["mock_world"] = self.adapter.get_mock_world()
            print("   Brain ready")
            
            # 5. 初始化交互层
            print("4. Initializing interaction...")
            self.interaction = InteractionManager(self.brain)
            print("   Terminal UI ready")
            
            print()
            print("=" * 60)
            print(" Ready for testing!")
            print("=" * 60)
            print()
            
            return True
            
        except Exception as e:
            print(f"\nInitialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run(self):
        """运行主循环"""
        if self.interaction:
            self.interaction.start()


def main():
    """主入口"""
    print("\n" + "=" * 70)
    print(" FishMindOS Mock System")
    print(" 与真实系统完全相同的架构，使用 Mock Adapter")
    print("=" * 70 + "\n")
    
    app = MockFishMindOS()
    
    if app.initialize():
        print("输入指令开始测试（输入 'exit' 退出）:\n")
        app.run()
    else:
        print("\nFailed to initialize")
        sys.exit(1)


if __name__ == "__main__":
    main()
