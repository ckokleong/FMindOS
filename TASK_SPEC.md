# FishMindOS 任务描述文件规范（Task Spec v1.0）

本规范用于产品、算法、后端、机器人控制同学协作定义任务，作为 Planner 与 Execution Runtime 的契约。

## 1. 目标

任务描述文件用于：
- 把业务目标转化为可执行任务
- 统一任务输入、计划输出、执行反馈格式
- 支持测试回放与问题定位

## 2. 任务文件结构

```json
{
  "task_meta": {},
  "intent": {},
  "world_context": {},
  "plan": {},
  "dialogue": {},
  "execution_policy": {}
}
```

## 3. 字段定义

### 3.1 `task_meta`

```json
{
  "task_id": "task_20260317_001",
  "created_at": "2026-03-17T12:00:00Z",
  "source": "voice",
  "robot_id": "dog-01",
  "priority": "normal"
}
```

### 3.2 `intent`

```json
{
  "raw_text": "到行政拿纸巾送到厕所",
  "task_type": "delivery",
  "entities": {
    "item": "纸巾",
    "pickup": "行政",
    "dropoff": "厕所"
  }
}
```

### 3.3 `world_context`

```json
{
  "pickup_location": {
    "name": "行政",
    "pose": [1.2, 3.4, 1.57],
    "reachable": true
  },
  "dropoff_location": {
    "name": "厕所",
    "pose": [8.1, 2.0, 0.0],
    "reachable": true
  }
}
```

### 3.4 `plan`

```json
{
  "goal": "配送卫生纸",
  "steps": [
    {
      "id": "s1",
      "skill": "navigate_to",
      "args": {"location": "行政"},
      "on_fail": "retry"
    },
    {
      "id": "s2",
      "skill": "speak_text",
      "args": {"text": "您好，我来领取一包卫生纸，请帮我放到我的载物区。"},
      "on_fail": "continue"
    },
    {
      "id": "s3",
      "skill": "wait_for_item",
      "args": {"timeout_sec": 60},
      "on_fail": "abort"
    },
    {
      "id": "s4",
      "skill": "navigate_to",
      "args": {"location": "厕所"},
      "on_fail": "retry"
    },
    {
      "id": "s5",
      "skill": "speak_text",
      "args": {"text": "您好，您需要的卫生纸已送到，请及时取用。"},
      "on_fail": "continue"
    }
  ]
}
```

### 3.5 `dialogue`

```json
{
  "pickup_script": "您好，我来领取一包卫生纸，请帮我放到我的载物区。",
  "dropoff_script": "您好，您需要的卫生纸已送到，请及时取用。",
  "failure_script": "抱歉，本次任务执行失败，我将返回待命点并上报。"
}
```

### 3.6 `execution_policy`

```json
{
  "max_retry_per_step": 2,
  "task_timeout_sec": 900,
  "fallback_skill": "go_home",
  "report_interval_sec": 3
}
```

## 4. 最小可用规范（MVP）

v0.1 必填字段：
- `task_meta.task_id`
- `intent.raw_text`
- `plan.steps[]`
- `execution_policy.max_retry_per_step`

## 5. 开发协作建议

- 产品同学：负责典型任务模板定义
- 算法同学：负责 Intent + Planner 输出质量
- 后端同学：负责任务存储与状态 API
- 机器人同学：负责 skill 适配与执行回传

## 6. 验收清单

每个任务模板提交前应满足：
- 可解析（JSON Schema 校验通过）
- 可执行（技能均已注册）
- 可回放（ExecutionEvent 完整）
- 可恢复（中断后可继续或安全退出）
