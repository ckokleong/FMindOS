"""
FishMindOS Brain - 智能大脑
实现任务规划、拆解和推理能力
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SubTask:
    """子任务"""
    id: str
    description: str
    skill: str
    params: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)  # 依赖的其他子任务ID
    status: str = "pending"  # pending, running, completed, failed
    result: Any = None


@dataclass
class TaskPlan:
    """任务计划"""
    goal: str
    subtasks: List[SubTask]
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def get_ready_subtasks(self) -> List[SubTask]:
        """获取可以执行的子任务（依赖已完成）"""
        ready = []
        completed_ids = {st.id for st in self.subtasks if st.status == "completed"}
        
        for st in self.subtasks:
            if st.status == "pending":
                # 检查所有依赖是否已完成
                if all(dep in completed_ids for dep in st.dependencies):
                    ready.append(st)
        
        return ready
    
    def is_complete(self) -> bool:
        """检查是否全部完成"""
        return all(st.status in ["completed", "failed"] for st in self.subtasks)
    
    def get_progress(self) -> tuple[int, int]:
        """获取进度 (完成数, 总数)"""
        completed = sum(1 for st in self.subtasks if st.status == "completed")
        return completed, len(self.subtasks)


class TaskPlanner:
    """
    任务规划器
    将复杂任务拆解为可执行的子任务序列
    """
    
    def __init__(self, registry):
        self.registry = registry
        self._task_counter = 0
    
    def _generate_task_id(self) -> str:
        """生成任务ID"""
        self._task_counter += 1
        return f"task_{self._task_counter}"
    
    def plan(self, goal: str, context: Dict[str, Any] = None) -> TaskPlan:
        """
        规划任务
        
        Args:
            goal: 用户目标（如"去大厅取纸送到卫生间"）
            context: 上下文信息
            
        Returns:
            TaskPlan: 任务计划
        """
        context = context or {}
        
        # 分析目标类型
        if self._is_delivery_task(goal):
            return self._plan_delivery_task(goal, context)
        elif self._is_navigation_task(goal):
            return self._plan_navigation_task(goal, context)
        elif self._is_inspection_task(goal):
            return self._plan_inspection_task(goal, context)
        else:
            # 默认处理为简单导航
            return self._plan_simple_task(goal, context)
    
    def _is_delivery_task(self, goal: str) -> bool:
        """判断是否为递送任务"""
        delivery_keywords = ["取", "送", "拿", "带", "递", "交给", "送到", "送去"]
        return any(kw in goal for kw in delivery_keywords)
    
    def _is_navigation_task(self, goal: str) -> bool:
        """判断是否为导航任务"""
        nav_keywords = ["去", "到", "前往", "导航", "走"]
        return any(kw in goal for kw in nav_keywords)
    
    def _is_inspection_task(self, goal: str) -> bool:
        """判断是否为巡检任务"""
        inspection_keywords = ["巡检", "巡逻", "检查", "查看"]
        return any(kw in goal for kw in inspection_keywords)
    
    def _plan_delivery_task(self, goal: str, context: Dict[str, Any]) -> TaskPlan:
        """
        规划递送任务
        
        示例："去大厅取一包纸送到卫生间"
        拆解为：
        1. 导航到大厅
        2. 取纸
        3. 导航到卫生间
        4. 放下纸
        """
        subtasks = []
        
        # 提取关键信息
        pickup_location, item, delivery_location = self._parse_delivery_goal(goal)
        
        # 子任务1: 导航到取货地点
        subtasks.append(SubTask(
            id=self._generate_task_id(),
            description=f"导航到{pickup_location}",
            skill="nav_goto_location",
            params={"location": pickup_location, "location_type": "waypoint"}
        ))
        
        # 子任务2: 等待到达
        subtasks.append(SubTask(
            id=self._generate_task_id(),
            description="等待到达目标点",
            skill="system_wait",
            params={"event_type": "arrival"},
            dependencies=[subtasks[-1].id]
        ))
        
        # 子任务3: 取物品
        subtasks.append(SubTask(
            id=self._generate_task_id(),
            description=f"取{item}",
            skill="item_pickup",
            params={"item_name": item, "location": pickup_location},
            dependencies=[subtasks[-1].id]
        ))
        
        # 子任务4: 导航到送货地点
        subtasks.append(SubTask(
            id=self._generate_task_id(),
            description=f"导航到{delivery_location}",
            skill="nav_goto_location",
            params={"location": delivery_location, "location_type": "waypoint"},
            dependencies=[subtasks[-1].id]
        ))
        
        # 子任务5: 等待到达
        subtasks.append(SubTask(
            id=self._generate_task_id(),
            description="等待到达目标点",
            skill="system_wait",
            params={"event_type": "arrival"},
            dependencies=[subtasks[-1].id]
        ))
        
        # 子任务6: 放下物品
        subtasks.append(SubTask(
            id=self._generate_task_id(),
            description=f"放下{item}",
            skill="item_dropoff",
            params={"item_name": item, "location": delivery_location},
            dependencies=[subtasks[-1].id]
        ))
        
        # 子任务7: 播报完成
        subtasks.append(SubTask(
            id=self._generate_task_id(),
            description="播报完成",
            skill="audio_play",
            params={"text": f"已将{item}送到{delivery_location}，任务完成！"},
            dependencies=[subtasks[-1].id]
        ))
        
        return TaskPlan(
            goal=goal,
            subtasks=subtasks,
            context={
                "pickup_location": pickup_location,
                "item": item,
                "delivery_location": delivery_location,
                "task_type": "delivery"
            }
        )
    
    def _plan_navigation_task(self, goal: str, context: Dict[str, Any]) -> TaskPlan:
        """规划导航任务 - 修复：添加完整的导航前置步骤"""
        subtasks = []
        prev_task_id = None
        
        # 提取目的地和地图
        destination = self._extract_destination(goal)
        map_name = self._extract_map_name(goal)
        
        # 步骤1: 检查状态
        task1 = SubTask(
            id=self._generate_task_id(),
            description="检查当前状态",
            skill="system_status",
            params={}
        )
        subtasks.append(task1)
        prev_task_id = task1.id
        
        # 步骤2: 站立（导航前必须先站立）
        task2 = SubTask(
            id=self._generate_task_id(),
            description="让机器狗站立",
            skill="motion_stand",
            params={},
            dependencies=[prev_task_id]
        )
        subtasks.append(task2)
        prev_task_id = task2.id
        
        # 步骤3: 加载地图（如果指定了地图名）
        if map_name:
            task3 = SubTask(
                id=self._generate_task_id(),
                description=f"加载地图{map_name}",
                skill="nav_start",
                params={"map_name": map_name},
                dependencies=[prev_task_id]
            )
            subtasks.append(task3)
            prev_task_id = task3.id
        
        # 步骤4: 导航到目标
        task4 = SubTask(
            id=self._generate_task_id(),
            description=f"导航到{destination}",
            skill="nav_goto_location",
            params={"location": destination},
            dependencies=[prev_task_id]
        )
        subtasks.append(task4)
        
        return TaskPlan(goal=goal, subtasks=subtasks, context={"destination": destination, "map_name": map_name})
    
    def _plan_inspection_task(self, goal: str, context: Dict[str, Any]) -> TaskPlan:
        """规划巡检任务"""
        subtasks = []
        
        # 提取巡检点
        locations = self._extract_locations(goal)
        
        prev_task_id = None
        for i, location in enumerate(locations):
            # 导航到巡检点
            nav_task = SubTask(
                id=self._generate_task_id(),
                description=f"导航到巡检点{i+1}: {location}",
                skill="nav_goto_location",
                params={"location": location, "location_type": "waypoint"},
                dependencies=[prev_task_id] if prev_task_id else []
            )
            subtasks.append(nav_task)
            
            # 等待到达
            wait_task = SubTask(
                id=self._generate_task_id(),
                description=f"等待到达{location}",
                skill="system_wait",
                params={"event_type": "arrival"},
                dependencies=[nav_task.id]
            )
            subtasks.append(wait_task)
            
            # 拍照/检查
            inspect_task = SubTask(
                id=self._generate_task_id(),
                description=f"检查{location}",
                skill="system_status",
                params={},
                dependencies=[wait_task.id]
            )
            subtasks.append(inspect_task)
            
            prev_task_id = inspect_task.id
        
        return TaskPlan(goal=goal, subtasks=subtasks, context={"locations": locations})
    
    def _plan_simple_task(self, goal: str, context: Dict[str, Any]) -> TaskPlan:
        """规划简单任务"""
        # 尝试匹配技能
        skill_name, params = self._match_skill(goal)
        
        if skill_name:
            subtasks = [SubTask(
                id=self._generate_task_id(),
                description=goal,
                skill=skill_name,
                params=params
            )]
        else:
            subtasks = [SubTask(
                id=self._generate_task_id(),
                description="未知任务",
                skill="audio_play",
                params={"text": "抱歉，我不理解这个任务"}
            )]
        
        return TaskPlan(goal=goal, subtasks=subtasks)
    
    def _parse_delivery_goal(self, goal: str) -> tuple[str, str, str]:
        """
        解析递送任务目标
        
        示例：
        - "去大厅取一包纸送到卫生间" -> ("大厅", "纸", "卫生间")
        - "把文件送到会议室" -> ("当前位置", "文件", "会议室")
        """
        # 默认位置
        pickup_location = "未知位置"
        item = "物品"
        delivery_location = "未知位置"
        
        # 匹配"去...取...送到..."模式
        pattern1 = r"去(.+?)取(.+?)送到(.+)"
        match = re.search(pattern1, goal)
        if match:
            pickup_location = match.group(1).strip()
            item = match.group(2).strip()
            delivery_location = match.group(3).strip()
            return pickup_location, item, delivery_location
        
        # 匹配"把...送到..."模式
        pattern2 = r"把(.+?)送到(.+)"
        match = re.search(pattern2, goal)
        if match:
            item = match.group(1).strip()
            delivery_location = match.group(2).strip()
            pickup_location = "当前位置"
            return pickup_location, item, delivery_location
        
        # 匹配"取...送到..."模式
        pattern3 = r"取(.+?)送到(.+)"
        match = re.search(pattern3, goal)
        if match:
            item = match.group(1).strip()
            delivery_location = match.group(2).strip()
            pickup_location = "大厅"  # 默认取货点
            return pickup_location, item, delivery_location
        
        return pickup_location, item, delivery_location
    
    def _extract_destination(self, goal: str) -> str:
        """提取目的地"""
        # 去除导航关键词
        for keyword in ["去", "到", "前往", "导航到", "走", "去一下"]:
            goal = goal.replace(keyword, "")
        return goal.strip() or "未知地点"

    def _extract_map_name(self, goal: str) -> Optional[str]:
        """提取地图名称（如"26层"、"3楼"等）"""
        import re
        # 匹配常见的地图名称模式
        patterns = [
            r'(\d+)\s*[层楼层]',  # 26层、3楼层
            r'(\d+)\s*[Ff]',      # 26F、3f
            r'([一二三四五六七八九十]+层)',  # 二十六层（中文数字）
        ]
        for pattern in patterns:
            match = re.search(pattern, goal)
            if match:
                return match.group(0)
        return None
    
    def _extract_locations(self, goal: str) -> List[str]:
        """提取多个地点"""
        # 简单实现：按逗号、顿号分隔
        locations = re.split(r"[，、,]", goal)
        # 去除导航关键词
        cleaned = []
        for loc in locations:
            for keyword in ["巡检", "检查", "查看", "去", "到"]:
                loc = loc.replace(keyword, "")
            loc = loc.strip()
            if loc:
                cleaned.append(loc)
        return cleaned if cleaned else ["默认巡检点"]
    
    def _match_skill(self, goal: str) -> tuple[Optional[str], Dict[str, Any]]:
        """匹配技能"""
        goal_lower = goal.lower()
        
        # 技能匹配规则
        skill_patterns = {
            "nav_list_maps": ["地图", "有哪些地图"],
            "nav_list_waypoints": ["路点", "点位"],
            "system_battery": ["电量", "电池"],
            "system_status": ["状态"],
            "motion_stand": ["站立", "起来"],
            "motion_lie_down": ["趴下", "躺下"],
            "light_on": ["开灯"],
            "light_off": ["关灯"],
        }
        
        for skill_name, patterns in skill_patterns.items():
            if any(p in goal_lower for p in patterns):
                return skill_name, {}
        
        return None, {}


class ChainExecutor:
    """
    链式执行器
    按顺序执行任务计划中的子任务
    """
    
    def __init__(self, registry, on_progress: Callable = None):
        self.registry = registry
        self.on_progress = on_progress
        self._cancel_event = threading.Event()
    
    def cancel(self):
        """取消执行"""
        self._cancel_event.set()
    
    def execute(self, plan: TaskPlan, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        执行任务计划
        
        Returns:
            执行结果
        """
        context = context or {}
        self._cancel_event.clear()
        
        results = []
        
        while not plan.is_complete():
            if self._cancel_event.is_set():
                return {
                    "success": False,
                    "message": "任务已取消",
                    "completed": results
                }
            
            # 获取可以执行的子任务
            ready_tasks = plan.get_ready_subtasks()
            
            if not ready_tasks:
                # 没有可执行的任务，但还没完成，说明有依赖问题
                break
            
            for subtask in ready_tasks:
                if self._cancel_event.is_set():
                    return {
                        "success": False,
                        "message": "任务已取消",
                        "completed": results
                    }
                
                # 更新状态
                subtask.status = "running"
                
                # 通知进度
                if self.on_progress:
                    progress = plan.get_progress()
                    self.on_progress({
                        "type": "subtask_start",
                        "subtask": subtask,
                        "progress": progress
                    })
                
                # 执行子任务
                try:
                    skill = self.registry.get(subtask.skill)
                    if skill:
                        result = skill.run(subtask.params, context)
                        subtask.result = result
                        subtask.status = "completed" if result.get("ok") else "failed"
                        
                        results.append({
                            "subtask_id": subtask.id,
                            "description": subtask.description,
                            "success": result.get("ok", False),
                            "result": result
                        })
                    else:
                        subtask.status = "failed"
                        subtask.result = {"ok": False, "detail": f"技能 {subtask.skill} 不存在"}
                        
                        results.append({
                            "subtask_id": subtask.id,
                            "description": subtask.description,
                            "success": False,
                            "result": subtask.result
                        })
                
                except Exception as e:
                    subtask.status = "failed"
                    subtask.result = {"ok": False, "detail": str(e)}
                    
                    results.append({
                        "subtask_id": subtask.id,
                        "description": subtask.description,
                        "success": False,
                        "error": str(e)
                    })
                
                # 通知进度
                if self.on_progress:
                    progress = plan.get_progress()
                    self.on_progress({
                        "type": "subtask_complete",
                        "subtask": subtask,
                        "progress": progress
                    })
        
        # 检查是否全部成功
        all_success = all(st.status == "completed" for st in plan.subtasks)
        completed_count, total_count = plan.get_progress()
        
        return {
            "success": all_success,
            "message": f"任务执行完成: {completed_count}/{total_count}",
            "plan": plan,
            "results": results
        }
