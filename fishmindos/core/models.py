"""
FishMindOS Core - 核心框架
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


class AgentEventType(str, Enum):
    THINK = "think"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TEXT = "text"
    ERROR = "error"
    CANCELED = "canceled"


@dataclass
class AgentEvent:
    """智能体事件"""
    type: AgentEventType
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: dict = field(default_factory=dict)
    text: str = ""
    turn: int = 0


@dataclass  
class InteractionEvent:
    """交互事件"""
    text: str
    source: str
    robot_id: str
    context: dict = field(default_factory=dict)
    event_id: str = ""


@dataclass
class SkillContext:
    """技能执行上下文"""
    user_text: str = ""
    session_data: dict = field(default_factory=dict)
    world_model: Optional[Any] = None
    
    def get(self, key: str, default=None):
        return self.session_data.get(key, default)
    
    def set(self, key: str, value: Any):
        self.session_data[key] = value


@dataclass
class SkillResult:
    """技能执行结果"""
    success: bool
    message: str
    data: Any = None
    
    def to_dict(self) -> dict:
        return {
            "ok": self.success,
            "detail": self.message,
            "data": self.data
        }


@dataclass
class ExecutionEvent:
    """执行事件"""
    task_id: str
    step_id: str
    skill: str
    status: TaskStatus
    detail: str
    data: Any = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
