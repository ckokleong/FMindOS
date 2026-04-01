"""Non-blocking mission state machine driven by EventBus."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from fishmindos.adapters.base import RobotAdapter
from fishmindos.config import get_config
from fishmindos.core.event_bus import global_event_bus as default_event_bus


class MissionManager:
    """Event-driven mission manager."""

    def __init__(self, adapter: RobotAdapter, global_event_bus=default_event_bus):
        self.adapter = adapter
        self.event_bus = global_event_bus
        self.current_mission_queue: List[Dict[str, Any]] = []
        self.is_busy = False
        self.waiting_for_human = False
        self.last_error: str = ""
        self._lock = threading.RLock()
        self._wait_reminder_thread: Optional[threading.Thread] = None
        self._wait_reminder_stop = threading.Event()
        self._last_speak_text: str = ""
        self._active_wait_confirm_text: str = ""
        self._active_wait_confirm_meta: Dict[str, Any] = {}
        self._active_target: str = ""
        self._awaiting_event: Optional[str] = None
        self._session_state: Optional[Dict[str, Any]] = None
        self._mission_steps: List[Dict[str, Any]] = []
        self._mission_step_statuses: List[str] = []
        self._current_task: Optional[Dict[str, Any]] = None
        self._current_step_index: int = -1

        cfg = get_config()
        self._wait_reminder_enabled = bool(getattr(cfg.mission, "wait_confirm_reminder_enabled", True))
        self._wait_reminder_interval_sec = max(
            1,
            int(getattr(cfg.mission, "wait_confirm_reminder_interval_sec", 20) or 20),
        )
        self._wait_reminder_text = str(
            getattr(cfg.mission, "wait_confirm_reminder_text", "请确认后我再继续执行。")
            or "请确认后我再继续执行。"
        )

        self.event_bus.subscribe("nav_arrived", self._on_nav_arrived)
        self.event_bus.subscribe("dock_completed", self._on_dock_completed)
        self.event_bus.subscribe("action_failed", self._on_action_failed)
        self.event_bus.subscribe("human_confirmed", self._on_human_confirmed)

    def _log(self, message: str) -> None:
        print(f"\n{message}", flush=True)

    def _get_session_id(self) -> Optional[str]:
        if isinstance(self._session_state, dict):
            session_id = self._session_state.get("session_id")
            if session_id:
                return str(session_id)
        return None

    def _task_label(self, task: Optional[Dict[str, Any]]) -> str:
        if not isinstance(task, dict):
            return "执行任务"
        action = str(task.get("action", "") or "").lower()
        if action == "goto":
            return f"前往 {task.get('target') or '目标点'}"
        if action == "dock":
            return "回充"
        if action == "wait_confirm":
            return "等待人工确认"
        if action == "speak":
            text = str(task.get("text", "") or "").strip()
            if len(text) > 24:
                text = text[:21] + "..."
            return f"播报：{text or '提示语'}"
        if action == "query":
            return "查询状态"
        if action == "light":
            color = str(task.get("color") or task.get("code") or "").strip()
            return f"灯光 {color}" if color else "调整灯光"
        if action == "stop_nav":
            return "停止导航"
        if action == "stand":
            return "站起来"
        if action in ("lie_down", "lie"):
            return "趴下"
        return action or "执行任务"

    def _publish_progress(
        self,
        status: str,
        *,
        task: Optional[Dict[str, Any]] = None,
        step_index: Optional[int] = None,
        message: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        with self._lock:
            progress_task = dict(task) if isinstance(task, dict) else (dict(self._current_task) if isinstance(self._current_task, dict) else None)
            current_index = self._current_step_index if step_index is None else step_index
            total_steps = len(self._mission_steps)

        payload: Dict[str, Any] = {
            "session_id": self._get_session_id(),
            "status": status,
            "step_index": current_index,
            "step_number": current_index + 1 if isinstance(current_index, int) and current_index >= 0 else None,
            "total_steps": total_steps,
            "label": self._task_label(progress_task),
        }
        if isinstance(progress_task, dict):
            payload["action"] = str(progress_task.get("action", "") or "").lower()
        if message:
            payload["message"] = str(message)
        if detail:
            payload["detail"] = str(detail)
        self._remember_progress_snapshot(
            status,
            task=progress_task,
            step_index=current_index,
            message=message,
            detail=detail,
            label=payload["label"],
        )
        self.event_bus.publish("mission_progress", payload)

    def bind_session_state(self, session_state: Optional[Dict[str, Any]]) -> None:
        self._session_state = session_state if isinstance(session_state, dict) else None
        self._sync_session_mission_snapshot()

    def _set_session_value(self, key: str, value: Any) -> None:
        if isinstance(self._session_state, dict):
            self._session_state[key] = value

    def _sync_session_mission_snapshot(self) -> None:
        with self._lock:
            tasks = [dict(task) if isinstance(task, dict) else {"action": str(task)} for task in self._mission_steps]
            statuses = list(self._mission_step_statuses)
            current_step_index = self._current_step_index if self._current_step_index >= 0 else None
        self._set_session_value("mission_tasks", tasks)
        self._set_session_value("mission_step_statuses", statuses)
        self._set_session_value("mission_current_step_index", current_step_index)

    def _clear_session_mission_snapshot(self) -> None:
        with self._lock:
            self._mission_steps = []
            self._mission_step_statuses = []
            self._current_task = None
            self._current_step_index = -1
        self._set_session_value("mission_tasks", [])
        self._set_session_value("mission_step_statuses", [])
        self._set_session_value("mission_current_step_index", None)
        self._set_session_value("mission_progress_status", None)
        self._set_session_value("mission_progress_message", None)
        self._set_session_value("mission_progress_detail", None)
        self._set_session_value("mission_progress_label", None)

    def _remember_progress_snapshot(
        self,
        status: str,
        *,
        task: Optional[Dict[str, Any]] = None,
        step_index: Optional[int] = None,
        message: Optional[str] = None,
        detail: Optional[str] = None,
        label: Optional[str] = None,
    ) -> None:
        with self._lock:
            if status == "all_completed":
                self._mission_step_statuses = [
                    "failed" if current == "failed" else "done"
                    for current in self._mission_step_statuses
                ]
                self._current_step_index = -1
            elif isinstance(step_index, int) and 0 <= step_index < len(self._mission_step_statuses):
                for index in range(step_index):
                    if self._mission_step_statuses[index] in {"pending", "running", "waiting"}:
                        self._mission_step_statuses[index] = "done"
                mapped_status = "done" if status == "completed" else status
                self._mission_step_statuses[step_index] = mapped_status
                self._current_step_index = step_index if mapped_status in {"running", "waiting", "failed"} else -1

            if self._mission_steps and len(self._mission_step_statuses) < len(self._mission_steps):
                self._mission_step_statuses.extend(
                    ["pending"] * (len(self._mission_steps) - len(self._mission_step_statuses))
                )

            tasks = [dict(item) if isinstance(item, dict) else {"action": str(item)} for item in self._mission_steps]
            statuses = list(self._mission_step_statuses)
            current_step_index = self._current_step_index if self._current_step_index >= 0 else None

        task_label = label or self._task_label(task)
        self._set_session_value("mission_tasks", tasks)
        self._set_session_value("mission_step_statuses", statuses)
        self._set_session_value("mission_current_step_index", current_step_index)
        self._set_session_value("mission_progress_status", status)
        self._set_session_value("mission_progress_message", message)
        self._set_session_value("mission_progress_detail", detail)
        self._set_session_value("mission_progress_label", task_label)

    def _get_session_list(self, key: str) -> List[str]:
        if not isinstance(self._session_state, dict):
            return []
        value = self._session_state.get(key)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _sync_carrying_state(self, items: List[str]) -> None:
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        self._set_session_value("carrying_items", cleaned)
        if cleaned:
            self._set_session_value("carrying_item", "、".join(cleaned))
        else:
            self._set_session_value("carrying_item", None)

    def _event_stream_ready(self) -> bool:
        checker = getattr(self.adapter, "_event_stream_enabled", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                return False
        return True

    def submit_mission(self, tasks: list) -> bool:
        """Accept mission tasks and trigger execution if idle."""
        if not isinstance(tasks, list):
            self.last_error = "tasks must be a list"
            return False

        with self._lock:
            if self.is_busy:
                self.current_mission_queue.extend(tasks)
                return True
            self.current_mission_queue = list(tasks)
            self._mission_steps = [dict(task) if isinstance(task, dict) else {"action": str(task)} for task in tasks]
            self._mission_step_statuses = ["pending"] * len(self._mission_steps)
            self.is_busy = True
            self.waiting_for_human = False
            self.last_error = ""
            self._last_speak_text = ""
            self._active_wait_confirm_text = ""
            self._active_wait_confirm_meta = {}
            self._active_target = ""
            self._awaiting_event = None
            self._current_task = None
            self._current_step_index = -1
            self._set_session_value("mission_progress_status", "pending")
            self._set_session_value("mission_progress_message", None)
            self._set_session_value("mission_progress_detail", None)
            self._set_session_value("mission_progress_label", None)
            self._sync_session_mission_snapshot()
            self._stop_wait_confirm_reminder()

        self._execute_next()
        return True

    def has_pending_work(self) -> bool:
        """Whether the current mission still has unfinished async or queued work."""
        with self._lock:
            return bool(
                self.is_busy
                or self.waiting_for_human
                or self.current_mission_queue
                or bool(self._awaiting_event)
            )

    def cancel_current(self, reason: str = "mission cancelled") -> bool:
        """Force-clear the current async mission and reset session wait state."""
        with self._lock:
            had_pending = bool(
                self.is_busy
                or self.waiting_for_human
                or self.current_mission_queue
                or bool(self._awaiting_event)
            )
            if not had_pending:
                return False

            self.is_busy = False
            self.waiting_for_human = False
            self.current_mission_queue = []
            self.last_error = reason
            self._last_speak_text = ""
            self._active_wait_confirm_text = ""
            self._active_wait_confirm_meta = {}
            self._active_target = ""
            self._awaiting_event = None

        self._set_session_value("waiting_for_human", False)
        self._set_session_value("human_prompt_text", None)
        self._stop_wait_confirm_reminder()

        stop_nav = getattr(self.adapter, "stop_navigation", None)
        if callable(stop_nav):
            try:
                stop_nav()
            except Exception:
                pass

        self._publish_progress("failed", message="任务已取消", detail=reason)
        self._log(f"[小脑] 任务取消: {reason}")
        self._clear_session_mission_snapshot()
        self.event_bus.publish("mission_failed", {"error": reason, "detail": {"cancelled": True}})
        return True

    def _execute_next(self, event_data=None):
        """Dispatch next action without blocking waits."""
        with self._lock:
            if not self.is_busy:
                return
            if self.waiting_for_human:
                return
            if not self.current_mission_queue:
                self.is_busy = False
                self.waiting_for_human = False
                self._awaiting_event = None
                self._stop_wait_confirm_reminder()
                self._current_task = None
                self._current_step_index = -1
                try:
                    self.adapter.play_audio("任务全部完成")
                except Exception:
                    pass
                self._log("[小脑] 任务全部完成")
                self._publish_progress("all_completed", message="任务全部完成")
                self._clear_session_mission_snapshot()
                self.event_bus.publish("mission_completed", {"status": "completed"})
                return
            step_index = len(self._mission_steps) - len(self.current_mission_queue)
            task = self.current_mission_queue.pop(0)
            self._current_task = dict(task) if isinstance(task, dict) else {"action": str(task)}
            self._current_step_index = step_index

        if not isinstance(task, dict):
            self._on_action_failed({"error": "task item is not a dict"})
            return

        action = str(task.get("action", "")).lower()

        if action == "goto":
            target = task.get("target")
            try:
                ok = bool(self.adapter.navigate_to(target))
            except Exception as exc:
                ok = False
                self.last_error = f"goto failed: {exc}"
            if not ok:
                self.event_bus.publish("action_failed", {"action": "goto", "target": target})
                return
            if not self._event_stream_ready():
                self.last_error = "event stream unavailable for goto"
                self.event_bus.publish("action_failed", {"action": "goto", "target": target, "error": self.last_error})
                return
            with self._lock:
                self._awaiting_event = "nav_arrived"
                self._active_target = str(target or "").strip()
            self._publish_progress("running", task=task, step_index=step_index, message=f"正在前往 {target}")
            self._log(f"[小脑] 已下发前往 {target}，等待到达回调...")
            return

        if action == "dock":
            try:
                if hasattr(self.adapter, "execute_docking_async"):
                    ok = bool(self.adapter.execute_docking_async())
                else:
                    ok = bool(self.adapter.execute_docking())
            except Exception as exc:
                ok = False
                self.last_error = f"dock failed: {exc}"
            if not ok:
                self.event_bus.publish("action_failed", {"action": "dock"})
                return
            if not self._event_stream_ready():
                self.last_error = "event stream unavailable for dock"
                self.event_bus.publish("action_failed", {"action": "dock", "error": self.last_error})
                return
            with self._lock:
                self._awaiting_event = "dock_completed"
                self._active_target = "回充点"
            self._publish_progress("running", task=task, step_index=step_index, message="正在回充")
            self._log("[小脑] 已下发回充，等待回充完成回调...")
            return

        if action == "stop_nav":
            try:
                ok = bool(self.adapter.stop_navigation())
            except Exception as exc:
                ok = False
                self.last_error = f"stop_nav failed: {exc}"
            if not ok:
                self.event_bus.publish("action_failed", {"action": "stop_nav"})
                return
            self._publish_progress("completed", task=task, step_index=step_index, message="已停止导航")
            self._log("[Mission] navigation stopped")
            self._execute_next()
            return

        if action == "wait_confirm":
            reminder_text = str(task.get("reminder_text") or "").strip()
            if not reminder_text:
                reminder_text = str(self._last_speak_text or "").strip()
            if not reminder_text:
                reminder_text = self._wait_reminder_text
            with self._lock:
                self.waiting_for_human = True
                self._active_wait_confirm_text = reminder_text
                self._active_wait_confirm_meta = dict(task)
                self._awaiting_event = "human_confirmed"
            self._set_session_value("waiting_for_human", True)
            self._set_session_value("human_prompt_text", reminder_text)
            self.event_bus.publish(
                "human_confirm_required",
                {
                    "session_id": self._session_state.get("session_id") if isinstance(self._session_state, dict) else None,
                    "message": reminder_text,
                },
            )
            self._publish_progress("waiting", task=task, step_index=step_index, message="等待现场确认", detail=reminder_text)
            self._start_wait_confirm_reminder(reminder_text)
            self._log("[小脑] 进入人机协同等待状态，悬停中...")
            return

        if action == "light":
            try:
                ok = bool(self.adapter.set_light(task.get("color")))
            except Exception as exc:
                ok = False
                self.last_error = f"light failed: {exc}"
            if not ok:
                self.event_bus.publish("action_failed", {"action": "light"})
                return
            self._publish_progress("completed", task=task, step_index=step_index, message="灯光动作已完成")
            self._execute_next()
            return

        if action == "speak":
            text = task.get("text")
            is_async = bool(task.get("async", False))
            if is_async:
                # 异步播放：后台线程播音，同时立即执行下一步
                def _play():
                    try:
                        self.adapter.play_audio(text)
                    except Exception:
                        pass
                threading.Thread(target=_play, daemon=True, name="speak-async").start()
                self._last_speak_text = str(text or "").strip()
                self._publish_progress("completed", task=task, step_index=step_index, message="播报（异步）")
                self._execute_next()
                return
            try:
                ok = bool(self.adapter.play_audio(text))
            except Exception as exc:
                ok = False
                self.last_error = f"speak failed: {exc}"
            if not ok:
                self.event_bus.publish("action_failed", {"action": "speak"})
                return
            self._last_speak_text = str(text or "").strip()
            self._publish_progress("completed", task=task, step_index=step_index, message="播报已完成")
            self._execute_next()
            return

        if action == "query":
            try:
                status = self.adapter.get_basic_status()
                self._log(f"[小脑] status={status}")
            except Exception as exc:
                self.event_bus.publish("action_failed", {"action": "query", "error": str(exc)})
                return
            self._publish_progress("completed", task=task, step_index=step_index, message="状态查询已完成")
            self._execute_next()
            return

        if action in ("stand", "lie_down", "lie"):
            method_name = "motion_stand" if action == "stand" else "motion_lie_down"
            method = getattr(self.adapter, method_name, None)
            if not callable(method):
                self.event_bus.publish("action_failed", {"action": action, "error": f"{method_name} not supported by adapter"})
                return
            try:
                ok = bool(method())
            except Exception as exc:
                ok = False
                self.last_error = f"{action} failed: {exc}"
            if not ok:
                self.event_bus.publish("action_failed", {"action": action})
                return
            label = "站立完成" if action == "stand" else "趴下完成"
            self._publish_progress("completed", task=task, step_index=step_index, message=label)
            self._execute_next()
            return

        self.event_bus.publish("action_failed", {"action": action, "error": "unsupported action"})

    def _on_nav_arrived(self, data):
        with self._lock:
            if not self.is_busy or self.waiting_for_human or self._awaiting_event != "nav_arrived":
                return
            arrived_target = ""
            if isinstance(data, dict):
                arrived_target = str(data.get("target") or data.get("location") or "").strip()
            arrived_target = arrived_target or self._active_target
            self._awaiting_event = None
            self._active_target = ""
        if arrived_target:
            self._set_session_value("current_location", arrived_target)
        self._publish_progress("completed", message=f"已到达 {arrived_target or '目标点'}")
        self._log("[小脑] 收到到达事件，触发下一步")
        time.sleep(0.5)
        self._execute_next(event_data=data)

    def _on_dock_completed(self, data):
        with self._lock:
            if not self.is_busy or self.waiting_for_human or self._awaiting_event != "dock_completed":
                return
            self._awaiting_event = None
            self._active_target = ""
        self._set_session_value("current_location", "回充点")
        self._publish_progress("completed", message="回充已完成")
        self._log("[小脑] 收到回充完成事件，触发下一步")
        time.sleep(0.5)
        self._execute_next(event_data=data)

    def _on_human_confirmed(self, data=None):
        with self._lock:
            if (
                not self.is_busy
                or not self.waiting_for_human
                or self._awaiting_event != "human_confirmed"
            ):
                return
            wait_meta = dict(self._active_wait_confirm_meta)
            self.waiting_for_human = False
            self._active_wait_confirm_text = ""
            self._active_wait_confirm_meta = {}
            self._awaiting_event = None
        self._set_session_value("waiting_for_human", False)
        self._set_session_value("human_prompt_text", None)
        self._stop_wait_confirm_reminder()
        phase = str(wait_meta.get("handover_phase", "") or "").strip().lower()
        item_name = str(wait_meta.get("item_name", "") or "").strip()
        if phase == "pickup" and item_name:
            items = self._get_session_list("carrying_items")
            if item_name not in items:
                items.append(item_name)
            self._sync_carrying_state(items)
        elif phase == "dropoff":
            items = self._get_session_list("carrying_items")
            if item_name:
                items = [item for item in items if item != item_name]
            else:
                items = []
            self._sync_carrying_state(items)
        self._publish_progress("completed", message="已收到人工确认，继续执行")
        self._log("[小脑] 收到人类确认事件，继续执行下一步。")
        time.sleep(0.2)
        self._execute_next(event_data=data)

    def _on_action_failed(self, data):
        with self._lock:
            self.is_busy = False
            self.waiting_for_human = False
            self._active_wait_confirm_text = ""
            self._active_wait_confirm_meta = {}
            self._active_target = ""
            self._awaiting_event = None
        self._set_session_value("waiting_for_human", False)
        self._set_session_value("human_prompt_text", None)
        self._stop_wait_confirm_reminder()
        self.last_error = f"action failed: {data}"
        self._publish_progress("failed", message="任务执行失败", detail=str(data))
        with self._lock:
            self._current_task = None
            self._current_step_index = -1
        self._log(f"[小脑] 动作失败，任务终止: {data}")
        self.event_bus.publish("mission_failed", {"error": self.last_error, "detail": data})

    def _start_wait_confirm_reminder(self, reminder_text: str) -> None:
        if not self._wait_reminder_enabled:
            return
        self._stop_wait_confirm_reminder()
        self._wait_reminder_stop.clear()
        text_to_speak = str(reminder_text or "").strip() or self._wait_reminder_text

        def _loop() -> None:
            while not self._wait_reminder_stop.wait(self._wait_reminder_interval_sec):
                with self._lock:
                    if not self.is_busy or not self.waiting_for_human:
                        break
                try:
                    self.adapter.play_audio(text_to_speak)
                except Exception as exc:
                    self._log(f"[小脑] wait_confirm 提醒播报失败: {exc}")

        self._wait_reminder_thread = threading.Thread(
            target=_loop,
            name="mission-wait-confirm-reminder",
            daemon=True,
        )
        self._wait_reminder_thread.start()

    def _stop_wait_confirm_reminder(self) -> None:
        self._wait_reminder_stop.set()
        thread = self._wait_reminder_thread
        if thread and thread.is_alive():
            thread.join(timeout=0.2)
        self._wait_reminder_thread = None
