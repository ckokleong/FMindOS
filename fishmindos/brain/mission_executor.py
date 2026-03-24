"""Small brain mission executor for deterministic action execution."""

from __future__ import annotations

import time
from typing import Any

from fishmindos.adapters.base import RobotAdapter


class MissionExecutor:
    """Execute structured mission JSON independently from LLM reasoning."""

    def __init__(self, adapter: RobotAdapter):
        self.adapter = adapter
        self.last_error: str = ""

    def _fail(self, message: str) -> bool:
        self.last_error = message
        return False

    def _is_dock_target(self, target: Any) -> bool:
        text = str(target or "").lower()
        return any(keyword in text for keyword in ("回充", "充电", "回桩", "dock"))

    def _task_timeout(self, task: dict, default_seconds: int) -> int:
        raw = task.get("timeout") or task.get("timeout_sec") or default_seconds
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default_seconds
        return max(1, value)

    def _wait_for_nav_idle(self, timeout: int) -> bool:
        if not hasattr(self.adapter, "get_navigation_status"):
            return True

        start = time.time()
        saw_running = False
        while time.time() - start < timeout:
            try:
                status = self.adapter.get_navigation_status() or {}
            except Exception:
                status = {}
            nav_running = bool(status.get("nav_running"))
            if nav_running:
                saw_running = True
            if saw_running and not nav_running:
                return True
            time.sleep(1.0)
        return False

    def _wait_after_goto(self, task: dict) -> bool:
        target = task.get("target")

        if self._is_dock_target(target):
            timeout = self._task_timeout(task, default_seconds=600)
            if hasattr(self.adapter, "wait_dock_complete"):
                try:
                    return bool(self.adapter.wait_dock_complete(timeout=timeout))
                except Exception as e:
                    return self._fail(f"wait_dock_complete exception: {e}")
            return self._wait_for_nav_idle(timeout)

        timeout = self._task_timeout(task, default_seconds=300)

        waypoint_id = None
        if hasattr(self.adapter, "get_callback_state"):
            try:
                callback_state = self.adapter.get_callback_state() or {}
            except Exception:
                callback_state = {}
            waypoint_id = callback_state.get("target_waypoint_id")
            if waypoint_id is None:
                waypoint_id = callback_state.get("arrived_waypoint_id")

        if waypoint_id is not None and hasattr(self.adapter, "wait_arrival"):
            try:
                return bool(self.adapter.wait_arrival(int(waypoint_id), timeout=timeout))
            except Exception as e:
                return self._fail(f"wait_arrival exception: {e}")

        return self._wait_for_nav_idle(timeout)

    def _wait_after_dock(self, task: dict) -> bool:
        timeout = self._task_timeout(task, default_seconds=600)
        if hasattr(self.adapter, "wait_dock_complete"):
            try:
                return bool(self.adapter.wait_dock_complete(timeout=timeout))
            except Exception as e:
                return self._fail(f"wait_dock_complete exception: {e}")
        return self._wait_for_nav_idle(timeout)

    def execute_mission(self, tasks: list) -> bool:
        """Execute task list sequentially with fail-fast behavior."""
        if not isinstance(tasks, list):
            return self._fail("tasks must be a list")

        try:
            self.last_error = ""
            needs_movement_prepare = any(
                isinstance(task, dict) and str(task.get("action", "")).lower() in {"goto", "dock"}
                for task in tasks
            )
            if needs_movement_prepare:
                if not self.adapter.prepare_for_movement():
                    return self._fail("prepare_for_movement failed")

            for task in tasks:
                if not isinstance(task, dict):
                    return self._fail("task item is not a dict")

                action = str(task.get("action", "")).lower()

                if action == "goto":
                    target = task.get("target")
                    if not self.adapter.navigate_to(target):
                        return self._fail(f"navigate_to failed: {target}")
                    if not self._wait_after_goto(task):
                        return self._fail(f"wait after goto failed: {target}")
                    continue

                if action == "dock":
                    if not self.adapter.execute_docking():
                        return self._fail("execute_docking failed")
                    if not self._wait_after_dock(task):
                        return self._fail("wait after dock failed")
                    continue

                if action == "light":
                    color = task.get("color")
                    if not self.adapter.set_light(color):
                        return self._fail(f"set_light failed: {color}")
                    continue

                if action == "speak":
                    text = task.get("text")
                    if not self.adapter.play_audio(text):
                        return self._fail(f"play_audio failed: {text}")
                    continue

                if action == "query":
                    status: Any = self.adapter.get_basic_status()
                    print(f"[MissionExecutor] status: {status}")
                    continue

                return self._fail(f"unsupported action: {action}")

            return True
        except Exception as e:
            return self._fail(f"mission exception: {e}")
