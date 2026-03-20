"""
FishMindOS - 基于LLM的智能大脑
使用LLM进行意图识别、任务规划和技能调用
"""

import json
import threading
from typing import Any, Dict, List, Optional, Generator
from dataclasses import dataclass, field

from fishmindos.skills.base import SkillRegistry
from fishmindos.adapters.fishbot import FishBotAdapter
from fishmindos.brain.llm_providers import LLMProvider, LLMMessage, create_llm_provider
from fishmindos.brain.planner import TaskPlanner
from fishmindos.brain.smart_brain import SmartBrain
from fishmindos.config import get_config
from fishmindos.brain.prompt_manager import AgentPromptManager


@dataclass
class BrainResponse:
    """大脑响应"""
    type: str  # thought, plan, action, result, text, error
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskPlan:
    """任务计划"""
    def __init__(self, steps: List[Dict[str, Any]]):
        self.steps = steps
        self.current_step = 0
    
    def next_step(self) -> Optional[Dict[str, Any]]:
        """获取下一步"""
        if self.current_step < len(self.steps):
            step = self.steps[self.current_step]
            self.current_step += 1
            return step
        return None
    
    def is_complete(self) -> bool:
        """是否完成"""
        return self.current_step >= len(self.steps)


class LLMBrain:
    """
    基于LLM的智能大脑
    使用大语言模型进行真正的意图理解和任务规划
    """
    
    def __init__(self, registry: SkillRegistry, adapter: FishBotAdapter, 
                 llm_provider: Optional[LLMProvider] = None):
        self.registry = registry
        self.adapter = adapter
        self.planner = TaskPlanner(registry)
        self._cancel_event = threading.Event()
        self._current_plan: Optional[TaskPlan] = None
        
        # 初始化提示词管理器（读取 docs/ 文件夹）
        self.prompt_manager = AgentPromptManager()
        
        # 初始化LLM提供商
        if llm_provider is None:
            config = get_config()
            try:
                self.llm = create_llm_provider(config.llm)
                print(f"OK LLM提供商已初始化: {config.llm.provider} ({config.llm.model})")
            except Exception as e:
                print(f"WARN LLM初始化失败: {e}，将使用规则引擎")
                self.llm = None
        else:
            self.llm = llm_provider
        
        # 会话上下文 - 包含对话历史
        self.session_context: Dict[str, Any] = {
            "conversation_history": [],
            "executed_tasks": [],
            "current_location": None,
            "carrying_item": None,
            "last_input": None,
            "last_plan": None,
        }
    
    def _get_system_prompt(self) -> str:
        """获取系统提示词 - 从 docs/ 文件夹加载"""
        # 生成基础提示词（包含技能和当前状态）
        config = get_config()
        identity = config.app.identity
        
        # 获取可用技能列表
        available_skills = self.registry.get_tools()
        skills_description = "\n".join([
            f"- {s['function']['name']}: {s['function']['description']}"
            for s in available_skills[:20]
        ])
        
        # 精简的系统提示词（避免塞入过多文档内容被复读）
        prompt_parts = []
        
        # 1. 核心身份（精简，不含示例）
        prompt_parts.append(f"""你是 FishMindOS，{identity}的智能控制系统。
你的任务是通过调用工具完成用户指令，禁止用纯文本回复动作请求。""")
        
        # 2. 当前可用技能（工具定义）
        prompt_parts.append(f"""# 可用工具
{skills_description}""")
        
        # 3. 关键约束（精简版）
        prompt_parts.append("""
# 约束
1. 动作请求必须调用工具，禁止纯文本回复
2. 导航顺序: system_status → motion_stand → [必要时 nav_start] → nav_goto_location
3. 地图 vs 路点:
   - 地图(Map): 整层或区域，如"26层"、"3层"
   - 路点(Waypoint): 地图内的位置，如"会议室"、"厕所"、"回充点"
   - 只有切换地图或当前地图未知时才需要 nav_start
4. 回充: nav_goto_location(location="回充点", location_type="dock")
5. 参数用JSON格式，不要XML
6. 一次性返回所有工具调用
7. 复合指令处理 - 必须完整规划所有步骤:
   用户说"去A，然后做B，然后做C"时，必须一次性返回所有工具调用:
   - 步骤1: 导航到A (system_status → motion_stand → [必要时 nav_start] → nav_goto_location)
   - 步骤2: 等待到达 (普通路点用 system_wait(event_type="arrival")；回充用 system_wait(event_type="dock_complete"))
   - 步骤3: 做B (如 light_set)
   - 步骤4: 如有必要再等待完成
   - 步骤5: 做C (如 nav_goto_location 到下一个地点)
   
   示例: "去大厅，亮红灯，然后去厕所"
   正确规划:
   1. system_status()
   2. motion_stand()
   3. nav_goto_location(location="大厅")
   4. system_wait(event_type="arrival")
   5. light_set(code=11)  # 亮红灯
   6. nav_goto_location(location="厕所")
   7. system_wait(event_type="arrival")
   
   禁止: 只返回前3步，漏掉亮红灯和去厕所！
""")
        
        # 4. 当前状态（动态）
        current_map = self.session_context.get('current_map', {})
        map_info = f"{current_map.get('name', '未加载')}(ID:{current_map.get('id', '无')})" if current_map else "未加载"
        prompt_parts.append(f"""# 当前状态
- 地图: {map_info}
- 位置: {self.session_context.get('current_location', '未知')}
- 身份: {identity}
""")
        
        return "\n\n---\n\n".join(prompt_parts)
    
    def think(self, user_input: str) -> Generator[BrainResponse, None, None]:
        """
        使用LLM进行思考
        支持多轮对话，直到任务完成
        """
        self._cancel_event.clear()
        
        # 如果没有LLM，使用规则引擎
        if self.llm is None:
            yield from self._rule_based_think(user_input)
            return
        
        try:
            # 保存当前输入
            self.session_context["last_input"] = user_input
            
            # 1. 构建消息（包含结构化状态，而非自然语言摘要）
            messages = [
                LLMMessage(role="system", content=self._get_system_prompt()),
            ]
            
            # 添加结构化状态记忆（不是对话历史）
            context_info = self._get_context_info()
            if context_info:
                messages.append(LLMMessage(role="system", content=f"[当前状态]\n{context_info}"))
            
            # 检测复合指令并添加提示
            compound_hint = self._detect_compound_instruction(user_input)
            if compound_hint:
                messages.append(LLMMessage(role="system", content=compound_hint))

            planning_hint = self._get_planning_mode_hint(user_input)
            if planning_hint:
                messages.append(LLMMessage(role="system", content=planning_hint))
            
            # 添加当前输入
            messages.append(LLMMessage(role="user", content=user_input))
            
            # 打印调试信息
            if context_info:
                print(f"[DEBUG] 使用状态上下文")
            if compound_hint:
                print(f"[DEBUG] 检测到复合指令，已添加提示")
            if planning_hint:
                print(f"[DEBUG] 使用规划优先模式")
            
            # 2. 获取可用技能作为工具
            available_tools = self._get_available_tools(user_input)
            allowed_tool_names = {
                tool.get("function", {}).get("name")
                for tool in available_tools
                if tool.get("function", {}).get("name")
            }
            tools = self.llm.get_tool_definitions(available_tools)
            
            # 3. 多轮对话，直到LLM不再调用工具
            max_iterations = 10
            iteration = 0
            final_text = ""
            
            # 收集所有计划步骤
            all_steps = []
            executed_steps = []
            plan_shown = False
            shown_plan_length = 0
            consecutive_failures = 0
            executed_any_step = False
            had_failures = False
            
            while iteration < max_iterations:
                iteration += 1
                
                # 调用LLM
                llm_response = self.llm.chat(
                    messages=messages,
                    tools=tools,
                    temperature=0.1  # 降低温度，更确定性
                )
                
                # 处理工具调用
                if llm_response.tool_calls:
                    # 收集这一轮的所有工具调用
                    round_steps = []
                    for tool_call in llm_response.tool_calls:
                        try:
                            extracted_calls = self._extract_steps_from_tool_call(tool_call)
                            for fixed_call in extracted_calls:
                                if fixed_call["name"] not in allowed_tool_names:
                                    print(f"[WARN] 规划模式下忽略工具: {fixed_call['name']}")
                                    continue
                                step = {
                                    'skill': fixed_call['name'],
                                    'params': fixed_call['arguments'],
                                    'tool_call': tool_call
                                }
                                round_steps.append(step)
                        except Exception as e:
                            print(f"[WARN] 解析工具调用失败: {e}")
                            continue
                    
                    # 强制按正确顺序排序（导航任务）
                    round_steps = self._sort_steps(round_steps)
                    
                    # 收集所有步骤（包括多轮返回的）
                    all_steps.extend(round_steps)

                    if not round_steps:
                        if self.session_context.get("planning_only"):
                            messages.append(LLMMessage(
                                role="system",
                                content="规划模式下禁止调用 nav_list_maps/nav_list_waypoints，请直接返回动作步骤。"
                            ))
                        continue
                    
                    # 如果是第一轮且有步骤，显示完整计划
                    if iteration == 1 and round_steps and not plan_shown:
                        yield BrainResponse(
                            type="plan",
                            content="",
                            metadata={"steps": all_steps.copy()}
                        )
                        plan_shown = True
                        shown_plan_length = len(all_steps)
                        # 保存计划到上下文
                        self.session_context["last_plan"] = all_steps.copy()
                    elif self.session_context.get("planning_only") and round_steps and len(all_steps) > shown_plan_length:
                        yield BrainResponse(
                            type="plan",
                            content="",
                            metadata={"steps": all_steps.copy()}
                        )
                        shown_plan_length = len(all_steps)
                        self.session_context["last_plan"] = all_steps.copy()
                    
                    # 执行这一轮的每个工具调用
                    for i, step in enumerate(round_steps):
                        if self._cancel_event.is_set():
                            yield BrainResponse(type="error", content="任务已取消")
                            return
                        
                        function_name = step['skill']
                        arguments = self._normalize_step_arguments(function_name, step['params'])
                        
                        # 跳过已执行的步骤（防重复）
                        step_key = f"{function_name}:{json.dumps(arguments, sort_keys=True)}"
                        if step_key in executed_steps:
                            continue
                        
                        # 显示技能调用
                        yield BrainResponse(
                            type="action",
                            content=f"执行技能: {function_name}",
                            metadata={
                                "skill": function_name,
                                "params": arguments,
                                "step_num": len(executed_steps) + 1
                            }
                        )
                        
                        # 执行技能
                        skill = self.registry.get(function_name)
                        if skill:
                            try:
                                result = skill.run(arguments, self.session_context)
                                # 检查结果是否为 None
                                if result is None:
                                    error_msg = f"技能 {function_name} 返回 None"
                                    yield BrainResponse(type="error", content=error_msg)
                                    consecutive_failures += 1
                                    continue
                                result_content = result.get("detail", "")
                                success = result.get("ok", False)
                                
                                yield BrainResponse(
                                    type="result",
                                    content=result_content,
                                    metadata={
                                        "success": success,
                                        "skill": function_name,
                                        "data": result.get("data")
                                    }
                                )
                                
                                executed_steps.append(step_key)
                                executed_any_step = True
                                
                                # 更新连续失败计数
                                if success:
                                    consecutive_failures = 0
                                else:
                                    had_failures = True
                                    consecutive_failures += 1
                                    if consecutive_failures >= 2:
                                        yield BrainResponse(
                                            type="error",
                                            content="连续执行失败，任务中止。请检查参数或手动处理。"
                                        )
                                        break
                                
                                # 更新上下文
                                self._update_context(function_name, result)
                                
                                # 添加到消息历史
                                messages.append(LLMMessage(
                                    role="assistant",
                                    content=f"调用了 {function_name}",
                                    tool_calls=[step['tool_call']]
                                ))
                                messages.append(LLMMessage(
                                    role="tool",
                                    content=json.dumps({"result": result_content, "success": success}),
                                    tool_call_id=step['tool_call'].get('id', '')
                                ))
                                
                            except Exception as e:
                                error_msg = f"执行异常: {str(e)}"
                                yield BrainResponse(type="error", content=error_msg)
                                messages.append(LLMMessage(
                                    role="tool",
                                    content=json.dumps({"error": error_msg}),
                                    tool_call_id=step['tool_call'].get('id', '')
                                ))
                                had_failures = True
                                consecutive_failures += 1
                        else:
                            yield BrainResponse(
                                type="error",
                                content=f"技能 {function_name} 不存在"
                            )
                    
                    # 如果连续失败过多，跳出循环
                    if consecutive_failures >= 2:
                        break
                    if self.session_context.get("planning_only") and round_steps:
                        if self._planning_requirements_met(user_input, all_steps):
                            break
                        messages.append(LLMMessage(
                            role="system",
                            content=self._get_planning_followup_hint(user_input, all_steps)
                        ))
                    elif round_steps and self._is_action_request(user_input):
                        if self._planning_requirements_met(user_input, all_steps):
                            break
                        
                else:
                    # 没有工具调用
                    if iteration == 1:
                        # 第一轮就没有工具调用，说明LLM没理解要执行动作
                        # 检查是否是纯查询类输入
                        query_keywords = ['?', '？', '多少', '什么', '哪些', '吗', '呢']
                        is_query = any(kw in user_input for kw in query_keywords)
                        
                        if self._is_action_request(user_input) and not is_query:
                            # 看起来是动作指令但没有调用工具，提示错误
                            error_msg = "我理解您的指令，但没有执行具体操作。请重试或检查系统状态。"
                            yield BrainResponse(type="error", content=error_msg)
                            # 添加错误到消息，让LLM知道需要调用工具
                            messages.append(LLMMessage(
                                role="tool",
                                content=json.dumps({"error": "用户要求执行动作，请调用相应技能"})
                            ))
                            continue  # 继续循环，让LLM重新生成
                    
                    # 纯查询或已经重试过，返回文本回复
                    if llm_response.content:
                        final_text = llm_response.content
                    break
            
            planning_complete = self._planning_requirements_met(user_input, all_steps) if self.session_context.get("planning_only") else True

            # 输出最终文本回复
            if self.session_context.get("planning_only") and executed_any_step and planning_complete:
                yield BrainResponse(type="text", content="本轮操作已执行完成。")
            elif self.session_context.get("planning_only") and not planning_complete:
                yield BrainResponse(
                    type="error",
                    content="规划未完整覆盖用户需求，请继续优化提示词或仿真场景。"
                )
            elif final_text and not self._is_polluted_text(final_text):
                yield BrainResponse(type="text", content=final_text)
            elif executed_any_step:
                yield BrainResponse(type="text", content="本轮操作已执行完成。")
            
            # 保存到历史（简化为一句话总结，不保留详细步骤）
            executed_skills = [s["skill"] for s in all_steps]
            history_summary = f"执行了: {', '.join(executed_skills)}" if executed_skills else "无操作"
            
            self.session_context["conversation_history"].append({
                "input": user_input,
                "summary": history_summary
            })
            # 保持历史不过长（最多保留3轮，减少干扰）
            if len(self.session_context["conversation_history"]) > 3:
                self.session_context["conversation_history"] = self.session_context["conversation_history"][-3:]
            
        except Exception as e:
            yield BrainResponse(type="error", content=f"LLM处理失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _sort_steps(self, steps: List[Dict]) -> List[Dict]:
        """
        仅对关键前置步骤做最小重排，尽量保留LLM原始顺序。
        """
        if not steps:
            return steps

        prefix_order = ["system_status", "motion_stand", "nav_start"]
        prefix_steps: List[Dict] = []
        used_indexes = set()

        for skill_name in prefix_order:
            for idx, step in enumerate(steps):
                if idx in used_indexes:
                    continue
                if step.get("skill") == skill_name:
                    prefix_steps.append(step)
                    used_indexes.add(idx)
                    break

        remaining_steps = [
            step for idx, step in enumerate(steps)
            if idx not in used_indexes
        ]
        return prefix_steps + remaining_steps

    def _is_action_request(self, user_input: str) -> bool:
        """识别更像动作而不是查询的输入。"""
        action_keywords = [
            "去", "返回", "回", "前往", "到", "亮", "关灯", "开灯",
            "播报", "播放", "站立", "趴下", "启动导航", "停止",
        ]
        return any(keyword in user_input for keyword in action_keywords)

    def _is_polluted_text(self, text: str) -> bool:
        """过滤模型把思维链或工具片段直接吐给用户的情况。"""
        polluted_markers = [
            "<think", "</think>", "<tool_call", "</tool_call>",
            "<arg_key>", "<arg_value>", "调用了", "调调用了",
        ]
        return any(marker in text for marker in polluted_markers)

    def _normalize_step_arguments(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """在执行前补齐少量可从上下文安全推导的参数。"""
        normalized = dict(arguments or {})

        if function_name == "system_wait" and normalized.get("event_type") == "arrival":
            if not normalized.get("waypoint_id"):
                pending = self.session_context.get("pending_arrival") or self.session_context.get("last_waypoint")
                if isinstance(pending, dict):
                    waypoint_id = pending.get("waypoint_id") or pending.get("id")
                    if waypoint_id:
                        normalized["waypoint_id"] = waypoint_id

        if function_name == "nav_start":
            has_map_name = bool(normalized.get("map_name"))
            has_map_id = normalized.get("map_id") is not None
            if not has_map_name and not has_map_id:
                current_map = self.session_context.get("current_map")
                if isinstance(current_map, dict):
                    if current_map.get("id") is not None:
                        normalized["map_id"] = current_map.get("id")
                    if current_map.get("name"):
                        normalized["map_name"] = current_map.get("name")

        return normalized
    
    def _detect_compound_instruction(self, user_input: str) -> str:
        """检测复合指令并返回提示"""
        user_lower = user_input.lower()
        
        # 检测连接词
        connectors = ['然后', '再', '接着', '之后', '随后', '完成后', '以后']
        action_keywords = ['去', '亮', '关灯', '开灯', '播报', '播放', '返回', '到', '前往']
        
        connector_count = sum(1 for c in connectors if c in user_input)
        action_count = sum(1 for a in action_keywords if a in user_lower)
        
        # 如果有多于2个动作且至少1个连接词，视为复合指令
        if action_count >= 2 and connector_count >= 1:
            return f"""[复合指令检测]
用户输入包含多个动作步骤，请完整规划所有步骤：
输入: "{user_input}"

必须包含：
1. 导航相关: system_status → motion_stand → [必要时 nav_start] → nav_goto_location → system_wait
2. 灯光控制: light_set (如果需要)
3. 语音播报: audio_play 或 tts_speak (如果需要)
4. 后续导航: nav_goto_location → system_wait (如果还有下一个地点)
5. 回充结束: nav_goto_location(location_type="dock") → system_wait(event_type="dock_complete")

禁止遗漏任何步骤！"""
        
        return ""

    def _get_available_tools(self, user_input: str) -> List[Dict[str, Any]]:
        """根据当前模式过滤给 LLM 的工具集合。"""
        tools = self.registry.get_tools()
        if self.session_context.get("planning_only"):
            disabled = {"nav_list_maps", "nav_list_waypoints"}
            tools = [
                tool for tool in tools
                if tool.get("function", {}).get("name") not in disabled
            ]
        return tools

    def _get_planning_mode_hint(self, user_input: str) -> str:
        """在 mock 规划模式下，明确告诉模型直接做任务规划。"""
        if not self.session_context.get("planning_only"):
            return ""

        lines = [
            "[仿真规划模式]",
            "当前目标是测试任务规划与决策，不是测试地图查询。",
            "不要调用 nav_list_maps 或 nav_list_waypoints。",
            "请直接基于已知场景规划动作序列。",
            "如果用户提到楼层、楼上或楼下，这通常表示切换地图，应先使用 nav_start(map_name=...)，再执行 nav_goto_location。",
            "如果用户要求拿、送、给物品，优先考虑 item_pickup、item_dropoff 或 item_place。",
            "不要只返回 system_status / motion_stand / nav_start，必须把后续动作一起规划出来。",
        ]

        mock_world = self.session_context.get("mock_world")
        if isinstance(mock_world, dict):
            current_map = mock_world.get("current_map")
            if current_map:
                lines.append(f"当前默认地图: {current_map}")
            aliases = mock_world.get("map_aliases", {})
            if aliases:
                alias_text = ", ".join(f"{alias}={target}" for alias, target in aliases.items())
                lines.append(f"地图别名: {alias_text}")
            waypoints = mock_world.get("waypoints", {})
            for map_name, names in waypoints.items():
                if names:
                    lines.append(f"{map_name} 路点: {', '.join(names)}")

        return "\n".join(lines)

    def _is_lookup_query(self, user_input: str) -> bool:
        """识别用户是否真的在问地图/路点列表。"""
        direct_keywords = [
            "哪些地图", "有什么地图", "地图列表", "列出地图",
            "哪些路点", "有什么路点", "路点列表", "列出路点",
        ]
        if any(keyword in user_input for keyword in direct_keywords):
            return True

        asks_for_list = any(keyword in user_input for keyword in ["哪些", "有什么", "列出", "查看", "看看"])
        mentions_world = any(keyword in user_input for keyword in ["地图", "路点", "楼层", "楼下", "楼上"])
        return asks_for_list and mentions_world

    def _planning_requirements_met(self, user_input: str, steps: List[Dict[str, Any]]) -> bool:
        """判断规划优先模式下本轮计划是否已经覆盖用户需求。"""
        skill_names = [step.get("skill", "") for step in steps]
        if not skill_names:
            return False

        has_navigation = any(name in {"nav_goto_location", "nav_goto_waypoint"} for name in skill_names)
        if self._is_action_request(user_input) and not has_navigation and any(k in user_input for k in ["去", "到", "返回", "回"]):
            return False

        if any(k in user_input for k in ["亮", "灯", "关灯"]) and not any(name.startswith("light_") for name in skill_names):
            return False

        if any(k in user_input for k in ["播报", "播放", "说"]) and not any(name in {"audio_play", "tts_speak"} for name in skill_names):
            return False

        if any(k in user_input for k in ["回充", "充电", "回充点", "充电点", "回桩"]):
            has_dock_nav = any(
                step.get("skill") == "nav_goto_location" and step.get("params", {}).get("location_type") == "dock"
                for step in steps
            )
            has_dock_wait = any(
                step.get("skill") == "system_wait" and step.get("params", {}).get("event_type") == "dock_complete"
                for step in steps
            )
            if not (has_dock_nav and has_dock_wait):
                return False

        if any(k in user_input for k in ["拿", "取", "给我", "送到", "放到", "交给"]):
            if not any(name in {"item_pickup", "item_dropoff", "item_place"} for name in skill_names):
                return False

        if self._detect_compound_instruction(user_input) and len(steps) < 4:
            return False

        return True

    def _get_planning_followup_hint(self, user_input: str, steps: List[Dict[str, Any]]) -> str:
        """当首轮只规划了前置步骤时，提醒模型补全剩余动作。"""
        planned = ", ".join(step.get("skill", "") for step in steps if step.get("skill"))
        return (
            "[规划未完成]\n"
            f"用户原始指令: {user_input}\n"
            f"你目前只规划了这些步骤: {planned}\n"
            "请继续补全剩余动作，不要重复已经执行的步骤。"
        )
    
    def _get_context_info(self) -> str:
        """获取结构化的上下文状态（不是对话历史）"""
        parts = []
        
        # 当前地图
        current_map = self.session_context.get("current_map")
        if current_map:
            parts.append(f"地图: {current_map.get('name', '未知')}")
        
        # 当前位置
        current_location = self.session_context.get("current_location")
        if current_location:
            parts.append(f"位置: {current_location}")
        
        # 导航状态
        if self.adapter and hasattr(self.adapter, 'get_status'):
            try:
                status = self.adapter.get_status()
                if status.nav_running:
                    parts.append("状态: 正在导航")
                else:
                    parts.append("状态: 待机")
            except:
                pass
        
        # 携带物品
        carrying = self.session_context.get("carrying_item")
        if carrying:
            parts.append(f"携带: {carrying}")
        
        return "\n".join(parts) if parts else ""
    
    def _summarize_responses(self, responses: List[Dict]) -> str:
        if not responses:
            return "任务完成"
        
        parts = []
        for r in responses:
            skill = r.get("skill", "")
            # 只保留关键信息
            if skill:
                parts.append(skill)
        
        return f"执行了: {', '.join(parts[:3])}" if parts else "已处理"

    def _extract_steps_from_tool_call(self, tool_call: Dict) -> List[Dict[str, Any]]:
        """从单个 tool_call 中提取一个或多个步骤。"""
        recovered_calls = self._recover_compound_tool_call(tool_call)
        if recovered_calls:
            return recovered_calls

        fixed_call = self._fix_tool_call(tool_call)
        return [fixed_call] if fixed_call else []

    def _recover_compound_tool_call(self, tool_call: Dict) -> List[Dict[str, Any]]:
        """恢复被模型错误压成一个 tool_call 的复合任务。"""
        function_data = tool_call.get("function", {})
        name_str = function_data.get("name", "") or ""
        args_str = function_data.get("arguments", "") or ""

        skill_names = sorted(self.registry.list_all(), key=len, reverse=True)
        if not args_str:
            return []

        hit_count = sum(args_str.count(skill) for skill in skill_names)
        if hit_count < 2:
            return []

        import re

        pair_pattern = r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"'
        raw_pairs = re.findall(pair_pattern, args_str)
        if not raw_pairs:
            return []

        def decode_json_string(raw: str) -> str:
            try:
                return json.loads(f'"{raw}"')
            except Exception:
                return raw

        recovered: List[Dict[str, Any]] = []
        current_step: Optional[Dict[str, Any]] = None

        if name_str in self.registry.list_all():
            recovered.append({"name": name_str, "arguments": {}})

        def flush_current():
            nonlocal current_step
            if current_step:
                recovered.append(current_step)
                current_step = None

        def find_skills_in_order(text: str) -> List[str]:
            hits = []
            for skill in skill_names:
                start = 0
                while True:
                    index = text.find(skill, start)
                    if index == -1:
                        break
                    hits.append((index, skill))
                    start = index + len(skill)
            hits.sort(key=lambda item: item[0])

            ordered = []
            for _, skill in hits:
                if not ordered or ordered[-1] != skill:
                    ordered.append(skill)
            return ordered

        for raw_key, raw_value in raw_pairs:
            key = decode_json_string(raw_key)
            value = self._coerce_argument_value(decode_json_string(raw_value))

            skills_in_key = find_skills_in_order(key)
            if skills_in_key:
                for skill_name in skills_in_key[:-1]:
                    flush_current()
                    recovered.append({"name": skill_name, "arguments": {}})

                flush_current()
                current_step = {"name": skills_in_key[-1], "arguments": {}}

                param_name = None
                if "<arg_key>" in key:
                    param_name = key.split("<arg_key>")[-1].strip()
                elif "\n" in key:
                    param_name = key.split("\n")[-1].strip()

                if param_name and param_name not in self.registry.list_all():
                    current_step["arguments"][param_name] = value
                continue

            clean_key = key.strip()
            if current_step and clean_key:
                current_step["arguments"][clean_key] = value

        flush_current()

        normalized: List[Dict[str, Any]] = []
        for step in recovered:
            if step["name"] in self.registry.list_all():
                normalized.append({
                    "name": step["name"],
                    "arguments": step.get("arguments", {})
                })

        if len(normalized) <= 1:
            return []
        return normalized

    def _coerce_argument_value(self, value: Any) -> Any:
        """把字符串参数转成更合适的类型。"""
        if not isinstance(value, str):
            return value

        stripped = value.strip()
        if stripped.isdigit():
            try:
                return int(stripped)
            except ValueError:
                pass

        lowered = stripped.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        return stripped
    
    def _fix_tool_call(self, tool_call: Dict) -> Optional[Dict]:
        """
        修复格式混乱的工具调用
        智谱AI有时会返回格式错误的 tool_call
        """
        try:
            function_data = tool_call.get('function', {})
            name_str = function_data.get('name', '')
            args_str = function_data.get('arguments', '{}')
            
            # 如果参数是null或空，尝试从name_str中提取
            if not args_str or args_str == 'null' or args_str == '{}':
                # 可能是参数嵌在name中
                combined = name_str
            else:
                combined = name_str + args_str
            
            # 提取函数名
            import re
            function_name = None
            
            # 常见技能名模式
            skill_patterns = [
                r'(nav_\w+)',
                r'(motion_\w+)',
                r'(system_\w+)',
                r'(light_\w+)',
                r'(audio_\w+)',
                r'(smart_\w+)',
                r'(tts)',
                r'(play_audio)',
            ]
            
            for pattern in skill_patterns:
                match = re.search(pattern, combined)
                if match:
                    function_name = match.group(1)
                    break
            
            if not function_name:
                # 如果找不到，清理原始name
                # 移除所有XML标签
                import re
                cleaned_name = re.sub(r'<[^>]+>', '', name_str)
                cleaned_name = cleaned_name.strip()
                # 如果清理后还有内容，尝试匹配技能名
                if cleaned_name:
                    for pattern in skill_patterns:
                        match = re.search(pattern, cleaned_name)
                        if match:
                            function_name = match.group(1)
                            break
                
                if not function_name:
                    return None

            alias_map = {
                "tts": "tts_speak",
                "play_audio": "audio_play",
            }
            function_name = alias_map.get(function_name, function_name)
            
            # 提取参数
            args = {}
            
            # 方法1：标准XML格式
            pattern1 = r'<arg_key>([^<]+)</arg_key>\s*<arg_value>([^<]*)</arg_value>'
            matches1 = re.findall(pattern1, combined)
            for key, value in matches1:
                key = key.strip()
                if key and not key.startswith('<'):
                    args[key] = value.strip()
            
            # 方法2：简化的 <key>value</key> 格式
            if not args:
                pattern2 = r'<(map_name|location|color|mode|text|waypoint_id|file|audio_file|code|speed|preset_name)\u003e([^<]+)</\1>'
                matches2 = re.findall(pattern2, combined)
                for key, value in matches2:
                    args[key] = value.strip()
            
            # 方法3：JSON格式（可能被包裹在XML中）
            if not args:
                try:
                    # 尝试找JSON对象
                    json_match = re.search(r'\{[^}]+\}', combined)
                    if json_match:
                        args = json.loads(json_match.group(0))
                except:
                    pass
            
            # 特殊处理：如果提取的key包含XML标签，需要清理
            cleaned_args = {}
            for key, value in args.items():
                # 清理key
                clean_key = key.replace('</arg_key>', '').replace('<arg_value>', '').strip()
                if clean_key and not clean_key.startswith('<'):
                    if clean_key in {"waypoint_id", "code"}:
                        try:
                            value = int(value)
                        except (TypeError, ValueError):
                            pass
                    cleaned_args[clean_key] = value
            
            return {
                'name': function_name,
                'arguments': cleaned_args if cleaned_args else args
            }
            
        except Exception as e:
            print(f"[ERROR] 修复工具调用失败: {e}")
            return None
    
    def _rule_based_think(self, user_input: str):
        """基于规则的思考（LLM不可用时使用）"""
        from fishmindos.brain.smart_brain import SmartBrain
        
        rule_brain = SmartBrain(self.registry, self.adapter)
        brain_responses = rule_brain.think(user_input)
        
        for resp in brain_responses:
            yield BrainResponse(
                type=resp.type,
                content=resp.content,
                metadata=resp.metadata
            )
    
    def _update_context(self, skill_name: str, result: Dict):
        """更新会话上下文 - 安全处理失败结果"""
        # 安全获取 data，防止为 None
        data = result.get("data")
        if not isinstance(data, dict):
            data = {}
        
        # nav_start 成功时，保存当前地图信息
        if skill_name == "nav_start" and result.get("ok"):
            map_id = data.get("map_id") or data.get("id")
            map_name = data.get("map_name") or data.get("name")
            print(f"[DEBUG] nav_start 结果: map_id={map_id}, map_name={map_name}")
            if map_id:
                self.session_context["current_map"] = {
                    "id": map_id,
                    "name": map_name or str(map_id)
                }
                self.session_context["current_location"] = map_name or str(map_id)
                print(f"[DEBUG] 上下文已更新: current_map={self.session_context['current_map']}")
        
        # nav_goto_location 成功时，保存当前位置
        if skill_name == "nav_goto_location" and result.get("ok"):
            location = data.get("location") or data.get("waypoint_name")
            if location:
                self.session_context["current_location"] = location
            waypoint_id = data.get("waypoint_id")
            waypoint_name = data.get("waypoint_name") or location
            if waypoint_id:
                pending = {"waypoint_id": waypoint_id, "name": waypoint_name}
                self.session_context["pending_arrival"] = pending
                self.session_context["last_waypoint"] = pending

        if skill_name == "system_wait" and result.get("ok") and data.get("event_type") == "arrival":
            self.session_context.pop("pending_arrival", None)
        
        if skill_name == "item_pickup" and result.get("ok"):
            self.session_context["carrying_item"] = data.get("item")
        
        if skill_name == "item_dropoff" and result.get("ok"):
            self.session_context["carrying_item"] = None
    
    def think_simple(self, user_input: str) -> List[Dict[str, Any]]:
        """简化的思考接口（兼容旧版）"""
        simple_responses = []
        for resp in self.think(user_input):
            if resp.type == "action":
                simple_responses.append({
                    "type": "skill_call",
                    "skill": resp.metadata.get("skill", ""),
                    "params": resp.metadata.get("params", {})
                })
            elif resp.type == "result":
                simple_responses.append({
                    "type": "skill_result",
                    "success": resp.metadata.get("success", False),
                    "message": resp.content
                })
            elif resp.type == "text":
                simple_responses.append({
                    "type": "text",
                    "text": resp.content
                })
        
        return simple_responses
    
    def cancel(self):
        """取消当前任务"""
        self._cancel_event.set()
    
    def get_current_plan(self) -> Optional[TaskPlan]:
        """获取当前任务计划"""
        return self._current_plan
    
    @staticmethod
    def list_supported_providers() -> List[str]:
        """列出支持的LLM提供商"""
        from fishmindos.brain.llm_providers import LLMFactory
        return LLMFactory.list_providers()
