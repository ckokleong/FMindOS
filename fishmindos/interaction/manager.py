"""
FishMindOS Interaction Layer - 交互层
提供终端对话界面
"""

from __future__ import annotations

import threading
import time
import itertools
import sys
from typing import Any, Dict, List, Optional, Callable, Generator
from datetime import datetime


class Spinner:
    """加载动画"""
    
    def __init__(self, message: str = "思考中"):
        self.message = message
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False
    
    def start(self):
        """开始动画"""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()
    
    def stop(self):
        """停止动画"""
        if not self._running:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        self._running = False
        # 清除行
        sys.stdout.write("\r" + " " * (len(self.message) + 10) + "\r")
        sys.stdout.flush()
    
    def _animate(self):
        """动画循环"""
        for dots in itertools.cycle(["", ".", "..", "..."]):
            if self._stop_event.is_set():
                break
            sys.stdout.write(f"\r{self.message}{dots}   ")
            sys.stdout.flush()
            time.sleep(0.3)


def sanitize_output(text: str) -> str:
    """清洗输出文本，移除污染内容"""
    if not text:
        return text
    
    import re
    
    # 1. 移除 <think>...</think> 块
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
    # 2. 移除孤立的 </think>
    text = re.sub(r'</think>', '', text)
    
    # 3. 移除 **回复**: 标记
    text = re.sub(r'\*\*回复\*\*[:\s]*', '', text)
    
    # 4. 移除执行了: xxx 历史摘要
    text = re.sub(r'执行了:\s*\w+(,\s*\w+)*', '', text)
    
    # 5. 移除 # 标题标记
    text = re.sub(r'^#+\s+.*$', '', text, flags=re.MULTILINE)
    
    # 6. 移除 --- 分隔线
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
    
    # 7. 移除多余空行
    text = re.sub(r'\n\n\n+', '\n\n', text)
    
    # 8. 移除我是FishMindOS 等自我介绍
    text = re.sub(r'我是FishMindOS.*', '', text)
    
    # 9. 移除当前在... 状态描述
    text = re.sub(r'我当前在.*', '', text)

    # 10. 移除工具调用和XML残片
    text = re.sub(r'<tool_call.*?>.*?</tool_call>', '', text, flags=re.DOTALL)
    text = re.sub(r'</?tool_call>', '', text)
    text = re.sub(r'<arg_key>.*?</arg_key>', '', text, flags=re.DOTALL)
    text = re.sub(r'<arg_value>.*?</arg_value>', '', text, flags=re.DOTALL)
    text = re.sub(r'^\s*调?调用了\s+\w+.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*location\s*$', '', text, flags=re.MULTILINE)
    
    return text.strip()


class TerminalUI:
    """终端UI - 简洁风格"""
    
    # 简单符号（Windows CMD 兼容）
    ICONS = {
        "dog": "[DOG]",
        "user": "[YOU]",
        "skill": ">>",
        "success": "OK",
        "error": "ERR",
        "info": "::",
        "arrow": "->",
        "plan": "[PLAN]",
        "step": "  -",
        "number": ["1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."]
    }
    
    def __init__(self, use_colors: bool = True):
        self.use_colors = use_colors
        self._last_was_skill = False
    
    def print_header(self):
        """打印标题"""
        print()
        print("=" * 50)
        print("  FishMindOS - 机器狗智能控制系统")
        print("=" * 50)
        print()
    
    def print_help(self):
        """打印帮助"""
        print("指令示例:")
        print("  去会议室    - 导航到会议室")
        print("  关灯        - 关闭灯光")
        print("  电量        - 查看状态")
        print("  停止        - 取消当前任务")
        print("  退出        - 结束对话")
        print()
    
    def print_user_prompt(self):
        """打印用户提示符"""
        if self._last_was_skill:
            print()
        print(f"{self.ICONS['user']} ", end="", flush=True)
    
    def print_robot_response(self, text: str):
        """打印机器人响应"""
        print(f"{self.ICONS['dog']} {text}")
        self._last_was_skill = False
    
    def print_plan(self, steps: List[Dict[str, Any]]):
        """打印执行规划"""
        print(f"{self.ICONS['plan']} 执行规划:")
        for i, step in enumerate(steps, 1):
            skill_name = step.get("skill", "")
            desc = self._get_skill_desc(skill_name)
            params = step.get("params", {})
            param_str = ", ".join([f"{k}={v}" for k, v in params.items()]) if params else ""
            
            num = self.ICONS['number'][i-1] if i <= len(self.ICONS['number']) else f"{i}."
            if desc:
                print(f"{self.ICONS['step']} {num} {desc} {param_str}")
            else:
                print(f"{self.ICONS['step']} {num} {skill_name} {param_str}")
        print()
        self._last_was_skill = False
    
    def print_skill_start(self, skill_name: str, description: str = "", step_num: int = 0):
        """打印技能开始 - 单行紧凑显示"""
        desc = f" ({description})" if description else ""
        num_str = f"[{step_num}] " if step_num > 0 else ""
        print(f"{self.ICONS['skill']} {num_str}{skill_name}{desc} ... ", end="", flush=True)
        self._last_was_skill = True
    
    def print_skill_result(self, success: bool, message: str):
        """打印技能结果 - 紧跟在技能开始后面"""
        if success:
            print(f"{self.ICONS['success']} {message}")
        else:
            print(f"{self.ICONS['error']} {message}")
    
    def print_error(self, message: str):
        """打印错误"""
        print(f"{self.ICONS['error']} {message}")
        self._last_was_skill = False
    
    def print_info(self, message: str):
        """打印信息"""
        print(f"{self.ICONS['info']} {message}")
        self._last_was_skill = False
    
    def _get_skill_desc(self, skill_name: str) -> str:
        """获取技能描述"""
        desc_map = {
            "light_set": "灯光",
            "light_on": "开灯",
            "light_off": "关灯",
            "nav_start": "启动导航",
            "nav_stop": "停止导航",
            "nav_goto_location": "前往",
            "nav_goto_waypoint": "前往路点",
            "motion_stand": "站立",
            "motion_lie_down": "趴下",
            "system_battery": "查看电量",
            "system_status": "查看状态",
            "smart_navigate": "智能导航"
        }
        return desc_map.get(skill_name, "")


