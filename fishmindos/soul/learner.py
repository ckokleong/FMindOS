from __future__ import annotations

from datetime import datetime
import re
from typing import Dict, List, Optional

from fishmindos.soul.models import SoulMemory, SoulPreference, SoulRule, SoulState
from fishmindos.soul.store import SoulStore


class Soul:
    """Long-term preference and rule learner for FishMindOS."""

    def __init__(self, store: SoulStore, state: Optional[SoulState] = None):
        self.store = store
        self.state = state or self.store.load()
        self._migrate_legacy_preferences()

    def _migrate_legacy_preferences(self) -> None:
        changed = False
        if "preferred_completion_light" in self.state.preferences:
            self.state.preferences.pop("preferred_completion_light", None)
            changed = True

        if changed:
            self.save()

    @classmethod
    def from_path(cls, path: str, max_memories: int = 200) -> "Soul":
        store = SoulStore(path, max_memories=max_memories)
        return cls(store=store, state=store.load())

    def describe(self) -> str:
        return (
            f"name={self.state.name}, preferences={len(self.state.preferences)}, "
            f"rules={len(self.state.rules)}, memories={len(self.state.memories)}"
        )

    def describe_for_prompt(self, max_rules: int = 5, max_memories: int = 3) -> str:
        lines = [f"当前 Soul: {self.state.name}"]
        if self.state.description:
            lines.append(f"Soul 描述: {self.state.description}")

        if self.state.preferences:
            pref_lines = []
            for pref in list(self.state.preferences.values())[:max_rules]:
                text = f"{pref.key}={pref.value}"
                if pref.notes:
                    text += f"（{pref.notes}）"
                pref_lines.append(text)
            lines.append(f"已学习偏好: {'，'.join(pref_lines)}")

        if self.state.rules:
            rule_lines = []
            for rule in list(self.state.rules.values())[:max_rules]:
                text = rule.rule or rule.name
                if rule.examples:
                    text += f"；示例: {' / '.join(rule.examples[:2])}"
                rule_lines.append(text)
            lines.append(f"已学习规则: {'，'.join(rule_lines)}")

        if self.state.memories:
            memory_lines = [memory.summary for memory in self.state.memories[-max_memories:] if memory.summary]
            if memory_lines:
                lines.append(f"最近学习记录: {'；'.join(memory_lines)}")

        return "\n".join(lines)

    def get_preference(self, key: str, default: str | None = None) -> str | None:
        pref = self.state.preferences.get(key)
        if pref is None:
            return default
        return pref.value

    def add_preference(self, key: str, value: str, notes: str = "", source: str = "learned") -> None:
        existing = self.state.preferences.get(key)
        if existing and existing.value == value:
            existing.confidence += 1
            if notes and notes not in existing.notes:
                existing.notes = f"{existing.notes}；{notes}".strip("；")
            return

        self.state.preferences[key] = SoulPreference(
            key=key,
            value=value,
            confidence=(existing.confidence + 1) if existing else 1,
            source=source,
            notes=notes,
        )

    def add_rule(self, name: str, rule: str, example: str = "", source: str = "learned") -> None:
        existing = self.state.rules.get(name)
        if existing:
            existing.confidence += 1
            if example and example not in existing.examples:
                existing.examples.append(example)
            if rule:
                existing.rule = rule
            return

        self.state.rules[name] = SoulRule(
            name=name,
            rule=rule,
            confidence=1,
            source=source,
            examples=[example] if example else [],
        )

    def add_location_alias(self, alias: str, target: str, notes: str = "") -> None:
        alias = (alias or "").strip()
        target = (target or "").strip()
        if not alias or not target or alias == target:
            return
        self.add_preference(
            f"location_alias:{self._normalize(alias)}",
            target,
            notes=notes or f"{alias} -> {target}",
        )

    def resolve_location_alias(self, alias: str) -> str | None:
        alias = self._normalize(alias)
        if not alias:
            return None
        return self.get_preference(f"location_alias:{alias}")

    def get_location_aliases_for_target(self, target: str) -> List[str]:
        target = (target or "").strip()
        if not target:
            return []

        normalized_target = self._normalize(target)
        aliases: List[str] = []
        for key, pref in self.state.preferences.items():
            if not key.startswith("location_alias:"):
                continue
            if self._normalize(pref.value) != normalized_target:
                continue
            alias = key.split(":", 1)[-1].strip()
            if alias:
                aliases.append(alias)
        return aliases

    def add_memory(self, summary: str, user_input: str = "", tags: Optional[List[str]] = None) -> None:
        if not summary:
            return
        self.state.memories.append(
            SoulMemory(
                summary=summary,
                user_input=user_input,
                learned_at=datetime.now().isoformat(timespec="seconds"),
                tags=list(tags or []),
            )
        )
        self.state.memories = self.state.memories[-self.store.max_memories:]

    def _extract_submit_mission_tasks(self, steps: List[Dict]) -> List[Dict]:
        tasks: List[Dict] = []
        for step in steps:
            if step.get("skill") != "submit_mission":
                continue
            params = step.get("params", {}) or {}
            raw_tasks = params.get("tasks")
            if not isinstance(raw_tasks, list):
                continue
            for task in raw_tasks:
                if isinstance(task, dict):
                    tasks.append(task)
        return tasks

    def _task_action(self, task: Dict) -> str:
        return str(task.get("action", "")).strip().lower()

    def _task_target(self, task: Dict) -> str:
        return str(task.get("target", "")).strip()

    def _collect_locations(self, tasks: List[Dict]) -> List[str]:
        return [
            self._task_target(task)
            for task in tasks
            if self._task_action(task) == "goto" and self._task_target(task)
        ]

    def _has_dock(self, tasks: List[Dict]) -> bool:
        return any(self._task_action(task) == "dock" for task in tasks)

    def _has_audio_after_dock(self, tasks: List[Dict]) -> bool:
        for idx, task in enumerate(tasks):
            if self._task_action(task) != "dock":
                continue
            return any(self._task_action(next_task) == "speak" for next_task in tasks[idx + 1 :])
        return False

    def _learn_location_aliases(self, normalized_input: str, locations: List[str], user_input: str, tags: List[str]) -> None:
        alias_pairs = [
            ("卫生间", "厕所"),
            ("洗手间", "厕所"),
            ("大堂", "大厅"),
            ("门厅", "大厅"),
            ("充电点", "回充点"),
        ]
        for alias, target in alias_pairs:
            if alias in normalized_input and target in locations:
                self.add_location_alias(alias, target, notes=f"用户常把{alias}叫做{target}")
                self.add_rule(
                    f"location_alias:{self._normalize(alias)}",
                    f"{alias} 可视为 {target} 的常用别名。",
                    example=user_input,
                )
                tags.append("alias")

    def learn_from_interaction(
        self,
        user_input: str,
        steps: List[Dict],
        session_context: Optional[Dict] = None,
    ) -> None:
        session_context = session_context or {}
        if not user_input:
            return

        tasks = self._extract_submit_mission_tasks(steps)
        if not tasks:
            return

        normalized_input = re.sub(r"\s+", "", user_input)
        locations = self._collect_locations(tasks)
        has_dock = self._has_dock(tasks)
        has_audio_after_dock = self._has_audio_after_dock(tasks)
        tags: List[str] = []

        if any(keyword in normalized_input for keyword in ("返回", "回来", "回去")) and has_dock:
            self.add_preference(
                "return_behavior",
                "charge",
                notes="用户说“返回/回来/回去”且未明确目标时，优先理解为回充。",
            )
            self.add_rule(
                "implicit_return_target",
                "当用户只说返回/回来而没有明确目标时，默认回到回充点。",
                example=user_input,
            )
            tags.append("return")

        self._learn_location_aliases(normalized_input, locations, user_input, tags)

        if any(keyword in normalized_input for keyword in ("任务完成", "已完成", "完成后")) and has_dock and has_audio_after_dock:
            self.add_preference(
                "post_charge_audio",
                "enabled",
                notes="用户偏好在回充完成后播报任务完成。",
            )
            tags.append("completion_audio")

        summary_parts: List[str] = []
        if "return" in tags:
            summary_parts.append("学到：用户说“返回/回来”通常表示回充。")
        if "alias" in tags:
            summary_parts.append("学到：用户在地点命名上存在稳定别名。")
        if "completion_audio" in tags:
            summary_parts.append("学到：用户偏好回充完成后播报任务完成。")

        if not summary_parts:
            first_location = next((location for location in locations if location), None)
            if first_location:
                summary_parts.append(f"记录：最近执行过与 {first_location} 相关的任务。")
                tags.append("task")

        if summary_parts:
            self.add_memory(" ".join(summary_parts), user_input=user_input, tags=tags)
            self.save()

    def save(self) -> None:
        self.store.save(self.state)

    def _normalize(self, text: str) -> str:
        text = (text or "").strip().lower()
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
