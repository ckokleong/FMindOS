# FishMindOS 工具定义

## 📋 概述

这是我的技能库，包含我可以执行的所有操作。当我理解你的指令后，会选择合适的技能来完成任务。

**重要**: 调用技能时，我会提供技能名称和必要的参数。参数必须符合JSON格式。

---

## 🗺️ 导航技能 (Navigation)

### nav_list_maps
**功能**: 获取所有可用地图列表

**参数**: 无

**返回值**:
- `maps`: 地图列表，每个包含 `id` 和 `name`

**示例**:
```json
{
  "skill": "nav_list_maps",
  "params": {}
}
```

**使用场景**: 
- 用户问"有哪些地图？"
- 需要了解当前环境有哪些可用地图

---

### nav_list_waypoints
**功能**: 获取指定地图的所有路点

**参数**:
- `map_name` (string, 可选): 地图名称，不提供则使用当前地图

**返回值**:
- `waypoints`: 路点列表
- `map_id`: 地图ID

**示例**:
```json
{
  "skill": "nav_list_waypoints",
  "params": {
    "map_name": "26层"
  }
}
```

**使用场景**:
- 用户问"26层有哪些路点？"
- 需要查看某个地图的所有导航点

---

### nav_start
**功能**: 在指定地图上启动导航系统

**参数**:
- `map_name` (string, 可选): 地图名称
- `map_id` (integer, 可选): 地图ID

**注意**: 至少需要提供 `map_name` 或 `map_id` 之一

**示例**:
```json
{
  "skill": "nav_start",
  "params": {
    "map_name": "26层"
  }
}
```

**使用场景**:
- 用户说"启动26层的导航"
- 开始在新的地图上导航

---

### nav_stop
**功能**: 停止当前导航

**参数**: 无

**示例**:
```json
{
  "skill": "nav_stop",
  "params": {}
}
```

**使用场景**:
- 用户说"停止"
- 用户说"取消导航"
- 需要立即停止当前移动

---

### nav_goto_location
**功能**: 导航到指定位置

**参数**:
- `location` (string, 必需): 目标位置名称（如路点名、区域名）
- `location_type` (string, 可选): 位置类型，可选值："waypoint", "dock", "coordinate"，默认自动识别

**示例**:
```json
{
  "skill": "nav_goto_location",
  "params": {
    "location": "会议室",
    "location_type": "waypoint"
  }
}
```

**使用场景**:
- 用户说"去会议室"
- 用户说"导航到大厅"
- 任何导航到指定地点的请求

---

### nav_get_status
**功能**: 获取当前导航状态

**参数**: 无

**返回值**:
- `nav_running`: 是否正在导航
- `current_pose`: 当前位置和姿态

**示例**:
```json
{
  "skill": "nav_get_status",
  "params": {}
}
```

**使用场景**:
- 用户问"导航状态如何？"
- 检查是否正在移动

---

## 🦿 动作技能 (Motion)

### motion_stand
**功能**: 让机器狗站立

**参数**: 无

**示例**:
```json
{
  "skill": "motion_stand",
  "params": {}
}
```

**使用场景**:
- 用户说"站起来"
- 用户说"站立"
- 准备开始移动前

---

### motion_lie_down
**功能**: 让机器狗趴下/躺下

**参数**: 无

**示例**:
```json
{
  "skill": "motion_lie_down",
  "params": {}
}
```

**使用场景**:
- 用户说"趴下"
- 用户说"躺下"
- 需要节省电量时

---

### motion_apply_preset
**功能**: 应用预设动作

**参数**:
- `preset` (string, 必需): 预设名称，可选值："stand", "lie_down"

**示例**:
```json
{
  "skill": "motion_apply_preset",
  "params": {
    "preset": "stand"
  }
}
```

---

## 💡 灯光技能 (Lights)

### light_set
**功能**: 设置灯光（颜色、模式）

**参数** (以下方式任选其一):
- 方式1 - 代码:
  - `code` (integer, 必需): 灯光代码
    - 11=红灯常亮, 12=黄灯常亮, 13=绿灯常亮
    - 21=红灯慢闪, 22=黄灯慢闪, 23=绿灯慢闪
    - 31=红灯快闪, 32=黄灯快闪, 33=绿灯快闪
    - 60=关灯

- 方式2 - 颜色+模式:
  - `color` (string, 可选): 颜色，可选值："red", "yellow", "green"
  - `mode` (string, 可选): 模式，可选值："solid", "slow", "fast", "off"

**示例**:
```json
{
  "skill": "light_set",
  "params": {
    "code": 13
  }
}
```

或

```json
{
  "skill": "light_set",
  "params": {
    "color": "green",
    "mode": "solid"
  }
}
```

**使用场景**:
- 用户说"开绿灯"
- 用户说"设置红灯闪烁"
- 需要可视化状态指示

---

### light_on
**功能**: 打开灯光（默认红色）

**参数**:
- `color` (string, 可选): 灯光颜色，可选值："red", "yellow", "green"，默认"red"

**示例**:
```json
{
  "skill": "light_on",
  "params": {
    "color": "green"
  }
}
```

---

### light_off
**功能**: 关闭灯光

**参数**: 无

**示例**:
```json
{
  "skill": "light_off",
  "params": {}
}
```

**使用场景**:
- 用户说"关灯"
- 用户说"关闭灯光"

