#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import threading
from datetime import datetime
from typing import Any

from flask import Flask, jsonify, request

app = Flask(__name__)

_MAX_EVENTS = int(os.environ.get("CALLBACK_MAX_EVENTS", "100"))
_EVENTS: list[dict[str, Any]] = []
_EVENTS_LOCK = threading.Lock()


def _parse_event_payload() -> tuple[dict[str, Any], str]:
    raw = request.get_data().decode("utf-8", errors="replace")
    payload = request.get_json(silent=True)

    if isinstance(payload, dict):
        event = dict(payload)
    elif payload is not None:
        event = {"payload": payload}
    elif raw:
        try:
            parsed = json.loads(raw)
            event = parsed if isinstance(parsed, dict) else {"payload": parsed}
        except Exception:
            event = {"raw": raw}
    else:
        event = {}

    return event, raw


def _store_event(event: dict[str, Any], raw: str) -> dict[str, Any]:
    record = {
        "received_at": datetime.now().isoformat(timespec="seconds"),
        "path": request.path,
        "remote_addr": request.remote_addr,
        "headers": {
            "Content-Type": request.headers.get("Content-Type"),
            "User-Agent": request.headers.get("User-Agent"),
        },
        "event": event,
        "raw": raw,
    }

    with _EVENTS_LOCK:
        _EVENTS.append(record)
        if len(_EVENTS) > _MAX_EVENTS:
            del _EVENTS[:-_MAX_EVENTS]
        count = len(_EVENTS)

    device_id = event.get("device_id")
    event_name = event.get("event") or event.get("raw")
    code = event.get("code", event.get("event_code"))
    print(
        f"[callback] count={count} path={record['path']} "
        f"device_id={device_id} event={event_name} code={code} payload={json.dumps(event, ensure_ascii=False)}",
        flush=True,
    )
    return record


@app.route("/", methods=["GET"])
def index():
    return jsonify(
        {
            "ok": True,
            "msg": "callback receiver is running",
            "post_urls": [
                "/",
                "/callback/nav_event",
            ],
            "inspect_urls": [
                "/healthz",
                "/events",
            ],
        }
    )


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"ok": True})


@app.route("/events", methods=["GET"])
def list_events():
    with _EVENTS_LOCK:
        events = list(_EVENTS)
    return jsonify({"ok": True, "count": len(events), "events": events})


@app.route("/", methods=["POST"])
@app.route("/callback/nav_event", methods=["POST"])
@app.route("/callback/nav_event/", methods=["POST"])
def receive():
    event, raw = _parse_event_payload()
    record = _store_event(event, raw)
    return jsonify({"ok": True, "received_at": record["received_at"]}), 200


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导航事件回调接收测试服务")
    parser.add_argument(
        "--host",
        default=os.environ.get("CALLBACK_HOST", "0.0.0.0"),
        help="监听地址，默认 0.0.0.0",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("CALLBACK_PORT", "8081")),
        help="监听端口，默认 8081",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=True,
        help="开启 Flask debug 模式",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    print("callback receiver started", flush=True)
    print(f"listen: http://{args.host}:{args.port}", flush=True)
    print(f"use as callback: http://127.0.0.1:{args.port}/callback/nav_event", flush=True)
    print(f"compatible root url: http://127.0.0.1:{args.port}/", flush=True)
    app.run(host=args.host, port=args.port, debug=args.debug)