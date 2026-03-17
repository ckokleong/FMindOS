# FishMindOS 架构描述（v1.0）

本文档用于技术团队协作开发，定义 FishMindOS 的系统边界、核心模块、数据结构与工程拆分建议。

## 1. 系统边界

FishMindOS 位于“用户输入”和“机器人硬件”之间，承担任务理解、规划、编排、执行与反馈。

- 上游：语音系统、IM、Web、外部 API
- 下游：ROS2 导航、机械臂、IoT 控制器、传感器

## 2. 分层设计

### 2.1 Interaction Layer

**输入适配器**：
- VoiceAdapter（ASR/NLU 前处理）
- TextAdapter（命令行/IM）
- HttpAdapter（第三方系统接入）

**统一输入对象 `InteractionEvent`**：

```json
{
  "event_id": "evt_20260317_001",
  "timestamp": "2026-03-17T12:00:00Z",
  "source": "voice",
  "robot_id": "dog-01",
  "text": "到行政拿纸巾送到厕所",
  "context": {
    "user_id": "u_001",
    "session_id": "s_abc"
  }
}
```

### 2.2 Agent Core

#### Intent Parser
输出 `Intent`：

```json
{
  "task_type": "delivery",
  "pickup_location": "行政",
  "dropoff_location": "厕所",
  "item": "纸巾",
  "priority": "normal"
}
```

#### Task Planner
输入：Intent + World Model + Skill Registry + Policy
输出：`TaskPlan`

#### Dialogue Generator
为关键步骤生成场景话术（取件提醒、到达提醒、失败解释）。

#### Memory
- Short-term：当前会话上下文
- Episodic：历史任务轨迹
- Semantic：偏好、常用点位映射

### 2.3 World Model

数据域：
- `locations`：点位名称、坐标、类型
- `relations`：邻接、包含、可达性
- `entities`：人员、物体、设备
- `state`：占用状态、临时封闭、拥堵等级

对外查询接口：
- `get_location(name)`
- `resolve_alias(alias)`
- `find_nearest(type, from)`
- `is_reachable(from, to)`

### 2.4 Skill Runtime

**技能注册中心** `SkillRegistry`：
- 技能发现
- 参数校验
- 版本管理

**插件技能系统** `SkillOS`：
- 运行时加载 `skill_store/*.py` 技能脚本
- 将新技能由 OS 生成脚本并持久化
- 重启后自动复用
- 插件加载失败自动隔离（跳过故障插件）

**标准技能协议**：

```python
class Skill:
    name: str
    version: str
    input_schema: dict
    output_schema: dict

    def run(self, args: dict, context: dict) -> dict:
        ...
```

### 2.5 Execution Runtime

核心组件：
- `TaskExecutor`：步骤执行与状态推进
- `StateMachine`：任务生命周期管理
- `RetryPolicy`：超时/失败重试策略
- `Observer`：执行事件上报

任务状态：

```text
pending -> running -> success
                  └-> failed
                  └-> canceled
```

## 3. 关键数据结构

### 3.1 TaskPlan

```json
{
  "task_id": "task_20260317_001",
  "goal": "配送卫生纸",
  "constraints": {
    "deadline": null,
    "safety_level": "normal"
  },
  "steps": [
    {
      "id": "step_1",
      "skill": "navigate_to",
      "args": {"location": "行政"}
    },
    {
      "id": "step_2",
      "skill": "speak_text",
      "args": {"text": "您好，我来领取一包卫生纸，请帮我放到我的载物区。"}
    }
  ]
}
```

### 3.2 ExecutionEvent

```json
{
  "task_id": "task_20260317_001",
  "step_id": "step_1",
  "status": "running",
  "timestamp": "2026-03-17T12:01:00Z",
  "detail": "navigating to 行政"
}
```

## 4. 工程目录建议

```text
fishmindos/
  interaction/
  agent_core/
    intent/
    planner/
    dialogue/
    memory/
  world_model/
  skill_runtime/
    skills/
  execution_runtime/
  adapters/
    ros2/
  api/
  tests/
```

## 5. 开发优先级

P0：
1. Planner Schema + Mock Planner
2. Skill 接口 + 6 个基础技能
3. 执行状态机（单任务串行）

P1：
1. World Model 别名解析与可达性校验
2. Memory 任务复盘
3. Web 可视化任务看板

P2：
1. 多机器人调度
2. 策略学习与任务优化
3. 跨场景迁移工具
