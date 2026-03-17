from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from fishmindos.skill_runtime.base import Skill
from fishmindos.skill_runtime.registry import SkillRegistry


class ScriptSkill(Skill):
    """从磁盘脚本动态加载的插件技能。"""

    def __init__(self, name: str, run_callable):
        self.name = name
        self._run_callable = run_callable

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return self._run_callable(args, context)


class SkillOS:
    """技能操作系统：负责技能脚本生成、存储、加载。"""

    def __init__(self, skills_dir: str | Path = "skill_store") -> None:
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def load_plugins(self, registry: SkillRegistry) -> list[str]:
        loaded: list[str] = []
        for script in sorted(self.skills_dir.glob("*.py")):
            spec = importlib.util.spec_from_file_location(f"fishmindos_plugin_{script.stem}", script)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            run_callable = getattr(module, "run", None)
            if run_callable is None:
                continue

            name = getattr(module, "SKILL_NAME", script.stem)
            registry.register(ScriptSkill(name=name, run_callable=run_callable))
            loaded.append(name)
        return loaded

    def generate_skill_script(self, name: str, script_body: str, description: str = "") -> Path:
        """由 OS 生成技能脚本，并持久化到本地供后续复用。"""
        safe_name = name.strip().replace(" ", "_")
        target = self.skills_dir / f"{safe_name}.py"

        content = f'''"""Auto-generated FishMindOS skill script."""
SKILL_NAME = "{safe_name}"
DESCRIPTION = {description!r}


def run(args, context):
{script_body}
'''
        target.write_text(content, encoding="utf-8")

        manifest = self.skills_dir / "skills_manifest.json"
        data: dict[str, Any] = {"skills": []}
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
        skill_names = {item["name"] for item in data.get("skills", [])}
        if safe_name not in skill_names:
            data.setdefault("skills", []).append({"name": safe_name, "file": target.name, "description": description})
            manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return target
