"""
导航回调相关技能。
"""

from pathlib import Path
from typing import Any, Dict

from fishmindos.config import get_config
from fishmindos.core.models import SkillContext, SkillResult
from fishmindos.skills.base import Skill


class SetCallbackSkill(Skill):
    """设置导航事件回调 URL。"""

    name = "callback_set"
    description = "设置导航事件回调 URL，用于接收导航状态通知"
    category = "system"

    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "回调 URL，例如 http://127.0.0.1:8081/callback/nav_event"
            },
            "enable": {
                "type": "boolean",
                "description": "是否启用回调",
                "default": True
            }
        },
        "required": ["url"]
    }

    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        url = params.get("url")
        enable = params.get("enable", True)

        if not self.adapter:
            return SkillResult(False, "适配器未设置")

        try:
            context.set("callback_url", url)
            context.set("callback_enabled", enable)

            if hasattr(self.adapter, "set_callback_url"):
                success = self.adapter.set_callback_url(url, enable)
                if success:
                    return SkillResult(True, f"回调已设置: {url}", {"url": url, "enabled": enable})
                return SkillResult(False, "设置回调失败")

            return SkillResult(True, f"回调 URL 已保存: {url}（当前适配器不支持）", {"url": url, "enabled": enable})
        except Exception as e:
            return SkillResult(False, f"设置回调异常: {str(e)}")


class GetCallbackStatusSkill(Skill):
    """获取回调状态。"""

    name = "callback_status"
    description = "获取当前回调配置和事件统计"
    category = "system"

    parameters = {
        "type": "object",
        "properties": {}
    }

    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        url = context.get("callback_url", "未设置")
        enabled = context.get("callback_enabled", False)
        event_count = context.get("callback_event_count", 0)
        host = context.get("callback_host")
        port = context.get("callback_port")

        lines = [
            f"回调URL: {url}",
            f"状态: {'启用' if enabled else '禁用'}",
            f"事件数: {event_count}",
        ]
        if host:
            lines.append(f"Host: {host}")
        if port:
            lines.append(f"Port: {port}")

        return SkillResult(True, "\n".join(lines), {
            "url": url,
            "enabled": enabled,
            "event_count": event_count,
            "host": host,
            "port": port,
        })


class StartCallbackServerSkill(Skill):
    """启动本地回调接收服务。"""

    name = "callback_server_start"
    description = "启动本地回调接收服务，行为与单独运行 test.py 一致"
    category = "system"
    expose_as_tool = False

    parameters = {
        "type": "object",
        "properties": {
            "host": {
                "type": "string",
                "description": "监听地址，对应 test.py 的 --host"
            },
            "port": {
                "type": "integer",
                "description": "监听端口，对应 test.py 的 --port",
                "default": 8081
            }
        }
    }

    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        config = get_config()
        callback_config = getattr(config, "callback", None)

        host = params.get("host") or (callback_config.host if callback_config else "0.0.0.0")
        port = params.get("port", callback_config.port if callback_config else 8081)

        try:
            import subprocess
            import sys

            callback_script = Path(__file__).resolve().parents[3] / "test.py"
            if not callback_script.exists():
                return SkillResult(False, f"回调服务脚本不存在: {callback_script}")

            process = subprocess.Popen(
                [sys.executable, str(callback_script), "--host", str(host), "--port", str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            )

            callback_host = "127.0.0.1" if host == "0.0.0.0" else host
            url = f"http://{callback_host}:{port}/callback/nav_event"

            context.set("callback_server_pid", process.pid)
            context.set("callback_server_host", host)
            context.set("callback_server_port", port)
            context.set("callback_url", url)
            context.set("callback_enabled", True)

            if hasattr(self.adapter, "set_callback_url"):
                self.adapter.set_callback_url(url, True)

            return SkillResult(
                True,
                f"回调服务已启动\n监听: http://{host}:{port}\n回调: {url}\n进程ID: {process.pid}",
                {
                    "url": url,
                    "host": host,
                    "port": port,
                    "pid": process.pid,
                },
            )
        except Exception as e:
            return SkillResult(False, f"启动回调服务失败: {str(e)}")