class InteractionManager:
    """
    交互管理器
    负责管理用户交互的整个流程
    """
    
    def __init__(self, brain=None):
        self.brain = brain
        self.ui = TerminalUI()
        self.spinner: Optional[Spinner] = None
        self.conversation_history: List[Dict] = []
        self.session_context: Dict[str, Any] = {}
        self._running = False
        self._cancel_event = threading.Event()
        self._current_skill = None
    
    def set_brain(self, brain):
        """设置大脑"""
        self.brain = brain
    
    def start(self):
        """启动交互"""
        self._running = True
        self.ui.print_header()
        self.ui.print_help()
        
        while self._running:
            try:
                self.ui.print_user_prompt()
                user_input = input().strip()
                
                if not user_input:
                    continue
                
                # 处理特殊命令
                if self._handle_special_command(user_input):
                    continue
                
                # 处理用户输入
                self._process_input(user_input)
                
            except KeyboardInterrupt:
                print()
                break
            except EOFError:
                break
        
        self._running = False
        print()
        print("再见!")
    
    def stop(self):
        """停止交互"""
        self._running = False
    
    def _handle_special_command(self, text: str) -> bool:
        """处理特殊命令"""
        text_lower = text.lower()
        
        # 退出命令
        if text_lower in ["exit", "quit", "q", "退出", "bye"]:
            self._running = False
            return True
        
        # 帮助命令
        if text_lower in ["help", "h", "帮助", "?"]:
            self.ui.print_help()
            return True
        
        # 停止/取消命令
        if text_lower in ["/stop", "stop", "停止", "取消", "cancel"]:
            if self.brain:
                self.brain.cancel()
                self.ui.print_info("已停止")
            return True
        
        # 过滤命令行命令（用户可能误输入启动命令）
        if text_lower.startswith("python") or text_lower.startswith("py "):
            self.ui.print_error("这是启动命令，不是有效的机器人指令。请输入自然语言指令，例如：'去会议室'、'关灯'、'查看电量'")
            return True
        
        # 过滤其他命令行模式
        if any(cmd in text_lower for cmd in ["pip ", "cd ", "ls", "dir", "cmd", "bash"]):
            self.ui.print_error("这是系统命令，不是有效的机器人指令。请输入自然语言指令。")
            return True
        
        return False
    
    def _process_input(self, text: str):
        """处理用户输入 - 先显示规划，再执行"""
        print()  # 换行，开始处理
        
        try:
            if not self.brain:
                self.ui.print_error("大脑未初始化")
                return
            
            # 显示思考动画
            print("思考中...", end="", flush=True)
            
            # 收集所有响应
            all_responses = []
            plan_steps = []
            current_step = 0
            final_response = None
            had_action = False
            
            if hasattr(self.brain, 'think'):
                for resp in self.brain.think(text):
                    if not isinstance(resp, dict):
                        resp_dict = {
                            "type": resp.type,
                            "content": resp.content,
                            "metadata": resp.metadata or {}
                        }
                    else:
                        resp_dict = resp
                    
                    all_responses.append(resp_dict)
                    
                    response_type = resp_dict.get("type", "text")
                    
                    if response_type == "plan":
                        # 清除"思考中"
                        print("\r" + " " * 20 + "\r", end="")
                        # 显示规划
                        steps = resp_dict.get("metadata", {}).get("steps", [])
                        plan_steps = steps
                        self.ui.print_plan(steps)
                        print("执行中...")
                        
                    elif response_type == "action":
                        current_step += 1
                        had_action = True
                        skill_name = resp_dict.get("metadata", {}).get("skill", "")
                        desc = self.ui._get_skill_desc(skill_name)
                        self.ui.print_skill_start(skill_name, desc, current_step)
                        
                    elif response_type == "result":
                        success = resp_dict.get("metadata", {}).get("success", False)
                        message = resp_dict.get("content", "")
                        self.ui.print_skill_result(success, message)
                        
                    elif response_type == "text":
                        # 清洗文本，移除污染内容
                        raw_text = resp_dict.get("content", "")
                        final_response = sanitize_output(raw_text)
                        
                    elif response_type == "error":
                        print("\r" + " " * 20 + "\r", end="")
                        self.ui.print_error(resp_dict.get("content", ""))
            else:
                print("\r" + " " * 20 + "\r", end="")
                self.ui.print_error("大脑没有think方法")
                return
            
            # 清除思考提示
            print("\r" + " " * 20 + "\r", end="")
            
            # 显示最终回复
            if final_response:
                self.ui.print_robot_response(final_response)
            elif had_action:
                self.ui.print_robot_response("本轮操作已执行完成。")
            
            # 保存历史
            self.conversation_history.append({
                "input": text,
                "responses": all_responses,
                "time": datetime.now().isoformat()
            })
            
        except Exception as e:
            print("\r" + " " * 20 + "\r", end="")
            self.ui.print_error(f"错误: {str(e)}")
            import traceback
            traceback.print_exc()


def create_interaction_manager(brain=None) -> InteractionManager:
    """工厂函数：创建交互管理器"""
    return InteractionManager(brain)
