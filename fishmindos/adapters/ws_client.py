"""
FishMindOS WebSocket客户端
支持Rosbridge和自定义WebSocket连接
用于实时控制灯光、接收导航事件等
"""

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class WSMessage:
    """WebSocket消息"""
    op: str  # 操作类型
    topic: Optional[str] = None
    type: Optional[str] = None  # 消息类型
    msg: Optional[Dict] = None
    id: Optional[str] = None
    service: Optional[str] = None
    args: Optional[Dict] = None


class WebSocketClient:
    """
    WebSocket客户端基类
    支持自动重连、订阅管理
    """
    
    def __init__(self, url: str, reconnect_interval: int = 5, 
                 max_reconnect_attempts: int = 10):
        self.url = url
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        
        self.ws = None
        self.connected = False
        self._stop_event = threading.Event()
        self._receive_thread: Optional[threading.Thread] = None
        self._reconnect_thread: Optional[threading.Thread] = None
        
        # 回调函数
        self._message_handlers: List[Callable] = []
        self._topic_handlers: Dict[str, List[Callable]] = {}
        self._service_handlers: Dict[str, List[Callable]] = {}
        
        # 消息ID计数器
        self._msg_id_counter = 0
    
    def connect(self) -> bool:
        """连接WebSocket服务器"""
        try:
            # 尝试导入websocket-client库
            try:
                import websocket
            except ImportError:
                print("⚠ 未安装websocket-client库，尝试使用内置实现")
                return self._connect_builtin()
            
            # 使用websocket-client库
            self.ws = websocket.WebSocketApp(
                self.url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            # 启动接收线程
            self._receive_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            self._receive_thread.start()
            
            # 等待连接建立
            timeout = 5
            start = time.time()
            while not self.connected and time.time() - start < timeout:
                time.sleep(0.1)
            
            return self.connected
            
        except Exception as e:
            print(f"WebSocket连接失败: {e}")
            return False
    
    def _connect_builtin(self) -> bool:
        """使用内置的websocket实现（简化版）"""
        try:
            # 这里使用socket实现一个简单的WebSocket客户端
            import socket
            import ssl
            from urllib.parse import urlparse
            
            parsed = urlparse(self.url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == 'wss' else 80)
            path = parsed.path or '/'
            
            # 创建socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # SSL支持
            if parsed.scheme == 'wss':
                context = ssl.create_default_context()
                sock = context.wrap_socket(sock, server_hostname=host)
            
            sock.connect((host, port))
            
            # 发送WebSocket握手
            handshake = f"GET {path} HTTP/1.1\r\n"
            handshake += f"Host: {host}\r\n"
            handshake += "Upgrade: websocket\r\n"
            handshake += "Connection: Upgrade\r\n"
            handshake += "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            handshake += "Sec-WebSocket-Version: 13\r\n"
            handshake += "\r\n"
            
            sock.send(handshake.encode())
            
            # 接收响应
            response = sock.recv(1024).decode()
            if "101 Switching Protocols" in response:
                self._sock = sock
                self.connected = True
                
                # 启动接收线程
                self._receive_thread = threading.Thread(target=self._receive_loop_builtin, daemon=True)
                self._receive_thread.start()
                
                return True
            else:
                sock.close()
                return False
                
        except Exception as e:
            print(f"内置WebSocket连接失败: {e}")
            return False
    
    def _receive_loop_builtin(self):
        """内置实现的接收循环"""
        while not self._stop_event.is_set():
            try:
                if hasattr(self, '_sock'):
                    data = self._sock.recv(4096)
                    if data:
                        # 简单的WebSocket帧解析（不完整，仅作示例）
                        try:
                            # 跳过WebSocket帧头，解析JSON
                            # 实际应该完整实现WebSocket协议
                            text_data = data.decode('utf-8', errors='ignore')
                            if '{"op":' in text_data:
                                json_start = text_data.find('{')
                                json_data = text_data[json_start:]
                                message = json.loads(json_data)
                                self._handle_message(message)
                        except:
                            pass
            except Exception:
                break
        
        self.connected = False
    
    def disconnect(self):
        """断开连接"""
        self._stop_event.set()
        self.connected = False
        
        if self.ws:
            self.ws.close()
        
        if hasattr(self, '_sock'):
            self._sock.close()
    
    def _on_open(self, ws):
        """连接打开回调"""
        self.connected = True
        # 静默连接，不在主界面显示
        pass
    
    def _on_message(self, ws, message):
        """收到消息回调"""
        try:
            data = json.loads(message)
            self._handle_message(data)
        except json.JSONDecodeError:
            pass  # 忽略非JSON消息
    
    def _on_error(self, ws, error):
        """错误回调"""
        self.connected = False
        # 静默处理错误，避免干扰主界面
        pass
    
    def _on_close(self, ws, close_status_code, close_msg):
        """连接关闭回调"""
        self.connected = False
        # 静默处理断开，自动重连在后台进行
        if not self._stop_event.is_set():
            self._start_reconnect()
    
    def _start_reconnect(self):
        """启动重连"""
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return
        
        self._reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self._reconnect_thread.start()
    
    def _reconnect_loop(self):
        """重连循环 - 静默重连"""
        attempts = 0
        while not self._stop_event.is_set() and attempts < self.max_reconnect_attempts:
            time.sleep(self.reconnect_interval)
            
            if self.connect():
                # 重新订阅之前的topic
                self._resubscribe_all()
                return
            
            attempts += 1
        # 重连失败也不输出，保持界面干净
        pass
    
    def _resubscribe_all(self):
        """重新订阅所有topic"""
        for topic in self._topic_handlers.keys():
            self.subscribe(topic)
    
    def _handle_message(self, data: Dict):
        """处理收到的消息"""
        # 调用通用消息处理器
        for handler in self._message_handlers:
            try:
                handler(data)
            except Exception as e:
                print(f"消息处理器错误: {e}")
        
        # 根据topic分发
        topic = data.get('topic')
        if topic and topic in self._topic_handlers:
            for handler in self._topic_handlers[topic]:
                try:
                    handler(data.get('msg', {}))
                except Exception as e:
                    print(f"Topic处理器错误: {e}")
        
        # 处理service响应
        if data.get('op') == 'service_response':
            service = data.get('service')
            if service and service in self._service_handlers:
                for handler in self._service_handlers[service]:
                    try:
                        handler(data.get('values', {}))
                    except Exception as e:
                        print(f"Service处理器错误: {e}")
    
    def send(self, data: Dict):
        """发送消息"""
        if not self.connected:
            print("WebSocket未连接")
            return False
        
        try:
            message = json.dumps(data)
            if self.ws:
                self.ws.send(message)
            elif hasattr(self, '_sock'):
                # 内置实现发送
                self._send_builtin(message)
            return True
        except Exception as e:
            print(f"发送失败: {e}")
            return False
    
    def _send_builtin(self, message: str):
        """内置实现发送消息"""
        # 构建WebSocket文本帧
        frame = bytearray()
        frame.append(0x81)  # FIN=1, opcode=text
        
        length = len(message)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(length.to_bytes(2, 'big'))
        else:
            frame.append(127)
            frame.extend(length.to_bytes(8, 'big'))
        
        frame.extend(message.encode('utf-8'))
        self._sock.send(frame)
    
    def subscribe(self, topic: str, msg_type: str = None):
        """订阅topic"""
        msg = {
            "op": "subscribe",
            "topic": topic
        }
        if msg_type:
            msg["type"] = msg_type
        
        return self.send(msg)
    
    def unsubscribe(self, topic: str):
        """取消订阅"""
        return self.send({
            "op": "unsubscribe",
            "topic": topic
        })
    
    def publish(self, topic: str, msg: Dict, msg_type: str = None):
        """发布消息到topic"""
        data = {
            "op": "publish",
            "topic": topic,
            "msg": msg
        }
        if msg_type:
            data["type"] = msg_type
        
        return self.send(data)
    
    def call_service(self, service: str, args: Dict = None, 
                     service_type: str = None) -> str:
        """调用service"""
        self._msg_id_counter += 1
        msg_id = f"call_{self._msg_id_counter}"
        
        data = {
            "op": "call_service",
            "service": service,
            "id": msg_id
        }
        if args:
            data["args"] = args
        if service_type:
            data["type"] = service_type
        
        self.send(data)
        return msg_id
    
    def on_message(self, handler: Callable):
        """注册消息处理器"""
        self._message_handlers.append(handler)
    
    def on_topic(self, topic: str, handler: Callable):
        """注册topic处理器"""
        if topic not in self._topic_handlers:
            self._topic_handlers[topic] = []
            # 自动订阅
            self.subscribe(topic)
        
        self._topic_handlers[topic].append(handler)
    
    def on_service_response(self, service: str, handler: Callable):
        """注册service响应处理器"""
        if service not in self._service_handlers:
            self._service_handlers[service] = []
        
        self._service_handlers[service].append(handler)


class RosbridgeClient(WebSocketClient):
    """
    Rosbridge专用客户端
    针对ROS导航系统的特定功能
    """
    
    def __init__(self, host: str = "127.0.0.1", port: int = 9090, 
                 path: str = "/api/rt", use_ssl: bool = False):
        protocol = "wss" if use_ssl else "ws"
        url = f"{protocol}://{host}:{port}{path}"
        super().__init__(url)
        
        self.host = host
        self.port = port
    
    def control_light(self, code: int):
        """控制灯光"""
        return self.publish(
            "/light_control",
            {"data": code},
            msg_type="std_msgs/msg/Int32"
        )
    
    def send_velocity(self, linear_x: float = 0.0, angular_z: float = 0.0):
        """发送速度指令"""
        return self.publish(
            "/cmd_vel",
            {
                "linear": {"x": linear_x, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": angular_z}
            },
            msg_type="geometry_msgs/msg/Twist"
        )
    
    def navigate_to_target(self, target_id: int, target_x: float, target_y: float,
                          linear_speed: float = 0.5, angular_speed: float = 0.5):
        """导航到目标点"""
        return self.call_service(
            "/NavPlannerGoToTarget",
            args={
                "target_id": target_id,
                "target_x": target_x,
                "target_y": target_y,
                "target_z": 0.0,
                "target_theta": 0.0,
                "linear_speed": linear_speed,
                "angular_speed": angular_speed,
                "obstacle_strategy": "avoid",
                "arrive_distance_thresh": 0.5,
                "arrive_angle_thresh": 0.1
            },
            service_type="nav_interfaces/srv/NavPlannerGoToTarget"
        )
    
    def cancel_navigation(self, target_id: int = 0):
        """取消导航"""
        return self.call_service(
            "/NavPlannerCancel",
            args={"target_id": target_id},
            service_type="nav_interfaces/srv/NavPlannerCancel"
        )
    
    def pause_navigation(self, pause: bool = True):
        """暂停/恢复导航"""
        return self.call_service(
            "/NavPlannerPause",
            args={"pause": pause},
            service_type="nav_interfaces/srv/NavPlannerPause"
        )
    
    def on_nav_event(self, handler: Callable):
        """监听导航事件"""
        self.on_topic("/nav_event", handler)
    
    def on_battery_status(self, handler: Callable):
        """监听电池状态"""
        self.on_topic("/bms_soc", handler)


def create_rosbridge_client(config=None) -> RosbridgeClient:
    """工厂函数：创建Rosbridge客户端"""
    if config is None:
        from fishmindos.config import get_config
        config = get_config()
    
    return RosbridgeClient(
        host=config.rosbridge.host,
        port=config.rosbridge.port,
        path=config.rosbridge.path,
        use_ssl=config.rosbridge.use_ssl
    )