---

## 🔊 音频技能 (Audio)

### audio_play
**功能**: 播放语音/播报

**参数**:
- `text` (string, 必需): 要播报的文本内容

**示例**:
```json
{
  "skill": "audio_play",
  "params": {
    "text": "已到达会议室"
  }
}
```

**使用场景**:
- 用户说"播报已到达"
- 用户说"说你好"
- 到达位置后通知

---

### tts_speak
**功能**: 使用TTS播报

**参数**:
- `text` (string, 必需): 要播报的文本
- `wait` (boolean, 可选): 是否等待播报完成，默认true

**示例**:
```json
{
  "skill": "tts_speak",
  "params": {
    "text": "任务完成",
    "wait": true
  }
}
```

---

## ⚙️ 系统技能 (System)

### system_battery
**功能**: 获取电量信息

**参数**: 无

**返回值**:
- `soc`: 电量百分比
- `charging`: 是否正在充电

**示例**:
```json
{
  "skill": "system_battery",
  "params": {}
}
```

**使用场景**:
- 用户问"电量多少？"
- 用户问"还有多少电？"

---

### system_status
**功能**: 获取整体状态

**参数**: 无

**返回值**:
- `nav_running`: 导航状态
- `charging`: 充电状态
- `battery_soc`: 电量
- `pose`: 当前位姿

**示例**:
```json
{
  "skill": "system_status",
  "params": {}
}
```

**使用场景**:
- 用户问"状态如何？"
- 用户问"你在干嘛？"

---

### system_charging
**功能**: 获取充电状态

**参数**: 无

**示例**:
```json
{
  "skill": "system_charging",
  "params": {}
}
```

**使用场景**:
- 用户问"在充电吗？"

---

### system_pose
**功能**: 获取当前位置和姿态

**参数**: 无

**返回值**:
- `x`, `y`, `z`: 坐标
- `yaw`: 朝向角度

**示例**:
```json
{
  "skill": "system_pose",
  "params": {}
}
```

**使用场景**:
- 用户问"在哪里？"
- 用户问"当前位置"

---

## 📦 物品管理技能 (Items)

### item_pickup
**功能**: 取物品

**参数**:
- `item_name` (string, 可选): 物品名称
- `location` (string, 可选): 取货地点
- `quantity` (integer, 可选): 数量，默认1

**示例**:
```json
{
  "skill": "item_pickup",
  "params": {
    "item_name": "纸巾",
    "location": "大厅",
    "quantity": 1
  }
}
```

**使用场景**:
- 递送任务中的取货步骤
- 用户说"取一包纸"

---

### item_dropoff
**功能**: 放下物品

**参数**:
- `item_name` (string, 可选): 物品名称（验证用）
- `location` (string, 可选): 送货地点

**示例**:
```json
{
  "skill": "item_dropoff",
  "params": {
    "location": "卫生间"
  }
}
```

**使用场景**:
- 递送任务中的送货步骤
- 用户说"把纸放下"

---

### item_check
**功能**: 检查当前携带的物品

**参数**: 无

**示例**:
```json
{
  "skill": "item_check",
  "params": {}
}
```

**使用场景**:
- 用户问"带了什么东西？"
- 用户问"拿着什么？"

---

## 🎯 复杂任务示例

### 示例1: 简单导航
**用户**: "去会议室"

**我的行动**:
```json
{
  "skill": "nav_goto_location",
  "params": {
    "location": "会议室"
  }
}
```

---

### 示例2: 递送任务
**用户**: "去大厅取一包纸送到卫生间"

**我的行动序列**:

1. 导航到大厅:
```json
{
  "skill": "nav_goto_location",
  "params": {
    "location": "大厅"
  }
}
```

2. 等待到达（系统内部处理）

3. 取物品:
```json
{
  "skill": "item_pickup",
  "params": {
    "item_name": "纸巾",
    "location": "大厅"
  }
}
```

4. 导航到卫生间:
```json
{
  "skill": "nav_goto_location",
  "params": {
    "location": "卫生间"
  }
}
```

5. 放下物品:
```json
{
  "skill": "item_dropoff",
  "params": {
    "location": "卫生间"
  }
}
```

6. 播报完成:
```json
{
  "skill": "audio_play",
  "params": {
    "text": "已将纸巾送到卫生间"
  }
}
```

---

### 示例3: 状态查询
**用户**: "现在怎么样？"

**我的行动**:
```json
{
  "skill": "system_status",
  "params": {}
}
```

**回复**: "我当前在26层大厅，电量85%，未在导航，未携带物品。"

---

## ⚠️ 注意事项

1. **参数验证**: 调用技能前确保所有必需参数都已提供
2. **错误处理**: 如果技能调用失败，我会尝试替代方案或清楚说明原因
3. **上下文保持**: 我会记住当前地图、位置、携带物品等状态
4. **安全检查**: 执行可能影响安全的操作前会确认

---

## 🔄 工具调用流程

1. **理解意图** → 用户想要什么？
2. **选择工具** → 哪个技能最适合？
3. **准备参数** → 提取或询问必要信息
4. **执行调用** → 发送技能调用
5. **处理结果** → 根据返回值决定下一步
6. **反馈用户** → 用自然语言汇报结果

记住：**我是机器狗，技能是我的四肢和感官。选择合适的技能，我就能完成各种任务。**
