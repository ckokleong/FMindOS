# FishMindOS Agent 文档体系

本目录同时包含两层文档：

- 框架默认文档：`docs/*.md`
- 项目实例文档：`docs/profiles/<profile_name>/*.md`

运行时加载顺序为：

1. 先读取 `docs/` 下的框架默认文档
2. 如果配置了 `app.prompt_profile`，再读取 `docs/profiles/<profile_name>/`
3. 同名文档由 profile 覆盖默认文档

这意味着：

- 框架默认文档应保持通用，不绑定某个具体机器人名字
- 项目实例文档只放当前项目的人设、身份、表达风格等特化内容

当前仓库内置的实例 profile 为：

- `xiaohuan`

## 目录建议

```text
docs/
├─ prompt.md
├─ identity.md
├─ agent.md
├─ tools.md
├─ Soul.md
└─ profiles/
   └─ xiaohuan/
      ├─ identity.md
      └─ agent.md
```

## 新建一个项目实例

1. 在 `docs/profiles/<你的profile名>/` 下创建需要覆盖的文档
2. 在配置文件里设置：

```json
{
  "app": {
    "identity": "你的角色名",
    "prompt_profile": "你的profile名"
  }
}
```

3. 重启 `python -m fishmindos`

如果某个 profile 下没有对应文档，系统会自动回退到 `docs/` 下的框架默认文档。
