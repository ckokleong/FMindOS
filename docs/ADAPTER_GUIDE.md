"""
新机器人适配器接入指南
===================

本文档说明如何将 YourRobot 或其他机器人接入 FishMindOS
"""

## 快速开始

### 1. 创建适配器文件

参考 `fishmindos/adapters/your_robot.py`，实现以下步骤：

```python
# fishmindos/adapters/your_robot.py
from fishmindos.adapters.base import RobotAdapter, MapInfo, WaypointInfo

class YourRobotAdapter(RobotAdapter):
    def __init__(self, host, port, api_key):
        # 初始化代码
        pass
    
    def connect(self):
        # 连接逻辑
        pass
    
    def list_maps(self):
        # 获取地图列表
        pass
    
    def start_navigation(self, map_id):
        # 启动导航
        pass
    
    # ... 其他必需方法
```

### 2. 注册到系统

修改 `fishmindos/adapters/__init__.py`：

```python
from fishmindos.adapters.your_robot import YourRobotAdapter, create_your_robot_adapter

__all__ = [
    # ... 原有导出
    "YourRobotAdapter",
    "create_your_robot_adapter",
]
```

### 3. 添加配置

在 `fishmindos.config.json` 中添加：

```json
{
  "robot_type": "your_robot",
  "your_robot": {
    "host": "192.168.1.100",
    "port": 8080,
    "api_key": "your-api-key-here"
  }
}
```

### 4. 修改入口

修改 `fishmindos/__main__.py`，在初始化时根据配置创建对应适配器：

```python
from fishmindos.adapters import (
    create_fishbot_adapter,
    create_your_robot_adapter  # 新增
)

def initialize(self):
    config = get_config()
    
    # 根据配置选择适配器
    if config.robot_type == "your_robot":
        robot_config = config.your_robot
        self.adapter = create_your_robot_adapter(
            host=robot_config.host,
            port=robot_config.port,
            api_key=robot_config.api_key
        )
    else:
        # 默认使用 FishBot
        self.adapter = create_fishbot_adapter(...)
```

## 完整示例

### 场景：接入 XYZRobot

#### 步骤 1：创建适配器

```bash
# 创建文件
touch fishmindos/adapters/xyz_robot.py
```

```python
# fishmindos/adapters/xyz_robot.py

import json
import urllib.request
from typing import Any, Dict, List, Optional

from fishmindos.adapters.base import (
    RobotAdapter, MapInfo, WaypointInfo, RobotStatus
)

class XYZRobotAdapter(RobotAdapter):
    """XYZRobot 适配器"""
    
    def __init__(self, host: str = "192.168.1.100", port: int = 9000):
        self.base_url = f"http://{host}:{port}"
        self._connected = False
    
    @property
    def vendor_name(self) -> str:
        return "XYZRobot"
    
    def connect(self) -> Dict[str, Any]:
        """连接检查"""
        try:
            # 测试连接
            self._request("GET", "/api/status")
            self._connected = True
            return {
                "success": True,
                "status": "online",
                "details": {}
            }
        except Exception as e:
            return {
                "success": False,
                "status": "offline",
                "details": {"error": str(e)}
            }
    
    def _request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """HTTP请求"""
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode() if data else None,
            headers=headers,
            method=method
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    
    def list_maps(self) -> List[MapInfo]:
        """获取地图列表"""
        result = self._request("GET", "/api/maps")
        maps_data = result.get("maps", [])
        return [
            MapInfo(id=m["id"], name=m["name"])
            for m in maps_data
        ]
    
    def start_navigation(self, map_id: int) -> bool:
        """启动导航"""
        try:
            result = self._request(
                "POST", 
                "/api/navigation/start",
                {"map_id": map_id}
            )
            return result.get("success", False)
        except:
            return False
    
    def goto_location(self, location: str, location_type: str = "waypoint") -> bool:
        """前往位置"""
        try:
            result = self._request(
                "POST",
                "/api/navigation/goto",
                {"location": location}
            )
            return result.get("success", False)
        except:
            return False
    
    def motion_stand(self) -> bool:
        """站立"""
        try:
            result = self._request("POST", "/api/robot/stand")
            return result.get("success", False)
        except:
            return False
    
    def set_light(self, code: int) -> bool:
        """设置灯光"""
        try:
            result = self._request(
                "POST",
                "/api/robot/light",
                {"code": code}
            )
            return result.get("success", False)
        except:
            return False
    
    def get_status(self) -> RobotStatus:
        """获取状态"""
        try:
            result = self._request("GET", "/api/status")
            data = result.get("data", {})
            return RobotStatus(
                nav_running=data.get("nav_running", False),
                charging=data.get("charging", False),
                battery_soc=data.get("battery", 100.0)
            )
        except:
            return RobotStatus()

def create_xyz_robot_adapter(host: str = "192.168.1.100", port: int = 9000):
    """工厂函数"""
    return XYZRobotAdapter(host=host, port=port)
```

#### 步骤 2：注册

```python
# fishmindos/adapters/__init__.py

from fishmindos.adapters.xyz_robot import XYZRobotAdapter, create_xyz_robot_adapter

__all__ = [
    # ... 原有
    "XYZRobotAdapter",
    "create_xyz_robot_adapter",
]
```

#### 步骤 3：配置

```json
{
  "robot_type": "xyz_robot",
  "xyz_robot": {
    "host": "192.168.1.100",
    "port": 9000
  }
}
```

#### 步骤 4：修改入口

```python
# fishmindos/__main__.py

class FishMindOS:
    def initialize(self):
        config = get_config()
        
        if config.robot_type == "xyz_robot":
            from fishmindos.adapters import create_xyz_robot_adapter
            robot_config = config.xyz_robot
            self.adapter = create_xyz_robot_adapter(
                host=robot_config.host,
                port=robot_config.port
            )
        else:
            # FishBot 默认
            self.adapter = create_fishbot_adapter(...)
```

## 测试

```bash
# 运行系统
python -m fishmindos

# 测试指令
> 去会议室
> 亮红灯
> 返回充电
```

## 调试技巧

1. **Mock 测试**: 先用 Mock 适配器测试逻辑
2. **日志输出**: 在适配器中添加 `print` 调试
3. **逐步验证**: 先测试 `connect()`，再测试单个技能

## 常见问题

### Q: API 格式不匹配？
A: 在适配器中进行数据转换，保持对外接口一致

### Q: 缺少某些功能？
A: 可以实现为空方法（返回 False），不影响其他功能

### Q: WebSocket 实时控制？
A: 参考 `fishbot.py` 中的 WebSocket 实现
