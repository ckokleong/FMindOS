from __future__ import annotations

from fishmindos import FishMindOSApp


def main() -> None:
    app = FishMindOSApp()
    text = "到行政拿纸巾送到厕所"
    result = app.run_text(text)

    print(f"任务: {text}")
    print(f"状态: {result['status']}")
    print("执行日志:")
    for event in result["events"]:
        print(f"- [{event.status.value}] {event.step_id}: {event.detail}")


if __name__ == "__main__":
    main()
