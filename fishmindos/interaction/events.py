"""
Canonical event type constants for the FishMindOS interaction layer.

All events emitted by InteractionManager use one of these type strings,
giving channels (terminal, Android gateway, future integrations) a
single source of truth for event names.

Usage
-----
from fishmindos.interaction import events as ev

manager.emit(ev.MESSAGE, session_id=sid, text="好的，正在前往会议室")
"""

from __future__ import annotations

# ── Lifecycle ──────────────────────────────────────────────────────────
THINKING_STARTED = "thinking_started"
THINKING_STOPPED = "thinking_stopped"
INTERACTION_COMPLETE = "interaction_complete"
PROMPT_READY = "prompt_ready"
HUMAN_CONFIRM_REQUIRED = "human_confirm_required"
USER_INPUT = "user_input"

# ── Task execution ─────────────────────────────────────────────────────
PLAN = "plan"
ACTION = "action"
RESULT = "result"
ACTUAL_MISSION_TASKS = "actual_mission_tasks"
ASYNC_MISSION_DONE = "async_mission_done"
MISSION_PROGRESS = "mission_progress"

# ── Text output ────────────────────────────────────────────────────────
MESSAGE = "message"
INFO = "info"
ERROR = "error"

# ── Session ────────────────────────────────────────────────────────────
SESSION_STATE = "session_state"

# ── Keepalive (WebSocket) ──────────────────────────────────────────────
PING = "ping"

# ── All defined types (for validation / logging) ──────────────────────
ALL: frozenset[str] = frozenset(
    {
        THINKING_STARTED,
        THINKING_STOPPED,
        INTERACTION_COMPLETE,
        PROMPT_READY,
        HUMAN_CONFIRM_REQUIRED,
        USER_INPUT,
        PLAN,
        ACTION,
        RESULT,
        ACTUAL_MISSION_TASKS,
        ASYNC_MISSION_DONE,
        MISSION_PROGRESS,
        MESSAGE,
        INFO,
        ERROR,
        SESSION_STATE,
        PING,
    }
)
