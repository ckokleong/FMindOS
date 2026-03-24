# World Layer

`world` 用来保存语义地图，而不是底层导航原始地图。

目标：

- 让用户可以直接说 `去大厅`、`去厕所`、`回充`
- 技能层先从语义地图里解析地点属于哪张地图、对应哪个路点
- 如果当前地图不对，再自动切图并继续导航

## 文件

- `semantic_map.json`
  世界语义地图配置
- `models.py`
  语义地图和解析结果的数据结构
- `store.py`
  负责加载和保存 `semantic_map.json`
- `resolver.py`
  负责把自然语言地点解析成 `map + waypoint`

## semantic_map.json 结构

```json
{
  "default_map_name": "26层",
  "maps": [
    {
      "name": "26层",
      "map_id": 51,
      "aliases": ["26F", "26楼"]
    }
  ],
  "locations": [
    {
      "name": "大厅",
      "map_name": "26层",
      "waypoint_name": "大厅",
      "aliases": ["大堂", "前厅"],
      "location_type": "waypoint",
      "category": "reception",
      "description": "26层主要接待区域，适合会合、送物、播报。",
      "task_hints": ["接待", "会合", "播报"],
      "relations": [{"type": "after_task_return", "target": "回充点"}]
    },
    {
      "name": "回充点",
      "map_name": "26层",
      "waypoint_name": "回充点",
      "aliases": ["充电点", "回充", "回桩"],
      "location_type": "dock",
      "category": "charging",
      "description": "机器人任务结束后返回充电的位置。",
      "task_hints": ["返回充电", "等待回充完成"]
    }
  ]
}
```

## 使用建议

- 先把高频地点写进去，比如 `大厅`、`会议室`、`厕所`、`回充点`
- 每个地点尽量补 `aliases`
- 尽量补 `description`、`category`、`task_hints`
- `relations` 用来表达“任务结束后回哪儿”“和哪个点同路线/可衔接”
- 如果一个地点在多张地图都存在，最好显式写 `map_name` 或 `map_id`

## 当前行为

即使 `semantic_map.json` 还是空的，系统也会尝试：

1. 先查语义地图
2. 再用适配器全局扫描所有地图和路点

这样你可以先跑起来，再慢慢把常用地点补完整。
