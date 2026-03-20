"""
智能大脑 - 实现高级推理和任务规划
"""

import threading
import time
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field

from fishmindos.skills import SkillRegistry
from fishmindos.adapters.base import RobotAdapter
from fishmindos.brain.planner import TaskPlanner, ChainExecutor, TaskPlan


@dataclass
class BrainResponse:
    """大脑响应"""
    type: str  # thought, plan, action, result, text, error
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)


class SmartBrain:
    """
    智能大脑
    具备任务规划、推理、执行能力的智能体
    """
    
    def __init__(self, registry: SkillRegistry, adapter: RobotAdapter):
        self.registry = registry
        self.adapter = adapter
        self.planner = TaskPlanner(registry)
        self.executor = ChainExecutor(registry, on_progress=self._on_progress)
        
        self._cancel_event = threading.Event()
        self._current_plan: Optional[TaskPlan] = None
        self._progress_callback: Optional[Callable] = None
        
        # 会话状态
        self.session_context: Dict[str, Any] = {
            "conversation_history": [],
            "executed_tasks": [],
            "current_location": None,
            "carrying_item": None,
        }
    
    def set_progress_callback(self, callback: Callable):
        """设置进度回调"""
        self._progress_callback = callback
    
    def _on_progress(self, progress: Dict[str, Any]):
        """进度回调"""
        if self._progress_callback:
            self._progress_callback(progress)
    
    def think(self, user_input: str) -> List[BrainResponse]:
        """
        思考过程
        
        分析用户输入，规划任务，执行任务
        
        Returns:
            响应列表
        """
        self._cancel_event.clear()
        responses = []
        
        # 1. 思考阶段
        responses.append(BrainResponse(
            type="thought",
            content=f"正在分析您的指令: '{user_input}'",
            metadata={"input": user_input}
        ))
        
        # 2. 任务规划
        try:
            plan = self.planner.plan(user_input, self.session_context)
            self._current_plan = plan
            
            # 显示规划结果
            responses.append(BrainResponse(
                type="plan",
                content=f"已规划任务: {plan.goal}",
                metadata={
                    "goal": plan.goal,
                    "steps_count": len(plan.subtasks),
                    "steps": [st.description for st in plan.subtasks]
                }
            ))
            
            # 3. 执行任务
            responses.append(BrainResponse(
                type="thought",
                content=f"开始执行 {len(plan.subtasks)} 个子任务...",
            ))
            
            # 执行每个子任务
            for i, subtask in enumerate(plan.subtasks, 1):
                if self._cancel_event.is_set():
                    responses.append(BrainResponse(
                        type="error",
                        content="任务已取消"
                    ))
                    return responses
                
                # 显示正在执行
                responses.append(BrainResponse(
                    type="action",
                    content=f"步骤 {i}/{len(plan.subtasks)}: {subtask.description}",
                    metadata={
                        "step": i,
                        "total": len(plan.subtasks),
                        "skill": subtask.skill,
                        "params": subtask.params
                    }
                ))
                
                # 执行子任务
                skill = self.registry.get(subtask.skill)
                if skill:
                    try:
                        result = skill.run(subtask.params, self.session_context)
                        subtask.result = result
                        subtask.status = "completed" if result.get("ok") else "failed"
                        
                        responses.append(BrainResponse(
                            type="result",
                            content=result.get("detail", ""),
                            metadata={
                                "success": result.get("ok", False),
                                "skill": subtask.skill,
                                "data": result.get("data")
                            }
                        ))
                    except Exception as e:
                        subtask.status = "failed"
                        responses.append(BrainResponse(
                            type="error",
                            content=f"执行失败: {str(e)}",
                            metadata={"skill": subtask.skill}
                        ))
                else:
                    subtask.status = "failed"
                    responses.append(BrainResponse(
                        type="error",
                        content=f"技能 {subtask.skill} 不存在",
                        metadata={"skill": subtask.skill}
                    ))
                
                # 更新会话上下文
                self._update_context(subtask)
            
            # 4. 任务完成总结
            completed = sum(1 for st in plan.subtasks if st.status == "completed")
            failed = sum(1 for st in plan.subtasks if st.status == "failed")
            
            if failed == 0:
                summary = f"任务完成！共执行 {completed} 个步骤。"
            else:
                summary = f"任务部分完成: {completed} 成功, {failed} 失败"
            
            responses.append(BrainResponse(
                type="text",
                content=summary,
                metadata={
                    "completed": completed,
                    "failed": failed,
                    "total": len(plan.subtasks)
                }
            ))
            
        except Exception as e:
            responses.append(BrainResponse(
                type="error",
                content=f"规划或执行失败: {str(e)}"
            ))
        
        # 记录到历史
        self.session_context["conversation_history"].append({
            "input": user_input,
            "responses": responses
        })
        
        return responses
    
    def think_simple(self, user_input: str) -> List[Dict[str, Any]]:
        """
        简化的思考接口（兼容旧版）
        
        Returns:
            简化的响应列表
        """
        brain_responses = self.think(user_input)
        
        # 转换为旧格式
        simple_responses = []
        for resp in brain_responses:
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
            elif resp.type == "plan":
                # 显示计划
                steps = resp.metadata.get("steps", [])
                plan_text = "执行计划:\n" + "\n".join([f"  {i+1}. {step}" for i, step in enumerate(steps)])
                simple_responses.append({
                    "type": "text",
                    "text": plan_text
                })
        
        return simple_responses
    
    def _update_context(self, subtask):
        """更新会话上下文"""
        # 更新位置
        if subtask.skill in ["nav_goto_location", "nav_start"]:
            location = subtask.params.get("location") or subtask.params.get("map_name")
            if location:
                self.session_context["current_location"] = location
        
        # 更新携带物品
        if subtask.skill == "item_pickup" and subtask.result:
            if subtask.result.get("ok"):
                self.session_context["carrying_item"] = subtask.result.get("data", {}).get("item")
        
        if subtask.skill == "item_dropoff" and subtask.result:
            if subtask.result.get("ok"):
                self.session_context["carrying_item"] = None
    
    def cancel(self):
        """取消当前任务"""
        self._cancel_event.set()
        self.executor.cancel()
    
    def get_current_plan(self) -> Optional[TaskPlan]:
        """获取当前任务计划"""
        return self._current_plan
    
    def get_progress(self) -> Dict[str, Any]:
        """获取当前进度"""
        if not self._current_plan:
            return {"completed": 0, "total": 0, "percentage": 0}
        
        completed, total = self._current_plan.get_progress()
        percentage = (completed / total * 100) if total > 0 else 0
        
        return {
            "completed": completed,
            "total": total,
            "percentage": percentage
        }
