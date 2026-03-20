"""
Embedded callback receiver for python -m fishmindos.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional


CallbackHandler = Callable[[Dict[str, Any]], None]


class CallbackReceiver:
    """Small built-in HTTP server compatible with test.py callback routes."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8081,
        path: str = "/callback/nav_event",
        max_events: int = 100,
    ) -> None:
        self.host = host
        self.port = port
        self.path = path if path.startswith("/") else f"/{path}"
        self.max_events = max_events
        self._events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._handlers: List[CallbackHandler] = []
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def add_handler(self, handler: CallbackHandler) -> None:
        self._handlers.append(handler)

    def start(self) -> None:
        if self._server is not None:
            return

        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

            def _write_json(self, status: int, payload: Dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/":
                    self._write_json(
                        200,
                        {
                            "ok": True,
                            "msg": "callback receiver is running",
                            "post_urls": ["/", owner.path],
                            "inspect_urls": ["/healthz", "/events"],
                        },
                    )
                    return

                if self.path == "/healthz":
                    self._write_json(200, {"ok": True})
                    return

                if self.path == "/events":
                    with owner._lock:
                        events = list(owner._events)
                    self._write_json(200, {"ok": True, "count": len(events), "events": events})
                    return

                self._write_json(404, {"ok": False, "msg": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                normalized_paths = {"/", owner.path, owner.path.rstrip("/")}
                if self.path.rstrip("/") not in {p.rstrip("/") for p in normalized_paths}:
                    self._write_json(404, {"ok": False, "msg": "not found"})
                    return

                length = int(self.headers.get("Content-Length", "0") or 0)
                raw_bytes = self.rfile.read(length) if length > 0 else b""
                raw = raw_bytes.decode("utf-8", errors="replace")
                payload = self._parse_payload(raw)
                record = owner._store_event(self.path, self.client_address[0] if self.client_address else None, payload, raw)
                self._write_json(200, {"ok": True, "received_at": record["received_at"]})

            @staticmethod
            def _parse_payload(raw: str) -> Dict[str, Any]:
                if not raw:
                    return {}
                try:
                    parsed = json.loads(raw)
                    return parsed if isinstance(parsed, dict) else {"payload": parsed}
                except Exception:
                    return {"raw": raw}

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="fishmind-callback", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def get_events(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def _store_event(self, path: str, remote_addr: Optional[str], event: Dict[str, Any], raw: str) -> Dict[str, Any]:
        with self._lock:
            self._events.append(
                {
                    "received_at": datetime.now().isoformat(timespec="seconds"),
                    "path": path,
                    "remote_addr": remote_addr,
                    "event": event,
                    "raw": raw,
                }
            )
            if len(self._events) > self.max_events:
                del self._events[:-self.max_events]
            count = len(self._events)
            record = dict(self._events[-1])
            record["count"] = count

        for handler in self._handlers:
            try:
                handler(record)
            except Exception as exc:
                print(f"[Callback] handler failed: {exc}")

        event_name = event.get("event") or event.get("type") or event.get("name") or "unknown"
        print(
            f"[Callback] count={count} path={path} remote={remote_addr} "
            f"event={event_name} payload={json.dumps(event, ensure_ascii=False)}"
        )
        return record
