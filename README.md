# FishMindOS

> **FishMindOS = 一个以大模型为认知核心、以语义地图为世界模型、以技能系统为执行接口的机器人智能体操作系统。**

一句话目标：

> **让机器人理解任务，而不是仅执行命令。**

---

## 1. 项目定位

FishMindOS 面向真实机器人场景，支持从语音/文本输入任务，到自动规划、执行并反馈结果的完整闭环。

核心能力：

- 自然语言任务理解（Intent Parsing）
- 多步骤任务规划（Task Planning）
- 语义地图世界建模（World Model）
- 标准化技能执行（Skill Runtime）
- 可观测、可恢复的调度执行（Execution Runtime）

---

## 2. 总体架构

```text
┌──────────────────────────────────────────────┐
│               Interaction Layer              │
│   语音 / 文本 / API / Web / 飞书 / App       │
└──────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────┐
│               Agent Core（大脑）             │
│  Intent / Planner / Dialogue / Memory        │
└──────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────┐
│            World Model（世界模型）            │
│  地图 / 点位 / 语义 / 关系 / 状态             │
└──────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────┐
│           Skill Runtime（技能层）             │
│  Nav / Speak / Wait / Inspect / Arm / IoT    │
└──────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────┐
│         Execution Runtime（执行调度）         │
│  Task Executor / State Machine / Scheduler   │
└──────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────┐
│          Robot System（ROS2 / 硬件）         │
└──────────────────────────────────────────────┘
```

---

## 3. 与 OpenClaw 的核心差异

OpenClaw 典型路径：

```text
LLM → Tool → 执行
```

FishMindOS 路径：

```text
LLM → 任务理解 → 世界模型 → 任务规划 → 技能链 → 执行
```

关键增强层：

- **Task Brain**：任务分解与隐式步骤补全
- **World Model**：语言到空间的 grounding
- **Execution Runtime**：可恢复状态机执行

---

## 4. 五大模块职责

### 4.1 Interaction Layer

统一输入通道（语音/文本/API/IM），标准化输入结构：

```json
{
  "text": "到行政拿纸巾送到厕所",
  "source": "voice",
  "robot_id": "dog-01"
}
```

### 4.2 Agent Core

- Intent Parser：抽取任务类型、地点、物品、动作
- Task Planner：基于世界模型与技能集生成执行计划
- Dialogue Generator：自动生成场景话术
- Memory：会话、任务、用户偏好与空间记忆

### 4.3 World Model

维护空间与语义关系，提供查询 API：

- `get_location(name)`
- `find_nearest(type)`
- `get_neighbors(location)`
- `is_valid_location(name)`

### 4.4 Skill Runtime

统一技能接口：

```python
class Skill:
    name: str
    input_schema: dict
    def run(args) -> result
```

首批技能建议：

- `navigate_to`
- `speak_text`
- `wait_for_item`
- `query_status`
- `inspect_area`
- `go_home`

### 4.5 Execution Runtime

任务调度与状态管理：

```text
pending → running → success / failed / cancel
```

支持：

- 步骤级重试
- 异常分级处理
- 中断恢复
- 全链路日志

---

## 5. 运行闭环（Think → Plan → Act → Observe）

以“到行政拿纸巾送到厕所”为例：

1. Interaction 接收语音并 ASR
2. Agent Core 解析意图
3. Planner 生成任务步骤
4. World Model 校验地点和可行性
5. Dialogue 生成话术
6. Execution Runtime 逐步调度技能
7. ROS2 执行并上报状态
8. Agent 更新任务记忆并反馈用户

---

## 6. 里程碑建议（v0.1）

1. 定义 Planner 输出 JSON Schema
2. 定义 Skill 接口与注册机制
3. 打通一句话到执行闭环 Demo

可参考文档：

- 架构描述：[`ARCHITECTURE.md`](./ARCHITECTURE.md)
- 任务描述规范：[`TASK_SPEC.md`](./TASK_SPEC.md)

---

## 7. 愿景

FishMindOS 不是单一机器人的脚本集合，而是机器人团队可复用的“智能体操作系统”，用于持续沉淀任务策略、地图知识与跨设备技能生态。

---

## 8. Python 初版框架（可运行）

已提供基础代码骨架（目录 `fishmindos/`）：

- `interaction`：输入适配
- `agent_core`：意图解析、规划、话术、记忆
- `world_model`：点位建模与查询
- `skill_runtime`：技能协议、注册中心、内置技能 + 插件技能加载（SkillOS）
- `execution_runtime`：任务执行器
- `main.py`：最小可运行 Demo

运行示例：

```bash
python3 main.py
```

插件化机制（新增）：

- `SkillOS` 可把技能生成为独立 Python 脚本并持久化到 `skill_store/`
- 系统启动时自动扫描并加载脚本技能（插件）
- 生成后的技能可跨重启复用，不需要再次手写注册

